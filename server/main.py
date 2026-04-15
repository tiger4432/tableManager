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
def get_table_data(table_name: str, skip: int = 0, limit: int = 50, q: str = None, db: Session = Depends(get_db)):
    """
    Lazy Loading을 위한 페이징 엔드포인트
    q 파라미터가 있으면 전체 데이터 중 해당 검색어가 포함된 행만 필터링합니다.
    """
    query = db.query(models.DataRow).filter(models.DataRow.table_name == table_name)
    
    if q:
        from sqlalchemy import cast, String
        # JSON 데이터를 문자열로 캐스팅하여 부분 일치(LIKE) 검색 수행 (SQLite 대응)
        search_filter = cast(models.DataRow.data, String).ilike(f"%{q}%")
        query = query.filter(search_filter)

    total_count = query.count()
    
    from sqlalchemy.sql import func
    # 정렬 기준: updated_at(최고 우선순위), 없으면 created_at으로 보완 (COALESCE)
    sort_expr = func.coalesce(models.DataRow.updated_at, models.DataRow.created_at).desc()
    
    rows = query.order_by(sort_expr).offset(skip).limit(limit).all()
    
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

@app.put("/tables/{table_name}/cells")
async def update_cell(table_name: str, cell_update: schemas.CellUpdate, db: Session = Depends(get_db)):
    """
    단일 셀 데이터 업데이트 엔드포인트
    """
    row = crud.update_cell(db, table_name, cell_update)
    if not row:
        raise HTTPException(status_code=404, detail="Row not found")
        
    # Broadcast cell update to connected clients via WebSocket
    msg = {
        "event": "cell_update",
        "table_name": table_name,
        "row_id": cell_update.row_id,
        "column_name": cell_update.column_name,
        "value": cell_update.value,
        "is_overwrite": True,
        "updated_by": cell_update.updated_by or "unknown",
        "updated_at": to_local_str(row.updated_at or row.created_at)
    }
    await manager.broadcast(json.dumps(msg))
    
    return {"status": "success", "row_id": row.row_id}

@app.put("/tables/{table_name}/cells/batch")
async def update_cells_batch(table_name: str, batch: schemas.CellUpdateBatch, db: Session = Depends(get_db)):
    """
    다중 셀 데이터 일괄 업데이트 엔드포인트
    """
    rows = crud.update_cells_batch(db, table_name, batch)
    row_map = {r.row_id: r for r in rows}
    
    # Broadcast batch update
    msg = {
        "event": "batch_cell_update",
        "table_name": table_name,
        "updates": [
            {
                "row_id": u.row_id,
                "column_name": u.column_name,
                "value": u.value,
                "is_overwrite": True,
                "updated_at": to_local_str(row_map[u.row_id].updated_at or row_map[u.row_id].created_at)
            } for u in batch.updates if u.row_id in row_map
        ],
        "updated_by": batch.updates[0].updated_by if batch.updates else "unknown"
    }
    await manager.broadcast(json.dumps(msg))
    
    return {"status": "success", "updated_count": len(rows)}
