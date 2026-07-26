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
"""
import os
import json
import time
import threading

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

_state_lock = threading.Lock()
_state = {}  # name -> {"beats": int, "last_write": float, "started_at": float, "errors": int}


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
    with _state_lock:
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


def read_all(stale_after=DEFAULT_STALE_AFTER_SEC, now=None):
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
            out[name] = {
                "pid": data.get("pid"),
                "beats": data.get("beats"),
                "note": data.get("note"),
                "age_seconds": round(age, 2),
                "stale": age > stale_after,
                "stale_after_seconds": stale_after,
            }
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
