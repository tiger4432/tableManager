"""Progress heartbeats for the background worker processes.

WHY THIS IS NOT A PID CHECK
---------------------------
The production incident this exists for was an event-loop freeze: the process was
alive the whole time and served nothing for tens of seconds. `tasklist` would have
reported it healthy. So the signal a worker publishes here is deliberately
**progress-based** — the beat is emitted from inside the worker's own work loop, so
it stops advancing when the loop stops advancing, whether the process died,
deadlocked, or is wedged behind a blocked call.

    supervisor status says "running"  +  heartbeat stale  ->  WEDGED
    supervisor status says "running"  +  heartbeat fresh  ->  ok
    supervisor status says not running                    ->  DOWN

Those two facts come from different owners on purpose. The supervisor owns the
process handle, so it is authoritative about existence; only the worker itself can
be authoritative about progress. A single source could not tell those two failures
apart, and they need different responses.

STORAGE
-------
One small JSON file per worker under ``<DATA_ROOT>/config/worker_heartbeats/``.
This reuses the ``scheduler_status.json`` pattern (JSON under the config dir)
rather than inventing a third mechanism, and it buys two things for free:

* ``ASSY_DATA_ROOT`` already relocates it, so an isolated dev/QA stack cannot
  overwrite production's heartbeats — no extra isolation work.
* It does not depend on the database. A heartbeat stored in PostgreSQL would go
  stale for every worker at once during a database outage, conflating "the
  database is down" with "the workers are wedged". Those are separate rows in
  ``/health`` precisely so an operator can tell them apart.

Reading is O(number of workers) tiny files, so ``/health`` stays cheap enough to
poll continuously.

COST
----
``beat()`` is called from loops that iterate every 2-5 s, but a loop draining a
backlog can spin much faster, so writes are throttled to at most one per
``MIN_WRITE_INTERVAL_SEC``. A beat is a ~200 byte atomic file replace.

A monitoring feature must never become a new failure mode: every disk error here
is swallowed and counted, never raised into the worker's loop.

WORK CLAIMS - WHY A LIVENESS BEAT IS NOT ENOUGH
-----------------------------------------------
A beat proves *some* loop in the process is still turning. It does not prove the
loop that matters is. The watcher is the case in point: its beat came from the
3-second retry poller, so a watcher wedged **inside ingestion** - the exact shape
of the incident this was built for - kept beating and reported healthy.

Beating from the ingestion path instead would only move the hole: ingestion is
idle most of the time, so an ingestion-only beat is stale most of the time and
says nothing.

So the two facts are kept separate. A worker opens a ``work_claim`` around each
unit of real work and refreshes it as it progresses; the claim's age is published
*inside* whatever beat is written next, by whichever thread writes it. The poller
therefore stops being able to mask a wedged ingestion and starts being the thing
that reports it: it is alive, so it beats, and its beat carries "a file has been
claimed for 400 s with no progress".

Claims are thread-affine. A beat only refreshes claims opened on its own thread,
so a healthy heavy-lane job cannot refresh a wedged inline job's claim.
"""
import os
import json
import time
import itertools
import threading
from contextlib import contextmanager

try:
    import paths
except ImportError:  # imported without server/ on sys.path
    from .. import paths  # type: ignore

HEARTBEAT_DIRNAME = "worker_heartbeats"

# Do not touch the disk more than once per second per worker even if the loop
# spins faster than that.
MIN_WRITE_INTERVAL_SEC = 1.0

