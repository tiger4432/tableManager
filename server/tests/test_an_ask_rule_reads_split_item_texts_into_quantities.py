"""Split template step 2 (owner 10-27, e88e6d882 #2; lead 10-28 ㄴ): every distinct free-text item of the expanded split
rows asked once - which quantity is it - its answer one row of an «item text -> quantity» table. The choices are a
table's column shown with another column of it (`common.about`); an answer outside them is the `none` word. Names are
the declaration's; the model is a stand-in."""
import json
import re

import pytest

from chain import ask_rule, rule_shape
from database import crud, models
from conftest import retire_dynamic_model

TABLES = {
    "sp_rows": {"composite_key_source": ["lot", "split", "item_text"], "column_types": {
        "lot": "string", "split": "string", "item_text": "string"}},
    "sp_quantities": {"composite_key_source": ["item_id"], "column_types": {"item_id": "string", "item_desc": "string"}},
    "sp_item_map": {"composite_key_source": ["item_text"], "column_types": {"item_text": "string", "quantity": "string"}},
}
DECLARATION = {
    "name": "split_item_quantity", "on": {"table": "sp_rows"}, "into": {"table": "sp_item_map"},
    "derive": {"kind": "ask", "ask": {
        "input": {"group_by": ["item_text"], "order_by": "split", "text": ["split"]},
        "output": {"carry": {"item_text": "item_text"}, "cells": ["quantity"]},
        "common": {"cell": "quantity", "table": "sp_quantities", "column": "item_id", "about": "item_desc",
                   "none": "not found"},
        "prompts": {"common": "Which measured quantity does this split item mean?"}}}}
RULE = rule_shape.as_chain_rule(rule_shape.from_declaration(DECLARATION))
TEXTS = ("M2 두께", "via CD bottom", "아무거나")


def fake(prompt, **_kw):
    """thickness -> PA40-THK, CD -> a value outside the list, anything else -> the none word."""
    texts = []
    for ident in re.findall(r"^\[(.+)\]$", prompt, re.M):
        text = json.loads(ident)[0]
        answer = "PA40-THK" if "두께" in text else "PA60-NOPE" if "CD" in text else "not found"
        texts.append({"id": ident, "rows": [{"quantity": answer}]})
    return {"texts": texts}


@pytest.fixture
def world(db_session, monkeypatch):
    models.init_dynamic_models(TABLES)
    m = models.DYNAMIC_TABLES
    for name, entry in TABLES.items():
        crud.TABLE_CONFIG[name] = entry
        m[name].__table__.create(bind=db_session.get_bind())
    for lot in ("L1", "L2"):
        for n, text in enumerate(TEXTS):
            db_session.add(m["sp_rows"](row_id="%s-%d" % (lot, n), lot=lot, split="base" if n else "leg",
                                        item_text=text))
    db_session.add(m["sp_quantities"](row_id="q1", item_id="PA40-THK", item_desc="M2 thickness"))
    db_session.add(m["sp_quantities"](row_id="q2", item_id="PA60-CD", item_desc="via critical dimension"))
    db_session.commit()
    calls = []

    def counted(prompt, **kw):
        calls.append(prompt)
        return fake(prompt, **kw)

    from utils import llm
    monkeypatch.setattr(llm, "ask_json", counted)
    monkeypatch.setattr(llm, "settings", lambda: {"batch_chars": 1})        # each text its own request
    yield db_session, calls
    db_session.rollback()
    for name in TABLES:
        m[name].__table__.drop(bind=db_session.get_bind())
        retire_dynamic_model(name)


def _rows(answer):
    return sorted((u["updates"]["item_text"], u["updates"]["quantity"]) for u in answer["updates"] if not u.get("gone"))


def test_each_distinct_item_text_is_asked_once_and_its_choices_say_what_they_are(world):
    db, calls = world
    answer = ask_rule.answer(db, RULE, ["%s-%d" % (lot, n) for lot in ("L1", "L2") for n in range(3)])
    asked = [ident for prompt in calls for ident in re.findall(r"^\[(.+)\]$", prompt, re.M)]
    assert sorted(json.loads(i)[0] for i in asked) == sorted(TEXTS), "six rows, three texts, each once"
    assert '"PA40-THK (M2 thickness)"' in calls[0] and '"PA60-CD (via critical dimension)"' in calls[0]
    assert _rows(answer) == [("M2 두께", "PA40-THK"), ("via CD bottom", "not found"), ("아무거나", "not found")], \
        "an answer outside the list is the none word"


def test_one_changed_row_asks_its_text_alone(world):
    db, calls = world
    answer = ask_rule.answer(db, RULE, ["L2-1"])
    asked = [json.loads(i)[0] for prompt in calls for i in re.findall(r"^\[(.+)\]$", prompt, re.M)]
    assert asked == ["via CD bottom"] and len(_rows(answer)) == 1


def test_the_prompt_grows_with_the_choices(world):
    """Lead 10-28: the ops quantity count is unknown - two points of the slope (box: this fixture's descriptions)."""
    db, calls = world
    m = models.DYNAMIC_TABLES["sp_quantities"]
    sizes = {}
    for total in (50, 500):
        have = db.query(m).count()
        for n in range(have, total):
            db.add(m(row_id="x%d" % n, item_id="PX%03d-ITEM" % n, item_desc="quantity number %d" % n))
        db.commit()
        calls.clear()
        ask_rule.answer(db, RULE, ["L1-2"])
        sizes[total] = len(calls[0])
    print("prompt chars: %d at 50 choices, %d at 500 (%.0f a choice)" % (
        sizes[50], sizes[500], (sizes[500] - sizes[50]) / 450.0))
    assert sizes[500] > sizes[50]
