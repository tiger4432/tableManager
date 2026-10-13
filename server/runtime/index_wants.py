"""A slow grid read asks for an automatic index (총괄 ff7890892, 소유자 「쓰이는 칸만」).

The read only remembers and queues (`want`) - each (table, columns, why) once a process. After it has answered, one
thread here asks the database whether an index already serves it, whether the table already holds
`auto_index_per_table` automatic indexes, and whether the same ask is already waiting; if none, it writes one
INDEX_WANTED row - the outbox control event the chain worker's index line takes and builds
(`models.ensure_auto_indexes`). Nothing is written in the read's own path.
"""
import json
import logging
import queue
import threading
import uuid

logger = logging.getLogger("Server")

_ASKED = set()
_QUEUE = queue.Queue()
_THREAD = [None]
_LOCK = threading.Lock()


def want(table, columns, why, seconds, bind):
    """Queue the ask - the first time this process sees it."""
    key = (table, tuple(columns), why)
    with _LOCK:
        if key in _ASKED:
            return
        _ASKED.add(key)
        if _THREAD[0] is None:
            _THREAD[0] = threading.Thread(target=_asking, name="index-wants", daemon=True)
            _THREAD[0].start()
    _QUEUE.put((table, list(columns), why, seconds, bind))


def _asking():
    while True:
        table, columns, why, seconds, bind = _QUEUE.get()
        try:
            ask(table, columns, why, seconds, bind)
        except Exception as exc:                                    # noqa: BLE001 - the next ask goes on
            logger.error("[Indexes] an automatic index on %s (%s) was not asked: %s: %s",
                         table, ", ".join(columns), type(exc).__name__, exc)


def ask(table, columns, why, seconds, bind):
    """One INDEX_WANTED row, unless an index serves it, the table is at its cap, or the same ask waits. -> written."""
    from sqlalchemy.orm import Session

    import event_constants
    from database import models
    from parsers.directory_watcher import auto_index_per_table

    if bind.dialect.name != "postgresql":
        return False
    db = Session(bind=bind)
    try:
        held = models.catalogue_indexes(db.connection().connection.dbapi_connection, table)
        if any(models.auto_index_serves(index, columns, why) for index in held):
            return False
        if sum(1 for index in held if index["name"].startswith(models.AUTO_INDEX_PREFIX)) >= auto_index_per_table():
            return False
        waiting = (db.query(models.DatabaseOutbox.payload)
                   .filter(models.DatabaseOutbox.event_type == event_constants.EVENT_INDEX_WANTED,
                           models.DatabaseOutbox.table_name == table,
                           models.DatabaseOutbox.processed_chain.is_(False)).all())
        if any((json.loads(row.payload or "{}").get("columns"), json.loads(row.payload or "{}").get("why"))
               == (columns, why) for row in waiting):
            return False
        db.add(models.DatabaseOutbox(
            event_uuid=str(uuid.uuid4()), table_name=table, event_type=event_constants.EVENT_INDEX_WANTED,
            payload=json.dumps({"table": table, "columns": columns, "why": why, "seconds": round(seconds, 3)}),
            processed_chain=False))
        db.commit()
    finally:
        db.close()
    logger.info("[Indexes] asked for an automatic index on %s (%s) - %s, the read took %.1f s",
                table, ", ".join(columns), why, seconds)
    return True


def taken(db):
    """The INDEX_WANTED rows the chain worker has not taken: [(row, (table, columns, why))] - a row it cannot read is
    taken with nothing (its line says so)."""
    import event_constants
    from database import models

    rows = (db.query(models.DatabaseOutbox)
            .filter(models.DatabaseOutbox.event_type == event_constants.EVENT_INDEX_WANTED,
                    models.DatabaseOutbox.processed_chain.is_(False))
            .order_by(models.DatabaseOutbox.id.asc()).all())
    out = []
    for row in rows:
        try:
            asked = json.loads(row.payload or "{}")
            out.append((row, (str(asked["table"]), [str(c) for c in asked["columns"]], str(asked["why"]))))
        except (TypeError, ValueError, KeyError) as exc:
            logger.error("[Indexes] INDEX_WANTED %s is not read: %s: %s", row.id, type(exc).__name__, exc)
            out.append((row, None))
    return out
