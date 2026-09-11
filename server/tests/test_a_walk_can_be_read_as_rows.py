# -*- coding: utf-8 -*-
"""S-183. The same walk, read sideways — one row per reached node.

Owner: 「collect 안 걸고 멀티 타입으로 표로 받아 스팟파이어」. A walk that has to be asked
one type at a time is a walk you cannot paste into a spreadsheet, so `format=rows` folds
THE SAME answer — no second route, no second traversal of the source.

🔴 `depth` AND `path` COME FROM DIFFERENT TRAVERSALS ON PURPOSE. `subgraph`'s own BFS
stamps `node["depth"]` under the follow/hops/backbone budgets; `_reach` re-walks the result
graph under further rules and owns the trail. Recomputing depth from the trail would make
「`path` 의 술어 수 = `depth`」 true by construction and measure nothing — taking each from
its own place makes that gate assert the two AGREE.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from ledger_api import ledger_subgraph as ls                          # noqa: E402

SEED = "seed-1"
MID = "die-1"
LEAF = "defect-1"

NODES = {
    SEED: {"id": SEED, "type": "wafer@1", "depth": 0, "keys": {"mat_id": "W1"}},
    MID: {"id": MID, "type": "die@1", "depth": 1,
          "keys": {"mat_id": "W1", "x": 3, "y": 4},
          "qualifiers": {"gate": 7}},
    LEAF: {"id": LEAF, "type": "defect@1", "depth": 2,
           "keys": {"k": "void-1"}, "attributes": {"radius": 1.5}},
}
EDGES = [
    {"source": SEED, "target": MID, "predicate": "inspected"},
    {"source": MID, "target": LEAF, "predicate": "observed"},
]
ENTITIES = {
    "wafer@1": {"keys": ["mat_id"]},
    "die@1": {"keys": ["mat_id", "x", "y"]},
    "defect@1": {"keys": ["k"], "attributes": ["radius"]},
}


def _payload(truncated=None, node_limit=400):
    return {
        "nodes": list(NODES.values()),
        "limits": {"nodes": node_limit},
        "truncated": truncated or {"depth": False, "nodes": False, "edges": False},
    }


def _rows(payload=None, entities=None):
    text = ls.rows_projection(payload or _payload(), NODES, EDGES, {SEED: 1},
                              ENTITIES if entities is None else entities)
    lines = text.rstrip("\n").split("\n")
    return lines[0], lines[1].split("\t"), [line.split("\t") for line in lines[2:]]


# ---------------------------------------------------------------------------
# Gate ⓐ — the rows ARE the walk's nodes
# ---------------------------------------------------------------------------

def test_every_reached_node_is_one_row():
    _marker, _header, body = _rows()
    assert len(body) == len(NODES)


def test_the_row_carries_the_walks_own_depth():
    _marker, header, body = _rows()
    depth = {row[header.index("id")]: row[header.index("depth")] for row in body}
    assert depth == {SEED: "0", MID: "1", LEAF: "2"}


# ---------------------------------------------------------------------------
# Gate ⓕ — 🔴 the two traversals agree
# ---------------------------------------------------------------------------

def test_the_path_has_one_predicate_per_hop_of_depth():
    """🔴 THIS IS A CROSS-CHECK, NOT A TAUTOLOGY. `depth` came from the payload (traversal
    one) and `path` from the trail (traversal two). If this goes red the two walks
    disagree about how far a node is, and THAT is the finding — not a broken gate."""
    _marker, header, body = _rows()
    for row in body:
        predicates = [p for p in row[header.index("path")].split("→") if p]
        assert len(predicates) == int(row[header.index("depth")]), row


def test_the_path_names_the_predicates_it_climbed():
    _marker, header, body = _rows()
    by_id = {row[header.index("id")]: row for row in body}
    assert by_id[LEAF][header.index("path")] == "inspected→observed"
    assert by_id[LEAF][header.index("path_ids")] == f"{SEED}→{MID}→{LEAF}"
    assert by_id[LEAF][header.index("parent_id")] == MID
    assert by_id[LEAF][header.index("via")] == "observed"


def test_the_seed_row_has_no_parent_and_an_empty_path():
    _marker, header, body = _rows()
    seed_row = next(r for r in body if r[header.index("id")] == SEED)
    assert seed_row[header.index("parent_id")] == ""
    assert seed_row[header.index("path")] == ""
    assert seed_row[header.index("via")] == ""


# ---------------------------------------------------------------------------
# Gate ⓒ — 「끊김 ≠ 없음」
# ---------------------------------------------------------------------------

def test_the_first_line_says_whether_the_walk_ran_out():
    """🔴 A READER PASTING THIS INTO A SPREADSHEET HAS NO OTHER WAY TO LEARN IT. A table
    that is silently short answers the question wrongly rather than refusing it."""
    marker, _header, _body = _rows()
    assert marker == "# truncated=false nodes=3 limit=400"
    cut, _h, _b = _rows(_payload(truncated={"nodes": True}, node_limit=2))
    assert cut == "# truncated=true nodes=3 limit=2"


def test_the_marker_is_the_first_line_not_a_trailer():
    text = ls.rows_projection(_payload(), NODES, EDGES, {SEED: 1}, ENTITIES)
    assert text.startswith("# truncated=")


# ---------------------------------------------------------------------------
# Gate ⓑ · ⓓ — the columns come from the DECLARATION
# ---------------------------------------------------------------------------

def test_a_key_added_to_the_declaration_adds_a_column_with_no_code_change():
    """🔴 THE WHOLE POINT. The screen and the table follow the declaration instead of
    copying it, so this is scored by EDITING THE FIXTURE and nothing else."""
    _m, before, _b = _rows()
    widened = dict(ENTITIES, **{"die@1": {"keys": ["mat_id", "x", "y", "lot"]}})
    _m2, after, _b2 = _rows(entities=widened)
    assert "lot" not in before
    assert "lot" in after
    assert len(after) == len(before) + 1


def test_a_multi_type_walk_carries_every_types_declared_columns():
    """⚠️ ONE TABLE, NOT SECTIONS. The client renders a section per type; a TSV has one
    header, so the columns are the UNION and a type that never declared one leaves it
    blank rather than shifting its row."""
    _marker, header, body = _rows()
    for name in ("mat_id", "x", "y", "k", "radius"):
        assert name in header, name
    by_id = {row[header.index("id")]: row for row in body}
    # the die declares x; the defect does not, and its cell is EMPTY rather than absent
    assert by_id[MID][header.index("x")] == "3"
    assert by_id[LEAF][header.index("x")] == ""
    assert by_id[LEAF][header.index("radius")] == "1.5"


def test_a_qualifier_the_response_carried_becomes_a_column():
    """The declaration names keys and attributes; qualifiers are what the ANSWER held —
    the same split the client's `tableColumns` makes."""
    _marker, header, body = _rows()
    assert "gate" in header
    by_id = {row[header.index("id")]: row for row in body}
    assert by_id[MID][header.index("gate")] == "7"


