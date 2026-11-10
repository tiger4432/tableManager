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
  storage   the tables' declared storage (`apply_table_storage`) - at the start, then each merge (a changed declaration)
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


#: PostgreSQL's table storage parameters (CREATE TABLE «Storage Parameters», PG 18; toast.* left out) - the one list a
#: declared storage is checked against (lead 11-09 ⓑ): name -> "number", "flag" or the words it takes. Ranges are
#: PostgreSQL's: an ALTER it refuses is said once ("failed") and the table tried again each merge.
STORAGE_PARAMETERS = dict(
    {name: "number" for name in (
        "fillfactor", "toast_tuple_target", "parallel_workers", "autovacuum_vacuum_threshold",
        "autovacuum_vacuum_max_threshold", "autovacuum_vacuum_scale_factor", "autovacuum_vacuum_insert_threshold",
        "autovacuum_vacuum_insert_scale_factor", "autovacuum_analyze_threshold", "autovacuum_analyze_scale_factor",
        "autovacuum_vacuum_cost_delay", "autovacuum_vacuum_cost_limit", "autovacuum_freeze_min_age",
        "autovacuum_freeze_max_age", "autovacuum_freeze_table_age", "autovacuum_multixact_freeze_min_age",
        "autovacuum_multixact_freeze_max_age", "autovacuum_multixact_freeze_table_age", "log_autovacuum_min_duration")},
    **{name: "flag" for name in ("autovacuum_enabled", "vacuum_truncate", "user_catalog_table")},
    vacuum_index_cleanup=("auto", "on", "off"))
_FLAG_WORDS = {"true": True, "on": True, "yes": True, "1": True, "false": False, "off": False, "no": False, "0": False}
#: The line of a table's comment that holds what the product set last (lead 11-09 ⓑ): a held value equal to it is the
#: product's and follows the declaration; one that is not was set by hand and is not overwritten. Other lines are kept.
STORAGE_RECORD = "assy storage set: "


def _spelled(kind, value):
    """A declared value as PostgreSQL writes it, or None when `kind` does not take it."""
    if kind == "flag":
        flag = value if isinstance(value, bool) else _FLAG_WORDS.get(value.lower()) if isinstance(value, str) else None
        return None if flag is None else "true" if flag else "false"
    if kind == "number":
        return None if isinstance(value, bool) or not isinstance(value, (int, float)) else str(value)
    return value.lower() if isinstance(value, str) and value.lower() in kind else None


def _same(kind, held, said):
    if kind == "flag":
        return _FLAG_WORDS.get(held.lower()) == _FLAG_WORDS.get(said.lower())
    if kind == "number":
        try:
            return float(held) == float(said)
        except ValueError:
            return False
    return held.lower() == said.lower()


def storage_refusal(table, entry):
    """Why one table's "storage" cannot be held - (path, sentence) - or None. Asked on a save of table_config.json and
    of every declared storage before it is set (a model's `info`, the ledger partitions')."""
    storage = (entry or {}).get("storage")
    if storage is None:
        return None
    path = "tables.%s.storage" % table
    if not isinstance(storage, dict):
        return path, 'storage must be an object of PostgreSQL storage parameters, e.g. {"fillfactor": 70}'
    if storage and (entry or {}).get("kind") == "view":
        return path, "%s is a view - a view has no storage" % table
    for name, value in storage.items():
        kind = STORAGE_PARAMETERS.get(name)
        if kind is None:
            return "%s.%s" % (path, name), "%s is not a PostgreSQL table storage parameter" % name
        if _spelled(kind, value) is None:
            return "%s.%s" % (path, name), "%s takes %s" % (
                name, {"number": "a number", "flag": "true or false"}.get(kind) or " or ".join(kind))
    return None


_STORAGE_HELD = ("SELECT c.relname, c.reloptions, obj_description(c.oid, 'pg_class') FROM pg_class c"
                 " JOIN pg_namespace n ON n.oid = c.relnamespace"
                 " WHERE n.nspname = current_schema() AND c.relkind = 'r' AND c.relname = ANY(:names)")
_PARTITIONS_HELD = ("SELECT c.oid::regclass::text, c.reloptions, obj_description(c.oid, 'pg_class') FROM pg_inherits i"
                    " JOIN pg_class c ON c.oid = i.inhrelid WHERE i.inhparent = to_regclass(:parent) ORDER BY 1")


