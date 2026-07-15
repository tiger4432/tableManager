from sqlalchemy import desc
from sqlalchemy.orm import Session
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from database.database import SessionLocal, engine, get_db
from database import models, schemas, crud
import uuid 
import os
import io
import csv
from fastapi import UploadFile, File, Body, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Setup Unified Logger & Hook Uvicorn Loggers
import logging
from utils.logger import get_process_logger, ColoredProcessFormatter
logger = get_process_logger("Server", "server.log")

for uv_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
    uv_logger = logging.getLogger(uv_name)
    for handler in uv_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setFormatter(ColoredProcessFormatter(
                '[%(name)s] [%(asctime)s] %(levelname)s - %(message)s',
                process_name="Server"
            ))

# Load table config and initialize dynamic database models
import json
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config", "table_config.json")
try:
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)
    models.init_dynamic_models(table_config)
except Exception as e:
    logger.error(f"Failed to load table_config or init dynamic models: {e}")

# Create tables if not exists
models.Base.metadata.create_all(bind=engine)
try:
    models.sync_dynamic_tables_schema(engine)
except Exception as e:
    logger.error(f"Failed to sync dynamic tables schema: {e}")

app = FastAPI(title="AssyManager Table Server")

# --- ContextVars Middleware config ---
from database.context import request_user, request_transaction_id, request_source

@app.middleware("http")
async def db_context_middleware(request: Request, call_next):
    user = request.headers.get("X-User") or request.query_params.get("user") or "user"
    tx_id = request.headers.get("X-Transaction-ID") or request.query_params.get("transaction_id") or str(uuid.uuid4())
    source = request.headers.get("X-Source") or request.query_params.get("source") or "user"
    
    token_user = request_user.set(user)
    token_tx = request_transaction_id.set(tx_id)
    token_src = request_source.set(source)
    
    try:
        response = await call_next(request)
        return response
    finally:
        request_user.reset(token_user)
        request_transaction_id.reset(token_tx)
        request_source.reset(token_src)

# --- CORS Middleware Config ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Estimated-Content-Length", "X-Total-Rows"]
)

# --- Directory Watcher Integration ---
import sys
import os
# parsers 디렉토리를 sys.path에 추가하여 내부 임포트(advanced_ingester 등) 정합성 확보
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(script_dir, "parsers"))
# pyrefly: ignore [missing-import]
from directory_watcher import WorkspaceWatcher

# 전역 워처 인스턴스 (종료 시 접근 위함)
global_watcher: WorkspaceWatcher = None
global_config_watcher = None

@app.on_event("startup")
async def startup_event():
    global global_watcher, global_config_watcher
    import asyncio
    main_loop = asyncio.get_running_loop()
    
    # [최적화] table_config.json의 동적 스키마 실시간 변경을 감시하는 config watcher 시작
    try:
        from database.config_watcher import start_config_watcher
        global_config_watcher = start_config_watcher(engine)
        logger.info("Dynamic table config watcher started.")
    except Exception as e:
        logger.error(f"Failed to start config watcher: {e}")
    
    if os.getenv("TESTING") == "True":
        logger.info("Running in Testing mode. Skipping migrations, Directory Watcher and background Workers.")
        return
        
    try:
        # [Migration] NULL updated_at 보정 (coalesce 제거 및 성능 최적화 대비)
        from sqlalchemy import text
        with engine.connect() as conn:
            try:
                logger.info("Checking for NULL updated_at...")
                res = conn.execute(text("UPDATE data_rows SET updated_at = created_at WHERE updated_at IS NULL"))
                conn.commit()
                if res.rowcount > 0:
                    logger.info(f"Successfully updated {res.rowcount} rows.")
            except Exception as e:
                logger.error(f"Skip data_rows migration (table may not exist): {e}")
                
            # [Migration] database_outbox 테이블에 processed_chain 컬럼 보정
            try:
                conn.execute(text("ALTER TABLE database_outbox ADD COLUMN processed_chain BOOLEAN DEFAULT FALSE"))
                conn.commit()
                logger.info("Added processed_chain column to database_outbox.")
            except Exception:
                pass

        if os.getenv("DECOUPLED") == "True":
            logger.info("Decoupled mode active. Skipping inline Directory Watcher, Graph DB Sync, and Chained Ingestion workers.")
            return

        logger.info("Initializing Directory Watcher...")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        workspace_base = os.path.join(script_dir, "ingestion_workspace")
        
        def trigger_ws_refresh(table_name: str, count: int, created_logs: list = None):
            import json
            
            # 캐시 무효화
            invalidate_table_cache(table_name)
                
            msg = {
                "event": "batch_refresh_required",
                "table_name": table_name,
                "change_count": count
            }
            if created_logs and len(created_logs) <= 5000:
                msg["created_logs"] = created_logs
                
            # 스레드 안전하게 메인 이벤트 루프에 브로드캐스트 예약
            try:
                asyncio.run_coroutine_threadsafe(manager.broadcast(json.dumps(msg)), main_loop)
            except Exception as e:
                logger.error(f"Failed to broadcast refresh signal: {e}")

        def trigger_ws_file_processed(table_name: str, filename: str, status: str, error_msg: str = None):
            import json
            try:
                from pipeline_base import BasePipelineParser
                clean_filename = BasePipelineParser.get_basename(filename)
            except Exception:
                clean_filename = filename

            if status == "SUCCESS":
                message = f"{clean_filename} 파일이 처리되었습니다."
            else:
                message = f"{clean_filename} 파일 처리에 실패했습니다."
                if error_msg:
                    message += f" ({error_msg[:100]})"
            
            msg = {
                "event": "file_ingestion_completed",
                "table_name": table_name,
                "filename": clean_filename,
                "status": status,
                "message": message
            }
            try:
                asyncio.run_coroutine_threadsafe(manager.broadcast(json.dumps(msg)), main_loop)
            except Exception as e:
                logger.error(f"Failed to broadcast file ingestion completion: {e}")
                
        global_watcher = WorkspaceWatcher(
            workspace_base, 
            on_refresh_callback=trigger_ws_refresh,
            on_file_processed_callback=trigger_ws_file_processed
        )
        global_watcher.discover_and_watch()
        # 비차단 모드(blocking=False)로 기동
        global_watcher.start(blocking=False)
        logger.info(f"Directory Watcher started with {global_watcher.watch_count} watches.")
        
        # Start Graph DB Sync Worker
        from graph_sync_worker import start_graph_sync_worker
        main_loop.create_task(start_graph_sync_worker(SessionLocal))
        logger.info("Graph DB Sync Worker background task spawned.")
        
        # Start Chained Ingestion Worker
        from chain_ingestion_worker import start_chain_ingestion_worker
        main_loop.create_task(start_chain_ingestion_worker(SessionLocal))
        logger.info("Chained Ingestion Worker background task spawned.")
    except Exception as e:
        logger.error(f"Failed to start Directory Watcher: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    global global_watcher, global_config_watcher
    if global_config_watcher:
        logger.info("Stopping Config Watcher...")
        global_config_watcher.stop()
        global_config_watcher.join()
        logger.info("Config Watcher stopped.")
        
    if global_watcher and global_watcher.observer:
        logger.info("Stopping Directory Watcher...")
        global_watcher.observer.stop()
        global_watcher.observer.join()
        logger.info("Directory Watcher stopped.")
# --------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        logger.info(f"Broadcasting to {len(self.active_connections)} clients: {message[:100]}...")
        failed_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending to a client: {e}")
                failed_connections.append(connection)
        
        for conn in failed_connections:
            self.disconnect(conn)

manager = ConnectionManager()


@app.get("/")
def read_root(request: Request):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    client2_dist_path = os.path.abspath(os.path.join(script_dir, "..", "client2", "dist"))
    if not os.path.exists(client2_dist_path):
        client2_dist_path = os.path.join(script_dir, "dist")
        
    index_file = os.path.join(client2_dist_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"status": "AssyManager Data Server is running"}


@app.get("/api/download/client")
def download_desktop_client():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # client/dist/AssyManagerClient.exe (onefile mode output)
    client_exe_path = os.path.abspath(os.path.join(script_dir, "..", "client", "dist", "AssyManagerClient.exe"))
    
    if not os.path.exists(client_exe_path):
        # Fallback to directory mode path if onefile isn't generated
        fallback_path = os.path.abspath(os.path.join(script_dir, "..", "client", "dist", "AssyManagerClient", "AssyManagerClient.exe"))
        if os.path.exists(fallback_path):
            client_exe_path = fallback_path
            
    if not os.path.exists(client_exe_path):
        raise HTTPException(status_code=404, detail="Desktop client executable not found on server. Please build it first.")
        
    return FileResponse(
        client_exe_path, 
        media_type="application/octet-stream", 
        filename="AssyManagerClient.exe"
    )

import time
# [성능 최적화] 테이블별 전체 개수 캐시 (2초간 유효)
TABLE_COUNT_CACHE = {} # {table_name: (count, timestamp)}

def invalidate_table_cache(table_name: str):
    """
    해당 테이블과 관련된 모든 카운트 캐시(전체 개수, 검색 결과 개수 등)를 무효화합니다.
    """
    if not table_name: return
    
    # dictionary size changed error 방지를 위해 list로 변환하여 순회
    all_keys = list(TABLE_COUNT_CACHE.keys())
    # 1. 테이블명과 정확히 일치하거나, 2. 테이블명_ 으로 시작하는 모든 키 제거
    targets = [k for k in all_keys if k == table_name or k.startswith(f"{table_name}_")]
    
    for k in targets:
        TABLE_COUNT_CACHE.pop(k, None)
        
    if targets:
        print(f"[Cache] Invalidated {len(targets)} keys for table: {table_name}")


from datetime import timezone, datetime
import datetime as dt_pkg

# [성능 최적화] 타임존 객체 캐싱 (astimezone()의 시스템 호출 비용 절감)
LOCAL_TIMEZONE = dt_pkg.datetime.now(dt_pkg.timezone.utc).astimezone().tzinfo

def to_local_str(dt):
    """UTC 데이트타임을 현지 시간(Local) 문자열로 변환합니다."""
    if not dt: return ""
    ts_fmt = "%Y-%m-%d %H:%M:%S"
    # SQLite naive datetime assumes UTC. Force UTC if naive before conversion.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # [최적화] 캐시된 타임존 사용
    return dt.astimezone(LOCAL_TIMEZONE).strftime(ts_fmt)

def inject_system_columns(row):
    """
    UI에서 created_at, updated_at을 즉시 볼 수 있도록 data JSON에 가상으로 주입합니다.
    (Single row, Batch, Upsert 등 모든 경로에서 공통 사용)
    """
    if not row: return
    
    # 1. table_name 식별
    table_name = getattr(row, "table_name", None)
    if not table_name and hasattr(row, "__table__"):
        table_name = row.__table__.name
        
    cfg = crud.TABLE_CONFIG.get(table_name, {}) if table_name else {}
    col_types = cfg.get("column_types", {})
    user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]

    # 2. data 속성 동적 바인딩 및 기존 바인딩 시 정합성 동기화
    if not hasattr(row, "data") or row.data is None:
        r_data = {}
        for col in user_cols:
            val = getattr(row, col, None)
            # [정규화 스키마] native 값을 레거시 API 포맷으로 래핑
            r_data[col] = {"value": val, "is_overwrite": False, "sources": {}, "updated_by": "system"}
        row.data = r_data
    else:
        # [정합성 보장] row.data가 이미 있어도 DB 객체의 최신 속성값과 동기화 (비즈니스키 변경 등 반영)
        for col in user_cols:
            val = getattr(row, col, None)
            if col in row.data:
                if isinstance(row.data[col], dict):
                    row.data[col]["value"] = val
                else:
                    row.data[col] = {"value": val, "is_overwrite": False, "sources": {}, "updated_by": "system"}
            else:
                row.data[col] = {"value": val, "is_overwrite": False, "sources": {}, "updated_by": "system"}
        
    # 3. created_at 주입
    if "created_at" not in row.data:
        row.data["created_at"] = {
            "value": to_local_str(row.created_at), 
            "is_overwrite": False, 
            "updated_by": "system"
        }
    
    # 4. updated_at 주입 (없을 경우 created_at 사용)
    effective_update = row.updated_at if row.updated_at else row.created_at
    if "updated_at" not in row.data:
        row.data["updated_at"] = {
            "value": to_local_str(effective_update), 
            "is_overwrite": False, 
            "updated_by": "system"
        }
    else:
        # 데이터가 이미 있더라도 DB의 실제 값이 더 최신이므로 동기화
        row.data["updated_at"]["value"] = to_local_str(effective_update)


