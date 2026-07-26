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
    for runner, hb in [("run_watcher.py", "watcher"), ("run_graph_sync.py", "graph"),
                       ("run_chain_worker.py", "chain"), ("run_auto_update.py", "scheduler")]:
        m = re.search(re.escape(runner) + r"[^\n]*\n?[^\n]*", src)
        assert m, f"{runner} is no longer spawned by the launcher"
        assert f'heartbeat="{hb}"' in m.group(0), \
            f"{runner} is supervised but publishes no heartbeat to /health"
