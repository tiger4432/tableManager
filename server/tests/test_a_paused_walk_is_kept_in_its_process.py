# -*- coding: utf-8 -*-
"""총괄 54f7edfdb ㄴ-1 · 9752e91f7 (소유자 «이어 걷기»): a paused walk stays in the process that walked it, under a key
per page - `more.resume` is that key alone, handed only to a caller that says it will continue (`resumable`). The same
key answers the same page; the key before goes when its next is asked; the last page's stays until swept. Past the
count the least recently used walk goes, unused it goes after its minutes by the process's own clock, a reload ends
them all; the next page must ask the walk's own question; a gone walk is a 410 with why. (Which process a key goes
back to is the pool's: test_a_walk_body_runs_in_a_pool_process.py.)"""
import json
import os
import sys
import threading
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


def _next(declared, answer):
    return paged.walk(declared, paged.ATOMS, json.loads(json.dumps(answer["more"]["resume"])))


def _bytes(answer):
    """The answer's bytes but the instant it was made (`generated_at`) - a page asked again is made again."""
    return json.dumps({k: v for k, v in answer.items() if k != "generated_at"}, sort_keys=True, default=str)


def _ids(answer):
    return {node["id"] for node in answer["nodes"]}, {edge["id"] for edge in answer["edges"]}


def _merged(answers):
    nodes, edges = set(), set()
    for answer in answers:
        nodes |= _ids(answer)[0]
        edges |= _ids(answer)[1]
    return nodes, edges


@pytest.fixture
def whole(declared):
    return _ids(paged.walk(declared, paged.ATOMS))


@pytest.fixture
def cut(monkeypatch, whole):
    monkeypatch.setattr(ledger_subgraph, "MAX_CLAIM_SCAN", 3)


def test_the_token_is_a_key_and_the_paused_walk_stays_here(declared, cut):
    first = _first(declared)
    key = first["more"]["resume"]["walk"]
    assert list(first["more"]["resume"]) == ["walk"] and key.startswith(process_pool.here() + ".") and \
        key.endswith(".1")
    state = ledger_subgraph._KEPT[key]["state"]
    assert set(state["built"]) == {item["id"] for item in state["frontier"]} and state["built"], \
        "every open node is kept as built"


def test_a_cut_walk_is_kept_only_for_a_caller_that_continues(declared, cut):
    kept = dict(ledger_subgraph._KEPT)
    answer = ledger_subgraph.subgraph(
        paged.SEEDS, ledger_subgraph.InMemoryEvidenceLookup(paged.ATOMS), declaration_paths=declared, hops=2,
        backbone_hops=2, static_types=["quantity", "recipe"], static_follow=["leads_to"], expand=paged.EXPAND)
    assert answer["more"]["resume"] is None and answer["more"]["unexpanded"] > 0
    assert not all(reach["complete"] for reach in answer["more"]["reach"].values()), "it still says it was cut"
    assert ledger_subgraph._KEPT == kept


def test_the_same_key_answers_the_same_page_and_leaves_its_state_as_it_was(declared, cut):
    first = _first(declared)
    state = ledger_subgraph._KEPT[first["more"]["resume"]["walk"]]["state"]
    before = _bytes(state)
    second = _next(declared, first)
    assert _bytes(state) == before, "a page wrote into the state its key names"
    again = _next(declared, first)                          # × then More, More twice, a retry
    assert _bytes(again) == _bytes(second)


def test_two_at_once_with_one_key_answer_the_same_page(declared, cut):
    first, out = _first(declared), {}
    both = [threading.Thread(target=lambda name=name: out.setdefault(name, _next(declared, first)))
            for name in ("a", "b")]
    for each in both:
        each.start()
    for each in both:
        each.join()
    assert _bytes(out["a"]) == _bytes(out["b"])


def test_the_key_before_goes_when_its_next_is_asked(declared, cut):
    first = _first(declared)
    second = _next(declared, first)
    third = _next(declared, second)
    assert _bytes(_next(declared, second)) == _bytes(third), "the key asked last still answers"
    with pytest.raises(ledger_subgraph.WalkExpired) as gone:
        _next(declared, first)                              # × twice, then More
    assert (gone.value.why, gone.value.said) == ("expired", "a later page of this walk was asked")