def test_the_declared_order_is_keys_then_qualifiers_then_attributes():
    """Scored because the contract vector pins this order against the client half."""
    assert ls._declared_columns(
        [{"type": "die@1", "qualifiers": {"gate": 7}}],
        {"die@1": {"keys": ["mat_id", "x"], "attributes": ["radius"]}}
    ) == ["mat_id", "x", "gate", "radius"]


# ---------------------------------------------------------------------------
# A cell can never invent a column
# ---------------------------------------------------------------------------

def test_a_tab_inside_a_value_cannot_invent_a_column():
    """⛔ A value carrying a tab would shift every column after it — silently, and only for
    the rows that carry one, so the table would be right and wrong at the same time."""
    assert "\t" not in ls._row_cell("a\tb")
    assert "\n" not in ls._row_cell("a\nb")
    _marker, header, body = _rows()
    assert all(len(row) == len(header) for row in body)


# ---------------------------------------------------------------------------
# Gate ⓔ — a format we do not answer is refused BY NAME
# ---------------------------------------------------------------------------

def test_an_unknown_format_is_refused_by_name():
    """⛔ NOT A FALLBACK TO JSON. A caller who asked for rows and received JSON reads the
    failure as 「the walk found nothing」 — the same shape this route already refuses for an
    unparsable interval and an undeclared predicate."""
    from fastapi import HTTPException

    import ledger_trace_router as router

    with pytest.raises(HTTPException) as caught:
        router.evidence_subgraph(node_id="x", response_format="csv", db=None)
    assert caught.value.status_code == 422
    assert caught.value.detail["reason"] == "format_unknown"
    assert caught.value.detail["value"] == "csv"


# ---------------------------------------------------------------------------
# The contract vector — the server half scores itself against the draft
# ---------------------------------------------------------------------------

def test_the_server_half_matches_every_contract_vector():
    """🔴 THE RULE, NOT THE SHAPE. The client renders per-type sections with Korean fixed
    columns; this is one TSV with machine ones, so the two column LISTS can never be equal.
    What is one rule is which DECLARED names appear and in what order, and that is what the
    vector pins — on both halves."""
    import json

    path = os.path.join(server_dir, os.pardir, "contracts", "walk_columns",
                        "vectors.json")
    with open(os.path.abspath(path), encoding="utf-8") as handle:
        vectors = json.load(handle)
    cases = vectors["per_type_declared_columns"]
    assert len(cases) >= 7, "vectors disappeared"
    for case in cases:
        nodes = [{"type": case["type"],
                  "qualifiers": {name: 1 for name in case["qualifiers_present"]}}]
        entities = ({} if case["declaration"] is None
                    else {case["type"]: case["declaration"]})
        assert ls._declared_columns(nodes, entities) == case["expect"], case["name"]
