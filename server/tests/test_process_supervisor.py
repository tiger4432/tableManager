"""B1 - child process supervision.

Every test here makes the thing the guard protects against actually happen: a
child dies, a child dies over and over, a spawn fails outright, a shutdown races
the monitor loop. Nothing is asserted about a code path that was not executed.

Real processes and real seconds are replaced by a fake process and a fake clock so
the restart *policy* - backoff growth, the attempt cap, the budget reset - is
tested deterministically rather than by sleeping and hoping. The live proof that
this drives real processes is in the isolated-environment run in the report.
"""
import os
import json
import time
import pytest

from process_supervisor import (
    ChildSpec, Supervisor, MAX_EVENTS,
    STATE_RUNNING, STATE_BACKOFF, STATE_FAILED, STATE_STOPPED,
    STATE_RETRYING_CORRELATED,
)


class FakeProc:
    def __init__(self, pid):
        self.pid = pid
        self._code = None
        self.terminated = False

    def poll(self):
        return self._code

    def die(self, code=1):
        self._code = code

    def terminate(self):
        self.terminated = True
        self._code = -15

    def wait(self, timeout=None):
        return self._code

    def kill(self):
        self._code = -9


class Harness:
    """A supervisor wired to a fake clock and a fake spawner."""

    def __init__(self, tmp_path, specs=None, **kw):
        self.now = 1000.0
        self.spawned = []
        self.next_pid = 100
        self.spawn_error = None
        self.logs = []
        specs = specs or [ChildSpec("worker", ["python", "w.py"], ".", heartbeat="w")]
        self.sup = Supervisor(
            specs,
            status_file=os.path.join(str(tmp_path), "supervisor_status.json"),
            log=lambda msg, level="INFO": self.logs.append((level, msg)),
            spawn=self._spawn,
            clock=lambda: self.now,
            sleep=lambda s: None,
            **kw
        )

    def _spawn(self, spec):
        if self.spawn_error:
            raise RuntimeError(self.spawn_error)
        self.next_pid += 1
        p = FakeProc(self.next_pid)
        self.spawned.append((spec.name, p))
        return p

    def advance(self, seconds):
        self.now += seconds

    def child(self, name="worker"):
        return self.sup._find(name)

    def status(self):
        with open(self.sup.status_file, encoding="utf-8") as f:
            return json.load(f)

    def errors(self):
        return [m for lvl, m in self.logs if lvl == "ERROR"]


# --------------------------------------------------------------- basic restart
def test_dead_child_is_detected_restarted_and_recorded(tmp_path):
    h = Harness(tmp_path)
    h.sup.start_all()
    assert len(h.spawned) == 1
    first = h.spawned[0][1]

    # The failure the old launcher could not see.
    first.die(code=1)
    h.sup.poll_once()

    c = h.child()
    assert c.state == STATE_BACKOFF, "a dead child must be noticed on the next tick"
    assert len(h.spawned) == 1, "restart must wait for the backoff, not happen instantly"

    h.advance(2.0)
    h.sup.poll_once()
    assert len(h.spawned) == 2, "child must actually come back"
    assert h.child().state == STATE_RUNNING
    assert h.child().restarts == 1

    # ...and the fact that it happened must be recorded, not just fixed.
    st = h.status()
    events = [e["event"] for e in st["events"]]
    assert "exited" in events and "restart_scheduled" in events
    exited = [e for e in st["events"] if e["event"] == "exited"][0]
    assert exited["child"] == "worker"
    assert exited["exit_code"] == 1
    assert st["children"]["worker"]["restarts"] == 1


# ------------------------------------------------------------ restart storms
def test_backoff_grows_between_attempts(tmp_path):
    """A child dying instantly must not be respawned in a tight loop."""
    h = Harness(tmp_path)
    h.sup.start_all()

    delays = []
    for _ in range(5):
        h.spawned[-1][1].die(code=1)
        h.sup.poll_once()
        c = h.child()
        assert c.state == STATE_BACKOFF
        delays.append(round(c.next_restart_at - h.now, 3))
        # Poll repeatedly *during* the backoff: nothing may be spawned yet.
        before = len(h.spawned)
        h.advance(delays[-1] - 0.5)
        h.sup.poll_once()
        assert len(h.spawned) == before, "respawned before the backoff expired"
        h.advance(0.5)
        h.sup.poll_once()

    assert delays == [2.0, 4.0, 8.0, 16.0, 32.0], delays


