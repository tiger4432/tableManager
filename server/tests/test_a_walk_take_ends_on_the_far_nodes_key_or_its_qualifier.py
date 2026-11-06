# -*- coding: utf-8 -*-
"""Lead 11-07 S2 (owner 11-06 «lot -> recipe»): a value walk may END - on the far node's key («processed_with») or on
its edge's qualifier («processed_with:step») - reached from the row's nodes along `follow`, the start type the subject
of the walk's first predicate. A join take and a report read it the same way, and how a walk ends is asked in one
seat (`report_reads.how_it_ends`). Several values from one row fold by `fold_end_values` (⏳ the owner's rule).
The ledger is the report values gate's in-memory one, with lot slots, their wafers and the recipes they ran."""
import ast
import dataclasses
import os

import pytest

from chain import join_into, report_reads
from ledger import explorer
from test_a_report_reads_the_quantities_values_by_two_walks import (  # noqa: F401
    CANDIDATES, DB, NOW, Reads, _atom, _cells, ledger)
from datetime import timedelta

ROW = ["lot", "slot"]
KEY = {"follow": ["has_wafer"], "end": "processed_with"}
STEP = {"follow": ["has_wafer"], "end": "processed_with:step"}


@pytest.fixture
def recipes(ledger):
    """L1 slot 1 holds W1 (ran R1 at S10), slot 2 W2 (R2 at S20), slot 3 W3 (R3a then R3b); slot 4 nothing."""
    atoms = [_atom(9001, "lot_slot", {"lot": "L1", "slot": "1"}, "has_wafer", "wafer", {"wafer": "W1"}),
             _atom(9002, "lot_slot", {"lot": "L1", "slot": "2"}, "has_wafer", "wafer", {"wafer": "W2"}),
             _atom(9003, "lot_slot", {"lot": "L1", "slot": "3"}, "has_wafer", "wafer", {"wafer": "W3"}),
             _atom(9011, "wafer", {"wafer": "W1"}, "processed_with", "recipe", {"recipe": "R1"}, step="S10"),
             _atom(9012, "wafer", {"wafer": "W2"}, "processed_with", "recipe", {"recipe": "R2"}, step="S20"),
             _atom(9013, "wafer", {"wafer": "W3"}, "processed_with", "recipe", {"recipe": "R3a"}, step="S30")]
    later = _atom(9014, "wafer", {"wafer": "W3"}, "processed_with", "recipe", {"recipe": "R3b"}, step="S40")
    atoms.append(dataclasses.replace(later, occurred_at=NOW + timedelta(days=1)))
    ledger["atoms"] += atoms
    return ledger


def _take(walk, rows):
    return join_into.walked(DB(), {"fn": "walk", "walk": dict(walk), "row": ROW, "why": "why"}, ["k"], rows)


def _slot(n):
    return {"lot": "L1", "slot": str(n)}


def test_a_take_ending_on_the_far_nodes_key_is_what_a_walk_from_the_wafer_reads(recipes):
    made = _take(KEY, [_slot(1), _slot(2)])
    direct = report_reads._walk(DB(), "test", node_id=explorer.entity_id("wafer", {"wafer": "W1"}),
                                follow=["processed_with"], hops=1)
    recipe = [n["keys"]["recipe"] for n in direct["nodes"] if n.get("type") == "recipe"]
    assert recipe == ["R1"] and made["value"](["k"], _slot(1), {}) == "R1", recipe
    assert (made["value"](["k"], _slot(2), {}), made["why"](["k"], _slot(2), {})) == ("R2", None)


def test_a_take_ending_on_a_qualifier_reads_the_edges_value(recipes):
    made = _take(STEP, [_slot(1)])
    assert made["value"](["k"], _slot(1), {}) == "S10"


def test_a_row_the_walk_reaches_nothing_from_says_no_value(recipes):
    made = _take(KEY, [_slot(4)])
    assert (made["value"](["k"], _slot(4), {}), made["why"](["k"], _slot(4), {})) == (None, "no value")


def test_several_values_from_one_row_fold_to_the_latest_pending_the_owners_rule(recipes):
    """⏳ PENDING (lead 11-07 (나)): the owner's rule for several end values sets `fold_end_values`; today the latest."""
    assert _take(KEY, [_slot(3)])["value"](["k"], _slot(3), {}) == "R3b"


def test_one_walk_a_batch_however_many_rows(recipes):
    recipes["walks"].clear()
    _take(KEY, [_slot(n) for n in (1, 2, 3, 4)] * 3)
    assert len(recipes["walks"]) == 1


def test_a_report_reads_the_same_end_on_its_wafers(recipes):
    report = Reads({"seed_type": "defect_kind", "values": {"follow": [], "end": "processed_at:tx_id"}})
    said = report.values(CANDIDATES)
    assert said["labels"] == ["processed_at:tx_id"] and said["to_fill"] == []
    assert {w: v for w, v in _cells(report, "processed_at:tx_id").items() if w in ("W2", "W0")} == {
        "W2": "T1", "W0": "T0"}


@pytest.mark.parametrize("walk,words", [
    ({"follow": ["has_wafer"], "end": "nope"}, "names nope - not a predicate"),
    ({"follow": ["has_wafer"], "end": "processed_with:nope"}, "nope is not a qualifier of processed_with"),
    ({"follow": [], "end": "processed_with"}, "subject is the node a row is walked from"),
])
def test_an_end_that_cannot_stand_is_refused_by_name(recipes, walk, words):
    assert words in join_into.walked.refusal({"fn": "walk", "walk": walk, "row": ROW})


def test_how_a_walk_ends_is_asked_in_one_seat():
    """The kind (an end, or a measured value) is asked only by `how_it_ends` - every reader goes through it. Counted:
    the functions whose if-tests hold the word «end» (`value` is the word of every cell, so it is not the kind's)."""
    asking, functions = [], 0
    for name in ("report_reads", "report_shape", "join_into"):
        tree = ast.parse(open(os.path.join(os.path.dirname(join_into.__file__), name + ".py"), encoding="utf-8").read())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.Lambda)):
                continue
            functions += 1
            tests = [n.test for n in ast.walk(node) if isinstance(n, (ast.If, ast.IfExp))]
            asks = any(isinstance(c, ast.Constant) and c.value == "end" for t in tests for c in ast.walk(t))
            if asks and isinstance(node, ast.FunctionDef):
                asking.append(node.name)
    assert functions > 100, "the census read the three modules"
    assert asking == ["how_it_ends"], asking
