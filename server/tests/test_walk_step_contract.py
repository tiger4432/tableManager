# -*- coding: utf-8 -*-
"""The walk's step rule, scored on the server half against `contracts/walk_step/vectors.json`
(총괄 2dcf6fb71). The client half is `node contracts/walk_step/client_harness.mjs`.

Each case is a chain seed -> ... -> `from` -> `to` with `step` steps before the judged one, walked
through the product's own seats: `_reach` (table rows, ranking) and the graph walk (`subgraph`:
the fetch split and `_step`). Both ask `_held_to_names`; a change to the rule there, or to how
either seat asks it, turns a case red.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402

VECTORS = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "contracts", "walk_step", "vectors.json"))
NOW = datetime(2026, 8, 15, 3, 0, tzinfo=timezone.utc)
EVENT = str(uuid.UUID("3101e12e-c814-58f4-87cf-c8e31084e923"))


def _cases():
    with open(VECTORS, encoding="utf-8") as handle:
        return json.load(handle)["cases"]


def _chain(case):
    """Node types along the chain: `step` dynamic hops, then `from`, then `to`."""
    return ["hop%d" % i for i in range(case["step"])] + [case["from"], case["to"]]


def _bare(name):
    return str(name).split("@", 1)[0]


@pytest.mark.parametrize("case", _cases(), ids=[c["id"] for c in _cases()])
def test_the_reach_takes_the_shared_vector(case):
    types = _chain(case)
    nodes = {"n%d" % i: {"id": "n%d" % i, "type": t} for i, t in enumerate(types)}
    edges = [{"source": "n%d" % i, "target": "n%d" % (i + 1), "predicate": "p%d" % i}
             for i in range(len(types) - 1)]
    reach, _, _ = ledger_subgraph._reach(nodes, edges, {"n0": 1}, static_types=set(case["static_types"]))
    assert ("n%d" % (len(types) - 1) in reach) is case["takes"]


@pytest.mark.parametrize("case", _cases(), ids=[c["id"] for c in _cases()])
def test_the_graph_walk_takes_the_shared_vector(case):
    types = _chain(case)
    static = set(case["static_types"])
    atoms = [ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=900 + i)), subject_type=_bare(types[i]), subject_keys={"k": "n%d" % i},
        predicate="p%d" % i, object_kind="entity_ref",
        object_payload={"type": _bare(types[i + 1]), "keys": {"k": "n%d" % (i + 1)}, "qualifiers": {}},
        occurred_at=NOW, source_who="contract", source_translator_ver="v1",
        source_raw_ref="row:%d" % i, supersedes=None, source_event_id=EVENT,
        source_event_state="source_record") for i in range(len(types) - 1)]
    # the declaration's own rule for which predicates a name may follow: both ends static
    static_follow = {"p%d" % i for i in range(len(types) - 1)
                     if _bare(types[i]) in static and _bare(types[i + 1]) in static}
    body = ledger_subgraph.subgraph(
        explorer.entity_id(types[0], {"k": "n0"}), ledger_subgraph.InMemoryEvidenceLookup(atoms),
        hops=len(types), direction="both", static_types=static, static_follow=static_follow)
    # the ledger stores bare types; the seed keeps the spelling a caller sends (the walk bares it)
    far = explorer.entity_id(_bare(types[-1]), {"k": "n%d" % (len(types) - 1)})
    assert (far in {node["id"] for node in body["nodes"]}) is case["takes"]
