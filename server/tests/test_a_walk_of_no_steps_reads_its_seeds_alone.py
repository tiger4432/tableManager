# -*- coding: utf-8 -*-
"""총괄 77eb0d06f (빌더 lead-board-10 물음 1 · 2): hops=0 reads the seeds alone - each seed's own record (keys, label,
attributes), no step, no edge - for a start written by hand and for a type's all (`seed_type`). No new argument: the
range of `hops` widened; a walk of one step or more is what it was. The node cap and a continued walk stand as they do."""
import inspect
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer, trace_router  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402

NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _shipped_declaration(monkeypatch, tmp_path):
    from tests.support.declaration import use_committed_declaration

    use_committed_declaration(monkeypatch, tmp_path)


def _atom(number, subject_type, subject_keys, predicate, far=None, qualifiers=None):
    far_type, far_keys = far or (None, None)
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type=subject_type, subject_keys=subject_keys, predicate=predicate,
        object_kind="entity_ref" if far else None,
        object_payload=({"type": far_type, "keys": far_keys} if far else {"qualifiers": qualifiers or {}}),
        occurred_at=NOW, source_who="t", source_translator_ver="v1", source_raw_ref="row:%d" % number,
        supersedes=None, source_event_id=str(uuid.UUID(int=10_000 + number)), source_event_state="source_molecule")


WAFERS = [{"wafer": "W%d" % k} for k in range(12)]
ATOMS = ([_atom(k + 1, "wafer", keys, "register", qualifiers={"product": "P%d" % k}) for k, keys in enumerate(WAFERS)]
         + [_atom(100 + k, "die", {"d": "D%d" % k}, "in_container", far=("wafer", WAFERS[k])) for k in range(12)])
SEEDS = [explorer.entity_id("wafer", keys) for keys in WAFERS[:3]]


def _walk(hops, seeds=SEEDS, **kwargs):
    return ledger_subgraph.subgraph({"positive": seeds, "negative": []} if seeds else None,
                                    ledger_subgraph.InMemoryEvidenceLookup(ATOMS), hops=hops,
                                    registration_follow={"register"}, **kwargs)


def test_no_steps_answers_the_seeds_own_records_and_no_edge():
    none, one = _walk(0), _walk(1)
    assert {n["id"] for n in none["nodes"]} == set(SEEDS) and none["edges"] == []
    assert one["edges"], "the fixture has a step to take"
    by_id = {n["id"]: n for n in one["nodes"]}
    for node in none["nodes"]:
        mine = {k: node.get(k) for k in ("type", "keys", "label", "attributes")}
        assert mine == {k: by_id[node["id"]].get(k) for k in ("type", "keys", "label", "attributes")}
        assert node["attributes"]["product"].startswith("P"), "its own record came with it"
    # «depth»: the steps asked were reached - the same rule as a walk of one step (the test bed does not read it as a cut)
    cut = none["truncated"]
    assert cut["reason"] == "depth" and not any(cut[axis] for axis in ("nodes", "edges", "claims", "actions"))
    assert none["more"]["resume"] is None


def test_a_type_s_all_with_no_steps():
    body = _walk(0, seeds=None, seed_type="wafer", seed_limit=50)
    assert sorted(n["keys"]["wafer"] for n in body["nodes"]) == sorted(k["wafer"] for k in WAFERS)
    assert body["edges"] == []


def test_the_node_cap_stands():
    many = [explorer.entity_id("wafer", keys) for keys in WAFERS]
    body = _walk(0, seeds=many, node_limit=10, resumable=True)
    assert len(body["nodes"]) == 10 and body["truncated"]["nodes"] is True


def test_the_route_takes_zero_and_one_or_more_is_as_before():
    hops = inspect.signature(trace_router.evidence_subgraph).parameters["hops"].default
    bounds = {type(m).__name__: getattr(m, "ge", getattr(m, "le", None)) for m in hops.metadata}
    assert bounds.get("Ge") == 0 and hops.default == ledger_subgraph.DEFAULT_HOPS
    assert _walk(1)["edges"] == _walk(1)["edges"] and len(_walk(1)["edges"]) == 3
