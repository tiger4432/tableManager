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
    try:
        print("[Startup] Initializing Directory Watcher...")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        workspace_base = os.path.join(script_dir, "ingestion_workspace")
        
        global_watcher = WorkspaceWatcher(workspace_base)
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

@app.get("/audit_logs/recent", response_model=list[schemas.AuditLogResponse])
def get_recent_audit_logs(limit_groups: int = 100, db: Session = Depends(get_db)):
    """
    최신 로그 100 '그룹(Transaction)'을 가져옵니다.
    한 그룹에 수천 건의 변경이 있을 경우를 대비해 전체 행은 5,000건으로 제한합니다.
    """
    from sqlalchemy import desc, func
    
    # 1. 최근 로그 5000건을 먼저 조회 (성능 및 안전 장치)
    raw_logs = db.query(models.AuditLog)\
                 .order_by(desc(models.AuditLog.timestamp))\
                 .limit(5000).all()
                 
    if not raw_logs: return []

    # 2. 클라이언트와 동일한 그룹화 로직 적용하여 상위 100그룹만 선별
    groups = []
    seen_tids = set()
    final_logs = []

    for log in raw_logs:
        tid = log.transaction_id
        if tid:
            if tid not in seen_tids:
                if len(seen_tids) >= limit_groups: continue
                seen_tids.add(tid)
            final_logs.append(log)
        else:
            # transaction_id가 없는 단건 기록
            if len(seen_tids) < limit_groups:
                final_logs.append(log)
                # 단건도 그룹 하나로 간주할지 여부는 정책에 따라 (여기서는 그룹 수에 포함하지 않음)

    return final_logs


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
    db: Session = Depends(get_db)
):
    """
    Lazy Loading을 위한 페이징 엔드포인트
    q 파라미터가 있으면 전체 데이터 중 해당 검색어가 포함된 행만 필터링합니다.
    """
    query = db.query(models.DataRow).filter(models.DataRow.table_name == table_name)
    
    if q:
        from sqlalchemy import cast, String, or_
        # [Phase 73.8] 검색어 특수문자(%, _) 이스케이프 (Wildcard 성격 방지)
        safe_q = q.replace("%", "\\%").replace("_", "\\_")
        
        if cols:
            # [Phase 73.6] 특정 컬럼 내에서만 검색 (전용 DB 최적화 및 시스템 컬럼 지원)
            col_list = [c.strip() for c in cols.split(",") if c.strip()]
            conditions = []
            for col in col_list:
                if col in ["created_at", "updated_at"]:
                    # 시스템 날짜 컬럼 검색 지원
                    target_col = models.DataRow.created_at if col == "created_at" else models.DataRow.updated_at
                    conditions.append(cast(target_col, String).ilike(f"%{safe_q}%", escape="\\"))
                elif col in ["row_id", "id"]:
                    # ID 컬럼 검색 지원
                    conditions.append(models.DataRow.row_id.ilike(f"%{safe_q}%", escape="\\"))
                else:
                    # 일반 데이터 컬럼: DB 호환성(SQLite/PG)을 위해 cast 사용 (astext 대신)
                    conditions.append(cast(models.DataRow.data[col]["value"], String).ilike(f"%{safe_q}%", escape="\\"))
            
            if conditions:
                query = query.filter(or_(*conditions))
        else:
            # Fallback: 전체 JSON 데이터를 문자열로 캐스팅하여 검색 (기존 방식)
            search_filter = cast(models.DataRow.data, String).ilike(f"%{safe_q}%", escape="\\")
            query = query.filter(search_filter)

    # [성능 최적화] 검색어가 없을 때만 카운트 캐시 적용
    now = time.time()
    t_start = now
    if not q and table_name in TABLE_COUNT_CACHE and (now - TABLE_COUNT_CACHE[table_name][1] < 2.0):
        total_count = TABLE_COUNT_CACHE[table_name][0]
    else:
        total_count = query.count()
        if not q: TABLE_COUNT_CACHE[table_name] = (total_count, now)
    
    t_count = time.time() - t_start
    
    from sqlalchemy.sql import func
    # 정렬 기준 구성 (PostgreSQL 최적화: nullslast/nullsfirst 사용)
    if order_by == "updated_at":
        sort_expr = func.coalesce(models.DataRow.updated_at, models.DataRow.created_at)
        sort_expr = sort_expr.desc().nullslast() if order_desc else sort_expr.asc().nullslast()
        tie_breaker = models.DataRow.row_id.asc()
        final_sort = [sort_expr, tie_breaker]
    elif order_by == "id":
        bk_sort = models.DataRow.business_key_val.desc().nullslast() if order_desc else models.DataRow.business_key_val.asc().nullslast()
        final_sort = [bk_sort, models.DataRow.row_id.asc()]
    else:
        sort_expr = models.DataRow.row_id.asc()
        final_sort = [sort_expr]
    
    # [성능 최적화] "물리적 2단계 Fetch" 적용 (PostgreSQL Index-Only Scan 유도)
    # 1단계: ID 리스트만 인덱스 스캔으로 먼저 Fetch (매우 가벼움)
    t_id_start = time.time()
    subquery = query.with_entities(models.DataRow.row_id)
    if order_by == "updated_at":
        subquery = subquery.order_by(*final_sort)
    else:
        subquery = subquery.order_by(*final_sort)
        
    id_results = subquery.offset(skip).limit(limit).all()
    id_list = [r[0] for r in id_results]
    t_id_fetch = time.time() - t_id_start
    
    # 2단계: 선별된 ID 목록으로만 본 데이터 조회 (PK 기반 고속 Fetch, JOIN 오티마이저 노이즈 제거)
    t_row_start = time.time()
    rows = db.query(models.DataRow).filter(models.DataRow.row_id.in_(id_list)).all()
    t_row_fetch = time.time() - t_row_start
    
    # 3. 애플리케이션 레벨 재정렬 (IN 절은 순서를 보장하지 않음)
    t_sort_start = time.time()
    # 정합성을 위해 id_list의 순서대로 정렬 (가장 확실하고 빠른 방법)
    id_to_idx = {rid: i for i, rid in enumerate(id_list)}
    rows.sort(key=lambda x: id_to_idx.get(x.row_id, 999999))
    
    # 공통 데코레이터 적용
    t_inject_start = time.time()
    data_list = []
    for row in rows:
        inject_system_columns(row)
        # [성능 최적화] Pydantic 객체 생성을 생략하고 원시 Dict로 변환 (속도 10배 향상)
        data_list.append({
            "row_id": row.row_id,
            "table_name": row.table_name,
            "data": row.data,
            "created_at": to_local_str(row.created_at),
            "updated_at": to_local_str(row.updated_at)
        })
    t_inject = time.time() - t_inject_start
    
    t_inject = time.time() - t_inject_start
    
    print(f"[PERF] /data: table={table_name}, skip={skip}, limit={limit}, query={q is not None}")
    print(f"       Count: {t_count:.3f}s | IDs: {t_id_fetch:.3f}s | Rows: {t_row_fetch:.3f}s | Inject: {t_inject:.3f}s | Total: {time.time()-t_start:.3f}s")

    return {
        "table_name": table_name,
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "data": data_list
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
        from sqlalchemy import cast, String, or_
        if req.cols:
            col_list = [c.strip() for c in req.cols.split(",") if c.strip()]
            conditions = []
            for col in col_list:
                if col in ["created_at", "updated_at"]:
                    target_col = models.DataRow.created_at if col == "created_at" else models.DataRow.updated_at
                    conditions.append(cast(target_col, String).ilike(f"%{req.q}%"))
                elif col in ["row_id", "id"]:
                    conditions.append(models.DataRow.row_id.ilike(f"%{req.q}%"))
                else:
                    # DB 호환성 보장
                    conditions.append(cast(models.DataRow.data[col]["value"], String).ilike(f"%{req.q}%"))
            
            if conditions:
                query = query.filter(or_(*conditions))
        else:
            search_filter = cast(models.DataRow.data, String).ilike(f"%{req.q}%")
            query = query.filter(search_filter)

    from sqlalchemy.sql import func
    if req.order_by == "updated_at":
        sort_expr = func.coalesce(models.DataRow.updated_at, models.DataRow.created_at)
        sort_expr = sort_expr.desc() if req.order_desc else sort_expr.asc()
        tie_breaker = models.DataRow.row_id.asc()
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

@app.post("/tables/{table_name}/row_index/{row_id}")
def get_row_index(table_name: str, row_id: str, req: schemas.RowIndexDiscoveryRequest, db: Session = Depends(get_db)):
    """
    특정 row_id가 현재 정렬/필터링 조건 하에서 몇 번째(Offset)에 위치하는지 계산하여 반환합니다.
    밀리언 로우 환경에서도 고속 점프를 지원하기 위해 Window Function을 활용합니다.
    """
    from sqlalchemy import func, over, literal_column
    
    # 1. 기본 쿼리 및 필터링 (get_table_data와 동일 로직)
    query = db.query(models.DataRow).filter(models.DataRow.table_name == table_name)
    
    if req.q:
        from sqlalchemy import cast, String, or_
        safe_q = req.q.replace("%", "\\%").replace("_", "\\_")
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
                    conditions.append(cast(models.DataRow.data[col]["value"], String).ilike(f"%{safe_q}%", escape="\\"))
            if conditions:
                query = query.filter(or_(*conditions))
        else:
            query = query.filter(cast(models.DataRow.data, String).ilike(f"%{safe_q}%", escape="\\"))

    # 2. 정렬 순서 결정 (get_table_data와 동일 로직)
    if req.order_by == "updated_at":
        sort_expr = func.coalesce(models.DataRow.updated_at, models.DataRow.created_at)
        sort_expr = sort_expr.desc() if req.order_desc else sort_expr.asc()
        final_orders = [sort_expr, models.DataRow.row_id.asc()]
    elif req.order_by == "id":
        bk_null_last = (models.DataRow.business_key_val == None).asc()
        bk_sort = models.DataRow.business_key_val.desc() if req.order_desc else models.DataRow.business_key_val.asc()
        final_orders = [bk_null_last, bk_sort, models.DataRow.row_id.asc()]
    else:
        final_orders = [models.DataRow.row_id.asc()]

    # 3. Window Function을 사용하여 전체 데이터 셋에서의 순번(Offset) 계산
    # SELECT pos FROM (SELECT row_id, (ROW_NUMBER() OVER (...)) - 1 as pos FROM data_rows ...) WHERE row_id = :id
    subquery = query.with_entities(
        models.DataRow.row_id,
        (func.row_number().over(order_by=final_orders) - 1).label("pos")
    ).subquery()
    
    result = db.query(subquery.c.pos).filter(subquery.c.row_id == row_id).first()
    
    if result is None:
        return {"row_id": row_id, "index": -1, "status": "not_found"}
        
    print(f"[Discovery] Row {row_id} found at offset {result[0]}")
    return {"row_id": row_id, "index": result[0], "status": "success"}


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
        sort_expr = func.coalesce(models.DataRow.updated_at, models.DataRow.created_at)
        sort_expr = sort_expr.desc() if order_desc else sort_expr.asc()
        final_sort = [sort_expr, models.DataRow.row_id.asc()]
    elif order_by == "id":
        bk_null_last = (models.DataRow.business_key_val == None).asc()
        bk_sort = models.DataRow.business_key_val.desc() if order_desc else models.DataRow.business_key_val.asc()
        final_sort = [bk_null_last, bk_sort, models.DataRow.row_id.asc()]
    else:
        final_sort = [models.DataRow.row_id.asc()]

    # [Safety Limit] 최대 100만 행으로 제한하며 정렬 적용
    total_count = min(query.count(), 1000000)
    query = query.order_by(*final_sort).limit(total_count)
    
    # 1. 헤더 구성을 위한 샘플링 (첫 행 기준)
    first_row = query.first()
    if not first_row:
        raise HTTPException(status_code=404, detail="No data matches the current filter")

    system_cols = ["created_at", "updated_at"]
    business_cols = [k for k in sorted(first_row.data.keys()) if k not in system_cols]
    header = business_cols + system_cols

    # 2. 크기 샘플링 예측 (1행당 평균 바이트 계산)
    sample_rows = query.limit(5).all()
    sample_io = io.StringIO()
    sample_writer = csv.writer(sample_io)
    sample_writer.writerow(header) # 헤더 포함
    header_size = len(sample_io.getvalue())
    sample_io.seek(0); sample_io.truncate(0)
    
    for row in sample_rows:
        inject_system_columns(row)
        sample_writer.writerow([row.data.get(col, {}).get("value") if isinstance(row.data.get(col, {}), dict) else row.data.get(col) for col in header])
    
    avg_row_size = len(sample_io.getvalue()) / len(sample_rows) if sample_rows else 100
    estimated_total_size = int(header_size + (avg_row_size * total_count))

    def generate():
        output = io.StringIO()
        writer = csv.writer(output)
        output.write('\ufeff') # BOM for Excel
        writer.writerow(header)
        yield output.getvalue()
        output.seek(0); output.truncate(0)


        # yield_per를 사용하여 DB 서버에서 한 번에 1000개씩만 페치 (메모리 보호)
        # SQLite는 yield_per를 지원하지 않을 수 있지만, 대용량 스케일(PG/MySQL) 대응용
        for row in query.yield_per(1000):
            inject_system_columns(row)
            row_vals = []
            for col in header:
                cell = row.data.get(col, {})
                val = cell.get("value") if isinstance(cell, dict) else cell
                if isinstance(val, dict) and "value" in val:
                    val = val.get("value")
                row_vals.append(val)
            
            writer.writerow(row_vals)
            yield output.getvalue()
            output.seek(0); output.truncate(0)

    filename = f"{table_name}_extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Content-Length": str(estimated_total_size),
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
    results, changed_cells = crud.apply_batch_updates(db, table_name, batch)
    
    msg_items = []
    for row, is_new in results:
        # Agent D v16: 브로드캐스트 페이로드에 시간 메타데이터(created_at, updated_at)를 강제 주입
        inject_system_columns(row)
        msg_items.append({
            "row_id": row.row_id,
            "is_new": is_new,
            "data": row.data
        })
    
    # WebSocket 브로드캐스트 (batch.silent가 False인 경우에만 수행)
    if not batch.silent:
        user_name = batch.updates[0].updated_by if batch.updates else "system"
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
        "items": [{"row_id": row_id, "is_new": False, "data": updated_row.data}],
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
        "items": [{"row_id": row_id, "is_new": False, "data": updated_row.data}],
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
