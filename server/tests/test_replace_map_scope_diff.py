"""`replace_map` replaces a map by DIFFERENCE, not by purge-and-rewrite.

WHAT CHANGED

The write used to delete every row in the map's scope and re-insert the payload, so a
re-push of an unchanged map deleted and recreated every cell. Measured on a 20,000-cell
map: 20,000 dead tuples on the data table, 120,000 on `cell_sources`, 120,000 on
`cell_overwrites`, and 120,000 audit rows claiming the operator had changed every column
of every cell. Now the rows in scope survive, the ordinary write path updates the ones
that changed, and only the cells the payload no longer claims are deleted.

WHY THE ROW IDENTITY TESTS BELOW ARE NOT INCIDENTAL

Recreating every row also recreated its `row_id` and its `created_at`. `created_at` is a
visible grid column, it is copied and exported, and it has been reporting the time of the
last push rather than the time the cell was created. That is a false statement on screen,
and the tests that pin `row_id` and `created_at` across a re-push are what stop it coming
back - not performance assertions.

WHAT IS DELIBERATELY NOT DIFFED

A table with no `map_key_columns` keeps the purge. Its scope is derived from every
non-coordinate column of `updates[0]`, which can resolve NARROWER than the map, and a
diff against a too-narrow scope would leave real cells behind while inserting duplicates
beside them. The response says which strategy ran and why, so a table that does not
improve can be explained instead of investigated.
"""
import json
from urllib.parse import quote


def _rows(client, table, col, value):
    filters = json.dumps({col: {"filterType": "text", "type": "equals", "filter": value}})
    res = client.get(f"/tables/{table}/data?filters={quote(filters)}")
    assert res.status_code == 200
    return res.json()["data"]


# `xscope_safe_map` mirrors the shape every shipped map table has: a composite business
# key that CONTAINS the map key. That pairing is the diff's precondition - the map key
# gives it a scope to subtract from, and the composite key is what lets it recognise a
# cell it already holds. `rmscope_test_map` deliberately is not used here: its business
# key arrives as a plain payload value, which the write path cannot resolve onto an
# existing row, so it takes the purge fallback (pinned in its own test below).
TABLE = "xscope_safe_map"


def _push(client, lot, cells, table=TABLE):
    """cells: list of (cx, bn). `lot` is the map scope."""
    return client.put(f"/tables/{table}/data/updates", json={
        "updates": [
            {"updates": {"lot": lot, "slot": "01", "cx": cx, "cy": 0, "bn": bn},
             "source_name": "user", "updated_by": "tester"}
            for cx, bn in cells
        ],
        "replace_map": True,
    }).json()


def _identity(rows):
    return {r["data"]["cell_key"]["value"]: (r["row_id"], r["data"]["created_at"]["value"])
            for r in rows}


def test_an_unchanged_repush_writes_nothing_and_records_nothing(client):
    cells = [(i, "1") for i in range(5)]
    _push(client, "DIFF_SAME", cells)
    first = _identity(_rows(client, TABLE, "lot", "DIFF_SAME"))
    assert len(first) == 5

    body = _push(client, "DIFF_SAME", cells)

    assert body["scope"]["mode"] == "diff"
    assert body["scope"]["deleted"] == 0, "nothing disappeared, so nothing may be deleted"
    assert body["scope"]["inserted"] == 0, "nothing appeared, so nothing may be inserted"
    assert body["created_logs"] == [], (
        "an unchanged re-push must record no history: the old purge made every row new "
        "and logged a change for every column of every cell, which was false"
    )
    assert body["deleted_row_ids"] == []

    assert _identity(_rows(client, TABLE, "lot", "DIFF_SAME")) == first, (
        "row_id AND created_at must both survive an unchanged re-push - recreating the "
        "row is what made created_at report the time of the last push"
    )


