"""`derive.ask` for step mapping (lead 10-27 A-2): a product's steps asked a window at a time with context lines, the
measured items under their step, an answer reused across products by the declared key unless its structure is not
this product's, and one changed step asking its window alone. Step numbers carry the product's two-character prefix
on both tables (owner 10-28), so an item matches its step as written and only the reuse key drops the prefix. Names are
the declaration's; the model is a stand-in that answers every line it is given."""
import re

import pytest

from chain import ask_rule, rule_shape
from database import crud, models
from conftest import retire_dynamic_model

TABLES = {
    "st_steps": {"composite_key_source": ["product", "step_seq"], "column_types": {
        "product": "string", "step_seq": "string", "step_desc": "string"}},
    "st_items": {"composite_key_source": ["step", "item_id"], "column_types": {"step": "string", "item_id": "string"}},
    "st_struct": {"composite_key_source": ["product", "structure"], "column_types": {
        "product": "string", "structure": "string"}},
    "st_common": {"composite_key_source": ["name"], "column_types": {"name": "string"}},
    "st_map": {"composite_key_source": ["product", "step_seq", "item_id"], "column_types": {
        "product": "string", "step_seq": "string", "item_id": "string", "process_kind": "string",
        "acts_on": "string", "item_desc": "string"}},
}
PREFIX = {"P1": "AA", "P2": "BB", "P3": "CC"}
DECLARATION = {
    "name": "step_mapping", "on": {"table": "st_steps"}, "into": {"table": "st_map"},
    "derive": {"kind": "ask", "ask": {
        "input": {"group_by": ["product"], "order_by": "step_seq", "text": ["step_desc"], "window": 3, "overlap": 1},
        "output": {"carry": {"product": "product"}, "line": "step_seq", "item": "item_id",
                   "cells": ["process_kind", "acts_on", "item_desc"]},
        "items": {"table": "st_items", "step": {"column": "step"}, "item": "item_id"},
        "reuse": {"key": [{"column": "step_seq", "drop_leading": 2}, {"column": "step_desc"}],
                  "within": {"cell": "acts_on", "table": "st_struct", "column": "structure",
                             "carry": {"product": "product"}}},
        "common": {"cell": "process_kind", "table": "st_common", "column": "name", "none": "no common"}}}}
RULE = rule_shape.as_chain_rule(rule_shape.from_declaration(DECLARATION))


def fake(prompt, **_kw):
    """Every line asked gets a row; an item line a row of its item; a context line too - the body must drop it."""
    texts = []
    for ident, body in re.findall(r"^\[(.+)\]\n((?:(?!^\[).*\n?)*)", prompt, re.M):
        rows, step = [], None
        for line in body.splitlines():
            if line.startswith("  item "):
                rows.append({"step_seq": step, "item_id": line.split()[-1], "process_kind": "measure",
                             "acts_on": "M1", "item_desc": "thickness"})
            elif line.strip():
                step = line.split(" | ")[0]
                rows.append({"step_seq": step, "item_id": None, "process_kind": "etch", "acts_on": "M1",
                             "item_desc": None})
        texts.append({"id": ident, "rows": rows})
    return {"texts": texts}


@pytest.fixture
def world(db_session, monkeypatch):
    models.init_dynamic_models(TABLES)
    m = models.DYNAMIC_TABLES
    for name, entry in TABLES.items():
        crud.TABLE_CONFIG[name] = entry
        m[name].__table__.create(bind=db_session.get_bind())
    for product, prefix in PREFIX.items():
        for n in range(1, 7):
            db_session.add(m["st_steps"](row_id="%s-%d" % (product, n), product=product,
                                          step_seq="%s%03d" % (prefix, n), step_desc="step %d" % n))
    for product, structure in (("P1", "M1"), ("P2", "M1"), ("P3", "X")):
        db_session.add(m["st_struct"](row_id="s-%s" % product, product=product, structure=structure))
    db_session.add(m["st_items"](row_id="i1", step="AA003", item_id="T1"))
    db_session.add(m["st_items"](row_id="i2", step="BB003", item_id="T9"))
    db_session.add(m["st_common"](row_id="c1", name="etch"))
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


