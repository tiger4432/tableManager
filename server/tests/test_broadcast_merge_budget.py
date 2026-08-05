"""[P1] A save large enough to broadcast `batch_refresh_required` must not first
read back the metadata for everything it just wrote.

`PUT /tables/{t}/data/updates` used to build `msg_items` unconditionally - one
`cell_overwrites` query over every written row plus an O(rows x columns) merge -
and only THEN ask `len(msg_items) > 100`. Above the threshold the answer is a
count, so the entire merge was computed and thrown away on exactly the saves big
enough for it to hurt.

The two tests below are a matched pair on purpose. Skipping work is only correct
if the branch that fires is unchanged, so one test pins that the big save still
does no merge AND still broadcasts the same refresh signal, and the other pins
that the small save (which consumes `msg_items`) still pays for it.
"""

import json

import pytest

from sql_budget import record_statements, selects_from


THRESHOLD = 100  # main.py: len(msg_items) > 100 -> refresh signal instead of items


def _new_cells(map_key, count):
    """`count` brand-new map rows. New rows have no stored metadata at all, so
    every `cell_overwrites` SELECT during the request comes from the merge."""
    return {
        "updates": [
            {"updates": {"die_key": f"{map_key}_{i}", "ref_table": "bonding_map",
                         "map_key": map_key, "x": i, "y": 0, "val": "1"},
             "source_name": "user", "updated_by": "tester"}
            for i in range(count)
        ]
    }


@pytest.fixture
def captured_broadcasts(monkeypatch):
    import main
    sent = []

    async def _capture(message):
        sent.append(json.loads(message))

    monkeypatch.setattr(main.manager, "broadcast", _capture)
    return sent


def test_refresh_sized_save_skips_the_merge_it_would_discard(
        client, db_session, captured_broadcasts):
    payload = _new_cells("P1_BIG", THRESHOLD + 1)

    with record_statements(db_session) as recorded:
        res = client.put("/tables/rmscope_test_map/data/updates", json=payload)

    assert res.status_code == 200
    assert res.json()["updated_count"] == THRESHOLD + 1

    # The branch is unchanged: still one refresh signal, still carrying the row count.
    upserts = [m for m in captured_broadcasts if m["event"] == "batch_row_upsert"]
    refreshes = [m for m in captured_broadcasts if m["event"] == "batch_refresh_required"]
    assert upserts == []
    assert len(refreshes) == 1
    assert refreshes[0]["change_count"] == THRESHOLD + 1
    assert refreshes[0]["table_name"] == "rmscope_test_map"

    # ...and nothing read cell_overwrites back. All rows are new, so the batch
    # itself never queries that table; a SELECT here can only be the merge.
    assert selects_from(recorded, "cell_overwrites") == []

    # The larger half of the bill. `crud.apply_batch_updates` commits, which
    # EXPIRES every instance in `results`; the merge's first act is `[r.row_id for
    # r in rows]`, so each expired row was reloaded one statement at a time. The
    # batch's own key lookup is the single legitimate SELECT on this table.
    assert len(selects_from(recorded, "rmscope_test_map")) == 1, (
        "a discarded merge also pays one ORM refresh per row, because the commit "
        "inside crud expired them all")


def test_item_sized_save_still_merges_because_it_ships_the_items(
        client, db_session, captured_broadcasts):
    """The other side of the pair. `msg_items` IS the payload below the
    threshold, so the merge must still run - a skip that swallowed this case
    would ship rows with no `is_overwrite`/`priority_source` and the grid would
    silently lose every overwrite marker."""
    payload = _new_cells("P1_SMALL", THRESHOLD)

    with record_statements(db_session) as recorded:
        res = client.put("/tables/rmscope_test_map/data/updates", json=payload)

    assert res.status_code == 200

    refreshes = [m for m in captured_broadcasts if m["event"] == "batch_refresh_required"]
    upserts = [m for m in captured_broadcasts if m["event"] == "batch_row_upsert"]
    assert refreshes == []
    assert len(upserts) == 1
    assert len(upserts[0]["items"]) == THRESHOLD
    # The merged shape the client contract requires, on a real item.
    cell = upserts[0]["items"][0]["data"]["val"]
    assert set(cell) >= {"value", "is_overwrite", "priority_source"}
    assert cell["priority_source"] == "user"

    assert len(selects_from(recorded, "cell_overwrites")) == 1
