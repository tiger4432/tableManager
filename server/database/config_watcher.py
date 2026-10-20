import os
import threading
import time
import logging
from error_said import told

logger = logging.getLogger("Watcher.ConfigWatcher")

CONFIG_FILENAME = "table_config.json"

# 마지막 이벤트 이후 이만큼 조용하면 발화하는 **트레일링 엣지** 디바운스 창(초).
# 창 안에 새 이벤트가 들어오면 타이머를 다시 무장한다(재무장).
DEBOUNCE_SEC = 1.0

#: 🔴 [e6a0bdbbd, 소유자 10-21 ㄱ 「체인 등등도 저장하면 즉시 다시 읽게 해 테이블 선언처럼」 · 「맵퍼 폴더도 감시해」]
#:    ONE MECHANISM FOR 「A DECLARATION CHANGED - READ IT AGAIN」, IN EVERY PROCESS THAT READS ONE. This watcher
#:    sees the config folder and the mappers folder - a save and a hand edit alike - and `changed` does the one thing:
#:      held   a value read from a file (`held`) names that file; it is read again on its next use. A file that no
#:             longer reads keeps the value read before, and the file and why are said - a first read that fails
#:             raises as it always did
#:      ROWS   what else a process forgets when that file changes (`ROWS` below, the one table)
#:    A `boundary` row waits, in a chain process (`start_config_watcher(boundary=True)`), for the loop's next group
#:    boundary (`apply_pending`) - a group running reads one set of rules and one set of mappers. A cell given the
#:    engine runs its writing half only in the process that was given it (the API).
#:    What a name is: `name_of`. The Reload button is `reload_everything` - every row at once.
_GEN = {}
_EVERY = [0]
_HELD = {}
_HELD_LOCK = threading.Lock()
_APPLY_LOCK = threading.RLock()
_ENGINE = [None]
_BOUNDARY = [False]
_PENDING = {}
#: A file this process applied itself (`changed` from its own save) - the watcher's event for that same write is
#: not applied twice. -> {path: stamp}
_SAID_HERE = {}
_UNSAID = object()
_ONTOLOGY_DIRS = ("ontology", "ontology_worlds")
ONTOLOGY, MAPPERS = "ontology", "mappers"


_MAPPER_DIRS = []


def _mapper_dirs():
    if _MAPPER_DIRS:
        return _MAPPER_DIRS[0]
    import importlib.util

    try:
        spec = importlib.util.find_spec(MAPPERS)
    except (ImportError, ValueError):                              # no package, no folder
        return ()
    _MAPPER_DIRS.append(tuple(os.path.normcase(os.path.abspath(folder))
                              for folder in ((spec.submodule_search_locations or ()) if spec else ())))
    return _MAPPER_DIRS[0]


def name_of(path):
    """The name a change of `path` is applied under: `mappers` (a .py of the mapper package), `ontology` (anything
    under config/ontology or config/ontology_worlds), the file's own name (a .json at the config folder's top), None
    (anything else in the config folder - backups, samples, beats, drafts). A path outside both folders is its own
    name, so a test that writes a file elsewhere says `changed(that path)`; a table_config.json or chain_rules.json
    there is still that row. Asked per read, so each answer is kept (by the path and the config folder)."""
    import paths

    if not path:
        return None
    if isinstance(path, bytes):
        path = path.decode("utf-8", "replace")
    asked = (str(path), paths.CONFIG_DIR)
    if asked not in _NAMES:
        _NAMES[asked] = _name_of(str(path), paths.CONFIG_DIR)
    return _NAMES[asked]


_NAMES = {}


