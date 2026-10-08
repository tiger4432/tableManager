"""Pause and resume the chain - the emergency stop (소유자 「오늘 보면 이런 대형 사고에서 끌 방법이
없는 게 문제였으」, 총괄 3840af307 ㄱ).

One control file in the config directory, the `auto_update_control.json` shape: written
atomically, read on every call - so a pause survives a restart (a restart must not release
the brake) and a resume reaches a running worker without one.

Paused, the chain loop takes no new group, a running group is rewound at its next stage
boundary (`alignment_batch_counts.interrupt_at_stages`, on the group's own thread) and not
charged as a failure, and the query it is running is cancelled by the pause itself. Its
events stay queued: nothing is lost, and Resume runs them.
"""
import json
import os
import time

try:
    import paths
except ImportError:  # imported without server/ on sys.path
    from .. import paths  # type: ignore

CONTROL_FILENAME = "chain_control.json"


class ChainPaused(Exception):
    """Raised at a stage boundary of a running group while the chain is paused."""


def control_path():
    return paths.config_path(CONTROL_FILENAME)


def paused():
    """`{"by", "at", "reason"}` while the chain is paused, else `None`. Read every time."""
    try:
        with open(control_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    state = data.get("paused") if isinstance(data, dict) else None
    return state if isinstance(state, dict) else None


def _write(data):
    path = control_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def pause(by, reason):
    state = {"by": str(by or "operator"), "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "reason": str(reason or "")}
    _write({"paused": state})
    return state


def resume():
    _write({"paused": None})


def raise_if_paused():
    """The stage-boundary check a running group makes."""
    if paused() is not None:
        raise ChainPaused("the chain is paused")


def cancel_running_group(db, line_key=None):
    """Cancel the query the running chain group is waiting on, if there is one - by the pid its
    beat published (up to one beat old) and only while that pid is still a chain connection,
    so a pid the database has handed to someone else is never touched. With `line_key` (a ×
    on one queue line, 소유자 10-08), only when the running group is that line. -> the pid, or None."""
    from sqlalchemy import text
    from chain import ingestion_worker
    from database.database import connection_name
    from utils import heartbeat

    work = (heartbeat.read_all().get("chain") or {}).get("work") or {}
    facts = work.get("facts") or {}
    pid = facts.get("db_pid")
    if line_key is not None and line_key not in (facts.get("line_keys") or ()):
        return None
    if pid is None or db.get_bind().dialect.name != "postgresql":
        return None
    cancelled = db.execute(text(
        "SELECT pg_cancel_backend(pid) FROM pg_stat_activity"
        " WHERE pid = :pid AND application_name = :name"),
        {"pid": pid, "name": connection_name(ingestion_worker.logger.name)}).scalar()
    db.commit()
    return pid if cancelled else None


def stop_line(db, key, by, must_be_run=False):
    """Stop one piece of work - one chain queue line (총괄 e2b5b6f35, 소유자 「x 버튼도 이미 끝난거라고
    안먹어 근데 왜 대기열에 있어?」). Whatever state its run is in, all three: ① a retroactive run
    is asked to stop ② the line's waiting chain events are set aside ③ the running group's query
    is cancelled when it is that line. A replay run only stages events and is `done` long before
    the worker has eaten them, so a stop that ended at ① left the work running.
    The queue line's × and a run's Cancel both call this; `must_be_run` (the latter) refuses a
    key that is not a run before anything moves. -> `{"run"?, "skipped_events", "cancelled_pid",
    "kept"?, "already"?}` - `run` the run's state read back, `done` stays `done`."""
    from admin import retroactive
    from chain import set_aside
    from database import models

    run = db.query(models.RetroactiveRun.run_id).filter(models.RetroactiveRun.run_id == key).first() is not None
    if must_be_run and not run:
        raise retroactive.RetroactiveRefused(f"unknown run_id '{key}'")
    answer = {"run": retroactive.request_cancel(db, key)["state"]} if run else {}
    done = set_aside.set_aside_line(db, key, by, run=run)
    answer.update(skipped_events=done["marked"], cancelled_pid=cancel_running_group(db, line_key=key))
    if done["kept"]:
        answer["kept"] = {"events": done["kept"],
                          "why": "not chain events - the worker that owns them empties them"}
    if not done["waited"] and not run:
        answer["already"] = set_aside.line_already(db, key)
    return answer


def pause_now(db, by, reason):
    """The one act a route and a script both take: record the pause, then cancel the running
    group's query so it stops within seconds rather than at its next stage boundary."""
    state = pause(by, reason)
    return dict(state, cancelled_pid=cancel_running_group(db))