def test_backoff_is_capped(tmp_path):
    h = Harness(tmp_path, backoff_base=2.0, backoff_max=10.0,
                max_consecutive_failures=6)
    h.sup.start_all()
    delays = []
    for _ in range(5):
        h.spawned[-1][1].die()
        h.sup.poll_once()
        delays.append(round(h.child().next_restart_at - h.now, 3))
        h.advance(delays[-1])
        h.sup.poll_once()
    assert delays == [2.0, 4.0, 8.0, 10.0, 10.0], delays


def test_crash_loop_hits_the_cap_and_stays_failed(tmp_path):
    """The requirement: fail loudly and STAY failed - never spin, never pretend."""
    h = Harness(tmp_path)
    h.sup.start_all()

    for _ in range(6):
        if h.child().state == STATE_BACKOFF:
            h.advance(1000.0)
            h.sup.poll_once()
        h.spawned[-1][1].die(code=3)
        h.sup.poll_once()

    c = h.child()
    assert c.state == STATE_FAILED
    spawns_at_failure = len(h.spawned)

    # Stay failed: no amount of further time or polling may resurrect it.
    for _ in range(50):
        h.advance(3600.0)
        h.sup.poll_once()
    assert len(h.spawned) == spawns_at_failure, "a permanently failed child was respawned"
    assert h.child().state == STATE_FAILED

    # Loud.
    errs = "\n".join(h.errors())
    assert "PERMANENTLY FAILED" in errs
    assert "will NOT be restarted" in errs

    # Visible from outside the process.
    st = h.status()
    assert st["failed_children"] == ["worker"]
    assert st["children"]["worker"]["state"] == STATE_FAILED
    assert st["children"]["worker"]["failure_reason"]
    assert any(e["event"] == "permanently_failed" for e in st["events"])


def test_a_spawn_that_raises_is_a_failure_not_an_exception(tmp_path):
    """Bad command / missing interpreter must enter the same bounded policy."""
    h = Harness(tmp_path)
    h.spawn_error = "The system cannot find the file specified"
    h.sup.start_all()

    assert h.child().state == STATE_BACKOFF
    for _ in range(6):
        h.advance(1000.0)
        h.sup.poll_once()
    assert h.child().state == STATE_FAILED
    assert "spawn failed" in (h.child().failure_reason or "")


def test_healthy_uptime_resets_the_restart_budget(tmp_path):
    """Otherwise a system running for months would exhaust its budget and stop
    restarting anything."""
    h = Harness(tmp_path, healthy_uptime=60.0)
    h.sup.start_all()

    for _ in range(20):
        h.advance(3600.0)          # the child ran for an hour: not a crash loop
        h.spawned[-1][1].die(code=0)
        h.sup.poll_once()
        assert h.child().state == STATE_BACKOFF
        assert h.child().consecutive_failures == 1, "a healthy run must reset the counter"
        h.advance(10.0)
        h.sup.poll_once()

    assert h.child().state == STATE_RUNNING
    assert h.child().restarts == 20


def test_short_uptime_does_not_reset_the_budget(tmp_path):
    """The mirror image - the fixture must actually be able to fail."""
    h = Harness(tmp_path, healthy_uptime=60.0)
    h.sup.start_all()
    for i in range(1, 4):
        h.advance(5.0)             # died young
        h.spawned[-1][1].die(code=1)
        h.sup.poll_once()
        assert h.child().consecutive_failures == i
        h.advance(1000.0)
        h.sup.poll_once()


