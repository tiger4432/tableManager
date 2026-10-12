# -*- coding: utf-8 -*-
"""Walk hubs, stage 2 (총괄 b5f3fc849 · afcb79f14 · 01a56c82d, 소유자 결정): a step along a predicate declared `hub`
from one node to two or more far nodes of one type folds them into a hub - one node in the answer, its members rows
of `tables[hub id]` - and the walk goes on from the members. A hub is one step AND one contrast value. Opened
(`expand`), the answer is today's."""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from ledger import setup_bundle  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402

NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)
DECLARED = ("test:walk-hubs",)
PLAIN = ("test:walk-no-hubs",)


def _facts(hubs):
    return ({}, {}, {}, {}, {}, {}, frozenset(hubs), {})


@pytest.fixture(autouse=True)
def declarations():
    ledger_subgraph._declaration_facts[DECLARED] = _facts({"has_wafer"})
    ledger_subgraph._declaration_facts[PLAIN] = _facts(())
    yield
    ledger_subgraph._declaration_facts.pop(DECLARED, None)
    ledger_subgraph._declaration_facts.pop(PLAIN, None)


def node(kind, name):
    return explorer.entity_id(kind, {kind: name})


def _atoms(*links):
    """(subject type, subject, predicate, object type, object) -> one atom each."""
    return [ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number + 1)), subject_type=st, subject_keys={st: s}, predicate=p,
        object_kind="entity_ref", object_payload={"type": ot, "keys": {ot: o}}, occurred_at=NOW,
        source_who="t", source_translator_ver="v1", source_raw_ref="row:%d" % number, supersedes=None,
        source_event_id=str(uuid.UUID(int=10_000 + number)), source_event_state="source_molecule")
        for number, (st, s, p, ot, o) in enumerate(links)]


def _walk(seed, atoms, declaration=DECLARED, **kwargs):
    kwargs.setdefault("backbone_hops", 0)
    return ledger_subgraph.subgraph(seed, ledger_subgraph.InMemoryEvidenceLookup(atoms),
                                    declaration_paths=declaration, **kwargs)


# the owner's example, small: a lot -> wafers x3 (declared) -> defects x2 each (each wafer's own) -> kinds (shared)
LOT = node("lot", "L")
OWNER = _atoms(*[("lot", "L", "has_wafer", "wafer", "W%d" % w) for w in range(3)],
               *[("wafer", "W%d" % w, "observed", "defect", "D%d%d" % (w, d)) for w in range(3) for d in range(2)],
               *[("defect", "D%d%d" % (w, d), "of_kind", "kind", "K%d" % d) for w in range(3) for d in range(2)])
WAFERS = LOT + "|has_wafer|outgoing|wafer|1,0"
DEFECTS = WAFERS + "|observed|outgoing|defect|1,0"


def _ids(body):
    return sorted(item["id"] for item in body["nodes"])


def _links(body):
    return sorted((e["source"], e["target"], e["predicate"], e.get("count")) for e in body["edges"])


def test_the_owners_example_is_a_lot_two_hubs_and_the_shared_kinds():
    body = _walk(LOT, OWNER, hops=3)
    assert _ids(body) == sorted([LOT, WAFERS, DEFECTS, node("kind", "K0"), node("kind", "K1")])
    assert _links(body) == sorted([
        (LOT, WAFERS, "has_wafer", 3), (WAFERS, DEFECTS, "observed", 6),
        (DEFECTS, node("kind", "K0"), "of_kind", 3), (DEFECTS, node("kind", "K1"), "of_kind", 3)])
    wafers, defects = body["tables"][WAFERS], body["tables"][DEFECTS]
    assert wafers["count"] == 3 and defects["count"] == 6
    assert wafers["columns"][:6] == ["type", "depth", "id", "parent_id", "via", "seed"]
    parent = wafers["columns"].index("parent_id")
    assert {row[parent] for row in wafers["rows"]} == {LOT}
    assert {row[parent] for row in defects["rows"]} == {node("wafer", "W%d" % w) for w in range(3)}
    hub = next(item for item in body["nodes"] if item["id"] == DEFECTS)
    assert (hub["type"], hub["count"], hub["value"], hub["hub"]["of"]) == ("defect", 6, [1, 0], WAFERS)


def test_a_hub_spends_one_of_the_node_budget_and_its_rows_none():
    body = _walk(LOT, OWNER, hops=3, node_limit=10)
    assert not body["truncated"]["nodes"]
    assert sum(table["count"] for table in body["tables"].values()) == 9


