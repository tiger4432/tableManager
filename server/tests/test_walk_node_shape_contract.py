# -*- coding: utf-8 -*-
"""`contracts/walk_node_shape` scored on the server side (총괄 5788bd81c) - the walk's own reading
rule, `_apply_registrations`, over each case's atoms gives the case's `expect`. The client half is
`contracts/walk_node_shape/client_harness.mjs`; both answer to the vector, not to each other.

⚠️ «Declared but not reached» is scored by name: a node no registration reached carries no
`attributes` key at all (test_a_nodes_own_columns_do_not_come_through_follow), the vector writes
`{}` - both say every declared name is absent, which is the property the vector pins.
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
    ledger_subgraph._apply_registrations(nodes, {"n1": seen} if seen else {})
    node, expect = nodes["n1"], case["expect"]

    assert node.get("attributes", {}) == expect["attributes"]
    assert node.get("attribute_conflicts", 0) == expect["attribute_conflicts"]
    assert node.get("attributes_by_world", {}) == expect["attributes_by_world"]
