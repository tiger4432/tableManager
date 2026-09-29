# -*- coding: utf-8 -*-
"""총괄 14c75ff43 — 조인 선언 한 칸 `derive.join.blank = "skip"` (소유자 09-29 ㄱ).

적은 조인은 짝이 된 값 행의 «빈» take 값을 쓰지 않는다 — 층을 안 만들어 파일 값이 선다.
값이 있는 take 는 지금처럼 덮는다. 안 적은 조인은 판정 f3c04dee 그대로(빈 답 = 빈 값을 씀).
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

import chain_bindings                                              # noqa: E402
from chain import join_into, rule_shape                            # noqa: E402
from conftest import run_join_and_write                            # noqa: E402
from database.database import Base                                 # noqa: E402
from database import crud, models, schemas                         # noqa: E402

LEFT = "s14c_left_log"
RIGHT = "s14c_right_values"

TABLES = {
    LEFT: {
        "business_key": "log_key",
        "composite_key_source": ["log_key"],
        "column_types": {"log_key": "string", "job": "string", "got": "string",
                         "got2": "string"},
        "display_columns": ["log_key", "job", "got", "got2"],
    },
    RIGHT: {
        "business_key": "ref_key",
        "composite_key_source": ["ref_key"],
        "column_types": {"ref_key": "string", "job": "string", "val": "string",
                         "val2": "string"},
        "display_columns": ["ref_key", "job", "val", "val2"],
    },
}

NAME = "s14c_blank_skip"


def _declaration(**join):
    cells = {"on": [{"left": "job", "right": "job"}],
             "take": [{"from": "val", "into": "got"}, {"from": "val2", "into": "got2"}]}
    cells.update(join)
    return {"name": NAME, "on": {"table": RIGHT},
            "derive": {"kind": "join", "join": cells}, "into": {"table": LEFT}}


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
                                  updated_by="s14c") for row in rows]))


def _rows(db, table):
    return db.query(models.DYNAMIC_TABLES[table]).all()


def _left(db):
    return {r.log_key: (r.got, r.got2) for r in _rows(db, LEFT)}


def _chain_layers(db, column):
    return db.query(models.CellSource).filter_by(
        table_name=LEFT, column_name=column, source_name=join_into.CHAIN_LAYER).count()


def _run(db, declaration, side):
    rule = rule_shape.as_chain_rule(rule_shape.from_declaration(declaration))
    rule["trigger_table"] = side
    table = LEFT if side == LEFT else RIGHT
    return run_join_and_write(db, rule, [r.row_id for r in _rows(db, table)])


def _lines(caplog):
    return [r.getMessage() for r in caplog.records
            if r.name == "Chain.JoinInto" and "blank answer" in r.getMessage()]


SIDES = pytest.mark.parametrize("side", [LEFT, RIGHT], ids=["target", "value"])


@SIDES
def test_a_blank_answer_is_not_written_and_the_file_value_stands(db, caplog, side):
    _push(db, RIGHT, [{"ref_key": "R1", "job": "J1", "val": None, "val2": ""}])
    _push(db, LEFT, [{"log_key": "L1", "job": "J1", "got": "FILE", "got2": "FILE2"}])
    with caplog.at_level(logging.INFO, logger="Chain.JoinInto"):
        result = _run(db, _declaration(blank="skip"), side)

    assert _left(db) == {"L1": ("FILE", "FILE2")}
    assert _chain_layers(db, "got") == 0 and _chain_layers(db, "got2") == 0, "no layer"
    assert result["written"] == 0 and result["rows_total"] == 0
    assert result["refusal"].startswith("matched 1 row(s) and wrote nothing - 2 blank")
    assert _lines(caplog) == [
        "%s: 2 blank answer(s) not written (blank: skip) - got=1, got2=1" % NAME]


@SIDES
def test_a_filled_answer_still_overwrites_and_a_blank_one_beside_it_does_not(db, caplog, side):
    _push(db, RIGHT, [{"ref_key": "R1", "job": "J1", "val": None, "val2": "JOIN2"}])
    _push(db, LEFT, [{"log_key": "L1", "job": "J1", "got": "FILE", "got2": "FILE2"}])
    with caplog.at_level(logging.INFO, logger="Chain.JoinInto"):
        result = _run(db, _declaration(blank="skip"), side)

    assert _left(db) == {"L1": ("FILE", "JOIN2")}
    assert _chain_layers(db, "got") == 0 and _chain_layers(db, "got2") == 1
    assert result["written"] == 1 and result["rows_total"] == 1
    assert _lines(caplog) == ["%s: 1 blank answer(s) not written (blank: skip) - got=1" % NAME]


def test_no_file_value_and_a_blank_answer_stays_empty(db):
    _push(db, RIGHT, [{"ref_key": "R1", "job": "J1", "val": None, "val2": None}])
    _push(db, LEFT, [{"log_key": "L1", "job": "J1"}])
    result = _run(db, _declaration(blank="skip"), LEFT)

    assert _left(db) == {"L1": (None, None)}
    assert _chain_layers(db, "got") == 0 and result["written"] == 0


@SIDES
def test_without_the_cell_a_blank_answer_is_written_as_empty(db, caplog, side):
    """판정 f3c04dee, unchanged for a join that does not declare the cell."""
    _push(db, RIGHT, [{"ref_key": "R1", "job": "J1", "val": None, "val2": "JOIN2"}])
    _push(db, LEFT, [{"log_key": "L1", "job": "J1", "got": "FILE", "got2": "FILE2"}])
    with caplog.at_level(logging.INFO, logger="Chain.JoinInto"):
        result = _run(db, _declaration(), side)

    assert _left(db) == {"L1": (None, "JOIN2")}
    assert _chain_layers(db, "got") == 1
    assert result["written"] == 1 and _lines(caplog) == []


def test_a_word_other_than_skip_is_refused_by_name_and_an_empty_cell_is_absent():
    stood, refusal, _notes = rule_shape.expand_declaration(_declaration(blank="yes"))
    assert stood == [] and refusal == "%s: derive.join.blank 'yes' - one of skip" % NAME

    for said in ("skip", "", None):
        stood, refusal, notes = rule_shape.expand_declaration(_declaration(blank=said))
        assert refusal is None and len(stood) == 2, said
        assert not [n for n in notes if "blank" in n], notes
        assert {r["params"].get("blank") for r in stood} == {said}


def test_the_declaration_form_draws_the_cell():
    root = chain_bindings.skeleton()["unified_root"]
    derive = next(f["node"] for f in root["fields"] if f["key"] == "derive")
    join = derive["branches"]["join"]
    assert "blank" in [f["key"] for f in join["fields"]]