def fetch_and_merge_metadata(db: Session, table_name: str, rows: list, user_cols: list, include_sources: bool = True) -> list:
    """
    기본 데이터 테이블의 row 객체들에 cell_overwrites 및 cell_sources 정보를 병합하여 
    API 응답 포맷인 { value, is_overwrite, sources, updated_by } 딕셔너리로 합성합니다.
    include_sources=False이면 cell_sources 조회를 생략하여 대량 조회 성능을 최적화합니다.
    """
    if not rows:
        return []
        
    row_ids = [r.row_id for r in rows]
    
    # 1. cell_overwrites 일괄 로딩 (Tuple 쿼리로 ORM 인스턴스화 오버헤드 제거)
    overwrites = db.query(
        models.CellOverwrite.row_id,
        models.CellOverwrite.column_name,
        models.CellOverwrite.is_overwrite,
        models.CellOverwrite.updated_by,
        models.CellOverwrite.manual_priority_source
    ).filter(
        models.CellOverwrite.table_name == table_name,
        models.CellOverwrite.row_id.in_(row_ids)
    ).all()
    
    overwrites_map = {}
    for row_id, column_name, is_ow, updated_by, manual_priority_source in overwrites:
        overwrites_map[(row_id, column_name)] = (is_ow, updated_by, manual_priority_source)
        
    # 2. cell_sources 일괄 로딩 (include_sources가 True일 때만 실행)
    sources_map = {}
    if include_sources:
        sources = db.query(
            models.CellSource.row_id,
            models.CellSource.column_name,
            models.CellSource.source_name,
            models.CellSource.value
        ).filter(
            models.CellSource.table_name == table_name,
            models.CellSource.row_id.in_(row_ids)
        ).all()
        
        for row_id, column_name, source_name, value in sources:
            key = (row_id, column_name)
            if key not in sources_map:
                sources_map[key] = {}
            sources_map[key][source_name] = value

    data_list = []
    for row in rows:
        r_dict = row.__dict__
        r_id = r_dict.get("row_id") or row.row_id
        r_data = {}
        c_at_str = to_local_str(r_dict.get("created_at") or row.created_at)
        u_at_str = to_local_str(r_dict.get("updated_at") or row.updated_at)
        
        for col in user_cols:
            val_raw = r_dict.get(col) if col in r_dict else getattr(row, col, None)
            key = (r_id, col)
            
            ow_info = overwrites_map.get(key)
            col_srcs = sources_map.get(key, {})
            
            is_ow = ow_info[0] if ow_info else False
            updated_by = ow_info[1] if ow_info else "system"
            manual_pin = ow_info[2] if ow_info else None
            
            has_overwrite = is_ow or ("user" in col_srcs) or (manual_pin is not None)
            
            r_data[col] = {
                "value": val_raw,
                "is_overwrite": has_overwrite,
                "sources": col_srcs,
                "updated_by": updated_by
            }
            r_data[col]["manual_priority_source"] = manual_pin
                
        r_data["created_at"] = {"value": c_at_str, "is_overwrite": False, "sources": {}, "updated_by": "system"}
        r_data["updated_at"] = {"value": u_at_str, "is_overwrite": False, "sources": {}, "updated_by": "system"}
        
        # dynamic data attribute 바인딩
        row.data = r_data
        
        data_list.append({
            "row_id": r_id,
            "table_name": table_name,
            "data": r_data,
            "created_at": c_at_str,
            "updated_at": u_at_str
        })
        
    return data_list

@app.get("/tables")
def list_tables():
    """
    서버에 정의된 모든 테이블 목록을 반환합니다.
    """
    return {"tables": list(crud.TABLE_CONFIG.keys())}

def get_deleted_row_business_key(db: Session, table_name: str, row_id: str):
    # Try querying the business_key column directly from any AuditLog entry for this row
    log = db.query(models.AuditLog.business_key).filter(
        models.AuditLog.table_name == table_name,
        models.AuditLog.row_id == row_id,
        models.AuditLog.business_key.isnot(None)
    ).order_by(models.AuditLog.timestamp.desc()).first()
    if log and log[0]:
        return str(log[0])

    # Fallback: Query the AuditLog to find the value from past cell-level edits on key_col
    config = crud.TABLE_CONFIG.get(table_name, {})
    key_col = config.get("business_key")
    if key_col:
        fallback_log = db.query(models.AuditLog.new_value).filter(
            models.AuditLog.table_name == table_name,
            models.AuditLog.row_id == row_id,
            models.AuditLog.column_name == key_col
        ).order_by(models.AuditLog.timestamp.desc()).first()
        if fallback_log and fallback_log[0]:
            return str(fallback_log[0])
    return None

def check_rows_exist(db: Session, row_keys: list[tuple[str, str]]) -> set[tuple[str, str]]:
    from collections import defaultdict
    by_table = defaultdict(list)
    for t_name, r_id in row_keys:
        if t_name and r_id and r_id != "_BATCH_":
            by_table[t_name].append(r_id)
            
    existing_keys = set()
    for t_name, r_ids in by_table.items():
        table_model = models.DYNAMIC_TABLES.get(t_name)
        if table_model and r_ids:
            found = db.query(table_model.row_id).filter(table_model.row_id.in_(r_ids)).all()
            for (f_id,) in found:
                existing_keys.add((t_name, f_id))
    return existing_keys

from audit_cache import audit_cache

@app.get("/audit_logs/recent", response_model=list[schemas.AuditLogGroupResponse])
def get_recent_audit_logs(limit_groups: int = 100, db: Session = Depends(get_db)):
    # 1. 인메모리 캐시 로드 (최초 1회만 DB 조회)
    audit_cache.load_initial(db, limit_groups)
    
    # 2. 캐시된 그룹을 경량화하여 반환
    result = []
    # Collect keys to check existence
    keys_to_check = []
    for g in audit_cache.groups:
        logs = g.get("logs", [])
        if not logs: continue
        repr_log = logs[0]
        if repr_log.row_id != "_BATCH_":
            keys_to_check.append((repr_log.table_name, repr_log.row_id))
            
    existing_keys = check_rows_exist(db, keys_to_check)
    
    for g in audit_cache.groups:
        logs = g.get("logs", [])
        if not logs: continue
        
        # summary_columns 추출 (중복 제거)
        cols = []
        for l in logs:
            c = l.column_name
            if c and c not in cols:
                cols.append(c)
                
        # Populate is_row_deleted flag for representing log
        repr_log = logs[0].model_copy()
        is_deleted = repr_log.row_id != "_BATCH_" and (repr_log.table_name, repr_log.row_id) not in existing_keys
        repr_log.is_row_deleted = is_deleted
        
        if is_deleted and not repr_log.business_key:
            repr_log.business_key = get_deleted_row_business_key(db, repr_log.table_name, repr_log.row_id)
                
        result.append({
            "transaction_id": g.get("transaction_id"),
            "total_count": g.get("total_count", len(logs)),
            "summary_columns": cols,
            "logs": [repr_log] # 대표 로그 1건만 포함
        })
    return result

@app.get("/audit_logs/transaction/{tx_id}", response_model=schemas.AuditLogGroupResponse)
def get_transaction_logs(tx_id: str, db: Session = Depends(get_db), limit: int = 500):
    """특정 트랜잭션의 상세 로그를 반환합니다. (인메모리 캐시 우선 조회, 최대 limit 건 반환)"""

    # 1. 캐시에서 조회 시도
    if audit_cache.is_loaded:
        for g in audit_cache.groups:
            if g.get("transaction_id") == tx_id:
                logs = g.get("logs", [])
                cols = []
                
                # Check existences
                keys_to_check = []
                for l in logs[:limit]:
                    if l.row_id != "_BATCH_":
                        keys_to_check.append((l.table_name, l.row_id))
                existing_keys = check_rows_exist(db, keys_to_check)
                
                cloned_logs = []
                for l in logs[:limit]:
                    c = l.column_name
                    if c and c not in cols: cols.append(c)
                    cloned_log = l.model_copy()
                    is_deleted = cloned_log.row_id != "_BATCH_" and (cloned_log.table_name, cloned_log.row_id) not in existing_keys
                    cloned_log.is_row_deleted = is_deleted
                    if is_deleted and not cloned_log.business_key:
                        cloned_log.business_key = get_deleted_row_business_key(db, cloned_log.table_name, cloned_log.row_id)
                    cloned_logs.append(cloned_log)
                return {
                    "transaction_id": tx_id,
                    "total_count": g.get("total_count", len(logs)),
                    "summary_columns": cols,
                    "logs": cloned_logs
                }
                
    # 2. 캐시에 없으면 DB에서 직접 조회 (만약 오래된 트랜잭션을 클릭했다면)
    total_count = db.query(models.AuditLog).filter(models.AuditLog.transaction_id == tx_id).count()
    if total_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    db_logs = db.query(models.AuditLog)\
                .filter(models.AuditLog.transaction_id == tx_id)\
                .order_by(models.AuditLog.timestamp.desc(), models.AuditLog.id.desc())\
                .limit(limit)\
                .all()
                
    # Check existences
    keys_to_check = []
    for log_obj in db_logs:
        if log_obj.row_id != "_BATCH_":
            keys_to_check.append((log_obj.table_name, log_obj.row_id))
    existing_keys = check_rows_exist(db, keys_to_check)
    
    logs = []
    cols = []
    for log_obj in db_logs:
        log_dict = log_obj.__dict__.copy()
        log_model = schemas.AuditLogResponse.model_validate(log_dict)
        is_deleted = log_model.row_id != "_BATCH_" and (log_model.table_name, log_model.row_id) not in existing_keys
        log_model.is_row_deleted = is_deleted
        if is_deleted and not log_model.business_key:
            log_model.business_key = get_deleted_row_business_key(db, log_model.table_name, log_model.row_id)
        logs.append(log_model)
        c = log_model.column_name
        if c and c not in cols: cols.append(c)
        
    return {
        "transaction_id": tx_id,
        "total_count": total_count,
        "summary_columns": cols,
        "logs": logs
    }


