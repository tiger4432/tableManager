# -*- coding: utf-8 -*-
"""소유자 10-22 (총괄 95d9525b4 · 46844ff15 · a1d9382fb): the main grid's pivot - a long table keyed (lot, wafer,
itemid) read as one row per (lot, wafer) and one cell per itemid, through the grid's own route (`?pivot=1`).

  page     key groups, not long rows: a group's items are never cut by the page; each cell carries its row_id
  filters  a key column's as the grid's; an item's an EXISTS of its row (the grid filter's condition), blank: none
  sort     one item's value, a group without it last both ways; then the keys
  items    the narrowed rows' DISTINCT itemid, up to pivot_max_columns, and how many more
  write    a cell by its row_id through the grid save door; a blank cell by its keys - the row is made
  refused  a declaration that cannot pivot, at save and at read; an argument a pivot does not take
"""
import json

import pytest

from conftest import retire_dynamic_model
from database import crud, models

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
def grid(db_session, client):
    models.init_dynamic_models({TABLE: ENTRY})
    crud.TABLE_CONFIG[TABLE] = ENTRY
    models.DYNAMIC_TABLES[TABLE].__table__.create(bind=db_session.get_bind())
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
    assert first["pivot"] == {"column": "itemid", "value": "value", "keys": ["lot", "wafer"],
                              "items": ["a", "b", "c"], "items_more": 0}
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
    logged = db_session.query(models.AuditLog).filter(models.AuditLog.row_id == cell["row_id"],
                                                      models.AuditLog.column_name == "value").all()
    assert [(log.old_value, log.new_value) for log in logged] == [(1, 11)], "one history line, the edit's"


def _values_with_ids(read):
    return {(row["lot"], row["wafer"]): row["cells"] for row in read["data"]}


@pytest.mark.parametrize("pivot, said", [
    ({"column": "note", "value": "value"}, "'note' is not one of the table's keys"),
    ({"column": "itemid", "value": "lot"}, "'lot' is a key column"),
    ({"column": "itemid", "value": "gone"}, "'gone' is not a declared column"),
    ({"column": "itemid"}, 'pivot is {"column"'),
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
    ({"q": "L1"}, "not q"),
    ({"after": "x"}, "not after"),
    ({"filters": json.dumps({"note": {"type": "equals", "filter": "x"}})}, "'note' is not a key column"),
    ({"order_by": "note"}, "cannot sort a pivot by 'note'"),
])
def test_what_a_pivot_read_does_not_take_is_refused_by_name(grid, params, said):
    answer = grid.get("/tables/%s/data" % TABLE, params=dict(pivot="true", **params))
    assert answer.status_code == 422 and said in answer.json()["detail"], answer.text


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