def _storage_tables(db):
    """Every table with a declared storage, as it is now: [(table, how SQL names it, source, {parameter: (declared,
    held or None, held | owed | follows | differs)}, the product's record, why refused or None)] - source model (a
    model's `info["storage"]`), table (its table_config.json entry's) or ledger (each world's partitions,
    `ledger.schema.partition_storage`)."""
    import json

    from sqlalchemy import text

    from database import crud
    from database.database import Base
    from ledger import schema

    wanted = [(t.name, "model", t.info["storage"]) for t in Base.metadata.sorted_tables if t.info.get("storage")]
    wanted += [(name, "table", entry["storage"]) for name, entry in sorted((crud.TABLE_CONFIG or {}).items())
               if isinstance(entry, dict) and entry.get("storage") is not None]
    held = {row[0]: row[1:] for row in db.execute(text(_STORAGE_HELD), {"names": [name for name, *_ in wanted]})}
    found = [(name, '"%s"' % name.replace('"', '""'), source, storage) + tuple(held[name])
             for name, source, storage in wanted if name in held]          # not made in this schema yet: none
    partitions = schema.partition_storage(schema.autoanalyze_scale_factor())
    for world in schema.world_listing()["worlds"]:
        found += [(name, name, "ledger", partitions, options, comment) for name, options, comment in db.execute(
            text(_PARTITIONS_HELD), {"parent": schema.world_names(world).ledger})]
    db.commit()
    tables = []
    for name, sql, source, storage, options, comment in found:
        refused = storage_refusal(name, {"storage": storage})
        record = {}
        for line in (comment or "").splitlines():
            if line.startswith(STORAGE_RECORD):
                try:
                    record = json.loads(line[len(STORAGE_RECORD):]).get("set") or {}
                except (ValueError, AttributeError):
                    record = {}
        options = dict(option.split("=", 1) for option in options or ())
        states = {}
        for parameter, value in ({} if refused else storage).items():
            kind = STORAGE_PARAMETERS[parameter]
            said, now, last = _spelled(kind, value), options.get(parameter), record.get(parameter)
            states[parameter] = (said, now, "owed" if now is None else "held" if _same(kind, now, said)
                                 else "follows" if isinstance(last, str) and _same(kind, now, last) else "differs")
        tables.append((name, sql, source, states, record, comment, refused and refused[1]))
    return tables


def storage_states(db):
    """The declared storage beside the database, one row per table and parameter: table · source (model | table |
    ledger) · parameter · declared · held · state (held | owed | follows | differs | refused, with why). PostgreSQL
    only; elsewhere []. Read-only."""
    if db.get_bind().dialect.name != "postgresql":
        return []
    rows = []
    for name, _sql, source, states, _record, _comment, refused in _storage_tables(db):
        if refused:
            rows.append({"table": name, "source": source, "parameter": None, "declared": None, "held": None,
                         "state": "refused", "why": refused})
        rows += [{"table": name, "source": source, "parameter": parameter, "declared": said, "held": now,
                  "state": state} for parameter, (said, now, state) in sorted(states.items())]
    return rows


def apply_table_storage(db_session_factory, take=None, by="product"):
    """Each table's declared storage (`_storage_tables`; owner 10-20 cell_sources' fillfactor, 11-09 no end truncation)
    set where it is owed or the product's own value follows a changed declaration, by ALTER TABLE ... SET through
    `db_safety.short_ddl`, and the values the product holds recorded on the table's comment (`STORAGE_RECORD`) in the
    same transaction. A value set by hand is not overwritten (lead 11-09 ⓑ) - unless the table is `take`, the one
    table «Apply declared» names, which alone is done then. -> {table: "set" | "recorded" | "differs" | "refused" |
    "failed" | "busy"} for the tables not as declared. PostgreSQL only; elsewhere {}."""
    import datetime
    import json

    from sqlalchemy import text
    import db_safety

    db = db_session_factory()
    try:
        if db.get_bind().dialect.name != "postgresql":
            return {}
        done = {}
        for name, sql, _source, states, record, comment, refused in _storage_tables(db):
            if take is not None and name != take:
                continue
            if refused:
                done[name] = "refused"
                continue
            setting = {k: said for k, (said, _now, state) in states.items()
                       if state in ("owed", "follows") or (state == "differs" and name == take)}
            kept = dict(record, **{k: said for k, (said, _now, state) in states.items() if state == "held"}, **setting)
            if not setting and kept == record:
                if any(state == "differs" for _said, _now, state in states.values()):
                    done[name] = "differs"
                continue
            said = "\n".join([line for line in (comment or "").splitlines() if not line.startswith(STORAGE_RECORD)]
                             + [STORAGE_RECORD + json.dumps({"set": kept, "by": by, "at": datetime.datetime.now(
                                 datetime.timezone.utc).isoformat(timespec="seconds")}, sort_keys=True)])

            def work(conn, sql=sql, setting=setting, said=said):
                if setting:
                    conn.execute(text("ALTER TABLE %s SET (%s)" % (
                        sql, ", ".join("%s = %s" % each for each in sorted(setting.items())))))
                conn.execute(text("COMMENT ON TABLE %s IS :said" % sql), {"said": said})
            try:
                db_safety.short_ddl(db.get_bind(), name, work, "storage")
            except Exception as exc:                                # noqa: BLE001 - one table, the others go on
                done[name] = "busy" if hasattr(exc, "ddl_holders") else "failed"
                if done[name] == "failed" and (name, "failed") not in _SAID_STORAGE:
                    _SAID_STORAGE.add((name, "failed"))
                    logger.warning("[Indexes] %s storage not set: %s", name, told(exc).strip().splitlines()[0][:200])
                continue
            done[name] = "set" if setting else "recorded"
            if setting:
                logger.info("[Indexes] %s storage set as declared by %s: %s (held before: %s)", name, by,
                            ", ".join("%s = %s" % each for each in sorted(setting.items())),
                            ", ".join("%s %s" % (k, states[k][1] or "unset") for k in sorted(setting)))
        return done
    finally:
        db.close()


