"""A `replace_map` push can write a row that belongs to a DIFFERENT map.

WHAT THIS IS ABOUT

`apply_batch_updates` resolves an incoming cell to a stored row by business key, and the
lookup it falls through to (`crud._get_or_create_row` -> `crud.get_row_by_business_key`)
filters on `business_key_val` ALONE - no map-scope filter, `.first()`. There is no unique
index on that column (verified physically: 0 of 50 covering indexes on the live dev
database are unique, 0 table constraints name it).

For a table whose map key is INSIDE its composite business key, that is harmless: a key
names its own map, so a row with that key cannot belong to another one. Every map table
that ships today is that shape except one.

`dt_log` is the exception, and deliberately so. Its business key is the physical
destination cell `(dt_job, dt_x, dt_y)`; its map key `(dt_lot, dt_slot)` is kept OUT of
the key because those two columns are inference targets - `table_config` records that
they are ~40% absent and ~10% present-but-wrong, and that "a guess must never sit inside
an identity". So two different maps CAN mint the same business key there.

`xscope_test_map` copies that shape and `xscope_safe_map` copies the ordinary one, so the
pair differs in exactly the property under test.

WHAT IS PROVEN AND WHAT IS STILL OPEN

Proven, and pinned by `test_push_into_one_map_rewrites_a_row_owned_by_another`: a push
into map A finds map B's row and rewrites it in place, keeping its row_id and taking over
its `lot`/`slot`. Map B loses the cell from its scope.

NOT settled, and deliberately not asserted as a verdict here: whether that re-attribution
is a defect or the point. For `dt_log` the row's identity is a physical tape cell and its
lot/slot are guesses being corrected, so a push that moves a cell into the map it really
belongs to may be exactly the correction the table exists to receive. Making identity
scope-local would instead create a SECOND row for one physical cell, which contradicts
the invariant `table_config` declares and the data upholds (8,995 rows / 8,995 distinct
business keys / 0 duplicate triples on the live dev database).

What is wrong under BOTH readings is the REPORT, which is what
`test_replace_map_reports_the_rows_it_wrote_into_this_map` pins: the response's `scope`
block is the honesty contract for a `replace_map` write, and it currently answers
`deleted: 0, inserted: 0` for a request that left one row in a map that had none.
"""
import json
from urllib.parse import quote

import pytest


def _rows(client, table, col, value):
    filters = json.dumps({col: {"filterType": "text", "type": "equals", "filter": value}})
    res = client.get(f"/tables/{table}/data?filters={quote(filters)}")
    assert res.status_code == 200
    return res.json()["data"]


def _push(client, table, *, job=None, lot, slot, cx, cy, bn, replace_map):
    updates = {"lot": lot, "slot": slot, "cx": cx, "cy": cy, "bn": bn}
    if job is not None:
        updates["job"] = job
    res = client.put(f"/tables/{table}/data/updates", json={
        "updates": [{"updates": updates, "source_name": "user", "updated_by": "tester"}],
        "replace_map": replace_map,
    })
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# CONTROL - the shape every other map table ships with.
# Must pass today and must keep passing: it is what says the exposure is confined
# to the one table whose key deliberately excludes its map key.
# ---------------------------------------------------------------------------

def test_map_key_inside_the_business_key_cannot_collide_across_maps(client):
    t = "xscope_safe_map"
    _push(client, t, lot="SAFE_B", slot="01", cx=1, cy=1, bn="B_ORIGINAL", replace_map=False)
    _push(client, t, lot="SAFE_A", slot="02", cx=1, cy=1, bn="A_PUSHED", replace_map=True)

    b = _rows(client, t, "lot", "SAFE_B")
    a = _rows(client, t, "lot", "SAFE_A")
    assert len(b) == 1, "map B must keep its own row"
    assert str(b[0]["data"]["bn"]["value"]) == "B_ORIGINAL", "map B's value must be untouched"
    assert len(a) == 1, "map A must get a row of its own"
    assert str(a[0]["data"]["bn"]["value"]) == "A_PUSHED"
    assert b[0]["row_id"] != a[0]["row_id"], "two maps, two rows"


# ---------------------------------------------------------------------------
# RED - the report is false under either reading of the semantics.
# ---------------------------------------------------------------------------

