import os
import sys
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
from directory_watcher import WorkspaceWatcher, IngestionHandler

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
        logger.error(f"Failed to sync dynamic tables schema: {e}")
    # [P2] 오프셋 체크포인트/해시 dedup 원장 테이블 보장.
    # 웹서버는 부팅 create_all로 만들지만 워처는 create_all을 돌리지 않으므로
    # (분리 모드에서 워처만 먼저 뜨는 경우 포함) 여기서 명시적으로 보장한다.
    try:
        models.ensure_ingestion_checkpoint_table(engine)
    except Exception as e:
        logger.error(f"Failed to ensure ingestion checkpoint table: {e}")
except Exception as e:
    logger.error(f"Failed to load table_config or init dynamic models: {e}")

import internal_event_client
# Single definition of the web server's address lives in internal_event_client.
# The module attribute stays: scripts/dev_env/iso_watcher.py reads
# run_watcher.API_BASE_URL to prove an isolated watcher is not posting to :8080.
API_BASE_URL = internal_event_client.api_base_url()

# [Std Ingestion] SYSTEM_RELOAD 시 신규 테이블 워크스페이스 자동 생성 + 런타임 감시 등록을 위해
# 폴러 스레드가 참조하는 WorkspaceWatcher 인스턴스 (main()에서 설정, None 가드 필수)
workspace_watcher = None

def post_event(endpoint: str, payload: dict):
    # [B5] /internal/events/* is gated with the admin secret; this worker
    # inherits ASSY_ADMIN_TOKEN from the launcher's environment. A 401 here means
    # the worker was started without it - the notification is dropped and
    # real-time sync goes quiet, so the status code is logged, not swallowed.
    # [F8] The session comes from internal_event_client and NOT from a bare
    # requests.post: `requests` trusts HTTP_PROXY and the Windows proxy registry,
    # whose `<local>` exemption does not cover a dotted address, so a notification
    # to 127.0.0.1 was relayed to a corporate proxy and refused with 403.
    import admin_auth
    import internal_event_client
    url = f"{API_BASE_URL}{endpoint}"
    try:
        res = internal_event_client.internal_event_session().post(
            url, json=payload, timeout=5,
            headers=admin_auth.internal_event_headers())
        if not res.ok:
            # [F8] Third sender, same discriminator. An auth-shaped refusal
            # escalates to ERROR: a 401/403 here means real-time propagation is
            # dead for every table this watcher feeds, which is not a warning.
            note = admin_auth.internal_event_failure_note(res.status_code, res.headers)
            if note:
                logger.error(f"API notification failed: {url} -> {res.status_code} | {note}")
            else:
                logger.warning(f"API notification failed: {url} -> {res.status_code}")
    except Exception as e:
        logger.error(f"Failed to send API notification: {e}")

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
    payload = {
        "event": "file_ingestion_progress",
        "table_name": table_name,
        "filename": clean_filename,
        "progress": progress,
        "processed_rows": processed_rows,
        "total_rows": total_rows,
        "status": "PROCESSING"
    }
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
    """와처 프로세스의 동적 모듈 캐시(pipeline plugins, mappers)를 명시적으로 무효화합니다."""
    import sys
    
    # Remove pipeline plugin parsers from sys.modules cache
    plugin_keys = [k for k in sys.modules.keys() if k.startswith("pipeline_plugin_")]
    for k in plugin_keys:
        sys.modules.pop(k, None)
        
    # Remove custom mappers from sys.modules cache
    mapper_keys = [k for k in sys.modules.keys() if k.startswith("mappers.")]
    for k in mapper_keys:
        sys.modules.pop(k, None)
        
    logger.info("Watcher worker modules cache cleared.")

