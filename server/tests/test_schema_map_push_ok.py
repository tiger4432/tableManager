"""GET /tables/{t}/schema serves the `map_push_ok` site declaration (map editor Gate 4).

The client blocks a cell push into any table whose declared columns exceed the map
contract (log-shaped target). `map_push_ok: true` in the table's table_config entry is
the site saying "editor overwrite into this table is a known flow (R&D manual
measurements) - downgrade the hard refusal to one loss-acknowledging confirm".
The endpoint must serve it strictly: only the JSON boolean true unlocks.
"""


def _schema(client, table):
    res = client.get(f"/tables/{table}/schema")
    assert res.status_code == 200
    return res.json()


def test_map_push_ok_absent_serves_false(client):
    body = _schema(client, "rmscope_test_map")
    assert body["map_push_ok"] is False
    # the rest of the contract is untouched by the new field
    assert body["map_key_columns"] == ["ref_table", "map_key"]


def test_map_push_ok_declared_true_passes_through(client):
    from database import crud
    crud.TABLE_CONFIG["rmscope_test_map"]["map_push_ok"] = True
    try:
        assert _schema(client, "rmscope_test_map")["map_push_ok"] is True
    finally:
        crud.TABLE_CONFIG["rmscope_test_map"].pop("map_push_ok", None)


def test_map_push_ok_non_boolean_declarations_stay_false(client):
    """A config typo must not unlock destruction: only JSON true counts."""
    from database import crud
    for typo in ("true", "false", 1, {"on": True}):
        crud.TABLE_CONFIG["rmscope_test_map"]["map_push_ok"] = typo
        try:
            assert _schema(client, "rmscope_test_map")["map_push_ok"] is False, typo
        finally:
            crud.TABLE_CONFIG["rmscope_test_map"].pop("map_push_ok", None)