#: (table, how) said already - a table set by hand or refused is said once a process, not every merge.
_SAID_STORAGE = set()


def _storage_and_say(db_session_factory):
    for table, how in sorted(apply_table_storage(db_session_factory).items()):
        if how == "busy":
            logger.warning("[Indexes] %s storage not set - its lock was busy (the [DDL] line names who held it); "
                           "tried again at the next merge", table)
        elif how in ("differs", "refused") and (table, how) not in _SAID_STORAGE:
            _SAID_STORAGE.add((table, how))
            logger.warning("[Indexes] %s storage %s - %s", table, how, "set by hand, not overwritten; Apply declared "
                           "on the indexes screen sets it" if how == "differs" else "its declaration is refused")


def _each(works):
    """Run each (function, *args); a failure is a line, never the end of the line."""
    for work in works:
        try:
            work[0](*work[1:])
        except Exception as exc:                                    # noqa: BLE001
            logger.error("[Indexes] %s failed: %s", getattr(work[0], "__name__", work[0]), told(exc))


#: Why a table is analysed after the round that built an index on it (`_round`).
BUILT_WHY = "an index was just built on it and the planner had no statistics for it"


#: The line's works that left an index for later (`models.comes_again`), each as (where it came from, work, its cuts
#: {name: (cuts, next try)}) - asked again each poll until none does (총괄 11-06 ㄱ-1): one «deferred», wherever it
#: was met, and its cuts go with it (lead 11-09 ㄱ). An index request's (INDEX_WANTED) is its row, open until
#: settled (`_take_asks`, 총괄 11-07 ㄱ), its cuts on the row - not kept here.
_LEFT = []
#: Where the declared work's came from - a Reload runs it anew with the rules as they stand and its old ones go.
DECLARED = "declared"


def _keep(left, source, replacing=False):
    """`left` (a round's (work, cuts) that left one) kept for the polls under `source`, a work once whatever its
    source - a work kept already takes the newer cuts.
    `replacing`: that source's old ones taken out first - a work holds the rules it was made with, and a rule changed
    or gone must not be asked for again (총괄 11-06)."""
    if replacing:
        _LEFT[:] = [kept for kept in _LEFT if kept[0] != source]
    for work, cuts in left:
        if work in left_works():
            _LEFT[:] = [(kept[0], kept[1], cuts) if kept[1] == work else kept for kept in _LEFT]
        else:
            _LEFT.append((source, work, cuts))


def left_works():
    """The works kept for the next poll."""
    return [work for _source, work, _cuts in _LEFT]


def _cuts_of(kept):
    """{name: (cuts, next try)} the kept works hold, each's last part - the round after starts from them."""
    out = {}
    for each in kept:
        out.update(each[-1])
    return out


def _round(db_session_factory, works, words=None, cuts=None):
    """Index works (`_each`), then one ANALYZE of every table the round built an index on (`models.built_tables` -
    the one builder notes it, 총괄 11-05 ㄴ): without statistics for a new index the planner guesses (owner 11-04 ·
    11-05). Its failure is its own sentence - the indexes stand (C 11-05 O4). -> [(work, its cuts)] of the works that
    left one for later; `words` gets each name's word (`models.words_in_round`); the round starts from `cuts`."""
    from chain import ingestion_worker as worker
    from database import models

    left = []
    with models.built_tables(cuts) as built:
        for work in works:
            before = len(models.left_in_round())
            _each([work])
            names = models.left_in_round()[before:]
            if names:
                cut = models.cuts_in_round()
                left.append((work, {name: cut[name] for name in names if name in cut}))
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
    _keep([each for each in left if each[0] not in declared], "start")
    _keep([each for each in left if each[0] in declared], DECLARED)


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
    import json

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
        # an open ask's cuts, kept on its row (lead 11-08 ④a)
        cuts = {index_wants.index_name(*each): tuple(json.loads(row.payload or "{}")["cut"])
                for row, each in asks if each is not None and "cut" in json.loads(row.payload or "{}")}
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
    carried = _cuts_of(kept for kept in _LEFT if kept[0] == DECLARED)  # a Reload's work keeps the old one's cuts
    if fresh is not None:
        _keep((), DECLARED, replacing=True)                       # the old rules' are not asked for again
    if _LEFT:
        left = _round(db_session_factory, left_works(), cuts=_cuts_of(_LEFT))
        _LEFT[:] = [(source, work, cuts) for source, work, _old in _LEFT for done, cuts in left if done == work]
    if fresh is not None:
        _keep(_round(db_session_factory, fresh, cuts=carried), DECLARED)
    if asks:
        _take_asks(db_session_factory, asks, cuts)
    return mark


