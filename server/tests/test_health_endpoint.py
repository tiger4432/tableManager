"""B2 - the /health contract, and the progress heartbeats it is built on.

The two failures this must not repeat:

* Before this route existed, `/health` fell through to the SPA catch-all and
  returned **HTML with a 200**. An external monitor would have called a dead
  server alive. `test_health_is_json_while_a_bogus_path_is_still_html` fails if
  that shadowing ever comes back.
* The production incident was an event-loop freeze - the process was alive and
  serving nothing. A pid check would have said healthy. So the worker verdict is
  driven by a progress beat, and `test_worker_alive_but_wedged_is_unhealthy` is
  the test that would fail if that were weakened back to an existence check.
"""
import os
import time
import json
import pytest

import health as health_mod
from health import compute_health, STATUS_OK, STATUS_DEGRADED, STATUS_UNHEALTHY
from utils import heartbeat


DB_OK = {"status": "ok", "latency_ms": 1.0}
OUTBOX_OK = {"pending": 0, "pending_capped": False, "oldest_age_seconds": None}
STALE_AFTER = 60.0


def supervisor_status(children, updated_age=0.0, failed=()):
    """Build a supervisor status file body as the launcher would write it."""
    return {
        "supervisor_pid": 42,
        "updated_at": time.time() - updated_age,
        "failed_children": list(failed),
        "children": children,
        "events": [],
    }


def running(hb_name, uptime=3600.0, pid=101, restarts=0):
    return {"state": "running", "heartbeat": hb_name, "pid": pid,
            "restarts": restarts, "uptime_seconds": uptime,
            "last_exit_code": None, "failure_reason": None}


def fresh(age=1.0):
    return {"pid": 101, "beats": 500, "age_seconds": age, "stale": False,
            "stale_after_seconds": STALE_AFTER}


def stale(age=180.0):
    return {"pid": 101, "beats": 500, "age_seconds": age, "stale": True,
            "stale_after_seconds": STALE_AFTER}


def run(db=DB_OK, hbs=None, sup=None, outbox=OUTBOX_OK):
    return compute_health(db, hbs if hbs is not None else {}, sup, outbox, STALE_AFTER)


# ------------------------------------------------------- the healthy baseline
def test_everything_working_is_ok_and_200():
    payload, code = run(hbs={"chain": fresh()},
                        sup=supervisor_status({"Chain": running("chain")}))
    assert code == 200
    assert payload["status"] == STATUS_OK
    assert payload["problems"] == []
    assert payload["checks"]["workers"]["chain"]["status"] == "ok"


# --------------------------------------------- the case a pid check cannot see
def test_worker_alive_but_wedged_is_unhealthy():
    """Supervisor says the process is running; it has stopped making progress."""
    payload, code = run(hbs={"chain": stale(age=180.0)},
                        sup=supervisor_status({"Chain": running("chain")}))
    assert code == 503, "a wedged worker must not be reported as healthy"
    assert payload["status"] == STATUS_UNHEALTHY
    w = payload["checks"]["workers"]["chain"]
    assert w["status"] == "wedged"
    assert w["supervisor_state"] == "running", \
        "the point of this case is that the process is still alive"
    assert any("no progress" in p for p in payload["problems"])


def test_the_same_worker_with_a_fresh_beat_is_ok():
    """Control: the only difference from the test above is beat age. Without
    this, 'wedged' could be produced by something other than staleness."""
    payload, code = run(hbs={"chain": fresh()},
                        sup=supervisor_status({"Chain": running("chain")}))
    assert code == 200 and payload["checks"]["workers"]["chain"]["status"] == "ok"


def test_dead_worker_is_unhealthy_and_named_down_not_wedged():
    dead = {"state": "backoff", "heartbeat": "watcher", "pid": None, "restarts": 2,
            "uptime_seconds": None, "last_exit_code": 1, "failure_reason": None}
    payload, code = run(hbs={"watcher": stale()},
                        sup=supervisor_status({"Watcher": dead}))
    assert code == 503
    w = payload["checks"]["workers"]["watcher"]
    assert w["status"] == "down", "a dead process and a wedged one need different names"
    assert w["restarts"] == 2


def test_permanently_failed_child_keeps_health_non_200():
    failed = {"state": "failed", "heartbeat": "watcher", "pid": None, "restarts": 5,
              "uptime_seconds": None, "last_exit_code": 1,
              "failure_reason": "exited 6 times in a row"}
    payload, code = run(hbs={}, sup=supervisor_status({"Watcher": failed},
                                                      failed=["Watcher"]))
    assert code == 503
    assert any("permanently failed" in p for p in payload["problems"])
    assert payload["checks"]["supervisor"]["failed_children"] == ["Watcher"]


