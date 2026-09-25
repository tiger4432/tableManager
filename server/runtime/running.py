# -*- coding: utf-8 -*-
"""「지금 도는 것」 — ONE seat, four sources (총괄 78ebdcfc0 · 5996d7f54, 소유자 「러닝도 한문으로」).

The top queue counted only the chain rules the chain loop was running; a retroactive run
left the queue the moment the scheduler claimed it, so a run could be moving while the
queue said RUNNING 0. Each source keeps its own judgement and this is where they are asked,
in one shape:

    chain rules      the chain loop's registry, or its heartbeat lap   `chain_sight`
    retroactive      the run table's in-flight row                     `admin.retroactive.in_flight`
    collectors       the scheduler's status file                       `collector_is_running`
    file ingestion   the watcher's pushed registry (this process)      `ingestion_is_running`

⛔ PROCESS LIVENESS IS NOT HERE (총괄 d02b5a4f4): 「is the process alive」 and 「is work
running」 are two questions. The supervisor's child state and the heartbeats answer the
first; this answers the second.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import event_constants

#: Where a running item runs - words the screen draws as they come, never branches on.
WHERE_CHAIN_WORKER = "chain_worker"
WHERE_OWN_PROCESS = "own_process"
WHERE_SCHEDULER = "scheduler"
WHERE_WATCHER = "watcher"

#: A run's `runner` is `<heartbeat name>/<host>/<pid>`; the name says which process.
_WHERE_BY_RUNNER = {"chain": WHERE_CHAIN_WORKER, "scheduler": WHERE_SCHEDULER}


#: Whether the process that started an item is still on it - `heartbeat.runner_state` in the
#: queue's words. One judgment for retroactive runs and collectors (총괄 c44a7d2e4).
STATE_RUNNING = "running"


def run_state(runner):
    """`running` · `orphaned` · `unknown` for a `<heartbeat name>/<host>/<pid>` stamp."""
    from utils import heartbeat

    state = heartbeat.runner_state(runner)
    return STATE_RUNNING if state == "owned" else state


def collector_is_running(entry) -> bool:
    """A scheduler status-file entry: the scheduler writes this status when a run starts."""
    return (entry or {}).get("last_status") == event_constants.COLLECTOR_STATUS_RUNNING


def collector_last_status(entry):
    """The Auto Update tab's word for a status-file entry: its `last_status` - except a
    RUNNING whose scheduler is no longer on it, which reads as the judgment says. A dead
    scheduler cannot write its own ending, so the reader decides."""
    if not collector_is_running(entry):
        return (entry or {}).get("last_status")
    state = run_state((entry or {}).get("runner"))
    return event_constants.COLLECTOR_STATUS_RUNNING if state == STATE_RUNNING else state


def ingestion_is_running(job) -> bool:
    """A watcher registry entry. QUEUED is waiting in the heavy lane, not running."""
    return (job or {}).get("status") == event_constants.PROGRESS_STATUS_RUNNING


def chain_sight():
    """WHOSE chain loop (총괄 3c3f2b1f2): this process's registry when the loop runs here;
    the chain worker's heartbeat lap when it runs on its own - the API's registry is empty
    then. `via` None = not seen: what it lists is then blind, not empty."""
    from chain import activity
    from utils import heartbeat
    # 🔴 «어느 파일을 열어야 하나» — 로거에서 «읽는다», 상수는 거짓이 된다(통합 프로세스는
    #    server.log, 단독 워커는 chain_worker.log). «이름»이지 경로가 아니다.
    from utils import logger as process_logging

    if activity.registry.attached:
        return {"via": "this_process", "age": 0.0, "pid": os.getpid(),
                "log": process_logging.active_log_filename(),
                "instants": activity.registry.instants()}
    beat = heartbeat.read_all().get("chain") or {}
    lap = (beat.get("laps") or {}).get("chain") or {}
    if "outcomes" in lap and not beat.get("stale"):
        return {"via": "chain_worker_heartbeat", "age": beat.get("age_seconds"),
                "pid": beat.get("pid"), "log": lap.get("log_filename"), "instants": lap}
    return {"via": None, "age": None, "pid": None, "log": None, "instants": {}}


def _item(what, where, pid, started_at, elapsed, processed=None, total=None, cancel=None,
          state=STATE_RUNNING):
    return {"what": what, "where": where, "pid": pid, "started_at": started_at,
            "elapsed_seconds": None if elapsed is None else round(max(0.0, elapsed), 1),
            "progress": (None if processed is None and total is None
                         else {"processed": processed, "total": total}),
            "cancel": cancel, "state": state}


def _chain(sight, shape, now):
    return [_item(e.get("rule"), WHERE_CHAIN_WORKER, sight["pid"],
                  None if e.get("running_seconds") is None else
                  (now - timedelta(seconds=e["running_seconds"])).isoformat(),
                  e.get("running_seconds"), total=e.get("rows_in"))
            for e in shape["running"]]


def _retroactive(db, now):
    from admin import retroactive

    run = retroactive.in_flight(db, now=now)
    if run is None:
        return []
    parts = str(run.get("runner") or "").split("/")
    name, pid = parts[0], (parts[2] if len(parts) == 3 else None)
    started = run.get("started_at")
    elapsed = None
    if started:
        at = datetime.fromisoformat(started)
        elapsed = (now - (at if at.tzinfo else at.replace(tzinfo=timezone.utc))).total_seconds()
    try:
        label = retroactive.operation(run["op"])["label"]
    except Exception:                                            # noqa: BLE001
        label = run["op"]
    return [_item(label, _WHERE_BY_RUNNER.get(name, WHERE_OWN_PROCESS),
                  int(pid) if str(pid).isdigit() else None, started, elapsed,
                  run.get("processed_rows"), run.get("total_rows"),
                  None if run.get("cancel_reaches") == retroactive.CANCEL_NEVER
                  else {"run_id": run["run_id"]},
                  state=run_state(run.get("runner")))]


def _collectors(scheduler_pid):
    from utils import auto_update_control as auc
    import json

    path = os.path.join(auc.SERVER_DIR, "config", "scheduler_status.json")
    try:
        with open(path, encoding="utf-8") as fh:
            entries = json.load(fh).get("collectors") or []
    except (OSError, ValueError):
        return []
    out = []
    for entry in entries:
        if not collector_is_running(entry):
            continue
        started, elapsed = entry.get("last_run"), None
        try:
            elapsed = (datetime.now() - datetime.strptime(
                started, "%Y-%m-%d %H:%M:%S")).total_seconds()
        except (TypeError, ValueError):
            pass
        # The pid the run was STAMPED with - the scheduler beating now may be a later one.
        parts = str(entry.get("runner") or "").split("/")
        pid = int(parts[2]) if len(parts) == 3 and parts[2].isdigit() else scheduler_pid
        out.append(_item("%s/%s" % (entry.get("table_name"), entry.get("script_name")),
                         WHERE_SCHEDULER, pid, started, elapsed,
                         state=run_state(entry.get("runner"))))
    return out


def _ingestions(watcher_pid):
    from ingestion.activity import registry

    return [_item(job.get("filename"), WHERE_WATCHER, watcher_pid, job.get("started_at"),
                  job.get("elapsed_seconds"), job.get("processed_rows"), job.get("total_rows"))
            for job in registry.snapshot() if ingestion_is_running(job)]


def running_now(db, now=None, sight=None, shape=None):
    """Everything running now, one shape per item, four sources. A source that cannot be
    read contributes nothing and says so in the log - it is not the others' problem."""
    import logging

    from chain import activity
    from utils import heartbeat

    now = now or datetime.now(timezone.utc)
    sight = sight or chain_sight()
    shape = shape or activity.view(sight["instants"], now=now.timestamp())
    beats = heartbeat.read_all()
    items = []
    for name, read in (("chain", lambda: _chain(sight, shape, now)),
                       ("retroactive", lambda: _retroactive(db, now)),
                       ("collectors", lambda: _collectors(
                           (beats.get("scheduler") or {}).get("pid"))),
                       ("ingestion", lambda: _ingestions(
                           (beats.get("watcher") or {}).get("pid")))):
        try:
            items.extend(read())
        except Exception as exc:                                 # noqa: BLE001
            logging.getLogger(__name__).warning("running_now: %s unreadable: %s", name, exc)
    return items
