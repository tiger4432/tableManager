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

WHY GIVING UP IS A JUDGEMENT ABOUT **ONE** CHILD
------------------------------------------------
The budget above is the right answer to "this child is broken" and the wrong
answer to "the environment is broken". If the whole stack goes down for a shared
reason, each child burns its own 2/4/8/16/32 s budget and roughly 90 s later
*every* child is permanently failed, so the system needs a human even after the
cause clears. Against a near-continuous-operation requirement that is worse than
the unsupervised launcher it replaced.

So permanent failure is reserved for a child that fails **alone**, and a child
has company in either of two ways:

1. **Peers.** Another child also failed inside ``CORRELATION_WINDOW_SEC``.
2. **A shared dependency is verifiably down.** Measured, not assumed: on a cold
   start with PostgreSQL unreachable exactly ONE child dies - the web server,
   because its import runs ``create_all``; the four workers catch the error in
   their loops and stay up. The most likely real outage therefore produces a lone
   failing child, and a peer-only rule would permanently fail the web server 94 s
   in and leave it down after the database came back. So at the moment of giving
   up, and only then, the database port is probed directly
   (``shared_dependency_down``). A closed port says the same thing a peer failure
   says: the fault is not in this child.

Either way the child enters ``retrying_correlated``: a long fixed backoff, retried
**indefinitely**, never permanently failed, and reported ``unhealthy`` by /health
the entire time. When the cause clears the children come back on their own.

The rule is deliberately biased toward "correlated". Two children inside two
minutes is weak evidence of a common cause and will sometimes catch two genuinely
independent deaths that landed close together; a database that is down for an
unrelated reason will excuse a child that really is broken. Those false positives
cost an indefinite retry loop on a broken child - loud, visible, recoverable, and
still reported unhealthy. The opposite error costs a manual restart of a healthy
system during an outage, discovered whenever someone next looks. We take the
first.

Unknown always counts as healthy: no DATABASE_URL, sqlite, an unparseable URL or
a probe that raises all mean "no evidence", so this can only ever ADD evidence -
it can never take away the ability to fail a genuinely broken child.

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

# --- Shared-cause (correlated) failure ------------------------------------
# Peer correlation is defined by time, not by exit code: on Windows every
# unhandled Python exception exits 1, so an exit-code signature would call almost
# any pair of failures correlated and would prove nothing. Two distinct children
# failing inside the window is the rule.
#
# The window has to outlast one full budget cycle, because that is when the
# decision is made. A child exhausts 2+4+8+16+32 s of backoff about 80 s after
# its first death, so at the moment it asks "did anyone else fail recently?" its
# peers' most recent failures are 20-40 s old. 120 s covers that with room for
# children that die at different rates during the same outage.
CORRELATION_WINDOW_SEC = 120.0
# How many distinct children must have failed in the window, counting this one.
# 2 of 5 is the loosest threshold above "alone" - chosen deliberately, because
# erring toward "correlated" keeps the system retrying.
CORRELATED_MIN_CHILDREN = 2
# Long enough not to hammer a database that is already in trouble, short enough
# that recovery is automatic within a minute of the cause clearing.
CORRELATED_BACKOFF_SEC = 60.0

STATE_RUNNING = "running"
STATE_BACKOFF = "backoff"
STATE_FAILED = "failed"
STATE_STOPPED = "stopped"
# Budget exhausted, but not alone: retried forever, never permanently failed.
STATE_RETRYING_CORRELATED = "retrying_correlated"

# States from which a child is still waiting to be restarted.
_WAITING_STATES = (STATE_BACKOFF, STATE_RETRYING_CORRELATED)


def status_path():
    return paths.config_path(STATUS_FILENAME)


def _database_endpoint(url=None):
    """(host, port) from DATABASE_URL, or None when there is nothing to probe.

    Parsed with urllib rather than sqlalchemy on purpose: this runs in the
    launcher, and one of the shared causes it has to survive is *sqlalchemy
    itself being unimportable* after a bad deploy.
    """
    url = url if url is not None else os.environ.get("DATABASE_URL", "")
    if not url or url.startswith("sqlite"):
        return None
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        if not parts.hostname:
            return None
        return parts.hostname, int(parts.port or 5432)
    except Exception:
        return None


def shared_dependency_down(url=None, timeout=2.0):
    """``(down, detail)`` - direct evidence that the ENVIRONMENT is broken.

    Why this exists alongside the peer-failure rule: measured on a cold start
    with PostgreSQL unreachable, exactly ONE child dies - the web server, whose
    import runs ``Base.metadata.create_all``. The four workers catch the error in
    their own loops and stay up. So the most likely real version of "the database
    was slow to come up after a reboot" produces a lone failing child, and a rule
    that only counts peer failures would permanently fail the web server 94 s in
    and keep it down after the database returned.

    A closed TCP port on the database is the same class of evidence as a peer
    failure - it says the fault is not in this child - so it is treated the same
    way. Only reachability is checked: authentication or a missing schema is a
    configuration fault that a retry loop will not fix.

    Unknown counts as healthy (no DATABASE_URL, sqlite, an unparseable URL), so
    this can only ever ADD evidence, never remove the ability to fail a child.
    """
    ep = _database_endpoint(url)
    if ep is None:
        return False, None
    host, port = ep
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return False, None
    except Exception as e:
        return True, (f"the database at {host}:{port} is not accepting "
                      f"connections ({type(e).__name__})")


