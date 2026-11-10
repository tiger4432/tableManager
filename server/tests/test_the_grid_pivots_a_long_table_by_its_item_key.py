# -*- coding: utf-8 -*-
"""소유자 10-22 (총괄 95d9525b4 · 46844ff15 · a1d9382fb): the main grid's pivot - a long table keyed (lot, wafer,
itemid) read as one row per (lot, wafer) and one cell per itemid, through the grid's own route (`?pivot=1`).

  page     key groups, not long rows: a group's items are never cut by the page; each cell carries its row_id
  filters  a key column's as the grid's; an item's an EXISTS of its row (the grid filter's condition), blank: none
           the item column's as the grid's on the long rows: the items spread, their count and the groups follow
           it (소유자 11-05 ㄴ); the value column's refused - filter it per item
           a set holding null takes a group without that item's row, as «blank» does (A ea92380da, 총괄 11-05)
  keys     an absent key part equals an absent part - on PostgreSQL as ARRAY[a] = ARRAY[b], which hashes; every
           read answered as a Python reckoning of the same rows (총괄 11-05 ㄴ)
  sort     one item's value, a group without it last both ways; then the keys
  items    the narrowed rows' DISTINCT itemid, up to pivot_max_columns, and how many more
  write    a cell by its row_id through the grid save door; a blank cell by its keys - the row is made
  search   a key group whose any long row matches q - the grid search's own condition - kept whole (총괄 10-22)
  schema   /schema says the pivot as declared, or null for one a read refuses (총괄 10-22)
  refused  a declaration that cannot pivot, at save and at read; an argument a pivot does not take
"""
import json

import pytest

from sqlalchemy import func

from conftest import retire_dynamic_model
from database import crud, models
from tests.support import line_tables

TABLE = "pivot_probe"
ENTRY = {"business_key": "bk", "composite_key_source": ["lot", "wafer", "itemid"],
         "column_types": {"lot": "string", "wafer": "string", "itemid": "string", "value": "number",
                          "note": "string"},
         "pivot": {"column": "itemid", "value": "value"}}
#: (lot, wafer) -> {itemid: value}. W2 has no «b»; (L2, None) - an absent key part - is a group of its own.
LONG = {("L1", "W1"): {"a": 1.0, "b": 5.0, "c": 9.0},
        ("L1", "W2"): {"a": 2.0, "c": 7.0},
        ("L2", "W1"): {"a": 3.0, "b": 4.0},
        ("L2", None): {"b": 8.0}}


@pytest.fixture
def grid(db_session, client, monkeypatch):
    # its own drop counts: a row made by its keys drops `bk` (not a declared column) into the process-wide registry
    # the chain worker's heartbeat note reads - left there, a later file's «clean worker» is not (총괄 10-23, B)
    for name in ("_undeclared_column_drops", "_undeclared_column_warned", "_undeclared_column_drops_over_budget"):
        monkeypatch.setattr(crud, name, {})
    models.init_dynamic_models({TABLE: ENTRY})
    crud.TABLE_CONFIG[TABLE] = ENTRY
    line_tables.build(db_session.get_bind(), TABLE)             # t and its lines, as ensure_declared makes them
    model = models.DYNAMIC_TABLES[TABLE]
    put = [{"updates": {"lot": lot, "wafer": wafer, "itemid": item, "value": value}, "source_name": "file",
            "updated_by": "probe"} for (lot, wafer), items in LONG.items() if wafer for item, value in items.items()]
    answer = client.put("/tables/%s/data/updates" % TABLE, json={"updates": put})
    assert answer.status_code == 200, answer.text
    # the save door drops a row whose key has an absent part; a row so kept elsewhere (`null_policy`) is put here
    db_session.add(model(row_id="absent-wafer", lot="L2", wafer=None, itemid="b", value=8.0))
    db_session.commit()
    assert db_session.query(model).count() == 8, "CANARY: the long rows"
    try:
        yield client
    finally:
        db_session.rollback()
        line_tables.drop(db_session.get_bind(), TABLE)
        model.__table__.drop(bind=db_session.get_bind())
        retire_dynamic_model(TABLE)


def _read(client, **params):
    answer = client.get("/tables/%s/data" % TABLE, params=dict(pivot="true", **params))
    assert answer.status_code == 200, answer.text
    return answer.json()


def _groups(read):
    return [(row["lot"], row["wafer"]) for row in read["data"]]


