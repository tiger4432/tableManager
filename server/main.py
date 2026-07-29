from sqlalchemy import desc
from sqlalchemy.orm import Session
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from database.database import SessionLocal, engine, get_db, SQLALCHEMY_DATABASE_URL, DB_URL_SOURCE
from database import models, schemas, crud
import uuid 
import os
import io
import csv
import time
from fastapi import UploadFile, File, Body, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Setup Unified Logger & Hook Uvicorn Loggers
import logging
from utils.logger import get_process_logger, ColoredProcessFormatter
from utils.payload_helper import get_payload_dict
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
import paths  # single override point for config/ + ingestion_workspace/ (ASSY_DATA_ROOT)
# Shared-token gate for /admin/*. Every route below whose path starts with
# /admin carries one of these two dependencies; server/tests/test_admin_auth.py
# enumerates the app's routes and fails if a new one ever misses.
from admin_auth import require_admin_token, require_admin_token_strict
import admin_auth
script_dir = os.path.dirname(os.path.abspath(__file__))
logger.info(f"[paths] {paths.describe()}")
# Which DB URL source won (env / config file / default) - password masked, never raw.
logger.info(f"[db] url source={DB_URL_SOURCE} target={paths.mask_db_password(SQLALCHEMY_DATABASE_URL)}")
# [#13] Boot is FAIL-FAST on a config that is not JSON.
#
# This block used to open the file itself and swallow every exception with a
# single ERROR line, while crud.load_table_config() swallowed the same failure
# with no line at all. A restart on a corrupt table_config.json therefore came up
# "successfully" with every table missing - the UI looked wiped, the log looked
# clean, and the operator had no thread to pull. Refusing to start is strictly
# better than serving an empty system that looks like data loss.
#
# The fail-fast is limited to PARSE failures on purpose (see the scope note on
# load_table_config_or_raise). A file that parses but declares something odd
# still boots: a production server that will not start over a semantic complaint
# is a bigger accident than the complaint.
try:
    table_config = crud.load_table_config_or_raise()
except crud.TableConfigError as e:
    logger.critical(f"[Boot] Refusing to start - {e}")
    raise
try:
    models.init_dynamic_models(table_config)
except Exception as e:
    logger.error(f"Failed to init dynamic models: {e}")


def bootstrap_database_schema():
    """[#16a] Build/patch the physical schema. Called from startup, NOT at import.

    Why it moved: these two statements used to run at module import, so anything
    that merely imported the app - pytest collecting this suite, a script poking
    at a router - issued DDL against whatever DATABASE_URL resolved to. With the
    variable unset that default is the production database, and it happened.

    Why it did NOT just get deleted: a fresh install starts with an empty
    database, and the whole onboarding story is "add a table to
    table_config.json -> boot -> use it". Removing this path would break every
    new install while every existing one kept working, which is the quietest
    possible regression. So it is still automatic - it just needs someone to
    actually start the server first.

    `create_all` stays unguarded so an unreachable database fails startup loudly
    (uvicorn aborts) instead of serving a schema-less app, which is exactly the
    behaviour the old import-time statement had.

    This function always does the work; deciding WHEN to run it belongs to the
    caller (see the guard at the call site in `startup_event`).
    """
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

# --- Health endpoint -------------------------------------------------------
# Registered HERE, far above the SPA catch-all `@app.get("/{file_name:path}")` at
# the bottom of this file. That ordering is the whole point: FastAPI matches in
# registration order, and before this route existed `/health` fell through to the
# catch-all and returned index.html with a 200. An external monitor would have
# called a dead server alive. server/tests/test_health_endpoint.py asserts both
# halves - /health is JSON, a bogus path is still HTML - so a future reorder that
# re-shadows this route fails the suite instead of failing silently in production.
import asyncio as _health_asyncio
from fastapi.responses import JSONResponse
import health as health_mod
import process_supervisor as _supervisor_mod
from utils import heartbeat as _heartbeat_mod

# A health check that blocks is a second outage, so the database probe is bounded.
_HEALTH_DB_TIMEOUT_SEC = 2.0
# When the database hangs, `wait_for` frees the request but not the worker thread.
# This flag stops a monitor polling every 10 s from stacking up one hung thread
# per poll: at most one probe is ever in flight, and it is cleared by the thread
# that owns it, not by the request that gave up waiting.
_health_probe_inflight = False


def _health_probe_db_sync():
    from sqlalchemy import text as _sql_text
    t0 = time.perf_counter()
    db = SessionLocal()
    try:
        db.execute(_sql_text("SELECT 1"))
        latency_ms = (time.perf_counter() - t0) * 1000.0
        outbox = health_mod.probe_outbox(db)
        return {"status": "ok", "latency_ms": round(latency_ms, 2)}, outbox
    finally:
        db.close()


def _health_probe_and_release():
    global _health_probe_inflight
    try:
        return _health_probe_db_sync()
    finally:
        _health_probe_inflight = False


@app.get("/health")
async def health_check():
    """운영 모니터링용 헬스체크. 정상 200, 비정상 503 (항상 JSON)."""
    global _health_probe_inflight
    if _health_probe_inflight:
        db_result = {"status": "timeout",
                     "error": "a previous database probe has not returned"}
        outbox_result = {"status": "unavailable"}
    else:
        _health_probe_inflight = True
        try:
            db_result, outbox_result = await _health_asyncio.wait_for(
                _health_asyncio.to_thread(_health_probe_and_release),
                timeout=_HEALTH_DB_TIMEOUT_SEC)
        except _health_asyncio.TimeoutError:
            db_result = {"status": "timeout",
                         "error": f"no answer within {_HEALTH_DB_TIMEOUT_SEC}s"}
            outbox_result = {"status": "unavailable"}
        except Exception as e:
            _health_probe_inflight = False
            db_result = {"status": "down", "error": f"{type(e).__name__}: {e}"}
            outbox_result = {"status": "unavailable"}

    payload, http_status = health_mod.compute_health(
        db_result=db_result,
        heartbeats=_heartbeat_mod.read_all(),
        supervisor_status=_supervisor_mod.read_status(),
        outbox_result=outbox_result,
        stale_after=_heartbeat_mod.DEFAULT_STALE_AFTER_SEC,
    )
    return JSONResponse(status_code=http_status, content=payload,
                        headers={"Cache-Control": "no-store"})

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

_admin_auth_banner_logged = False


@app.on_event("startup")
async def startup_event():
    global global_watcher, global_config_watcher, _admin_auth_banner_logged
    import asyncio
    main_loop = asyncio.get_running_loop()

    # Emitted BEFORE the TESTING early-return below, and before anything that can
    # fail, so an operator restarting into this build always sees whether the
    # admin surface is locked and which variable locks it. Guarded by a
    # module-level flag because TestClient(app) re-runs startup per test.
    if not _admin_auth_banner_logged:
        _admin_auth_banner_logged = True
        _lvl, _msg = admin_auth.startup_banner()
        getattr(logger, _lvl)(_msg)

    # [#16a] Physical schema first: it used to run at import, so it completed
    # before anything else in the process. Keep that ordering - the config
    # watcher below can fire an ALTER, and it must not race a table that does
    # not exist yet.
    #
    # Skipped under TESTING, and for a concrete reason rather than tidiness:
    # conftest.py runs this same step once on the MAIN thread. Running it again
    # here would open a new connection on every TestClient's startup thread, and
    # SQLAlchemy's pool for `sqlite:///:memory:` (SingletonThreadPool) closes
    # older connections once more than five exist - taking the main thread's
    # database, tables and all, with it. That is measured, not theoretical: it
    # broke test_api.py::test_file_ingestion_callback_direct, which drives the
    # real watcher through `database.SessionLocal` on the main thread.
    if os.getenv("TESTING") == "True":
        logger.info("[Schema] TESTING mode - conftest owns the boot-time schema step.")
    else:
        bootstrap_database_schema()

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
        # [2026-07-25 정리] 레거시 data_rows NULL updated_at 보정 마이그레이션 제거
        # (data_rows 테이블 자체가 폐기 — scripts/drop_legacy_tables_20260725.sql 참조).
        from sqlalchemy import text
        with engine.connect() as conn:
            # [Migration] database_outbox.processed_chain 컬럼 보정 (information_schema 존재확인 게이팅).
            #   기존: 무조건 ADD COLUMN → 기존 DB에서 "컬럼 이미 존재" 예외로 트랜잭션 abort(rollback 부재)
            #   → 같은 커넥션의 후속 broadcast_at ADD COLUMN 이 InFailedSqlTransaction 으로 조용히 실패
            #   → 워커가 UndefinedColumn(broadcast_at) 크래시. 존재확인 게이팅으로 예외 경로 자체를 제거한다.
            try:
                col_exists = conn.execute(text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'database_outbox' AND column_name = 'processed_chain'"
                )).first()
                if not col_exists:
                    conn.execute(text("ALTER TABLE database_outbox ADD COLUMN processed_chain BOOLEAN DEFAULT FALSE"))
                    conn.commit()
                    logger.info("Added processed_chain column to database_outbox.")
            except Exception as e:
                conn.rollback()
                logger.error(f"processed_chain migration failed: {e}")

            # [Reliability F1] database_outbox.broadcast_at 컬럼 + **최초 생성 시에만** 1회 백필.
            #   broadcast_at NULL 인 처리완료(SUCCESS) 행 = "통지 미확정" → 워커 스윕이 재발사 대상으로 삼는다.
            #   백필하지 않으면 기존 outbox 전량이 미확정으로 오인되어 스윕이 대량 오발사(refresh storm)한다.
            #   재기동 시엔 컬럼 존재 → 백필 skip 필수: 진짜 미전달 행(NULL)을 전달됨으로 덮어쓰면
            #   재기동 중 유실분이 영구 stale 이 된다(스윕 회수 경로 보존).
            try:
                col_exists = conn.execute(text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'database_outbox' AND column_name = 'broadcast_at'"
                )).first()
                if not col_exists:
                    conn.execute(text("ALTER TABLE database_outbox ADD COLUMN broadcast_at TIMESTAMPTZ"))
                    conn.commit()
                    logger.info("Added broadcast_at column to database_outbox. Backfilling existing processed rows...")
                    # 1000행 청킹 백필(1000만행 대비 락/WAL 부담 최소화). 기존 행은 이미 전달된 것으로 간주.
                    backfilled = 0
                    while True:
                        res = conn.execute(text(
                            "UPDATE database_outbox SET broadcast_at = COALESCE(processed_at, created_at) "
                            "WHERE id IN (SELECT id FROM database_outbox "
                            "WHERE processed_chain = true AND broadcast_at IS NULL LIMIT 1000)"
                        ))
                        conn.commit()
                        if not res.rowcount:
                            break
                        backfilled += res.rowcount
                    logger.info(f"[Reliability F1] Backfilled broadcast_at for {backfilled} pre-existing processed outbox row(s).")
            except Exception as e:
                # 백필 중단 시 잔여 NULL 행은 워커 스윕이 회수(over-refresh 1회, stale 아님) — 삼키지 않고 기록.
                conn.rollback()
                logger.error(f"broadcast_at migration/backfill failed (undelivered rows recovered by worker sweep): {e}")

        if os.getenv("DECOUPLED") == "True":
            logger.info("Decoupled mode active. Skipping inline Directory Watcher, Graph DB Sync, and Chained Ingestion workers.")
            return

        logger.info("Initializing Directory Watcher...")
        workspace_base = paths.WORKSPACE_DIR
        
        def trigger_ws_refresh(table_name: str, count: int, created_logs: list = None, total_log_count: int = None):
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
                # [F1] SUCCESS의 error_msg 슬롯은 detail(예: "키 결측으로 N행 스킵") 전달용 —
                # 메시지 문자열에만 덧붙인다(페이로드 구조 불변).
                if error_msg:
                    message += f" ({error_msg[:100]})"
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
            # [Heavy Lane P1] 완료/실패 시 진행 스냅샷 레지스트리 정리 (멱등)
            try:
                ingestion_activity_registry.remove(table_name, clean_filename)
            except Exception as e:
                logger.warning(f"Failed to clear ingestion activity entry: {e}")
            try:
                asyncio.run_coroutine_threadsafe(manager.broadcast(json.dumps(msg)), main_loop)
            except Exception as e:
                logger.error(f"Failed to broadcast file ingestion completion: {e}")

        def trigger_ingestion_state(state: dict):
            # [Heavy Lane P1] 임베디드 모드: watcher가 같은 프로세스이므로 HTTP 왕복 없이
            # 레지스트리에 직접 반영한다 (분리 모드는 run_watcher가 /internal/events/ingestion-state로 POST).
            try:
                from pipeline_base import BasePipelineParser
                clean = BasePipelineParser.get_basename(state.get("filename") or "")
            except Exception:
                clean = state.get("filename")
            try:
                ingestion_activity_registry.apply_state({**state, "filename": clean})
            except Exception as e:
                logger.warning(f"Failed to apply ingestion state: {e}")

        global_watcher = WorkspaceWatcher(
            workspace_base,
            on_refresh_callback=trigger_ws_refresh,
            on_file_processed_callback=trigger_ws_file_processed,
            on_ingestion_state_callback=trigger_ingestion_state
        )
        global_watcher.discover_and_watch()
        # 비차단 모드(blocking=False)로 기동
        global_watcher.start(blocking=False)
        logger.info(f"Directory Watcher started with {global_watcher.watch_count} watches.")
        
        # Start Graph DB Sync Worker (Disabled for manual sync mode)
        # from graph_sync_worker import start_graph_sync_worker
        # main_loop.create_task(start_graph_sync_worker(SessionLocal))
        # logger.info("Graph DB Sync Worker background task spawned.")
        
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
        # The reload debounce runs on its own timer thread; observer.stop() does
        # not reach it, so an armed reload would fire DDL after shutdown.
        handler = getattr(global_config_watcher, "config_handler", None)
        if handler is not None:
            handler.cancel_pending()
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

