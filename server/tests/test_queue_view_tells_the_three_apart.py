# -*- coding: utf-8 -*-
""""Soon", "late" and "nothing is picking up" were one answer: an empty queue.

The picker is the scheduler's tick. If it is alive a run waits one tick; if it is not, a
run waits forever - measured 2026-09-05 across three runs at 3.0s, 3.0s and 320.5s, with
nothing in between. So queue LENGTH cannot separate the three, and the age of the last
pickup can: a short queue with an old pickup is the state that looked like an idle one.

⛔ No distribution (the waits are two peaks, and drawing a spread draws a middle that does
not exist) and no predicted start time (the peaks differ hundredfold, so one number would
be false most of the time).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import retroactive                                               # noqa: E402
from database import models                                      # noqa: E402

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def add(db, run_id, state, *, queued_ago=None, started_ago=None, runner=None):
    db.add(models.RetroactiveRun(
        run_id=run_id, op="ledger_rescope", state=state,
        queued_at=None if queued_ago is None else NOW - timedelta(seconds=queued_ago),
        started_at=None if started_ago is None else NOW - timedelta(seconds=started_ago),
        runner=runner))
    db.flush()


def test_an_idle_queue_and_a_dead_picker_are_different_answers(db_session):
    """🔴 THE WHOLE POINT. Both have an empty waiting list; only the pickup age differs."""
    add(db_session, "recent", "done", queued_ago=100, started_ago=97)
    fresh = retroactive.queue_view(db_session, now=NOW)
    assert fresh["waiting_count"] == 0
    assert fresh["last_pickup_age_seconds"] == pytest.approx(97, abs=1)


def test_the_pickup_age_is_the_newest_start_not_the_oldest(db_session):
    add(db_session, "old", "done", queued_ago=9000, started_ago=8990)
    add(db_session, "new", "done", queued_ago=300, started_ago=290)
    out = retroactive.queue_view(db_session, now=NOW)
    assert out["last_pickup_age_seconds"] == pytest.approx(290, abs=1)


def test_nothing_ever_picked_up_reports_none_not_zero(db_session):
    """`None` is "never", and 0 would read as "just now" - the opposite fact."""
    add(db_session, "queued_only", "queued", queued_ago=30)
    out = retroactive.queue_view(db_session, now=NOW)
    assert out["last_pickup_at"] is None
    assert out["last_pickup_age_seconds"] is None


def test_waiting_runs_are_listed_oldest_first_with_the_server_counting_position(db_session):
    """🔴 THE SERVER COUNTS. A screen counting its own rows would answer a different
    question whenever the list is capped or reordered."""
    add(db_session, "second", "queued", queued_ago=60)
    add(db_session, "first", "queued", queued_ago=120)
    out = retroactive.queue_view(db_session, now=NOW)
    assert [w["run_id"] for w in out["waiting"]] == ["first", "second"]
    assert [w["ahead"] for w in out["waiting"]] == [0, 1]
    assert out["waiting"][0]["waiting_seconds"] == pytest.approx(120, abs=1)
    assert out["waiting_count"] == 2


def test_a_running_row_whose_pid_is_gone_is_reported_orphaned(db_session, monkeypatch):
    import socket

    import psutil
    monkeypatch.setattr(psutil, "pid_exists", lambda pid: False)
    add(db_session, "stuck", "running", queued_ago=900, started_ago=880,
        runner="%s/424242" % socket.gethostname())
    out = retroactive.queue_view(db_session, now=NOW)
    assert [o["run_id"] for o in out["orphaned"]] == ["stuck"]
    assert out["orphaned"][0]["owner"] == "orphaned"


def test_a_live_pid_is_not_orphaned(db_session, monkeypatch):
    import socket

    import psutil
    monkeypatch.setattr(psutil, "pid_exists", lambda pid: True)
    add(db_session, "working", "running", queued_ago=90, started_ago=80,
        runner="%s/4242" % socket.gethostname())
    assert retroactive.queue_view(db_session, now=NOW)["orphaned"] == []


def test_a_pid_on_another_host_is_unknown_rather_than_dead(db_session, monkeypatch):
    """⚠️ Calling a foreign pid dead is how "never finishes" becomes "two at once"."""
    import psutil
    monkeypatch.setattr(psutil, "pid_exists", lambda pid: False)
    add(db_session, "elsewhere", "running", queued_ago=900, started_ago=880,
        runner="some-other-host/9")
    out = retroactive.queue_view(db_session, now=NOW)
    assert [o["owner"] for o in out["orphaned"]] == ["unknown"]


def test_no_distribution_and_no_predicted_start_are_published(db_session):
    """Both were asked for at some point and both were retired by measurement. A field
    reappearing here is a number that would be false most of the time."""
    add(db_session, "queued_only", "queued", queued_ago=30)
    out = retroactive.queue_view(db_session, now=NOW)
    for banned in ("eta", "eta_seconds", "expected_start", "median_wait_seconds",
                   "wait_distribution", "p50_wait_seconds"):
        assert banned not in out, "%s is a predicted number, not a value" % banned
