# -*- coding: utf-8 -*-
"""S-71 «a filter that cannot be built is refused, not dropped» - the two it missed (총괄 10-23): a filter on a column
the table does not have, and a value its number column cannot read, came back as no condition and the read answered
the WHOLE table (the client found it building «delete the pivot's rows by key»). Now every road refuses by name.

  road \\ filter                          a column it lacks   a number column, not a number   an empty value
  grid page · count · CSV                  422, the name       422, the value                  no condition: all rows
  pivot item (its value column)            -                   422, the value                  no condition
  AI report read (report_reads._rows)      ReadRefused         ReadRefused                     all rows
  enrichment queue predicate               QueuePredicateError (as before, now with the reason)
  an empty compound condition              no condition (unchanged)
"""
import json

import pytest

from column_filter import FilterRefused, get_column_filter_condition
from tests.test_the_grid_pivots_a_long_table_by_its_item_key import TABLE, grid  # noqa: F401

LACKS = {"nope": {"filterType": "text", "type": "equals", "filter": "x"}}
NOT_A_NUMBER = {"value": {"filterType": "number", "type": "equals", "filter": "abc"}}
EMPTY = {"note": {"filterType": "text", "type": "contains"}}
EMPTY_COMPOUND = {"note": {"filterType": "text", "operator": "AND", "conditions": []}}
ROWS = 8


def _get(client, path, filters, **params):
    return client.get("/tables/%s/%s" % (TABLE, path), params=dict(filters=json.dumps(filters), **params))


@pytest.mark.parametrize("path", ["data", "data/count", "export"])
def test_a_grid_road_refuses_a_column_it_lacks_and_a_value_its_number_column_cannot_read(grid, path):  # noqa: F811
    lacks = _get(grid, path, LACKS)
    assert lacks.status_code == 422 and "'%s' has no column 'nope'" % TABLE in lacks.json()["detail"], lacks.text
    wrong = _get(grid, path, NOT_A_NUMBER)
    assert wrong.status_code == 422 and "'abc' is not a number for 'value'" in wrong.json()["detail"], wrong.text
    for nothing in (EMPTY, EMPTY_COMPOUND):
        assert _get(grid, path, nothing).status_code == 200


def test_the_grid_page_and_its_count_read_every_row_for_an_empty_filter(grid):  # noqa: F811
    assert len(_get(grid, "data", EMPTY).json()["data"]) == ROWS
    assert _get(grid, "data/count", EMPTY).json()["total"] == ROWS


def test_a_pivot_item_filter_its_value_column_cannot_read_is_refused(grid):  # noqa: F811
    refused = _get(grid, "data", {"item:a": {"filterType": "number", "type": "inRange", "filter": "x", "filterTo": 3}},
                   pivot="true")
    assert refused.status_code == 422 and "'x' to 3 is not a number range for 'value'" in refused.json()["detail"]
    assert _get(grid, "data", {"item:a": {"filterType": "number", "type": "equals"}}, pivot="true").status_code == 200


def test_the_report_read_refuses_by_name(grid, db_session):  # noqa: F811
    from chain import report_reads

    with pytest.raises(report_reads.ReadRefused, match="has no column 'nope'"):
        report_reads._rows(db_session, {"table": TABLE}, ["lot"], where=LACKS)
    with pytest.raises(report_reads.ReadRefused, match="'abc' is not a number for 'value'"):
        report_reads._rows(db_session, {"table": TABLE}, ["lot"], where=NOT_A_NUMBER)
    assert len(report_reads._rows(db_session, {"table": TABLE}, ["lot"], where=EMPTY)) == ROWS


def test_the_enrichment_queue_says_why(grid):  # noqa: F811
    from chain.enrichment import config
    from database import models

    rule = {"derived_table": TABLE}
    with pytest.raises(config.QueuePredicateError, match="has no column 'nope'"):
        config._queue_spec_condition(models.DYNAMIC_TABLES[TABLE], rule, "nope", {"type": "blank"})


def test_the_translator_itself(grid):  # noqa: F811
    from database import models

    model = models.DYNAMIC_TABLES[TABLE]
    with pytest.raises(FilterRefused):
        get_column_filter_condition(model, "nope", LACKS["nope"])
    assert get_column_filter_condition(model, "note", EMPTY["note"]) is None
    assert get_column_filter_condition(model, "note", EMPTY_COMPOUND["note"]) is None
