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

from datetime import timezone

def to_local_str(dt):
    """UTC 데이트타임을 현지 시간(Local) 문자열로 변환합니다."""
    if not dt: return ""
    ts_fmt = "%Y-%m-%d %H:%M:%S"
    # SQLite naive datetime assumes UTC. Force UTC if naive before conversion.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime(ts_fmt)

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

@app.get("/tables/{table_name}/data", response_model=schemas.PaginatedDataResponse)
def get_table_data(
    table_name: str, 
    skip: int = 0, 
    limit: int = 500, 
    q: str = None, 
    cols: str = None, # [Phase 73.6] 검색 대상 컬럼 제한 (comma separated)
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

    total_count = query.count()
    
    from sqlalchemy.sql import func
    # 정렬 기준 구성 (고성능 Shadow Column 활용)
    if order_by == "updated_at":
        sort_expr = func.coalesce(models.DataRow.updated_at, models.DataRow.created_at)
        sort_expr = sort_expr.desc() if order_desc else sort_expr.asc()
    elif order_by == "id":
        # 사용자가 "자연 정렬"을 원할 경우: BK가 있으면 BK순, 없으면 ID순으로 고성능 정렬
        # [기능 개선] BK가 비어있는(NULL) 행은 항상 맨 마지막으로 보냄
        # (business_key_val == None) 은 IS NULL 로 번역되며, False(0) < True(1) 이므로 오름차순 시 NULL(True)이 뒤로 감
        bk_null_last = (models.DataRow.business_key_val == None).asc()
        bk_sort = models.DataRow.business_key_val.desc() if order_desc else models.DataRow.business_key_val.asc()
        
        final_sort = [bk_null_last, bk_sort, models.DataRow.row_id.asc()]
    else:
        sort_expr = models.DataRow.row_id.asc()
        final_sort = [sort_expr]
    
    if order_by == "updated_at":
        # [핵심] Tie-breaker 추가: 시간이 완전히 동일한 행들의 임의 섞임을 방지하기 위해 row_id를 2차 정렬 조건으로 사용
        tie_breaker = models.DataRow.row_id.asc()
        rows = query.order_by(sort_expr, tie_breaker).offset(skip).limit(limit).all()
    else:
        rows = query.order_by(*final_sort).offset(skip).limit(limit).all()
    
    # 공통 데코레이터 적용
    for row in rows:
        inject_system_columns(row)

    return schemas.PaginatedDataResponse(
        table_name=table_name,
        total=total_count,
        skip=skip,
        limit=limit,
        data=rows
    )

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


from fastapi.responses import StreamingResponse
import csv
import io
from datetime import datetime

@app.get("/tables/{table_name}/export")
def export_table_csv(table_name: str, db: Session = Depends(get_db)):
    """
    테이블의 모든 데이터를 CSV 형식으로 추출하여 스트리밍 반환합니다.
    (Spotfire 등 외부 분석 도구 연동용)
    """
    rows = db.query(models.DataRow).filter(models.DataRow.table_name == table_name).all()
    
    if not rows:
        raise HTTPException(status_code=404, detail="No data found for this table")

    # 1. 컬럼 헤더 구성 (모든 행의 키 집합 추출)
    all_keys = set()
    for row in rows:
        all_keys.update(row.data.keys())
    
    # 정렬: 일반 컬럼 -> 시스템 컬럼 순
    system_cols = ["created_at", "updated_at"]
    business_cols = [k for k in sorted(all_keys) if k not in system_cols]
    header = business_cols + system_cols

    def generate():
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Excel 한글 깨짐 방지용 BOM 추가
        output.write('\ufeff')
        writer.writerow(header)
        yield output.getvalue()
        output.seek(0); output.truncate(0)

        for row in rows:
            # 시스템 컬럼 및 KST 시간 정보를 data 에 주입
            inject_system_columns(row)
            
            row_vals = []
            for col in header:
                cell = row.data.get(col, {})
                # CellData 구조일 경우 value 추출 (이중 래핑 방지: value 자체가 dict인 경우 재귀 추출)
                val = cell.get("value") if isinstance(cell, dict) else cell
                # 마이그레이션 오류 등으로 인한 이중 래핑 방어
                if isinstance(val, dict) and "value" in val:
                    val = val.get("value")
                row_vals.append(val)
            
            writer.writerow(row_vals)
            yield output.getvalue()
            output.seek(0); output.truncate(0)

    filename = f"{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response = StreamingResponse(generate(), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response

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
    
    # WebSocket 브로드캐스트 (대량 작업 시 500개씩 청크 분할 전송)
    user_name = batch.updates[0].updated_by if batch.updates else "system"
    CHUNK_SIZE = 500
    for i in range(0, len(msg_items), CHUNK_SIZE):
        chunk = msg_items[i:i + CHUNK_SIZE]
        msg = {
            "event": "batch_row_upsert",
            "table_name": table_name,
            "items": chunk,
            "change_count": len(chunk), # 해당 청크의 개수만 전달
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
    os.makedirs(target_dir, exist_ok=True)
    
    file_path = os.path.join(target_dir, file.filename)
    
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
