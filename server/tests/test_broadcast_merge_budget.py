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
def write_spans(monkeypatch):
    """Where in a recording the WRITE ran - `crud.apply_batch_updates`, which the route calls. The overhaul's write
    reads cell_overwrites itself (its cells' pins, `write_lines._overwrites`; the row's shown value, `lines.merge`);
    what this file budgets is the route's merge after the write (`grid_read.read_as_page`), so the write's statements
    are set apart. -> (live: put the recording in it as "recorded", spans: [(start, end)])"""
    from database import crud
    live, spans, real = {}, [], crud.apply_batch_updates

    def noted(*args, **kwargs):
        start = len(live["recorded"]) if "recorded" in live else None
        try:
            return real(*args, **kwargs)
        finally:
            if start is not None:
                spans.append((start, len(live["recorded"])))

    monkeypatch.setattr(crud, "apply_batch_updates", noted)
    return live, spans


def _merge_selects(recorded, spans, table_name):
    """The SELECTs of `table_name` outside the write (`write_spans`)."""
    inside = {i for start, end in spans for i in range(start, end)}
    return selects_from([call for i, call in enumerate(recorded) if i not in inside], table_name)


@pytest.fixture
def captured_broadcasts(monkeypatch):
    import main
    sent = []

    async def _capture(message):
        sent.append(json.loads(message))

    monkeypatch.setattr(main.manager, "broadcast", _capture)
    return sent


def test_refresh_sized_save_skips_the_merge_it_would_discard(
        client, db_session, captured_broadcasts, write_spans):
    payload = _new_cells("P1_BIG", THRESHOLD + 1)
    live, spans = write_spans

    with record_statements(db_session) as recorded:
        live["recorded"] = recorded
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

    # ...and nothing read cell_overwrites back. The write's own statements are set apart
    # (`write_spans`); a SELECT left can only be the merge.
    assert spans, "CANARY: the write ran inside the recording"
    assert _merge_selects(recorded, spans, "cell_overwrites") == []

    # The larger half of the bill. `crud.apply_batch_updates` commits, which
    # EXPIRES every instance in `results`; the merge's first act is `[r.row_id for
    # r in rows]`, so each expired row was reloaded one statement at a time. The
    # write's own reads of this table are the write's (`write_spans`); after it,
    # none - a reload per row would be THRESHOLD + 1 of them.
    assert len(_merge_selects(recorded, spans, "rmscope_test_map")) == 0, (
        "a discarded merge also pays one ORM refresh per row, because the commit "
        "inside crud expired them all")


def test_item_sized_save_still_merges_because_it_ships_the_items(
        client, db_session, captured_broadcasts, write_spans):
    """The other side of the pair. `msg_items` IS the payload below the
    threshold, so the merge must still run - a skip that swallowed this case
    would ship rows with no `is_overwrite`/`priority_source` and the grid would
    silently lose every overwrite marker."""
    payload = _new_cells("P1_SMALL", THRESHOLD)
    live, spans = write_spans

    with record_statements(db_session) as recorded:
        live["recorded"] = recorded
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

    assert spans, "CANARY: the write ran inside the recording"
    assert len(_merge_selects(recorded, spans, "cell_overwrites")) == 1
