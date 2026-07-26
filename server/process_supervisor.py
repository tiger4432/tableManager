"""Child-process supervision for the decoupled launcher.

THE HOLE THIS FILLS
-------------------
``run_decoupled_app.py`` used to spawn five processes and then run
``while True: time.sleep(1)``. If the directory watcher or the chain worker died,
nothing detected it and nothing restarted it. The web server stayed up, so the UI
looked perfectly healthy while data quietly stopped flowing. That is not
near-continuous operation; it is undetected downtime.

RESTART POLICY, AND WHY IT REFUSES TO RETRY FOREVER
---------------------------------------------------
A child that dies immediately on every start — bad config, port already taken, a
missing table — must not be respawned in a tight loop. Respawning it forever burns
CPU, floods the log, and (worst of all) *looks like supervision is working*. A
supervisor that hides a permanently broken child is worse than no supervisor.

So each child gets a bounded budget:

    consecutive failure n  ->  wait min(BACKOFF_BASE * 2**(n-1), BACKOFF_MAX)
    n > MAX_CONSECUTIVE_FAILURES  ->  state FAILED, never respawned again,
                                      logged as a banner, and surfaced by /health
                                      as a non-200 for as long as it stays failed.

``HEALTHY_UPTIME_SEC`` is what keeps that budget from leaking away over weeks: a
child that ran fine for a while before dying is not in a crash loop, so its
consecutive counter resets to zero and it gets a full budget again. Without this,
a system restarted once a month would eventually refuse to restart anything.

Restarting a mid-ingestion watcher is safe, and this design depends on that being
true: P2's checkpoint resume was drilled under a real ``taskkill /F`` at 30,000 of
100,000 rows — the committed offset matched the actual row count exactly and the
resume skipped the completed rows in 275 ms with zero loss and zero duplication
(``agent_workspace/reports/QA_p2_drills_isolated.md`` §2). Auto-restart is only
acceptable because of that.

OBSERVABILITY
-------------
Every state change is written to ``<DATA_ROOT>/config/supervisor_status.json``,
which is what lets ``/health`` report *from outside* which child died, when, why,
and how many times. ``updated_at`` doubles as the supervisor's own liveness
signal — if the supervisor itself dies, its children keep beating but this
timestamp stops, and /health says so.
"""
import os
import json
import time
import subprocess

try:
    import paths
except ImportError:  # imported without server/ on sys.path
    from . import paths  # type: ignore

STATUS_FILENAME = "supervisor_status.json"

BACKOFF_BASE_SEC = 2.0
BACKOFF_MAX_SEC = 60.0
MAX_CONSECUTIVE_FAILURES = 5
# A child that stayed up this long was not in a crash loop.
HEALTHY_UPTIME_SEC = 60.0
POLL_INTERVAL_SEC = 1.0
# Refresh the status file at least this often so `updated_at` is a liveness signal.
STATUS_REFRESH_SEC = 5.0
# Bounded ring: a supervisor running for months must not grow an unbounded log.
MAX_EVENTS = 100

STATE_RUNNING = "running"
STATE_BACKOFF = "backoff"
STATE_FAILED = "failed"
STATE_STOPPED = "stopped"


def status_path():
    return paths.config_path(STATUS_FILENAME)


def _descendant_pids(pid):
    """Pids of everything below ``pid``, captured while it is still alive.

    Must be called BEFORE terminating the parent: once it exits, the link from a
    grandchild back to it is gone and the grandchild can no longer be found.

    psutil is not a declared project dependency, so its absence degrades to "no
    descendant cleanup" rather than an import error at shutdown.
    """
    try:
        import psutil
    except ImportError:
        return []
    try:
        return [c.pid for c in psutil.Process(pid).children(recursive=True)]
    except Exception:
        return []


def _kill_pids(pids):
    """Kill any of ``pids`` still running. Returns how many were killed."""
    if not pids:
        return 0
    try:
        import psutil
    except ImportError:
        return 0
    killed = 0
    for pid in pids:
        try:
            p = psutil.Process(pid)
            p.kill()
            killed += 1
        except Exception:
            pass
    return killed


class ChildSpec:
    """How to start one child, and what to do when it dies.

    ``restartable=False`` marks a child whose exit means the whole system should
    stop (the desktop client window closing), not one to be brought back.
    """

    def __init__(self, name, cmd, cwd, env=None, restartable=True,
                 heartbeat=None, start_delay=0.0):
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self.restartable = restartable
        # Name of the heartbeat this child publishes, so /health can join the
        # supervisor's view of the process to the worker's view of its own
        # progress. None for children that publish none.
        self.heartbeat = heartbeat
        self.start_delay = start_delay


class _ChildState:
    def __init__(self, spec):
        self.spec = spec
        self.proc = None
        self.state = STATE_STOPPED
        self.started_at = None
        self.restarts = 0
        self.consecutive_failures = 0
        self.last_exit_code = None
        self.last_exit_at = None
        self.next_restart_at = None
        self.failure_reason = None