@app.get("/dashboard/summary", response_model=schemas.DashboardSummaryResponse)
def get_dashboard_summary(db: Session = Depends(get_db)):
    """
    대시보드에 표시할 전역 통계 및 테이블별 현황을 반환합니다.
    """
    from datetime import datetime, date, timezone
    import sqlalchemy as sa
    
    table_names = list(crud.TABLE_CONFIG.keys())
    table_stats = []
    total_global_rows = 0
    
    for name in table_names:
        table_model = models.DYNAMIC_TABLES.get(name)
        if not table_model:
            continue
        # [최적화] 각 테이블의 행 개수 및 최신 업데이트 시간 조회
        count = db.query(sa.func.count(table_model.row_id)).scalar() or 0
        
        last_item = db.query(sa.func.max(sa.func.coalesce(table_model.updated_at, table_model.created_at))).scalar()
        
        table_stats.append(schemas.TableStat(
            table_name=name,
            row_count=count,
            last_updated=to_local_str(last_item) if last_item else "No Activity",
            status="Active" if (last_item and (datetime.now(timezone.utc) - (last_item.replace(tzinfo=timezone.utc) if last_item.tzinfo is None else last_item)).total_seconds() < 3600) else "Idle"
        ))
        total_global_rows += count

    # [신규] 테이블 정렬: 상태순(Active 우선) -> 이름순(A-Z)
    table_stats.sort(key=lambda x: (x.status != "Active", x.table_name))

    # 오늘의 업데이트 건수 (AuditLog 기준 - 각 항목이 셀 단위 수정임)
    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
    today_updates_count = db.query(models.AuditLog).filter(models.AuditLog.timestamp >= today_start).count()

    return schemas.DashboardSummaryResponse(
        total_tables=len(table_names),
        total_rows=total_global_rows,
        today_updates=today_updates_count,
        table_stats=table_stats,
        system_health="Excellent"
    )

def get_column_filter_condition(table_model, col_name: str, f_info: dict):
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy import cast, String, func, or_, and_
    
    # 1. Handle compound filter conditions (AND / OR)
    if "operator" in f_info:
        operator = f_info.get("operator")
        conditions = f_info.get("conditions", [])
        sqlalchemy_conds = []
        for cond_info in conditions:
            sub_cond = get_column_filter_condition(table_model, col_name, cond_info)
            if sub_cond is not None:
                sqlalchemy_conds.append(sub_cond)
        if not sqlalchemy_conds:
            return None
        return and_(*sqlalchemy_conds) if operator == "AND" else or_(*sqlalchemy_conds)
        
    # 2. Handle simple filter condition
    f_val = f_info.get("filter")
    f_type = f_info.get("type", "contains")
    
    # Allow blank/notBlank even if f_val is not present
    if f_type not in ["blank", "notBlank"] and f_val is None:
        return None
        
    # Column path resolution and numeric check
    is_numeric = False
    if col_name in ["created_at", "updated_at"]:
        target_col = table_model.created_at if col_name == "created_at" else table_model.updated_at
        col_expr = cast(target_col, String)
    elif col_name in ["row_id", "id"]:
        col_expr = table_model.row_id
    else:
        if not hasattr(table_model, col_name):
            return None
        raw_col = getattr(table_model, col_name)
        from sqlalchemy.sql.sqltypes import Numeric, Float, Integer
        is_numeric = isinstance(raw_col.type, (Numeric, Float, Integer))
        
        # Check if we should treat it as numeric filter
        numeric_operators = ["equals", "notEqual", "lessThan", "lessThanOrEqual", "greaterThan", "greaterThanOrEqual", "inRange"]
        if is_numeric and f_type in numeric_operators:
            col_expr = raw_col
        else:
            from sqlalchemy import cast, String
            col_expr = cast(raw_col, String)
            
    # Condition mapping based on type
    if f_type == "blank":
        if is_numeric:
            return col_expr.is_(None)
        else:
            return or_(col_expr.is_(None), col_expr == "")
    elif f_type == "notBlank":
        if is_numeric:
            return col_expr.isnot(None)
        else:
            return and_(col_expr.isnot(None), col_expr != "")
            
    if is_numeric and f_type in ["equals", "notEqual", "lessThan", "lessThanOrEqual", "greaterThan", "greaterThanOrEqual", "inRange"]:
        if f_type == "inRange":
            try:
                val_from = float(f_info.get("filter"))
                val_to = float(f_info.get("filterTo"))
                return and_(col_expr >= val_from, col_expr <= val_to)
            except (ValueError, TypeError):
                return None
        else:
            try:
                val = float(f_val)
            except (ValueError, TypeError):
                return None
            
            if f_type == "equals":
                return col_expr == val
            elif f_type == "notEqual":
                return col_expr != val
            elif f_type == "lessThan":
                return col_expr < val
            elif f_type == "lessThanOrEqual":
                return col_expr <= val
            elif f_type == "greaterThan":
                return col_expr > val
            elif f_type == "greaterThanOrEqual":
                return col_expr >= val
    else:
        # String comparison
        if f_type == "contains":
            return col_expr.ilike(f"%{f_val}%")
        elif f_type == "notContains":
            return ~col_expr.ilike(f"%{f_val}%")
        elif f_type == "equals":
            return col_expr == f_val
        elif f_type == "notEqual":
            return col_expr != f_val
        elif f_type == "startsWith":
            return col_expr.ilike(f"{f_val}%")
        elif f_type == "endsWith":
            return col_expr.ilike(f"%{f_val}")
        else:
            return col_expr.ilike(f"%{f_val}%")

