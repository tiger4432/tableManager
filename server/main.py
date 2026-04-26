from sqlalchemy import desc
from sqlalchemy.orm import Session
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from database.database import SessionLocal, engine, get_db
from database import models, schemas, crud
import uuid 
import os
from fastapi import UploadFile, File, Body, HTTPException

# Create tables if not exists
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="AssyManager Table Server")

# --- Directory Watcher Integration ---
import sys
import os
# parsers 디렉토리를 sys.path에 추가하여 내부 임포트(advanced_ingester 등) 정합성 확보
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(script_dir, "parsers"))
from directory_watcher import WorkspaceWatcher

# 전역 워처 인스턴스 (종료 시 접근 위함)
global_watcher: WorkspaceWatcher = None

@app.on_event("startup")
async def startup_event():
    global global_watcher
    import asyncio
    main_loop = asyncio.get_running_loop()
    
    try:
        # [Migration] NULL updated_at 보정 (coalesce 제거 및 성능 최적화 대비)
        from sqlalchemy import text
        with engine.connect() as conn:
            print("[Migration] Checking for NULL updated_at...")
            res = conn.execute(text("UPDATE data_rows SET updated_at = created_at WHERE updated_at IS NULL"))
            conn.commit()
            if res.rowcount > 0:
                print(f"[Migration] Successfully updated {res.rowcount} rows.")

        print("[Startup] Initializing Directory Watcher...")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        workspace_base = os.path.join(script_dir, "ingestion_workspace")
        
        def trigger_ws_refresh(table_name: str, count: int):
            import json
            
            # 캐시 무효화
            invalidate_table_cache(table_name)
                
            msg = {
                "event": "batch_refresh_required",
                "table_name": table_name,
                "change_count": count
            }
            # 스레드 안전하게 메인 이벤트 루프에 브로드캐스트 예약
            try:
                asyncio.run_coroutine_threadsafe(manager.broadcast(json.dumps(msg)), main_loop)
            except Exception as e:
                print(f"[WS] Failed to broadcast refresh signal: {e}")
                
        global_watcher = WorkspaceWatcher(workspace_base, on_refresh_callback=trigger_ws_refresh)
        global_watcher.discover_and_watch()
        # 비차단 모드(blocking=False)로 기동
        global_watcher.start(blocking=False)
        print(f"[Startup] Directory Watcher started with {global_watcher.watch_count} watches.")
    except Exception as e:
        print(f"[Startup] Failed to start Directory Watcher: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    global global_watcher
    if global_watcher and global_watcher.observer:
        print("[Shutdown] Stopping Directory Watcher...")
        global_watcher.observer.stop()
        global_watcher.observer.join()
        print("[Shutdown] Directory Watcher stopped.")
# --------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"Client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"Client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        print(f"[ServerWS] Broadcasting to {len(self.active_connections)} clients: {message[:100]}...")
        failed_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                print(f"[ServerWS] Error sending to a client: {e}")
                failed_connections.append(connection)
        
        for conn in failed_connections:
            self.disconnect(conn)

manager = ConnectionManager()


@app.get("/")
def read_root():
    return {"status": "AssyManager Data Server is running"}

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
    
    # created_at 주입
    if "created_at" not in row.data:
        row.data["created_at"] = {
            "value": to_local_str(row.created_at), 
            "is_overwrite": False, 
            "updated_by": "system"
        }
    
    # updated_at 주입 (없을 경우 created_at 사용)
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

@app.get("/tables")
def list_tables():
    """
    서버에 정의된 모든 테이블 목록을 반환합니다.
    """
    return {"tables": list(crud.TABLE_CONFIG.keys())}

from audit_cache import audit_cache

@app.get("/audit_logs/recent", response_model=list[schemas.AuditLogGroupResponse])
def get_recent_audit_logs(limit_groups: int = 100, db: Session = Depends(get_db)):
    # 1. 인메모리 캐시 로드 (최초 1회만 DB 조회)
    audit_cache.load_initial(db, limit_groups)
    
    # 2. 캐시된 그룹을 경량화하여 반환
    result = []
    for g in audit_cache.groups:
        logs = g.get("logs", [])
        if not logs: continue
        
        # summary_columns 추출 (중복 제거)
        cols = []
        for l in logs:
            c = l.column_name
            if c and c not in cols:
                cols.append(c)
                
        result.append({
            "transaction_id": g.get("transaction_id"),
            "total_count": g.get("total_count", len(logs)),
            "summary_columns": cols,
            "logs": [logs[0]] # 대표 로그 1건만 포함
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
                for l in logs:
                    c = l.column_name
                    if c and c not in cols: cols.append(c)
                return {
                    "transaction_id": tx_id,
                    "total_count": g.get("total_count", len(logs)),
                    "summary_columns": cols,
                    "logs": logs[:limit]
                }
                
    # 2. 캐시에 없으면 DB에서 직접 조회 (만약 오래된 트랜잭션을 클릭했다면)
    # total_count 계산을 위해 별도 쿼리 (가벼운 쿼리)
    total_count = db.query(models.AuditLog).filter(models.AuditLog.transaction_id == tx_id).count()
    if total_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    db_logs = db.query(models.AuditLog, models.DataRow.business_key_val)\
                .outerjoin(models.DataRow, models.AuditLog.row_id == models.DataRow.row_id)\
                .filter(models.AuditLog.transaction_id == tx_id)\
                .order_by(models.AuditLog.timestamp.desc(), models.AuditLog.id.desc())\
                .limit(limit)\
                .all()
                
    logs = []
    cols = []
    for log_obj, bk in db_logs:
        log_dict = log_obj.__dict__.copy()
        log_dict["business_key"] = bk
        log_model = schemas.AuditLogResponse.model_validate(log_dict)
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
        # [최적화] 각 테이블의 행 개수 및 최신 업데이트 시간 조회
        count = db.query(sa.func.count(models.DataRow.row_id)).filter(models.DataRow.table_name == name).scalar()
        
        last_item = db.query(sa.func.max(sa.func.coalesce(models.DataRow.updated_at, models.DataRow.created_at)))\
                      .filter(models.DataRow.table_name == name).scalar()
        
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
    db: Session = Depends(get_db)
):
    """
    Lazy Loading을 위한 페이징 엔드포인트
    target_row_id가 있으면 해당 행이 포함된 페이지의 skip을 자동으로 계산합니다.
    """
    t_total_start = time.time()
    t_target = 0.0
    t_count = 0.0
    query = db.query(models.DataRow).filter(models.DataRow.table_name == table_name)
    
    # ── [Step 0] 검색 필터 구성 (Trigram Index + 컬럼 한정) ──
    if q:
        from sqlalchemy import cast, String, or_, and_, func
        safe_q = q.replace("%", "\\%").replace("_", "\\_")
        
        # [Pre-Filter] GIN Trigram 인덱스(idx_data_trgm)를 활용하여 후보군을 1차 선별 (Very Fast)
        # 이 조건이 인덱스 스캔을 유도하여 1,000만 건 중 수천 건 이하로 범위를 좁힙니다.
        from sqlalchemy import Text
        # [Optimization] GIN Trigram 인덱스(idx_data_trgm)는 CAST(data AS text) 기준임.
        # SQLAlchemy String은 VARCHAR를 생성하므로, 명시적으로 Text 타입을 사용하여 인덱스 매칭 보장.
        global_filter = models.DataRow.data.cast(Text).ilike(f"%{safe_q}%", escape="\\")
        
        if cols:
            col_list = [c.strip() for c in cols.split(",") if c.strip()]
            conditions = []
            for col in col_list:
                if col in ["created_at", "updated_at"]:
                    target_col = models.DataRow.created_at if col == "created_at" else models.DataRow.updated_at
                    conditions.append(cast(target_col, String).ilike(f"%{safe_q}%", escape="\\"))
                elif col in ["row_id", "id"]:
                    conditions.append(models.DataRow.row_id.ilike(f"%{safe_q}%", escape="\\"))
                else:
                    # [Refinement] 특정 컬럼으로 결과를 제한 (PostgreSQL JSONB 캐스팅 명시)
                    from sqlalchemy.dialects.postgresql import JSONB
                    conditions.append(func.jsonb_extract_path_text(cast(models.DataRow.data, JSONB), col, "value").ilike(f"%{safe_q}%", escape="\\"))
            
            # 글로벌 필터(속도)와 컬럼 필터(정합성)를 AND로 결합
            if conditions:
                query = query.filter(and_(global_filter, or_(*conditions)))
            else:
                query = query.filter(global_filter)
        else:
            query = query.filter(global_filter)

    # ── [Step 1] 타겟 위치(Offset) 자동 계산 (Unified Jump) ──
    actual_target_offset = -1
    if target_row_id:
        # [Optimization] 타겟 행이 현재 검색 조건(query)에 부합하는지 PK를 활용해 초고속(1ms 이내) 검증
        target_row = query.filter(models.DataRow.row_id == target_row_id).first()
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
                sort_expr = models.DataRow.updated_at
                if order_desc: # DESC (최신순)
                    # 1. 시간이 더 최근이거나(sort_expr > t_val)
                    # 2. 시간이 같으면 row_id가 더 큰 행(DESC)이 앞에 오므로 row_id > target_row_id인 행을 카운트
                    count_query = count_query.filter(or_(sort_expr > t_val, and_(sort_expr == t_val, models.DataRow.row_id > target_row_id)))
                else: # ASC
                    count_query = count_query.filter(or_(sort_expr < t_val, and_(sort_expr == t_val, models.DataRow.row_id < target_row_id)))
            elif order_by == "id":
                t_bk = target_row.business_key_val
                if t_bk is None:
                    # NULLS LAST: NULL 행들은 값이 있는 행들 뒤에 위치함
                    count_query = count_query.filter(or_(
                        models.DataRow.business_key_val.isnot(None),
                        and_(models.DataRow.business_key_val.is_(None), models.DataRow.row_id < target_row_id)
                    ))
                else:
                    if order_desc:
                        count_query = count_query.filter(or_(models.DataRow.business_key_val > t_bk, and_(models.DataRow.business_key_val == t_bk, models.DataRow.row_id < target_row_id)))
                    else:
                        count_query = count_query.filter(or_(models.DataRow.business_key_val < t_bk, and_(models.DataRow.business_key_val == t_bk, models.DataRow.row_id < target_row_id)))
            else:
                count_query = count_query.filter(models.DataRow.row_id < target_row_id)
            t_tmp = time.time()
            actual_target_offset = count_query.count()
            t_target = time.time() - t_tmp
            # [Optimization] 점프 시 타겟 행이 화면 중앙에 오도록 +- 50행 범위를 맞춤
            skip = max(0, actual_target_offset - (limit // 2))
    
    # ── [Step 2] 데이터 페칭 및 개수 산출 (Optimization) ──
    # [Optimization] 검색어 유무와 관계없이 일관된 캐시 키와 5초 TTL을 사용하여 스크롤 성능을 보장합니다.
    cache_key = f"{table_name}_total_count_{q}_{cols}" if q else f"{table_name}_total_count"
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
        sort_expr = models.DataRow.updated_at.desc() if order_desc else models.DataRow.updated_at.asc()
        # [Fix] 인덱스(ASC, ASC)를 거꾸로 타려면(DESC, DESC) 두 컬럼의 정렬 방향이 일치해야 합니다!
        tie_breaker = models.DataRow.row_id.desc() if order_desc else models.DataRow.row_id.asc()
        final_sort = [sort_expr, tie_breaker]
    elif order_by == "id":
        bk_sort = models.DataRow.business_key_val.desc() if order_desc else models.DataRow.business_key_val.asc()
        tie_breaker_bk = models.DataRow.row_id.desc() if order_desc else models.DataRow.row_id.asc()
        final_sort = [bk_sort, tie_breaker_bk]
    else:
        final_sort = [models.DataRow.row_id.asc()]
    
    # ── [Step 2.5] Session Memory Optimization (Search Only) ──
    if q:
        # [Optimization] 검색 결과 정렬 시 External Merge Sort(디스크)를 방지하기 위해 
        # 현재 트랜잭션의 정렬 메모리(work_mem)를 일시적으로 크게 할당합니다.
        from sqlalchemy import text
        db.execute(text("SET LOCAL work_mem = '64MB'"))
    
    # ── [Step 3] 데이터 페칭 (2단계 인덱스 기반 페칭으로 원복) ──
    t_id_start = time.time()
    # 1. ID만 먼저 인덱스로 스캔 (Very Fast)
    id_results = query.with_entities(models.DataRow.row_id).order_by(*final_sort).offset(skip).limit(limit).all()
    id_list = [r[0] for r in id_results]
    t_id_scan = time.time() - t_id_start
    
    t_row_start = time.time()
    # 2. 본 데이터는 해당 ID들만 PK로 조회 (Tuple 반환으로 ORM 오버헤드 완벽 제거)
    raw_rows = db.query(
        models.DataRow.row_id, 
        models.DataRow.table_name, 
        models.DataRow.data, 
        models.DataRow.created_at, 
        models.DataRow.updated_at
    ).filter(models.DataRow.row_id.in_(id_list)).all()
    
    # ID 순서대로 정렬 (인덱스 스캔 순서 복원)
    id_to_idx = {rid: i for i, rid in enumerate(id_list)}
    raw_rows.sort(key=lambda x: id_to_idx.get(x[0], 999999))
    t_row_scan = time.time() - t_row_start
    
    t_dict_start = time.time()
    data_list = []
    for r_id, t_name, r_data, c_at, u_at in raw_rows:
        # 시스템 컬럼 데이터 가공 (inject_system_columns 로직의 인라인 최적화)
        c_at_str = to_local_str(c_at)
        u_at_str = to_local_str(u_at if u_at else c_at)
        
        # 딕셔너리 직접 수정으로 메모리 할당 최소화
        if "created_at" not in r_data:
            r_data["created_at"] = {"value": c_at_str, "is_overwrite": False, "updated_by": "system"}
        if "updated_at" not in r_data:
            r_data["updated_at"] = {"value": u_at_str, "is_overwrite": False, "updated_by": "system"}
        else:
            r_data["updated_at"]["value"] = u_at_str
            
        data_list.append({
            "row_id": r_id, 
            "table_name": t_name, 
            "data": r_data,
            "created_at": c_at_str, 
            "updated_at": u_at_str
        })
    
    t_dict = time.time() - t_dict_start
    t_total = time.time() - t_total_start
    
    print(f"[get_table_data] Total: {t_total:.3f}s | Target: {t_target:.3f}s | Count: {t_count:.3f}s | ID Scan: {t_id_scan:.3f}s | Entity Fetch: {t_row_scan:.3f}s | Dict Conv: {t_dict:.3f}s | skip={skip}, limit={limit}, order={order_by}, q={q}")
    
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
    
    if deleted_count > 0:
        invalidate_table_cache(table_name)
        CHUNK_SIZE = 500
        for i in range(0, len(batch.row_ids), CHUNK_SIZE):
            chunk = batch.row_ids[i:i + CHUNK_SIZE]
            msg = {
                "event": "batch_row_delete",
                "table_name": table_name,
                "row_ids": chunk,
                "updated_by": batch.user_name
            }
            await manager.broadcast(json.dumps(msg))
        
    return {"status": "success", "deleted_count": deleted_count}

@app.post("/tables/{table_name}/row_ids/target")
def get_target_row_ids(table_name: str, req: schemas.TargetedRowIdRequest, db: Session = Depends(get_db)):
    """Targeted RowID Scanner: 오프셋 리스트 기반 초고속 UUID 추출"""
    query = db.query(models.DataRow).filter(models.DataRow.table_name == table_name)
    
    if req.q:
        from sqlalchemy import cast, String, or_, and_, func
        safe_q = req.q.replace("%", "\\%").replace("_", "\\_")
        
        from sqlalchemy import Text
        global_filter = or_(
            models.DataRow.business_key_val.ilike(f"%{safe_q}%", escape="\\"),
            models.DataRow.row_id.ilike(f"%{safe_q}%", escape="\\"),
            models.DataRow.data.cast(Text).ilike(f"%{safe_q}%", escape="\\")
        )

        if req.cols:
            col_list = [c.strip() for c in req.cols.split(",") if c.strip()]
            conditions = []
            for col in col_list:
                if col in ["created_at", "updated_at"]:
                    target_col = models.DataRow.created_at if col == "created_at" else models.DataRow.updated_at
                    conditions.append(cast(target_col, String).ilike(f"%{safe_q}%", escape="\\"))
                elif col in ["row_id", "id"]:
                    conditions.append(models.DataRow.row_id.ilike(f"%{safe_q}%", escape="\\"))
                else:
                    from sqlalchemy.dialects.postgresql import JSONB
                    conditions.append(func.jsonb_extract_path_text(cast(models.DataRow.data, JSONB), col, "value").ilike(f"%{safe_q}%", escape="\\"))
            
            if conditions:
                query = query.filter(and_(global_filter, or_(*conditions)))
            else:
                query = query.filter(global_filter)
        else:
            query = query.filter(global_filter)

    from sqlalchemy.sql import func
    if req.order_by == "updated_at":
        sort_expr = models.DataRow.updated_at
        sort_expr = sort_expr.desc() if req.order_desc else sort_expr.asc()
        # [Fix] 메인 테이블과 동일한 Tie-breaker 방향 적용 (Index 성능 및 정합성)
        tie_breaker = models.DataRow.row_id.desc() if req.order_desc else models.DataRow.row_id.asc()
        query = query.order_by(sort_expr, tie_breaker)
    elif req.order_by == "id":
        bk_null_last = (models.DataRow.business_key_val == None).asc()
        bk_sort = models.DataRow.business_key_val.desc() if req.order_desc else models.DataRow.business_key_val.asc()
        final_sort = [bk_null_last, bk_sort, models.DataRow.row_id.asc()]
        query = query.order_by(*final_sort)
    else:
        sort_expr = models.DataRow.row_id.asc()
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
    results = query.with_entities(models.DataRow.row_id).offset(min_offset).limit(limit).all()
    print(f"[Server] DB Query finished. Fetched {len(results)} row_id entities.")
    
    matched_ids = []
    for offset in req.offsets:
        local_idx = offset - min_offset
        if 0 <= local_idx < len(results):
            matched_ids.append(results[local_idx][0])
            
    return {"row_ids": matched_ids}


from fastapi.responses import StreamingResponse
import csv
import io
from datetime import datetime

@app.get("/tables/{table_name}/export")
def export_table_csv(
    table_name: str, 
    q: str = None, 
    cols: str = None,
    order_by: str = "row_id",
    order_desc: bool = False,
    db: Session = Depends(get_db)
):
    """
    현재 검색/정렬 조건에 맞는 데이터를 최대 100만 행까지 CSV로 스트리밍 추출합니다.
    """
    query = db.query(models.DataRow).filter(models.DataRow.table_name == table_name)
    
    # [Filter] get_table_data와 검색 로직 동기화
    if q:
        from sqlalchemy import cast, String, or_
        safe_q = q.replace("%", "\\%").replace("_", "\\_")
        if cols:
            col_list = [c.strip() for c in cols.split(",") if c.strip()]
            conditions = []
            for col in col_list:
                if col in ["created_at", "updated_at"]:
                    target_col = models.DataRow.created_at if col == "created_at" else models.DataRow.updated_at
                    conditions.append(cast(target_col, String).ilike(f"%{safe_q}%", escape="\\"))
                elif col in ["row_id", "id"]:
                    conditions.append(models.DataRow.row_id.ilike(f"%{safe_q}%", escape="\\"))
                else:
                    conditions.append(cast(models.DataRow.data[col]["value"], String).ilike(f"%{safe_q}%", escape="\\"))
            if conditions:
                query = query.filter(or_(*conditions))
        else:
            query = query.filter(cast(models.DataRow.data, String).ilike(f"%{safe_q}%", escape="\\"))

    # [Sort] 정렬 조건 동기화
    from sqlalchemy.sql import func
    if order_by == "updated_at":
        sort_expr = models.DataRow.updated_at.desc() if order_desc else models.DataRow.updated_at.asc()
        tie_breaker = models.DataRow.row_id.desc() if order_desc else models.DataRow.row_id.asc()
        final_sort = [sort_expr, tie_breaker]
    elif order_by == "id":
        bk_sort = models.DataRow.business_key_val.desc() if order_desc else models.DataRow.business_key_val.asc()
        tie_breaker_bk = models.DataRow.row_id.desc() if order_desc else models.DataRow.row_id.asc()
        final_sort = [bk_sort, tie_breaker_bk]
    else:
        final_sort = [models.DataRow.row_id.asc()]

    # [Safety Limit] 최대 100만 행으로 제한
    # [Accuracy] 내보내기 시에는 캐시를 사용하지 않고 실시간 DB 카운트를 수행합니다.
    total_count = query.count()
    total_count = min(total_count, 1000000)
    
    # ── [Optimization] ORM 객체 생성을 피하기 위해 필요한 필드만 추출 ──
    # data(JSONB), created_at, updated_at만 가져와서 속도 2배 이상 향상
    export_query = query.with_entities(models.DataRow.data, models.DataRow.created_at, models.DataRow.updated_at)\
                        .order_by(*final_sort)\
                        .limit(total_count)
    
    # 1. 헤더 구성을 위한 샘플링 (첫 행 기준)
    first_row_data = db.query(models.DataRow.data).filter(models.DataRow.table_name == table_name).first()
    if not first_row_data:
        raise HTTPException(status_code=404, detail="No data matches the current filter")
    
    data_map = first_row_data[0]
    system_cols = ["created_at", "updated_at"]
    business_cols = [k for k in sorted(data_map.keys()) if k not in system_cols]
    header = business_cols + system_cols

    # 2. 크기 샘플링 예측 (초기 10행 기반 정밀 추산)
    sample_io = io.StringIO()
    sample_writer = csv.writer(sample_io)
    # 실제 상위 10건 데이터 페치 (이미 정렬/필터링된 query 활용)
    sample_rows = export_query.limit(10).all()
    
    tz = LOCAL_TIMEZONE
    ts_fmt = "%Y-%m-%d %H:%M:%S"
    
    for r_data, c_at, u_at in sample_rows:
        # 시스템 컬럼 데이터 가공 시뮬레이션 (generate 루프와 동일 로직)
        eff_upd = u_at if u_at else c_at
        c_at_s = c_at.replace(tzinfo=timezone.utc).astimezone(tz).strftime(ts_fmt) if c_at else ""
        u_at_s = eff_upd.replace(tzinfo=timezone.utc).astimezone(tz).strftime(ts_fmt) if eff_upd else ""
        
        row_v = []
        for col in header:
            if col == "created_at":
                row_v.append(c_at_s)
            elif col == "updated_at":
                row_v.append(u_at_s)
            else:
                cell = r_data.get(col, {})
                val = cell.get("value") if isinstance(cell, dict) else cell
                if isinstance(val, dict) and "value" in val:
                    val = val.get("value")
                row_v.append(val)
        sample_writer.writerow(row_v)
    
    # UTF-8 바이트 수 기준으로 계산
    sample_bytes = len(sample_io.getvalue().encode("utf-8"))
    avg_row_size = sample_bytes / len(sample_rows) if sample_rows else 150
    header_size = len("\ufeff".encode("utf-8")) + len(",".join(header).encode("utf-8")) + 2
    estimated_total_size = int(header_size + (avg_row_size * total_count))

    def generate():
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Excel 인식을 위한 BOM 추가
        output.write('\ufeff')
        writer.writerow(header)
        yield output.getvalue()
        output.seek(0); output.truncate(0)

        # ── [Optimization] 1000개 단위로 청크 처리하여 Yield 부하 감소 ──
        batch_size = 1000
        current_batch = []
        
        # 타임존 및 포맷터 미리 캐싱
        tz = LOCAL_TIMEZONE
        ts_fmt = "%Y-%m-%d %H:%M:%S"

        for row_data, created_at, updated_at in export_query.yield_per(batch_size):
            row_vals = []
            # 시스템 컬럼 데이터 가공 (inject_system_columns 로직의 인라인 최적화)
            effective_update = updated_at if updated_at else created_at
            c_at_str = created_at.replace(tzinfo=timezone.utc).astimezone(tz).strftime(ts_fmt) if created_at else ""
            u_at_str = effective_update.replace(tzinfo=timezone.utc).astimezone(tz).strftime(ts_fmt) if effective_update else ""
            
            for col in header:
                if col == "created_at":
                    row_vals.append(c_at_str)
                elif col == "updated_at":
                    row_vals.append(u_at_str)
                else:
                    cell = row_data.get(col, {})
                    val = cell.get("value") if isinstance(cell, dict) else cell
                    # 만약 val이 또 dict 형태라면 (중첩 방어 로직)
                    if isinstance(val, dict) and "value" in val:
                        val = val.get("value")
                    row_vals.append(val)
            
            writer.writerow(row_vals)
            current_batch.append(output.getvalue())
            output.seek(0); output.truncate(0)
            
            if len(current_batch) >= batch_size:
                yield "".join(current_batch)
                current_batch = []
        
        # 남은 데이터 송신
        if current_batch:
            yield "".join(current_batch)

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
        first_row = db.query(models.DataRow).filter(
            models.DataRow.table_name == table_name
        ).first()
        
        if first_row and first_row.data:
            columns = list(first_row.data.keys())
        else:
            columns = []
            
    # [버그 수정] display_columns 정의 여부와 관계없이 시스템 컬럼은 항상 마지막에 보장
    system_cols = ["created_at", "updated_at"]
    for sc in system_cols:
        if sc not in columns:
            columns.append(sc)
            
    return {"table_name": table_name, "columns": columns}


@app.get("/tables/{table_name}/{row_id}", response_model=schemas.DataRowResponse)
def get_row_data(table_name: str, row_id: str, db: Session = Depends(get_db)):
    """
    특정 행의 데이터를 가져옵니다.
    """
    row = db.query(models.DataRow).filter(
        models.DataRow.table_name == table_name,
        models.DataRow.row_id == row_id
    ).first()
    
    if row:
        inject_system_columns(row)
        
    if not row:
        raise HTTPException(status_code=404, detail="Row not found")
    return row


@app.get("/tables/{table_name}/rows/{row_id}/history", response_model=list[schemas.AuditLogResponse])
def get_row_history(table_name: str, row_id: str, db: Session = Depends(get_db)):
    """
    특정 행의 모든 변경 이력을 가져옵니다.
    """
    logs = db.query(models.AuditLog).filter(
        models.AuditLog.table_name == table_name,
        models.AuditLog.row_id == row_id
    ).order_by(models.AuditLog.timestamp.desc()).all()
    return logs

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
    return logs

@app.post("/tables/{table_name}/rows")
async def create_row(table_name: str, count: int = 1, user_name: str = "system", db: Session = Depends(get_db)):
    """
    신규 행 추가 엔드포인트 (단건 및 다건 지원)
    """
    new_rows = crud.create_empty_rows_batch(db, table_name, count, user_name)
    
    if new_rows:
        invalidate_table_cache(table_name)
    
    msg_items = []
    for row in new_rows:
        inject_system_columns(row)
        msg_items.append({
            "row_id": row.row_id,
            "table_name": row.table_name,
            "data": row.data
        })
    
    # WebSocket 브로드캐스트 (대량 작업 시 500개씩 청크 분할 전송하여 메모리/통신 안정성 확보)
    CHUNK_SIZE = 500
    for i in range(0, len(msg_items), CHUNK_SIZE):
        chunk = msg_items[i:i + CHUNK_SIZE]
        msg = {
            "event": "batch_row_create",
            "table_name": table_name,
            "items": chunk,
            "updated_by": user_name
        }
        await manager.broadcast(json.dumps(msg))
    
    return {"status": "success", "count": len(new_rows), "row_ids": [r.row_id for r in new_rows]}

@app.put("/tables/{table_name}/data/updates")
async def apply_batch_updates_endpoint(table_name: str, batch: schemas.GeneralUpdateBatch, db: Session = Depends(get_db)):
    """단건 및 다건 업데이트를 통합 처리하고 브로드캐스트합니다."""
    from fastapi.concurrency import run_in_threadpool
    results, changed_cells = await run_in_threadpool(crud.apply_batch_updates, db, table_name, batch)
    
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
        
        if len(msg_items) > 100:
            # 대량 업데이트: 경량화된 새로고침 신호만 전송
            msg = {
                "event": "batch_refresh_required",
                "table_name": table_name,
                "change_count": len(msg_items)
            }
            await manager.broadcast(json.dumps(msg))
        else:
            # 소량 업데이트: 전체 데이터 전송
            CHUNK_SIZE = 500
            for i in range(0, len(msg_items), CHUNK_SIZE):
                chunk = msg_items[i:i + CHUNK_SIZE]
                msg = {
                    "event": "batch_row_upsert",
                    "table_name": table_name,
                    "items": chunk,
                    "change_count": len(chunk), 
                    "updated_by": user_name
                }
                await manager.broadcast(json.dumps(msg))
    
    return {"status": "success", "updated_count": len(results), "change_count": len(changed_cells)}

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
async def upload_file(table_name: str, file: UploadFile = File(...)):
    """
    클라이언트에서 보낸 로그 파일을 수신하여 해당 테이블의 인제션 워크스페이스(raws/)에 저장합니다.
    저장 시 directory_watcher.py가 이를 감지하여 자동으로 파싱을 시작합니다.
    """
    # 1. 대상 디렉토리 결정 (server/ingestion_workspace/{table_name}/raws)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.join(base_dir, "ingestion_workspace", table_name, "raws")
    
    # 2. 디렉토리가 없으면 생성 (setup_workspace.py가 미리 생성해두지만 안전을 위해)
    # 2. 파일명 중복 방지 (기존명_UUID.ext)
    orig_name, ext = os.path.splitext(file.filename)
    unique_name = f"{orig_name}_{uuid.uuid4().hex[:8]}{ext}"
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
    row = crud.get_row_cell(db, table_name, row_id)
    if not row or col_name not in row.data:
        raise HTTPException(status_code=404, detail="Cell not found")
    
    cell = row.data[col_name]
    return {
        "sources": cell.get("sources", {}),
        "manual_priority_source": cell.get("manual_priority_source"),
        "priority_source": cell.get("priority_source"),
        "value": cell.get("value")
    }

@app.delete("/tables/{table_name}/{row_id}/{col_name}/sources/{source_name}")
async def delete_cell_source(table_name: str, row_id: str, col_name: str, source_name: str, db: Session = Depends(get_db)):
    """특정 셀의 특정 원천 데이터를 삭제합니다."""
    updated_row, changed_cols = crud.delete_cell_source(db, table_name, row_id, col_name, source_name)
    if not updated_row:
        raise HTTPException(status_code=404, detail="Source or Cell not found")
    
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
    source_name: str = Body(..., embed=True), 
    updated_by: str = Body("user", embed=True),
    db: Session = Depends(get_db)
):
    """특정 셀의 표시 우선순위 소스를 수동으로 지정합니다 (Pin). source_name이 null이면 수동 지정 해제."""
    updated_row, changed_cols = crud.set_cell_manual_priority(db, table_name, row_id, col_name, source_name, updated_by)
    if not updated_row:
        raise HTTPException(status_code=404, detail="Cell not found or source invalid")
    
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

@app.get("/tables/{table_name}/rows/{row_id}/cells/{col_name}/history")
async def get_cell_history(table_name: str, row_id: str, col_name: str, db: Session = Depends(get_db)):
    """특정 셀의 변경 이력(AuditLog)을 조회합니다."""
    logs = db.query(models.AuditLog).filter(
        models.AuditLog.table_name == table_name,
        models.AuditLog.row_id == row_id,
        models.AuditLog.column_name == col_name
    ).order_by(desc(models.AuditLog.timestamp)).all()
    
    return logs
