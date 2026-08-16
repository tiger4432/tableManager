"""One audit row per WRITE, structured — and the five things that proves.

WHAT CHANGED
    `apply_row_update_internal` used to encode the same event two ways. A human
    write emitted ONE ROW PER CHANGED COLUMN; every other writer emitted one
    RENDERED SENTENCE per row-write under the literal `column_name='ROW_UPDATE'`
    (`f"{col}: {val}"` joined on ", ", NULL written as 비어있음). Measured on the
    isolated `assy_qa` copy 2026-08-11: 225,591 of 239,801 audit rows (94.07%)
    were the sentence, and the same 16-column `dt_log` write cost 7,760.0 B as
    per-column rows against 1,008.6 B as a sentence.

    The human path may now stop writing one row per column. It does NOT adopt
    the sentence: both paths write ONE row whose values are JSON OBJECTS.

WHY EACH TEST HERE EXISTS
    The sentence is cheap because it throws data away, so a change that merely
    shrinks the table can be green and wrong in five distinct ways. Each is
    pinned below with a case that FAILS under the rendered encoding:

      1. not cell-addressable -> `test_a_machine_write_is_visible_in_the_cell_tab`
      2. typed values -> `test_integer_zero_and_string_zero_stay_distinct`
      3. NULL vs 비어있음 -> `test_a_null_and_a_cell_holding_the_word_are_distinct`
      4. delimiter ambiguity -> `test_a_value_full_of_delimiters_survives_intact`
      5. truncation granularity -> `test_an_oversized_value_does_not_delete_its_neighbours`

    Plus the two that keep the change from breaking things it did not intend to:
    the re-correction metric must keep counting CELLS, and legacy rows must keep
    reading. Every one of these was verified to go RED with the guard reverted -
    see the mutation table in the lane report.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import audit_changeset
from database import crud, models, schemas
from database.database import Base

#: Namespaced so it can never collide with a real table in the user's
#: (gitignored) table_config.json - a collision pre-empts the shared in-memory
#: SQLite schema and breaks the suite with `no such column`.
T = "auditcs_test_tbl"

TEST_TABLE_CONFIG = {
    T: {
        "business_key": "unit_id",
        "column_types": {"unit_id": "string", "a": "string", "b": "string",
                         "c": "string", "note": "string"},
        "display_columns": ["unit_id", "a", "b", "c", "note"],
    },
}

#: The table the HTTP fixtures already know about (see test_audit_history_paging).
HTTP_TABLE = "raw_table_1"


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TEST_TABLE_CONFIG)
    crud.TABLE_CONFIG.update(TEST_TABLE_CONFIG)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _write(db, unit_id, updates, source="user", by="tester"):
    batch = schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val=unit_id, updates=dict(updates, unit_id=unit_id),
        source_name=source, updated_by=by)])
    crud.apply_batch_updates(db, T, batch)
    db.commit()


def _audit(db, table=None):
    return (db.query(models.AuditLog)
            .filter(models.AuditLog.table_name == (table or T))
            .order_by(models.AuditLog.id).all())


def _changesets(db, table=None):
    return [l for l in _audit(db, table)
            if l.column_name == audit_changeset.ROW_CHANGESET_COLUMN]


# ---------------------------------------------------------------------------
# 0. The saving itself
# ---------------------------------------------------------------------------

def test_a_human_write_of_many_columns_is_one_audit_row(db):
    """THE RULING. Four changed columns used to be four audit rows."""
    _write(db, "u1", {"a": "1", "b": "2", "c": "3"})          # creation
    before = len(_audit(db))
    _write(db, "u1", {"a": "9", "b": "8", "c": "7", "note": "n"})

    added = _audit(db)[before:]
    changesets = [l for l in added
                  if l.column_name == audit_changeset.ROW_CHANGESET_COLUMN]
    assert len(changesets) == 1, [(l.column_name, l.new_value) for l in added]
    # ...and it is one row because it CARRIES the four, not because it dropped three.
    assert set(changesets[0].new_value) == {"a", "b", "c", "note"}


def test_the_payload_is_an_object_and_never_a_sentence(db):
    """The whole constraint. A rendered string here is the regression."""
    _write(db, "u1", {"a": "1"})
    cs = _changesets(db)[-1]
    assert isinstance(cs.new_value, dict), repr(cs.new_value)
    assert not isinstance(cs.new_value, str)


def test_a_machine_write_uses_the_same_shape_as_a_human_one(db):
    """The axis is 'one write touching many columns', not 'who wrote it'."""
    _write(db, "u1", {"a": "1"}, source="pipeline_parser", by="watcher")
    cs = _changesets(db)
    assert len(cs) == 1
    assert isinstance(cs[0].new_value, dict)
    assert cs[0].source_name == "pipeline_parser"


# ---------------------------------------------------------------------------
# 1..5 The five losses
# ---------------------------------------------------------------------------

def test_integer_zero_and_string_zero_stay_distinct(db):
    """LOSS 2. `str(0) == str("0")`, so the sentence cannot tell these apart."""
    _write(db, "u1", {"a": 0, "b": "0"})
    cs = _changesets(db)[-1]
    assert cs.new_value["a"] == 0
    assert cs.new_value["b"] == "0"
    assert cs.new_value["a"] is not cs.new_value["b"]
    assert isinstance(cs.new_value["a"], int) and not isinstance(cs.new_value["a"], str)
    assert isinstance(cs.new_value["b"], str)


def test_a_null_and_a_cell_holding_the_word_are_distinct(db):
    """LOSS 3. The sentence writes NULL as the Korean word 비어있음, so a NULL and
    a cell whose value IS that word become the same characters. 81,523 rows on
    `assy_qa` contain that word today and nothing can say which were NULLs."""
    _write(db, "u1", {"a": "x", "b": "y"})
    _write(db, "u1", {"a": None, "b": audit_changeset.RENDER_NULL})

    cs = _changesets(db)[-1]
    assert cs.new_value["a"] is None                       # a real NULL
    assert cs.new_value["b"] == audit_changeset.RENDER_NULL  # a real string
    assert cs.new_value["a"] != cs.new_value["b"]

    # And the projection keeps them apart, which is what a cell tab shows.
    assert audit_changeset.project(cs.old_value, cs.new_value, "a")[1] is None
    assert audit_changeset.project(cs.old_value, cs.new_value, "b")[1] == "비어있음"


def test_a_value_full_of_delimiters_survives_intact(db):
    """LOSS 4. Joined on ", ", read back by splitting on ": ", nothing escaped.
    This exact value shape is live: a `wafer_map_metadata` row reads
    `grid_metadata: {"grid_cols": 2, "grid_rows": 2, ...}`, so a reader splitting
    the sentence invents a column called `"grid_rows"`."""
    nasty = '{"grid_cols": 2, "grid_rows": 2, "note": "a, b: c"}'
    _write(db, "u1", {"a": nasty, "b": "plain"})

    cs = _changesets(db)[-1]
    assert cs.new_value["a"] == nasty          # byte-for-byte, no escaping needed
    assert cs.new_value["b"] == "plain"
    assert set(cs.new_value) == {"unit_id", "a", "b"}   # no invented column
    assert "grid_rows" not in cs.new_value


def test_an_oversized_value_does_not_delete_its_neighbours(db):
    """LOSS 5. The 4,096-char cap used to apply to the whole concatenation, so
    one long cell deleted every column after it from the record entirely."""
    from event_constants import MAX_AUDIT_VALUE_CHARS
    huge = "X" * (MAX_AUDIT_VALUE_CHARS + 500)
    _write(db, "u1", {"a": huge, "b": "still here", "c": "and me"})

    cs = _changesets(db)[-1]
    assert cs.new_value["b"] == "still here"
    assert cs.new_value["c"] == "and me"
    # the oversized one is capped, and SAYS it was capped
    assert len(cs.new_value["a"]) < len(huge)
    assert "truncated" in cs.new_value["a"]


def test_a_whole_changeset_is_never_replaced_by_a_truncation_placeholder(db):
    """The guard in `create_audit_log`. `truncate_audit_value` REPLACES a dict
    (it does not shorten one), so without the exemption a wide-enough write
    would collapse the entire record into '[truncated: dict ...]'."""
    _write(db, "u1", {"a": "A" * 3000, "b": "B" * 3000, "c": "C" * 3000})
    cs = _changesets(db)[-1]
    assert isinstance(cs.new_value, dict)               # not a placeholder string
    assert {"a", "b", "c"} <= set(cs.new_value)
    assert cs.new_value["a"].startswith("AAA")


# ---------------------------------------------------------------------------
# The reader: projection, rendering, and both legacy shapes
# ---------------------------------------------------------------------------

def _seed_log(db, *, row, col, old, new, table=HTTP_TABLE, source="probe",
              tx=None, when=None):
    db.add(models.AuditLog(
        table_name=table, row_id=row, column_name=col,
        old_value=old, new_value=new, source_name=source, updated_by="probe",
        transaction_id=tx or str(uuid.uuid4()),
        timestamp=when or datetime(2026, 1, 1, tzinfo=timezone.utc)))
    db.commit()


def _cell(client, row, col, table=HTTP_TABLE):
    r = client.get(f"/tables/{table}/rows/{row}/cells/{col}/history")
    assert r.status_code == 200, r.text
    return r.json()


def _row_page(client, row, table=HTTP_TABLE):
    r = client.get(f"/tables/{table}/rows/{row}/history")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_machine_write_is_visible_in_the_cell_tab(client, db_session):
    """LOSS 1, and the one a user actually reported as 'no history'. A row-level
    entry is found BY QUERYING THE STRUCTURE and projected to the column asked
    for. Measured on `assy_qa`: 225,101 rows had history and an empty cell tab."""
    row = str(uuid.uuid4())
    _seed_log(db_session, row=row, col=audit_changeset.ROW_CHANGESET_COLUMN,
              old={"EQP_ID": "E1", "LOT": "L1"}, new={"EQP_ID": "E2", "LOT": "L2"})

    page = _cell(client, row, "EQP_ID")
    assert page["returned"] == 1, page
    log = page["logs"][0]
    # projected into the per-column shape the client already renders
    assert log["column_name"] == "EQP_ID"
    assert log["old_value"] == "E1"
    assert log["new_value"] == "E2"


def test_a_column_the_write_did_not_touch_stays_empty(client, db_session):
    """The other half of the above. A found-everything filter would be as wrong
    as a found-nothing one, just less visibly."""
    row = str(uuid.uuid4())
    _seed_log(db_session, row=row, col=audit_changeset.ROW_CHANGESET_COLUMN,
              old={"EQP_ID": "E1"}, new={"EQP_ID": "E2"})

    page = _cell(client, row, "LOT")
    assert page["returned"] == 0
    # ...and it SAYS the row has history it cannot show - the disclosure that
    # `row_history_total` exists for, which this change does NOT make redundant.
    assert page["row_history_total"] == 1


def test_a_key_present_with_a_null_value_is_found_not_skipped(client, db_session):
    """Clearing a cell is a change. `key in payload` must decide, not truthiness -
    otherwise 'the user emptied this cell' silently vanishes from its history."""
    row = str(uuid.uuid4())
    _seed_log(db_session, row=row, col=audit_changeset.ROW_CHANGESET_COLUMN,
              old={"EQP_ID": "E1"}, new={"EQP_ID": None})

    page = _cell(client, row, "EQP_ID")
    assert page["returned"] == 1
    assert page["logs"][0]["new_value"] is None


def test_a_legacy_per_column_row_still_reads(client, db_session):
    """History is append-only; old rows are NOT migrated. This shape must keep
    working forever."""
    row = str(uuid.uuid4())
    _seed_log(db_session, row=row, col="EQP_ID", old="old", new="new")

    page = _cell(client, row, "EQP_ID")
    assert page["returned"] == 1
    assert page["logs"][0]["new_value"] == "new"


def test_a_legacy_rendered_summary_is_not_column_addressed(client, db_session):
    """🔴 THE REFUSAL. The old sentence cannot be column-addressed without
    splitting presentation back into data, which is loss 4 - so it is left out
    and the row-total disclosure speaks for it. A confidently wrong history is
    worse than an absent one."""
    row = str(uuid.uuid4())
    _seed_log(db_session, row=row, col=audit_changeset.ROW_CHANGESET_COLUMN,
              old=None, new="신규 데이터 생성: EQP_ID: E2, LOT: 비어있음")

    page = _cell(client, row, "EQP_ID")
    assert page["returned"] == 0
    assert page["row_history_total"] == 1     # "records exist, this screen can't show them"

    # It still reads on the ROW tab, unchanged and unparsed.
    assert _row_page(client, row)["logs"][0]["new_value"].startswith("신규 데이터 생성: ")


def test_a_legacy_string_equal_to_a_column_name_is_not_that_cells_history(client, db_session):
    """⚠️ POSTGRESQL HAZARD, pinned on both dialects. `jsonb`'s `?` operator on a
    STRING tests string equality, so `'"EQP_ID"'::jsonb ? 'EQP_ID'` is TRUE.
    Without the `jsonb_typeof(...) = 'object'` guard this legacy row would be
    served as EQP_ID's history. Probed on assy_qa 2026-08-11: it matches without
    the guard, and does not with it."""
    row = str(uuid.uuid4())
    _seed_log(db_session, row=row, col=audit_changeset.ROW_CHANGESET_COLUMN,
              old=None, new="EQP_ID")

    assert _cell(client, row, "EQP_ID")["returned"] == 0


def test_an_object_valued_cell_does_not_leak_into_another_columns_tab(client, db_session):
    """⚠️ The sentinel guard, and this one is not hypothetical: production has a
    `wafer_map_metadata.grid_metadata` cell whose VALUE is
    `{"grid_cols": 2, "grid_rows": 2, ...}`. Matching on payload keys alone would
    serve that cell's history as the history of a column called `grid_rows`."""
    row = str(uuid.uuid4())
    _seed_log(db_session, row=row, col="grid_metadata",
              old=None, new={"grid_cols": 2, "grid_rows": 2})

    assert _cell(client, row, "grid_rows")["returned"] == 0
    assert _cell(client, row, "grid_metadata")["returned"] == 1


