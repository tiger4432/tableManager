# -*- coding: utf-8 -*-
"""The MECHANISM gate — asserted on a fixture the two candidate rules DISAGREE about.

These run WITHOUT PostgreSQL: the gate is a BFS over a config file and touches no
database, so a green line here is a green line rather than a grey skip.

🔴 WHY THE FIXTURE LOOKS LIKE THIS
-----------------------------------
A fixture both rules agree on decides nothing (this project's standing lesson, 2026-08-13).
「기전 관문이 돈다」 could mean any of four rules, and a graph where every bound quantity
reaches the finding cannot tell them apart. So `GRAPH` below is built so that ONE config
produces all four verdicts at once:

    pressure  -> unfill -> void          in the FORMATION model     -> pass
    queue_h   -> void_seen               in the BIAS model ONLY     -> bias_candidate
    humidity  in the formation model, NO path to void               -> fail
    mold_temp bound to a quantity no model of this kind mentions    -> unknown
    thickness  not bound at all                                     -> unknown (other reason)

The two `unknown`s carry DIFFERENT reasons on purpose: 「모델이 이 물리량을 안 다룬다」
and 「이 필드가 뭘 재는지 아무도 안 말했다」 are different states of knowledge and the
console's whole job is telling one absence from another.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import mechanism_gate                                               # noqa: E402


GRAPH = {
    "bindings": {
        "processed_with:params_actual.pressure_MPa": ["bond_pressure"],
        "processed_with:params_actual.queue_h": ["post_bond_queue_h"],
        "processed_with:params_actual.humidity_pct": ["humidity"],
        "processed_with:params_actual.mold_temp_C": ["mold_temp"],
        "bare.path": ["bond_pressure"],
    },
    "void_formation": {
        "role": "formation", "finding_kind": "void", "target": "void",
        "nodes": ["bond_pressure", "interface_unfill", "void", "humidity"],
        "edges": [
            {"from": "bond_pressure", "to": "interface_unfill", "dir": "-"},
            {"from": "interface_unfill", "to": "void", "dir": "+"},
        ],
    },
    "void_observation_bias": {
        "role": "observation_bias", "finding_kind": "void", "target": "void_seen",
        "nodes": ["post_bond_queue_h", "void_seen"],
        "edges": [{"from": "post_bond_queue_h", "to": "void_seen", "dir": "u"}],
    },
    "delam_formation": {
        "role": "formation", "finding_kind": "delam", "target": "delam",
        "nodes": ["bond_pressure", "delam"],
        "edges": [{"from": "bond_pressure", "to": "delam", "dir": "+"}],
    },
}


@pytest.fixture
def graph():
    return mechanism_gate.MechanismGraph(GRAPH, "<test>", "memory")


def _v(graph, key, kind="void"):
    return mechanism_gate.verdict(kind, key, graph)


# ---------------------------------------------------------------- the four verdicts
def test_a_quantity_that_reaches_the_finding_passes_and_shows_its_path(graph):
    out = _v(graph, "processed_with:params_actual.pressure_MPa")
    assert out["verdict"] == mechanism_gate.VERDICT_PASS
    assert out["model"] == "void_formation"
    assert [step["node"] for step in out["path"]] == [
        "bond_pressure", "interface_unfill", "void"]
    assert out["hops"] == 2


def test_a_quantity_reaching_only_the_bias_model_is_never_reported_as_a_cause(graph):
    """🔴 The split the bias model exists for. `post_bond_queue_h` DOES reach a declared
    target — so a gate that merely asked「닿는가」would return `pass` and the console
    would print a scanner artefact as a process cause."""
    out = _v(graph, "processed_with:params_actual.queue_h")
    assert out["verdict"] == mechanism_gate.VERDICT_BIAS
    assert out["verdict"] != mechanism_gate.VERDICT_PASS
    assert out["reason"] == mechanism_gate.REASON_BIAS_ONLY
    assert out["bias_models"] == ["void_observation_bias"]


def test_a_quantity_in_the_model_with_no_path_fails(graph):
    out = _v(graph, "processed_with:params_actual.humidity_pct")
    assert out["verdict"] == mechanism_gate.VERDICT_FAIL
    assert out["reason"] == mechanism_gate.REASON_NO_PATH


def test_the_two_unknowns_are_told_apart_by_reason(graph):
    """Both render as 「기전 —」 and they are NOT the same fact."""
    not_modelled = _v(graph, "processed_with:params_actual.mold_temp_C")
    not_bound = _v(graph, "processed_with:params_actual.thickness_nm")
    assert not_modelled["verdict"] == mechanism_gate.VERDICT_UNKNOWN
    assert not_bound["verdict"] == mechanism_gate.VERDICT_UNKNOWN
    assert not_modelled["reason"] == mechanism_gate.REASON_NODE_ABSENT
    assert not_bound["reason"] == mechanism_gate.REASON_NO_BINDING
    assert not_modelled["reason"] != not_bound["reason"]


def test_an_unbound_candidate_is_unknown_and_never_fail(graph):
    """🔴 「못 판정한 것을 불통과로 접지 마십시오」 — and it is what keeps the walk's
    zero-declaration promise: a newly translated predicate arrives unbound, ranks, and
    simply carries `unknown` here."""
    out = _v(graph, "brand_new_predicate:some.field")
    assert out["verdict"] == mechanism_gate.VERDICT_UNKNOWN
    assert out["verdict"] != mechanism_gate.VERDICT_FAIL


# ------------------------------------------------------------------- the boundaries
def test_traversal_never_crosses_models(graph):
    """`bond_pressure` reaches `delam` in the delam model and `void` in the void model.
    Asking about `void` must not walk into the delam model to get there, and asking about
    `delam` must not borrow the void model's `interface_unfill` hop."""
    as_delam = _v(graph, "processed_with:params_actual.pressure_MPa", kind="delam")
    assert as_delam["model"] == "delam_formation"
    assert [s["node"] for s in as_delam["path"]] == ["bond_pressure", "delam"]