# [Phase 73.12] 대량 데이터 조회 시 Pydantic 검증 오버헤드 제거를 위해 response_model 제거
@app.get("/tables/{table_name}/data")
def get_table_data(
    table_name: str, 
    skip: int = 0, 
    limit: int = 500, 
    q: str = None, 
    cols: str = None, 
    order_by: str = "row_id", 
    order_desc: bool = False,
    target_row_id: str = None, # [신규] 특정 행 위치 추적 점프 기능
    transaction_id: str = None, # [NEW] 특정 트랜잭션 결과만 필터링
    filters: str = None, # [NEW] AG-Grid 컬럼 필터링 조건
    db: Session = Depends(get_db)
):
    """
    Lazy Loading을 위한 페이징 엔드포인트
    target_row_id가 있으면 해당 행이 포함된 페이지의 skip을 자동으로 계산합니다.
    """
    t_total_start = time.time()
    t_target = 0.0
    t_count = 0.0
    
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
        
    query = db.query(table_model)
    
    # [NEW] 트랜잭션 필터링
    if transaction_id:
        subquery = db.query(models.AuditLog.row_id).filter(
            models.AuditLog.table_name == table_name,
            models.AuditLog.transaction_id == transaction_id
        )
        query = query.filter(table_model.row_id.in_(subquery))

    # [NEW] AG-Grid 컬럼 필터링
    if filters:
        try:
            import json
            filter_dict = json.loads(filters)
            for col_name, f_info in filter_dict.items():
                cond = get_column_filter_condition(table_model, col_name, f_info)
                if cond is not None:
                    query = query.filter(cond)
        except Exception as e:
            print(f"[Server] Failed to apply column filters: {e}")
    
    # ── [Step 0] 검색 필터 구성 (실제 컬럼 기준 ilike 다중 OR 검색) ──
    if q:
        from sqlalchemy import cast, String, or_, and_, func
        safe_q = q.replace("%", "\\%").replace("_", "\\_")
        
        cfg = crud.TABLE_CONFIG.get(table_name, {})
        col_types = cfg.get("column_types", {})
        
        if cols:
            col_list = [c.strip() for c in cols.split(",") if c.strip()]
        else:
            col_list = ["row_id", "business_key_val"] + [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]
            
        conditions = []
        for col in col_list:
            if col in ["created_at", "updated_at"]:
                target_col = table_model.created_at if col == "created_at" else table_model.updated_at
                conditions.append(cast(target_col, String).ilike(f"%{safe_q}%", escape="\\"))
            elif col in ["row_id", "id"]:
                conditions.append(table_model.row_id.ilike(f"%{safe_q}%", escape="\\"))
            elif col == "business_key_val":
                conditions.append(table_model.business_key_val.ilike(f"%{safe_q}%", escape="\\"))
            else:
                if hasattr(table_model, col):
                    conditions.append(cast(getattr(table_model, col), String).ilike(f"%{safe_q}%", escape="\\"))
        
        if conditions:
            query = query.filter(or_(*conditions))

    # ── [Step 1] 타겟 위치(Offset) 자동 계산 (Unified Jump) ──
    actual_target_offset = -1
    if target_row_id:
        # [Optimization] 타겟 행이 현재 검색 조건(query)에 부합하는지 PK를 활용해 초고속(1ms 이내) 검증
        target_row = query.filter(table_model.row_id == target_row_id).first()
        if not target_row:
            # [Task 4] DB에는 존재하지만 현재 검색 조건(query)에 맞지 않는 경우,
            # 무거운 count() 연산과 무의미한 데이터 페칭을 즉시 스킵하고 Fast-fail 응답을 반환합니다.
            # 이로 인해 클라이언트가 10초간 Nav Lock에 걸리는 현상을 방지합니다.
            print(f"[Server] Target {target_row_id} not found in query. Fast returning.")
            return {
                "total": 0,
                "data": [],
                "skip": skip,
                "limit": limit,
                "calculated_skip": skip,
                "target_offset": -1
            }
        
        if target_row:
            from sqlalchemy import func, or_, and_
            count_query = query
            
            if order_by == "updated_at":
                t_val = target_row.updated_at
                sort_expr = table_model.updated_at
                if order_desc: # DESC (최신순)
                    # 1. 시간이 더 최근이거나(sort_expr > t_val)
                    # 2. 시간이 같으면 row_id가 더 큰 행(DESC)이 앞에 오므로 row_id > target_row_id인 행을 카운트
                    count_query = count_query.filter(or_(sort_expr > t_val, and_(sort_expr == t_val, table_model.row_id > target_row_id)))
                else: # ASC
                    count_query = count_query.filter(or_(sort_expr < t_val, and_(sort_expr == t_val, table_model.row_id < target_row_id)))
            elif order_by == "id":
                t_bk = target_row.business_key_val
                if t_bk is None:
                    # NULLS LAST: NULL 행들은 값이 있는 행들 뒤에 위치함
                    count_query = count_query.filter(or_(
                        table_model.business_key_val.isnot(None),
                        and_(table_model.business_key_val.is_(None), table_model.row_id < target_row_id)
                    ))
                else:
                    if order_desc:
                        count_query = count_query.filter(or_(table_model.business_key_val > t_bk, and_(table_model.business_key_val == t_bk, table_model.row_id < target_row_id)))
                    else:
                        count_query = count_query.filter(or_(table_model.business_key_val < t_bk, and_(table_model.business_key_val == t_bk, table_model.row_id < target_row_id)))
            else:
                count_query = count_query.filter(table_model.row_id < target_row_id)
            t_tmp = time.time()
            actual_target_offset = count_query.count()
            t_target = time.time() - t_tmp
            # [Optimization] 웹 UI의 viewMode에 맞게 skip을 계산합니다.
            # pagination 모드(limit=500 등 대용량)인 경우 페이지 경계에 정렬(Align)하고,
            # infinite 모드(limit=100 등)인 경우 타겟이 중앙 부근에 오도록 배치합니다.
            if limit >= 500:
                skip = (actual_target_offset // limit) * limit
            else:
                skip = max(0, actual_target_offset - (limit // 2))
    
    # ── [Step 2] 데이터 페칭 및 개수 산출 (Optimization) ──
    # [Fix] transaction_id 필터링 시에도 캐시 정합성을 보장하기 위해 키에 포함
    cache_key_parts = [table_name, "total_count"]
    if q: cache_key_parts.append(f"q:{q}")
    if cols: cache_key_parts.append(f"cols:{cols}")
    if transaction_id: cache_key_parts.append(f"tx:{transaction_id}")
    if filters: cache_key_parts.append(f"filters:{filters}")
    cache_key = "|".join(cache_key_parts)
    cache_ttl = 5.0
    
    if cache_key in TABLE_COUNT_CACHE and (time.time() - TABLE_COUNT_CACHE[cache_key][1] < cache_ttl):
        total_count = TABLE_COUNT_CACHE[cache_key][0]
    else:
        t_tmp = time.time()
        total_count = query.count()
        t_count = time.time() - t_tmp
        TABLE_COUNT_CACHE[cache_key] = (total_count, time.time())
    
    from sqlalchemy.sql import func
    if order_by == "updated_at":
        sort_expr = table_model.updated_at.desc() if order_desc else table_model.updated_at.asc()
        tie_breaker = table_model.row_id.desc() if order_desc else table_model.row_id.asc()
        final_sort = [sort_expr, tie_breaker]
    elif order_by == "id":
        bk_sort = table_model.business_key_val.desc() if order_desc else table_model.business_key_val.asc()
        tie_breaker_bk = table_model.row_id.desc() if order_desc else table_model.row_id.asc()
        final_sort = [bk_sort, tie_breaker_bk]
    else:
        final_sort = [table_model.row_id.asc()]
    
    # ── [Step 2.5] Session Memory Optimization (Search Only) ──
    if q:
        # [Optimization] 검색 결과 정렬 시 External Merge Sort(디스크)를 방지하기 위해 
        # 현재 트랜잭션의 정렬 메모리(work_mem)를 일시적으로 크게 할당합니다.
        from sqlalchemy import text
        db.execute(text("SET LOCAL work_mem = '64MB'"))
    
    # ── [Step 3] 데이터 페칭 (2단계 인덱스 기반 페칭으로 원복) ──
    t_id_start = time.time()
    # 1. ID만 먼저 인덱스로 스캔 (Very Fast)
    id_results = query.with_entities(table_model.row_id).order_by(*final_sort).offset(skip).limit(limit).all()
    id_list = [r[0] for r in id_results]
    t_id_scan = time.time() - t_id_start
    
    t_row_start = time.time()
    
    cfg = crud.TABLE_CONFIG.get(table_name, {})
    col_types = cfg.get("column_types", {})
    user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]
    
    # [정규화 스키마] 통합 ORM 쿼리 (SQLite/PostgreSQL 공용)
    raw_rows = db.query(table_model).filter(table_model.row_id.in_(id_list)).all()
    id_to_idx = {rid: i for i, rid in enumerate(id_list)}
    raw_rows.sort(key=lambda x: id_to_idx.get(x.row_id, 999999))
    t_row_scan = time.time() - t_row_start
    
    t_dict_start = time.time()
    # [성능 최적화] 그리드 목록 조회에서는 cell_sources 로딩을 생략(include_sources=False)하여
    # 112K+ 소스 레코드 스캔으로 인한 2.4초 병목을 제거합니다.
    # 셀별 상세 소스는 기존 get_cell_sources API를 통해 온디맨드로 제공합니다.
    data_list = fetch_and_merge_metadata(db, table_name, raw_rows, user_cols, include_sources=False)
    t_dict = time.time() - t_dict_start
        
    t_total = time.time() - t_total_start
    
    logger.debug(f"[get_table_data] Total: {t_total:.3f}s | Target: {t_target:.3f}s | Count: {t_count:.3f}s | ID Scan: {t_id_scan:.3f}s | Entity Fetch: {t_row_scan:.3f}s | Dict Conv: {t_dict:.3f}s | skip={skip}, limit={limit}, order={order_by}, q={q}")
    
    return {
        "table_name": table_name, "total": total_count, "skip": skip, "limit": limit,
        "data": data_list, "calculated_skip": skip if target_row_id else None, "target_offset": actual_target_offset
    }

import json
from fastapi import HTTPException

@app.delete("/tables/{table_name}/rows/{row_id}")
async def delete_row(table_name: str, row_id: str, db: Session = Depends(get_db)):
    """
    행 삭제 엔드포인트
    """
    success = crud.delete_row(db, table_name, row_id)
    if not success:
        raise HTTPException(status_code=404, detail="Row not found")
        
    invalidate_table_cache(table_name)

    # Broadcast (Unified to batch_row_delete)
    msg = {
        "event": "batch_row_delete",
        "table_name": table_name,
        "row_ids": [row_id]
    }
    await manager.broadcast(json.dumps(msg))
    
    return {"status": "success", "row_id": row_id}

@app.post("/tables/{table_name}/rows/batch_delete")
async def delete_rows_batch_endpoint(table_name: str, batch: schemas.RowDeleteBatch, db: Session = Depends(get_db)):
    """여러 행을 물리적으로 삭제하고 브로드캐스트합니다."""
    deleted_count = crud.delete_rows_batch(db, table_name, batch.row_ids, batch.user_name)
    
    created_logs = []
    if deleted_count > 0:
        log_objs = db.query(models.AuditLog).filter(
            models.AuditLog.table_name == table_name,
            models.AuditLog.row_id.in_(batch.row_ids),
            models.AuditLog.column_name == "DELETE"
        ).all()
        for log in log_objs:
            bk = get_deleted_row_business_key(db, log.table_name, log.row_id)
            created_logs.append({
                "id": log.id,
                "table_name": log.table_name,
                "row_id": log.row_id,
                "column_name": log.column_name,
                "old_value": log.old_value,
                "new_value": log.new_value,
                "source_name": log.source_name,
                "updated_by": log.updated_by,
                "transaction_id": log.transaction_id,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "business_key": bk,
                "is_row_deleted": True
            })
            
        invalidate_table_cache(table_name)
        CHUNK_SIZE = 500
        for i in range(0, len(batch.row_ids), CHUNK_SIZE):
            chunk = batch.row_ids[i:i + CHUNK_SIZE]
            chunk_row_ids = set(chunk)
            chunk_logs = [log for log in created_logs if log["row_id"] in chunk_row_ids]
            msg = {
                "event": "batch_row_delete",
                "table_name": table_name,
                "row_ids": chunk,
                "updated_by": batch.user_name,
                "created_logs": chunk_logs
            }
            await manager.broadcast(json.dumps(msg))
        
    return {"status": "success", "deleted_count": deleted_count, "created_logs": created_logs}

@app.post("/tables/{table_name}/row_ids/target")
def get_target_row_ids(table_name: str, req: schemas.TargetedRowIdRequest, transaction_id: str = None, db: Session = Depends(get_db)):
    """Targeted RowID Scanner: 오프셋 리스트 기반 초고속 UUID 추출"""
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
        
    query = db.query(table_model)
    
    if transaction_id:
        subquery = db.query(models.AuditLog.row_id).filter(
            models.AuditLog.table_name == table_name,
            models.AuditLog.transaction_id == transaction_id
        )
        query = query.filter(table_model.row_id.in_(subquery))
    
    if req.q:
        from sqlalchemy import cast, String, or_, and_, func
        safe_q = req.q.replace("%", "\\%").replace("_", "\\_")
        
        cfg = crud.TABLE_CONFIG.get(table_name, {})
        col_types = cfg.get("column_types", {})
        
        if req.cols:
            col_list = [c.strip() for c in req.cols.split(",") if c.strip()]
        else:
            col_list = ["row_id", "business_key_val"] + [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]
            
        conditions = []
        for col in col_list:
            if col in ["created_at", "updated_at"]:
                target_col = table_model.created_at if col == "created_at" else table_model.updated_at
                conditions.append(cast(target_col, String).ilike(f"%{safe_q}%", escape="\\"))
            elif col in ["row_id", "id"]:
                conditions.append(table_model.row_id.ilike(f"%{safe_q}%", escape="\\"))
            elif col == "business_key_val":
                conditions.append(table_model.business_key_val.ilike(f"%{safe_q}%", escape="\\"))
            else:
                if hasattr(table_model, col):
                    conditions.append(cast(getattr(table_model, col), String).ilike(f"%{safe_q}%", escape="\\"))
        
        if conditions:
            query = query.filter(or_(*conditions))

    from sqlalchemy.sql import func
    if req.order_by == "updated_at":
        sort_expr = table_model.updated_at
        sort_expr = sort_expr.desc() if req.order_desc else sort_expr.asc()
        # [Fix] 메인 테이블과 동일한 Tie-breaker 방향 적용 (Index 성능 및 정합성)
        tie_breaker = table_model.row_id.desc() if req.order_desc else table_model.row_id.asc()
        query = query.order_by(sort_expr, tie_breaker)
    elif req.order_by == "id":
        bk_null_last = (table_model.business_key_val == None).asc()
        bk_sort = table_model.business_key_val.desc() if req.order_desc else table_model.business_key_val.asc()
        final_sort = [bk_null_last, bk_sort, table_model.row_id.asc()]
        query = query.order_by(*final_sort)
    else:
        sort_expr = table_model.row_id.asc()
        query = query.order_by(sort_expr)

    offsets = sorted(req.offsets)
    if not offsets:
        return {"row_ids": []}
        
    min_offset = offsets[0]
    max_offset = offsets[-1]
    limit = max_offset - min_offset + 1
    
    print(f"[Server] Scan Range: {min_offset} to {max_offset} (Total range count: {limit})")
    
    if limit > 50000:
        # 너무 큰 범위는 서버 보호를 위해 거절 (추후 Window Function 기반 정밀 쿼리로 고도화 필요)
        print(f"[Server] Scan rejected: Range {limit} exceeds safety limit of 50,000")
        return {"row_ids": [], "error": "Scan range too large"}

    # 튜플 단위 최적화 (딕셔너리 빌드 생략)
    results = query.with_entities(table_model.row_id).offset(min_offset).limit(limit).all()
    print(f"[Server] DB Query finished. Fetched {len(results)} row_id entities.")
    
    matched_ids = []
    for offset in req.offsets:
        local_idx = offset - min_offset
        if 0 <= local_idx < len(results):
            matched_ids.append(results[local_idx][0])
            
    return {"row_ids": matched_ids}


@app.get("/tables/{table_name}/export")
def export_table_csv(
    table_name: str, 
    q: str = None, 
    cols: str = None,
    order_by: str = "row_id",
    order_desc: bool = False,
    transaction_id: str = None, # [NEW] 트랜잭션 필터
    filters: str = None, # [NEW] 필터 지원
    db: Session = Depends(get_db)
):
    """
    현재 검색/정렬 조건에 맞는 데이터를 최대 100만 행까지 CSV로 스트리밍 추출합니다.
    """
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
        
    query = db.query(table_model)
    
    # [NEW] 트랜잭션 필터링
    if transaction_id:
        subquery = db.query(models.AuditLog.row_id).filter(
            models.AuditLog.table_name == table_name,
            models.AuditLog.transaction_id == transaction_id
        )
        query = query.filter(table_model.row_id.in_(subquery))

    # [NEW] AG-Grid 컬럼 필터링
    if filters:
        try:
            import json
            filter_dict = json.loads(filters)
            for col_name, f_info in filter_dict.items():
                cond = get_column_filter_condition(table_model, col_name, f_info)
                if cond is not None:
                    query = query.filter(cond)
        except Exception as e:
            print(f"[Server] Failed to apply column filters in export: {e}")
    
    # [Filter] get_table_data와 검색 로직 동기화
    if q:
        from sqlalchemy import cast, String, or_, and_, func
        safe_q = q.replace("%", "\\%").replace("_", "\\_")
        
        cfg = crud.TABLE_CONFIG.get(table_name, {})
        col_types = cfg.get("column_types", {})
        
        if cols:
            col_list = [c.strip() for c in cols.split(",") if c.strip()]
        else:
            col_list = ["row_id", "business_key_val"] + [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]
            
        conditions = []
        for col in col_list:
            if col in ["created_at", "updated_at"]:
                target_col = table_model.created_at if col == "created_at" else table_model.updated_at
                conditions.append(cast(target_col, String).ilike(f"%{safe_q}%", escape="\\"))
            elif col in ["row_id", "id"]:
                conditions.append(table_model.row_id.ilike(f"%{safe_q}%", escape="\\"))
            elif col == "business_key_val":
                conditions.append(table_model.business_key_val.ilike(f"%{safe_q}%", escape="\\"))
            else:
                if hasattr(table_model, col):
                    conditions.append(cast(getattr(table_model, col), String).ilike(f"%{safe_q}%", escape="\\"))
        
        if conditions:
            query = query.filter(or_(*conditions))

    # [Sort] 정렬 조건 동기화
    from sqlalchemy.sql import func
    if order_by == "updated_at":
        sort_expr = table_model.updated_at.desc() if order_desc else table_model.updated_at.asc()
        tie_breaker = table_model.row_id.desc() if order_desc else table_model.row_id.asc()
        final_sort = [sort_expr, tie_breaker]
    elif order_by == "id":
        bk_sort = table_model.business_key_val.desc() if order_desc else table_model.business_key_val.asc()
        tie_breaker_bk = table_model.row_id.desc() if order_desc else table_model.row_id.asc()
        final_sort = [bk_sort, tie_breaker_bk]
    else:
        final_sort = [table_model.row_id.asc()]

    # 1. 헤더 구성
    cfg = crud.TABLE_CONFIG.get(table_name, {})
    col_types = cfg.get("column_types", {})
    business_cols = [c for c in sorted(col_types.keys()) if c not in ["created_at", "updated_at"]]
    header = business_cols + ["created_at", "updated_at"]

    # [정규화 스키마] native 컬럼을 직접 SELECT하여 JSONB 파싱 부하 완전 제거
    select_entities = []
    for col in business_cols:
        select_entities.append(getattr(table_model, col).label(col))
    
    select_entities.append(table_model.created_at)
    select_entities.append(table_model.updated_at)

    # 2. 크기 샘플링 예측 (초기 10행 기반 정밀 추산)
    # [Performance Optimization] 전체 테이블을 읽지 않고 limit(10)만 지정하여 메모리 로드 비용 격감
    sample_query = query.with_entities(*select_entities).limit(10)
    sample_rows = db.execute(sample_query.statement).fetchall()
    
    sample_io = io.StringIO()
    sample_writer = csv.writer(sample_io)
    
    tz = LOCAL_TIMEZONE
    ts_fmt = "%Y-%m-%d %H:%M:%S"
    
    for row in sample_rows:
        created_at = row[-2]
        updated_at = row[-1]
        eff_upd = updated_at if updated_at else created_at
        c_at_s = created_at.replace(tzinfo=timezone.utc).astimezone(tz).strftime(ts_fmt) if created_at else ""
        u_at_s = eff_upd.replace(tzinfo=timezone.utc).astimezone(tz).strftime(ts_fmt) if eff_upd else ""
        
        row_v = [r if r is not None else "" for r in row[:-2]]
        row_v.append(c_at_s)
        row_v.append(u_at_s)
        sample_writer.writerow(row_v)
        
    sample_bytes = len(sample_io.getvalue().encode("utf-8"))
    avg_row_size = sample_bytes / len(sample_rows) if sample_rows else 150
    header_size = len("\ufeff".encode("utf-8")) + len(",".join(header).encode("utf-8")) + 2
    
    # [Performance Optimization] 빠른 카운트(SELECT COUNT(*))만 실행하여 헤더 준비 속도 극대화
    total_count = query.count()
    total_count = min(total_count, 1000000)
    estimated_total_size = int(header_size + (avg_row_size * total_count))

    def generate():
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Excel 인식을 위한 BOM 추가
        output.write('\ufeff')
        writer.writerow(header)
        yield output.getvalue()
        output.seek(0); output.truncate(0)

        # ── [Optimization] 서버사이드 커서(yield_per)를 활용하여 Offset 없이 선형 속도(Constant Speed) 스트리밍 ──
        batch_size = 5000
        
        # Datetime formatting cache to eliminate redundant tz conversions and formatting (bounded to 10k items)
        date_cache = {}
        def format_date(dt):
            if dt is None:
                return ""
            if dt in date_cache:
                return date_cache[dt]
            formatted = dt.replace(tzinfo=timezone.utc).astimezone(tz).strftime(ts_fmt)
            if len(date_cache) < 10000:
                date_cache[dt] = formatted
            return formatted

        # SQL 레벨 가상 컬럼 분해 쿼리 생성 (stream_results=True 옵션으로 PostgreSQL 서버사이드 커서 강제화)
        export_query = query.with_entities(*select_entities)\
                            .order_by(*final_sort)\
                            .execution_options(stream_results=True)

        # yield_per(batch_size)는 내부적으로 단 하나의 서버사이드 커서를 사용하여 offset 오버헤드 없이 순차적으로 스트리밍합니다.
        batch_counter = 0
        for row in export_query.yield_per(batch_size):
            created_at = row[-2]
            updated_at = row[-1]
            
            # 비즈니스 컬럼 값은 그대로 로드 (이미 SQL 레벨에서 분해됨)
            row_vals = [r if r is not None else "" for r in row[:-2]]
            
            # 시스템 컬럼 날짜 포맷 캐시 활용
            effective_update = updated_at if updated_at else created_at
            row_vals.append(format_date(created_at))
            row_vals.append(format_date(effective_update))
            
            writer.writerow(row_vals)
            batch_counter += 1
            
            # 5,000행 단위로만 StringIO 문자열을 빌드하여 yield하므로 row-by-row string compilation 부하 5,000배 격감
            if batch_counter >= batch_size:
                yield output.getvalue()
                output.seek(0); output.truncate(0)
                batch_counter = 0
        
        # 남은 데이터 송신
        if batch_counter > 0:
            yield output.getvalue()

    filename = f"{table_name}_extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "X-Estimated-Content-Length": str(estimated_total_size),
        "X-Total-Rows": str(total_count)
    }
    return StreamingResponse(generate(), media_type="text/csv", headers=headers)



@app.get("/tables/{table_name}/schema")
def get_table_schema(table_name: str, db: Session = Depends(get_db)):
    """
    테이블의 컬럼 스키마 정보를 반환합니다.
    """
    config = crud.TABLE_CONFIG.get(table_name, {})
    columns = config.get("display_columns")
    
    if not columns:
        # 데이터에서 동적 추출 (Fallback)
        table_model = models.DYNAMIC_TABLES.get(table_name)
        if table_model:
            columns = [c.name for c in table_model.__table__.columns if c.name not in ["row_id", "business_key_val", "created_at", "updated_at"]]
        else:
            columns = []
            
    # [버그 수정] display_columns 정의 여부와 관계없이 시스템 컬럼은 항상 마지막에 보장
    system_cols = ["created_at", "updated_at"]
    for sc in system_cols:
        if sc not in columns:
            columns.append(sc)
            
    return {
        "table_name": table_name,
        "columns": columns,
        "column_types": config.get("column_types", {}),
        "business_key": config.get("business_key", ""),
        "composite_key_source": config.get("composite_key_source", [])
    }



@app.get("/tables/{table_name}/{row_id}", response_model=schemas.DataRowResponse)
def get_row_data(table_name: str, row_id: str, db: Session = Depends(get_db)):
    """
    특정 행의 데이터를 가져옵니다.
    """
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        raise HTTPException(status_code=404, detail="Table not found")
        
    row = db.query(table_model).filter(table_model.row_id == row_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Row not found")
        
    # Format dates and build data dict (matching get_table_data formatting)
    c_at_str = to_local_str(row.created_at)
    u_at_str = to_local_str(row.updated_at)
    
    cfg = crud.TABLE_CONFIG.get(table_name, {})
    col_types = cfg.get("column_types", {})
    user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]
    
    # [정규화 스키마] 단일 행은 cell_sources 포함하여 완전한 메타데이터를 반환
    data_list = fetch_and_merge_metadata(db, table_name, [row], user_cols, include_sources=True)
    if data_list:
        return data_list[0]
    
    return {
        "row_id": row.row_id,
        "table_name": table_name,
        "data": {},
        "created_at": row.created_at,
        "updated_at": row.updated_at
    }


@app.get("/tables/{table_name}/rows/{row_id}/history", response_model=list[schemas.AuditLogResponse])
def get_row_history(table_name: str, row_id: str, db: Session = Depends(get_db)):
    """
    특정 행의 모든 변경 이력을 가져옵니다.
    """
    logs = db.query(models.AuditLog).filter(
        models.AuditLog.table_name == table_name,
        models.AuditLog.row_id == row_id
    ).order_by(models.AuditLog.timestamp.desc()).all()
    
    table_model = models.DYNAMIC_TABLES.get(table_name)
    row_obj = None
    if table_model:
        row_obj = db.query(table_model).filter(table_model.row_id == row_id).first()
        
    row_exists = row_obj is not None
    bk_val = row_obj.business_key_val if row_exists else get_deleted_row_business_key(db, table_name, row_id)
    
    result = []
    for log in logs:
        log_res = schemas.AuditLogResponse.model_validate(log)
        log_res.is_row_deleted = not row_exists
        log_res.business_key = log.business_key or bk_val
        result.append(log_res)
    return result

@app.get("/tables/{table_name}/rows/{row_id}/cells/{col_name}/history", response_model=list[schemas.AuditLogResponse])
def get_cell_history(table_name: str, row_id: str, col_name: str, db: Session = Depends(get_db)):
    """
    특정 셀의 변경 이력을 가져옵니다.
    """
    logs = db.query(models.AuditLog).filter(
        models.AuditLog.table_name == table_name,
        models.AuditLog.row_id == row_id,
        models.AuditLog.column_name == col_name
    ).order_by(models.AuditLog.timestamp.desc()).all()
    
    table_model = models.DYNAMIC_TABLES.get(table_name)
    row_obj = None
    if table_model:
        row_obj = db.query(table_model).filter(table_model.row_id == row_id).first()
        
    row_exists = row_obj is not None
    bk_val = row_obj.business_key_val if row_exists else get_deleted_row_business_key(db, table_name, row_id)
    
    result = []
    for log in logs:
        log_res = schemas.AuditLogResponse.model_validate(log)
        log_res.is_row_deleted = not row_exists
        log_res.business_key = log.business_key or bk_val
        result.append(log_res)
    return result

@app.post("/tables/{table_name}/rows")
async def create_row(table_name: str, count: int = 1, user_name: str = "system", db: Session = Depends(get_db)):
    """
    신규 행 추가 엔드포인트 (단건 및 다건 지원)
    """
    new_rows = crud.create_empty_rows_batch(db, table_name, count, user_name)
    
    created_logs = []
    if new_rows:
        invalidate_table_cache(table_name)
        log_objs = db.query(models.AuditLog).filter(
            models.AuditLog.table_name == table_name,
            models.AuditLog.row_id.in_([r.row_id for r in new_rows]),
            models.AuditLog.column_name == "CREATE"
        ).all()
        for log in log_objs:
            created_logs.append({
                "id": log.id,
                "table_name": log.table_name,
                "row_id": log.row_id,
                "column_name": log.column_name,
                "old_value": log.old_value,
                "new_value": log.new_value,
                "source_name": log.source_name,
                "updated_by": log.updated_by,
                "transaction_id": log.transaction_id,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "business_key": log.business_key
            })
    
    msg_items = []
    for row in new_rows:
        inject_system_columns(row)
        msg_items.append({
            "row_id": row.row_id,
            "table_name": table_name,
            "data": row.data
        })
    
    # WebSocket 브로드캐스트 (대량 작업 시 500개씩 청크 분할 전송하여 메모리/통신 안정성 확보)
    CHUNK_SIZE = 500
    for i in range(0, len(msg_items), CHUNK_SIZE):
        chunk = msg_items[i:i + CHUNK_SIZE]
        chunk_row_ids = {item["row_id"] for item in chunk}
        chunk_logs = [log for log in created_logs if log["row_id"] in chunk_row_ids]
        msg = {
            "event": "batch_row_create",
            "table_name": table_name,
            "items": chunk,
            "updated_by": user_name,
            "created_logs": chunk_logs
        }
        await manager.broadcast(json.dumps(msg))
    
    return {"status": "success", "count": len(new_rows), "row_ids": [r.row_id for r in new_rows], "created_logs": created_logs}

@app.put("/tables/{table_name}/data/updates")
async def apply_batch_updates_endpoint(table_name: str, batch: schemas.GeneralUpdateBatch, db: Session = Depends(get_db)):
    """단건 및 다건 업데이트를 통합 처리하고 브로드캐스트합니다."""
    from fastapi.concurrency import run_in_threadpool
    try:
        results, changed_cells, created_logs = await run_in_threadpool(crud.apply_batch_updates, db, table_name, batch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if results:
        invalidate_table_cache(table_name)
    
    msg_items = []
    for row, is_new in results:
        # Agent D v16: 브로드캐스트 페이로드에 시간 메타데이터(created_at, updated_at)를 강제 주입
        inject_system_columns(row)
        msg_items.append({
            "row_id": row.row_id,
            "is_new": is_new,
            "data": row.data,
            "created_at": to_local_str(row.created_at),
            "updated_at": to_local_str(row.updated_at)
        })
    
    # WebSocket 브로드캐스트 (batch.silent가 False인 경우에만 수행)
    if not batch.silent:
        user_name = batch.updates[0].updated_by if batch.updates else "system"
        tx_id = created_logs[0]["transaction_id"] if created_logs else (batch.transaction_id or str(uuid.uuid4()))
        
        if len(msg_items) > 100:
            # 대량 업데이트: 경량화된 새로고침 신호만 전송
            msg = {
                "event": "batch_refresh_required",
                "table_name": table_name,
                "change_count": len(msg_items)
            }
            if created_logs and len(created_logs) <= 5000:
                msg["created_logs"] = created_logs
            await manager.broadcast(json.dumps(msg))
        else:
            # 소량 업데이트: 전체 데이터 전송
            CHUNK_SIZE = 500
            for i in range(0, len(msg_items), CHUNK_SIZE):
                chunk = msg_items[i:i + CHUNK_SIZE]
                chunk_row_ids = {item["row_id"] for item in chunk}
                chunk_logs = [log for log in created_logs if log["row_id"] in chunk_row_ids]
                msg = {
                    "event": "batch_row_upsert",
                    "table_name": table_name,
                    "items": chunk,
                    "change_count": len(chunk), 
                    "updated_by": user_name,
                    "transaction_id": tx_id,
                    "created_logs": chunk_logs
                }
                await manager.broadcast(json.dumps(msg))
    
    return {"status": "success", "updated_count": len(results), "change_count": len(changed_cells), "created_logs": created_logs}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # [Phase 73.8] 클라이언트로부터의 메시지 수신 대기 (필요 시 로직 확장 가능)
            data = await websocket.receive_text()
            # 에코(Echo) 브로드캐스트 제거 (프로덕션 노이즈 방지)
            print(f"[WS] Received client msg: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/tables/{table_name}/upload")
async def upload_file(table_name: str, user: str = "Unknown", file: UploadFile = File(...)):
    """
    클라이언트에서 보낸 로그 파일을 수신하여 해당 테이블의 인제션 워크스페이스(raws/)에 저장합니다.
    저장 시 directory_watcher.py가 이를 감지하여 자동으로 파싱을 시작합니다.
    """
    # 1. 대상 디렉토리 결정 (server/ingestion_workspace/{table_name}/raws)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.join(base_dir, "ingestion_workspace", table_name, "raws")
    
    # 2. 디렉토리가 없으면 생성 (setup_workspace.py가 미리 생성해두지만 안전을 위해)
    os.makedirs(target_dir, exist_ok=True)
    
    # 2. 파일명 중복 방지 (기존명_UUID.ext) + 업로더 정보(user) 인코딩
    orig_name, ext = os.path.splitext(file.filename)
    unique_name = f"user({user})_{orig_name}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(target_dir, unique_name)
    
    # 3. 파일 저장
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        return {"status": "success", "filename": file.filename, "path": file_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

@app.get("/tables/{table_name}/{row_id}/{col_name}/sources")
async def get_cell_sources(table_name: str, row_id: str, col_name: str, db: Session = Depends(get_db)):
    """특정 셀에 중첩된 모든 데이터 원천(Sources) 정보를 반환합니다."""
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
        
    row = db.query(table_model).filter(table_model.row_id == row_id).first()
    if not row or not hasattr(table_model, col_name):
        raise HTTPException(status_code=404, detail="Cell not found")
        
    cell_sources = db.query(models.CellSource).filter(
        models.CellSource.table_name == table_name,
        models.CellSource.row_id == row_id,
        models.CellSource.column_name == col_name
    ).all()
    
    ow = db.query(models.CellOverwrite).filter(
        models.CellOverwrite.table_name == table_name,
        models.CellOverwrite.row_id == row_id,
        models.CellOverwrite.column_name == col_name
    ).first()
    
    sources_dict = {
        s.source_name: {
            "value": s.value,
            "timestamp": s.ingested_at.isoformat() if s.ingested_at else None,
            "updated_by": s.updated_by
        }
        for s in cell_sources
    }
    
    manual_priority_source = ow.manual_priority_source if ow else None
    
    _, priority_source = crud.compute_priority_value(sources_dict, manual_priority_source)
    
    return {
        "sources": sources_dict,
        "manual_priority_source": manual_priority_source,
        "priority_source": priority_source,
        "value": getattr(row, col_name)
    }

@app.delete("/tables/{table_name}/{row_id}/{col_name}/sources/{source_name}")
async def delete_cell_source(table_name: str, row_id: str, col_name: str, source_name: str, db: Session = Depends(get_db)):
    """특정 셀의 특정 원천 데이터를 삭제합니다."""
    updated_row, changed_cols = crud.delete_cell_source(db, table_name, row_id, col_name, source_name)
    if not updated_row:
        raise HTTPException(status_code=404, detail="Source or Cell not found")
    
    inject_system_columns(updated_row)
    # WebSocket 브로드캐스트 (통합 규격: batch_row_upsert 사용)
    await manager.broadcast(json.dumps({
        "event": "batch_row_upsert",
        "table_name": table_name,
        "items": [{
            "row_id": row_id, 
            "is_new": False, 
            "data": updated_row.data,
            "created_at": to_local_str(updated_row.created_at),
            "updated_at": to_local_str(updated_row.updated_at)
        }],
        "change_count": len(changed_cols)
    }))
    return {"status": "success", "row_id": row_id}

@app.put("/tables/{table_name}/{row_id}/{col_name}/priority")
async def set_cell_priority(
    table_name: str, row_id: str, col_name: str, 
    source_name: Optional[str] = Body(None, embed=True), 
    updated_by: str = Body("user", embed=True),
    db: Session = Depends(get_db)
):
    """특정 셀의 표시 우선순위 소스를 수동으로 지정합니다 (Pin). source_name이 null이면 수동 지정 해제."""
    updated_row, changed_cols = crud.set_cell_manual_priority(db, table_name, row_id, col_name, source_name, updated_by)
    if not updated_row:
        raise HTTPException(status_code=404, detail="Cell not found or source invalid")
    
    cfg = crud.TABLE_CONFIG.get(table_name, {})
    col_types = cfg.get("column_types", {})
    user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]
    
    merged_rows = fetch_and_merge_metadata(db, table_name, [updated_row], user_cols, include_sources=True)
    if not merged_rows:
        raise HTTPException(status_code=500, detail="Failed to serialize updated row")
        
    merged_item = merged_rows[0]
    
    # WebSocket 브로드캐스트 (통합 규격: batch_row_upsert 사용)
    await manager.broadcast(json.dumps({
        "event": "batch_row_upsert",
        "table_name": table_name,
        "items": [{
            "row_id": row_id, 
            "is_new": False, 
            "data": merged_item["data"],
            "created_at": merged_item["created_at"],
            "updated_at": merged_item["updated_at"]
        }],
        "change_count": len(changed_cols)
    }))
    return {"status": "success", "row_id": row_id}

@app.get("/tables/{table_name}/rows/{row_id}/cells/{col_name}/history")
async def get_cell_history(table_name: str, row_id: str, col_name: str, db: Session = Depends(get_db)):
    """특정 셀의 변경 이력(AuditLog)을 조회합니다."""
    logs = db.query(models.AuditLog).filter(
        models.AuditLog.table_name == table_name,
        models.AuditLog.row_id == row_id,
        models.AuditLog.column_name == col_name
    ).order_by(desc(models.AuditLog.timestamp)).all()
    
    return logs

@app.put("/tables/{table_name}/cells/priority/batch")
async def set_cell_priority_batch_endpoint(
    table_name: str,
    req: schemas.BatchCellPriorityRequest,
    db: Session = Depends(get_db)
):
    """여러 셀의 표시 우선순위 소스를 수동으로 일괄 지정합니다 (Pin)."""
    changed_rows, created_logs = crud.set_cell_manual_priority_batch(
        db, table_name, req.updates, req.source_name, req.updated_by
    )
    
    if changed_rows:
        invalidate_table_cache(table_name)
        
        cfg = crud.TABLE_CONFIG.get(table_name, {})
        col_types = cfg.get("column_types", {})
        user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]
        
        merged_items = fetch_and_merge_metadata(db, table_name, changed_rows, user_cols, include_sources=True)
        
        # WebSocket 브로드캐스트 (통합 규격: batch_row_upsert 사용)
        msg_items = [{
            "row_id": item["row_id"],
            "is_new": False,
            "data": item["data"],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"]
        } for item in merged_items]
        
        if len(msg_items) > 100:
            # 대량 업데이트: 경량화된 새로고침 신호만 전송
            msg = {
                "event": "batch_refresh_required",
                "table_name": table_name,
                "change_count": len(msg_items)
            }
            if created_logs and len(created_logs) <= 5000:
                msg["created_logs"] = created_logs
            await manager.broadcast(json.dumps(msg))
        else:
            # Split into chunks of 500
            CHUNK_SIZE = 500
            for i in range(0, len(msg_items), CHUNK_SIZE):
                chunk = msg_items[i:i + CHUNK_SIZE]
                chunk_row_ids = {item["row_id"] for item in chunk}
                chunk_logs = [log for log in created_logs if log["row_id"] in chunk_row_ids]
                await manager.broadcast(json.dumps({
                    "event": "batch_row_upsert",
                    "table_name": table_name,
                    "items": chunk,
                    "change_count": len(chunk),
                    "created_logs": chunk_logs
                }))
            
    return {"status": "success", "count": len(changed_rows)}

@app.post("/tables/{table_name}/cells/sources/delete/batch")
async def delete_cell_source_batch_endpoint(
    table_name: str,
    req: schemas.BatchCellSourceDeleteRequest,
    db: Session = Depends(get_db)
):
    """여러 셀의 특정 데이터 원천(Source)을 일괄 삭제합니다."""
    changed_rows, created_logs = crud.delete_cell_source_batch(
        db, table_name, req.cells, req.source_name
    )
    
    if changed_rows:
        invalidate_table_cache(table_name)
        
        cfg = crud.TABLE_CONFIG.get(table_name, {})
        col_types = cfg.get("column_types", {})
        user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]
        
        merged_items = fetch_and_merge_metadata(db, table_name, changed_rows, user_cols, include_sources=True)
        
        # WebSocket 브로드캐스트 (통합 규격: batch_row_upsert 사용)
        msg_items = [{
            "row_id": item["row_id"],
            "is_new": False,
            "data": item["data"],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"]
        } for item in merged_items]
        
        if len(msg_items) > 100:
            # 대량 업데이트: 경량화된 새로고침 신호만 전송
            msg = {
                "event": "batch_refresh_required",
                "table_name": table_name,
                "change_count": len(msg_items)
            }
            if created_logs and len(created_logs) <= 5000:
                msg["created_logs"] = created_logs
            await manager.broadcast(json.dumps(msg))
        else:
            # Split into chunks of 500
            CHUNK_SIZE = 500
            for i in range(0, len(msg_items), CHUNK_SIZE):
                chunk = msg_items[i:i + CHUNK_SIZE]
                chunk_row_ids = {item["row_id"] for item in chunk}
                chunk_logs = [log for log in created_logs if log["row_id"] in chunk_row_ids]
                await manager.broadcast(json.dumps({
                    "event": "batch_row_upsert",
                    "table_name": table_name,
                    "items": chunk,
                    "change_count": len(chunk),
                    "created_logs": chunk_logs
                }))
            
    return {"status": "success", "count": len(changed_rows)}

