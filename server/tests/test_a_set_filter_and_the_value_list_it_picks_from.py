# -*- coding: utf-8 -*-
"""The grid's multi-value filter (소유자 «시안대로 해», 총괄 11-05): a set filter `{"filterType": "set", "values": [...]}`
- each value as `equals` reads it, a null the blank cells, [] no row - and the list it picks from,
`GET /tables/{t}/data/values?column=` (the grid's narrowing less the column's own filter). A filter shape the translator
does not read is refused by name where it used to be dropped into an unnarrowed 200 (S-71).

  road \\ filter               set of texts  set + null    []    numbers   not numbers   an unknown shape
  grid page · count · CSV       its rows      + blanks      0     its rows  422           422
  pivot key / item column       its groups                                               422
  pivot item (value)            its groups                                               422
  report read · queue predicate                                                          ReadRefused · QueuePredicateError
  ordered_filtered_columns      counted       counted       -     counted   -             -

  value list                    sorted, blank a null last · own filter left out · others kept · search contains
                                cap -> more · pivot item column = the pivot read's items · a slow one asks its index
  pivot value list              item:<x> = its cells (a group without the row: blank) · a picked value narrows
                                the read · the value column and an unknown name refused as the read refuses
"""
import json

import pytest

import grid_read
from column_filter import ordered_filtered_columns
from tests.test_the_grid_pivots_a_long_table_by_its_item_key import TABLE, grid  # noqa: F401


def _set(*values):
    return {"filterType": "set", "values": list(values)}


UNKNOWN = [{"filterType": "date", "type": "equals", "dateFrom": "2026-11-05"},
           {"filterType": "text", "type": "between", "filter": "L1"},
           {"filterType": "text", "type": "lessThan", "filter": "L2"}]


def _get(client, path, filters=None, **params):
    if filters is not None:
        params["filters"] = json.dumps(filters)
    return client.get("/tables/%s/%s" % (TABLE, path), params=params)


def _count(client, filters, **params):
    answer = _get(client, "data/count", filters, **params)
    assert answer.status_code == 200, answer.text
    return answer.json()["total"]


@pytest.mark.parametrize("filters, rows", [
    ({"lot": _set("L1")}, 5),
    ({"wafer": _set("W2", None)}, 3),
    ({"wafer": _set(None)}, 1),
    ({"lot": _set()}, 0),
    ({"value": _set(1, "9", 8.0)}, 3),
    ({"lot": _set("L2"), "value": _set(3, 5)}, 1),
])
def test_a_set_narrows_the_page_the_count_and_the_csv_alike(grid, filters, rows):  # noqa: F811
    assert _count(grid, filters) == rows
    page = _get(grid, "data", filters)
    assert page.status_code == 200 and len(page.json()["data"]) == rows, page.text
    csv = _get(grid, "export", filters)
    assert csv.status_code == 200 and len(csv.text.strip().splitlines()) == rows + 1, csv.text


def test_a_set_of_not_numbers_on_a_number_column_is_refused(grid):  # noqa: F811
    answer = _get(grid, "data/count", {"value": _set(1, "x")})
    assert answer.status_code == 422 and "is not a list of numbers for 'value'" in answer.json()["detail"]


def test_a_pivot_key_and_item_take_a_set(grid):  # noqa: F811
    assert _count(grid, {"itemid": _set("c")}, pivot="true") == 2
    assert _count(grid, {"item:b": _set(4, 8)}, pivot="true") == 2


@pytest.mark.parametrize("shape", UNKNOWN)
@pytest.mark.parametrize("path, params", [("data", {}), ("data/count", {}), ("export", {}),
                                          ("data/count", {"pivot": "true"}), ("data/values", {"column": "wafer"})])
def test_an_unknown_shape_is_refused_by_name_on_every_road(grid, shape, path, params):  # noqa: F811
    answer = _get(grid, path, {"lot": shape}, **params)
    assert answer.status_code == 422 and "item 'lot'" in answer.json()["detail"], answer.text


@pytest.mark.parametrize("shape", UNKNOWN[:2])
def test_an_unknown_shape_on_a_pivot_item_is_refused(grid, shape):  # noqa: F811
    assert _get(grid, "data/count", {"item:a": shape}, pivot="true").status_code == 422


def test_the_report_read_and_the_queue_predicate_refuse_an_unknown_shape(grid, db_session):  # noqa: F811
    from chain import report_reads
    from chain.enrichment import config
    from database import models

    with pytest.raises(report_reads.ReadRefused, match="is not a filter 'lot' can read"):
        report_reads._rows(db_session, {"table": TABLE}, ["lot"], where={"lot": UNKNOWN[1]})
    with pytest.raises(config.QueuePredicateError, match="is not a filter 'lot' can read"):
        config._queue_spec_condition(models.DYNAMIC_TABLES[TABLE], {"derived_table": TABLE}, "lot", {"type": "between"})


