# -*- coding: utf-8 -*-
"""S-187. The client can learn a relation is a view, from the routes it already calls.

C-84 blocked on this: the grid had no way to refuse edit entry on a view, because no route
said which relations were views. Measured before building — `/tables`,
`/tables/<name>/schema` and `/data` all lacked `kind`, and the only server site reading it
on the data path was one branch in `main.py`.

🔴 IT RIDES WITH THE LIST FOR THE REASON `map_key_columns` DOES (S-72). The alternative is
one request per table — 44 on this box, and the client measured 76% of the previous
per-table round trips thrown away.

⚠️ AND THE DEFAULT LIVES IN ONE PLACE. Four sites had spelled `str(x.get("kind") or
"table")` separately; `setup_bundle.catalog_kind` is now the only one, beside the closed
list that refuses a typo. A reader inventing its own default is how `"veiw"` comes to mean
`table` somewhere and `view` somewhere else.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from ledger.setup_bundle import (CATALOG_KINDS, DEFAULT_CATALOG_KIND,   # noqa: E402
                                 catalog_kind)

#: What `/tables` answered before S-187, read out of the route at the parent commit.
TABLES_KEYS_BEFORE = {"tables", "map_key_columns"}
#: The same for `/tables/<name>/schema`.
SCHEMA_KEYS_BEFORE = {
    "table_name", "columns", "column_types", "business_key",
    "composite_key_source", "map_key_columns", "map_push_ok",
    "virtual_columns", "join_resolved_columns",
}


# ---------------------------------------------------------------------------
# The one function
# ---------------------------------------------------------------------------

def test_the_default_is_the_catalogues_own_and_lives_in_one_place():
    assert catalog_kind({"kind": "view"}) == "view"
    assert catalog_kind({"kind": "table"}) == "table"
    assert catalog_kind({}) == DEFAULT_CATALOG_KIND == "table"
    assert catalog_kind(None) == "table", "a missing entry must not raise at a read site"
    assert set(CATALOG_KINDS) == {"table", "view"}


def test_it_does_not_validate_because_the_loader_already_refuses():
    """⚠️ An unknown word is refused at LOAD time, by path, where the operator can be told
    which line is wrong. Answering that here too would be a second gate able to disagree
    with the first — so a typo passes through as itself and the loader stops it."""
    assert catalog_kind({"kind": "veiw"}) == "veiw"


# ---------------------------------------------------------------------------
# Both routes, and nothing else moved
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    os.environ.setdefault("TESTING", "1")
    from fastapi.testclient import TestClient

    import main

    return TestClient(main.app, raise_server_exceptions=False)


def test_the_list_route_says_the_kind_of_every_table(client):
    body = client.get("/tables").json()
    kinds = body["kinds"]
    # ⚠️ EVERY relation is present, unlike `map_key_columns` where absence means "none".
    # Every relation HAS a kind, and a missing entry would make the reader guess — the
    # guess being exactly the default this hands over explicitly.
    assert set(kinds) == set(body["tables"])
    assert set(kinds.values()) <= set(CATALOG_KINDS)


def test_the_list_route_moved_nothing_else(client):
    """🔴 THE REGRESSION LINE, scored against the keys the route answered at the parent
    commit rather than against my memory of them."""
    assert set(client.get("/tables").json()) == TABLES_KEYS_BEFORE | {"kinds"}


def test_the_schema_route_says_the_same_thing_for_one_table(client):
    from database import crud

    views = [n for n, e in crud.TABLE_CONFIG.items() if catalog_kind(e) == "view"]
    tables = [n for n, e in crud.TABLE_CONFIG.items() if catalog_kind(e) == "table"]
    if not views or not tables:
        pytest.skip("this catalogue declares no view, or no ordinary table")

    listed = client.get("/tables").json()["kinds"]
    for name in (views[0], tables[0]):
        body = client.get(f"/tables/{name}/schema").json()
        # 🔴 THE TWO ROUTES AGREE BECAUSE THEY READ ONE FUNCTION. Two spellings of 「is this
        # a view」 is how a screen comes to trust the wrong one and offer an edit the write
        # door refuses.
        assert body["kind"] == listed[name], name


def test_the_schema_route_moved_nothing_else(client):
    from database import crud

    name = next(iter(crud.TABLE_CONFIG))
    assert set(client.get(f"/tables/{name}/schema").json()) == (
        SCHEMA_KEYS_BEFORE | {"kind"})
