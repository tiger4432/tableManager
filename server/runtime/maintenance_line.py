"""The index and statistics line - in the scheduler's process, never the chain worker's (소유자 10-15).

🔴 WHY HERE. A large backfill left stale statistics and long transactions; the chain worker's start
awaited ANALYZE and the index builds, both waiting on those, so it did not start, and its loop took
INDEX_WANTED beside the outbox. The chain worker now starts at once and builds nothing; this line
does all of it beside the scheduler's 5 s loop, on a thread of its own:
  start     the startup indexes, then ANALYZE of the stale tables, then the declared keys', the
            models' and the automatic indexes
  reload    any SYSTEM_RELOAD past its mark, or a changed chain_rules.json (`declarations_changed`) - the
            chain rules read again, the declared work again
  ask       INDEX_WANTED rows (`index_wants.taken`) - the automatic index each names
  merge     every GIN_CLEAN_SECONDS the GIN indexes' pending lists (`clean_gin_pending`) - not a file's flush
  storage   the tables' declared storage (`apply_table_storage`) - at the start, then each merge until it holds
  pictures  every IMAGE_SWEEP_SECONDS the received pictures no image cell holds (`image_sources.sweep`, owner 11-05)
"""
import logging
import threading
import time
from error_said import told

logger = logging.getLogger("Server")

#: How often the line reads the outbox for reloads and index asks.
POLL_SECONDS = 5.0
#: How often it merges the GIN indexes' pending lists (owner 10-16: a file's flush of 1,000 rows took 20 s). A list past
#: gin_pending_list_limit is merged by the session that writes the row - a file's flush; merged here first, it is not.
GIN_CLEAN_SECONDS = 120.0

#: Plain GIN indexes only (relkind 'i'): a partitioned table's index (relkind 'I', the ledger's) is refused by
#: gin_clean_pending_list - 「is not a GIN index」 every merge (owner 10-20); its partitions' indexes are listed themselves.
_GIN_INDEXES = ("SELECT c.oid, c.relname FROM pg_index x JOIN pg_class c ON c.oid = x.indexrelid"
                " JOIN pg_am am ON am.oid = c.relam JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE am.amname = 'gin' AND c.relkind = 'i' AND n.nspname = current_schema() ORDER BY c.relname")


_SAID_GIN_FAILURES = set()


def clean_gin_pending(db_session_factory):
    """Merge each GIN index's pending list in this schema, one at a time, each its own transaction. -> [(index, pages
    merged)] for those that had any. PostgreSQL only; elsewhere []."""
    from sqlalchemy import text

    db = db_session_factory()
    try:
        if db.get_bind().dialect.name != "postgresql":
            return []
        indexes = [(row[0], row[1]) for row in db.execute(text(_GIN_INDEXES))]
        db.commit()
        merged = []
        for oid, name in indexes:
            # by oid, not by name - a name resolves through search_path and can reach another schema's index
            try:
                pages = db.execute(text("SELECT gin_clean_pending_list(CAST(CAST(:oid AS oid) AS regclass))"),
                                   {"oid": int(oid)}).scalar()
                db.commit()
            except Exception as exc:                                # noqa: BLE001 - one index, the others go on
                db.rollback()
                if name not in _SAID_GIN_FAILURES:                  # said once a process, not every merge
                    _SAID_GIN_FAILURES.add(name)
                    logger.warning("[Indexes] GIN pending list of %s not merged: %s", name,
                                   told(exc).strip().split("\n")[0][:200])
                continue
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


#: How often the received pictures are swept (`image_sources.sweep`) - the first at the line's first merge beat.
IMAGE_SWEEP_SECONDS = 24 * 3600.0


def sweep_images(db_session_factory):
    import image_sources

    db = db_session_factory()
    try:
        return image_sources.sweep(db)
    finally:
        db.close()


#: How long ALTER TABLE ... SET waits for its lock. Under deadlock_timeout (1 s by default): a waiter past it makes
#: PostgreSQL cancel a running autovacuum of that table, and the one cleaning cell_sources may have run for hours.
STORAGE_LOCK_TIMEOUT = "500ms"


