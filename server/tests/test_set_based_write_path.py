"""[P3] The batch write path resolves row identity SET-WISE, once per chunk.

A 100,000-row map file used to cost 301,222 SQL statements - 3.01 per data row -
and 65% of its wall clock was Python and SQLAlchemy rather than the database.
Three of those costs are attacked here, and each one is a place where "faster"
and "wrong" are one edit apart:

  1. Two identity SELECTs per row (the old row lookup -> the old key lookup,
     and the composite-key collision probe). Both are replaced by reading the proof
     the batch prefetch already produced - the old prefetch proof.
  2. One `INSERT ... RETURNING` per new row, because `updated_at=func.now()` put a
     SQL expression in the parameter set and SQLAlchemy cannot batch those.
  3. the old layer upsert building a fresh multi-row VALUES clause per chunk.

🔴 WHAT THESE TESTS ARE REALLY GUARDING. A statement-count assertion alone would
pass for an implementation that stopped looking up rows at all - which is to say
one that duplicates every row it should have matched, and drops the `user` layer
of every cell it should have merged. So every budget assertion here is paired
with an assertion about what LANDED: row identity, the layering verdict, the
audit trail and the outbox.
"""

import re

import pytest

from database import crud, lines, models, schemas
from sql_budget import record_statements


def _relation(sql):
    """The relation a statement writes (INSERT INTO / UPDATE / DELETE FROM) or first reads (FROM)."""
    text = " ".join(sql.split())
    hit = re.match(r'(?i)(?:insert(?: or \w+)? into|update|delete from)\s+"?(\w+)"?', text)
    if hit is None:
        hit = re.search(r'(?i)\bfrom\s+"?(\w+)"?', text)
    return hit.group(1) if hit else None