# `to_local_str`/`LOCAL_TIMEZONE` now live in utils.time_format so the background
# workers can format timestamps without importing this module. Importing `main`
# runs the #13 boot fail-fast, and a worker that only wanted a timestamp helper
# would lose its WebSocket notification whenever the config was corrupt - see the
# module docstring there. Re-exported here so `main.to_local_str` keeps working
# for every existing caller.
from utils.time_format import LOCAL_TIMEZONE, to_local_str

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
    user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at", "is_graph_synced", "needs_graph_rollback", "graph_synced_at"]]

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
        
    # 5. is_graph_synced 주입
    is_sync_val = getattr(row, "is_graph_synced", False)
    if is_sync_val is None:
        is_sync_val = False
    row.data["is_graph_synced"] = {
        "value": is_sync_val,
        "is_overwrite": False,
        "updated_by": "system"
    }

    # 6. needs_graph_rollback 주입
    needs_roll_val = getattr(row, "needs_graph_rollback", False)
    if needs_roll_val is None:
        needs_roll_val = False
    row.data["needs_graph_rollback"] = {
        "value": needs_roll_val,
        "is_overwrite": False,
        "updated_by": "system"
    }

    # 7. graph_synced_at 주입
    synced_at_val = getattr(row, "graph_synced_at", None)
    row.data["graph_synced_at"] = {
        "value": to_local_str(synced_at_val) if synced_at_val else "미동기화",
        "is_overwrite": False,
        "updated_by": "system"
    }


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
            
            # [성능 최적화] include_sources=False 일 때는 소스 쿼리를 건너뛰었으므로 Overwrite 테이블 정보로 즉시 유도
            if not include_sources:
                if manual_pin == "collision_merge" or updated_by == "collision_merge":
                    priority_source = "collision_merge"
                elif is_ow or updated_by == "user" or manual_pin == "user":
                    priority_source = "user"
                else:
                    priority_source = None
            else:
                _, priority_source = crud.compute_priority_value(col_srcs, manual_pin, table_name)

            is_collision = (priority_source == "collision_merge") or (include_sources and "collision_merge" in col_srcs)
            has_overwrite = is_ow or (manual_pin is not None) or is_collision or (include_sources and "user" in col_srcs)
            
            r_data[col] = {
                "value": val_raw,
                "is_overwrite": has_overwrite,
                "is_collision_merge": is_collision,
                "sources": col_srcs,
                "updated_by": updated_by,
                "manual_priority_source": manual_pin,
                "priority_source": priority_source
            }
                
        r_data["created_at"] = {"value": c_at_str, "is_overwrite": False, "sources": {}, "updated_by": "system"}
        r_data["updated_at"] = {"value": u_at_str, "is_overwrite": False, "sources": {}, "updated_by": "system"}
        
        # 그래프 동기화 컬럼 3종 주입
        is_sync_val = getattr(row, "is_graph_synced", False)
        if is_sync_val is None:
            is_sync_val = False
            
        needs_roll_val = getattr(row, "needs_graph_rollback", False)
        if needs_roll_val is None:
            needs_roll_val = False
            
        synced_at_val = getattr(row, "graph_synced_at", None)
        synced_at_str = to_local_str(synced_at_val) if synced_at_val else "미동기화"
        
        r_data["is_graph_synced"] = {"value": is_sync_val, "is_overwrite": False, "sources": {}, "updated_by": "system"}
        r_data["needs_graph_rollback"] = {"value": needs_roll_val, "is_overwrite": False, "sources": {}, "updated_by": "system"}
        r_data["graph_synced_at"] = {"value": synced_at_str, "is_overwrite": False, "sources": {}, "updated_by": "system"}
        
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

def get_deleted_rows_business_keys_bulk(db: Session, table_name: str, row_ids: list) -> dict:
    """[C-1 Fix] batch_delete용 business_key 일괄 유도 — 행별 N+1 쿼리를 청크당 IN 쿼리 2회로 대체.

    get_deleted_row_business_key와 동일 의미론(최신 business_key 우선, 없으면 key_col 셀 편집
    로그의 new_value fallback)을 유지하되 1000행 청킹으로 대량 삭제에서도 안전하다.
    반환: {row_id: business_key(str)}
    """
    result = {}
    if not row_ids:
        return result
    config = crud.TABLE_CONFIG.get(table_name, {})
    key_col = config.get("business_key")
    CHUNK = 1000
    for i in range(0, len(row_ids), CHUNK):
        chunk = row_ids[i:i + CHUNK]
        # 1차: AuditLog.business_key를 직접 보유한 로그 (timestamp 오름차순 순회 → 최신값이 최종 반영)
        rows = db.query(models.AuditLog.row_id, models.AuditLog.business_key).filter(
            models.AuditLog.table_name == table_name,
            models.AuditLog.row_id.in_(chunk),
            models.AuditLog.business_key.isnot(None)
        ).order_by(models.AuditLog.timestamp.asc()).all()
        for r_id, bk in rows:
            if bk:
                result[r_id] = str(bk)
        # 2차 fallback: business_key 미보유 행은 key_col 셀 편집 로그의 new_value에서 유도
        if key_col:
            missing = [r for r in chunk if r not in result]
            if missing:
                fb_rows = db.query(models.AuditLog.row_id, models.AuditLog.new_value).filter(
                    models.AuditLog.table_name == table_name,
                    models.AuditLog.row_id.in_(missing),
                    models.AuditLog.column_name == key_col
                ).order_by(models.AuditLog.timestamp.asc()).all()
                for r_id, nv in fb_rows:
                    if nv:
                        result[r_id] = str(nv)
    return result

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
from event_constants import MAX_NOTIFY_CREATED_LOGS
# [Heavy Lane P1] 진행 중 인제션 스냅샷 레지스트리 (watcher가 push, admin API가 서빙)
from ingestion_activity import registry as ingestion_activity_registry

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
def get_transaction_logs(tx_id: str, db: Session = Depends(get_db), limit: int = 20000):
    """특정 트랜잭션의 상세 로그를 반환합니다. (인메모리 캐시 우선 조회, 최대 limit 건 반환)"""

    # 1. 캐시에서 조회 시도
    if audit_cache.is_loaded:
        for g in audit_cache.groups:
            if g.get("transaction_id") == tx_id:
                logs = g.get("logs", [])
                total_count = g.get("total_count", len(logs))
                
                # 캐시 캡핑(500개)이 걸렸고 limit이 그보다 많은 양을 요구한다면 캐시 조회를 건너뛰고 DB 조회로 폴백합니다.
                if len(logs) >= total_count or len(logs) >= limit:
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
                        "total_count": total_count,
                        "summary_columns": cols,
                        "logs": cloned_logs
                    }
                break
                
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


# [재교정률] 대시보드 로드마다 감사 테이블을 집계하지 않기 위한 TTL 캐시.
# 값은 7일 창 집계라 초 단위로 변하지 않는다 — 60초 캐시로 충분하고, 이 캐시가
# "대시보드를 열 때마다 GROUP BY"를 구조적으로 막는 1차 방어선이다.
RECORRECTION_CACHE = {"value": None, "at": 0.0}
RECORRECTION_CACHE_TTL = 60.0
# 2차 방어선: 인덱스(idx_audit_user_recorrection)가 아직 없는 운영 DB에서도 대시보드가
# 절대 느려지지 않게 하는 상한. 인덱스가 있으면 도달할 일이 없고, 없으면 값 대신 '—'가 뜬다.
# (지표 하나 때문에 대시보드 전체가 굼떠지는 것보다, 그 칸만 비는 편이 낫다.)
RECORRECTION_TIMEOUT_MS = 1500


def _get_recorrection_stat(db: Session) -> schemas.RecorrectionStat:
    """재교정률을 캐시/타임아웃 보호 하에 계산한다. 절대 예외를 밖으로 내보내지 않는다."""
    import sqlalchemy as sa
    now = time.time()
    if RECORRECTION_CACHE["value"] is not None and (now - RECORRECTION_CACHE["at"]) < RECORRECTION_CACHE_TTL:
        return RECORRECTION_CACHE["value"]

    try:
        # SET LOCAL은 현재 트랜잭션에서만 유효하고 세션 종료(get_db의 db.close())에서 되돌아간다.
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(sa.text(f"SET LOCAL statement_timeout = {RECORRECTION_TIMEOUT_MS}"))
        result = schemas.RecorrectionStat(**crud.get_recorrection_stats(db))
    except Exception as e:
        # 타임아웃은 트랜잭션을 오염시킨다 — 즉시 rollback 하지 않으면 이후 쿼리가 전부 실패한다.
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[Dashboard] re-correction rate unavailable: {e}")
        # F6 (twin of _get_effort_stat): name the ACTUAL cause. The old text claimed
        # "timeout or failure" and pointed at the index unconditionally, so a missing
        # column or a broken query read as "the index is slow" and sent whoever was on
        # call to tune an index that was never the problem.
        detail = (str(e).strip().splitlines() or [""])[0][:200]
        lowered = detail.lower()
        if "timeout" in lowered or "canceling statement" in lowered:
            reason = (f"집계 시간 초과 ({RECORRECTION_TIMEOUT_MS}ms) — "
                      f"idx_audit_user_recorrection 인덱스 확인. "
                      f"[{type(e).__name__}] {detail}")
        else:
            reason = f"집계 실패 — [{type(e).__name__}] {detail or '상세 없음'}"
        result = schemas.RecorrectionStat(
            window_days=crud.RECORRECTION_WINDOW_DAYS,
            measured_cells=0, recorrected_cells=0, rate_pct=None,
            unavailable_reason=reason,
        )

    RECORRECTION_CACHE["value"] = result
    RECORRECTION_CACHE["at"] = now
    return result


# [V1 계기] 상호작용 점수도 재교정률과 **완전히 같은 방어**를 쓴다(캐시 + statement_timeout).
# 두 계기가 같은 무거운 엔드포인트에 얹혀 있으므로, 방어가 하나라도 빠지면 대시보드가
# 지표 때문에 느려진다 — 그건 지표가 자기 목적을 배신하는 것이다.
EFFORT_CACHE = {"value": None, "at": 0.0}
EFFORT_CACHE_TTL = 60.0
EFFORT_TIMEOUT_MS = 1500


def _get_effort_stat(db: Session) -> schemas.EffortStat:
    """상호작용 점수를 캐시/타임아웃 보호 하에 계산한다. 절대 예외를 밖으로 내보내지 않는다."""
    import sqlalchemy as sa
    import effort_metric
    now = time.time()
    if EFFORT_CACHE["value"] is not None and (now - EFFORT_CACHE["at"]) < EFFORT_CACHE_TTL:
        return EFFORT_CACHE["value"]

    # 배점은 캐시하지 않는다 — config 핫리로드가 다음 집계부터 반영되어야 하고,
    # 파일 읽기 1회는 60초에 한 번뿐이다.
    weights = effort_metric.resolve_weights(effort_metric.load_config())

    try:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(sa.text(f"SET LOCAL statement_timeout = {EFFORT_TIMEOUT_MS}"))
        result = schemas.EffortStat(**crud.get_effort_stats(db, weights))
    except Exception as e:
        # 타임아웃은 트랜잭션을 오염시킨다 — 즉시 rollback 하지 않으면 이후 쿼리가 전부 실패한다.
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[Dashboard] interaction effort score unavailable: {e}")
        # F6: name the ACTUAL cause. The old text claimed a timeout unconditionally, so a
        # missing column or a broken query read as "the index is slow" and sent whoever
        # was on call to tune an index that was never the problem.
        detail = (str(e).strip().splitlines() or [""])[0][:200]
        lowered = detail.lower()
        if "timeout" in lowered or "canceling statement" in lowered:
            reason = (f"집계 시간 초과 ({EFFORT_TIMEOUT_MS}ms) — idx_effort_window 인덱스 확인. "
                      f"[{type(e).__name__}] {detail}")
        else:
            reason = f"집계 실패 — [{type(e).__name__}] {detail or '상세 없음'}"
        result = schemas.EffortStat(
            window_days=crud.EFFORT_WINDOW_DAYS,
            avg_score=None, tx_count=0, session_count=0,
            weights=weights, measured_ratio=None,
            unavailable_reason=reason,
        )

    EFFORT_CACHE["value"] = result
    EFFORT_CACHE["at"] = now
    return result


