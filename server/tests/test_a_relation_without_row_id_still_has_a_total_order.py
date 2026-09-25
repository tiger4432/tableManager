# -*- coding: utf-8 -*-
"""S-186. The grid can read a relation that has no `row_id`, and cannot write a view.

Owner: 「ledger event 도 메인 그리드에 read only 로」. Declaring `ledger_events` with
`kind: "view"` and a `business_key` is meant to be the whole job — two lines, no new cell.

Two things stood in the way, both measured before anything was built:

🔴 THE WRITE DOOR NEVER READ `kind`. It was read at three sites in `models.py`, all of them
「do not build the model/index」; no write path looked. So a view was read-only only because
PostgreSQL refused it, and a real table declared `kind: view` would simply be written.

🔴 `row_id` WAS HARDCODED AS THE TOTAL ORDER in four seats — the two tiebreakers, the
default sort, and the two-phase paging. 판정 296 named three; the fourth (the page's id
selection) was found by grep, and one direct read is all it takes to make this two paths.

⚠️ `row_id` STILL WINS WHEREVER IT EXISTS. S-131 measured what moving the grid's total
order costs: `idx_<t>_updated (updated_at, row_id)` stops being usable and one page spends
0.7 s sorting 440,000 rows. This is a lookup, not a replacement.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import main                                                           # noqa: E402
from database import crud, schemas                                    # noqa: E402

VIEW = "s186_view_rel"
TABLE = "s186_plain_rel"


class _Model:
    """A relation with only the columns it declares - which is the point."""

    def __init__(self, **columns):
        for name, value in columns.items():
            setattr(self, name, value)


@pytest.fixture(autouse=True)
def _declared():
    crud.TABLE_CONFIG[VIEW] = {
        "kind": "view", "business_key": "id",
        "column_types": {"id": "string", "occurred_at": "datetime"}}
    crud.TABLE_CONFIG[TABLE] = {
        "business_key": "k", "column_types": {"k": "string"}}
    yield
    # ⚠️ THE MODEL REGISTRY IS PROCESS-WIDE, and several tests here build models to reach
    # the view path. A model left behind makes a SIBLING test that COUNTS the registry
    # fail - measured, not guessed: it read 50 against a 46-entry catalogue. So the
    # fixture removes every name this file introduces and rebuilds from the real
    # catalogue, rather than each test remembering to.
    from conftest import retire_dynamic_model
    from database import models
    from database.database import Base

    crud.TABLE_CONFIG.pop(VIEW, None)
    crud.TABLE_CONFIG.pop(TABLE, None)
    # 🔴 POPPING THE CLASS IS ONLY HALF OF IT, AND THE OTHER HALF FAILS THREE FILES AWAY.
    # `Base.metadata` is the same process-wide singleton, so the `Table` and its
    # `Index` survive the pop -- and because the class is gone, the NEXT test in this
    # file takes `init_dynamic_models`'s fresh-build arm and appends a SECOND `Index`
    # of the same name. After nine tests the metadata holds nine of them, and the first
    # LATER file to call `Base.metadata.create_all` dies with 「index
    # idx_s186_plain_rel_updated already exists」 -- measured as 5 errors in
    # `test_capped_reads_have_a_total_order.py`, which names neither this file nor this
    # fixture.
    # S-191: the pair is `conftest.retire_dynamic_model` now, so this file no longer
    # spells it out and cannot drift from the seven other seats that do the same thing.
    # ⚠️ BOTH registries are swept, not just one -- a name can outlive its class in
    # `Base.metadata` (that is exactly the leak), so iterating only `DYNAMIC_TABLES`
    # would walk past it.
    leaked = [n for n in list(models.DYNAMIC_TABLES) + list(Base.metadata.tables)
              if str(n).startswith("s186_")]
    for name in dict.fromkeys(leaked):
        retire_dynamic_model(name)
    models.init_dynamic_models(dict(crud.TABLE_CONFIG))


# ---------------------------------------------------------------------------
# The one function
# ---------------------------------------------------------------------------

def test_row_id_wins_wherever_it_exists():
    """🔴 THE REGRESSION LINE. Every table that has `row_id` must keep it as its total
    order, or S-131's index path dies across the whole grid."""
    model = _Model(row_id="ROWID_COL", id="ID_COL", k="K_COL")
    assert main.total_order_keys(model, TABLE) == ("ROWID_COL",)


def test_a_relation_without_row_id_falls_to_its_declared_business_key():
    model = _Model(id="ID_COL", occurred_at="TS_COL")
    assert main.total_order_keys(model, VIEW) == ("ID_COL",)


