# -*- coding: utf-8 -*-
"""A text PostgreSQL will not read as a time is not entered; the rest of its row and batch is written (owner 10-29 ㄱ,
lead: PostgreSQL judges, one query per batch). Before, «not a time» in a datetime column failed the whole batch on
INSERT with PostgreSQL's own message (measured 0 of 3 rows)."""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import event, text  # noqa: E402

import conftest  # noqa: E402
from chain import ingestion_worker as worker  # noqa: E402
from database import crud, models, schemas  # noqa: E402

pytestmark = pytest.mark.pg
S = conftest.PG_TEST_SCHEMA
T = "pgqa_dv_time"
CFG = {T: {"business_key": "part_no",
           "column_types": {"part_no": "string", "qty": "number", "note": "string", "at": "datetime"}}}
GOOD = "2026-10-29T10:00:00+09:00"


@pytest.fixture
def table(pg_engine, pg_session):
    with pg_engine.begin() as c:
        c.execute(text('CREATE TABLE "%s"."%s" (LIKE "%s"."pgqa_bk_table" INCLUDING ALL)' % (S, T, S)))
        c.execute(text('ALTER TABLE "%s"."%s" ADD COLUMN "at" timestamptz' % (S, T)))
    models.init_dynamic_models(CFG)
    crud.TABLE_CONFIG.update(CFG)
    yield pg_session
    pg_session.rollback()
    with pg_engine.begin() as c:
        c.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (S, T)))
    crud.TABLE_CONFIG.pop(T, None)


def _items(pairs):
    return [schemas.GeneralUpdateItem(business_key_val=k, updates={"part_no": k, "at": v}) for k, v in pairs]


def _at(db):
    rows = db.execute(text('SELECT part_no, at IS NOT NULL FROM "%s"."%s" ORDER BY 1' % (S, T))).fetchall()
    db.rollback()
    return dict(rows)


def test_a_refused_time_is_not_entered_and_the_rest_is_written(table):
    report = {}
    crud.apply_batch_updates(table, T, schemas.GeneralUpdateBatch(
        updates=_items([("P1", GOOD), ("P2", "not a time"), ("P3", "2026.10.29 10:00"), ("P4", "10/29/2026")]),
        transaction_id="tx-time"), drop_report=report)
    table.commit()

    assert _at(table) == {"P1": True, "P2": False, "P3": True, "P4": False}, "2026.10.29 is PostgreSQL's to take"
    assert report["by_reason"] == {crud.DROP_VALUE_REFUSED: 2}
    assert report["refused_values"]["at"]["cells"] == 2


def test_the_chain_door_asks_inside_its_held_write(table):
    ok, reason = worker.apply_chain_writes(
        table, "tx-time-chain", {"name": "r_probe", "target_table": T}, 0, {T: {"r_probe"}},
        {T: [{"business_key_val": "C1", "updates": {"part_no": "C1", "at": "not a time"}},
             {"business_key_val": "C2", "updates": {"part_no": "C2", "at": GOOD}}]}, [], [],
        {T: ["r_probe"]}, [])
    assert ok is True, reason
    import session_contract
    session_contract.release_hold(table)
    table.commit()
    assert _at(table) == {"C1": False, "C2": True}


def test_a_clean_batch_asks_once_and_an_iso_batch_not_at_all(table, pg_engine):
    seen = []
    listener = lambda conn, cursor, statement, *a: seen.append(statement)   # noqa: E731
    event.listen(table.get_bind(), "before_cursor_execute", listener)
    try:
        crud.times_the_database_refuses(table, T, _items([("A", GOOD), ("B", "2026-10-29 10:00:00")]))
        iso = sum("timestamptz" in s and "unnest" in s for s in seen)
        seen.clear()
        crud.times_the_database_refuses(table, T, _items([("A", "2026/10/29"), ("B", "2026.10.29")]))
        other = sum("timestamptz" in s and "unnest" in s for s in seen)
    finally:
        event.remove(table.get_bind(), "before_cursor_execute", listener)
        table.rollback()
    assert (iso, other) == (0, 1)


def test_the_cost_of_asking(table, capsys):
    """Lead 10-29: the ms for 1,000 rows of non-ISO times, all good, and with 10 bad. Printed, not asserted."""
    good = _items([("K%d" % i, "2026/10/%02d %02d:%02d:00" % (i % 28 + 1, i % 24, i % 60)) for i in range(1000)])
    bad = list(good)
    for i in range(0, 1000, 100):
        bad[i] = _items([("K%d" % i, "not a time %d" % i)])[0]
    out = {}
    for name, items in (("all_good", good), ("ten_bad", bad)):
        started = time.perf_counter()
        refused = crud.times_the_database_refuses(table, T, items)
        out[name] = (round((time.perf_counter() - started) * 1000, 1), len(refused.get("at", ())))
    table.rollback()
    with capsys.disabled():
        print("\nCOST ms, refused:", out)
    assert out["all_good"][1] == 0 and out["ten_bad"][1] == 10
