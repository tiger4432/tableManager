# -*- coding: utf-8 -*-
"""e38466810 (owner 10-20, lead 10-21): what the agent walk shows the LLM is its state's recipe rows - one card
function per name, asked in one place (`text_links.walk_context`). Four states x thirteen cards: each card the
recipe gives a state is there with its shape, every other card is absent; an unknown card and a state with no row
are refused by name. The walk answer's two cells (a0ca0428c) are the same function's output on the same answer."""
import os
import sys

import pytest

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)

from ledger import explorer, walk_cards  # noqa: E402
from utils import text_links  # noqa: E402

DECLARATION = {
    "entities": {"wafer@1": {"keys": ["wafer"]}, "die@1": {"keys": ["mat_id", "x", "y"]},
                 "recipe@1": {"keys": ["recipe"]}, "doc_chunk@1": {"keys": ["chunk"]}},
    "vocabulary": {
        "bonded_from@1": {"subjects": ["die@1"], "object": {"kind": "entity_ref", "types": ["die@1"]}},
        "in_container@1": {"subjects": ["die@1"], "object": {"kind": "entity_ref", "types": ["wafer@1"]}},
        "processed_with@1": {"subjects": ["wafer@1"], "object": {"kind": "entity_ref", "types": ["recipe@1"]}},
        "mentions@1": {"subjects": ["doc_chunk@1"], "object": {"kind": "entity_ref", "types": ["wafer@1"]}},
    }}
CORE = explorer.entity_id("wafer", {"wafer": "SYN-CX-CW-LOGIC-A-01"})
DIES = [explorer.entity_id("die", {"mat_id": "SYN-CX-CW-LOGIC-A-01", "x": float(x), "y": 1.0}) for x in range(5)]
CHUNK = explorer.entity_id("doc_chunk", {"chunk": "c1"})
#: the one-hop walk around the core wafer: five dies in it (a bundle drew two, three left), one fragment names it,
#: and no recipe - the core's processed_with is missing
ANSWER = {
    "nodes": [{"id": CORE, "type": "wafer", "label": "SYN-CX-CW-LOGIC-A-01"},
              {"id": CHUNK, "type": "doc_chunk", "label": "c1"}]
             + [{"id": d, "type": "die", "label": "die %d" % i} for i, d in enumerate(DIES[:2])],
    "edges": [{"source": d, "target": CORE, "predicate": "in_container"} for d in DIES[:2]]
             + [{"source": CHUNK, "target": CORE, "predicate": "mentions@1"}],
    "bundles": [{"node": CORE, "predicate": "in_container", "direction": "incoming", "far_type": "die",
                 "count": 5, "drawn": 2}],
}
EVERY = sorted(walk_cards.CARDS)
#: the recipe the gate walks by - a card for every state, and the state's other cards absent
RECIPE = [
    *({"recipe": "r", "state": "unwalked", "card_order": n, "card": c, "card_limit": 3, "argument": None,
       "instruction": "Pick the node the question is about." if n == 1 else None}
      for n, c in enumerate(["node_types", "key_shapes", "node_count", "meanings", "key_candidates", "question",
                             "budget"], 1)),
    *({"recipe": "r", "state": "on_node", "card_order": n, "card": c, "card_limit": 2,
       "argument": "mentions" if c == "mentions" else None, "instruction": None}
      for n, c in enumerate(["edges", "missing_edges", "mentions", "path", "budget", "question"], 1)),
    {"recipe": "r", "state": "stuck", "card_order": 1, "card": "dead_end", "card_limit": 5, "argument": None,
     "instruction": None},
    {"recipe": "r", "state": "stuck", "card_order": 2, "card": "path", "card_limit": None, "argument": None,
     "instruction": None},
    {"recipe": "r", "state": "end", "card_order": 1, "card": "full_path", "card_limit": None, "argument": None,
     "instruction": "Say what the walk found."},
]
WANTED = {state: [row["card"] for row in RECIPE if row["state"] == state]
          for state in ("unwalked", "on_node", "stuck", "end")}


@pytest.fixture
def sight(monkeypatch):
    searched = []

    def key_values(sight, node_type, limit, starts_with=None):
        searched.append((node_type, starts_with))
        if node_type == "wafer" and starts_with in (None, "SYN-CX-CW-LOGIC-A-01"):
            return {"nodes": [{"keys": {"wafer": "SYN-CX-CW-LOGIC-A-01"}, "count": 9}], "scanned": 1,
                    "scan_truncated": False, "values_truncated": False}
        return {"nodes": [], "scanned": 0, "scan_truncated": False, "values_truncated": False}

    monkeypatch.setattr(walk_cards, "key_values", key_values)
    made = walk_cards.Sight(
        question="Why has core SYN-CX-CW-LOGIC-A-01 no history?", declaration=DECLARATION,
        meanings=[{"target_kind": "entity", "target_name": "wafer", "meaning": "a silicon disc"},
                  {"target_kind": "predicate", "target_name": "processed_with", "meaning": None}],
        hops_left=3, calls_left=7,
        path=[{"step": 1, "position": DIES[4], "chosen": "N1", "reason": "the bonded core die",
               "cards": [{"card": "edges", "items": [{"predicate": "bonded_from", "direction": "outgoing",
                                                      "far_type": "die", "sample": [DIES[3]]}], "more": 0}]}])
    made.searched = searched
    return made


