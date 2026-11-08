# -*- coding: utf-8 -*-
"""Lead 11-08 (QA on the retroactive release):

  ① one automatic release   `release_dead_runs` (judgement `heartbeat.runner_gone`, one sentence) - the chain worker
                            asks it for its own ops; a runner this host cannot judge is the ×'s, and the queue says so
  ② its own output          each run's process prints to its own file; the row quotes that run's line, the file goes
  ③ the start's window      the scheduler died between the child's start and its stamp: the row names a dead pid, the
                            child beats holding the run - the next scheduler does not release it
"""
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from admin import retroactive                                        # noqa: E402
from database import models                                          # noqa: E402
from utils import heartbeat                                          # noqa: E402

HOST = socket.gethostname()


class _Kept:
    """The run row's own session, never closed under the test."""

    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


@pytest.fixture(name="db")
def fixture_db(db_session, monkeypatch, tmp_path):
    import paths
    from database.database import Base

    Base.metadata.create_all(bind=db_session.get_bind())
    monkeypatch.setattr("database.database.SessionLocal", lambda: _Kept(db_session))
    monkeypatch.setattr(paths, "log_path", lambda name: str(tmp_path / name))
    path = heartbeat.heartbeat_path(retroactive.RUN_HERE_HEARTBEAT)
    if os.path.exists(path):
        os.remove(path)
    yield db_session


def _dead_pid():
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait()
    return done.pid


def _row(db, run_id, runner, op="withdraw"):
    db.add(models.RetroactiveRun(run_id=run_id, op=op, params="{}", state=retroactive.RUN_RUNNING, runner=runner,
                                 started_at=datetime.now(timezone.utc)))
    db.commit()


def _state(db, run_id):
    db.expire_all()
    row = db.query(models.RetroactiveRun).filter_by(run_id=run_id).one()
    return row.state, row.error


def test_a_child_beating_for_its_run_is_not_released_under_a_dead_scheduler_s_name(db):
    """③ - the row still names the scheduler that died before it stamped the child."""
    _row(db, "w1", "auto_update/%s/%d" % (HOST, _dead_pid()))
    heartbeat.beat(retroactive.RUN_HERE_HEARTBEAT, note="holds run w1", force=True)
    assert retroactive.release_dead_runs(log=lambda line: None) == []
    assert _state(db, "w1")[0] == retroactive.RUN_RUNNING
    os.remove(heartbeat.heartbeat_path(retroactive.RUN_HERE_HEARTBEAT))
    assert retroactive.release_dead_runs(log=lambda line: None) == ["w1"], "canary: no beat holds it - released"
    assert heartbeat.holding_note("w1") == "holds run w1", "the note a child beats is this one"


def test_a_child_names_itself_only_on_a_row_still_running(db):
    """③ - a row released while the child started keeps its end."""
    _row(db, "w2", "auto_update/%s/%d" % (HOST, _dead_pid()))
    retroactive._mark_run("w2", state=retroactive.RUN_FAILED, finished=True, error="released")
    with pytest.raises(retroactive.RetroactiveRefused):
        retroactive.run_claimed("w2", log=lambda line: None)
    db.expire_all()
    assert db.query(models.RetroactiveRun).filter_by(run_id="w2").one().runner.startswith("auto_update/")


def test_each_run_quotes_its_own_last_line_and_its_file_goes(db):
    """② - two runs' processes printed; the released one's row quotes its own line."""
    for run_id, line in (("a1", "OSError: a1 broke"), ("b1", "b1 still printing")):
        with open(retroactive.child_stdout(run_id), "w", encoding="utf-8") as sink:
            sink.write(line + "\n")
    _row(db, "a1", "%s/%s/%d" % (retroactive.RUN_HERE_HEARTBEAT, HOST, _dead_pid()))
    assert retroactive.release_dead_runs(log=lambda line: None) == ["a1"]
    state, error = _state(db, "a1")
    assert state == retroactive.RUN_FAILED and "a1 broke" in error and "b1" not in error, error
    assert not os.path.exists(retroactive.child_stdout("a1")) and os.path.exists(retroactive.child_stdout("b1"))


