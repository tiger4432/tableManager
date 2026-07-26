"""The /health contract.

WHAT THIS HAS TO GET RIGHT
--------------------------
1. It must return JSON and it must return **non-200 when unhealthy**. Before this
   existed, `/health` was not a route at all, so it fell through to the SPA
   catch-all in main.py and returned **HTML with a 200** - an external monitor
   pointed at this system would have called a dead server alive.

2. Liveness is not enough. The production incident was an event-loop freeze: the
   process was alive the whole time and served nothing for tens of seconds. A pid
   check would have reported healthy. So a worker is judged by the *progress beat*
   it publishes (server/utils/heartbeat.py), and the supervisor's process view is
   joined to it to name the failure precisely:

       supervisor: not running                  -> down    (B1 restarts it)
       supervisor: running + beat stale         -> wedged  (alive, not progressing)
       supervisor: running + no beat yet, young -> starting (grace, not an alarm)
       supervisor: running + beat fresh         -> ok

3. It must not hang when the database is down, and it must be cheap enough to
   poll continuously. Every query here is O(1) against a partial index; the
   database probe is time-bounded by the caller.

WHY BACKLOG IS MEASURED BY AGE, NOT SIZE
----------------------------------------
The obvious check - "is the unprocessed outbox count large?" - is wrong here. A
single legitimate 100,000-row ingestion creates ~116,000 outbox rows (measured in
the P2 drills), so a size threshold low enough to catch a stuck chain worker would
fire on every large file. What separates "busy" from "stuck" is whether the queue
*drains*: if the chain worker is keeping up, the oldest unprocessed row stays
young no matter how many rows are behind it. If it is dead or wedged, that age
grows without bound. Age is the signal; size is reported for context only.
"""
import time
from datetime import datetime, timezone

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_UNHEALTHY = "unhealthy"

HTTP_OK = 200
HTTP_UNHEALTHY = 503

# A freshly started worker has to import its modules and reach its loop before it
# can beat. Without this grace the launcher would serve a 503 on every boot, and a
# health check that is routinely wrong at startup gets ignored.
STARTUP_GRACE_SEC = 60.0

# Backlog age thresholds. The chain worker's measured notify latency is 0-31 ms
# and it drains continuously even mid-ingestion, so an oldest-unprocessed row
# older than 5 minutes already means it is not keeping up; 15 minutes means it is
# not working at all. Both are far above normal operation and far below "someone
# notices tomorrow".
OUTBOX_AGE_DEGRADED_SEC = 300.0
OUTBOX_AGE_UNHEALTHY_SEC = 900.0

# Counting the backlog is capped so the query cost cannot grow with the table.
OUTBOX_COUNT_CAP = 10000


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat()