def test_a_relation_with_neither_is_refused_by_name_not_paged_anyway():
    """🔴 SCHEMA_CANON R7: 「상한 걸린 읽기에는 전순서가 있어야 한다」. A `LIMIT` without a
    total order hands the operator a different page on every refresh and raises nothing, so
    returning None here would be the silent version of the defect R7 exists to name."""
    from fastapi import HTTPException

    crud.TABLE_CONFIG[VIEW] = {"kind": "view", "column_types": {"id": "string"}}
    with pytest.raises(HTTPException) as caught:
        main.total_order_keys(_Model(id="ID_COL"), VIEW)
    assert caught.value.status_code == 422
    assert "R7" in str(caught.value.detail)
    assert VIEW in str(caught.value.detail)


def test_a_business_key_naming_a_column_the_model_lacks_is_refused():
    """The sensitivity control: a declaration that names a missing column must not resolve
    to None and then page arbitrarily."""
    from fastapi import HTTPException

    crud.TABLE_CONFIG[VIEW]["business_key"] = "not_a_column"
    with pytest.raises(HTTPException):
        main.total_order_keys(_Model(id="ID_COL"), VIEW)


# ---------------------------------------------------------------------------
# Gate ⓒ — the write door
# ---------------------------------------------------------------------------

def test_writing_a_view_is_refused_and_the_refusal_names_the_table_and_the_kind():
    batch = schemas.GeneralUpdateBatch(updates=[], transaction_id="t", silent=True)
    with pytest.raises(ValueError) as caught:
        crud.apply_batch_updates(None, VIEW, batch)
    said = str(caught.value)
    assert VIEW in said, said
    assert "kind: view" in said, said


def test_an_ordinary_table_is_not_touched_by_that_guard():
    """⚠️ THE CONTROL, and it must fail for a DIFFERENT reason. If this raised the view
    refusal the guard would be refusing everything, and every assertion above would still
    pass."""
    batch = schemas.GeneralUpdateBatch(updates=[], transaction_id="t", silent=True)
    with pytest.raises(Exception) as caught:
        crud.apply_batch_updates(None, TABLE, batch)
    assert "kind: view" not in str(caught.value)


def test_a_table_declaring_no_kind_is_writable():
    """A catalogue entry without the cell is not one character different - which is what
    makes this safe to deploy against a live declaration nobody has edited."""
    assert (crud.TABLE_CONFIG[TABLE].get("kind") or "table") != "view"


# ---------------------------------------------------------------------------
# 🔴 THE ROUTE, ON A REAL VIEW — the read the unit tests above could not reach
# ---------------------------------------------------------------------------

def test_a_view_model_carries_only_its_declared_columns():
    """⚰️ THE FIFTH SEAT, AND THE ONE THAT KEPT THE ROUTE AT 500 AFTER THE SORT WAS FIXED.
    Every dynamic model got `row_id`, `business_key_val`, `created_at`, `updated_at` — the
    columns a WRITE path maintains — whatever its kind. A view has none of them unless its
    SQL selects them, so the failure simply moved from the ORDER BY to the SELECT:
    `UndefinedColumn: void_obs_observed.row_id`.

    ⚠️ `dt_log_transferable` is a view that DOES expose `row_id`, and it answered 200 all
    along — which is exactly why the suite was green while a relation without one had never
    been read through the route at all."""
    from database import models

    cfg = dict(crud.TABLE_CONFIG)
    cfg["s186_real_view"] = {
        "kind": "view", "business_key": "vid",
        "column_types": {"vid": "string", "seen_at": "datetime", "updated_at": "datetime"}}
    models.init_dynamic_models(cfg)
    model = models.DYNAMIC_TABLES["s186_real_view"]
    names = [c.name for c in model.__table__.columns]

    assert names == ["vid", "seen_at", "updated_at"], names
    for framework in ("row_id", "business_key_val", "created_at"):
        assert framework not in names, framework
    # the declared key is the mapped primary key, so the model and `total_order_key` agree
    assert [c.name for c in model.__table__.primary_key] == ["vid"]
    # 🔴 a view cannot be indexed, and the framework index names columns it does not have
    assert not model.__table__.indexes


def test_a_view_declaring_no_business_key_is_still_mappable_but_refused_at_read():
    """🔴 TWO DIFFERENT QUESTIONS, and conflating them is how a page gets served
    arbitrarily. Measured: of ten `kind: view` relations on this box, FOUR declare no
    `business_key`. SQLAlchemy cannot map a class without a primary key, so one is
    nominated — that is a mapping mechanic, NOT a claim that the relation has an identity,
    and `total_order_key` still refuses to page it under R7."""
    from fastapi import HTTPException
    from database import models

    cfg = dict(crud.TABLE_CONFIG)
    cfg["s186_keyless_view"] = {
        "kind": "view", "column_types": {"a": "string", "b": "string"}}
    models.init_dynamic_models(cfg)
    model = models.DYNAMIC_TABLES["s186_keyless_view"]
    assert [c.name for c in model.__table__.primary_key] == ["a"], "not mappable"

    crud.TABLE_CONFIG["s186_keyless_view"] = cfg["s186_keyless_view"]
    try:
        with pytest.raises(HTTPException) as caught:
            main.total_order_keys(model, "s186_keyless_view")
        assert "R7" in str(caught.value.detail)
    finally:
        crud.TABLE_CONFIG.pop("s186_keyless_view", None)


