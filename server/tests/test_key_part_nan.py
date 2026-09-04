# -*- coding: utf-8 -*-
"""A NaN key part must reach the gate that already refuses missing key parts.

`clean_str_value(float("nan"))` is the string `"nan"`, so a NaN key part does not look
empty to anything - it looks like a value:

    compose_business_key("t", ["A", float("nan"), "C"])  ->  "A_nan_C"

Two rows whose key part is missing for unrelated reasons then land on ONE identity, and
the row whose value arrives later gets a different key and orphans the first. Nothing
raises. The door is open today: seed scripts write table rows directly and so never pass
`cast_value_by_type`, which is the one place that refuses nan/inf into a column.

🔴 THE FIX IS NOT A NEW REFUSAL. `unfilled_key_columns` already decides what happens when
a key part is missing; the defect was that it could not SEE this one. A second refusal
would be a second place for that judgement to live, and the two would answer differently
one day.

⚠️ AND `is_blank_value` IS NOT TOUCHED. It is read where blankness decides what gets
WRITTEN (the virtual join's fill-only-empty, the enrichment gate, blank_to_null), and
whether a NaN is blank THERE is a separate question that has not been measured.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud                                        # noqa: E402


class Item:
    """The three attributes `unfilled_key_columns` reads."""

    def __init__(self, updates, row_id=None, business_key_val=None):
        self.updates, self.row_id = updates, row_id
        self.business_key_val = business_key_val


@pytest.fixture
def composite_table(monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, "probe_composite",
                        {"composite_key_source": ["lot", "slot", "wafer"]})
    return "probe_composite"


@pytest.fixture
def plain_table(monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, "probe_plain", {"business_key": "serial"})
    return "probe_plain"


# ----------------------------------------------------------------- what is caught now

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_key_part_is_named_by_the_existing_gate(composite_table, bad):
    unfilled = crud.unfilled_key_columns(
        composite_table, Item({"lot": "A", "slot": bad, "wafer": "C"}))
    assert unfilled == ["slot"], unfilled


def test_the_assembler_and_the_gate_still_answer_the_same_question(composite_table):
    """🔴 THEY MUST. One asks "may I build a key?" and the other "will a key be
    buildable?" - a divergence would refuse rows the writer would have keyed, or pass rows
    it will not. So `A_nan_C` is not merely refused, it is never assembled."""
    item = Item({"lot": "A", "slot": float("nan"), "wafer": "C"})
    assert crud.unfilled_key_columns(composite_table, item) == ["slot"]
    assert crud.assemble_composite_business_key(composite_table, item) is False
    assert item.business_key_val is None, item.business_key_val


def test_a_non_finite_plain_key_is_caught_too(plain_table):
    assert crud.unfilled_key_columns(
        plain_table, Item({"serial": float("nan")})) == ["serial"]


def test_a_non_finite_business_key_val_is_not_an_identity(plain_table):
    """It is truthy and it is not blank, so the early accept let it through."""
    assert crud.unfilled_key_columns(
        plain_table, Item({}, business_key_val=float("nan"))) == ["serial"]


# ------------------------------------------------------- what must NOT change (gate 3)

def test_an_ordinary_composite_key_is_spelled_exactly_as_before(composite_table):
    """🔴 THE MOST IMPORTANT CASE. If one business key changes spelling, EVERY existing
    row keyed the old way is orphaned - a far larger failure than the one being fixed."""
    item = Item({"lot": "LOT1", "slot": "01", "wafer": "W3"})
    assert crud.unfilled_key_columns(composite_table, item) == []
    assert crud.assemble_composite_business_key(composite_table, item) is True
    assert item.business_key_val == "LOT1_01_W3"


@pytest.mark.parametrize("value", [0, 0.0, False, "0", "nan", 7.0, -1, "  x  "])
def test_values_that_are_not_missing_still_key_the_row(composite_table, value):
    """0 and False are VALUES, and the string "nan" is a value too - only the float is
    the missing marker. A guard that swallowed these would orphan rows it was written to
    protect."""
    assert crud.unfilled_key_columns(
        composite_table, Item({"lot": "A", "slot": value, "wafer": "C"})) == []


def test_the_blankness_predicate_itself_is_left_alone():
    """Deliberate, and pinned so the next round cannot widen it by accident: whether a
    NaN counts as blank where blankness decides WRITES is unmeasured."""
    assert crud.is_blank_value(float("nan")) is False
    assert crud.is_blank_key_part(float("nan")) is True
