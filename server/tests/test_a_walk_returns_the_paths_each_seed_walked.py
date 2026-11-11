# -*- coding: utf-8 -*-
"""The walk returns the paths each seed walked (owner 11-11 «걸은 경로를 리턴», lead 안 2): `_reach` keeps every step
from the level before, so a node two paths reach keeps both; the evidence, the rows and the next page's `resume.reach`
give the same paths; past PATHS_PER_SEED the answer says «K of N» in evidence and rows alike."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger_api import ledger_subgraph as ls  # noqa: E402


def graph(*edges):
    ids = {end for source, _p, target in edges for end in (source, target)}
    nodes = {item: {"id": item, "type": "thing", "label": item, "keys": {"id": item}, "depth": 0} for item in ids}
    return nodes, [{"source": s, "target": t, "predicate": p} for s, p, t in edges]


def paths_of(trail, node):
    return sorted(tuple(ids) for ids, _p in ls._trail_back(trail, node)[0])


def evidence_paths(nodes, parents, signs, node):
    out = {}
    for trail in ls._evidence(nodes, parents, signs, node, ls._predicates_between([])):
        out.setdefault(trail["seed"], []).append((tuple(hop["id"] for hop in trail["hops"]), trail["paths"]))
    return {seed: sorted(found) for seed, found in out.items()}


def rows_paths(nodes, edges, signs, node):
    payload = {"nodes": [nodes[node]], "limits": {}, "truncated": {}}
    text = ls.rows_projection(payload, nodes, edges, signs, {})
    header, *rows = [line.split("\t") for line in text.splitlines()[1:]]
    out = {}
    for row in rows:
        cell = dict(zip(header, row))
        out.setdefault(cell["seed"], []).append((tuple(cell["path_ids"].split(ls.PATH_SEPARATOR)), cell["paths"]))
    return {seed: sorted(found) for seed, found in out.items()}


SHARED = graph(("A", "ran", "N"), ("B", "ran", "N"), ("N", "used", "R1"), ("N", "used", "R2"))
DIRECT = graph(("A", "ran", "R1"), ("B", "ran", "R2"))
TWO_WAYS = graph(("A", "x", "M1"), ("A", "x", "M2"), ("M1", "y", "R"), ("M2", "y", "R"))
SIGNS = {"A": 1, "B": -1}


def test_through_a_shared_node_each_seed_keeps_its_own_path():
    nodes, edges = SHARED
    _reach, parents, _kinds = ls._reach(nodes, edges, SIGNS)
    assert paths_of(parents["A"], "R1") == [("A", "N", "R1")]
    assert paths_of(parents["B"], "R1") == [("B", "N", "R1")]


def test_a_direct_edge_is_its_seeds_alone():
    nodes, edges = DIRECT
    _reach, parents, _kinds = ls._reach(nodes, edges, SIGNS)
    assert paths_of(parents["A"], "R1") == [("A", "R1")]
    assert "R1" not in parents["B"] and "R2" not in parents["A"]


def test_two_ways_to_a_node_are_both_kept_and_the_cap_says_k_of_n(monkeypatch):
    nodes, edges = TWO_WAYS
    _reach, parents, _kinds = ls._reach(nodes, edges, {"A": 1})
    assert paths_of(parents["A"], "R") == [("A", "M1", "R"), ("A", "M2", "R")], "the first path alone was kept"
    assert [said for _p, said in evidence_paths(nodes, parents, {"A": 1}, "R")["A"]] == ["2 of 2", "2 of 2"]
    monkeypatch.setattr(ls, "PATHS_PER_SEED", 1)
    evidence = evidence_paths(nodes, parents, {"A": 1}, "R")["A"]
    rows = rows_paths(nodes, edges, {"A": 1}, "R")["A"]
    assert [said for _p, said in evidence] == ["1 of 2"] and [said for _p, said in rows] == ["1 of 2"]


@pytest.mark.parametrize("name", ["SHARED", "TWO_WAYS"])
def test_evidence_rows_and_the_next_pages_reach_give_the_same_paths(name):
    nodes, edges = globals()[name]
    signs = {"A": 1, "B": -1} if name == "SHARED" else {"A": 1}
    keep = {}
    _reach, parents, _kinds = ls._reach(nodes, edges, signs, keep=keep)
    for node in (n for n in nodes if n not in signs):
        evidence = evidence_paths(nodes, parents, signs, node)
        assert evidence, "canary: some seed reached " + node
        assert rows_paths(nodes, edges, signs, node) == evidence
        assert {seed: [p for p, _s in found] for seed, found in evidence.items()} == {
            seed: paths_of(keep[seed]["parents"], node) for seed in evidence}