def test_a_view_row_carries_no_layering_metadata_and_renders_its_times():
    """A view's cells have exactly one value each — the write door refuses the relation, so
    nothing ever wrote a source for it. And the times are RENDERED: a raw `datetime` makes
    the payload non-JSON-native and the route's own warning prices that at ~10x."""
    from datetime import datetime, timezone

    class _Row:
        vid = "V1"
        seen_at = datetime(2026, 8, 13, 4, 12, 7, tzinfo=timezone.utc)

    from database import models

    crud.TABLE_CONFIG["s186_render_view"] = {
        "kind": "view", "business_key": "vid",
        "column_types": {"vid": "string", "seen_at": "datetime"}}
    # ⚠️ THE MODEL IS BUILT, because the route always has one — it just queried through it.
    # The merge resolves the row's identity through `total_order_key`, the SAME function the
    # sort uses, rather than re-deriving 「row_id or business_key」 as a second spelling.
    models.init_dynamic_models(dict(crud.TABLE_CONFIG))
    try:
        merged = main.fetch_and_merge_metadata(
            None, "s186_render_view", [_Row()], ["vid", "seen_at"])
    finally:
        # ⚠️ The registry is process-wide, so a model left behind makes a SIBLING test that
        # counts it fail — measured, not guessed: it went 46 -> 51.
        from conftest import retire_dynamic_model

        crud.TABLE_CONFIG.pop("s186_render_view", None)
        # S-191: this seat popped the class and left the `Table` behind -- the autouse
        # fixture above swept it up afterwards, which is why nothing here ever went red.
        # It goes through the one function anyway: a seat that only works because
        # something else cleans up after it is a seat that breaks when that changes.
        retire_dynamic_model("s186_render_view")
        models.init_dynamic_models(dict(crud.TABLE_CONFIG))

    # 🔴 THE SAME WRAPPER EVERY ROW USES — the grid reads `dataObj.data[col]` for every
    # relation, so a flat row stopped it drawing a view it had been drawing.
    row = merged[0]
    assert sorted(row) == ["created_at", "data", "row_id", "table_name", "updated_at"]
    assert row["row_id"] == "V1", "the view's identity is its declared key"
    # ⛔ THE CELL IS `{value}` AND NOTHING MORE. Writing `is_overwrite: False` would invent
    # an absent layering marker as a value - 「없는 것」 and 「0인 것」 must not look alike.
    assert row["data"]["vid"] == {"value": "V1"}
    assert set(row["data"]["seen_at"]) == {"value"}
    assert isinstance(row["data"]["seen_at"]["value"], str), "a raw datetime costs 10x"
    assert row["data"]["seen_at"]["value"].endswith("+00:00")


# ---------------------------------------------------------------------------
# 총괄 218f907f5 · 4e508835a — a view on the grid, through the routes
# ---------------------------------------------------------------------------

GRID_VIEW = "s186_grid_view"


@pytest.fixture
def grid_view(client, db_session):
    """A view the way `ledger_events` stands on the grid: declared `kind: view`, keyed by its
    `id`, no `row_id`, no layering pair - and two rows in the relation."""
    from datetime import datetime, timezone

    from conftest import retire_dynamic_model
    from database import models

    crud.TABLE_CONFIG[GRID_VIEW] = {
        "kind": "view", "business_key": "id",
        "column_types": {"id": "string", "occurred_at": "datetime"}}
    models.init_dynamic_models(dict(crud.TABLE_CONFIG))
    table = models.DYNAMIC_TABLES[GRID_VIEW].__table__
    bind = db_session.get_bind()
    table.create(bind=bind)
    db_session.execute(table.insert(), [
        {"id": "EV-1", "occurred_at": datetime(2026, 9, 1, tzinfo=timezone.utc)},
        {"id": "EV-2", "occurred_at": datetime(2026, 9, 2, tzinfo=timezone.utc)}])
    db_session.commit()
    try:
        yield client
    finally:
        table.drop(bind=bind)
        crud.TABLE_CONFIG.pop(GRID_VIEW, None)
        retire_dynamic_model(GRID_VIEW)
        models.init_dynamic_models(dict(crud.TABLE_CONFIG))