def _name_of(path, config_dir):
    full = os.path.normcase(os.path.abspath(path))
    base = os.path.basename(full)
    for folder in _mapper_dirs():
        if os.path.dirname(full) == folder:
            return MAPPERS if base.endswith(".py") else None
    root = os.path.normcase(os.path.abspath(config_dir))
    if full == root or full.startswith(root + os.sep):
        parts = os.path.relpath(full, root).split(os.sep)
        if parts[0] in _ONTOLOGY_DIRS:
            return ONTOLOGY
        return parts[0] if len(parts) == 1 and parts[0].endswith(".json") else None
    return base if base in ROWS else full


def generation(*names):
    """Where these names stand: moves when one of them is applied (`changed`) or everything is (`forget_held`)."""
    return (_EVERY[0],) + tuple(_GEN.get(name, 0) for name in names)


def names_of(paths):
    """`name_of` of each path, Nones out."""
    return tuple(name for name in (name_of(path) for path in paths) if name is not None)


class _Held:
    __slots__ = ("lock", "at", "has", "value", "failure")

    def __init__(self):
        self.lock = threading.Lock()
        self.at, self.has, self.value, self.failure = None, False, None, None


#: `held`'s fallback when none is given: a first read that fails raises.
RAISE = object()


def held(names, key, read, fallback=RAISE, keep=True):
    """`read()`, again only once one of `names` changed (`changed`). A read that raises keeps the value read before
    and says the names and why; with nothing read before it gives `fallback` (said the same way) or, without one,
    raises - the same failure again until a name changes, never a read per call. Said once per change.
    `keep=False`: a failure is the answer even after a good read - the ledger's compile, whose refusal the
    authoring screen and the follow-up must give alike (총괄 558a46ef1)."""
    names = (names,) if isinstance(names, str) else tuple(names)
    now = (names, generation(*names))
    slot = _HELD.get(key)
    if slot is None:
        with _HELD_LOCK:
            slot = _HELD.setdefault(key, _Held())
    if slot.at != now:
        with slot.lock:
            if slot.at != now:
                # what was read before is kept only for the same files - a key asked of other files starts afresh
                same = slot.at is not None and slot.at[0] == names
                try:
                    slot.value, slot.has, slot.failure = read(), True, None
                except Exception as exc:                           # noqa: BLE001 - kept, given or raised below
                    if slot.has and same and keep:
                        logger.error("[Config] %s does not read - this process keeps what it read before: %s",
                                     " · ".join(names), told(exc))
                    elif fallback is not RAISE:
                        slot.value, slot.has, slot.failure = fallback, False, None
                        logger.error("[Config] %s does not read - this process reads it as empty until it does: %s",
                                     " · ".join(names), told(exc))
                    else:
                        slot.has, slot.failure = False, (type(exc), exc.args, dict(vars(exc)))
                slot.at = now
    if slot.failure is not None:
        kind, args, attributes = slot.failure
        failure = kind.__new__(kind)
        failure.args = args
        failure.__dict__.update(attributes)
        raise failure
    return slot.value


def json_object(path, encoding="utf-8"):
    """A declaration file read as a JSON object - `{}` when it is not there - held until it changes (`held`), a copy
    each call. One that does not read, or is not an object, is said once and read as `{}` - or as it read before."""
    import copy

    return copy.deepcopy(held(names_of([path]), ("json", path, encoding), lambda: _json_object(path, encoding),
                              fallback={}))


def _json_object(path, encoding):
    import json

    try:
        with open(path, "r", encoding=encoding) as handle:
            loaded = json.load(handle)
    except FileNotFoundError:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError("the file is %s, not an object" % type(loaded).__name__)
    return loaded


def forget_held():
    """Every held value is read again on its next use - the Reload button's half. A file that no longer reads
    keeps its value, as on any change."""
    _EVERY[0] += 1


def _stamp(path):
    try:
        status = os.stat(path)
    except OSError:
        return None
    return status.st_mtime_ns, status.st_size