def test_opened_every_hub_the_answer_is_today_s():
    """① 펼침 = 오늘: the same nodes, edges and ranking as the walk whose declaration folds nothing."""
    today = _walk(LOT, OWNER, declaration=PLAIN, hops=3)
    opened = _walk(LOT, OWNER, hops=3, expand=[WAFERS, DEFECTS])
    assert "tables" not in today and "tables" not in opened
    assert _ids(opened) == _ids(today) and _links(opened) == _links(today)
    rank = lambda body: sorted((item["id"], tuple(item["reach"])) for item in body["propagation"]["ranked"])
    assert rank(opened) == rank(today)


@pytest.mark.parametrize("limit,folded", [(2, True), (3, False)])
def test_a_step_over_fanout_limit_is_the_same_hub_undeclared(limit, folded):
    """THE ONE SEAT: a declared predicate OR more far nodes than `fanout_limit` - `bundles` retired with it."""
    body = _walk(LOT, OWNER, declaration=PLAIN, hops=3, fanout_limit=limit)
    assert "bundles" not in body
    assert (WAFERS in _ids(body)) is folded


def test_an_undeclared_predicate_folds_nothing():
    assert "tables" not in _walk(LOT, OWNER, declaration=PLAIN, hops=3)


# two seeds: + P, - N. P's own wafers and N's wafers that share a recipe with P's tool are reached from both; N's
# other wafers only from N (a step back down to a sibling is not walked) - one step, two values, two hubs
P, N = node("lot", "P"), node("lot", "N")
CONTRAST = _atoms(("lot", "P", "has_wafer", "wafer", "W5"), ("lot", "P", "has_wafer", "wafer", "W6"),
                  ("lot", "P", "uses_tool", "tool", "X"), ("tool", "X", "feeds", "recipe", "R"),
                  *[("lot", "N", "has_wafer", "wafer", "W%d" % w) for w in range(1, 5)],
                  ("wafer", "W1", "uses", "recipe", "R"), ("wafer", "W2", "uses", "recipe", "R"))


def test_one_step_with_two_values_is_two_hubs_and_each_ranks_with_its_own_value():
    """총괄 afcb79f14: under the control, (0,1) and (1,1) side by side; under the marked seed, (1,1) alone."""
    body = _walk({"positive": [P], "negative": [N]}, CONTRAST, hops=2)
    hubs = {item["id"]: (item["count"], item["value"]) for item in body["nodes"] if "hub" in item}
    assert hubs == {N + "|has_wafer|outgoing|wafer|0,1": (2, [0, 1]),
                    N + "|has_wafer|outgoing|wafer|1,1": (2, [1, 1]),
                    P + "|has_wafer|outgoing|wafer|1,1": (2, [1, 1])}
    ranked = {item["id"]: (item["reach"], item.get("tied_members")) for item in body["propagation"]["ranked"]}
    assert ranked[N + "|has_wafer|outgoing|wafer|0,1"] == ([0, 1], 2)
    assert not {node("wafer", "W%d" % w) for w in range(1, 7)} & set(ranked)


def test_a_declared_step_folds_even_one_far_node():
    """QA F2 (owner «접을 것은 선언 — 자동 기준 수가 아니다»): a declared hub predicate folds whatever its count - a hub ×1;
    drawing it as a node is the screen's to choose."""
    body = _walk(LOT, _atoms(("lot", "L", "has_wafer", "wafer", "W0")), hops=1)
    assert {item["id"]: item["count"] for item in body["nodes"] if "hub" in item} == {WAFERS: 1}


def test_a_seed_is_never_folded_and_a_row_reached_another_way_later_stands_alone_with_its_rows():
    """W1 is a row at depth 1; at depth 2 a tool the lot checks reaches it - another way: W1 and its own defects stand
    alone, the other wafers stay rows."""
    atoms = OWNER + _atoms(("lot", "L", "checks", "tool", "X"), ("tool", "X", "feeds", "tool", "G"),
                           ("tool", "G", "near", "wafer", "W1"))
    body = _walk(LOT, atoms, hops=3)
    ids = _ids(body)
    assert LOT in ids and node("wafer", "W1") in ids
    assert {node("defect", "D10"), node("defect", "D11")} <= set(ids)
    assert body["tables"][WAFERS]["count"] == 2


def test_a_hub_id_as_a_seed_walks_from_the_step_s_far_nodes():
    """총괄 01a56c82d - the step's, every value: a value belongs to the walk that drew it."""
    body = _walk(N + "|has_wafer|outgoing|wafer|0,1", CONTRAST, hops=1)
    assert sorted(item["id"] for item in body["seeds"]) == sorted(node("wafer", "W%d" % w) for w in range(1, 5))


def test_an_expand_that_is_not_a_hub_id_is_refused_by_name():
    with pytest.raises(ValueError, match="is not a hub id"):
        _walk(LOT, OWNER, hops=3, expand=[LOT + "|has_wafer|outgoing"])


SHIPPED = Path(__file__).resolve().parent.parent / "config" / "sample"


