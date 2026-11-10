# -*- coding: utf-8 -*-
"""Lead 11-10 (owner «왜 뭐는 = 을 하고 뭐는 = 을 안 하고 · 조인은 = 하잖아»): «is this value a formula» is one function,
join_into.formula_text. Every seat that reads a formula answers the same table:

  seat                 «=식»         bare text                   a word
  join take fn         a formula     not one (a word of the list) not one
  formula column       taken         refused «starts with =»     refused
  aggregation          the formula   the formula (old)           "count" -> Count()

and the form skeleton marks the take's fn and the aggregation's expression with the same mark."""
import pytest

from chain import formula, join_into, rule_shape
from chain.enrichment import config

FORMULA = "UniqueCount([stack_height])"


@pytest.mark.parametrize("value, text", [("=" + FORMULA, FORMULA), (" = " + FORMULA + " ", " " + FORMULA),
                                         (FORMULA, None), ("unique_concat", None), (None, None)])
def test_the_one_answer(value, text):
    assert join_into.formula_text(value) == text


@pytest.mark.parametrize("value, is_formula", [("=" + FORMULA, True), (FORMULA, False), ("unique_concat", False)])
def test_a_join_take(value, is_formula):
    read = join_into.formula_of(value)
    assert (read is not None and read["ok"]) == is_formula


@pytest.mark.parametrize("value, refused", [("=" + FORMULA, False), (FORMULA, True), ("count", True)])
def test_a_formula_column(value, refused, monkeypatch):
    monkeypatch.setattr(formula, "_config", lambda table: {"column_types": {"c": "string", "stack_height": "string"}})
    try:
        formula._judge("t", "c", value)
        said = None
    except formula.FormulaRefused as exc:
        said = str(exc)
    # refused for its mark - a «=…» may still be refused later for another reason (this table is not loaded)
    assert (said is not None and "starts with =" in said) == refused, said


@pytest.mark.parametrize("value, expression", [("=" + FORMULA, FORMULA), (FORMULA, FORMULA), ("count", "Count()")])
def test_an_aggregation(value, expression):
    normalized, why = config._parse_aggregation("stack_height", value)
    assert why is None and normalized["expression"] == expression, why


def test_the_form_marks_both_formula_leaves_alike():
    take_fn = next(field["node"] for field in
                   join_into.JOIN_CELL_SHAPES["take"]["of"]["branches"]["record"]["fields"]
                   if field["key"] == join_into.TAKE_FN)
    aggregation = rule_shape.DECIDE_CELL_SHAPES["aggregations"]["of"]["branches"]["expression"]
    assert take_fn["mark"] == aggregation["mark"] == join_into.FORMULA_MARK
