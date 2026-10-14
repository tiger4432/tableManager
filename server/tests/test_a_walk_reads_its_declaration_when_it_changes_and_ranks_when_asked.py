# -*- coding: utf-8 -*-
"""총괄 9166099d4 (소유자 «ㅇㅇ 진행해», B 의 걷기 스캔 재기): a walk request read and checked its declaration four to six
times (19.6 ms each on the box's) - now its files are read again only when one changes, by the follow-up's own stamp
rule (`worker._stamped`); and a caller that does not read the ranking says `propagation=false` and is not made to wait
for it (70 % of a 200-seed value walk). The default is today's: ranked."""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer  # noqa: E402
from ledger import trace_router, worker  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402


@pytest.fixture
def root(monkeypatch, tmp_path):
    from tests.support.declaration import use_committed_declaration

    return use_committed_declaration(monkeypatch, tmp_path)


def _bump(path):
    """The file written again and stamped later - what an activation does."""
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    stamp = os.stat(path).st_mtime + 5
    os.utime(path, (stamp, stamp))


def test_the_stamp_rule_builds_once_a_stamp_and_holds_a_failure(tmp_path):
    a = tmp_path / "a.json"
    a.write_text("1", encoding="utf-8")
    built = []

    def build():
        built.append(a.read_text(encoding="utf-8"))
        if "bad" in built[-1]:
            raise ValueError("bad file")
        return built[-1]

    assert [worker._stamped("k", (a,), build) for _ in range(3)] == ["1", "1", "1"] and len(built) == 1
    a.write_text("bad", encoding="utf-8")
    os.utime(a, (os.stat(a).st_mtime + 5,) * 2)
    for _ in range(2):
        with pytest.raises(ValueError, match="bad file"):
            worker._stamped("k", (a,), build)
    assert len(built) == 2, "the same files fail the same way - not read again"
    raised = []
    for _ in range(2):
        try:
            worker._stamped("k", (a,), build)
        except ValueError as exc:
            raised.append(exc)
    assert raised[0] is not raised[1] and str(raised[0]) == str(raised[1]) == "bad file", "raised anew each time"
    assert not any(isinstance(part, BaseException) for part in worker._COMPILED["k"]), "no exception object is held"
    a.write_text("2", encoding="utf-8")
    os.utime(a, (os.stat(a).st_mtime + 10,) * 2)
    assert worker._stamped("k", (a,), build) == "2" and len(built) == 3


def test_a_walk_request_reads_its_declaration_once_until_a_file_changes(root, monkeypatch):
    from ledger import config as ledger_config

    reads = []
    real = ledger_config.load
    monkeypatch.setattr(ledger_config, "load", lambda *a, **k: reads.append(a) or real(*a, **k))
    first = trace_router._declaration()
    for _ in range(5):
        trace_router._static_types()
        trace_router._predicate_cardinalities()
        trace_router._self_describing_predicates()
    assert len(reads) == 1 and trace_router._declaration() == first

    declaration = root / "ontology" / "ledger_config.json"
    document = json.loads(declaration.read_text(encoding="utf-8"))
    document["entities"]["probe_b@1"] = {"keys": ["k"]}
    declaration.write_text(json.dumps(document), encoding="utf-8")
    os.utime(declaration, (os.stat(declaration).st_mtime + 5,) * 2)
    assert "probe_b" in trace_router._declaration()["entities"], "an edited file is read at once - no reload"
    assert len(reads) == 2

    _bump(root / "table_config.json")
    trace_router._declaration()
    assert len(reads) == 3, "the catalogue it is checked against is in the stamp too"


def test_the_follow_up_s_compile_keeps_its_stamp_rule(root, monkeypatch):
    from ledger import setup

    compiles = []
    monkeypatch.setattr(setup, "load_setup", lambda path: compiles.append(path) or object())
    worker._compiled_setup(None)
    worker._compiled_setup(None)
    trace_router._declaration()
    assert len(compiles) == 1, "the route's read does not take the compile's seat, nor the compile the route's"
    _bump(root / "ontology" / "ledger_config.json")
    worker._compiled_setup(None)
    assert len(compiles) == 2


NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)
SEEDS = [explorer.entity_id("die", {"d": "D%d" % k}) for k in range(3)]
MANY = [explorer.entity_id("die", {"d": "D%d" % k}) for k in range(12)]


