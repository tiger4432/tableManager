# -*- coding: utf-8 -*-
"""The two free-text fields an author cannot answer, turned into a list and a count.

`prepare.implementation_id` and `map.implementation_id` were required free text with no
list and no default, so authoring a source meant typing `declarative-role` from nothing.
That is not a domain question - it is a question the operator cannot answer - and the
completion test ("say how to declare it in two lines") failed on it.

⛔ AND THE ANSWER IS NOT A LITERAL. Writing `declarative-role` into code or a form would
put a domain word in code, and the 13-of-15 ratio behind it is evidence about the SHIPPED
SAMPLE rather than about any deployment. The list comes from the registry and the default
is counted from whatever sources it is handed.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import implementations as impl                       # noqa: E402


def sources(*pairs):
    return {"s%d" % i: {"prepare": {"implementation_id": p},
                        "map": {"implementation_id": m}}
            for i, (p, m) in enumerate(pairs)}


def test_the_options_come_from_the_registry(monkeypatch):
    out = impl.implementation_choices({})
    ids = {o["id"] for o in out["map"]["options"]}
    assert ids == {n for n, _ in impl.mapper_declarations()}
    assert all("version" in o for o in out["map"]["options"])


def test_the_default_is_whatever_these_sources_use_most():
    out = impl.implementation_choices(sources(("a", "x"), ("a", "x"), ("b", "y")))
    assert out["prepare"]["default"] == "a"
    assert out["map"]["default"] == "x"
    assert out["map"]["counts"] == {"x": 2, "y": 1}


def test_a_different_deployment_gets_a_different_default():
    """🔴 THE PROPERTY THAT KEEPS IT OUT OF THE CODE. Same function, other sources, other
    answer - which a literal could not do."""
    a = impl.implementation_choices(sources(("a", "x"), ("a", "x")))
    b = impl.implementation_choices(sources(("b", "y"), ("b", "y")))
    assert a["map"]["default"] == "x" and b["map"]["default"] == "y"


def test_a_tie_leaves_no_default():
    """A tie is an answer, not a failure. Breaking it would decide by an axis that is not
    evidence."""
    out = impl.implementation_choices(sources(("a", "x"), ("b", "y")))
    assert out["prepare"]["default"] is None and out["map"]["default"] is None
    assert out["map"]["counts"] == {"x": 1, "y": 1}


def test_nothing_declared_means_no_default_not_a_guess():
    out = impl.implementation_choices({})
    assert out["prepare"]["default"] is None and out["map"]["default"] is None
    assert out["prepare"]["counts"] == {} and out["map"]["counts"] == {}
    assert out["map"]["options"], "the list must still be offered when nothing is declared"


def test_the_minority_implementations_stay_selectable():
    """⚠️ THE AXIS MUST NOT DIE. Two of the shipped sources use something else, and those
    two are the reason the field exists at all."""
    out = impl.implementation_choices(sources(("a", "x"), ("a", "x"), ("a", "x")))
    ids = {o["id"] for o in out["map"]["options"]}
    assert ids == {n for n, _ in impl.mapper_declarations()}
    assert len(ids) > 1


def test_counts_travel_with_the_default():
    """So a reader can see what it was counted from instead of trusting the word."""
    out = impl.implementation_choices(sources(("a", "x"), ("a", "x")))
    assert out["prepare"]["counts"] == {"a": 2}


def test_a_source_missing_the_field_is_not_counted_as_a_vote():
    out = impl.implementation_choices({"s0": {"map": {"implementation_id": "x"}},
                                       "s1": {"map": {}}, "s2": {}})
    assert out["map"]["counts"] == {"x": 1}
    assert out["prepare"]["counts"] == {}
