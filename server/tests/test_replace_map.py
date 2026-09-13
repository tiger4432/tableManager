import json
from urllib.parse import quote


def _get_rows(client, table, col, value):
    filters = json.dumps({col: {"filterType": "text", "type": "equals", "filter": value}})
    res = client.get(f"/tables/{table}/data?filters={quote(filters)}")
    assert res.status_code == 200
    return res.json()["data"]


def _seed_map(client, table, map_key, count):
    """Seed `count` map cells for (ref_table=bonding_map, map_key=<map_key>)."""
    payload = {
        "updates": [
            {"updates": {"die_key": f"{map_key}_{i}", "ref_table": "bonding_map",
                         "map_key": map_key, "x": i, "y": 0, "val": "1"}}
            for i in range(count)
        ],
        "replace_map": False,
    }
    res = client.put(f"/tables/{table}/data/updates", json=payload)
    assert res.status_code == 200
    return res


def test_replace_map_clean_purge(client):
    """The purge deletes what its scope covers and nothing beside it.

    ⚰️ THE COUNTS CHANGED, AND THE SUBJECT DID NOT (S-226, 판정 391·393). This test used
    to push ONE `EQP_ID` three times and expect THREE rows: on a plain-keyed table the
    declared key was never lifted into `business_key_val`, so every push minted another
    row. That was the defect S-226 removed, and this test was standing on it. Three
    pushes of one key are now one row, so the numbers here are what the declaration
    permits rather than what the defect produced.

    🔴 AND THE SCOPE NEIGHBOUR IS WHY THIS IS STILL A TEST. With one row before and one
    after, "purged then re-inserted" and "did nothing at all" look identical. A row under
    a DIFFERENT key makes the assertion discriminating again: the legacy derivation pins
    `EQP_ID`, so a purge that ignored its filters would take that row too."""
    unique_eqp = "EQP_UNIQUE_999"
    neighbour = "EQP_UNIQUE_998"

    res1 = client.put("/tables/raw_table_1/data/updates", json={
        "updates": [
            {"updates": {"EQP_ID": unique_eqp}},
            {"updates": {"EQP_ID": unique_eqp}},
            {"updates": {"EQP_ID": unique_eqp}},
            {"updates": {"EQP_ID": neighbour}},
        ],
        "replace_map": False,
    })
    assert res1.status_code == 200
    assert len(_get_rows(client, "raw_table_1", "EQP_ID", unique_eqp)) == 1
    assert len(_get_rows(client, "raw_table_1", "EQP_ID", neighbour)) == 1

    res_purge = client.put("/tables/raw_table_1/data/updates", json={
        "updates": [{"updates": {"EQP_ID": unique_eqp}}],
        "replace_map": True,
    })
    assert res_purge.status_code == 200
    assert res_purge.json()["scope"]["deleted"] == 1, "the row in scope WAS purged"

    rows2 = _get_rows(client, "raw_table_1", "EQP_ID", unique_eqp)
    assert len(rows2) == 1
    assert str(rows2[0]["data"]["EQP_ID"]["value"]) == unique_eqp
    assert len(_get_rows(client, "raw_table_1", "EQP_ID", neighbour)) == 1, (
        "the purge widened past its own filters")


# ---------------------------------------------------------------------------
# [U6] replace_map honesty contract: the response carries the EXACT purge scope
# (`scope: {filters, deleted, inserted}`), an underivable scope is a 4xx refusal
# (never the historical silent 200-noop), and an explicit scope with an empty
# payload is the intentional erase-all - reported as deleted: N, inserted: 0.
# `rmscope_test_map` declares map_key_columns (the legend/map_split_registry
# shape); `raw_table_1` has none and exercises the legacy fallback derivation.
# ---------------------------------------------------------------------------

def test_replace_map_response_reports_scope_and_counts(client):
    _seed_map(client, "rmscope_test_map", "RMS_MAPX", 3)
    seed_res = _seed_map(client, "rmscope_test_map", "RMS_MAPY", 2)
    # a non-replace write reports no scope
    assert seed_res.json()["scope"] is None

    res = client.put("/tables/rmscope_test_map/data/updates", json={
        "updates": [{"updates": {"die_key": "RMS_MAPX_new", "ref_table": "bonding_map",
                                 "map_key": "RMS_MAPX", "x": 9, "y": 9, "val": "2"}}],
        "replace_map": True,
    })
    assert res.status_code == 200
    body = res.json()
    # the exact filters the DELETE used - map_key_columns only, never `val`/`x`/`y`
    assert body["scope"]["filters"] == {"ref_table": "bonding_map", "map_key": "RMS_MAPX"}
    assert body["scope"]["deleted"] == 3
    assert body["scope"]["inserted"] == 1

    assert len(_get_rows(client, "rmscope_test_map", "map_key", "RMS_MAPX")) == 1
    # the neighbouring scope is untouched
    assert len(_get_rows(client, "rmscope_test_map", "map_key", "RMS_MAPY")) == 2