def test_a_kind_with_no_model_is_unknown_not_fail(graph):
    out = _v(graph, "processed_with:params_actual.pressure_MPa", kind="scratch")
    assert out["verdict"] == mechanism_gate.VERDICT_UNKNOWN
    assert out["reason"] == mechanism_gate.REASON_NO_MODEL_FOR_KIND


def test_a_model_missing_role_or_target_is_refused_rather_than_guessed():
    """A model named `*_observation_bias` with no declared `role` must NOT be classified
    from its name — that would decide 「원인이냐 편향이냐」 from a string."""
    raw = {"void_observation_bias": {"finding_kind": "void", "target": "void_seen",
                                     "nodes": ["a", "void_seen"],
                                     "edges": [{"from": "a", "to": "void_seen"}]},
           "bindings": {"p:f": ["a"]}}
    graph = mechanism_gate.MechanismGraph(raw, "<test>", "memory")
    assert graph.models[0].usable is False
    assert "role" in graph.models[0].reason
    out = mechanism_gate.verdict("void", "p:f", graph)
    assert out["verdict"] == mechanism_gate.VERDICT_UNKNOWN
    assert out["reason"] == mechanism_gate.REASON_NO_MODEL_FOR_KIND


def test_an_absent_declaration_is_a_state_and_never_an_exception():
    graph = mechanism_gate._AbsentGraph(
        "<none>", "absent", mechanism_gate.REASON_NO_CONFIG, "없음")
    out = mechanism_gate.verdict("void", "p:f", graph)
    assert out["verdict"] == mechanism_gate.VERDICT_UNKNOWN
    assert out["reason"] == mechanism_gate.REASON_NO_CONFIG


def test_a_bare_path_binding_serves_every_predicate_that_carries_it(graph):
    assert _v(graph, "anything:bare.path")["verdict"] == mechanism_gate.VERDICT_PASS


# -------------------------------------------------------- the shipped declaration
def test_the_shipped_declaration_loads_and_its_models_are_usable():
    """The config in `server/config/` (or its `.sample`) must actually drive the gate —
    a declaration that loads but is `unusable` would make every verdict `unknown` and the
    R3 column would be blank everywhere for a reason nobody would look for."""
    graph = mechanism_gate.load(force_reload=True)
    assert graph.state == "declared", graph.message
    void_models = graph.models_for("void")
    assert [m.name for m in void_models] == ["void_formation", "void_observation_bias"]
    assert {m.role for m in void_models} == {mechanism_gate.ROLE_FORMATION,
                                             mechanism_gate.ROLE_OBSERVATION_BIAS}
    out = mechanism_gate.verdict(
        "void", "processed_with:params_actual.pressure_MPa", graph)
    assert out["verdict"] == mechanism_gate.VERDICT_PASS
    assert out["path"][-1]["node"] == "void"
