# -*- coding: utf-8 -*-
"""총괄 6eb3f8e76 (소유자 «collect 걸고 끝까지 가져오기»): a walk whose seeds outrun its node budget, or a type's every node
past its seed budget, goes on page by page through the one `resume` door - each seed once, to the end; and the seeds may
come in a POST body (a URL over 64 KB reaches the route with its query's last 64 KB only - httptools.parse_url keeps
offsets in 16 bits), the same question a GET asks."""
import inspect
import os
import sys
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer, trace_router  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402
from tests.test_ledger_trace_pg import ledger, ledger_engine  # noqa: E402,F401 - the shipped ledger schema

NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _shipped_declaration(monkeypatch, tmp_path):
    from tests.support.declaration import use_committed_declaration

    use_committed_declaration(monkeypatch, tmp_path)


def _atom(number, subject_keys, predicate, far=None, qualifiers=None):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="wafer", subject_keys=subject_keys, predicate=predicate,
        object_kind="entity_ref" if far else None,
        object_payload=({"type": "die", "keys": far} if far else {"qualifiers": qualifiers or {}}),
        occurred_at=NOW, source_who="t", source_translator_ver="v1", source_raw_ref="row:%d" % number,
        supersedes=None, source_event_id=str(uuid.UUID(int=10_000 + number)), source_event_state="source_molecule")


WAFERS = [{"wafer": "W%02d" % k} for k in range(23)]
ATOMS = ([_atom(k + 1, keys, "register", qualifiers={"product": "P%d" % k}) for k, keys in enumerate(WAFERS)]
         + [_atom(100 + k, keys, "inspected", far={"d": "D%02d" % k}) for k, keys in enumerate(WAFERS)]
         + [_atom(200 + k, keys, "inspected", far={"d": "SHARED"}) for k, keys in enumerate(WAFERS)])
IDS = [explorer.entity_id("wafer", keys) for keys in WAFERS]


def _pages(**kwargs):
    lookup = ledger_subgraph.InMemoryEvidenceLookup(ATOMS)
    seeds = kwargs.pop("seeds", None)
    first = ({"positive": seeds, "negative": []} if seeds else None)
    out, resume = [], None
    for _ in range(20):
        body = ledger_subgraph.subgraph(first, lookup, registration_follow={"register"}, resumable=True,
                                        **({"resume": resume} if resume else {}), **kwargs)
        out.append(body)
        resume = body["more"]["resume"]
        if not resume:
            return out
    raise AssertionError("did not end")


def _listed(pages, node_type="wafer"):
    return [n["id"] for page in pages for n in page["nodes"] if n["type"] == node_type]


def test_seeds_past_the_node_budget_come_on_the_next_pages_each_once():
    pages = _pages(seeds=IDS, hops=0, node_limit=10)
    listed = _listed(pages)
    assert len(pages) == 3 and sorted(listed) == sorted(IDS) and len(listed) == len(set(listed))
    assert [p["more"]["unexpanded"] for p in pages] == [13, 3, 0]


def test_a_type_s_every_node_page_by_page_past_its_seed_budget():
    pages = _pages(seed_type="wafer", seed_limit=5, hops=0)
    listed = _listed(pages)
    assert sorted(listed) == sorted(IDS) and len(listed) == len(set(listed)) and len(pages) == 5


def test_a_batch_cut_by_the_node_budget_goes_on_before_the_type_moves():
    pages = _pages(seed_type="wafer", seed_limit=12, hops=0, node_limit=10)
    listed = _listed(pages)
    assert sorted(listed) == sorted(IDS) and len(listed) == len(set(listed))
    assert [len(p["nodes"]) for p in pages] == [10, 2, 10, 1], "10 of the first 12, their 2, then 10 of 11, its 1"


def test_a_walk_of_steps_takes_every_seed_too():
    pages = _pages(seeds=IDS, hops=1, node_limit=10, collect=["wafer", "die"])
    assert set(_listed(pages)) == set(IDS)
    assert set(_listed(pages, "die")) == {explorer.entity_id("die", {"d": "D%02d" % k}) for k in range(23)} | {
        explorer.entity_id("die", {"d": "SHARED"})}