@app.get("/api/effort/config")
def get_effort_config():
    """[V1 계기] 배점과 '컨텍스트 유지 전이' 선언 — 클라이언트의 **유일한** 정본.

    클라는 자기 사본을 두지 않고 여기서 읽어 적용한다(`/api/maps/paint-rules`가 `binding`을
    서빙하는 것과 같은 패턴). 배점을 클라에 하드코딩하면 서버 집계와 화면 표시가 갈라지고,
    배점을 조정하는 순간 둘이 조용히 다른 숫자를 말하게 된다.

    `context_preserving_transitions`는 **0점으로 칠 전이의 선언형 허용목록**이다. 기본은
    "상실(이동 가중치 부과)"이고, 선언된 전이만 면제된다 — 목록은 비어 있는 상태로 출발하며
    항목은 라우팅 소유자가 제안하고 총괄이 승인한다.
    """
    import effort_metric
    return effort_metric.get_public_config()


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

    # 두 계기는 **마지막에** 계산한다 — 타임아웃 시 rollback 이 위쪽 집계를 건드리지 않도록.
    # (각자 자기 rollback 을 하므로 앞의 실패가 뒤의 집계를 오염시키지 않는다.)
    recorrection = _get_recorrection_stat(db)
    effort = _get_effort_stat(db)

    return schemas.DashboardSummaryResponse(
        total_tables=len(table_names),
        total_rows=total_global_rows,
        today_updates=today_updates_count,
        table_stats=table_stats,
        system_health="Excellent",
        recorrection=recorrection,
        effort=effort
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
    # [C-1 Fix] async 핸들러 내 동기 DB 호출 → threadpool 격리(이벤트 루프 동결 방지)
    from fastapi.concurrency import run_in_threadpool
    success = await run_in_threadpool(crud.delete_row, db, table_name, row_id)
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
    from fastapi.concurrency import run_in_threadpool

    # [C-1 Fix] 동기 crud 삭제 + 감사 로그 조회를 threadpool로 격리(이벤트 루프 동결 방지).
    # 기존 삭제행별 get_deleted_row_business_key N+1 쿼리(대량 삭제 시 최악의 루프 블로커)는
    # get_deleted_rows_business_keys_bulk의 청크 IN 쿼리 2회로 대체한다.
    def _delete_and_collect():
        deleted = crud.delete_rows_batch(db, table_name, batch.row_ids, batch.user_name)
        logs = []
        if deleted > 0:
            log_objs = db.query(models.AuditLog).filter(
                models.AuditLog.table_name == table_name,
                models.AuditLog.row_id.in_(batch.row_ids),
                models.AuditLog.column_name == "DELETE"
            ).all()
            bk_map = get_deleted_rows_business_keys_bulk(db, table_name, [l.row_id for l in log_objs])
            for log in log_objs:
                logs.append({
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
                    "business_key": bk_map.get(log.row_id),
                    "is_row_deleted": True
                })
        return deleted, logs

    deleted_count, created_logs = await run_in_threadpool(_delete_and_collect)

    if deleted_count > 0:
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
            columns = [c.name for c in table_model.__table__.columns if c.name not in ["row_id", "business_key_val", "created_at", "updated_at", "is_graph_synced", "needs_graph_rollback", "graph_synced_at"]]
        else:
            columns = []
            
    # [버그 수정] display_columns 정의 여부와 관계없이 시스템 컬럼은 항상 마지막에 보장
    system_cols = ["created_at", "updated_at", "is_graph_synced", "needs_graph_rollback", "graph_synced_at"]
    for sc in system_cols:
        if sc not in columns:
            columns.append(sc)
            
    col_types = dict(config.get("column_types", {}))
    col_types["is_graph_synced"] = "boolean"
    col_types["needs_graph_rollback"] = "boolean"
    col_types["graph_synced_at"] = "datetime"
            
    return {
        "table_name": table_name,
        "columns": columns,
        "column_types": col_types,
        "business_key": config.get("business_key", ""),
        "composite_key_source": config.get("composite_key_source", []),
        "map_key_columns": config.get("map_key_columns", []),
        # Site declaration for the log-shaped push gate (map editor Gate 4): true means
        # "this table has data columns outside the map contract, but an editor push is a
        # KNOWN flow here (e.g. R&D manual-measurement overwrite) - downgrade the hard
        # refusal to a one-shot loss-acknowledging confirm". Absent/false keeps the block.
        # Strict `is True`: a config typo ("true"/"false" strings, 1) must not unlock
        # destruction - only the JSON boolean true counts, same as the client's `=== true`.
        "map_push_ok": config.get("map_push_ok") is True
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
    # [C-1 Fix] 동기 crud 생성 + AuditLog 조회 + ORM 속성 접근(msg_items)을 threadpool로 격리
    from fastapi.concurrency import run_in_threadpool

    def _create_and_collect():
        new_rows_ = crud.create_empty_rows_batch(db, table_name, count, user_name)
        logs = []
        if new_rows_:
            log_objs = db.query(models.AuditLog).filter(
                models.AuditLog.table_name == table_name,
                models.AuditLog.row_id.in_([r.row_id for r in new_rows_]),
                models.AuditLog.column_name == "CREATE"
            ).all()
            for log in log_objs:
                logs.append({
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
        items = []
        for row in new_rows_:
            inject_system_columns(row)
            items.append({
                "row_id": row.row_id,
                "table_name": table_name,
                "data": row.data
            })
        return new_rows_, logs, items

    new_rows, created_logs, msg_items = await run_in_threadpool(_create_and_collect)
    if new_rows:
        invalidate_table_cache(table_name)

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

def _validate_effort(effort):
    """[V1 instrument] Normalise the interaction counts. NEVER raises, NEVER blocks.

    Returns `(counts, error)`:
      * `counts` = `(session_id, key, mouse, nav, nav_preserved)`, or None when there is
        nothing to record (field absent = NOT MEASURED, or the blob was discarded).
      * `error`  = human-readable reason the blob was DISCARDED, or None.

    **No silent clamping, no silent casting.** A negative or non-integer count is the
    signature of a broken counter, and swallowing it as 0 or a rounded value puts a wrong
    number into the baseline wearing a plausible face. So a bad blob is never stored.

    But loudness is paid for in the RESPONSE and the LOG, never with the user's data.
    This validator used to raise HTTPException before any write (fix round F4,
    2026-07-29): a client counter bug therefore rejected the operator's correction
    outright, turning a metric defect into a data-entry outage. Losing a counter costs
    one row in an instrument; losing a correction costs a human their work and violates
    core value #1 - the very thing the instrument exists to defend. The correction always
    goes through.
    """
    if effort is None:
        return None, None

    # The declared shape (schemas.EffortReport) is parsed HERE rather than by FastAPI, so
    # that a blob which is not even an object is a discard instead of a 422 that would
    # take the write with it.
    if isinstance(effort, schemas.EffortReport):
        report = effort
    elif isinstance(effort, dict):
        try:
            report = schemas.EffortReport.model_validate(effort)
        except Exception as e:
            return None, f"effort could not be parsed and was discarded: {e}"
    else:
        return None, (f"effort must be an object with "
                      f"{{session_id, key, mouse, nav, nav_preserved}}, got "
                      f"{type(effort).__name__} - discarded.")

    # 모르는 키는 **무시하지 않는다.** pydantic 기본 동작(조용히 버리기)에서는
    # 클라가 새 카운터를 추가해도 서버가 말없이 삼키고, 나머지 값이 멀쩡하니 아무도
    # 모른다 — 그리고 이 계기는 소급 재계산이 불가능해서, 발견했을 땐 그 기간의 기준선이
    # 이미 없다. 빠진 키는 정상(미계측)이고, **모르는 키만** 오류다.
    unknown = sorted((report.model_extra or {}).keys())
    if unknown:
        return None, (f"effort has unknown field(s): {', '.join(unknown)} - the whole "
                      f"effort blob was discarded (the correction was still applied). "
                      f"Allowed: session_id, key, mouse, nav, nav_preserved.")

    # session_id is what ties the counts to a working session; without it the row cannot
    # enter the per-session average at all, so a missing one is a discard, not a default.
    sid = report.session_id
    if not isinstance(sid, str) or not sid.strip():
        return None, (f"effort.session_id must be a non-empty string (got "
                      f"{type(sid).__name__}: {sid!r}) - effort discarded.")
    session_id = sid.strip()

    counts = {}
    # nav_preserved 는 나중에 추가된 필드다 — 아직 보내지 않는 클라는 오류가 아니며
    # 기본 0으로 취급된다(스키마 기본값). 보낸다면 나머지와 똑같이 검증한다.
    for field in ("key", "mouse", "nav", "nav_preserved"):
        v = getattr(report, field)
        # bool 은 파이썬에서 int 의 서브클래스다 — True 가 조용히 1 이 되는 것을 막는다.
        # 3.0 같은 JSON float 도 거절한다("정수여야 한다"는 계약을 반올림으로 대신하지 않는다).
        if isinstance(v, bool) or not isinstance(v, int):
            return None, (f"effort.{field} must be an integer (got "
                          f"{type(v).__name__}: {v!r}) - effort discarded.")
        if v < 0:
            return None, f"effort.{field} must be >= 0 (got {v}) - effort discarded."
        counts[field] = v

    return (session_id, counts["key"], counts["mouse"],
            counts["nav"], counts["nav_preserved"]), None


@app.put("/tables/{table_name}/data/updates")
async def apply_batch_updates_endpoint(
    table_name: str,
    batch: schemas.GeneralUpdateBatch,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """단건 및 다건 업데이트를 통합 처리하고 브로드캐스트합니다."""
    from fastapi.concurrency import run_in_threadpool
    # [V1 instrument] The instrument must never be able to destroy the operation it
    # measures (fix round F4). A malformed `effort` blob is DISCARDED and reported - in
    # the response (`effort_error`) and in the server log, by the offending key name -
    # while the correction proceeds untouched. Absent effort stays legal ("not measured").
    effort_counts, effort_error = _validate_effort(batch.effort)
    # Same defect one level up (F7): `{"efort": {...}}` parsed fine and the whole
    # measurement silently never happened. Report the misspelling, never block on it.
    unknown_top = sorted((batch.model_extra or {}).keys())
    if unknown_top:
        top_msg = (f"unknown top-level field(s): {', '.join(unknown_top)} - ignored. "
                   f"If one of these was meant to be 'effort', this correction was NOT "
                   f"measured.")
        effort_error = f"{effort_error} | {top_msg}" if effort_error else top_msg
    if effort_error:
        logger.error(f"[EffortMetric] table={table_name} {effort_error}")
    # [U6] replace_map honesty contract: crud fills this with the EXACT purge filters and
    # the purged row count (same resolver that built the DELETE), and it is echoed back
    # as response.scope. No derivable scope raises ValueError in crud -> 400 here, never
    # the historical silent 200-noop.
    replace_report = {} if batch.replace_map else None
    try:
        results, changed_cells, created_logs, deleted_row_ids = await run_in_threadpool(
            crud.apply_batch_updates, db, table_name, batch, replace_report
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    replace_scope = None
    if replace_report is not None:
        replace_scope = {
            "filters": replace_report.get("filters"),
            "deleted": replace_report.get("deleted", 0),
            # Rows newly created by this payload (a scope wipe with an empty payload
            # legitimately reports inserted: 0 - the caller must surface that).
            "inserted": sum(1 for _, is_new in results if is_new),
        }

    # A pure scope wipe (deleted > 0, no upserts) must still invalidate the count cache.
    if results or (replace_scope and replace_scope["deleted"] > 0):
        invalidate_table_cache(table_name)
    
    cfg = crud.TABLE_CONFIG.get(table_name, {})
    col_types = cfg.get("column_types", {})
    user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]
    row_objects = [r for r, _ in results]

    # [C-1 Fix] fetch_and_merge_metadata(동기 DB 쿼리 + O(행×컬럼) 병합 루프)와 msg_items 구성
    # (ORM 속성 접근 → 잠재적 lazy-load)을 async 핸들러 본문에서 실행하면 uvicorn 단일 이벤트
    # 루프가 통째로 동결된다(라이브 실측 7초 freeze의 주범). threadpool로 격리한다.
    def _merge_and_build_items():
        if row_objects:
            fetch_and_merge_metadata(db, table_name, row_objects, user_cols, include_sources=False)
        items = []
        for row, is_new in results:
            inject_system_columns(row)
            items.append({
                "row_id": row.row_id,
                "is_new": is_new,
                "data": row.data,
                "created_at": to_local_str(row.created_at),
                "updated_at": to_local_str(row.updated_at)
            })
        return items

    msg_items = await run_in_threadpool(_merge_and_build_items)

    # WebSocket 브로드캐스트를 백그라운드 태스크로 이관하여 즉시 HTTP 200 반환!
    if not batch.silent:
        user_name = batch.updates[0].updated_by if batch.updates else "system"
        tx_id = created_logs[0]["transaction_id"] if created_logs else (batch.transaction_id or str(uuid.uuid4()))
        
        async def async_broadcast():
            if deleted_row_ids:
                delete_msg = {
                    "event": "batch_row_delete",
                    "table_name": table_name,
                    "row_ids": deleted_row_ids
                }
                await manager.broadcast(json.dumps(delete_msg))

            if len(msg_items) > 100:
                msg = {
                    "event": "batch_refresh_required",
                    "table_name": table_name,
                    "change_count": len(msg_items)
                }
                if created_logs and len(created_logs) <= 5000:
                    msg["created_logs"] = created_logs
                await manager.broadcast(json.dumps(msg))
            else:
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

        background_tasks.add_task(async_broadcast)

    # [V1 계기] 교정이 **이미 커밋된 뒤에** 별도 트랜잭션으로 공수를 기록한다.
    # 계측이 계측 대상을 깨뜨려서는 안 되므로 실패해도 요청은 성공으로 끝난다.
    #
    # 기록 조건 = "이 tx 가 사람이 쓴 감사 로그를 실제로 남겼는가". 이유는 커버리지 비율의
    # 모집단 정합이다 — `measured_ratio` 의 분모는 창 안의 **사람 tx 수**(audit_logs 의
    # source_name='user' distinct tx)다. 아무것도 바꾸지 않은 tx(has_changed 가드에 전부
    # 걸린 no-op)나 자동 소스 tx까지 계측 행을 남기면 분자가 분모에 없는 tx를 세어 비율이
    # 1을 넘고, 그 순간 비율은 커버리지가 아니라 잡음이 된다.
    #   ⚠️ A NO-OP SAVE COSTS EFFORT THAT IS NOT RECORDED HERE, and the client must not
    #   throw it away either: it clears its counters only when `effort_recorded` is true
    #   (F1, 2026-07-29). Measured live: an operator spends 20 keys + 5 clicks correcting
    #   a cell whose stored value already matches (stale grid, or the whitespace/numeric
    #   normalisation in crud's has_changed guard), gets no audit log and therefore no
    #   effort row, then redoes it properly with 3 keys + 1 click. Resetting on `res.ok`
    #   scored that two-attempt correction 6 against a true cost of ~40 - the highest-
    #   friction event in the product reporting the LOWEST score in the dataset. The
    #   recording condition below is still right (a no-op is not a completed correction,
    #   and recording one would break measured_ratio's population match); what was wrong
    #   was letting the client believe it had been recorded.
    #
    # ⚠️ 위치가 계약이다 — 반드시 `msg_items` 구성이 **끝난 뒤**에 둔다. 여기서 커밋하면
    # 세션의 ORM 인스턴스가 expire 되므로, 그 이후에 `row.*` 속성을 읽는 코드를 추가하면
    # 응답 경로에 뜻밖의 리로드 쿼리가 생긴다. msg_items 는 이미 평범한 dict 로 떠 있다.
    effort_recorded = False
    if effort_counts is not None:
        tx_for_effort = next(
            (l["transaction_id"] for l in created_logs
             if l.get("source_name") == crud.USER_SOURCE), None)
        if tx_for_effort:
            session_id, k, m, n, n_kept = effort_counts
            # False here also covers "a row for this tx already existed" (client retry,
            # first write wins). Unreachable through this endpoint today - the tx id is
            # minted per crud call unless the caller supplies one - and treating it as
            # not-recorded is the conservative side: the client keeps counting.
            effort_recorded = bool(await run_in_threadpool(
                crud.record_interaction_effort, db, tx_for_effort, session_id,
                k, m, n, n_kept))

    return {
        "status": "success",
        "updated_count": len(results),
        "change_count": len(changed_cells),
        "deleted_row_ids": deleted_row_ids,
        "created_logs": created_logs,
        # [V1 instrument] Did THIS request durably store the effort it was sent?
        # The client resets its counters only on true - false means the effort is still
        # unspent human work and must ride the next attempt (F1).
        "effort_recorded": effort_recorded,
        # Why the effort was discarded, if it was. Null on the normal path. Never a
        # reason to fail the request - the correction above has already been applied.
        "effort_error": effort_error,
        # [U6] null unless replace_map; otherwise {filters, deleted, inserted} - the exact
        # purge scope used, so a caller can detect "deleted 0 while expecting replacement".
        "scope": replace_scope
    }




from pydantic import BaseModel

class GraphSyncRequest(BaseModel):
    table_name: str
    row_ids: Optional[list[str]] = None

@app.post("/api/graph/sync")
async def manual_graph_sync(req: Optional[GraphSyncRequest] = None, db: Session = Depends(get_db)):
    """관리자 수동 트리거 그래프 DB 동기화 API (상시 가동 GraphSync 서버 호출 위임)"""
    import httpx
    
    table_name = req.table_name if req else "all"
    row_ids = req.row_ids if req and req.row_ids else []
    
    port = int(os.getenv("GRAPH_SYNC_PORT", "8090"))
    url = f"http://127.0.0.1:{port}/sync"
    
    logger.info(f"[GraphSync Routing] Forwarding sync request to worker service at {url}")
    
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                url,
                json={"table_name": table_name, "row_ids": row_ids},
                timeout=120.0
            )
            if res.status_code == 200:
                resp_data = res.json()
                if resp_data.get("status") == "accepted":
                    return {
                        "status": "success",
                        "mode": "accepted",
                        "synced_count": len(row_ids) if row_ids else 0,
                        "deleted_count": 0,
                        "message": resp_data.get("message", "")
                    }
                return resp_data
            else:
                try:
                    err_detail = res.json().get("detail", "알 수 없는 오류")
                except Exception:
                    err_detail = res.text
                logger.error(f"[GraphSync Routing] Sync worker failed: {res.status_code} - {err_detail}")
                raise HTTPException(status_code=res.status_code, detail=f"그래프 동기화 서버 에러: {err_detail}")
        except httpx.RequestError as e:
            logger.error(f"[GraphSync Routing] Failed to connect to sync worker service: {e}")
            raise HTTPException(
                status_code=503,
                detail="그래프 동기화 서비스가 가동 중이 아닙니다. graph_sync_worker.py 가 실행되어 있는지 확인하세요."
            )


# ----------------- [Ontology 뷰어] read-only 그래프 조회 API (경계 계약 — 총괄 승인) -----------------
# graph_nodes/graph_edges를 웹서버가 직접 조회한다(read-only — 워커 경유 불필요).
# G2 추적 리포트가 같은 응답 형태를 공유할 예정이므로 필드는 최소로 유지(과설계 금지).

GRAPH_NEIGHBOR_NODE_CAP = 500        # limit 하드캡 — 무제한 로드 금지(C-7 교훈)
GRAPH_NEIGHBOR_EDGE_FETCH_CAP = 2000  # 홉·방향당 엣지 페치 상한 (수퍼노드 방어)
GRAPH_SEARCH_LIMIT_CAP = 50
GRAPH_LABEL_LIST_LIMIT_CAP = 200     # 빈 q + label 리스팅 페이지 하드캡 (뷰어 200 규율과 동일)
GRAPH_TRACE_NODE_CAP = 1000          # [G2] trace 노드 하드캡 (경계 계약 — 총괄 고정)
GRAPH_TRACE_DEPTH_CAP = 3            # [G2] trace depth 하드캡
GRAPH_TRACE_DEFAULT_LIMIT = 500


def _escape_like_term(term: str) -> str:
    """LIKE 패턴 메타문자 이스케이프 (escape='\\'와 짝)."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _expand_graph_subgraph(
    db: Session,
    seed_nodes: list,
    depth: int,
    node_cap: int,
    edge_types: Optional[list] = None,
    time_from=None,
    time_to=None,
):
    """시드 노드 집합에서 k-hop BFS로 서브그래프를 수집한다 (뷰어/추적 공용 코어).

    - 엣지 접근은 (from,type)/(to,type) 인덱스 경로만 사용(방향별 2쿼리).
    - edge_types: 지정(비어있지 않은 리스트) 시 해당 타입 엣지만 확장.
    - time_from/time_to: 엣지 event_time 범위 필터 — event_time이 NULL인 엣지는
      구조 엣지이므로 항상 통과(경계 계약 — 배제 금지).
    - node_cap 도달로 일부가 잘리면 truncated=True. 잘린 노드로 향하는 엣지는 응답에서 제외.
    반환: (nodes {id: GraphNode}, edges_out [직렬화 dict], truncated)
    """
    from sqlalchemy import and_, or_

    nodes = {n.id: n for n in seed_nodes}
    collected_edges = []
    seen_edge_ids = set()
    truncated = False
    frontier = list(nodes.keys())

    time_conds = []
    if time_from is not None:
        time_conds.append(models.GraphEdge.event_time >= time_from)
    if time_to is not None:
        time_conds.append(models.GraphEdge.event_time <= time_to)

    for _hop in range(depth):
        if not frontier:
            break
        hop_edges = []
        # idx_graph_edges_from_type / idx_graph_edges_to_type 프리픽스 룩업
        for endpoint_col in (models.GraphEdge.from_node, models.GraphEdge.to_node):
            query = db.query(models.GraphEdge).filter(endpoint_col.in_(frontier))
            if edge_types:
                query = query.filter(models.GraphEdge.type.in_(edge_types))
            if time_conds:
                query = query.filter(
                    or_(models.GraphEdge.event_time.is_(None), and_(*time_conds))
                )
            rows = (
                query.order_by(models.GraphEdge.id.asc())
                .limit(GRAPH_NEIGHBOR_EDGE_FETCH_CAP)
                .all()
            )
            if len(rows) >= GRAPH_NEIGHBOR_EDGE_FETCH_CAP:
                truncated = True
            hop_edges.extend(rows)

        new_ids = []
        new_seen = set()
        for e in hop_edges:
            if e.id in seen_edge_ids:
                continue
            seen_edge_ids.add(e.id)
            collected_edges.append(e)
            for nid in (e.from_node, e.to_node):
                if nid not in nodes and nid not in new_seen:
                    new_seen.add(nid)
                    new_ids.append(nid)

        capacity = node_cap - len(nodes)
        if len(new_ids) > capacity:
            truncated = True
            new_ids = new_ids[: max(capacity, 0)]

        for i in range(0, len(new_ids), 500):
            chunk = new_ids[i : i + 500]
            for n in db.query(models.GraphNode).filter(models.GraphNode.id.in_(chunk)).all():
                nodes[n.id] = n
        frontier = new_ids

    node_ids = set(nodes.keys())
    edges_out = [
        {
            "from": e.from_node,
            "to": e.to_node,
            "type": e.type,
            "source_name": e.source_name,
            "updated_by": e.updated_by,
            "event_time": e.event_time.isoformat() if e.event_time else None,
        }
        for e in collected_edges
        if e.from_node in node_ids and e.to_node in node_ids   # 캡으로 잘린 노드의 엣지 제외
    ]
    return nodes, edges_out, truncated


def _serialize_graph_nodes(nodes: dict) -> list:
    """노드 형태 계약 {id, label, identity_key, props} — 뷰어/추적 공용."""
    return [
        {"id": n.id, "label": n.label, "identity_key": n.identity_key, "props": n.props or {}}
        for n in nodes.values()
    ]


@app.get("/graph/stats")
def get_graph_stats(db: Session = Depends(get_db)):
    """뷰어 첫 화면 + 라이브 검증용 — label/edge_type별 카운트와 마지막 동기화 시각."""
    from sqlalchemy import func as sa_func

    label_rows = (
        db.query(models.GraphNode.label, sa_func.count(models.GraphNode.id))
        .group_by(models.GraphNode.label)
        .order_by(sa_func.count(models.GraphNode.id).desc())
        .all()
    )
    type_rows = (
        db.query(models.GraphEdge.type, sa_func.count(models.GraphEdge.id))
        .group_by(models.GraphEdge.type)
        .order_by(sa_func.count(models.GraphEdge.id).desc())
        .all()
    )
    state = db.query(models.GraphSyncState).filter(models.GraphSyncState.id == 1).first()
    return {
        "labels": [{"label": lbl, "count": cnt} for lbl, cnt in label_rows],
        "edge_types": [{"type": typ, "count": cnt} for typ, cnt in type_rows],
        "last_sync": state.updated_at.isoformat() if state and state.updated_at else None,
    }


@app.get("/graph/neighbors")
def get_graph_neighbors(
    label: str,
    identity: str,
    depth: int = 1,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    """중심 노드 (label, identity)에서 k-hop 이웃 서브그래프를 반환한다.

    - limit = 응답 노드 총수 상한(중심 포함), 하드캡 GRAPH_NEIGHBOR_NODE_CAP.
    - 엣지 접근은 (from,type)/(to,type) 인덱스 경로만 사용(방향별 2쿼리).
    - 상한 도달로 일부가 잘리면 truncated=True.
    """
    if depth not in (1, 2):
        raise HTTPException(status_code=400, detail="depth는 1 또는 2만 허용됩니다.")
    limit = max(1, min(int(limit), GRAPH_NEIGHBOR_NODE_CAP))

    center = (
        db.query(models.GraphNode)
        .filter(models.GraphNode.label == label, models.GraphNode.identity_key == identity)
        .first()
    )
    if center is None:
        raise HTTPException(status_code=404, detail=f"노드를 찾을 수 없습니다: ({label}, {identity})")

    nodes, edges_out, truncated = _expand_graph_subgraph(db, [center], depth, limit)

    return {
        "nodes": _serialize_graph_nodes(nodes),
        "edges": edges_out,
        "truncated": truncated,
    }


@app.get("/graph/nodes/search")
def search_graph_nodes(
    q: str = "",
    label: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """identity_key 시작일치 자동완성 (label 지정 시 (label, identity_key) 인덱스 경로).

    - 빈 q + label → 해당 라벨 전체 리스팅 (Stats 라벨 카드 → 노드 리스트,
      limit/offset 페이지네이션, 캡 GRAPH_LABEL_LIST_LIMIT_CAP).
    - 빈 q + label 없음 → 빈 결과 (전 테이블 덤프 금지 — C-7 무제한 로드 금지).
    - offset은 두 모드 공통 지원 (identity_key 오름차순 안정 정렬 전제).
    """
    term = (q or "").strip()
    if not term and not label:
        return {"results": []}
    cap = GRAPH_SEARCH_LIMIT_CAP if term else GRAPH_LABEL_LIST_LIMIT_CAP
    limit = max(1, min(int(limit), cap))
    offset = max(0, int(offset))

    query = db.query(models.GraphNode.id, models.GraphNode.label, models.GraphNode.identity_key)
    if label:
        query = query.filter(models.GraphNode.label == label)
    if term:
        query = query.filter(
            models.GraphNode.identity_key.ilike(_escape_like_term(term) + "%", escape="\\")
        )
    rows = (
        query.order_by(models.GraphNode.label.asc(), models.GraphNode.identity_key.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "results": [
            {"id": r.id, "label": r.label, "identity_key": r.identity_key} for r in rows
        ]
    }


# ----------------- [Ontology G2] 추적(trace) API (경계 계약 — 총괄 고정) -----------------
# 킬러 유스케이스: 그리드에서 불량 개체들 선택 → 멀티 시드 BFS 합집합으로 연관 전체 추적.
# 응답 노드/엣지 형태는 뷰어(/graph/neighbors)와 동일 계약을 공유한다.

class GraphTraceSeed(BaseModel):
    label: str
    identity: str


class GraphTraceRequest(BaseModel):
    seeds: list[GraphTraceSeed]
    depth: int = 2
    # 시간 필터는 문자열로 받아 핸들러에서 파싱 — 형식 오류를 계약대로 400으로 응답하기 위함
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    edge_types: Optional[list[str]] = None
    limit: int = GRAPH_TRACE_DEFAULT_LIMIT


def _parse_trace_time(value: Optional[str], field: str):
    """ISO 8601 문자열 → datetime. 형식 오류는 400 (경계 계약: 검증 실패 400)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"{field}은(는) ISO 8601 형식이어야 합니다: {value!r}"
        )


@app.post("/graph/trace")
def post_graph_trace(req: GraphTraceRequest, db: Session = Depends(get_db)):
    """멀티 시드 k-hop 추적 — 시드별 BFS의 합집합 서브그래프를 반환한다.

    - depth 1..3 (기본 2), 노드 하드캡 GRAPH_TRACE_NODE_CAP(수퍼노드 방어 — 뷰어 패턴 준용).
    - time_from/to: 엣지 event_time 범위 필터. event_time이 NULL인 구조 엣지는 항상 통과.
    - edge_types 지정 시 해당 타입 엣지만 확장.
    - 존재하지 않는 시드는 무시하고 missing_seeds로 보고. 전부 미존재여도 404가 아니라
      빈 nodes로 200 응답(경계 계약).
    """
    if not req.seeds:
        raise HTTPException(status_code=400, detail="seeds는 1개 이상이어야 합니다.")
    if not (1 <= req.depth <= GRAPH_TRACE_DEPTH_CAP):
        raise HTTPException(
            status_code=400, detail=f"depth는 1..{GRAPH_TRACE_DEPTH_CAP}만 허용됩니다."
        )
    time_from = _parse_trace_time(req.time_from, "time_from")
    time_to = _parse_trace_time(req.time_to, "time_to")
    limit = max(1, min(int(req.limit), GRAPH_TRACE_NODE_CAP))

    # 시드 해석 — 요청 순서 보존 dedup 후 label 그룹별 (label, identity_key) 인덱스 조회(500 청킹)
    requested = []
    seen_pairs = set()
    for s in req.seeds:
        pair = (s.label, s.identity)
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            requested.append(pair)

    identities_by_label = {}
    for lbl, ident in requested:
        identities_by_label.setdefault(lbl, []).append(ident)
    found = {}
    for lbl, identities in identities_by_label.items():
        for i in range(0, len(identities), 500):
            chunk = identities[i : i + 500]
            rows = (
                db.query(models.GraphNode)
                .filter(
                    models.GraphNode.label == lbl,
                    models.GraphNode.identity_key.in_(chunk),
                )
                .all()
            )
            for n in rows:
                found[(n.label, n.identity_key)] = n

    missing_seeds = [
        {"label": lbl, "identity": ident}
        for (lbl, ident) in requested
        if (lbl, ident) not in found
    ]
    seed_nodes = [found[p] for p in requested if p in found]

    truncated = False
    if len(seed_nodes) > limit:   # 시드 자체가 캡 초과 — 하드캡 우선(무제한 로드 금지)
        seed_nodes = seed_nodes[:limit]
        truncated = True

    if seed_nodes:
        nodes, edges_out, bfs_truncated = _expand_graph_subgraph(
            db, seed_nodes, req.depth, limit,
            edge_types=req.edge_types, time_from=time_from, time_to=time_to,
        )
        truncated = truncated or bfs_truncated
    else:
        nodes, edges_out = {}, []

    return {
        "nodes": _serialize_graph_nodes(nodes),
        "edges": edges_out,
        "seed_ids": [n.id for n in seed_nodes],
        "missing_seeds": missing_seeds,
        "truncated": truncated,
    }


@app.get("/graph/mapping-summary")
def get_graph_mapping_summary():
    """현재 로드된 온톨로지 매핑(enrichment RESOLVED_AS 자동 승격 포함) 요약.

    클라이언트가 그리드 선택 행 → trace 시드 변환에 사용한다(경계 계약).
    materializer(_load_graph_mappings)와 같은 로더를 태워 같은 신호원을 보장하고,
    config 파일이 작으므로 요청 시마다 디스크에서 읽는다(무중단 반영 — enrichment 패턴).
    매핑 없는 테이블은 포함하지 않는다.
    """
    import ontology_config
    known = crud.TABLE_CONFIG if crud.TABLE_CONFIG else None
    mappings = ontology_config.load_ontology_mappings(known_tables=known)
    return {
        "tables": [
            {
                "table": table_name,
                "node_label": m["node"]["label"],
                "identity_columns": list(m["node"]["identity"]),
            }
            for table_name, m in sorted(mappings.items())
        ]
    }


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
    # 1. 대상 디렉토리 결정 (<data root>/ingestion_workspace/{table_name}/raws)
    target_dir = paths.workspace_path(table_name, "raws")
    
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
def get_cell_sources(table_name: str, row_id: str, col_name: str, db: Session = Depends(get_db)):
    # [C-1 Fix] await가 없는 순수 동기 핸들러 — def로 전환해 FastAPI가 threadpool에서 실행(루프 비블로킹)
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
    # [C-1 Fix] 동기 crud + ORM 속성 접근을 threadpool로 격리
    from fastapi.concurrency import run_in_threadpool

    def _delete_and_build():
        updated_row, changed_cols = crud.delete_cell_source(db, table_name, row_id, col_name, source_name)
        if not updated_row:
            return None
        inject_system_columns(updated_row)
        return {
            "row_id": row_id,
            "is_new": False,
            "data": updated_row.data,
            "created_at": to_local_str(updated_row.created_at),
            "updated_at": to_local_str(updated_row.updated_at)
        }, len(changed_cols)

    built = await run_in_threadpool(_delete_and_build)
    if not built:
        raise HTTPException(status_code=404, detail="Source or Cell not found")
    item, change_count = built

    # WebSocket 브로드캐스트 (통합 규격: batch_row_upsert 사용)
    await manager.broadcast(json.dumps({
        "event": "batch_row_upsert",
        "table_name": table_name,
        "items": [item],
        "change_count": change_count
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
    # [C-1 Fix] 동기 crud + fetch_and_merge_metadata를 threadpool로 격리
    from fastapi.concurrency import run_in_threadpool

    def _apply_and_merge_single():
        updated_row, changed_cols, deleted = crud.set_cell_manual_priority(db, table_name, row_id, col_name, source_name, updated_by)
        if not updated_row:
            return None, None, None
        cfg = crud.TABLE_CONFIG.get(table_name, {})
        col_types = cfg.get("column_types", {})
        user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]
        merged = fetch_and_merge_metadata(db, table_name, [updated_row], user_cols, include_sources=True)
        return merged, changed_cols, deleted

    merged_rows, changed_cols, deleted_row_ids = await run_in_threadpool(_apply_and_merge_single)
    if merged_rows is None:
        raise HTTPException(status_code=404, detail="Cell not found or source invalid")
    if not merged_rows:
        raise HTTPException(status_code=500, detail="Failed to serialize updated row")

    merged_item = merged_rows[0]

    # 껍데기 행 실시간 제거 브로드캐스트 전송
    if deleted_row_ids:
        await manager.broadcast(json.dumps({
            "event": "batch_row_delete",
            "table_name": table_name,
            "row_ids": deleted_row_ids
        }))

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
    return {"status": "success", "row_id": row_id, "deleted_row_ids": deleted_row_ids}

@app.get("/tables/{table_name}/rows/{row_id}/cells/{col_name}/history")
def get_cell_history(table_name: str, row_id: str, col_name: str, db: Session = Depends(get_db)):
    # [C-1 Fix] await가 없는 순수 동기 핸들러 — def로 전환해 threadpool 실행(루프 비블로킹)
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
    # [C-1 Fix] 동기 배치 crud + fetch_and_merge_metadata(include_sources=True)를 threadpool로 격리
    from fastapi.concurrency import run_in_threadpool

    def _apply_and_merge():
        changed, logs, deleted = crud.set_cell_manual_priority_batch(
            db, table_name, req.updates, req.source_name, req.updated_by
        )
        merged = []
        if changed:
            cfg = crud.TABLE_CONFIG.get(table_name, {})
            col_types = cfg.get("column_types", {})
            user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]
            merged = fetch_and_merge_metadata(db, table_name, changed, user_cols, include_sources=True)
        return changed, logs, deleted, merged

    changed_rows, created_logs, deleted_row_ids, merged_items = await run_in_threadpool(_apply_and_merge)

    if changed_rows:
        invalidate_table_cache(table_name)

        # 껍데기 행 실시간 제거 브로드캐스트 전송
        if deleted_row_ids:
            await manager.broadcast(json.dumps({
                "event": "batch_row_delete",
                "table_name": table_name,
                "row_ids": deleted_row_ids
            }))

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
            
    return {"status": "success", "count": len(changed_rows), "deleted_row_ids": deleted_row_ids}

@app.post("/tables/{table_name}/cells/sources/delete/batch")
async def delete_cell_source_batch_endpoint(
    table_name: str,
    req: schemas.BatchCellSourceDeleteRequest,
    db: Session = Depends(get_db)
):
    """여러 셀의 특정 데이터 원천(Source)을 일괄 삭제합니다."""
    # [C-1 Fix] 동기 배치 crud + fetch_and_merge_metadata(include_sources=True)를 threadpool로 격리
    from fastapi.concurrency import run_in_threadpool

    def _delete_and_merge():
        changed, logs = crud.delete_cell_source_batch(db, table_name, req.cells, req.source_name)
        merged = []
        if changed:
            cfg = crud.TABLE_CONFIG.get(table_name, {})
            col_types = cfg.get("column_types", {})
            user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]
            merged = fetch_and_merge_metadata(db, table_name, changed, user_cols, include_sources=True)
        return changed, logs, merged

    changed_rows, created_logs, merged_items = await run_in_threadpool(_delete_and_merge)

    if changed_rows:
        invalidate_table_cache(table_name)

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

@app.post("/admin/outbox/retry-failed", dependencies=[Depends(require_admin_token)])
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
            if (get_payload_dict(e).get("transaction_id") == transaction_id) or
               (f"single_{e.event_uuid}" == transaction_id)
        ]
        
    if not failed_events:
        return {"status": "success", "message": "No matching failed outbox events found."}
        
    for event in failed_events:
        event.status = "PENDING"
        event.retry_count = 0
        event.processed_chain = False
        pay_dict = get_payload_dict(event)
        if pay_dict and "error_log" in pay_dict:
            payload_copy = dict(pay_dict)
            if isinstance(payload_copy.get("error_log"), dict):
                payload_copy["error_log"] = dict(payload_copy["error_log"])
                payload_copy["error_log"]["resolved_at"] = datetime.now().isoformat()
            event.payload = payload_copy
            
    db.commit()
    return {"status": "success", "message": f"Successfully reset {len(failed_events)} failed events to PENDING."}

@app.get("/admin/outbox/failed", dependencies=[Depends(require_admin_token)])
def get_failed_outbox_events(page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
    """실패(FAILED) 상태로 격리된 Outbox 체인 이벤트 목록을 transaction_id 단위로 묶고 페이지네이션하여 반환합니다."""
    query = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.status == "FAILED"
    ).order_by(models.DatabaseOutbox.id.desc())
    
    all_failed = query.all()
    
    from collections import defaultdict
    groups = defaultdict(list)
    for e in all_failed:
        tx_id = get_payload_dict(e).get("transaction_id")
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

@app.get("/admin/file-ingestion/logs", dependencies=[Depends(require_admin_token)])
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

@app.get("/admin/file-ingestion/failed", dependencies=[Depends(require_admin_token)])
def get_failed_file_ingestion_logs(page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
    """실패(FAILED) 상태인 File Ingestion 로그 목록을 페이지네이션하여 반환합니다."""
    return get_file_ingestion_logs(status="FAILED", page=page, limit=limit, db=db)


@app.get("/admin/file-ingestion/active", dependencies=[Depends(require_admin_token)])
def get_active_file_ingestions():
    """[Heavy Lane P1] 진행 중 파일 인제션 스냅샷 (admin File 탭 진행 목록·재기동 경고용).

    원천은 watcher 프로세스가 /internal/events/*로 push한 인메모리 레지스트리 —
    DB 조회 없음(O(진행 중 파일 수), 상시 소수). 항목: 파일명·테이블·레인(heavy/normal)·
    상태(QUEUED/PROCESSING)·진행률·행 수·경과 초."""
    data = ingestion_activity_registry.snapshot()
    return {
        "status": "success",
        "total": len(data),
        "data": data,
    }

def reload_local_process_cache():
    """웹 서버 프로세스의 table_config 캐시 및 동적 모듈 캐시(mappers, pipeline plugins)를 명시적으로 무효화합니다.

    [이슈 #7] config 재로드 시 TABLE_CONFIG 싱글턴·DYNAMIC_TABLES(ORM) 갱신과 함께
    런타임에 추가된 신규 테이블의 물리 CREATE까지 동기적으로 수행한다
    (watchdog 스레드 디바운스 타이밍에 의존하지 않는 결정적 경로 — 기존 테이블 ALTER는 범위 밖).
    """
    import sys

    try:
        created = models.refresh_dynamic_models(engine)
        if created:
            logger.info(f"[Reload] Created missing physical tables at runtime: {created}")
    except Exception as e:
        print(f"[Reload] Failed to reload table_config.json: {e}")
        
    # [Ontology G1] 온톨로지 매핑 캐시 무효화(핫리로드 대상 — check_needs_rollback 판정용)
    try:
        crud._ontology_cache = None
    except Exception:
        pass

    # Remove custom mappers from sys.modules cache
    mapper_keys = [k for k in sys.modules.keys() if k.startswith("mappers.")]
    for k in mapper_keys:
        sys.modules.pop(k, None)
        
    # Remove pipeline plugin parsers from sys.modules cache
    plugin_keys = [k for k in sys.modules.keys() if k.startswith("pipeline_plugin_")]
    for k in plugin_keys:
        sys.modules.pop(k, None)
        
    print("[Reload] Local web server process cache successfully cleared.")

@app.post("/admin/reload-configs", dependencies=[Depends(require_admin_token)])
def reload_system_configs(db: Session = Depends(get_db)):
    """시스템 전역의 설정 및 파이썬 모듈 캐시를 리로드하는 이벤트를 Outbox에 적재하여 모든 워커에 전파합니다."""
    import uuid
    from datetime import datetime
    from sqlalchemy import text
    
    # 1. 웹 서버 자체 메모리 캐시 갱신
    reload_local_process_cache()

    # 1-1. [Std Ingestion] 임베디드 워처(비-decoupled 모드) 사용 시 신규 테이블 워크스페이스
    #      자동 생성 + 런타임 감시 등록. decoupled 모드에서는 run_watcher.py의 SYSTEM_RELOAD
    #      폴러가 동일 처리를 담당한다.
    if global_watcher is not None:
        try:
            global_watcher.sync_new_workspaces()
        except Exception as e:
            logger.error(f"[Reload] Embedded watcher workspace sync failed: {e}")

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

# -----------------------------------------------------------------------------
# Map Geometry & Offset Presets Endpoints (<data root>/config/maps.json)
# -----------------------------------------------------------------------------
MAPS_CONFIG_PATH = paths.config_path("maps.json")

def load_maps_config() -> dict:
    if os.path.exists(MAPS_CONFIG_PATH):
        try:
            with open(MAPS_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Maps Config] Error loading maps.json: {e}")
    return {"presets": {}}

def save_maps_config(data: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(MAPS_CONFIG_PATH), exist_ok=True)
        with open(MAPS_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[Maps Config] Error saving maps.json: {e}")
        return False

class MapPresetItem(BaseModel):
    preset_key: Optional[str] = None
    name: str
    phys_wafer_dia: float = 300.0
    phys_chip_x: float = 2.5
    phys_chip_y: float = 2.5
    phys_offset_x: float = 0.0
    phys_offset_y: float = 0.0
    phys_edge_margin: float = 3.0
    rotation: int = 0
    side: str = "front"

@app.get("/map-presets")
@app.get("/api/map-presets")
def get_map_presets():
    """서버 config/maps.json에 저장된 웨이퍼 물리 규격 및 오프셋 프리셋 목록을 반환합니다."""
    config_data = load_maps_config()
    return {"status": "success", "presets": config_data.get("presets", {})}

def _save_map_preset_impl(item: MapPresetItem):
    config_data = load_maps_config()
    presets = config_data.get("presets", {})
    
    key = item.preset_key or f"custom_{int(time.time() * 1000)}"
    preset_entry = {
        "name": item.name,
        "phys_wafer_dia": item.phys_wafer_dia,
        "phys_chip_x": item.phys_chip_x,
        "phys_chip_y": item.phys_chip_y,
        "phys_offset_x": item.phys_offset_x,
        "phys_offset_y": item.phys_offset_y,
        "phys_edge_margin": item.phys_edge_margin,
        "rotation": item.rotation,
        "side": item.side,
        "is_custom": True
    }
    presets[key] = preset_entry
    config_data["presets"] = presets
    
    if not save_maps_config(config_data):
        raise HTTPException(status_code=500, detail="Failed to save map preset to server config.")
        
    return {"status": "success", "preset_key": key, "preset": preset_entry}

@app.post("/map-presets")
def save_map_preset_root(item: MapPresetItem):
    return _save_map_preset_impl(item)

@app.post("/api/map-presets")
def save_map_preset_api(item: MapPresetItem):
    return _save_map_preset_impl(item)

def _delete_map_preset_impl(preset_key: str):
    config_data = load_maps_config()
    presets = config_data.get("presets", {})
    
    if preset_key not in presets:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_key}' not found.")
        
    del presets[preset_key]
    config_data["presets"] = presets
    
    if not save_maps_config(config_data):
        raise HTTPException(status_code=500, detail="Failed to update maps.json on deletion.")
        
    return {"status": "success", "message": f"Preset '{preset_key}' deleted successfully."}

@app.delete("/map-presets/{preset_key}")
def delete_map_preset_root(preset_key: str):
    return _delete_map_preset_impl(preset_key)

@app.delete("/api/map-presets/{preset_key}")
def delete_map_preset_api(preset_key: str):
    return _delete_map_preset_impl(preset_key)

# -----------------------------------------------------------------------------
# Bonding Experiment Plan (M1) — 코어 집계 API (경계 계약 — 총괄 고정)
# -----------------------------------------------------------------------------
import bonding_plan as bonding_plan_module

@app.get("/api/bonding-plan/core-summary")
def get_bonding_plan_core_summary(
    lot: str,
    slot: str,
    region: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """본딩 실험계획 Info 창용 코어(lot, slot) 집계 요약.

    - 역할 바인딩은 config/bonding_plan_config.json 경유(스냅샷은 요청당 1회) —
      역할 누락/테이블 부재는 'missing' 부분 가동(에러 아님).
    - region: URL 인코딩 JSON {"rects":[{"x1","y1","x2","y2"}]} (canonical 칩 좌표,
      복수 사각형 합집합). 형식 위반은 400. 맵 메타 규격 밖 rect는 클램프.
    - 칩 좌표 목록은 반환하지 않는다(집계만 — 페이로드 상한 규율).
    """
    config = bonding_plan_module.load_bonding_plan_config()
    rects = None
    if region is not None:
        try:
            rects = bonding_plan_module.parse_region(region)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid region parameter: {e}")
    try:
        return bonding_plan_module.get_core_summary(db, lot, slot, rects=rects, config=config)
    except Exception as e:
        logger.error(f"[BondingPlan] core-summary failed for ({lot}, {slot}): {e}")
        raise HTTPException(status_code=500, detail="Failed to compute core summary.")

# -----------------------------------------------------------------------------
# 범용 맵 오버레이 (S1') — 맵 인프라(계획 전용 아님). 경계 계약 — 총괄 고정
# -----------------------------------------------------------------------------
import map_overlay as map_overlay_module

@app.get("/api/maps/overlay")
def get_map_overlay(
    target_table: str,
    target_key: str,
    sources: str,
    eqp: Optional[str] = None,
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """임의의 맵들을 타깃 맵 캔버스 좌표로 정렬해 반환한다(범용 — 계획 전용 아님).

    - sources: "table" 또는 "table:key"의 CSV(키 생략 시 target_key 승계), 최대 8종.
    - 정렬은 각 맵의 wafer_map_metadata(rotation/side/start/치수/phys) 차이에서만 유도된다
      — 선언(align_overrides) 레이어는 제거됐다(정렬의 근거는 메타 하나뿐).
      유도 근거가 없으면 identity로 간주해 그대로 붙인다(메타 부재는 실패가 아니다).
      변환을 계산할 근거가 없을 때만 status=align_unavailable.
    - eqp: **폐기됨(no-op)**. align_overrides.by_eqp 분기 전용 파라미터였다. 기존 호출자가
      깨지지 않도록 시그니처만 남겨두었다 — 제거는 총괄 승인 사항.
    - 셀 목록을 반환하는 API이므로 상한 필수 — 초과 시 truncated:true로 명시한다.
    """
    config = map_overlay_module.load_overlay_config()
    try:
        src_list = map_overlay_module.parse_sources(sources)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    cap = map_overlay_module.MAX_OVERLAY_CELLS
    if limit is not None:
        try:
            cap = max(1, min(int(limit), map_overlay_module.MAX_OVERLAY_CELLS))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="limit must be an integer")
    try:
        return map_overlay_module.get_overlay(
            db, config, target_table, target_key, src_list, cell_cap=cap)
    except Exception as e:
        logger.error(f"[MapOverlay] overlay failed ({target_table}/{target_key}): {e}")
        raise HTTPException(status_code=500, detail="Failed to build map overlay.")

@app.get("/api/maps/paint-rules")
def get_map_paint_rules(table: Optional[str] = None):
    """맵 페인트 잠금 선언(정본은 서버 config — 클라는 읽어서 적용, 하드코딩 금지).

    [U6] Also serves the two map defaults so the client keeps no copy of its own:
    - value_column_candidates: RESOLVED ordered list (declared beats documented
      default — always present).
    - default_legend: declared legend rows for maps without registry rows,
      verbatim; null when undeclared (honest absence — no default semantics).
    [F1] binding: the RESOLVED coordinate binding for `table` (declared
      table_bindings win, else table_config derivation), shape
      {x, y, val, key_columns[], source: "declared"|"derived"|"fallback_guess"};
      null when unresolvable or when no table param. This response is the single
      client-facing source for the binding — the editor must consume it instead
      of re-deriving. [F2] "fallback_guess" means the value column is a guess the
      data paths refuse to use — the client must warn, not silently render it.
    """
    config = map_overlay_module.load_overlay_config()
    return {
        "table": table,
        "rules": map_overlay_module.get_paint_rules(config, table),
        "binding": (map_overlay_module.resolve_binding_info(config, table)
                    if table else None),
        "default_legend": map_overlay_module.get_default_legend(config),
        "value_column_candidates": map_overlay_module.resolve_value_column_candidates(config),
    }

# [M4 phase 1] 유효 다이(`valid_die_ref`)에 **새 REST 경로는 추가하지 않았다.**
# 클라 half는 이미 있는 셋(`/tables/{t}/data` + `/api/maps/paint-rules`의 binding +
# `/tables/{t}/schema`)으로 참조를 풀고 있으므로 새 경로에 소비자가 없고, REST 시그니처는
# 총괄 승인이 필요한 경계 계약이다. 서버측 해석기는 `map_overlay.resolve_valid_die_set`
# (모듈 함수)로 존재하며, 서버가 스스로 유효 다이를 판정해야 하는 phase 2/3에서 그것을
# 그대로 쓴다. 노출이 필요해지면 그때 승인을 받아 여기 한 곳에 얹는다.

# -----------------------------------------------------------------------------
# Universal Transfer Plan (M2) — 전사 프레임워크 API (경계 계약 — 총괄 고정)
# -----------------------------------------------------------------------------
import transfer_plan as transfer_plan_module

@app.get("/api/transfer-plan/stages")
def get_transfer_plan_stages():
    """선언된 전사 stage 목록 + 역할 연결 상태 (config 선언 해석만 — 행 조회 없음).

    stage 선언은 config/transfer_plan_config.json (스냅샷은 요청당 1회).
    역할/plan_store 누락은 'missing' 부분 가동(에러 아님).
    """
    config = transfer_plan_module.load_transfer_plan_config()
    try:
        return transfer_plan_module.list_stages(config)
    except Exception as e:
        logger.error(f"[TransferPlan] stages listing failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to list transfer plan stages.")

@app.get("/api/transfer-plan/source-summary")
def get_transfer_plan_source_summary(
    stage: str,
    lot: str,
    slot: Optional[str] = None,
    ref_table: Optional[str] = None,
    map_key: Optional[str] = None,
    bins: Optional[str] = None,
    scope: str = "slot",
    db: Session = Depends(get_db),
):
    """단계별 소스 가용 집계 — `(lot, slot)` 또는 `(lot 전체)`, 선택적으로 BIN별 분해.

    - 공통 형태: {identity, stage, source_kind, sources, chips{total, fail_breakdown,
      transferred, remaining}, history, warnings}
    - tape-kind(origin_log 연결) 소스면 by_core(출신 코어별 분해 — 집계만) 동봉.
    - 미선언 stage는 404. 역할 누락은 'missing'/'unavailable(...)' 부분 가동.
    - (ref_table, map_key) 지정 시 그 계획 맵이 이 소스에서 쓰기로 페인팅한 **셀 집합**을
      스코프로 `region_chips`(영역 내 가용)를 동봉한다. 영역 미저장/바인딩 미선언이면 생략.
      (v2 모델: 구 `plan_id` 파라미터 대체 — 계획 정체성이 곧 맵 정체성이다)
    - 칩 좌표 목록은 반환하지 않는다(집계만 — 페이로드 상한 규율).

    [BIN 축 — DOE_BAND_MODEL §4-bis]
    - `bins=1,2` 를 주면 `bins` 블록이 동봉된다. 요청한 BIN은 **전부** 답을 받으며,
      맵에 없는 BIN은 `status: "bin_absent"`다 — **절대 `0`이 아니다.** `0`은 "다 썼다"로
      읽히고 그러면 신뢰 불가한 `가용`에서 확정 `잔여`가 나온다.
    - `bins=` (빈 값)이면 맵에 있는 BIN을 전부 나열한다. 파라미터를 아예 생략하면 블록도
      없다 — 기존 소비자의 응답 크기가 변하지 않는다.
    - `scope=lot`은 자재 토큰의 **로트 전체**(`MID1:2` = 모든 슬롯) 형태다. 이때 `slot`은
      비어 있어야 하며, 응답은 `{identity{lot, slot:null}, scope, slots, bins, warnings}`로
      **`chips`를 싣지 않는다**(로트 단위 헤드라인 잔여는 아무도 요청하지 않은 숫자다).
      `scope=lot`에 `slot`을 함께 주면 400 — 두 형태는 겹쳐 답하지 않는다(B10 참조).
    """
    config = transfer_plan_module.load_transfer_plan_config()
    if scope not in (transfer_plan_module.BIN_SCOPE_SLOT, transfer_plan_module.BIN_SCOPE_LOT):
        raise HTTPException(status_code=400, detail=f"scope must be 'slot' or 'lot' (got '{scope}')")
    try:
        if scope == transfer_plan_module.BIN_SCOPE_LOT:
            if slot:
                # 로트 전체와 그 로트의 슬롯을 한 질의로 섞지 않는다. 섞으면 슬롯이 두 번
                # 계산되고, 부풀린 소요는 가장 나쁜 순간에 부족으로 나타난다(B10과 같은 규율).
                raise HTTPException(
                    status_code=400,
                    detail="scope=lot with a slot is ambiguous — omit slot for the whole lot")
            return transfer_plan_module.get_lot_bin_summary(db, config, stage, lot, bins=bins)
        if slot is None:
            raise HTTPException(status_code=400, detail="slot is required when scope=slot")
        return transfer_plan_module.get_stage_source_summary(
            db, config, stage, lot, slot, ref_table=ref_table, map_key=map_key, bins=bins)
    except HTTPException:
        raise
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[TransferPlan] source-summary failed for stage={stage} ({lot}, {slot}): {e}")
        raise HTTPException(status_code=500, detail="Failed to compute source summary.")

@app.get("/api/transfer-plan/validate")
def validate_transfer_plan(
    ref_table: str,
    map_key: str,
    db: Session = Depends(get_db),
):
    """계획 검증 — 경고 목록(수량 부족·구간 구조 결함·DOE 값-맵 정합·소스 fail).

    [v2 계획 모델] 계획 정체성은 **지금 열어 편집 중인 맵**(`ref_table`, `map_key`)이다.
    구 `plan_id` 파라미터는 폐기 — 계획 헤더 테이블도 계획 맵 사본도 존재하지 않는다.
    stage는 `stages.*.target_map.table` 역인덱스로 유도되며 미선언 맵은 `stage_unknown`
    경고 + `status: unverified`(404 아님 — 임의의 맵도 열 수 있어야 한다).

    [M2.6] 계획 저장소는 `map_split_registry` 하나다(값 1행 = DOE 1건, 구간은 `bands` JSON).
    수량은 저장되지 않고 `painted × layers`에서 유도된다. 구 STACK 커버리지 공백 검사는
    구간이 정의상 연속이라 사라졌고, 지금의 구조 결함은 `layer_range_invalid`가 낸다.

    plan_store.registry 미구성은 404.
    """
    config = transfer_plan_module.load_transfer_plan_config()
    try:
        return transfer_plan_module.validate_plan(db, config, ref_table, map_key)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[TransferPlan] validate failed for map '{ref_table}/{map_key}': {e}")
        raise HTTPException(status_code=500, detail="Failed to validate transfer plan.")

@app.get("/admin/file-ingestion/workspaces", dependencies=[Depends(require_admin_token)])
def get_ingestion_workspaces():
    """등록된 모든 파일 인제션 워크스페이스 목록을 반환합니다."""
    import os
    import json
    
    workspace_base = paths.WORKSPACE_DIR

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

            # [Deprecation 2026-07-25] 글로벌 table_config.json의 workspace_name 별칭이
            # 레거시 워크스페이스 config.json보다 우선한다 (충돌 시 table_config 승리).
            try:
                from directory_watcher import find_workspace_alias, load_global_table_config
                aliased = find_workspace_alias(name, load_global_table_config())
                if aliased is not None:
                    table_name = aliased
            except Exception as e:
                print(f"Error resolving workspace alias for '{name}': {e}")
            
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

@app.get("/admin/chain/rules", dependencies=[Depends(require_admin_token)])
def get_chain_rules():
    """등록된 모든 체인 인제션 룰 목록을 반환합니다."""
    import os
    import json
    
    rules_path = paths.config_path("chain_rules.json")
    
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

@app.get("/admin/mappers/list", dependencies=[Depends(require_admin_token)])
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

# -----------------------------------------------------------------------------
# Enrichment Queue Endpoints (docs/spec/ENRICHMENT_QUEUE_SPEC.md §5 — 경계 계약 확정분)
#   워크리스트/결손 카운트/저장은 기존 GET /tables/{t}/data + PUT /tables/{t}/data/updates 재사용.
#   신규는 아래 2종(규칙 메타 + 참조뷰 조회)뿐이다.
# -----------------------------------------------------------------------------
import enrichment_config

@app.get("/enrichment/rules")
def get_enrichment_rules():
    """활성 enrichment 규칙 메타를 반환합니다.

    응답 계약(변경 금지): {"rules": [{name, source_table, derived_table, decision_key[],
    target_fields[], list_columns[], reference_views: [{label}]}]}
    참조뷰의 쿼리 본문은 서버 config에만 존재하며 클라이언트에 절대 노출하지 않습니다.
    """
    rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
    return {"rules": [enrichment_config.to_public_rule(r) for r in rules]}

@app.get("/enrichment/rules/{rule_name}/references/{index}")
def get_enrichment_reference(rule_name: str, index: int, params: str = None, db: Session = Depends(get_db)):
    """규칙의 참조뷰 쿼리를 서버측 정의로 실행해 반환합니다.

    - `params`: URL 인코딩된 JSON 객체 {decision_key_col: value}. 해당 규칙의
      decision_key 컬럼만 허용(그 외 400). 값은 SQLAlchemy 파라미터 바인딩으로만
      전달되어 SQL 주입이 구조적으로 불가합니다.
    - LIMIT은 서버가 강제합니다(뷰별 설정, 기본 200 / 최대 1000).
    - 규칙/인덱스 미존재 404.
    """
    from sqlalchemy import text

    rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
    rule = next((r for r in rules if r["name"] == rule_name), None)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Enrichment rule '{rule_name}' not found")
    views = rule.get("reference_views", [])
    if index < 0 or index >= len(views):
        raise HTTPException(status_code=404, detail=f"Reference view index {index} not found for rule '{rule_name}'")
    view = views[index]

    bind_params = {}
    if params:
        try:
            parsed = json.loads(params)
            if not isinstance(parsed, dict):
                raise ValueError("not an object")
        except Exception:
            raise HTTPException(status_code=400, detail="'params' must be a URL-encoded JSON object")
        allowed = set(rule.get("decision_key", []))
        invalid = sorted(k for k in parsed.keys() if k not in allowed)
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"'params' keys must be decision_key columns only; invalid: {invalid}"
            )
        bind_params = parsed

    # 서버 LIMIT 강제: 사용자 쿼리를 서브쿼리로 감싸 상한을 바인딩한다(내부 LIMIT이 더 작으면 그 값 유지).
    wrapped_sql = text(
        f"SELECT * FROM ({view['query']}) AS __enrichment_ref LIMIT :__enrichment_limit"
    )
    exec_params = dict(bind_params)
    exec_params["__enrichment_limit"] = view.get("limit") or enrichment_config.DEFAULT_REFERENCE_LIMIT
    try:
        result = db.execute(wrapped_sql, exec_params)
        columns = list(result.keys())
        rows = [list(r) for r in result.fetchall()]
    except Exception as e:
        # 필수 바인드 누락 등 파라미터/실행 오류 — 쿼리 본문은 응답에 노출하지 않는다.
        logger.warning(f"[Enrichment] reference view '{rule_name}'#{index} execution failed: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Reference query execution failed ({e.__class__.__name__}). Check required params."
        )
    return {"label": view["label"], "columns": columns, "rows": rows}

@app.post("/admin/file-ingestion/retry-failed", dependencies=[Depends(require_admin_token)])
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
    
    def sync_refresh_callback(t_name: str, count: int, created_logs: list = None, total_log_count: int = None):
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
            # [F1] SUCCESS의 error_msg 슬롯은 detail(예: "키 결측으로 N행 스킵") 전달용.
            if error_msg:
                message += f" ({error_msg[:100]})"
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
        # [D3] workspace_name 별칭 역조회 — 별칭 워크스페이스의 재시도 오배송 방지
        from directory_watcher import resolve_workspace_root, load_global_table_config
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

@app.get("/admin/auto-update/status", dependencies=[Depends(require_admin_token)])
async def get_auto_update_status():
    """실시간 auto_update 스케줄러의 기동 현황(JSON)을 조회합니다. 각 항목에 active(제어 파일 기준) 필드를 부가합니다."""
    import os
    import json
    from utils import auto_update_control as auc

    # auc.SERVER_DIR is the relocatable data root (see server/paths.py) and is the
    # symbol tests monkeypatch — resolve through it, not through paths directly.
    status_path = os.path.join(auc.SERVER_DIR, "config", "scheduler_status.json")

    if not os.path.exists(status_path):
        return {"status": "success", "data": [], "last_updated": None}

    try:
        with open(status_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        collectors = data.get("collectors", [])
        # [핫 반영] active는 항상 제어 파일(auto_update_control.json)을 실시간으로 읽어 계산 —
        # 스케줄러가 다음 사이클에 status 파일을 재기록하기 전에도 toggle 결과가 즉시 일치한다.
        disabled_set = auc.read_disabled_scripts()
        for col in collectors:
            key = f"{col.get('table_name')}/{col.get('script_name')}"
            col["active"] = key not in disabled_set
        return {
            "status": "success",
            "data": collectors,
            "last_updated": data.get("last_updated")
        }
    except Exception as e:
        logger.error(f"Failed to read scheduler status file: {e}")
        return {"status": "error", "message": str(e), "data": []}

@app.post("/admin/auto-update/toggle", dependencies=[Depends(require_admin_token)])
def toggle_auto_update_script(payload: dict = Body(...)):
    """
    auto_update 수집기 스크립트의 active 상태를 토글합니다.
    body: {"script": "<workspace>/<script.py>", "active": bool}
    제어 파일(server/config/auto_update_control.json)을 갱신하며, 스케줄러가 매 사이클
    이를 읽으므로 재기동 없이 핫 반영됩니다. 단, run-now(수동 실행)는 active와 무관하게 항상 실행됩니다.
    """
    import os
    from utils import auto_update_control as auc

    script = payload.get("script")
    active = payload.get("active")

    if not auc.validate_script_key(script):
        raise HTTPException(status_code=400, detail="Invalid 'script' field. Expected format: '<workspace>/<script.py>'.")
    if not isinstance(active, bool):
        raise HTTPException(status_code=400, detail="Invalid 'active' field. Expected a boolean.")

    script_file = auc.resolve_script_file(script)
    if not os.path.isfile(script_file):
        raise HTTPException(status_code=404, detail=f"Auto update script not found: '{script}'")

    try:
        auc.set_script_active(script, active)
    except Exception as e:
        logger.error(f"Failed to update auto update control file for '{script}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to persist control file: {e}")

    logger.info(f"[Toggle] Auto update script '{script}' set to active={active}")
    return {"status": "success", "script": script, "active": active}

# [STRICT] The execution half of the pair with POST /admin/scripts/code: this
# publishes SCHEDULER_RUN_NOW, which makes the scheduler run the named script.
# Refuses with 503 when no admin token is configured.
@app.post("/admin/auto-update/run-now", dependencies=[Depends(require_admin_token_strict)])
def trigger_auto_update_run_now(
    # [C-1 Fix] await가 없는 순수 동기 핸들러(INSERT+commit) — def로 전환해 threadpool 실행
    table_name: str = Body(..., embed=True),
    script_name: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """지정된 수집기를 즉각 비동기로 강제 실행하도록 아웃박스 트리거 이벤트를 발행합니다."""
    import json
    import uuid
    try:
        trigger_payload = {
            "table_name": table_name,
            "script_name": script_name
        }
        
        new_event = models.DatabaseOutbox(
            event_uuid=str(uuid.uuid4()),
            table_name=table_name,
            event_type="SCHEDULER_RUN_NOW",
            payload=json.dumps(trigger_payload),
            processed_chain=False
        )
        db.add(new_event)
        db.commit()
        
        try:
            from sqlalchemy import text
            db.execute(text("NOTIFY outbox_event;"))
            db.commit()
        except Exception as notify_err:
            logger.debug(f"PostgreSQL NOTIFY skip or failed: {notify_err}")
            
        logger.info(f"[On-Demand] Published SCHEDULER_RUN_NOW outbox event for table='{table_name}', script='{script_name}'")
        return {"status": "success", "message": f"Successfully published trigger to run '{script_name}' for table '{table_name}'."}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to publish on-demand run trigger: {e}")
        return {"status": "error", "message": str(e)}

# [B5] /internal/events/* is worker->web-server IPC, and it was completely
# unauthenticated while read-only admin routes were gated - an inverted
# asymmetry, because POST /internal/events/broadcast relays an arbitrary dict to
# EVERY connected WebSocket client and injects into audit_cache. Anyone able to
# reach the port could make every operator's grid display a fabricated value and
# put fabricated rows in the history timeline, which SYSTEM_OVERVIEW section 1
# ranks as worse than the system being slow: if the propagation is not believed,
# correction stops and the ontology sets wrong.
#
# Gated with the SAME secret rather than bound to loopback, because the server
# already binds loopback (run_decoupled_app.py runs uvicorn with no --host, so
# uvicorn's 127.0.0.1 default applies) and that plainly was not sufficient on its
# own. The workers inherit the variable from the launcher's environment, so
# nothing extra has to be configured. Open when no token is set, exactly like
# the ordinary admin routes, so an unconfigured server behaves as it does today.
@app.post("/internal/events/batch-refresh", dependencies=[Depends(require_admin_token)])
async def internal_event_batch_refresh(
    table_name: str = Body(..., embed=True),
    change_count: int = Body(..., embed=True),
    created_logs: list = Body(None, embed=True),
    total_log_count: int = Body(None, embed=True)
):
    """Ingestion Worker가 파일 적재 완료 시 웹 서버에 갱신 및 캐시 무효화를 알리는 내부 이벤트 엔드포인트입니다."""
    import json
    from fastapi.concurrency import run_in_threadpool
    invalidate_table_cache(table_name)
    msg = {
        "event": "batch_refresh_required",
        "table_name": table_name,
        "change_count": change_count
    }
    if created_logs:
        # [C-5] 워처가 이미 500건으로 절단해 보내며(total_log_count = 실제 총 건수),
        # 구버전 워처(무절단 전량 전송) 호환을 위해 서버측 절단도 유지한다.
        actual_count = total_log_count if total_log_count is not None else len(created_logs)
        sliced_logs = created_logs[:MAX_NOTIFY_CREATED_LOGS] if len(created_logs) > MAX_NOTIFY_CREATED_LOGS else created_logs
        msg["created_logs"] = sliced_logs
        # [C-5 대칭화 — 라이브 드릴 관찰] 체인 경로(/internal/events/broadcast passthrough)는
        # WS 페이로드에 total_log_count가 실리는데 이 경로는 msg 재구성 과정에서 누락됐다.
        # 순수 추가 필드로 동봉해 클라이언트가 절단 여부(len(created_logs) < total_log_count)를
        # 양 경로에서 동일하게 판별할 수 있게 한다.
        msg["total_log_count"] = actual_count
        # Update the web server's in-memory audit cache
        # [C-1] pydantic 검증(add_logs_batch)은 CPU 바운드 — threadpool로 이관(루프 비블로킹, 내부 Lock으로 안전)
        try:
            await run_in_threadpool(audit_cache.add_logs_batch, sliced_logs, actual_count)
        except Exception as e:
            print(f"[Main Server] Failed to update audit_cache from batch-refresh: {e}")
    text_msg = await run_in_threadpool(json.dumps, msg)
    await manager.broadcast(text_msg)
    return {"status": "ok"}

@app.post("/internal/events/broadcast", dependencies=[Depends(require_admin_token)])
async def internal_event_broadcast(payload: dict = Body(...)):
    """외부 데몬 프로세스로부터 임의의 WebSocket 메시지를 받아 중계하는 엔드포인트입니다."""
    import json
    from fastapi.concurrency import run_in_threadpool
    # If the payload is a table refresh/update, handle caching/invalidation
    table_name = payload.get("table_name")
    if table_name:
        invalidate_table_cache(table_name)

    # [Heavy Lane P1] 인제션 진행 이벤트는 진행 스냅샷 레지스트리에도 반영
    # (normal 레인 파일 엔트리의 유일한 생성 경로 — dict 갱신이라 인라인 수행이 저렴)
    if payload.get("event") == "file_ingestion_progress":
        try:
            ingestion_activity_registry.apply_progress(
                payload.get("table_name"), payload.get("filename"),
                progress=payload.get("progress"),
                processed_rows=payload.get("processed_rows"),
                total_rows=payload.get("total_rows"),
            )
        except Exception as e:
            print(f"[Main Server] Failed to update ingestion activity from progress: {e}")

    created_logs = payload.get("created_logs")
    if created_logs:
        try:
            # [C-5 확장] 체인 워커가 created_logs를 500건으로 절단해 보내며,
            # total_log_count가 절단 전 실제 총 건수(audit_cache total_count 표기용).
            # 구버전(무절단 전량 전송, 필드 부재) 호환: len(created_logs) 사용 + 서버측 절단 유지.
            total_log_count = payload.get("total_log_count")
            actual_count = total_log_count if total_log_count is not None else len(created_logs)
            sliced_logs = created_logs[:MAX_NOTIFY_CREATED_LOGS] if len(created_logs) > MAX_NOTIFY_CREATED_LOGS else created_logs
            payload["created_logs"] = sliced_logs
            # [C-1] pydantic 검증(add_logs_batch)·대형 json.dumps는 CPU 바운드 — threadpool로 이관
            await run_in_threadpool(audit_cache.add_logs_batch, sliced_logs, actual_count)
        except Exception as e:
            print(f"[Main Server] Failed to update audit_cache from broadcast: {e}")

    text_msg = await run_in_threadpool(json.dumps, payload)
    await manager.broadcast(text_msg)
    return {"status": "ok"}

@app.post("/internal/events/file-processed", dependencies=[Depends(require_admin_token)])
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
        # [F1] SUCCESS의 error_msg 슬롯은 detail(예: "키 결측으로 N행 스킵") 전달용 —
        # 메시지 문자열에만 반영(페이로드 구조 불변).
        if error_msg:
            message += f" ({error_msg[:100]})"
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
    # [Heavy Lane P1] 완료/실패한 파일은 진행 스냅샷에서 제거 (멱등)
    try:
        ingestion_activity_registry.remove(table_name, clean_filename)
    except Exception as e:
        print(f"[Main Server] Failed to clear ingestion activity entry: {e}")
    await manager.broadcast(json.dumps(msg))
    return {"status": "ok"}


@app.post("/internal/events/ingestion-state", dependencies=[Depends(require_admin_token)])
async def internal_event_ingestion_state(payload: dict = Body(...)):
    """[Heavy Lane P1] watcher 프로세스가 인제션 라이프사이클 상태(QUEUED/PROCESSING/FINISHED)를
    웹서버 진행 스냅샷 레지스트리에 push하는 내부 이벤트 엔드포인트.

    WS 브로드캐스트는 하지 않는다 — admin이 GET /admin/file-ingestion/active로 조회한다.
    페이로드는 소형 스칼라 필드만(무절단 컬렉션 금지 계약과 무관하게 컬렉션 자체가 없음)."""
    try:
        ingestion_activity_registry.apply_state(payload)
    except Exception as e:
        print(f"[Main Server] Failed to apply ingestion state event: {e}")
    return {"status": "ok"}

# --- Admin Code Editor APIs ---
@app.get("/admin/scripts/list", dependencies=[Depends(require_admin_token)])
def list_admin_scripts():
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    mappers_dir = os.path.join(script_dir, "mappers")
    workspace_dir = paths.WORKSPACE_DIR
    
    mappers = []
    if os.path.exists(mappers_dir):
        for name in os.listdir(mappers_dir):
            if name.endswith(".py") and name not in ["base.py", "utils.py", "__init__.py"]:
                mappers.append({
                    "filename": name,
                    "path": f"mappers/{name}",
                    "type": "mapper"
                })
                
    ingestions = []
    auto_updates = []
    
    if os.path.exists(workspace_dir):
        for table in os.listdir(workspace_dir):
            table_path = os.path.join(workspace_dir, table)
            if not os.path.isdir(table_path):
                continue
                
            # Ingestion scripts
            scripts_dir = os.path.join(table_path, "scripts")
            if os.path.exists(scripts_dir):
                for name in os.listdir(scripts_dir):
                    if name.endswith(".py"):
                        ingestions.append({
                            "table_name": table,
                            "filename": name,
                            "path": f"ingestion_workspace/{table}/scripts/{name}",
                            "type": "ingestion"
                        })
                        
            # Auto-update scripts
            auto_update_dir = os.path.join(table_path, "auto_update")
            if os.path.exists(auto_update_dir):
                for name in os.listdir(auto_update_dir):
                    if name.endswith(".py"):
                        auto_updates.append({
                            "table_name": table,
                            "filename": name,
                            "path": f"ingestion_workspace/{table}/auto_update/{name}",
                            "type": "auto_update"
                        })
                        
    return {
        "status": "success",
        "data": {
            "mappers": mappers,
            "ingestions": ingestions,
            "auto_updates": auto_updates
        }
    }

def _resolve_admin_script_path(clean_path: str, for_write: bool = False) -> str:
    """Resolve an admin-editable script path to an absolute path.

    'ingestion_workspace/...' is user DATA and follows the relocatable data root
    (ASSY_DATA_ROOT); 'mappers/...' is code, resolved as the `mappers` package via
    sys.path, so it stays under server/ and is NOT relocated. Containment is
    checked against the resolved base with a separator so that a sibling
    directory sharing the base's prefix cannot pass.

    Because mappers/ is not relocated, an isolated server would otherwise write
    straight into the user's live files. Writes to any non-relocated prefix are
    therefore refused while running isolated (ASSY_DATA_ROOT set). Reads stay
    allowed - reading a mapper to understand it is harmless, overwriting it is
    the incident. The isolated environment must be structurally unable to reach
    production, not merely unlikely to.
    """
    ws_prefix = "ingestion_workspace/"
    if clean_path.startswith(ws_prefix):
        base = os.path.abspath(paths.WORKSPACE_DIR)
        rel = clean_path[len(ws_prefix):]
    else:
        # Looked up at call time (not captured at import) so the flag stays
        # patchable and reflects the process's actual data root.
        if for_write and paths.IS_ISOLATED:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Refused: this server runs on an isolated data root "
                    f"({paths.DATA_ROOT}), but '{clean_path}' resolves to the live "
                    "server/ tree, which is not relocated. Edit it in the real "
                    "server, or drop the file under ingestion_workspace/."
                ),
            )
        base = os.path.dirname(os.path.abspath(__file__))
        rel = clean_path
    full_path = os.path.abspath(os.path.join(base, rel))
    if full_path != base and not full_path.startswith(base + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path traversal outside project")
    return full_path


# Reading source is a leak, not a lookup: this returns the contents of any file
# under mappers/ or ingestion_workspace/. Gated like every other admin read.
@app.get("/admin/scripts/code", dependencies=[Depends(require_admin_token)])
def get_admin_script_code(path: str):
    import os

    # Path Traversal & Prefix whitelist check
    clean_path = os.path.normpath(path).replace("\\", "/")
    if clean_path.startswith("../") or "/../" in clean_path or clean_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid directory traversal detected")
        
    allowed = False
    for prefix in ["mappers/", "ingestion_workspace/"]:
        if clean_path.startswith(prefix):
            allowed = True
            break
            
    if not allowed:
        raise HTTPException(status_code=400, detail="Access denied to this path prefix")
        
    full_path = _resolve_admin_script_path(clean_path)

    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            code = f.read()
        return {
            "status": "success",
            "path": clean_path,
            "code": code
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

# [STRICT] Half of a remote-code-execution pair: this writes an arbitrary Python
# file, /admin/auto-update/run-now runs it. Refuses with 503 when no admin token
# is configured - an unconfigured server must not offer this at all.
@app.post("/admin/scripts/code", dependencies=[Depends(require_admin_token_strict)])
async def save_admin_script_code(
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    import os
    import json
    import uuid
    from datetime import datetime
    from sqlalchemy import text
    
    path = payload.get("path")
    code = payload.get("code")
    
    if not path or code is None:
        raise HTTPException(status_code=400, detail="Path and code are required")
        
    clean_path = os.path.normpath(path).replace("\\", "/")
    if clean_path.startswith("../") or "/../" in clean_path or clean_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid directory traversal detected")
        
    allowed = False
    for prefix in ["mappers/", "ingestion_workspace/"]:
        if clean_path.startswith(prefix):
            allowed = True
            break
            
    if not allowed:
        raise HTTPException(status_code=400, detail="Access denied to this path prefix")
        
    full_path = _resolve_admin_script_path(clean_path, for_write=True)

    # Auto-create directories if missing
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    try:
        with open(full_path, "w", encoding="utf-8", newline="") as f:
            f.write(code)
            
        # Trigger System Reload
        reload_payload = {
            "trigger": "code_editor",
            "modified_file": clean_path,
            "timestamp": datetime.now().isoformat()
        }
        
        reload_event = models.DatabaseOutbox(
            event_uuid=str(uuid.uuid4()),
            table_name="system",
            event_type="SYSTEM_RELOAD",
            payload=json.dumps(reload_payload),
            status="PENDING"
        )
        db.add(reload_event)
        db.commit()
        
        try:
            db.execute(text("NOTIFY outbox_event;"))
        except:
            pass
            
        return {
            "status": "success",
            "message": f"Successfully saved file: {clean_path} and triggered system reload."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

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
        no_cache_headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        admin_file = os.path.join(client2_dist_path, "admin.html")
        if os.path.exists(admin_file):
            return FileResponse(admin_file, headers=no_cache_headers)
        dev_admin_file = os.path.abspath(os.path.join(script_dir, "..", "client2", "admin.html"))
        if os.path.exists(dev_admin_file):
            return FileResponse(dev_admin_file, headers=no_cache_headers)
        raise HTTPException(status_code=404, detail="Admin page not found. Please build frontend first.")

    @app.get("/map-editor")
    @app.get("/map_editor.html")
    def serve_map_editor_page():
        """맵 에디터 페이지(map_editor.html)를 반환합니다."""
        no_cache_headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        map_file = os.path.join(client2_dist_path, "map_editor.html")
        if os.path.exists(map_file):
            return FileResponse(map_file, headers=no_cache_headers)
        dev_map_file = os.path.abspath(os.path.join(script_dir, "..", "client2", "map_editor.html"))
        if os.path.exists(dev_map_file):
            return FileResponse(dev_map_file, headers=no_cache_headers)
        raise HTTPException(status_code=404, detail="Map Editor page not found. Please build frontend first.")

    @app.get("/enrichment")
    @app.get("/enrichment.html")
    def serve_enrichment_page():
        """Enrichment Queue 페이지(enrichment.html)를 반환합니다."""
        no_cache_headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        page_file = os.path.join(client2_dist_path, "enrichment.html")
        if os.path.exists(page_file):
            return FileResponse(page_file, headers=no_cache_headers)
        dev_page_file = os.path.abspath(os.path.join(script_dir, "..", "client2", "enrichment.html"))
        if os.path.exists(dev_page_file):
            return FileResponse(dev_page_file, headers=no_cache_headers)
        raise HTTPException(status_code=404, detail="Enrichment page not found. Please build frontend first.")

    @app.get("/{file_name:path}")
    async def serve_static_or_index(file_name: str):
        # The prefix list below is an API-SHADOWING guard, not a security
        # boundary. It matches on the start of the path, so
        # `../../server/config/table_config.json` looks nothing like `admin` and
        # sails straight through. Containment is enforced after resolution, below.
        if (file_name.startswith("tables") or
            file_name.startswith("ws") or
            file_name.startswith("audit_logs") or
            file_name.startswith("dashboard") or
            file_name.startswith("admin") or
            file_name.startswith("map-editor") or
            file_name.startswith("map_editor") or
            file_name.startswith("map-presets") or
            file_name.startswith("enrichment/") or
            file_name.startswith("api")):
            raise HTTPException(status_code=404)

        # [B1] Containment check - the same shape _resolve_admin_script_path uses.
        # Before this, `os.path.join(client2_dist_path, file_name)` handed out any
        # file the process could read, unauthenticated: `/../../server/config/
        # table_config.json`, `/../../../../../../Windows/win.ini`, and even
        # `/../../server/admin_auth.py` all returned 200. That made the gate on
        # GET /admin/scripts/code, /admin/chain/rules and
        # /admin/file-ingestion/workspaces decorative - the bytes they protect were
        # readable next door, and a token persisted in any readable file would have
        # gone with them.
        #
        # Resolve first, then require the result to sit inside the dist root.
        # A denylist of characters cannot do this: `os.path.join` DISCARDS the base
        # when the second argument is absolute (`/C:/Windows/win.ini`) or Windows
        # drive-relative (`C:foo`), so only checking the resolved result is sound.
        dist_base = os.path.abspath(client2_dist_path)
        target_path = os.path.abspath(os.path.join(dist_base, file_name))
        if target_path != dist_base and not target_path.startswith(dist_base + os.sep):
            # 404, not 403: a static route must not confirm that the escape parsed.
            raise HTTPException(status_code=404)

        if file_name and os.path.exists(target_path) and os.path.isfile(target_path):
            return FileResponse(target_path)

        index_file = os.path.join(client2_dist_path, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Index file not found")

