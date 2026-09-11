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

# 🔴 THE SHAPE THE PRODUCT ACTUALLY PRODUCES, and it is not symmetric: a walk's node
# carries a BARE type (`wafer`) while the declaration is keyed with its version
# (`wafer@1`). The first fixtures here used bare on both sides — which is why the live
# route returned ZERO declared columns while this file was green, and worse, why
# `unknown_type` was vacuous: with bare declarations nothing matched, so every type was
# "unknown" and the control could not fail.
NODES = {
    SEED: {"id": SEED, "type": "wafer", "depth": 0, "keys": {"mat_id": "W1"}},
    MID: {"id": MID, "type": "die", "depth": 1,
          "keys": {"mat_id": "W1", "x": 3, "y": 4},
          "qualifiers": {"gate": 7}},
    LEAF: {"id": LEAF, "type": "defect", "depth": 2,
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
    assert seed_row[header.index("seed")] == SEED, (
        "a seed row is its own seed; blank read as 「belongs to no walk」")
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
    assert marker == "# truncated=none nodes=3 limit=400"
    # 🔴 THE REASON, NOT A BOOLEAN. Measured live: the walk stopped at the hop count it was
    # ASKED for and the marker said `true`, which reads as 「your table is short」 when the
    # table is complete. A budget it exhausted and a depth it was told to stop at are
    # different facts.
    cut, _h, _b = _rows(_payload(truncated={"nodes": True, "reason": "nodes"},
                                 node_limit=2))
    assert cut == "# truncated=nodes nodes=3 limit=2"
    depth_stop, _h2, _b2 = _rows(_payload(truncated={"depth": True, "reason": "depth"}))
    assert depth_stop == "# truncated=depth nodes=3 limit=400"


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


def test_a_declared_type_never_comes_back_with_no_columns():
    """🔴 THE ASSERTION THAT WOULD HAVE CAUGHT THE LIVE ZERO. Every other column test says
    「this name is present」; none of them said 「a declared type has ANY column at all」, so a
    lookup that matched nothing passed them all. It shipped, and the live table had eight
    fixed columns and not one declared."""
    for node_type in ("wafer", "die", "defect"):
        assert ls._declared_columns([{"type": node_type, "qualifiers": {}}], ENTITIES), (
            node_type, "a declared type resolved to no columns")


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
        # 🔴 KEYED BY THE VERSIONED NAME while the node carries the bare one — the
        # product's own asymmetry. A symmetric fixture is exactly what let a lookup that
        # matched NOTHING pass all seven of these.
        entities = ({} if case["declaration"] is None
                    else {case["declaration_key"]: case["declaration"]})
        assert ls._declared_columns(nodes, entities) == case["expect"], case["name"]


# ---------------------------------------------------------------------------
# 🔴 THE ROUTE'S rows BRANCH — the one the unit tests above could not reach
# ---------------------------------------------------------------------------

def test_the_router_can_read_the_declarations_it_hands_the_fold():
    """🔴 THE ONE ASSERTION THAT WOULD HAVE CAUGHT THE 500. `_evidence_graph` reached for
    `_config` — a name every sibling handler imports LOCALLY and this one never did — so
    the rows branch raised `NameError` on its first live call while the whole suite stayed
    green. Calling the accessor is enough to prove the name resolves."""
    import ledger_trace_router as router

    entities = router._declared_entities()
    assert isinstance(entities, dict)


def test_the_route_hands_back_the_fold_as_text_not_json(monkeypatch):
    """The other half of the seam: the route must return the TSV as TEXT. A JSON body
    would parse for nobody and read as 「the walk found nothing」."""
    import ledger_trace_router as router

    monkeypatch.setattr(router, "_evidence_graph",
                        lambda *a, **kw: {
                            "rows": "# truncated=false" + chr(10)
                                    + "type" + chr(9) + "id" + chr(10),
                            "nodes": []})
    monkeypatch.setattr(router, "_signed_start", lambda *a, **kw: "seed")

    class _Db:
        def connection(self):
            return None

    # Every argument a direct call would otherwise leave as a `Query` sentinel is passed
    # explicitly — the handler's own note warns that an omitted one is the sentinel object.
    answer = router.evidence_subgraph(
        node_id="seed", response_format="rows", db=_Db(),
        hops=1, direction="both", since=None, until=None,
        node_limit=400, edge_limit=1200, positive=None, negative=None,
        follow=None, backbone_hops=0, collect=None, include_superseded=False)
    assert answer.media_type == "text/tab-separated-values"
    assert answer.body.decode().startswith("# truncated=")


def test_the_route_itself_answers_rows():
    """🔴 THIS IS THE TEST WHOSE ABSENCE SHIPPED A 500. Every gate above scored
    `rows_projection` and the refusal directly, so the WIRING between them — the route
    reading the declarations and handing back a PlainTextResponse — was never executed.
    It raised `NameError: _config` on the first live call while the suite stayed green:
    a function can be right in every test and still be unreachable.

    ⚠️ It asks the SAME question twice, once per format, and scores the rows against the
    JSON — that is gate ⓐ measured where it matters rather than on the fold in isolation.
    """
    import os

    os.environ.setdefault("TESTING", "1")
    from fastapi.testclient import TestClient

    import main

    # `raise_server_exceptions=False` so a 500 comes back AS a status rather than as an
    # exception — this test needs to read the code to decide whether to skip.
    client = TestClient(main.app, raise_server_exceptions=False)
    params = {"id": "ledger-entity:v1:heartbeat", "hops": 1, "format": "rows"}
    rows = client.get("/api/ledger/subgraph", params=params)
    # ⚠️ THE WALK IS PostgreSQL-ONLY (`to_regclass`), so this one cannot run on the
    # SQLite suite and says so by name rather than by passing vacuously. The two tests
    # above cover the same seam on every box; this is the end-to-end one, and it runs
    # wherever a walk can actually run.
    if rows.status_code in (404, 422, 500, 503):
        pytest.skip(f"no walkable seed on this box: {rows.status_code}")
    assert rows.status_code == 200, rows.text[:300]

    lines = rows.text.rstrip("\n").split("\n")
    assert lines[0].startswith("# truncated="), lines[0]
    header = lines[1].split("\t")
    assert header[:len(ls.ROW_FIXED_COLUMNS)] == list(ls.ROW_FIXED_COLUMNS)

    as_json = client.get("/api/ledger/subgraph",
                         params=dict(params, format="json"))
    assert as_json.status_code == 200
    assert len(lines) - 2 >= len(as_json.json().get("nodes") or [])


# ---------------------------------------------------------------------------
# S-183-b (판정 294) — the reaching edge's qualifiers, under a prefix
# ---------------------------------------------------------------------------

EDGES_WITH_QUALS = [
    {"source": SEED, "target": MID, "predicate": "inspected",
     "qualifiers": {"gate": "E1", "step": 10}},
    {"source": MID, "target": LEAF, "predicate": "observed",
     "qualifiers": {"gate": "E2"}},
]


def _rows_with_edge_quals():
    text = ls.rows_projection(_payload(), NODES, EDGES_WITH_QUALS, {SEED: 1}, ENTITIES)
    lines = text.rstrip("\n").split("\n")
    return lines[1].split("\t"), [line.split("\t") for line in lines[2:]]


def test_the_reaching_edges_qualifiers_ride_as_via_columns():
    header, body = _rows_with_edge_quals()
    assert "via.gate" in header and "via.step" in header
    by_id = {row[header.index("id")]: row for row in body}
    assert by_id[MID][header.index("via.gate")] == "E1"
    assert by_id[MID][header.index("via.step")] == "10"
    # the second hop was reached by a DIFFERENT edge, and carries that edge's value
    assert by_id[LEAF][header.index("via.gate")] == "E2"
    assert by_id[LEAF][header.index("via.step")] == ""


def test_the_prefix_makes_a_collision_with_a_node_column_impossible():
    """🔴 THE GATE 판정 294 NAMED. `gate` is a node qualifier on the die AND an edge
    qualifier on the edge that reached it. Without the prefix those are one column and the
    edge's value silently overwrites the node's — in a table where both are real facts."""
    header, body = _rows_with_edge_quals()
    assert "gate" in header and "via.gate" in header
    by_id = {row[header.index("id")]: row for row in body}
    assert by_id[MID][header.index("gate")] == "7", "the node's own qualifier was lost"
    assert by_id[MID][header.index("via.gate")] == "E1", "the edge's qualifier was lost"


def test_the_seed_row_has_no_reaching_edge_so_its_via_cells_are_blank():
    header, body = _rows_with_edge_quals()
    seed_row = next(r for r in body if r[header.index("id")] == SEED)
    assert seed_row[header.index("via.gate")] == ""


def test_via_columns_sit_after_the_declared_ones():
    """A row is read identity-first; the edge's facts follow what the node IS."""
    header, _body = _rows_with_edge_quals()
    assert header.index("mat_id") < header.index("via.gate")


def test_depth_and_path_are_untouched_by_the_new_columns():
    """판정 294: 「depth=path 그대로」 — the new axis must not disturb the old gate."""
    header, body = _rows_with_edge_quals()
    for row in body:
        predicates = [p for p in row[header.index("path")].split("→") if p]
        assert len(predicates) == int(row[header.index("depth")]), row


def test_an_edge_carrying_no_qualifiers_adds_no_column():
    """The control: `via.` columns come from what the answer CARRIED, so a walk whose
    edges carry nothing must render byte-identically to before this feature."""
    _marker, header, _body = _rows()
    assert not [name for name in header if name.startswith("via.")]
