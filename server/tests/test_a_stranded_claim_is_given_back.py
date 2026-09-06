# -*- coding: utf-8 -*-
"""A retry claimed by a process that then died was never given back.

`poll_pending_retries` commits `status = "PENDING"` before it works, and its own query
selects only `PENDING_RETRY`. So a row claimed by a process that stopped existing sits in a
state nothing looks for again -- permanent, with no code to revive it. `fe3e9261` closed the
case where SETUP throws; nothing inside that process can close the case where the process
is killed. This sweep can, from outside.

⚠️ THE PREDICATE IS TWO FACTS. "Claimed and old" alone reclaims a healthy long ingestion,
and reclaiming a live job turns a LOSS into DUPLICATE work -- worse, because loss means the
data never arrives while duplication means wrong data arrives quietly. The second fact is
the checkpoint: if chunks are still landing, the job is alive however long it has run.

⛔ AND A ROW WITH NO CHECKPOINT IS SKIPPED, NOT RECLAIMED -- three arms of
`_plan_checkpoint` produce none and none of them means the file is stuck. The skip is
COUNTED, because nobody knows today how often those arms fire.
"""
import inspect
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ingestion_checkpoint                                      # noqa: E402
import run_watcher                                               # noqa: E402
from database import models                                      # noqa: E402
from utils import heartbeat                                      # noqa: E402

OLD = datetime.now(timezone.utc) - timedelta(seconds=100_000)
NOW = datetime.now(timezone.utc)


def claimed_row(db, *, table="dt_map", filename="a.csv", updated_at=OLD):
    row = models.FileIngestionLog(filename=filename, filepath="/tmp/" + filename,
                                  table_name=table, status="PENDING")
    db.add(row)
    db.flush()
    row.updated_at = updated_at            # after flush: onupdate would stamp `now`
    db.flush()
    return row


def checkpoint(db, *, table="dt_map", filename="a.csv", updated_at=OLD,
               status=ingestion_checkpoint.STATUS_IN_PROGRESS):
    row = models.FileIngestionCheckpoint(
        table_name=table, file_signature="sig-" + filename, filename=filename,
        status=status, processed_rows=1, chunk_index=1)
    db.add(row)
    db.flush()
    row.updated_at = updated_at
    db.flush()
    return row


# ------------------------------------------------------------------ the grace is CITED

def test_the_grace_calls_the_derivation_rather_than_copying_it():
    """🔴 ONE AUTHOR. `DEFAULT_STALL_AFTER_SEC` already carries the measurement and the
    floor it clears; a 300 written here would be a second author for one number."""
    assert ingestion_checkpoint.reclaim_after_seconds() == heartbeat.DEFAULT_STALL_AFTER_SEC
    assert "300" not in inspect.getsource(ingestion_checkpoint.reclaim_after_seconds)


def test_a_declared_grace_wins():
    assert ingestion_checkpoint.reclaim_after_seconds(900) == 900.0


@pytest.mark.parametrize("junk", [None, 0, -1, True, "600"])
def test_anything_not_a_positive_number_falls_back(junk):
    assert ingestion_checkpoint.reclaim_after_seconds(junk) == \
        heartbeat.DEFAULT_STALL_AFTER_SEC


# ------------------------------------------------- liveness keeps its two answers apart

def test_no_checkpoint_and_a_stale_one_are_different_answers(db_session):
    assert ingestion_checkpoint.liveness(db_session, "dt_map", "nothing.csv") == (False, None)
    checkpoint(db_session, filename="b.csv")
    has, moved = ingestion_checkpoint.liveness(db_session, "dt_map", "b.csv")
    assert has is True and moved is not None


def test_a_finished_checkpoint_is_not_liveness(db_session):
    """Only IN_PROGRESS says "still working"; a DONE row would make a stranded claim look
    alive for ever."""
    checkpoint(db_session, filename="c.csv", status=ingestion_checkpoint.STATUS_DONE)
    assert ingestion_checkpoint.liveness(db_session, "dt_map", "c.csv")[0] is False


@pytest.mark.parametrize("table,name", [(None, "a.csv"), ("dt_map", None), ("", "")])
def test_liveness_needs_both_names(db_session, table, name):
    assert ingestion_checkpoint.liveness(db_session, table, name) == (False, None)


# -------------------------------------------------------------- the sweep, on real rows

def test_a_stranded_claim_with_a_stale_checkpoint_is_given_back(db_session):
    """🔴 THE WHOLE POINT. It goes back to the status the poller's own query selects."""
    row = claimed_row(db_session, filename="d.csv")
    checkpoint(db_session, filename="d.csv")
    reclaimed, skipped = run_watcher.reclaim_stranded_claims(db_session)
    assert (reclaimed, skipped) == (1, 0)
    db_session.refresh(row)
    assert row.status == "PENDING_RETRY"


def test_a_live_job_is_left_alone_however_long_it_has_run(db_session):
    """🔴 THE ANTI-DUPLICATION ARM. The claim is ancient; the chunks are recent. Judging on
    runtime instead of progress would reclaim this and run it twice."""
    row = claimed_row(db_session, filename="e.csv")
    checkpoint(db_session, filename="e.csv", updated_at=NOW)
    assert run_watcher.reclaim_stranded_claims(db_session) == (0, 0)
    db_session.refresh(row)
    assert row.status == "PENDING"


def test_a_row_with_no_checkpoint_is_skipped_and_counted(db_session):
    """⛔ NOT RECLAIMED. Its liveness is unknown, and guessing "dead" trades loss for
    duplication. The count is what keeps the hole visible."""
    row = claimed_row(db_session, filename="f.csv")
    assert run_watcher.reclaim_stranded_claims(db_session) == (0, 1)
    db_session.refresh(row)
    assert row.status == "PENDING", "a row of unknown liveness was reclaimed"


def test_a_recent_claim_is_not_a_candidate_at_all(db_session):
    claimed_row(db_session, filename="g.csv", updated_at=NOW)
    checkpoint(db_session, filename="g.csv")
    assert run_watcher.reclaim_stranded_claims(db_session) == (0, 0)


def test_nothing_claimed_is_a_quiet_no_op(db_session):
    assert run_watcher.reclaim_stranded_claims(db_session) == (0, 0)


def test_the_reclaim_and_the_skip_are_reported_with_numbers(db_session, caplog):
    """⚠️ Silent either way would hide both how often rows strand AND how big the
    checkpoint-less hole is."""
    import logging

    claimed_row(db_session, filename="h.csv")
    checkpoint(db_session, filename="h.csv")
    claimed_row(db_session, filename="i.csv")          # no checkpoint
    with caplog.at_level(logging.WARNING):
        assert run_watcher.reclaim_stranded_claims(db_session) == (1, 1)
    said = "\n".join(r.getMessage() for r in caplog.records)
    assert "was claimed" in said and "h.csv" in said
    assert "1 reclaimed, 1 skipped" in said


def test_the_sweep_runs_before_the_poller_reads_its_queue():
    """Anything given back has to be PENDING_RETRY by the time the query runs, or it waits
    a whole extra cycle for nothing."""
    body = inspect.getsource(run_watcher.poll_pending_retries)
    assert "reclaim_stranded_claims(db)" in body.split("PENDING_RETRY", 1)[0]
