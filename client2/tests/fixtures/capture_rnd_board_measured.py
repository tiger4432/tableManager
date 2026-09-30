# -*- coding: utf-8 -*-
"""A walk response whose candidates tell 「measured」 from 「name only」, built by the server's own trail code.

Regenerate (conda env assy_manager), from the repository root:
    python client2/tests/fixtures/capture_rnd_board_measured.py

The graph is small and made here; the evidence (hops, and each hop's `predicates`) is what
`ledger_subgraph._evidence` and `_predicates_between` make of it - the same two functions the
route runs. Cases: a measures edge crossed forward, one crossed backward, one on the second hop, a
pair joined by two predicates while the walk took the other one, and a measures edge that touches
the candidate from outside its trail. Writes rnd_board_measured.json beside this file.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))

from ledger_api.ledger_subgraph import _evidence, _predicates_between  # noqa: E402

SEED = "ledger-entity:v1:W"
OTHER = "ledger-entity:v1:W2"
EQP = "ledger-entity:v1:E"


def quantity(name):
    return "ledger-quantity:v1:" + name


EDGES = [
    {"source": SEED, "target": quantity("forward"), "predicate": "measures"},
    {"source": quantity("backward"), "target": SEED, "predicate": "measures"},
    {"source": SEED, "target": quantity("named"), "predicate": "leads_to"},
    {"source": SEED, "target": EQP, "predicate": "processed_with"},
    {"source": EQP, "target": quantity("second_hop"), "predicate": "measures"},
    {"source": SEED, "target": quantity("both"), "predicate": "leads_to"},
    {"source": SEED, "target": quantity("both"), "predicate": "measures"},
    {"source": SEED, "target": quantity("outside"), "predicate": "leads_to"},
    {"source": OTHER, "target": quantity("outside"), "predicate": "measures"},
]
# The walk's parent map: what each node was first reached from, and by which predicate.
TRAIL = {
    SEED: None,
    quantity("forward"): (SEED, "measures"),
    quantity("backward"): (SEED, "measures"),
    quantity("named"): (SEED, "leads_to"),
    EQP: (SEED, "processed_with"),
    quantity("second_hop"): (EQP, "measures"),
    quantity("both"): (SEED, "leads_to"),
    quantity("outside"): (SEED, "leads_to"),
}
CANDIDATES = ["forward", "backward", "named", "second_hop", "both", "outside"]

if __name__ == "__main__":
    ids = set(TRAIL) | {OTHER}
    nodes = {i: {"node_kind": "entity", "label": i.rsplit(":", 1)[-1], "keys": {}, "basis": None} for i in ids}
    between = _predicates_between(EDGES)
    ranked = []
    for rank, name in enumerate(CANDIDATES, start=1):
        node_id = quantity(name)
        ranked.append({"id": node_id, "type": "Quantity", "label": name + " · model", "rank": rank,
                       "top": rank == 1, "tied": False, "incomparable": False,
                       "evidence": _evidence(nodes, {SEED: TRAIL}, {SEED: 1}, node_id, between)})
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                            check=True).stdout.strip()
    body = {"captured_by": "client2/tests/fixtures/capture_rnd_board_measured.py", "server_at": commit,
            "state": "ok", "nodes": sorted(ids), "edges": EDGES,
            "propagation": {"collect": "quantity", "state": "ranked", "contrast": "unexamined",
                            "complete": True, "message": None, "top_set": [quantity(CANDIDATES[0])],
                            "ranked": ranked}}
    path = os.path.join(HERE, "rnd_board_measured.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(body, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(len(ranked), "candidates ->", path)