def compute_health(db_result, heartbeats, supervisor_status, outbox_result,
                   stale_after, now=None):
    """Pure status computation. Returns ``(payload, http_status)``.

    Kept free of I/O so the decision table can be tested directly, without a
    database, a supervisor, or a running worker.
    """
    now = time.time() if now is None else now
    problems = []
    worst = STATUS_OK

    def escalate(level):
        nonlocal worst
        order = {STATUS_OK: 0, STATUS_DEGRADED: 1, STATUS_UNHEALTHY: 2}
        if order[level] > order[worst]:
            worst = level

    # ---------------------------------------------------------------- database
    db_check = dict(db_result or {"status": "down", "error": "no probe result"})
    if db_check.get("status") == "ok":
        pass
    elif db_check.get("status") == "timeout":
        escalate(STATUS_DEGRADED)
        problems.append("database probe timed out")
    else:
        escalate(STATUS_UNHEALTHY)
        problems.append(f"database unreachable: {db_check.get('error')}")

    # -------------------------------------------------------------- supervisor
    sup_check = {}
    sup_children = {}
    if supervisor_status is None:
        # No launcher-managed supervisor (a bare uvicorn, or the isolated dev
        # stack). Worker beats found on disk are still checked, but nothing can
        # be said about processes that never started.
        sup_check = {"status": "absent",
                     "detail": "no supervisor status file; worker checks are advisory"}
    else:
        sup_children = supervisor_status.get("children") or {}
        age = now - float(supervisor_status.get("updated_at") or 0.0)
        failed = supervisor_status.get("failed_children") or []
        sup_check = {
            "status": STATUS_OK,
            "pid": supervisor_status.get("supervisor_pid"),
            "updated_age_seconds": round(age, 2),
            "failed_children": failed,
            "children": {n: {"state": c.get("state"),
                             "restarts": c.get("restarts"),
                             "pid": c.get("pid"),
                             "last_exit_code": c.get("last_exit_code"),
                             "failure_reason": c.get("failure_reason")}
                         for n, c in sup_children.items()},
        }
        if age > stale_after:
            sup_check["status"] = "stale"
            escalate(STATUS_UNHEALTHY)
            problems.append(
                f"supervisor status is {age:.0f}s old - the supervisor itself "
                f"is not running, so no child is being watched")
        if failed:
            sup_check["status"] = "failed_children"
            escalate(STATUS_UNHEALTHY)
            for name in failed:
                reason = (sup_children.get(name) or {}).get("failure_reason")
                problems.append(f"child '{name}' permanently failed: {reason}")

    # ----------------------------------------------------------------- workers
    # Who *should* be beating: the supervisor's own list when there is one,
    # otherwise whatever beats exist on disk.
    expected = {}
    for cname, cinfo in sup_children.items():
        hb_name = cinfo.get("heartbeat")
        if hb_name:
            expected[hb_name] = cinfo
    if not expected:
        expected = {name: None for name in heartbeats}

    workers = {}
    for hb_name, cinfo in sorted(expected.items()):
        hb = heartbeats.get(hb_name)
        entry = {"heartbeat": hb_name}
        if cinfo is not None:
            entry["supervisor_state"] = cinfo.get("state")
            entry["pid"] = cinfo.get("pid")
            entry["restarts"] = cinfo.get("restarts")

        sup_state = (cinfo or {}).get("state")
        uptime = (cinfo or {}).get("uptime_seconds")

        # A beat only counts if the SUPERVISED process wrote it. Heartbeat files
        # are keyed by worker role, so without this check any second process of
        # the same role masks the real one. Two ways that bites:
        #
        #   * a stray worker started by hand (or by a second stack sharing this
        #     data root) keeps beating while the supervised one is wedged;
        #   * right after a restart the *dead predecessor's* beat is still fresh,
        #     so a replacement that crashes before reaching its loop would look
        #     healthy for a whole staleness window.
        #
        # Both were observed for real: a concurrent isolated stack on the same
        # dev_env kept `chain.json` fresh while the supervised chain worker was
        # suspended, and /health reported ok. Treat a mismatched pid as no beat
        # at all, which routes into the starting/missing logic below.
        if (hb is not None and cinfo is not None
                and cinfo.get("pid") is not None
                and hb.get("pid") is not None
                and hb.get("pid") != cinfo.get("pid")):
            entry["beat_pid"] = hb.get("pid")
            entry["detail_beat"] = (
                f"heartbeat was written by pid {hb.get('pid')}, not by the "
                f"supervised pid {cinfo.get('pid')}")
            hb = None

        if cinfo is not None and sup_state != "running":
            entry["status"] = "down"
            entry["detail"] = f"supervisor reports state '{sup_state}'"
            escalate(STATUS_UNHEALTHY)
            problems.append(f"worker '{hb_name}' is down (supervisor state: {sup_state})")
        elif hb is None:
            why = entry.pop("detail_beat", None)
            if uptime is not None and uptime < STARTUP_GRACE_SEC:
                entry["status"] = "starting"
                entry["detail"] = why or f"no beat yet, up {uptime:.0f}s"
                escalate(STATUS_DEGRADED)
            else:
                entry["status"] = "foreign_beat" if why else "missing"
                entry["detail"] = why or (
                    "process is running but has never published a beat")
                escalate(STATUS_UNHEALTHY)
                problems.append(f"worker '{hb_name}': {entry['detail']}")
        elif hb.get("stale"):
            # The case a pid check cannot see.
            entry["status"] = "wedged" if cinfo is not None else "stale"
            entry["age_seconds"] = hb.get("age_seconds")
            entry["beats"] = hb.get("beats")
            if hb.get("error"):
                entry["error"] = hb["error"]
            escalate(STATUS_UNHEALTHY)
            problems.append(
                f"worker '{hb_name}' has made no progress for "
                f"{hb.get('age_seconds')}s (threshold {stale_after:.0f}s)"
                + (" although its process is alive" if cinfo is not None else ""))
        else:
            entry["status"] = STATUS_OK
            entry["age_seconds"] = hb.get("age_seconds")
            entry["beats"] = hb.get("beats")
        entry["stale_after_seconds"] = stale_after
        workers[hb_name] = entry

    # ------------------------------------------------------------------ outbox
    outbox_check = dict(outbox_result or {})
    if outbox_check.get("status") == "unavailable":
        # The database check above already reported this; do not double-count.
        pass
    else:
        oldest = outbox_check.get("oldest_age_seconds")
        outbox_check["status"] = STATUS_OK
        if oldest is not None and oldest > OUTBOX_AGE_UNHEALTHY_SEC:
            outbox_check["status"] = STATUS_UNHEALTHY
            escalate(STATUS_UNHEALTHY)
            problems.append(
                f"outbox backlog is not draining: oldest unprocessed event is "
                f"{oldest:.0f}s old")
        elif oldest is not None and oldest > OUTBOX_AGE_DEGRADED_SEC:
            outbox_check["status"] = STATUS_DEGRADED
            escalate(STATUS_DEGRADED)
            problems.append(
                f"outbox backlog draining slowly: oldest unprocessed event is "
                f"{oldest:.0f}s old")

    payload = {
        "status": worst,
        "checked_at": _iso(now),
        "problems": problems,
        "checks": {
            "database": db_check,
            "workers": workers,
            "outbox": outbox_check,
            "supervisor": sup_check,
        },
    }
    return payload, (HTTP_OK if worst != STATUS_UNHEALTHY else HTTP_UNHEALTHY)