def apply_table_storage(db_session_factory):
    """Each model table's declared storage (`info["storage"]`, e.g. cell_sources' fillfactor - owner 10-20: an updated
    layer's old version is pruned on its page only where the page has room) that the table does not hold yet, set by
    ALTER TABLE ... SET. A table whose lock is not had within STORAGE_LOCK_TIMEOUT is left for the next try.
    -> {table: "set" | "busy"}. PostgreSQL only; elsewhere {}."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    from database.database import Base

    db = db_session_factory()
    try:
        if db.get_bind().dialect.name != "postgresql":
            return {}
        done = {}
        for table in Base.metadata.sorted_tables:
            wanted = {str(k): str(v) for k, v in (table.info.get("storage") or {}).items()}
            if not wanted:
                continue
            held = db.execute(text("SELECT c.reloptions FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                                   " WHERE c.relname = :t AND n.nspname = current_schema() AND c.relkind = 'r'"),
                              {"t": table.name}).first()
            db.commit()
            if held is None:                                        # no such table in this schema
                continue
            held = dict(option.split("=", 1) for option in (held[0] or []))
            if all(held.get(k) == v for k, v in wanted.items()):
                continue
            try:
                db.execute(text("SET LOCAL lock_timeout = '%s'" % STORAGE_LOCK_TIMEOUT))
                db.execute(text('ALTER TABLE "%s" SET (%s)' % (
                    table.name, ", ".join("%s = %s" % (k, v) for k, v in sorted(wanted.items())))))
                db.commit()
                done[table.name] = "set"
            except OperationalError:
                db.rollback()
                done[table.name] = "busy"
        return done
    finally:
        db.close()


def _storage_and_say(db_session_factory):
    """-> True once every declared storage holds."""
    done = apply_table_storage(db_session_factory)
    for table, how in sorted(done.items()):
        if how == "set":
            logger.info("[Indexes] %s storage set as declared", table)
        else:
            logger.warning("[Indexes] %s storage not set - its lock was busy past %s (a running vacuum keeps it); "
                           "tried again at the next merge", table, STORAGE_LOCK_TIMEOUT)
    return "busy" not in done.values()


def _each(works):
    """Run each (function, *args); a failure is a line, never the end of the line."""
    for work in works:
        try:
            work[0](*work[1:])
        except Exception as exc:                                    # noqa: BLE001
            logger.error("[Indexes] %s failed: %s", getattr(work[0], "__name__", work[0]), told(exc))


#: Why a table is analysed after the round that built an index on it (`_round`).
BUILT_WHY = "an index was just built on it and the planner had no statistics for it"


#: The line's works that left an index for later (`models.comes_again`), each as (where it came from, work) - asked
#: again each poll until none does (총괄 11-06 ㄱ-1): one «deferred», wherever it was met. An index request's
#: (INDEX_WANTED) is its row, open until settled (`_take_asks`, 총괄 11-07 ㄱ), not kept here.
_LEFT = []
#: Where the declared work's came from - a Reload runs it anew with the rules as they stand and its old ones go.
DECLARED = "declared"


def _keep(left, source, replacing=False):
    """`left` (a round's works that left one) kept for the polls under `source`, a work once whatever its source.
    `replacing`: that source's old ones taken out first - a work holds the rules it was made with, and a rule changed
    or gone must not be asked for again (총괄 11-06)."""
    if replacing:
        _LEFT[:] = [kept for kept in _LEFT if kept[0] != source]
    for work in left:
        if work not in left_works():
            _LEFT.append((source, work))


def left_works():
    """The works kept for the next poll."""
    return [work for _source, work in _LEFT]


def _round(db_session_factory, works, words=None):
    """Index works (`_each`), then one ANALYZE of every table the round built an index on (`models.built_tables` -
    the one builder notes it, 총괄 11-05 ㄴ): without statistics for a new index the planner guesses (owner 11-04 ·
    11-05). Its failure is its own sentence - the indexes stand (C 11-05 O4). -> the works that left one for later;
    `words` gets each name's word (`models.words_in_round`)."""
    from chain import ingestion_worker as worker
    from database import models

    left = []
    with models.built_tables() as built:
        for work in works:
            before = models.left_in_round()
            _each([work])
            if models.left_in_round() > before:
                left.append(work)
        if words is not None:
            words.update(models.words_in_round())
    if built:
        try:
            worker._analyze_stale_tables_sync(db_session_factory, built=set(built), built_why=BUILT_WHY)
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("[Indexes] built on %s; the ANALYZE after it did not run (this process goes on): %s: %s",
                           ", ".join(sorted(built)), type(exc).__name__, told(exc))
    return left


def _start(db_session_factory):
    """The start's works; those that left an index for later stay in `_LEFT` for the polls - its declared ones as the
    declared work's (a Reload replaces them)."""
    declared = _declared_work(db_session_factory)
    left = _round(db_session_factory, _start_work(db_session_factory))
    _LEFT[:] = []
    _keep([work for work in left if work not in declared], "start")
    _keep([work for work in left if work in declared], DECLARED)


def _declared_work(db_session_factory):
    """The declared keys', the alignment decision keys', the map keys', the models' (the ledger's are the ledger
    process's) and every decide rule's key - the only builder of each (소유자 10-15: the chain worker, its slots and the
    watcher build none)."""
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
            (worker._ensure_human_claims_index_sync, db_session_factory),
            (worker._analyze_stale_tables_sync, db_session_factory)] + _declared_work(db_session_factory)


#: The chain rules file changed (`config_watcher`'s chain_rules row) - the next poll does the declared work again.
_DECLARATIONS_CHANGED = threading.Event()


def declarations_changed():
    """The chain rules changed in this process: the line's next poll builds the declared indexes again."""
    _DECLARATIONS_CHANGED.set()


