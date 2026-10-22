import os
import sys
from datetime import datetime, timedelta, timezone
import time
import threading

# Add server and parsers directories to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)
sys.path.append(os.path.join(script_dir, "parsers"))

# Setup Unified Logger
from utils.logger import get_process_logger
from utils import heartbeat
logger = get_process_logger("Watcher", "watcher.log")

# Now we can import database, models, and directory_watcher
from database.database import SessionLocal, engine
from database import models
from directory_watcher import WorkspaceWatcher
from error_said import told
from ingestion.activity import path_of

# Initialize dynamic database models
try:
    import json
    import paths  # single override point (ASSY_DATA_ROOT)
    config_path = paths.config_path("table_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)
    models.init_dynamic_models(table_config)
    try:
        models.sync_dynamic_tables_schema(engine)
        logger.info("Dynamic database models and schema sync completed.")
    except Exception as e:
        logger.error(f"Failed to sync dynamic tables schema: {told(e)}", exc_info=e)
    # [P2] 오프셋 체크포인트(이어 읽기) 원장 테이블 보장.
    # 웹서버는 부팅 create_all로 만들지만 워처는 create_all을 돌리지 않으므로
    # (분리 모드에서 워처만 먼저 뜨는 경우 포함) 여기서 명시적으로 보장한다.
    try:
        models.ensure_ingestion_checkpoint_table(engine)
    except Exception as e:
        logger.error(f"Failed to ensure ingestion checkpoint table: {told(e)}", exc_info=e)
except Exception as e:
    logger.error(f"Failed to load table_config or init dynamic models: {told(e)}", exc_info=e)

import internal_event_client
# Single definition of the web server's address lives in internal_event_client.
# The module attribute stays: scripts/dev_env/iso_watcher.py reads
# run_watcher.API_BASE_URL to prove an isolated watcher is not posting to :8080.
API_BASE_URL = internal_event_client.api_base_url()

# [Std Ingestion] SYSTEM_RELOAD 시 신규 테이블 워크스페이스 자동 생성 + 런타임 감시 등록을 위해
# 폴러 스레드가 참조하는 WorkspaceWatcher 인스턴스 (main()에서 설정, None 가드 필수)
workspace_watcher = None

def _record_undelivered(endpoint: str, payload: dict, reason: str):
    """[Broadcast Recovery] Durable marker for a notification that did not arrive.

    This function is the whole difference between "the grid catches up within a
    few seconds" and "the row is in the database and the screen never learns".
    `post_event` used to log the failure and return; nothing on disk remembered
    that an announcement was owed, so every notification emitted while the web
    server was unreachable was lost for good - at every restart, and at every
    momentary blip in between.

    The marker is a `database_outbox` row in the exact shape the chain worker's
    `sweep_undelivered_broadcasts` already collects, so recovery costs no new
    mechanism, no new table and no second retry policy. See
    internal_event_client.record_undelivered_notification.
    """
    import internal_event_client
    table_name = (payload or {}).get("table_name")
    if not table_name:
        # Nothing to refresh: no table means no recoverable announcement.
        return
    internal_event_client.record_undelivered_notification(
        SessionLocal, table_name, endpoint, reason, logger=logger)


def post_event(endpoint: str, payload: dict):
    # [B5] /internal/events/* is gated with the admin secret; this worker
    # inherits ASSY_ADMIN_TOKEN from the launcher's environment. A 401 here means
    # the worker was started without it - the notification is dropped and
    # real-time sync goes quiet, so the status code is logged, not swallowed.
    # [F8] The session comes from internal_event_client and NOT from a bare
    # requests.post: `requests` trusts HTTP_PROXY and the Windows proxy registry,
    # whose `<local>` exemption does not cover a dotted address, so a notification
    # to 127.0.0.1 was relayed to a corporate proxy and refused with 403.
    # [S-37 · 판정 98] URL·헤더·판별자는 `internal_event_client` 가 «짓는다**. 이 자리는
    # 「실패가 무슨 뜻인가」만 들고 있다 — 워처에게 그것은 «미전달 기록»이다.
    import internal_event_client
    # 총괄 10-21 (C 간섭 전수 ③): within a refusal's window nothing is sent - the file goes on without waiting on the
    # API for every chunk; what is not sent is undelivered, as a refusal's is, for the chain's sweep
    if not internal_event_client.api_may_send():
        _record_undelivered(endpoint, payload, "not sent - the API refused one under %g s ago"
                            % internal_event_client.SWEEP_INTERVAL)
        return
    ok = False
    try:
        url, res, note = internal_event_client.send_internal_event(
            API_BASE_URL, endpoint, payload, timeout=5)
        ok = res.ok
        if not res.ok:
            # [F8] Third sender, same discriminator. An auth-shaped refusal
            # escalates to ERROR: a 401/403 here means real-time propagation is
            # dead for every table this watcher feeds, which is not a warning.
            if note:
                logger.error(f"API notification failed: {url} -> {res.status_code} | {note}")
            else:
                logger.warning(f"API notification failed: {url} -> {res.status_code}")
            _record_undelivered(endpoint, payload, f"HTTP {res.status_code}")
    except Exception as e:
        logger.error(f"Failed to send API notification: {told(e)}", exc_info=e)
        _record_undelivered(endpoint, payload, f"{type(e).__name__}: {told(e)}")
    internal_event_client.api_took(ok, None, logger, "Watcher")

def trigger_ws_refresh(table_name: str, count: int, created_logs: list = None, total_log_count: int = None):
    logger.info(f"Refresh required for {table_name}: {count} rows updated.")
    payload = {
        "table_name": table_name,
        "change_count": count
    }
    if created_logs:
        from datetime import datetime
        serialized_logs = []
        for log in created_logs:
            log_copy = dict(log)
            ts = log_copy.get("timestamp")
            if ts is not None and isinstance(ts, datetime):
                log_copy["timestamp"] = ts.isoformat()
            serialized_logs.append(log_copy)
        payload["created_logs"] = serialized_logs
        # [C-5] created_logs는 상한(500) 절단본 — 실제 총 건수를 별도 필드로 전달해
        # 웹서버 audit_cache의 트랜잭션 total_count 표기가 절단과 무관하게 정확하도록 한다.
        if total_log_count is not None:
            payload["total_log_count"] = total_log_count
    post_event("/internal/events/batch-refresh", payload)

def trigger_ws_file_processed(table_name: str, filename: str, status: str, error_msg: str = None):
    logger.info(f"File processed: {filename} ({status}) for {table_name}.")
    payload = {
        "table_name": table_name,
        "filename": filename,
        "status": status
    }
    if error_msg:
        payload["error_msg"] = error_msg
    post_event("/internal/events/file-processed", payload)

def trigger_ws_progress(table_name: str, filename: str, progress: int, processed_rows: int, total_rows: int):
    try:
        from pipeline_base import BasePipelineParser
        clean_filename = BasePipelineParser.get_basename(filename)
    except Exception:
        clean_filename = filename

    logger.info(f"Ingestion progress for {clean_filename} on {table_name}: {progress}% ({processed_rows}/{total_rows})")
    # [S-37] 봉투는 `event_constants` 가 짓는다 — 소급 러너가 «같은 함수»를 부른다.
    import event_constants
    payload = event_constants.progress_event(
        event_constants.PROGRESS_STATUS_RUNNING,
        progress=progress, processed_rows=processed_rows, total_rows=total_rows,
        table_name=table_name, filename=clean_filename, filepath=path_of(filename))
    post_event("/internal/events/broadcast", payload)

def trigger_ws_ingestion_state(state: dict):
    """[Heavy Lane P1] 인제션 라이프사이클 상태(QUEUED/PROCESSING/FINISHED)를 웹서버
    진행 스냅샷 레지스트리에 push한다. WS 브로드캐스트 없음 — admin active API 전용.
    페이로드는 소형 스칼라 필드만 (무절단 컬렉션 동봉 금지 교훈 준수)."""
    try:
        from pipeline_base import BasePipelineParser
        clean_filename = BasePipelineParser.get_basename(state.get("filename") or "")
    except Exception:
        clean_filename = state.get("filename")
    payload = {**state, "filename": clean_filename}
    logger.info(
        f"Ingestion state: {payload.get('status')} lane={payload.get('lane')} "
        f"{clean_filename} -> {payload.get('table_name')}"
    )
    post_event("/internal/events/ingestion-state", payload)

def reload_watcher_cache():
    """The Reload button in the watcher process: every declaration and mapper again by the one table
    (`config_watcher.reload_everything` - the join keys this writer learned go with the chain rules' row). Pipeline
    plugins are read per file (`scan_workspace_pipeline_parsers`): nothing is held to drop."""
    from database import config_watcher

    config_watcher.reload_everything()
    logger.info("Watcher worker modules cache cleared.")

# Database polling for PENDING_RETRY logs
def reclaim_grace_setting():
    """The operator's grace if they declared one; `None` means "use the derivation".
    Through the file's one read (`ingestion.settings`, 총괄 10-07)."""
    from ingestion.settings import read_ingestion_settings
    return read_ingestion_settings().get("retry_reclaim_after_seconds")


def reclaim_stranded_claims(db):
    """Give back rows this poller claimed and never finished.

    🔴 THE HALF THAT SURVIVES A KILLED PROCESS. The poller commits `status = "PENDING"`
    before it works and its own query selects only `PENDING_RETRY`, so a row claimed by a
    process that then stopped existing is in a state nothing looks for again. `fe3e9261`
    closed the case where SETUP throws; nothing inside that process can close the case
    where the process is gone. This can, from outside.

    ⚠️ THE PREDICATE IS TWO FACTS. "Claimed and old" alone reclaims a healthy long
    ingestion, and reclaiming a live job turns a LOSS into DUPLICATE work -- worse, because
    loss means the data never arrives while duplication means wrong data arrives quietly.
    The second fact is the checkpoint: if chunks are still landing it is alive, however long
    it has run.

    ⛔ A ROW WITH NO CHECKPOINT IS SKIPPED, NOT RECLAIMED, AND THE SKIP IS COUNTED. Three
    arms of `directory_watcher._plan_checkpoint` produce none and none of them means the
    file is stuck. Counting is what keeps the remaining hole visible: nobody knows today how
    often those arms fire, and this line is what will answer it.
    """
    import ingestion.checkpoint

    now = datetime.now(timezone.utc)
    grace = ingestion.checkpoint.reclaim_after_seconds(reclaim_grace_setting())
    cutoff = now - timedelta(seconds=grace)

    claimed = (db.query(models.FileIngestionLog)
               .filter(models.FileIngestionLog.status == "PENDING",
                       models.FileIngestionLog.updated_at < cutoff)
               .order_by(models.FileIngestionLog.id.asc()).all())
    if not claimed:
        return 0, 0

    reclaimed = skipped = 0
    for log in claimed:
        has_checkpoint, moved_at = ingestion.checkpoint.liveness(
            db, log.table_name, log.filename)
        if not has_checkpoint:
            skipped += 1
            continue
        if moved_at is not None:
            moved = moved_at if moved_at.tzinfo else moved_at.replace(tzinfo=timezone.utc)
            if moved >= cutoff:
                continue                      # chunks are still landing: it is alive
        stamped = (log.updated_at if log.updated_at.tzinfo
                   else log.updated_at.replace(tzinfo=timezone.utc))
        # ⚠️ Named, with the age, one line per row. A silent reclaim would hide how often
        # this happens - the class this whole day was spent removing.
        logger.warning(
            "[Reclaim] log #%s (%s / %s) was claimed %.0fs ago and its checkpoint has not "
            "moved; returning it to PENDING_RETRY so it runs again.",
            log.id, log.table_name, log.filename, (now - stamped).total_seconds())
        log.status = "PENDING_RETRY"
        reclaimed += 1

    if reclaimed or skipped:
        db.commit()
        # 🔴 THE SKIP COUNT IS THE POINT. "N candidates, M skipped" is the only thing that
        # will ever say how big the checkpoint-less hole is.
        logger.warning(
            "[Reclaim] %d candidate(s) past the %.0fs grace: %d reclaimed, %d skipped "
            "(no checkpoint - liveness unknown, left claimed on purpose).",
            len(claimed), grace, reclaimed, skipped)
    return reclaimed, skipped


def claim_retry(db, log):
    """PENDING_RETRY -> PENDING in one statement, only while the row still is (총괄 49792d3f6 B): a row a cancel put
    back after the list was read is not read, and the cancel's count is what it put back. -> True when claimed."""
    claimed = (db.query(models.FileIngestionLog)
               .filter(models.FileIngestionLog.id == log.id, models.FileIngestionLog.status == "PENDING_RETRY")
               .update({"status": "PENDING"}, synchronize_session=False))
    db.commit()
    if claimed:
        db.refresh(log)
    return bool(claimed)


def hand_back_claimed_retries():
    """The file log's PENDING rows when the watcher starts, handed to the retry door again (총괄 18a3bc5b7 ㄱ). Only
    `claim_retry` writes PENDING there, and this process reads nothing yet - so the run that claimed them is gone. A
    claim it left before its first checkpoint is one `reclaim_stranded_claims` skips by design: it stood PENDING for
    good. One watcher per install. Then every waiting row the declaration does not take now is deleted
    (`reread.delete_not_taken`, 소유자 10-22 「재기동시」) - a Read now or Retry of such a file is read only before the next
    start. -> how many handed."""
    from ingestion import reread

    db = SessionLocal()
    try:
        handed = (db.query(models.FileIngestionLog)
                  .filter(models.FileIngestionLog.status == "PENDING")
                  .update({"status": "PENDING_RETRY"}, synchronize_session=False))
        db.commit()
        deleted = reread.delete_not_taken(db)
    finally:
        db.close()
    if handed:
        logger.warning("[Retry] %d retry claim(s) left by the last run handed again", handed)
    for table, count, why in deleted:
        logger.warning("[Watcher] %s: %d waiting file(s) the declaration does not take - deleted (%s)", table, count,
                       " · ".join("%s %d" % item for item in why.items()))
    return handed


def pending_retries(db):
    """PENDING_RETRY rows, oldest first, `reread.max_files()` of them a turn - the rest wait for the next turns, and
    the poller's other work runs between (총괄 10-21: the cap is a pace). None before the watcher holds its handlers
    (총괄 fab40ed69): this thread starts first, and a retry runs on the table's own handler."""
    from ingestion import reread

    if workspace_watcher is None:
        return []
    return (db.query(models.FileIngestionLog)
            .filter(models.FileIngestionLog.status == "PENDING_RETRY")
            .order_by(models.FileIngestionLog.id.asc()).limit(reread.max_files()).all())


def retry_one(db, log):
    """Run one claimed PENDING_RETRY row through the watcher's own handler for its table.

    🔴 [총괄 fab40ed69, 소유자 「ㄱ」] THE HANDLER THAT READ IT THE FIRST TIME. A handler built
    here knew no external source, so an external file's retry read without its folder's
    wafer and time, its parser options and its `external:` source name. The watcher's
    handler holds them, and takes the same workspace lock its own ingestion takes.

    🔴 EVERYTHING IS INSIDE THE TRY. The row was claimed (PENDING) before this runs, which the
    poller's own query cannot see again, so any exception here must still end it FAILED by
    name. A process DEATH is the reclaim sweep's half.
    """
    table_name = log.table_name or "unknown"
    try:
        from directory_watcher import get_workspace_serial_lock
        handler = workspace_watcher.handlers_by_raw_path.get(
            workspace_watcher.raws_root_for(table_name))
        if handler is None:
            raise RuntimeError(
                "the watcher runs no handler for table %r (%s) - nothing to retry it with"
                % (table_name, workspace_watcher.raws_root_for(table_name)))
        with get_workspace_serial_lock(handler.workspace_path):
            res = handler.process_archived_file_sync(log, db)
        if res:
            logger.info(f"Retry succeeded for log ID #{log.id}.")
        else:
            logger.warning(f"Retry failed for log ID #{log.id}.")
    except Exception as e:
        import traceback
        logger.error(f"Exception during retry: {e}\n{traceback.format_exc()}")
        log.status = "FAILED"
        log.error_message = traceback.format_exc()
        db.commit()
        trigger_ws_file_processed(table_name, log.filepath or log.filename, "FAILED", str(e))


#: Written once the read files' log rows were stamped (`stamp_read_files_once`) - beside the reading stamps.
READ_FILES_STAMPED_FILENAME = "watcher_read_files_stamped"


def readings_now(watcher, stamps):
    """{table: its reading now} for the watcher's tables, or None when table_config reads as nothing. An
    ingestion_settings.json there that reads as nothing keeps each table's kept external part (see the caller)."""
    from directory_watcher import load_global_table_config
    from ingestion import reread, settings as ingestion_settings

    handlers = list(watcher.handlers_by_raw_path.values()) if watcher is not None else []
    table_config = load_global_table_config() if handlers else {}
    if not table_config:
        return None
    declared = ingestion_settings.read_ingestion_settings()
    unread = not declared and os.path.exists(ingestion_settings.INGESTION_SETTINGS_PATH)
    sources = declared.get("external_sources") or []
    now = {}
    for handler in handlers:
        table = handler._resolve_table_name(table_config)
        if table:
            now[table] = reread.reading_of(table, table_config.get(table), sources, handler.scripts_path)
            if unread and table in stamps:
                now[table]["external source"] = stamps[table].get("external source")
    return now


def stamp_read_files_once(watcher):
    """🔴 The checklist's first start (총괄 10-21, 소유자 「좀 가볍게 돌게 만들어」) - nothing heavy before the watcher
    stands: the rows from before it are stamped by the first full sweep off the stat it takes anyway
    (`directory_watcher.start_read_files_fill`; the marker is written when that sweep reached every source). Here only
    the readings are kept as `reading_of` spells them now (it no longer reads `enabled`), else the first tick takes the
    new spelling for a changed reading and unchecks those tables. A failure is said and the watcher goes on."""
    import directory_watcher
    import paths
    from ingestion import reread

    marker = paths.config_path(READ_FILES_STAMPED_FILENAME)
    if os.path.exists(marker):
        return None
    directory_watcher.start_read_files_fill(marker)
    try:
        stamps = reread.load_reading_stamps()
        now = readings_now(watcher, stamps)
        if now is not None:
            reread.keep_reading_stamps({**stamps, **now})
    except Exception as e:                                                  # noqa: BLE001 - the watcher goes on
        logger.warning("[Watcher] the tables' readings were not kept for the checklist's first start: %s", told(e))
    line = "[Watcher] read files are stamped by the first sweep (the checklist's first start)"
    logger.info(line)
    return line


def folders_of(watcher, table, table_config):
    """(the table's raws/ folders, its external source ids) - where its sweeps look. A handler's table as
    `readings_now` resolves it."""
    raws = [path for path, handler in watcher.handlers_by_raw_path.items()
            if handler._resolve_table_name(table_config) == table]
    sources = [source_id for source_id, target in watcher.external_targets.items()
               if target["spec"]["table_name"] == table]
    return raws, sources


def sweep_a_table_now(watcher, raws, sources, line):
    """What a changed reading unchecked is looked at now, by that table's own sweeps - not the next periodic one - and
    ONE line says both: what was unchecked and what was dispatched to be read again (총괄 10-21)."""
    dispatched = 0
    try:
        if raws:
            dispatched += watcher.sweep_existing_files(raws)
        if sources:
            dispatched += watcher.sweep_external_sources(sources)
        logger.info("%s - %d dispatched to be read again", line, dispatched)
    except Exception as e:                                         # noqa: BLE001 - the periodic sweep reads them
        logger.warning("%s - its sweep failed, the next periodic sweep reads them: %s", line, told(e), exc_info=e)


def hear_changed_readings(db, stamps):
    """🔴 [총괄 10-20 ab951f09b, 소유자 「ㅇㅇ」] Each watched table's reading (`reread.reading_of`) against the one kept:
    changed -> its failed files handed again through the retry door; a table seen the first time is only kept. A
    table_config that reads as nothing (absent, or mid-write) is no reading - the tick passes. An
    ingestion_settings.json there that reads as nothing (mid-write, 총괄 10-20) keeps each table's external part as
    kept - neither compared nor written over; its table_config and plugins are compared as ever. -> the stamps."""
    from directory_watcher import load_global_table_config
    from ingestion import reread

    now = readings_now(workspace_watcher, stamps)
    if now is None:
        return stamps
    changed = {table: reading for table, reading in now.items() if stamps.get(table) != reading}
    table_config = load_global_table_config() if changed else {}
    for table, reading in changed.items():
        if table not in stamps:
            continue
        raws, sources = folders_of(workspace_watcher, table, table_config)
        line = reread.hand_on_a_changed_reading(
            db, table, stamps[table], reading,
            folders=raws + [workspace_watcher.external_targets[source_id]["spec"]["root"] for source_id in sources])
        if line:
            threading.Thread(target=sweep_a_table_now, args=(workspace_watcher, raws, sources, line),
                             name="watcher-reading-changed", daemon=True).start()
    if changed:
        stamps = {**stamps, **changed}
        reread.keep_reading_stamps(stamps)
    return stamps


def poll_pending_retries():
    logger.info("Background retry poller thread started.")
    last_reload_event_id = 0
    from ingestion import reread

    reading_stamps = reread.load_reading_stamps()
    from ingestion import settings as ingestion_settings
    sources_seen = ingestion_settings.read_ingestion_settings().get("external_sources")

    while True:
        # [B1/B2] Liveness beat. This loop does real work every ~3 s (a database
        # query plus the reload check), so a beat that stops advancing means the
        # watcher process can no longer schedule this thread or reach the
        # database - not merely that a pid vanished.
        #
        # This beat used to be the ONLY watcher signal, which left a hole: a
        # watcher wedged inside ingestion kept polling and reported healthy. It
        # is no longer sufficient on its own and no longer needs to be - the
        # ingestion path opens work claims (directory_watcher.HEARTBEAT_NAME),
        # and this beat carries their stall age. The poller is now the reporter
        # of a wedged ingestion rather than a mask over it.
        heartbeat.beat("watcher")
        db = SessionLocal()
        try:
            # The Reload button's SYSTEM_RELOAD row and the index line's join-keys row - a save writes none; this
            # process watches the files (e6a0bdbbd).
            from runtime import system_reload
            new_reloads = system_reload.reloads_after(db, last_reload_event_id)
            latest_reload = new_reloads[-1] if new_reloads else None
            if latest_reload is not None:
                last_reload_event_id = latest_reload.id

            reload_work = system_reload.reload_for(system_reload.WATCHER, new_reloads)
            if reload_work == system_reload.SCOPE_JOIN_KEYS:
                # the index line built or took back a join unique index: this writer's gate learns it again
                from chain import synthesis

                synthesis.reset_right_key_cache()
            if reload_work == system_reload.FULL:
                logger.info(f"[Reload] SYSTEM_RELOAD trigger detected (Event ID: {latest_reload.id}). Reloading scripts...")
                reload_watcher_cache()
                # [이슈 #7] config 재로드 + 신규 테이블 ORM 등록 + 물리 CREATE 보충
                # (웹서버가 1차로 CREATE하지만, information_schema 게이트 + checkfirst로
                #  중복/경합이 무해하므로 인제션 직전 안전망으로 한 번 더 보장)
                try:
                    created = models.refresh_dynamic_models(engine)
                    if created:
                        logger.info(f"[Reload] Created missing physical tables at runtime: {created}")
                except Exception as e:
                    logger.error(f"[Reload] Dynamic model refresh failed: {told(e)}")
                # [Std Ingestion] 신규 테이블 워크스페이스 자동 생성 + 실행 중 observer에 런타임 감시 등록
                if workspace_watcher is not None:
                    try:
                        workspace_watcher.sync_new_workspaces()
                    except Exception as e:
                        logger.error(f"[Reload] Workspace sync after SYSTEM_RELOAD failed: {told(e)}")
                
            # a table whose reading changed hands its failed files here, so the query below reads them this cycle
            try:
                reading_stamps = hear_changed_readings(db, reading_stamps)
            except Exception as reading_error:                         # noqa: BLE001 - the retries below go on
                db.rollback()
                logger.warning("[Watcher] the tables' readings were not compared this time: %s", told(reading_error))

            # Reclaim first, so anything given back is visible to the query below
            # in this same cycle rather than waiting a whole extra one.
            reclaim_stranded_claims(db)

            # ingestion_settings.json saved: each external source as it says now - a source switched off, removed or
            # changed is retired or stands again, the others and raws/ untouched, no restart (총괄 10-21). Its held
            # reading is asked, not the file's stamp: the stamp moves a moment before the reading does.
            sources_now = ingestion_settings.read_ingestion_settings().get("external_sources")
            if sources_now != sources_seen and workspace_watcher is not None:
                sources_seen = sources_now
                try:
                    workspace_watcher.refresh_external_sources()
                except Exception as refresh_error:                     # noqa: BLE001 - the retries below go on
                    logger.warning("[Watcher] the external sources were not read again: %s", told(refresh_error))
            pending_logs = pending_retries(db)

            for log in pending_logs:
                logger.info(f"Detected PENDING_RETRY log ID #{log.id} ({log.filename}). Processing...")

                if not claim_retry(db, log):
                    logger.info(f"Log ID #{log.id} ({log.filename}) is no longer PENDING_RETRY - not read")
                    continue
                retry_one(db, log)
                    
        except Exception as e:
            logger.error(f"Error in retry poller loop: {told(e)}")
        finally:
            db.close()
            
        time.sleep(3)

def main():
    logger.info("=" * 60)
    logger.info(" Starting Standalone File Ingestion Watcher Process...")
    logger.info(f" API Base URL: {API_BASE_URL}")
    logger.info("=" * 60)

    # [F8] Everything about this process's path to /internal/events/*, before any
    # data is in flight: which token it holds (as a one-way fingerprint the API
    # server prints too), what proxy configuration exists, and whether /health
    # answers directly. The 2026-07-30 proxy incident was invisible until the
    # first correction happened to be made.
    for _lvl, _msg in internal_event_client.startup_lines("File Ingestion Watcher"):
        getattr(logger, _lvl)(_msg)
    
    import paths
    workspace_base = paths.WORKSPACE_DIR
    
    # [최적화] table_config.json의 동적 스키마 실시간 변경을 감시하는 config watcher 시작 (데몬이므로 engine=None 전달)
    config_watcher = None
    try:
        from database.config_watcher import start_config_watcher
        config_watcher = start_config_watcher(None)
    except Exception as e:
        logger.error(f"Failed to start config watcher: {told(e)}", exc_info=e)
    
    watcher = WorkspaceWatcher(
        workspace_base,
        on_refresh_callback=trigger_ws_refresh,
        on_file_processed_callback=trigger_ws_file_processed,
        on_progress_callback=trigger_ws_progress,
        on_ingestion_state_callback=trigger_ws_ingestion_state
    )
    watcher.discover_and_watch()
    stamp_read_files_once(watcher)
    hand_back_claimed_retries()

    # Start retry poller thread - after the stamp fill, which rewrites the readings it keeps
    poller_thread = threading.Thread(target=poll_pending_retries, daemon=True)
    poller_thread.start()

    # [Std Ingestion] SYSTEM_RELOAD 폴러가 런타임 워크스페이스 동기화에 사용할 참조 등록
    global workspace_watcher
    workspace_watcher = watcher
    
    logger.info(f"Watching {watcher.watch_count} directory configurations...")
    try:
        watcher.start(blocking=True)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping watcher observer...")
        if watcher.observer:
            watcher.observer.stop()
            watcher.observer.join()
        if config_watcher:
            # The reload debounce lives on its own timer thread, out of reach of
            # observer.stop(). Cancel it before tearing the observer down.
            handler = getattr(config_watcher, "config_handler", None)
            if handler is not None:
                handler.cancel_pending()
            config_watcher.stop()
            config_watcher.join()
        logger.info("Stopped successfully.")

if __name__ == "__main__":
    main()
