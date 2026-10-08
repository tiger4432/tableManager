"""Pause and resume the chain - the emergency stop (소유자 「오늘 보면 이런 대형 사고에서 끌 방법이
없는 게 문제였으」, 총괄 3840af307 ㄱ).

One control file in the config directory, the `auto_update_control.json` shape: written
atomically, read on every call - so a pause survives a restart (a restart must not release
the brake) and a resume reaches a running worker without one.

Paused, the chain gives no slot a new line, a running group is rewound at its next stage
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


def cancel_running_group(db, ids=None):
    """Cancel the queries the running chain groups wait on - each group publishes its database
    pids in its process's beat (the chain's, a slot's - 총괄 19f6a9277): its session's, and its
    lock connection's while it waits for a table. Up to one beat old, so only a pid still a
    chain connection is touched - one the database handed to someone else never is.
    `ids` (events just set aside, 총괄 10-08): only a group holding one of them - its query is cut,
    the group rewinds and runs on without them in the same slot; a pause cuts every group.
    -> the pids cancelled, in order."""
    from sqlalchemy import text
    from chain import ingestion_worker, slots
    from database.database import connection_name
    from utils import heartbeat

    if db.get_bind().dialect.name != "postgresql":
        return []
    groups = [((beat.get("work") or {}).get("facts") or {}) for name, beat in heartbeat.read_all().items()
              if name == ingestion_worker.GROUP_BEAT or name.startswith(slots.BEAT_PREFIX)]
    if ids is not None:
        groups = [facts for facts in groups if _holds_one_of(db, facts, ids)]
    pids = sorted({facts[fact] for facts in groups for fact in ("db_pid", "lock_db_pid") if facts.get(fact)})
    if not pids:
        return []
    # 🔴 THE CANCEL INSIDE A CASE: PostgreSQL evaluates a WHERE's ANDs in no promised order, so
    #    `pg_cancel_backend` beside the checks could run before them - and it did, on this
    #    statement's own backend (a pid a beat named can since be the canceller's; the chain
    #    worker cancels too, on chain connections). A CASE runs its test first.
    cancelled = [row[0] for row in db.execute(text(
        "SELECT pid FROM pg_stat_activity WHERE CASE WHEN pid = ANY(:pids)"
        " AND application_name LIKE :chain AND pid <> pg_backend_pid()"
        " THEN pg_cancel_backend(pid) ELSE false END ORDER BY pid"),
        {"pids": pids, "chain": connection_name(ingestion_worker.logger.name) + "%"})]
    db.commit()
    return cancelled


def _holds_one_of(db, facts, ids):
    """Whether the group these work facts describe holds one of `ids`: an event of its line
    (`line_keys`) within its first and last event (`event_span`)."""
    import event_constants
    from chain.set_aside import CHUNK
    from database.models import DatabaseOutbox as outbox

    span, keys = facts.get("event_span"), facts.get("line_keys")
    if not span or not keys:
        return False
    inside = sorted(i for i in ids if span[0] <= i <= span[1])
    for start in range(0, len(inside), CHUNK):
        if db.query(outbox.id).filter(outbox.id.in_(inside[start:start + CHUNK]),
                                      event_constants.queue_line_key(outbox).in_(keys)).first() is not None:
            return True
    return False


def stop_line(db, key, by, must_be_run=False):
    """Stop one piece of work - one chain queue line (총괄 e2b5b6f35, 소유자 「x 버튼도 이미 끝난거라고
    안먹어 근데 왜 대기열에 있어?」). Whatever state its run is in, all three: ① a retroactive run
    is asked to stop ② the line's waiting chain events are set aside ③ the slot process running
    that line is stopped (`chain.slots.stop_slot`, 총괄 19f6a9277 - its pid is `slot_pid`).
    A replay run only stages events and is `done` long before the worker has eaten them, so a
    stop that ended at ① left the work running.
    The queue line's × and a run's Cancel both call this; `must_be_run` (the latter) refuses a
    key that is not a run before anything moves. -> `{"run"?, "skipped_events",
    "already_processed", "slot_pid", "kept"?, "already"?}` - `run` the run's state read back,
    `done` stays `done`; of the line's chain events waiting when the × read, `skipped_events`
    are set aside and `already_processed` ran, counted once the slot has ended."""
    from admin import retroactive
    from chain import set_aside, slots
    from database import models

    run = db.query(models.RetroactiveRun.run_id).filter(models.RetroactiveRun.run_id == key).first() is not None
    if must_be_run and not run:
        raise retroactive.RetroactiveRefused(f"unknown run_id '{key}'")
    answer = {"run": retroactive.request_cancel(db, key)["state"]} if run else {}
    done = set_aside.set_aside_line(db, key, by, run=run)
    slot_pid = slots.stop_slot(db, key)
    # 🔴 COUNTED AFTER THE SLOT HAS ENDED (총괄 54a53f894): a group that commits between the mark
    #    and the slot's end ran its rows - the count at mark time says 「set aside」 of rows that ran.
    aside, ran = set_aside.what_became_of(db, done["ids"])
    answer.update(skipped_events=aside, already_processed=ran, slot_pid=slot_pid)
    if done["kept"]:
        answer["kept"] = {"events": done["kept"],
                          "why": "not chain events - the worker that owns them empties them"}
    if not done["waited"] and not run:
        answer["already"] = set_aside.line_already(db, key)
    return answer


def pause_now(db, by, reason):
    """The one act a route and a script both take: record the pause, then cancel the running
    groups' queries - every slot's - so they stop within seconds rather than at their next stage
    boundary."""
    state = pause(by, reason)
    return dict(state, cancelled_pids=cancel_running_group(db))