@app.post("/tables/{table_name}/cells/sources/query")
def query_cells_sources(
    table_name: str,
    req: schemas.BatchCellPriorityRequest,
    db: Session = Depends(get_db)
):
    """여러 셀의 데이터 원천(Sources) 정보를 일괄 조회합니다."""
    row_ids = list(set(item.get("row_id") for item in req.updates if item.get("row_id")))
    col_names = list(set(item.get("column_name") for item in req.updates if item.get("column_name")))
    
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        raise HTTPException(status_code=404, detail="Table not found")
        
    rows = db.query(table_model).filter(
        table_model.row_id.in_(row_ids)
    ).all()
    row_map = {r.row_id: r for r in rows}
    
    # [정규화 스키마] N+1 문제를 방지하기 위해 단 2개의 배치 쿼리로 원천 데이터와 오버라이트 정보 일괄 로드
    cell_sources = db.query(models.CellSource).filter(
        models.CellSource.table_name == table_name,
        models.CellSource.row_id.in_(row_ids),
        models.CellSource.column_name.in_(col_names)
    ).all()
    
    sources_map = {}
    for s in cell_sources:
        key = (s.row_id, s.column_name)
        if key not in sources_map:
            sources_map[key] = {}
        sources_map[key][s.source_name] = {
            "value": s.value,
            "timestamp": s.ingested_at.isoformat() if s.ingested_at else None,
            "updated_by": s.updated_by
        }
        
    overwrites = db.query(models.CellOverwrite).filter(
        models.CellOverwrite.table_name == table_name,
        models.CellOverwrite.row_id.in_(row_ids),
        models.CellOverwrite.column_name.in_(col_names)
    ).all()
    
    overwrites_map = {}
    for ow in overwrites:
        key = (ow.row_id, ow.column_name)
        overwrites_map[key] = ow.manual_priority_source
        
    result = []
    for item in req.updates:
        row_id = item.get("row_id")
        col_name = item.get("column_name")
        if not row_id or not col_name:
            continue
            
        row = row_map.get(row_id)
        if not row or not hasattr(table_model, col_name):
            result.append({
                "row_id": row_id,
                "column_name": col_name,
                "sources": {},
                "manual_priority_source": None,
                "priority_source": None,
                "value": None
            })
            continue
            
        key = (row_id, col_name)
        sources_dict = sources_map.get(key, {})
        manual_priority_source = overwrites_map.get(key)
        
        _, priority_source = crud.compute_priority_value(sources_dict, manual_priority_source)
        
        result.append({
            "row_id": row_id,
            "column_name": col_name,
            "sources": sources_dict,
            "manual_priority_source": manual_priority_source,
            "priority_source": priority_source,
            "value": getattr(row, col_name)
        })
        
    return result

