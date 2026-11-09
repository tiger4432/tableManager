# -*- coding: utf-8 -*-
"""A same-row formula on a grid column (owner 10-28 «수식 그리드 바로 적기»): `=[a]+[b]*3` on column c of a table is a
chain rule - a join of the table onto itself on its own key, taking c from the formula (`chain.formula`). The grammar is
the shared calculator's (server/expression.py, lead: the whole of it); the formula reads the row's other columns, never
its own (owner «self 빼 — 재귀»).

    seat                                  gate
    formula.to_declaration / of_           a formula's rule and back: the same table, column and text
    the loader + the chain's batch body    c = the formula over its row; a changed operand changes c
    the calculator's answer                Round · If work; a text operand or a division by 0 answers blank
    take_refusal (save and load)           reads itself · a column the table lacks · a grammar error · a written from
"""
import asyncio
import json

import pytest

import event_constants
from chain import formula, rule_shape
from chain import ingestion_worker as worker
from database import crud, models, schemas
from database.context import channel, outbox_mode
from tests.test_a_join_take_can_gather_every_row_of_a_key import _NoClose, _no_post

T = "fx"
TABLES = {T: {"business_key": "k", "composite_key_source": ["k"],
              "column_types": {"k": "string", "a": "number", "b": "number", "c": "number", "t": "string"},
              "display_columns": ["k", "a", "b", "c", "t"]}}


@pytest.fixture(name="db")
def fixture_db(tmp_path, monkeypatch):
    import mapper_sdk
    import paths
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from database.database import Base
    from utils import heartbeat

    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path / "beats"))
    monkeypatch.setattr(heartbeat, "heartbeat_path", lambda name: str(tmp_path / "beats" / (name + ".json")))
    monkeypatch.setattr(worker, "post_event_async", _no_post)
    mapper_sdk.discover()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    monkeypatch.setattr("database.database.SessionLocal", lambda: _NoClose(session))
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _rules(tmp_path, monkeypatch, text, column="c"):
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [formula.to_declaration(T, column, text)]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    rules = [r for r in worker.load_chain_rules() if str(r.get("name") or "").startswith("formula ")]
    monkeypatch.setattr(worker, "loaded_chain_rules", lambda: list(rules))
    return rules


def _put(db, rows, who="user"):
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_PER_ROW):
        crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name=who, updated_by=who) for row in rows]))
        db.commit()


def _drain(db, rules):
    for _ in range(20):
        pending = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            return
        asyncio.run(worker.drain_events(db, pending, rules, None))
    raise AssertionError("the chain did not settle")


def _c(db):
    db.expire_all()
    return {row.k: row.c for row in db.query(models.DYNAMIC_TABLES[T]).order_by("k")}


def test_a_formula_is_a_join_onto_its_own_row_and_back():
    crud.TABLE_CONFIG.update(TABLES)
    try:
        declaration = formula.to_declaration(T, "c", "=[a]+[b]*3")
        assert declaration["name"] == "formula fx.c" and declaration["enabled"] is True
        assert declaration["on"] == declaration["into"] == {"table": T}
        assert declaration["derive"]["join"] == {"on": [{"left": "k", "right": "k"}],
                                                 "take": [{"into": "c", "fn": "=[a]+[b]*3"}]}
        assert formula.of_declaration(declaration) == (T, "c", "=[a]+[b]*3")
        assert formula.of_declaration(dict(declaration, name="mine")) is None, "another rule of that shape"
        stood, refusal, _notes = rule_shape.expand_declaration(declaration, crud.TABLE_CONFIG)
        assert refusal is None and [r.get("name") for r in stood] == ["formula fx.c"]
    finally:
        crud.TABLE_CONFIG.pop(T, None)


def test_the_column_is_the_formula_over_its_row_and_follows_its_operands(db, tmp_path, monkeypatch):
    rules = _rules(tmp_path, monkeypatch, "=[a]+[b]*3")
    assert [r.get("trigger_table") for r in rules] == [T], "one rule: on and into are the same table"
    _put(db, [{"k": "k1", "a": 1, "b": 2}, {"k": "k2", "a": 10, "b": 0}])
    _drain(db, rules)
    assert _c(db) == {"k1": 7, "k2": 10}
    _put(db, [{"k": "k1", "b": 5}])
    _drain(db, rules)
    assert _c(db) == {"k1": 16, "k2": 10}


def test_the_calculator_answers_its_functions_and_blank_where_it_cannot(db, tmp_path, monkeypatch):
    rules = _rules(tmp_path, monkeypatch, "=Round([a]/[b], 1)")
    _put(db, [{"k": "k1", "a": 10, "b": 3}, {"k": "k2", "a": 1, "b": 0}, {"k": "k3", "a": 1}])
    _drain(db, rules)
    assert _c(db) == {"k1": 3.3, "k2": None, "k3": None}, "a division by 0 and a blank operand answer blank"


def test_a_text_operand_answers_blank(db, tmp_path, monkeypatch):
    rules = _rules(tmp_path, monkeypatch, "=[t]*2", column="c")
    _put(db, [{"k": "k1", "t": "4"}, {"k": "k2", "t": "four"}])
    _drain(db, rules)
    assert _c(db) == {"k1": 8, "k2": None}