def psutil_status():
    """``(available, detail)`` - whether grandchild cleanup is armed.

    Called once at launcher startup. Silent degradation of a cleanup path is how
    orphaned collector subprocesses accumulate for weeks without anyone noticing,
    so the answer is announced at boot rather than discovered at shutdown.
    """
    try:
        import psutil
    except ImportError as e:
        return False, (
            f"psutil is not importable ({e}) - grandchild cleanup is DISABLED: "
            "stopping the launcher will terminate its five children but not the "
            "subprocesses they spawned (auto-update collector scripts), leaving "
            "orphans behind. Install it: conda install -n assy_manager psutil")
    return True, f"psutil {getattr(psutil, '__version__', '?')} - grandchild cleanup armed"


_psutil_missing_warned = False


def _psutil_or_warn(log=None):
    """Import psutil, complaining exactly once per process if it is absent."""
    global _psutil_missing_warned
    try:
        import psutil
        return psutil
    except ImportError:
        if not _psutil_missing_warned:
            _psutil_missing_warned = True
            _, detail = psutil_status()
            if log is None:
                print(f"WARNING: {detail}", flush=True)
            else:
                log(detail, level="WARNING")
        return None


def _descendant_pids(pid, log=None):
    """Pids of everything below ``pid``, captured while it is still alive.

    Must be called BEFORE terminating the parent: once it exits, the link from a
    grandchild back to it is gone and the grandchild can no longer be found.

    Without psutil this degrades to "no descendant cleanup" rather than raising
    at shutdown - but it says so, once, instead of degrading silently.
    """
    psutil = _psutil_or_warn(log)
    if psutil is None:
        return []
    try:
        return [c.pid for c in psutil.Process(pid).children(recursive=True)]
    except Exception:
        return []


