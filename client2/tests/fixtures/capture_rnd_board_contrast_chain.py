# -*- coding: utf-8 -*-
"""What the board's Save contrast list reads after the REAL chain computed its saved runs.

Regenerate (conda env assy_manager), from the repository root:
    python client2/tests/fixtures/capture_rnd_board_contrast_chain.py

The ledger, the tables and the rule are the implementer's own gate
(server/tests/test_a_saved_contrast_is_the_walks_own_ranking.py): the runs are put in through the
model as that gate does, the chain rule runs through its seat (all but R_WAITING) and BOTH of its
writes land - the factor rows, and the run's own computed_at / candidates / contrast / complete
(the write-back batch the gate's `_run_facts` reads). SQLite takes no ISO text for a DateTime (the
gate says so of `until`), so the write-back is set through the model as the gate sets the run -
and SQLite keeps no zone, so computed_at reads back bare here (PostgreSQL returns +00:00; the
harness's gate C draws that spelling).
The body below is what GET /tables/contrast_run/data answers to the board's own list query - the
one read the list makes (lead 2dd93d4a9). `written` counts the factor rows, independently.
Writes rnd_board_contrast_chain.json.
"""
import json
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SERVER = os.path.join(ROOT, "server")
sys.path.insert(0, SERVER)
sys.path.insert(0, os.path.join(SERVER, "tests"))

import pytest                                                        # noqa: E402
import test_a_saved_contrast_is_the_walks_own_ranking as gate       # noqa: E402
import main                                                          # noqa: E402

#: The board's list query, as client2/src/rnd_board/api.js sends it.
LIST = dict(limit=10, order_by="updated_at", order_desc=True)
RUNS = {
    "R_SEEN": ([gate._lot("P1"), gate._lot("P2")], [gate._lot("N1")], {}),
    "R_OPEN": ([gate._lot("P1"), gate._lot("P2")], [], {}),
    "R_CUT": ([gate._lot("P1")], [gate._lot("N1")], {"node_limit": 10}),
    "R_EMPTY": ([gate._lot("NOBODY")], [gate._lot("NOBODY2")], {}),
    "R_WAITING": ([gate._lot("P1")], [gate._lot("N1")], {}),
}
NOT_WALKED = {"R_WAITING"}


def body(answer):
    """The route's answer as the wire carries it."""
    raw = getattr(answer, "body", None)
    return json.loads(raw) if raw is not None else json.loads(json.dumps(answer, default=str))


def write_back(db, facts):
    """The run's own cells the same call proposes, set on the run row."""
    model = gate.models.DYNAMIC_TABLES["contrast_run"]
    for run_id, cells in facts.items():
        row = db.query(model).filter(model.run_id == run_id).one()
        for key, value in cells.items():
            if key == "computed_at" and isinstance(value, str):
                value = datetime.fromisoformat(value)
            if key != "run_id":
                setattr(row, key, value)
    db.commit()


def capture():
    setup = getattr(gate.fixture_db, "__wrapped__", None) or gate.fixture_db.__pytest_wrapped__.obj
    patch = pytest.MonkeyPatch()
    rows = setup(patch)
    db = next(rows)
    try:
        for run_id, (positive, negative, walk) in RUNS.items():
            row_id = gate._save_run(db, run_id, positive, negative, **walk)
            if run_id not in NOT_WALKED:
                write_back(db, gate._run_facts(gate._chain(db, row_id)))
        written = {run_id: len(gate._factors(db, run_id)) for run_id in RUNS}
        run_list = body(main.get_table_data("contrast_run", db=db, **LIST))
        return written, run_list
    finally:
        next(rows, None)
        patch.undo()


if __name__ == "__main__":
    written, run_list = capture()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                            check=True).stdout.strip()
    out = {"captured_by": "client2/tests/fixtures/capture_rnd_board_contrast_chain.py",
           "server_at": commit, "written": written, "run_list": run_list}
    path = os.path.join(HERE, "rnd_board_contrast_chain.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("written", written, "runs listed", len(run_list.get("data", [])), "->", path)