def _values(read):
    return {(row["lot"], row["wafer"]): {item: cell["value"] for item, cell in row["cells"].items()}
            for row in read["data"]}


def test_a_page_is_key_groups_and_each_cell_names_its_row(grid, db_session):
    model = models.DYNAMIC_TABLES[TABLE]
    first = _read(grid, limit=2)
    assert first["pivot"] == {"column": "itemid", "value": "value", "keys": ["lot", "wafer"], "carry": [],
                              "items": ["a", "b", "c"], "items_more": 0}
    assert "carry" not in first["data"][0], "no carry declared, none read"
    assert first["total"] == 4, "four key groups, not eight rows"
    assert _groups(first) == [("L1", "W1"), ("L1", "W2")]
    assert _values(first) == {key: LONG[key] for key in _groups(first)}, "no group's items cut by the page"
    for row in first["data"]:
        for item, cell in row["cells"].items():
            held = db_session.query(model).filter(model.row_id == cell["row_id"]).one()
            assert (held.lot, held.wafer, held.itemid, held.value) == (row["lot"], row["wafer"], item, cell["value"])
    rest = _read(grid, skip=2, limit=2)
    assert _values(rest) == {("L2", "W1"): LONG[("L2", "W1")], ("L2", None): LONG[("L2", None)]}
    counted = grid.get("/tables/%s/data/count" % TABLE, params={"pivot": "true"}).json()
    assert counted["total"] == 4


def test_a_key_filter_and_an_item_filter_narrow_the_groups(grid):
    by_key = _read(grid, filters=json.dumps({"lot": {"filterType": "text", "type": "equals", "filter": "L2"}}))
    assert sorted(_groups(by_key), key=str) == [("L2", "W1"), ("L2", None)]
    assert by_key["pivot"]["items"] == ["a", "b"], "the items of the narrowed rows - L2 has no «c»"
    over = _read(grid, filters=json.dumps({"item:a": {"filterType": "number", "type": "greaterThan", "filter": 1}}))
    assert _groups(over) == [("L1", "W2"), ("L2", "W1")]
    assert _values(over)[("L1", "W2")] == LONG[("L1", "W2")], "the group's other items stay"
    blank = _read(grid, filters=json.dumps({"item:b": {"filterType": "number", "type": "blank"}}))
    assert _groups(blank) == [("L1", "W2")]
    both = _read(grid, filters=json.dumps({"item:b": {"filterType": "number", "type": "notBlank"},
                                           "item:c": {"filterType": "number", "type": "lessThan", "filter": 10}}))
    assert _groups(both) == [("L1", "W1")]
    assert grid.get("/tables/%s/data/count" % TABLE, params={"pivot": "true", "filters": json.dumps(
        {"item:a": {"filterType": "number", "type": "greaterThan", "filter": 1}})}).json()["total"] == 2


# ── the item column's own filter, carried from the long grid (소유자 11-05 ㄴ, 총괄 ㄱ) ──

def _item_is(*names):
    """The long grid's filter on the item column: one name, or any of several."""
    said = [{"filterType": "text", "type": "equals", "filter": name} for name in names]
    return said[0] if len(said) == 1 else {"filterType": "text", "operator": "OR", "conditions": said}


def _count(client, filters):
    return client.get("/tables/%s/data/count" % TABLE,
                      params={"pivot": "true", "filters": json.dumps(filters)}).json()["total"]


@pytest.mark.parametrize("filters, groups, items", [
    ({"itemid": _item_is("c")}, [("L1", "W1"), ("L1", "W2")], ["c"]),
    ({"itemid": _item_is("a", "b")}, [("L1", "W1"), ("L1", "W2"), ("L2", "W1"), ("L2", None)], ["a", "b"]),
    ({"lot": {"filterType": "text", "type": "equals", "filter": "L2"}, "itemid": _item_is("b")},
     [("L2", "W1"), ("L2", None)], ["b"]),
    ({"itemid": _item_is("z")}, [], []),
    ({"itemid": _item_is("a"), "item:c": {"filterType": "number", "type": "lessThan", "filter": 8}},
     [("L1", "W2")], ["a"]),
])
def test_the_item_columns_filter_picks_the_items_spread_and_the_groups_that_have_one(grid, filters, groups, items):
    """Key only and item only, both, none matching, and with an item:<v> filter on an item it does not spread - the
    long rows narrowed by the grid's own filter: the items, the cells, the groups and their count all follow."""
    read = _read(grid, filters=json.dumps(filters))
    assert sorted(_groups(read), key=str) == sorted(groups, key=str)
    assert (read["pivot"]["items"], read["pivot"]["items_more"]) == (items, 0)
    assert _values(read) == {key: {item: LONG[key][item] for item in items if item in LONG[key]} for key in groups}
    assert _count(grid, filters) == len(groups)