def test_replace_map_fallback_scope_reported(client):
    """Table WITHOUT map_key_columns: the legacy fallback derivation still works
    and the response says which filters it actually used.

    ⚰️ `deleted` WAS 2 AND IS 1 (S-226, 판정 391·393). The seed pushed one `EQP_ID`
    twice and got two rows only because a plain declared key was never lifted into
    `business_key_val`; it is one row now, so the scope covers one row and the report
    says so. The subject - that the response states the filters and the counts it
    really used - is unchanged, and `deleted: 1` still separates a purge that ran from
    one that did not."""
    eqp = "EQP_SCOPE_FB"
    client.put("/tables/raw_table_1/data/updates", json={
        "updates": [{"updates": {"EQP_ID": eqp}}, {"updates": {"EQP_ID": eqp}}],
        "replace_map": False,
    })
    res = client.put("/tables/raw_table_1/data/updates", json={
        "updates": [{"updates": {"EQP_ID": eqp}}],
        "replace_map": True,
    })
    assert res.status_code == 200
    body = res.json()
    assert body["scope"]["filters"] == {"EQP_ID": eqp}
    assert body["scope"]["deleted"] == 1
    assert body["scope"]["inserted"] == 1


def test_replace_map_refuses_when_scope_underivable(client):
    _seed_map(client, "rmscope_test_map", "RMS_KEEP", 2)

    # payload carries none of the declared map_key_columns -> refusal, not a 200-noop
    res = client.put("/tables/rmscope_test_map/data/updates", json={
        "updates": [{"updates": {"val": "9"}}],
        "replace_map": True,
    })
    assert res.status_code == 400
    assert "purge scope" in res.json()["detail"]

    # nothing was deleted and nothing was inserted by the refused request
    assert len(_get_rows(client, "rmscope_test_map", "map_key", "RMS_KEEP")) == 2
    assert len(_get_rows(client, "rmscope_test_map", "val", "9")) == 0


def test_replace_map_refuses_empty_payload_without_scope(client):
    res = client.put("/tables/rmscope_test_map/data/updates", json={
        "updates": [],
        "replace_map": True,
    })
    assert res.status_code == 400
    assert "purge scope" in res.json()["detail"]


def test_replace_map_explicit_scope_full_wipe(client):
    """Empty payload + explicit valid scope = intentional erase-all of that scope,
    reported honestly as deleted: N, inserted: 0."""
    _seed_map(client, "rmscope_test_map", "RMS_WIPE", 3)
    _seed_map(client, "rmscope_test_map", "RMS_SAFE", 2)

    res = client.put("/tables/rmscope_test_map/data/updates", json={
        "updates": [],
        "replace_map": True,
        "scope": {"ref_table": "bonding_map", "map_key": "RMS_WIPE"},
    })
    assert res.status_code == 200
    body = res.json()
    assert body["scope"]["filters"] == {"ref_table": "bonding_map", "map_key": "RMS_WIPE"}
    assert body["scope"]["deleted"] == 3
    assert body["scope"]["inserted"] == 0

    assert len(_get_rows(client, "rmscope_test_map", "map_key", "RMS_WIPE")) == 0
    assert len(_get_rows(client, "rmscope_test_map", "map_key", "RMS_SAFE")) == 2


def test_replace_map_explicit_scope_validation(client):
    _seed_map(client, "rmscope_test_map", "RMS_VAL", 1)

    # unknown column
    res = client.put("/tables/rmscope_test_map/data/updates", json={
        "updates": [], "replace_map": True,
        "scope": {"nonexistent_col": "x"},
    })
    assert res.status_code == 400
    assert "not a declared column" in res.json()["detail"]

    # declared column but outside the map-key contract - a DELETE filter must not
    # be built from arbitrary columns when map_key_columns is declared
    res = client.put("/tables/rmscope_test_map/data/updates", json={
        "updates": [], "replace_map": True,
        "scope": {"val": "1"},
    })
    assert res.status_code == 400
    assert "outside the map-key contract" in res.json()["detail"]

    # empty value would silently widen the DELETE - refused
    res = client.put("/tables/rmscope_test_map/data/updates", json={
        "updates": [], "replace_map": True,
        "scope": {"ref_table": "bonding_map", "map_key": "  "},
    })
    assert res.status_code == 400
    assert "empty value" in res.json()["detail"]

    # nothing was harmed by any refused request
    assert len(_get_rows(client, "rmscope_test_map", "map_key", "RMS_VAL")) == 1
