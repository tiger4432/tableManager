"""[P4] `PUT /tables/{t}/data/updates` must not return the whole audit trail it
just wrote.

The response body carried one audit-log dict per CHANGED CELL, so its size is
rows x columns, not rows. A map push is the worst case in the product: 20,000 dies
x one row of columns each, returned as JSON built by the encoder on the event loop
and parsed on the browser's main thread. That is the same shape as the 2026-07-25
incident (a ~50 MB `created_logs` payload froze :8080 for tens of seconds), except
on the response path instead of the internal-event path - where the truncation
already exists.

Nothing read it. `created_logs` appears twice under `client2/src`: `websocket.js`
consumes it off the WEBSOCKET message, and one comment in `effort_meter.js`. The
WS message is deliberately NOT changed here.

The fix is the truncate-plus-count contract already in use for internal events:
key present, still a list, capped at `MAX_NOTIFY_CREATED_LOGS`, with the honest
pre-truncation total in `total_log_count`.

Counts and structure, not bytes: a byte figure is a fact about this fixture's
column widths, the entry count is a fact about the contract.
"""

import json

import pytest

from event_constants import MAX_NOTIFY_CREATED_LOGS
from sql_budget import record_statements  # noqa: F401  (kept for symmetry of imports)


TABLE = "rmscope_test_map"
COLUMNS_PER_ROW = 6  # die_key, ref_table, map_key, x, y, val - all written, all logged


@pytest.fixture(autouse=True)
def _no_broadcast(monkeypatch):
    """The WS payload is a separate contract and is not under test here; silence it
    so this module measures the RESPONSE only."""
    import main

    async def _sink(message):
        return None

    monkeypatch.setattr(main.manager, "broadcast", _sink)


def _push(client, tag, rows):
    # `business_key_val` is sent explicitly. `rmscope_test_map` declares no
    # `composite_key_source`, so without it a repeat push would not resolve the
    # existing rows and the no-op case below could never be constructed.
    payload = {"updates": [
        {"business_key_val": f"{tag}_{i}",
         "updates": {"die_key": f"{tag}_{i}", "ref_table": "bonding_map",
                     "map_key": tag, "x": i, "y": 0, "val": "1"},
         "source_name": "user", "updated_by": "tester"}
        for i in range(rows)]}
    res = client.put(f"/tables/{TABLE}/data/updates", json=payload)
    assert res.status_code == 200, res.text
    return res


def test_a_map_sized_push_does_not_return_a_log_per_cell(client, db_session):
    rows = 200
    res = _push(client, "P4BIG", rows)
    body = res.json()

    created = rows * COLUMNS_PER_ROW  # 1,200 - what the body used to carry in full
    assert body["total_log_count"] == created, (
        "the honest total must survive truncation; a caller detects truncation as "
        "len(created_logs) < total_log_count")
    assert len(body["created_logs"]) == MAX_NOTIFY_CREATED_LOGS

    # The key is still present and still a list of the same dicts - the shape a caller
    # could have been relying on is intact, only bounded.
    assert isinstance(body["created_logs"], list)
    first = body["created_logs"][0]
    assert {"row_id", "column_name", "new_value", "transaction_id"} <= set(first)

    # And the entries are a PREFIX of what was created, not a resample: the first log
    # of the first row is still first.
    assert first["new_value"] == "P4BIG_0"

    # The bound is on the response, so the body can no longer grow with the map. This
    # is the property, stated as a count: 1,200 log dicts became 500, and 20,000 dies
    # would also be 500.
    assert len(json.dumps(body["created_logs"])) < len(json.dumps(
        [first] * created)), "the truncated body is smaller than the untruncated one"


def test_a_push_under_the_cap_returns_every_log_and_an_equal_total(client, db_session):
    """The matched pair. Truncation must not fire on ordinary saves - an editor
    correcting a handful of cells still gets the complete list it always got, and
    `total_log_count` must equal it so 'was I truncated?' is answerable."""
    rows = 10
    body = _push(client, "P4SMALL", rows).json()

    created = rows * COLUMNS_PER_ROW  # 60, well under the cap
    assert created < MAX_NOTIFY_CREATED_LOGS
    assert body["total_log_count"] == created
    assert len(body["created_logs"]) == created
    assert len(body["created_logs"]) == body["total_log_count"], \
        "not truncated means the two agree"


def test_a_noop_save_still_returns_the_empty_list_it_always_did(client, db_session):
    """`client2/src/effort_meter.js` documents the no-op response as
    `{change_count: 0, created_logs: []}`. The key must not become absent or null."""
    _push(client, "P4NOOP", 3)
    body = _push(client, "P4NOOP", 3).json()  # identical values -> nothing changes

    assert body["change_count"] == 0
    assert body["created_logs"] == []
    assert body["total_log_count"] == 0


def test_the_cap_is_the_one_the_internal_event_payload_already_uses(client, db_session):
    """Not a second convention. If someone raises the internal-event cap, this moves
    with it, because there is one constant."""
    import main
    assert main.MAX_NOTIFY_CREATED_LOGS is MAX_NOTIFY_CREATED_LOGS

    body = _push(client, "P4CAP", 200).json()
    assert len(body["created_logs"]) == MAX_NOTIFY_CREATED_LOGS


def test_the_websocket_payload_is_untouched_by_the_response_bound(client, db_session,
                                                                  monkeypatch):
    """The WS message is a boundary contract with the client and is NOT part of P4.
    A save under the broadcast item limit must still ship its per-row items with
    their own `created_logs`, unchanged."""
    import main
    sent = []

    async def _capture(message):
        sent.append(json.loads(message))

    monkeypatch.setattr(main.manager, "broadcast", _capture)

    rows = 10
    body = _push(client, "P4WS", rows).json()

    upserts = [m for m in sent if m["event"] == "batch_row_upsert"]
    assert len(upserts) == 1
    assert len(upserts[0]["items"]) == rows
    # The WS message carries the full log set for its chunk, on its own rules.
    assert len(upserts[0]["created_logs"]) == body["total_log_count"]
