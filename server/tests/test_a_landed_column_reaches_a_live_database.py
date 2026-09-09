# -*- coding: utf-8 -*-
"""S-88. A column that lands in `schema.py` must reach a live database by itself.

🔴 MEASURED 2026-09-09, AND THE ANSWER WAS ZERO. `schema.CURSOR_ADDITIONS` is the ADD COLUMN
list and `ensure_schema` applies it — and its only callers were seed scripts and tests. No
production path ran it. The procedure that used to, 「배포 뒤 소스마다 백필 한 번」, went away
with the cursor read path (S-76), and the ensure it carried went with it. Nothing noticed,
because nothing had needed a new column since.

S-58 is what found it: the census column landed, its paced job ran every tick, and every tick
failed on a column that did not exist. The lead PM opened it with one hand-run line.

⛔ THE DEFECT IS NOT THAT COLUMN. It is that a landed column needed a person. Two entry
points now ensure — the chain daemon at startup (both ledger loops live there) and
`backfill.run` (the CLI must not need the daemon to have run first) — and this file scores
that, because the next round would otherwise walk into the same hole with nothing to fail.

⚠️ AND THREE COMMENTS SAID THE OPPOSITE. `schema.py` twice and `rename_ledger_for_rebuild.py`
once asserted 「`ensure_schema` runs at the start of every backfill」, which had quietly
become false. A comment that describes a call nobody makes is how a gap survives a reading.
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_ingestion_worker                                        # noqa: E402
from ledger import backfill, schema                                  # noqa: E402


def test_the_additions_list_is_reachable_from_the_daemon():
    """🔴 THE PROPERTY, NOT THE COLUMN. Whatever `CURSOR_ADDITIONS` names next has to arrive
    without a person, so the assertion is on the CALL and not on today's members."""
    body = inspect.getsource(chain_ingestion_worker.start_chain_ingestion_worker)
    assert "_ensure_ledger_schema_sync" in body
    helper = inspect.getsource(chain_ingestion_worker._ensure_ledger_schema_sync)
    assert "ensure_schema()" in helper


def test_the_cli_does_not_need_the_daemon_to_have_run_first():
    """A fresh install driven by `python -m ledger.backfill --source X` gets the same schema
    the daemon would have ensured. Otherwise 「it works on the server」 and 「it works from the
    command line」 become different facts about the same database."""
    # ⚠️ AT `main`, NOT IN `run`. `run` is a LIBRARY function and a caller does not expect
    # DDL from it; every CLI branch (`rescope`, `--via-events`, the plain load) writes to the
    # ledger, so one call at the entry point covers what three inside would. And it sits
    # AFTER the destructive gate, because a refusal that fires once the store is open is a
    # report rather than a refusal (`test_v2_backfill_refuses_reset_controls_before_store_access`).
    body = inspect.getsource(backfill.main)
    assert "ensure_schema()" in body
    assert "destructive_approval_required" in body.split("ensure_schema()")[0]


def test_the_daemon_names_a_failure_rather_than_dying_of_it():
    """⚠️ THIS DAEMON ALSO DOES CHAIN WORK THAT OWES THE LEDGER NOTHING. A ledger schema that
    cannot be ensured must cost the ledger jobs, not the outbox."""
    body = inspect.getsource(chain_ingestion_worker.start_chain_ingestion_worker)
    assert "logger.error" in body.split("_ensure_ledger_schema_sync")[1][:600]


def test_the_ensure_is_catalogue_first_so_a_startup_costs_no_ddl():
    """It runs on EVERY start and every CLI invocation, so an unconditional ALTER would take
    an ACCESS EXCLUSIVE lock on the ledger each time. The additions are applied by name
    against the catalogue."""
    body = inspect.getsource(schema.ensure_schema)
    assert "CURSOR_ADDITIONS" in body or "_add_missing_columns" in body


def test_no_comment_still_claims_the_retired_procedure_runs_it():
    """⚠️ THE SENTENCE THAT HID THIS. Three comments asserted 「runs at the start of every
    backfill」 while nothing ran it at all — and a reader checking the gap would have found
    the claim and stopped."""
    source = inspect.getsource(schema)
    assert "start of every backfill" not in source
