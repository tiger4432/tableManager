# -*- coding: utf-8 -*-
"""The seat that decides「is this a PostgreSQL-only proof?」must ask the PROPERTY.

`conftest.pytest_collection_modifyitems` takes those proofs out of the plain run and
`scripts/run_pg_tests.py` calls them with `-m pg`. Until 2026-09-23 the seat asked
whether the author had WRITTEN `pg`; fifteen items requested `pg_engine` and had not,
so they ran in the plain run - and the first of them left `ASSY_TEST_DATABASE_URL`
declared for the rest of the session, which cost five other tests their own premise.

🔴 WHAT IS PINNED HERE IS THE ORDER, not the seat's arithmetic. The seat adds the mark,
and pytest's own `-m` deselection has to run AFTER that or the mark reaches nothing.
Today that holds because conftest plugins are registered late and pluggy calls them
first. That is an implementation detail of pluggy, so it is asserted rather than
trusted - if it ever flips, these two cry instead of fifteen proofs going quiet.
"""
import os
import subprocess
import sys

from conftest import PG_ASKED_OUT_REASON

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = "tests/" + os.path.basename(__file__)
CANARY = HERE + "::test_the_canary_asks_for_a_pg_only_fixture_and_carries_no_mark"


def _pytest(*args):
    done = subprocess.run([sys.executable, "-m", "pytest", *args, "-q", "--no-header",
                           "-p", "no:warnings"],
                          cwd=SERVER_DIR, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return done.stdout + done.stderr


def test_an_unmarked_pg_fixture_user_is_taken_out_of_the_plain_run():
    """⚠️ The canary below carries NO `pg` mark ON PURPOSE. If a later round marks it,
    this stops measuring the seat and measures the mark instead."""
    out = _pytest(CANARY, "-rs")
    assert "1 skipped" in out, out[-2000:]
    # 🔴 THE REASON, NOT JUST THE COLOUR. `pg_engine` skips on its own when no database is
    #   declared, so a box without one would make the line above green with the seat gone.
    assert PG_ASKED_OUT_REASON in out, out[-2000:]


def test_the_same_item_is_still_selected_by_the_pg_lane():
    """The other half. Taking it out of the plain run is only correct if the lane that
    exists for it still picks it up - otherwise the proof is gone from BOTH runs, which
    is the failure `conftest` warns about for a mistyped marker."""
    out = _pytest(CANARY, "-m", "pg", "--collect-only")
    assert CANARY.replace("/", os.sep) in out.replace("/", os.sep), out[-2000:]


def test_the_canary_asks_for_a_pg_only_fixture_and_carries_no_mark(pg_engine):
    """Not a proof of its own - the control group the two above read."""
    assert pg_engine is not None