def test_the_row_tab_renders_the_sentence_the_summary_used_to_store(client, db_session):
    """Presentation computed from data. The client prints `new_value` directly
    (client2/src/timeline.js), so the row tab must keep looking exactly as it did
    - including 비어있음 for a NULL, which is now a RENDERING and not a record."""
    row = str(uuid.uuid4())
    _seed_log(db_session, row=row, col=audit_changeset.ROW_CHANGESET_COLUMN,
              old=None, new={"EQP_ID": "E2", "LOT": None})

    log = _row_page(client, row)["logs"][0]
    assert log["column_name"] == audit_changeset.ROW_CHANGESET_COLUMN
    assert log["new_value"] == "신규 데이터 생성: EQP_ID: E2, LOT: 비어있음"
    # ...while the STRUCTURE travels alongside it, so no client ever has to parse
    # that string to recover the columns.
    assert log["changes"] == {"EQP_ID": [None, "E2"], "LOT": [None, None]}


def test_a_non_changeset_entry_carries_no_changes_field(client, db_session):
    """`changes` is None for every other shape, so its presence is a reliable
    signal rather than something a client has to sniff."""
    row = str(uuid.uuid4())
    _seed_log(db_session, row=row, col="EQP_ID", old="a", new="b")
    assert _row_page(client, row)["logs"][0]["changes"] is None