def _on(sight, at, answer):
    sight.at, sight.answer = [at], answer
    return sight


@pytest.mark.parametrize("state", ["unwalked", "on_node", "stuck", "end"])
def test_a_state_carries_its_recipe_cards_and_no_other(sight, state):
    if state != "unwalked":
        _on(sight, CORE, ANSWER)
    context = text_links.walk_context(sight, RECIPE, state, end=state == "end")
    assert [card["card"] for card in context["cards"]] == WANTED[state]
    for name in EVERY:
        assert ("## %s" % name in context["text"]) == (name in WANTED[state]), (state, name)
    assert context["print"] == text_links.recipe_print(RECIPE) and len(context["print"]) == 12
    assert context["text"].endswith(text_links.WALK_END_ASK if state == "end" else text_links.WALK_HOP_ASK)


def test_unwalked_offers_the_question_s_node_and_no_edge(sight):
    context = text_links.walk_context(sight, RECIPE, "unwalked")
    by = {card["card"]: card for card in context["cards"]}
    assert by["key_candidates"]["items"] == [{"id": CORE, "type": "wafer", "keys": {"wafer": "SYN-CX-CW-LOGIC-A-01"},
                                              "word": "SYN-CX-CW-LOGIC-A-01"}]
    assert context["ids"] == {"N1": CORE}                        # the one node the model may name
    assert by["meanings"]["items"] == [{"kind": "entity", "name": "wafer", "meaning": "a silicon disc"}]
    assert [i["type"] for i in by["node_types"]["items"]] == ["wafer", "die", "recipe"]     # card_limit 3
    assert by["node_types"]["more"] == 1 and "- (1 more not shown)" in context["text"]
    assert by["node_types"]["items"][1]["keys"] == ["mat_id", "x", "y"]
    assert by["budget"]["items"] == [{"hops_left": 3, "calls_left": 7}]
    assert "Pick the node the question is about." in context["text"]


def test_on_a_node_the_branches_count_the_bundle_and_the_missing_edge_is_named(sight):
    context = text_links.walk_context(_on(sight, CORE, ANSWER), RECIPE, "on_node")
    by = {card["card"]: card for card in context["cards"]}
    assert by["edges"]["items"] == [
        {"predicate": "in_container", "direction": "incoming", "far_type": "die", "count": 5, "sample": DIES[:2]},
        {"predicate": "mentions", "direction": "incoming", "far_type": "doc_chunk", "count": 1, "sample": [CHUNK]}]
    assert by["missing_edges"]["items"] == [
        {"type": "wafer", "predicate": "processed_with", "direction": "outgoing", "nodes": 1, "sample": [CORE]}]
    assert by["mentions"]["items"] == [{"node": CHUNK, "label": "c1"}]
    assert sorted(context["ids"].values()) == sorted([CORE, CHUNK, *DIES[:2], DIES[4]])


def test_a_hub_is_cut_at_the_card_limit(sight):
    many = dict(ANSWER, edges=[{"source": d, "target": CORE, "predicate": "in_container"} for d in DIES])
    branch = walk_cards.edges(_on(sight, CORE, many), 2)["items"][0]
    assert (branch["count"], branch["sample"]) == (5 + 3, DIES[:2])


def test_the_cards_fit_the_character_cap_and_the_ask_always_goes(sight):
    whole = text_links.walk_context(_on(sight, CORE, ANSWER), RECIPE, "on_node")["text"]
    cap = len(whole) - 40
    context = text_links.walk_context(sight, RECIPE, "on_node", cap=cap)
    assert len(context["text"]) <= cap and context["text"].endswith(text_links.WALK_HOP_ASK)
    assert "more not shown)" in context["text"] and "more not shown)" not in whole
    assert all(name in context["text"] for name in context["ids"])     # every identifier named is listed


def test_stuck_shows_the_branch_not_taken(sight):
    context = text_links.walk_context(_on(sight, CORE, {"nodes": [], "edges": []}), RECIPE, "stuck")
    by = {card["card"]: card for card in context["cards"]}
    assert by["dead_end"]["items"] == [{"from": DIES[4], "predicate": "bonded_from", "direction": "outgoing",
                                        "far_type": "die", "sample": [DIES[3]]}]


def test_an_unknown_card_and_a_state_without_rows_are_refused_by_name(sight):
    with pytest.raises(walk_cards.UnknownCard, match="unknown card 'route' - one of"):
        text_links.walk_context(sight, [dict(RECIPE[0], card="route")], "unwalked")
    with pytest.raises(walk_cards.UnknownCard, match="no row for state 'stuck'"):
        text_links.walk_context(sight, RECIPE[:1], "stuck")
    with pytest.raises(walk_cards.UnknownCard, match="needs the predicate"):
        walk_cards.card("mentions", _on(sight, CORE, ANSWER), 2, None)


def test_the_walk_answer_s_cells_are_the_cards_the_model_gets(sight):
    """a0ca0428c: one function, two readers - the same fixture gives the same cards."""
    context = text_links.walk_context(_on(sight, CORE, ANSWER), RECIPE, "on_node")
    by = {card["card"]: card for card in context["cards"]}
    cells = walk_cards.answer_cells(ANSWER, [CORE], {}, DECLARATION, limit=2)
    assert cells == {"branches": by["edges"], "missing_edges": by["missing_edges"]}