def test_ordered_filtered_columns_counts_a_set_with_a_value():
    filters = json.dumps({"a": _set("x"), "b": _set(None), "c": _set(), "d": {"type": "equals", "filter": "y"},
                          "e": {"type": "contains", "filter": "z"}})
    assert ordered_filtered_columns(filters) == ["a", "d"]


def _values(client, column, filters=None, **params):
    answer = _get(client, "data/values", filters, column=column, **params)
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_the_value_list_is_sorted_with_the_blank_last(grid):  # noqa: F811
    assert _values(grid, "lot") == {"table_name": TABLE, "column": "lot", "values": ["L1", "L2"], "more": False}
    assert _values(grid, "wafer")["values"] == ["W1", "W2", None]
    assert _values(grid, "value")["values"] == [1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 8.0, 9.0]


def test_the_value_list_leaves_out_its_own_filter_and_keeps_the_others(grid):  # noqa: F811
    assert _values(grid, "wafer", {"wafer": _set("W2")})["values"] == ["W1", "W2", None]
    assert _values(grid, "wafer", {"lot": _set("L2")})["values"] == ["W1", None]
    assert _values(grid, "lot", {"value": {"filterType": "number", "type": "greaterThan", "filter": 6}})["values"] \
        == ["L1", "L2"]
    assert _values(grid, "lot", {"value": _set(1)})["values"] == ["L1"]


def test_the_value_list_search_keeps_the_values_that_contain_it(grid):  # noqa: F811
    assert _values(grid, "lot", search="2")["values"] == ["L2"]
    assert _values(grid, "wafer", search="w")["values"] == ["W1", "W2"], "a blank contains nothing"


def test_the_value_list_stops_at_its_cap(grid, monkeypatch):  # noqa: F811
    monkeypatch.setattr(grid_read, "VALUES_CAP", 3)
    assert _values(grid, "value") == {"table_name": TABLE, "column": "value", "values": [1.0, 2.0, 3.0], "more": True}
    assert _values(grid, "wafer") == {"table_name": TABLE, "column": "wafer", "values": ["W1", "W2", None],
                                      "more": False}


def test_the_value_list_refuses_a_column_the_table_lacks(grid):  # noqa: F811
    answer = _get(grid, "data/values", column="nope")
    assert answer.status_code == 422 and "has no column" in answer.json()["detail"], answer.text


@pytest.mark.parametrize("column", ["value", "nope"])
def test_on_a_pivot_the_value_list_refuses_a_name_as_the_read_does(grid, column):  # noqa: F811
    listed = _get(grid, "data/values", column=column, pivot="true")
    read = _get(grid, "data/count", {column: _set("x")}, pivot="true")
    assert listed.status_code == read.status_code == 422, (listed.text, read.text)
    assert listed.json()["detail"] == read.json()["detail"]


@pytest.mark.parametrize("column, filters, search, values", [
    ("item:a", None, None, [1.0, 2.0, 3.0, None]),         # (L2, None) has no «a» row: its cell shows blank
    ("item:c", None, None, [7.0, 9.0, None]),
    ("item:a", {"item:a": _set(1)}, None, [1.0, 2.0, 3.0, None]),
    ("item:a", {"lot": _set("L2")}, None, [3.0, None]),
    ("item:c", None, "9", [9.0]),
])
def test_a_pivot_items_value_list_is_its_cells(grid, column, filters, search, values):  # noqa: F811
    params = {"pivot": "true"} if search is None else {"pivot": "true", "search": search}
    assert _values(grid, column, filters, **params)["values"] == values


@pytest.mark.parametrize("column", ["lot", "wafer", "itemid", "item:a", "item:b", "item:c"])
def test_on_a_pivot_a_value_picked_from_the_list_narrows_the_read(grid, column):  # noqa: F811
    for value in _values(grid, column, pivot="true")["values"]:
        answer = _get(grid, "data/count", {column: _set(value)}, pivot="true")
        assert answer.status_code == 200 and answer.json()["total"] > 0, (column, value, answer.text)


@pytest.mark.parametrize("filters", [None, {"lot": _set("L2")}, {"item:c": {"filterType": "number", "type": "lessThan",
                                                                             "filter": 8}}])
def test_the_pivot_item_column_list_is_the_pivot_reads_items(grid, filters):  # noqa: F811
    read = _get(grid, "data", filters, pivot="true")
    assert read.status_code == 200, read.text
    assert _values(grid, "itemid", filters, pivot="true")["values"] == read.json()["pivot"]["items"]


def test_a_slow_value_list_asks_for_its_columns_index(grid, monkeypatch):  # noqa: F811
    from database import models
    from parsers import directory_watcher
    from runtime import index_wants

    asked = []
    monkeypatch.setattr(directory_watcher, "grid_auto_index_after", lambda: 1e-9)
    monkeypatch.setattr(index_wants, "want", lambda table, columns, why, *rest: asked.append((table, columns, why)))
    _values(grid, "lot", {"wafer": _set("W1")})
    assert (TABLE, ["lot"], models.AUTO_SLOW_SORT) in asked, asked
    assert (TABLE, ["wafer"], models.AUTO_SLOW_FILTER) in asked, asked
