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


def cancel_running_group(db):
    """Cancel the query the running chain group is waiting on, if there is one - by the pid its
    beat published (up to one beat old) and only while that pid is still a chain connection,
    so a pid the database has handed to someone else is never touched. -> the pid, or None."""
    from sqlalchemy import text
    from chain import ingestion_worker
    from database.database import connection_name
    from utils import heartbeat

    work = (heartbeat.read_all().get("chain") or {}).get("work") or {}
    pid = (work.get("facts") or {}).get("db_pid")
    if pid is None or db.get_bind().dialect.name != "postgresql":
        return None
    cancelled = db.execute(text(
        "SELECT pg_cancel_backend(pid) FROM pg_stat_activity"
        " WHERE pid = :pid AND application_name = :name"),
        {"pid": pid, "name": connection_name(ingestion_worker.logger.name)}).scalar()
    db.commit()
    return pid if cancelled else None


def pause_now(db, by, reason):
    """The one act a route and a script both take: record the pause, then cancel the running
    group's query so it stops within seconds rather than at its next stage boundary."""
    state = pause(by, reason)
    return dict(state, cancelled_pid=cancel_running_group(db))