def _by_relation(recorded):
    """{(verb, relation): statements} of a recorded block - an executemany is one statement."""
    out = {}
    for call in recorded:
        key = (call.sql.strip().split()[0].upper(), _relation(call.sql))
        out[key] = out.get(key, 0) + 1
    return out


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
    the old key write and `data_model.md` §3.1-bis.
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
    table (1 prefetch + 200 key lookups + 200 collision probes).
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

    # per relation, a chunk's reads, never a row's (the overhaul's record - lead 11-12): t - the claim's keys, read
    # once under lock (a key put answers its row), the funnel's answer rows; t__lines - the head lines (_spoken), a
    # person's heads (_marks), the merge's
    counts = _by_relation(recorded)
    assert (counts.get(("SELECT", TABLE)), counts.get(("SELECT", lines.lines_relation(TABLE)))) == (2, 3), counts


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

    counts = _by_relation(recorded)
    assert counts.get(("INSERT", TABLE)) == 1, (
        f"{n} new rows must be claimed by one INSERT statement a page: {counts}")
    # t__lines' INSERT ... RETURNING goes a row at a time on sqlite - SQLAlchemy keeps the parameter order that way,
    # the driver, not this code; it is one statement a page on PostgreSQL and pinned there
    # (test_a_new_rows_lines_go_in_a_statement_a_page_pg)
    print("sqlite: %d t__lines INSERT statements, counted on PostgreSQL only"
          % counts.get(("INSERT", lines.lines_relation(TABLE)), 0))


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
    """the old key lookup strips before comparing and the prefetch filter is
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


# --------------------------------------------------------------------------
# 1-bis. One identity, one spelling
#
# 🔴 THE SAME DEFECT CLASS AS THE WHITESPACE TEST ABOVE, ON A DIFFERENT AXIS. There the
# two sides agreed on how to strip; here they disagreed on how to render a float. A
# plain-keyed table's identity was built by `clean_str_value` (SDK, and the composite
# assembler), looked up by `business_key_val`, and then STORED by `str().strip()` - so
# 1234.0 was found as `'1234'` and saved as `'1234.0'`. Nothing errored: the strings
# differ, so `uq_bk_` does not fire, and the next push simply inserts another copy.
#
# A float arrives on the ordinary path, not an exotic one: `pd.read_sql` types a numeric
# SQL column as float64, which is exactly what the SDK's own `sql()` helper hands the
# author.
# --------------------------------------------------------------------------

PLAIN = "inventory_master"          # plain `business_key`: part_no. No composite.


def _plain_item(part_no, qty, key=None, row_id=None):
    """An SDK-shaped item carries `business_key_val` (that is what `df_to_updates`
    lifts); a grid-shaped one carries `row_id` and leaves the key to the writer."""
    return schemas.GeneralUpdateItem(
        row_id=row_id, business_key_val=key,
        updates={"part_no": part_no, "stock_qty": qty},
        source_name="probe.csv", updated_by="watcher")


def _plain_rows(db, prefix):
    model = models.DYNAMIC_TABLES[PLAIN]
    return [r for r in db.query(model).all()
            if str(r.business_key_val or "").startswith(prefix)]


def test_a_float_identity_is_stored_under_the_spelling_it_was_resolved_by(db_session):
    """Push the same row twice, a batch apart. The second must LAND ON the first.

    The item resolves on `business_key_val` = '1234' and the payload carries the float
    1234.0. Re-deriving the stored key from the payload writes '1234.0', so the second
    push looks up '1234', misses, and inserts - without colliding, because the strings
    differ."""
    for qty in (1, 2):
        crud.apply_batch_updates(db_session, PLAIN,
                                 _batch([_plain_item(1234.0, qty, key="1234")]))
    rows = _plain_rows(db_session, "1234")
    assert len(rows) == 1, [r.business_key_val for r in rows]
    assert rows[0].business_key_val == "1234"
    assert rows[0].stock_qty == 2


def test_two_items_with_one_float_identity_are_one_row_inside_a_batch(db_session):
    """The in-batch half. A new row is cached with no key at creation time, so the row
    cache is repopulated from whatever the writer stores - a second spelling there makes
    the SECOND item of the SAME batch miss."""
    crud.apply_batch_updates(db_session, PLAIN, _batch([
        _plain_item(77.0, 1, key="77"),
        _plain_item(77.0, 5, key="77"),
    ]))
    rows = _plain_rows(db_session, "77")
    assert len(rows) == 1, [r.business_key_val for r in rows]
    assert rows[0].business_key_val == "77"


def test_a_key_the_writer_derives_itself_gets_the_same_spelling(db_session):
    """The other door: a grid-shaped item names a `row_id` and carries no key, so the
    writer derives one from the payload. That derivation is the one that used to render
    a float differently - and the proof is that an SDK-shaped push afterwards, carrying
    the SDK's spelling, must land on THIS row rather than make a second."""
    model = models.DYNAMIC_TABLES[PLAIN]
    seeded = model(row_id="FLOATKEY_SEED", part_no=None, stock_qty=0)
    db_session.add(seeded)
    db_session.commit()

    crud.apply_batch_updates(db_session, PLAIN,
                             _batch([_plain_item(5150.0, 1, row_id="FLOATKEY_SEED")]))
    assert _plain_rows(db_session, "5150")[0].business_key_val == "5150"

    crud.apply_batch_updates(db_session, PLAIN,
                             _batch([_plain_item(5150.0, 9, key="5150")]))
    rows = _plain_rows(db_session, "5150")
    assert len(rows) == 1, [r.business_key_val for r in rows]
    assert rows[0].row_id == "FLOATKEY_SEED" and rows[0].stock_qty == 9


def test_the_items_own_key_wins_over_any_re_derivation_from_the_payload(db_session):
    """🔴 THE DISCRIMINATING CASE FOR *WHOSE* VALUE IS STORED, and it needs the two to be
    values one spelling cannot reconcile. A float payload folds to the item's key, so a
    fixture built on one proves only the spelling half - it passes with the writer still
    re-deriving. Here the payload carries the STRING '1234.0', which `clean_str_value`
    leaves alone, while the item was resolved by '1234'.

    The item's key is what the prefetch filtered on and what the old row lookup
    matched, so storing anything else saves the row under a handle nothing looks it up
    by."""
    item = schemas.GeneralUpdateItem(
        business_key_val="1234",
        updates={"part_no": "1234.0", "stock_qty": 1},
        source_name="probe.csv", updated_by="watcher")
    crud.apply_batch_updates(db_session, PLAIN, _batch([item]))

    rows = _plain_rows(db_session, "1234")
    assert len(rows) == 1
    assert rows[0].business_key_val == "1234", (
        "the writer re-derived the identity from the payload; the row is now stored "
        "under a key the batch never resolved on")