def test_the_items_past_the_setting_are_counted_from_the_filtered_items(grid, monkeypatch):
    from parsers import directory_watcher

    monkeypatch.setattr(directory_watcher, "pivot_max_columns", lambda settings=None: 1)
    read = _read(grid, filters=json.dumps({"itemid": _item_is("a", "b")}))
    assert (read["pivot"]["items"], read["pivot"]["items_more"]) == (["a"], 1), "of a and b, not a, b and c"


def test_a_blank_item_filter_keeps_the_groups_with_a_nameless_row_and_spreads_no_item(grid, db_session):
    model = models.DYNAMIC_TABLES[TABLE]
    db_session.add(model(row_id="nameless", lot="L1", wafer="W2", itemid=None, value=6.0))
    db_session.commit()
    filters = {"itemid": {"filterType": "text", "type": "blank"}}
    read = _read(grid, filters=json.dumps(filters))
    assert _groups(read) == [("L1", "W2")] and read["data"][0]["cells"] == {}
    assert (read["pivot"]["items"], read["pivot"]["items_more"]) == ([], 0)
    assert _count(grid, filters) == 1


def test_an_item_sort_puts_a_group_without_it_last_both_ways(grid):
    assert _groups(_read(grid, order_by="item:b")) == [("L2", "W1"), ("L1", "W1"), ("L2", None), ("L1", "W2")]
    assert _groups(_read(grid, order_by="item:b", order_desc="true")) == [
        ("L2", None), ("L1", "W1"), ("L2", "W1"), ("L1", "W2")]
    assert _groups(_read(grid, order_by="lot", order_desc="true"))[:2] == [("L2", None), ("L2", "W1")]


def test_the_items_past_the_setting_are_counted_not_spread(grid, monkeypatch):
    from parsers import directory_watcher

    monkeypatch.setattr(directory_watcher, "pivot_max_columns", lambda settings=None: 2)
    read = _read(grid)
    assert (read["pivot"]["items"], read["pivot"]["items_more"]) == (["a", "b"], 1)
    assert all(set(row["cells"]) <= {"a", "b"} for row in read["data"])


def test_a_cell_is_written_by_its_row_and_a_blank_cell_makes_the_row(grid, db_session):
    model = models.DYNAMIC_TABLES[TABLE]
    cell = _values_with_ids(_read(grid))[("L1", "W1")]["a"]
    answer = grid.put("/tables/%s/data/updates" % TABLE, json={"updates": [
        {"row_id": cell["row_id"], "updates": {"value": 11.0}, "source_name": "user", "updated_by": "probe"}]})
    assert answer.status_code == 200, answer.text
    answer = grid.put("/tables/%s/data/updates" % TABLE, json={"updates": [
        {"updates": {"lot": "L1", "wafer": "W2", "itemid": "b", "value": 6.0}, "source_name": "user",
         "updated_by": "probe"}]})
    assert answer.status_code == 200, answer.text
    after = _read(grid)
    assert _values(after)[("L1", "W1")]["a"] == 11.0
    assert _values_with_ids(after)[("L1", "W1")]["a"]["row_id"] == cell["row_id"], "the same row"
    assert _values(after)[("L1", "W2")] == {"a": 2.0, "b": 6.0, "c": 7.0}
    assert db_session.query(model).count() == 9, "one row made, none else"
    # the cell's history is its lines (cell-source overhaul), newest first: the edit's, over the file's that made it
    logged = grid.get("/tables/%s/rows/%s/cells/value/history" % (TABLE, cell["row_id"])).json()["logs"]
    assert [(log["source_name"], log["new_value"]) for log in logged] == [("user", 11), ("file", 1)], \
        "one history line, the edit's"


def _values_with_ids(read):
    return {(row["lot"], row["wafer"]): row["cells"] for row in read["data"]}


