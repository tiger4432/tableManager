# -*- coding: utf-8 -*-
"""A walk node's label is every DECLARED key in the declared order, each spelled the way the
ledger spells a key (총괄 1d07f1dae). The first two stored values labelled 278 dies with 42
names on the box: {.. x 1, y 10} and {.. x 1, y 4} were both 「SYN-CX-BW-001 / 1.0」."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger_api import ledger_subgraph  # noqa: E402

DECLARED = {"die": ["mat_id", "mat_type", "x", "y"], "wafer": ["wafer"]}


@pytest.fixture(autouse=True)
def declaration():
    fake = "test:label-every-key"
    token = ledger_subgraph._WALK_DECLARATION.set(fake)
    ledger_subgraph._declaration_facts[fake] = (DECLARED, {}, {})
    try:
        yield
    finally:
        ledger_subgraph._declaration_facts.pop(fake, None)
        ledger_subgraph._WALK_DECLARATION.reset(token)


def _label(entity_type, keys):
    return ledger_subgraph._entity_node(entity_type, keys)["label"]


def test_two_dies_that_differ_in_one_key_have_two_labels():
    a = {"mat_id": "SYN-CX-BW-001", "mat_type": "Wafer", "x": 1.0, "y": 10.0}
    b = dict(a, y=4.0)
    assert _label("die", a) == "SYN-CX-BW-001 / Wafer / 1 / 10"
    assert _label("die", a) != _label("die", b)


def test_a_number_is_spelled_as_the_key_is():
    one = {"mat_id": "M", "mat_type": "Wafer", "x": 1, "y": 2}
    assert _label("die", one) == _label("die", dict(one, x=1.0, y=2.0)) == "M / Wafer / 1 / 2"
    assert _label("die", dict(one, x=7.5)) == "M / Wafer / 7.5 / 2"


def test_text_keeps_its_spelling_and_a_blank_key_is_left_out():
    assert _label("die", {"mat_id": " M ", "mat_type": "", "x": "1.0", "y": None}) == "M / 1.0"


def test_a_one_key_type_and_an_undeclared_type_are_as_before():
    assert _label("wafer", {"wafer": "SYN-CX-BW-001"}) == "SYN-CX-BW-001"
    assert _label("lot", {"lot": "L1", "site": 2.0}) == "L1 / 2.0"