class Supervisor:
    """Watches a fixed set of children, restarts them, and records that it did.

    ``spawn``, ``clock`` and ``sleep`` are injectable so the restart policy can be
    tested deterministically without spawning real processes or waiting real
    seconds. Production passes none of them.
    """

    def __init__(self, specs=(), status_file=None, log=None, spawn=None,
                 clock=None, sleep=None,
                 poll_interval=POLL_INTERVAL_SEC,
                 backoff_base=BACKOFF_BASE_SEC,
                 backoff_max=BACKOFF_MAX_SEC,
                 max_consecutive_failures=MAX_CONSECUTIVE_FAILURES,
                 healthy_uptime=HEALTHY_UPTIME_SEC):
        self.children = [_ChildState(s) for s in specs]
        self.status_file = status_file or status_path()
        self._log = log or (lambda msg, level="INFO": None)
        self._spawn = spawn or self._default_spawn
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self.poll_interval = poll_interval
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.max_consecutive_failures = max_consecutive_failures
        self.healthy_uptime = healthy_uptime

        self._stopping = False
        self._exit_requested = False
        self.events = []
        self._last_status_write = 0.0
        self._started_wall = time.time()

    # ------------------------------------------------------------- internals
    def _default_spawn(self, spec):
        merged = os.environ.copy()
        if spec.env:
            merged.update(spec.env)
        return subprocess.Popen(spec.cmd, cwd=spec.cwd, env=merged)

    def _find(self, name):
        for c in self.children:
            if c.spec.name == name:
                return c
        return None

    def _record(self, child, event, **fields):
        entry = {"ts": time.time(), "child": child.spec.name, "event": event}
        entry.update(fields)
        self.events.append(entry)
        if len(self.events) > MAX_EVENTS:
            del self.events[: len(self.events) - MAX_EVENTS]

    def _backoff_for(self, n):
        return min(self.backoff_base * (2 ** (n - 1)), self.backoff_max)

    # ---------------------------------------------------------------- start
    def start_all(self):
        for child in self.children:
            if child.spec.start_delay:
                self._sleep(child.spec.start_delay)
            self._start(child)
        self.write_status(force=True)

    def _start(self, child):
        name = child.spec.name
        try:
            child.proc = self._spawn(child.spec)
            child.state = STATE_RUNNING
            child.started_at = self._clock()
            child.next_restart_at = None
            self._log(f"Starting {name}: {' '.join(child.spec.cmd)}")
            self._record(child, "started", pid=getattr(child.proc, "pid", None))
        except Exception as e:
            # A spawn that raises is a failure exactly like a child that exits
            # immediately - otherwise a bad command line would spin here forever.
            child.proc = None
            self._log(f"Failed to spawn {name}: {e}", level="ERROR")
            self._register_failure(child, exit_code=None, reason=f"spawn failed: {e}")
        return child.proc

    # --------------------------------------------------------------- policy
    def _register_failure(self, child, exit_code, reason=None):
        """A child is gone and we are not shutting down. Decide what happens next."""
        now = self._clock()
        uptime = (now - child.started_at) if child.started_at is not None else 0.0
        child.last_exit_code = exit_code
        child.last_exit_at = time.time()
        child.proc = None

        if uptime >= self.healthy_uptime:
            # It ran fine and then died. Not a crash loop - full budget again.
            child.consecutive_failures = 1
        else:
            child.consecutive_failures += 1

        self._record(child, "exited", exit_code=exit_code,
                     uptime_seconds=round(uptime, 2),
                     consecutive_failures=child.consecutive_failures,
                     reason=reason)

        if child.consecutive_failures > self.max_consecutive_failures:
            child.state = STATE_FAILED
            child.next_restart_at = None
            child.failure_reason = (
                reason or
                f"exited {child.consecutive_failures} times in a row "
                f"(last exit code {exit_code}) without staying up "
                f"{self.healthy_uptime:.0f}s"
            )
            # Loud, and it stays failed. No further restart attempts.
            self._log("=" * 68, level="ERROR")
            self._log(f"CHILD PERMANENTLY FAILED: {child.spec.name}", level="ERROR")
            self._log(f"  {child.failure_reason}", level="ERROR")
            self._log("  Giving up - this child will NOT be restarted again.", level="ERROR")
            self._log("  /health now reports unhealthy until it is fixed and the "
                      "launcher restarted.", level="ERROR")
            self._log("=" * 68, level="ERROR")
            self._record(child, "permanently_failed",
                         consecutive_failures=child.consecutive_failures,
                         reason=child.failure_reason)
        else:
            delay = self._backoff_for(child.consecutive_failures)
            child.state = STATE_BACKOFF
            child.next_restart_at = now + delay
            child.restarts += 1
            self._log(
                f"{child.spec.name} died (exit code {exit_code}, up "
                f"{uptime:.1f}s). Restart {child.consecutive_failures}/"
                f"{self.max_consecutive_failures} in {delay:.0f}s.",
                level="WARNING")
            self._record(child, "restart_scheduled", delay_seconds=delay,
                         attempt=child.consecutive_failures)
        self.write_status(force=True)

    # ----------------------------------------------------------------- poll
    def poll_once(self):
        """One supervision tick. Returns True while the launcher should keep going."""
        if self._stopping:
            return False
        changed = False
        now = self._clock()

        for child in self.children:
            if child.state == STATE_RUNNING and child.proc is not None:
                code = child.proc.poll()
                if code is None:
                    continue
                changed = True
                if not child.spec.restartable:
                    # The desktop client closed: that means "stop everything",
                    # not "bring it back".
                    self._log(f"{child.spec.name} exited (code {code}).")
                    child.state = STATE_STOPPED
                    child.proc = None
                    self._record(child, "exited_no_restart", exit_code=code)
                    self._exit_requested = True
                else:
                    self._register_failure(child, exit_code=code)

            elif child.state == STATE_BACKOFF:
                if child.next_restart_at is not None and now >= child.next_restart_at:
                    changed = True
                    self._log(f"Restarting {child.spec.name} "
                              f"(attempt {child.consecutive_failures}/"
                              f"{self.max_consecutive_failures})...")
                    self._start(child)

        self.write_status(force=changed)
        return not self._exit_requested

    def run(self):
        """Blocking monitor loop. Replaces `while True: time.sleep(1)`."""
        while not self._stopping:
            if not self.poll_once():
                break
            self._sleep(self.poll_interval)
        return self._exit_requested

    # ------------------------------------------------------------- shutdown
    def stop_all(self, timeout=3.0):
        """Terminate every running child. Sets the stopping flag FIRST.

        Order matters: if the flag were set after the first terminate, the monitor
        loop could observe that child as "died" and helpfully restart it while we
        are trying to shut down. That race is how a supervisor turns Ctrl+C into a
        process that will not die.
        """
        self._stopping = True
        for child in reversed(self.children):
            proc = child.proc
            if proc is None or proc.poll() is not None:
                child.state = STATE_STOPPED
                child.proc = None
                continue
            self._log(f"Stopping {child.spec.name}...")
            # Capture the subtree first. terminate() on Windows is
            # TerminateProcess, which does not walk the tree, so a child that
            # exits cleanly still leaves its own subprocesses behind. Measured:
            # stopping two children left both of their grandchildren running.
            # In production that is run_auto_update.py's collector scripts.
            descendants = _descendant_pids(proc.pid)
            try:
                proc.terminate()
                proc.wait(timeout=timeout)
                self._log(f"{child.spec.name} stopped successfully.")
            except Exception as e:
                self._log(f"Error stopping {child.spec.name}: {e}. Killing process...",
                          level="ERROR")
                try:
                    proc.kill()
                except Exception:
                    pass
            orphaned = _kill_pids(descendants)
            if orphaned:
                self._log(f"Stopped {orphaned} leftover subprocess(es) of "
                          f"{child.spec.name}.")
                self._record(child, "orphans_killed", count=orphaned)
            child.state = STATE_STOPPED
            child.proc = None
            self._record(child, "stopped")
        self.write_status(force=True)

    # --------------------------------------------------------------- status
    def snapshot(self):
        children = {}
        now = self._clock()
        for c in self.children:
            children[c.spec.name] = {
                "state": c.state,
                "pid": getattr(c.proc, "pid", None) if c.proc is not None else None,
                "heartbeat": c.spec.heartbeat,
                "restartable": c.spec.restartable,
                "restarts": c.restarts,
                "consecutive_failures": c.consecutive_failures,
                "uptime_seconds": (round(now - c.started_at, 1)
                                   if c.state == STATE_RUNNING and c.started_at is not None
                                   else None),
                "last_exit_code": c.last_exit_code,
                "last_exit_at": c.last_exit_at,
                "seconds_until_restart": (round(c.next_restart_at - now, 1)
                                          if c.next_restart_at is not None else None),
                "failure_reason": c.failure_reason,
            }
        return {
            "supervisor_pid": os.getpid(),
            "started_at": self._started_wall,
            "updated_at": time.time(),
            "stopping": self._stopping,
            "failed_children": [c.spec.name for c in self.children
                                if c.state == STATE_FAILED],
            "children": children,
            "events": self.events[-MAX_EVENTS:],
        }

    def write_status(self, force=False):
        now = self._clock()
        if not force and (now - self._last_status_write) < STATUS_REFRESH_SEC:
            return False
        self._last_status_write = now
        try:
            path = self.status_file
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.snapshot(), f, indent=2)
            os.replace(tmp, path)  # atomic: /health never reads a partial file
            return True
        except Exception as e:
            self._log(f"Failed to write supervisor status: {e}", level="ERROR")
            return False


def read_status(path=None):
    """Read the supervisor status file. Returns None when there is no supervisor."""
    path = path or status_path()
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