def changed(path, engine=None, heard=False):
    """`path` changed: its name moves and its row's cells run - now, or at the chain loop's next boundary. A
    process that wrote the file calls this itself after the write, so it reads the new one at once; the watcher's
    event for that same write is then not applied twice. -> the name applied, or None."""
    name = name_of(path)
    if name is None:
        return None
    said = os.path.normcase(os.path.abspath(str(path)))
    if heard:
        if _SAID_HERE.pop(said, _UNSAID) == _stamp(path):
            return None
    else:
        _SAID_HERE[said] = _stamp(path)
    row = ROWS.get(name)
    if row is not None and row[1] and _BOUNDARY[0]:
        _PENDING.setdefault(name, set()).add(path)
        return name
    _apply(name, [path], _ENGINE[0] if engine is None else engine)
    return name


def apply_pending():
    """The chain loop's boundary: the rows that waited for it, applied. -> the names applied."""
    if not _PENDING:
        return []
    applied = []
    for name in list(_PENDING):
        paths = _PENDING.pop(name, set())
        _apply(name, sorted(paths), _ENGINE[0])
        applied.append(name)
    return applied


def reload_everything(engine=None):
    """The Reload button: every held value read again and every row's cells run, in this process, now - the walk's
    pool started again once, not once a row."""
    with _APPLY_LOCK:
        forget_held()
        _PENDING.clear()
        _BATCH[0] = []
        logger.info("[Config] Reload - every declaration read again in this process")
        try:
            for name in ROWS:
                _apply(name, None, _ENGINE[0] if engine is None else engine)
        finally:
            asked, _BATCH[0] = _BATCH[0], None
        if asked:
            recycle_pools()


#: Inside `reload_everything`: the rows that asked for the pool to start again.
_BATCH = [None]


def recycle_pools():
    """The walk's pool processes started again (`process_pool.recycle` - they hold their own copies of what this
    process read); a whole reload asks it once."""
    if _BATCH[0] is not None:
        _BATCH[0].append(1)
        return
    from runtime import process_pool

    process_pool.recycle()


def _apply(name, paths, engine):
    """`paths` None: the Reload button's - said once by `reload_everything`, not per row."""
    with _APPLY_LOCK:
        _GEN[name] = _GEN.get(name, 0) + 1
        if paths is not None:
            logger.info("[Config] %s changed - read again in this process", name)
        row = ROWS.get(name)
        if row is None:
            return
        try:
            row[0](paths, engine)
        except Exception as exc:                                   # noqa: BLE001 - one row does not stop the rest
            logger.error("[Config] %s changed, but this process did not forget all it holds of it: %s",
                         name, told(exc), exc_info=exc)


def _each(cells):
    """Each cell called; one that raises is said and the others still run."""
    for what, cell in cells:
        try:
            cell()
        except Exception as exc:                                   # noqa: BLE001
            logger.error("[Config] %s not done in this process: %s", what, told(exc), exc_info=exc)


def _table_config(paths, engine):
    from ingestion import reread

    path = (paths or [None])[0] or CONFIG_FILENAME
    _each([("the table config reload", lambda: ConfigChangeHandler(engine=engine)._reload(path)),
           ("the external sources", reread.forget_sources)])


def _chain_rules(paths, engine):
    from chain import ingestion_worker, synthesis
    from runtime import maintenance_line

    _each([("the chain rules", ingestion_worker.forget_loaded_chain_rules),
           ("the join keys", synthesis.reset_right_key_cache),
           ("the declared indexes", maintenance_line.declarations_changed)])


def _ontology(paths, engine):
    from ledger import trace
    from ledger_api import ledger_subgraph

    _each([("the walk's vocabulary", trace.reset_walk_cache),
           ("the walks kept here", ledger_subgraph.reset_declaration_cache),
           ("the walk pool", recycle_pools)])


def _pools(paths, engine):
    """A file the walk's pool processes read: they hold their own copies, so new ones read it."""
    _each([("the walk pool", recycle_pools)])


def _database(paths, engine):
    if paths is None:
        return
    logger.warning("[Config] database.json changed - the connection it names is opened at start: restart to use it")


