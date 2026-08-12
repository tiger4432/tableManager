"""[P3] The batch write path resolves row identity SET-WISE, once per chunk.

A 100,000-row map file used to cost 301,222 SQL statements - 3.01 per data row -
and 65% of its wall clock was Python and SQLAlchemy rather than the database.
Three of those costs are attacked here, and each one is a place where "faster"
and "wrong" are one edit apart:

  1. Two identity SELECTs per row (`_get_or_create_row` -> `get_row_by_business_key`,
     and the composite-key collision probe). Both are replaced by reading the proof
     the batch prefetch already produced - `ProbedIdentity`.
  2. One `INSERT ... RETURNING` per new row, because `updated_at=func.now()` put a
     SQL expression in the parameter set and SQLAlchemy cannot batch those.
  3. `bulk_upsert_cell_sources` building a fresh multi-row VALUES clause per chunk.

🔴 WHAT THESE TESTS ARE REALLY GUARDING. A statement-count assertion alone would
pass for an implementation that stopped looking up rows at all - which is to say
one that duplicates every row it should have matched, and drops the `user` layer
of every cell it should have merged. So every budget assertion here is paired
with an assertion about what LANDED: row identity, the layering verdict, the
audit trail and the outbox.
"""

import pytest
from sqlalchemy.sql import func

from database import crud, models, schemas
from sql_budget import inserts_into, record_statements, selects_from


#: `xscope_safe_map` is the shipped map shape: business key `cell_key` assembled
#: from (lot, slot, cx, cy), map key inside the composite key. Reused rather than
#: declared afresh so this file cannot drift from the shape the other map tests use.
TABLE = "xscope_safe_map"


def _item(lot, slot, cx, cy, bn, source="probe.csv", by="watcher", cell_key=""):
    """One watcher-shaped payload item.

    `cell_key` is present and EMPTY on purpose - that is what a map CSV carrying
    its key column looks like, and it is the case that makes the composite-key
    collision probe fire on every row: the row is created with no
    `business_key_val` at all, which never equals the assembled key.

    ⚠️ That spelling used to be `''` and is now NULL (2026-08-07). The probe count
    this file budgets is unchanged either way - neither value ever equals the
    assembled key - but `''` is a VALUE, so every keyless row in the database shared
    one identity and collided under `uq_bk_<table>`. See
    `crud._update_row_business_key` and `data_model.md` §3.1-bis.
    """
    updates = {"lot": lot, "slot": slot, "cx": cx, "cy": cy, "bn": bn}
    if cell_key is not None:
        updates["cell_key"] = cell_key
    return schemas.GeneralUpdateItem(
        updates=updates, source_name=source, updated_by=by)


def _batch(items, **kw):
    return schemas.GeneralUpdateBatch(updates=items, **kw)


# --------------------------------------------------------------------------
# 1. The budget
# --------------------------------------------------------------------------

def test_fresh_insert_costs_one_identity_select_for_the_whole_chunk(db_session):
    """The headline: identity is resolved once per CHUNK, not twice per ROW.

    Before this change a 200-row fresh chunk issued 401 SELECTs against the data
    table (1 prefetch + 200 `get_row_by_business_key` + 200 collision probes).
    """
    n = 200
    items = [_item("L1", "01", i, 0, "1") for i in range(n)]

    with record_statements(db_session) as recorded:
        results, changed, _logs, _deleted = crud.apply_batch_updates(
            db_session, TABLE, _batch(items))

    # What landed, asserted BEFORE the budget - a cheap write that wrote nothing
    # would otherwise pass the interesting assertion.
    model = models.DYNAMIC_TABLES[TABLE]
    assert len(results) == n
    assert db_session.query(model).count() == n
    keys = {r.business_key_val for r, _new in results}
    assert keys == {f"L1_01_{i}_0" for i in range(n)}, \
        "identity must still be the assembled composite key, not a fresh uuid per row"

    data_selects = selects_from(recorded, TABLE)
    assert len(data_selects) == 1, (
        f"a fresh chunk must cost ONE prefetch SELECT on the data table, got "
        f"{len(data_selects)}:\n" + "\n".join(s.sql[:100] for s in data_selects[:5]))