@pytest.mark.parametrize("pivot, said", [
    ({"column": "note", "value": "value"}, "'note' is not one of the table's keys"),
    ({"column": "itemid", "value": "lot"}, "'lot' is a key column"),
    ({"column": "itemid", "value": "gone"}, "'gone' is not a declared column"),
    ({"column": "itemid"}, 'pivot is {"column"'),
    ({"column": "itemid", "value": "value", "carry": "note"}, "carry is a list of columns"),
    ({"column": "itemid", "value": "value", "carry": ["lot"]}, "'lot' is already a pivot row's key"),
    ({"column": "itemid", "value": "value", "carry": ["value"]}, "'value' is already a pivot row's key"),
    ({"column": "itemid", "value": "value", "carry": ["gone"]}, "'gone' is not a declared column"),
    ({"column": "itemid", "value": "value", "carry": ["note", "note"]}, "'note' is named twice"),
])
def test_a_declaration_that_cannot_pivot_is_refused_at_save_and_at_read(grid, pivot, said):
    import grid_pivot

    entry = dict(ENTRY, pivot=pivot)
    path, sentence = grid_pivot.refusal(TABLE, entry)
    assert path.startswith("tables.%s.pivot" % TABLE) and said in sentence, sentence
    crud.TABLE_CONFIG[TABLE] = entry
    answer = grid.get("/tables/%s/data" % TABLE, params={"pivot": "true"})
    assert answer.status_code == 422 and said in answer.json()["detail"], answer.text
    assert grid_pivot.refusal(TABLE, ENTRY) is None and grid_pivot.refusal(TABLE, {"column_types": {}}) is None
    only = {"composite_key_source": ["itemid"], "column_types": ENTRY["column_types"], "pivot": ENTRY["pivot"]}
    assert "the table's only key is 'itemid'" in grid_pivot.refusal(TABLE, only)[1]


@pytest.mark.parametrize("params, said", [
    ({"transaction_id": "t"}, "not transaction_id"),
    ({"after": "x"}, "not after"),
    ({"filters": json.dumps({"note": {"type": "equals", "filter": "x"}})},
     "'note' is not a key column (lot, wafer) or the item column (itemid) of the pivot"),
    ({"filters": json.dumps({"value": {"filterType": "number", "type": "greaterThan", "filter": 1}})},
     "'value' fills the pivot's cells - filter it per item inside the pivot as item:<item>"),
    ({"order_by": "note"}, "cannot sort a pivot by 'note'"),
])
def test_what_a_pivot_read_does_not_take_is_refused_by_name(grid, params, said):
    answer = grid.get("/tables/%s/data" % TABLE, params=dict(pivot="true", **params))
    assert answer.status_code == 422 and said in answer.json()["detail"], answer.text


def test_a_search_keeps_each_key_group_any_of_whose_rows_matches_whole(grid):
    """q «c» matches one long row of (L1, W1) and one of (L1, W2) - their itemid: both groups, every item of each."""
    found = _read(grid, q="c")
    assert _values(found) == {("L1", "W1"): LONG[("L1", "W1")], ("L1", "W2"): LONG[("L1", "W2")]}
    assert found["total"] == 2 and found["pivot"]["items"] == ["a", "b", "c"]
    assert grid.get("/tables/%s/data/count" % TABLE, params={"pivot": "true", "q": "c"}).json()["total"] == 2
    assert _read(grid, q="nothing-matches")["data"] == []


def test_the_schema_says_the_pivot_or_null(grid):
    said = grid.get("/tables/%s/schema" % TABLE).json()
    assert said["pivot"] == {"column": "itemid", "value": "value", "carry": []}
    crud.TABLE_CONFIG[TABLE] = dict(ENTRY, pivot={"column": "itemid", "value": "lot"})
    assert "pivot" in grid.get("/tables/%s/schema" % TABLE).json()
    assert grid.get("/tables/%s/schema" % TABLE).json()["pivot"] is None, "a declaration a read refuses"


