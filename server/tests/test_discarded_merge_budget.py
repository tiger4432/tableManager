"""[P1b] The discarded-merge pattern's remaining three copies, plus the copy that
had no consumer at any size.

Tier 0 corrected `PUT /tables/{t}/data/updates`: it built `msg_items` (a read-back of
everything just written, plus an O(rows x columns) merge) and only THEN asked whether
the broadcast wanted items. The same decision is written at four more places, and this
module pins all four:

  * `PUT  /tables/{t}/cells/priority/batch`        (`set_cell_priority_batch_endpoint`)
  * `POST /tables/{t}/cells/sources/delete/batch`  (`delete_cell_source_batch_endpoint`)
  * `chain_ingestion_worker.process_chain_transaction_group`
  * the SILENT batch update - `msg_items` is read only inside `if not batch.silent:`

The bill these tests price is the READS: constant in rows (the same SELECTs per table at
n rows and at 2n - A 11-11, lead: the cell-source overhaul's lines changed which tables
are read, never «one per row»), and an arm that ships no items reads less than the arm
that ships them - the merge it would discard is skipped. Writes are not priced: on SQLite
a line insert that returns its ids in order is one statement a line (PG batches them).

Every skipping test is paired with the consuming arm, which still ships the merged cell
shape: a skip that swallowed the consuming case would broadcast rows with no
`is_overwrite`/`priority_source` and the grid would silently lose every overwrite marker.
"""

import json

import pytest

from event_constants import BROADCAST_ITEM_LIMIT
from sql_budget import record_statements, selects_from


TABLE = "rmscope_test_map"
READ = (TABLE, TABLE + "__lines", "cell_overwrites")

# `rmscope_test_map` declares no `composite_key_source`, so every batch below resolves
# its rows through the up-front prefetch. That is deliberate: it keeps these budgets
# independent of the prefetch/composite-key work (P6), so a regression in either lane
# can be attributed to that lane.


@pytest.fixture
def captured_broadcasts(monkeypatch):
    import main
    sent = []

    async def _capture(message):
        sent.append(json.loads(message))

    monkeypatch.setattr(main.manager, "broadcast", _capture)
    return sent


def _seed_cells(client, db_session, map_key, count):
    """`count` fresh rows with a stored `user` source on every column, and their ids."""
    payload = {"updates": [
        {"updates": {"die_key": f"{map_key}_{i}", "ref_table": "bonding_map",
                     "map_key": map_key, "x": i, "y": 0, "val": "1"},
         "source_name": "user", "updated_by": "tester"}
        for i in range(count)]}
    res = client.put(f"/tables/{TABLE}/data/updates", json=payload)
    assert res.status_code == 200, res.text

    from database import models
    model = models.DYNAMIC_TABLES[TABLE]
    rows = db_session.query(model).filter(model.map_key == map_key).all()
    assert len(rows) == count
    return [r.row_id for r in rows]


def _events(captured, name):
    return [m for m in captured if m["event"] == name]


def _reads(recorded, tables=READ):
    """{table: the SELECTs that read it, "*": every SELECT} - a table's count is by name, so t's holds t__lines'
    too; the whole count catches a read a row on a table not named (QA 11-11). CANARY: the write read its own table."""
    said = {name: len(selects_from(recorded, name)) for name in tables}
    said["*"] = sum(1 for call in recorded if call.sql.lstrip().upper().startswith("SELECT"))
    assert said[tables[0]] > 0, ("CANARY: the recorder saw no read of the written table", said)
    return said


def _door(client, db_session, captured, door, tag, n):
    """`door`'s write on `n` fresh rows' «val» - (its answer, the broadcasts it sent, its reads)."""
    ids = _seed_cells(client, db_session, tag, n)
    captured.clear()                                   # drop the seeding broadcast
    with record_statements(db_session) as recorded:
        if door == "priority":
            res = client.put(f"/tables/{TABLE}/cells/priority/batch", json={
                "updates": [{"row_id": r, "column_name": "val"} for r in ids],
                "source_name": "user", "updated_by": "tester"})
        else:
            res = client.post(f"/tables/{TABLE}/cells/sources/delete/batch", json={
                "cells": [{"row_id": r, "column_name": "val"} for r in ids], "source_name": "user"})
    assert res.status_code == 200, res.text
    return res.json(), list(captured), _reads(recorded)


