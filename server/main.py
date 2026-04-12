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
        for connection in self.active_connections:
            await connection.send_text(message)

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
def get_table_data(table_name: str, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """
    Lazy Loading을 위한 페이징 엔드포인트
    클라이언트 Viewport에서 필요한 영역만 (skip ~ skip+limit) 가져옵니다.
    """
    query = db.query(models.DataRow).filter(models.DataRow.table_name == table_name)
    total_count = query.count()
    rows = query.offset(skip).limit(limit).all()
    
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
        "is_overwrite": True
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
                "is_overwrite": True
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
    
    # WebSocket 브로드캐스트
    msg = {
        "event": "row_create",
        "table_name": table_name,
        "data": {
            "row_id": new_row.row_id,
            "table_name": new_row.table_name,
            "data": new_row.data,
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
        msg = {
            "event": "row_create",
            "table_name": table_name,
            "data": {
                "row_id": row.row_id,
                "table_name": row.table_name,
                "data": row.data,
                "created_at": row.created_at.isoformat() if row.created_at else None
            }
        }
    else:
        msg = {
            "event": "batch_cell_update",
            "table_name": table_name,
            "updates": [
                {
                    "row_id": row.row_id,
                    "column_name": col,
                    "value": val,
                    "is_overwrite": (upsert.source_name == "user")
                } for col, val in upsert.updates.items()
            ]
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