def test_a_carried_column_shows_its_one_value_or_how_many(grid, db_session, monkeypatch):
    """owner 11-06: `carry` - a column besides the keys, items and value shown on each pivot row, over the long rows
    the read took: one value -> it, more -> {"values": N}; a blank is no value (lead 11-06 ㄱ), all blank -> None. An item
    past pivot_max_columns still counts; an item column filter's narrowed rows are all it counts."""
    from parsers import directory_watcher

    notes = {("L1", "W1", "a"): "x", ("L1", "W1", "b"): "x", ("L1", "W1", "c"): "",
             ("L1", "W2", "a"): "x", ("L1", "W2", "c"): "y"}
    put = [{"updates": {"lot": lot, "wafer": wafer, "itemid": item, "note": note}, "source_name": "file",
            "updated_by": "probe"} for (lot, wafer, item), note in notes.items()]
    assert grid.put("/tables/%s/data/updates" % TABLE, json={"updates": put}).status_code == 200
    crud.TABLE_CONFIG[TABLE] = dict(ENTRY, pivot=dict(ENTRY["pivot"], carry=["note"]))

    def carried(**params):
        read = _read(grid, **params)
        assert read["pivot"]["carry"] == ["note"]
        return {(row["lot"], row["wafer"]): row["carry"]["note"] for row in read["data"]}

    assert carried() == {("L1", "W1"): {"value": "x"}, ("L1", "W2"): {"values": 2},
                         ("L2", "W1"): {"value": None}, ("L2", None): {"value": None}}
    only_a = json.dumps({"itemid": {"filterType": "set", "values": ["a"]}})
    assert carried(filters=only_a)[("L1", "W2")] == {"value": "x"}, "the narrowed long rows only"
    monkeypatch.setattr(directory_watcher, "pivot_max_columns", lambda: 1)
    shown = _read(grid)
    assert shown["pivot"]["items"] == ["a"], "CANARY: c is past the columns shown"
    assert {(r["lot"], r["wafer"]): r["carry"]["note"] for r in shown["data"]}[("L1", "W2")] == {"values": 2}


def test_a_table_without_a_pivot_reads_as_it_did(grid):
    crud.TABLE_CONFIG[TABLE] = {key: value for key, value in ENTRY.items() if key != "pivot"}
    assert grid.get("/tables/%s/data" % TABLE, params={"pivot": "true"}).status_code == 422
    plain = grid.get("/tables/%s/data" % TABLE).json()
    assert plain["total"] == 8 and "pivot" not in plain


def test_a_slow_pivot_read_asks_its_index_by_the_value_column(grid, monkeypatch):
    """A pivot read past `grid_auto_index_after_seconds` asks for the column that holds an item, not «item:b»."""
    from parsers import directory_watcher
    from runtime import index_wants

    asked = []
    monkeypatch.setattr(directory_watcher, "grid_auto_index_after", lambda settings=None: 0.000001)
    monkeypatch.setattr(index_wants, "want", lambda table, columns, *rest: asked.append((table, list(columns))))
    _read(grid, order_by="item:b", filters=json.dumps({"item:a": {"filterType": "number", "type": "equals",
                                                                   "filter": 1}}))
    assert asked and set(map(tuple, (columns for _t, columns in asked))) == {("value",)}, asked


def test_a_set_holding_null_takes_a_group_without_that_items_row(grid):
    """item:b set [5, null]: (L1, W1) by its 5, (L1, W2) by having no «b» row - not (L2, W1)'s 4 or (L2, None)'s 8."""
    filters = {"item:b": {"filterType": "set", "values": [5, None]}}
    assert sorted(_groups(_read(grid, filters=json.dumps(filters))), key=str) == [("L1", "W1"), ("L1", "W2")]
    assert _count(grid, filters) == 2
    assert _groups(_read(grid, filters=json.dumps({"item:b": {"filterType": "set", "values": [5]}}))) == [("L1", "W1")]


def _reckoned(rows, item):
    """{group: its `item` value or None} and the groups in key order - lot, then wafer with an absent wafer last."""
    groups = sorted({(lot, wafer) for lot, wafer, _i, _v in rows}, key=lambda g: (g[0], g[1] is None, g[1] or ""))
    value = {(lot, wafer): v for lot, wafer, i, v in rows if i == item}
    return groups, value


