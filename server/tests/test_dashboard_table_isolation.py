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


@pytest.fixture
def two_broken_tables(monkeypatch, db_session):
    """TWO of them, one after the other, because that is what proves the loop CONTINUED.

    ⚠️ The declaration is walked in insertion order and these go on the end, so the second
    name can only appear if the first failure did not end the walk.
    """
    names = ["probe_broken_first", "probe_broken_second"]
    for name in names:
        monkeypatch.setitem(crud.TABLE_CONFIG, name, {"columns": {}})
        monkeypatch.setitem(models.DYNAMIC_TABLES, name, _BrokenModel())
    main.RECORRECTION_CACHE["value"] = None
    return names


def test_the_route_answers_200_and_names_the_table_it_could_not_count(
        client, one_broken_table):
    res = client.get("/dashboard/summary")
    assert res.status_code == 200, res.text
    body = res.json()

    named = {u["table_name"]: u["reason"] for u in body["uncounted_tables"]}
    assert one_broken_table in named, body["uncounted_tables"]
    assert "row_id" in named[one_broken_table], named[one_broken_table]


def test_a_table_that_could_not_be_read_is_named_as_that_and_never_as_a_figure(
        client, one_broken_table):
    """🔴 「could not count」 IS NOT 「counted, and it was zero」 — an operator acts differently
    on 「empty」 and 「could not read」.

    ⚰️ REWRITTEN, AND THE OLD SURFACE IS WHY (S-198). This asserted the broken table was
    absent from `table_stats`; `471f66f7` retired `table_stats`, `total_rows` and
    `total_tables` together (one loop made all three, and nothing read them). So the test had
    been red on a contract that no longer exists — measuring the SURFACE a property was once
    visible on, not the property.

    🔴 TODAY THE PROPERTY IS STRONGER, NOT WEAKER: there is no per-table figure at all, so a
    table that could not be read CANNOT be folded into one. That is what is asserted — the
    three retired names stay gone, and the table appears by name with a reason.
    """
    body = client.get("/dashboard/summary").json()

    named = {u["table_name"]: u["reason"] for u in body["uncounted_tables"]}
    assert one_broken_table in named
    assert "row_id" in named[one_broken_table]
    for retired in ("table_stats", "total_rows", "total_tables"):
        assert retired not in body, (
            "%s is back; a table that could not be read can be folded into a figure "
            "again, and this test has to grow that arm back" % retired)


def test_a_failure_does_not_end_the_walk_so_a_LATER_table_is_still_examined(
        client, two_broken_tables):
    """🔴 THE GATE THAT MATTERS, MEASURED ON WHAT SURVIVES. One table's failure must not cost
    the ones after it — the `try` is INSIDE the loop and the loop `continue`s.

    ⚰️ THE OLD FORM COMPARED `table_stats` WITH AND WITHOUT THE BROKEN TABLE, and there is no
    per-table figure left to compare. Two broken tables answer the same question through the
    field that did survive: the declaration is walked in insertion order, so the SECOND name
    can only appear if the first failure did not end the walk. A `try` around the whole loop
    — which is what this guards against — names one and loses the rest silently.

    ⚠️ WHAT THIS DOES NOT MEASURE, STATED: the per-table `db.rollback()`. These probes raise
    in Python before any statement reaches the database, and sqlite does not abort a
    transaction on a failed statement the way PostgreSQL does. The rollback's necessity is
    recorded at its seat in `main.py`; it is not something this file can score.
    """
    body = client.get("/dashboard/summary").json()

    named = [u["table_name"] for u in body["uncounted_tables"]]
    assert named == two_broken_tables, named

    healthy = set(crud.TABLE_CONFIG) - set(two_broken_tables)
    assert healthy, "the fixture declares real tables too, or this asserts nothing"
    assert not (healthy & set(named)), "a healthy table was dragged in by the broken ones"


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