@app.delete("/tables/{table_name}/rows/{row_id}")
async def delete_row(table_name: str, row_id: str, db: Session = Depends(get_db)):
    """
    행 삭제 엔드포인트
    """
    success = crud.delete_row(db, table_name, row_id)
    if not success:
        raise HTTPException(status_code=404, detail="Row not found")
        
    # Broadcast row deletion to connected clients
    msg = {
        "event": "row_delete",
        "table_name": table_name,
        "row_id": row_id
    }
    await manager.broadcast(json.dumps(msg))
    
    return {"status": "success", "row_id": row_id}


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
    설정 파일에 정의된 display_columns 를 우선적으로 반환하며, 
    정의되지 않은 경우 데이터에서 키를 추출합니다.
    """
    config = crud.TABLE_CONFIG.get(table_name, {})
    columns = config.get("display_columns")
    
    if columns:
        return {"table_name": table_name, "columns": columns}
        
    # 데이터에서 동적 추출 (Fallback)
    first_row = db.query(models.DataRow).filter(
        models.DataRow.table_name == table_name
    ).first()
    
    if first_row and first_row.data:
        # key 리스트 추출 (정적 정렬 등 추가 고려 가능)
        columns = list(first_row.data.keys())
    else:
        columns = []
        
    # Always suggest system columns at the end
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

@app.post("/tables/{table_name}/rows", response_model=schemas.DataRowResponse)
async def create_row(table_name: str, db: Session = Depends(get_db)):
    """
    신규 행 추가 엔드포인트
    """
    new_row = crud.create_empty_row(db, table_name)
    
    # 공통 데코레이터 적용 (created_at, updated_at 주입)
    inject_system_columns(new_row)
    broadcast_data = new_row.data.copy()

    # WebSocket 브로드캐스트
    msg = {
        "event": "row_create",
        "table_name": table_name,
        "data": {
            "row_id": new_row.row_id,
            "table_name": new_row.table_name,
            "data": broadcast_data,
            "created_at": new_row.created_at.isoformat() if new_row.created_at else None
        }
    }
    await manager.broadcast(json.dumps(msg))
    
    return new_row

@app.put("/tables/{table_name}/upsert/batch")
async def upsert_rows_batch_endpoint(table_name: str, batch: schemas.CellUpsertBatch, db: Session = Depends(get_db)):
    """
    다중 행 비즈니스 키 기반 배치 업서트 엔드포인트
    """
    if not batch.items:
        return {"status": "success", "count": 0}
        
    results = crud.upsert_rows_batch(db, table_name, batch.items)
    
    # WebSocket 브로드캐스트: 모든 변경사항을 하나의 'batch_row_upsert'로 압축
    # 클라이언트는 이를 받고 모델을 효율적으로 갱신
    upsert_events = []
    for row, is_new in results:
        inject_system_columns(row)
        upsert_events.append({
            "row_id": row.row_id,
            "is_new": is_new,
            "data": row.data # 전체 데이터 포함
        })
        
    msg = {
        "event": "batch_row_upsert",
        "table_name": table_name,
        "items": upsert_events
    }
    await manager.broadcast(json.dumps(msg))
    
    return {
        "status": "success",
        "count": len(results)
    }



@app.put("/tables/{table_name}/upsert")
async def upsert_row(table_name: str, upsert: schemas.CellUpsert, db: Session = Depends(get_db)):
    """
    비즈니스 키 기반 Upsert 엔드포인트
    """
    row, is_new = crud.upsert_row(
        db, table_name, upsert.business_key_val, 
        upsert.updates, upsert.source_name, upsert.updated_by
    )
    
    # WebSocket 브로드캐스트
    if is_new:
        # Virtual inject system columns
        inject_system_columns(row)
        broadcast_data = row.data.copy()

        msg = {
            "event": "row_create",
            "table_name": table_name,
            "data": {
                "row_id": row.row_id,
                "table_name": row.table_name,
                "data": broadcast_data,
                "created_at": to_local_str(row.created_at)
            }
        }
    else:
        # Include updated timestamps in the updates list for real-time UI refresh
        # 공통 데코레이터 적용
        inject_system_columns(row)
        
        updates_list = []
        for col, val in row.data.items():
            cell_state = row.data.get(col, {})
            updates_list.append({
                "row_id": row.row_id,
                "column_name": col,
                "value": cell_state.get("value", val),
                "is_overwrite": cell_state.get("is_overwrite", False)
            })
        
        msg = {
            "event": "batch_cell_update",
            "table_name": table_name,
            "updates": updates_list
        }
        
    await manager.broadcast(json.dumps(msg))
    
    return {
        "status": "success", 
        "row_id": row.row_id, 
        "is_new": is_new
    }



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received msg: {data}")
            # Echo back for test
            await manager.broadcast(f"Broadcast: {data}")
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
    row = crud.get_row_cell(db, table_name, row_id, col_name)
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
    updated_row = crud.delete_cell_source(db, table_name, row_id, col_name, source_name)
    if not updated_row:
        raise HTTPException(status_code=404, detail="Source or Cell not found")
    
    # WebSocket 브로드캐스트 (실시간 갱신용)
    import json
    cell_state = updated_row.data[col_name]
    await manager.broadcast(json.dumps({
        "event": "batch_cell_update", # 'type' 대신 'event' 사용 (클라이언트 파서 규격 준수)
        "table_name": table_name,
        "updates": [
            {
                "row_id": row_id, "column_name": col_name, 
                "value": cell_state["value"],
                "is_overwrite": cell_state.get("is_overwrite", False),
                "updated_by": cell_state.get("updated_by", "system")
            }
        ]
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
    updated_row = crud.set_cell_manual_priority(db, table_name, row_id, col_name, source_name, updated_by)
    if not updated_row:
        raise HTTPException(status_code=404, detail="Cell not found or source invalid")
    
    # WebSocket 브로드캐스트
    import json
    cell_state = updated_row.data[col_name]
    await manager.broadcast(json.dumps({
        "event": "batch_cell_update",
        "table_name": table_name,
        "updates": [
            {
                "row_id": row_id, "column_name": col_name, 
                "value": cell_state["value"],
                "is_overwrite": cell_state.get("is_overwrite", False),
                "updated_by": cell_state.get("updated_by", "system")
            }
        ]
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
