from sqlalchemy.orm import Session
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from database.database import SessionLocal, engine, get_db
from database import models, schemas, crud
import uuid 

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
    
    rows = query.order_by(models.DataRow.updated_at.desc(), models.DataRow.created_at.desc())\
                .offset(skip).limit(limit).all()
    
    # UI에서 바로 볼 수 있도록 created_at, updated_at을 data JSON에 가상으로 주입
    for row in rows:
        if "created_at" not in row.data:
            row.data["created_at"] = {"value": row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else "", "is_overwrite": False, "updated_by": "system"}
        if "updated_at" not in row.data:
            row.data["updated_at"] = {"value": row.updated_at.strftime("%Y-%m-%d %H:%M:%S") if row.updated_at else "", "is_overwrite": False, "updated_by": "system"}

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
        "updated_by": cell_update.updated_by or "unknown"
    }
    await manager.broadcast(json.dumps(msg))
    
    return {"status": "success", "row_id": row.row_id}

@app.put("/tables/{table_name}/cells/batch")
async def update_cells_batch(table_name: str, batch: schemas.CellUpdateBatch, db: Session = Depends(get_db)):
    """
    다중 셀 데이터 일괄 업데이트 엔드포인트
    """
    rows = crud.update_cells_batch(db, table_name, batch)
    
    # Broadcast batch update to connected clients
    msg = {
        "event": "batch_cell_update",
        "table_name": table_name,
        "updates": [
            {
                "row_id": u.row_id,
                "column_name": u.column_name,
                "value": u.value,
                "is_overwrite": True,
                "updated_by": u.updated_by or "unknown"
            } for u in batch.updates
        ]
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
    
    # Virtual inject system columns for real-time UI
    broadcast_data = new_row.data.copy()
    broadcast_data["created_at"] = {"value": new_row.created_at.strftime("%Y-%m-%d %H:%M:%S") if new_row.created_at else "", "is_overwrite": False, "updated_by": "system"}
    broadcast_data["updated_at"] = {"value": new_row.updated_at.strftime("%Y-%m-%d %H:%M:%S") if new_row.updated_at else "", "is_overwrite": False, "updated_by": "system"}

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
        broadcast_data = row.data.copy()
        broadcast_data["created_at"] = {"value": row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else "", "is_overwrite": False, "updated_by": "system"}
        broadcast_data["updated_at"] = {"value": row.updated_at.strftime("%Y-%m-%d %H:%M:%S") if row.updated_at else "", "is_overwrite": False, "updated_by": "system"}

        msg = {
            "event": "row_create",
            "table_name": table_name,
            "data": {
                "row_id": row.row_id,
                "table_name": row.table_name,
                "data": broadcast_data,
                "created_at": row.created_at.isoformat() if row.created_at else None
            }
        }
    else:
        # Include updated timestamps in the updates list for real-time UI refresh
        updates_list = []
        for col, val in upsert.updates.items():
            cell_state = row.data.get(col, {})
            updates_list.append({
                "row_id": row.row_id,
                "column_name": col,
                "value": cell_state.get("value", val),
                "is_overwrite": cell_state.get("is_overwrite", False)
            })
        
        # Add system columns as virtual updates
        ts_fmt = "%Y-%m-%d %H:%M:%S"
        updates_list.append({
            "row_id": row.row_id,
            "column_name": "created_at",
            "value": row.created_at.strftime(ts_fmt) if row.created_at else "",
            "is_overwrite": False
        })
        updates_list.append({
            "row_id": row.row_id,
            "column_name": "updated_at",
            "value": row.updated_at.strftime(ts_fmt) if row.updated_at else "",
            "is_overwrite": False
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
