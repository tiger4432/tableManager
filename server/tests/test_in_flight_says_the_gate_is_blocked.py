# -*- coding: utf-8 -*-
""""A run is in flight" and "a run is stuck holding the gate" were the same answer.

`in_flight` already worked out whether the run was progressing, stalled or unreported -
and then dropped it. The response said a run was in flight, so a screen could not tell
"about to finish" from "stopped, and everything behind it is waiting". The second one
looks exactly like the first, which is why the owner's report was "it goes in the queue
and then nothing happens".

And nothing on the row said WHO was running it. A run row outlives its process, so a
scheduler killed mid-run leaves `running` behind forever - with no identity, "it died"
and "it is slow" are one row. `runner` records that; ⛔ nothing judges on it yet, because
reaping without an identity turns "never finishes" into "two at once".
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import retroactive                                               # noqa: E402
from database import models                                      # noqa: E402

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
STALL = 60.0


def run_row(db, *, started_ago, progress_ago, runner=None):
    row = models.RetroactiveRun(
        run_id="probe%s" % (started_ago or 0), op="ledger_rescope", state="running",
        queued_at=NOW - timedelta(seconds=started_ago + 5),
        started_at=NOW - timedelta(seconds=started_ago),
        last_progress_at=(None if progress_ago is None
                          else NOW - timedelta(seconds=progress_ago)),
        runner=runner)
    db.add(row)
    db.flush()
    return row


def test_a_progressing_run_is_not_reported_as_blocked(db_session):
    run_row(db_session, started_ago=300, progress_ago=1)
    out = retroactive.in_flight(db_session, now=NOW, stall_after=STALL)
    assert out["moving"] == retroactive.MOVING_PROGRESSING
    assert out["gate_blocked"] is False


def test_a_stalled_run_says_the_gate_is_blocked(db_session):
    """🔴 THE STATE THAT LOOKED LIKE NOTHING. It reported progress once and then stopped,
    so the gate is closed on a run that is not moving."""
    run_row(db_session, started_ago=600, progress_ago=500)
    out = retroactive.in_flight(db_session, now=NOW, stall_after=STALL)
    assert out["moving"] == retroactive.MOVING_STALLED
    assert out["gate_blocked"] is True


def test_a_run_that_never_reported_also_blocks(db_session):
    """`unreported` is not `stalled` - two of the six operations never checkpoint - but
    from the gate's side both hold it shut, and the screen has to draw that."""
    row = run_row(db_session, started_ago=600, progress_ago=600)
    row.last_progress_at = row.started_at          # progress == start: never reported
    db_session.flush()
    out = retroactive.in_flight(db_session, now=NOW, stall_after=STALL)
    assert out["moving"] == retroactive.MOVING_UNREPORTED
    assert out["gate_blocked"] is True


def test_the_runner_travels_and_null_stays_null(db_session):
    """Raw, and NULL means "unknown" rather than "nobody" - rows predate the column."""
    run_row(db_session, started_ago=10, progress_ago=1, runner="host-a/4242")
    out = retroactive.in_flight(db_session, now=NOW, stall_after=STALL)
    assert out["runner"] == "host-a/4242"


def test_a_row_without_a_runner_reports_none_not_a_guess(db_session):
    run_row(db_session, started_ago=10, progress_ago=1, runner=None)
    out = retroactive.in_flight(db_session, now=NOW, stall_after=STALL)
    assert out["runner"] is None


def test_the_identity_is_this_process_and_is_read_when_asked(monkeypatch):
    """Behavioural: the value names THIS process, and changing the process changes it -
    which is what "read at stamp time, not at import" means."""
    import os

    first = retroactive.runner_identity()
    assert first.endswith("/%d" % os.getpid())
    assert "/" in first and first.split("/")[0]

    monkeypatch.setattr(os, "getpid", lambda: 999999)
    assert retroactive.runner_identity().endswith("/999999"),         "the identity was captured once instead of read when the run starts"


def test_an_unresolvable_hostname_still_yields_an_identity(monkeypatch):
    """A name lookup that fails must not stop a run from recording that it started."""
    import socket

    monkeypatch.setattr(socket, "gethostname", lambda: (_ for _ in ()).throw(OSError()))
    got = retroactive.runner_identity()
    assert got.startswith("?/") and got.split("/")[1].isdigit()
