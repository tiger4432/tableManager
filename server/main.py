from sqlalchemy import desc
from sqlalchemy.orm import Session
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from database.database import SessionLocal, engine, get_db, SQLALCHEMY_DATABASE_URL, DB_URL_SOURCE, DEFAULT_PG_URL
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
import db_safety  # [#16a] "a test process may not touch a real database", as a decision
import value_suggest  # [F3] unique-value lookup + THE shared prefix predicate
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


def bootstrap_database_schema(bind=None):
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

    `bind` defaults to the shared engine and exists so this refusal can be
    exercised against a target that is NOT the process's own engine - both by a
    caller that builds its own, and by the regression test, which must be able
    to prove the refusal without ever pointing the real engine at production.

    [#16a] The refusal below is a PURE DECISION - taken before a connection is
    opened, so a test process is turned away without the database being
    contacted at all. Outside pytest it returns immediately and this function
    behaves exactly as it did: `create_all` stays unguarded, and an unreachable
    database still aborts the boot.
    """
    target = engine if bind is None else bind
    db_safety.require_test_database(
        str(target.url),
        context="boot-time DDL (Base.metadata.create_all)",
        production_url=DEFAULT_PG_URL,
    )
    models.Base.metadata.create_all(bind=target)
    try:
        models.sync_dynamic_tables_schema(target)
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
    # 🔴 `WWW-Authenticate`가 여기 없으면 **교차 출처에서 게이트를 식별할 수 없다.**
    #    클라의 `isGateRejection`은 401/403에 더해 이 헤더가 `X-Admin-Token`을 지목하는지
    #    본다 — 앞단 프록시가 같은 포트에 자기 `WWW-Authenticate: Basic ...`으로 답하는
    #    것과 구별하기 위해서다(2026-07-30 loopback 프록시 인시던트가 그 모양이었다).
    #    노출 안 하면 브라우저가 그 헤더를 지우므로, vite dev(:5173)에서는 **진짜 게이트
    #    거부가 「앞단이 답했다」로 확신 있게 잘못 표시된다.** 값은 원하는 헤더의 **이름**뿐
    #    이라 비밀이 없다. 같은 출처(:8080/:8081 직접 서빙)에서는 원래 읽혔다.
    expose_headers=["Content-Disposition", "X-Estimated-Content-Length", "X-Total-Rows",
                    "WWW-Authenticate"]
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
# Used only by `_table_data_response`'s fallback branch - see its docstring. Importing
# it here keeps the fallback on the exact code path FastAPI would have taken anyway.
from fastapi.encoders import jsonable_encoder
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

        # [Schema drift] Say out loud whether this database carries the schema this
        # build expects. The outages on 2026-08-05 had one shape: a model gained a
        # column, the migration did not run here, and the first anyone heard of it
        # was a screen erroring. `create_all` above cannot close that class - it
        # builds missing TABLES and never ALTERs an existing one - so nothing before
        # this line was ever going to catch it.
        #
        # WHY HERE AND NOT EARLIER. Above this point the boot applies two of its own
        # migrations (database_outbox.processed_chain, .broadcast_at). Checked before
        # they run, a database that is about to be corrected reads as broken. Below
        # the DECOUPLED return it would never run in production, which is the only
        # mode that matters. This is the one line that is after every migration this
        # process performs and before every mode-specific exit.
        #
        # WHY IT DOES NOT REFUSE: see run_at_startup and the banner it prints.
        # `schema_drift` is a RUNTIME module, not the script in server/scripts.
        # server/tests/test_prod_import_env.py forbids the latter: nothing on a
        # runtime import path may reach into server/scripts, and a sys.path append
        # here would be caught by it. The CLI wraps this same code.
        try:
            import schema_drift
            schema_drift.run_at_startup(
                engine,
                lambda level, text: getattr(logger, level)(text),
                # Masked: this line goes to the log FILE, and the URL carries the
                # database password. Same helper the [db] boot line already uses.
                target=f"{paths.mask_db_password(SQLALCHEMY_DATABASE_URL)} "
                       f"(from {DB_URL_SOURCE})",
            )
        except Exception as e:
            logger.error(f"[Schema] drift check unavailable ({type(e).__name__}: {e}). "
                         f"Starting anyway - run "
                         f"'python server/scripts/check_schema_drift.py' by hand.")

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

    # [Virtual join] Attach the declared `expose` columns of every VERIFIED join whose
    # left table is this one. Here and only here: this is the single serialization point
    # for row payloads (grid page, single-row read, batch-update response, WS items), so
    # a joined column cannot be present on one of those and absent on another.
    #
    # Cost is one LEFT JOIN per rule per CALL, not per row - the page's row_ids are
    # already in hand and the right side rides the UNIQUE index that approved the rule.
    #
    # A failure here must not take the grid down. The safe direction is the ABSENT
    # column: an unattached column is a visible absence, a wrongly attached one is a
    # silent wrong answer.
    try:
        import virtual_join_executor
        virtual_join_executor.attach(db, table_name, data_list)
    except Exception as e:
        logger.error(f"[VirtualJoin] attach failed on '{table_name}', columns omitted: {e}")

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
from event_constants import MAX_NOTIFY_CREATED_LOGS, BROADCAST_ITEM_LIMIT
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

# The AG-Grid filter DSL translator lives in `column_filter.py`, not here, and this
# import is a deliberate RE-EXPORT: `main.get_column_filter_condition` keeps
# resolving. It moved because a worker process cannot rely on `main` naming this
# module - see the module docstring of `column_filter.py` for the failure it caused.
from column_filter import get_column_filter_condition

# ---------------------------------------------------------------------------
# Shared query construction for the two routes that read a table with the same
# `?q=` / `?cols=` / `?filters=` vocabulary: the grid (`/tables/{t}/data`) and the
# CSV extract (`/tables/{t}/export`).
#
# 🔴 These were two VERBATIM COPIES - the export's own comment said
# "get_table_data와 검색 로직 동기화", which is a promise a comment cannot keep. The
# 2026-07-31 round proved the cost: the `?cols=` whole-table defect was fixed in the
# grid copy and stayed live in the export copy, so for a few hours the two routes
# disagreed about what "search this column" means. One implementation, two callers.
# ---------------------------------------------------------------------------

class VirtualColumnBinder:
    """Binds virtual-join columns into ONE query, adding each column's LEFT JOIN once.

    A route holds one of these for its lifetime. `?filters=`, `?q=` and (in the export)
    the SELECT list can all name the same virtual column; without the memo each mention
    would add its own join. Duplicate joins are still CORRECT here - the right side is
    unique on the join key, so they cannot fan out - but they are paid for.
    """

    def __init__(self, db, table_model, table_name):
        self.db = db
        self.table_model = table_model
        self.table_name = table_name
        self.columns = set()
        self._cache = {}
        self._vjx = None
        try:
            import virtual_join_executor
            self._vjx = virtual_join_executor
            # collide AND virtual_only - see `exposed_columns` for why this is wider
            # than what `/schema` announces.
            self.columns = virtual_join_executor.exposed_columns(db, table_name)
        except Exception as e:
            # Same safe direction as the read path: unreadable declarations mean NO join
            # is in effect, so no column is virtual and every caller falls through to the
            # ordinary stored-column path.
            logger.error(f"[VirtualJoin] search columns unavailable on '{table_name}': {e}")

    def __contains__(self, col):
        return col in self.columns

    def expr(self, query, col):
        """`(query_with_join, expr)`. `expr` is None when no expression could be built."""
        if col not in self._cache:
            query, e, _label = self._vjx.resolved_expression(
                self.db, self.table_model, self.table_name, col, query)
            self._cache[col] = e
        return query, self._cache[col]


def apply_column_filters(query, table_model, table_name, filters, binder):
    """`?filters=` (AG-Grid filter model) -> query. Shared by the grid and the export."""
    if not filters:
        return query
    try:
        import json
        filter_dict = json.loads(filters)
        for col_name, f_info in filter_dict.items():
            override = None
            if col_name in binder:
                # The filter must run against the value the user SEES. For a virtual_only
                # column there is no stored column at all; for a collide column the stored
                # one is only half the answer (the join fills it where it is blank).
                query, override = binder.expr(query, col_name)
                if override is None:
                    # We know this column is virtual and we FAILED to build its
                    # expression. Falling through would drop the condition and answer with
                    # MORE rows than were asked for, while the response still implies the
                    # column was filtered. Refuse, for the same reason the `?cols=` path
                    # refuses.
                    raise HTTPException(
                        status_code=400,
                        detail=(f"'{table_name}'의 가상 조인 컬럼 '{col_name}'에 대한 "
                                f"필터를 만들 수 없습니다(조인 대상 테이블이 로드되지 "
                                f"않았습니다). 필터 없이 전체를 돌려주지 않습니다."))
            cond = get_column_filter_condition(table_model, col_name, f_info,
                                               col_expr_override=override)
            if cond is not None:
                query = query.filter(cond)
    except HTTPException:
        # A deliberate refusal must not be swallowed by the catch-all below and turned
        # back into the silent 200 it exists to prevent.
        raise
    except Exception as e:
        print(f"[Server] Failed to apply column filters on '{table_name}': {e}")
    return query


def apply_enrichment_queue_predicate(query, table_model, table_name, rule_name, scope):
    """`?enrichment_queue=<rule name>` -> query. THE named queue predicate.

    🔴 THIS IS NOT A FILTER, AND THAT IS THE POINT  [2026-08-05, user ruling]
        "Which rows still need work" is one specific question the rule already
        declares the answer to. It used to be shipped to the client as a filter
        dict (`queue_filters`) and applied through `?filters=`, which put its
        DEFINITION in the caller: every consumer ANDs the per-column specs, so on
        a multi-target rule the queue meant EVERY target blank and filling one
        column dropped the row out of the list while its sibling was still empty.
        A row leaving the queue with work in it - the same shape as N36.

        The queue needs a cross-column OR. Rather than grow the public filter DSL
        (a surface every existing caller would inherit) the client now asks for
        the predicate BY NAME and the server composes it from the rule's own
        `target_fields`. `?filters=` is untouched and still means what it meant.

    A 400 rather than a silent fallback: answering an unfiltered page to a caller
    who asked for the queue would return MORE rows than were asked for while the
    response implied the queue - the same refusal `?cols=` and the virtual-join
    filter path make.
    """
    if not rule_name:
        return query
    rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
    rule = next((r for r in rules if r["name"] == rule_name), None)
    if rule is None:
        raise HTTPException(
            status_code=400,
            detail=(f"enrichment 규칙 '{rule_name}'을(를) 찾을 수 없습니다. "
                    f"큐 조건을 만들 수 없으므로 전체를 돌려주지 않습니다."))
    if rule["derived_table"] != table_name:
        # The predicate is composed from THIS rule's target fields; against any
        # other table those columns mean nothing (or do not exist).
        raise HTTPException(
            status_code=400,
            detail=(f"규칙 '{rule_name}'의 큐는 '{rule['derived_table']}' 테이블의 "
                    f"것입니다 (요청: '{table_name}')."))
    try:
        cond = enrichment_config.queue_predicate_condition(
            table_model, rule, scope=scope or enrichment_config.QUEUE_SCOPE_QUEUE)
    except enrichment_config.QueuePredicateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return query.filter(cond)


def apply_search_filter(query, table_model, table_name, q, cols, binder):
    """`?q=` (+ optional `?cols=` scope) -> query. Shared by the grid and the export.

    🔴 The `?cols=` refusal is the reason this is one function. A column named in the
    scope that builds NO condition used to be dropped silently, and because the filter is
    only applied when at least one condition survives, a scope consisting ENTIRELY of such
    columns skipped filtering and returned the WHOLE TABLE with 200 - while the response
    implied that column had been searched.
    """
    if not q:
        return query
    from sqlalchemy import cast, String, or_
    safe_q = q.replace("%", "\\%").replace("_", "\\_")

    col_types = (crud.TABLE_CONFIG.get(table_name, {}) or {}).get("column_types", {})

    if cols:
        col_list = [c.strip() for c in cols.split(",") if c.strip()]
    else:
        # A virtual_only column is not in `column_types` (it is not stored), so an
        # unscoped search would skip it while the grid shows it. Union it in.
        col_list = (["row_id", "business_key_val"]
                    + [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]
                    + sorted(binder.columns - set(col_types.keys())))

    conditions = []
    unsearchable = []
    for col in col_list:
        if col in binder:
            query, expr = binder.expr(query, col)
            if expr is None:
                unsearchable.append(col)
            else:
                conditions.append(cast(expr, String).ilike(f"%{safe_q}%", escape="\\"))
        elif col in ["created_at", "updated_at"]:
            target_col = table_model.created_at if col == "created_at" else table_model.updated_at
            conditions.append(cast(target_col, String).ilike(f"%{safe_q}%", escape="\\"))
        elif col in ["row_id", "id"]:
            conditions.append(table_model.row_id.ilike(f"%{safe_q}%", escape="\\"))
        elif col == "business_key_val":
            conditions.append(table_model.business_key_val.ilike(f"%{safe_q}%", escape="\\"))
        elif hasattr(table_model, col):
            conditions.append(cast(getattr(table_model, col), String).ilike(f"%{safe_q}%", escape="\\"))
        else:
            unsearchable.append(col)

    # Only when the caller SCOPED the search (`?cols=`) and nothing in that scope is
    # searchable. The unscoped path cannot reach here (it always contributes row_id and
    # business_key_val).
    if unsearchable and not conditions:
        raise HTTPException(
            status_code=400,
            detail=(f"'{table_name}' 테이블에서 검색할 수 없는 컬럼입니다: "
                    f"{', '.join(unsearchable)}. 이 컬럼들은 이 테이블에 존재하지 "
                    f"않습니다. 전체를 돌려주면 검색한 것처럼 보이므로 거부합니다."))
    if unsearchable:
        logger.warning("[Search] '%s': ignoring unsearchable column(s) %s in ?cols=",
                       table_name, ", ".join(unsearchable))

    if conditions:
        query = query.filter(or_(*conditions))
    return query


# ── [perf 2026-08-06] Response serialization for the grid/map read path ──────────
#
# Counts how many times this route has had to fall back to the slow encoder, keyed by
# table. Read it from the log line below; it exists so the fallback is COUNTABLE and
# not just a one-off warning that scrolls past.
SLOW_JSON_FALLBACKS: dict[str, int] = {}


def _table_data_response(payload, table_name: str):
    """Serialize the grid payload without FastAPI's `jsonable_encoder` pass.

    FastAPI serializes a handler's return value by running `jsonable_encoder` over it
    and then `json.dumps`-ing the result. Returning a `Response` skips that entirely
    (`fastapi.routing.get_request_handler`: `if isinstance(raw_response, Response):
    response = raw_response`).

    This route's payload is built out of plain primitives - `fetch_and_merge_metadata`
    emits str/bool/None/float/int and nothing else - so that encoder pass converts an
    already-JSON-native dict into an identical one. Measured against the development
    database over all 14 declared tables: encoder 1,831 ms vs a direct dumps 129 ms
    (9.6x-17.5x), with BYTE-IDENTICAL output every time. On `dt_log` (1,000 rows /
    4.4 MB) that was 548 ms of a 763 ms request, against 5.4 ms of actual SQL
    execution. This is the continuation of the Phase 73.12 note below: that change
    dropped the Pydantic validation pass, this one drops the encoder pass.

    THE RISK IS THE DAY THE PAYLOAD STOPS BEING NATIVE. `jsonable_encoder` copes with
    Decimal/datetime/UUID; `json.dumps` raises TypeError. A new column type or a config
    change could introduce one, and this route is the operator's main screen - a 500
    here is the whole grid, empty.

    So the fast path is TRIED, not assumed, and the fallback is the exact path this
    route uses today. The bytes on the wire are therefore unchanged in BOTH branches.
    `default=str` was considered and rejected: it keeps the request alive but SILENTLY
    changes the encoding of a datetime (`str()` gives "2026-08-06 09:00:00" where
    `jsonable_encoder` gives the isoformat), which is a boundary-contract change
    discovered by the client rather than by us.

    ValueError is caught alongside TypeError so that "the fallback is today's
    behaviour" holds without exception: NaN/Infinity already raise under
    `allow_nan=False` on today's path too, so the retry re-raises and the request fails
    exactly as it does now, rather than failing differently on the way to the encoder.

    The fallback is LOUD on purpose. A slow path nobody notices is how this gets
    un-fixed - the encoder cost would quietly return and the next profile would
    rediscover it from scratch.
    """
    try:
        return JSONResponse(content=payload)
    except (TypeError, ValueError) as exc:
        SLOW_JSON_FALLBACKS[table_name] = SLOW_JSON_FALLBACKS.get(table_name, 0) + 1
        logger.warning(
            "[get_table_data] '%s': payload is NOT JSON-native, falling back to "
            "jsonable_encoder (%d time(s) for this table since boot). This costs "
            "roughly 10x the serialization time - find the column that emits it. "
            "Cause: %s",
            table_name, SLOW_JSON_FALLBACKS[table_name], exc)
        return JSONResponse(content=jsonable_encoder(payload))


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
    enrichment_queue: str = None,       # [2026-08-05] 이름으로 요청하는 큐 술어 (규칙명)
    enrichment_queue_scope: str = None, # queue(기본) | keyed | blank_key | resolved
    db: Session = Depends(get_db)
):
    """
    Lazy Loading을 위한 페이징 엔드포인트
    target_row_id가 있으면 해당 행이 포함된 페이지의 skip을 자동으로 계산합니다.

    `enrichment_queue`는 일반 필터가 아니라 **이름 붙은 서버측 술어**입니다
    (`apply_enrichment_queue_predicate` 참조). `filters`와 함께 쓸 수 있고 서로
    AND로 결합됩니다.
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

    # Virtual-join binder for this request. Shared with the CSV export - see the block
    # above `get_table_data` for why these two routes must not hold separate copies.
    binder = VirtualColumnBinder(db, table_model, table_name)

    # [NEW] AG-Grid 컬럼 필터링
    query = apply_column_filters(query, table_model, table_name, filters, binder)

    # [2026-08-05] 이름 붙은 큐 술어 (일반 필터 DSL이 표현할 수 없는 컬럼 간 OR)
    query = apply_enrichment_queue_predicate(query, table_model, table_name,
                                             enrichment_queue, enrichment_queue_scope)

    # ── [Step 0] 검색 필터 구성 (실제 컬럼 기준 ilike 다중 OR 검색) ──
    query = apply_search_filter(query, table_model, table_name, q, cols, binder)

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
            # Same serializer as the main return below - both exits of this route hand
            # back a Response, so neither can be re-routed through the encoder by accident.
            return _table_data_response({
                "total": 0,
                "data": [],
                "skip": skip,
                "limit": limit,
                "calculated_skip": skip,
                "target_offset": -1
            }, table_name)
        
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
    # The named queue predicate narrows the query exactly like `?filters=` does, so
    # it must narrow the CACHE KEY too. Omitting it would serve the unfiltered
    # table total as the queue remainder for 5 seconds - a progress bar reading
    # 0% with everything answered, which is N36 wearing the other face.
    if enrichment_queue:
        cache_key_parts.append(f"eq:{enrichment_queue}:{enrichment_queue_scope or ''}")
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
    if q and db.get_bind().dialect.name == "postgresql":
        # [Optimization] 검색 결과 정렬 시 External Merge Sort(디스크)를 방지하기 위해
        # 현재 트랜잭션의 정렬 메모리(work_mem)를 일시적으로 크게 할당합니다.
        #
        # Dialect-guarded: `SET LOCAL` is Postgres-only and raises
        # `OperationalError: near "SET": syntax error` on SQLite, which made the ENTIRE
        # `?q=` path unreachable from the test suite - no test could reach a search, so
        # nothing about search behaviour was pinned. Production is unaffected either way
        # (it is always Postgres); what changes is that the path can now be tested.
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
    
    return _table_data_response({
        "table_name": table_name, "total": total_count, "skip": skip, "limit": limit,
        "data": data_list, "calculated_skip": skip if target_row_id else None, "target_offset": actual_target_offset
    }, table_name)

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

    # Virtual-join binder for this request. THE SAME implementation the grid route uses -
    # these two blocks were verbatim copies and drifted the moment one was fixed.
    binder = VirtualColumnBinder(db, table_model, table_name)

    # [NEW] AG-Grid 컬럼 필터링
    query = apply_column_filters(query, table_model, table_name, filters, binder)

    # [Filter] get_table_data와 검색 로직 동기화 - 이제 주석이 아니라 같은 함수가 보장한다
    query = apply_search_filter(query, table_model, table_name, q, cols, binder)

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

    # [Virtual join] The extract must carry what the screen carries. There are TWO shapes
    # and only handling one of them would have shipped nothing for the live declaration:
    #
    #   collide      - the name is ALREADY a stored column and already in `business_cols`.
    #                  The header does not change; what changes is WHICH EXPRESSION fills
    #                  it. Selecting the raw stored column here is precisely the
    #                  "empty cell in the CSV where the screen said 미상" lie, and it is
    #                  the ONLY shape the production declaration has today
    #                  (`bonding_log.wafer_id`), so an append-only fix would have been a
    #                  no-op in production while looking complete.
    #   virtual_only - the name is not stored at all, so it is a NEW column and needs a
    #                  header slot.
    #
    # `announced_columns` is the virtual_only list and is the SAME source `/schema` gives
    # the grid, in the same order, so the extract's virtual columns appear in the order
    # the operator saw them. They go after the business columns and BEFORE the system
    # pair, which keeps "created_at/updated_at last" - an invariant the row writer below
    # depends on positionally (`row[-2]`, `row[-1]`).
    virtual_only_cols = []
    try:
        import virtual_join_executor
        virtual_only_cols = [c["name"] for c in
                             virtual_join_executor.announced_columns(db, table_name)
                             if c["name"] not in business_cols
                             and c["name"] not in ("created_at", "updated_at")]
    except Exception as e:
        # Safe direction, same as every other virtual-join call site: the ABSENT column.
        # A missing column is a visible absence; a wrong one is a silent wrong answer.
        logger.error(f"[VirtualJoin] export could not announce columns on "
                     f"'{table_name}', extract omits them: {e}")

    header = business_cols + virtual_only_cols + ["created_at", "updated_at"]

    # [정규화 스키마] native 컬럼을 직접 SELECT하여 JSONB 파싱 부하 완전 제거
    #
    # 🔴 The join goes in THIS statement, not in a per-chunk attach. The stream below runs
    # on ONE server-side cursor inside a StreamingResponse: by the time it is producing
    # rows, 200 OK and the headers are already on the wire. An extra query per chunk means
    # a mid-stream failure arrives after that point and the user receives a TRUNCATED CSV
    # THAT LOOKS COMPLETE, with nothing in the file saying otherwise. Folding the join into
    # the one statement costs zero extra queries and keeps memory constant.
    select_entities = []
    for col in business_cols:
        entity = None
        if col in binder:
            query, expr = binder.expr(query, col)
            if expr is not None:
                entity = expr.label(col)
        select_entities.append(entity if entity is not None
                               else getattr(table_model, col).label(col))

    for col in virtual_only_cols:
        query, expr = binder.expr(query, col)
        if expr is None:
            # Cannot happen while `announced_columns` and `exposed_columns` come from the
            # same `rules_for`, but a header slot with no expression would shift every
            # column after it. Fail loudly rather than emit a misaligned extract.
            raise HTTPException(
                status_code=500,
                detail=(f"'{table_name}'의 가상 조인 컬럼 '{col}'을(를) 추출 쿼리에 실을 수 "
                        f"없습니다. 컬럼이 밀린 CSV를 내보내지 않습니다."))
        select_entities.append(expr.label(col))

    select_entities.append(table_model.created_at)
    select_entities.append(table_model.updated_at)

    # The one invariant that keeps a CSV honest: a header cell per selected value. Any
    # future edit that adds to one list and forgets the other shifts every column after
    # the mistake, and a shifted extract is READABLE - it opens fine, the numbers are just
    # under the wrong headings. Cheap check, catastrophic failure mode.
    if len(header) != len(select_entities):
        raise HTTPException(
            status_code=500,
            detail=(f"'{table_name}' 추출 헤더({len(header)})와 컬럼({len(select_entities)}) "
                    f"수가 다릅니다. 컬럼이 밀린 CSV를 내보내지 않습니다."))

    # 2. 크기 샘플링 예측 (초기 10행 기반 정밀 추산)
    # [Performance Optimization] 전체 테이블을 읽지 않고 limit(10)만 지정하여 메모리 로드 비용 격감
    #
    # 🔴 Built from the SAME `select_entities` as the stream, on the SAME joined `query`.
    # If the sample ever diverged from the streamed statement, `avg_row_size` - and so
    # `X-Estimated-Content-Length` - would silently under-report by exactly the width of
    # the columns the sample missed, and the client's progress bar would run past 100%.
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

    # [Virtual join] Announce the columns a VERIFIED join ADDS to this table's read
    # payload. The payload has carried them since `d70a33d`; without this key the grid
    # never heard of a `virtual_only` column, so an operator who declared an expose got
    # neither the column nor a reason - the same defect class as a config that takes
    # effect silently, which is what the F9 surface exists to end.
    #
    # STRICTLY ADDITIVE. `columns`/`column_types` above describe STORED columns and are
    # untouched, so a client that ignores this key behaves exactly as it did before the
    # key existed - no new entry in the column list, no change in the push gate's
    # "unprotected data column" arithmetic, no new paste target.
    #
    # `virtual_only` columns only. A `collide` column is a real stored column that a join
    # also fills; it is already in `columns` and announcing it again would give two
    # answers to "is this column stored?". A collide-only declaration therefore leaves
    # this response BYTE-IDENTICAL (test_schema_virtual_columns proves it on res.text).
    #
    # 🔴 Read-only is NOT enforced here. `crud.refuse_virtual_join_columns` refuses the
    # write at the single funnel every write path converges on; `editable: False` only
    # stops the client OFFERING an edit that would come back 400.
    #
    # A failure must not take the schema route down, and the safe direction is the read
    # path's: announce NOTHING. An unannounced column is a visible absence; a phantom
    # column is a silent wrong answer (and a write target that does not exist).
    virtual_columns = []
    # [Virtual join] The columns whose displayed value the server RESOLVES THROUGH A JOIN -
    # collide AND virtual_only. A collide column is a real stored column that a join also
    # fills, so it is already in `columns` and looks perfectly ordinary; its AG-Grid Blank
    # filter then matches nothing, because the value the operator sees COALESCEs to a
    # non-empty label. This key is the only way a client can know that, and it must not be
    # deduced by differencing `columns` against `virtual_columns` - that arithmetic is
    # wrong for the collide case by construction.
    #
    # 🔴 NOT the write guard. `crud.refuse_virtual_join_columns` refuses the write at the
    # funnel; this only stops the UI proposing an edit that would come back 400.
    join_resolved_columns = []
    try:
        import virtual_join_executor
        join_resolved_columns = virtual_join_executor.resolved_column_announcements(
            db, table_name)
    except Exception as e:
        # Safe direction, same as every other virtual-join call site: announce NOTHING.
        # A missing announcement costs the client a greyed cell; a phantom one names a
        # column that does not resolve.
        logger.error(f"[VirtualJoin] join_resolved_columns unavailable on '{table_name}': {e}")

    try:
        announced = virtual_join_executor.announced_columns(db, table_name)
        # 🔴 A name already in `columns` is never announced again. The executor drops
        # `collide` names, but `collide` is computed against `column_types` and that is
        # NOT the whole of `columns`: the system tail above is appended unconditionally
        # and belongs to no config. A right table declaring `created_at` would therefore
        # reach `virtual_only` and be announced twice. Only this function knows the final
        # list, so the de-duplication belongs here - and it only ever REMOVES, so a stored
        # column keeps its stored identity and its editability.
        known = set(columns)
        virtual_columns = [c for c in announced if c["name"] not in known]
    except Exception as e:
        logger.error(f"[VirtualJoin] schema announcement failed on '{table_name}', "
                     f"virtual columns omitted: {e}")

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
        "map_push_ok": config.get("map_push_ok") is True,
        # Always present, `[]` when no verified join touches this table: a stable shape
        # is what lets a client read it without asking whether the key exists.
        "virtual_columns": virtual_columns,
        # Same rule, and for the same reason: ALWAYS PRESENT, `[]` when there is no join.
        # An absent key would force a client to tell "no joins on this table" apart from
        # "this server predates the key" - a version check wearing a data field, and the
        # seed of a fallback that outlives the server it was written for.
        "join_resolved_columns": join_resolved_columns
    }