def test_the_formula_is_read_once_a_page_not_once_a_row(db, tmp_path, monkeypatch):
    """Owner 11-09 «수식 소급이 너무 오래»: C's board counted 50,663 compiles over 10,000 rows - the formula's text was
    read again a key. A group of 40 rows reads it as often as one of 4."""
    import expression

    rules = _rules(tmp_path, monkeypatch, "=[a]*2")
    real, read = expression.compile, []
    monkeypatch.setattr(expression, "compile", lambda text: read.append(text) or real(text))
    asked = []
    for rows in (4, 40):
        _put(db, [{"k": "k%d-%d" % (rows, i), "a": i} for i in range(rows)])
        before = len(read)
        _drain(db, rules)
        asked.append(len(read) - before)
    assert asked[0] == asked[1] and asked[0] > 0, asked
    assert _c(db) == {"k%d-%d" % (rows, i): i * 2 for rows in (4, 40) for i in range(rows)}


@pytest.mark.parametrize("take, said", [
    ({"into": "c", "fn": "=[c]+1"}, "take 'c' fn '=[c]+1' reads c itself - a formula reads the row's other columns"),
    ({"into": "c", "fn": "=[nope]+1"}, "take 'c' from 'nope' - not a column of fx"),
    ({"into": "c", "fn": "=[a]+"}, "take 'c' fn '=[a]+' - "),
    ({"into": "c", "fn": "=[a]+1", "from": "a"},
     "take 'c' from - a formula reads the columns it names, so from is not written"),
])
def test_a_formula_the_join_cannot_answer_is_refused_by_name(take, said):
    crud.TABLE_CONFIG.update(TABLES)
    try:
        declaration = formula.to_declaration(T, "c", "=[a]")
        declaration["derive"]["join"]["take"] = [take]
        stood, refusal, _notes = rule_shape.expand_declaration(declaration, crud.TABLE_CONFIG)
        assert stood == [] and refusal and said in refusal, refusal
    finally:
        crud.TABLE_CONFIG.pop(T, None)


def test_the_view_reads_the_tables_formulas_from_the_rules_file(db, tmp_path, monkeypatch):
    other = {"name": "formula fx.c-like", "on": {"table": T}, "into": {"table": T},
             "derive": {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}],
                                                 "take": [{"into": "b", "fn": "=[a]*2"}]}}}
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [formula.to_declaration(T, "c", "=[a]+[b]*3"), other]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    said = formula.view(T)
    assert said["formulas"] == [{"column": "c", "formula": "=[a]+[b]*3", "rule": "formula fx.c", "enabled": True}]
    assert said["base"] and formula.view("elsewhere")["formulas"] == []


def test_a_preview_answers_the_first_rows_and_says_what_saving_replaces(db, monkeypatch):
    monkeypatch.setattr(formula, "SAMPLE_ROWS", 2)
    _put(db, [{"k": "k1", "a": 1, "b": 2}, {"k": "k2", "a": 3}, {"k": "k3", "a": 5, "b": 1}])
    said = formula.preview(db, T, "c", "=[a]+[b]*3")
    assert said == {"rule": "formula fx.c", "says": formula.SAVING_REPLACES, "sample": [
        {"keys": {"k": "k1"}, "reads": {"a": 1, "b": 2}, "now": None, "becomes": 7},
        {"keys": {"k": "k2"}, "reads": {"a": 3, "b": None}, "now": None, "becomes": None}]}
    assert db.query(models.DYNAMIC_TABLES[T]).filter(models.DYNAMIC_TABLES[T].c.isnot(None)).count() == 0, \
        "a preview writes nothing"


@pytest.mark.parametrize("table, column, text, said", [
    ("nope", "c", "=[a]", "'nope' is not a table table_config declares"),
    (T, "z", "=[a]", "'z' is not a column of fx"),
    (T, "c", "[a]+1", "a formula starts with ="),
    (T, "c", "=[c]+1", "reads c itself - a formula reads the row's other columns"),
])
def test_a_preview_refuses_by_name(db, table, column, text, said):
    with pytest.raises(formula.FormulaRefused) as refused:
        formula.preview(db, table, column, text)
    assert said in str(refused.value)


def test_the_route_answers_a_preview_and_says_a_refusal_as_it_is(db):
    import main
    from fastapi import HTTPException

    _put(db, [{"k": "k1", "a": 1, "b": 2}, {"k": "k2", "a": 3, "b": 4}])
    said = main.post_chain_formula({"table": T, "column": "c", "formula": "=[a]", "preview": True}, db)
    assert len(said["sample"]) == 2
    assert said["count"]["total"] == 2 and said["count"]["counted_at"], "every row runs again - the grid's count"
    with pytest.raises(HTTPException) as refused:
        main.post_chain_formula({"table": T, "column": "z", "formula": "=[a]", "preview": True}, db)
    assert (refused.value.status_code, refused.value.detail) == (400, "'z' is not a column of fx")
    with pytest.raises(HTTPException) as closed:
        main.post_chain_formula({"table": T, "column": "c", "formula": "=[a]"}, db)
    assert closed.value.detail == "Send preview: true, or the base GET read to save"
