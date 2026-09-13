# -*- coding: utf-8 -*-
"""S-152. A typo in a rule cell is refused once the mapper said what it reads.

🔴 THE FAILURE SHAPE THIS CLOSES (owner's, 판정 371): `trigger_colums` for `trigger_columns`.
The routing grammar is a CLOSED set, so the misspelling falls outside it and is read as a
mapper argument still written flat - warned about, never refused - and the rule then runs
against the whole table with no column scope at all. Nothing throws. The rule is table-wide
and the operator finds out from the data.

🔴 WHY IT COULD ONLY WARN: the mapper that would read that argument lives in a gitignored
file, so 「stale argument」 and 「typo」 looked identical. `@mapper(params=…)` is what tells them
apart - and once a mapper has declared, a flat cell outside the declaration is a name that
mapper will never look at.

⚠️ SO THE RULE IS 「WHERE WE CAN TELL」. No declaration, no refusal: refusing there would
refuse a working rule over a name nobody defined. That half is asserted too, because it is
the half a later tightening would quietly break.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import chain_bindings                                                # noqa: E402

RUNNABLE = {"name": "r", "trigger_table": "t", "mapper": "m"}


def _refusals(rule, *, declared=None, registered=True):
    """`declared=None` stands for 「this mapper never declared its arguments」."""
    return chain_bindings.rule_refusals(
        rule, "rule",
        mapper_resolvable=(lambda name: object() if registered else None),
        mapper_params=(lambda name: declared))


def _codes(issues):
    return sorted(i.code for i in issues)


# ---------------------------------------------------------------------------
# 🔴 declared: the typo is refused, by name
# ---------------------------------------------------------------------------

def test_the_owners_misspelling_is_refused_when_the_mapper_declared(declared=("scope",)):
    """🔴 THE ROUND. `trigger_colums` is not routing and not declared, so it is a name
    nothing will read - and running table-wide on it is the damage."""
    rule = dict(RUNNABLE, trigger_colums="a,b")

    issues = _refusals(rule, declared=declared)

    assert "undeclared_param" in _codes(issues)
    named = [i for i in issues if i.code == "undeclared_param"]
    assert named[0].path.endswith("trigger_colums"), named[0].path
    assert "trigger_colums" in named[0].path


def test_the_refusal_says_what_the_mapper_does_read():
    """⚠️ A REFUSAL AN OPERATOR CANNOT ACT ON IS HALF A REFUSAL. The message names the
    mapper's own declaration, so the next move is to compare two spellings."""
    issues = _refusals(dict(RUNNABLE, trigger_colums="a"), declared=("scope", "unit"))

    message = [i for i in issues if i.code == "undeclared_param"][0].message
    assert "scope" in message and "unit" in message


def test_a_declared_argument_written_flat_is_not_refused():
    """⛔ THE LINE BETWEEN TIDY AND BROKEN. A cell the mapper DOES read still runs; it is
    warned about so it moves under `params`, and warning is all it ever was."""
    rule = dict(RUNNABLE, scope="wafer")

    assert "undeclared_param" not in _codes(_refusals(rule, declared=("scope",)))
    assert [w.code for w in chain_bindings.rule_warnings(rule)] == ["flat_param_cell"]


def test_the_same_name_under_params_is_read_the_same_way():
    """⚠️ `params_of` IS THE VIEW THE MAPPER GETS - block and flat cells together - so the
    judgement must not change with where the operator wrote it."""
    under_block = dict(RUNNABLE, params={"trigger_colums": "a"})

    assert "undeclared_param" in _codes(_refusals(under_block, declared=("scope",)))


# ---------------------------------------------------------------------------
# ⚠️ undeclared: today's behaviour, untouched
# ---------------------------------------------------------------------------

def test_without_a_declaration_the_typo_only_warns():
    """⚠️ THE HALF THAT MUST NOT TIGHTEN. A mapper that never declared its arguments cannot
    tell a typo from a live cell, and refusing on a guess would stop a rule that works."""
    rule = dict(RUNNABLE, trigger_colums="a,b")

    assert "undeclared_param" not in _codes(_refusals(rule, declared=None))
    assert [w.path for w in chain_bindings.rule_warnings(rule)] == ["rule.trigger_colums"]


def test_an_unregistered_mapper_is_not_asked_about_its_arguments():
    """⛔ ONE REFUSAL PER FACT. A rule naming no runnable mapper is already refused for that;
    adding a second complaint about its arguments would report one defect twice."""
    issues = _refusals(dict(RUNNABLE, trigger_colums="a"), declared=("scope",),
                       registered=False)

    assert "undeclared_param" not in _codes(issues)
    assert "unresolvable_mapper" in _codes(issues)


# ---------------------------------------------------------------------------
# ⛔ one judge, three readers
# ---------------------------------------------------------------------------

def test_the_grammar_does_not_reach_into_the_registry():
    """🔴 S-188's DIRECTION, KEPT. `mapper_params` arrives as a callable for the same reason
    `mapper_resolvable` does: if this module imported `mapper_sdk`, 「what the rules file may
    say」 would depend on what the importing process happened to load."""
    import ast
    import io as _io

    tree = ast.parse(_io.open(os.path.join(SERVER_DIR, "chain_bindings.py"),
                              encoding="utf-8").read())
    named = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            named.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            named.add(node.module.split(".")[0])

    assert "mapper_sdk" not in named