def test_every_pivot_read_on_postgresql_answers_as_the_rows_reckoned(pg_session, monkeypatch):
    """Production is PostgreSQL, where an absent key part is compared as ARRAY[a] = ARRAY[b]: 200 groups, one in ten
    with no wafer, items missing here and there - the item filter, the item sort (both ways), the sort of the
    no-wafer groups, a search and the counts, each against a reckoning of the same rows in Python."""
    import grid_pivot
    from grid_read import narrowed_table_query

    db = pg_session
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    models.init_dynamic_models({TABLE: ENTRY})
    model = models.DYNAMIC_TABLES[TABLE]
    model.__table__.create(bind=db.get_bind())
    rows = [("L%03d" % (g // 10), None if g % 10 == 9 else "W%02d" % (g % 10), "i%d" % i, float((g * 7 + i * 13) % 50))
            for g in range(200) for i in range(5) if (g + i) % 7]
    try:
        db.add_all([model(row_id="r%d" % n, lot=lot, wafer=wafer, itemid=item, value=value)
                    for n, (lot, wafer, item, value) in enumerate(rows)])
        db.commit()
        pivot = grid_pivot.of(TABLE)
        groups, value = _reckoned(rows, "i2")
        absent = [g for g in groups if g[1] is None]
        assert len(absent) == 20 and len(value) < len(groups), "CANARY: no-wafer groups, and groups without «i2»"

        def read(order_by="row_id", desc=False, **narrowing):
            narrowing = {k: json.dumps(v) if k == "filters" else v for k, v in narrowing.items()}
            query, _key = narrowed_table_query(db, TABLE, model, pivot=pivot, **narrowing)
            got = [tuple(g) for g in grid_pivot.order(grid_pivot.groups(query, model, pivot), model, pivot, order_by,
                                                      desc).all()]
            count = db.query(func.count()).select_from(grid_pivot.groups(query, model, pivot).subquery()).scalar()
            assert count == len(got)
            return got

        def by_value(desc, among):
            held = sorted((g for g in among if g in value), key=lambda g: (value[g], g[0], g[1] is None, g[1] or ""),
                          reverse=False)
            if desc:
                held = sorted(held, key=lambda g: value[g], reverse=True)    # stable: keys stay in order within a tie
            return held + [g for g in among if g not in value]

        assert read(filters={"item:i2": {"filterType": "number", "type": "lessThan", "filter": 20}}) == [
            g for g in groups if g in value and value[g] < 20]
        assert read(order_by="item:i2") == by_value(False, groups)
        assert read(order_by="item:i2", desc=True) == by_value(True, groups)
        assert read(order_by="item:i2", filters={"wafer": {"filterType": "text", "type": "blank"}}) == by_value(
            False, absent)
        assert read(q="L005") == [g for g in groups if g[0] == "L005"]
        assert read(filters={"item:i2": {"filterType": "set", "values": [value[groups[0]], None]}}) == [
            g for g in groups if g not in value or value[g] == value[groups[0]]]
    finally:
        db.rollback()
        model.__table__.drop(bind=db.get_bind())
        retire_dynamic_model(TABLE)


def test_the_item_columns_filter_on_postgresql(pg_session, monkeypatch):
    """Production is PostgreSQL: the same narrowing - the item column's filter beside a key's and an item:<v> EXISTS,
    one matching nothing, a blank one - read by the pivot's own query pieces."""
    import grid_pivot
    from grid_read import narrowed_table_query

    db = pg_session
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    models.init_dynamic_models({TABLE: ENTRY})
    model = models.DYNAMIC_TABLES[TABLE]
    model.__table__.create(bind=db.get_bind())
    try:
        db.add_all([model(row_id="%s-%s-%s" % (lot, wafer, item), lot=lot, wafer=wafer, itemid=item, value=value)
                    for (lot, wafer), items in LONG.items() for item, value in items.items()]
                   + [model(row_id="nameless", lot="L1", wafer="W2", itemid=None, value=6.0)])
        db.commit()
        pivot = grid_pivot.of(TABLE)

        def read(filters):
            rows, _key = narrowed_table_query(db, TABLE, model, filters=json.dumps(filters), pivot=pivot)
            groups = sorted((tuple(group) for group in grid_pivot.groups(rows, model, pivot).all()), key=str)
            return groups, grid_pivot.item_names(rows, model, pivot, 10)

        assert read({"lot": {"filterType": "text", "type": "equals", "filter": "L2"}, "itemid": _item_is("b")}) == (
            [("L2", "W1"), ("L2", None)], (["b"], 0))
        assert read({"itemid": _item_is("a", "b")})[1] == (["a", "b"], 0)
        assert read({"itemid": _item_is("a"), "item:c": {"filterType": "number", "type": "lessThan",
                                                         "filter": 8}}) == ([("L1", "W2")], (["a"], 0))
        assert read({"itemid": _item_is("z")}) == ([], ([], 0))
        assert read({"itemid": {"filterType": "text", "type": "blank"}}) == ([("L1", "W2")], ([], 0))
    finally:
        db.rollback()
        model.__table__.drop(bind=db.get_bind())
        retire_dynamic_model(TABLE)