# [F3] Unique value lookup - the primitive every input suggestion sits on.
#   Registered ABOVE `/tables/{table_name}/{row_id}` deliberately: the literal
#   segments make it unambiguous, but route order is what guarantees it.
#   Contract: values + WHETHER THE LIST WAS CUT (`truncated`). A dropdown that
#   is handed a silently trimmed list tells the user "this is all of them".
@app.get("/tables/{table_name}/columns/{column_name}/values")
def get_column_unique_values(
    table_name: str,
    column_name: str,
    prefix: str = "",
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """`table.column` 의 prefix 시작 고유값 목록 (+ 잘림 여부).

    - 테이블/컬럼은 `table_config` 선언과 대조한다. 미선언은 400/404이며
      원문이 SQL 텍스트에 들어가는 경로는 없다.
    - 조회 불가(인덱스 부재·타임아웃 등)는 빈 목록이 아니라
      `unavailable_reason` 으로 응답한다.
    """
    try:
        return value_suggest.suggest_values(
            db, table_name, column_name, prefix=prefix, limit=limit)
    except value_suggest.SuggestValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


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


# [P1b] `BROADCAST_ITEM_LIMIT` moved to `event_constants` (imported above) when the same
# decision was corrected at the priority-batch, source-delete-batch and chain-worker sites.
# One definition, four senders - see the rationale there.


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

    # [adopt] Decided HERE, before the response is built, not inside the background
    # broadcast - the caller has to be told in the same answer that the id list it is
    # about to stop receiving was capped rather than empty.
    delete_ids_omitted = len(deleted_row_ids) if len(deleted_row_ids) > BROADCAST_ITEM_LIMIT else 0

    replace_scope = None
    if replace_report is not None:
        replace_scope = {
            "filters": replace_report.get("filters"),
            "deleted": replace_report.get("deleted", 0),
            # Rows newly created by this payload (a scope wipe with an empty payload
            # legitimately reports inserted: 0 - the caller must surface that).
            "inserted": sum(1 for _, is_new in results if is_new),
            # [adopt] Rows this write updated that were NOT inside the scope it declared
            # - i.e. cells it took over from another map. Non-zero is only possible for a
            # table whose map key sits outside its business key (`dt_log` today). It is
            # reported rather than prevented: see the note in crud.apply_batch_updates for
            # why scope-local identity would be the corruption, not the fix.
            "adopted": replace_report.get("adopted", 0),
            "mode": replace_report.get("mode"),
            "reason": replace_report.get("reason"),
            # How many ids the `batch_row_delete` broadcast withheld because the list
            # exceeded BROADCAST_ITEM_LIMIT. 0 on the normal path. Never omitted
            # silently - a refresh signal carrying this same count goes out instead.
            "delete_ids_omitted": delete_ids_omitted,
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

    # [P1] The size branch is decided HERE, before the work, not after it. Above the
    # threshold the broadcast below sends a refresh signal carrying only a count, so
    # `msg_items` has no consumer at all - and building it costs one `cell_overwrites`
    # read-back of everything this request just wrote plus an O(rows x columns) merge,
    # on exactly the saves large enough for that to be felt.
    #
    # ⚠️ Same predicate, moved - NOT an approximation of it. `_merge_and_build_items`
    # appends exactly one item per entry of `results`, unconditionally, so
    # `len(msg_items) == len(results)` always holds and the branch below fires on
    # precisely the same inputs as the old `len(msg_items) > 100`. If that loop ever
    # gains a `continue`, this equality breaks and the branch must move back.
    broadcast_needs_items = len(results) <= BROADCAST_ITEM_LIMIT
    # [P1b] The second consumer test, and the one the size branch alone does not cover:
    # `msg_items` is read ONLY inside `if not batch.silent:` below, so a silent save under
    # the threshold built the whole merge for nobody at all. Silent is not a rare path -
    # it is what a caller passes when it will broadcast for itself.
    #
    # Kept as a separate name from `broadcast_needs_items` on purpose. That one is the SIZE
    # predicate and still selects which broadcast shape the non-silent branch sends; this
    # one is the CONSUMER predicate. Folding silence into the size flag would make
    # `not broadcast_needs_items` mean "refresh signal" in one place and "silent" in
    # another, and the next edit would pick the wrong one.
    items_have_a_consumer = broadcast_needs_items and not batch.silent
    msg_items = await run_in_threadpool(_merge_and_build_items) if items_have_a_consumer else []

    # WebSocket 브로드캐스트를 백그라운드 태스크로 이관하여 즉시 HTTP 200 반환!
    if not batch.silent:
        user_name = batch.updates[0].updated_by if batch.updates else "system"
        tx_id = created_logs[0]["transaction_id"] if created_logs else (batch.transaction_id or str(uuid.uuid4()))
        
        async def async_broadcast():
            if deleted_row_ids:
                if delete_ids_omitted:
                    # [adopt] Same threshold the upsert arm below already applies, and it
                    # arrives with the same change that makes this arm reachable at size.
                    # Until now `deleted_row_ids` only ever carried a handful of
                    # collision-merge shells, so the missing cap was unreachable; adopted
                    # rows are bounded only by the payload, so a 20k-cell push could put
                    # 20k ids in one JSON frame - the payload shape behind the
                    # 2026-07-25 event-loop freeze.
                    #
                    # NOT a silent truncation: the count rides the refresh signal and the
                    # response's `scope.delete_ids_omitted`. A cap that drops the tail
                    # without saying so would rebuild, one level up, exactly the silence
                    # this change exists to remove.
                    await manager.broadcast(json.dumps({
                        "event": "batch_refresh_required",
                        "table_name": table_name,
                        "change_count": delete_ids_omitted,
                        "deleted_row_ids_omitted": delete_ids_omitted,
                    }))
                else:
                    delete_msg = {
                        "event": "batch_row_delete",
                        "table_name": table_name,
                        "row_ids": deleted_row_ids
                    }
                    await manager.broadcast(json.dumps(delete_msg))

            if not broadcast_needs_items:
                msg = {
                    "event": "batch_refresh_required",
                    "table_name": table_name,
                    # len(msg_items) on this arm; msg_items is now empty by construction.
                    "change_count": len(results)
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
        # [P4] Bounded, not removed. This used to be EVERY audit log the write created -
        # one dict per changed cell, so a map push returned the whole audit trail it had
        # just written. Measured on a 200-row x 6-column save: 1,200 dicts, 405 KB of
        # JSON, built by the encoder on the event loop and parsed on the browser's main
        # thread. It scales with rows x columns, so a 20,000-die map returns tens of MB.
        #
        # No consumer reads it: the only `created_logs` reader in the client
        # (`client2/src/websocket.js`) takes it off the WEBSOCKET message, which is
        # untouched below and still carries its own logs on its own rules.
        #
        # Same truncate-plus-count contract the internal-event payloads already use
        # (`MAX_NOTIFY_CREATED_LOGS`, `total_log_count`) rather than a second convention:
        # the key stays present and stays a list, and the honest total rides alongside so
        # a caller can detect truncation as `len(created_logs) < total_log_count`.
        #
        # ⚠️ Slice HERE, not by rebinding `created_logs` - `async_broadcast` above reads
        # the same name and its WS payload rules are a separate contract.
        "created_logs": (created_logs[:MAX_NOTIFY_CREATED_LOGS]
                         if len(created_logs) > MAX_NOTIFY_CREATED_LOGS else created_logs),
        "total_log_count": len(created_logs),
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
    
    # [F8] trust_env=False for the same reason the workers' session sets it: this
    # is a loopback hop between two of our own processes, and httpx honours
    # HTTP_PROXY / ALL_PROXY by default. On 2026-07-30 that default sent the chain
    # worker's 127.0.0.1 notifications to the corporate proxy, which refused them
    # with 403; this call has the identical shape and would fail the identical way,
    # surfacing to the operator as "그래프 동기화 서버 에러" with a healthy worker.
    # A proxy can never be a legitimate hop between two processes on one machine.
    async with httpx.AsyncClient(trust_env=False) as client:
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

# ----------------- chip trace: the declared walk (see get_chip_trace) -----------------
# This is a SHAPE, not a BFS. The wafer is a hard scope, and the shape is what
# enforces decision (2) - "Knob/Recipe/Eqp are leaves" - because the mapping
# config has no channel to declare a class on a stub label (that channel is
# G2.5). Measured grounds for refusing to reach this with a filtered BFS:
# blocking `Core -FROM_CORE->` made the flood WORSE (1,341 -> 11,549 nodes)
# because it reroutes through Eqp (degree 10,284) and Wafer.
#
# Every (edge type, target label) pair below is ALSO declared in
# ontology_mapping.json. `_chip_trace_declared_pairs` cross-checks them per
# request so that a config rename surfaces as `not_declared` instead of masquerading
# as `none_recorded` - conflating "the ontology moved" with "this chip has no dt
# event" is the same declaration-dies-quietly class as spatial-on-an-edge-prop.
GRAPH_CHIP_TRACE_SEED_LABEL = "CoreCell"          # the chip identity ledger
GRAPH_CHIP_TRACE_SCOPE_EDGE = ("FROM_CORE", "Core")     # seed -> its wafer (the scope)
# Leg 1 - the chip itself: destinations of the SEED CELL ONLY. These are the one
# place the answer is allowed to leave the wafer scope, because they ARE the
# chip's own history. Sibling cells of the same core are never included.
GRAPH_CHIP_TRACE_CHIP_LEGS = (
    ("BONDED_TO", "BaseCell"),
    ("TRANSFERRED_TO", "DtCell"),
)
# Leg 2 - the wafer: events performed on the scope core. The edge runs
# ProcessEvent -> Core, so this leg is traversed INBOUND, and what the mapping
# declares is (PERFORMED_ON, Core) - the anchor's label, not the collected one.
GRAPH_CHIP_TRACE_EVENT_EDGE = ("PERFORMED_ON", "ProcessEvent")
GRAPH_CHIP_TRACE_EVENT_DECLARED = ("PERFORMED_ON", "Core")
# Leg 3 - terminals: reached FROM the core's events and never expanded from.
GRAPH_CHIP_TRACE_TERMINAL_LEGS = (
    ("USED_KNOB", "Knob"),
    ("USED_RECIPE", "Recipe"),
    ("EXECUTED_BY", "Eqp"),
)
GRAPH_CHIP_TRACE_EVENT_CAP = 500     # live max ProcessEvents on one core = 206 (LOT-A|05)
GRAPH_CHIP_TRACE_TARGET_CAP = 200    # per CHIP leg; live max BONDED_TO on one cell = 6
# A terminal leg is anchored on EVERY event of the core, so its claim count scales
# with the event count, not with the number of terminal entities: LOT-A|05 yields
# 206 EXECUTED_BY claims that resolve to 8 Eqp. Sharing TARGET_CAP=200 truncated
# that 8-entity answer - found by the loud-truncation flag on the first live run,
# which is the argument for having the flag. Sized off EVENT_CAP because that is
# what actually bounds it (one edge per event per source claim).
GRAPH_CHIP_TRACE_TERMINAL_CAP = 4 * GRAPH_CHIP_TRACE_EVENT_CAP
GRAPH_CHIP_TRACE_ID_CHUNK = 500      # IN-list chunk (idx_graph_edges_from_type lookup)
# [QA 2026-07-30, LOW] These two are NOT independent, and nothing said so. The
# leg applies `limit(remaining)` PER ANCHOR CHUNK and then slices, so the
# documented "truncated by (identity_key, edge id) order" only holds while every
# anchor set fits in one chunk. Raise EVENT_CAP above ID_CHUNK and the terminal
# legs would truncate by chunk-arrival order instead, which is not a stated order
# at all. Asserted at import rather than commented, so the coupling cannot be
# broken by editing one number.
assert GRAPH_CHIP_TRACE_EVENT_CAP <= GRAPH_CHIP_TRACE_ID_CHUNK, (
    "chip-trace anchor sets must fit in one IN-list chunk, or the leg's truncation "
    "order is no longer (identity_key, edge id) - see _chip_trace_leg"
)


# [F3] `_escape_like_term` is GONE. Its only caller was the graph node prefix
# search, which no longer uses LIKE at all: `value_suggest.prefix_conditions`
# expresses a prefix as a byte-order RANGE, where '%' and '_' are ordinary
# characters and there is nothing to escape. Reintroducing a LIKE escaper would
# mean reintroducing the un-indexable `ILIKE 'x%'` it was written for.


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
        _serialize_graph_edge(e)
        for e in collected_edges
        if e.from_node in node_ids and e.to_node in node_ids   # 캡으로 잘린 노드의 엣지 제외
    ]
    return nodes, edges_out, truncated


def _serialize_graph_edge(e, include_props: bool = False) -> dict:
    """Single definition of the edge shape shared by viewer / trace / chip trace.

    `include_props` is additive - the same keys are always present, chip trace
    just adds one. It needs the props because the event properties ARE the answer
    there (eventtime, dt_eqp): without them the three BONDED_TO dates on one chip
    are an unordered set instead of a rework sequence.
    """
    out = {
        "from": e.from_node,
        "to": e.to_node,
        "type": e.type,
        "source_name": e.source_name,
        "updated_by": e.updated_by,
        "event_time": e.event_time.isoformat() if e.event_time else None,
    }
    if include_props:
        out["props"] = e.props or {}
    return out


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
        # [F3] Second consumer of the SAME prefix predicate as the unique-value
        # lookup. The old `ILIKE 'term%'` could never use an index: this database
        # is Korean_Korea.949, and outside the C collation a btree does not serve
        # a LIKE prefix at all - it degrades to a full scan with a Filter.
        # `lower(col) >= term AND < term+1` in byte order keeps the previous
        # case-insensitive semantics and becomes a real range on
        # idx_suggest_graph_nodes_identity_key. LIKE escaping is gone with the
        # LIKE: '%' and '_' are ordinary characters in a range comparison.
        #
        # This route has NO second filter behind the predicate - whatever the
        # range says IS the answer - so it must fold through `db_fold` like the
        # other consumer. Folding here with Python's `.lower()` instead would
        # both miss rows the index holds and (before the upper bound learned to
        # carry) return everything at or above the term.
        is_pg = bool(db.bind is not None and db.bind.dialect.name == "postgresql")
        query = query.filter(
            *value_suggest.prefix_conditions(
                models.GraphNode.identity_key,
                value_suggest.db_fold(db, term),
                is_pg,
            )
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


# ----------------- chip trace — wafer-scoped, shape-bounded (경계 계약) -----------------

# Closed status vocabulary. Every leg reports exactly one of these, and a reader
# can tell "the source says nothing" from "the ontology moved" from "we refused to
# guess". A silently empty hop is the failure mode this endpoint exists to close.
CHIP_TRACE_RECORDED = "recorded"                # declared, rows found
CHIP_TRACE_NONE = "none_recorded"               # declared, zero rows (the 8,493 bonding-only chips)
CHIP_TRACE_NOT_DECLARED = "not_declared"        # the mapping no longer declares this (type, target)
CHIP_TRACE_SCOPE_UNRESOLVED = "scope_unresolved"  # 0 or >1 distinct Core claimed - we do not pick
# [QA 2026-07-30, HIGH] "we could not read the declaration" is NOT "the ontology
# moved". Measured: with the mapping file mid-save (`json.load` raises ->
# `raw_config = {}`) the declared-pair set collapses to the enrichment-promoted
# pairs alone, and the endpoint answered 200 with every leg `not_declared` - i.e.
# it asserted that BONDED_TO->BaseCell is no longer declared for a chip whose
# three BONDED_TO edges are sitting in `graph_edges`. That window is reachable:
# main.py's config writers use a plain `open(..., "w")`, not temp+rename.
CHIP_TRACE_MAPPING_UNAVAILABLE = "mapping_unavailable"
# [QA 2026-07-30, MEDIUM] A leg anchored on a leg that never ran must not report
# `none_recorded` ("declared, zero rows"). Nothing was asked.
CHIP_TRACE_NOT_REACHED = "not_reached"


def _chip_trace_declaration():
    """-> (declared pairs, report). The report says whether the set can be trusted.

    WHY NOT 503 (the alternative QA offered, and why this instead)
        Refusing the request would discard the half of the answer that is still
        true: the edges are in `graph_edges` and the walk is computable - only the
        question "is this shape currently declared?" is unanswerable. This endpoint's
        premise is a CLOSED PER-LEG VOCABULARY, so the honest place for "unknown" is
        inside that vocabulary, where the client's existing per-leg rendering shows
        it; a transport-level 503 moves it into HTTP where nothing displays it, on a
        read-only idempotent request the caller has nothing to retry *for*.

    WHAT DEGRADES, AND WHY ONLY THAT
        `degraded` replaces exactly one status: `not_declared`. It is the only status
        that makes a claim ABOUT THE DECLARATION'S ABSENCE. `recorded` and
        `none_recorded` are conclusions from rows we actually read and stay true
        whatever the config file is doing.

        Degraded when the file is unreadable (a `file`-scope rejection), when a table
        mapping was rejected (a renamed column silently drops that table's whole
        mapping - the same conflation one notch down), or when the file is ABSENT.
        Absence is the case QA measured, and it logged nothing at all: a system whose
        graph holds BONDED_TO edges and whose mapping file has vanished is a config
        accident, not an ontology decision.

        Same rule as `graph_orphans.declaration_blockers`: a declaration that did not
        load cleanly does not get to be the authority on what is declared.
    """
    import ontology_config
    known = crud.TABLE_CONFIG if crud.TABLE_CONFIG else None
    rejections = []
    mappings = ontology_config.load_ontology_mappings(
        known_tables=known, rejections=rejections
    )
    path = ontology_config.ONTOLOGY_PATH
    exists = os.path.exists(path)
    degraded = bool(rejections) or not exists
    if degraded:
        # Previously silent. The absent-file branch in particular logged nothing.
        logger.warning(
            "[ChipTrace] the ontology declaration did not load cleanly "
            f"(exists={exists}, rejections={len(rejections)}) — legs that would "
            "have said 'not_declared' will say 'mapping_unavailable' instead: "
            f"{rejections or 'file absent at ' + path}"
        )
    pairs = {
        (e["type"], e["target_label"])
        for m in mappings.values()
        for e in m.get("edges", [])
    }
    report = {
        "status": "degraded" if degraded else "ok",
        "path": path,
        "exists": exists,
        "rejected": rejections,
    }
    return pairs, report


def _chip_trace_sort_key(pair):
    """Time order for readability; NULL event_time last, then identity, then edge id.

    Sorted in Python rather than SQL because `NULLS LAST` is not portable to the
    SQLite path the suite runs on, and the caps make the cost nil.
    """
    edge, node = pair
    return (edge.event_time is None, edge.event_time, node.identity_key, edge.id)


def _chip_trace_leg(db, anchor_ids, edge_type, other_label, cap, inbound, declared,
                    declared_pair=None, declaration_degraded=False,
                    anchor_leg=None):
    """One typed leg of the walk. Returns a (leg dict, [(edge, node)]) pair.

    `declared_pair` is the (type, target_label) the ontology mapping declares, which
    differs from (type, other_label) on an INBOUND leg: PERFORMED_ON is declared as
    (PERFORMED_ON, Core) but collects ProcessEvent nodes.

    `anchor_leg` is the leg this one hangs off, when there is one. An empty anchor
    means two different things and they must not share a status:
      * the anchor was `none_recorded` -> zero events genuinely implies zero knobs
        REACHED THROUGH events, so `none_recorded` here is a sound inference.
      * the anchor was `not_declared` / `mapping_unavailable` -> no query ran, and
        "this wafer used no knobs" would be a fabrication. -> `not_reached`.

    Index path only: idx_graph_edges_from_type (outbound) / idx_graph_edges_to_type
    (inbound), anchor ids chunked. No recursive CTE and no unindexed edge access -
    a set join per leg is the right primitive on a relational edge store.

    Truncation is by (identity_key, edge id) order and is always reported; `cap+1`
    is fetched so that "exactly at the cap" is not mistaken for truncated.
    """
    leg = {
        "edge_type": edge_type,
        "target_label": other_label,
        "status": CHIP_TRACE_RECORDED,
        "count": 0,
        "node_ids": [],
        "truncated": False,
        "capped_at": cap,
    }
    if (declared_pair or (edge_type, other_label)) not in declared:
        # The negative assertion is only safe when the declaration loaded cleanly.
        leg["status"] = (CHIP_TRACE_MAPPING_UNAVAILABLE if declaration_degraded
                         else CHIP_TRACE_NOT_DECLARED)
        return leg, []
    if anchor_leg is not None and anchor_leg["status"] in (
            CHIP_TRACE_NOT_DECLARED, CHIP_TRACE_MAPPING_UNAVAILABLE):
        leg["status"] = CHIP_TRACE_NOT_REACHED
        leg["blocked_by"] = {"edge_type": anchor_leg["edge_type"],
                             "status": anchor_leg["status"]}
        return leg, []
    if not anchor_ids:
        leg["status"] = CHIP_TRACE_NONE
        return leg, []

    Edge, Node = models.GraphEdge, models.GraphNode
    anchor_col = Edge.to_node if inbound else Edge.from_node
    other_col = Edge.from_node if inbound else Edge.to_node

    collected = []
    ids = list(anchor_ids)
    for i in range(0, len(ids), GRAPH_CHIP_TRACE_ID_CHUNK):
        remaining = (cap + 1) - len(collected)
        if remaining <= 0:
            break
        chunk = ids[i:i + GRAPH_CHIP_TRACE_ID_CHUNK]
        collected.extend(
            db.query(Edge, Node)
            .join(Node, Node.id == other_col)
            .filter(
                anchor_col.in_(chunk),
                Edge.type == edge_type,
                Node.label == other_label,
            )
            .order_by(Node.identity_key.asc(), Edge.id.asc())
            .limit(remaining)
            .all()
        )

    if len(collected) > cap:
        leg["truncated"] = True
        collected = collected[:cap]
    collected.sort(key=_chip_trace_sort_key)

    # count counts EDGE claims, node_ids counts distinct entities. They differ on
    # purpose: 2,687 cells carry more than one FROM_CORE edge (one per source
    # file) for a single Core, and the three BONDED_TO edges of a reworked chip
    # are three separate events. Collapsing either would hide a fact.
    seen = set()
    for _e, n in collected:
        if n.id not in seen:
            seen.add(n.id)
            leg["node_ids"].append(n.id)
    leg["count"] = len(collected)
    if not collected:
        leg["status"] = CHIP_TRACE_NONE
    return leg, collected


@app.get("/graph/chip-trace")
def get_chip_trace(identity: str, db: Session = Depends(get_db)):
    """한 칩(CoreCell)의 이력을 **웨이퍼 스코프**로 추적한다 — BFS가 아니라 고정 형상 질의.

    - 파라미터는 `identity` 하나. **depth는 없다** — 형상이 알려져 있고, depth를 노출하면
      홍수가 되돌아온다(실측: BFS depth 3 = 2,142노드 중 1,763개가 남의 칩).
    - 스코프는 웨이퍼(Core). 스코프 밖 노드는 **시드 셀 자신의 직접 목적지**(BaseCell·DtCell)
      로만 도달한다. 같은 코어의 형제 셀은 포함하지 않는다 — 칩의 이력에 형제는 없다.
    - Knob·Recipe·Eqp는 **잎**이다. 코어의 ProcessEvent에서 도달하고 되확장하지 않는다
      (결정 ② — 정책 엔진 G2.5가 없으므로 질의 형상이 강제한다).
    - 빈 홉은 없다. 모든 홉이 recorded / none_recorded / not_declared 중 하나를 말한다.
    """
    seed = (
        db.query(models.GraphNode)
        .filter(
            models.GraphNode.label == GRAPH_CHIP_TRACE_SEED_LABEL,
            models.GraphNode.identity_key == identity,
        )
        .first()
    )
    if seed is None:
        raise HTTPException(
            status_code=404,
            detail=f"칩 노드를 찾을 수 없습니다: ({GRAPH_CHIP_TRACE_SEED_LABEL}, {identity})",
        )

    declared, declaration = _chip_trace_declaration()
    degraded = declaration["status"] == "degraded"
    nodes = {seed.id: seed}
    edges_out = []
    truncated = False

    def _absorb(pairs):
        for e, n in pairs:
            nodes.setdefault(n.id, n)
            edges_out.append(_serialize_graph_edge(e, include_props=True))

    # --- leg 1: the chip itself - where this die went ---
    chip_legs = {}
    for edge_type, target_label in GRAPH_CHIP_TRACE_CHIP_LEGS:
        leg, pairs = _chip_trace_leg(
            db, [seed.id], edge_type, target_label,
            GRAPH_CHIP_TRACE_TARGET_CAP, inbound=False, declared=declared,
            declaration_degraded=degraded,
        )
        _absorb(pairs)
        truncated = truncated or leg["truncated"]
        chip_legs[edge_type] = leg

    # --- the scope: this die's wafer. Resolved, never guessed. ---
    scope_type, scope_label = GRAPH_CHIP_TRACE_SCOPE_EDGE
    scope_leg, scope_pairs = _chip_trace_leg(
        db, [seed.id], scope_type, scope_label,
        GRAPH_CHIP_TRACE_TARGET_CAP, inbound=False, declared=declared,
        declaration_degraded=degraded,
    )
    _absorb(scope_pairs)
    truncated = truncated or scope_leg["truncated"]

    wafer = {"scope_edge": scope_leg}
    scope_node = None
    # [QA 2026-07-30] `not truncated` is a required conjunct, not a nicety. The leg
    # fetches cap+1 in (identity_key, edge id) order, so 201 claims to LOT-A|05 fill
    # the buffer before a single claim to LOT-Z|01 is read: length 1, scope
    # "resolved", and the entire wafer half computed for the WRONG core. That is the
    # LIMIT 1 winner-pick this design refuses, reached by a different road.
    if len(scope_leg["node_ids"]) == 1 and not scope_leg["truncated"]:
        scope_node = nodes[scope_leg["node_ids"][0]]
    else:
        # 0 -> the cell claims no wafer; >1 -> it claims two, and a chip has one
        # core; truncated -> the set we can see is not the set that exists. In every
        # case the wafer half is unanswerable and we say so rather than take the
        # first row ("the count was right but it pointed at another node" is a defect
        # this repository has actually shipped).
        wafer["status"] = CHIP_TRACE_SCOPE_UNRESOLVED
        wafer["scope_candidates"] = [
            {"label": nodes[i].label, "identity": nodes[i].identity_key, "id": i}
            for i in scope_leg["node_ids"]
        ]

    # --- leg 2/3: what the wafer went through, and the terminals it used ---
    if scope_node is not None:
        event_type, event_label = GRAPH_CHIP_TRACE_EVENT_EDGE
        event_leg, event_pairs = _chip_trace_leg(
            db, [scope_node.id], event_type, event_label,
            GRAPH_CHIP_TRACE_EVENT_CAP, inbound=True, declared=declared,
            declared_pair=GRAPH_CHIP_TRACE_EVENT_DECLARED,
            declaration_degraded=degraded,
        )
        _absorb(event_pairs)
        truncated = truncated or event_leg["truncated"]
        wafer["status"] = event_leg["status"]
        wafer["events"] = event_leg

        terminals = {}
        for edge_type, target_label in GRAPH_CHIP_TRACE_TERMINAL_LEGS:
            # anchor_leg: rename PERFORMED_ON and `events` correctly says
            # `not_declared`, but every terminal used to report `USED_KNOB:
            # none_recorded, count 0` - "this wafer used no knobs" when no knob
            # query ran (QA 2026-07-30).
            leg, pairs = _chip_trace_leg(
                db, event_leg["node_ids"], edge_type, target_label,
                GRAPH_CHIP_TRACE_TERMINAL_CAP, inbound=False, declared=declared,
                declaration_degraded=degraded, anchor_leg=event_leg,
            )
            _absorb(pairs)
            truncated = truncated or leg["truncated"]
            terminals[edge_type] = leg
        wafer["terminals"] = terminals

    return {
        "seed": {"label": seed.label, "identity": seed.identity_key, "id": seed.id},
        "scope": (
            {"label": scope_node.label, "identity": scope_node.identity_key,
             "id": scope_node.id}
            if scope_node is not None else None
        ),
        # What the leg statuses were judged against. Without this a reader cannot
        # tell a `mapping_unavailable` leg's cause from the outside.
        "declaration": declaration,
        "walk": {"chip": chip_legs, "wafer": wafer},
        "nodes": _serialize_graph_nodes(nodes),
        "edges": edges_out,
        "counts": {"nodes": len(nodes), "edges": len(edges_out)},
        "truncated": truncated,
    }


@app.get("/graph/mapping-summary")
def get_graph_mapping_summary():
    """현재 로드된 온톨로지 매핑(enrichment RESOLVED_AS 자동 승격 포함) 요약 + **거부된 매핑**.

    클라이언트가 그리드 선택 행 → trace 시드 변환에 사용한다(경계 계약).
    materializer(_load_graph_mappings)와 같은 로더를 태워 같은 신호원을 보장하고,
    config 파일이 작으므로 요청 시마다 디스크에서 읽는다(무중단 반영 — enrichment 패턴).

    `rejected`는 로드되지 **않은** 선언과 그 사유다. 로더의 계약은 "무효 테이블은 로깅 후
    스킵"인데, 그 스킵이 로그에만 있으면 **컬럼 하나를 rename한 순간 그 테이블의 온톨로지가
    통째로 사라지고 표면에는 아무 것도 안 나온다** — 성공 개수만 보면 "안 늘었다"와
    "죽었다"가 구별되지 않는다. 그래서 성공 목록과 **같은 응답**에 실어 보낸다: 이것은 새
    엔드포인트를 만들 자리가 아니라 이미 조회하는 응답에 태울 자리다(PRIMITIVES §3).
    `tables`의 형태는 바뀌지 않았다 — 추가 필드이므로 기존 클라 계약은 그대로다.
    """
    import ontology_config
    known = crud.TABLE_CONFIG if crud.TABLE_CONFIG else None
    rejections = []
    mappings = ontology_config.load_ontology_mappings(
        known_tables=known, rejections=rejections
    )
    mapping_path = ontology_config.ONTOLOGY_PATH
    return {
        "tables": [
            {
                "table": table_name,
                "node_label": m["node"]["label"],
                "identity_columns": list(m["node"]["identity"]),
            }
            for table_name, m in sorted(mappings.items())
        ],
        # scope: "table" (그 테이블만 스킵) | "file" (파일 전체가 안 읽힘/v1 형식)
        #      | "enrichment" (RESOLVED_AS 자동 승격이 죽음)
        "rejected": rejections,
        "rejected_count": len(rejections),
        "source": {
            "path": mapping_path,
            # 파일 부재는 "거부"가 아니라 "선언이 없다"다 — 둘을 섞으면 사유 목록이
            # 정상 상태에서도 비어있지 않게 되어 곧 무시당한다.
            "exists": os.path.exists(mapping_path),
        },
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
    #
    # 🔴 [보안] `file.filename`과 `user` 둘 다 **클라이언트가 정한다**. 종전에는 둘을 그대로
    #    f-string에 넣었고, `os.path.splitext`는 경로 구분자를 보존하므로
    #    `../../x.csv`가 `user(kim)_../../x_<uuid>.csv`가 되어 성분 중 `..`이 살아남았다.
    #    접두 성분 하나가 `..` 하나를 흡수하지만 그보다 많으면 raws/ 밖을 가리킨다
    #    (`open(...,"wb")`은 디렉터리를 만들지 않으므로 실재하는 archives/·err/·config/가
    #    사거리다). `user`는 쿼리 파라미터라 같은 벡터다.
    #
    # 두 겹으로 막는다. **결과 기반 검증이 정본**이다 — 입력 필터만 두면 다음에 구분자를
    # 하나 놓치는 순간 뚫린다. 같은 규율이 `directory_watcher._resolve_flatten_dest`에도
    # 있다("must be a direct child").
    def _safe_component(raw: str) -> str:
        # 클라가 Windows이고 서버가 POSIX일 수 있으므로 두 구분자를 모두 접는다
        # (POSIX의 os.path.basename은 역슬래시를 구분자로 보지 않는다).
        s = str(raw or "").replace("\\", "/")
        s = os.path.basename(s).strip().strip(".")
        return s

    orig_name, ext = os.path.splitext(_safe_component(file.filename))
    safe_user = _safe_component(user) or "Unknown"
    unique_name = f"user({safe_user})_{orig_name}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(target_dir, unique_name)

    # 결과 검증: 반드시 target_dir의 **직접 자식**이어야 한다.
    norm_target = os.path.normpath(os.path.abspath(target_dir))
    norm_dest = os.path.normpath(os.path.abspath(file_path))
    if (os.path.dirname(norm_dest) != norm_target
            or os.path.basename(norm_dest) != unique_name):
        raise HTTPException(
            status_code=400,
            detail=("업로드 파일명을 안전한 경로로 정규화하지 못했습니다 — "
                    f"파일명과 업로더 이름에서 경로 구분자를 제거한 뒤 다시 시도하십시오."),
        )

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
        # [P1b] Same discarded merge as the batch-update endpoint, and dearer here:
        # `include_sources=True` costs a `cell_sources` read on top of the
        # `cell_overwrites` one, and `crud.set_cell_manual_priority_batch` commits - so
        # every row in `changed` is expired and gets reloaded ONE STATEMENT AT A TIME by
        # the merge's first act, `[r.row_id for r in rows]`. Measured on a 101-cell pin:
        # 102 SELECTs against the data table where 1 is the crud lookup that did the work.
        # Above the threshold the broadcast below sends only a count, so all of it was
        # computed and thrown away.
        #
        # ⚠️ Same predicate, moved - NOT an approximation. `fetch_and_merge_metadata`
        # appends exactly one entry per input row, and `msg_items` below is a 1:1
        # comprehension over that, so `len(msg_items) == len(changed)` always holds.
        if changed and len(changed) <= BROADCAST_ITEM_LIMIT:
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
        
        # [P1b] `len(changed_rows)` is what `len(msg_items)` was - see the equality note in
        # `_apply_and_merge`. It is read here because on this arm `msg_items` is now empty
        # by construction, exactly as in the batch-update endpoint.
        if len(changed_rows) > BROADCAST_ITEM_LIMIT:
            # 대량 업데이트: 경량화된 새로고침 신호만 전송
            msg = {
                "event": "batch_refresh_required",
                "table_name": table_name,
                "change_count": len(changed_rows)
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
        # [P1b] Third copy of the discarded merge; see `set_cell_priority_batch_endpoint`
        # above for the full accounting. Same shape, same commit-then-reload bill, same
        # 1:1 equality `len(msg_items) == len(changed)` that lets the size branch be
        # decided before the work instead of after it.
        if changed and len(changed) <= BROADCAST_ITEM_LIMIT:
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
        
        # [P1b] `len(changed_rows)` is what `len(msg_items)` was - `msg_items` is empty by
        # construction on this arm now. See `_delete_and_merge`.
        if len(changed_rows) > BROADCAST_ITEM_LIMIT:
            # 대량 업데이트: 경량화된 새로고침 신호만 전송
            msg = {
                "event": "batch_refresh_required",
                "table_name": table_name,
                "change_count": len(changed_rows)
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

    # [Virtual join] Verified-declaration cache. It carries a TTL of its own for worker
    # processes that never reach this hook, but the web server must not wait it out:
    # a declaration edited in the admin UI has to take effect on the next read.
    try:
        import virtual_join_executor
        virtual_join_executor.reset_cache()
    except Exception:
        pass

    # [Notation normalization] Same shape and same reason as the line above: the
    # declaration carries a TTL for the worker processes, but one edited in the
    # admin UI has to take effect on the next QUERY here. (It is a query-time fold
    # now, not a write hook - see notation_norm's docstring.)
    try:
        import notation_norm
        notation_norm.reset_cache()
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
import map_alignment
import frame_confirmation
import map_preset_routing as map_preset_routing_module

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

@app.get("/api/maps/alignment/view")
def get_map_alignment_view(
    rule: str,
    map_table: str,
    params: str = None,
    reference: str = None,
    include_cells: bool = True,
    x_col: str = None,
    y_col: str = None,
    value_col: str = None,
    assume_reference_geometry: bool = True,
    db: Session = Depends(get_db),
):
    """한 결정 단위의 **정렬 화면 payload 전부**를 한 요청으로 낸다 (읽기 전용).

    소비자는 `client2/map_editor2.html`(`client2/src/map2/`)이다.

    - `rule`: 결정 단위를 선언한 인리치먼트 규칙 이름(예 `eqp_product_frame_attribution`).
      단위(`decision_key`)의 정본은 그 선언이며 여기에 컬럼명을 하드코딩하지 않는다.
    - `params`: URL 인코딩된 JSON 객체 {decision_key_col: value}. **그 규칙의 decision_key
      컬럼만** 허용한다(그 외 400) — `/enrichment/rules/{r}/references/{i}`와 같은 규율이고,
      값은 SQLAlchemy 바인딩으로만 전달된다.
    - `map_table`: 소스 좌표가 속한 맵 테이블(그 테이블의 `map_key_columns`가 맵 단위다).
    - `reference`: 공통 바닥을 **꽂아 넣는다** — `"테이블:맵ID"`. 생략하면 소스 맵이 선언한
      `valid_die_ref`를 따르고, 그것도 없으면 `reference.state = "absent"`로 나간다.
      🔴 기준 없음은 오류가 아니라 **가장 흔한 정상 상태**다.
    - `include_cells`: false면 셀 배열을 빼고 개수·채점만 낸다(목록 화면용).
    - `x_col` / `y_col` / `value_col`: **읽을 좌표 삼중항**. 이것이 원시 단위다(제품 소유자
      지시 2026-08-05: 「`CORE FRAME`이라는 이름이 아니라 `CORE_X`·`CORE_Y`·`C_BN`」).
      테이블의 **실제 스키마**에 대해 검증하고 없는 컬럼은 400 — `params`를 규칙 자신의
      `decision_key`에 대해 검증하는 것과 같은 규율이다.
      🔴 생략하면 선언 바인딩(`map_overlay_config.table_bindings`)이 **제안**한다. 제안은
      정본이 아니고, `unit.columns`가 축마다 `chosen`/`proposed`/`absent`를 말한다 — 화면이
      제안을 선택처럼 그리면 기본값이 선언을 사칭한다(I4).
      🔴 `value_col`은 셋을 구별한다: **이름을 대면** 그 컬럼, **생략하면** 선언이 제안,
      **빈 값(`?value_col=`)이면 명시적으로 없이** 간다. 생략만으로는 셋째를 말할 수 없고,
      그러면 선언이 값 컬럼을 가진 테이블에서 조작자는 점유 전용 실행을 요청할 방법이 없다.
      🔴 `value_col`의 부재는 **결함이 아니다.** 없으면 이 실행이 답할 수
      있는 것은 점유뿐이고, 그 사실은 `reference.kind = "occupancy"`로 나간다(기준 맵 자신이
      싣고 있는 것은 `reference.map_kind`에 그대로 남는다). 점유는 평평하다 — 실측
      `core_defect_map LOT-A/05`에서 8후보가 **같은 다이를 차지**했고 값 일치가 374다이
      차이로 갈랐다. 그래서 이 구별은 장식이 아니라 「승자 없음」의 사유를 가르는 값이다.

    - `assume_reference_geometry`: 규격 선언이 없는 소스 맵을 **기준 맵의 웨이퍼 치수를
      빌려** 채점한다(스펙 §9ⓐ, 총괄 판정 2026-08-05).
      🔴 순환을 끊는 자리다: 규격이 선언돼야 채점하는데, 조작자가 정렬을 도는 이유가 바로
      그 맵의 규격을 모르기 때문이다. 「이 둘은 같은 웨이퍼다」는 애초에 두 맵을 정렬하는
      전제이므로 조작자가 낼 자격이 있는 주장이고, **기본값은 true**다. `false`를 명시로
      넘기면 끌 수 있다 — 가정 없는 답을 보려는 진단은 실재하는 요구다.
      🔴 **기본값 뒤집힘 2026-08-06.** 종전 기본값은 false였고 근거는 「자동으로 걸면
      아무도 주장한 적 없는 가정 위에서 판정이 나온다」였다. 그 문장은 **쓰인 시점에
      참이었다** — 그때 응답은 가정이 걸렸다는 사실을 말할 수 없었고, 버튼이 그 침묵의
      대역이었다. 지금은 아래 세 필드가 그 사실을 나르므로(그리고 확정 기록까지 따라가므로)
      버튼이 대신 서 있던 정직성이 **버튼과 무관하게 응답 안에 있다.** 마찰은 아무것도
      사지 못하면서, 조작자가 **규격을 모르기 때문에 여는 화면**에서 단위마다 클릭 하나를
      물린다. 제품 소유자 확정: 채점은 읽기이고 읽기에는 마찰이 없다. 근거가 바뀐 것이지
      사라진 것이 아니다 — 가정이 걸린 판정은 여전히 다른 사실이고 여전히 기록된다.
      🔴 빌린 값은 **어디에도 쓰이지 않는다.** 소스 맵의 메타는 그대로 남고, 응답은
      `assumption`(무엇에서·몇 장·제안인가)과 `ruling.geometry_assumed`,
      `sources.maps[].geometry_basis`로 그 사실을 나른다. 확정하면 그 사실이
      `frame_confirmation`에도 남아 「나중에 이 가정이 거짓이면 어느 결정이 그 위에 서
      있었나」에 답할 수 있다.
      🔴 **격자 치수(cols/rows)는 빌리지 않는다** — 웨이퍼가 아니라 맵의 성질이고, 한
      웨이퍼의 두 맵이 다르게 잘려 있을 수 있다. 없거나 어긋나면 이름을 대고 제외한다
      (`grid_dims_missing` / `grid_dims_differ`). 방위(회전·면·start·y반전)도 빌리지
      않는다 — 그것이 풀고 있는 미지 그 자체다.
      켜지 않아도 `assumption.state = "available"`로 **제안은 실린다.** 규격 미선언 맵이
      막다른 길이 아니라 제안이 되는 자리다.

    [왜 컬럼이 인자인가] 이 경로는 예전에 `_binding_of(cfg, source_table)`을 정본으로 읽었고,
    `dt_log`의 선언 바인딩이 `dt_x`/`dt_y`로 고정돼 있어서 `map_table=core_wafer_map`으로
    열어도 **core 맵 ID 아래에 dt 좌표가 모였다.** `core_x`/`core_y`는 아예 도달 불가였다.
    화면은 완벽히 정렬되고 값만 전부 틀리는 상태이고(스펙 §7 I3), 그 위에 컬럼 선택기를
    붙이면 아무것도 하지 않는 컨트롤이 된다.

    [후보 8개가 같은 응답에 들어간다] 후보 전환이 네트워크 왕복이면 조작 3회·30초 예산이
    상호작용만으로 소진된다. 그래서 채점은 한 번에 전부 하고 전환은 클라 리페인트로 둔다.

    [상태] `scored` / `no_winner` / `not_scorable`. 답이 없을 때 `refusal`에 **서버가 만든
    한국어 한 문장**이 들어간다 — 클라가 사유를 자기 규칙으로 유도하기 시작하면 그것이 두 번째
    판정 구현이 되고, 두 판정이 갈리는 날 화면은 멀쩡한 채 값만 틀린다
    (`/admin/config/resolve`와 같은 규율).
    """
    rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
    decl = next((r for r in rules if r["name"] == rule), None)
    if decl is None:
        raise HTTPException(status_code=404, detail=f"Enrichment rule '{rule}' not found")

    key_values = {}
    if params:
        try:
            parsed = json.loads(params)
            if not isinstance(parsed, dict):
                raise ValueError("not an object")
        except Exception:
            raise HTTPException(status_code=400,
                                detail="'params' must be a URL-encoded JSON object")
        allowed = set(decl.get("decision_key", []))
        invalid = sorted(k for k in parsed.keys() if k not in allowed)
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"'params' keys must be decision_key columns only; invalid: {invalid}")
        key_values = parsed

    config = map_overlay_module.load_overlay_config()
    try:
        return map_alignment.build_alignment_view(
            db, config, decl, key_values, map_table,
            reference_spec=reference, include_cells=include_cells,
            x_col=x_col, y_col=y_col, value_col=value_col,
            assume_reference_geometry=assume_reference_geometry)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[MapAlignment] view failed ({rule}/{map_table}): {e}")
        raise HTTPException(status_code=500, detail="Failed to build map alignment view.")


@app.post("/api/maps/alignment/confirm")
def confirm_map_alignment(payload: dict = Body(...), db: Session = Depends(get_db)):
    """🔴 **좌표계 확정 — 이 사슬에서 데이터베이스에 쓰는 유일한 요청이다.**

    스펙 `MAP_ALIGNMENT_SPEC` §0.2 층 ⑧. 앞의 일곱 층(신원·근거·선언·좌석·채점·비교·판정)은
    아무것도 쓰지 않고, 층 ⑨(다이 맵 파생·본딩 계획·온톨로지 조인)는 여기 기록만 읽는다.

    [사고로 도달할 수 없어야 한다]
    그래서 **POST만** 있고 같은 일을 하는 GET이 없다. 읽기 경로에는 부작용이 없다
    (`/api/maps/alignment/view`는 순수 조회다). 화면 쪽은 arm-then-commit이 앞에 서고,
    이 라우트는 그 두 번째 몸짓에서만 불린다.

    [판정을 여기서 다시 하지 않는다]
    `ruling`·`sources`는 요청이 **명시적으로** 실어 온다. 쓰기 경로가 재채점하면 조작자가 보고
    결정한 것과 기록된 것이 갈릴 수 있고, 기록해야 하는 것은 조작자가 본 쪽이다. 재채점이
    필요하면 그것은 확정이 아니라 새 조회다.

    요청 본문:
      rule          결정 단위를 선언한 인리치먼트 규칙 이름 (`/view`와 같은 어휘)
      decision_key  {컬럼: 값} — **그 규칙의 decision_key 컬럼만**, 그리고 전부 채워야 한다
      frame         확정된 프레임(예 `rot90_front`) — **확정의 주체**
      map_table     그 좌표가 사는 테이블
      columns       {x, y, val} — 정렬한 좌표 삼중항. `val`은 없을 수 있다(점유 전용 실행)
      frames        {target_field: 프레임} — 그 규칙의 target_fields 안에 있어야 한다.
                    화면은 이것을 **일부러 비워** 보내고 답을 `frame`에 담는다(판정 2026-08-05)
      sources       합의에 올린 소스 목록(제외된 것 포함). 비면 거절한다
      ruling        `/view`가 낸 판정 그대로
      state         `/view` **응답 최상위**의 `state`. 판정 dict 안이 아니다 — 거기 없다
      reference     {table, map_id} — 공통 바닥
      confirmed_by  주체

    🔴 [D-1] `frame`·`map_table`·`columns`는 화면이 예전부터 보내던 것인데 이 라우트가 **하나도
       읽지 않았다.** 그래서 화면으로 만든 확정은 「무엇을 확정했나」가 전부 빈 채로 남았고,
       응답은 남의 규칙의 컬럼 두 개를 null로 실어 보냈다(실측 2026-08-06). 무엇도 명명하지
       않은 확정은 이제 **거절**이다 — 아무것도 기록하지 않은 기록은 완료로 보이기 때문이다.
    🔴 [D-2] `state`가 여기 따로 있는 이유는 `/view`가 그 값을 `ruling` 안이 아니라 응답
       최상위에 싣기 때문이다. 「`ruling`을 그대로 넘겨라」만 따르면 상태가 통째로 사라지고,
       그러면 승자를 지명한 판정이 「채점 안 됨」으로 기록된다. 화면의 전사 규칙은 두 줄이다:
       `ruling`을 복사하고 `state`를 복사한다.

    응답은 만들어진 기록 전체(`confirmation_uid`·`version` 포함)다 — 화면이 방금 무엇을
    했는지 알기 위해 다시 조회할 필요가 없어야 한다.

    ⚠️ **WS 브로드캐스트는 하지 않는다**(총괄 결정 2026-08-05). 듣는 쪽이 아직 없고, 이
    사슬에 이벤트를 붙이는 것은 별도 결정이다.
    """
    rule_name = payload.get("rule")
    if not rule_name:
        raise HTTPException(status_code=400, detail="'rule' is required")

    rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
    decl = next((r for r in rules if r["name"] == rule_name), None)
    if decl is None:
        raise HTTPException(status_code=404, detail=f"Enrichment rule '{rule_name}' not found")

    key_values = payload.get("decision_key") or {}
    if not isinstance(key_values, dict):
        raise HTTPException(status_code=400, detail="'decision_key' must be an object")
    # `/view`·`/enrichment/rules/{r}/references/{i}`와 같은 규율 — 선언되지 않은 컬럼은 거절.
    allowed = set(decl.get("decision_key", []))
    invalid = sorted(k for k in key_values if k not in allowed)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"'decision_key' keys must be decision_key columns only; invalid: {invalid}")

    frames = payload.get("frames") or {}
    if not isinstance(frames, dict):
        raise HTTPException(status_code=400, detail="'frames' must be an object")
    columns = payload.get("columns") or {}
    if not isinstance(columns, dict):
        raise HTTPException(status_code=400, detail="'columns' must be an object")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise HTTPException(status_code=400, detail="'sources' must be a list")

    confirmed_by = (payload.get("confirmed_by") or "").strip()
    if not confirmed_by:
        raise HTTPException(status_code=400, detail="'confirmed_by' is required")

    try:
        header = frame_confirmation.record_confirmation(
            db, decl, key_values, sources,
            confirmed_by=confirmed_by, frames=frames,
            frame=payload.get("frame"), map_table=payload.get("map_table"),
            columns=columns, state=payload.get("state"),
            ruling=payload.get("ruling"), reference=payload.get("reference"),
            enrichment_row_id=payload.get("enrichment_row_id"))
        return frame_confirmation.as_payload(db, header)
    except frame_confirmation.ConfirmationRefused as e:
        # 거절문은 서버가 만든다(`/view`의 refusal과 같은 규율) — 클라가 사유를 자기 규칙으로
        # 유도하기 시작하면 그것이 두 번째 판정 구현이 된다.
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"[MapAlignment] confirm failed ({rule_name}): {e}")
        raise HTTPException(status_code=500, detail="Failed to record frame confirmation.")


@app.get("/api/maps/alignment/worklist")
def get_map_alignment_worklist(
    rule: str,
    map_table: str,
    params: str = None,
    q: str = None,
    sort: str = "unit_key",
    order: str = "asc",
    limit: int = map_alignment.DEFAULT_WORKLIST_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """결정 단위 **목록** — 조작자가 「어느 단위를 열 것인가」를 고르는 자리 (읽기 전용).

    소비자는 `client2/map_editor2.html`의 작업 목록이다. `/api/maps/alignment/view`의
    **색인**이고, 그래서 어휘·검증·거절문 규율을 그것과 공유한다:

    - `rule`: 결정 단위를 선언한 인리치먼트 규칙 이름. 단위(`decision_key`)의 정본은 그
      선언이고 여기에 컬럼명을 하드코딩하지 않는다 — `?eqp=&product=`가 아니라 `?rule=`인
      이유가 이것이고, 그 판정이 이 경로에도 그대로 적용된다.
    - `params`: URL 인코딩된 JSON 객체 {decision_key_col: value}. **그 규칙의 decision_key
      컬럼만** 허용한다(그 외 400, 미지 규칙은 404 — `/view`와 같은 규율).
    - `map_table`: 맵 단위를 정하는 맵 테이블. 응답 `selection.map_tables`가 고를 수 있는
      것과 못 고르는 이유를 함께 낸다 — 지금까지 조작자에게 이 선택지가 아예 없었다.
    - `q`: 결정키 값들에 대한 **부분 문자열** 검색. `sort`/`order`도 서버가 한다. 단위 수는
      클라가 통제하는 어떤 값에도 묶여 있지 않으므로, 전량을 내려 브라우저에서 거르는
      설계는 규모에서 먼저 깨진다.

    [상태 셋, 그리고 `unscorable`이 흔한 쪽이다] `pending` / `confirmed` / `unscorable`.
    개발 박스 실측(운영 아님): `wafer_map_metadata` 668행 중 320행이 `auto_registered`라
    `make_frame_transform`이 거절하고, `valid_die_ref` 선언 8건 중 **0건**이 해석된다.
    그래서 `unscorable`은 0도 null도 아닌 **자기 상태**이고 `reason_code`를 달고 나가며,
    그 총계는 `totals.unscorable`로 **서버가 세어** 보낸다(클라가 세지 않는다).

    [사유 문장은 서버가 만든다] 행에는 `reason_code`만 싣고 사람 말은 `unscorable_reasons`에
    **사유당 한 번** 싣는다. 클라가 사유를 자기 규칙으로 유도하기 시작하면 그것이 두 번째
    판정 구현이 되고(`/view`·`/admin/config/resolve`와 같은 규율), 문장을 행마다 반복하면
    목록이 색인하는 것보다 무거워진다.

    [프레임 필드를 모른다] `core_frame`/`dt_frame`은 **이름**이고 단위는 좌표 컬럼이다.
    어느 좌표 컬럼을 읽을지는 상세에서 고르며, 이 경로는 이름과 무관한 것만 답한다 —
    어떤 단위가 있는가 · 확정됐는가 · 채점 가능한가 · 맵 몇 장이 모이는가.
    """
    rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
    decl = next((r for r in rules if r["name"] == rule), None)
    if decl is None:
        raise HTTPException(status_code=404, detail=f"Enrichment rule '{rule}' not found")

    key_values = {}
    if params:
        try:
            parsed = json.loads(params)
            if not isinstance(parsed, dict):
                raise ValueError("not an object")
        except Exception:
            raise HTTPException(status_code=400,
                                detail="'params' must be a URL-encoded JSON object")
        allowed = set(decl.get("decision_key", []))
        invalid = sorted(k for k in parsed.keys() if k not in allowed)
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"'params' keys must be decision_key columns only; invalid: {invalid}")
        key_values = parsed

    if sort and sort not in map_alignment.worklist_sort_keys(decl):
        raise HTTPException(
            status_code=400,
            detail=f"'sort' must be one of {map_alignment.worklist_sort_keys(decl)}")
    try:
        limit = max(1, min(int(limit), map_alignment.MAX_WORKLIST_UNITS))
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="'limit'/'offset' must be integers")

    config = map_overlay_module.load_overlay_config()
    try:
        return map_alignment.build_alignment_worklist(
            db, config, decl, map_table, key_values=key_values, q=q,
            sort=sort, order=order, limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[MapAlignment] worklist failed ({rule}/{map_table}): {e}")
        raise HTTPException(status_code=500, detail="Failed to build alignment worklist.")


@app.get("/api/maps/alignment/references")
def get_map_alignment_references(
    table: str = None,
    cap: int = map_alignment.MAX_REFERENCE_CANDIDATES,
    db: Session = Depends(get_db),
):
    """꽂을 수 있는 **기준 바닥** 목록 — 규칙 없이도 답한다 (읽기 전용).

    [왜 별도 경로인가] 이 목록은 원래 `/worklist`의 `selection.references`에만 실려 있었고,
    그래서 `?rule=`에 묶여 있었다. **그것이 거짓 의존이었다.** 어느 바닥이 풀리는가는 맵
    테이블의 성질이지 지금 작업 중인 인리치먼트 규칙의 성질이 아니다. 정렬 규칙을 아직
    선언하지 않은 운영에서는 워크리스트가 아무것도 답하지 못했고, 양쪽 반(셀 + 메타 행)이
    다 있는 바닥까지 같이 안 보이게 됐다. 규칙이 없어도 이 질문은 답이 있어야 한다.

    응답은 `selection.references`와 **같은 객체 그대로**다(감싸지 않는다 — 이 경로의 주제가
    references 하나뿐이라 한 겹 더 씌우면 정보 없는 층이 된다). 워크리스트 쪽은 여러 선택
    사실 중 하나라 `selection.` 아래 그대로 둔다. 계산은 `resolve_reference_catalog`
    하나이고 호출자가 둘이다 — **해석 경로를 두 벌 만들지 않는다.**

    - `table`: **보고 대상 테이블 필터**(선택). 없으면 바닥을 담을 수 있는 모든 테이블.
      ⚠️ `map_table` 좁히기가 아니다 — 어느 맵 테이블을 정렬 중인지는 어느 바닥이 풀리는가를
      바꾸지 않으므로 후보 집합은 그것으로 좁히지 않는다.
    - `cap`: 한 요청이 검사할 후보 수 상한. 넘으면 `truncated: true`로 **알린다**.

    [제안되지 않은 것에는 이유가 붙는다] `items`는 **실제로 풀린 것만**이고, 나머지는
    `not_offered`에 `map_id` · `reason_code` · 사람이 읽는 `reason` · `cell_count`를 달고
    나간다. 이유 없는 「없음」이 제품 소유자를 수리가 아니라 사람에게 보냈다.
    """
    if table is not None:
        table = table.strip()
        if not table:
            table = None
        elif table not in (crud.TABLE_CONFIG or {}):
            raise HTTPException(status_code=404, detail=f"Table '{table}' not found")
    try:
        cap = max(1, min(int(cap), map_alignment.MAX_REFERENCE_CANDIDATES))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="'cap' must be an integer")

    config = map_overlay_module.load_overlay_config()
    try:
        return map_alignment.resolve_reference_catalog(db, config, table=table, cap=cap)
    except Exception as e:
        logger.error(f"[MapAlignment] reference catalog failed (table={table}): {e}")
        raise HTTPException(status_code=500, detail="Failed to build reference catalog.")


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

@app.get("/api/maps/preset-routing")
def get_map_preset_routing(
    table: str,
    map_key: str,
    db: Session = Depends(get_db),
):
    """[F5] 이 맵을 **어떤 물리 규격(프리셋)으로 열지**의 선언된 답.

    해석 순서가 계약이다 — ①제품코드 조회 테이블 → ②텍스트 패턴 규칙 → ③라우팅 없음.
    ①의 선언이 없거나 조회가 빗나가는 것은 **정상**이며(운영 테이블은 이 환경에 없고,
    있어도 불완전하다) 조용히 ②로 넘어간다. 자세한 규율은 `map_preset_routing` 모듈 참조.

    - status: `ok` | `not_declared` | `no_match` | `meta_present` | `unresolvable`
      | `preset_missing`. **`ok`가 아니면 `preset_key`/`preset`은 항상 null**이고
      클라는 지금 동작을 그대로 유지한다(추측한 프리셋을 주지 않는다 — 틀린 규격은
      `inside`를, 따라서 저장 가능 집합을 바꾼다).
    - `meta_present`: 이 맵은 `wafer_map_metadata`에 규격이 이미 등록돼 있다.
      **저장된 규격 > 라우팅 > 패널**이 절대 순서이므로 서버가 여기서 거절한다.
    - `matched_by`: {stage, rule, lot, product_code} — 어느 규칙이 왜 걸렸는지(클라 표시용).
    - `lookup`: {declared, status, product_code} — ①의 결과. 미선언/빗나감은 경고가
      아니라 이 필드로만 드러난다(운영 선언을 검증하는 유일한 창).
    """
    config = map_overlay_module.load_overlay_config()
    presets = load_maps_config().get("presets", {})
    try:
        return map_preset_routing_module.resolve_preset_routing(
            db, config, table, map_key, presets)
    except Exception as e:
        logger.error(f"[PresetRouting] resolution failed ({table}/{map_key}): {e}")
        raise HTTPException(status_code=500, detail="Failed to resolve preset routing.")

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

@app.get("/admin/transfer-plan/dry-run", dependencies=[Depends(require_admin_token)])
def get_transfer_plan_dry_run():
    """「내가 쓴 이 선언이 받아들여지는가, 아니면 왜 거절되는가」 ― 쓰기 없는 계기.

    `GET /api/transfer-plan/stages`는 역할별로 `connected`/`missing` **한 단어**를 낸다.
    그 단어로는 config를 고칠 수 없다. 이 경로는 역할마다
      · 수용 여부와 **이름 붙은 거절 사유**(`bonding_plan.explain_binding_refusal` ―
        문장 생성기를 두 번 쓰지 않는다),
      · 각 필수 역할의 **해석된 실제 컬럼명**,
      · 그 컬럼이 **선언에서 왔는지 유도에서 왔는지**와 유도 출처,
      · 틀린 선언 때문에 유도가 지고 있다면 **지우면 무엇이 유도되는지**
    를 함께 낸다. 유도는 조용히 틀릴 수 있으므로 「어느 철자가 이겼는가」를 볼 자리가
    없으면 유도를 넣는 것 자체가 위험하다 ― 그래서 둘이 한 라운드다.

    [읽기 전용] 이 경로는 읽기 전용이다. 모델·컬럼 해석만 하고 **행을 조회하지 않으며**, 파라미터가 없다
    (선례 `GET /admin/enrichment/auto-confirm/dry-run`과 같은 자세 ― 쓰기를 촉발하는
    파라미터는 이 경로에 생기지 않는다). 그래서 strict가 아닌 `require_admin_token`이다.
    """
    config = transfer_plan_module.load_transfer_plan_config()
    try:
        return transfer_plan_module.dry_run(config)
    except Exception as e:
        logger.error(f"[TransferPlan] dry-run failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to evaluate transfer plan config.")

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

    응답 계약: {"rules": [{name, source_table, derived_table, decision_key[],
    target_fields[], list_columns[], reference_views: [{label, candidate_for}]}]}
    참조뷰의 쿼리 본문·limit은 서버 config에만 존재하며 클라이언트에 절대 노출하지 않습니다.

    `candidate_for`는 2026-07-30 [F9]에서 총괄 승인으로 추가된 **가산적** 필드입니다
    (어느 뷰가 어느 target_field의 후보 원천인지 — 클라가 유도하지 않게 하는 유일한 길).
    형태 근거는 `enrichment_config.to_public_rule` 참조. 기존 필드는 그대로입니다.
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

    # 서버 LIMIT 강제 + 필수 바인드 검사는 `execute_reference_view`가 **유일한** 정의다.
    # (2026-07-30 [F9]) 여기 있던 인라인 사본을 제거했다 — 두 정의가 갈라지면 클라가 보는
    # 표시 결과와 후보 해석이 다른 행 집합을 보게 된다.
    try:
        columns, rows = enrichment_config.execute_reference_view(db, view, bind_params)
    except enrichment_config.ReferenceViewError as e:
        # 필수 바인드 누락 등 파라미터/실행 오류 — 쿼리 본문은 응답에 노출하지 않는다.
        # This line names WHICH view failed; the driver's own error and its
        # traceback were already logged in full at the raise site
        # (`enrichment_config._reference_view_failure`), so this stays short.
        logger.warning(f"[Enrichment] reference view '{rule_name}'#{index} execution failed: {e}")
        # `detail` is the SERVER'S sentence, rendered verbatim by the client
        # under its own heading (`client2/src/enrichment.js` `showRefError`:
        # "머리말은 클라의 분류 라벨이고, 사유 문장은 서버 것을 그대로"). The old
        # wrapper produced "Reference query execution failed (reference query
        # execution failed (...)). Check required params." under a heading that
        # already said the same thing a third time - and the trailing advice was
        # wrong for every cause except a missing bind. The error now says what
        # it is exactly once.
        raise HTTPException(status_code=400, detail=str(e))
    return {"label": view["label"], "columns": columns, "rows": rows}


# -----------------------------------------------------------------------------
# [F9] 「config가 먹었는가」 — 선언의 효과를 어드민에 노출
#   `POST /admin/reload-configs`는 캐시를 갱신하고 아무것도 반환하지 않는다. 아래 둘이
#   그 공백을 메운다: 해석 보고서(설정만 읽는 값싼 질의)와 드라이런(큐를 걷는 계기).
# -----------------------------------------------------------------------------

@app.get("/admin/config/resolve", dependencies=[Depends(require_admin_token)])
def get_config_resolve_report(domain: str = None):
    """등록된 config 도메인의 **해석 보고서**(effective / ineffective / rejected).

    설정 파일만 읽는다 — DB 질의 0건이라 요청 경로에 앉아도 된다. 사유는 닫힌 어휘
    (`config_resolve_report.REASONS`)이고, 사람이 읽을 문장은 서버가 만든다:
    클라이언트는 `detail`을 그대로 렌더하고 「효과 없음」을 스스로 판정하지 않는다.
    """
    import config_resolve_report
    domains = [d.strip() for d in domain.split(",")] if domain else None
    return config_resolve_report.resolve_report(domains)


@app.get("/admin/config/virtual-join/verify", dependencies=[Depends(require_admin_token)])
def verify_virtual_join_declarations(db: Session = Depends(get_db)):
    """virtual join 선언이 **승인됐는가**, 아니면 무엇을 만들어야 하는가.

    `/admin/config/resolve`가 답하지 못하는 절반이다. 그 라우트는 「DB 질의 0건」이
    계약이라 설정 파일만 읽는데, 승인 조건인 「조인 키를 덮는 UNIQUE 인덱스」는
    `pg_index`가 아는 사실이라 세션이 필요하다.

    비싸지 않다 ― **행을 세지 않고 카탈로그만 읽는다.** 비용이 테이블 크기와 무관하므로
    1,000만 행 테이블에서도 요청 경로에 앉을 수 있다(직전 판의 중복 프로브는 전수
    스캔이라 그럴 수 없었고, 그래서 게이트에서 내려왔다).

    거부된 선언에는 `required_index_ddl`과 **사람이 읽을 `detail` 문장**이 실린다 ―
    문장은 `/admin/config/resolve`와 **같은 조립기**(`config_resolve_report.
    virtual_join_detail`)가 만든다. 갈라 두면 같은 거부가 두 화면에서 다른 문장으로
    나오고, 그 순간 「서버가 문장의 정본」이라는 계약이 깨진다.

    중복이 있으면 PostgreSQL이 그 중복 키 값을 지목하며 인덱스 생성에 실패하므로,
    데이터 정리가 필요하다는 사실도 같은 자리에서 드러난다.
    """
    import virtual_join_config
    from database import crud
    return virtual_join_config.verification_report(db, known_tables=crud.TABLE_CONFIG)


@app.get("/admin/config/notation/preview", dependencies=[Depends(require_admin_token)])
def preview_notation_fold(table: str = None, column: str = None,
                          limit: int = None, db: Session = Depends(get_db)):
    """표기 정규화 선언이 **실제로 무엇을 합치는가** ― 오병합(false merge) 점검.

    `/admin/config/resolve`가 답하지 못하는 절반이다. 그 라우트는 「DB 질의 0건」이
    계약이라 config만 읽고 「선언이 유효한가」까지만 말한다. 「내 규칙이 서로 다른 두
    로트를 하나로 합쳐 버리지 않았는가」는 **테이블 안의 값**을 봐야 답할 수 있다.

    [왜 이 라우트가 있어야 하는가 ― 없어진 파생 컬럼의 대가]
    직전 판은 접힌 값을 물리 컬럼에 실었고, 운영자는 그것을 그리드에서 **눈으로** 볼 수
    있었다. 컬럼이 사라졌으므로 그 확인 수단도 사라졌고, 그 손실은 흡수하는 것이 아니라
    갚아야 한다. 갚는 형태는 원본→접힌값 나열이 아니라 **병합군**이다:
    한 접힌 값에 원본 표기가 둘 이상 모인 그룹과 그 원본 목록. 나열은 「합쳐졌는가」를
    묻는 사람에게 답하지 않는다 ― 정작 중요한 줄이 나머지에 묻히기 때문이다.

    🔴 접기는 **SQL에서, 조인이 쓰는 바로 그 식(`notation_norm.fold_notation_sql`)으로**
    계산된다. 파이썬에서 접어 보여 주면 운영자가 신뢰하는 화면이 조인이 쓰지 않는 답을
    보여 주게 되고, 그것이 이 기능이 없애려는 「두 철자」 문제 그 자체다.

    ⚠️ **비싸다.** 접힌 식에는 평범한 인덱스가 없으므로 GROUP BY는 전수 스캔이다.
    운영자가 직접 부르는 점검용이고 쓰기가 없으며, 반환 그룹 수에 상한이 있다
    (`notation_norm.PREVIEW_GROUP_LIMIT`). 요청 경로에 상주하는 종류의 질의가 아니다.

    인자 없이 부르면 **선언된 모든 컬럼**을 훑는다.
    """
    import notation_norm
    import config_resolve_report as crr

    cap = limit or notation_norm.PREVIEW_GROUP_LIMIT
    cap = max(1, min(int(cap), notation_norm.PREVIEW_GROUP_LIMIT))
    if table and column:
        previews = [notation_norm.fold_preview(db, table, column, limit=cap)]
    elif table or column:
        raise HTTPException(status_code=400,
                            detail="table 과 column 은 함께 주거나 둘 다 생략하세요.")
    else:
        previews = notation_norm.declared_previews(db, limit=cap)
    for p in previews:
        # 문장은 서버가 만든다 ― 클라이언트가 판정하지 않는다(F9 계약).
        p["detail"] = crr.notation_preview_detail(p)
    return {
        "declarations": previews,
        "with_merge_groups": sum(1 for p in previews if p.get("merge_groups")),
        "total_merge_groups": sum(len(p.get("merge_groups") or []) for p in previews),
    }


# 드라이런은 큐를 걷는 분석 질의라(키·선언뷰당 SQL 1회) 요청 경로에서 **표본**만 본다.
# 기본값은 작업 단위 상한과 같은 200 — 「한 작업 단위가 무엇을 했을까」가 그대로 답이 된다.
ENRICHMENT_DRY_RUN_DEFAULT_LIMIT = 200
ENRICHMENT_DRY_RUN_MAX_LIMIT = 2000


@app.get("/admin/enrichment/auto-confirm/dry-run", dependencies=[Depends(require_admin_token)])
def get_enrichment_auto_confirm_dry_run(
    rule: str, limit: int = ENRICHMENT_DRY_RUN_DEFAULT_LIMIT,
    db: Session = Depends(get_db)
):
    """「이 규칙은 사람 없이 몇 건을 확정할 수 있는가」 — 쓰기 없는 계기.

    `enrichment_analysis.run_auto_confirm_sweep(apply=False)`를 그대로 노출한다. 그
    함수는 이미 읽기 전용이고 끝에서 구조적으로 rollback하므로, 여기서 새로 만드는
    계기는 없다 — CLI에만 닿아 있던 것을 어드민에서 닿게 할 뿐이다.

    🔴 `apply`는 **이 경로에 존재하지 않는다.** 이 라우트는 지금도 읽기 전용이고,
    그 점은 바뀌지 않았다. 대신 `ignore_knob=True`로 **노브가 꺼진 규칙도 측정**한다 —
    「켜면 무슨 일이 일어나는가」가 켜기 전에 답해야 하는 질문이고,
    `run_auto_confirm_sweep`은 그 조합을 apply와 결합하는 것을 스스로 거부한다.

    ⚠️ **[2026-07-31 결정 번복 — 이 문단을 지우지 말 것]**
    F9 당시 이 자리에는 「쓰기는 CLI에만 남는다」고 적혀 있었다. 그 판단의 **전제**는
    「어드민에서 쓰기를 촉발하는 안전한 형태가 없다」였고, 그 전제는 더 이상 참이 아니다:
    `POST /admin/auto-update/run-now`가 이미 **아웃박스에 이벤트를 한 줄 쓰고 즉시
    반환**하는 형태를 확립해 두었다(요청은 쓰기를 기다리지 않고, 실제 실행은 스케줄러
    워커가 한다). 그래서 사용자가 번복했고, 쓰기 촉발은
    **`POST /admin/retroactive/{op}/run`**(strict 토큰, 아래)에 생겼다.

    지금 유효한 분업 —
      · **이 라우트**: 여전히 쓰기 없음. `apply` 파라미터는 여기 생기지 않는다
        (쿼리 파라미터 하나는 오타 하나 거리에 있는 쓰기다). 노브가 꺼진 규칙까지
        측정하는 「켜면?」 질문의 답이 여기 있다.
      · **`GET /admin/retroactive/enrichment_confirm/count`**: 같은 함수를 부르되
        「지금 버튼을 누르면?」을 답한다 — 노브가 꺼져 있으면 `blocked_reason`을 실어
        버튼을 막는다.
      · **CLI(`enrichment_insights.py`)**: 버튼이 덮지 않는 나머지 전부 — 규칙 전체
        일괄 실행, `--limit`, `--ignore-knob` 측정, classify/propose. 버튼이 생겼다고
        CLI가 없어진 것이 아니다.
    """
    import enrichment_analysis
    import config_resolve_report

    limit = max(1, min(int(limit or ENRICHMENT_DRY_RUN_DEFAULT_LIMIT),
                       ENRICHMENT_DRY_RUN_MAX_LIMIT))
    rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
    target = next((r for r in rules if r["name"] == rule), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Enrichment rule '{rule}' not found")

    try:
        stats = enrichment_analysis.run_auto_confirm_sweep(
            db, target, apply=False, limit=limit, ignore_knob=True, log=logger.info)
    except enrichment_analysis.AnalysisRefused as e:
        # 선언이 없어 측정 자체가 불가능한 상태 — 라이브가 지금 그 상태다. 500이 아니라
        # 보고서와 **같은 어휘**로 답한다: 클라가 두 표면에서 같은 단어를 읽는다.
        db.rollback()
        return {
            "rule": rule, "mode": "dry-run", "limit": limit,
            "refused_reason": config_resolve_report.REASON_NOT_DECLARED,
            "detail": (f"측정할 수 없습니다 — 어떤 참조뷰도 'candidate_for'를 선언하지 "
                       f"않았습니다. ({e})"),
            "queue_size": None, "keys_examined": 0, "confirmed": 0,
            "written_cells": 0, "refused": {}, "samples": [], "truncated": False,
        }

    examined = stats.get("queue_size", 0)
    confirmed = stats.get("confirmed", 0)
    truncated = examined >= limit
    detail = (f"큐 {examined}건을 검사해 {confirmed}건이 사람 없이 확정 가능합니다"
              f"({stats.get('written_cells', 0)}개 셀). 쓰기는 하지 않았습니다.")
    if truncated:
        detail += f" ⚠️ 표본 {limit}건까지만 본 결과입니다 — 큐는 더 클 수 있습니다."
    return {
        "rule": rule, "mode": "dry-run", "limit": limit,
        "refused_reason": None, "detail": detail,
        "queue_size": examined,
        "keys_examined": stats.get("keys_examined", 0),
        "confirmed": confirmed,
        "written_cells": stats.get("written_cells", 0),
        "refused": stats.get("refused", {}),
        "samples": stats.get("samples", []),
        "truncated": truncated,
    }

# -----------------------------------------------------------------------------
# [Queue 25] 소급 적용(retroactive/backfill) 어드민 표면 — 「몇 건인가」와 「실행」
#
#   다섯 경로 전부 이미 CLI로 존재하고, 전부 드라이런이 기본이며, 전부 진짜 매퍼·진짜
#   쓰기 경로를 쓴다. 여기서 새로 구현하는 연산은 **하나도 없다** — 등록부는
#   `server/retroactive.py`이고 이 라우트들은 그 위의 얇은 껍질이다.
#
#   카운트가 값싸지 않다는 사실을 숨기지 않는다: 다섯 중 셋은 「몇 건인가」가 곧
#   드라이런 자체(테이블 전수 + 매퍼)라서 요청 경로에 앉을 수 없다. 그래서 모든 카운트는
#   `count_kind`(exact / sample / upper_bound)를 **함께** 반환하고, 표본이면 `truncated`와
#   `scanned`를 실어 「테이블에 대한 수」가 아니라 「표본에 대한 수」임을 서버가 문장으로
#   말한다(`detail`). 클라이언트는 그 문장을 그대로 렌더하고 스스로 판정하지 않는다 —
#   `/admin/config/resolve`·auto-confirm 드라이런과 같은 규율.
#
#   ⚠️ 다섯이 **같은 종류의 연산이 아니다.** 넷은 값을 쓰고 청크 단위로 커밋되어 중단돼도
#   이어서 재실행되지만, `graph_orphans`는 노드를 **삭제**하고 삭제 루프가 끝난 뒤에야
#   한 번 커밋한다 — 중단되면 이미 지운 청크까지 통째로 롤백된다(2026-07-31 소스 확인:
#   `graph_orphans.py`의 유일한 commit). 그래서 인벤토리·카운트 응답이 `deletes` ·
#   `restartable` · `commit_granularity`를 실어 나른다. 확인 문구 하나로 다섯 버튼을
#   덮으면 그 하나가 틀린다.
# -----------------------------------------------------------------------------

@app.get("/admin/retroactive/operations", dependencies=[Depends(require_admin_token)])
def list_retroactive_operations():
    """실행 가능한 소급 적용 연산 목록과 각각의 파라미터 · CLI 대응.

    설정만 읽는다 — DB 질의 0건이라 `/admin/config/resolve`와 같은 자세로 요청 경로에
    앉는다. `cli` 필드는 장식이 아니라 계약이다: 버튼은 각 연산의 **흔한 형태**만 덮고,
    나머지(`replay-all`, `--limit`, `--force-disabled`, 라벨 한정 스윕, 컬럼 한정 회수)는
    CLI에 남는다.
    """
    import retroactive
    return {"operations": retroactive.inventory()}


@app.get("/admin/retroactive/{op}/count", dependencies=[Depends(require_admin_token)])
def get_retroactive_count(op: str, request: Request, scan_limit: int = None,
                          db: Session = Depends(get_db)):
    """「이 연산은 몇 건에 영향을 주는가」 — 쓰기 없는 계기.

    각 연산이 **자기 드라이런**(또는 자기 모듈의 값싼 질의)으로 답한다. 파라미터는
    쿼리스트링으로 받되 연산이 선언한 이름만 허용하고, 모르는 이름은 400으로 거절한다
    (오타가 조용히 무시되면 「0건」이 정답처럼 보인다).

    ⚠️ `scan_limit`은 **미리보기의 예산**이지 어떤 CLI의 `--limit`도 아니다. 다섯 CLI에서
    `--limit`은 서로 다른 세 가지를 뜻한다(훑은 행 수 / 새로 만드는 파생 정체성 수 —
    이때 소스 스캔은 끝까지 간다 / 검사한 행 수), 그리고 고아 스윕에는 아예 없다.
    같은 단어로 묶으면 세 계약을 하나처럼 보이게 한다. 응답의 `scan_limit`은 실제로
    행을 훑은 연산에서만 숫자이고, 나머지는 `null`이다.

    `apply`류 파라미터는 여기 존재하지 않는다 — 이 라우트는 구조적으로 rollback한다.
    """
    import retroactive

    params = {k: v for k, v in request.query_params.items() if k != "scan_limit"}
    try:
        return retroactive.count(db, op, params,
                                 scan_limit=retroactive.clamp_scan_limit(scan_limit))
    except retroactive.RetroactiveRefused as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        # 측정이 불가능한 상태(선언 없음·모델 미초기화 등)는 500이 아니라 이름 있는
        # 거절로 답한다 — 500은 운영자를 로그로 돌려보낸다.
        db.rollback()
        logger.warning(f"[Retroactive] count failed for op={op}: {e}")
        raise HTTPException(status_code=400,
                            detail=f"이 연산의 건수를 계산할 수 없습니다: {e}")


# [STRICT] 쓰기를 촉발한다. `POST /admin/auto-update/run-now`와 **같은 형태**:
# 아웃박스 한 줄 + NOTIFY 후 즉시 반환하고, 실제 실행은 auto_update 스케줄러가 자기
# 스레드에서 한다. 소급 실행은 테이블을 전수로 걷기 때문에 동기 핸들러는 브라우저가
# 포기할 때까지 요청을 붙잡는다. 토큰 미설정 서버에서는 503으로 거부한다.
@app.post("/admin/retroactive/{op}/run", dependencies=[Depends(require_admin_token_strict)])
def trigger_retroactive_run(op: str, payload: dict = Body(default=None),
                            db: Session = Depends(get_db)):
    """소급 적용을 **큐에 넣고** 즉시 반환한다. 여기서 실행하지 않는다.

    body: `{"params": {...}}` — 파라미터 검증은 `retroactive.validate` 한 곳에서만
    한다. 그래서 라우트와 워커가 「무엇이 유효한 요청인가」에 대해 다른 답을 낼 수 없다.

    R2(`withdraw`)의 두 거절 — `user` 소스 거부, 사람이 고정한 소스 건너뛰기 — 은
    `chain_replay.withdraw_source` 안에 있고 이 경로는 **그 함수로 들어간다**. 즉 어드민을
    거쳐도 우회되지 않는다. 여기서 다시 확인하는 것은 편의(400을 즉시 돌려주려고)이지
    안전장치가 아니다.
    """
    import retroactive

    body = payload if isinstance(payload, dict) else {}
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    try:
        return retroactive.publish(db, op, params,
                                   requested_by=body.get("requested_by") or "admin")
    except retroactive.RetroactiveRefused as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"[Retroactive] failed to queue op={op}: {e}")
        raise HTTPException(status_code=500, detail=f"실행 요청을 큐에 넣지 못했습니다: {e}")


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

    @app.get("/map-editor2")
    @app.get("/map_editor2.html")
    def serve_map_editor2_page():
        """Map Editor 2 페이지(map_editor2.html)를 반환합니다.

        🔴 이 라우트가 없어서 화면이 404였다. `vite.config.js`에 엔트리를 넣고 `dist`까지
           구웠는데, **페이지마다 라우트를 명시적으로 다는 구조**라 번들만으로는 열리지
           않는다. 빌드 산출물의 존재가 곧 도달 가능성이 아니다 ― 새 페이지를 추가할 때
           반드시 여기 한 벌이 같이 온다.

        레거시 `/map_editor.html`은 그대로 살아 있다. 유효 다이 저작과 오버레이는 아직
        그쪽 소관이고, 이 화면은 좌표계 확정 ― 후보 채점·판정·확정 ― 을 맡는다.
        """
        no_cache_headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        map2_file = os.path.join(client2_dist_path, "map_editor2.html")
        if os.path.exists(map2_file):
            return FileResponse(map2_file, headers=no_cache_headers)
        dev_map2_file = os.path.abspath(os.path.join(script_dir, "..", "client2", "map_editor2.html"))
        if os.path.exists(dev_map2_file):
            return FileResponse(dev_map2_file, headers=no_cache_headers)
        raise HTTPException(status_code=404, detail="Map Editor 2 page not found. Please build frontend first.")

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