@app.post("/admin/outbox/retry-failed")
def retry_failed_outbox_events(event_id: int = None, transaction_id: str = None, db: Session = Depends(get_db)):
    """
    실패(FAILED) 상태인 Outbox 체인 이벤트를 
    다시 대기열(PENDING)로 원복하여 재시도하도록 리셋합니다.
    """
    from datetime import datetime
    query = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.status == "FAILED"
    )
    failed_events = query.all()
    
    if event_id is not None:
        failed_events = [e for e in failed_events if e.id == event_id]
    elif transaction_id is not None:
        failed_events = [
            e for e in failed_events 
            if (e.payload.get("transaction_id") == transaction_id if e.payload else False) or
               (f"single_{e.event_uuid}" == transaction_id)
        ]
        
    if not failed_events:
        return {"status": "success", "message": "No matching failed outbox events found."}
        
    for event in failed_events:
        event.status = "PENDING"
        event.retry_count = 0
        event.processed_chain = False
        if event.payload and "error_log" in event.payload:
            payload_copy = dict(event.payload)
            payload_copy["error_log"] = dict(payload_copy["error_log"])
            payload_copy["error_log"]["resolved_at"] = datetime.now().isoformat()
            event.payload = payload_copy
            
    db.commit()
    return {"status": "success", "message": f"Successfully reset {len(failed_events)} failed events to PENDING."}

