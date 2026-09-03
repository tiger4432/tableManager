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


@pytest.fixture(autouse=True)
def no_live_config_backup_probe(monkeypatch):
    """Keep the live config-backup probe out of this file's verdicts.

    Same class of leak as conftest's DATABASE_URL pin. The `/health` route does
    not take a backup argument, so `compute_health` runs its own probe against
    the real `server/config/` - which means `test_health_route_returns_200_...`
    would assert `ok` or `degraded` depending on whether THIS MACHINE happens to
    have a snapshot less than 10 days old. That is a suite whose result depends
    on whose laptop it runs on, and it was observed failing exactly that way.

    Returning None makes compute_health skip the check (see its docstring). The
    config-backup rows of the decision table are covered in test_config_backup.py,
    which injects explicit values instead.
    """
    monkeypatch.setattr(health_mod, "probe_config_backups", lambda now=None: None)
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


def run(db=DB_OK, hbs=None, sup=None, outbox=OUTBOX_OK, backup=None):
    # backup=None means "do not check config backups here". These cases are about
    # the database/worker/outbox decision table, and letting compute_health run its
    # own filesystem probe would make every one of them depend on whether the
    # machine happens to have a recent snapshot on disk. The config-backup rows of
    # the table are exercised explicitly in test_config_backup.py.
    return compute_health(db, hbs if hbs is not None else {}, sup, outbox,
                          STALE_AFTER, backup_result=backup)


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


def test_a_dead_supervisors_table_may_not_call_a_beating_worker_down():
    """🔴 THE CHECK ONE PARAGRAPH EARLIER HAS ALREADY SAID THIS FILE CANNOT BE
    READ AS THE PRESENT. Asserting "worker 'chain' is down (supervisor state:
    stopped)" out of the same file is that conclusion contradicted immediately -
    and here the refuting evidence is in the very same response, because the beat
    is fresh.

    Measured on this box 2026-09-04, which is what this test is made of: a
    14.2-day-old status file named three workers 'stopped' while two of them had
    written a beat 0.1 s and 0.6 s before the request. /health reported all three
    down. Nothing was wrong with the workers.

    What must NOT change: the supervisor problem itself stays, and so does 503.
    Nobody is watching those workers, and that is the real alarm - it is just not
    a claim about what they are doing.
    """
    stopped = {"state": "stopped", "heartbeat": "chain", "pid": None,
               "restarts": 0, "uptime_seconds": None, "last_exit_code": 0,
               "failure_reason": None}
    payload, code = run(hbs={"chain": fresh()},
                        sup=supervisor_status({"Chain": stopped},
                                              updated_age=600.0))
    assert code == 503
    assert payload["checks"]["workers"]["chain"]["status"] == "ok",         "a worker that beat one second ago was called down by a ten-minute-old file"
    assert not any("is down" in p for p in payload["problems"]), payload["problems"]
    assert any("supervisor itself is not running" in p for p in payload["problems"]),         "the real alarm was collapsed away with the false one"


def test_a_dead_supervisor_and_no_beat_is_unknown_not_a_claim():
    """With no beat there is nothing to contradict the table with - and still
    nothing that says what the worker is doing NOW. Unhealthy either way; the
    sentence is what this fixes.

    Both wordings this replaces asserted something unestablished: 'down' restates
    the dead table in the present tense, and the 'missing' branch says the process
    is running and has never beaten - a running process nobody has seen.
    """
    stopped = {"state": "stopped", "heartbeat": "chain", "pid": None,
               "restarts": 0, "uptime_seconds": None, "last_exit_code": 0,
               "failure_reason": None}
    payload, code = run(hbs={}, sup=supervisor_status({"Chain": stopped},
                                                      updated_age=600.0))
    assert code == 503
    w = payload["checks"]["workers"]["chain"]
    assert w["status"] == "unknown", w
    assert "stopped updating" in w["detail"], w
    assert "process is running" not in w["detail"],         "the replacement wording asserts a running process too"


def test_a_stale_beat_under_a_dead_supervisor_is_not_wedged():
    """'wedged' MEANS "alive but not progressing" - the suffix says so out loud:
    "although its process is alive". Both come from the same table that stopped
    being written, so both are the present-tense claim again, in the branch that
    LOOKS like it is reading the beat.

    'stale' is what the identical beat is called when there is no supervisor at
    all, and that is the honest name here too: the beat is old, and nothing
    trustworthy says whether a process is behind it.
    """
    stopped = {"state": "stopped", "heartbeat": "watcher", "pid": None,
               "restarts": 0, "uptime_seconds": None, "last_exit_code": 0,
               "failure_reason": None}
    payload, code = run(hbs={"watcher": stale()},
                        sup=supervisor_status({"Watcher": stopped},
                                              updated_age=600.0))
    assert code == 503
    assert payload["checks"]["workers"]["watcher"]["status"] == "stale",         "'wedged' asserts a live process, on the word of a file that stopped updating"
    assert not any("although its process is alive" in p for p in payload["problems"]),         payload["problems"]
    assert any("no progress" in p for p in payload["problems"]),         "the beat is genuinely old and that has to still be said"


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


