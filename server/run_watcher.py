import os
import sys
import time
import requests
import threading

# Add server and parsers directories to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)
sys.path.append(os.path.join(script_dir, "parsers"))

# Now we can import database, models, and directory_watcher
from database.database import SessionLocal
from database import models
from directory_watcher import WorkspaceWatcher, IngestionHandler

# Initialize dynamic database models
try:
    import json
    config_path = os.path.join(script_dir, "config", "table_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)
    models.init_dynamic_models(table_config)
    print("[Watcher Worker] Dynamic database models initialized successfully.")
except Exception as e:
    print(f"[Watcher Worker] Failed to load table_config or init dynamic models: {e}")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8080")

def post_event(endpoint: str, payload: dict):
    url = f"{API_BASE_URL}{endpoint}"
    try:
        res = requests.post(url, json=payload, timeout=5)
        if not res.ok:
            print(f"[Watcher Worker] API notification failed: {url} -> {res.status_code}")
    except Exception as e:
        print(f"[Watcher Worker] Failed to send API notification: {e}")

def trigger_ws_refresh(table_name: str, count: int, created_logs: list = None):
    print(f"[Watcher Worker] Refresh required for {table_name}: {count} rows updated.")
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
    post_event("/internal/events/batch-refresh", payload)

def trigger_ws_file_processed(table_name: str, filename: str, status: str, error_msg: str = None):
    print(f"[Watcher Worker] File processed: {filename} ({status}) for {table_name}.")
    payload = {
        "table_name": table_name,
        "filename": filename,
        "status": status
    }
    if error_msg:
        payload["error_msg"] = error_msg
    post_event("/internal/events/file-processed", payload)

# Database polling for PENDING_RETRY logs
def poll_pending_retries():
    print("[Watcher Worker] Background retry poller thread started.")
    while True:
        db = SessionLocal()
        try:
            # Query for logs in PENDING_RETRY status
            pending_logs = db.query(models.FileIngestionLog).filter(
                models.FileIngestionLog.status == "PENDING_RETRY"
            ).order_by(models.FileIngestionLog.id.asc()).all()
            
            for log in pending_logs:
                print(f"[Watcher Worker] Detected PENDING_RETRY log ID #{log.id} ({log.filename}). Processing...")
                
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
                    on_file_processed_callback=trigger_ws_file_processed
                )
                
                # Process the file
                try:
                    res = handler.process_archived_file_sync(log, db)
                    if res:
                        print(f"[Watcher Worker] Retry succeeded for log ID #{log.id}.")
                    else:
                        print(f"[Watcher Worker] Retry failed for log ID #{log.id}.")
                except Exception as e:
                    import traceback
                    print(f"[Watcher Worker] Exception during retry: {e}")
                    log.status = "FAILED"
                    log.error_message = traceback.format_exc()
                    db.commit()
                    trigger_ws_file_processed(table_name, log.filename, "FAILED", str(e))
                    
        except Exception as e:
            print(f"[Watcher Worker] Error in retry poller loop: {e}")
        finally:
            db.close()
            
        time.sleep(3)

def main():
    print("=" * 60)
    print(" Starting Standalone File Ingestion Watcher Process...")
    print(f" API Base URL: {API_BASE_URL}")
    print("=" * 60)
    
    workspace_base = os.path.join(script_dir, "ingestion_workspace")
    
    # Start retry poller thread
    poller_thread = threading.Thread(target=poll_pending_retries, daemon=True)
    poller_thread.start()
    
    watcher = WorkspaceWatcher(
        workspace_base,
        on_refresh_callback=trigger_ws_refresh,
        on_file_processed_callback=trigger_ws_file_processed
    )
    watcher.discover_and_watch()
    
    print(f"[Watcher Worker] Watching {watcher.watch_count} directory configurations...")
    try:
        watcher.start(blocking=True)
    except KeyboardInterrupt:
        print("[Watcher Worker] Keyboard interrupt received. Stopping watcher observer...")
        if watcher.observer:
            watcher.observer.stop()
            watcher.observer.join()
        print("[Watcher Worker] Stopped successfully.")

if __name__ == "__main__":
    main()