# How old a beat may get before /health calls the worker unhealthy.
#
# Derivation, not a round number picked by feel. The natural loop periods are:
#   watcher retry poller   3.0 s   (run_watcher.poll_pending_retries)
#   chain worker           2.0 s   (LISTEN wait timeout when idle)
#   graph materializer     2.0 s   (LISTEN wait timeout when idle)
#   auto-update scheduler  5.0 s   (check_interval)
# 60 s is therefore >= 12 consecutive missed beats for the slowest loop and ~20-30
# for the others. One missed beat must never trip an alarm — a GC pause, a slow
# disk, or a momentarily busy database would do that, and a health check that
# cries wolf gets muted, which is worse than not having one. Twelve consecutive
# misses is not noise.
#
# The ceiling on this number is how long data may silently stop flowing before
# someone finds out; 60 s is well inside "near-continuous operation" for an
# intranet team, and /health also publishes the raw age so a monitor may alarm
# earlier on its own.
DEFAULT_STALE_AFTER_SEC = 60.0

# How long a claimed unit of work may go without progress before /health calls it
# stalled. Deliberately much larger than DEFAULT_STALE_AFTER_SEC, because the two
# numbers bound different things.
#
# A missed beat means a loop that runs every 2-5 s did not run. A missed *claim
# progress* means a chunk of real work did not finish, and chunks are not
# uniform. Measured under a live 100,000-row heavy-lane ingestion (35 MB, 893 s
# end to end): chunk-to-chunk intervals p50 9.20 s, p95 9.70 s, **max 12.50 s**
# over 42 unambiguous single-chunk intervals. That is the instrumented part, and
# on its own it would justify something far tighter than this.
#
# The part we CANNOT instrument is what sets the floor: a custom pipeline parser
# is a user script that reads a whole file in one opaque call and reports nothing
# while it does. On a large workbook that legitimately takes minutes, and no beat
# can be emitted from inside it. 300 s clears the measured chunk cadence by 24x
# and still surfaces a genuinely wedged ingestion inside five minutes.
#
# The bias is toward silence, and that is the deliberate choice: this fires a 503
# on an operator dashboard, and a health check that cries wolf during the exact
# operation people care about gets muted, which costs more than five minutes of
# detection delay.
DEFAULT_STALL_AFTER_SEC = 300.0

_state_lock = threading.Lock()
_state = {}  # name -> {"beats": int, "last_write": float, "started_at": float, "errors": int}

# claim_id -> {"name", "what", "thread", "started", "last_progress"}
# Bounded by the number of units of work in flight (one per ingestion lane), not
# by time: every claim is removed in a finally block.
_claims = {}
_claim_seq = itertools.count(1)


def heartbeat_dir():
    return paths.config_path(HEARTBEAT_DIRNAME)


def heartbeat_path(name):
    return os.path.join(heartbeat_dir(), f"{name}.json")


def beat(name, note=None, force=False):
    """Record one unit of progress for worker ``name``.

    Call this from inside the worker's real work loop, once per iteration. Returns
    True when the beat reached the disk, False when it was throttled or failed —
    callers ignore the result; it exists for the tests.
    """
    now = time.time()
    tid = threading.get_ident()
    with _state_lock:
        # Progress on this thread's own claims. Thread-affine on purpose: a
        # healthy heavy-lane job must not be able to refresh a wedged inline
        # job's claim just because both belong to the same worker.
        for c in _claims.values():
            if c["name"] == name and c["thread"] == tid:
                c["last_progress"] = now

        st = _state.get(name)
        if st is None:
            st = {"beats": 0, "last_write": 0.0, "started_at": now, "errors": 0}
            _state[name] = st
        st["beats"] += 1
        if not force and (now - st["last_write"]) < MIN_WRITE_INTERVAL_SEC:
            return False
        st["last_write"] = now
        payload = {
            "name": name,
            "pid": os.getpid(),
            "ts": now,
            "beats": st["beats"],
            "started_at": st["started_at"],
            "note": note,
            # Written by whichever thread beats next - which is the point. The
            # poller reports the ingestion thread's stall.
            "work": _work_snapshot_locked(name),
        }

    try:
        d = heartbeat_dir()
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, f"{name}.json.tmp")
        # Fixed temp name per worker, so a crash mid-write leaves at most one
        # stale temp file instead of accumulating them.
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, heartbeat_path(name))  # atomic: a reader never sees a partial file
        return True
    except Exception:
        with _state_lock:
            _state[name]["errors"] += 1
        return False


