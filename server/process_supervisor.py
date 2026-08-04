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

A PORT CONFLICT IS NEITHER OF THOSE TWO THINGS
----------------------------------------------
``shared_dependency_down`` probes the database and nothing else, so the most
common real cause of a mass child failure on this box was landing in the
"environment is down" bucket by default. Measured over 74 child deaths since
2026-07-25: **100 % of them were the only two children that bind a TCP port**
(:8080 n=41, :8090 n=33); the three children that bind nothing died zero times.
Their uptime at death was a dead constant (min 3.0 s, median 3.1 s) - the time it
takes uvicorn to import the app and discover that the port is taken. The cause is
a second launcher started while the first was still running, and the response was
a 60 s correlated retry with NO LIMIT: the new stack fought the old one silently
for a minute, or forever.

A port held by another process is a **permanent local misconfiguration**. No
amount of retrying frees it, the environment is fine, and the fix is a sentence
long. So it is probed FIRST, ahead of both the peer rule and the database probe,
and it produces a terminal verdict that names the port and the PID that owns it.
The database-outage case is untouched: nothing is listening on the child's port
then, so the probe reports clear and the correlated policy runs exactly as before.

CHILD OUTPUT GOES TO A FILE, NOT ONLY TO A CONSOLE NOBODY KEPT
--------------------------------------------------------------
Every line uvicorn writes about its own start - ``Started server process``,
``Uvicorn running on``, ``Application startup complete``, and the ``OSError`` when
the bind fails - goes to the child's stdout/stderr, which the launcher used to
leave attached to the console and never record. So the single most decisive line
of the incident above existed in **no file on disk**, and diagnosing it required
reconstructing the cause from 74 deaths' worth of statistics. Each child's output
is now teed: byte-for-byte to the launcher's console exactly as before, and
appended to ``<DATA_ROOT>/<name>_stdout.log``.

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
import socket
import sys
import threading
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

# --- Port conflict -------------------------------------------------------
# How long the probes may take. Both run against this machine only, so a timeout
# this short is generous; the point is that a supervision tick can never hang on
# them.
PORT_PROBE_TIMEOUT_SEC = 0.5

# --- Child output capture -------------------------------------------------
# Each child's tee'd output file is rotated at this size (one .1 backup kept).
# uvicorn's access log is the volume driver, so this cannot be left unbounded on
# a launcher that runs for months.
CHILD_LOG_MAX_BYTES = 20 * 1024 * 1024

STATE_RUNNING = "running"
STATE_BACKOFF = "backoff"
STATE_FAILED = "failed"
STATE_STOPPED = "stopped"
# Budget exhausted, but not alone: retried forever, never permanently failed.
STATE_RETRYING_CORRELATED = "retrying_correlated"

# Why a child reached a terminal state. Recorded in the status file (and so in
# /health) because "permanently failed" and "permanently failed because something
# else owns its port" need completely different responses from an operator.
VERDICT_BROKEN_CHILD = "broken_child"
VERDICT_PORT_CONFLICT = "port_conflict"

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
    if url is None:
        # Same precedence as database/database.py (env > config/database.json),
        # resolved through paths (stdlib-only) so this keeps working when
        # sqlalchemy is broken. No built-in default here: the probe has always
        # treated "nothing configured" as nothing to probe.
        try:
            url, _src = paths.resolve_database_url()
        except Exception:
            url = os.environ.get("DATABASE_URL", "")
        url = url or ""
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


def port_owner(port, log=None):
    """``(pid, process_name)`` of whatever is LISTENing on ``port``, or ``(None, None)``.

    The PID is the whole value of this function: "port 8080 is taken" sends an
    operator hunting, "port 8080 is held by PID 8444 (python.exe)" ends the
    question. Verified on this box without administrator rights - the Windows
    TCP table exposes the owning PID to any caller.

    Never raises. Without psutil, or when the connection table cannot be read,
    the answer degrades to "taken by someone" rather than to an exception.
    """
    psutil = _psutil_or_warn(log)
    if psutil is None:
        return None, None
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status != psutil.CONN_LISTEN:
                continue
            if not conn.laddr or conn.laddr.port != port:
                continue
            pid = conn.pid
            name = None
            if pid:
                try:
                    name = psutil.Process(pid).name()
                except Exception:
                    name = None
            return pid, name
    except Exception:
        return None, None
    return None, None