def _issues(hub_value):
    document = json.loads((SHIPPED / "ledger_config.json.sample").read_text(encoding="utf-8"))
    document["vocabulary"]["inspected@1"]["hub"] = hub_value
    catalog = setup_bundle.load_physical_catalog(SHIPPED / "table_config.json.sample")
    return {(issue.path, issue.code) for issue in setup_bundle.validate_bundle_errors(document, catalog=catalog)}


@pytest.mark.parametrize("value", [True, False])
def test_the_hub_cell_takes_true_or_false(value):
    assert not {path for path, _code in _issues(value) if path.endswith(".hub")}


@pytest.mark.parametrize("value", ["yes", 1, None, ["a"]])
def test_any_other_hub_value_is_refused_by_name(value):
    assert ("bundle.vocabulary.inspected.hub", "invalid_predicate") in _issues(value)


def test_an_aux_judgement_splits_a_hub_as_the_contrast_does_and_rides_its_head():
    """lead 5ad030347: the values a hub is one of are the contrast and, when asked, the aux judgement."""
    body = _walk(LOT, OWNER, hops=3, aux=[node("kind", "K0")])
    hubs = {item["id"]: item.get("aux") for item in body["nodes"] if "hub" in item}
    assert hubs == {WAFERS + ",found": {"state": "found"},
                    WAFERS + ",found|observed|outgoing|defect|1,0,found": {"state": "found"}}
    assert body["aux"]["seeds"] == [node("kind", "K0")]


# read newest first, so the wafers (the later atoms) are drawn before the tools cut the first page: the wafers are rows
# when it stops, and their defects - on the next page - fold only because the resume carried the hub
PAGED = _atoms(*[("lot", "L", "made_by", "tool", "T%d" % t) for t in range(30)],
               *[("wafer", "W%d" % w, "observed", "defect", "D%d" % w) for w in range(6)],
               *[("lot", "L", "has_wafer", "wafer", "W%d" % w) for w in range(6)])


#: A node's counts of the atoms its page read - per page, hubs or none (open: lead d2a64a904 asked)
PAGE_LOCAL = ("claim_count", "predicates")


def _applied(pages):
    """What a receiver holds after the pages, each a delta laid over the last by id (lead d2a64a904): moved and left
    first, then the nodes (a hub head of count 0 is gone, its table with it), the edges (a hub edge of count 0 is
    gone), the rows. -> the bytes, page-local counts aside."""
    nodes, edges, tables = {}, {}, {}
    for body in pages:
        for row, old, new in body.get("moved") or ():
            tables.setdefault(new, {})[row] = tables.get(old, {}).pop(row)
        for hub_id, row in body.get("left") or ():
            tables.get(hub_id, {}).pop(row, None)
        for item in body["nodes"]:
            if set(item) == {"id", "count"} and item["count"] == 0:
                nodes.pop(item["id"], None)
                tables.pop(item["id"], None)
            else:
                nodes[item["id"]] = {k: v for k, v in item.items() if k not in PAGE_LOCAL}
        for edge in body["edges"]:
            if set(edge) == {"id", "count"} and edge["count"] == 0:
                edges.pop(edge["id"], None)
            else:
                edges[edge["id"]] = edge
        for hub_id, table in (body.get("tables") or {}).items():
            for row in table["rows"]:
                tables.setdefault(hub_id, {})[row[2]] = dict(zip(table["columns"], row))
    return json.dumps({"nodes": nodes, "edges": edges, "tables": {h: rows for h, rows in tables.items() if rows}},
                      sort_keys=True, default=str)


def _paged(seed, atoms, **kwargs):
    pages, body = [], _walk(seed, atoms, **kwargs)
    for _ in range(50):
        pages.append(body)
        if body["more"]["resume"] is None:
            return pages
        body = _walk(seed, atoms, resume=json.loads(json.dumps(body["more"]["resume"])), **kwargs)
    raise AssertionError("the walk did not end in 50 pages")


# the memory repro (lead d2a64a904): a wafer's dies (declared), each die's defects -> kinds (shared), each die bonded
# from a die of one of seven other wafers. Cut by edges, a die a page answered as a row is reached again later.
BONDED_DECLARED = ("test:walk-hubs-bonded",)
WAFER = node("wafer", "W")
BONDED = _atoms(*[link for d in range(60) for link in (
    ("die", "D%d" % d, "in_container", "wafer", "W"),
    *[("die", "D%d" % d, "observed", "defect", "F%d_%d" % (d, f)) for f in range(4)],
    *[("defect", "F%d_%d" % (d, f), "of_kind", "kind", "K%d" % (f % 3)) for f in range(4)],
    ("die", "D%d" % d, "bonded_from", "die", "B%d" % d),
    ("die", "B%d" % d, "in_container", "wafer", "WB%d" % (d % 7)))])
