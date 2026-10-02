# -*- coding: utf-8 -*-
"""총괄 35b76ba92 — 표 하나를 통째로 비운다 (소유자 10-02 「100만 행인데 어케 지움」 · 「ㄹ로 내가 내일 할게」).

`scripts/empty_table.py` on PostgreSQL, on the hold-copy world: the report says what goes; the
apply takes the rows, the table's cell layers and overwrites in one transaction with one summary
audit line, withdraws the ledger atoms of every source reading the table through `rescope`, and
leaves no outbox event. It refuses a count that moved and a view.
"""
import os
import sys

import pytest
from sqlalchemy import text

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (SERVER_DIR, os.path.join(SERVER_DIR, "scripts")):
    if path not in sys.path:
        sys.path.insert(0, path)

import empty_table                                                   # noqa: E402
from database import crud, models, schemas                           # noqa: E402
from support import hold_world as hw                                 # noqa: E402

pytestmark = pytest.mark.pg


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path)


def _seeded(world):
    """Two official rows (two keys), said by the ledger, and a person's cell on one."""
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7},
                    {"log_id": "B", "dt_job": "J2", "dt_x": 3, "dt_y": 4, "netdie": 8}])
    hw.settle(world)
    db = world["db"]
    target = db.query(models.DYNAMIC_TABLES[hw.OFFICIAL]).filter_by(dt_job="J2").one().row_id
    crud.apply_batch_updates(db, hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=target, updates={"netdie": 9}, source_name=crud.USER_SOURCE,
                                  updated_by="person")]))
    db.commit()
    hw.settle(world)
    assert len(hw.said(world)) == 2


def _count(world, sql, **params):
    return world["db"].execute(text(sql), params).scalar()


def test_the_report_says_what_goes_and_writes_nothing(world):
    _seeded(world)
    found = empty_table.report(world["db"], world["setup"], hw.OFFICIAL, world["rules"])
    assert (found["rows"], found["user_layers"], found["ledger_atoms"], found["chain_rules"]) \
        == (2, 1, {hw.SOURCE: 2}, [hw.RECOUNT["name"]])
    assert found["layers"] > found["user_layers"] and found["overwrites"] > 0
    assert _count(world, 'SELECT count(*) FROM "%s"' % hw.OFFICIAL) == 2


def test_apply_takes_rows_layers_overwrites_and_atoms_and_wakes_nothing(world):
    _seeded(world)
    log_layers = _count(world, "SELECT count(*) FROM cell_sources WHERE table_name = :t", t=hw.LOG)
    outbox = _count(world, "SELECT coalesce(max(id), 0) FROM database_outbox")
    result = empty_table.empty(world["db"], world["engine"], world["setup"], hw.OFFICIAL,
                               world["rules"], confirm_rows=2, by="tester")

    assert result["done"]["rows"] == 2
    assert result["done"]["ledger_withdrawn"] == {hw.SOURCE: 2}
    for sql in ('SELECT count(*) FROM "%s"' % hw.OFFICIAL,
                "SELECT count(*) FROM cell_sources WHERE table_name = '%s'" % hw.OFFICIAL,
                "SELECT count(*) FROM cell_overwrites WHERE table_name = '%s'" % hw.OFFICIAL,
                "SELECT count(*) FROM database_outbox WHERE id > %d" % outbox):
        assert _count(world, sql) == 0, sql
    assert hw.said(world) == []
    assert _count(world, "SELECT count(*) FROM cell_sources WHERE table_name = :t", t=hw.LOG) \
        == log_layers                                                 # the other table untouched
    assert _count(world, "SELECT count(*) FROM audit_logs WHERE table_name = :t AND source_name = :s",
                  t=hw.OFFICIAL, s=empty_table.SOURCE) == 1


def test_a_count_that_moved_is_refused_and_nothing_goes(world):
    _seeded(world)
    with pytest.raises(empty_table.Refused):
        empty_table.empty(world["db"], world["engine"], world["setup"], hw.OFFICIAL,
                          world["rules"], confirm_rows=3, by="tester")
    assert _count(world, 'SELECT count(*) FROM "%s"' % hw.OFFICIAL) == 2
    assert len(hw.said(world)) == 2


def test_a_view_is_refused(world, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, hw.OFFICIAL, {**crud.TABLE_CONFIG[hw.OFFICIAL],
                                                         "kind": "view"})
    with pytest.raises(empty_table.Refused):
        empty_table.report(world["db"], world["setup"], hw.OFFICIAL, world["rules"])