@app.get("/admin/outbox/failed")
def get_failed_outbox_events(page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
    """실패(FAILED) 상태로 격리된 Outbox 체인 이벤트 목록을 transaction_id 단위로 묶고 페이지네이션하여 반환합니다."""
    query = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.status == "FAILED"
    ).order_by(models.DatabaseOutbox.id.desc())
    
    all_failed = query.all()
    
    from collections import defaultdict
    groups = defaultdict(list)
    for e in all_failed:
        tx_id = e.payload.get("transaction_id") if e.payload else None
        if not tx_id:
            tx_id = f"single_{e.event_uuid}"
        groups[tx_id].append(e)
        
    # Sort transaction groups by the newest event's ID inside each group descending
    sorted_groups = sorted(
        groups.items(),
        key=lambda item: max(e.id for e in item[1]),
        reverse=True
    )
    
    total = len(sorted_groups)
    start = (page - 1) * limit
    end = start + limit
    paginated_groups = sorted_groups[start:end]
    
    result_list = []
    for tx_id, events in paginated_groups:
        table_names = list(set(e.table_name for e in events))
        event_types = list(set(e.event_type for e in events))
        max_retry = max(e.retry_count for e in events)
        
        # Max created_at or failed_at
        created_at_list = [e.created_at for e in events if e.created_at]
        failed_at = max(created_at_list).isoformat() if created_at_list else None
        
        event_details = []
        for e in events:
            event_details.append({
                "id": e.id,
                "event_uuid": e.event_uuid,
                "event_type": e.event_type,
                "table_name": e.table_name,
                "payload": e.payload,
                "status": e.status,
                "retry_count": e.retry_count,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "processed_at": e.processed_at.isoformat() if e.processed_at else None
            })
            
        result_list.append({
            "transaction_id": tx_id,
            "table_names": table_names,
            "event_types": event_types,
            "retry_count": max_retry,
            "failed_at": failed_at,
            "events": event_details
        })
        
    return {
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "data": result_list
    }

