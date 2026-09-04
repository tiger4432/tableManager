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
       ... + a claimed unit of work that has stopped progressing -> stalled

   The last row is what a beat alone cannot see. A beat proves *a* loop is
   turning; the watcher's came from its 3 s retry poller, so a watcher wedged
   inside ingestion kept beating and this endpoint said ok. Workers therefore
   also publish work claims (server/utils/heartbeat.py), and a claim that stops
   advancing is unhealthy no matter how fresh the beat is.

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

# The config-backup probe is re-read at most this often. /health is designed to be
# polled continuously, and the answer changes at most once a week.
BACKUP_PROBE_CACHE_SEC = 60.0

# Sentinel: "the caller said nothing, so run the probe". Distinct from None, which
# means "explicitly do not check" - that is what the unit tests pass to keep the
# decision table free of I/O.
_PROBE = object()

_backup_cache = {"at": 0.0, "value": None}


def probe_config_backups(now=None):
    """Age of the newest ``server/config/`` snapshot. Never raises.

    Unlike the database probe this is not injected from the route. The database
    probe has to be, because it can hang and therefore needs the route's
    ``wait_for`` around it; this is a ``listdir`` of a local directory, which
    cannot hang in any way worth defending against, and it is cached for
    ``BACKUP_PROBE_CACHE_SEC`` on top of that.
    """
    wall = time.time()
    if (_backup_cache["value"] is not None
            and wall - _backup_cache["at"] < BACKUP_PROBE_CACHE_SEC):
        return _backup_cache["value"]
    try:
        import config_backup
        value = config_backup.probe(now=now)
    except Exception as e:
        value = {"status": "unknown", "error": f"{type(e).__name__}: {e}"}
    _backup_cache["at"] = wall
    _backup_cache["value"] = value
    return value


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat()


