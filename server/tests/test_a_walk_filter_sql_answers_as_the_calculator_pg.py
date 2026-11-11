# -*- coding: utf-8 -*-
"""Lead 11-11 (owner «여기에 걸을 엣지 필터, 노드 필터»): a walk's value filters - `edge_filter=<predicate>:<expression>`
over a step's qualifiers, `node_filter=<type>:<expression>` over a reached node's keys. The calculator is the judge
(the stored walk runs it over each atom, `walk_filter.keeps_atom`); the virtual walk says the same in its legs' WHERE.

  the answer   on one board, each expression draws the same walk by SQL (virtual) as by the calculator (stored) -
               blank, a text, a number spelled as text, a text and a number compared, three-valued not / or
  the reading  the expression keeps exactly the steps the calculator holds true of, over the unfiltered walk's own
               qualifiers - and keeps some and drops some of them (no vacuous filter); the walk reaches every step
               value the board holds (a value it does not reach tests nothing - «s1» four steps out let the COLLATE live)
  the nodes    a node filter leaves out the nodes it does not hold of, not a node the read starts from - nor the far
               end of a step when that end is a start too
  refused      a function, or a name the predicate or type does not carry, refused by name (422)
"""
import json
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import trace_router, walk_filter                        # noqa: E402
from test_a_virtual_walk_draws_what_the_ledger_draws_pg import (    # noqa: E402,F401
    ROWS, _board, _drawn, _times_declared, _walk)
from test_ledger_worlds_are_independent_and_meet_in_a_walk import (  # noqa: E402,F401
    CHANGED, KEPT, _only, fixture_config, fixture_world)

pytestmark = pytest.mark.pg

#: steps a filter reads: a text, none (blank), numbers spelled as text, a text that reads as no number - each on a
#: wafer the walk reaches in one step (W1 from the seat L1/1, W3 a seed)
MORE = [{"proc_id": "P5", "wafer_id": "W1", "step": "10", "recipe_id": "RCP-4", "eventtime": "2026-09-30 13:00:00"},
        {"proc_id": "P6", "wafer_id": "W1", "step": "9", "recipe_id": "RCP-5", "eventtime": "2026-09-30 14:00:00"},
        {"proc_id": "P7", "wafer_id": "W3", "step": "5.0", "recipe_id": "RCP-6", "eventtime": "2026-09-30 15:00:00"},
        {"proc_id": "P8", "wafer_id": "W3", "step": "s1", "recipe_id": "RCP-7", "eventtime": "2026-09-30 16:00:00"},
        {"proc_id": "P9", "wafer_id": "W3", "step": "  ", "recipe_id": "RCP-8", "eventtime": "2026-09-30 17:00:00"}]
EXPRESSIONS = ['[step] = "S1"', '[step] <> "S1"', "[step] is null", "[step] is not null", '[step] > "S"',
               '[step] <= "S2"', "[step] >= 9", "[step] = 5", '[step] < "5"', 'not ([step] = "S1")',
               '[step] = "S1" or [step] is null', '[step] = "S2" and not [step] is null']


@pytest.fixture(name="board")
def fixture_board(world):
    return _board(world, _only(CHANGED, KEPT), rows=ROWS + MORE)


def _filtered(board, engine, edge=(), node=()):
    filters = trace_router._walk_filters(list(edge), list(node), None)
    return _walk(board, engine, filters=filters)


def _steps(payload):
    return sorted(json.dumps(edge.get("qualifiers") or {}, sort_keys=True) for edge in payload["edges"]
                  if edge["predicate"].startswith("processed_with"))


@pytest.mark.parametrize("text", EXPRESSIONS)
def test_each_expression_draws_the_same_walk_by_sql_as_by_the_calculator(board, text):
    asked = ["processed_with:" + text]
    virtual = _filtered(board, "virtual", edge=asked)
    assert _drawn(virtual) == _drawn(_filtered(board, "stored", edge=asked))
    whole = [json.loads(q) for q in _steps(_walk(board, "virtual"))]
    compiled = walk_filter.compiled("edge_filter", "processed_with", text, ["step"])
    kept = sorted(json.dumps(q, sort_keys=True) for q in whole if walk_filter.holds([compiled], q))
    assert _steps(virtual) == kept
    assert 0 < len(kept) < len(whole), "keeps some, drops some of the walk's own steps"


def test_the_walk_reaches_every_step_the_board_holds(board):
    reached = {json.loads(q).get("step") for q in _steps(_walk(board, "virtual"))}
    assert reached == {(row.get("step") or "").strip() or None for row in ROWS + MORE}, \
        "every step reached - spaces stored as no step (`crud.is_blank_value`, storage canonical)"


def test_a_node_filter_leaves_out_the_nodes_it_does_not_hold_of_but_not_a_start(board):
    asked = ['recipe:[recipe] = "RCP-1"', 'wafer:[wafer] = "W1"']
    virtual = _filtered(board, "virtual", node=asked)
    assert _drawn(virtual) == _drawn(_filtered(board, "stored", node=asked))
    kinds = {(node["type"].split("@")[0], node["keys"].get("recipe") or node["keys"].get("wafer"))
             for node in virtual["nodes"] if node["type"].split("@")[0] in ("recipe", "wafer")}
    assert ("recipe", "RCP-1") in kinds and not {k for k in kinds if k[0] == "recipe"} - {("recipe", "RCP-1")}
    assert ("wafer", "W3") in kinds, "the walk's start is not judged again"
    assert ("wafer", "W2") not in kinds and ("wafer", "W1") in kinds


def test_a_step_between_two_starts_is_not_judged_by_either(board):
    """Seeds W1 and RCP-2, one step apart (P2): a filter holding of neither leaves that step drawn - both ends are
    starts - and judges W1's other steps by their far recipe."""
    from ledger import explorer

    seeds = {"positive": [explorer.entity_id("wafer", {"wafer": "W1"}),
                          explorer.entity_id("recipe", {"recipe": "RCP-2"})], "negative": []}
    filters = trace_router._walk_filters([], ['recipe:[recipe] = "RCP-1"', 'wafer:[wafer] = "W2"'], None)
    drawn = {}
    for engine in ("virtual", "stored"):
        with board["engine"].connect() as conn:
            drawn[engine] = trace_router._evidence_graph(conn, node_id=seeds, hops=1, direction="both",
                                                         node_limit=200, edge_limit=400, engine=engine,
                                                         filters=filters)
    assert _drawn(drawn["virtual"]) == _drawn(drawn["stored"])
    recipes = {node["keys"].get("recipe") for node in drawn["virtual"]["nodes"]
               if node["type"].split("@")[0] == "recipe"}
    assert recipes == {"RCP-1", "RCP-2"}, recipes
    ends = {(edge["source"], edge["target"]) for edge in drawn["virtual"]["edges"]}
    assert any(set(seeds["positive"]) == set(pair) for pair in ends), ends


@pytest.mark.parametrize("argument, entry, said", [
    ("edge_filter", "processed_with:Len([step]) > 1", "«Len»"),
    ("edge_filter", 'processed_with:[eqp] = "E1"', "[eqp]"),
    ("node_filter", 'recipe:[step] = "S1"', "[step]")])
def test_what_a_filter_does_not_read_is_refused_by_name(board, argument, entry, said):
    with pytest.raises(HTTPException) as refused:
        trace_router._walk_filters(*([entry], []) if argument == "edge_filter" else ([], [entry]), None)
    assert refused.value.status_code == 422 and refused.value.detail["reason"] == "filter_not_read"
    assert said in refused.value.detail["message"], refused.value.detail