def poll_once(db_session_factory, mark):
    """One read: the Reload button's rows past `mark`, or a changed rules file (`declarations_changed`) -> the
    declared work again; INDEX_WANTED -> its automatic index. -> the new mark."""
    import event_constants
    from runtime import index_wants, system_reload

    db = db_session_factory()
    try:
        # what the rows say is read before the commit: after it and the close they are expired and detached, and
        # reading one raised every poll - the mark never moved and the asks taken were never built (10-16)
        reloads = system_reload.reloads_after(db, mark)
        latest = reloads[-1].id if reloads else mark
        # a join-keys row is this line's own word to the writers - not a reason to do the declared work again
        declared = system_reload.reload_for(system_reload.INDEX_LINE, reloads)
        asks = index_wants.taken(db)
        for row, each in asks:
            if each is None:                                       # unreadable - nothing to build (its line said it)
                event_constants.mark_processed(row, "FAILED")
        asks = [(row.id, each) for row, each in asks if each is not None]
        db.commit()
    finally:
        db.close()
    if _DECLARATIONS_CHANGED.is_set():
        _DECLARATIONS_CHANGED.clear()
        declared = True
    if latest != mark:
        mark = latest
    fresh = _declared_work(db_session_factory) if declared else None
    if fresh is not None:
        _keep((), DECLARED, replacing=True)                       # the old rules' are not asked for again
    if _LEFT:
        left = _round(db_session_factory, left_works())
        _LEFT[:] = [kept for kept in _LEFT if kept[1] in left]
    if fresh is not None:
        _keep(_round(db_session_factory, fresh), DECLARED)
    if asks:
        _take_asks(db_session_factory, asks)
    return mark


def _ask_works(db_session_factory, asked):
    """The works that build `asked` [(table, columns, why)]: the keys' unique indexes, the automatic ones."""
    from chain import ingestion_worker as worker
    from database import models

    keys = [table for table, _columns, why in asked if why == models.KEY_UNIQUE]
    auto = [each for each in asked if each[2] != models.KEY_UNIQUE]
    return (([(worker._ensure_business_key_unique_indexes_sync, db_session_factory, keys)] if keys else [])
            + ([(models.ensure_auto_indexes_sync, db_session_factory, auto, logger.warning, False)] if auto else []))


def _take_asks(db_session_factory, asks):
    """The open index requests [(row id, (table, columns, why))], oldest first: the oldest built with the whole wait
    before it, the others only if nothing holds them now (`models.waits_before(0)` - a poll waits for one, 총괄 11-07
    ⑴). Each row closed by its index's word - built or there: SUCCESS; ruled out: FAILED (its sentence said where it
    was met); put off: left open, taken again next poll (총괄 11-07 ㄱ)."""
    import event_constants
    from database import models
    from runtime import index_wants

    words = {}
    _round(db_session_factory, _ask_works(db_session_factory, [asks[0][1]]), words)
    if asks[1:]:
        with models.waits_before(0):
            _round(db_session_factory, _ask_works(db_session_factory, [each for _id, each in asks[1:]]), words)
    closed = {}
    for row_id, (table, columns, why) in asks:
        word = words.get(index_wants.index_name(table, columns, why))
        if word in (models.INDEX_BUILT, models.INDEX_PRESENT):
            closed[row_id] = "SUCCESS"
        elif word in (models.INDEX_FAILED, models.INDEX_REFUSED):
            closed[row_id] = "FAILED"
            logger.warning("[Indexes] the request for an index on %s (%s, %s) is closed: %s - see its line above",
                           table, ", ".join(columns), why, word)
    if not closed:
        return
    db = db_session_factory()
    try:
        for row in db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.id.in_(sorted(closed))):
            event_constants.mark_processed(row, closed[row.id])
        db.commit()
    finally:
        db.close()


def run(db_session_factory, stop=None):
    """The line itself: the start's work, then a poll every POLL_SECONDS until `stop` is set."""
    stop = stop or threading.Event()
    db = db_session_factory()
    try:
        from runtime import system_reload

        mark = system_reload.latest_reload_id(db)
    finally:
        db.close()
    started = time.time()
    _start(db_session_factory)
    logger.info("[Indexes] start work done in %.1f s", time.time() - started)
    stored = [False]
    _each([(lambda: stored.__setitem__(0, _storage_and_say(db_session_factory)),)])
    cleaned, swept = time.monotonic(), None
    while not stop.wait(POLL_SECONDS):
        try:
            mark = poll_once(db_session_factory, mark)
        except Exception as exc:                                    # noqa: BLE001
            logger.error("[Indexes] poll failed: %s", told(exc))
        if time.monotonic() - cleaned >= GIN_CLEAN_SECONDS:
            cleaned = time.monotonic()
            _each([(_clean_and_say, db_session_factory)])
            if not stored[0]:
                _each([(lambda: stored.__setitem__(0, _storage_and_say(db_session_factory)),)])
            if swept is None or time.monotonic() - swept >= IMAGE_SWEEP_SECONDS:
                swept = time.monotonic()
                _each([(sweep_images, db_session_factory)])


def start(db_session_factory):
    """The line on a daemon thread. -> the thread."""
    thread = threading.Thread(target=run, args=(db_session_factory,), name="index-statistics-line", daemon=True)
    thread.start()
    return thread
