# -*- coding: utf-8 -*-
"""S-65-c ①. A view's base tables are DERIVED from the catalogue, not declared.

판정 154·155. Nine of the fifteen shipped sources read a view, and the outbox names base
tables -- never a view -- so those nine never reach the follow-up at all: the live path S-65
opened covers six of fifteen. Closing that means knowing, for each view, which real tables it
ultimately reads, and the two-line promise ("nothing is written in production") means nobody
may be asked to type that mapping. PostgreSQL already holds it, in `pg_rewrite` and
`pg_depend`.

🔴 THE RECURSION IS THE POINT, not a refinement. Eight of the nine reach a table in one step;
`bonding_die_from_core` reads `bonding_core_die`, which reads two tables. A one-step walk
answers "no base table" for exactly the case that needed the answer -- a silent zero.

🔴 THE DEPTH LIMIT IS A NAMED CONSTANT (판정 155), because the question "could a user write
this value?" answers no: it is an engine safety limit on a catalogue walk, not a fact about
anybody's domain. Being visible as a value is the refusal's job -- it carries the limit and
the chain it walked.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import followup                                          # noqa: E402


class _Cursor:
    def __init__(self, edges, asked):
        self._edges, self._asked = edges, asked
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        name = params[0]
        self._asked.append(name)
        self._rows = list(self._edges.get(name, ()))

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, edges, asked):
        self._edges, self._asked = edges, asked

    def cursor(self):
        return _Cursor(self._edges, self._asked)

    def rollback(self):
        pass

    def close(self):
        pass


class _Engine:
    """A stand-in catalogue: {relation: [(name, relkind), ...]}."""

    def __init__(self, edges):
        self.edges = edges
        self.asked = []

    def raw_connection(self):
        return _Connection(self.edges, self.asked)


def test_a_table_answers_with_itself():
    """A caller must not have to know which kind it was holding."""
    engine = _Engine({})
    assert followup.base_tables_of(engine, "dt_log") == ("dt_log",)


def test_a_view_answers_with_its_table():
    engine = _Engine({"dt_log_transferable": [("dt_log", "r")]})
    assert followup.base_tables_of(engine, "dt_log_transferable") == ("dt_log",)


def test_a_view_over_a_view_is_walked_through():
    """🔴 THE ONE THAT A SINGLE STEP GETS WRONG. Measured on this box:
    bonding_die_from_core reads bonding_core_die, which reads two real tables. One step
    returns nothing at all, which reads as "this view has no base table"."""
    engine = _Engine({
        "bonding_die_from_core": [("bonding_core_die", "v")],
        "bonding_core_die": [("bonding_log", "r"), ("core_wafer_map", "r")],
    })
    assert followup.base_tables_of(engine, "bonding_die_from_core") == (
        "bonding_log", "core_wafer_map")


def test_a_cycle_does_not_spin():
    """A catalogue should not describe a cycle, but a walk that trusts it must not hang."""
    engine = _Engine({"a": [("b", "v")], "b": [("a", "v")]})
    assert followup.base_tables_of(engine, "a") == ()


def test_too_deep_is_refused_with_the_limit_and_the_chain():
    """⛔ NOT AN EMPTY LIST. A silent zero would read as "no base table", which is the same
    answer a correct walk gives for a table -- the two must not render alike."""
    engine = _Engine({"v0": [("v1", "v")], "v1": [("v2", "v")], "v2": [("t", "r")]})
    with pytest.raises(followup.ViewDependencyTooDeep) as caught:
        followup.base_tables_of(engine, "v0", limit=0)
    assert caught.value.code == "view_dependency_too_deep"
    assert caught.value.limit == 0
    assert caught.value.chain[0] == "v0"
    # And the shipped limit is generous enough for the same shape.
    assert followup.base_tables_of(engine, "v0") == ("t",)


def test_the_limit_is_a_constant_and_not_a_declaration():
    """판정 155. A field for it would be a field nobody fills."""
    assert followup.VIEW_DEPENDENCY_DEPTH_LIMIT == 4


def test_each_relation_is_asked_about_once():
    """Two views over one view must not query the catalogue twice for it."""
    engine = _Engine({
        "top": [("mid_a", "v"), ("mid_b", "v")],
        "mid_a": [("shared", "v")],
        "mid_b": [("shared", "v")],
        "shared": [("t", "r")],
    })
    assert followup.base_tables_of(engine, "top") == ("t",)
    assert engine.asked.count("shared") == 1, engine.asked
