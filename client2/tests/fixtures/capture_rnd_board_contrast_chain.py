# -*- coding: utf-8 -*-
"""What the board's Save contrast list reads after the REAL chain computed three saved runs.

Regenerate (conda env assy_manager), from the repository root:
    python client2/tests/fixtures/capture_rnd_board_contrast_chain.py

The ledger, the tables and the rule are the implementer's own gate
(server/tests/test_a_saved_contrast_is_the_walks_own_ranking.py): the runs are put in through the
model as that gate does, the chain rule runs through its seat, and the bodies below are what
GET /tables/<t>/data answers to the board's own two queries. Writes rnd_board_contrast_chain.json.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SERVER = os.path.join(ROOT, "server")
sys.path.insert(0, SERVER)
sys.path.insert(0, os.path.join(SERVER, "tests"))

import pytest                                                        # noqa: E402
import test_a_saved_contrast_is_the_walks_own_ranking as gate       # noqa: E402
import main                                                          # noqa: E402

#: The board's list query and its factor query, as client2/src/rnd_board/api.js sends them.
LIST = dict(limit=10, order_by="updated_at", order_desc=True)
RUNS = {
    "R_SEEN": ([gate._lot("P1"), gate._lot("P2")], [gate._lot("N1")], {}),
    "R_OPEN": ([gate._lot("P1"), gate._lot("P2")], [], {}),
    "R_CUT": ([gate._lot("P1")], [gate._lot("N1")], {"node_limit": 10}),
}


def body(answer):
    """The route's answer as the wire carries it."""
    raw = getattr(answer, "body", None)
    return json.loads(raw) if raw is not None else json.loads(json.dumps(answer, default=str))


def capture():
    setup = getattr(gate.fixture_db, "__wrapped__", None) or gate.fixture_db.__pytest_wrapped__.obj
    patch = pytest.MonkeyPatch()
    rows = setup(patch)
    db = next(rows)
    try:
        for run_id, (positive, negative, walk) in RUNS.items():
            gate._chain(db, gate._save_run(db, run_id, positive, negative, **walk))
        written = {run_id: len(gate._factors(db, run_id)) for run_id in RUNS}
        run_list = body(main.get_table_data("contrast_run", db=db, **LIST))
        factor_reads = {}
        for run_id in RUNS:
            filters = json.dumps({"run_id": {"filterType": "text", "type": "equals", "filter": run_id}})
            factor_reads[run_id] = body(main.get_table_data("contrast_factor", limit=1, filters=filters, db=db))
        return written, run_list, factor_reads
    finally:
        next(rows, None)
        patch.undo()


if __name__ == "__main__":
    written, run_list, factor_reads = capture()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                            check=True).stdout.strip()
    out = {"captured_by": "client2/tests/fixtures/capture_rnd_board_contrast_chain.py",
           "server_at": commit, "written": written, "run_list": run_list, "factor_reads": factor_reads}
    path = os.path.join(HERE, "rnd_board_contrast_chain.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("written", written, "runs listed", len(run_list.get("data", [])), "->", path)