def test_a_node_two_pages_of_a_type_reach_is_listed_once():
    pages = _pages(seed_type="wafer", seed_limit=5, hops=1, collect=["wafer", "die"])
    shared = [n for n in _listed(pages, "die") if n == explorer.entity_id("die", {"d": "SHARED"})]
    assert len(pages) == 5 and shared == [shared[0]], "the die every wafer inspects - on the first page only"


def test_a_caller_that_does_not_go_on_is_told_how_many_wait():
    body = ledger_subgraph.subgraph({"positive": IDS, "negative": []}, ledger_subgraph.InMemoryEvidenceLookup(ATOMS),
                                    hops=0, node_limit=10, registration_follow={"register"})
    assert body["more"]["resume"] is None and body["more"]["unexpanded"] == 13 and body["truncated"]["nodes"]


def _route(monkeypatch, **asked):
    got = {}
    monkeypatch.setattr(trace_router, "_evidence_graph", lambda connection, **kwargs: got.update(kwargs) or {})
    params = inspect.signature(trace_router.evidence_subgraph).parameters
    call = {name: getattr(p.default, "default", p.default) for name, p in params.items()}
    call.update(db=SimpleNamespace(connection=lambda: None), hops=0, **asked)
    trace_router.evidence_subgraph(**call)
    return got


def test_the_body_s_seeds_are_the_query_s_question(monkeypatch):
    by_query = _route(monkeypatch, node_id=IDS[0], positive=IDS[1:], negative=[IDS[0]][:0])
    by_body = _route(monkeypatch, seeds={"id": IDS[0], "positive": IDS[1:], "negative": []})
    assert by_body["node_id"] == by_query["node_id"] == {"positive": IDS, "negative": []}
    assert by_body == by_query


@pytest.mark.parametrize("asked, reason", [
    ({"node_id": IDS[0], "seeds": {"positive": IDS}}, "seeds_defined_twice"),
    ({"positive": IDS, "seeds": {"id": IDS[0]}}, "seeds_defined_twice"),
    ({"seeds": {"positive": "not a list"}}, "subgraph_request_invalid"),
    ({"seeds": {"id": 7}}, "subgraph_request_invalid")])
def test_seeds_in_two_places_or_of_another_shape_are_refused(monkeypatch, asked, reason):
    with pytest.raises(HTTPException) as refused:
        _route(monkeypatch, **asked)
    assert refused.value.status_code == 422 and refused.value.detail["reason"] == reason


@pytest.mark.pg
def test_the_ledger_s_nodes_of_a_type_go_on_past_a_key_on_both_sides(ledger):
    """The SQL door (`gaps._nodes_of_type_sql(after=)`): both sides start past the key - a type named only as an object
    is paged too - in the key order, each node once."""
    import json as _json

    from sqlalchemy import text

    rows = []
    for k in range(10):                                 # subject side: registered
        rows.append({"id": str(uuid.uuid4()), "st": "wafer", "sk": _json.dumps({"wafer": "S%02d" % k}), "p": "register",
                     "ok": None, "op": None})
    for k in range(3):                                  # object side only: a die in it
        rows.append({"id": str(uuid.uuid4()), "st": "die", "sk": _json.dumps({"d": "D%d" % k}), "p": "in_container",
                     "ok": "entity_ref", "op": _json.dumps({"type": "wafer", "keys": {"wafer": "O%d" % k}})})
    with ledger.begin() as conn:
        conn.execute(text(
            "INSERT INTO ledger_events (id, subject_type, subject_keys, predicate, object_kind, object_payload, "
            "occurred_at, source_who, source_translator_ver, source_raw_ref, source_event_id, source_event_state) "
            "VALUES (CAST(:id AS uuid), :st, CAST(:sk AS jsonb), :p, :ok, CAST(:op AS jsonb), :at, 't', 'v1', :id, "
            "CAST(:id AS uuid), 'source_record')"), [dict(row, at=NOW) for row in rows])
    with ledger.connect() as conn:
        lookup = ledger_subgraph.SqlEvidenceLookup(conn)
        seen, after, pages = [], None, 0
        while pages < 10:
            page = lookup.subjects_of_type("wafer", 4, after=after)
            seen += page.ids
            pages += 1
            if not page.cut:
                break
            after = page.last
    expected = {explorer.entity_id("wafer", {"wafer": w}) for w in ["S%02d" % k for k in range(10)] + ["O0", "O1", "O2"]}
    assert pages == 4 and set(seen) == expected and len(seen) == len(expected)
