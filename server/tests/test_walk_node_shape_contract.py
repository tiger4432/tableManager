# -*- coding: utf-8 -*-
"""`contracts/walk_node_shape` scored on the server side (총괄 5788bd81c) - the walk's own reading
rule, `_apply_registrations`, over each case's atoms gives the case's `expect`. The client half is
`contracts/walk_node_shape/client_harness.mjs`; both answer to the vector, not to each other.

Scored EXACTLY (총괄 0cde56e07): the keys of the three a node carries are the case's `expect` -
an unreached node carries none of them, as the server sends it. Each-world lines are in the
order the case `picked` (총괄 4be010312).
"""
import json
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger_api import ledger_subgraph                            # noqa: E402

VECTORS = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "contracts", "walk_node_shape", "vectors.json"))
TYPE, KEY = "shape@1", "k"                                        # the client half's own
FIELDS = ("attributes", "attribute_conflicts", "attributes_by_world")


def _cases():
    with open(VECTORS, encoding="utf-8") as handle:
        return json.load(handle)["cases"]


@pytest.mark.parametrize("case", _cases(), ids=[c["name"] for c in _cases()])
def test_the_server_reads_the_shared_vector(case, tmp_path, monkeypatch, request):
    import paths

    root = tmp_path / "ontology"                                  # ⛔ not the box's declaration
    root.mkdir()
    (root / "ledger_config.json").write_text(json.dumps({"entities": {
        TYPE: {"keys": [KEY], "attributes": case["declared_attributes"]}}}), encoding="utf-8")
    monkeypatch.setattr(paths, "config_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    ledger_subgraph.reset_declaration_cache()
    request.addfinalizer(ledger_subgraph.reset_declaration_cache)

    seen = {}
    for atom in case["atoms"]:
        at = datetime.fromisoformat(atom["occurred_at"].replace("Z", "+00:00"))
        seen.setdefault(atom["attribute"], []).append(
            (at, atom["value"], atom["world"], atom["source_who"], ledger_subgraph._instant(at)))
    nodes = {"n1": {"id": "n1", "type": TYPE}}
    ledger_subgraph._apply_registrations(
        nodes, {"n1": seen} if seen else {},
        ledger_subgraph._in_picked_order(case.get("picked", ())))
    node = nodes["n1"]

    assert {name: node[name] for name in FIELDS if name in node} == case["expect"]