def probe_outbox(db):
    """Backlog size (capped) and age of the oldest unprocessed event.

    Both queries ride the partial index ``idx_outbox_unprocessed``
    (``(processed_chain, id) WHERE processed_chain = false``):

    * the age query is ``ORDER BY id ASC LIMIT 1`` - one index entry, O(1)
      regardless of how many rows the table holds;
    * the count is wrapped in ``LIMIT OUTBOX_COUNT_CAP + 1`` so it can never scan
      more than ~10k index entries even with a 10,000,000-row table. An exact
      count above the cap has no operational meaning anyway.
    """
    from sqlalchemy import text
    out = {}
    row = db.execute(text(
        "SELECT EXTRACT(EPOCH FROM (now() - created_at)) AS age "
        "FROM database_outbox WHERE processed_chain = false "
        "ORDER BY id ASC LIMIT 1"
    )).fetchone()
    out["oldest_age_seconds"] = round(float(row[0]), 2) if row and row[0] is not None else None

    cnt = db.execute(text(
        "SELECT count(*) FROM ("
        "  SELECT 1 FROM database_outbox WHERE processed_chain = false LIMIT :cap"
        ") s"
    ), {"cap": OUTBOX_COUNT_CAP + 1}).scalar()
    cnt = int(cnt or 0)
    out["pending"] = min(cnt, OUTBOX_COUNT_CAP)
    out["pending_capped"] = cnt > OUTBOX_COUNT_CAP
    out["count_cap"] = OUTBOX_COUNT_CAP
    return out