def _mappers(paths, engine):
    import mapper_sdk

    mapper_sdk.reload_modules(paths)


#: 🔴 THE ONE TABLE - name -> (what a process forgets, waits for the chain loop's boundary). A file not here is
#:    read again through `held` alone.
ROWS = {
    CONFIG_FILENAME: (_table_config, False),
    "chain_rules.json": (_chain_rules, True),
    ONTOLOGY: (_ontology, False),
    "ledger_resolver.json": (_pools, False),
    "notation_rules.json": (_pools, False),
    "map_overlay_config.json": (_pools, False),
    "ingestion_settings.json": (_pools, False),
    "database.json": (_database, False),
    MAPPERS: (_mappers, True),
}



class ConfigChangeHandler:
    """Applies a changed declaration (`changed`) after its writes stop, whatever shape they take - one
    trailing timer per file, so two files saved together are two applies. What follows was measured on
    table_config.json and holds for every file.

    Two properties matter here, and the old leading-edge debounce had neither.

    1) EVERY event re-arms the timer and the reload runs after the last one, so a
       save that arrives as several events is coalesced into one reload while a
       save that arrives *after* another save still gets its own. The previous
       "first event in the window wins, ignore the rest" rule dropped the second
       of two saves 0.3s apart ENTIRELY - disk said [col_a, col_b, lot_id], the
       physical table said [col_a, lot_id], and the log said success. It also
       dropped the completion of a slow non-atomic write, whose first event
       arrives while the file is still truncated: the handler read partial JSON,
       aborted, and then discarded the `modified` that meant "finished". That is
       the product's own write path (`crud.update_table_config` is a plain
       `open(w)`), not a hypothetical editor.

    2) All three arrival shapes are handled, because which one you get depends on
       the writer, not on the change:
         - in-place write          -> modified
         - temp + rename, SAME dir -> deleted(target) + moved(tmp -> target)
         - temp + rename, OTHER dir-> deleted(target) + created(target), NO moved
       (measured on watchdog 6.0.0 / Windows). `tempfile.mkstemp()` defaults to
       the system temp directory, so the third shape is not exotic. Handling
       `created` is only safe with a trailing edge - with a leading edge the
       truncation-time event could win the window and the completed write be
       discarded, which is what made `created` look unsafe in the first place.

    What made all of this expensive to diagnose is that `GET /tables/{t}/schema`
    reads the in-memory config singleton, so it answered 200 with the new column
    whether or not the database had ever heard of it. Physical-column checks are
    the only evidence that means anything here.
    """

    def __init__(self, engine=None):
        self.engine = engine
        self._timer_lock = threading.Lock()
        self._timers = {}
        # Reloads run on timer threads; a fresh event may re-arm and fire while
        # a previous reload is still issuing DDL. Serialize them.
        self._reload_lock = threading.Lock()

    def dispatch(self, event):
        """watchdog calls this for every event: routed by its type. Spelled here, not inherited, so the modules
        that read through `held` do not import watchdog - only `start_config_watcher` does."""
        on = getattr(self, "on_" + str(getattr(event, "event_type", "")), None)
        if on is not None:
            on(event)

    def on_deleted(self, event):
        if event.is_directory:
            return
        # a mapper file removed takes its names; a declaration removed is read as such (the table config keeps
        # its old one, as an empty file does)
        self._maybe_reload(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        # The config is the DESTINATION of the rename; src_path is the temp file.
        self._maybe_reload(getattr(event, "dest_path", None))

    def on_modified(self, event):
        if event.is_directory:
            return
        self._maybe_reload(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            return
        self._maybe_reload(event.src_path)

    def _maybe_reload(self, path):
        if not path:
            return
        if isinstance(path, bytes):  # watchdog may hand back bytes paths
            path = path.decode("utf-8", "replace")
        if name_of(path) is None:
            return

        with self._timer_lock:
            armed = self._timers.get(path)
            if armed is not None:
                armed.cancel()
            timer = self._timers[path] = threading.Timer(DEBOUNCE_SEC, self._fire, args=(path,))
            timer.daemon = True
            timer.start()

    def _fire(self, path):
        # the reload's lock BEFORE the timer goes: a waiter that sees no timer then sees this reload held or done
        # (총괄 71044b745 - in between it heard idle and read the schema first, one run in five); and only its own
        # timer - one armed again meanwhile stays for its own fire
        with self._reload_lock:
            with self._timer_lock:
                if self._timers.get(path) is threading.current_thread():
                    self._timers.pop(path)
            logger.info(f"Configuration change detected on {path}.")
            changed(path, engine=self.engine, heard=True)

    def cancel_pending(self):
        """Drop an armed reload. For shutdown paths and tests, not for hot use."""
        with self._timer_lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()

    def wait_for_idle(self, timeout=None):
        """Block until no reload is armed or running. Returns True if it settled.

        Exists so a caller that just wrote the file can observe the effect
        deterministically instead of sleeping and hoping.
        """
        deadline = None if timeout is None else time.time() + timeout
        while True:
            with self._timer_lock:
                armed = bool(self._timers)
            if not armed:
                # A timer that already fired is no longer registered, but its
                # reload may still be running - the reload lock is the join.
                if self._reload_lock.acquire(timeout=0.2):
                    self._reload_lock.release()
                    with self._timer_lock:
                        if not self._timers:
                            return True
            if deadline is not None and time.time() >= deadline:
                return False
            time.sleep(0.05)

    def _reload(self, path):
        try:
            from database import crud, models
            # 1. crud.TABLE_CONFIG 재구성
            new_config = crud.load_table_config()
            if not new_config:
                # [#9 INV-9-2] 예전에는 `if new_config:` 아래로 흘러 아무 일도 없이 끝났다.
                # 적용도 안 되고 로그도 없으니, "컬럼이 안 생겼다"는 신고의 증거가 빈 로그였다.
                # 여기서 멈추는 것 자체는 옳다(빈 config로 기존 싱글턴을 지우지 않는다) —
                # 다만 조용히 멈추지 않는다. 상세 원인은 crud.load_table_config가 로깅한다.
                logger.error(
                    f"Config reload ABORTED: '{path}' produced an empty table config "
                    f"(unparsable, unreadable, or empty). The in-memory config and the "
                    f"physical schema are UNCHANGED - any schema edit in that file has "
                    f"NOT been applied."
                )
                return

            crud.TABLE_CONFIG.clear()
            crud.TABLE_CONFIG.update(new_config)
            # The walk's pool processes read the table config when they start (lead 9a3c510c5): new ones read this
            # one - here, so a schema sync that fails below does not leave the pool on the old one (lead eb9c328e4)
            try:
                recycle_pools()
            except Exception as exc:                              # noqa: BLE001
                logger.error("[Reload] walk pool NOT recycled - its processes keep the table config they read until "
                             "restart: %s: %s", type(exc).__name__, told(exc), exc_info=exc)
            try:
                from ledger_api import ledger_subgraph        # walk_processes 0: the walks kept here end as the pool's
                ledger_subgraph.end_kept_walks("reloaded")
            except Exception as exc:                              # noqa: BLE001
                logger.error("[Reload] walks kept in this process NOT ended - their More goes on under the table "
                             "config they began with: %s: %s", type(exc).__name__, told(exc), exc_info=exc)

            # 🔴 A `search_columns` ENTRY NOTHING CAN SEARCH IS NAMED HERE, NOT WHEN
            # SOMEBODY SEARCHES (판정 255). A typo in that cell is invisible until a
            # user types in the box and quietly gets a narrower scope than the
            # declaration promises; the reload is the moment the operator is looking.
            #
            # ⚠️ REFUSED PER CELL, NOT PER FILE. `load_table_config_or_raise` states its
            # own scope - 「Semantic complaints must never keep a production server
            # down」 - so a bad name must not abort a reload that also carries a schema
            # edit. The declaration falls back to the identity and says so.
            _report_unsearchable_declarations(new_config)

            # 2. models.DYNAMIC_TABLES 동적 모델 갱신 및 핫스왑
            models.init_dynamic_models(new_config, engine=self.engine)

            # 3. 데이터베이스 엔진이 인입된 경우(웹 서버 전용) 실제 DB 물리 스키마 동기화 가동
            if self.engine:
                # [이슈 #7] 런타임에 추가된 신규 테이블 물리 CREATE (게이트 + checkfirst로 경합 무해)
                created = models.create_missing_dynamic_tables(self.engine)
                if created:
                    logger.info(f"Created missing physical tables at runtime: {created}")
                models.sync_dynamic_tables_schema(self.engine)
                logger.info("Physical database schema synced successfully.")

            logger.info("Dynamic models reloaded and hot-swapped successfully.")
        except Exception as e:
            logger.error(f"Failed to hot-swap configuration changes: {e}", exc_info=True)


def start_config_watcher(engine=None, boundary=False):
    """The config folder (all of it - `name_of` says what is a declaration) and the mappers folder, watched on a
    thread. `engine`: this process writes (the API) - the table config's physical sync and the writing cells.
    `boundary`: a chain process - the `boundary` rows wait for `apply_pending`."""
    from database import crud
    config_dir = os.path.dirname(crud.CONFIG_PATH)

    _ENGINE[0], _BOUNDARY[0] = engine, bool(boundary)
    event_handler = ConfigChangeHandler(engine=engine)
    from watchdog.observers import Observer

    observer = Observer()
    observer.schedule(event_handler, path=config_dir, recursive=True)
    for folder in _mapper_dirs():
        if os.path.isdir(folder):
            observer.schedule(event_handler, path=folder, recursive=False)
    observer.start()
    # The debounce fires on its own timer thread, which `observer.stop()` knows
    # nothing about. Expose the handler so a shutdown (or a test) can cancel an
    # armed reload instead of letting it run against a disposed engine.
    observer.config_handler = event_handler
    logger.info(f"Started config folder watchdog on '{config_dir}' and the mappers folder")
    return observer


def _report_unsearchable_declarations(config: dict):
    """Name every `search_columns` entry that nothing can search. Never raises.

    🔴 THE VERDICT COMES FROM `crud.resolve_search_columns`, the same function the
    search path calls, because two spellings of "is this column searchable" is how a reload
    comes to bless a name the search then ignores. Only the set of KNOWN columns differs,
    and that difference is the reason the decision was factored out rather than copied.

    ⚰️ IT USED TO TAKE AN `engine`, and open a session, to ask the read-time join which
    columns it exposed - a name could be searchable without being stored. Read-time joins
    are gone (S-283), so a searchable column is a DECLARED column and the known set is the
    declaration itself. Nothing here needs a connection any more, which also retires the
    「without an engine the virtual half is invisible, so do not judge」 arm: there is no
    invisible half left, and every declared name can now be judged on every reload.
    """
    from database import crud

    try:
        for table_name, table_info in (config or {}).items():
            if not isinstance(table_info, dict):
                continue
            if not table_info.get(crud.SEARCH_COLUMNS_KEY):
                continue
            used, unknown = crud.resolve_search_columns(
                table_name, set(table_info.get("column_types") or ()))
            if unknown:
                logger.error(
                    "[Config] '%s' declares search_columns that nothing can search: %s. "
                    "They are not in column_types, so `?q=` will use %s instead. "
                    "Fix the names or remove them.",
                    table_name, sorted(unknown), list(used))
    except Exception as exc:                                         # noqa: BLE001
        # A reload that dies here would trade a typo for an outage.
        logger.warning("[Config] search_columns check skipped: %s", told(exc), exc_info=exc)