def test_a_beat_from_another_process_does_not_count():
    """Found by drill, not by design review: a concurrent isolated stack sharing
    the data root kept chain.json fresh while the SUPERVISED chain worker was
    suspended, and /health said ok. Heartbeat files are keyed by role, so a beat
    is only evidence about the process the supervisor actually started."""
    payload, code = run(
        hbs={"chain": dict(fresh(), pid=999)},          # a stray same-role process
        sup=supervisor_status({"Chain": running("chain", pid=101)}))
    assert code == 503, "a stray worker must not be able to mask a wedged one"
    w = payload["checks"]["workers"]["chain"]
    assert w["status"] == "foreign_beat"
    assert w["beat_pid"] == 999
    assert "999" in w["detail"] and "101" in w["detail"]


def test_a_dead_predecessors_beat_does_not_cover_a_replacement():
    """The same check closes a second hole: just after a restart the previous
    process's beat is still fresh, so a replacement that dies before reaching its
    loop would look healthy for a whole staleness window."""
    payload, code = run(
        hbs={"watcher": dict(fresh(age=3.0), pid=555)},  # the process that just died
        sup=supervisor_status({"Watcher": running("watcher", pid=777,
                                                  uptime=health_mod.STARTUP_GRACE_SEC + 5,
                                                  restarts=1)}))
    assert code == 503
    assert payload["checks"]["workers"]["watcher"]["status"] == "foreign_beat"


def test_pid_mismatch_inside_the_startup_grace_is_only_degraded():
    """Immediately after a restart the mismatch is expected and must not page."""
    payload, code = run(
        hbs={"watcher": dict(fresh(), pid=555)},
        sup=supervisor_status({"Watcher": running("watcher", pid=777, uptime=3.0)}))
    assert code == 200
    assert payload["checks"]["workers"]["watcher"]["status"] == "starting"


def test_matching_pid_is_the_control():
    """Same shape as the two tests above, differing only in the pid - so their
    failure really is caused by the mismatch."""
    payload, code = run(hbs={"chain": dict(fresh(), pid=101)},
                        sup=supervisor_status({"Chain": running("chain", pid=101)}))
    assert code == 200 and payload["checks"]["workers"]["chain"]["status"] == "ok"


def test_a_starting_worker_is_not_an_alarm():
    """A 503 on every boot would train the operator to ignore this endpoint."""
    payload, code = run(hbs={}, sup=supervisor_status(
        {"Chain": running("chain", uptime=5.0)}))
    assert code == 200
    assert payload["status"] == STATUS_DEGRADED
    assert payload["checks"]["workers"]["chain"]["status"] == "starting"


def test_a_worker_up_past_the_grace_with_no_beat_is_unhealthy():
    payload, code = run(hbs={}, sup=supervisor_status(
        {"Chain": running("chain", uptime=health_mod.STARTUP_GRACE_SEC + 1)}))
    assert code == 503
    assert payload["checks"]["workers"]["chain"]["status"] == "missing"


def test_supervisor_itself_dead_is_unhealthy():
    """Children can keep beating while nothing is left to restart them."""
    payload, code = run(hbs={"chain": fresh()},
                        sup=supervisor_status({"Chain": running("chain")},
                                              updated_age=600.0))
    assert code == 503
    assert payload["checks"]["supervisor"]["status"] == "stale"
    assert any("supervisor itself is not running" in p for p in payload["problems"])


def test_no_supervisor_is_advisory_not_a_failure():
    """A bare uvicorn or the isolated dev stack has no launcher."""
    payload, code = run(hbs={"chain": fresh()}, sup=None)
    assert code == 200
    assert payload["checks"]["supervisor"]["status"] == "absent"
    assert payload["checks"]["workers"]["chain"]["status"] == "ok"


def test_no_supervisor_still_flags_a_stale_beat():
    payload, code = run(hbs={"chain": stale()}, sup=None)
    assert code == 503
    assert payload["checks"]["workers"]["chain"]["status"] == "stale"


# ----------------------------------------------------------------- database
def test_database_down_is_unhealthy():
    payload, code = run(db={"status": "down", "error": "connection refused"},
                        hbs={"chain": fresh()},
                        sup=supervisor_status({"Chain": running("chain")}))
    assert code == 503
    assert any("database unreachable" in p for p in payload["problems"])


def test_database_timeout_is_degraded_not_silent():
    payload, code = run(db={"status": "timeout", "error": "no answer within 2.0s"},
                        hbs={"chain": fresh()},
                        sup=supervisor_status({"Chain": running("chain")}),
                        outbox={"status": "unavailable"})
    assert payload["status"] == STATUS_DEGRADED
    assert any("timed out" in p for p in payload["problems"])


# ------------------------------------------------------------------- outbox
def test_outbox_backlog_age_escalates():
    base = {"pending": 5000, "pending_capped": False}
    ok, code_ok = run(hbs={"chain": fresh()},
                      outbox=dict(base, oldest_age_seconds=10.0))
    assert code_ok == 200 and ok["checks"]["outbox"]["status"] == STATUS_OK, \
        "a large but draining backlog is normal during a bulk ingestion"

    warn, code_warn = run(hbs={"chain": fresh()},
                          outbox=dict(base, oldest_age_seconds=
                                      health_mod.OUTBOX_AGE_DEGRADED_SEC + 1))
    assert code_warn == 200 and warn["status"] == STATUS_DEGRADED

    bad, code_bad = run(hbs={"chain": fresh()},
                        outbox=dict(base, oldest_age_seconds=
                                    health_mod.OUTBOX_AGE_UNHEALTHY_SEC + 1))
    assert code_bad == 503
    assert any("not draining" in p for p in bad["problems"])