# ---------------------------------------------------------------------------
# The re-correction metric must keep counting CELLS
# ---------------------------------------------------------------------------

def _user_cs(db, *, row, cols, tx, days_ago=1, table="recorr_cs_tbl"):
    db.add(models.AuditLog(
        table_name=table, row_id=row,
        column_name=audit_changeset.ROW_CHANGESET_COLUMN,
        old_value={c: "before" for c in cols}, new_value={c: "after" for c in cols},
        source_name=crud.USER_SOURCE, updated_by="tester", transaction_id=tx,
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago)))


def test_a_changeset_counts_one_cell_per_column_not_one_per_row(db_session):
    """🔴 THE SILENT REDEFINITION THIS CHANGE COULD HAVE CAUSED. The metric's
    denominator is CELLS = (table, row, column). Leaving `get_recorrection_stats`
    grouping on `column_name` would have made every human write group under the
    literal `ROW_UPDATE`, collapsing three cells into one row. Doing NOTHING was
    the way to break this, which is why it is pinned."""
    _user_cs(db_session, row="r1", cols=["a", "b", "c"], tx="tx-1")
    db_session.commit()

    s = crud.get_recorrection_stats(db_session, window_days=7)
    assert s["measured_cells"] == 3          # not 1
    assert s["recorrected_cells"] == 0


