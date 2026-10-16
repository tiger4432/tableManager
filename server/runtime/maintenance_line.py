"""The index and statistics line - in the scheduler's process, never the chain worker's (소유자 10-15).

🔴 WHY HERE. A large backfill left stale statistics and long transactions; the chain worker's start
awaited ANALYZE and the index builds, both waiting on those, so it did not start, and its loop took
INDEX_WANTED beside the outbox. The chain worker now starts at once and builds nothing; this line
does all of it beside the scheduler's 5 s loop, on a thread of its own:
  start     the startup indexes, then ANALYZE of the stale tables, then the declared keys', the
            models' and the automatic indexes
  reload    any SYSTEM_RELOAD past its mark - the chain rules read again, the declared work again
  ask       INDEX_WANTED rows (`index_wants.taken`) - the automatic index each names
  merge     every GIN_CLEAN_SECONDS the GIN indexes' pending lists (`clean_gin_pending`) - not a file's flush
"""
import logging
import threading
import time

logger = logging.getLogger("Server")

#: How often the line reads the outbox for reloads and index asks.
POLL_SECONDS = 5.0
#: How often it merges the GIN indexes' pending lists (owner 10-16: a file's flush of 1,000 rows took 20 s). A list past
#: gin_pending_list_limit is merged by the session that writes the row - a file's flush; merged here first, it is not.
GIN_CLEAN_SECONDS = 120.0

_GIN_INDEXES = ("SELECT c.relname FROM pg_index x JOIN pg_class c ON c.oid = x.indexrelid JOIN pg_am am ON am.oid = c.relam"
                " JOIN pg_namespace n ON n.oid = c.relnamespace WHERE am.amname = 'gin' AND n.nspname = current_schema()"
                " ORDER BY c.relname")


def clean_gin_pending(db_session_factory):
    """Merge each GIN index's pending list in this schema, one at a time, each its own transaction. -> [(index, pages
    merged)] for those that had any. PostgreSQL only; elsewhere []."""
    from sqlalchemy import text

    db = db_session_factory()
    try:
        if db.get_bind().dialect.name != "postgresql":
            return []
        names = [row[0] for row in db.execute(text(_GIN_INDEXES))]
        db.commit()
        merged = []
        for name in names:
            pages = db.execute(text("SELECT gin_clean_pending_list(CAST(:name AS regclass))"),
                               {"name": '"%s"' % name.replace('"', '""')}).scalar()
            db.commit()
            if pages:
                merged.append((name, int(pages)))
        return merged
    finally:
        db.close()


def _clean_and_say(db_session_factory):
    started = time.time()
    merged = clean_gin_pending(db_session_factory)
    if merged:
        logger.info("[Indexes] merged GIN pending lists in %.1f s: %s", time.time() - started,
                    ", ".join("%s %d page(s)" % each for each in merged))


def _each(works):
    """Run each (function, *args); a failure is a line, never the end of the line."""
    for work in works:
        try:
            work[0](*work[1:])
        except Exception as exc:                                    # noqa: BLE001
            logger.error("[Indexes] %s failed: %s", getattr(work[0], "__name__", work[0]), exc)


def _declared_work(db_session_factory):
    """The declared keys', the models' (the ledger's are the ledger process's) and every decide rule's key."""
    from chain import ingestion_worker as worker
    from database import models

    rules = worker.load_chain_rules()
    return [(worker._ensure_declared_indexes_sync, rules, db_session_factory),
            (models.ensure_model_indexes_sync, db_session_factory,
             tuple(source for source in models.INDEX_SOURCES if source != "ledger"), logger.warning),
            (models.ensure_auto_indexes_sync, db_session_factory, None, logger.warning, True)]


def _start_work(db_session_factory):
    from chain import ingestion_worker as worker

    return [(worker._ensure_business_key_unique_indexes_sync, db_session_factory),
            (worker._ensure_alignment_decision_key_indexes_sync, db_session_factory),
            (worker._ensure_human_claims_index_sync, db_session_factory),
            (worker._ensure_dynamic_table_indexes_sync, db_session_factory),
            (worker._analyze_stale_tables_sync, db_session_factory)] + _declared_work(db_session_factory)


def _latest_reload_id(db):
    from database.models import DatabaseOutbox

    row = (db.query(DatabaseOutbox.id).filter(DatabaseOutbox.event_type == "SYSTEM_RELOAD")
           .order_by(DatabaseOutbox.id.desc()).first())
    return row[0] if row else 0


def poll_once(db_session_factory, mark):
    """One read: reloads past `mark` -> the declared work again; INDEX_WANTED -> its automatic index. -> the new mark."""
    import event_constants
    from database import models
    from runtime import index_wants, system_reload

    db = db_session_factory()
    try:
        # what the rows say is read before the commit: after it and the close they are expired and detached, and
        # reading one raised every poll - the mark never moved and the asks taken were never built (10-16)
        reloads = system_reload.reloads_after(db, mark)
        latest = reloads[-1].id if reloads else mark
        asks = index_wants.taken(db)
        asked = [each for _row, each in asks if each is not None]
        for row, _each_ask in asks:
            event_constants.mark_processed(row, "SUCCESS")
        db.commit()
    finally:
        db.close()
    if latest != mark:
        mark = latest
        _each(_declared_work(db_session_factory))
    if asked:
        _each([(models.ensure_auto_indexes_sync, db_session_factory, asked, logger.warning, False)])
    return mark


def run(db_session_factory, stop=None):
    """The line itself: the start's work, then a poll every POLL_SECONDS until `stop` is set."""
    stop = stop or threading.Event()
    db = db_session_factory()
    try:
        mark = _latest_reload_id(db)
    finally:
        db.close()
    started = time.time()
    _each(_start_work(db_session_factory))
    logger.info("[Indexes] start work done in %.1f s", time.time() - started)
    cleaned = time.monotonic()
    while not stop.wait(POLL_SECONDS):
        try:
            mark = poll_once(db_session_factory, mark)
        except Exception as exc:                                    # noqa: BLE001
            logger.error("[Indexes] poll failed: %s", exc)
        if time.monotonic() - cleaned >= GIN_CLEAN_SECONDS:
            cleaned = time.monotonic()
            _each([(_clean_and_say, db_session_factory)])


def start(db_session_factory):
    """The line on a daemon thread. -> the thread."""
    thread = threading.Thread(target=run, args=(db_session_factory,), name="index-statistics-line", daemon=True)
    thread.start()
    return thread
