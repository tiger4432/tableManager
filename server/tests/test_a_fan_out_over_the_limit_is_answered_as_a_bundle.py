# -*- coding: utf-8 -*-
"""Walk control ㄴ (총괄 c9bf53033): a step from one node along one predicate and direction to
more than `fanout_limit` nodes is not drawn - `bundles` says it, with its count.

The count is taken over the steps the walk's guards pass (`_step`), so it is what expanding
that bundle draws. A bundle is not a node and not a truncation.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402

NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)
DIES = 25
WAFER = explorer.entity_id("wafer", {"w": "W"})
SEED = explorer.entity_id("die", {"d": "D0"})


def _atom(number, subject_type, subject_keys, predicate, far_type, far_keys):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type=subject_type, subject_keys=subject_keys,
        predicate=predicate, object_kind="entity_ref",
        object_payload={"type": far_type, "keys": far_keys}, occurred_at=NOW,
        source_who="t", source_translator_ver="v1", source_raw_ref="row:%d" % number,
        supersedes=None, source_event_id=str(uuid.UUID(int=10_000 + number)),
        source_event_state="source_molecule")


def _wafer_of_dies(seed_in_container=True):
    """One wafer, its dies said twice - `in_container` (die -> wafer) and `inspected`
    (wafer -> die) - the shape the box measured (c9bf53033 ①)."""
    atoms = []
    for k in range(DIES):
        if k or seed_in_container:
            atoms.append(_atom(k + 1, "die", {"d": f"D{k}"}, "in_container", "wafer", {"w": "W"}))
        atoms.append(_atom(100 + k, "wafer", {"w": "W"}, "inspected", "die", {"d": f"D{k}"}))
    # one die inspected TWICE - two atoms, one far node (총괄 b1245bab9 검증): a count of
    # atoms would read DIES + 1 here, and the count is of distinct far nodes
    atoms.append(_atom(999, "wafer", {"w": "W"}, "inspected", "die", {"d": "D3"}))
    return atoms


def _walk(atoms, **kwargs):
    return ledger_subgraph.subgraph(SEED, ledger_subgraph.InMemoryEvidenceLookup(atoms),
                                    hops=2, **kwargs)


def _dies(body):
    return {n["id"] for n in body["nodes"] if n["type"] == "die"}


def test_a_fan_out_over_the_limit_is_a_bundle_and_its_count_is_what_expanding_draws():
    body = _walk(_wafer_of_dies(), fanout_limit=20)
    assert body["bundles"] == [
        {"node": WAFER, "predicate": "in_container", "direction": "incoming",
         "far_type": "die", "count": DIES},
        {"node": WAFER, "predicate": "inspected", "direction": "outgoing",
         "far_type": "die", "count": DIES}]
    assert _dies(body) == {SEED}, "a bundled step drew its nodes"

    opened = _walk(_wafer_of_dies(), fanout_limit=20,
                   expand=[f"{WAFER}|in_container|incoming"])
    assert [b["predicate"] for b in opened["bundles"]] == ["inspected"]
    drawn = {e["source"] for e in opened["edges"]
             if e["predicate"] == "in_container" and e["target"] == WAFER}
    assert len(drawn) == DIES == len(_dies(opened)), "the count is not what expanding draws"


def test_the_limit_is_exceeded_not_reached():
    assert _walk(_wafer_of_dies(), fanout_limit=DIES)["bundles"] == []


def test_a_step_a_guard_refuses_is_not_counted():
    """Reached ONLY by climbing `inspected`, the wafer may not descend `inspected` - the
    guard refuses those steps, so they are no bundle; `in_container` still fans out."""
    body = _walk(_wafer_of_dies(seed_in_container=False), fanout_limit=20)
    assert body["bundles"] == [
        {"node": WAFER, "predicate": "in_container", "direction": "incoming",
         "far_type": "die", "count": DIES - 1}]


def test_no_fanout_limit_answers_as_today():
    atoms = _wafer_of_dies()
    plain = _walk(atoms)
    roomy = _walk(atoms, fanout_limit=1000)
    assert "bundles" not in plain, "the key is absent when the question was not put"
    assert roomy.pop("bundles") == []
    for body in (plain, roomy):
        body.pop("generated_at")
    assert plain == roomy
    assert len(_dies(plain)) == DIES


def test_a_bundle_is_not_a_truncation():
    cut = _walk(_wafer_of_dies(), node_limit=10)
    assert cut["truncated"]["nodes"] is True and "bundles" not in cut
    bundled = _walk(_wafer_of_dies(), node_limit=10, fanout_limit=20)
    assert bundled["truncated"]["reason"] is None and len(bundled["bundles"]) == 2


@pytest.mark.parametrize("item", ["W|in_container", "W|in_container|sideways", "|x|incoming"])
def test_an_expand_that_is_not_a_bundle_key_is_refused(item):
    with pytest.raises(ValueError, match="expand"):
        _walk(_wafer_of_dies(), fanout_limit=20, expand=[item])


def test_the_route_passes_both_cells_through(monkeypatch):
    from ledger import trace_router as router

    seen = []
    monkeypatch.setattr(router, "_evidence_graph", lambda *a, **kw: seen.append(kw) or {})
    monkeypatch.setattr(router, "_signed_start", lambda *a, **kw: "seed")

    class _Db:
        def connection(self):
            return None

    common = dict(node_id="seed", response_format="json", db=_Db(), hops=1,
                  direction="both", since=None, until=None, node_limit=400, edge_limit=1200,
                  positive=None, negative=None, follow=None, backbone_hops=0, collect=None,
                  include_superseded=False)
    router.evidence_subgraph(fanout_limit=20, expand=["n|p|outgoing"], **common)
    router.evidence_subgraph(**common)
    assert (seen[0]["fanout_limit"], seen[0]["expand"]) == (20, ["n|p|outgoing"])
    assert (seen[1]["fanout_limit"], seen[1]["expand"]) == (None, None)