def _written(answer):
    return sorted([(u["updates"]["product"], u["updates"]["step_seq"], u["updates"].get("item_id"),
                    u["updates"].get("process_kind")) for u in answer["updates"] if not u.get("gone")],
                  key=lambda r: tuple("" if v is None else v for v in r))


def _store(db, answer):
    m = models.DYNAMIC_TABLES["st_map"]
    for n, u in enumerate(u for u in answer["updates"] if not u.get("gone")):
        row = u["updates"]
        db.add(m(row_id="w%d-%s" % (n, row["product"]), business_key_val=ask_rule._key_of("st_map", row),
                 **{k: v for k, v in row.items()}))
    db.commit()


def _p(product, n):
    return ["%s-%d" % (product, k) for k in n]


def test_a_product_is_asked_a_window_at_a_time_and_its_items_ride_their_step(world):
    db, calls = world
    answer = ask_rule.answer(db, RULE, _p("P1", range(1, 7)))
    assert answer["calls"] == len(calls) == 2, "six steps, windows of three"
    assert "AA004 | step 4  (context only" in calls[0] and calls[0].count("AA004 | step 4") == 1, \
        "the next window's first line rides the first window as context only"
    assert "  item T1" in calls[0] and "T9" not in calls[0], "AA003's item, not another product's BB003"
    rows = _written(answer)
    assert [r[1] for r in rows if r[2] is None] == ["AA%03d" % n for n in range(1, 7)], "each step once"
    assert ("P1", "AA003", "T1", "no common") in rows, "an item row; «measure» is not a common name"
    carried = [u for u in answer["updates"] if not u.get("gone")]
    assert all("item_id" in u["updates"] for u in carried), "a key column rides the row though blank (the key gate)"


def test_another_product_takes_the_answers_of_the_same_place_and_asks_only_for_its_own_items(world):
    db, calls = world
    _store(db, ask_rule.answer(db, RULE, _p("P1", range(1, 7))))
    calls.clear()
    answer = ask_rule.answer(db, RULE, _p("P2", range(1, 7)))
    assert answer["calls"] == len(calls) == 1, "BB001-006 are AA001-006's place; BB003 holds T9 P1 never answered"
    rows = _written(answer)
    assert [r[1] for r in rows if r[2] is None] == ["BB%03d" % n for n in range(1, 7)]
    assert ("P2", "BB003", "T9", "no common") in rows and not any(r[2] == "T1" for r in rows)


def test_an_answer_whose_structure_is_not_this_products_is_asked_again(world):
    db, calls = world
    _store(db, ask_rule.answer(db, RULE, _p("P1", range(1, 7))))
    calls.clear()
    answer = ask_rule.answer(db, RULE, _p("P3", range(1, 7)))
    assert answer["calls"] == len(calls) == 2, "P1's M1 is not P3's structure - P3 is asked"


def test_one_changed_step_asks_its_window_and_speaks_only_for_its_lines(world):
    db, calls = world
    _store(db, ask_rule.answer(db, RULE, _p("P1", range(1, 7))))
    m = models.DYNAMIC_TABLES["st_map"]
    stale = {"product": "P1", "step_seq": "AA005", "item_id": "OLD"}
    db.add(m(row_id="stale", business_key_val=ask_rule._key_of("st_map", stale), **stale))
    db.commit()
    calls.clear()
    no_reuse = dict(RULE, params=dict(RULE["params"], reuse=None))
    answer = ask_rule.answer(db, no_reuse, _p("P1", [5]))
    assert answer["calls"] == len(calls) == 1
    assert {r[1] for r in _written(answer)} == {"AA004", "AA005", "AA006"}
    gone = [u["business_key_val"] for u in answer["updates"] if u.get("gone")]
    assert gone == [ask_rule._key_of("st_map", stale)], "the window's stale row only - AA001-AA003 untouched"
