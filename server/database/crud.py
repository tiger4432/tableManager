from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import Any
from . import models, schemas
import uuid

# 소스별 우선순위 정의 (숫자가 낮을수록 높음)
SOURCE_PRIORITY = {
    "user": 0,
    "parser_a": 1,
    "parser_b": 2
}

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "table_config.json")

def load_table_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"Config file not found: {CONFIG_PATH}")
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading table config: {e}")
        return {}

TABLE_CONFIG = load_table_config()

def get_row_by_business_key(db: Session, table_name: str, key_value: Any):
    """
    테이블별 비즈니스 키(예: part_no)를 기반으로 행을 조회합니다.
    데이터 수동 입력 시 발생하는 공백이나 타입 차이(int vs str)를 고려하여 정밀 비교합니다.
    """
    config = TABLE_CONFIG.get(table_name, {})
    key_col = config.get("business_key")
    if not key_col:
        return None
        
    rows = db.query(models.DataRow).filter(
        models.DataRow.table_name == table_name
    ).all()
    
    target_val = str(key_value).strip() if key_value is not None else ""
    
    for row in rows:
        cell = row.data.get(key_col, {})
        stored_val = cell.get("value")
        if stored_val is not None and str(stored_val).strip() == target_val:
            return row
    return None

def compute_priority_value(sources: dict, manual_priority_source: str = None):
    """
    저장된 여러 소스들 중 가장 우선순위가 높은 값을 결정합니다.
    manual_priority_source가 지정된 경우 해당 소스를 최우선으로 채택합니다.
    """
    if not sources:
        return None, None
        
    # 1. 수동 지정된 소스가 있는 경우 최우선 적용
    if manual_priority_source and manual_priority_source in sources:
        val_data = sources[manual_priority_source]
        if isinstance(val_data, dict) and "value" in val_data:
            return val_data["value"], manual_priority_source
        return val_data, manual_priority_source

    # 2. 기본 우선순위 순서대로 정렬 (지정되지 않은 소스는 기본값 99)
    sorted_sources = sorted(
        sources.keys(),
        key=lambda k: SOURCE_PRIORITY.get(k, 99)
    )
    
    top_source = sorted_sources[0]
    val_data = sources[top_source]
    if isinstance(val_data, dict) and "value" in val_data:
        return val_data["value"], top_source
    return val_data, top_source

def create_audit_log(db: Session, table_name: str, row_id: str, col_name: str, old_val: Any, new_val: Any, source: str, user: str):
    log = models.AuditLog(
        table_name=table_name,
        row_id=row_id,
        column_name=col_name,
        old_value=old_val,
        new_value=new_val,
        source_name=source,
        updated_by=user
    )
    db.add(log)

def update_cell(db: Session, table_name: str, cell_update: schemas.CellUpdate):
    # Agent D v12: 시스템 컬럼 수정 차단
    if cell_update.column_name in ["created_at", "updated_at", "row_id", "id", "updated_by"]:
        return None  # 또는 에러 발생 가능. 여기서는 None으로 무시 처리.
        
    row = db.query(models.DataRow).filter(
        models.DataRow.table_name == table_name,
        models.DataRow.row_id == cell_update.row_id
    ).first()
    
    if not row:
        return None
        
    data = row.data
    if cell_update.column_name not in data:
        data[cell_update.column_name] = {
            "value": None,
            "is_overwrite": False,
            "sources": {},
            "updated_by": "system",
            "priority_source": None
        }
        
    cell = data[cell_update.column_name]
    old_full_value = cell.get("value")
    
    # 1. 해당 소스의 데이터를 저장 (타임스탬프와 함께)
    if "sources" not in cell: cell["sources"] = {}
    from datetime import datetime
    cell["sources"][cell_update.source_name] = {
        "value": cell_update.value,
        "timestamp": datetime.now().isoformat(),
        "updated_by": cell_update.updated_by
    }
    
    # 2. 우선순위 계산 및 최종 값(value) 결정
    final_val, top_src = compute_priority_value(cell["sources"], cell.get("manual_priority_source"))
    
    cell["value"] = final_val
    cell["priority_source"] = top_src
    cell["is_overwrite"] = ("user" in cell["sources"])
    cell["updated_by"] = cell_update.updated_by
    
    # 3. 감사 로그 생성
    create_audit_log(db, table_name, cell_update.row_id, cell_update.column_name, old_full_value, cell_update.value, cell_update.source_name, cell_update.updated_by)
    
    # Notify SQLAlchemy that the JSON column was mutated
    flag_modified(row, "data")
    db.commit()
    db.refresh(row)
    return row