def compute_health(db_result, heartbeats, supervisor_status, outbox_result,
                   stale_after, now=None, backup_result=_PROBE):
    """Pure status computation. Returns ``(payload, http_status)``.

    Kept free of I/O so the decision table can be tested directly, without a
    database, a supervisor, or a running worker. ``backup_result`` is the one
    argument that defaults to running its own probe when the caller omits it
    (see ``probe_config_backups``); pass ``None`` to skip the check entirely,
    which is what the tests do to keep this function pure.
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
    # Set when the status file is too old to be read as the present. Everything
    # below that reads `sup_children` has to know, because a table whose writer
    # stopped updating it is a RECORD - and a record stated in the present tense
    # is a claim with nothing behind it.
    sup_stale = False
    sup_age = None
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
        correlated = supervisor_status.get("correlated_children") or []
        sup_check = {
            "status": STATUS_OK,
            "pid": supervisor_status.get("supervisor_pid"),
            "updated_age_seconds": round(age, 2),
            "failed_children": failed,
            "correlated_children": correlated,
            "children": {n: {"state": c.get("state"),
                             "restarts": c.get("restarts"),
                             "pid": c.get("pid"),
                             "last_exit_code": c.get("last_exit_code"),
                             "failure_reason": c.get("failure_reason"),
                             "correlated_with": c.get("correlated_with"),
                             "correlated_retries": c.get("correlated_retries")}
                         for n, c in sup_children.items()},
        }
        if age > stale_after:
            sup_check["status"] = "stale"
            sup_stale = True
            sup_age = age
            escalate(STATUS_UNHEALTHY)
            problems.append(
                f"supervisor status is {age:.0f}s old - the supervisor itself "
                f"is not running, so no child is being watched")
        # Reported before permanent failures, because it changes what the
        # operator should do: a shared-cause outage needs the environment fixed
        # and then recovers by itself, with no launcher restart.
        if correlated:
            sup_check["status"] = "correlated_failure"
            escalate(STATUS_UNHEALTHY)
            problems.append(
                f"{len(correlated)} children are failing together "
                f"({', '.join(correlated)}) - treated as a shared-cause outage. "
                f"They are being retried indefinitely and will recover on their "
                f"own once the cause clears; no manual restart is needed. Check "
                f"the database, the disk and the network first.")
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

        # 🔴 IS THIS WORKER BEING WATCHED *NOW*? Having a row in the table is a
        # different question. Once the supervisor stopped updating the file, its
        # row records what was true when it was written and nothing about the
        # present, so it decides nothing below and the beats on disk decide
        # instead. The check above has already said as much - this is the same
        # conclusion applied to the lines that consume the table.
        #
        # MEASURED 2026-09-04 ON THIS BOX, which is why this is not a tidy-up:
        # the file was 14.2 days old and named three workers 'stopped', and two
        # of them had written a beat 0.1 s and 0.6 s before the request. The
        # endpoint called all three down while the evidence refuting it was
        # already in `hb`, in the same response.
        watched = cinfo is not None and not sup_stale

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
        # (`watched`, not `cinfo is not None`: when the supervisor is gone there is
        # no supervised pid for a beat to disagree with, so the mismatch below is
        # not a fact that can be established.)
        if (hb is not None and watched
                and cinfo.get("pid") is not None
                and hb.get("pid") is not None
                and hb.get("pid") != cinfo.get("pid")):
            entry["beat_pid"] = hb.get("pid")
            entry["detail_beat"] = (
                f"heartbeat was written by pid {hb.get('pid')}, not by the "
                f"supervised pid {cinfo.get('pid')}")
            hb = None

        if watched and sup_state != "running":
            entry["status"] = "down"
            entry["detail"] = f"supervisor reports state '{sup_state}'"
            escalate(STATUS_UNHEALTHY)
            problems.append(f"worker '{hb_name}' is down (supervisor state: {sup_state})")
        elif hb is None and cinfo is not None and sup_stale:
            # No beat, and the only other witness stopped writing. Unhealthy
            # either way - but "down" would restate the dead table, and the
            # "missing" wording below says the process is running and has never
            # beaten, which asserts a running process nobody has seen. What is
            # actually known is that nothing here says anything about now.
            entry["status"] = "unknown"
            entry["detail"] = (
                f"no beat on disk, and the supervisor that recorded state "
                f"'{sup_state}' stopped updating {sup_age:.0f}s ago")
            escalate(STATUS_UNHEALTHY)
            problems.append(f"worker '{hb_name}': {entry['detail']}")
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
            entry["status"] = "wedged" if watched else "stale"
            entry["age_seconds"] = hb.get("age_seconds")
            entry["beats"] = hb.get("beats")
            if hb.get("error"):
                entry["error"] = hb["error"]
            escalate(STATUS_UNHEALTHY)
            problems.append(
                f"worker '{hb_name}' has made no progress for "
                f"{hb.get('age_seconds')}s (threshold {stale_after:.0f}s)"
                + (" although its process is alive" if watched else ""))
        else:
            entry["status"] = STATUS_OK
            entry["age_seconds"] = hb.get("age_seconds")
            entry["beats"] = hb.get("beats")

        # A fresh beat only proves *a* loop is turning. If the worker also has a
        # unit of real work claimed and that work has stopped progressing, the
        # worker is wedged where it matters even though it is still beating -
        # which is precisely the watcher case: its 3 s retry poller kept beating
        # while ingestion was stuck, and this endpoint said ok.
        work = (hb or {}).get("work") or {}
        if work.get("open"):
            entry["work"] = work
            if work.get("stalled"):
                # Do not mask a more specific verdict (down/wedged/missing);
                # those name a bigger problem than a stalled unit of work.
                if entry["status"] == STATUS_OK:
                    entry["status"] = "stalled"
                escalate(STATUS_UNHEALTHY)
                problems.append(
                    f"worker '{hb_name}' is beating but its work has not "
                    f"progressed for {work.get('no_progress_seconds')}s "
                    f"(threshold {work.get('stall_after_seconds')}s): "
                    f"{work.get('what')}")
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

        # The undelivered-broadcast sweep. Judged by the SAME thresholds as the backlog
        # above rather than new ones: it is the same question - is this queue draining -
        # and those numbers already carry their justification at the top of this file.
        # The sweep's own interval is 5 s plus a 5 s grace, so five minutes of a row
        # sitting undelivered is far outside anything the sweep does when it is running.
        undelivered = outbox_check.get("undelivered_oldest_age_seconds")
        if undelivered is not None and undelivered > OUTBOX_AGE_UNHEALTHY_SEC:
            escalate(STATUS_UNHEALTHY)
            problems.append(
                f"undelivered broadcasts are not being swept: the oldest row written "
                f"but never announced is {undelivered:.0f}s old - the chain worker's "
                f"recovery sweep is not clearing them, so clients are not being told "
                f"about writes that succeeded")
        elif undelivered is not None and undelivered > OUTBOX_AGE_DEGRADED_SEC:
            escalate(STATUS_DEGRADED)
            problems.append(
                f"undelivered broadcasts are draining slowly: the oldest row written "
                f"but never announced is {undelivered:.0f}s old")

    # ----------------------------------------------------------- config backup
    # A weekly job that silently stopped three weeks ago is worse than no job at
    # all, because the rollback procedure will claim a backup exists. This is the
    # place that says otherwise, and it reads the snapshot files themselves rather
    # than any "last run" status the job wrote about itself.
    #
    # DEGRADED, never UNHEALTHY: a missing backup means the *next* incident will
    # be harder, not that this system is failing now. Returning 503 for it would
    # tell a monitor to restart a perfectly healthy stack.
    if backup_result is _PROBE:
        backup_result = probe_config_backups(now=None)
    backup_check = {}
    if backup_result is not None:
        backup_check = dict(backup_result)
        # "unknown" escalates too: could-not-check must never be reported as
        # nothing-is-wrong, which is the same contract the collectors follow.
        if backup_check.get("status") in ("missing", "stale", "unknown"):
            escalate(STATUS_DEGRADED)
            problems.append(
                "config backup: " + str(backup_check.get("detail")
                                        or backup_check.get("error")
                                        or backup_check.get("status")))

    payload = {
        "status": worst,
        "checked_at": _iso(now),
        "problems": problems,
        "checks": {
            "database": db_check,
            "workers": workers,
            "outbox": outbox_check,
            "supervisor": sup_check,
            "config_backup": backup_check,
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

    # 🔴 THE SAFETY NET LIVES INSIDE THE THING IT PROTECTS, so nothing outside could
    # tell it had stopped. `sweep_undelivered_broadcasts` re-fires notifications whose
    # `broadcast_at` never got stamped, and it runs INSIDE the chain worker's loop - if
    # that sweep stops while the worker keeps beating, every affected client simply never
    # hears about rows that were written. Nothing reported that, at all.
    #
    # This measures the sweep's BACKLOG rather than its last run, for the same reason
    # this file measures the outbox by age and not by size: a sweep that runs and fails
    # every time leaves a fresh timestamp and a growing backlog, and it is the backlog
    # that hurts. It also needs no new state anywhere - the row set is exactly the one
    # `idx_outbox_undelivered` already indexes for the sweep itself (EXPLAIN 2026-09-04:
    # index scan, cost 4.15), so the watcher and the watched read the same definition.
    row = db.execute(text(
        "SELECT EXTRACT(EPOCH FROM (now() - created_at)) AS age "
        "FROM database_outbox "
        "WHERE processed_chain = true AND status = 'SUCCESS' AND broadcast_at IS NULL "
        "ORDER BY id ASC LIMIT 1"
    )).fetchone()
    out["undelivered_oldest_age_seconds"] = (
        round(float(row[0]), 2) if row and row[0] is not None else None)
    return out