BONDED_KW = dict(declaration=BONDED_DECLARED, hops=6, static_types=["kind"], backbone_hops=2)


@pytest.fixture
def bonded(monkeypatch):
    inverse = {"inspected": "in_container", "in_container": "inspected"}
    monkeypatch.setitem(ledger_subgraph._declaration_facts, BONDED_DECLARED,
                        ({}, {}, {}, inverse, {}, {}, frozenset({"in_container"}), {}))


def test_pages_applied_as_deltas_are_the_one_walk_s_answer():
    """Gate (lead d2a64a904): each page laid over the last by id is the one walk's answer, byte for byte - nodes, hub
    tables, edges with their counts. The resume carries the hubs, so a row stays its hub's on the next page."""
    whole = _walk(LOT, PAGED, hops=2, node_limit=1000)
    assert whole["more"]["resume"] is None
    pages = _paged(LOT, PAGED, hops=2, node_limit=10)
    assert len(pages) > 1, "canary: the first page is cut"
    later = {hub_id for body in pages[1:] for hub_id in body.get("tables") or {}}
    assert any(hub_id.endswith("|observed|outgoing|defect|1,0") for hub_id in later), \
        "canary: a row's own children come on a later page, as the next hub's rows"
    assert _applied(pages) == _applied([whole])


def test_a_row_an_earlier_page_answered_that_leaves_its_hub_is_said_and_its_edges_read_again(bonded):
    """A2 (lead d2a64a904): the page that reaches a row another way says it `left`, answers it as a node and reads its
    edges again within the atom budget - what does not fit is `edges_pending`, the next page's first read."""
    whole = _walk(WAFER, BONDED, edge_limit=10 ** 6, node_limit=1000, **BONDED_KW)
    assert whole["more"]["resume"] is None
    pages = _paged(WAFER, BONDED, edge_limit=40, **BONDED_KW)
    assert _applied(pages) == _applied([whole])
    assert any(body.get("left") for body in pages), "canary: a row of an earlier page leaves its hub"
    assert any(body.get("edges_pending") for body in pages), "canary: a page runs out of atoms reading edges again"


def test_rows_a_page_had_no_atoms_left_for_are_the_next_page_s_first_read(bonded, monkeypatch):
    """A2 (lead d2a64a904): the rows whose edges a page could not read again are the next page's FIRST read - before
    it walks on, so they do not wait behind a read that spends every page's atoms (the walk board's seed read)."""
    reads = []
    real = ledger_subgraph.InMemoryEvidenceLookup.claims_for_entities

    def spy(self, entities, direction, limit, **kwargs):
        reads.append([explorer.entity_id(item[0], item[1]) for item in entities])
        return real(self, entities, direction, limit, **kwargs)

    monkeypatch.setattr(ledger_subgraph.InMemoryEvidenceLookup, "claims_for_entities", spy)
    body, firsts = _walk(WAFER, BONDED, edge_limit=40, **BONDED_KW), 0
    for _ in range(50):
        pending = body.get("edges_pending") or []
        if body["more"]["resume"] is None:
            break
        reads.clear()
        body = _walk(WAFER, BONDED, edge_limit=40, resume=json.loads(json.dumps(body["more"]["resume"])), **BONDED_KW)
        if pending:
            assert reads[0] == pending[:50], "the page after read something else first"
            firsts += 1
    assert firsts, "canary: a page ran out of atoms reading edges again"


# the owner's example behind 250 of the lot's tools: the first page stops in the lot's read with W0..W2 rows; a later
# page reaches W1 through the tool the lot checks - W1 leaves, the hub keeps W0 and W2
LEAVING = _atoms(*[("lot", "L", "made_by", "tool", "T%d" % i) for i in range(250)],
                 *[("lot", "L", "has_wafer", "wafer", "W%d" % w) for w in range(3)],
                 *[("wafer", "W%d" % w, "observed", "defect", "D%d%d" % (w, d)) for w in range(3) for d in range(2)],
                 *[("defect", "D%d%d" % (w, d), "of_kind", "kind", "K%d" % d) for w in range(3) for d in range(2)],
                 ("lot", "L", "checks", "tool", "X"), ("tool", "X", "feeds", "tool", "G"),
                 ("tool", "G", "near", "wafer", "W1"))


def test_a_row_that_leaves_a_hub_that_keeps_its_others_is_said_left():
    """left (lead d2a64a904): the receiver takes the row out of its hub's table - without it the row would stand twice,
    as a node and as a row of a hub that still stands."""
    whole = _walk(LOT, LEAVING, hops=3, node_limit=1000, edge_limit=10 ** 6)
    pages = _paged(LOT, LEAVING, hops=3, edge_limit=100)
    assert _applied(pages) == _applied([whole])
    assert [row for body in pages for _hub, row in body.get("left") or ()] == [node("wafer", "W1")],         "canary: W1, a row of the first page, leaves on a later one"
    assert json.loads(_applied([whole]))["nodes"][WAFERS]["count"] == 2, "canary: its hub keeps W0 and W2"