def _kill_pids(pids, log=None):
    """Kill any of ``pids`` still running. Returns how many were killed."""
    if not pids:
        return 0
    psutil = _psutil_or_warn(log)
    if psutil is None:
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
        # Names of the other children whose failures made this one look like a
        # shared-cause outage rather than a broken child.
        self.correlated_with = []
        self.correlated_evidence = None
        self.correlated_since = None
        self.correlated_retries = 0


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
                 healthy_uptime=HEALTHY_UPTIME_SEC,
                 correlation_window=CORRELATION_WINDOW_SEC,
                 correlated_min_children=CORRELATED_MIN_CHILDREN,
                 correlated_backoff=CORRELATED_BACKOFF_SEC,
                 environment_probe=None):
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
        self.correlation_window = correlation_window
        self.correlated_min_children = correlated_min_children
        self.correlated_backoff = correlated_backoff
        # Injectable so the decision can be tested without a socket.
        self.environment_probe = environment_probe or shared_dependency_down

        self._stopping = False
        self._exit_requested = False
        # name -> monotonic timestamp of that child's most recent failure. One
        # entry per child, so this cannot grow with time.
        self._last_failure_at = {}
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

    def _peers_failed_recently(self, child, now):
        """Other children whose most recent failure is inside the window.

        Only the *latest* failure per child is kept, which is all the rule needs
        and means the evidence cannot grow without bound during a long outage.
        During a shared outage every child keeps failing, so the evidence keeps
        refreshing itself and the correlated verdict holds for as long as the
        cause does. Once the peers recover and stay up, the window empties and a
        child still failing on its own falls back to permanent failure - so
        'correlated' is never a permanent escape from the budget.
        """
        return sorted(
            name for name, ts in self._last_failure_at.items()
            if name != child.spec.name and (now - ts) <= self.correlation_window
        )

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
        self._last_failure_at[child.spec.name] = now

        if uptime >= self.healthy_uptime:
            # It ran fine and then died. Not a crash loop - full budget again,
            # and any previous shared-cause episode is over. Clearing the peer
            # list matters: a stale "correlated with X" in the status file is
            # exactly the kind of thing that misdirects the next incident.
            child.consecutive_failures = 1
            child.correlated_with = []
            child.correlated_evidence = None
            child.correlated_since = None
        else:
            child.consecutive_failures += 1

        self._record(child, "exited", exit_code=exit_code,
                     uptime_seconds=round(uptime, 2),
                     consecutive_failures=child.consecutive_failures,
                     reason=reason)

        if child.consecutive_failures > self.max_consecutive_failures:
            # The budget is gone. Whether that means "this child is broken" or
            # "the environment is broken" is decided by whether it is alone -
            # and a child can have company in two ways: another child failing in
            # the same window, or a shared dependency being verifiably down.
            peers = self._peers_failed_recently(child, now)
            env_down, env_detail = False, None
            if len(peers) + 1 < self.correlated_min_children:
                try:
                    env_down, env_detail = self.environment_probe()
                except Exception as e:
                    # A probe that breaks must not decide anything.
                    self._log(f"environment probe failed: {e}", level="WARNING")
            if len(peers) + 1 >= self.correlated_min_children or env_down:
                self._enter_correlated(child, now, peers, exit_code, env_detail)
            else:
                self._fail_permanently(child, exit_code, reason)
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

    def _fail_permanently(self, child, exit_code, reason):
        """This child exhausted its budget and it did it alone."""
        child.state = STATE_FAILED
        child.next_restart_at = None
        child.correlated_with = []
        child.correlated_evidence = None
        child.correlated_since = None
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
        self._log("  No other child failed recently, so this is a broken child, "
                  "not a broken environment.", level="ERROR")
        self._log("  Giving up - this child will NOT be restarted again.", level="ERROR")
        self._log("  /health now reports unhealthy until it is fixed and the "
                  "launcher restarted.", level="ERROR")
        self._log("=" * 68, level="ERROR")
        self._record(child, "permanently_failed",
                     consecutive_failures=child.consecutive_failures,
                     reason=child.failure_reason)

    def _enter_correlated(self, child, now, peers, exit_code, env_detail=None):
        """Budget exhausted, but not alone - keep retrying, forever, loudly.

        No permanent failure and no escalating backoff: a fixed, long delay that
        neither hammers a struggling environment nor delays recovery past a
        minute once it clears.
        """
        first_time = child.state != STATE_RETRYING_CORRELATED
        evidence = (f"{len(peers)} other child(ren) failing within "
                    f"{self.correlation_window:.0f}s ({', '.join(peers)})"
                    if peers else (env_detail or "shared-cause evidence"))
        child.state = STATE_RETRYING_CORRELATED
        child.correlated_with = peers
        child.correlated_evidence = evidence
        child.correlated_retries += 1
        if first_time:
            child.correlated_since = time.time()
        child.failure_reason = (
            f"not failing alone - {evidence}. Treated as a shared-cause outage, "
            f"not a broken child. Retrying every {self.correlated_backoff:.0f}s "
            f"indefinitely; last exit code {exit_code}."
        )
        child.next_restart_at = now + self.correlated_backoff
        child.restarts += 1
        if first_time:
            self._log("=" * 68, level="ERROR")
            self._log(f"SHARED-CAUSE FAILURE: {child.spec.name}", level="ERROR")
            self._log(f"  Evidence: {evidence}", level="ERROR")
            self._log("  That points at the environment (database, disk, network),",
                      level="ERROR")
            self._log("  not at this child. NOT giving up.", level="ERROR")
            self._log(f"  Retrying every {self.correlated_backoff:.0f}s for as long "
                      "as it takes. No manual restart", level="ERROR")
            self._log("  will be needed once the cause clears; /health stays "
                      "unhealthy until then.", level="ERROR")
            self._log("=" * 68, level="ERROR")
        else:
            self._log(f"{child.spec.name} still failing ({evidence}); attempt "
                      f"{child.correlated_retries}, retrying again in "
                      f"{self.correlated_backoff:.0f}s.", level="ERROR")
        self._record(child, "correlated_failure",
                     peers=peers, evidence=evidence,
                     attempt=child.correlated_retries,
                     retry_in_seconds=self.correlated_backoff,
                     exit_code=exit_code)

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

            elif child.state in _WAITING_STATES:
                if child.next_restart_at is not None and now >= child.next_restart_at:
                    changed = True
                    if child.state == STATE_RETRYING_CORRELATED:
                        self._log(f"Retrying {child.spec.name} after shared-cause "
                                  f"failure (attempt {child.correlated_retries}, "
                                  f"no limit)...")
                    else:
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
            descendants = _descendant_pids(proc.pid, log=self._log)
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
            orphaned = _kill_pids(descendants, log=self._log)
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
                "correlated_with": c.correlated_with,
                "correlated_evidence": c.correlated_evidence,
                "correlated_since": c.correlated_since,
                "correlated_retries": c.correlated_retries,
            }
        return {
            "supervisor_pid": os.getpid(),
            "started_at": self._started_wall,
            "updated_at": time.time(),
            "stopping": self._stopping,
            # Two separate lists because they demand different responses: a
            # permanently failed child needs a human, a correlated one needs the
            # environment fixed and will then recover by itself.
            "failed_children": [c.spec.name for c in self.children
                                if c.state == STATE_FAILED],
            "correlated_children": [c.spec.name for c in self.children
                                    if c.state == STATE_RETRYING_CORRELATED],
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
