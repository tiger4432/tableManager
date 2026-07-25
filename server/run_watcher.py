import os
import sys
import time
import requests
import threading

# Add server and parsers directories to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)
sys.path.append(os.path.join(script_dir, "parsers"))

# Setup Unified Logger
from utils.logger import get_process_logger
logger = get_process_logger("Watcher", "watcher.log")

# Now we can import database, models, and directory_watcher
from database.database import SessionLocal, engine
from database import models
from directory_watcher import WorkspaceWatcher, IngestionHandler

# Initialize dynamic database models
try:
    import json
    config_path = os.path.join(script_dir, "config", "table_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)
    models.init_dynamic_models(table_config)
    try:
        models.sync_dynamic_tables_schema(engine)
        logger.info("Dynamic database models and schema sync completed.")
    except Exception as e:
        logger.error(f"Failed to sync dynamic tables schema: {e}")
except Exception as e:
    logger.error(f"Failed to load table_config or init dynamic models: {e}")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8080")

def post_event(endpoint: str, payload: dict):
    url = f"{API_BASE_URL}{endpoint}"
    try:
        res = requests.post(url, json=payload, timeout=5)
        if not res.ok:
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
                workspace_root = os.path.join(script_dir, "ingestion_workspace", table_name)
                
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
    
    workspace_base = os.path.join(script_dir, "ingestion_workspace")
    
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
        on_progress_callback=trigger_ws_progress
    )
    watcher.discover_and_watch()
    
    logger.info(f"Watching {watcher.watch_count} directory configurations...")
    try:
        watcher.start(blocking=True)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping watcher observer...")
        if watcher.observer:
            watcher.observer.stop()
            watcher.observer.join()
        if config_watcher:
            config_watcher.stop()
            config_watcher.join()
        logger.info("Stopped successfully.")

if __name__ == "__main__":
    main()