# CONTRAST behind 150 of P's tools: the first page stops in the seeds' read with N's W1 and W2 rows of «0,1»
MOVING = _atoms(*[("lot", "P", "made_by", "tool", "T%d" % i) for i in range(150)],
                ("lot", "P", "has_wafer", "wafer", "W5"), ("lot", "P", "has_wafer", "wafer", "W6"),
                ("lot", "P", "uses_tool", "tool", "X"), ("tool", "X", "feeds", "recipe", "R"),
                *[("lot", "N", "has_wafer", "wafer", "W%d" % w) for w in range(1, 5)],
                ("wafer", "W1", "uses", "recipe", "R"), ("wafer", "W2", "uses", "recipe", "R"))


def test_a_row_whose_value_a_later_page_changes_is_said_moved():
    """moved (lead d2a64a904): the page that brings P's reach through the recipe moves W1 and W2 from «0,1» to «1,1».
    The limit (lead, 10-13 ㄱ): a row a later page does not reach again keeps its page's value - a continued page ranks
    what it newly reached, as nodes did before hubs - so P's own wafers stay «1,0» where the one walk says «1,1»."""
    seeds = {"positive": [P], "negative": [N]}
    whole = _walk(seeds, MOVING, hops=2, node_limit=1000, edge_limit=10 ** 6)
    pages = _paged(seeds, MOVING, hops=2, edge_limit=100)
    moved = sorted((row, old.rsplit("|", 1)[-1], new.rsplit("|", 1)[-1])
                   for body in pages for row, old, new in body.get("moved") or ())
    assert moved == sorted([(node("wafer", "W1"), "0,1", "1,1"), (node("wafer", "W2"), "0,1", "1,1")])
    applied, one = json.loads(_applied(pages)), json.loads(_applied([whole]))
    for hub_id in (N + "|has_wafer|outgoing|wafer|0,1", N + "|has_wafer|outgoing|wafer|1,1"):
        assert applied["tables"][hub_id] == one["tables"][hub_id]
        assert applied["nodes"][hub_id] == one["nodes"][hub_id]


def test_a_page_after_the_first_reads_as_the_walk_asked(monkeypatch):
    """🔴 The 7-page early end (lead d2a64a904): the resume's hubs were read into the walk's own `direction`, so every
    page after the first read one side - on the walk board, the dies gave 738 atoms of 72,018."""
    directions = []
    real = ledger_subgraph.InMemoryEvidenceLookup.claims_for_entities

    def spy(self, entities, direction, limit, **kwargs):
        directions.append(direction)
        return real(self, entities, direction, limit, **kwargs)

    monkeypatch.setattr(ledger_subgraph.InMemoryEvidenceLookup, "claims_for_entities", spy)
    first = _walk(LOT, PAGED, hops=2, node_limit=10)
    on_first = set(directions)
    assert first["more"]["resume"]["hubs"], "canary: the next page carries hubs"
    directions.clear()
    _walk(LOT, PAGED, hops=2, node_limit=10, resume=json.loads(json.dumps(first["more"]["resume"])))
    assert directions and on_first == {"both"} and set(directions) == {"both"}, (on_first, directions)


# ---- QA on fc4ce3147 (lead 0e24891ce) --------------------------------------------------------------------------------

ROWS_DECLARED = ("test:walk-hubs-rows",)


@pytest.fixture
def rows_declared(monkeypatch):
    monkeypatch.setitem(ledger_subgraph._declaration_facts, ROWS_DECLARED, _facts({"has_wafer", "observed"}))


def _rows_with_atoms(n, defects):
    """QA's shape (qa_endless_default): the lot behind 450 of its tools (page 1 cut by nodes); W1 is reached another way
    after its defects were answered as rows, so they leave together - `defects` rows of W1 with `n` atoms each to read
    again, more than a page's atoms."""
    return _atoms(("tool", "G", "near", "wafer", "W1"), ("tool", "X", "feeds", "tool", "G"), ("lot", "L", "checks", "tool", "X"),
                  *[("defect", "D%d_%02d" % (w, d), "of_kind", "kind", "K%04d" % k)
                    for w in range(3) for d in range(defects) for k in range(n)],
                  *[("wafer", "W%d" % w, "observed", "defect", "D%d_%02d" % (w, d)) for w in range(3) for d in range(defects)],
                  *[("lot", "L", "made_by", "tool", "T%d" % i) for i in range(450)],
                  *[("lot", "L", "has_wafer", "wafer", "W%d" % w) for w in range(3)])


