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


# ---------------------------------------------------------------------------
# 총괄 8e54a261b ③ · c44a7d2e4 — a stamp on the run, and an ending that lands
# ---------------------------------------------------------------------------

class _Registered:
    """What `discover_and_load_collectors` registers - every field the status file writes."""
    table_name = "probe_table"
    script_path = "/probe/reloaded.py"
    cron_expression = None
    next_run = None

    def __init__(self, on_execute=None):
        self.last_run, self.last_status, self.last_error, self.runner = None, "PENDING", None, None
        self.on_execute = on_execute

    def execute(self):
        if self.on_execute:
            self.on_execute()


def _status_file(tmp_path):
    import json

    with open(os.path.join(str(tmp_path), "config", "scheduler_status.json"),
              encoding="utf-8") as fh:
        return json.load(fh)["collectors"]


def test_a_run_is_stamped_with_the_process_that_runs_it(tmp_path):
    from utils import heartbeat

    s = MultiDiscoveryScheduler(check_interval=5, server_dir=str(tmp_path))
    seen = {}
    collector = _Registered(on_execute=lambda: seen.update(_status_file(tmp_path)[0]))
    s.collectors = [collector]

    s.execute_collector(collector)

    assert seen["last_status"] == "RUNNING"
    assert seen["runner"] == heartbeat.runner_identity()
    assert seen["runner"].endswith("/%d" % os.getpid())


def test_a_run_that_outlives_a_reload_ends_on_the_collector_registered_now(tmp_path):
    """④ — a reload mid-run registers a NEW object carrying the restored RUNNING, and the
    file is written from the registry: the run's ending has to land there."""
    s = MultiDiscoveryScheduler(check_interval=5, server_dir=str(tmp_path))
    reloaded = _Registered()

    def reload_mid_run():
        reloaded.last_status, reloaded.runner = old.last_status, old.runner
        s.collectors = [reloaded]

    old = _Registered(on_execute=reload_mid_run)
    s.collectors = [old]

    s.execute_collector(old)

    assert reloaded.last_status == "SUCCESS"
    assert [row["last_status"] for row in _status_file(tmp_path)] == ["SUCCESS"]


# ---------------------------------------------------------------------------
# 총괄 bfcf2a7ba 3-ㄴ — a restart restores each last run, and ends the run it cut off
# ---------------------------------------------------------------------------

_CUT_AT = "2026-09-26 07:00:00"
_DEAD = "scheduler/HOST/999999"


@pytest.mark.parametrize("before, after, queue", [
    # its scheduler was killed a moment ago - that beat is still fresh on disk
    (("RUNNING", _DEAD), ("FAIL", "cut off"), []),
    # a run that finished before the restart
    (("SUCCESS", _DEAD), ("SUCCESS", None), []),
    # written before runs were stamped: unknown, and read as it is
    (("RUNNING", None), ("RUNNING", None), ["unknown"]),
])
def test_a_restart_restores_the_last_run_and_ends_the_run_it_cut_off(
        tmp_path, monkeypatch, before, after, queue):
    import json

    import run_auto_update
    from runtime import running
    from utils import auto_update_control as auc
    from utils import heartbeat

    beats = tmp_path / "heartbeats"
    beats.mkdir()
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(beats))
    monkeypatch.setattr(heartbeat, "heartbeat_path",
                        lambda name: os.path.join(str(beats), "%s.json" % name))
    monkeypatch.setattr(heartbeat, "_own_name", heartbeat._own_name)
    monkeypatch.setattr(auc, "SERVER_DIR", str(tmp_path))
    (beats / "scheduler.json").write_text(json.dumps(
        {"name": "scheduler", "pid": 999999, "ts": time.time(), "beats": 1,
         "started_at": time.time(), "note": None, "work": {}, "laps": {}}), encoding="utf-8")
    script = tmp_path / "ingestion_workspace" / "t_probe" / "auto_update" / "pull.py"
    script.parent.mkdir(parents=True)
    script.write_text("# schedule: 0 0 1 1 *\nout = []\n", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "scheduler_status.json").write_text(json.dumps({"collectors": [
        {"table_name": "t_probe", "script_name": "pull.py", "last_run": _CUT_AT,
         "last_status": before[0], "last_error": None, "runner": before[1]}]}),
        encoding="utf-8")

    class _Started(Exception):
        pass

    s = MultiDiscoveryScheduler(check_interval=5, server_dir=str(tmp_path))
    restore = s.discover_and_load_collectors

    def restore_then_stop():
        restore()
        raise _Started

    monkeypatch.setattr(s, "discover_and_load_collectors", restore_then_stop)
    with pytest.raises(_Started):
        s.run()                                  # the way a restarted scheduler starts

    [row] = _status_file(tmp_path)
    reason = {"cut off": run_auto_update.COLLECTOR_CUT_OFF}.get(after[1], after[1])
    assert (row["last_run"], row["last_status"], row["last_error"]) == (_CUT_AT, after[0], reason)
    assert [i["state"] for i in running._collectors(None)] == queue
