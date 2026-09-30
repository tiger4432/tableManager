"""GET /tables/{t}/schema serves the table's `smart_paste` declaration as written (총괄 12cc7dd1f ⓪):
the client reads the format order from it. Undeclared is `None`, not `[]` - no order was said."""


def _schema(client, table):
    res = client.get(f"/tables/{table}/schema")
    assert res.status_code == 200
    return res.json()


def test_an_undeclared_order_is_null(client):
    assert _schema(client, "rmscope_test_map")["smart_paste"] is None


def test_a_declared_order_passes_through_as_written(client):
    from database import crud
    order = ["text/html", "text/plain"]
    crud.TABLE_CONFIG["rmscope_test_map"]["smart_paste"] = list(order)
    try:
        assert _schema(client, "rmscope_test_map")["smart_paste"] == order
    finally:
        crud.TABLE_CONFIG["rmscope_test_map"].pop("smart_paste", None)