def _uncapped(monkeypatch):
    """The one walk to hold pages against: the route's caps lifted, as the walk board's gate lifts them."""
    for name in ("MAX_NODE_LIMIT", "MAX_EDGE_LIMIT", "MAX_CLAIM_SCAN"):
        monkeypatch.setattr(ledger_subgraph, name, 10 ** 7)


@pytest.mark.parametrize("n,defects", [(120, 60), (500, 20), (6001, 1)])
def test_a_continued_walk_ends_whatever_a_row_carries_and_every_page_moves_on(rows_declared, n, defects, monkeypatch):
    """QA F1: reading a row's edges again went back whole when a chunk was over the atom budget - 6 to 9 pages the same
    state. It goes on from where it stopped: every page hands out a state it was not given, the walk ends, and the
    pages laid over the last are the one walk - the edges read again too (M3: kept only within the page, they went)."""
    atoms = _rows_with_atoms(n, defects)
    with monkeypatch.context() as lifted:
        _uncapped(lifted)
        whole = _walk(LOT, atoms, declaration=ROWS_DECLARED, hops=3, node_limit=10 ** 7, edge_limit=10 ** 7)
    assert whole["more"]["resume"] is None, "canary: the one walk is whole"
    pages, given, body = [], None, _walk(LOT, atoms, declaration=ROWS_DECLARED, hops=3)
    for _ in range(50):
        pages.append(body)
        assert "stalled" not in (body["truncated"]["reason"] or "")
        if body["more"]["resume"] is None:
            break
        handed = json.dumps(body["more"]["resume"], sort_keys=True)
        assert handed != given, "a page handed out the state it was given"
        given = handed
        body = _walk(LOT, atoms, declaration=ROWS_DECLARED, hops=3, resume=json.loads(handed))
    else:
        raise AssertionError("the walk did not end in 50 pages")
    assert any(body.get("left") for body in pages), "canary: rows of a page before leave"
    assert any(body.get("edges_pending") for body in pages), "canary: reading their edges again runs out of atoms"
    assert _applied(pages) == _applied([whole])


def test_a_page_that_hands_back_the_state_it_was_given_ends_the_walk_and_says_so(rows_declared):
    """QA F1's guard: a read that does not move on (here a lookup that ignores the cursor) would page forever - the walk
    ends where a page would hand out the very state it was given, «stalled»."""
    class Stuck(ledger_subgraph.InMemoryEvidenceLookup):
        def claims_for_entities(self, entities, direction, limit, **kwargs):
            kwargs.pop("before", None)
            return super().claims_for_entities(entities, direction, limit, **kwargs)

    lookup = Stuck(_rows_with_atoms(3500, defects=2))
    body = ledger_subgraph.subgraph(LOT, lookup, declaration_paths=ROWS_DECLARED, hops=3, backbone_hops=0)
    for _ in range(50):
        if body["more"]["resume"] is None:
            break
        body = ledger_subgraph.subgraph(LOT, lookup, declaration_paths=ROWS_DECLARED, hops=3, backbone_hops=0,
                                        resume=json.loads(json.dumps(body["more"]["resume"])))
    else:
        raise AssertionError("the walk did not end in 50 pages")
    assert "stalled" in body["truncated"]["reason"]


def test_a_fan_out_limit_reads_the_step_s_whole_count_across_pages(monkeypatch):
    """QA F2: «over fanout_limit» was counted within one read - a page cut that left one wafer on page 1 never folded the
    step. A read the budget cut counts its steps whole, once: the pages laid over the last are the one walk."""
    atoms = _atoms(*[("lot", "L", "has_wafer", "wafer", "W%d" % w) for w in range(5)],
                   ("lot", "L", "made_by", "tool", "T0"), ("lot", "L", "made_by", "tool", "T1"))
    whole = _walk(LOT, atoms, declaration=PLAIN, hops=1, fanout_limit=2)
    monkeypatch.setattr(ledger_subgraph, "MAX_CLAIM_SCAN", 3)
    pages = _paged(LOT, atoms, declaration=PLAIN, hops=1, fanout_limit=2)
    assert len(pages) > 1 and "tables" in pages[0], "canary: page 1 is cut with one wafer read, and folds it"
    assert _applied(pages) == _applied([whole])


