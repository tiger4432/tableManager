"""`derive.ask` memory (lead 10-27 A-3): its memory half writes a row for each AI cell a person corrected, keyed by the
situation (the output row's key) and the cell; a correction put back goes; the prompt carries the
newest `limit` corrections of the same `scope`. Names are the declaration's; the layers are written as the product
writes them (person = `user`, the rule = `chain_ingestion` by the declaration)."""
import json

import pytest

from chain import ask_rule, rule_shape
from database import crud, models
from conftest import retire_dynamic_model

TABLES = {
    "am_steps": {"composite_key_source": ["product", "step_seq"], "column_types": {
        "product": "string", "step_seq": "string", "step_desc": "string"}},
    "am_map": {"composite_key_source": ["product", "step_seq"], "column_types": {
        "product": "string", "step_seq": "string", "process_kind": "string"}},
    "am_memory": {"composite_key_source": ["purpose", "situation", "cell"], "column_types": {
        "purpose": "string", "situation": "string", "cell": "string", "ai": "string", "right": "string",
        "memo": "string", "who": "string", "at": "string"}},
}
DECLARATION = {
    "name": "step_kind", "on": {"table": "am_steps"}, "into": {"table": "am_map"},
    "derive": {"kind": "ask", "ask": {
        "input": {"group_by": ["product"], "order_by": "step_seq", "text": ["step_desc"]},
        "output": {"carry": {"product": "product"}, "line": "step_seq", "cells": ["process_kind"]},
        "prompts": {"memory": {"scope": ["product"], "limit": 2}},
        "memory": {"table": "am_memory", "columns": {
            "purpose": "purpose", "key": "situation", "cell": "cell", "ai": "ai", "right": "right", "memo": "memo",
            "who": "who", "when": "at"}}}}}
INTERNAL = rule_shape.from_declaration(DECLARATION)
RULE = rule_shape.as_chain_rule(INTERNAL)


@pytest.fixture
def world(db_session):
    models.init_dynamic_models(TABLES)
    m = models.DYNAMIC_TABLES
    for name, entry in TABLES.items():
        crud.TABLE_CONFIG[name] = entry
        m[name].__table__.create(bind=db_session.get_bind())
    for product in ("P1", "P2"):
        for n in (1, 2, 3):
            row = {"product": product, "step_seq": "%s%d" % (product, n), "process_kind": "etch"}
            db_session.add(m["am_map"](row_id="%s-%d" % (product, n), business_key_val=ask_rule._key_of("am_map", row),
                                       **row))
            db_session.add(models.CellSource(table_name="am_map", row_id="%s-%d" % (product, n),
                                             column_name="process_kind", source_name=crud.CHAIN_SOURCE,
                                             value="etch", updated_by="step_kind"))
    db_session.commit()
    yield db_session
    db_session.rollback()
    db_session.query(models.CellSource).filter(models.CellSource.table_name == "am_map").delete()
    db_session.commit()
    for name in TABLES:
        m[name].__table__.drop(bind=db_session.get_bind())
        retire_dynamic_model(name)


def _person(db, row_id, value, at="2026-10-28 09:00"):
    db.add(models.CellSource(table_name="am_map", row_id=row_id, column_name="process_kind",
                             source_name=crud.USER_SOURCE, value=value, updated_by="kim"))
    db.commit()


def _half():
    (half,) = rule_shape.companion_rules(INTERNAL)
    return half


def test_the_declaration_stands_a_memory_half_on_the_output_table():
    half = _half()
    assert (half["trigger_table"], half["target_table"]) == ("am_map", "am_memory")
    assert rule_shape.declaration_of(half) == "step_kind" and half["name"] != "step_kind"
    assert ask_rule.written_columns(half) == ["purpose", "situation", "cell", "ai", "right", "who", "at"], "not memo"


