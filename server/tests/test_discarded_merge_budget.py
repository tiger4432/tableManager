"""[P1b] The discarded-merge pattern's remaining three copies, plus the copy that
had no consumer at any size.

Tier 0 corrected `PUT /tables/{t}/data/updates`: it built `msg_items` (one
`cell_overwrites` read-back of everything just written, plus an O(rows x columns)
merge) and only THEN asked whether the broadcast wanted items. The same decision
is written at four more places, and this module pins all four.

Three of them are the same shape as Tier 0's:

  * `PUT  /tables/{t}/cells/priority/batch`        (`set_cell_priority_batch_endpoint`)
  * `POST /tables/{t}/cells/sources/delete/batch`  (`delete_cell_source_batch_endpoint`)
  * `chain_ingestion_worker.process_chain_transaction_group`

The fourth is not a size question at all: `msg_items` in the batch-update endpoint
is read ONLY inside `if not batch.silent:`, so a SILENT save under the threshold
paid the whole merge for nobody.

WHY THE BILL IS N+1 AND NOT ONE QUERY. Every one of these sites runs after a crud
function that COMMITS. `expire_on_commit` is true, so each written row is expired;
the first attribute read on it (`[r.row_id for r in rows]` in
`fetch_and_merge_metadata`, `row.created_at` in the chain worker) reloads it with
its own SELECT. The merge query is the small half of the bill.

Every test below is a matched PAIR. Skipping work is only correct if the branch
that fires is unchanged, so each "skips it" test is accompanied by one pinning that
the arm which really consumes the items still pays for them and still ships the
merged cell shape. A skip that swallowed the consuming case would broadcast rows
with no `is_overwrite`/`priority_source` and the grid would silently lose every
overwrite marker.

Counts, not timings: these numbers are identical on SQLite and PostgreSQL.
"""

import json

import pytest

from event_constants import BROADCAST_ITEM_LIMIT
from sql_budget import record_statements, selects_from


TABLE = "rmscope_test_map"

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


# ---------------------------------------------------------------------------
# Copy 1: PUT /tables/{t}/cells/priority/batch
# ---------------------------------------------------------------------------

def test_priority_pin_above_threshold_skips_the_merge_it_would_discard(
        client, db_session, captured_broadcasts):
    ids = _seed_cells(client, db_session, "PRI_BIG", BROADCAST_ITEM_LIMIT + 1)
    captured_broadcasts.clear()  # drop the seeding broadcast

    body = {"updates": [{"row_id": r, "column_name": "val"} for r in ids],
            "source_name": "user", "updated_by": "tester"}
    with record_statements(db_session) as recorded:
        res = client.put(f"/tables/{TABLE}/cells/priority/batch", json=body)

    assert res.status_code == 200
    assert res.json()["count"] == BROADCAST_ITEM_LIMIT + 1

    # The branch is unchanged: one refresh signal, carrying the same count it did
    # when that count was `len(msg_items)`.
    assert _events(captured_broadcasts, "batch_row_upsert") == []
    refreshes = _events(captured_broadcasts, "batch_refresh_required")
    assert len(refreshes) == 1
    assert refreshes[0]["change_count"] == BROADCAST_ITEM_LIMIT + 1
    assert refreshes[0]["table_name"] == TABLE

    # One SELECT on each table, and each one is work that produced the write:
    # crud's row lookup, and crud's two metadata prefetches. The merge's own
    # `cell_overwrites` + `cell_sources` reads are gone, and so are the 101 per-row
    # reloads its first line used to trigger.
    assert len(selects_from(recorded, TABLE)) == 1, (
        "a discarded merge also pays one ORM refresh per row, because "
        "set_cell_manual_priority_batch commits and expires them all")
    assert len(selects_from(recorded, "cell_overwrites")) == 1
    assert len(selects_from(recorded, "cell_sources")) == 1


def test_priority_pin_at_threshold_still_merges_because_it_ships_the_items(
        client, db_session, captured_broadcasts):
    """The consuming arm, unchanged. `include_sources=True` here, so the items carry
    the full `sources` map - dropping this merge would blank the source picker."""
    ids = _seed_cells(client, db_session, "PRI_SMALL", BROADCAST_ITEM_LIMIT)
    captured_broadcasts.clear()

    body = {"updates": [{"row_id": r, "column_name": "val"} for r in ids],
            "source_name": "user", "updated_by": "tester"}
    with record_statements(db_session) as recorded:
        res = client.put(f"/tables/{TABLE}/cells/priority/batch", json=body)

    assert res.status_code == 200
    assert _events(captured_broadcasts, "batch_refresh_required") == []
    upserts = _events(captured_broadcasts, "batch_row_upsert")
    assert len(upserts) == 1
    assert len(upserts[0]["items"]) == BROADCAST_ITEM_LIMIT

    cell = upserts[0]["items"][0]["data"]["val"]
    assert set(cell) >= {"value", "is_overwrite", "priority_source", "sources"}
    assert cell["manual_priority_source"] == "user", "the pin this request set"
    assert "user" in cell["sources"], "include_sources=True must still be paid for here"

    # The merge still runs on this arm: two reads of each metadata table (crud's
    # prefetch and the merge's), and the per-row reloads after crud's commit.
    assert len(selects_from(recorded, "cell_overwrites")) == 2
    assert len(selects_from(recorded, "cell_sources")) == 2
    assert len(selects_from(recorded, TABLE)) == BROADCAST_ITEM_LIMIT + 1