# Database polling for PENDING_RETRY logs
def poll_pending_retries():
    logger.info("Background retry poller thread started.")
    last_reload_event_id = 0

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
            # Check for SYSTEM_RELOAD outbox event to reload modules
            from database.models import DatabaseOutbox
            latest_reload = db.query(DatabaseOutbox).filter(
                DatabaseOutbox.event_type == "SYSTEM_RELOAD"
            ).order_by(DatabaseOutbox.id.desc()).first()
            
            if latest_reload and latest_reload.id > last_reload_event_id:
                last_reload_event_id = latest_reload.id
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
                    logger.error(f"[Reload] Dynamic model refresh failed: {e}")
                # [Std Ingestion] 신규 테이블 워크스페이스 자동 생성 + 실행 중 observer에 런타임 감시 등록
                if workspace_watcher is not None:
                    try:
                        workspace_watcher.sync_new_workspaces()
                    except Exception as e:
                        logger.error(f"[Reload] Workspace sync after SYSTEM_RELOAD failed: {e}")
                
            # Query for logs in PENDING_RETRY status
            pending_logs = db.query(models.FileIngestionLog).filter(
                models.FileIngestionLog.status == "PENDING_RETRY"
            ).order_by(models.FileIngestionLog.id.asc()).all()
            
            for log in pending_logs:
                logger.info(f"Detected PENDING_RETRY log ID #{log.id} ({log.filename}). Processing...")
                
                # Update status to processing (PENDING) to prevent concurrent runs
                log.status = "PENDING"
                db.commit()
                
                # Setup handler and run synchronous retry
                table_name = log.table_name or "unknown"
                # [D3] workspace_name 별칭 역조회 — 별칭 워크스페이스의 재시도가
                # ingestion_workspace/<table_name> 허공 경로로 오배송되지 않게 한다.
                from directory_watcher import resolve_workspace_root, load_global_table_config
                import paths
                workspace_root = resolve_workspace_root(
                    paths.WORKSPACE_DIR, table_name, load_global_table_config()
                )

                config_path = os.path.join(workspace_root, "config", "config.json")
                if not os.path.exists(config_path) and os.path.exists(os.path.join(workspace_root, "config")):
                    json_files = [f for f in os.listdir(os.path.join(workspace_root, "config")) if f.endswith('.json')]
                    if json_files:
                        config_path = os.path.join(workspace_root, "config", json_files[0])
                        
                archives_path = os.path.join(workspace_root, "archives")
                
                handler = IngestionHandler(
                    workspace_path=workspace_root,
                    config_path=config_path if os.path.exists(config_path) else None,
                    archives_path=archives_path,
                    default_table_name=table_name,
                    on_refresh_callback=trigger_ws_refresh,
                    on_file_processed_callback=trigger_ws_file_processed,
                    on_progress_callback=trigger_ws_progress
                )
                
                # Process the file
                try:
                    # [QA F3] 재처리 폴러는 heavy 워커·observer와 같은 프로세스 —
                    # 워크스페이스 직렬화 락을 잡아 heavy/normal 레인 처리와 재처리
                    # 업서트가 같은 테이블에서 인터리빙되지 않게 한다(순서 계약 편입).
                    # heavy 7분 처리 중이면 폴러가 그만큼 대기하지만 백그라운드 스레드라 무해.
                    from directory_watcher import get_workspace_serial_lock
                    with get_workspace_serial_lock(workspace_root):
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
                    trigger_ws_file_processed(table_name, log.filename, "FAILED", str(e))
                    
        except Exception as e:
            logger.error(f"Error in retry poller loop: {e}")
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

    # Start retry poller thread
    poller_thread = threading.Thread(target=poll_pending_retries, daemon=True)
    poller_thread.start()
    
    # [최적화] table_config.json의 동적 스키마 실시간 변경을 감시하는 config watcher 시작 (데몬이므로 engine=None 전달)
    config_watcher = None
    try:
        from database.config_watcher import start_config_watcher
        config_watcher = start_config_watcher(None)
    except Exception as e:
        logger.error(f"Failed to start config watcher: {e}")
    
    watcher = WorkspaceWatcher(
        workspace_base,
        on_refresh_callback=trigger_ws_refresh,
        on_file_processed_callback=trigger_ws_file_processed,
        on_progress_callback=trigger_ws_progress,
        on_ingestion_state_callback=trigger_ws_ingestion_state
    )
    watcher.discover_and_watch()

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