# ------------------------------------------------------------------ shutdown
def test_shutdown_does_not_fight_the_supervisor(tmp_path):
    """stop_all() must set the stopping flag BEFORE terminating, or the monitor
    loop restarts the very children we are trying to kill."""
    h = Harness(tmp_path, specs=[
        ChildSpec("a", ["python", "a.py"], "."),
        ChildSpec("b", ["python", "b.py"], "."),
    ])
    h.sup.start_all()
    assert len(h.spawned) == 2

    h.sup.stop_all(timeout=0.1)
    assert all(p.terminated for _, p in h.spawned)

    # Whatever the loop does afterwards, nothing comes back.
    for _ in range(10):
        h.advance(100.0)
        assert h.sup.poll_once() is False
    assert len(h.spawned) == 2, "supervisor restarted a child during shutdown"
    assert all(c.state == STATE_STOPPED for c in h.sup.children)


def test_stop_all_is_safe_when_a_child_is_already_dead(tmp_path):
    h = Harness(tmp_path)
    h.sup.start_all()
    h.spawned[0][1].die(code=0)
    h.sup.stop_all(timeout=0.1)
    assert h.child().state == STATE_STOPPED


def test_non_restartable_child_exit_requests_shutdown(tmp_path):
    """The desktop window closing means 'stop everything', not 'restart me'."""
    h = Harness(tmp_path, specs=[
        ChildSpec("worker", ["python", "w.py"], ".", heartbeat="w"),
        ChildSpec("Desktop Client UI", ["python", "ui.py"], ".", restartable=False),
    ])
    h.sup.start_all()
    desktop = [p for name, p in h.spawned if name == "Desktop Client UI"][0]
    desktop.die(code=0)

    assert h.sup.poll_once() is False, "launcher should be asked to exit"
    assert len(h.spawned) == 2, "a non-restartable child must not be respawned"
    assert h.sup._find("Desktop Client UI").state == STATE_STOPPED


# ------------------------------------------------- real processes, real orphans
def test_stop_all_leaves_no_orphans_including_grandchildren(tmp_path):
    """Real processes, because this is about OS behaviour a fake cannot model.

    terminate() on Windows is TerminateProcess and does not walk the tree, so a
    child that exits cleanly used to leave its own subprocesses running. That is
    exactly the shape of run_auto_update.py running a collector script when the
    launcher is stopped.
    """
    psutil = pytest.importorskip("psutil")
    import sys as _sys

    work = str(tmp_path)
    child_src = os.path.join(work, "child.py")
    with open(child_src, "w", encoding="utf-8") as f:
        f.write(
            "import subprocess, sys, time, os\n"
            "g = subprocess.Popen([sys.executable, '-c',\n"
            "    'import time\\nwhile True: time.sleep(1)'])\n"
            "open(os.path.join(os.path.dirname(os.path.abspath(__file__)),\n"
            "     'gc.pid'), 'w').write(str(g.pid))\n"
            "while True: time.sleep(1)\n")

    sup = Supervisor([ChildSpec("w", [_sys.executable, child_src], work)],
                     status_file=os.path.join(work, "status.json"))
    sup.start_all()
    child_pid = sup.children[0].proc.pid

    gc_file = os.path.join(work, "gc.pid")
    deadline = time.time() + 20
    while not os.path.exists(gc_file) and time.time() < deadline:
        time.sleep(0.1)
    assert os.path.exists(gc_file), "fixture broken: no grandchild was spawned"
    gc_pid = int(open(gc_file).read())
    assert psutil.pid_exists(gc_pid), "fixture broken: grandchild not running"

    try:
        sup.stop_all(timeout=3.0)
        deadline = time.time() + 10
        while (psutil.pid_exists(child_pid) or psutil.pid_exists(gc_pid)) \
                and time.time() < deadline:
            time.sleep(0.2)
        assert not psutil.pid_exists(child_pid), "supervised child survived stop_all"
        assert not psutil.pid_exists(gc_pid), \
            "grandchild orphaned by stop_all - the launcher leaks processes"
    finally:
        for pid in (child_pid, gc_pid):
            try:
                psutil.Process(pid).kill()
            except Exception:
                pass