def test_a_corrected_cell_is_remembered_and_an_agreeing_one_is_not(world):
    _person(world, "P1-2", "deposit")
    _person(world, "P1-3", "etch")                       # the person wrote the AI's own answer - nothing to learn
    answer = ask_rule.answer(world, _half(), ["P1-1", "P1-2", "P1-3"])
    rows = [u["updates"] for u in answer["updates"] if not u.get("covers")]
    assert [(json.loads(r["situation"]), r["cell"], r["ai"], r["right"], r["who"]) for r in rows] == [
        ({"product": "P1", "step_seq": "P12"}, "process_kind", "etch", "deposit", "kim")]
    assert answer["calls"] == 0 and not [u for u in answer["updates"] if u.get("covers")]


def test_a_correction_put_back_takes_its_memory_row_away(world):
    m = models.DYNAMIC_TABLES["am_memory"]
    held = {"purpose": "step_kind", "situation": json.dumps({"product": "P1", "step_seq": "P12"}, sort_keys=True),
            "cell": "process_kind"}
    other = dict(held, situation=json.dumps({"product": "P2", "step_seq": "P22"}, sort_keys=True))
    for n, row in enumerate((held, other)):
        world.add(m(row_id="mem%d" % n, business_key_val=ask_rule._key_of("am_memory", row), **row))
    world.commit()
    answer = ask_rule.answer(world, _half(), ["P1-2"])    # no person layer on P1-2 any more
    assert [where["business_key_val"] for u in answer["updates"] if u.get("covers") for where in u["covers"]["where"]] == [
        ask_rule._key_of("am_memory", held)], "only the handed row's situation - P2's memory untouched"


def test_the_prompt_carries_this_scopes_newest_corrections_up_to_the_limit(world):
    m = models.DYNAMIC_TABLES["am_memory"]
    for n, (product, at) in enumerate((("P1", "2026-10-01"), ("P1", "2026-10-03"), ("P1", "2026-10-02"),
                                       ("P2", "2026-10-09"))):
        row = {"purpose": "step_kind", "situation": json.dumps({"product": product, "step_seq": "s%d" % n}),
               "cell": "process_kind", "ai": "etch", "right": "fix%d" % n, "at": at}
        world.add(m(row_id="mem%d" % n, business_key_val=ask_rule._key_of("am_memory", row), **row))
    world.commit()
    spec, request = RULE["params"], [(json.dumps(["P1"]), "P11 | step 1")]
    bare = ask_rule.prompt(world, spec, request, "")
    told = ask_rule.prompt(world, spec, request, "", "step_kind")
    assert ask_rule.MEMORY_HEADING not in bare and ask_rule.MEMORY_HEADING in told
    assert [w for w in ("fix0", "fix1", "fix2", "fix3") if w in told] == ["fix1", "fix2"], "newest two of P1's"
    assert told.index("fix1") < told.index("fix2")
    print("memory lines: limit 2 adds %d chars to a %d char prompt" % (len(told) - len(bare), len(bare)))


def test_a_report_declares_the_same_memory_and_its_prompt_carries_the_lines():
    from chain import report_loop, report_shape

    fields = {f["key"]: f for f in report_shape.skeleton_node()["fields"]}
    asked = {f["key"]: f for f in ask_rule.skeleton_node()["fields"]}
    # the same form, a report's with its reviewer comment column too (owner 10-29)
    assert asked["memory"] == ask_rule.memory_nodes()[0] and "memory" in report_shape.REPORT_CELLS
    assert fields["memory"] == ask_rule.memory_nodes(comment=True)[0]
    assert [f for f in fields["memory"]["node"]["fields"] if f["key"] != ask_rule.MEMORY_COMMENT] == \
        asked["memory"]["node"]["fields"]
    prompts = {f["key"]: f for f in fields["prompts"]["node"]["fields"]}
    assert prompts["memory"] == {f["key"]: f for f in asked["prompts"]["node"]["fields"]}["memory"]
    said = report_loop._request({"evaluation": "e", "memory": ask_rule.MEMORY_HEADING + "\n- x"})
    assert said[-1].startswith(ask_rule.MEMORY_HEADING)
    assert not [s for s in report_loop._request({"evaluation": "e", "memory": ""}) if ask_rule.MEMORY_HEADING in s]
