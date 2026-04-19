from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import Any, Optional
from . import models, schemas
import uuid
import json
import os
from datetime import datetime

# 소스별 우선순위 정의 (숫자가 낮을수록 높음)
SOURCE_PRIORITY = {
    "user": 0,
    "parser_a": 1,
    "parser_b": 2,
    "batch_ingester": 3,
    "custom_script": 4
}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "table_config.json")

def sanitize_to_utf8(data: Any) -> Any:
    """
    데이터 객체(Dict, List, Str 등) 내부의 모든 문자열을 재귀적으로 탐색하여 
    비유효한 UTF-8 바이트 시퀀스를 제거/정정합니다.
    """
    if isinstance(data, dict):
        return {k: sanitize_to_utf8(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_to_utf8(v) for v in data]
    elif isinstance(data, str):
        # 비유효한 UTF-8 바이트를 무시(ignore)하고 다시 디코딩하여 깨끗한 문자열 생성
        return data.encode("utf-8", "ignore").decode("utf-8")
    else:
        return data

def load_table_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

TABLE_CONFIG = load_table_config()

def get_row_by_business_key(db: Session, table_name: str, key_value: Any):
    """테이블별 비즈니스 키를 기반으로 행을 조회합니다. (인덱스 컬럼 사용으로 최적화)"""
    target_val = str(key_value).strip() if key_value is not None else ""
    if not target_val:
        return None
        
    return db.query(models.DataRow).filter(
        models.DataRow.table_name == table_name,
        models.DataRow.business_key_val == target_val
    ).first()

def compute_priority_value(sources: dict, manual_priority_source: str = None):
    """여러 소스들 중 가장 우선순위가 높은 값을 결정합니다."""
    if not sources:
        return None, None
        
    if manual_priority_source and manual_priority_source in sources:
        val_data = sources[manual_priority_source]
        val = val_data["value"] if isinstance(val_data, dict) and "value" in val_data else val_data
        return val, manual_priority_source

    sorted_sources = sorted(
        sources.keys(),
        key=lambda k: SOURCE_PRIORITY.get(k, 99)
    )
    
    top_source = sorted_sources[0]
    val_data = sources[top_source]
    val = val_data["value"] if isinstance(val_data, dict) and "value" in val_data else val_data
    return val, top_source

def create_audit_log(db: Session, table_name: str, row_id: str, col_name: str, old_val: Any, new_val: Any, source: str, user: str):
    """감사 로그를 기록합니다. (저장 전 인코딩 정제 수행)"""
    log = models.AuditLog(
        table_name=table_name,
        row_id=row_id,
        column_name=col_name,
        old_value=sanitize_to_utf8(old_val),
        new_value=sanitize_to_utf8(new_val),
        source_name=source,
        updated_by=user
    )
    db.add(log)

def apply_row_update_internal(
    db: Session, 
    table_name: str, 
    update_item: schemas.GeneralUpdateItem,
    row_cache: dict = None
) -> tuple[models.DataRow, bool, list[str]]:
    """[통합 코어] row_id 또는 business_key 기반으로 행을 찾아 업데이트합니다."""
    system_cols = ["created_at", "updated_at", "row_id", "id", "updated_by"]
    
    row = None
    # 1. 캐시 소스에서 먼저 검색 (O(1))
    if row_cache:
        if update_item.row_id and update_item.row_id in row_cache:
            row = row_cache[update_item.row_id]
        elif update_item.business_key_val and update_item.business_key_val in row_cache:
            row = row_cache[update_item.business_key_val]

    # 2. 캐시에 없으면 DB 검색 (Fallback)
    if not row:
        if update_item.row_id:
            row = db.query(models.DataRow).filter(
                models.DataRow.table_name == table_name,
                models.DataRow.row_id == update_item.row_id
            ).first()
        
        if not row and update_item.business_key_val:
            row = get_row_by_business_key(db, table_name, update_item.business_key_val)
        
    is_new = False
    if not row:
        row = models.DataRow(
            row_id=update_item.row_id or str(uuid.uuid4()),
            table_name=table_name,
            data={}
        )
        db.add(row)
        is_new = True
        
    changed_cols = []
    for col_name, val in update_item.updates.items():
        if col_name in system_cols: continue
            
        if col_name not in row.data:
            row.data[col_name] = {"value": None, "is_overwrite": False, "sources": {}, "updated_by": "system", "priority_source": None}
            
        cell = row.data[col_name]
        old_val = cell.get("value")
        
        clean_val = sanitize_to_utf8(val)
        
        if "sources" not in cell: cell["sources"] = {}
        cell["sources"][update_item.source_name] = {
            "value": clean_val,
            "timestamp": datetime.now().isoformat(),
            "updated_by": update_item.updated_by
        }
        
        new_val, top_src = compute_priority_value(cell["sources"], cell.get("manual_priority_source"))
        
        if is_new or (str(old_val) != str(new_val)):
            changed_cols.append(col_name)
            create_audit_log(db, table_name, row.row_id, col_name, old_val, new_val, update_item.source_name, (update_item.updated_by or "system"))
            
        cell["value"] = new_val
        cell["priority_source"] = top_src
        cell["is_overwrite"] = ("user" in cell["sources"])
        cell["updated_by"] = (update_item.updated_by or "system")
        
    config = TABLE_CONFIG.get(table_name, {})
    key_col = config.get("business_key")
    if key_col and key_col in row.data:
        new_bk_val = row.data[key_col].get("value")
        if new_bk_val is not None:
            row.business_key_val = str(new_bk_val).strip()
            
    flag_modified(row, "data")
    return row, is_new, changed_cols

def apply_batch_updates(db: Session, table_name: str, batch: schemas.GeneralUpdateBatch):
    """통합 업데이트를 배치로 처리합니다."""
    # 1. [O(1) 최적화] 대상 행들을 한 번에 조회하여 캐시 구축 (Pre-fetch)
    target_ids = [u.row_id for u in batch.updates if u.row_id]
    target_bks = [str(u.business_key_val).strip() for u in batch.updates if u.business_key_val]
    
    from sqlalchemy import or_
    existing_rows_list = db.query(models.DataRow).filter(
        models.DataRow.table_name == table_name,
        or_(
            models.DataRow.row_id.in_(target_ids) if target_ids else False,
            models.DataRow.business_key_val.in_(target_bks) if target_bks else False
        )
    ).all()
    
    row_cache = {}
    for r in existing_rows_list:
        row_cache[r.row_id] = r
        if r.business_key_val:
            row_cache[r.business_key_val] = r

    unique_results = {} # row_id -> (row, is_new)
    total_changed_cells = [] # list of (row_id, col_name)
    
    for item in batch.updates:
        row, is_new, changed_cols = apply_row_update_internal(db, table_name, item, row_cache=row_cache)
        prev_row, prev_is_new = unique_results.get(row.row_id, (None, False))
        unique_results[row.row_id] = (row, is_new or prev_is_new)
        
        for col in changed_cols:
            total_changed_cells.append((row.row_id, col))
            
    db.commit()
    # [O(N) 제거] 개별 refresh()를 호출하지 않고 세션 상태를 활용하여 리턴
    results = list(unique_results.values())
    return results, total_changed_cells

def create_empty_row(db: Session, table_name: str):
    """신규 빈 행을 하나 생성합니다."""
    new_rows = create_empty_rows_batch(db, table_name, 1)
    return new_rows[0] if new_rows else None

def create_empty_rows_batch(db: Session, table_name: str, count: int, user_name: str = "system"):
    """신규 빈 행들을 일괄 생성하고 요약 히스토리를 남깁니다."""
    new_rows = []
    for _ in range(count):
        row = models.DataRow(
            row_id=str(uuid.uuid4()),
            table_name=table_name,
            data={}
        )
        new_rows.append(row)
    
    db.add_all(new_rows)
    
    if count > 0:
        summary_msg = f"{table_name} / {count}개의 새 행이 생성됨"
        create_audit_log(
            db, table_name, "_BATCH_", "CREATE",
            None, summary_msg, "system", user_name
        )
    
    db.commit()
    # [O(N) 제거] refresh() 루프를 제거하여 대량 생성 시 지연 방지
    return new_rows

    return False

def delete_row(db: Session, table_name: str, row_id: str, user_name: str = "system"):
    """단일 행을 삭제합니다 (배치 로직으로 통합)."""
    return delete_rows_batch(db, table_name, [row_id], user_name) > 0

def delete_rows_batch(db: Session, table_name: str, row_ids: list[str], user_name: str = "system"):
    """여러 행을 일괄 삭제하고 요약 히스토리를 남깁니다."""
    if not row_ids:
        return 0
        
    # [O(1) 최적화] 매 건마다 쿼리하는 대신 IN 연산자로 단숨에 삭제
    deleted_count = db.query(models.DataRow).filter(
        models.DataRow.table_name == table_name,
        models.DataRow.row_id.in_(row_ids)
    ).delete(synchronize_session=False)
            
    if deleted_count > 0:
        # 요약 히스토리 남기기
        summary_msg = f"{table_name} / {deleted_count}개의 행이 삭제됨"
        create_audit_log(
            db, table_name, "_BATCH_", "DELETE", 
            None, summary_msg, "system", user_name
        )
        db.commit()
    return deleted_count

def get_row_cell(db: Session, table_name: str, row_id: str):
    return db.query(models.DataRow).filter(models.DataRow.table_name == table_name, models.DataRow.row_id == row_id).first()

def delete_cell_source(db: Session, table_name: str, row_id: str, col_name: str, source_name: str):
    """특정 소스의 데이터를 삭제하고 값을 재계산합니다."""
    row = get_row_cell(db, table_name, row_id)
    if not row or col_name not in row.data: return None, []
    cell = row.data[col_name]
    if "sources" in cell and source_name in cell["sources"]:
        del cell["sources"][source_name]
        if cell.get("manual_priority_source") == source_name: cell["manual_priority_source"] = None
        old_val = cell.get("value")
        new_val, top_src = compute_priority_value(cell["sources"], cell.get("manual_priority_source"))
        cell["value"] = new_val
        cell["priority_source"] = top_src
        cell["is_overwrite"] = ("user" in cell["sources"])
        
        changed_cols = []
        if str(old_val) != str(new_val):
            changed_cols = [col_name]
            create_audit_log(db, table_name, row_id, col_name, old_val, new_val, f"delete_source:{source_name}", "system")
        
        flag_modified(row, "data")
        db.commit()
        db.refresh(row)
        return row, changed_cols
    return None, []

def set_cell_manual_priority(db: Session, table_name: str, row_id: str, col_name: str, source_name: Optional[str], updated_by: str = "user"):
    """수동 소스 우선순위(Pin)를 설정합니다."""
    row = get_row_cell(db, table_name, row_id)
    if not row or col_name not in row.data: return None, []
    cell = row.data[col_name]
    if source_name and (source_name not in cell.get("sources", {})): return None, []
    cell["manual_priority_source"] = source_name
    old_val = cell.get("value")
    new_val, top_src = compute_priority_value(cell["sources"], cell.get("manual_priority_source"))
    cell["value"] = new_val
    cell["priority_source"] = top_src
    cell["is_overwrite"] = (source_name == "user") or ("user" in cell.get("sources", {}))
    
    changed_cols = []
    if str(old_val) != str(new_val):
        changed_cols = [col_name]
        create_audit_log(db, table_name, row_id, col_name, old_val, new_val, f"set_priority:{source_name}", updated_by)
    
    flag_modified(row, "data")
    db.commit()
    db.refresh(row)
    return row, changed_cols
