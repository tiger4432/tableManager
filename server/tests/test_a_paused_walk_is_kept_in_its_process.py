# -*- coding: utf-8 -*-
"""총괄 54f7edfdb ㄴ-1 (소유자 «이어 걷기» · 응용 실측: 토큰이 쪽마다 자라 쪽 47 에 10 MB): a paused walk stays in the process
that walked it, under a key - `more.resume` is that key alone. Past the count the least recently used goes, unused it
goes after its minutes; the next page must ask the walk's own question; its last page lets it go; a gone walk is a
410 with why. (Which process a key goes back to is the pool's: test_a_walk_body_runs_in_a_pool_process.py.)"""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

import test_a_walk_continued_page_by_page_is_the_walk_without_caps as paged  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402
from runtime import process_pool  # noqa: E402

declared = paged.declared


def _first(declared):
    answer = paged.walk(declared, paged.ATOMS)
    assert answer["more"]["resume"] is not None, "canary: the first page was cut"
    return answer


@pytest.fixture
def cut(monkeypatch):
    monkeypatch.setattr(ledger_subgraph, "MAX_CLAIM_SCAN", 3)


def test_the_token_is_a_key_and_the_paused_walk_stays_here(declared, cut):
    first = _first(declared)
    key = first["more"]["resume"]["walk"]
    assert list(first["more"]["resume"]) == ["walk"] and key.startswith(process_pool.here() + ".")
    state = ledger_subgraph._KEPT[key]["state"]
    assert set(state["built"]) == {item["id"] for item in state["frontier"]} and state["built"], \
        "every open node is kept as built"


def test_past_the_count_the_least_recently_used_walk_goes(declared, cut, monkeypatch):
    monkeypatch.setattr(process_pool, "live_walks", lambda settings=None: 1)
    a, b = _first(declared), _first(declared)
    with pytest.raises(ledger_subgraph.WalkExpired) as gone:
        paged.walk(declared, paged.ATOMS, a["more"]["resume"])
    assert (gone.value.why, gone.value.said) == ("expired", "1 newer walks are kept in its process")
    assert paged.walk(declared, paged.ATOMS, b["more"]["resume"])["nodes"] is not None


def test_an_unused_walk_goes_after_its_minutes(declared, cut, monkeypatch):
    first = _first(declared)
    monkeypatch.setattr(process_pool, "live_minutes", lambda settings=None: 1e-9)
    time.sleep(0.05)                                            # the clock's tick on this platform is ~16 ms
    with pytest.raises(ledger_subgraph.WalkExpired) as gone:
        paged.walk(declared, paged.ATOMS, first["more"]["resume"])
    assert gone.value.why == "expired" and gone.value.said.startswith("unused for more than")


def test_a_next_page_asks_the_walk_s_own_question(declared, cut):
    first = _first(declared)
    with pytest.raises(ValueError, match="belongs to another walk"):
        ledger_subgraph.subgraph(
            paged.SEEDS, ledger_subgraph.InMemoryEvidenceLookup(paged.ATOMS), declaration_paths=declared, hops=3,
            backbone_hops=2, static_types=["quantity", "recipe"], static_follow=["leads_to"],
            node_limit=ledger_subgraph.DEFAULT_NODE_LIMIT, edge_limit=ledger_subgraph.DEFAULT_EDGE_LIMIT,
            expand=paged.EXPAND, resume=first["more"]["resume"])
    with pytest.raises(ValueError, match="more.resume as it came"):
        paged.walk(declared, paged.ATOMS, {"frontier": []})


def test_the_last_page_lets_its_walk_go(declared, cut):
    run = paged.pages(declared, paged.ATOMS, ledger_subgraph.DEFAULT_NODE_LIMIT, ledger_subgraph.DEFAULT_EDGE_LIMIT,
                      first=_first(declared))
    keys = {answer["more"]["resume"]["walk"] for answer, _held in run[:-1]}
    assert len(keys) == 1 and len(run) >= 2, "canary: one walk, paged"
    assert run[-1][0]["more"]["resume"] is None and keys.isdisjoint(ledger_subgraph._KEPT)


def test_the_route_says_a_gone_walk_as_a_410_with_why(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ledger import explorer, trace_router

    def gone(*_args, **_kwargs):
        raise ledger_subgraph.WalkExpired("expired", "unused for more than 10 min")
    monkeypatch.setattr(trace_router, "_evidence_graph", gone)
    monkeypatch.setattr(process_pool, "_settings", lambda: {"walk_processes": 0})
    app = FastAPI()
    app.include_router(trace_router.router)
    answer = TestClient(app).post("/api/ledger/subgraph", params={"id": explorer.entity_id("wafer", {"w": "W"})},
                                  json={"resume": {"walk": process_pool.here() + ".99"}})
    assert answer.status_code == 410, answer.text
    assert answer.json()["detail"] == {
        "reason": "walk_expired", "why": "expired",
        "message": "This walk expired (expired: unused for more than 10 min) - walk again"}
    assert json.loads(json.dumps(answer.json()))["detail"]["why"] in ledger_subgraph.WALK_GONE
