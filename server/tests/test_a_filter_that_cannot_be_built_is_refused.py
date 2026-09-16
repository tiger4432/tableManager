# -*- coding: utf-8 -*-
"""S-71 · S-72. A filter nobody could build must REFUSE, and the map key must ride along.

S-71: `apply_column_filters` used to log the failure and fall through, so the answer carried
every row of the table while still implying the column had been filtered. Measured
2026-09-08 on a `dt_map` holding 1,006,147 rows: a filter whose shape the parser could not
read came back HTTP 200 with all 1,006,147 instead of the 400 the map has. The refusal that
already existed one block above -- for a read-time join column that could not be expressed -- now
covers both reasons.

S-72: `GET /tables` carries `map_key_columns`, because the only other way to learn which
tables have a map key was one `/schema` request per table.

🔴 THE MUTATION THIS FILE EXISTS FOR: put the old `except` back (log and return the query
unfiltered) and `test_a_filter_the_parser_cannot_read_is_refused` goes red instead of
quietly answering with the whole table.
"""
import json
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                          # noqa: E402
from database import crud                                            # noqa: E402


class _Column:
    """Stands in for a mapped column: only its presence on the model is read here."""


class _Model:
    dt_lot = _Column()


def _apply(filters):
    return main.apply_column_filters(
        query=object(), table_model=_Model, table_name="dt_map",
        filters=filters)


def test_a_filter_the_parser_cannot_read_is_refused():
    """⛔ NOT LOGGED AND DROPPED. The caller asked to be narrowed; answering with
    everything is a wrong answer wearing a 200."""
    with pytest.raises(HTTPException) as caught:
        _apply(json.dumps({"dt_lot": "SYN-P70-01234"}))
    assert caught.value.status_code == 400
    assert "dt_lot" in str(caught.value.detail), caught.value.detail


def test_a_body_that_is_not_json_is_refused_and_names_the_parameter():
    """The failure can happen before any item exists, and the refusal still has to say
    where -- `None` there would read as "some column"."""
    with pytest.raises(HTTPException) as caught:
        _apply("{not json")
    assert caught.value.status_code == 400
    assert "filters" in str(caught.value.detail), caught.value.detail


def test_no_filter_is_not_a_failure():
    """An absent filter is not a broken one: it returns the query untouched, as before."""
    sentinel = object()
    assert main.apply_column_filters(
        query=sentinel, table_model=_Model, table_name="dt_map",
        filters=None) is sentinel


def test_the_table_list_carries_the_map_key_columns():
    """S-72. And a table that declares none is ABSENT rather than present-and-empty."""
    saved = dict(crud.TABLE_CONFIG)
    crud.TABLE_CONFIG.clear()
    crud.TABLE_CONFIG.update({
        "with_map": {"map_key_columns": ["dt_lot", "dt_slot"]},
        "without_map": {"column_types": {"a": "string"}},
        "empty_map": {"map_key_columns": []},
    })
    try:
        answer = main.list_tables()
    finally:
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
    assert answer["tables"] == ["with_map", "without_map", "empty_map"]
    assert answer["map_key_columns"] == {"with_map": ["dt_lot", "dt_slot"]}