# -------------------------------------------------------------- status file
def test_status_file_event_ring_is_bounded(tmp_path):
    h = Harness(tmp_path, max_consecutive_failures=10 ** 6, healthy_uptime=0.0)
    h.sup.start_all()
    for _ in range(MAX_EVENTS + 40):
        h.spawned[-1][1].die(code=1)
        h.sup.poll_once()
        h.advance(1000.0)
        h.sup.poll_once()
    st = h.status()
    assert len(st["events"]) <= MAX_EVENTS
    assert len(h.sup.events) <= MAX_EVENTS


def test_status_file_names_the_heartbeat_each_child_publishes(tmp_path):
    """/health joins the two by this field; if it is dropped, health silently
    stops checking that worker."""
    h = Harness(tmp_path, specs=[
        ChildSpec("File Ingestion Watcher", ["python", "w.py"], ".", heartbeat="watcher"),
        ChildSpec("Backend FastAPI Server", ["python", "s.py"], "."),
    ])
    h.sup.start_all()
    st = h.status()
    assert st["children"]["File Ingestion Watcher"]["heartbeat"] == "watcher"
    assert st["children"]["Backend FastAPI Server"]["heartbeat"] is None


def test_launcher_declares_a_heartbeat_for_every_worker():
    """Guards the wiring in run_decoupled_app.py: a worker added later without a
    heartbeat would be supervised but invisible to /health."""
    import re
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    src = open(os.path.join(root, "run_decoupled_app.py"), encoding="utf-8").read()
    # Scoped to the spec list. The whole file is not searchable for a runner
    # name: a comment mentioning `run_graph_sync.py` above main() matched first
    # and made this guard fail on a launcher whose specs were perfectly correct.
    src = src[src.index("    specs = ["):]
    # `run_graph_sync.py`/"graph" was here until R-2026-08-14-H retired the old
    # graph branch and removed that child from the launcher entirely.
    for runner, hb in [("run_watcher.py", "watcher"),
                       ("run_chain_worker.py", "chain"), ("run_auto_update.py", "scheduler")]:
        m = re.search(re.escape(runner) + r"[^\n]*\n?[^\n]*", src)
        assert m, f"{runner} is no longer spawned by the launcher"
        assert f'heartbeat="{hb}"' in m.group(0), \
            f"{runner} is supervised but publishes no heartbeat to /health"


# ===========================================================================
# Shared-cause (correlated) failure.
#
# The hole this closes: a database outage takes all five children down at once,
# each burns its own 2/4/8/16/32 s budget, and ~80 s later EVERY child is
# permanently failed - so the system needs a human even after the database comes
# back. Permanent failure is a judgement about ONE child; these tests make
# several children fail together and require the supervisor to keep trying.
#
# Nothing here touches a real process, a real database or a real second: the
# policy is driven through the injected clock and spawner, so a guard that fails
# cannot damage anything.
# ===========================================================================

def _two_children(tmp_path, **kw):
    # Environment reported healthy unless a test says otherwise, so the peer rule
    # is what these tests actually exercise.
    kw.setdefault("environment_probe", lambda: (False, None))
    return Harness(tmp_path, specs=[
        ChildSpec("alpha", ["python", "a.py"], ".", heartbeat="a"),
        ChildSpec("beta", ["python", "b.py"], ".", heartbeat="b"),
    ], **kw)


def _spawn_count(h, name):
    return len([n for n, _ in h.spawned if n == name])


def _kill(h, *names):
    """Kill the named live children (all of them if none named)."""
    for c in h.sup.children:
        if names and c.spec.name not in names:
            continue
        if c.proc is not None and c.proc.poll() is None:
            c.proc.die(code=1)


def _outage_cycle(h, dying=(), settle=61.0):
    """One round of "everything that touches the database dies immediately".

    The kill lands with zero uptime, so HEALTHY_UPTIME_SEC never resets the
    budget - this is a crash loop, not a series of unrelated deaths.
    """
    _kill_and_observe(h, *dying)
    h.advance(settle)          # past the longest backoff, correlated included
    h.sup.poll_once()          # respawn