def _ask_works(db_session_factory, asked):
    """The works that build `asked` [(table, columns, why)]: the keys' unique indexes, the automatic ones."""
    from chain import ingestion_worker as worker
    from database import models

    keys = [table for table, _columns, why in asked if why == models.KEY_UNIQUE]
    auto = [each for each in asked if each[2] != models.KEY_UNIQUE]
    return (([(worker._ensure_business_key_unique_indexes_sync, db_session_factory, keys)] if keys else [])
            + ([(models.ensure_auto_indexes_sync, db_session_factory, auto, logger.warning, False)] if auto else []))


def _take_asks(db_session_factory, asks, cuts=None):
    """The open index requests [(row id, (table, columns, why))], oldest first: the oldest built with the whole wait
    before it, the others only if nothing holds them now (`models.waits_before(0)` - a poll waits for one, 총괄 11-07
    ⑴). Each row closed by its index's word - built or there: SUCCESS; ruled out: FAILED (its sentence said where it
    was met); put off: left open, taken again next poll (총괄 11-07 ㄱ)."""
    import json

    import event_constants
    from database import models
    from runtime import index_wants

    names = {row_id: index_wants.index_name(*each) for row_id, each in asks}
    cuts, before = dict(cuts or {}), dict(cuts or {})
    words = {}
    cuts.update(_cuts_of(_round(db_session_factory, _ask_works(db_session_factory, [asks[0][1]]), words, cuts)))
    if asks[1:]:
        with models.waits_before(0):
            cuts.update(_cuts_of(_round(db_session_factory, _ask_works(db_session_factory,
                                                                       [each for _id, each in asks[1:]]),
                                        words, cuts)))
    closed = {}
    for row_id, (table, columns, why) in asks:
        word = words.get(index_wants.index_name(table, columns, why))
        if word in (models.INDEX_BUILT, models.INDEX_PRESENT):
            closed[row_id] = "SUCCESS"
        elif word in (models.INDEX_FAILED, models.INDEX_REFUSED):
            closed[row_id] = "FAILED"
            logger.warning("[Indexes] the request for an index on %s (%s, %s) is closed: %s - see its line above",
                           table, ", ".join(columns), why, word)
    keyed = [table for row_id, (table, _columns, why) in asks
             if why == models.KEY_UNIQUE and closed.get(row_id) == "SUCCESS"]
    if keyed:                                    # a table's key index stands: its lines can be built (lead 11-11 ㄱ)
        from database import lines

        db = db_session_factory()
        try:
            lines.ensure_declared(db.get_bind(), keyed)
        finally:
            db.close()
    if not closed and cuts == before:
        return
    db = db_session_factory()
    try:
        for row in db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.id.in_(sorted(names))):
            if row.id in closed:
                event_constants.mark_processed(row, closed[row.id])
            elif names[row.id] in cuts:                  # an open ask keeps its cuts on its row (lead 11-08 ④a)
                row.payload = json.dumps(dict(json.loads(row.payload or "{}"), cut=list(cuts[names[row.id]])))
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
    _each([(_storage_and_say, db_session_factory)])
    cleaned, swept = time.monotonic(), None
    while not stop.wait(POLL_SECONDS):
        try:
            mark = poll_once(db_session_factory, mark)
        except Exception as exc:                                    # noqa: BLE001
            logger.error("[Indexes] poll failed: %s", told(exc))
        if time.monotonic() - cleaned >= GIN_CLEAN_SECONDS:
            cleaned = time.monotonic()
            _each([(_clean_and_say, db_session_factory)])
            _each([(_storage_and_say, db_session_factory)])
            if swept is None or time.monotonic() - swept >= IMAGE_SWEEP_SECONDS:
                swept = time.monotonic()
                _each([(sweep_images, db_session_factory)])


def start(db_session_factory):
    """The line on a daemon thread. -> the thread."""
    thread = threading.Thread(target=run, args=(db_session_factory,), name="index-statistics-line", daemon=True)
    thread.start()
    return thread