def test_replace_map_reports_the_rows_it_wrote_into_this_map(client):
    """`scope` is the honesty contract: it must account for what the write did to
    THIS map. Map A starts empty and ends with one cell, so a report of
    `deleted: 0, inserted: 0` describes a request that did nothing - and one did.

    This assertion does not depend on whether adopting the row is right or wrong.
    Either the row is map A's now (then map A gained a row and `inserted` must say
    so) or it is not (then map A must have got its own row, and `inserted` must
    still say so). `0` is the one answer that cannot be true.
    """
    t = "xscope_test_map"
    _push(client, t, job="JOB_R", lot="REP_B", slot="01", cx=1, cy=1,
          bn="B_ORIGINAL", replace_map=False)
    assert len(_rows(client, t, "lot", "REP_A")) == 0, "map A starts empty"

    body = _push(client, t, job="JOB_R", lot="REP_A", slot="02", cx=1, cy=1,
                 bn="A_PUSHED", replace_map=True)

    in_a = _rows(client, t, "lot", "REP_A")
    assert len(in_a) == 1, "map A ends with exactly one cell"
    assert body["scope"]["filters"] == {"lot": "REP_A", "slot": "02"}

    scope = body["scope"]
    accounted = scope["deleted"] + scope["inserted"] + scope.get("adopted", 0)
    assert accounted == len(in_a), (
        f"map A went from 0 cells to {len(in_a)}, so the report must account for "
        f"{len(in_a)} row(s). It accounted for {accounted}: deleted={scope['deleted']} "
        f"inserted={scope['inserted']} adopted={scope.get('adopted', 0)}"
    )
    # and the row is named, not just counted - a count alone cannot be reconciled
    # against the delete event by a consumer that missed it.
    assert in_a[0]["row_id"] in (body.get("deleted_row_ids") or []), (
        "the adopted row left the map it used to belong to, so it must be announced "
        "as a departure; otherwise that map's viewers are never told"
    )


# ---------------------------------------------------------------------------
# RED - and this one encodes the CONTESTED expectation. See the module docstring:
# whether map B should keep its row is a product question, not a code question.
# It is written as the coordinator specified so the behaviour is on the record;
# do NOT write a fix aimed at making it green until that ruling exists.
# ---------------------------------------------------------------------------

def test_adopted_id_list_is_capped_and_says_so(client):
    """Populating `deleted_row_ids` is what makes the uncapped broadcast branch
    reachable at size, so the cap ships with the population, not after it.

    The adopted set is bounded by the payload and by nothing smaller: every payload
    item resolves at most one row, so a 20k-cell push can adopt 20k rows. That is why
    "small in the fixture" is not a bound and the cap is not optional.
    """
    from event_constants import BROADCAST_ITEM_LIMIT

    t = "xscope_test_map"
    n = BROADCAST_ITEM_LIMIT + 5
    seed = [{"updates": {"job": f"CAP_{i}", "cx": i, "cy": 0, "lot": "CAP_B",
                         "slot": "01", "bn": "B"},
             "source_name": "user", "updated_by": "tester"} for i in range(n)]
    r = client.put(f"/tables/{t}/data/updates", json={"updates": seed, "replace_map": False})
    assert r.status_code == 200

    take = [{"updates": {"job": f"CAP_{i}", "cx": i, "cy": 0, "lot": "CAP_A",
                         "slot": "02", "bn": "A"},
             "source_name": "user", "updated_by": "tester"} for i in range(n)]
    body = client.put(f"/tables/{t}/data/updates",
                      json={"updates": take, "replace_map": True}).json()

    assert body["scope"]["adopted"] == n, "every seeded row should have been adopted"
    assert len(body["deleted_row_ids"]) == n, "the response still names every one"
    assert body["scope"]["delete_ids_omitted"] == n, (
        "the id list exceeds BROADCAST_ITEM_LIMIT, so the broadcast withholds it - and "
        "the response must say so rather than let the caller read silence as 'none'"
    )


@pytest.mark.xfail(strict=True, reason=(
    "Contested expectation, not a known-broken feature. `strict` is the point: this is "
    "green while the current behaviour holds and turns RED the moment someone changes "
    "it without removing the marker - which is the alarm we want, and is not what a "
    "plain red test gives you in a tree where five lanes read the same suite output. "
    "Remove the marker only together with the product ruling that settles it."
))
def test_push_into_one_map_rewrites_a_row_owned_by_another(client):
    t = "xscope_test_map"
    _push(client, t, job="JOB_X", lot="LOT_B", slot="01", cx=1, cy=1,
          bn="B_ORIGINAL", replace_map=False)
    before = _rows(client, t, "lot", "LOT_B")
    assert len(before) == 1
    b_row_id = before[0]["row_id"]

    _push(client, t, job="JOB_X", lot="LOT_A", slot="02", cx=1, cy=1,
          bn="A_PUSHED", replace_map=True)

    after_b = _rows(client, t, "lot", "LOT_B")
    after_a = _rows(client, t, "lot", "LOT_A")
    assert len(after_b) == 1, (
        f"map B (LOT_B/01) no longer owns its cell: a replace_map push scoped to "
        f"(LOT_A, 02) rewrote row {b_row_id[:8]} in place. Map B's rows were never "
        f"in the purge scope and were never reported as deleted."
    )
    assert str(after_b[0]["data"]["bn"]["value"]) == "B_ORIGINAL"
    assert len(after_a) == 1
    assert after_a[0]["row_id"] != b_row_id
