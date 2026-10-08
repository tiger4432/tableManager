# -*- coding: utf-8 -*-
"""The walk with a fan-out cap, as GET /api/ledger/subgraph answers it with `fanout_limit`, and the one-step walks
`stepAlong` asks - the fixtures `subgraph_view_harness` and `walk_table_harness` read (leads 1d07f1dae, 11e5ea207).

Regenerate (conda env assy_manager), from the repository root, on a box with a ledger:
    ASSY_DATA_ROOT=<the running server's server/ dir> python client2/tests/fixtures/capture_walk_bundles.py

🔴 ASSY_DATA_ROOT is not optional on a worktree: the walk reads its static types from the live declaration
under the data root, and a worktree's own (gitignored) copy can be older than the server's. Captured once
without it, the static `quantity` read as dynamic and four bundles of +583 wafers came back that the box
server would never answer (its declaration marks quantity static). The script prints the static types it
walked with, so a capture against the wrong declaration is visible.

Only the ledger router is mounted on a bare app (no lifespan, so no worker starts), and only GETs are
made - this reads the box database through the repository's own route code. Each walk is asked as the
page's wire asks it. START is named below: a die whose wafer holds more dies than the cap, so its walk
answers the wafer's fan-outs as bundles one step from the start (10-08: the die `walk_start_die.json`
starts from no longer reaches its wafer on the box). On another box name one that does; the script stops
when the walk answers no bundle off the start. Writes:
    walk_bundles_die.json         START walked as the viewer walks a marking: the marking and `fanout_limit` 20
    walk_bundles_die_opened.json  its first bundle opened: one step from the bundle's node along its predicate,
                                  the way the bundle leaves, to its far type
    walk_step_same_type.json      the declaration, and one step each way and both ways from a node along a
                                  predicate whose subject and object are that node's type - a node with a node
                                  on each side the other side does not hold
"""
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from ledger import trace_router  # noqa: E402
from ledger.explorer import entity_id  # noqa: E402

FANOUT = 20
START = ("die", {"mat_id": "SYN-BW-050-19", "mat_type": "Wafer", "x": "0", "y": "0"})
DIRECTIONS = ("outgoing", "incoming", "both")


def _get(client, path, params):
    res = client.get(path, params=params)
    if res.status_code != 200:
        raise SystemExit(f"{res.status_code} {res.text[:400]}")
    return res.json()


def _step(node, predicate, far_type, direction):
    """The query `stepAlong` makes through the wire: the marking (id and positive) and one step."""
    return [("id", node), ("positive", node), ("follow", predicate), ("collect", far_type),
            ("direction", direction), ("hops", "1")]


def _write(name, body):
    with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)


def _same_type(client, stamp):
    """The first declared same-type predicate, in name order, with a node whose two sides differ."""
    declaration = _get(client, "/api/ledger/declaration", [])
    for p in declaration["predicates"]:
        types = (p.get("object") or {}).get("types") or []
        if len(types) != 1 or p.get("subjects") != types:
            continue
        kind = types[0]
        listed = _get(client, "/api/ledger/key-values", [("type", kind), ("limit", "100")])
        for item in listed.get("nodes") or []:
            node = entity_id(kind, item["keys"])
            answers = {d: _get(client, "/api/ledger/subgraph", _step(node, p["name"], kind, d)) for d in DIRECTIONS}
            far = {d: {n["id"] for n in a["nodes"]} - {node} for d, a in answers.items()}
            if far["outgoing"] - far["incoming"] and far["incoming"] - far["outgoing"]:
                if far["both"] != far["outgoing"] | far["incoming"]:
                    raise SystemExit("both is not out and in for %s %s" % (p["name"], item["keys"]))
                _write("walk_step_same_type.json", {
                    "_what": "REAL server output (repository route code, box database), captured %s by "
                             "capture_walk_bundles.py: GET /api/ledger/declaration, then GET /api/ledger/subgraph "
                             "one step from _start along _predicate to its type, each of _answers' directions." % stamp,
                    "_predicate": p["name"], "_start": {"id": node, "type": kind, "keys": item["keys"]},
                    "_declaration": declaration, "_answers": answers})
                return p["name"], item["keys"], {d: len(v) for d, v in far.items()}
    raise SystemExit("no same-type predicate with a node whose two sides differ - nothing to capture")


if __name__ == "__main__":
    seed = entity_id(*START)
    app = FastAPI()
    app.include_router(trace_router.router)
    client = TestClient(app)
    stamp = datetime.now(timezone.utc).isoformat()
    asked = [("id", seed), ("positive", seed), ("fanout_limit", str(FANOUT))]
    body = _get(client, "/api/ledger/subgraph", asked)
    bundles = body.get("bundles") or []
    if not bundles or any(b["node"] == seed for b in bundles):
        raise SystemExit("no bundle off the start at fanout_limit %d - name another START" % FANOUT)
    _write("walk_bundles_die.json", {
        "_what": "REAL server output (repository route code, box database). GET /api/ledger/subgraph "
                 "?id=<_start>&positive=<_start>&fanout_limit=%d, captured %s by capture_walk_bundles.py."
                 % (FANOUT, stamp), "_start": {"type": START[0], "keys": START[1]}, **body})
    first = bundles[0]
    opened = _get(client, "/api/ledger/subgraph",
                  _step(first["node"], first["predicate"], first["far_type"], first["direction"]))
    _write("walk_bundles_die_opened.json", {
        "_what": "REAL server output, the first bundle of walk_bundles_die.json opened: one step from its node along "
                 "its predicate, its direction, to its far type, captured %s by capture_walk_bundles.py." % stamp,
        "_opened": first, **opened})
    print("static types walked with", sorted(trace_router._static_types(None)))
    print("bundles", len(bundles), "nodes", len(body["nodes"]), "edges", len(body["edges"]),
          "truncated", (body.get("truncated") or {}).get("reason"))
    print("opened", first["predicate"], first["direction"], "count", first["count"], "drawn", first.get("drawn"),
          "-> nodes", len(opened["nodes"]), "edges", len(opened["edges"]))
    print("same type", *_same_type(client, stamp))
