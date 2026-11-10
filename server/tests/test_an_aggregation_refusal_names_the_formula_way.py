# -*- coding: utf-8 -*-
"""Lead 11-10: the owner declared an aggregation as {"expression": "UniqueCount([stack_height])"} and the refusal
named only «"count" or {"fn": ..., "column": ...}» / «fn=None; supported: ...» - not that a formula is written as text.
The refusal names it; the {"expression": ...} spelling is still refused (one grammar), and the text form is taken."""
from chain.enrichment import config


def test_the_owners_spelling_is_refused_with_the_formula_way_named():
    normalized, why = config._parse_aggregation("stack_height", {"expression": "UniqueCount([stack_height])"})
    assert normalized is None
    assert 'a formula as text, e.g. "stack_height": "=UniqueCount([col])"' in why, why


def test_a_spec_of_another_type_names_it_too():
    normalized, why = config._parse_aggregation("stack_height", 3)
    assert normalized is None
    assert 'a formula as text, e.g. "=UniqueCount([col])"' in why, why


def test_the_text_form_is_taken():
    normalized, why = config._parse_aggregation("stack_height", "UniqueCount([stack_height])")
    assert why is None and normalized, why
