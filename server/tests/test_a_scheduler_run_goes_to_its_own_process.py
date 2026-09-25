# -*- coding: utf-8 -*-
"""총괄 7d2c5845b · 811ff7f06 · f453968fe — a retroactive run the scheduler picks runs in a
process of its own, through the same function a CLI's run goes through. The scheduler claims
the row before the child exists, names the child as its runner, and a failed start ends the
row failed. An app stop asks the child to stop the screen's way, then kills it; a CLI's run,
which beats the same heartbeat, is not the app's to stop."""
import json
import os
import subprocess
import sys
import time

import pytest

from admin import retroactive
from database import models
from tests.test_a_cli_run_goes_through_the_admin_runs_door import _probe, _row
from tests.test_retroactive_admin import retro_env  # noqa: F401  - its session and tables


def _claimed(db, monkeypatch, on_page=lambda page: None, pages=2):
    _probe(monkeypatch, on_page)
    payload = retroactive.publish(db, "probe_op", {"pages": pages})
    assert retroactive.claim(run_id=payload["run_id"]) == payload["run_id"]
    return payload["run_id"]


def test_the_child_runs_a_claimed_row_and_names_itself(retro_env, monkeypatch):
    from utils import heartbeat

    run_id = _claimed(retro_env, monkeypatch)
    out = retroactive.run_claimed(run_id, log=lambda *_: None)

    row = _row(retro_env)
    assert (row.state, json.loads(row.result)) == (retroactive.RUN_DONE, {"pages_done": 2})
    assert row.runner.startswith(retroactive.RUN_HERE_HEARTBEAT + "/")
    assert row.runner.endswith("/%d" % os.getpid())
    assert out["stats"]["pages_done"] == 2
    assert not os.path.exists(heartbeat.heartbeat_path(retroactive.RUN_HERE_HEARTBEAT))


def test_a_row_that_is_not_running_is_not_run(retro_env, monkeypatch):
    """Cancelled or released while the child was starting - the child does not run it."""
    _probe(monkeypatch, lambda page: pytest.fail("ran a row that was not running"))
    payload = retroactive.publish(retro_env, "probe_op", {})
    with pytest.raises(retroactive.RetroactiveRefused, match="not running"):
        retroactive.run_claimed(payload["run_id"], log=lambda *_: None)
    assert _row(retro_env).state == retroactive.RUN_QUEUED


def test_a_claimed_row_whose_params_are_refused_ends_failed(retro_env, monkeypatch):
    run_id = _claimed(retro_env, monkeypatch)

    def refuse(op, params):
        raise retroactive.RetroactiveRefused("no")

    monkeypatch.setattr(retroactive, "validate", refuse)
    with pytest.raises(retroactive.RetroactiveRefused):
        retroactive.run_claimed(run_id, log=lambda *_: None)
    assert _row(retro_env).state == retroactive.RUN_FAILED


def test_the_scheduler_starts_the_child_and_names_it_the_runner(retro_env, monkeypatch):
    import socket

    run_id = _claimed(retro_env, monkeypatch)
    started = []

    class Child:
        pid = 777

    def popen(cmd, **kwargs):
        started.append(cmd)
        return Child()

    monkeypatch.setattr(subprocess, "Popen", popen)
    assert retroactive.spawn_claimed(run_id, log=lambda *_: None) == 777
    assert started == [[sys.executable, "-m", "admin.retroactive_run", run_id]]
    assert _row(retro_env).runner == "%s/%s/777" % (retroactive.RUN_HERE_HEARTBEAT,
                                                   socket.gethostname())


def test_a_child_that_cannot_start_ends_the_row_failed(retro_env, monkeypatch):
    run_id = _claimed(retro_env, monkeypatch)

    def popen(cmd, **kwargs):
        raise OSError("no such interpreter")

    monkeypatch.setattr(subprocess, "Popen", popen)
    assert retroactive.spawn_claimed(run_id, log=lambda *_: None) is None
    row = _row(retro_env)
    assert row.state == retroactive.RUN_FAILED and "could not start" in row.error


@pytest.mark.parametrize("outcome, code", [(None, 0), ("refused", 2), ("cancelled", 2),
                                           ("boom", 1)])
def test_the_child_says_how_it_ended_in_its_exit_code(monkeypatch, outcome, code):
    from admin import retroactive_run

    def run_claimed(run_id, log=None):
        if outcome == "refused":
            raise retroactive.RetroactiveRefused("gone")
        if outcome == "cancelled":
            raise retroactive.RunCancelled("stopped")
        if outcome == "boom":
            raise ValueError("boom")
        return {}

    monkeypatch.setattr(retroactive, "run_claimed", run_claimed)
    assert retroactive_run.main(["some-run"]) == code
    assert retroactive_run.main([]) == 2


# ------------------------------------------------------------------ the app stop (②)

def _beat_as(pid):
    from utils import heartbeat

    path = heartbeat.heartbeat_path(retroactive.RUN_HERE_HEARTBEAT)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"name": retroactive.RUN_HERE_HEARTBEAT, "pid": pid, "ts": time.time(),
                   "beats": 1, "started_at": time.time()}, f)
    return path


def _sleeper(tag):
    """A stand-in process whose command line carries `tag` - what tells the child apart."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", tag])


def test_nothing_running_is_nothing_to_stop():
    from runtime import process_supervisor

    assert process_supervisor.stop_retroactive_child(grace=0.1) == "none"


def test_an_app_stop_asks_the_child_to_stop_then_kills_it(retro_env, monkeypatch):
    from runtime import process_supervisor

    run_id = _claimed(retro_env, monkeypatch)
    child = _sleeper("admin.retroactive_run")
    path = _beat_as(child.pid)
    try:
        retroactive._restamp_runner(run_id, "retroactive/h/%d" % child.pid)
        assert process_supervisor.stop_retroactive_child(grace=0.5) == "killed"
        assert child.wait(5) is not None
        assert _row(retro_env).state == retroactive.RUN_CANCEL_REQUESTED, \
            "asked the screen's way first"
    finally:
        child.kill()
        if os.path.exists(path):
            os.remove(path)


def test_a_cli_run_is_not_the_apps_to_stop(retro_env, monkeypatch):
    from runtime import process_supervisor

    run_id = _claimed(retro_env, monkeypatch)
    cli = _sleeper("scripts/chain_replay_cli.py")
    path = _beat_as(cli.pid)
    try:
        retroactive._restamp_runner(run_id, "retroactive/h/%d" % cli.pid)
        assert process_supervisor.stop_retroactive_child(grace=0.1) == "not_ours"
        assert cli.poll() is None, "the operator's CLI was stopped"
        assert _row(retro_env).state == retroactive.RUN_RUNNING
    finally:
        cli.kill()
        if os.path.exists(path):
            os.remove(path)


def test_stop_all_stops_the_child_before_anything_else(monkeypatch):
    from runtime import process_supervisor

    asked = []
    monkeypatch.setattr(process_supervisor, "stop_retroactive_child",
                        lambda **k: asked.append("child"))
    process_supervisor.Supervisor([]).stop_all(timeout=0.1)
    assert asked == ["child"]