def test_fresh_insert_does_not_emit_one_insert_per_row(db_session):
    """The ORM flush must batch. One statement per row was 14.7% of the run.

    Skipped rather than failed on a dialect that cannot fold `INSERT ... RETURNING`
    into one statement: the property under test is "this code puts nothing in the
    parameter set that PREVENTS batching", and on such a dialect the assertion would
    be measuring the driver instead of the code. PostgreSQL (every production
    connection) does support it, and the lane's end-to-end benchmark measures it
    there.
    """
    bind = db_session.get_bind()
    if not getattr(bind.dialect, "use_insertmanyvalues", False) or \
            not getattr(bind.dialect, "insert_executemany_returning", False):
        pytest.skip(f"{bind.dialect.name} cannot batch INSERT ... RETURNING")

    n = 200
    items = [_item("L2", "01", i, 0, "1") for i in range(n)]

    with record_statements(db_session) as recorded:
        crud.apply_batch_updates(db_session, TABLE, _batch(items))

    data_inserts = inserts_into(recorded, TABLE)
    assert len(data_inserts) < n / 4, (
        f"{n} new rows produced {len(data_inserts)} INSERT statements; the flush is "
        f"not batching. A SQL expression (func.now()) in the parameter set is the "
        f"usual cause.")


def test_new_rows_still_get_an_updated_at(db_session):
    """`updated_at` is no longer set explicitly on INSERT - the column's
    `server_default=func.now()` supplies it. If a physical table ever lacks that
    default the column would land NULL, and every incremental sweep that orders by
    it would silently skip the row."""
    crud.apply_batch_updates(db_session, TABLE, _batch(
        [_item("L3", "01", 0, 0, "1")]))
    model = models.DYNAMIC_TABLES[TABLE]
    row = db_session.query(model).filter(model.business_key_val == "L3_01_0_0").one()
    assert row.updated_at is not None
    assert row.created_at is not None


# --------------------------------------------------------------------------
# 2. Identity must still be resolved - the ways the shortcut could be wrong
# --------------------------------------------------------------------------

def test_second_push_updates_the_same_rows_instead_of_duplicating_them(db_session):
    """The proof is "the prefetch asked and got nothing", so a row that DOES exist
    must still be found. This is the assertion that fails if the membership test is
    read as "skip the lookup" rather than "absence is proven"."""
    items = [_item("L4", "01", i, 0, "1") for i in range(20)]
    crud.apply_batch_updates(db_session, TABLE, _batch(items))

    model = models.DYNAMIC_TABLES[TABLE]
    first_ids = {r.row_id for r in db_session.query(model).filter(
        model.lot == "L4").all()}
    assert len(first_ids) == 20

    items2 = [_item("L4", "01", i, 0, "2") for i in range(20)]
    crud.apply_batch_updates(db_session, TABLE, _batch(items2))

    rows = db_session.query(model).filter(model.lot == "L4").all()
    assert len(rows) == 20, "a re-push must UPDATE, not duplicate"
    assert {r.row_id for r in rows} == first_ids
    assert {r.bn for r in rows} == {"2"}


def test_a_business_key_with_surrounding_whitespace_still_matches(db_session):
    """`get_row_by_business_key` strips before comparing and the prefetch filter is
    built from stripped values, so the membership test must strip too. Testing the
    raw value would be merely slow; testing a DIFFERENT normalisation on either side
    is what mints a duplicate."""
    model = models.DYNAMIC_TABLES[TABLE]
    seed = model(row_id="WS_SEED", business_key_val="PAD_01_1_1",
                 lot="PAD", slot="01", cx=1, cy=1, bn="seed")
    db_session.add(seed)
    db_session.commit()

    item = schemas.GeneralUpdateItem(
        business_key_val="  PAD_01_1_1  ",
        updates={"lot": "PAD", "slot": "01", "cx": 1, "cy": 1, "bn": "updated"},
        source_name="probe.csv", updated_by="watcher")
    results, _c, _l, _d = crud.apply_batch_updates(db_session, TABLE, _batch([item]))

    assert db_session.query(model).filter(
        model.business_key_val == "PAD_01_1_1").count() == 1
    assert results[0][0].row_id == "WS_SEED"
    assert results[0][0].bn == "updated"