# ---------------------------------------------------------------------------
# Copy 2: POST /tables/{t}/cells/sources/delete/batch
# ---------------------------------------------------------------------------

def test_source_delete_above_threshold_skips_the_merge_it_would_discard(
        client, db_session, captured_broadcasts):
    ids = _seed_cells(client, db_session, "DEL_BIG", BROADCAST_ITEM_LIMIT + 1)
    captured_broadcasts.clear()

    body = {"cells": [{"row_id": r, "column_name": "val"} for r in ids],
            "source_name": "user"}
    with record_statements(db_session) as recorded:
        res = client.post(f"/tables/{TABLE}/cells/sources/delete/batch", json=body)

    assert res.status_code == 200
    assert res.json()["count"] == BROADCAST_ITEM_LIMIT + 1

    assert _events(captured_broadcasts, "batch_row_upsert") == []
    refreshes = _events(captured_broadcasts, "batch_refresh_required")
    assert len(refreshes) == 1
    assert refreshes[0]["change_count"] == BROADCAST_ITEM_LIMIT + 1

    assert len(selects_from(recorded, TABLE)) == 1
    assert len(selects_from(recorded, "cell_overwrites")) == 1
    assert len(selects_from(recorded, "cell_sources")) == 1


def test_source_delete_at_threshold_still_merges_because_it_ships_the_items(
        client, db_session, captured_broadcasts):
    ids = _seed_cells(client, db_session, "DEL_SMALL", BROADCAST_ITEM_LIMIT)
    captured_broadcasts.clear()

    body = {"cells": [{"row_id": r, "column_name": "val"} for r in ids],
            "source_name": "user"}
    with record_statements(db_session) as recorded:
        res = client.post(f"/tables/{TABLE}/cells/sources/delete/batch", json=body)

    assert res.status_code == 200
    upserts = _events(captured_broadcasts, "batch_row_upsert")
    assert len(upserts) == 1
    assert len(upserts[0]["items"]) == BROADCAST_ITEM_LIMIT
    cell = upserts[0]["items"][0]["data"]["val"]
    assert set(cell) >= {"value", "is_overwrite", "priority_source", "sources"}
    assert "user" not in cell["sources"], "the source this request deleted"

    assert len(selects_from(recorded, "cell_overwrites")) == 2
    assert len(selects_from(recorded, "cell_sources")) == 2
    assert len(selects_from(recorded, TABLE)) == BROADCAST_ITEM_LIMIT + 1


# ---------------------------------------------------------------------------
# Copy 3: the SILENT batch update - no consumer at any size
# ---------------------------------------------------------------------------

SILENT_ROWS = 50  # deliberately well under BROADCAST_ITEM_LIMIT


def _silent_payload(tag, silent):
    return {"updates": [
        {"updates": {"die_key": f"{tag}_{i}", "ref_table": "bonding_map",
                     "map_key": tag, "x": i, "y": 0, "val": "1"},
         "source_name": "user", "updated_by": "tester"}
        for i in range(SILENT_ROWS)], "silent": silent}


def test_silent_save_builds_no_items_for_nobody(
        client, db_session, captured_broadcasts):
    """`silent=True` suppresses the broadcast entirely, and `msg_items` is read
    nowhere else - so a small silent save used to pay a full metadata merge and 50
    per-row reloads to produce a list that was dropped on the floor."""
    with record_statements(db_session) as recorded:
        res = client.put(f"/tables/{TABLE}/data/updates",
                         json=_silent_payload("SIL", True))

    assert res.status_code == 200
    assert res.json()["updated_count"] == SILENT_ROWS
    assert captured_broadcasts == [], "silent means silent - the contract is unchanged"

    # Nothing read cell_overwrites back at all. Every row is new, so the batch itself
    # never queries that table (P2 memoises the absence); a SELECT here could only be
    # the merge.
    assert selects_from(recorded, "cell_overwrites") == []
    assert len(selects_from(recorded, TABLE)) == 1, (
        "one lookup, the batch's own - not one reload per written row")


def test_non_silent_save_of_the_same_size_still_merges(
        client, db_session, captured_broadcasts):
    """The mutation guard for the test above: identical payload, `silent=False`.
    If the skip were keyed on anything but silence this would go quiet too."""
    with record_statements(db_session) as recorded:
        res = client.put(f"/tables/{TABLE}/data/updates",
                         json=_silent_payload("LOUD", False))

    assert res.status_code == 200
    upserts = _events(captured_broadcasts, "batch_row_upsert")
    assert len(upserts) == 1
    assert len(upserts[0]["items"]) == SILENT_ROWS
    cell = upserts[0]["items"][0]["data"]["val"]
    assert cell["priority_source"] == "user"

    assert len(selects_from(recorded, "cell_overwrites")) == 1, "the merge"
    assert len(selects_from(recorded, TABLE)) == SILENT_ROWS + 1