def _work_snapshot_locked(name):
    """Oldest un-progressed claim for ``name``. Caller holds ``_state_lock``.

    Publishes an absolute timestamp rather than an age, so a reader measures the
    stall from *now* and not from whenever the beat happened to be written.
    """
    mine = [c for c in _claims.values() if c["name"] == name]
    if not mine:
        return {"open": 0}
    oldest = min(mine, key=lambda c: c["last_progress"])
    return {
        "open": len(mine),
        "oldest_progress_ts": oldest["last_progress"],
        "oldest_started_ts": oldest["started"],
        "oldest_what": oldest["what"],
    }


@contextmanager
def work_claim(name, what):
    """Declare a unit of real work in progress for worker ``name``.

    Wrap the whole unit (one file's ingestion), and call ``beat(name)`` from
    inside it as it progresses - each beat on this thread refreshes the claim.
    The claim is always released, including on the failure paths, because a claim
    left open by a crashed job would look exactly like a stall forever.
    """
    now = time.time()
    cid = next(_claim_seq)
    with _state_lock:
        _claims[cid] = {"name": name, "what": str(what)[:200],
                        "thread": threading.get_ident(),
                        "started": now, "last_progress": now}
    # Beat on entry so the claim is visible in the heartbeat file immediately,
    # rather than only after the next poller tick.
    beat(name, note=f"start: {what}", force=True)
    try:
        yield
    finally:
        with _state_lock:
            _claims.pop(cid, None)
        beat(name, note=f"done: {what}", force=True)


def open_claims():
    """Every claim currently open in this process (for tests and diagnostics)."""
    with _state_lock:
        return [dict(c) for c in _claims.values()]


def read_all(stale_after=DEFAULT_STALE_AFTER_SEC, now=None,
             stall_after=DEFAULT_STALL_AFTER_SEC):
    """Read every worker heartbeat. Returns ``{name: {...}}``.

    Each entry carries ``age_seconds`` and ``stale``. Unreadable or corrupt files
    are reported as stale with an ``error`` field rather than being skipped —
    silence is the one answer a health check must never give.
    """
    now = time.time() if now is None else now
    out = {}
    d = heartbeat_dir()
    try:
        names = [f for f in os.listdir(d) if f.endswith(".json")]
    except OSError:
        return out

    for fname in names:
        name = fname[: -len(".json")]
        try:
            with open(os.path.join(d, fname), encoding="utf-8") as f:
                data = json.load(f)
            ts = float(data.get("ts") or 0.0)
            age = max(0.0, now - ts)
            entry = {
                "pid": data.get("pid"),
                "beats": data.get("beats"),
                "note": data.get("note"),
                "age_seconds": round(age, 2),
                "stale": age > stale_after,
                "stale_after_seconds": stale_after,
            }
            work = data.get("work") or {}
            if work.get("open"):
                # Measured from now, not from when the beat was written: a beat
                # that is itself 30 s old must not under-report the stall by 30 s.
                since = now - float(work.get("oldest_progress_ts") or now)
                entry["work"] = {
                    "open": work.get("open"),
                    "what": work.get("oldest_what"),
                    "no_progress_seconds": round(max(0.0, since), 2),
                    "held_seconds": round(
                        max(0.0, now - float(work.get("oldest_started_ts") or now)), 2),
                    "stalled": since > stall_after,
                    "stall_after_seconds": stall_after,
                }
            out[name] = entry
        except Exception as e:
            out[name] = {
                "pid": None,
                "beats": None,
                "age_seconds": None,
                "stale": True,
                "stale_after_seconds": stale_after,
                "error": f"unreadable heartbeat: {type(e).__name__}",
            }
    return out