def _kill_and_observe(h, *names):
    """Kill and register the failure, but do not advance past the restart timer.

    Needed because a child that has just been respawned is RUNNING again - the
    waiting state is only observable between the death and the next restart.
    """
    _kill(h, *names)
    h.sup.poll_once()


def test_children_failing_together_keep_being_retried_past_the_cap(tmp_path):
    """The database-outage case: nobody is permanently failed, everybody retries.

    This is the regression that matters. Before the correlation rule both
    children reached STATE_FAILED and stopped being spawned at all.
    """
    h = _two_children(tmp_path)
    h.sup.start_all()

    for _ in range(12):        # twice the old 6-failure budget
        _outage_cycle(h)
    _kill_and_observe(h)       # observe the verdict, not the respawn after it

    for name in ("alpha", "beta"):
        c = h.child(name)
        assert c.state == STATE_RETRYING_CORRELATED, \
            f"{name} is {c.state}, not being retried as a shared-cause failure"
        assert c.consecutive_failures > h.sup.max_consecutive_failures, \
            "fixture broken: the budget was never actually exhausted"
        # The load-bearing number: spawns keep happening past the old cap.
        assert _spawn_count(h, name) > h.sup.max_consecutive_failures + 1, \
            f"{name} stopped being respawned - the old cap is still in force"

    st = h.status()
    assert st["failed_children"] == []
    assert sorted(st["correlated_children"]) == ["alpha", "beta"]
    assert h.child("alpha").correlated_with == ["beta"]


def test_a_correlated_outage_recovers_with_no_manual_restart(tmp_path):
    """When the cause clears, the children come back by themselves."""
    h = _two_children(tmp_path)
    h.sup.start_all()
    for _ in range(10):
        _outage_cycle(h)
    _kill_and_observe(h)
    assert all(c.state == STATE_RETRYING_CORRELATED for c in h.sup.children)

    # The database comes back: nothing dies any more, and nobody intervenes.
    h.advance(61.0)
    h.sup.poll_once()
    assert all(c.state == STATE_RUNNING for c in h.sup.children), \
        "children did not recover on their own after the shared cause cleared"

    st = h.status()
    assert st["correlated_children"] == []
    assert st["failed_children"] == []


def test_a_child_that_fails_alone_is_still_permanently_failed(tmp_path):
    """The control. Without it, "never give up" would be indistinguishable from
    "the correlation rule disabled permanent failure entirely"."""
    h = _two_children(tmp_path)
    h.sup.start_all()

    for _ in range(12):
        _outage_cycle(h, dying=("alpha",))   # beta stays up the whole time

    assert h.child("beta").state == STATE_RUNNING
    assert h.child("alpha").state == STATE_FAILED, \
        "a child failing on its own must still hit the cap and stay failed"
    assert h.status()["failed_children"] == ["alpha"]
    assert h.status()["correlated_children"] == []
    # And it really stops: no further spawns.
    before = _spawn_count(h, "alpha")
    for _ in range(5):
        h.advance(120.0)
        h.sup.poll_once()
    assert _spawn_count(h, "alpha") == before


def test_correlated_is_not_a_permanent_escape_from_the_budget(tmp_path):
    """A child left failing alone after its peers recover falls back to failed.

    Otherwise one coincidental outage would buy a broken child an infinite retry
    loop for the rest of the launcher's life.
    """
    h = _two_children(tmp_path)
    h.sup.start_all()
    for _ in range(8):
        _outage_cycle(h)
    _kill_and_observe(h)
    assert h.child("alpha").state == STATE_RETRYING_CORRELATED

    # beta recovers and stays up, so its last failure ages out of the window.
    for _ in range(4):
        _outage_cycle(h, dying=("alpha",))

    assert h.child("beta").state == STATE_RUNNING
    assert h.child("alpha").state == STATE_FAILED, \
        "alpha kept retrying forever although it was the only thing failing"