def test_a_rename_inside_one_batch_does_not_orphan_the_old_key(db_session):
    """🔴 The case that makes the SUBTRACTION in `probed_identity` load-bearing.

    Item A resolves an existing row by its key and changes a composite-source column,
    so the row is renamed and `row_cache` drops the old key. Item B then names that
    old key: the cache no longer has it, and the only thing between B and a duplicate
    row is that the old key is not in the proven-absent set, because the prefetch DID
    bring a row back for it.

    Proved to ring: with the subtraction removed, this test's PostgreSQL equivalent
    minted a second row carrying the old key. Every other test in this file stayed
    green for that defect - `row_cache` answers first on the ordinary paths - so this
    is the only net over it.
    """
    model = models.DYNAMIC_TABLES[TABLE]
    seed = model(row_id="RN_ROW", business_key_val="RN_01_1_1",
                 lot="RN", slot="01", cx=1, cy=1, bn="seed")
    db_session.add(seed)
    db_session.commit()

    a = schemas.GeneralUpdateItem(
        business_key_val="RN_01_1_1",
        updates={"lot": "RN", "slot": "01", "cx": 2, "cy": 1, "bn": "renamed"},
        source_name="probe.csv", updated_by="watcher")
    b = schemas.GeneralUpdateItem(
        business_key_val="RN_01_1_1", updates={"bn": "second"},
        source_name="probe.csv", updated_by="watcher")
    crud.apply_batch_updates(db_session, TABLE, _batch([a, b]))

    rows = db_session.query(model).filter(model.lot == "RN").all()
    assert len(rows) == 1, f"a duplicate row was minted: {[r.row_id for r in rows]}"
    assert rows[0].row_id == "RN_ROW"


def test_collision_merge_still_fires_against_a_row_outside_the_prefetch(db_session):
    """The collision probe's fast path may only skip when the prefetch covered the
    ASSEMBLED key. Here it did not: the payload arrives with an explicit
    `business_key_val` that is NOT the key its own columns assemble to, so the probe
    must still run and merge onto the row that already owns the assembled key."""
    model = models.DYNAMIC_TABLES[TABLE]
    victim = model(row_id="MERGE_TARGET", business_key_val="MG_01_5_5",
                   lot="MG", slot="01", cx=5, cy=5, bn="old")
    db_session.add(victim)
    db_session.commit()

    # `business_key_val` is supplied, so `assemble_composite_business_key` returns
    # early and the prefetch asks about "SOMETHING_ELSE" - never about "MG_01_5_5".
    item = schemas.GeneralUpdateItem(
        business_key_val="SOMETHING_ELSE",
        updates={"lot": "MG", "slot": "01", "cx": 5, "cy": 5, "bn": "new"},
        source_name="probe.csv", updated_by="watcher")
    crud.apply_batch_updates(db_session, TABLE, _batch([item]))

    # THE discriminating assertion: with the probe skipped the merge never happens and
    # this row still reads "old". Proved to ring - stubbing
    # `_find_business_key_conflict` to return None fails exactly this and nothing else.
    #
    # ⚠️ Deliberately NOT asserting the row count. The merge leaves its shell row
    # behind (`db.delete` on a still-pending instance, inside a bare `except: pass`),
    # so this scenario ends with TWO rows. That is a pre-existing defect, identical on
    # the pre-change code, and pinning it here would freeze it.
    target = db_session.query(model).filter(model.row_id == "MERGE_TARGET").one()
    assert target.bn == "new", (
        "the collision probe was skipped - the merge onto the existing row never ran")
    assert target.business_key_val == "MG_01_5_5"