def test_the_read_side_spells_a_float_the_way_the_write_side_did(db_session):
    """The other end of the same seam: a later write that names no key and carries the value 931.0 must reach the
    row that value stored - the write's row claim (`write_lines._claim`) reads the key as the write side spelled it
    (the old door's key lookup retired with the lines, 11-11).

    ⚠️ It folds a FLOAT, not a string that looks like one: `'931.0'` is a different
    identity and stays one. This unifies how a VALUE is spelled, it does not add
    string-level normalisation."""
    crud.apply_batch_updates(db_session, PLAIN,
                             _batch([_plain_item(931.0, 8, key="931")]))
    crud.apply_batch_updates(db_session, PLAIN, _batch([_plain_item(931.0, 9)]))
    rows = _plain_rows(db_session, "931")
    assert [(r.business_key_val, r.stock_qty) for r in rows] == [("931", 9)]


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


def test_the_assembled_key_wins_and_the_supplied_key_s_row_is_left_alone(db_session):
    """🔴 판정 188's BOUNDARY, and the one case where the two keys of 판정 191 disagree
    about a row that EXISTS on both sides.

    191 lets a supplied key resolve a row so a rename keeps its address (S-90). This
    pins the price of that: the fallback is a FALLBACK. When the assembled key already
    names a row, that row is the identity and wins; the row carrying the supplied key is
    not read, not written and not renamed. Reversing the order would let any caller
    retarget somebody else's row by sending its key - the defect 190 closed, re-opened
    through the door 191 had to leave ajar.
    """
    model = models.DYNAMIC_TABLES[TABLE]
    owner = model(row_id="BD_ROW", business_key_val="BD_01_9_9",
                  lot="BD", slot="01", cx=9, cy=9, bn="owner")
    bystander = model(row_id="OLD_ROW", business_key_val="OLD_HANDLE",
                      lot="ZZ", slot="99", cx=0, cy=0, bn="untouched")
    db_session.add_all([owner, bystander])
    db_session.commit()

    item = schemas.GeneralUpdateItem(
        business_key_val="OLD_HANDLE",
        updates={"lot": "BD", "slot": "01", "cx": 9, "cy": 9, "bn": "written"},
        source_name="probe.csv", updated_by="watcher")
    crud.apply_batch_updates(db_session, TABLE, _batch([item]))

    assert db_session.query(model).count() == 2, "no third row was minted"
    assert db_session.query(model).filter(
        model.row_id == "BD_ROW").one().bn == "written", \
        "the assembled key names a row, so that row is the one written"

    left = db_session.query(model).filter(model.row_id == "OLD_ROW").one()
    assert (left.bn, left.business_key_val) == ("untouched", "OLD_HANDLE"), \
        "the supplied key is a fallback address, never a way to retarget a live row"


def test_a_supplied_key_that_names_nothing_still_resolves_onto_the_assembled_row(db_session):
    """A payload whose explicit `business_key_val` is NOT the key its own columns
    assemble to still lands on the row that owns the ASSEMBLED key.

    🔴 RENAMED AND RE-STATED BECAUSE WHAT IT MEASURES MOVED, and that was MEASURED
    rather than reasoned (2026-09-09, 판정 191). It used to be the collision-merge test:
    the assembly returned early on a supplied key, so the payload was looked up under
    "SOMETHING_ELSE", missed, and the old collision probe had to run and merge.
    Since 190/191 the assembly runs anyway and the prefetch carries the assembled key,
    so this row now comes back from `row_cache` and the merge is never reached. Stubbing
    the old collision probe to return None leaves this test GREEN - its old
    docstring claimed the opposite, which is why the claim is not simply repeated here.

    ⚠️ THE MERGE ARM IS NOT UNCOVERED, also measured with that same stub:
    `test_a_collision_merge_leaves_history.py` (5 red) and `test_composite_business_key.py`
    (2 red) both ring on it. What is gone is this scenario's ability to reach it."""
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
    # the old collision probe to return None fails exactly this and nothing else.
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

    stored = {source: said["value"] for source, said in
              lines.layers(db_session, TABLE, [row.row_id], ["bn"]).get((row.row_id, "bn"), {}).items()}
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
    """The write's own audit row and its own lines - one a row (the overhaul's record: audit_batches + the lines
    by batch, lead 11-11)."""
    from sqlalchemy import text

    n = 10
    items = [_item("AU", "01", i, 0, "1") for i in range(n)]
    crud.apply_batch_updates(db_session, TABLE, _batch(items, transaction_id="au-tx"))

    audited = db_session.query(lines.AuditBatch).filter_by(table_name=TABLE, transaction_id="au-tx").all()
    assert len(audited) == 1, [(a.work_kind, a.written_by) for a in audited]
    said = db_session.execute(text('SELECT count(DISTINCT row_id), count(*) FROM "%s" WHERE batch = :tx'
                                   % lines.lines_relation(TABLE)), {"tx": "au-tx"}).one()
    assert tuple(said) == (n, n), "one line a row of the write"