def test_an_unchanged_cell_does_not_rewrite_its_source_layer(client):
    """The half of this change that the row-level assertions cannot see.

    Dropping the purge alone does NOT stop the churn: the source layer re-stored every
    cell-column unconditionally, and in PostgreSQL `ON CONFLICT DO UPDATE` writes a new
    tuple version, so the deletes simply became updates - 120,000 of them on a 20,000
    cell map where nothing had changed. `ingested_at` is the observable: if the source
    row is rewritten it moves, and if the write is correctly skipped it does not.

    This is also the assertion that keeps `ingested_at` honest. It now means "when this
    source last set this value" rather than "when someone last pressed save".
    """
    _push(client, "DIFF_SRC", [(0, "1")])
    row = _rows(client, TABLE, "lot", "DIFF_SRC")[0]

    def stamp():
        res = client.get(f"/tables/{TABLE}/{row['row_id']}/bn/sources")
        assert res.status_code == 200
        return {name: d["timestamp"] for name, d in res.json()["sources"].items()}

    before = stamp()
    assert before, "the cell must have a source layer to begin with"

    _push(client, "DIFF_SRC", [(0, "1")])
    assert stamp() == before, (
        "an unchanged re-push rewrote the source layer: same value, same writer, new "
        "ingested_at - which is a new tuple version per cell-column and the dead tuples "
        "this change exists to remove"
    )

    _push(client, "DIFF_SRC", [(0, "2")])
    assert stamp() != before, (
        "a REAL change must still move it - otherwise the skip above is not a skip, "
        "it is a broken write"
    )


def test_an_unchanged_cell_does_not_rewrite_its_overwrite_marker(client, db_session):
    """The overwrite layer is the SECOND half of the same skip, and it costs exactly as
    much as the first: a map push declares `source_name='user'`, which marks every
    cell-column as an overwrite, so `cell_overwrites` took an identical 6-rows-per-cell
    hit to `cell_sources` on every re-push.

    It needs its own test because no endpoint surfaces `cell_overwrites.updated_at`, so
    the source-layer assertion above cannot see it. A mutation removing this skip passed
    the entire suite before this test existed.
    """
    from database import models

    _push(client, "DIFF_OW", [(0, "1")])
    row = _rows(client, TABLE, "lot", "DIFF_OW")[0]

    def marker():
        db_session.expire_all()
        ow = db_session.query(models.CellOverwrite).filter(
            models.CellOverwrite.table_name == TABLE,
            models.CellOverwrite.row_id == row["row_id"],
            models.CellOverwrite.column_name == "bn",
        ).first()
        assert ow is not None, "a user-sourced cell must carry an overwrite marker"
        return ow.updated_at

    before = marker()
    _push(client, "DIFF_OW", [(0, "1")])
    assert marker() == before, (
        "an unchanged re-push re-stated the overwrite marker: same flag, same writer, "
        "same pin, new updated_at - one new tuple version per cell-column"
    )

    _push(client, "DIFF_OW", [(0, "2")])
    assert marker() != before, "a real change must still refresh it"


def test_only_the_cells_that_disappeared_are_deleted(client):
    _push(client, "DIFF_DEL", [(i, "1") for i in range(5)])
    before = _identity(_rows(client, TABLE, "lot", "DIFF_DEL"))
    gone_row_id = before["DIFF_DEL_01_4_0"][0]

    body = _push(client, "DIFF_DEL", [(i, "1") for i in range(4)])

    assert body["scope"]["deleted"] == 1, "exactly one cell left the payload"
    assert gone_row_id in body["deleted_row_ids"], "and it is named, not just counted"

    after = _rows(client, TABLE, "lot", "DIFF_DEL")
    assert len(after) == 4
    survivors = _identity(after)
    assert survivors == {k: v for k, v in before.items() if k != "DIFF_DEL_01_4_0"}, (
        "the four survivors keep their identity; only the fifth was removed"
    )


def test_a_cell_absent_from_the_payload_cannot_be_read_as_unchanged(client):
    """The failure mode this design exists to prevent: a diff keyed off the payload
    would treat 'not mentioned' as 'unchanged' and leave the row forever. Emptying the
    map must empty it - absence is decided against the SCOPE, not against the payload."""
    _push(client, "DIFF_WIPE", [(i, "1") for i in range(3)])
    body = client.put(f"/tables/{TABLE}/data/updates", json={
        "updates": [],
        "scope": {"lot": "DIFF_WIPE", "slot": "01"},
        "replace_map": True,
    }).json()
    assert body["scope"]["deleted"] == 3
    assert _rows(client, TABLE, "lot", "DIFF_WIPE") == []


