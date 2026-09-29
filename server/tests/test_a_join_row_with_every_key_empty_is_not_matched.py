# -*- coding: utf-8 -*-
"""총괄 534f375f8 — 조인 키 칸이 «모두» 빈 행은 짝이 아니다. «일부»만 비면 지금 그대로.

소유자: 「키가 여러 컬럼이면 모든 칼럼 null이면 무시, 일부 null은 허용」.
두 반쪽(대상 쪽 :target · 값 쪽)이 같은 판정(`join_into._every_part_blank`)을 지난다.
"""
import logging
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import rule_shape                                       # noqa: E402
from conftest import run_join_and_write                            # noqa: E402
from database.database import Base                                 # noqa: E402
from database import crud, models, schemas                         # noqa: E402

LEFT = "s534_left_log"
RIGHT = "s534_right_values"

TABLES = {
    LEFT: {
        "business_key": "log_key",
        "composite_key_source": ["log_key"],
        "column_types": {"log_key": "string", "a": "string", "b": "string", "got": "string"},
        "display_columns": ["log_key", "a", "b", "got"],
    },
    RIGHT: {
        "business_key": "ref_key",
        "composite_key_source": ["ref_key"],
        "column_types": {"ref_key": "string", "a": "string", "b": "string", "val": "string"},
        "display_columns": ["ref_key", "a", "b", "val"],
    },
}


def _declaration(name, keys):
    return {"name": name, "on": {"table": RIGHT},
            "derive": {"kind": "join",
                       "join": {"on": [{"left": k, "right": k} for k in keys],
                                "take": [{"from": "val", "into": "got"}]}},
            "into": {"table": LEFT}}


ONE = _declaration("s534_one_key", ["a"])
TWO = _declaration("s534_two_keys", ["a", "b"])


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _push(db, table, rows):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(row), source_name="seed",
                                  updated_by="s534") for row in rows]))


def _rows(db, table):
    return db.query(models.DYNAMIC_TABLES[table]).all()


def _got(db):
    return {r.log_key: r.got for r in _rows(db, LEFT)}


def _run(db, declaration, side, row_ids):
    rule = rule_shape.as_chain_rule(rule_shape.from_declaration(declaration))
    rule["trigger_table"] = side
    return run_join_and_write(db, rule, row_ids)


def _said(caplog, name, count, side):
    line = "%s: %d row(s) with every join key empty - not matched (%s side)" % (name, count, side)
    return [r.getMessage() for r in caplog.records
            if r.name == "Chain.JoinInto" and "every join key empty" in r.getMessage()] == [line]


def test_one_key_a_target_row_whose_key_is_empty_seeks_no_answer(db, caplog):
    _push(db, RIGHT, [{"ref_key": "R1", "a": None, "val": "V"}])
    _push(db, LEFT, [{"log_key": "L_EMPTY", "a": "", "got": "KEEP"},
                     {"log_key": "L_FILLED", "a": "X", "got": "KEEP"}])
    with caplog.at_level(logging.INFO, logger="Chain.JoinInto"):
        result = _run(db, ONE, LEFT, [r.row_id for r in _rows(db, LEFT)])

    assert result["written"] == 0
    assert _got(db) == {"L_EMPTY": "KEEP", "L_FILLED": "KEEP"}
    assert _said(caplog, ONE["name"], 1, "target"), [r.getMessage() for r in caplog.records]


def test_one_key_a_value_row_whose_key_is_empty_answers_nobody(db, caplog):
    _push(db, RIGHT, [{"ref_key": "R_EMPTY", "a": "", "val": "V"}])
    _push(db, LEFT, [{"log_key": "L_EMPTY", "a": None, "got": "KEEP"},
                     {"log_key": "L_FILLED", "a": "X", "got": "KEEP"}])
    with caplog.at_level(logging.INFO, logger="Chain.JoinInto"):
        result = _run(db, ONE, RIGHT, [r.row_id for r in _rows(db, RIGHT)])

    assert result["written"] == 0
    assert _got(db) == {"L_EMPTY": "KEEP", "L_FILLED": "KEEP"}
    assert _said(caplog, ONE["name"], 1, "value"), [r.getMessage() for r in caplog.records]


def test_two_keys_one_empty_part_still_matches_empty_to_empty(db, caplog):
    _push(db, RIGHT, [{"ref_key": "R1", "a": "X", "b": None, "val": "V"}])
    _push(db, LEFT, [{"log_key": "L1", "a": "X", "b": ""}])
    with caplog.at_level(logging.INFO, logger="Chain.JoinInto"):
        result = _run(db, TWO, LEFT, [r.row_id for r in _rows(db, LEFT)])

    assert result["written"] == 1
    assert _got(db) == {"L1": "V"}
    assert not [r for r in caplog.records if "every join key empty" in r.getMessage()]


@pytest.mark.parametrize("side", [LEFT, RIGHT])
def test_two_keys_every_part_empty_matches_nothing_from_either_side(db, caplog, side):
    """Two value rows share the empty key: they are not a fan-out any more - not answers."""
    _push(db, RIGHT, [{"ref_key": "R_EMPTY_1", "a": "", "b": None, "val": "V1"},
                      {"ref_key": "R_EMPTY_2", "a": None, "b": None, "val": "V2"},
                      {"ref_key": "R_FILLED", "a": "X", "b": "Y", "val": "V3"}])
    _push(db, LEFT, [{"log_key": "L_EMPTY", "a": "", "b": "", "got": "KEEP"},
                     {"log_key": "L_FILLED", "a": "X", "b": "Y"}])
    table = LEFT if side == LEFT else RIGHT
    with caplog.at_level(logging.INFO, logger="Chain.JoinInto"):
        result = _run(db, TWO, side, [r.row_id for r in _rows(db, table)])

    assert result["written"] == 1
    assert _got(db) == {"L_EMPTY": "KEEP", "L_FILLED": "V3"}
    assert _said(caplog, TWO["name"], 1 if side == LEFT else 2,
                 "target" if side == LEFT else "value"), [r.getMessage() for r in caplog.records]
    assert not [r for r in caplog.records
                if r.name == "Chain.JoinInto" and r.levelno >= logging.WARNING], (
        "the empty-key value rows are not answers, so they are not a fan-out")