@pytest.mark.parametrize("filters", ["none", "as of", "interval", "follow", "superseded"])
def test_a_step_s_count_reads_through_the_read_s_own_filters(filters):
    """QA F2 ①: the count is the read's - the same lookup, the same filters - so it never counts what the walk would not
    read: the distinct ends `ends_only` gives are the ends of every atom an uncapped read gives."""
    later = datetime(2026, 6, 1, tzinfo=timezone.utc)
    atoms = _atoms(*[("lot", "L", "has_wafer", "wafer", "W%d" % w) for w in range(6)],
                   ("lot", "L", "made_by", "tool", "T0"))
    atoms[1] = ledger_subgraph.EvidenceAtom(**{**atoms[1].__dict__, "occurred_at": later})
    atoms[2] = ledger_subgraph.EvidenceAtom(**{**atoms[2].__dict__,
                                               "id": str(uuid.UUID(int=(4_102_444_800_000 << 80) | (7 << 76) | 1))})
    lookup = ledger_subgraph.InMemoryEvidenceLookup(
        atoms, **({"since": later - timedelta(days=1)} if filters == "interval" else {}),
        **({"current_only": False} if filters == "superseded" else {}))
    if filters == "as of":
        lookup.recorded_before = ledger_subgraph._as_of_bound(NOW)
    follow = ["has_wafer"] if filters == "follow" else None
    entities = [("lot", {"lot": "L"})]
    read, _cut = lookup.claims_for_entities(entities, "both", 10 ** 6, follow=follow)
    ends, _ = lookup.claims_for_entities(entities, "both", 0, follow=follow, ends_only=True)
    as_ends = sorted(json.dumps([a.subject_type, a.subject_keys, a.predicate, a.object_kind, a.object_payload],
                                sort_keys=True) for a in read)
    assert sorted(json.dumps(list(end), sort_keys=True) for end in ends) == sorted(set(as_ends))
    assert len(ends) < 7 or filters in {"none", "superseded"}, "canary: the filter left something out"


def test_a_hub_seed_reads_as_of_the_first_page_and_within_its_budget(monkeypatch):
    """QA F4 · F5: a hub id seed is read as every read of the page - as of the first page (an atom written after it is
    not a seed of page 2) - and within the atom budget, a cut said as claims."""
    atoms = _atoms(*[("lot", "L", "has_wafer", "wafer", "W%d" % w) for w in range(8)],
                   *[("wafer", "W%d" % w, "observed", "defect", "D%d%d" % (w, d)) for w in range(8) for d in range(30)])
    first = _walk(WAFERS, atoms, hops=1, node_limit=10)
    assert first["more"]["resume"] is not None, "canary: page 1 is cut"
    late = ledger_subgraph.EvidenceAtom(**{**_atoms(("lot", "L", "has_wafer", "wafer", "W9"))[0].__dict__,
                                           "id": str(uuid.UUID(int=(4_102_444_800_000 << 80) | (7 << 76) | 1))})
    second = _walk(WAFERS, atoms + [late], hops=1, node_limit=10,
                   resume=json.loads(json.dumps(first["more"]["resume"])))
    assert node("wafer", "W9") not in {item["id"] for item in second["nodes"]}
    monkeypatch.setattr(ledger_subgraph, "MAX_CLAIM_SCAN", 5)
    cut = _walk(WAFERS, atoms, hops=1)
    assert cut["truncated"]["claims"] is True and "claims" in cut["truncated"]["reason"]


def test_the_pages_are_the_same_bytes_whatever_the_hash_seed():
    """QA F7: `edges_pending`'s order rode the hash seed (a row's children in a set) - three seeds, the same pages but
    for the instants."""
    import subprocess

    code = r"""
import hashlib, json, os, sys
sys.path.insert(0, os.getcwd()); sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
import test_a_walk_folds_a_declared_step_into_a_hub as t
from ledger_api import ledger_subgraph as l
l._declaration_facts[t.ROWS_DECLARED] = t._facts({"has_wafer", "observed"})
atoms = t._atoms(*[("lot", "L", "made_by", "tool", "T%d" % i) for i in range(250)],
                 *[("lot", "L", "has_wafer", "wafer", "W%d" % w) for w in range(3)],
                 *[("wafer", "W%d" % w, "observed", "defect", "D%d_%02d" % (w, d)) for w in range(3) for d in range(60)],
                 *[("defect", "D%d_%02d" % (w, d), "of_kind", "kind", "K%d" % k)
                   for w in range(3) for d in range(60) for k in range(4)],
                 ("lot", "L", "checks", "tool", "X"), ("tool", "X", "feeds", "tool", "G"), ("tool", "G", "near", "wafer", "W1"))
pages = t._paged(t.LOT, atoms, declaration=t.ROWS_DECLARED, hops=3, edge_limit=100)
def strip(item):
    if isinstance(item, dict):
        return {k: strip(v) for k, v in item.items() if k not in ("generated_at", "as_of")}
    return [strip(v) for v in item] if isinstance(item, list) else item
print(len(pages), sum(len(p.get("edges_pending") or ()) for p in pages),
      hashlib.md5(json.dumps(strip(pages), default=str).encode()).hexdigest())
"""
    seen = set()
    for seed in ("1", "2", "3"):
        out = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(os.path.dirname(__file__)),
                             env=dict(os.environ, PYTHONHASHSEED=seed), capture_output=True, text=True, timeout=300)
        assert out.returncode == 0, out.stderr[-2000:]
        seen.add(out.stdout.strip().splitlines()[-1])
    (line,) = seen
    assert int(line.split()[1]) > 0, "canary: edges were pending"


