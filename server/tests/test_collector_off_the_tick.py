# -*- coding: utf-8 -*-
"""A collector must not be able to take the heartbeat down with it.

WHY
---
`run()` emits `heartbeat.beat("scheduler")` once per tick, and `check_and_run_schedules`
called `execute_collector` from that same thread - so for the whole duration of a cron
collector's user script there was no beat, and `/health` reported the daemon as making no
progress. On 2026-09-04 that reading cost two hours spent looking at a chain worker that
was fine: the tick was blocked, so the outbox poll in the same loop did not run either,
and a queued RETROACTIVE_RUN row aged in place looking like the culprit.

🔴 THE PROPERTY MEASURED HERE IS "THE CALL RETURNS WHILE THE WORK IS STILL RUNNING",
because that is precisely what lets the next beat happen. Asserting on the beat file
instead would measure `heartbeat`, which was never the broken part.

⚠️ AND THE DOOR IS NOT OPTIONAL. Until this change the INLINE CALL was the door: the tick
could not come round and fire the same collector again while it was inside one. Taking the
work off the tick removes that accident, and `execute_collector` advances `next_run` at
its start - in the thread - so without an explicit claim the next tick can see the old
`next_run` and start the same collector twice. A cron collector that ran twice is not
something an operator can undo.
"""
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from run_auto_update import MultiDiscoveryScheduler                 # noqa: E402


class SlowCollector:
    """A collector whose script takes time - load, not a fixture value."""

    table_name = "probe_table"
    script_path = "/probe/slow_collector.py"
    cron_expression = None

    def __init__(self, seconds=0.4, raises=False):
        self.seconds, self.raises = seconds, raises
        self.started = threading.Event()
        self.finished = threading.Event()
        self.runs = 0

    def execute(self):
        self.runs += 1
        self.started.set()
        time.sleep(self.seconds)
        self.finished.set()
        if self.raises:
            raise RuntimeError("the collector's script failed")


@pytest.fixture
def scheduler(tmp_path, monkeypatch):
    s = MultiDiscoveryScheduler(check_interval=5, server_dir=str(tmp_path))
    # The status file write is not what these cases are about, and it would put this
    # test's probe rows in a real config directory.
    monkeypatch.setattr(s, "_write_status_file", lambda *a, **k: None)
    return s


def test_the_tick_is_free_while_the_collector_is_still_running():
    """🔴 THE GATE. `start_collector` must come back before the work does - that is the
    whole difference between a beat that keeps going and one that stops for the length of
    a user script."""
    s = MultiDiscoveryScheduler(check_interval=5, server_dir=os.getcwd())
    s._write_status_file = lambda *a, **k: None
    collector = SlowCollector(seconds=0.5)

    began = time.monotonic()
    assert s.start_collector(collector) is True
    returned_after = time.monotonic() - began

    assert collector.started.wait(2.0), "the collector never started"
    assert not collector.finished.is_set(), "the call waited for the work"
    assert returned_after < 0.25, (
        "start_collector took %.3fs; the tick was blocked for that long and so was the "
        "beat" % returned_after)
    assert collector.finished.wait(3.0)


def test_the_CRON_PATH_is_the_one_that_must_not_block(scheduler):
    """🔴 THIS IS THE TEST THAT ACTUALLY PINS THE FIX, and it was missing at first: every
    case around it drives `start_collector` directly, so putting the inline call back in
    `check_and_run_schedules` left them all green. The defect lived in the CALLER.

    A due cron collector is fired through the real scheduling pass, and the pass has to
    come back while the collector is still inside its script.
    """
    from datetime import datetime, timedelta

    collector = SlowCollector(seconds=0.5)
    collector.cron_expression = "*/5 * * * *"
    collector.next_run = datetime.now() - timedelta(minutes=1)      # due
    scheduler.collectors = [collector]

    began = time.monotonic()
    scheduler.check_and_run_schedules()
    returned_after = time.monotonic() - began

    assert collector.started.wait(2.0), "the due collector never ran"
    assert not collector.finished.is_set(), (
        "check_and_run_schedules waited for the collector - the tick, and the beat with "
        "it, were blocked for the length of a user script")
    assert returned_after < 0.25, "the scheduling pass took %.3fs" % returned_after
    assert collector.finished.wait(3.0)


def test_the_same_collector_cannot_be_started_twice(scheduler):
    """The door. Without it the next tick - five seconds later, or sooner on a busy
    machine - can fire the same collector again before `next_run` has moved."""
    collector = SlowCollector(seconds=0.5)
    assert scheduler.start_collector(collector) is True
    assert collector.started.wait(2.0)
    assert scheduler.start_collector(collector) is False, "a second run was started"
    assert collector.finished.wait(3.0)
    time.sleep(0.1)
    assert collector.runs == 1


def test_the_claim_is_released_when_the_run_ends(scheduler):
    collector = SlowCollector(seconds=0.05)
    assert scheduler.start_collector(collector) is True
    assert collector.finished.wait(3.0)
    for _ in range(50):
        if scheduler.start_collector(collector):
            break
        time.sleep(0.02)
    else:
        pytest.fail("the collector could never be started again")


def test_a_collector_that_raises_still_releases_its_claim(scheduler):
    """🔴 A claim left behind by a failing collector would refuse that collector FOREVER,
    and on a screen that looks identical to a schedule that quietly stopped working."""
    collector = SlowCollector(seconds=0.05, raises=True)
    assert scheduler.start_collector(collector) is True
    assert collector.finished.wait(3.0)
    for _ in range(50):
        if scheduler.start_collector(collector):
            break
        time.sleep(0.02)
    else:
        pytest.fail("a raising collector kept its claim")


def test_the_on_demand_trigger_uses_the_same_door(scheduler):
    """It already ran on its own thread, so it was never the beat's problem - but it had
    no door at all, which let an on-demand run overlap a cron run of the same collector.
    One door, both entrances."""
    collector = SlowCollector(seconds=0.5)
    scheduler.collectors = [collector]
    assert scheduler.run_collector_on_demand("probe_table", "slow_collector.py") is True
    assert collector.started.wait(2.0)
    assert scheduler.run_collector_on_demand("probe_table", "slow_collector.py") is False
    assert collector.finished.wait(3.0)
    time.sleep(0.1)
    assert collector.runs == 1