# ------------------------------------------------- S-83 ③: the row write is ONE statement


def _statements_for(db, table, items, tx):
    """Every statement one request sends, by verb. THE production-relevant number."""
    import event_constants
    from sqlalchemy import event
    from database.context import outbox_mode

    counts = {}

    def before(conn, cursor, statement, params, context, executemany):
        verb = statement.strip().split()[0].upper()
        key = (verb, _relation(statement))
        counts[key] = counts.get(key, 0) + 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
            crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
                updates=items, transaction_id=tx, silent=True))
    finally:
        event.remove(engine, "before_cursor_execute", before)
    return counts


def _rows_for(table, n, tag):
    """⚠️ THE KEY IS ASSEMBLED, not supplied: this fixture table declares
    `composite_key_source`, so the identity comes from the four columns and `bn` is the only
    thing an edit can change."""
    return [schemas.GeneralUpdateItem(
        updates={"lot": "S83", "slot": "A", "cx": i, "cy": 0, "bn": f"{tag}-{i}"},
        source_name="s83", updated_by="s83") for i in range(n)]


def test_editing_many_rows_sends_one_update_statement_not_one_per_row(db_session):
    """🔴 S-83 ③ (판정 183: 「행 «한 번» 벌크」). THE COUNT IS THE CONTRACT, NOT THE SECOND.

    Measured before this landed: a 1,000-row edit sent 1,006 statements, of which 1,000 were
    `UPDATE ... SET updated_at=CURRENT_TIMESTAMP, ... WHERE row_id = ?` - ONE DISTINCT TEXT,
    executed a thousand times. The cause is the one [P3] already named for the cell upserts:
    a `ClauseElement` in the SET clause takes the write off its batched path. The row's
    instant is now read ONCE per request, as a value, and the write is one executemany.

    ⛔ NOT A TIMING TEST, deliberately. On sqlite those thousand executions are function
    calls and the whole request fits inside the second the ruling asked for - so a wall-clock
    gate here would be GREEN on the defect. On PostgreSQL they are a thousand ROUND TRIPS.
    The statement count is the same number in both, which is why it is what is pinned.
    """
    rows = 40
    inserting = _statements_for(db_session, TABLE, _rows_for(TABLE, rows, "first"),
                                "s83-insert")
    counts = _statements_for(db_session, TABLE, _rows_for(TABLE, rows, "second"), "s83-edit")
    # 판정 206 gate ①, BOTH halves. The insert path was already batched before this round -
    # measured, not assumed: the only single INSERT is the collapsed outbox event (S-82),
    # which is one per request by construction. Pinned here so a later change cannot take
    # the INSERT off its batched path the way the UPDATE was off its.
    # by relation (the overhaul's record - lead 11-12): t__lines' INSERT is a row at a time on sqlite (the driver
    # keeping the parameter order) and pinned on PostgreSQL (test_a_new_rows_lines_go_in_a_statement_a_page_pg)
    line_rel = lines.lines_relation(TABLE)
    assert inserting.get(("INSERT", TABLE)) == 1, f"new rows must be claimed by one statement: {inserting}"
    assert counts.get(("UPDATE", TABLE)) == 1, f"the {rows} edited rows must be written by ONE statement: {counts}"
    assert counts.get(("UPDATE", line_rel)) == 1, f"the earlier lines' heads by ONE statement: {counts}"
    for said in (inserting, counts):
        grows = {k: v for k, v in said.items() if k[0] != "PRAGMA" and k != ("INSERT", line_rel) and v >= rows}
        assert not grows, f"a statement a row is back: {grows}"


def test_the_batch_instant_comes_from_the_database_rather_than_this_process(db_session):
    """⚠️ THE CLOCK DID NOT MOVE, and that is the half a speed number cannot see.

    INSERT still takes the database's clock through `server_default`. Had the UPDATE started
    reading THIS process's clock instead, one column would carry two clock sources, and skew
    between them is invisible until the day it orders `idx_<table>_updated` wrong. On
    PostgreSQL `now()` is the TRANSACTION timestamp, so reading it once reproduces exactly
    what the per-row expression produced rather than approximating it.
    """
    assert crud.batch_write_instant(db_session) is not None, (
        "the instant must come from the session; a None here silently restores the "
        "per-row expression")