def test_two_transactions_on_different_columns_of_one_row_are_not_a_re_correction(db_session):
    """The inflation half. Grouping by row would call this a re-correction; the
    user corrected two DIFFERENT cells and re-corrected nothing."""
    _user_cs(db_session, row="r1", cols=["a"], tx="tx-1")
    _user_cs(db_session, row="r1", cols=["b"], tx="tx-2")
    db_session.commit()

    s = crud.get_recorrection_stats(db_session, window_days=7)
    assert s["measured_cells"] == 2
    assert s["recorrected_cells"] == 0


def test_the_same_column_in_two_transactions_is_still_a_re_correction(db_session):
    """And the metric still detects the thing it exists to detect."""
    _user_cs(db_session, row="r1", cols=["a", "b"], tx="tx-1")
    _user_cs(db_session, row="r1", cols=["a"], tx="tx-2")
    db_session.commit()

    s = crud.get_recorrection_stats(db_session, window_days=7)
    assert s["measured_cells"] == 2
    assert s["recorrected_cells"] == 1       # (r1, a)


def test_legacy_and_changeset_rows_are_counted_together(db_session):
    """The transition week. History is append-only, so both shapes sit inside the
    same 7-day window; counting only one silently halves the number."""
    db_session.add(models.AuditLog(
        table_name="recorr_cs_tbl", row_id="r1", column_name="legacy_col",
        old_value="before", new_value="after", source_name=crud.USER_SOURCE,
        updated_by="tester", transaction_id="tx-0",
        timestamp=datetime.now(timezone.utc) - timedelta(days=1)))
    _user_cs(db_session, row="r1", cols=["a"], tx="tx-1")
    db_session.commit()

    s = crud.get_recorrection_stats(db_session, window_days=7)
    assert s["measured_cells"] == 2


# ---------------------------------------------------------------------------
# summary_columns
# ---------------------------------------------------------------------------

def test_a_transaction_header_lists_real_columns_not_the_sentinel(db_session):
    """The timeline header used to show one column called `ROW_UPDATE` for every
    machine transaction. It is built from the payload now."""
    class _L:
        column_name = audit_changeset.ROW_CHANGESET_COLUMN
        new_value = {"a": 1, "b": 2}
    assert audit_changeset.summary_columns_for(_L()) == ["a", "b"]


def test_a_legacy_summary_header_falls_back_to_the_literal(db_session):
    """It does NOT split the sentence to invent column names (loss 4)."""
    class _L:
        column_name = audit_changeset.ROW_CHANGESET_COLUMN
        new_value = "a: 1, b: 2"
    assert audit_changeset.summary_columns_for(_L()) == ["ROW_UPDATE"]
