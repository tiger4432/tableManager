# -*- coding: utf-8 -*-
"""Real walk answers from the server hub branch (impl-walk-hub), the fixture walk_hub_answers.json.gz that
walk_hub_harness and subgraph_view_harness read (lead 10-12 · 10-13, task/WALK_HUB_ANSWER_SHAPE.md).

It runs the branch's own hub test scenarios through that test's own helpers (`_walk`, `_paged`, `_applied`) and writes
each answer, each page of a continued walk, and what the pages laid over each other by id come to - the server's
reference receiver, the harness's expected value. No database: the test's atoms in memory, as the test runs them.

Regenerate (conda env assy_manager), from the hub branch's server/ directory:
    python <repo>/client2/tests/fixtures/capture_walk_hubs.py . <out.json>
then gzip it with no timestamp into the fixture, from the repository root:
    python -c "import gzip,shutil; shutil.copyfileobj(open('<out.json>','rb'), gzip.GzipFile('client2/tests/fixtures/walk_hub_answers.json.gz','wb',mtime=0))"
A run on an unchanged branch differs only in its times (generated_at, more.as_of).
"""
import json
import subprocess
import sys

SERVER, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, SERVER)
sys.path.insert(0, SERVER + "/tests")

import test_a_walk_folds_a_declared_step_into_a_hub as t  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402

ledger_subgraph._declaration_facts[t.DECLARED] = t._facts({"has_wafer"})
ledger_subgraph._declaration_facts[t.PLAIN] = t._facts(())
ledger_subgraph._declaration_facts[t.BONDED_DECLARED] = (
    {}, {}, {}, {"inspected": "in_container", "in_container": "inspected"}, {}, {}, frozenset({"in_container"}), {})

clean = lambda body: json.loads(json.dumps(body, default=str))


def paged(name, seed, atoms, **kwargs):
    pages = t._paged(seed, atoms, **kwargs)
    return {"name": name, "pages": [clean(p) for p in pages], "applied": json.loads(t._applied(pages))}


head = subprocess.run(["git", "-C", SERVER, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
out = {
    "source": "server/tests/test_a_walk_folds_a_declared_step_into_a_hub.py on impl-walk-hub " + head,
    "ids": {"lot": t.LOT, "wafers": t.WAFERS, "defects": t.DEFECTS, "P": t.P, "N": t.N, "wafer": t.WAFER},
    "single": {
        "owner": clean(t._walk(t.LOT, t.OWNER, hops=3)),
        "opened": clean(t._walk(t.LOT, t.OWNER, hops=3, expand=[t.WAFERS, t.DEFECTS])),
        "wafers_opened": clean(t._walk(t.LOT, t.OWNER, hops=3, expand=[t.WAFERS])),
        "capped": clean(t._walk(t.LOT, t.OWNER, declaration=t.PLAIN, hops=3, fanout_limit=2)),
        "capped_opened": clean(t._walk(t.LOT, t.OWNER, declaration=t.PLAIN, hops=3, fanout_limit=2, expand=[t.WAFERS])),
        "plain": clean(t._walk(t.LOT, t.OWNER, declaration=t.PLAIN, hops=3)),
        "contrast": clean(t._walk({"positive": [t.P], "negative": [t.N]}, t.CONTRAST, hops=2)),
    },
    "paged": [
        paged("paged", t.LOT, t.PAGED, hops=2, node_limit=10),
        paged("leaving", t.LOT, t.LEAVING, hops=3, edge_limit=100),
        paged("moving", {"positive": [t.P], "negative": [t.N]}, t.MOVING, hops=2, edge_limit=100),
        paged("bonded", t.WAFER, t.BONDED, edge_limit=40, **t.BONDED_KW),
    ],
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, sort_keys=True)
print("pages", {p["name"]: len(p["pages"]) for p in out["paged"]},
      "left", sum(len(b.get("left") or []) for p in out["paged"] for b in p["pages"]),
      "moved", sum(len(b.get("moved") or []) for p in out["paged"] for b in p["pages"]),
      "pending", sum(len(b.get("edges_pending") or []) for p in out["paged"] for b in p["pages"]),
      "gone heads", sum(1 for p in out["paged"] for b in p["pages"] for n in b["nodes"] if set(n) == {"id", "count"}))