# ---------------------------------------------------------------------------
# Copies 1 and 2: PUT cells/priority/batch · POST cells/sources/delete/batch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("door", ["priority", "sources_delete"])
def test_above_threshold_the_door_skips_the_merge_it_would_discard(client, db_session, captured_broadcasts, door):
    big = BROADCAST_ITEM_LIMIT + 1
    answer, sent, reads = _door(client, db_session, captured_broadcasts, door, door + "_B1", big)
    assert answer["count"] == big
    # The branch is unchanged: one refresh signal, carrying the same count it did
    # when that count was `len(msg_items)`.
    assert _events(sent, "batch_row_upsert") == []
    [refresh] = _events(sent, "batch_refresh_required")
    assert (refresh["change_count"], refresh["table_name"]) == (big, TABLE)

    assert _door(client, db_session, captured_broadcasts, door, door + "_B2", 2 * big)[2] == reads, \
        "constant in rows - not one read per written row"
    shipped = _door(client, db_session, captured_broadcasts, door, door + "_S", BROADCAST_ITEM_LIMIT)[2]
    assert sum(reads.values()) < sum(shipped.values()), ("the merge it would discard is skipped", reads, shipped)


@pytest.mark.parametrize("door", ["priority", "sources_delete"])
def test_at_threshold_the_door_still_merges_because_it_ships_the_items(client, db_session, captured_broadcasts,
                                                                      door):
    """The consuming arm, unchanged. `include_sources=True` here, so the items carry
    the full `sources` map - dropping this merge would blank the source picker."""
    _answer, sent, reads = _door(client, db_session, captured_broadcasts, door, door + "_S1", BROADCAST_ITEM_LIMIT)
    assert _events(sent, "batch_refresh_required") == []
    [upsert] = _events(sent, "batch_row_upsert")
    assert len(upsert["items"]) == BROADCAST_ITEM_LIMIT
    cell = upsert["items"][0]["data"]["val"]
    assert set(cell) >= {"value", "is_overwrite", "priority_source", "sources"}
    if door == "priority":
        assert cell["manual_priority_source"] == "user", "the pin this request set"
        assert "user" in cell["sources"], "include_sources=True must still be paid for here"
    else:
        assert "user" not in cell["sources"], "the source this request deleted"

    half = _door(client, db_session, captured_broadcasts, door, door + "_S2", BROADCAST_ITEM_LIMIT // 2)[2]
    assert half == reads, "constant in rows - the items it ships cost no read a row"


# ---------------------------------------------------------------------------
# Copy 3: the SILENT batch update - no consumer at any size
# ---------------------------------------------------------------------------

SILENT_ROWS = 50  # deliberately well under BROADCAST_ITEM_LIMIT


def _save(client, db_session, tag, silent, n=SILENT_ROWS):
    with record_statements(db_session) as recorded:
        res = client.put(f"/tables/{TABLE}/data/updates", json={"updates": [
            {"updates": {"die_key": f"{tag}_{i}", "ref_table": "bonding_map",
                         "map_key": tag, "x": i, "y": 0, "val": "1"},
             "source_name": "user", "updated_by": "tester"}
            for i in range(n)], "silent": silent})
    assert res.status_code == 200, res.text
    assert res.json()["updated_count"] == n
    return _reads(recorded)


def test_silent_save_builds_no_items_for_nobody(client, db_session, captured_broadcasts):
    """`silent=True` suppresses the broadcast entirely, and `msg_items` is read
    nowhere else - so a small silent save used to pay a full metadata merge to
    produce a list that was dropped on the floor."""
    reads = _save(client, db_session, "SIL", True)
    assert captured_broadcasts == [], "silent means silent - the contract is unchanged"
    assert _save(client, db_session, "SIL2", True, 2 * SILENT_ROWS) == reads, "constant in rows"
    loud = _save(client, db_session, "LOUD0", False)
    assert sum(reads.values()) < sum(loud.values()), ("the merge for nobody is skipped", reads, loud)


def test_non_silent_save_of_the_same_size_still_merges(client, db_session, captured_broadcasts):
    """The mutation guard for the test above: identical payload, `silent=False`.
    If the skip were keyed on anything but silence this would go quiet too."""
    reads = _save(client, db_session, "LOUD", False)
    [upsert] = _events(captured_broadcasts, "batch_row_upsert")
    assert len(upsert["items"]) == SILENT_ROWS
    assert upsert["items"][0]["data"]["val"]["priority_source"] == "user"
    assert _save(client, db_session, "LOUD2", False, SILENT_ROWS // 2) == reads, "constant in rows"


# ---------------------------------------------------------------------------
# Copy 4: the chain worker
# ---------------------------------------------------------------------------

CHAIN_TABLE = "production_plan"  # business key given directly; no composite assembly
CHAIN_READ = (CHAIN_TABLE, CHAIN_TABLE + "__lines", "cell_overwrites")


def _chain_updates(n, line):
    """`n` rows of their own - keys none of another size's (a size meeting the rows another wrote reads them)."""
    return [{"business_key_val": f"CB{n}_{i}",
             "updates": {"plan_id": f"CB{n}_{i}", "prod_line": line},
             "source_name": "chain_ingestion"}
            for i in range(n)]


def _seed_chain_rows(db, n):
    """Create the target rows before measuring, so the measured batch writes rows that are there."""
    from database import crud, schemas
    crud.apply_batch_updates(db, CHAIN_TABLE, schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(**u) for u in _chain_updates(n, "L0")]))


