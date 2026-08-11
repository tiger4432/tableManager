"""The write path can say "I accepted 900 of your 1,000 keys, and here is what I dropped".

WHY THIS EXISTS
---------------
`crud.apply_batch_updates` had two possible answers: raise, or return the 4-tuple that
means success. It had no vocabulary for PARTIAL failure, so every partial discard had to
pick one - and it picked success. That is the 2026-08-11 production incident end to end:

    config declares `dt_job` / the box sends `dt_job_id`
      -> the key is not in `column_types`, so it is dropped
      -> 200 SUCCESS is returned
      -> a row lands in `dt_inventory` with no identity
      -> the alignment worklist composes a unit key from that row and 500s the request

`347de78` made the drop COUNTABLE for an operator reading `/health`
(`undeclared_column_drops()` + the heartbeat note). It did nothing for the CALLER: a
process-lifetime counter has no batch, no row and no transaction in it, so "is this
deployment losing a column?" became answerable while "did MY write land?" did not.

TWO THINGS ARE PINNED HERE
    1. `drop_report={}` - an out-parameter with the same contract `replace_report`
       already has - tells the caller which update keys were discarded, on which rows,
       and under which reason name.
    2. A row that exists ONLY because we threw away everything the caller sent is not
       created at all. It used to be INSERTed carrying nothing but a `row_id`, returned
       as `is_new=True`, and announced as a CREATE.

MUTATION SCORING
Each test names the guard whose removal turns it red. Three cases are scored SEPARATELY -
none dropped, some dropped, every key dropped - because a test that only exercises the
case that already worked proves nothing.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from database.database import Base
from database import crud, models, schemas


#: A prefix that cannot exist in the user's own (gitignored) `table_config.json`. A
#: collision there lets `init_dynamic_models` win the race for the shared in-memory
#: sqlite schema and the suite fails with `no such column` - the `bonding_log` incident
#: in the server-pm lessons file.
PLAIN = "dropreport_test_plain"
COMPOSITE = "dropreport_test_composite"
VERSIONED = "dropreport_test_versioned"

TEST_TABLE_CONFIG = {
    PLAIN: {
        "business_key": "unit_id",
        "column_types": {"unit_id": "string", "payload": "string", "note": "string"},
        "display_columns": ["unit_id", "payload", "note"],
    },
    # The incident's shape: the business key is assembled from two source columns, and
    # one of them is the column the sender spells differently.
    COMPOSITE: {
        "business_key": "map_pk",
        "composite_key_source": ["map_id", "die_no"],
        "composite_key_separator": "_",
        "column_types": {"map_pk": "string", "map_id": "string", "die_no": "string",
                         "payload": "string"},
        "display_columns": ["map_pk", "map_id", "die_no", "payload"],
    },
    VERSIONED: {
        "business_key": "unit_id",
        "version_column": "rev",
        "column_types": {"unit_id": "string", "rev": "number", "payload": "string"},
        "display_columns": ["unit_id", "rev", "payload"],
    },
}


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


def _push(db, table, items, drop_report=None, **kw):
    batch = schemas.GeneralUpdateBatch(updates=items, **kw)
    return crud.apply_batch_updates(db, table, batch, None, drop_report)


def _item(**kw):
    kw.setdefault("source_name", "pipeline_parser")
    kw.setdefault("updated_by", "watcher")
    return schemas.GeneralUpdateItem(**kw)


def _rows(db, table):
    return db.query(models.DYNAMIC_TABLES[table]).all()


def _outbox(db, event_type=None):
    q = db.query(models.DatabaseOutbox)
    events = q.all()
    if event_type:
        events = [e for e in events if e.event_type == event_type]
    return events


# ---------------------------------------------------------------------------
# 1. The phantom row: every key dropped
# ---------------------------------------------------------------------------

def test_a_payload_whose_every_key_is_undeclared_creates_no_row(db):
    """KILLS: deleting the phantom-row `expunge` guard in `_apply_batch_updates_once`.

    MEASURED BEFORE THE GUARD (2026-08-11): one row, `business_key_val` NULL, every
    column NULL, returned as `is_new=True`, plus a staged CREATE outbox event. A record
    that exists and asserts nothing is worse than a refusal - downstream has a row to
    trust, which is precisely what the alignment worklist did before it 500'd.
    """
    results, changed, logs, deleted = _push(db, PLAIN, [
        _item(updates={"unit_id_TYPO": "U1", "payload_TYPO": "P"})])

    assert _rows(db, PLAIN) == [], "a row was fabricated out of a payload we discarded"
    assert results == [], "the caller was handed a row that does not exist"
    assert changed == [] and logs == []
    assert deleted == [], "nothing was deleted - the row was never created"


def test_the_suppressed_row_announces_no_create_event(db):
    """KILLS: the same guard. Separately scored because the outbox is a DIFFERENT
    consumer from the return value - `auto_stage_database_outbox` walks `session.new`,
    so a guard that only cleaned up `unique_results` would still broadcast the ghost."""
    _push(db, PLAIN, [_item(updates={"unit_id_TYPO": "U1"})])

    assert _outbox(db) == [], "a CREATE was announced for a row that was never written"


def test_a_supplied_business_key_does_not_rescue_the_row(db):
    """The production shape, and the reason this is data corruption rather than waste.

    MEASURED BEFORE THE GUARD: the item carried `business_key_val='U3'`, and the stored
    row still had `business_key_val` NULL - `_update_row_business_key` reads
    `updates[key_col]`, and the key column was the one being dropped. So the next push of
    the SAME key created ANOTHER identity-less row, without limit.
    """
    _push(db, PLAIN, [_item(business_key_val="U3",
                            updates={"unit_id_TYPO": "U3", "payload_TYPO": "P"})])
    _push(db, PLAIN, [_item(business_key_val="U3",
                            updates={"unit_id_TYPO": "U3", "payload_TYPO": "P"})])

    assert _rows(db, PLAIN) == [], "two pushes of one key minted two anonymous rows"


def test_a_payload_of_only_system_columns_creates_no_row(db):
    """KILLS: removing `DROP_SYSTEM_COLUMN` accounting from the `system_cols` branch.

    The system-column skip was the branch nobody had even counted. Without it recorded
    as a discard, `rows_with_drops` stays empty for this payload and the phantom guard
    never fires.
    """
    _push(db, PLAIN, [_item(updates={"updated_by": "x", "row_id": "nope"})])

    assert _rows(db, PLAIN) == []


def test_an_empty_payload_keeps_todays_behaviour_exactly(db):
    """THE BOUNDARY, asserted so nobody widens the guard by accident.

    `updates={}` discards nothing - it is the caller's own statement that it wants a row
    with no columns, the same thing `create_empty_rows_batch` does deliberately. Turning
    that into a refusal is a POLICY change about contentless inserts, and this lane is
    visibility only. The guard therefore requires that at least one key was DISCARDED.
    """
    results, _c, _l, _d = _push(db, PLAIN, [_item(updates={})])

    assert len(_rows(db, PLAIN)) == 1, "the guard swallowed a write it used to accept"
    assert len(results) == 1


def test_an_empty_payload_survives_a_batch_that_also_has_a_dropped_row(db):
    """KILLS: dropping the `r_id in rows_with_drops` membership test.

    ⚠️ THE SINGLE-ITEM VERSION ABOVE CANNOT KILL THAT MUTATION, which is why this test
    exists as well. When a batch drops nothing at all, the guard's OUTER gate
    (`if drop_stats["rows_with_drops"]`) is already false and the inner membership test
    is unreachable - so removing the inner test changed no behaviour and the batch of one
    stayed green. The two conditions only separate inside a batch that contains BOTH: one
    row whose keys were discarded, and one row the caller deliberately sent empty. Only
    the first may be suppressed.
    """
    results, _c, _l, _d = _push(db, PLAIN, [
        _item(updates={}),
        _item(business_key_val="U2", updates={"unit_id_TYPO": "U2"}),
    ])

    assert len(_rows(db, PLAIN)) == 1, \
        "the deliberately-empty row was suppressed by a neighbour's dropped key"
    assert len(results) == 1


# ---------------------------------------------------------------------------
# 2. A partial drop still writes. Visibility first; no new refusals.
# ---------------------------------------------------------------------------

def test_a_partial_drop_still_writes_every_declared_column(db):
    """KILLS: any widening of the phantom guard from "no content" to "any drop".

    This is the case the brief forbids breaking: one bad key must never cost the other
    999. The row lands, it is returned, and the declared columns hold their values.
    """
    results, changed, _l, _d = _push(db, PLAIN, [
        _item(business_key_val="U9",
              updates={"unit_id": "U9", "payload": "P", "typo_col": "X"})])

    rows = _rows(db, PLAIN)
    assert len(rows) == 1
    assert rows[0].unit_id == "U9" and rows[0].payload == "P"
    assert rows[0].business_key_val == "U9"
    assert len(results) == 1 and results[0][1] is True
    assert sorted(c for _r, c in changed) == ["payload", "unit_id"]


def test_the_incident_shape_is_written_and_reported_not_refused(db):
    """The production defect itself: a composite-key source column is spelled
    differently, so the row lands with its decision key NULL. It must still be WRITTEN
    (refusing would turn a lagging config into an outage) and it must now be REPORTED."""
    report = {}
    _push(db, COMPOSITE, [
        _item(updates={"map_id": "M1", "die_no_TYPO": "7", "payload": "P"})],
        drop_report=report)

    rows = _rows(db, COMPOSITE)
    assert len(rows) == 1, "the write carried real content and must not be refused"
    assert rows[0].die_no is None and rows[0].business_key_val is None, \
        "this is the shape the worklist chokes on - if it changed, re-read this test"
    assert report["dropped_cells"] == 1
    assert report["by_column"] == {"die_no_TYPO": 1}
    assert report["rows"][0]["columns"] == {"die_no_TYPO": crud.DROP_UNDECLARED_COLUMN}
    assert report["empty_rows_suppressed"] == 0


# ---------------------------------------------------------------------------
# 3. The report itself - three cases scored separately
# ---------------------------------------------------------------------------

def test_none_dropped_reports_zero_in_a_stable_shape(db):
    """A caller must be able to read `dropped_cells` without first testing for the key,
    or the healthy path and the "nobody filled it in" path look identical again."""
    report = {}
    _push(db, PLAIN, [_item(business_key_val="U1",
                            updates={"unit_id": "U1", "payload": "P"})],
          drop_report=report)

    assert report["dropped_cells"] == 0
    assert report["by_reason"] == {} and report["by_column"] == {}
    assert report["rows"] == [] and report["rows_affected"] == 0
    assert report["empty_rows_suppressed"] == 0
    assert report["table"] == PLAIN


def test_some_dropped_names_the_column_the_row_and_the_reason(db):
    """KILLS: removing the `_record_dropped_cell` call from the undeclared-column branch.

    Two of three rows lose a key. The report has to survive being read by someone who
    has to go and FIX it, so it carries the caller's own handle on the record - the
    business key it sent - and not only an opaque `row_id`.
    """
    report = {}
    _push(db, PLAIN, [
        _item(business_key_val="U1", updates={"unit_id": "U1", "payload": "P"}),
        _item(business_key_val="U2", updates={"unit_id": "U2", "payload": "P",
                                              "dt_job_id": "J1"}),
        _item(business_key_val="U3", updates={"unit_id": "U3", "payload": "P",
                                              "dt_job_id": "J2", "extra": "E"}),
    ], drop_report=report)

    assert report["dropped_cells"] == 3
    assert report["by_reason"] == {crud.DROP_UNDECLARED_COLUMN: 3}
    assert report["by_column"] == {"dt_job_id": 2, "extra": 1}
    assert report["rows_affected"] == 2, "the healthy row must not be counted as damaged"
    assert report["rows_omitted"] == 0
    assert sorted(r["business_key_val"] for r in report["rows"]) == ["U2", "U3"]
    by_key = {r["business_key_val"]: r["columns"] for r in report["rows"]}
    assert by_key["U2"] == {"dt_job_id": crud.DROP_UNDECLARED_COLUMN}
    assert by_key["U3"] == {"dt_job_id": crud.DROP_UNDECLARED_COLUMN,
                            "extra": crud.DROP_UNDECLARED_COLUMN}
    # And the write still landed for all three.
    assert len(_rows(db, PLAIN)) == 3


def test_every_key_dropped_is_reported_as_a_suppressed_row(db):
    """KILLS: the phantom guard (`empty_rows_suppressed` falls to 0 and a row appears).

    The all-dropped case must be DISTINGUISHABLE from the some-dropped case in the
    report, not merely absent from the database - "nothing happened" and "we refused to
    fabricate a record for you" are different pieces of news.
    """
    report = {}
    results, _c, _l, _d = _push(db, PLAIN, [
        _item(business_key_val="U1", updates={"unit_id": "U1", "payload": "P"}),
        _item(business_key_val="U2", updates={"unit_id_TYPO": "U2", "payload_TYPO": "P"}),
    ], drop_report=report)

    assert report["empty_rows_suppressed"] == 1
    assert report["empty_rows"][0]["business_key_val"] == "U2", \
        "the operator has to be able to tell WHICH record vanished"
    assert report["dropped_cells"] == 2
    assert report["rows_affected"] == 1
    # The healthy sibling was untouched: one bad row never costs the good ones.
    assert len(_rows(db, PLAIN)) == 1 and len(results) == 1
    assert _rows(db, PLAIN)[0].unit_id == "U1"


def test_a_system_column_drop_is_reported_under_its_own_reason(db):
    """KILLS: reusing `DROP_UNDECLARED_COLUMN` for the system-column branch. The two
    need different fixes by different people - one is a config edit, one is a sender
    bug - so folding them into one count is the same silence in a smaller font.

    ⚠️ THE REASON NAMES ARE ASSERTED AS LITERALS, and the first draft of this test did
    not do that: it compared against `crud.DROP_SYSTEM_COLUMN`, so redefining that
    constant to `"undeclared_column"` moved the expectation with the mutation and the
    test stayed green. These strings are a caller-facing vocabulary - pinning the
    constant to itself pins nothing.
    """
    report = {}
    _push(db, PLAIN, [_item(business_key_val="U1",
                            updates={"unit_id": "U1", "updated_at": "2020-01-01"})],
          drop_report=report)

    assert crud.DROP_SYSTEM_COLUMN == "system_column"
    assert crud.DROP_UNDECLARED_COLUMN == "undeclared_column"
    assert report["by_reason"] == {"system_column": 1}
    assert report["rows"][0]["columns"] == {"updated_at": "system_column"}
    assert len(_rows(db, PLAIN)) == 1, "the declared column still had to be written"


# ---------------------------------------------------------------------------
# 4. The report is bounded - names come from the payload
# ---------------------------------------------------------------------------

def test_the_row_sample_is_capped_and_says_how_much_it_withheld(db, monkeypatch):
    """Row ids and column names come from the payload, so at 10M rows an uncapped report
    is an out-of-memory error dressed as diagnostics. Counts are never capped; detail is."""
    monkeypatch.setattr(crud, "MAX_DROP_REPORT_ROWS", 3)
    report = {}
    _push(db, PLAIN, [
        _item(business_key_val=f"U{i}", updates={"unit_id": f"U{i}", "typo": "X"})
        for i in range(10)
    ], drop_report=report)

    assert report["dropped_cells"] == 10, "the COUNT must not be capped"
    assert report["rows_affected"] == 10
    assert len(report["rows"]) == 3
    assert report["rows_omitted"] == 7


def test_the_column_census_is_capped_and_says_how_much_it_withheld(db, monkeypatch):
    """A malformed header row can mint unbounded distinct column names - the same hazard
    `_MAX_UNDECLARED_WARNED_PER_TABLE` exists for."""
    monkeypatch.setattr(crud, "MAX_DROP_REPORT_COLUMNS", 4)
    report = {}
    updates = {"unit_id": "U1"}
    for i in range(10):
        updates[f"junk_{i:02d}"] = "v"
    _push(db, PLAIN, [_item(business_key_val="U1", updates=updates)], drop_report=report)

    assert report["dropped_cells"] == 10
    assert len(report["by_column"]) == 4
    assert report["columns_omitted"] == 6


# ---------------------------------------------------------------------------
# 5. The guard's scope: it may only ever suppress a row it caused
# ---------------------------------------------------------------------------

def test_an_existing_row_is_never_removed_by_the_guard(db):
    """KILLS: relaxing the `was_new` condition.

    ⚠️ THE DATABASE ASSERTIONS BELOW CANNOT KILL THAT MUTATION ON THEIR OWN, and the
    first draft of this test had only those. `expunge` on a PERSISTENT row detaches it
    from the session; it emits no DELETE, so the row survives in the table and every
    row-count assertion stays green. What actually changes is that the caller stops being
    told about the row - it drops out of `results`, so the API layer broadcasts nothing
    for it and the grid never learns the write was processed. That is the assertion with
    teeth here.
    """
    _push(db, PLAIN, [_item(business_key_val="U1",
                            updates={"unit_id": "U1", "payload": "P"})])
    before = _rows(db, PLAIN)[0].row_id

    results, _c, _l, deleted = _push(db, PLAIN, [
        _item(business_key_val="U1", updates={"unit_id_TYPO": "U1", "payload_TYPO": "Q"})])

    rows = _rows(db, PLAIN)
    assert len(rows) == 1 and rows[0].row_id == before
    assert rows[0].payload == "P", "an existing value was destroyed by a dropped key"
    assert [r.row_id for r, _n in results] == [before], \
        "an existing row stopped being reported to the caller"
    assert deleted == []


def test_a_later_item_filling_the_same_row_prevents_suppression(db):
    """KILLS: deciding suppression per ITEM instead of per ROW.

    Item 1 drops every key of a row it creates; item 2 names the same business key and
    carries a declared column. The row is real and must survive - a per-item guard would
    expunge an object item 2 had already written into, and the write would vanish at
    flush time with nothing raised.
    """
    results, _c, _l, _d = _push(db, PLAIN, [
        _item(business_key_val="U1", updates={"unit_id": "U1"}),
        _item(business_key_val="U1", updates={"unit_id_TYPO": "U1"}),
    ], drop_report={})

    rows = _rows(db, PLAIN)
    assert len(rows) == 1, "the row item 1 legitimately created was thrown away"
    assert rows[0].unit_id == "U1"
    assert len(results) == 1


def test_no_orphan_cell_metadata_survives_a_suppressed_row(db):
    """The suppressed row must leave nothing behind in the metadata tables either.

    This is an argument the guard relies on rather than re-checks: `has_changed` is
    unconditionally True on an insert, so a new row with an empty `changed_cols`
    provably accumulated no `cell_sources` and no `cell_overwrites`. If that ever stops
    being true, this test is where it surfaces.
    """
    _push(db, PLAIN, [_item(updates={"unit_id_TYPO": "U1", "payload_TYPO": "P"})])

    assert db.query(models.CellSource).count() == 0
    assert db.query(models.CellOverwrite).count() == 0
    assert db.query(models.AuditLog).count() == 0


# ---------------------------------------------------------------------------
# 6. Whole-row refusals reach the caller too
# ---------------------------------------------------------------------------

def test_a_version_gate_refusal_reaches_the_caller_by_name(db):
    """The version gate discards EVERY key of a row and counted itself only into a log
    line. A caller holding `drop_report` now sees the refusal under its own reason
    name."""
    _push(db, VERSIONED, [_item(business_key_val="U1",
                                updates={"unit_id": "U1", "rev": 5, "payload": "NEW"})])
    report = {}
    _push(db, VERSIONED, [_item(business_key_val="U1",
                                updates={"unit_id": "U1", "rev": 2, "payload": "OLD"})],
          drop_report=report)

    assert report["rows_refused"] == {crud.REASON_VERSION_OLDER: 1}
    assert _rows(db, VERSIONED)[0].payload == "NEW", "a superseded file overwrote current"


# ---------------------------------------------------------------------------
# 7. The out-param contract: no existing call site changes
# ---------------------------------------------------------------------------

def test_the_four_tuple_is_unchanged_for_a_caller_that_asks_for_nothing(db):
    """Every production call site unpacks 4 values from a 3-argument call. Both have to
    keep working untouched, or this whole out-parameter design was pointless."""
    batch = schemas.GeneralUpdateBatch(updates=[
        _item(business_key_val="U1", updates={"unit_id": "U1", "payload": "P"})])
    out = crud.apply_batch_updates(db, PLAIN, batch)

    assert len(out) == 4
    results, changed, logs, deleted = out
    assert len(results) == 1 and deleted == []


def test_replace_report_still_rides_in_its_own_positional_slot(db):
    """`main.py` passes `replace_report` POSITIONALLY through `run_in_threadpool`, so a
    new parameter inserted before it would corrupt the API layer's purge report."""
    batch = schemas.GeneralUpdateBatch(
        updates=[_item(business_key_val="U1", updates={"unit_id": "U1", "payload": "P"},
                       source_name="user", updated_by="tester")],
        replace_map=True, scope={"payload": "P"})
    report = {}
    crud.apply_batch_updates(db, PLAIN, batch, report)

    assert report["filters"] == {"payload": "P"}
    assert "deleted" in report and "mode" in report


def test_a_replayed_attempt_reports_only_the_transaction_that_committed(monkeypatch):
    """KILLS: removing `drop_report.clear()` from the retry loop.

    A rolled-back attempt wrote nothing, so its drops describe a transaction that never
    happened. Leaving them in the dict makes a recovered race look like data loss.
    """
    from test_business_key_conflict_retry import FakeDB, FakeBatch, _pg_error

    seen = {}

    def fake_once(db, table_name, batch, replace_report=None, drop_report=None):
        if not seen:
            seen["first"] = True
            drop_report["dropped_cells"] = 999
            drop_report["by_column"] = {"ghost": 999}
            raise _pg_error("uq_bk_dt_log")
        drop_report["dropped_cells"] = 1
        return ([], [], [], [])

    monkeypatch.setattr(crud, "_apply_batch_updates_once", fake_once)
    report = {}
    crud.apply_batch_updates(FakeDB(), "dt_log", FakeBatch(), None, report)

    assert report == {"dropped_cells": 1}, "the abandoned attempt's drops were reported"
