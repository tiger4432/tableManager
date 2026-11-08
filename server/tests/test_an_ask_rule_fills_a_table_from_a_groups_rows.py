"""`derive: {kind: "ask"}` (lead 10-27 A-1): a product's whole step sequence is one text, asked once, and the answer
becomes rows of the structure table. Every name below is the declaration's - the code holds none of them."""
import json
import re

import pytest

from chain import ask_rule, dynamic_mappers, rule_shape
from database import crud, models
from conftest import retire_dynamic_model

TABLES = {
    "ak_steps": {"composite_key_source": ["product", "step_seq"], "column_types": {
        "product": "string", "step_seq": "string", "step_desc": "string"}},
    "ak_structure": {"composite_key_source": ["product", "structure"], "column_types": {
        "product": "string", "structure": "string", "parent": "string", "kind": "string"}},
    "ak_common": {"composite_key_source": ["name"], "column_types": {"name": "string"}},
}
DECLARATION = {
    "name": "structure_of_product", "on": {"table": "ak_steps"}, "into": {"table": "ak_structure"},
    "derive": {"kind": "ask", "ask": {
        "input": {"group_by": ["product"], "order_by": "step_seq", "text": ["step_desc"]},
        "output": {"carry": {"product": "product"}, "cells": ["structure", "parent", "kind"]},
        "common": {"cell": "kind", "table": "ak_common", "column": "name", "none": "no common"},
        "prompts": {"common": "Read the step sequence of one product."}}}}


@pytest.fixture
def world(db_session, monkeypatch):
    models.init_dynamic_models(TABLES)
    for name, entry in TABLES.items():
        crud.TABLE_CONFIG[name] = entry
        models.DYNAMIC_TABLES[name].__table__.create(bind=db_session.get_bind())
    m = models.DYNAMIC_TABLES
    for product in ("P1", "P2"):
        for n in range(6):
            db_session.add(m["ak_steps"](row_id="%s-%d" % (product, n), product=product, step_seq="%03d" % n,
                                          step_desc="step %d of %s" % (n, product)))
    db_session.add(m["ak_common"](row_id="c1", name="line"))
    db_session.commit()
    calls = []

    def fake(prompt, **_kw):
        calls.append(prompt)
        ids = re.findall(r"^\[(.+)\]$", prompt, re.M)
        return {"texts": [{"id": i, "rows": [{"structure": "M1", "parent": None, "kind": "line"},
                                             {"structure": "V1", "parent": "M1", "kind": "via"}]} for i in ids]}

    from utils import llm
    monkeypatch.setattr(llm, "ask_json", fake)
    monkeypatch.setattr(llm, "settings", lambda: {"batch_chars": 100})
    yield db_session, calls
    db_session.rollback()
    for name in TABLES:
        m[name].__table__.drop(bind=db_session.get_bind())
        retire_dynamic_model(name)


def test_the_declaration_lowers_to_the_reports_seat_with_its_own_body():
    rule = rule_shape.as_chain_rule(rule_shape.from_declaration(DECLARATION))
    assert rule["mapper"] == ask_rule.ASK_MAPPER and rule["is_batch"] is True
    assert rule["trigger_table"] == "ak_steps" and rule["target_table"] == "ak_structure"
    assert dynamic_mappers.TEMPLATES[ask_rule.ASK_MAPPER] is dynamic_mappers._ask


def test_a_product_is_one_call_and_its_rows_carry_the_product(world):
    db, calls = world
    rule = rule_shape.as_chain_rule(rule_shape.from_declaration(DECLARATION))
    answer = ask_rule.answer(db, rule, ["P1-0", "P2-3"])
    assert answer["calls"] == len(calls) == 2, "one product a request: batch_chars 100 holds one product's text"
    written = [u for u in answer["updates"] if not u.get("covers")]
    rows = sorted((u["updates"]["product"], u["updates"]["structure"], u["updates"].get("kind")) for u in written)
    assert rows == [("P1", "M1", "line"), ("P1", "V1", "no common"), ("P2", "M1", "line"), ("P2", "V1", "no common")]
    assert all("row_id" not in u for u in answer["updates"])
    whole = calls[0]
    assert all("step %d of P1" % n in whole for n in range(6)), "the whole sequence, not only the row handed"
    assert whole.index("step 0 of P1") < whole.index("step 5 of P1")
    assert '"line"' in whole and '"no common"' in whole


def test_a_refused_group_is_named_with_its_length(world, monkeypatch):
    db, _calls = world
    from utils import llm
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **_kw: (_ for _ in ()).throw(llm.LlmRefused("too long")))
    answer = ask_rule.answer(db, rule_shape.as_chain_rule(rule_shape.from_declaration(DECLARATION)), ["P1-0"])
    text = ask_rule._text(ask_rule._groups(db, "ak_steps", DECLARATION["derive"]["ask"], ["P1-0"])[("P1",)][0],
                          DECLARATION["derive"]["ask"])
    assert answer["updates"] == []
    assert answer["refusal"] == '["P1"] (%d chars): too long' % len(text)


def test_a_row_of_the_group_the_answer_no_longer_gives_is_handed_as_gone(world):
    """The write's gone seat takes it (this rule's cells; a person's row stays - the seat's own gate). Only the
    answered group's rows: P2's row is not P1's answer."""
    db, _calls = world
    m = models.DYNAMIC_TABLES["ak_structure"]
    for row_id, product, structure in (("s1", "P1", "M1"), ("s2", "P1", "OLD"), ("s3", "P2", "OLD")):
        db.add(m(row_id=row_id, product=product, structure=structure,
                 business_key_val=crud.compose_business_key("ak_structure", [product, structure], ["product", "structure"])))
    db.commit()
    answer = ask_rule.answer(db, rule_shape.as_chain_rule(rule_shape.from_declaration(DECLARATION)), ["P1-0"])
    # what the answer covers and no longer gives - its rule's cells there go, by the write's settle (owner 11-06 step 2)
    gone = [where["business_key_val"] for u in answer["updates"] if u.get("covers") for where in u["covers"]["where"]]
    assert gone == [crud.compose_business_key("ak_structure", ["P1", "OLD"], ["product", "structure"])]


def test_one_group_handed_twice_is_asked_once(world):
    db, calls = world
    ask_rule.answer(db, rule_shape.as_chain_rule(rule_shape.from_declaration(DECLARATION)), ["P1-0", "P1-1", "P1-5"])
    assert len(calls) == 1