def chain_budget_mapper(db, payload):
    """The rows its trigger names - the rule imports this module under its own name, so no state here reaches it."""
    said = payload.get("data", payload) if isinstance(payload, dict) else {}
    return {"updates": _chain_updates(int(said["n"]), "L1")}


def _chain_rule():
    return {"name": "p1b_chain_rule", "trigger_table": "p1b_test_trigger",
            "target_table": CHAIN_TABLE,
            "mapper_module": "tests.test_discarded_merge_budget",
            "mapper_function": "chain_budget_mapper", "enabled": True, "is_batch": False}


def _chain_trigger(tx_id, n):
    import uuid
    from database.models import DatabaseOutbox
    return DatabaseOutbox(event_uuid=str(uuid.uuid4()), event_type="CREATE",
                          table_name="p1b_test_trigger",
                          payload={"source_name": "user", "transaction_id": tx_id,
                                   "data": {"k": "v", "n": n}})


async def _chain_group(db_session, n):
    """One chain group answering `n` rows that are there - (its messages, its reads)."""
    from chain.ingestion_worker import process_chain_transaction_group

    _seed_chain_rows(db_session, n)
    tx_id = "p1b_chain_%d" % n
    with record_statements(db_session) as recorded:
        ok, err, msgs = await process_chain_transaction_group(tx_id, [_chain_trigger(tx_id, n)], db_session,
                                                              [_chain_rule()])
    assert ok is True and err is None
    return msgs, _reads(recorded, CHAIN_READ)


@pytest.mark.anyio
async def test_chain_above_threshold_builds_no_items_it_would_discard(db_session):
    big = BROADCAST_ITEM_LIMIT + 1
    msgs, reads = await _chain_group(db_session, big)
    [refresh] = [m for m in msgs if m.get("event") == "batch_refresh_required"]
    assert (refresh["change_count"], refresh["table_name"]) == (big, CHAIN_TABLE)
    assert refresh["transaction_id"] == "chain_p1b_chain_%d" % big
    assert [m for m in msgs if m.get("event") == "batch_row_upsert"] == []
    assert (await _chain_group(db_session, 2 * big))[1] == reads, "constant in rows - not one reload per written row"
    shipped = (await _chain_group(db_session, BROADCAST_ITEM_LIMIT))[1]
    assert sum(reads.values()) < sum(shipped.values()), ("the items it would discard are not built", reads, shipped)


@pytest.mark.anyio
async def test_chain_at_threshold_still_builds_the_items_it_ships(db_session):
    msgs, reads = await _chain_group(db_session, BROADCAST_ITEM_LIMIT)
    [upsert] = [m for m in msgs if m.get("event") == "batch_row_upsert"]
    assert len(upsert["items"]) == BROADCAST_ITEM_LIMIT
    item = upsert["items"][0]
    assert item["data"]["prod_line"]["value"] == "L1"     # a wrapped cell, as every sender's (9eb902922 ①)
    assert item["created_at"] and item["updated_at"]
    # its write step ends in a savepoint, not a commit (총괄 09f58844f) - nothing written is expired, so the items
    # it ships cost no reload
    assert (await _chain_group(db_session, BROADCAST_ITEM_LIMIT // 2))[1] == reads, "constant in rows"


# ---------------------------------------------------------------------------
# The threshold itself
# ---------------------------------------------------------------------------

def test_every_sender_reads_the_same_threshold():
    """Four senders decide the same client-facing contract. The documented failure
    mode of this codebase is one of them being corrected while the others keep the
    old literal (see the created_logs truncation history)."""
    import main
    from chain import ingestion_worker

    assert BROADCAST_ITEM_LIMIT == 100
    assert main.BROADCAST_ITEM_LIMIT is BROADCAST_ITEM_LIMIT
    assert ingestion_worker.BROADCAST_ITEM_LIMIT is BROADCAST_ITEM_LIMIT