ROW_ADDRESSED = [
    ("get", "/tables/%s/EV-1", None),
    ("get", "/tables/%s/EV-1/id/sources", None),
    ("get", "/tables/%s/rows/EV-1/history", None),
    ("get", "/tables/%s/rows/EV-1/cells/id/history", None),
    ("post", "/tables/%s/row_ids/target", {"offsets": [0]}),
    ("post", "/tables/%s/cells/sources/query",
     {"updates": [{"row_id": "EV-1", "column_name": "id"}]}),
    ("get", "/tables/%s/data?transaction_id=tx", None),
    ("get", "/tables/%s/data/count?transaction_id=tx", None),
    ("get", "/tables/%s/export?transaction_id=tx", None),
]


def test_every_route_that_addresses_a_views_row_refuses_it_by_name(grid_view):
    said = {}
    for method, path, body in ROW_ADDRESSED:
        url = path % GRID_VIEW
        response = getattr(grid_view, method)(url, **({"json": body} if body else {}))
        said[url] = (response.status_code, GRID_VIEW in str(response.json().get("detail")))
    assert said == {path % GRID_VIEW: (422, True) for _m, path, _b in ROW_ADDRESSED}
    table = grid_view.get("/tables/raw_table_1/data?transaction_id=tx")
    assert table.status_code == 200, "CANARY: a table's transaction filter still reads"


def test_a_view_exports_in_its_key_order_with_the_layering_pair_left_empty(grid_view):
    import csv
    import io as _io

    response = grid_view.get("/tables/%s/export?order_by=row_id&order_desc=true" % GRID_VIEW)
    assert response.status_code == 200, response.text
    rows = list(csv.reader(_io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == ["id", "occurred_at", "created_at", "updated_at"]
    assert [row[0] for row in rows[1:]] == ["EV-2", "EV-1"], "ordered by the view's key"
    assert {tuple(row[2:]) for row in rows[1:]} == {("", "")}


def test_a_search_on_id_finds_a_views_key_and_a_tables_sql_is_unchanged(grid_view, db_session):
    from database import models

    found = grid_view.get("/tables/%s/data?q=EV-2&cols=id" % GRID_VIEW)
    assert found.status_code == 200, found.text
    assert [row["row_id"] for row in found.json()["data"]] == ["EV-2"]
    assert grid_view.get("/tables/%s/data?q=EV" % GRID_VIEW).status_code == 200

    table = models.DYNAMIC_TABLES["raw_table_1"]
    sql = str(main.apply_search_filter(db_session.query(table), table, "raw_table_1",
                                       "x", "row_id").statement)
    assert "row_id" in sql and "CAST" not in sql.upper(), sql
    # ⚠️ The declared key is cast: `ledger_events.id` is declared string over a uuid, and
    #   PostgreSQL refuses ILIKE on a uuid - sqlite here would not.
    view = models.DYNAMIC_TABLES[GRID_VIEW]
    sql = str(main.apply_search_filter(db_session.query(view), view, GRID_VIEW,
                                       "x", "id").statement)
    assert "CAST(%s.id AS" % GRID_VIEW in sql.replace('"', ""), sql


def test_the_id_header_sorts_a_view_by_its_key_and_a_table_by_its_key_column(grid_view,
                                                                            db_session):
    """총괄 01cad807c — the grid sends `order_by=<colId>`; `id` read `business_key_val`."""
    import csv
    import io as _io

    from database import models

    rows = grid_view.get("/tables/%s/data?order_by=id&order_desc=true" % GRID_VIEW)
    assert rows.status_code == 200, rows.text
    assert [row["row_id"] for row in rows.json()["data"]] == ["EV-2", "EV-1"]
    export = grid_view.get("/tables/%s/export?order_by=id&order_desc=true" % GRID_VIEW)
    assert export.status_code == 200, export.text
    lines = list(csv.reader(_io.StringIO(export.content.decode("utf-8-sig"))))
    assert [line[0] for line in lines[1:]] == ["EV-2", "EV-1"]

    table = models.DYNAMIC_TABLES["raw_table_1"]
    order = main._named_sort(table, "raw_table_1", "id", False)
    assert "business_key_val" in str(order[0]), "a table keeps its key column, not row_id"


def test_a_framework_column_a_view_lacks_is_unsearchable_by_name(grid_view):
    alone = grid_view.get("/tables/%s/data?q=EV&cols=created_at" % GRID_VIEW)
    assert alone.status_code == 400 and "created_at" in alone.json()["detail"], alone.text
    beside = grid_view.get("/tables/%s/data?q=EV-1&cols=created_at,id" % GRID_VIEW)
    assert beside.status_code == 200, beside.text
    assert [row["row_id"] for row in beside.json()["data"]] == ["EV-1"]


def test_the_dashboard_does_not_report_a_view_as_a_drifted_table(grid_view):
    body = grid_view.get("/dashboard/summary").json()
    assert GRID_VIEW not in [u["table_name"] for u in body["uncounted_tables"]]