def _atom(number, subject_type, subject_keys, predicate, far_type, far_keys):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type=subject_type, subject_keys=subject_keys,
        predicate=predicate, object_kind="entity_ref", object_payload={"type": far_type, "keys": far_keys},
        occurred_at=NOW, source_who="t", source_translator_ver="v1", source_raw_ref="row:%d" % number,
        supersedes=None, source_event_id=str(uuid.UUID(int=10_000 + number)), source_event_state="source_molecule")


ATOMS = ([_atom(k + 1, "die", {"d": "D%d" % k}, "in_container", "wafer", {"w": "W"}) for k in range(12)]
         + [_atom(100 + k, "die", {"d": "D%d" % k}, "observed", "defect", {"x": "X%d" % k}) for k in range(12)])


def _walk(seeds=SEEDS, **kwargs):
    return ledger_subgraph.subgraph({"positive": seeds, "negative": []}, ledger_subgraph.InMemoryEvidenceLookup(ATOMS),
                                    hops=3, **kwargs)


def _same(body):
    return {k: v for k, v in body.items() if k not in ("generated_at", "propagation")}


def test_a_walk_not_ranked_answers_the_same_but_the_ranking(root):
    ranked, plain = _walk(), _walk(propagation=False)
    assert "propagation" in ranked and ranked["propagation"].get("ranked"), "the fixture ranks something"
    assert "propagation" not in plain, "not asked - not there (not null)"
    assert _same(plain) == _same(ranked)


def test_a_next_page_asks_with_the_same_value(root):
    first = _walk(MANY, propagation=False, node_limit=10, resumable=True)
    resume = first["more"]["resume"]
    assert resume, "the fixture cuts the walk"
    with pytest.raises(ValueError, match="another walk"):
        _walk(MANY, propagation=True, node_limit=10, resume=resume)
    second = _walk(MANY, propagation=False, node_limit=10, resume=resume)
    assert "propagation" not in second and second["nodes"]


@pytest.mark.parametrize("asked, handed", [(False, False), (True, True), (None, True)])
def test_the_route_hands_the_walk_whether_to_rank(monkeypatch, asked, handed):
    from fastapi.params import Query

    from ledger import trace as ledger_trace

    monkeypatch.setattr(ledger_trace, "relation_exists", lambda *a, **k: True)
    monkeypatch.setattr(trace_router, "_subgraph_contract_state", lambda *a, **k: [])
    got = {}
    monkeypatch.setattr(ledger_subgraph, "subgraph", lambda *args, **kwargs: got.update(kwargs) or {})
    trace_router._evidence_graph(object(), node_id=SEEDS[0], hops=1, direction="both", node_limit=10, edge_limit=10,
                                 **({} if asked is None else {"propagation": asked}))
    assert got["propagation"] is handed
    # the route itself: a direct call leaves FastAPI's Query sentinel - the ranking, as before
    import inspect
    default = inspect.signature(trace_router.evidence_subgraph).parameters["propagation"].default
    assert isinstance(default, Query) and default.default is True


@pytest.mark.parametrize("asked, handed", [(False, False), (True, True), ("sentinel", True)])
def test_the_route_reads_the_argument_as_it_came(root, monkeypatch, asked, handed):
    """The handler itself: `propagation=false` is the only thing that turns the ranking off - a direct call's Query
    sentinel ranks, as before."""
    import inspect
    from types import SimpleNamespace

    got = {}
    monkeypatch.setattr(trace_router, "_evidence_graph", lambda connection, **kwargs: got.update(kwargs) or {})
    params = inspect.signature(trace_router.evidence_subgraph).parameters
    call = {name: getattr(p.default, "default", p.default) for name, p in params.items()}
    call.update(node_id=SEEDS[0], db=SimpleNamespace(connection=lambda: None),
                propagation=params["propagation"].default if asked == "sentinel" else asked)
    trace_router.evidence_subgraph(**call)
    assert got["propagation"] is handed


def test_one_walk_reads_the_declaration_facts_once(root, monkeypatch):
    """The walk's facts (key order, labels, plural names, steps) - read once at its start by the stamp rule and held for
    that walk (`_WALK_FACTS`): not a stat per node, and one revision for the whole walk. Outside a walk: the rule."""
    asked = []
    real = worker._stamped
    monkeypatch.setattr(worker, "_stamped", lambda key, paths, build: asked.append(key[0]) or real(key, paths, build))
    body = _walk(MANY)
    assert body["nodes"] and asked.count("facts") == 1, asked
    assert ledger_subgraph._WALK_FACTS.get() is None, "unbound after the walk"
    ledger_subgraph._read_entity_declaration()
    assert asked.count("facts") == 2