# ===========================================================================
# Work claims: a beating worker that is wedged where it matters.
#
# The hole: the watcher's beat came from its 3 s retry poller, so a watcher
# wedged INSIDE ingestion kept beating and /health said ok - a hole in exactly
# the property this endpoint exists for, since the real incident was a process
# that was alive and not progressing.
# ===========================================================================

def working(what="ingest big.csv", no_progress=1.0, held=None, stalled=False):
    return {"open": 1, "what": what, "no_progress_seconds": no_progress,
            "held_seconds": held if held is not None else no_progress,
            "stalled": stalled,
            "stall_after_seconds": heartbeat.DEFAULT_STALL_AFTER_SEC}


def test_a_beating_worker_with_stalled_work_is_unhealthy():
    """The regression: fresh beat, stalled ingestion, must not be 200/ok."""
    hb = dict(fresh(age=1.0))
    hb["work"] = working(no_progress=612.0, stalled=True)
    payload, status = run(hbs={"watcher": hb},
                          sup=supervisor_status({"File Ingestion Watcher": running("watcher")}))
    assert status == 503, "a wedged ingestion behind a healthy poller reported 200"
    assert payload["status"] == STATUS_UNHEALTHY
    assert payload["checks"]["workers"]["watcher"]["status"] == "stalled"
    assert any("has not progressed" in p for p in payload["problems"])
    assert any("ingest big.csv" in p for p in payload["problems"]), \
        "the operator is not told WHICH unit of work is stuck"


def test_the_same_worker_with_progressing_work_is_ok():
    """The control that makes the test above attributable.

    Identical fixture except that the claim is advancing - so a failure of the
    test above is about the stall, not about the mere presence of a claim.
    """
    hb = dict(fresh(age=1.0))
    hb["work"] = working(no_progress=2.0, held=900.0, stalled=False)
    payload, status = run(hbs={"watcher": hb},
                          sup=supervisor_status({"File Ingestion Watcher": running("watcher")}))
    assert status == 200
    assert payload["status"] == STATUS_OK
    assert payload["checks"]["workers"]["watcher"]["status"] == STATUS_OK
    # A long-running ingestion is reported, just not as a problem.
    assert payload["checks"]["workers"]["watcher"]["work"]["held_seconds"] == 900.0


def test_idle_is_not_stalled():
    """No claim open means nothing to stall on - an idle watcher is healthy."""
    payload, status = run(hbs={"watcher": fresh()},
                          sup=supervisor_status({"File Ingestion Watcher": running("watcher")}))
    assert status == 200
    assert "work" not in payload["checks"]["workers"]["watcher"]


def test_a_stall_does_not_mask_a_worse_verdict():
    """down/wedged name a bigger problem than a stalled unit of work."""
    hb = dict(stale(age=200.0))
    hb["work"] = working(no_progress=612.0, stalled=True)
    payload, status = run(hbs={"watcher": hb},
                          sup=supervisor_status({"File Ingestion Watcher": running("watcher")}))
    assert status == 503
    assert payload["checks"]["workers"]["watcher"]["status"] == "wedged"


def test_claim_refreshes_only_on_its_own_thread(hb_dir):
    """Thread affinity, driven with real threads.

    Without it a healthy heavy-lane job would refresh a wedged inline job's
    claim just because both belong to the watcher, and the wedge would vanish.
    """
    import threading
    heartbeat._claims.clear()
    started = threading.Event()
    release = threading.Event()

    def holder():
        with heartbeat.work_claim("watcher", "wedged file"):
            started.set()
            release.wait(10.0)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    assert started.wait(5.0), "fixture broken: the claim was never opened"

    claims = heartbeat.open_claims()
    assert len(claims) == 1
    before = claims[0]["last_progress"]

    time.sleep(0.05)
    # A beat from THIS thread (standing in for the retry poller) must not
    # advance a claim held by the other one.
    heartbeat.beat("watcher", force=True)
    after = heartbeat.open_claims()[0]["last_progress"]
    assert after == before, \
        "another thread's beat refreshed a wedged claim - the wedge is masked"

    release.set()
    t.join(5.0)
    assert heartbeat.open_claims() == [], "the claim outlived its work"


def test_a_claim_is_released_even_when_the_work_raises(hb_dir):
    """A claim leaked by a failed ingestion would look like a stall forever."""
    heartbeat._claims.clear()
    with pytest.raises(ValueError):
        with heartbeat.work_claim("watcher", "doomed file"):
            raise ValueError("parser blew up")
    assert heartbeat.open_claims() == []