def test_hub_on_the_name_atoms_are_not_stored_under_is_refused_naming_the_other():
    """QA F8: `hub: true` on the other name of an inverse pair folded nothing - refused, naming where to write it."""
    document = json.loads((SHIPPED / "ledger_config.json.sample").read_text(encoding="utf-8"))
    inspected = document["vocabulary"]["inspected@1"]
    document["vocabulary"]["inspected_by@1"] = {
        "status": "active", "subjects": list(inspected["object"]["types"]), "inverse_of": "inspected@1", "hub": True,
        "object": {"kind": "entity_ref", "types": list(inspected["subjects"]), "qualifiers": {"required": [], "optional": []}}}
    catalog = setup_bundle.load_physical_catalog(SHIPPED / "table_config.json.sample")
    issues = setup_bundle.validate_bundle_errors(document, catalog=catalog)
    said = [issue for issue in issues if issue.path.endswith(".hub")]
    assert [(issue.path, issue.code) for issue in said] == [("bundle.vocabulary.inspected_by.hub", "invalid_predicate")]
    assert "'inspected'" in said[0].message


def test_a_walk_that_cannot_fold_resumes_and_answers_as_before_hubs():
    """QA F9: no hub predicate and no fan-out limit - the resume carries what it carried before hubs, and the aux block
    is the answer's last key, where it was."""
    body = _walk(LOT, PAGED, declaration=PLAIN, hops=2, node_limit=10)
    assert set(body["more"]["resume"]) == {"as_of", "frontier", "seen", "cursor", "reach", "ids"}
    aux = _walk(LOT, OWNER, declaration=PLAIN, hops=3, aux=[node("kind", "K0")])
    assert list(aux)[-1] == "aux"


def test_a_resume_this_walk_did_not_hand_out_is_refused_by_name():
    """QA F10: a place number out of range was a 500 - it is a refusal (the route's 422)."""
    first = _walk(LOT, PAGED, hops=2, node_limit=10)
    resume = json.loads(json.dumps(first["more"]["resume"]))
    resume["shown"]["rows"][0][1] = 99
    with pytest.raises(ValueError, match="not a page this walk handed out"):
        _walk(LOT, PAGED, hops=2, node_limit=10, resume=resume)


def test_the_route_folds_and_a_direct_caller_that_stores_what_it_walked_does_not(monkeypatch):
    """QA F11: the route's `fold` is a dependency that is always true - through the pool's wrapping too - and the contrast
    mapper passes false: its run rows hold the walked nodes, never a hub - the walk a declaration without hubs gives."""
    from ledger import trace_router
    from mappers import contrast_walk

    (route,) = [r for r in trace_router.router.routes if getattr(r, "path", "") == "/api/ledger/subgraph"]
    (fold,) = [d for d in route.dependant.dependencies if d.name == "fold"]
    assert fold.call() is True
    assert "fold" not in {param.name for param in route.dependant.query_params}
    passed = []
    monkeypatch.setattr(trace_router, "_evidence_graph", lambda *a, **kw: passed.append(kw.get("fold")) or {})
    from database.database import SessionLocal
    db = SessionLocal()
    try:
        contrast_walk._walk(db, {"positive": [LOT], "negative": [], "hops": 2, "direction": "both", "since": None,
                                 "until": None, "node_limit": 400, "edge_limit": 1200, "follow": None,
                                 "backbone_hops": 0, "seed_type": None, "seed_limit": 200, "include_superseded": False,
                                 "world": None})
    finally:
        db.close()
    assert passed == [False]
    unfolded = ledger_subgraph.subgraph(LOT, ledger_subgraph.InMemoryEvidenceLookup(OWNER), declaration_paths=DECLARED,
                                        hops=3, backbone_hops=0, fold=False)
    plain = _walk(LOT, OWNER, declaration=PLAIN, hops=3)
    drop = lambda body: json.dumps({k: v for k, v in body.items() if k != "generated_at"}, sort_keys=True, default=str)
    assert drop(unfolded) == drop(plain)


def test_a_hub_edge_carries_the_union_of_its_member_edges_worlds():
    """M8 (QA): a hub edge's worlds are the union, sorted, of the edges it folds."""
    atoms = [ledger_subgraph.EvidenceAtom(**{**atom.__dict__, "world": "w%d" % (i % 2)})
             for i, atom in enumerate(OWNER)]
    body = _walk(LOT, atoms, hops=1)
    (edge,) = [e for e in body["edges"] if e["target"] == WAFERS]
    assert edge["worlds"] == ["w0", "w1"]