@app.get("/admin/file-ingestion/logs")
def get_file_ingestion_logs(status: str = "ALL", page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
    """File Ingestion 로그 목록을 페이지네이션하여 반환합니다. status 필터(ALL, SUCCESS, FAILED)를 지원합니다."""
    query = db.query(models.FileIngestionLog)
    if status != "ALL":
        query = query.filter(models.FileIngestionLog.status == status)
    
    query = query.order_by(models.FileIngestionLog.id.desc())
    
    total = query.count()
    start = (page - 1) * limit
    logs = query.offset(start).limit(limit).all()
    
    result_list = []
    for log in logs:
        result_list.append({
            "id": log.id,
            "filename": log.filename,
            "filepath": log.filepath,
            "table_name": log.table_name,
            "status": log.status,
            "error_message": log.error_message,
            "retry_count": log.retry_count,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "updated_at": log.updated_at.isoformat() if log.updated_at else None
        })
        
    return {
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "data": result_list
    }

@app.get("/admin/file-ingestion/failed")
def get_failed_file_ingestion_logs(page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
    """실패(FAILED) 상태인 File Ingestion 로그 목록을 페이지네이션하여 반환합니다."""
    return get_file_ingestion_logs(status="FAILED", page=page, limit=limit, db=db)

def reload_local_process_cache():
    """웹 서버 프로세스의 table_config 캐시 및 동적 모듈 캐시(mappers, pipeline plugins)를 명시적으로 무효화합니다."""
    import sys
    from database.crud import load_table_config
    
    try:
        load_table_config()
    except Exception as e:
        print(f"[Reload] Failed to reload table_config.json: {e}")
        
    # Remove custom mappers from sys.modules cache
    mapper_keys = [k for k in sys.modules.keys() if k.startswith("mappers.")]
    for k in mapper_keys:
        sys.modules.pop(k, None)
        
    # Remove pipeline plugin parsers from sys.modules cache
    plugin_keys = [k for k in sys.modules.keys() if k.startswith("pipeline_plugin_")]
    for k in plugin_keys:
        sys.modules.pop(k, None)
        
    print("[Reload] Local web server process cache successfully cleared.")

@app.post("/admin/reload-configs")
def reload_system_configs(db: Session = Depends(get_db)):
    """시스템 전역의 설정 및 파이썬 모듈 캐시를 리로드하는 이벤트를 Outbox에 적재하여 모든 워커에 전파합니다."""
    import uuid
    from datetime import datetime
    from sqlalchemy import text
    
    # 1. 웹 서버 자체 메모리 캐시 갱신
    reload_local_process_cache()
    
    # 2. SYSTEM_RELOAD Outbox 이벤트 적재 (데몬 프로세스들로 전파)
    from database.models import DatabaseOutbox
    from database.context import request_transaction_id
    
    tx_id = request_transaction_id.get() or f"reload_{str(uuid.uuid4())[:8]}"
    
    reload_event = DatabaseOutbox(
        event_uuid=str(uuid.uuid4()),
        event_type="SYSTEM_RELOAD",
        table_name="system",
        payload={
            "transaction_id": tx_id,
            "timestamp": datetime.now().isoformat(),
            "msg": "Reload configs and custom scripts modules"
        },
        status="PENDING"
    )
    db.add(reload_event)
    db.commit()
    
    try:
        db.execute(text("NOTIFY outbox_event;"))
    except:
        pass
        
    return {"status": "success", "message": "System configurations and custom scripts modules successfully reloaded."}

@app.get("/admin/file-ingestion/workspaces")
def get_ingestion_workspaces():
    """등록된 모든 파일 인제션 워크스페이스 목록을 반환합니다."""
    import os
    import json
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_base = os.path.abspath(os.path.join(script_dir, "ingestion_workspace"))
    
    if not os.path.exists(workspace_base):
        return {"status": "success", "data": []}
        
    workspaces = []
    for name in os.listdir(workspace_base):
        path = os.path.join(workspace_base, name)
        if os.path.isdir(path):
            config_dir = os.path.join(path, "config")
            config_path = os.path.join(config_dir, "config.json")
            raws_dir = os.path.join(path, "raws")
            scripts_dir = os.path.join(path, "scripts")
            archives_dir = os.path.join(path, "archives")
            errors_dir = os.path.join(path, "err")
            
            # Alternative config file search
            alternative_config = None
            if not os.path.exists(config_path) and os.path.exists(config_dir):
                json_files = [f for f in os.listdir(config_dir) if f.endswith('.json')]
                if json_files:
                    config_path = os.path.join(config_dir, json_files[0])
                    alternative_config = json_files[0]
            
            # Read config details
            table_name = name
            config_data = {}
            has_config = False
            if os.path.exists(config_path):
                has_config = True
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                    table_name = config_data.get("table_name", table_name)
                except Exception as e:
                    print(f"Error reading workspace config {config_path}: {e}")
            
            # Check for custom scripts
            custom_scripts = []
            if os.path.exists(scripts_dir):
                for f in os.listdir(scripts_dir):
                    if f.endswith('.py'):
                        custom_scripts.append(f)
                        
            # Count files in raws
            raw_files_count = 0
            if os.path.exists(raws_dir):
                raw_files_count = len([f for f in os.listdir(raws_dir) if os.path.isfile(os.path.join(raws_dir, f))])
                
            workspaces.append({
                "name": name,
                "table_name": table_name,
                "has_config": has_config,
                "config_file": os.path.basename(config_path) if has_config else None,
                "config_details": config_data,
                "custom_scripts": custom_scripts,
                "raw_files_count": raw_files_count,
                "raws_dir": raws_dir if os.path.exists(raws_dir) else None,
                "archives_dir": archives_dir if os.path.exists(archives_dir) else None,
                "errors_dir": errors_dir if os.path.exists(errors_dir) else None
            })
            
    return {"status": "success", "data": workspaces}

@app.get("/admin/chain/rules")
def get_chain_rules():
    """등록된 모든 체인 인제션 룰 목록을 반환합니다."""
    import os
    import json
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    rules_path = os.path.join(script_dir, "config", "chain_rules.json")
    
    if not os.path.exists(rules_path):
        return {"status": "success", "data": []}
        
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = json.load(f)
        if isinstance(rules, dict):
            rules = rules.get("rules", [])
        return {"status": "success", "data": rules}
    except Exception as e:
        print(f"Error reading chain rules: {e}")
        return {"status": "error", "message": str(e), "data": []}

@app.get("/admin/mappers/list")
def get_mappers():
    """등록된 맵퍼 파일들과 내부 매핑 함수 목록을 반환합니다."""
    import os
    import ast
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mappers_dir = os.path.join(script_dir, "mappers")
    
    if not os.path.exists(mappers_dir):
        return {"status": "success", "data": []}
        
    mappers = []
    for name in os.listdir(mappers_dir):
        if name.endswith(".py") and name != "__init__.py" and name != "base.py" and name != "utils.py":
            filepath = os.path.join(mappers_dir, name)
            
            # AST parsing to find functions inside the file safely
            functions = []
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    node = ast.parse(f.read(), filename=name)
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        docstring = ast.get_docstring(item) or ""
                        first_line = docstring.split("\n")[0] if docstring else ""
                        
                        args = [arg.arg for arg in item.args.args]
                        
                        functions.append({
                            "name": item.name,
                            "arguments": args,
                            "summary": first_line
                        })
            except Exception as e:
                print(f"AST parsing error in mapper {name}: {e}")
                
            mappers.append({
                "filename": name,
                "module_name": f"mappers.{name[:-3]}",
                "functions": functions
            })
            
    return {"status": "success", "data": mappers}

@app.post("/admin/file-ingestion/retry-failed")
async def retry_failed_file_ingestion(log_id: int = None, db: Session = Depends(get_db)):
    """실패(FAILED) 상태인 File Ingestion 로그를 다시 재처리합니다."""
    import os
    import asyncio
    import json
    
    query = db.query(models.FileIngestionLog).filter(
        models.FileIngestionLog.status == "FAILED"
    )
    if log_id is not None:
        query = query.filter(models.FileIngestionLog.id == log_id)
        
    failed_logs = query.all()
    if not failed_logs:
        return {"status": "success", "message": "No failed file ingestion logs found."}
        
    # 만약 프로세스 분리(DECOUPLED) 모드라면 상태만 PENDING_RETRY로 변경하고 즉시 반환합니다.
    if os.getenv("DECOUPLED") == "True":
        for log in failed_logs:
            log.status = "PENDING_RETRY"
        db.commit()
        return {
            "status": "success",
            "message": f"Decoupled mode: Marked {len(failed_logs)} logs as PENDING_RETRY. Standalone watcher will process them."
        }
        
    from directory_watcher import IngestionHandler
    success_count = 0
    fail_count = 0
    
    loop = asyncio.get_running_loop()
    
    def sync_refresh_callback(t_name: str, count: int, created_logs: list = None):
        msg = {
            "event": "batch_refresh_required",
            "table_name": t_name,
            "change_count": count
        }
        if created_logs and len(created_logs) <= 5000:
            msg["created_logs"] = created_logs
        
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(manager.broadcast(json.dumps(msg)))
        )

    def sync_file_processed_callback(t_name: str, filename: str, status: str, error_msg: str = None):
        try:
            from pipeline_base import BasePipelineParser
            clean_filename = BasePipelineParser.get_basename(filename)
        except Exception:
            clean_filename = filename

        if status == "SUCCESS":
            message = f"{clean_filename} 파일이 처리되었습니다."
        else:
            message = f"{clean_filename} 파일 처리에 실패했습니다."
            if error_msg:
                message += f" ({error_msg[:100]})"

        msg = {
            "event": "file_ingestion_completed",
            "table_name": t_name,
            "filename": clean_filename,
            "status": status,
            "message": message
        }
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(manager.broadcast(json.dumps(msg)))
        )

    for log in failed_logs:
        table_name = log.table_name or "unknown"
        server_dir = os.path.dirname(os.path.abspath(__file__))
        workspace_root = os.path.join(server_dir, "ingestion_workspace", table_name)
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
            on_refresh_callback=sync_refresh_callback,
            on_file_processed_callback=sync_file_processed_callback
        )
        
        res = await asyncio.to_thread(handler.process_archived_file_sync, log, db)
        if res:
            success_count += 1
        else:
            fail_count += 1
            
    return {
        "status": "success",
        "message": f"Successfully retried. Success: {success_count}, Failed: {fail_count}."
    }

@app.get("/admin/auto-update/status")
async def get_auto_update_status():
    """실시간 auto_update 스케줄러의 기동 현황(JSON)을 조회합니다."""
    import os
    import json
    
    server_dir = os.path.dirname(os.path.abspath(__file__))
    status_path = os.path.join(server_dir, "config", "scheduler_status.json")
    
    if not os.path.exists(status_path):
        return {"status": "success", "data": [], "last_updated": None}
        
    try:
        with open(status_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "status": "success",
            "data": data.get("collectors", []),
            "last_updated": data.get("last_updated")
        }
    except Exception as e:
        logger.error(f"Failed to read scheduler status file: {e}")
        return {"status": "error", "message": str(e), "data": []}

@app.post("/admin/auto-update/run-now")
async def trigger_auto_update_run_now(
    table_name: str = Body(..., embed=True),
    script_name: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """지정된 수집기를 즉각 비동기로 강제 실행하도록 아웃박스 트리거 이벤트를 발행합니다."""
    import json
    import time
    try:
        trigger_payload = {
            "table_name": table_name,
            "script_name": script_name
        }
        
        new_event = models.DatabaseOutbox(
            transaction_id=f"ON_DEMAND_{int(time.time())}",
            table_name=table_name,
            event_type="SCHEDULER_RUN_NOW",
            payload=json.dumps(trigger_payload),
            processed_chain=False
        )
        db.add(new_event)
        db.commit()
        
        logger.info(f"[On-Demand] Published SCHEDULER_RUN_NOW outbox event for table='{table_name}', script='{script_name}'")
        return {"status": "success", "message": f"Successfully published trigger to run '{script_name}' for table '{table_name}'."}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to publish on-demand run trigger: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/internal/events/batch-refresh")
async def internal_event_batch_refresh(
    table_name: str = Body(..., embed=True),
    change_count: int = Body(..., embed=True),
    created_logs: list = Body(None, embed=True)
):
    """Ingestion Worker가 파일 적재 완료 시 웹 서버에 갱신 및 캐시 무효화를 알리는 내부 이벤트 엔드포인트입니다."""
    import json
    invalidate_table_cache(table_name)
    msg = {
        "event": "batch_refresh_required",
        "table_name": table_name,
        "change_count": change_count
    }
    if created_logs and len(created_logs) <= 5000:
        msg["created_logs"] = created_logs
        # Update the web server's in-memory audit cache
        try:
            audit_cache.add_logs_batch(created_logs)
        except Exception as e:
            print(f"[Main Server] Failed to update audit_cache from batch-refresh: {e}")
    await manager.broadcast(json.dumps(msg))
    return {"status": "ok"}

@app.post("/internal/events/broadcast")
async def internal_event_broadcast(payload: dict = Body(...)):
    """외부 데몬 프로세스로부터 임의의 WebSocket 메시지를 받아 중계하는 엔드포인트입니다."""
    import json
    # If the payload is a table refresh/update, handle caching/invalidation
    table_name = payload.get("table_name")
    if table_name:
        invalidate_table_cache(table_name)
        
    created_logs = payload.get("created_logs")
    if created_logs and len(created_logs) <= 5000:
        try:
            audit_cache.add_logs_batch(created_logs)
        except Exception as e:
            print(f"[Main Server] Failed to update audit_cache from broadcast: {e}")
            
    await manager.broadcast(json.dumps(payload))
    return {"status": "ok"}

@app.post("/internal/events/file-processed")
async def internal_event_file_processed(
    table_name: str = Body(..., embed=True),
    filename: str = Body(..., embed=True),
    status: str = Body(..., embed=True),
    error_msg: str = Body(None, embed=True)
):
    """Ingestion Worker가 단일 파일 인제션 완료 시 웹 서버에 브로드캐스트를 요청하는 내부 이벤트 엔드포인트입니다."""
    import json
    try:
        from pipeline_base import BasePipelineParser
        clean_filename = BasePipelineParser.get_basename(filename)
    except Exception:
        clean_filename = filename

    if status == "SUCCESS":
        message = f"{clean_filename} 파일이 처리되었습니다."
    else:
        message = f"{clean_filename} 파일 처리에 실패했습니다."
        if error_msg:
            message += f" ({error_msg[:100]})"

    msg = {
        "event": "file_ingestion_completed",
        "table_name": table_name,
        "filename": clean_filename,
        "status": status,
        "message": message
    }
    await manager.broadcast(json.dumps(msg))
    return {"status": "ok"}

# --- Static File Serving & SPA Fallback for client2 ---
script_dir = os.path.dirname(os.path.abspath(__file__))
client2_dist_path = os.path.abspath(os.path.join(script_dir, "..", "client2", "dist"))
if not os.path.exists(client2_dist_path):
    client2_dist_path = os.path.join(script_dir, "dist")

if os.path.exists(client2_dist_path):
    assets_dir = os.path.join(client2_dist_path, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/admin")
    @app.get("/admin.html")
    def serve_admin_page():
        """어드민 페이지(admin.html)를 반환합니다."""
        admin_file = os.path.join(client2_dist_path, "admin.html")
        if os.path.exists(admin_file):
            return FileResponse(admin_file)
        dev_admin_file = os.path.abspath(os.path.join(script_dir, "..", "client2", "admin.html"))
        if os.path.exists(dev_admin_file):
            return FileResponse(dev_admin_file)
        raise HTTPException(status_code=404, detail="Admin page not found. Please build frontend first.")

    @app.get("/{file_name:path}")
    async def serve_static_or_index(file_name: str):
        # Prevent catching API endpoints or WebSocket or Admin page
        if (file_name.startswith("tables") or 
            file_name.startswith("ws") or 
            file_name.startswith("audit_logs") or 
            file_name.startswith("dashboard") or
            file_name.startswith("admin") or
            file_name.startswith("api")):
            raise HTTPException(status_code=404)

        target_path = os.path.join(client2_dist_path, file_name)
        if file_name and os.path.exists(target_path) and os.path.isfile(target_path):
            return FileResponse(target_path)

        index_file = os.path.join(client2_dist_path, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Index file not found")

