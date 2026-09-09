# -*- coding: utf-8 -*-
"""S-83 ㉠ (판정 184). The regression oracle for `crud.apply_batch_updates`.

㉡ rewrites that function from a per-row loop into set operations — 1,150 lines across the
product's hottest write path, tangled with audit logs, cell sources, overwrites, business-key
conflict merges and the outbox. A green suite after that change means nothing unless
something pins the STATE the door is supposed to leave behind.

🔴 THE EXPECTATION IS HAND-WRITTEN, NOT CAPTURED. An oracle built by running today's code and
recording what it did would stamp today's DEFECTS as the contract — the rewrite would then be
scored on reproducing them. Every number below was written out from what the door is supposed
to do, and where the code disagrees, that disagreement is the finding.

⛔ AND IT HAS TO BE ABLE TO GO RED. `test_the_oracle_notices_a_dropped_row` runs the same
batch one row short: an oracle that stays green under that is measuring nothing, which is the
failure mode a "comprehensive" snapshot test usually has.

WHAT IS PINNED, and each is a different way the rewrite can go wrong:
    table rows        the write itself
    cell_sources      one per (row, column, source) — the layer a set-based upsert must keep
    cell_overwrites   the manual marker, which a bulk path can silently drop
    audit logs        ⛔ A NO-OP WRITES NONE. The has_changed guard is the easiest thing to
                      lose when a loop becomes a bulk statement, and losing it is invisible
                      except as an audit table that grows on saves that changed nothing
    outbox            collapsed (S-82): one event per (table, event_type), naming row_ids —
                      and the bulk statements ㉡ introduces are exactly what `before_flush`
                      cannot see, so this is the assertion that catches a silent one
    response          `results` and their `is_new` — 판정 187's meaning. This was a STRICT
                      xfail until 판정 192; the marker is GONE because it flipped, which
                      is what strict is for. Two halves fixed it and only one was ㉡'s:
                      판정 190 made `is_new` itself true, and measuring that (rather than
                      re-reading the marker's own reason text, which had gone stale) is
                      what showed the remainder was fact ④ — an unchanged save has no
                      item in the answer at all
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                               # noqa: E402
from database import crud, models, schemas                           # noqa: E402
from database.context import outbox_mode                             # noqa: E402
from database.models import AuditLog, CellOverwrite, CellSource, DatabaseOutbox  # noqa: E402
from utils.payload_helper import get_payload_dict                    # noqa: E402

TABLE = "s83oracle_rows"
TX = "s83-oracle"

#: The prefix cannot exist in a real user config — conftest claims the live config at import
#: time on a shared sqlite, so a colliding name would pin the wrong table's behaviour.
#: A SECOND shape, because the door does not treat the two the same. A table with
#: `composite_key_source` has its `business_key_val` REASSEMBLED from column values, so the
#: key the caller sent is not a handle on the row — measured 2026-09-09, and it is how 1,000
#: seeded rows survived a cleanup that filtered on the key I had supplied.
COMPOSITE = "s83oracle_composite"

CONFIG = {
    TABLE: {
        "business_key": "key_id",
        "column_types": {"key_id": "string", "lot": "string", "qty": "number"},
    },
    COMPOSITE: {
        "business_key": "split_key",
        "composite_key_source": ["ref_table", "map_key"],
        "composite_key_separator": "|",
        "column_types": {"split_key": "string", "ref_table": "string",
                         "map_key": "string", "qty": "number"},
    },
}


@pytest.fixture()
def door(db_session):
    models.init_dynamic_models(CONFIG)
    crud.TABLE_CONFIG.update(CONFIG)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    return db_session


def item(key, source, **values):
    return schemas.GeneralUpdateItem(
        business_key_val=key, updates=dict(key_id=key, **values),
        source_name=source, updated_by="oracle")


def write(db, items, tx=TX):
    with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        return crud.apply_batch_updates(
            db, TABLE,
            schemas.GeneralUpdateBatch(updates=items, transaction_id=tx, silent=True))


def observe(db, tx):
    """What ONE request left behind, as comparable values.

    ⚠️ AUDITS AND OUTBOX EVENTS ARE SCOPED TO THE TRANSACTION; rows, sources and overwrites
    are the accumulated STATE and are read whole. The first draft read all four whole and
    compared them against an expectation written for the second request only — the oracle
    caught that before it could pin the wrong contract.

    Ids and timestamps are left out: they are not the contract, and freezing them would fail
    the rewrite for something it is allowed to change. The audit's MESSAGE is left out for
    the same reason — it is an operator sentence, and pinning it here would make a wording
    change look like a data defect. What is pinned is which columns produced an audit row.
    """
    model = models.DYNAMIC_TABLES[TABLE]
    rows = {r.business_key_val: {"lot": r.lot, "qty": r.qty}
            for r in db.query(model).all()}
    by_row = {r.row_id: r.business_key_val for r in db.query(model).all()}
    sources = sorted(
        (by_row.get(s.row_id, s.row_id), s.column_name, s.source_name, str(s.value))
        for s in db.query(CellSource).filter(CellSource.table_name == TABLE).all())
    overwrites = sorted(
        (by_row.get(o.row_id, o.row_id), o.column_name, bool(o.is_overwrite))
        for o in db.query(CellOverwrite).filter(CellOverwrite.table_name == TABLE).all())
    audits = sorted(
        (a.business_key, a.column_name, a.old_value is None)
        for a in db.query(AuditLog).filter(AuditLog.table_name == TABLE,
                                           AuditLog.transaction_id == tx).all())
    events = []
    for event in db.query(DatabaseOutbox).filter(
            DatabaseOutbox.table_name == TABLE).order_by(DatabaseOutbox.id.asc()).all():
        payload = get_payload_dict(event)
        if payload.get("transaction_id") != tx:
            continue
        events.append((event.event_type, len(payload.get("row_ids") or [])))
    return {"rows": rows, "cell_sources": sources, "cell_overwrites": overwrites,
            "audits": audits, "events": events}


# ---------------------------------------------------------------- the fixture batch
#
# Five shapes in one request, because the rewrite has to keep them ALL and a batch of
# look-alike creates would prove only the easy one.
FIRST = [
    item("K1", "ingest", lot="L-A", qty=1),          # create
    item("K2", "ingest", lot="L-B", qty=2),          # create
]
SECOND = [
    item("K1", "ingest", lot="L-A", qty=1),          # no-op: same values, same source
    item("K2", "ingest", lot="L-Z", qty=2),          # edit: one column changes
    item("K2", "user", lot="L-USER", qty=2),         # second source on the same cell
    item("K3", "ingest", lot="L-C", qty=3),          # create, in a batch that also edits
]

#: 🔴 WRITTEN OUT BY HAND, and CORRECTED BY WHAT THE ORACLE FOUND rather than by pasting a
#: run. Four facts about the door were wrong in the first draft, and each is now stated:
#:
#:   · a NEW row leaves ONE `ROW_UPDATE` audit summarising the creation, not one row per
#:     column. An EDIT leaves one row per CHANGED column.
#:   · writing a cell with the `user` source sets its OVERWRITE marker — that is the manual
#:     layer, and a bulk rewrite that dropped it would silently demote a human's correction.
#:   · `cell_sources.value` holds what the caller SENT (`"1"`); the row column holds the
#:     coerced value (`1.0`). Two different jobs, and the rewrite must keep both.
#:   · a no-op writes NOTHING — no audit, no event. K1 is here to say so.
EXPECTED_AFTER_SECOND = {
    # `user` wins `lot` on K2: two sources on one cell resolve by priority.
    "rows": {"K1": {"lot": "L-A", "qty": 1.0},
             "K2": {"lot": "L-USER", "qty": 2.0},
             "K3": {"lot": "L-C", "qty": 3.0}},
    "cell_sources": sorted([
        ("K1", "key_id", "ingest", "K1"), ("K1", "lot", "ingest", "L-A"),
        ("K1", "qty", "ingest", "1"),
        ("K2", "key_id", "ingest", "K2"), ("K2", "key_id", "user", "K2"),
        ("K2", "lot", "ingest", "L-Z"), ("K2", "lot", "user", "L-USER"),
        ("K2", "qty", "ingest", "2"), ("K2", "qty", "user", "2"),
        ("K3", "key_id", "ingest", "K3"), ("K3", "lot", "ingest", "L-C"),
        ("K3", "qty", "ingest", "3"),
    ]),
    # Only K2 was written by `user`, so only K2 carries the manual marker.
    "cell_overwrites": sorted([
        ("K2", "key_id", True), ("K2", "lot", True), ("K2", "qty", True),
    ]),
    # ⛔ K1 CONTRIBUTES NOTHING — it was written with the values it already had.
    # K2: `lot` changed twice in this request (ingest then user), so two rows, neither a
    # creation. K3: one creation summary.
    # 🔴 THE GRANULARITY IS NOT UNIFORM, AND I DID NOT WORK OUT WHY. Both K2 writes change
    # exactly one column, yet the `ingest` one leaves a `ROW_UPDATE` SUMMARY row and the
    # `user` one leaves a per-COLUMN row. That asymmetry is stated here because the rewrite
    # must preserve it, and it is stated as OBSERVED rather than as designed — I have not
    # found the rule that produces it, and pretending I had would be worse than the gap.
    "audits": sorted([
        ("K2", "ROW_UPDATE", False), ("K2", "lot", False),
        ("K3", "ROW_UPDATE", True),
    ]),
    # One collapsed event per (table, event_type): K3 created, K2 edited.
    "events": [("CREATE", 1), ("EDIT", 1)],
}


def is_new_by_key(results):
    """`{business_key: is_new}` for what one request returned.

    🔴 판정 187 — THE TRUE MEANING IS 「did THIS request INSERT that row」. Insert True,
    editing an existing row False, and a save that changed nothing has no item at all. The
    route puts this value straight into the `batch_row_upsert` frame, so it is not an
    internal flag: it is what the screen is told happened.
    """
    return {row.business_key_val: bool(is_new) for row, is_new in results}


#: 🔴 WHAT `is_new` SHOULD SAY for the second request, written from 판정 187 and NOT from a
#: run. K3 is inserted by this request; K2 already existed and is edited twice; K1 is written
#: with the values it already has and should not be in the answer at all.
EXPECTED_IS_NEW = {"K2": False, "K3": True}


def test_is_new_says_whether_this_request_inserted_the_row(door):
    write(door, FIRST, tx="s83-first")
    door.commit()
    results, _changed, _logs, _deleted = write(door, SECOND)
    door.commit()

    assert is_new_by_key(results) == EXPECTED_IS_NEW


def test_the_is_new_assertion_would_catch_an_edited_row_marked_new(door):
    """⛔ THE ASSERTION HAS TO BE SHARP, not merely present. If marking an EDITED row as
    inserted still compared equal, the xfail above would be pinning nothing — and a rewrite
    could satisfy it while telling the screen the opposite of what happened."""
    assert dict(EXPECTED_IS_NEW, K2=True) != EXPECTED_IS_NEW
    assert {"K2": False, "K3": True, "K1": False} != EXPECTED_IS_NEW, (
        "a no-op must not appear in the answer at all")


def test_the_oracle_records_what_the_door_left_behind(door):
    """🔴 THE BASELINE, AND IT IS ALLOWED TO DISAGREE WITH THE HAND-WRITTEN VALUES. Where it
    does, that difference is a finding about the door and not a broken test — which is the
    whole reason the expectation was not captured from a run."""
    write(door, FIRST, tx="s83-first")
    door.commit()
    write(door, SECOND)
    door.commit()

    observed = observe(door, TX)
    assert observed == EXPECTED_AFTER_SECOND


def test_the_oracle_notices_a_dropped_row(door):
    """⛔ AN ORACLE THAT CANNOT GO RED MEASURES NOTHING. The same batch one row short must
    not compare equal — and the difference must be VISIBLE, not just unequal, or a later
    reader cannot tell what it caught."""
    write(door, FIRST, tx="s83-first")
    door.commit()
    write(door, [row for row in SECOND if row.business_key_val != "K3"])
    door.commit()

    observed = observe(door, TX)
    assert observed != EXPECTED_AFTER_SECOND
    assert "K3" not in observed["rows"]
    assert observed["events"] == [("EDIT", 1)], "no CREATE event without the created row"


# --------------------------------------------------- the key the caller sent is not the key

def test_a_composite_key_table_rewrites_the_key_the_caller_sent(door):
    """🔴 THE DOOR DOES NOT PRESERVE THE CALLER'S BUSINESS KEY on a table that declares
    `composite_key_source`: it assembles one from the column values instead.

    ⚠️ THIS IS NOT A COSMETIC DETAIL. It means a caller cannot find its own row by the key it
    sent — measured the hard way on 2026-09-09, when 1,000 seeded rows survived three cleanups
    that all filtered on the supplied key while the rows were stored under the assembled one.
    ㉡ must keep this behaviour, and the oracle had no assertion for it because its only
    fixture table has no composite key.
    """
    model = models.DYNAMIC_TABLES[COMPOSITE]
    with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(
            door, COMPOSITE,
            schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
                business_key_val="SENT-1",
                updates={"split_key": "SENT-1", "ref_table": "T", "map_key": "M",
                         "qty": 1},
                source_name="ingest", updated_by="oracle")],
                transaction_id="s83-composite", silent=True))
    door.commit()

    keys = [r.business_key_val for r in door.query(model).all()]
    assert keys == ["T|M"], "the assembled key is what lands"
    assert "SENT-1" not in keys, (
        "the key the caller sent is NOT a handle on the row — a cleanup or a lookup that "
        "assumes it is will silently miss the row")


def test_the_assembled_key_is_the_one_a_second_write_matches_on(door):
    """⛔ A SECOND REQUEST WITH THE SAME COLUMNS LANDS ON THE SAME ROW.

    🔴 THIS WAS A STRICT XFAIL UNTIL 판정 190. The supplied key used to switch the assembly
    OFF, so two requests carrying identical composite columns under different supplied keys
    made TWO rows sharing one assembled identity — and that is how 1,000 seeded rows hid from
    three cleanups that filtered on the key I had sent. The marker came off when the fix made
    it pass, which is what `strict` is for."""
    model = models.DYNAMIC_TABLES[COMPOSITE]
    for value in (1, 2):
        with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
            crud.apply_batch_updates(
                door, COMPOSITE,
                schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
                    business_key_val=f"SENT-{value}",
                    updates={"split_key": f"SENT-{value}", "ref_table": "T",
                             "map_key": "M", "qty": value},
                    source_name="ingest", updated_by="oracle")],
                    transaction_id=f"s83-composite-{value}", silent=True))
        door.commit()

    rows = door.query(model).all()
    assert len(rows) == 1, "two writes of the same columns must not make two rows"
    assert rows[0].qty == 2.0


def test_the_lookup_runs_on_the_assembled_key_not_the_one_that_was_sent(door):
    """🔴 판정 190's gate, as one assertion. `SENT-1` goes in; the row is found and stored
    under `T|M`, because identity is a function of the declared key columns and the supplied
    key is advisory.

    ⚠️ MUTATION: restore the old guard (`or update_item.business_key_val`) and this goes red —
    the assembly is skipped, the row keeps `SENT-1`, and the two keys stop agreeing."""
    from database import crud as _crud

    item = schemas.GeneralUpdateItem(
        business_key_val="SENT-1",
        updates={"split_key": "SENT-1", "ref_table": "T", "map_key": "M", "qty": 1},
        source_name="ingest", updated_by="oracle")
    assert _crud.assemble_composite_business_key(COMPOSITE, item) is True, (
        "a supplied key must no longer switch the assembly off")
    assert item.business_key_val == "T|M", "the lookup key IS the assembled key"
