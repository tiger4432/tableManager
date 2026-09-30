# -*- coding: utf-8 -*-
"""총괄 2dd93d4a9 2 — 시각 칸은 «같은 순간이면 같은 값». 「값이 바뀌었나」를 묻는 자리는 모두
`crud.values_differ` 를 지나고, datetime 칸이면 그 함수가 순간으로 견준다. 꼬리 없는 시각은 PG 가 읽는
세션 시간대로 읽는다 — 쓰기 문이 그 글을 PG 에 넘길 때와 같은 규칙이다.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import retire_dynamic_model                         # noqa: E402
from database.database import Base                                # noqa: E402
from database import crud, models, schemas                        # noqa: E402

LEFT, RIGHT = "instant_left", "instant_right"
TABLES = {
    LEFT: {"business_key": "k", "composite_key_source": ["k"],
           "column_types": {"k": "string", "job": "string", "t": "datetime"}},
    RIGHT: {"business_key": "rk", "composite_key_source": ["rk"],
            "column_types": {"rk": "string", "job": "string", "rt": "datetime"}},
}
INSTANT = datetime(2026, 9, 29, 1, 0, tzinfo=timezone.utc)


@pytest.fixture(name="db")
def fixture_db(pg_engine):
    saved = dict(crud.TABLE_CONFIG)
    for name in TABLES:
        retire_dynamic_model(name)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    with pg_engine.begin() as conn:
        for name in TABLES:
            conn.execute(text('DROP TABLE IF EXISTS "%s"' % name))
            conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": name})
    Base.metadata.create_all(bind=pg_engine,
                             tables=[models.DYNAMIC_TABLES[n].__table__ for n in TABLES])
    session = sessionmaker(bind=pg_engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in TABLES:
            retire_dynamic_model(name)
        with pg_engine.begin() as conn:
            for name in TABLES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"' % name))
                conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"),
                             {"t": name})


def _apply(db, table, updates):
    """Changed cells, ROW_UPDATE lines and outbox events one write left on LEFT."""
    lines = db.query(models.AuditLog).filter(models.AuditLog.table_name == LEFT,
                                             models.AuditLog.column_name == "ROW_UPDATE")
    events = db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.table_name == LEFT)
    before = (lines.count(), events.count())
    _rows, changed, _logs, _deleted = crud.apply_batch_updates(
        db, table, schemas.GeneralUpdateBatch(updates=updates))
    db.commit()
    return len(changed), lines.count() - before[0], events.count() - before[1]


def _file(rows, source="instant.csv"):
    return [schemas.GeneralUpdateItem(updates=dict(row), source_name=source, updated_by="t")
            for row in rows]


def _join():
    from chain import rule_shape
    rule = rule_shape.as_chain_rule(rule_shape.from_declaration({
        "name": "instant_join", "on": {"table": RIGHT},
        "derive": {"kind": "join", "join": {"on": [{"left": "job", "right": "job"}],
                                            "take": [{"from": "rt", "into": "t"}]}},
        "into": {"table": LEFT}}))
    rule["trigger_table"] = RIGHT
    return rule


@pytest.mark.pg
def test_the_same_instant_moved_again_is_not_written(db):
    """0ba95c23a measured 1 changed cell on every re-move - the table's datetime and the moved
    ISO text differ by a 'T'. The first move and a different instant are written as before."""
    from chain import join_into
    _apply(db, RIGHT, _file([{"rk": "R1", "job": "J1", "rt": "2026-09-28T08:00:00+09:00"}]))
    _apply(db, LEFT, _file([{"k": "L1", "job": "J1", "t": "2026-09-29 10:00:00+09:00"}]))
    right_ids = [r[0] for r in db.execute(text('SELECT row_id FROM "%s"' % RIGHT))]

    def move():
        return _apply(db, LEFT, join_into.propose(db, _join(), right_ids)["updates"])

    runs = [move(), move(), move()]
    _apply(db, RIGHT, _file([{"rk": "R1", "job": "J1", "rt": "2026-09-28T09:30:00+09:00"}]))
    runs.append(move())

    first, again, third, other = runs
    assert first[:2] == (1, 1) and first[2] >= 1                  # a real move: cell, line, event
    assert again == third == (0, 0, 0)
    assert other[:2] == (1, 1) and other[2] >= 1
    stored = db.execute(text('SELECT t FROM "%s"' % LEFT)).scalar()
    assert stored == datetime(2026, 9, 28, 0, 30, tzinfo=timezone.utc)


def _spelling(db, kind):
    zone = ZoneInfo(db.execute(text("SHOW TimeZone")).scalar())
    return {"utc": "2026-09-29T01:00:00Z",
            "naive_in_session_zone": INSTANT.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S"),
            "another_instant": "2026-09-29T02:00:00Z"}[kind]


@pytest.mark.pg
@pytest.mark.parametrize("kind, expected", [
    ("utc", (0, 0, 0)), ("naive_in_session_zone", (0, 0, 0)), ("another_instant", (1, 1, 1))])
def test_a_file_resending_the_same_instant_writes_nothing(db, kind, expected):
    _apply(db, LEFT, _file([{"k": "L1", "job": "J1", "t": "2026-09-29T10:00:00+09:00"}]))
    assert _apply(db, LEFT, _file([{"k": "L1", "job": "J1", "t": _spelling(db, kind)}])) == expected


def _blank_the_stored(db, key):
    """A cell stored as '' - what rows written before the write door folded blanks hold."""
    db.execute(text('UPDATE "%s" SET job = \'\' WHERE k = :k' % LEFT), {"k": key})
    db.commit()


@pytest.mark.pg
def test_a_stored_blank_under_an_empty_winner_is_not_rewritten(db):
    """판정 284: '' is absence. A cell stored '' whose winning layer is None is the same value."""
    _apply(db, LEFT, _file([{"k": "E", "job": "J"}]))
    _blank_the_stored(db, "E")
    emptied = schemas.GeneralUpdateItem(updates={"k": "E", "job": None},
                                        source_name=crud.CHAIN_SOURCE, updated_by="t")
    assert _apply(db, LEFT, [emptied]) == (0, 0, 0)
    assert db.execute(text('SELECT job FROM "%s"' % LEFT)).scalar() == ""


@pytest.mark.pg
def test_r3_counts_neither_a_respelled_instant_nor_a_stored_blank(db):
    """A newer layer saying the table's instant in another spelling, or an empty winner over a
    stored '', is not a change; a newer layer holding another instant is."""
    from chain import replay
    _apply(db, LEFT, _file([{"k": "S", "job": "J", "t": "2026-09-29 10:00:00+09:00"},
                            {"k": "D", "job": "J", "t": "2026-09-29 10:00:00+09:00"},
                            {"k": "E", "job": "J"}]))
    _blank_the_stored(db, "E")
    ids = dict(db.execute(text('SELECT k, row_id FROM "%s"' % LEFT)).all())
    late = datetime.now(timezone.utc) + timedelta(minutes=1)
    for key, column, source, value in (
            ("S", "t", "late.csv", "2026-09-29T01:00:00Z"),
            ("D", "t", "late.csv", "2026-09-29T02:00:00Z"),
            ("E", "job", crud.CHAIN_SOURCE, None)):
        db.add(models.CellSource(table_name=LEFT, row_id=ids[key], column_name=column,
                                 source_name=source, value=value, ingested_at=late,
                                 updated_by="t"))
    db.commit()

    stats = replay.recompute_display_values(db, LEFT, columns=["t", "job"], log=lambda *a: None)

    assert [(c["business_key_val"], c["column"]) for c in stats["changes"]] == [("D", "t")]
