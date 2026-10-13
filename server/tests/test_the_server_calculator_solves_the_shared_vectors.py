"""Lead 5667ea0fe: the server's calculator (`expression`) solves contracts/expression/vectors.json as it is - the
screen's calculator's exam (client2/tests/expression_vectors_harness.mjs). A vector that walks a graph or reads the
page's markings is the screen's: the server refuses it by name."""
import json
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SERVER_DIR)

import expression  # noqa: E402

FILE = json.load(open(os.path.join(SERVER_DIR, "..", "contracts", "expression", "vectors.json"), encoding="utf-8"))
SCORED = FILE["vectors"] + FILE["ours"]
#: A vector the screen alone answers (`screen_only`: markings, a sheet's cells, node constructors) or that walks a graph.
REFUSED = [v for v in SCORED if v.get("screen_only") or "graph" in v]
ANSWERED = [v for v in SCORED if v not in REFUSED]
SAID = {"markings": "is the screen's - it reads the page's markings", "cells": "is the screen's - a sheet's cells",
        "nodes": "node constructors (type(\"key\")) are the screen's",
        "graph": "is a way from the row - ways are not read on the server yet"}


def _near(got, want):
    if isinstance(want, (int, float)) and not isinstance(want, bool):
        return (isinstance(got, (int, float)) and not isinstance(got, bool)
                and abs(got - want) <= 1e-9 * max(1, abs(want)))
    return json.dumps(got) == json.dumps(want)


def test_the_file_is_the_one_both_calculators_read():
    assert len(SCORED) == len({v["id"] for v in SCORED}) and len(ANSWERED) > 200, (len(SCORED), len(ANSWERED))
    assert not (FILE.get("unsettled") or []), "an unsettled row is not scored by either calculator"


@pytest.mark.parametrize("vector", ANSWERED, ids=[v["id"] for v in ANSWERED])
def test_a_vector(vector):
    out = expression.run(expression.compile(vector["expr"]), vector["rows"], vector.get("types"))
    if "expect_rows" in vector:
        got = out.get("values")
        assert got is not None and len(got) == len(vector["expect_rows"]) and all(
            _near(g, w) for g, w in zip(got, vector["expect_rows"])), (out, vector["expect_rows"])
    else:
        assert "value" in out and _near(out["value"], vector["expect"]), (out, vector["expect"])


@pytest.mark.parametrize("vector", REFUSED, ids=[v["id"] for v in REFUSED])
def test_a_screen_vector_is_refused_by_name(vector):
    compiled = expression.compile(vector["expr"])
    said = SAID[next(k for k in SAID if k in vector)]
    assert not compiled["ok"] and said in compiled["why"], compiled


@pytest.mark.parametrize("text, number", [("29.50", 29.5), (" 1 ", 1), ("+2", 2), ("1e1", 10), (".5", 0.5), ("5.", 5),
                                          ("-3E-2", -0.03), (7, 7)])
def test_a_numeral_is_a_number(text, number):
    assert expression.number_of(text) == number


@pytest.mark.parametrize("text", ["29,50", "29 mm", "0x10", "", "  ", "Infinity", "1e", ".", "+", None, True])
def test_anything_else_is_not_a_number(text):
    assert expression.number_of(text) is None


@pytest.mark.parametrize("text, said", [
    ("A1 * 2", "A1 is the screen's - a sheet's cells"), ("Sum(B1:B3)", "B1 is the screen's - a sheet's cells"),
    ("wafer(\"W01\")", "wafer is not a function here - node constructors"), ("Log10(100)", None)])
def test_a_sheet_s_cell_and_a_node_constructor_are_refused_by_name(text, said):
    compiled = expression.compile(text)
    assert (compiled["ok"], compiled.get("why", "")[:len(said or "")]) == (said is None, said or ""), compiled


def test_an_operator_counts_each_row_it_met_a_text_on_once():
    out = expression.run(expression.compile("[x] * 2 + [x]"), [{"x": "29 mm"}, {"x": "29.50"}, {"x": None},
                                                               {"x": "a"}, {"x": 3}])
    assert out == {"values": [None, 88.5, None, None, 9], "not_number": 2}, out