@pytest.mark.parametrize("where", ["after the page was kept", "while the page was walked"])
def test_a_page_that_failed_asked_again_leaves_no_hole(declared, cut, whole, monkeypatch, where):
    seat = "_keep_walk" if where == "after the page was kept" else "_walk"
    real, failed = getattr(ledger_subgraph, seat), []

    def once(*args, **kwargs):
        answer = real(*args, **kwargs)
        if not failed and kwargs.get("resume", args[0] if seat == "_keep_walk" else None) is not None:
            failed.append(1)
            raise RuntimeError("the answer did not reach the screen")
        return answer

    monkeypatch.setattr(ledger_subgraph, seat, once)
    answers = [_first(declared)]
    while answers[-1]["more"]["resume"] is not None:
        try:
            answers.append(_next(declared, answers[-1]))
        except RuntimeError:
            continue                                         # the screen asks the same key again
    assert failed and len(answers) >= 3, "canary: a continued page failed once, the walk went on"
    assert _merged(answers) == whole


def test_the_last_page_s_key_answers_the_last_page_until_swept(declared, cut, monkeypatch):
    run = [_first(declared)]
    while run[-1]["more"]["resume"] is not None:
        run.append(_next(declared, run[-1]))
    assert len(run) >= 3, "canary: one walk, paged"
    assert _bytes(_next(declared, run[-2])) == _bytes(run[-1])
    monkeypatch.setattr(process_pool, "live_minutes", lambda settings=None: 1e-9)
    time.sleep(0.05)                                        # the clock's tick on this platform is ~16 ms
    with pytest.raises(ledger_subgraph.WalkExpired) as gone:
        _next(declared, run[-2])
    assert gone.value.why == "expired"


def test_past_the_count_the_least_recently_used_walk_goes(declared, cut, monkeypatch):
    monkeypatch.setattr(process_pool, "live_walks", lambda settings=None: 1)
    a, b = _first(declared), _first(declared)
    with pytest.raises(ledger_subgraph.WalkExpired) as gone:
        _next(declared, a)
    assert (gone.value.why, gone.value.said) == ("expired", "1 newer walks are kept in its process")
    assert _next(declared, _next(declared, b))["nodes"] is not None, "one walk's two keys count as one walk"


def test_an_unused_walk_goes_after_its_minutes_by_the_process_s_clock(declared, cut, monkeypatch):
    monkeypatch.setattr(ledger_subgraph, "SWEEP_SECONDS", 0.05)
    monkeypatch.setattr(ledger_subgraph, "_SWEEPER", [None])          # a clock that ticks at the patched pace
    monkeypatch.setattr(process_pool, "live_minutes", lambda settings=None: 1e-9)
    key = _first(declared)["more"]["resume"]["walk"]
    for _ in range(100):
        if key in ledger_subgraph._GONE:
            break
        time.sleep(0.02)
    assert ledger_subgraph._GONE.get(key, ("", ""))[0] == "expired" and key not in ledger_subgraph._KEPT


def test_a_walk_being_walked_is_not_swept(declared, cut, monkeypatch):
    key = _first(declared)["more"]["resume"]["walk"]
    walk = ledger_subgraph._KEPT[key]["walk"]
    ledger_subgraph._WALKS[walk]["lock"].acquire()
    monkeypatch.setattr(process_pool, "live_minutes", lambda settings=None: 1e-9)
    time.sleep(0.05)
    try:
        with ledger_subgraph._KEPT_LOCK:
            ledger_subgraph._sweep_kept()
        assert key in ledger_subgraph._KEPT
    finally:
        ledger_subgraph._WALKS[walk]["lock"].release()
    with ledger_subgraph._KEPT_LOCK:
        ledger_subgraph._sweep_kept()
    assert key not in ledger_subgraph._KEPT


def test_past_the_count_a_walk_being_walked_and_the_newest_stay(declared, cut, monkeypatch):
    monkeypatch.setattr(process_pool, "live_walks", lambda settings=None: 1)
    a = _first(declared)["more"]["resume"]["walk"]
    walk_a = ledger_subgraph._KEPT[a]["walk"]
    ledger_subgraph._WALKS[walk_a]["lock"].acquire()
    try:
        b = _first(declared)["more"]["resume"]["walk"]
        assert {a, b} <= set(ledger_subgraph._KEPT), "A is being walked, B is the newest"
    finally:
        ledger_subgraph._WALKS[walk_a]["lock"].release()
    c = _first(declared)["more"]["resume"]["walk"]
    assert c in ledger_subgraph._KEPT and not {a, b} & set(ledger_subgraph._KEPT)


