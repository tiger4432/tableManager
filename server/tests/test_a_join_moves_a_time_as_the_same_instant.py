# -*- coding: utf-8 -*-
"""총괄 791c0f45e 4 — 조인이 시각 칸 값을 옮기면 쓰기 전체가 TypeError 였다(0a7c46615 덤): 원천 표에서
읽은 파이썬 datetime 이 층(JSON)에 그대로 갔다. 쓰기 문의 경계(cast_value_by_type)가 그 값을 crud 의 JSON
변환(sanitize_to_utf8 — 시간대 꼬리 있는 ISO 글)으로 바꾼다. 층 · 표 · 다시 읽은 값이 같은 순간이다.
"""
import os
import sys
from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import retire_dynamic_model, run_join_and_write     # noqa: E402
from database.database import Base                                # noqa: E402
from database import crud, models, schemas                        # noqa: E402

LEFT, RIGHT = "join_dt_left", "join_dt_right"
TABLES = {
    LEFT: {"business_key": "k", "composite_key_source": ["k"],
           "column_types": {"k": "string", "job": "string", "t": "datetime"}},
    RIGHT: {"business_key": "rk", "composite_key_source": ["rk"],
            "column_types": {"rk": "string", "job": "string", "rt": "datetime"}},
}


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


def _write(db, table, cells):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(row), source_name="join_dt.csv", updated_by="t")
        for row in cells]))


def _rule(blank):
    from chain import rule_shape
    cells = {"on": [{"left": "job", "right": "job"}], "take": [{"from": "rt", "into": "t"}]}
    if blank:
        cells["blank"] = blank
    rule = rule_shape.as_chain_rule(rule_shape.from_declaration({
        "name": "join_dt", "on": {"table": RIGHT},
        "derive": {"kind": "join", "join": cells}, "into": {"table": LEFT}}))
    rule["trigger_table"] = RIGHT
    return rule


@pytest.mark.pg
@pytest.mark.parametrize("blank", [None, "skip"], ids=["blank_written", "blank_skip"])
def test_a_join_moves_a_time_and_every_copy_is_the_same_instant(db, blank):
    _write(db, RIGHT, [{"rk": "R1", "job": "J1", "rt": "2026-09-28T08:00:00+09:00"},
                       {"rk": "R2", "job": "J2"}])
    _write(db, LEFT, [{"k": "L1", "job": "J1", "t": "2026-09-29 10:00:00+09:00"},
                      {"k": "L2", "job": "J2", "t": "2026-09-29 10:00:00+09:00"}])
    source = db.execute(text('SELECT rt FROM "%s" WHERE rk = %s' % (RIGHT, "'R1'"))).scalar()
    right_ids = [r[0] for r in db.execute(text('SELECT row_id FROM "%s"' % RIGHT))]

    outcome = run_join_and_write(db, _rule(blank), right_ids)
    db.commit()
    table = dict(db.execute(text('SELECT k, t FROM "%s"' % LEFT)).all())
    layer = dict(db.execute(text(
        "SELECT r.k, s.value FROM cell_sources s JOIN \"%s\" r ON r.row_id = s.row_id "
        "WHERE s.table_name = :t AND s.column_name = 't' AND s.source_name = :c" % LEFT),
        {"t": LEFT, "c": crud.CHAIN_SOURCE}).all())

    assert outcome["written"] >= 1
    assert isinstance(layer["L1"], str)
    assert datetime.fromisoformat(layer["L1"]) == table["L1"] == source
    if blank == "skip":
        assert "L2" not in layer and table["L2"] is not None       # the file value stands
    else:
        assert layer["L2"] is None and table["L2"] is None         # the blank answer, written