def test_the_pollers_beat_carries_the_wedged_threads_stall(hb_dir):
    """The whole mechanism, end to end, with two real threads.

    One thread holds a claim and stops progressing (the wedged ingestion); the
    other beats (the retry poller). The poller's beat is what reaches disk, and
    it must report the *other* thread's stall - that is what turns the poller
    from a mask over the wedge into the thing that reports it.

    Also pins the age to read time: a 30 s old beat must not under-report a
    stall by 30 s.
    """
    import threading
    heartbeat._claims.clear()
    holder_ready = threading.Event()
    release = threading.Event()

    def holder():
        with heartbeat.work_claim("watcher", "slow file"):
            # Backdate: no progress for 400 s.
            with heartbeat._state_lock:
                for c in heartbeat._claims.values():
                    c["last_progress"] -= 400.0
            holder_ready.set()
            release.wait(10.0)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    assert holder_ready.wait(5.0), "fixture broken: claim never opened"
    try:
        heartbeat.beat("watcher", force=True)       # the poller thread
        entry = heartbeat.read_all(now=time.time() + 30.0)["watcher"]
    finally:
        release.set()
        t.join(5.0)

    assert entry["stale"] is False, "fixture broken: the beat itself was stale"
    assert entry["work"]["no_progress_seconds"] >= 430.0
    assert entry["work"]["stalled"] is True


def test_stall_threshold_leaves_room_for_a_real_ingestion():
    """Measured, not guessed: under a live 100,000-row heavy-lane ingestion the
    worst chunk-to-chunk interval was 12.50 s (p50 9.20 s) over 42 unambiguous
    single-chunk intervals. The threshold must clear that by a wide margin or it
    fires during exactly the operation people care about."""
    measured_worst_chunk_gap = 12.50
    assert heartbeat.DEFAULT_STALL_AFTER_SEC >= 10 * measured_worst_chunk_gap
    assert heartbeat.DEFAULT_STALL_AFTER_SEC > heartbeat.DEFAULT_STALE_AFTER_SEC


def test_stale_threshold_survives_the_measured_load(hb_dir):
    """The 60 s beat-staleness threshold was justified on an IDLE stack (worst
    gap 10.26 s). Under a live 100k-row ingestion the worst beat gap across all
    four workers was 7.01 s - load did not eat the headroom."""
    measured_worst_beat_gap_under_load = 7.01
    assert heartbeat.DEFAULT_STALE_AFTER_SEC >= 8 * measured_worst_beat_gap_under_load


# ===========================================================================
# Shared-cause failure surfaced to the operator.
# ===========================================================================

def test_correlated_children_are_unhealthy_and_named_as_an_outage():
    """A shared-cause outage must be loudly unhealthy AND must tell the operator
    that no manual restart is needed - the response differs from a permanent
    failure, so the message has to differ too."""
    sup = supervisor_status({
        "File Ingestion Watcher": {"state": "retrying_correlated", "heartbeat": "watcher",
                                   "pid": None, "restarts": 9, "uptime_seconds": None,
                                   "last_exit_code": 1, "failure_reason": "shared cause",
                                   "correlated_with": ["Chained Ingestion Worker"],
                                   "correlated_retries": 4},
        "Chained Ingestion Worker": {"state": "retrying_correlated", "heartbeat": "chain",
                                     "pid": None, "restarts": 9, "uptime_seconds": None,
                                     "last_exit_code": 1, "failure_reason": "shared cause",
                                     "correlated_with": ["File Ingestion Watcher"],
                                     "correlated_retries": 4},
    })
    sup["correlated_children"] = ["File Ingestion Watcher", "Chained Ingestion Worker"]

    payload, status = run(hbs={"watcher": stale(), "chain": stale()}, sup=sup)
    assert status == 503
    assert payload["checks"]["supervisor"]["status"] == "correlated_failure"
    joined = " ".join(payload["problems"])
    assert "failing together" in joined
    assert "no manual restart is needed" in joined
    assert payload["checks"]["supervisor"]["correlated_children"]


def test_a_permanent_failure_still_reads_as_a_permanent_failure():
    """The control: the correlated branch must not have swallowed the other."""
    # The child named here is a FIXTURE, not an assertion about the stack - this
    # test drives synthetic supervisor state and never reads the launcher. It used
    # to name "Graph DB Sync Worker"/"graph", which R-2026-08-14-H retired; renamed
    # to a child that still exists so the fixture stops teaching a dead name.
    sup = supervisor_status(
        {"Chained Ingestion Worker": {"state": "failed", "heartbeat": "chain", "pid": None,
                                      "restarts": 5, "uptime_seconds": None,
                                      "last_exit_code": 1,
                                      "failure_reason": "exited 6 times in a row"}},
        failed=["Chained Ingestion Worker"])
    payload, status = run(hbs={"chain": stale()}, sup=sup)
    assert status == 503
    assert payload["checks"]["supervisor"]["status"] == "failed_children"
    assert any("permanently failed" in p for p in payload["problems"])