def test_a_reload_ends_the_kept_walks(declared, cut):
    first = _first(declared)
    ledger_subgraph.reset_declaration_cache()
    with pytest.raises(ledger_subgraph.WalkExpired) as gone:
        _next(declared, first)
    assert gone.value.why == "reloaded"


@pytest.mark.parametrize("asked", [
    {"hops": 3}, {"worlds": ("other",)}, {"since": "2020-01-01T00:00:00+00:00"},
    {"until": "2030-01-01T00:00:00+00:00"}, {"current_only": False}])
def test_a_next_page_asks_the_walk_s_own_question(declared, cut, asked):
    first = _first(declared)
    lookup = ledger_subgraph.InMemoryEvidenceLookup(paged.ATOMS)
    for name in ("worlds", "since", "until", "current_only"):
        if name in asked:
            setattr(lookup, name, asked[name])
    with pytest.raises(ValueError, match="belongs to another walk"):
        ledger_subgraph.subgraph(
            paged.SEEDS, lookup, declaration_paths=declared, hops=asked.get("hops", 2), backbone_hops=2,
            static_types=["quantity", "recipe"], static_follow=["leads_to"],
            node_limit=ledger_subgraph.DEFAULT_NODE_LIMIT, edge_limit=ledger_subgraph.DEFAULT_EDGE_LIMIT,
            expand=paged.EXPAND, resume=first["more"]["resume"])
    with pytest.raises(ValueError, match="more.resume as it came"):
        paged.walk(declared, paged.ATOMS, {"frontier": []})


def test_the_seed_is_drawn_on_every_page(declared, cut):
    run = [_first(declared)]
    while run[-1]["more"]["resume"] is not None:
        run.append(_next(declared, run[-1]))

    def on_this_page(answer):
        seed = answer["seed"]["id"]
        return len({edge["claim_id"] for edge in answer["edges"]
                    if edge.get("claim_id") and seed in (edge["source"], edge["target"])})

    counts = [on_this_page(answer) for answer in run]
    assert len(run) >= 3 and len(set(counts)) > 1, ("canary: the seed's claims differ page by page", counts)
    assert [(answer["seed"]["depth"], answer["seed"]["claim_count"]) for answer in run] == [(0, n) for n in counts]


def _route(monkeypatch, **request):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ledger import explorer, trace_router

    asked = {}

    def walked(*_args, **kwargs):
        asked.update(kwargs)
        if kwargs.get("resume"):
            raise ledger_subgraph.WalkExpired("expired", "unused for more than 10 min")
        return {"rows": ""} if kwargs.get("rows") else {"nodes": []}
    monkeypatch.setattr(trace_router, "_evidence_graph", walked)
    monkeypatch.setattr(process_pool, "_settings", lambda: {"walk_processes": 0})
    app = FastAPI()
    app.include_router(trace_router.router)
    params = {"id": explorer.entity_id("wafer", {"w": "W"}), **request.pop("params", {})}
    return TestClient(app).request(request.pop("method", "GET"), "/api/ledger/subgraph", params=params,
                                   **request), asked


@pytest.mark.parametrize("request_, resumable", [
    ({}, False), ({"params": {"resumable": "true"}}, True), ({"params": {"resumable": "true", "format": "rows"}}, False),
    ({"method": "POST", "params": {"resumable": "true"}, "json": {}}, True)])
def test_the_route_hands_resumable_on_as_asked(monkeypatch, request_, resumable):
    answer, asked = _route(monkeypatch, **request_)
    assert answer.status_code == 200 and asked["resumable"] is resumable, (answer.text, asked)


def test_the_route_says_a_gone_walk_as_a_410_with_why(monkeypatch):
    answer, _asked = _route(monkeypatch, method="POST",
                            json={"resume": {"walk": process_pool.here() + ".0123456789abcdef.2"}})
    assert answer.status_code == 410, answer.text
    assert answer.json()["detail"] == {
        "reason": "walk_expired", "why": "expired",
        "message": "This walk expired (expired: unused for more than 10 min) - walk again"}
    assert json.loads(json.dumps(answer.json()))["detail"]["why"] in ledger_subgraph.WALK_GONE