# --------------------------------------------------------------------------
# 3. Layering, audit and outbox must survive the fast path
# --------------------------------------------------------------------------

def test_a_user_layer_still_beats_a_later_parser_write(db_session):
    """The system's first core value. A manual value outranks an automatic one
    (`user` 0 < `pipeline_parser` 2), and a write path that resolves rows without
    reading their stored sources would silently let the parser win."""
    crud.apply_batch_updates(db_session, TABLE, _batch(
        [_item("LP", "01", 2, 2, "USER_VALUE", source="user", by="operator")]))

    model = models.DYNAMIC_TABLES[TABLE]
    row = db_session.query(model).filter(
        model.business_key_val == "LP_01_2_2").one()
    assert row.bn == "USER_VALUE"

    crud.apply_batch_updates(db_session, TABLE, _batch(
        [_item("LP", "01", 2, 2, "PARSER_VALUE",
               source="pipeline_parser", by="watcher")]))

    db_session.expire_all()
    row = db_session.query(model).filter(
        model.business_key_val == "LP_01_2_2").one()
    assert row.bn == "USER_VALUE", (
        "the parser layer overwrote the user layer - the priority computation no "
        "longer sees the stored `user` CellSource")

    stored = {s.source_name: s.value for s in db_session.query(models.CellSource).filter(
        models.CellSource.table_name == TABLE,
        models.CellSource.row_id == row.row_id,
        models.CellSource.column_name == "bn").all()}
    assert stored == {"user": "USER_VALUE", "pipeline_parser": "PARSER_VALUE"}, \
        "both layers must be stored; only the resolved value is decided by priority"


def test_every_new_row_still_stages_an_outbox_event(db_session):
    """A row that lands without its outbox event is invisible to every downstream
    worker. The outbox is staged from `session.new`, so any bulk-insert shortcut
    that bypassed the ORM would silently drop it."""
    n = 30
    items = [_item("OB", "01", i, 0, "1") for i in range(n)]
    crud.apply_batch_updates(db_session, TABLE, _batch(items))

    events = db_session.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == TABLE,
        models.DatabaseOutbox.event_type == "CREATE").all()
    assert len(events) == n
    payload_keys = {e.payload["business_key"] for e in events}
    assert payload_keys == {f"OB_01_{i}_0" for i in range(n)}


def test_audit_trail_still_records_the_ingest(db_session):
    n = 10
    items = [_item("AU", "01", i, 0, "1") for i in range(n)]
    crud.apply_batch_updates(db_session, TABLE, _batch(items))

    logs = db_session.query(models.AuditLog).filter(
        models.AuditLog.table_name == TABLE,
        models.AuditLog.column_name == "ROW_UPDATE").all()
    assert len(logs) == n


# --------------------------------------------------------------------------
# 4. The bulk upsert FALLBACK
#
# 🔴 EVERY TEST IN THIS SECTION RUNS ON THE FALLBACK, AND THE NAMES NOW SAY SO.
# `_pg_multirow_upsert` returns False on `dialect.name != "postgresql"`, and
# this suite's engine is in-memory SQLite, so the accepted branch is
# unreachable from here - measured with a counting spy over this file plus
# `test_bulk_chunking_budget.py` and `test_business_key_conflict_retry.py`:
# `entered=28 accepted=0 declined=28` across 42 passing tests. Two of these
# tests used to be called "the fast path", which meant a later change could
# break the accepted branch outright while 42 green tests reported it covered.
#
# The fallback is worth testing - it is what SQLite, psycopg3 and every
# declined shape actually take. It is simply not what these names used to
# claim. The accepted branch is covered by `test_pg_multirow_upsert.py`, which
# skips unless an isolated PostgreSQL is declared.
# --------------------------------------------------------------------------

