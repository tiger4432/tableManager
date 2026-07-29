import os
import threading
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger("Watcher.ConfigWatcher")

CONFIG_FILENAME = "table_config.json"

# 마지막 이벤트 이후 이만큼 조용하면 발화하는 **트레일링 엣지** 디바운스 창(초).
# 창 안에 새 이벤트가 들어오면 타이머를 다시 무장한다(재무장).
DEBOUNCE_SEC = 1.0


class ConfigChangeHandler(FileSystemEventHandler):
    """Reloads table_config.json after the writes stop, whatever shape they take.

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
        self._timer = None
        # Reloads run on timer threads; a fresh event may re-arm and fire while
        # a previous reload is still issuing DDL. Serialize them.
        self._reload_lock = threading.Lock()

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
        if os.path.basename(path) != CONFIG_FILENAME:
            return

        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SEC, self._fire, args=(path,))
            self._timer.daemon = True
            self._timer.start()

    def _fire(self, path):
        with self._timer_lock:
            self._timer = None
        logger.info(f"Configuration change detected on {path}. Reloading dynamic models...")
        with self._reload_lock:
            self._reload(path)

    def cancel_pending(self):
        """Drop an armed reload. For shutdown paths and tests, not for hot use."""
        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def wait_for_idle(self, timeout=None):
        """Block until no reload is armed or running. Returns True if it settled.

        Exists so a caller that just wrote the file can observe the effect
        deterministically instead of sleeping and hoping.
        """
        deadline = None if timeout is None else time.time() + timeout
        while True:
            with self._timer_lock:
                armed = self._timer is not None
            if not armed:
                # A timer that already fired is no longer registered, but its
                # reload may still be running - the reload lock is the join.
                if self._reload_lock.acquire(timeout=0.2):
                    self._reload_lock.release()
                    with self._timer_lock:
                        if self._timer is None:
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

            # 2. models.DYNAMIC_TABLES 동적 모델 갱신 및 핫스왑
            models.init_dynamic_models(new_config)

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


def start_config_watcher(engine=None):
    """
    table_config.json 설정 폴더를 비동기로 감시하는 watchdog 스레드를 시작합니다.
    """
    from database import crud
    config_dir = os.path.dirname(crud.CONFIG_PATH)

    event_handler = ConfigChangeHandler(engine=engine)
    observer = Observer()
    observer.schedule(event_handler, path=config_dir, recursive=False)
    observer.start()
    # The debounce fires on its own timer thread, which `observer.stop()` knows
    # nothing about. Expose the handler so a shutdown (or a test) can cancel an
    # armed reload instead of letting it run against a disposed engine.
    observer.config_handler = event_handler
    logger.info(f"Started config folder watchdog on '{config_dir}'")
    return observer
