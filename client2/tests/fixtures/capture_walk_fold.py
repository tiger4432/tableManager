# -*- coding: utf-8 -*-
"""The three walks a folded lump asks for, as GET /api/ledger/subgraph answers them (총괄 793017c62 · edcc0568c).

Regenerate (conda env assy_manager), from the repository root, with the isolated test PostgreSQL:
    python client2/tests/fixtures/capture_walk_fold.py

The world is built by server/tests/test_a_recipe_walk_brings_the_measurements_other_wafers_made.py on a
PostgreSQL scratch schema - the sample's `metro` and `process_event` tables, a ledger declaration with the
owner's measurement shape (wafer ─measured▶ measurement_event(value) ─used▶ recipe · ─of▶ quantity) and
process events (wafer ─underwent▶ process_event), rows translated by `backfill.run`. That test runs here with
WALK_FOLD_CAPTURE_DIR set to this folder and writes:
    walk_fold_wafer.json         the start wafer W1, two hops - its measurements M1 · M2
    walk_fold_recipe_step.json   the recipe RCP-A, one step in, one day, cap 200 - M1 · M2 (W1) and M3 (W2) · M4 (W3)
    walk_fold_process_lump.json  W1's process events P1 · P2 as seeds, through the wafer - M1 · M2
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SERVER = os.path.join(ROOT, "server")

if __name__ == "__main__":
    env = dict(os.environ, WALK_FOLD_CAPTURE_DIR=HERE)
    run = subprocess.run([sys.executable, "scripts/run_pg_tests.py", "-k",
                          "test_a_recipe_walk_brings_the_measurements_other_wafers_made",
                          "-p", "no:cacheprovider", "-q"], cwd=SERVER, env=env)
    if run.returncode != 0:
        raise SystemExit("the walk test failed - nothing captured")
    for name in ("walk_fold_wafer", "walk_fold_recipe_step", "walk_fold_process_lump"):
        print(os.path.join(HERE, name + ".json"))