def test_the_correlation_window_has_an_edge(tmp_path):
    """A peer failure older than the window is not evidence of a shared cause."""
    h = _two_children(tmp_path, correlation_window=120.0)
    h.sup.start_all()

    # beta dies once, long ago, and is left waiting in backoff.
    _kill(h, "beta")
    h.sup.poll_once()
    h.advance(121.0)

    # alpha now burns its whole budget alone.
    for _ in range(8):
        _kill(h, "alpha")
        h.sup.poll_once()
        h.advance(61.0)
        h.sup.poll_once()

    assert h.child("alpha").state == STATE_FAILED, \
        "a 121s-old peer failure was counted as correlated inside a 120s window"


def test_correlated_backoff_is_flat_not_exponential(tmp_path):
    """Retrying forever with a doubling delay would reach hours between
    attempts, which is "gave up" with extra steps."""
    h = _two_children(tmp_path)
    h.sup.start_all()
    for _ in range(10):
        _outage_cycle(h)

    _kill_and_observe(h)
    for c in h.sup.children:
        assert c.state == STATE_RETRYING_CORRELATED
        delay = c.next_restart_at - h.now
        assert abs(delay - h.sup.correlated_backoff) < 0.001, \
            f"correlated retry delay drifted to {delay}s"


def test_a_shared_cause_outage_is_loud(tmp_path):
    """It must not retry quietly. "Unhealthy but working on it" is still an
    incident, and the log is where an operator finds out which one."""
    h = _two_children(tmp_path)
    h.sup.start_all()
    for _ in range(8):
        _outage_cycle(h)

    errs = "\n".join(h.errors())
    assert "SHARED-CAUSE FAILURE" in errs
    assert "NOT giving up" in errs
    assert "alpha" in errs and "beta" in errs
    events = [e for e in h.status()["events"] if e["event"] == "correlated_failure"]
    assert events, "the correlated decision left no durable record"
    assert events[-1]["peers"]


# ------------------------------------- the second kind of evidence: the env
#
# Measured live: on a cold start with PostgreSQL unreachable, exactly ONE child
# dies (the web server - its import runs create_all); the four workers catch the
# error in their loops and stay up. So the most likely real outage produces a
# LONE failing child, which the peer rule alone permanently fails 94 s in.

def test_a_lone_child_is_spared_while_its_database_is_down(tmp_path):
    """The web server after a reboot where PostgreSQL is slow to come up."""
    h = Harness(tmp_path, specs=[
        ChildSpec("web", ["python", "s.py"], "."),
        ChildSpec("worker", ["python", "w.py"], ".", heartbeat="w"),
    ], environment_probe=lambda: (True, "the database at db:5432 is not "
                                        "accepting connections (TimeoutError)"))
    h.sup.start_all()

    for _ in range(12):
        _outage_cycle(h, dying=("web",))
    _kill_and_observe(h, "web")

    c = h.child("web")
    assert c.state == STATE_RETRYING_CORRELATED, \
        "the web server was permanently failed while its database was down"
    assert c.correlated_with == [], "there were no peer failures - this is env evidence"
    assert "database" in (c.correlated_evidence or "")
    assert h.status()["failed_children"] == []
    assert _spawn_count(h, "web") > h.sup.max_consecutive_failures + 1


def test_the_same_child_with_a_healthy_database_is_failed(tmp_path):
    """The control that makes the test above attributable. Identical fixture,
    one difference: the environment probe says the database is fine."""
    h = Harness(tmp_path, specs=[
        ChildSpec("web", ["python", "s.py"], "."),
        ChildSpec("worker", ["python", "w.py"], ".", heartbeat="w"),
    ], environment_probe=lambda: (False, None))
    h.sup.start_all()

    for _ in range(12):
        _outage_cycle(h, dying=("web",))
    _kill_and_observe(h, "web")

    assert h.child("web").state == STATE_FAILED, \
        "a broken child with a healthy database must still be given up on"