def update_cells_batch(db: Session, table_name: str, batch: schemas.CellUpdateBatch):
    updated_rows = []
    # For now, do iterative updates. Can be aggregated by row_id for better perf.
    for update in batch.updates:
        row = db.query(models.DataRow).filter(
            models.DataRow.table_name == table_name,
            models.DataRow.row_id == update.row_id
        ).first()
        
        if row:
            if update.column_name not in row.data:
                row.data[update.column_name] = {
                    "value": None, "is_overwrite": False, "sources": {},
                    "updated_by": "system", "priority_source": None
                }
            
            cell = row.data[update.column_name]
            old_full_value = cell.get("value")
            
            if "sources" not in cell: cell["sources"] = {}
            from datetime import datetime
            cell["sources"][update.source_name] = {
                "value": update.value,
                "timestamp": datetime.now().isoformat()
            }
            
            final_val, top_src = compute_priority_value(cell["sources"], cell.get("manual_priority_source"))
            cell["value"] = final_val
            cell["priority_source"] = top_src
            cell["is_overwrite"] = ("user" in cell["sources"])
            cell["updated_by"] = update.updated_by

            # 감사 로그 (배치 내 개별 로그 생성)
            create_audit_log(db, table_name, update.row_id, update.column_name, old_full_value, update.value, update.source_name, update.updated_by)
            flag_modified(row, "data")
            if row not in updated_rows:
                updated_rows.append(row)
                
    if updated_rows:
        db.commit()
        for r in updated_rows:
            db.refresh(r)
            
    return updated_rows

def delete_row(db: Session, table_name: str, row_id: str):
    row = db.query(models.DataRow).filter(
        models.DataRow.table_name == table_name,
        models.DataRow.row_id == row_id
    ).first()
    
    if row:
        db.delete(row)
        db.commit()
        return True
    return False
    
    if row:
        db.delete(row)
        db.commit()
        return True
    return False