def test_the_chain_s_release_is_the_one_release_and_the_x_says_the_same(db):
    """① - a dead replay is released in the one sentence; one on another host is the ×'s, and the queue says so."""
    from chain import ingestion_worker
    from runtime import running

    _row(db, "c1", "chain/%s/%d" % (HOST, _dead_pid()), op="chain_replay")
    _row(db, "c2", "chain/elsewhere/%d" % _dead_pid(), op="chain_replay")
    assert ingestion_worker.release_dead_replays(db) == ["c1"]
    assert "runner gone" in _state(db, "c1")[1]
    items = running._retroactive(db, datetime.now(timezone.utc))
    assert [item["waiting"] for item in items] == [retroactive.HELD_UNSEEN]
    assert {run["run_id"]: run["waiting"] for run in retroactive.runs(db)}["c2"] == retroactive.HELD_UNSEEN, \
        "the runs list says what the queue says (lead 11-09)"
    retroactive.request_cancel(db, "c2")
    state, error = _state(db, "c2")
    assert state == retroactive.RUN_FAILED and error.startswith("runner gone: chain/elsewhere/"), error


def test_a_live_runner_in_its_first_seconds_is_asked_and_a_reused_pid_is_released(db):
    """Lead 11-09: a runner alive here with no beat yet - the child just started (its command line names the run) or a
    process older than the claim - is not «held» and the × asks it (cancel_requested), never releases it; a pid alive
    as ANOTHER process (started after the claim, not naming the run - reused) is dead: released, by the tick too."""
    import time
    from runtime import running

    _row(db, "live1", "placeholder")
    time.sleep(0.2)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "live1"])  # after its claim
    other = None
    try:
        db.query(models.RetroactiveRun).filter_by(run_id="live1").update(
            {"runner": "%s/%s/%d" % (retroactive.RUN_HERE_HEARTBEAT, HOST, child.pid)})
        db.commit()
        assert {run["run_id"]: run["waiting"] for run in retroactive.runs(db)}["live1"] is None, "not held"
        assert [item["waiting"] for item in running._retroactive(db, datetime.now(timezone.utc))] == [None]
        assert retroactive.release_dead_runs(log=lambda line: None) == []
        answer = retroactive.request_cancel(db, "live1")
        assert (answer["released"], _state(db, "live1")[0]) == (False, retroactive.RUN_CANCEL_REQUESTED), answer

        _row(db, "live2", "%s/%s/%d" % (retroactive.RUN_HERE_HEARTBEAT, HOST, os.getpid()))   # older than its claim
        assert retroactive.request_cancel(db, "live2")["released"] is False

        _row(db, "reused", "placeholder")
        time.sleep(0.2)
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])       # after the claim
        db.query(models.RetroactiveRun).filter_by(run_id="reused").update(
            {"runner": "%s/%s/%d" % (retroactive.RUN_HERE_HEARTBEAT, HOST, other.pid)})
        db.commit()
        assert heartbeat.pid_here("x/%s/%d" % (HOST, other.pid), "reused", time.time() - 0.1) is False
        assert retroactive.release_dead_runs(log=lambda line: None) == ["reused"], "a reused pid is a dead runner"
        assert "runner gone" in _state(db, "reused")[1]
    finally:
        child.kill()
        if other is not None:
            other.kill()


def test_a_run_cancelled_before_its_child_starts_ends_cancelled_not_runner_gone(db):
    """Lead 11-09 (box): × asked a run the scheduler had just handed to its child; the child read cancel_requested
    and left, and a minute later the tick released it «failed - runner gone - run it again». The child ends it."""
    _row(db, "x1", "%s/%s/%d" % (retroactive.RUN_HERE_HEARTBEAT, HOST, _dead_pid()))
    db.query(models.RetroactiveRun).filter_by(run_id="x1").update({"state": retroactive.RUN_CANCEL_REQUESTED})
    db.commit()
    with pytest.raises(retroactive.RetroactiveRefused):
        retroactive.run_claimed("x1", log=lambda line: None)
    assert _state(db, "x1") == (retroactive.RUN_CANCELLED, None)
    assert retroactive.release_dead_runs(log=lambda line: None) == [], "nothing left in flight for the tick"