def test_only_the_changed_cell_is_updated_and_logged(client):
    _push(client, "DIFF_PART", [(i, "1") for i in range(4)])
    before = _identity(_rows(client, TABLE, "lot", "DIFF_PART"))

    body = _push(client, "DIFF_PART", [(0, "1"), (1, "9"), (2, "1"), (3, "1")])

    assert body["scope"]["deleted"] == 0
    logged = {(l["row_id"], l["column_name"]) for l in body["created_logs"]}
    assert logged == {(before["DIFF_PART_01_1_0"][0], "bn")}, (
        f"exactly one cell changed, so exactly one column write may be recorded; got {logged}"
    )
    assert _identity(_rows(client, TABLE, "lot", "DIFF_PART")) == before


def test_a_large_removal_is_capped_and_says_so(client):
    """The cap's bound CHANGED with this round and had to be re-derived, not inherited.

    Before the diff, `deleted_row_ids` carried adoptions, and adoptions are bounded by
    the payload (each item resolves at most one row). It now also carries removals, and
    removals are bounded by the SCOPE - which is independent of the payload. The erase-all
    is the case that breaks the old reasoning outright: an empty payload against a
    20,000-cell map produces 20,000 delete ids while `results` is empty, so the
    payload-sized bound is not just loose there, it is false.

    That also kills the tempting shortcut of keying the cap on `len(results)`: on this
    path `results` is 0 and the id list is at its largest.
    """
    from event_constants import BROADCAST_ITEM_LIMIT

    n = BROADCAST_ITEM_LIMIT + 5
    _push(client, "DIFF_BIG", [(i, "1") for i in range(n)])
    assert len(_rows(client, TABLE, "lot", "DIFF_BIG")) == n

    body = client.put(f"/tables/{TABLE}/data/updates", json={
        "updates": [],
        "scope": {"lot": "DIFF_BIG", "slot": "01"},
        "replace_map": True,
    }).json()

    assert body["scope"]["deleted"] == n
    assert body["updated_count"] == 0, "the payload is empty - nothing was upserted"
    assert len(body["deleted_row_ids"]) == n
    assert body["scope"]["delete_ids_omitted"] == n, (
        "the id list is over the limit and must be withheld from the broadcast, with the "
        "count said out loud - and note `results` is 0 here, so a cap keyed on the "
        "upsert size would have let the largest possible frame through"
    )
    assert _rows(client, TABLE, "lot", "DIFF_BIG") == []


def test_a_table_without_map_key_columns_keeps_the_purge_and_says_so(client):
    """No silent downgrade: the table that does not improve says which strategy ran."""
    client.put("/tables/raw_table_1/data/updates", json={
        "updates": [{"updates": {"EQP_ID": "DIFF_LEGACY"}},
                    {"updates": {"EQP_ID": "DIFF_LEGACY"}}],
        "replace_map": False,
    })
    body = client.put("/tables/raw_table_1/data/updates", json={
        "updates": [{"updates": {"EQP_ID": "DIFF_LEGACY"}}],
        "replace_map": True,
    }).json()

    assert body["scope"]["mode"] == "purge"
    assert body["scope"]["reason"] == "legacy_column_derivation"
    assert body["scope"]["deleted"] == 2 and body["scope"]["inserted"] == 1


def test_the_declared_branch_reports_the_diff_strategy(client):
    body = _push(client, "DIFF_MODE", [(0, "1")])
    assert body["scope"]["mode"] == "diff"
    assert body["scope"]["reason"] == "declared_map_key_columns"


def test_a_map_whose_rows_cannot_be_matched_keeps_the_purge_and_says_which(client):
    """`rmscope_test_map` declares `map_key_columns` but has no `composite_key_source`,
    so its business key arrives as a plain payload value that the write path never
    resolves onto an existing row. Diffing it would find every stored cell unclaimed and
    delete the whole map on every push, so it takes the purge - under its own reason,
    which is a different fact from "this table declares no map key" and must not be
    collapsed into it.
    """
    body = client.put("/tables/rmscope_test_map/data/updates", json={
        "updates": [{"updates": {"die_key": "UNRES_1", "ref_table": "bonding_map",
                                 "map_key": "UNRES", "x": 1, "y": 0, "val": "1"}}],
        "replace_map": True,
    }).json()
    assert body["scope"]["mode"] == "purge"
    assert body["scope"]["reason"] == "unresolvable_row_identity"