def create_empty_row(db: Session, table_name: str):
    new_row_id = str(uuid.uuid4())
    # Create basic data structure for the row
    # In this app, columns are dynamic in JSON. 
    # We can initialize with an empty dict or pre-fill known columns.
    # For now, let's keep it empty as per instructions.
    new_row = models.DataRow(
        row_id=new_row_id,
        table_name=table_name,
        data={}
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return new_row

def upsert_row(db: Session, table_name: str, business_key_val: Any, updates: dict, source_name: str = "user", updated_by: str = "system"):
    """
    비즈니스 키를 기반으로 행을 찾아 업데이트하거나, 없으면 생성합니다.
    """
    # Agent D v12: 시스템 컬럼은 외부(Parser, API)에서 업데이트하지 못하도록 필터링
    system_cols = ["created_at", "updated_at", "row_id", "id", "updated_by"]
    updates = {k: v for k, v in updates.items() if k not in system_cols}
    
    row = get_row_by_business_key(db, table_name, business_key_val)
    is_new = False
    
    if not row:
        row = create_empty_row(db, table_name)
        is_new = True
        
    for col_name, val in updates.items():
        if col_name not in row.data:
            row.data[col_name] = {
                "value": None, "is_overwrite": False, "sources": {},
                "updated_by": "system", "priority_source": None
            }
        
        cell = row.data[col_name]
        old_val = cell.get("value")
        
        # 1. 소스 데이터 저장
        if "sources" not in cell: cell["sources"] = {}
        from datetime import datetime
        cell["sources"][source_name] = {
            "value": val,
            "timestamp": datetime.now().isoformat(),
            "updated_by": updated_by
        }
        
        # 2. 우선순위 기반 최종 값 결정
        new_final_val, top_src = compute_priority_value(cell["sources"], cell.get("manual_priority_source"))
        
        # 3. 값의 변화가 있거나 신규 행인 경우에만 감사 로그 기록 (무결성 규칙 준수)
        if is_new or (str(old_val) != str(new_final_val)):
            create_audit_log(db, table_name, row.row_id, col_name, old_val, new_final_val, source_name, updated_by)
        
        cell["value"] = new_final_val
        cell["priority_source"] = top_src
        cell["is_overwrite"] = ("user" in cell["sources"])
        cell["updated_by"] = updated_by
        
    flag_modified(row, "data")
    db.commit()
    db.refresh(row)
    return row, is_new

def upsert_rows_batch(db: Session, table_name: str, batch_items: list[schemas.CellUpsert]):
    """
    여러 개의 업서트 요청을 단일 트랜잭션으로 처리합니다.
    """
    from datetime import datetime
    results = []
    system_cols = ["created_at", "updated_at", "row_id", "id", "updated_by"]
    
    for item in batch_items:
        updates = {k: v for k, v in item.updates.items() if k not in system_cols}
        row = get_row_by_business_key(db, table_name, item.business_key_val)
        is_new = False
        
        if not row:
            new_row_id = str(uuid.uuid4())
            row = models.DataRow(
                row_id=new_row_id,
                table_name=table_name,
                data={}
            )
            db.add(row)
            is_new = True
            
        for col_name, val in updates.items():
            if col_name not in row.data:
                row.data[col_name] = {
                    "value": None, "is_overwrite": False, "sources": {},
                    "updated_by": "system", "priority_source": None
                }
            
            cell = row.data[col_name]
            old_val = cell.get("value")
            
            if "sources" not in cell: cell["sources"] = {}
            cell["sources"][item.source_name] = {
                "value": val,
                "timestamp": datetime.now().isoformat()
            }
            
            new_final_val, top_src = compute_priority_value(cell["sources"], cell.get("manual_priority_source"))
            
            # 변화가 있을 때만 감사 로그 기록
            if is_new or (str(old_val) != str(new_final_val)):
                create_audit_log(db, table_name, row.row_id, col_name, old_val, new_final_val, item.source_name, (item.updated_by or "system"))
            
            cell["value"] = new_final_val
            cell["priority_source"] = top_src
            cell["is_overwrite"] = ("user" in cell["sources"])
            cell["updated_by"] = (item.updated_by or "system")
            
        flag_modified(row, "data")
        results.append((row, is_new))
        
    db.commit()
    for row, _ in results:
        db.refresh(row)
    return results

def get_row_cell(db: Session, table_name: str, row_id: str, col_name: str):
    return db.query(models.DataRow).filter(
        models.DataRow.table_name == table_name,
        models.DataRow.row_id == row_id
    ).first()

def delete_cell_source(db: Session, table_name: str, row_id: str, col_name: str, source_name: str):
    row = get_row_cell(db, table_name, row_id, col_name)
    if not row or col_name not in row.data:
        return None
        
    cell = row.data[col_name]
    if "sources" in cell and source_name in cell["sources"]:
        del cell["sources"][source_name]
        
        # manual_priority_source가 삭제된 소스면 해제
        if cell.get("manual_priority_source") == source_name:
            cell["manual_priority_source"] = None
            
        # 값 재계산
        old_val = cell.get("value")
        final_val, top_src = compute_priority_value(cell["sources"], cell.get("manual_priority_source"))
        cell["value"] = final_val
        cell["priority_source"] = top_src
        cell["is_overwrite"] = ("user" in cell["sources"])
        
        # 감사 로그 기록
        create_audit_log(db, table_name, row_id, col_name, old_val, final_val, f"delete_source:{source_name}", "system")

        flag_modified(row, "data")
        db.commit()
        db.refresh(row)
        return row
    return None

def set_cell_manual_priority(db: Session, table_name: str, row_id: str, col_name: str, source_name: str | None, updated_by: str = "user"):
    row = get_row_cell(db, table_name, row_id, col_name)
    if not row or col_name not in row.data:
        return None
        
    cell = row.data[col_name]
    # source_name 이 None 이면 수동 우선순위 해제
    # source_name 이 존재하면 sources 에 있는지 확인
    if source_name and (source_name not in cell.get("sources", {})):
        return None
        
    cell["manual_priority_source"] = source_name
    
    # 값 재계산
    old_val = cell.get("value")
    final_val, top_src = compute_priority_value(cell["sources"], cell.get("manual_priority_source"))
    cell["value"] = final_val
    cell["priority_source"] = top_src
    cell["is_overwrite"] = (source_name == "user") or ("user" in cell.get("sources", {}))
    
    # 감사 로그 기록
    create_audit_log(db, table_name, row_id, col_name, old_val, final_val, f"set_priority:{source_name}", updated_by)

    flag_modified(row, "data")
    db.commit()
    db.refresh(row)
    return row
