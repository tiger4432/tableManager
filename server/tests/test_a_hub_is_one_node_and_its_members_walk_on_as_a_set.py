# -*- coding: utf-8 -*-
"""A hub is a set node (소유자 10-27 «허브 = 집합 노드», 총괄 eda0c65c7): a step from one node along one predicate and
direction folds into one hub - every step of a predicate declared `hub`, or the far nodes past `fanout_limit` - and the
members walk on as a set, in the depth's one read.

  one seat     `_folds`: declared, or past the limit; a step `expand` opened (a hub id too) is drawn unfolded
  the node     type = the members' domain type, a label a person reads, the hub cell (near end · predicate ·
               direction · count · the ledger's count · sample), the same id on every walk
  the set      the folded walk reaches what the unfolded one reaches, in as many reads; a set's step to many folds again
  the count    the ledger's - a read the atom cap cut says «of N in the ledger»
  unchanged    group_by · measure; a walk with no hub is the walk it was (no new key)
  value        members of one step split by the value they share - the contrast's reach, the aux verdict (10-12)
"""
import json
import uuid
from datetime import datetime, timezone

import pytest

import validation
from ledger import explorer, setup_bundle, trace_router, walk_cards
from ledger_api import ledger_subgraph

pytestmark = pytest.mark.usefixtures("stored_walks")   # a stored-only ledger fixture (11-10)


@pytest.fixture(autouse=True)
def _shipped_declaration(monkeypatch, tmp_path_factory):
    """The repository's declaration and catalogue, not the box's gitignored files (총괄 10-14)."""
    from tests.support.declaration import use_committed_declaration

    use_committed_declaration(monkeypatch, tmp_path_factory.mktemp("shipped"))

NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)
DIES = 30
WAFER = explorer.entity_id("wafer", {"w": "W"})


def _atom(n, subject_type, subject_keys, predicate, far_type, far_keys, **qualifiers):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=n)), subject_type=subject_type, subject_keys=subject_keys, predicate=predicate,
        object_kind="entity_ref", object_payload={"type": far_type, "keys": far_keys,
                                                  **({"qualifiers": qualifiers} if qualifiers else {})},
        occurred_at=NOW, source_who="t", source_translator_ver="v1", source_raw_ref="row:%d" % n, supersedes=None,
        source_event_id=str(uuid.UUID(int=100_000 + n)), source_event_state="source_molecule")


def _wafer(dies=DIES, defects=5):
    """One wafer inspecting `dies` dies, each die observing one of `defects` defects."""
    atoms = []
    for k in range(dies):
        atoms.append(_atom(1 + k, "wafer", {"w": "W"}, "inspected", "die", {"d": "D%d" % k}))
        atoms.append(_atom(10_000 + k, "die", {"d": "D%d" % k}, "observed", "defect", {"f": "F%d" % (k % defects)}))
    return atoms


def _walk(atoms, seed=WAFER, **kwargs):
    return ledger_subgraph.subgraph(seed, ledger_subgraph.InMemoryEvidenceLookup(atoms), **kwargs)


def _hubs(body):
    return {n["id"]: n for n in body["nodes"] if "hub" in n}


def _plain_ids(body):
    return {n["id"] for n in body["nodes"] if "hub" not in n}


def _dies():
    return {explorer.entity_id("die", {"d": "D%d" % k}) for k in range(DIES)}


def test_a_declared_predicate_folds_its_step_into_one_hub():
    body = _walk(_wafer(), hops=1, hubs={"inspected"})
    (hub,) = _hubs(body).values()
    assert hub["id"] == ledger_subgraph.hub_step_id(WAFER, "inspected", "outgoing", "die") + "|"
    assert (hub["type"], hub["label"]) == ("die", "die × %d via inspected" % DIES)
    assert {k: hub["hub"][k] for k in ("near", "predicate", "direction", "far_type", "count", "in_ledger")} == {
        "near": WAFER, "predicate": "inspected", "direction": "outgoing", "far_type": "die", "count": DIES,
        "in_ledger": DIES}
    assert _plain_ids(body) == {WAFER}, "no member stands as a node"
    (edge,) = body["edges"]
    assert (edge["source"], edge["target"], edge["count"]) == (WAFER, hub["id"], DIES)
    assert ledger_subgraph.hub_cells(hub["id"]) == {"near": WAFER, "predicate": "inspected",
                                                   "direction": "outgoing", "far_type": "die", "value": ""}
    assert body["bundles"] == [{"node": WAFER, "predicate": "inspected", "direction": "outgoing", "far_type": "die",
                                "count": DIES, "drawn": 0, "hubs": [hub["id"]]}]
    again = _walk(_wafer(), hops=1, hubs={"inspected"})
    assert set(_hubs(again)) == {hub["id"]}, "the same step folds to the same id"


