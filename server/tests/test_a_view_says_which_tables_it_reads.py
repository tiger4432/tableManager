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
    def __init__(self, edges, asked, columns):
        self._edges, self._asked, self._columns = edges, asked, columns
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        # Two questions reach this fake, and they are told apart by WHAT IS ASKED rather
        # than by the shape of the SQL: "what does this relation read" takes one argument,
        # "does this table have this column" takes two.
        if params is not None and len(params) == 2:
            table, column = params
            self._rows = [(1,)] if column in self._columns.get(table, ()) else []
            return
        name = params[0]
        self._asked.append(name)
        self._rows = list(self._edges.get(name, ()))

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, edges, asked, columns):
        self._edges, self._asked, self._columns = edges, asked, columns

    def cursor(self):
        return _Cursor(self._edges, self._asked, self._columns)

    def rollback(self):
        pass

    def close(self):
        pass


class _Engine:
    """A stand-in catalogue: {relation: [(name, relkind), ...]}."""

    def __init__(self, edges, columns=None):
        self.edges = edges
        self.columns = columns or {}
        self.asked = []

    def raw_connection(self):
        return _Connection(self.edges, self.asked, self.columns)


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


# ------------------------------------------------- which view sources a base table wakes

class _Plan:
    def __init__(self, relation, page_key):
        self.relation = relation
        self.driver = type("D", (), {"cursor_columns": (page_key,),
                                     "identity": (page_key,)})()


def _setup(plans):
    """🔴 THE SNAPSHOT STAND-IN IS UNHASHABLE, BECAUSE THE REAL ONE IS (판정 160).

    `LedgerSetupSnapshot` is a frozen dataclass, so its generated `__hash__` hashes every
    field -- including dict ones -- and raises `unhashable type: 'dict'`. The first cut of
    the cache used a `WeakKeyDictionary`, which hashes its key, and every follow-up batch on
    the live setup died; a double that was hashable by identity said nothing. Setting
    `__hash__ = None` here is what makes this file able to see that class of bug at all.
    """
    snapshot = type("Snap", (), {"source_plans": plans, "__hash__": None})()
    return type("S", (), {"snapshot": snapshot})()


def test_a_base_tables_event_wakes_the_sources_that_read_views_on_it():
    """🔴 THE MISSING HALF OF THE LIVE PATH. The outbox names base tables, never views, so
    without this the view-backed sources are unreachable -- S-65 covered six of fifteen."""
    engine = _Engine(
        edges={"void_obs_observed": [("void_obs", "r")]},
        columns={"void_obs": ("void_uid",)})
    setup = _setup({"void_observation": _Plan("void_obs_observed", "void_uid")})
    followers, cannot = followup.view_followers_of(engine, setup, "void_obs")
    assert followers == [("void_observation", "void_uid")]
    assert cannot == []


def test_a_base_table_without_the_page_key_is_named_and_not_silently_dropped():
    """⛔ THE SILENT ZERO IS THE DEFECT. `inspection_run` is a base of `void_obs_observed`
    and carries no `void_uid`, so there is nothing to aim a scope with -- and "nothing to
    aim with" must not render the same as "nothing to do"."""
    engine = _Engine(
        edges={"void_obs_observed": [("void_obs", "r"), ("inspection_run", "r")]},
        columns={"void_obs": ("void_uid",), "inspection_run": ("run_uid",)})
    setup = _setup({"void_observation": _Plan("void_obs_observed", "void_uid")})
    followers, cannot = followup.view_followers_of(engine, setup, "inspection_run")
    assert followers == []
    assert cannot == [{"view": "void_obs_observed", "source": "void_observation",
                       "base": "inspection_run", "missing_column": "void_uid"}]


def test_a_table_source_is_not_woken_twice():
    """It is already woken by `sources_for_table`; adding it here would translate the same
    molecule twice."""
    engine = _Engine(edges={}, columns={"dt_log": ("dt_job",)})
    setup = _setup({"dt_job": _Plan("dt_log", "dt_job")})
    followers, cannot = followup.view_followers_of(engine, setup, "dt_log")
    assert followers == [] and cannot == []


def test_the_derivation_is_built_once_per_snapshot():
    """판정 156. Asking twice must not ask the catalogue twice."""
    engine = _Engine(
        edges={"void_obs_observed": [("void_obs", "r")]},
        columns={"void_obs": ("void_uid",)})
    setup = _setup({"void_observation": _Plan("void_obs_observed", "void_uid")})
    followup.view_followers_of(engine, setup, "void_obs")
    asked_once = list(engine.asked)
    followup.view_followers_of(engine, setup, "void_obs")
    assert engine.asked == asked_once, engine.asked


def test_the_cache_does_not_require_a_hashable_snapshot():
    """⛔ THE REGRESSION THAT BROKE THE LIVE PATH. Asking twice must work on a snapshot that
    cannot be hashed -- which is every real one."""
    engine = _Engine(
        edges={"void_obs_observed": [("void_obs", "r")]},
        columns={"void_obs": ("void_uid",)})
    setup = _setup({"void_observation": _Plan("void_obs_observed", "void_uid")})
    with pytest.raises(TypeError):
        hash(setup.snapshot)
    first = followup.view_followers_of(engine, setup, "void_obs")
    assert followup.view_followers_of(engine, setup, "void_obs") == first


def test_a_new_snapshot_replaces_the_cached_derivation():
    """A reload must not be answered with the previous declaration's map."""
    engine = _Engine(edges={"v_a": [("t_a", "r")]}, columns={"t_a": ("k",)})
    followup.view_followers_of(engine, _setup({"s_a": _Plan("v_a", "k")}), "t_a")
    other = _Engine(edges={"v_b": [("t_b", "r")]}, columns={"t_b": ("k",)})
    followers, _cannot = followup.view_followers_of(
        other, _setup({"s_b": _Plan("v_b", "k")}), "t_b")
    assert followers == [("s_b", "k")]