def test_outbox_count_is_capped():
    """A count that scales with the table would make /health expensive to poll."""
    assert health_mod.OUTBOX_COUNT_CAP <= 10000


# ------------------------------------------------------- routing, not shadowed
def test_health_is_json_while_a_bogus_path_is_still_html(client):
    """The regression that made B2 necessary: an unrouted path returns index.html
    with a 200, so /health must be genuinely routed above the catch-all."""
    bogus = client.get("/definitely-not-a-real-path-9c41ab7e")
    assert bogus.status_code == 200
    assert bogus.headers["content-type"].startswith("text/html"), \
        "fixture broken: the SPA catch-all is not active, so this proves nothing"

    r = client.get("/health")
    assert r.headers["content-type"].startswith("application/json"), \
        "/health is being shadowed by the SPA catch-all"
    body = r.json()
    assert "status" in body and "checks" in body


def test_health_route_returns_503_when_unhealthy(client, monkeypatch):
    monkeypatch.setattr("main._health_probe_db_sync",
                        lambda: ({"status": "down", "error": "refused"},
                                 {"status": "unavailable"}))
    monkeypatch.setattr(heartbeat, "read_all", lambda *a, **k: {})
    r = client.get("/health")
    assert r.status_code == 503
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["status"] == STATUS_UNHEALTHY


def test_health_route_returns_200_when_everything_is_fine(client, monkeypatch):
    import process_supervisor
    monkeypatch.setattr("main._health_probe_db_sync",
                        lambda: (DB_OK, dict(OUTBOX_OK)))
    monkeypatch.setattr(heartbeat, "read_all", lambda *a, **k: {"chain": fresh()})
    monkeypatch.setattr(process_supervisor, "read_status",
                        lambda *a, **k: supervisor_status({"Chain": running("chain")}))
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == STATUS_OK


def test_health_survives_a_probe_that_raises(client, monkeypatch):
    def boom():
        raise RuntimeError("psycopg2 exploded")
    monkeypatch.setattr("main._health_probe_db_sync", boom)
    monkeypatch.setattr(heartbeat, "read_all", lambda *a, **k: {})
    r = client.get("/health")
    assert r.status_code == 503
    assert "psycopg2 exploded" in json.dumps(r.json())


# ---------------------------------------------------------------- heartbeats
@pytest.fixture
def hb_dir(tmp_path, monkeypatch):
    d = str(tmp_path / "worker_heartbeats")
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: d)
    monkeypatch.setattr(heartbeat, "heartbeat_path",
                        lambda name: os.path.join(d, f"{name}.json"))
    heartbeat._state.clear()
    yield d
    heartbeat._state.clear()


def test_beat_is_readable_and_fresh(hb_dir):
    assert heartbeat.beat("chain", note="idle") is True
    all_hb = heartbeat.read_all()
    assert all_hb["chain"]["stale"] is False
    assert all_hb["chain"]["pid"] == os.getpid()
    assert all_hb["chain"]["beats"] == 1


def test_beat_goes_stale_with_age(hb_dir):
    heartbeat.beat("chain")
    future = time.time() + 3600.0
    assert heartbeat.read_all(stale_after=60.0, now=future)["chain"]["stale"] is True
    assert heartbeat.read_all(stale_after=7200.0, now=future)["chain"]["stale"] is False


def test_beat_is_throttled_but_still_counted(hb_dir):
    """A loop draining a backlog can spin fast; it must not hammer the disk."""
    for _ in range(50):
        heartbeat.beat("chain")
    assert heartbeat._state["chain"]["beats"] == 50
    written = heartbeat.read_all()["chain"]["beats"]
    assert written < 50, "throttle is not working"


def test_beat_never_raises_into_the_worker_loop(hb_dir, monkeypatch):
    """Monitoring must not become a new failure mode."""
    def explode(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(heartbeat.os, "makedirs", explode)
    assert heartbeat.beat("chain", force=True) is False
    assert heartbeat._state["chain"]["errors"] == 1


def test_corrupt_heartbeat_is_reported_stale_not_skipped(hb_dir):
    """Silence is the one answer a health check must never give."""
    os.makedirs(hb_dir, exist_ok=True)
    with open(os.path.join(hb_dir, "chain.json"), "w", encoding="utf-8") as f:
        f.write("{ this is not json")
    entry = heartbeat.read_all()["chain"]
    assert entry["stale"] is True
    assert "unreadable" in entry["error"]


def test_stale_threshold_covers_at_least_ten_loop_periods():
    """The threshold must never be so tight that one missed beat trips it."""
    slowest_loop_period = 5.0  # auto-update scheduler check_interval
    assert heartbeat.DEFAULT_STALE_AFTER_SEC >= 10 * slowest_loop_period