# ---------------------------------------------------------------------------
# Copy 4: the chain worker
# ---------------------------------------------------------------------------

CHAIN_TABLE = "production_plan"  # business key given directly; no composite assembly


def _chain_updates(n, line):
    return [{"business_key_val": f"CB{i}",
             "updates": {"plan_id": f"CB{i}", "prod_line": line},
             "source_name": "chain_ingestion"}
            for i in range(n)]


def _seed_chain_rows(db, n):
    """Create the target rows before measuring.

    Without this the measured batch is an INSERT batch, and `_get_or_create_row`
    issues its own `WHERE business_key_val = ?` per row looking for a row that does
    not exist yet - a separate, real cost that has nothing to do with the item build
    and would swamp it. Seeding first makes the prefetch resolve every row, so the
    only per-row statements left in the window are the post-commit reloads this test
    is about.
    """
    from database import crud, schemas
    crud.apply_batch_updates(db, CHAIN_TABLE, schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(**u) for u in _chain_updates(n, "L0")]))


def chain_budget_mapper_over(db, payload):
    return {"updates": _chain_updates(BROADCAST_ITEM_LIMIT + 1, "L1")}


def chain_budget_mapper_under(db, payload):
    return {"updates": _chain_updates(BROADCAST_ITEM_LIMIT, "L1")}


def _chain_rule(func_name):
    return {"name": "p1b_chain_rule", "trigger_table": "p1b_test_trigger",
            "target_table": CHAIN_TABLE,
            "mapper_module": "tests.test_discarded_merge_budget",
            "mapper_function": func_name, "enabled": True, "is_batch": False}


def _chain_trigger(tx_id):
    import uuid
    from database.models import DatabaseOutbox
    return DatabaseOutbox(event_uuid=str(uuid.uuid4()), event_type="CREATE",
                          table_name="p1b_test_trigger",
                          payload={"source_name": "user", "transaction_id": tx_id,
                                   "data": {"k": "v"}})


@pytest.mark.anyio
async def test_chain_above_threshold_builds_no_items_it_would_discard(db_session):
    """The chain worker has no metadata merge, so its whole bill IS the reloads:
    `to_local_str(row.created_at)` on a row expired by crud's commit."""
    from chain_ingestion_worker import process_chain_transaction_group

    _seed_chain_rows(db_session, BROADCAST_ITEM_LIMIT + 1)
    tx_id = "p1b_chain_over"
    with record_statements(db_session) as recorded:
        ok, err, msgs = await process_chain_transaction_group(
            tx_id, [_chain_trigger(tx_id)], db_session,
            [_chain_rule("chain_budget_mapper_over")])

    assert ok is True and err is None
    refreshes = [m for m in msgs if m.get("event") == "batch_refresh_required"]
    assert len(refreshes) == 1
    assert refreshes[0]["change_count"] == BROADCAST_ITEM_LIMIT + 1
    assert refreshes[0]["table_name"] == CHAIN_TABLE
    assert refreshes[0]["transaction_id"] == f"chain_{tx_id}"
    assert [m for m in msgs if m.get("event") == "batch_row_upsert"] == []

    assert len(selects_from(recorded, CHAIN_TABLE)) == 1, (
        "crud's own prefetch, and nothing else - not one reload per written row")


@pytest.mark.anyio
async def test_chain_at_threshold_still_builds_the_items_it_ships(db_session):
    from chain_ingestion_worker import process_chain_transaction_group

    _seed_chain_rows(db_session, BROADCAST_ITEM_LIMIT)
    tx_id = "p1b_chain_under"
    with record_statements(db_session) as recorded:
        ok, err, msgs = await process_chain_transaction_group(
            tx_id, [_chain_trigger(tx_id)], db_session,
            [_chain_rule("chain_budget_mapper_under")])

    assert ok is True and err is None
    upserts = [m for m in msgs if m.get("event") == "batch_row_upsert"]
    assert len(upserts) == 1
    assert len(upserts[0]["items"]) == BROADCAST_ITEM_LIMIT
    item = upserts[0]["items"][0]
    assert item["data"]["prod_line"] == "L1"
    assert item["created_at"] and item["updated_at"]

    assert len(selects_from(recorded, CHAIN_TABLE)) == BROADCAST_ITEM_LIMIT + 1, (
        "the items this arm really sends still cost their reloads")


# ---------------------------------------------------------------------------
# The threshold itself
# ---------------------------------------------------------------------------

def test_every_sender_reads_the_same_threshold():
    """Four senders decide the same client-facing contract. The documented failure
    mode of this codebase is one of them being corrected while the others keep the
    old literal (see the created_logs truncation history)."""
    import main
    import chain_ingestion_worker

    assert BROADCAST_ITEM_LIMIT == 100
    assert main.BROADCAST_ITEM_LIMIT is BROADCAST_ITEM_LIMIT
    assert chain_ingestion_worker.BROADCAST_ITEM_LIMIT is BROADCAST_ITEM_LIMIT
