# -*- coding: utf-8 -*-
"""One table that cannot be counted must not take the dashboard down with it.

Measured 2026-09-04: `GET /dashboard/summary` answered 500 because ONE declared table's
physical shape had drifted from its declaration (`UndefinedColumn: row_id`). Twenty-odd
tables' figures disappeared because of one, and with them the `recorrection` and `effort`
fields - which are the instruments for two of the project's core-value metrics. The meter
had been dark for as long as that one table had been wrong.

🔴 THE TESTS DRIVE THE ROUTE, NOT THE LOOP. Twice today a set of tests went UNDER the
defect by exercising a helper the broken caller never reached, and stayed green while the
defect was restored.

⚠️ AND AN UNCOUNTED TABLE IS A THIRD STATE. Not a row of zero - an operator acts
differently on "empty" and "could not read" - and not silently dropped either, which would
read as "that table does not exist".
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                      # noqa: E402
from database import crud, models                                # noqa: E402


class _BrokenModel:
    """A declared table whose physical column the database does not have."""

    class _Missing:
        def __getattr__(self, item):
            raise RuntimeError('column "row_id" does not exist')

    row_id = property(lambda self: (_ for _ in ()).throw(
        RuntimeError('column "row_id" does not exist')))


@pytest.fixture
def one_broken_table(monkeypatch, db_session):
    """Put a table into the declaration whose count will raise, alongside the real ones."""
    broken = "probe_broken_table"
    monkeypatch.setitem(crud.TABLE_CONFIG, broken, {"columns": {}})
    monkeypatch.setitem(models.DYNAMIC_TABLES, broken, _BrokenModel())
    main.RECORRECTION_CACHE["value"] = None
    return broken


def test_the_route_answers_200_and_names_the_table_it_could_not_count(
        client, one_broken_table):
    res = client.get("/dashboard/summary")
    assert res.status_code == 200, res.text
    body = res.json()

    named = {u["table_name"]: u["reason"] for u in body["uncounted_tables"]}
    assert one_broken_table in named, body["uncounted_tables"]
    assert "row_id" in named[one_broken_table], named[one_broken_table]


def test_the_broken_table_is_not_reported_as_a_table_with_zero_rows(
        client, one_broken_table):
    """🔴 "could not count" is not "counted, and it was zero". Reporting the second would
    tell an operator the table is empty, which is a different instruction."""
    body = client.get("/dashboard/summary").json()
    assert one_broken_table not in {t["table_name"] for t in body["table_stats"]}


def test_every_other_table_still_reports_its_own_number(client, one_broken_table):
    """🔴 THE GATE THAT MATTERS. PostgreSQL aborts the whole transaction on a failed
    statement, so without a rollback every table AFTER the bad one fails too - the
    isolation would be a comment rather than a behaviour. The comparison is against the
    same route with nothing broken."""
    with_broken = client.get("/dashboard/summary").json()

    del crud.TABLE_CONFIG[one_broken_table]
    del models.DYNAMIC_TABLES[one_broken_table]
    main.RECORRECTION_CACHE["value"] = None
    without = client.get("/dashboard/summary").json()

    assert {t["table_name"]: t["row_count"] for t in with_broken["table_stats"]} == \
           {t["table_name"]: t["row_count"] for t in without["table_stats"]}
    assert with_broken["total_rows"] == without["total_rows"]


def test_a_healthy_dashboard_lists_nothing_as_uncounted(client):
    """The empty list is the normal answer, and it has to be distinguishable from the
    field being absent."""
    main.RECORRECTION_CACHE["value"] = None
    body = client.get("/dashboard/summary").json()
    assert body["uncounted_tables"] == []


def test_the_core_value_meters_survive_a_broken_table(client, one_broken_table):
    """What the 500 was actually costing: these two fields are the core-value
    instruments, and they were absent for every request the bad table poisoned."""
    body = client.get("/dashboard/summary").json()
    assert "recorrection" in body and "effort" in body