def test_a_probe_that_raises_decides_nothing(tmp_path):
    """Monitoring must never become a new failure mode: a broken probe must not
    be able to keep a broken child alive forever, nor crash the supervisor."""
    def boom():
        raise OSError("probe exploded")

    h = Harness(tmp_path, specs=[ChildSpec("web", ["python", "s.py"], ".")],
                environment_probe=boom)
    h.sup.start_all()
    for _ in range(12):
        _outage_cycle(h, dying=("web",))
    _kill_and_observe(h, "web")
    assert h.child("web").state == STATE_FAILED


def test_the_environment_probe_is_only_consulted_at_the_giving_up_point(tmp_path):
    """It opens a socket, so it must not run on every ordinary restart."""
    calls = []
    h = Harness(tmp_path, specs=[ChildSpec("web", ["python", "s.py"], ".")],
                environment_probe=lambda: (calls.append(1), (False, None))[1])
    h.sup.start_all()
    for _ in range(3):        # well inside the budget
        _outage_cycle(h, dying=("web",))
    assert calls == [], "the probe ran during ordinary backoff restarts"

    for _ in range(5):
        _outage_cycle(h, dying=("web",))
    assert calls, "the probe never ran, even at the permanent-failure decision"


def test_unknown_environments_count_as_healthy():
    """No DATABASE_URL, sqlite, or an unparseable URL must not be read as an
    outage - that would make every lone failure un-failable."""
    import process_supervisor as ps
    for url in ("", "sqlite:///:memory:", "not a url at all", "postgresql:///nohost"):
        down, detail = ps.shared_dependency_down(url=url)
        assert down is False, f"{url!r} was read as a database outage"
        assert detail is None


def test_an_unreachable_database_is_detected_for_real():
    """A closed port, actually opened against, not a mocked return value."""
    import socket
    import process_supervisor as ps

    # A port nothing is listening on: bind it, read the number, close it.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    down, detail = ps.shared_dependency_down(
        url=f"postgresql://u:p@127.0.0.1:{port}/db", timeout=2.0)
    assert down is True, "a closed database port was reported reachable"
    assert str(port) in detail

    # Control: a port that IS listening reads as healthy, so the test above is
    # about reachability and not about the probe always saying "down".
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        ok_port = srv.getsockname()[1]
        down, detail = ps.shared_dependency_down(
            url=f"postgresql://u:p@127.0.0.1:{ok_port}/db", timeout=2.0)
        assert down is False and detail is None
    finally:
        srv.close()


# ---------------------------------------------------------------- psutil
def test_psutil_absence_is_announced_not_silent():
    """Grandchild cleanup degrades to a no-op without psutil. Silent degradation
    of a cleanup path is how orphans accumulate unnoticed."""
    import sys as _sys
    import process_supervisor as ps

    ok, detail = ps.psutil_status()
    assert ok, "psutil is a declared dependency and must be importable"
    assert "armed" in detail

    # Make `import psutil` raise, exactly as it would on a machine without it.
    # Restored in the finally block, so no other test can observe this.
    sentinel = object()
    saved = _sys.modules.get("psutil", sentinel)
    _sys.modules["psutil"] = None
    try:
        ok, detail = ps.psutil_status()
        assert ok is False
        assert "grandchild cleanup is DISABLED" in detail
        assert "orphans" in detail
        assert "conda install" in detail, "the message must say how to fix it"

        # And the degraded path complains through the launcher log, once.
        said = []
        ps._psutil_missing_warned = False
        assert ps._descendant_pids(
            os.getpid(), log=lambda m, level="INFO": said.append((level, m))) == []
        assert said and said[0][0] == "WARNING"
        assert "grandchild cleanup is DISABLED" in said[0][1]

        said2 = []
        ps._kill_pids([1234], log=lambda m, level="INFO": said2.append(m))
        assert said2 == [], "the warning must not repeat on every call"
    finally:
        ps._psutil_missing_warned = False
        if saved is sentinel:
            _sys.modules.pop("psutil", None)
        else:
            _sys.modules["psutil"] = saved