def test_a_declared_hub_folds_one_member_too():
    (hub,) = _hubs(_walk(_wafer(dies=1), hops=1, hubs={"inspected"})).values()
    assert hub["hub"]["count"] == 1


def test_past_the_limit_the_first_are_drawn_and_the_rest_are_one_hub_with_its_sample():
    body = _walk(_wafer(), hops=1, fanout_limit=4)
    (hub,) = _hubs(body).values()
    assert (len(_plain_ids(body) - {WAFER}), hub["hub"]["count"]) == (4, DIES - 4)
    assert len(hub["hub"]["sample"]) == 4 and set(hub["hub"]["sample"]) <= _dies() - _plain_ids(body)
    assert _walk(_wafer(), hops=1, fanout_limit=DIES).get("bundles") == [], "the limit is exceeded, not reached"


def test_the_walk_card_counts_each_member_once_and_names_the_hub():
    body = _walk(_wafer(), hops=1, fanout_limit=4)
    (item,) = walk_cards.edges(walk_cards.Sight(at=[WAFER], answer=body), 10)["items"]
    assert item["count"] == DIES and set(_hubs(body)) <= set(item["sample"]), item


def test_the_members_walk_on_as_a_set_and_reach_what_the_unfolded_walk_reaches():
    folded = _walk(_wafer(), hops=2, hubs={"inspected"})
    unfolded = _walk(_wafer(), hops=2)
    assert _plain_ids(folded) | _dies() == {n["id"] for n in unfolded["nodes"]}
    (hub,) = _hubs(folded).values()
    onward = {(e["source"], e["predicate"], e["target"]): e.get("count") for e in folded["edges"]}
    defects = {explorer.entity_id("defect", {"f": "F%d" % k}) for k in range(5)}
    assert {(hub["id"], "observed", f): DIES // 5 for f in defects}.items() <= onward.items(), \
        "each defect is reached from the set, its edge counting the members that observed it"


def test_the_members_go_on_in_the_depths_one_read():
    def reads(**kwargs):
        lookup = ledger_subgraph.InMemoryEvidenceLookup(_wafer())
        calls, read = [], lookup.claims_for_entities
        lookup.claims_for_entities = lambda *a, **k: calls.append(len(a[0])) or read(*a, **k)
        ledger_subgraph.subgraph(WAFER, lookup, hops=2, propagation=False, **kwargs)
        return calls
    assert reads(hubs={"inspected"}) == reads(), "a set's step is one read of every member, as unfolded"


def test_a_sets_step_to_many_folds_again_its_near_end_the_hub_it_went_on_from():
    atoms = _wafer(defects=DIES)                    # each die its own defect: the set's step reaches thirty
    body = _walk(atoms, hops=2, hubs={"inspected"}, fanout_limit=10)
    step = ledger_subgraph.hub_step_id(WAFER, "inspected", "outgoing", "die")
    (onward,) = [hub for hub in _hubs(body).values() if hub["hub"]["near"] == step]
    assert (onward["type"], onward["hub"]["predicate"], onward["hub"]["count"]) == ("defect", "observed", DIES - 10)
    assert onward["hub"]["in_ledger"] == DIES, "counted from every member of the set"
    assert ledger_subgraph.hub_cells(onward["id"])["near"] == step


def test_a_hubs_count_is_the_ledgers_when_the_atom_cap_cut_the_read():
    many = 300
    body = _walk(_wafer(dies=many), hops=1, hubs={"inspected"}, edge_limit=20)      # claims: 200
    (hub,) = _hubs(body).values()
    assert body["truncated"]["claims"] is True
    assert hub["hub"]["in_ledger"] == many > hub["hub"]["count"]
    assert hub["label"] == "die × %d via inspected (of %d in the ledger)" % (hub["hub"]["count"], many)


def test_group_by_and_measure_are_the_unfolded_walks():
    asked = dict(hops=2, group_by="type", measure=["Count"])
    assert _walk(_wafer(), hubs={"inspected"}, **asked)["groups"] == _walk(_wafer(), **asked)["groups"]


def test_a_hub_id_opens_its_step():
    folded = _walk(_wafer(), hops=2, hubs={"inspected"})
    (hub,) = _hubs(folded)
    opened = _walk(_wafer(), hops=2, hubs={"inspected"}, expand=[hub])
    plain = _walk(_wafer(), hops=2)
    for body in (opened, plain):
        body.pop("generated_at")
        body.pop("bundles", None)
    assert opened == plain


def test_no_hub_no_new_key():
    """The control: no declared hub and no limit - not a cell of the answer moves (byte-equal to the walk before hubs,
    measured on the box against a63712842 with scratch walks; here, the keys a hub adds are absent)."""
    body = _walk(_wafer(), hops=2, hubs=set(), node_limit=10, resumable=True)
    text = json.dumps(body, default=str)
    assert "bundles" not in body and ledger_subgraph.HUBS_STATE not in body and "hub|" not in text
    assert '"hub"' not in text


def test_an_aux_verdict_splits_a_hub():
    """`_fold_hubs` after the aux verdicts: members found and members with none stand in two hubs (10-12)."""
    step = ledger_subgraph.hub_step_id("N", "p", "outgoing", "t")
    payload = {"walk": {"start": {"positive": 1, "negative": 0}}, "edges": [],
               "nodes": [{"id": i, "type": "t", "label": i, "node_kind": "entity", "depth": 1,
                          "aux": {"state": "found" if i == "a" else "none"}} for i in "abc"]}
    ledger_subgraph._fold_hubs(payload, {"members": dict.fromkeys("abc", step), "steps": {step: {
        "near": "N", "predicate": "p", "direction": "outgoing", "far_type": "t"}}}, None)
    assert {n["hub"]["value"]: n["hub"]["count"] for n in payload["nodes"]} == {"found": 1, "none": 2}


def test_a_contrast_splits_a_hub_by_the_reach_its_members_share():
    """`_fold_hubs` over a contrast answer: members ranked at two reaches stand in two hubs; the ranking lists each
    hub once, where its first member stood."""
    step = ledger_subgraph.hub_step_id("N", "p", "outgoing", "t")
    payload = {"walk": {"start": {"positive": 1, "negative": 1}}, "edges": [],
               "nodes": [{"id": i, "type": "t", "label": i, "node_kind": "entity", "depth": 1} for i in "abc"],
               "propagation": {"ranked": [{"id": "a", "reach": [1, 0]}, {"id": "b", "reach": [1, 1]},
                                          {"id": "c", "reach": [1, 0]}], "top_set": ["a", "c"]}}
    ids = ledger_subgraph._fold_hubs(payload, {"members": dict.fromkeys("abc", step), "steps": {step: {
        "near": "N", "predicate": "p", "direction": "outgoing", "far_type": "t"}}}, None)
    assert ids == {"a": step + "|1,0", "b": step + "|1,1", "c": step + "|1,0"}
    assert [item["id"] for item in payload["propagation"]["ranked"]] == [step + "|1,0", step + "|1,1"]
    assert payload["propagation"]["top_set"] == [step + "|1,0"]


def test_a_continued_walk_keeps_each_member_in_its_hub():
    atoms = _wafer(dies=60, defects=60)
    first = _walk(atoms, hops=2, hubs={"inspected"}, edge_limit=20, resumable=True)          # claims: 200
    pages, resume = [first], first["more"]["resume"]
    while resume:
        page = _walk(atoms, hops=2, hubs={"inspected"}, edge_limit=20, resume=resume)
        pages.append(page)
        resume = page["more"]["resume"]
    assert len(pages) > 1
    members = {explorer.entity_id("die", {"d": "D%d" % k}) for k in range(60)}
    for page in pages:
        assert not members & _plain_ids(page), "a member never stands as a node"
        assert not {endpoint for e in page["edges"] for endpoint in (e["source"], e["target"])} & members
    step = ledger_subgraph.hub_step_id(WAFER, "inspected", "outgoing", "die")
    assert {hub for page in pages for hub in _hubs(page) if hub.startswith(step + "|")} == {step + "|"}


def test_a_bound_follow_walks_a_hubs_members_as_the_unfolded_walk_does():
    atoms = [_atom(1 + k, "wafer", {"w": "W%d" % k}, "processed_at", "step", {"s": "S"}, tx_id="T%d" % (k % 2))
             for k in range(12)]
    seed = explorer.entity_id("wafer", {"w": "W0"})
    asked = dict(hops=2, follow=["processed_at"], follow_keys={"processed_at": ("tx_id",)},
                 follow_qualifiers={"processed_at": ["tx_id"]})
    folded, plain = _walk(atoms, seed, hubs={"processed_at"}, **asked), _walk(atoms, seed, **asked)
    reached = {n["id"] for n in plain["nodes"]}
    (step, wafers) = sorted(_hubs(folded).values(), key=lambda hub: hub["hub"]["near"] != seed)
    assert (step["hub"]["count"], wafers["hub"]["count"]) == (1, 5), "the step, then T0's other wafers - not T1's"
    assert step["hub"]["count"] + wafers["hub"]["count"] == len(reached - _plain_ids(folded))


def test_the_hub_cell_is_true_or_false_and_only_true_folds():
    assert setup_bundle.hub_predicates({"a@1": {"hub": True}, "b@1": {"hub": False}, "c@1": {}}) == {"a"}
    problems = validation.Problems()
    setup_bundle._validate_vocabulary({"a@1": {"status": "active", "subjects": ["x@1"], "hub": "yes",
                                               "object": {"kind": "none", "qualifiers": {"required": [],
                                                                                         "optional": []}}}},
                                      problems)
    said = [issue.to_mapping() for issue in problems.finish()]
    assert [i["message"] for i in said if i["path"] == "bundle.vocabulary.a@1.hub"] == ["must be true or false"], said


def test_the_route_reads_the_declared_hubs_and_hands_them_to_the_walk(monkeypatch):
    monkeypatch.setattr(trace_router, "_declaration", lambda world=None: {"vocabulary": {
        "inspected@1": {"hub": True}, "observed@1": {"hub": False}}})
    assert trace_router._hub_predicates() == {"inspected"}
    seen = {}
    monkeypatch.setattr(trace_router, "_ledgers_present", lambda *a: None)
    monkeypatch.setattr(trace_router, "_subgraph_contract_state", lambda *a: [])
    monkeypatch.setattr(ledger_subgraph, "subgraph", lambda *a, **k: seen.update(k) or {})
    trace_router._evidence_graph(None, node_id=WAFER, hops=1, direction="both", node_limit=400, edge_limit=6000)
    assert seen["hubs"] == {"inspected"}


# ------------------------------------------------- on PostgreSQL, the operating shape (총괄 eda0c65c7)

from tests.test_ledger_trace_pg import ledger_engine  # noqa: E402,F401 - the shipped ledger schema

PG_MEMBERS = 10_000
PG_WAFER = explorer.entity_id("wafer", {"wafer": "W1"})


@pytest.fixture(name="pg_hub")
def fixture_pg_hub(request):
    """One wafer; `PG_MEMBERS` defects `on_wafer` it - one hop to ten thousand."""
    from sqlalchemy import text
    from tests.test_ledger_trace_pg import insert

    engine = request.getfixturevalue("ledger_engine")
    rows = [{"id": str(uuid.uuid4()), "st": "defect", "sk": json.dumps({"defect": "F%05d" % k}), "p": "on_wafer",
             "ok": "entity_ref", "op": json.dumps({"type": "wafer", "keys": {"wafer": "W1"}}), "oa": NOW,
             "who": "hub", "ver": "hub/1", "raw": "d:%d" % k, "sup": None} for k in range(PG_MEMBERS)]
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE ledger_events"))
        for start in range(0, len(rows), 5000):
            insert(conn, rows[start:start + 5000])

    def walk(**kw):
        with engine.connect() as conn:
            return ledger_subgraph.subgraph(PG_WAFER, ledger_subgraph.SqlEvidenceLookup(conn), hops=1, **kw)
    try:
        yield walk
    finally:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE ledger_events"))


@pytest.mark.pg
def test_ten_thousand_in_one_hop_are_one_hub_counted_by_the_ledger(pg_hub):
    import time

    timed = {}
    for name, kw in (("plain", {}), ("hub", {"hubs": {"on_wafer"}}), ("limit", {"fanout_limit": 20})):
        started = time.perf_counter()
        timed[name] = (pg_hub(**kw), time.perf_counter() - started)
    for name, (body, seconds) in timed.items():
        print("hub-box %-5s %.3f s nodes %d edges %d claims %d" % (
            name, seconds, len(body["nodes"]), len(body["edges"]), body["walk"]["claims_scanned"]))

    body = timed["hub"][0]
    (hub,) = _hubs(body).values()
    read = hub["hub"]["count"]
    assert read == ledger_subgraph.MAX_CLAIM_SCAN and body["truncated"]["claims"] is True   # the atom cap cut the read
    assert hub["hub"]["in_ledger"] == PG_MEMBERS, "the count is the ledger's, not the read's"
    assert hub["label"] == "defect \u00d7 %d via on_wafer (of %d in the ledger)" % (read, PG_MEMBERS)
    assert (_plain_ids(body), len(body["edges"])) == ({PG_WAFER}, 1)

    limited = timed["limit"][0]
    (rest,) = _hubs(limited).values()
    assert len(_plain_ids(limited)) == 1 + 20 and len(rest["hub"]["sample"]) == 20
    assert rest["hub"]["in_ledger"] == PG_MEMBERS

    plain = timed["plain"][0]
    assert not _hubs(plain) and "bundles" not in plain                      # no hub: as before