def test_bulk_upsert_falls_back_when_a_mapping_holds_a_sql_expression(db_session):
    """`_is_executemany_safe` refuses a `ClauseElement` - a parameter set cannot
    carry one. The refusal must degrade to the old VALUES path, not to an error:
    an outside caller is allowed to hand one in."""
    rows = [{"table_name": TABLE, "row_id": f"EX_{i}", "column_name": "bn",
             "source_name": "probe.csv", "value": str(i), "updated_by": "p3",
             "ingested_at": func.now()}
            for i in range(5)]
    crud.bulk_upsert_cell_sources(db_session, rows)
    db_session.flush()

    stored = db_session.query(models.CellSource).filter(
        models.CellSource.table_name == TABLE,
        models.CellSource.row_id.like("EX_%")).all()
    assert len(stored) == 5
    assert all(s.ingested_at is not None for s in stored)


def test_a_ragged_mapping_list_is_still_refused(db_session):
    """Different key sets across mappings.

    Measured, not assumed: SQLAlchemy 2.0's `.values(ragged_list)` refuses this too
    (`CompileError`), so the contract has always been "a ragged list is REFUSED".
    The uniformity half of `_is_executemany_safe` exists to keep that refusal
    identical rather than replace it with a driver-level error from the batched path.
    """
    rows = [
        {"table_name": TABLE, "row_id": "RG_1", "column_name": "bn",
         "source_name": "probe.csv", "value": "a", "updated_by": "p3"},
        {"table_name": TABLE, "row_id": "RG_2", "column_name": "bn",
         "source_name": "probe.csv", "value": "b"},
    ]
    with pytest.raises(Exception):
        crud.bulk_upsert_cell_sources(db_session, rows)
        db_session.flush()
    db_session.rollback()


def test_bulk_upsert_fallback_still_updates_on_conflict(db_session):
    """The FALLBACK keeps ON CONFLICT DO UPDATE semantics: a second write of the
    same (table, row, column, source) replaces the value rather than raising.

    The accepted branch's own conflict target is a string `_pg_multirow_upsert`
    assembles by hand and is therefore the one that can be wrong; it is
    asserted in `test_pg_multirow_upsert.py::
    test_on_conflict_do_update_replaces_the_value_on_the_accepted_branch`.
    """
    from datetime import datetime
    def rows(v):
        return [{"table_name": TABLE, "row_id": "CF_1", "column_name": "bn",
                 "source_name": "probe.csv", "value": v, "updated_by": "p3",
                 "ingested_at": datetime.now()}]

    crud.bulk_upsert_cell_sources(db_session, rows("first"))
    db_session.flush()
    crud.bulk_upsert_cell_sources(db_session, rows("second"))
    db_session.flush()

    stored = db_session.query(models.CellSource).filter(
        models.CellSource.table_name == TABLE,
        models.CellSource.row_id == "CF_1").all()
    assert len(stored) == 1
    assert stored[0].value == "second"


@pytest.mark.parametrize("n", [0, 1, crud.BULK_CHUNK_SIZE - 1,
                               crud.BULK_CHUNK_SIZE, crud.BULK_CHUNK_SIZE + 1])
def test_fallback_chunk_boundaries_write_every_mapping(db_session, n):
    """Off-by-one guard on the chunk loop, at and around the boundary, for the
    send this suite can reach.

    ⚠️ It used to be called `test_fast_path_chunk_boundaries_...`. It never ran
    the fast path; the equivalent on the accepted branch (which also asserts
    the STATEMENT count, because `row_sql_cache` is keyed by chunk length) is
    `test_pg_multirow_upsert.py::
    test_chunk_boundaries_write_every_mapping_on_the_accepted_branch`.
    """
    from datetime import datetime
    now = datetime.now()
    mappings = [{"table_name": TABLE, "row_id": f"CB_{i}", "column_name": "bn",
                 "source_name": "probe.csv", "value": str(i),
                 "updated_by": "p3", "ingested_at": now}
                for i in range(n)]
    crud.bulk_upsert_cell_sources(db_session, mappings)
    db_session.flush()

    stored = db_session.query(models.CellSource).filter(
        models.CellSource.table_name == TABLE,
        models.CellSource.row_id.like("CB_%")).count()
    assert stored == n
