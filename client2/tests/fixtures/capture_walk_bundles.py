# -*- coding: utf-8 -*-
"""The walk with a fan-out cap, as GET /api/ledger/subgraph answers it with `fanout_limit` (and then with
one bundle expanded) - the fixtures `subgraph_view_harness` reads for the bundle chips (lead 1d07f1dae).

Regenerate (conda env assy_manager), from the repository root, on a box with a ledger:
    ASSY_DATA_ROOT=<the running server's server/ dir> python client2/tests/fixtures/capture_walk_bundles.py

🔴 ASSY_DATA_ROOT is not optional on a worktree: the walk reads its static types from the live declaration
under the data root, and a worktree's own (gitignored) copy can be older than the server's. Captured once
without it, the static `quantity` read as dynamic and four bundles of +583 wafers came back that the box
server would never answer (its declaration marks quantity static). The script prints the static types it
walked with, so a capture against the wrong declaration is visible.

Only the ledger router is mounted on a bare app (no lifespan, so no worker starts), and only GETs are
made - this reads the box database through the repository's own route code. The start is the die
`walk_start_die.json` starts from, asked as the viewer asks it: the marking (id and positive) and
`fanout_limit` 20, nothing else. Writes walk_bundles_die.json and walk_bundles_die_expanded.json.
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

FANOUT = 20


def _get(client, params):
    res = client.get("/api/ledger/subgraph", params=params)
    if res.status_code != 200:
        raise SystemExit(f"{res.status_code} {res.text[:400]}")
    return res.json()


if __name__ == "__main__":
    with open(os.path.join(HERE, "walk_start_die.json"), encoding="utf-8") as f:
        seed = json.load(f)["seed"]["id"]
    app = FastAPI()
    app.include_router(trace_router.router)
    client = TestClient(app)
    stamp = datetime.now(timezone.utc).isoformat()
    asked = [("id", seed), ("positive", seed), ("fanout_limit", str(FANOUT))]
    body = _get(client, asked)
    bundles = body.get("bundles") or []
    if not bundles:
        raise SystemExit("no bundle at fanout_limit %d - nothing to capture" % FANOUT)
    with open(os.path.join(HERE, "walk_bundles_die.json"), "w", encoding="utf-8") as f:
        json.dump({"_what": "REAL server output (repository route code, box database). GET /api/ledger/subgraph "
                            "?id=<die seed>&positive=<die seed>&fanout_limit=%d, captured %s by capture_walk_bundles.py."
                            % (FANOUT, stamp), **body}, f, ensure_ascii=False)
    first = bundles[0]
    key = "%s|%s|%s" % (first["node"], first["predicate"], first["direction"])
    expanded = _get(client, asked + [("expand", key)])
    with open(os.path.join(HERE, "walk_bundles_die_expanded.json"), "w", encoding="utf-8") as f:
        json.dump({"_what": "REAL server output, as walk_bundles_die.json plus expand=<its first bundle>, "
                            "captured %s by capture_walk_bundles.py." % stamp,
                   "_expanded": first, **expanded}, f, ensure_ascii=False)
    print("static types walked with", sorted(trace_router._static_types(None)))
    print("bundles", len(bundles), "nodes", len(body["nodes"]), "edges", len(body["edges"]),
          "truncated", (body.get("truncated") or {}).get("reason"))
    print("expanded", key[-60:], "count", first["count"], "-> nodes", len(expanded["nodes"]),
          "bundles", len(expanded.get("bundles") or []))