def port_is_taken(port, host="0.0.0.0", timeout=PORT_PROBE_TIMEOUT_SEC):
    """``(taken, how)`` - could a new child bind ``port`` on ``host`` right now?

    Two independent probes, ORed, because each one alone has a blind spot on
    Windows: a bind test against ``0.0.0.0`` can succeed while another process
    holds ``127.0.0.1`` on the same port, and a connect test only sees a socket
    that is already accepting.

    ``SO_REUSEADDR`` is deliberately NOT set. On Windows it lets a bind to an
    already-bound port SUCCEED, which is precisely the answer this function must
    never produce.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host or "0.0.0.0", port))
        finally:
            s.close()
    except OSError as e:
        return True, f"bind failed ({type(e).__name__})"
    probe_host = "127.0.0.1" if host in (None, "", "0.0.0.0", "::") else host
    try:
        with socket.create_connection((probe_host, port), timeout=timeout):
            return True, f"something is already accepting on {probe_host}:{port}"
    except Exception:
        pass
    return False, None


def describe_port_conflict(port, host="0.0.0.0", timeout=PORT_PROBE_TIMEOUT_SEC):
    """One log-ready sentence about a port that is taken, or ``None`` if it is free."""
    taken, how = port_is_taken(port, host, timeout=timeout)
    if not taken:
        return None
    pid, name = port_owner(port)
    if pid:
        owner = f"PID {pid}" + (f" ({name})" if name else "")
    else:
        owner = "another process (its PID could not be read)"
    return f"TCP port {port} is already held by {owner} [{how}]"


def port_conflict(spec, timeout=PORT_PROBE_TIMEOUT_SEC):
    """``(conflict, detail)`` - is a port this child must bind already owned?

    The same class of evidence as ``shared_dependency_down`` and the opposite
    conclusion: a database that is down will come back and the child should keep
    trying, a port that belongs to somebody else will not free itself and the
    child must stop trying and say whose it is.
    """
    for port in getattr(spec, "ports", ()) or ():
        detail = describe_port_conflict(port, getattr(spec, "port_host", None),
                                        timeout=timeout)
        if detail:
            return True, detail
    return False, None


def preflight_port_check(ports, host="0.0.0.0", timeout=PORT_PROBE_TIMEOUT_SEC):
    """``[(port, detail), ...]`` for every port that is already taken.

    Called by the launcher BEFORE it starts anything. Five children racing an
    older stack for two ports is not a startup, it is a fight the operator cannot
    see; the only sane move is to refuse and name the winner.
    """
    conflicts = []
    for port in ports:
        detail = describe_port_conflict(port, host, timeout=timeout)
        if detail:
            conflicts.append((port, detail))
    return conflicts


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
                 heartbeat=None, start_delay=0.0, ports=(), port_host=None,
                 log_file=None):
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
        # TCP ports this child must be able to bind. Empty for a child that binds
        # nothing - and that distinction is exactly the one the 74-death sample
        # drew: every failure was a port binder, none were the others.
        self.ports = tuple(ports)
        self.port_host = port_host
        # Where this child's stdout/stderr is tee'd. None keeps the old
        # behaviour (console only, recorded nowhere).
        self.log_file = log_file


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
        # Which terminal verdict was reached, when one was. See VERDICT_*.
        self.terminal_verdict = None
        # Thread tee-ing this child's output to console + file, if it has one.
        self.log_pump = None
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
                 environment_probe=None, port_probe=None):
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
        # Same, for the port-conflict verdict. Takes the ChildSpec, because the
        # answer is per child: only some children bind anything.
        self.port_probe = port_probe or port_conflict

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
        if not spec.log_file:
            return subprocess.Popen(spec.cmd, cwd=spec.cwd, env=merged)
        # PYTHONUNBUFFERED is not a nicety here. With stdout on a pipe instead of
        # a console, CPython block-buffers it, and the one line this capture
        # exists for - the bind error - can sit in an 8 KB buffer while the
        # process dies. Flushing on every write costs nothing measurable next to
        # losing it.
        merged.setdefault("PYTHONUNBUFFERED", "1")
        return subprocess.Popen(spec.cmd, cwd=spec.cwd, env=merged,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)

    def _attach_log_pump(self, child):
        """Tee a child's merged stdout/stderr to the console AND to its own file.

        A pipe plus a reader thread rather than ``stdout=<file>`` because the
        console must keep showing exactly what it showed before: five children's
        interleaved output in one window is how an operator watches this system
        start. Redirecting straight to a file would have silenced that.

        Bytes are passed through undecoded. A child's stdout is already encoded
        in the console's code page (cp949 here), so writing its bytes to
        ``sys.stdout.buffer`` reproduces today's console byte for byte, and no
        decode step exists that could raise on a line and lose it.
        """
        spec = child.spec
        stream = getattr(child.proc, "stdout", None)
        if not spec.log_file or stream is None:
            return
        path = spec.log_file
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:
            pass
        header = (f"\n=== {spec.name} started "
                  f"{time.strftime('%Y-%m-%d %H:%M:%S')} pid="
                  f"{getattr(child.proc, 'pid', '?')} cmd={' '.join(spec.cmd)} "
                  f"===\n").encode("utf-8", "replace")

        def pump():
            handle = None
            written = 0
            try:
                handle = open(path, "ab")
                handle.write(header)
                handle.flush()
                written = os.path.getsize(path)
                console = getattr(sys.stdout, "buffer", None)
                for line in iter(stream.readline, b""):
                    try:
                        handle.write(line)
                        handle.flush()
                        written += len(line)
                    except Exception:
                        pass
                    if written > CHILD_LOG_MAX_BYTES:
                        # Rotate. If the rename fails (a reader holding the file
                        # open, say) reopen the original rather than leaving this
                        # child's output going nowhere for the rest of the run.
                        try:
                            handle.close()
                            os.replace(path, path + ".1")
                        except Exception:
                            pass
                        handle = open(path, "ab")
                        written = 0
                    if console is not None:
                        try:
                            console.write(line)
                            console.flush()
                        except Exception:
                            pass
            except Exception as e:
                self._log(f"Output capture for {spec.name} stopped: {e}",
                          level="WARNING")
            finally:
                for closeable in (handle, stream):
                    try:
                        if closeable is not None:
                            closeable.close()
                    except Exception:
                        pass

        t = threading.Thread(target=pump, name=f"logpump-{spec.name}", daemon=True)
        child.log_pump = t
        t.start()

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
            self._attach_log_pump(child)
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
            # The budget is gone. Three verdicts are possible, and they are asked
            # in this order because each one, when true, makes the next question
            # meaningless:
            #
            # 1. Someone else owns this child's port. Terminal, local, and named.
            #    It is asked FIRST because the duplicate-launcher case kills BOTH
            #    port-binding children at once, so the peer rule would happily
            #    call it a shared-cause outage and retry every 60 s forever -
            #    which is the bug this ordering exists to fix.
            # 2. It is not failing alone (peers, or the database is down).
            #    Retried indefinitely; the environment will come back.
            # 3. It is failing alone in a healthy environment. Broken child.
            conflict, conflict_detail = False, None
            if child.spec.ports:
                try:
                    conflict, conflict_detail = self.port_probe(child.spec)
                except Exception as e:
                    # A probe that breaks must not decide anything.
                    self._log(f"port conflict probe failed: {e}", level="WARNING")
            if conflict:
                self._fail_permanently(child, exit_code, reason,
                                       verdict=VERDICT_PORT_CONFLICT,
                                       detail=conflict_detail)
                self.write_status(force=True)
                return
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

    def _fail_permanently(self, child, exit_code, reason,
                          verdict=VERDICT_BROKEN_CHILD, detail=None):
        """Terminal. Either this child is broken, or its port belongs to somebody else."""
        child.state = STATE_FAILED
        child.next_restart_at = None
        child.correlated_with = []
        child.correlated_evidence = None
        child.correlated_since = None
        child.terminal_verdict = verdict
        if verdict == VERDICT_PORT_CONFLICT:
            child.failure_reason = (
                f"{detail}. That is a permanent local misconfiguration, not an "
                f"environment outage - retrying cannot take a port away from the "
                f"process that owns it."
            )
        else:
            child.failure_reason = (
                reason or
                f"exited {child.consecutive_failures} times in a row "
                f"(last exit code {exit_code}) without staying up "
                f"{self.healthy_uptime:.0f}s"
            )
        # Loud, and it stays failed. No further restart attempts.
        self._log("=" * 68, level="ERROR")
        if verdict == VERDICT_PORT_CONFLICT:
            self._log(f"CHILD PERMANENTLY FAILED - PORT CONFLICT: {child.spec.name}",
                      level="ERROR")
            self._log(f"  {detail}", level="ERROR")
            self._log("  This is NOT an environment outage: the database and the "
                      "network are irrelevant to", level="ERROR")
            self._log("  a port another process owns, and no number of retries "
                      "will free it.", level="ERROR")
            self._log("  Almost always a second launcher started while the first "
                      "was still running.", level="ERROR")
            self._log("  [HOW TO FIX] 기존 스택이 이미 떠 있으면 그대로 쓰십시오. "
                      "중복 기동이라면 위 PID 를 종료한 뒤", level="ERROR")
            self._log("  (taskkill /PID <pid> /T /F) 런처를 다시 시작하십시오.",
                      level="ERROR")
        else:
            self._log(f"CHILD PERMANENTLY FAILED: {child.spec.name}", level="ERROR")
            self._log(f"  {child.failure_reason}", level="ERROR")
            self._log("  No other child failed recently, so this is a broken child, "
                      "not a broken environment.", level="ERROR")
        self._log("  Giving up - this child will NOT be restarted again.", level="ERROR")
        self._log("  /health now reports unhealthy until it is fixed and the "
                  "launcher restarted.", level="ERROR")
        self._log("=" * 68, level="ERROR")
        self._record(child, "permanently_failed", verdict=verdict,
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
                "terminal_verdict": c.terminal_verdict,
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
