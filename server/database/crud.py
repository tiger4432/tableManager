from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import Any, Optional
from . import models, schemas
from contextlib import contextmanager

@contextmanager
def transaction_context(user: str, tx_id: str, source: str):
    from database.context import request_user, request_transaction_id, request_source
    token_user = request_user.set(user)
    token_tx = request_transaction_id.set(tx_id)
    token_src = request_source.set(source)
    try:
        yield
    finally:
        request_user.reset(token_user)
        request_transaction_id.reset(token_tx)
        request_source.reset(token_src)
import uuid
import uuid6
import json
import os
from datetime import datetime

class LightCellSource:
    __slots__ = ('table_name', 'row_id', 'column_name', 'source_name', 'value', 'updated_by', 'ingested_at')
    def __init__(self, table_name, row_id, column_name, source_name, value, updated_by, ingested_at):
        self.table_name = table_name
        self.row_id = row_id
        self.column_name = column_name
        self.source_name = source_name
        self.value = value
        self.updated_by = updated_by
        self.ingested_at = ingested_at

class LightCellOverwrite:
    __slots__ = ('table_name', 'row_id', 'column_name', 'is_overwrite', 'updated_by', 'updated_at', 'manual_priority_source')
    def __init__(self, table_name, row_id, column_name, is_overwrite, updated_by, updated_at, manual_priority_source):
        self.table_name = table_name
        self.row_id = row_id
        self.column_name = column_name
        self.is_overwrite = is_overwrite
        self.updated_by = updated_by
        self.updated_at = updated_at
        self.manual_priority_source = manual_priority_source

# 소스별 우선순위 정의 (숫자가 낮을수록 높음)
SOURCE_PRIORITY = {
    "user": 0,
    "collision_merge": 1,
    "pipeline_parser": 2,
    "custom_script": 3
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

def update_table_config(new_config: dict):
    """테이블 설정을 갱신하고 디스크에 저장합니다."""
    global TABLE_CONFIG
    TABLE_CONFIG.update(new_config)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(TABLE_CONFIG, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[crud] Failed to save table config: {e}")

import sys
if not hasattr(sys, "_table_config_singleton"):
    sys._table_config_singleton = load_table_config()
TABLE_CONFIG = sys._table_config_singleton


def cast_value_by_type(value: Any, col_type: str, col_name: str) -> Any:
    """컬럼의 타입 스펙에 맞춰 데이터를 int, float 등으로 명시적으로 형변환합니다."""
    if value is None or str(value).strip() == "":
        return None
        
    if col_type == "number":
        val_str = str(value).strip()
        try:
            if "." in val_str:
                return float(val_str)
            else:
                return int(val_str)
        except ValueError:
            raise ValueError(f"컬럼 '{col_name}'의 값 '{value}'은(는) 올바른 숫자 형식이 아닙니다.")
            
    return sanitize_to_utf8(value)

def clean_str_value(val: Any) -> str:
    """값을 깔끔하게 문자열로 변환합니다. float인 경우 소수점 이하가 .0이면 정수로 처리합니다."""
    if val is None:
        return ""
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return str(val)
    return str(val).strip()

def get_row_by_business_key(db: Session, table_name: str, key_value: Any):
    """테이블별 비즈니스 키를 기반으로 행을 조회합니다. (인덱스 컬럼 사용으로 최적화)"""
    target_val = str(key_value).strip() if key_value is not None else ""
    if not target_val:
        return None
        
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        return None
        
    return db.query(table_model).filter(
        table_model.business_key_val == target_val
    ).first()

def compute_priority_value(sources: dict, manual_priority_source: str = None, table_name: str = None):
    """여러 소스들 중 가장 우선순위가 높은 값을 결정합니다."""
    if not sources:
        return None, None
        
    if manual_priority_source and manual_priority_source in sources:
        val_data = sources[manual_priority_source]
        val = val_data["value"] if isinstance(val_data, dict) and "value" in val_data else val_data
        return val, manual_priority_source

    priority_map = SOURCE_PRIORITY
    if table_name:
        table_info = TABLE_CONFIG.get(table_name, {})
        custom_priority = table_info.get("source_priority")
        if custom_priority and isinstance(custom_priority, dict):
            priority_map = custom_priority

    sorted_sources = sorted(
        sources.keys(),
        key=lambda k: priority_map.get(k, 99)
    )
    
    top_source = sorted_sources[0]
    val_data = sources[top_source]
    val = val_data["value"] if isinstance(val_data, dict) and "value" in val_data else val_data
    return val, top_source

def create_audit_log(db: Session, table_name: str, row_id: str, col_name: str, old_val: Any, new_val: Any, source: str, user: str, transaction_id: str = None, business_key: str = None, add_to_cache: bool = True):
    """감사 로그를 기록합니다. (저장 전 인코딩 정제 수행)"""
    if not transaction_id:
        transaction_id = str(uuid6.uuid7())

    # ID와 Timestamp는 DB 커밋 시점에 생성되지만, 캐싱을 위해 파이썬 레벨에서 타임스탬프를 명시적으로 주입합니다.
    from datetime import timezone
    ts = datetime.now(timezone.utc)
    
    log = models.AuditLog(
        table_name=table_name,
        row_id=row_id,
        column_name=col_name,
        old_value=sanitize_to_utf8(old_val),
        new_value=sanitize_to_utf8(new_val),
        source_name=source,
        updated_by=user,
        transaction_id=transaction_id,
        timestamp=ts,
        business_key=business_key
    )
    db.add(log)

    log_dict = {
        "id": 0,
        "table_name": table_name,
        "row_id": row_id,
        "column_name": col_name,
        "old_value": log.old_value,
        "new_value": log.new_value,
        "source_name": source,
        "updated_by": user,
        "transaction_id": transaction_id,
        "business_key": business_key,
        "timestamp": ts
    }
    if add_to_cache:
        # 인메모리 캐시에 즉시 반영 (ID는 클라이언트 뷰에서 사용되지 않으므로 0으로 임시 매핑)
        from audit_cache import audit_cache
        audit_cache.add_log(log_dict)
        
    return log_dict

def bulk_upsert_cell_sources(db: Session, mappings: list[dict]):
    if not mappings:
        return
    
    # Deduplicate mappings to avoid psycopg2.errors.CardinalityViolation in PostgreSQL.
    # Keep the last (most recent) dictionary for each unique constraint key.
    deduped = {}
    for item in mappings:
        key = (item['table_name'], item['row_id'], item['column_name'], item['source_name'])
        deduped[key] = item
    
    # Sort deterministically by key to prevent Deadlocks in PostgreSQL.
    sorted_keys = sorted(deduped.keys())
    deduped_mappings = [deduped[k] for k in sorted_keys]
    
    is_sqlite = db.bind.dialect.name == "sqlite"
    if is_sqlite:
        from sqlalchemy.dialects.sqlite import insert as upsert_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as upsert_insert
        
    stmt = upsert_insert(models.CellSource).values(deduped_mappings)
    stmt = stmt.on_conflict_do_update(
        index_elements=['table_name', 'row_id', 'column_name', 'source_name'],
        set_={
            'value': stmt.excluded.value,
            'updated_by': stmt.excluded.updated_by,
            'ingested_at': stmt.excluded.ingested_at
        }
    )
    db.execute(stmt)

def bulk_upsert_cell_overwrites(db: Session, mappings: list[dict]):
    if not mappings:
        return
    
    # Deduplicate mappings to avoid psycopg2.errors.CardinalityViolation in PostgreSQL.
    # Keep the last (most recent) dictionary for each unique constraint key.
    deduped = {}
    for item in mappings:
        key = (item['table_name'], item['row_id'], item['column_name'])
        deduped[key] = item
    
    # Sort deterministically by key to prevent Deadlocks in PostgreSQL.
    sorted_keys = sorted(deduped.keys())
    deduped_mappings = [deduped[k] for k in sorted_keys]
    
    is_sqlite = db.bind.dialect.name == "sqlite"
    if is_sqlite:
        from sqlalchemy.dialects.sqlite import insert as upsert_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as upsert_insert
        
    stmt = upsert_insert(models.CellOverwrite).values(deduped_mappings)
    stmt = stmt.on_conflict_do_update(
        index_elements=['table_name', 'row_id', 'column_name'],
        set_={
            'is_overwrite': stmt.excluded.is_overwrite,
            'updated_by': stmt.excluded.updated_by,
            'updated_at': stmt.excluded.updated_at,
            'manual_priority_source': stmt.excluded.manual_priority_source
        }
    )
    db.execute(stmt)

def bulk_delete_cell_overwrites(db: Session, delete_keys: list[tuple[str, str, str]]):
    if not delete_keys:
        return
        
    from sqlalchemy import and_, or_
    conds = []
    for t_name, r_id, col_name in delete_keys:
        conds.append(
            and_(
                models.CellOverwrite.table_name == t_name,
                models.CellOverwrite.row_id == r_id,
                models.CellOverwrite.column_name == col_name
            )
        )
    db.query(models.CellOverwrite).filter(or_(*conds)).delete(synchronize_session=False)

def _get_or_create_row(db: Session, table_model: Any, update_item: schemas.GeneralUpdateItem, row_cache: dict, table_name: str) -> tuple[Any, bool]:
    """대상 행 객체를 캐시 또는 DB에서 획득하고, 존재하지 않으면 신규 생성합니다."""
    row = None
    if row_cache is not None:
        if update_item.row_id and update_item.row_id in row_cache:
            row = row_cache[update_item.row_id]
        elif update_item.business_key_val and update_item.business_key_val in row_cache:
            row = row_cache[update_item.business_key_val]
            
    if not row:
        if update_item.row_id:
            row = db.query(table_model).filter(table_model.row_id == update_item.row_id).first()
        if not row and update_item.business_key_val:
            row = get_row_by_business_key(db, table_name, update_item.business_key_val)
            
        if row and row_cache is not None:
            row_cache[row.row_id] = row
            if row.business_key_val:
                row_cache[row.business_key_val] = row
    
    is_new = False
    if not row:
        from sqlalchemy.sql import func
        row = table_model(
            row_id=update_item.row_id or str(uuid6.uuid7()),
            updated_at=func.now()
        )
        db.add(row)
        is_new = True
        if row_cache is not None:
            row_cache[row.row_id] = row
            if row.business_key_val:
                row_cache[row.business_key_val] = row
            
    return row, is_new

def _update_row_business_key(row: Any, key_col: str, update_item: schemas.GeneralUpdateItem, row_cache: dict):
    """비즈니스 키가 업데이트 항목에 있거나 기존 행에 존재하면 DYNAMIC 테이블의 business_key_val 필드를 최신화합니다."""
    if key_col and key_col in update_item.updates:
        new_bk_val = update_item.updates[key_col]
        if new_bk_val is not None:
            str_val = str(new_bk_val).strip()
            if row.business_key_val != str_val:
                row.business_key_val = str_val
                if row_cache is not None:
                    row_cache[str_val] = row
    elif key_col and hasattr(row, key_col):
        existing_val = getattr(row, key_col)
        new_bk_val = existing_val.get("value") if isinstance(existing_val, dict) else existing_val
        if new_bk_val is not None:
            str_val = str(new_bk_val).strip()
            if row.business_key_val != str_val:
                row.business_key_val = str_val
                if row_cache is not None:
                    row_cache[str_val] = row

def _load_metadata_row_cell(db: Session, table_name: str, row_id: str, col_name: str, is_new: bool, sources_cache: dict, overwrites_cache: dict, cell_sources_to_upsert: dict, cell_overwrites_to_upsert: dict) -> tuple[list, Any]:
    """해당 셀의 CellSource 리스트와 CellOverwrite 객체를 캐시 혹은 DB로부터 획득합니다."""
    key = (row_id, col_name)
    
    # CellSource 로드
    if sources_cache is not None:
        col_srcs = sources_cache.get(key, [])
        if key not in sources_cache:
            sources_cache[key] = col_srcs
    else:
        if is_new:
            col_srcs = []
        else:
            col_srcs = db.query(models.CellSource).filter(
                models.CellSource.table_name == table_name,
                models.CellSource.row_id == row_id,
                models.CellSource.column_name == col_name
            ).all()
            if cell_sources_to_upsert is not None:
                for s in col_srcs:
                    db.expunge(s)
            
    # CellOverwrite 로드
    if overwrites_cache is not None:
        ow = overwrites_cache.get(key)
        if key not in overwrites_cache:
            overwrites_cache[key] = ow
    else:
        if is_new:
            ow = None
        else:
            ow = db.query(models.CellOverwrite).filter(
                models.CellOverwrite.table_name == table_name,
                models.CellOverwrite.row_id == row_id,
                models.CellOverwrite.column_name == col_name
            ).first()
            if ow and cell_overwrites_to_upsert is not None:
                db.expunge(ow)
            
    return col_srcs, ow

def apply_row_update_internal(
    db: Session, 
    table_name: str, 
    update_item: schemas.GeneralUpdateItem,
    row_cache: dict = None,
    sources_cache: dict = None,
    overwrites_cache: dict = None,
    transaction_id: str = None,
    logs_to_cache: list = None,
    cell_sources_to_upsert: dict = None,
    cell_overwrites_to_upsert: dict = None,
    cell_overwrites_to_delete: set = None,
    deleted_row_ids: list = None
) -> tuple[Any, bool, list[str]]:
    """[통합 코어] row_id 또는 business_key 기반으로 행을 찾아 업데이트하고 메타데이터 테이블을 갱신합니다."""
    system_cols = ["created_at", "updated_at", "row_id", "id", "updated_by"]
    
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        raise ValueError(f"Table model for '{table_name}' is not initialized. Please define the table in config/table_config.json and restart the server/watcher processes.")
    config = TABLE_CONFIG.get(table_name, {})
    key_col = config.get("business_key")
    composite_src = config.get("composite_key_source")
    composite_sep = config.get("composite_key_separator", "_")

    # 인제션 매칭을 위해 updates 기반 선제 키 조립
    if not update_item.row_id and not update_item.business_key_val and composite_src and key_col:
        has_all_srcs = all(col in update_item.updates for col in composite_src)
        if has_all_srcs:
            vals = [clean_str_value(update_item.updates.get(col)) for col in composite_src]
            if all(v != "" for v in vals):
                computed_key = composite_sep.join(vals)
                update_item.business_key_val = computed_key
                if key_col not in update_item.updates:
                    update_item.updates[key_col] = computed_key

    row, is_new = _get_or_create_row(db, table_model, update_item, row_cache, table_name)
    changed_cols = []
    config = TABLE_CONFIG.get(table_name, {})
    key_col = config.get("business_key")
    
    # Update business key first
    _update_row_business_key(row, key_col, update_item, row_cache)

    # Old values snapshot for auditing
    old_values_snapshot = {}
    for col_name in update_item.updates.keys():
        if col_name in system_cols: continue
        old_values_snapshot[col_name] = getattr(row, col_name, None)

    for col_name, val in update_item.updates.items():
        if col_name in system_cols: continue
            
        col_types = config.get("column_types", {})
        if col_name not in col_types:
            continue
            
        key = (row.row_id, col_name)
        col_srcs, ow = _load_metadata_row_cell(db, table_name, row.row_id, col_name, is_new, sources_cache, overwrites_cache, cell_sources_to_upsert, cell_overwrites_to_upsert)

        # 3. 소스 데이터 upsert
        col_type = col_types.get(col_name, "string")
        clean_val = cast_value_by_type(val, col_type, col_name)
        
        src_obj = next((s for s in col_srcs if s.source_name == update_item.source_name), None)
        if not src_obj:
            src_obj = models.CellSource(
                table_name=table_name,
                row_id=row.row_id,
                column_name=col_name,
                source_name=update_item.source_name
            )
            if cell_sources_to_upsert is None:
                db.add(src_obj)
            col_srcs.append(src_obj)
            
        src_obj.value = clean_val
        src_obj.updated_by = update_item.updated_by
        src_obj.ingested_at = datetime.now()

        if cell_sources_to_upsert is not None:
            upsert_key = (table_name, row.row_id, col_name, update_item.source_name)
            cell_sources_to_upsert[upsert_key] = {
                "table_name": table_name,
                "row_id": row.row_id,
                "column_name": col_name,
                "source_name": update_item.source_name,
                "value": clean_val,
                "updated_by": update_item.updated_by,
                "ingested_at": src_obj.ingested_at
            }

        # 4. 우선순위 결정
        sources_dict = {}
        for s in col_srcs:
            sources_dict[s.source_name] = {
                "value": s.value,
                "timestamp": s.ingested_at.isoformat() if s.ingested_at else datetime.now().isoformat(),
                "updated_by": s.updated_by
            }
            
        manual_pin = ow.manual_priority_source if ow else None
        if update_item.source_name == "user":
            manual_pin = None # 수동 값 입력 시 핀 초기화
            
        new_val, top_src = compute_priority_value(sources_dict, manual_pin, table_name)
        old_val = old_values_snapshot.get(col_name)
        
        # 6. cell_overwrites 마킹
        is_overwrite = ("user" in sources_dict) or (manual_pin is not None)
        if is_overwrite:
            if not ow:
                ow = models.CellOverwrite(
                    table_name=table_name,
                    row_id=row.row_id,
                    column_name=col_name
                )
                if cell_overwrites_to_upsert is None:
                    db.add(ow)
                if overwrites_cache is not None:
                    overwrites_cache[key] = ow
            ow.is_overwrite = True
            ow.updated_by = update_item.updated_by or "system"
            ow.updated_at = datetime.now()
            ow.manual_priority_source = manual_pin
            
            if cell_overwrites_to_upsert is not None:
                ow_key = (table_name, row.row_id, col_name)
                cell_overwrites_to_upsert[ow_key] = {
                    "table_name": table_name,
                    "row_id": row.row_id,
                    "column_name": col_name,
                    "is_overwrite": True,
                    "updated_by": ow.updated_by,
                    "updated_at": ow.updated_at,
                    "manual_priority_source": ow.manual_priority_source
                }
                if cell_overwrites_to_delete is not None:
                    cell_overwrites_to_delete.discard(ow_key)
        else:
            if ow:
                ow_key = (table_name, row.row_id, col_name)
                if cell_overwrites_to_delete is not None:
                    cell_overwrites_to_delete.add(ow_key)
                    if cell_overwrites_to_upsert is not None:
                        cell_overwrites_to_upsert.pop(ow_key, None)
                else:
                    db.delete(ow)
                if overwrites_cache is not None:
                    overwrites_cache[key] = None

        has_changed = False
        if is_new:
            has_changed = True
        else:
            if old_val is None and new_val is None:
                has_changed = False
            elif (old_val is None) != (new_val is None):
                has_changed = True
            elif col_type == "number":
                try:
                    has_changed = float(old_val) != float(new_val)
                except (ValueError, TypeError):
                    has_changed = str(old_val).strip() != str(new_val).strip()
            else:
                has_changed = str(old_val).strip() != str(new_val).strip()

        if has_changed:
            setattr(row, col_name, new_val)
            changed_cols.append(col_name)
            if update_item.source_name == "user":
                log_dict = create_audit_log(
                    db, table_name, row.row_id, col_name, old_val, new_val, 
                    update_item.source_name, (update_item.updated_by or "user"), 
                    transaction_id=transaction_id, business_key=row.business_key_val,
                    add_to_cache=(logs_to_cache is None)
                )
                if logs_to_cache is not None:
                    logs_to_cache.append(log_dict)

    if changed_cols and update_item.source_name != "user":
        new_summary_parts = []
        for col in changed_cols:
            new_val = getattr(row, col, None)
            new_val_str = "비어있음" if new_val is None else str(new_val)
            new_summary_parts.append(f"{col}: {new_val_str}")
            
        if is_new:
            old_summary = None
            summary_msg = "신규 데이터 생성: " + ", ".join(new_summary_parts)
        else:
            old_summary_parts = []
            for col in changed_cols:
                old_val = old_values_snapshot.get(col)
                old_val_str = "비어있음" if old_val is None else str(old_val)
                old_summary_parts.append(f"{col}: {old_val_str}")
            old_summary = ", ".join(old_summary_parts)
            summary_msg = ", ".join(new_summary_parts)
            
        log_dict = create_audit_log(
            db, table_name, row.row_id, "ROW_UPDATE",
            old_summary, summary_msg, update_item.source_name,
            (update_item.updated_by or "system"),
            transaction_id=transaction_id,
            business_key=row.business_key_val,
            add_to_cache=(logs_to_cache is None)
        )
        if logs_to_cache is not None:
            logs_to_cache.append(log_dict)
    # 2. 복합 비즈니스 키 실시간 재계산 및 동기화, 유일성 검사
    if composite_src and key_col:
        is_src_changed = any(col in changed_cols for col in composite_src)
        if is_src_changed or is_new:
            vals = [clean_str_value(getattr(row, col, None)) for col in composite_src]
            if all(v != "" for v in vals):
                new_bk_val = composite_sep.join(vals)
            else:
                # 조합 소스 컬럼들이 누락되었으나 신규 생성 시 business_key_val이 유효하게 주어져 있다면 폴백 사용
                new_bk_val = update_item.business_key_val if (is_new and update_item.business_key_val) else None

            current_bk = getattr(row, "business_key_val", None)
            if current_bk != new_bk_val:
                if new_bk_val is not None:
                    conflict_row = db.query(table_model).filter(
                        table_model.business_key_val == new_bk_val,
                        table_model.row_id != row.row_id
                    ).first()
                    if conflict_row:
                        # -------------------------------------------------------------
                        # [대안 B: Silent Merge & Overwrite]
                        # -------------------------------------------------------------
                        # 1. 중복되어 버려질 임시 껍데기 행 기록
                        row_to_delete = row
                        
                        # 2. 가공 대상 행을 기존 존재하던 충돌 행으로 스위칭
                        row = conflict_row
                        is_new = False
                        
                        # 3. 임시 행(row_to_delete)에 채워진 모든 실제 값을 충돌 행(row)에 덮어쓰기 병합
                        columns_to_merge = [c.name for c in table_model.__table__.columns]
                        for col_name in columns_to_merge:
                            if col_name in [key_col, "row_id", "business_key_val", "created_at", "updated_at"]:
                                continue
                            
                            is_explicitly_edited = (col_name in update_item.updates)
                            
                            # [병합 보호 정책] 충돌 행(row)에 이미 사용자 수정(user)이나 핀이 들어있고, 이번에 직접 수정하는 셀이 아니면 기존 값 보존
                            old_ow = overwrites_cache.get((row.row_id, col_name)) if overwrites_cache else None
                            if not old_ow:
                                old_ow = db.query(models.CellOverwrite).filter(
                                    models.CellOverwrite.table_name == table_name,
                                    models.CellOverwrite.row_id == row.row_id,
                                    models.CellOverwrite.column_name == col_name
                                ).first()
                                
                            is_old_user_overwritten = False
                            if old_ow:
                                is_old_user_overwritten = old_ow.is_overwrite or (old_ow.manual_priority_source is not None)
                                
                            if is_old_user_overwritten and not is_explicitly_edited:
                                continue

                            new_val = getattr(row_to_delete, col_name, None)
                            
                            # update_item.updates에도 명시적으로 새로 기입된 값이 있으면 그 값을 우선적으로 선정
                            if col_name in update_item.updates:
                                new_val = update_item.updates[col_name]
                                
                            old_val = getattr(row, col_name, None)
                            
                            has_cell_changed = False
                            if new_val is not None:
                                if old_val is None:
                                    has_cell_changed = True
                                else:
                                    has_cell_changed = str(old_val).strip() != str(new_val).strip()
                                
                            if has_cell_changed:
                                setattr(row, col_name, new_val)
                                if col_name not in changed_cols:
                                    changed_cols.append(col_name)
                                    
                                # 중복키 충돌 병합을 어드민 원천 관리 패널에서 추적 가능하도록 원래의 진짜 소스명 보존하여 적재
                                if cell_sources_to_upsert is not None:
                                    from sqlalchemy.sql import func
                                    # 껍데기 행이 원래 가졌던 소스 명칭 추적 계승
                                    old_srcs, _ = _load_metadata_row_cell(
                                        db, table_name, row_to_delete.row_id, col_name,
                                        is_new=False,
                                        sources_cache=sources_cache,
                                        overwrites_cache=overwrites_cache,
                                        cell_sources_to_upsert=cell_sources_to_upsert,
                                        cell_overwrites_to_upsert=cell_overwrites_to_upsert
                                    )
                                    effective_src_name = None
                                    if old_srcs:
                                        effective_src_name = old_srcs[0].source_name
                                    if not effective_src_name:
                                        effective_src_name = update_item.source_name or "user"

                                    src_key = (table_name, row.row_id, col_name, effective_src_name)
                                    cell_sources_to_upsert[src_key] = {
                                        "table_name": table_name,
                                        "row_id": row.row_id,
                                        "column_name": col_name,
                                        "source_name": effective_src_name,
                                        "value": clean_str_value(new_val),
                                        "updated_by": update_item.updated_by or "system",
                                        "ingested_at": func.now()
                                    }
                                    
                                # 중복키 충돌 병합이 발생했음을 가벼운 Overwrite 테이블에도 기록하여 그리드 성능 최적화 지원
                                if cell_overwrites_to_upsert is not None:
                                    from sqlalchemy.sql import func
                                    ow_key = (table_name, row.row_id, col_name)
                                    cell_overwrites_to_upsert[ow_key] = {
                                        "table_name": table_name,
                                        "row_id": row.row_id,
                                        "column_name": col_name,
                                        "is_overwrite": True,
                                        "updated_by": "collision_merge",
                                        "updated_at": func.now(),
                                        "manual_priority_source": "collision_merge"
                                    }
                                    if cell_overwrites_to_delete is not None:
                                        cell_overwrites_to_delete.discard(ow_key)
                                    
                                # AuditLog 기록
                                create_audit_log(
                                    db, table_name, row.row_id, col_name, old_val, new_val,
                                    "collision_merge", (update_item.updated_by or "system"),
                                    transaction_id=transaction_id, business_key=row.business_key_val,
                                    add_to_cache=(logs_to_cache is None)
                                )

                        # 4. 캐시 맵 마이그레이션 (row_to_delete.row_id ➡️ conflict_row.row_id)
                        if cell_sources_to_upsert is not None:
                            keys_to_migrate = [k for k in cell_sources_to_upsert.keys() if k[1] == row_to_delete.row_id]
                            for k in keys_to_migrate:
                                src_data = cell_sources_to_upsert.pop(k)
                                new_k = (k[0], row.row_id, k[2], k[3])
                                src_data["row_id"] = row.row_id
                                cell_sources_to_upsert[new_k] = src_data
                                
                        if cell_overwrites_to_upsert is not None:
                            keys_to_migrate = [k for k in cell_overwrites_to_upsert.keys() if k[1] == row_to_delete.row_id]
                            for k in keys_to_migrate:
                                ow_data = cell_overwrites_to_upsert.pop(k)
                                new_k = (k[0], row.row_id, k[2])
                                ow_data["row_id"] = row.row_id
                                cell_overwrites_to_upsert[new_k] = ow_data
                                
                        if cell_overwrites_to_delete is not None:
                            keys_to_migrate = [k for k in cell_overwrites_to_delete if k[1] == row_to_delete.row_id]
                            for k in keys_to_migrate:
                                cell_overwrites_to_delete.discard(k)
                                cell_overwrites_to_delete.add((k[0], row.row_id, k[2]))
                                
                        if logs_to_cache is not None:
                            for log in logs_to_cache:
                                if log.get("row_id") == row_to_delete.row_id:
                                    log["row_id"] = row.row_id
                                    
                        for obj in db.new:
                            if isinstance(obj, models.AuditLog) and obj.row_id == row_to_delete.row_id:
                                obj.row_id = row.row_id

                        # 5. 무의미한 껍데기 행을 DB 세션 및 메모리 캐시에서 완전 소거
                        try:
                            db.delete(row_to_delete)
                            if deleted_row_ids is not None:
                                deleted_row_ids.append(row_to_delete.row_id)
                        except Exception:
                            pass
                        if row_cache is not None:
                            row_cache.pop(row_to_delete.row_id, None)
                            if row_to_delete.business_key_val:
                                row_cache.pop(row_to_delete.business_key_val, None)

                old_bk_col_val = getattr(row, key_col, None)
                
                row.business_key_val = new_bk_val
                if row_cache is not None:
                    if current_bk in row_cache and row_cache[current_bk] == row:
                        del row_cache[current_bk]
                    if new_bk_val is not None:
                        row_cache[new_bk_val] = row

                setattr(row, key_col, new_bk_val)
                
                if old_bk_col_val != new_bk_val:
                    changed_cols.append(key_col)
                    if update_item.source_name == "user":
                        log_dict = create_audit_log(
                            db, table_name, row.row_id, key_col, old_bk_col_val, new_bk_val, 
                            update_item.source_name, (update_item.updated_by or "user"), 
                            transaction_id=transaction_id, business_key=row.business_key_val,
                            add_to_cache=(logs_to_cache is None)
                        )
                        if logs_to_cache is not None:
                            logs_to_cache.append(log_dict)

    if changed_cols or is_new:
        from sqlalchemy.sql import func
        row.updated_at = func.now()

    return row, is_new, changed_cols


def apply_batch_updates(db: Session, table_name: str, batch: schemas.GeneralUpdateBatch):
    """통합 업데이트를 배치로 처리합니다."""
    tx_id = batch.transaction_id or str(uuid6.uuid7())
    
    user_val = batch.updates[0].updated_by if batch.updates else "system"
    source_val = batch.updates[0].source_name if batch.updates else "batch"
    
    with transaction_context(user_val, tx_id, source_val):
        table_model = models.DYNAMIC_TABLES.get(table_name)
        if not table_model:
            raise ValueError(f"Table model for '{table_name}' is not initialized. Please define the table in config/table_config.json and restart the server/watcher processes.")
            
        target_ids = [u.row_id for u in batch.updates if u.row_id]
        target_bks = [str(u.business_key_val).strip() for u in batch.updates if u.business_key_val]

        from sqlalchemy import or_
        existing_rows_list = db.query(table_model).filter(
            or_(
                table_model.row_id.in_(target_ids) if target_ids else False,
                table_model.business_key_val.in_(target_bks) if target_bks else False
            )
        ).all()
        
        row_cache = {}
        for r in existing_rows_list:
            row_cache[r.row_id] = r
            if r.business_key_val:
                row_cache[r.business_key_val] = r
                
        all_row_ids = list(set(r.row_id for r in existing_rows_list))
        
        sources_cache = {}
        overwrites_cache = {}
        
        if all_row_ids:
            all_sources = db.query(
                models.CellSource.table_name,
                models.CellSource.row_id,
                models.CellSource.column_name,
                models.CellSource.source_name,
                models.CellSource.value,
                models.CellSource.updated_by,
                models.CellSource.ingested_at
            ).filter(
                models.CellSource.table_name == table_name,
                models.CellSource.row_id.in_(all_row_ids)
            ).all()
            for t_name, r_id, col_name, src_name, val, upd_by, ing_at in all_sources:
                key = (r_id, col_name)
                if key not in sources_cache:
                    sources_cache[key] = []
                sources_cache[key].append(LightCellSource(t_name, r_id, col_name, src_name, val, upd_by, ing_at))
                
            all_overwrites = db.query(
                models.CellOverwrite.table_name,
                models.CellOverwrite.row_id,
                models.CellOverwrite.column_name,
                models.CellOverwrite.is_overwrite,
                models.CellOverwrite.updated_by,
                models.CellOverwrite.updated_at,
                models.CellOverwrite.manual_priority_source
            ).filter(
                models.CellOverwrite.table_name == table_name,
                models.CellOverwrite.row_id.in_(all_row_ids)
            ).all()
            for t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin in all_overwrites:
                overwrites_cache[(r_id, col_name)] = LightCellOverwrite(t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin)
    
        unique_results = {}
        total_changed_cells = []
        logs_to_cache = []
        
        # Batch containers for bulk operations (deduplicated early via dict/set)
        cell_sources_to_upsert = {}
        cell_overwrites_to_upsert = {}
        cell_overwrites_to_delete = set()
        deleted_row_ids = []
        
        with db.no_autoflush:
            for item in batch.updates:
                row, is_new, changed_cols = apply_row_update_internal(
                    db, table_name, item, 
                    row_cache=row_cache, 
                    sources_cache=sources_cache,
                    overwrites_cache=overwrites_cache,
                    transaction_id=tx_id, 
                    logs_to_cache=logs_to_cache,
                    cell_sources_to_upsert=cell_sources_to_upsert,
                    cell_overwrites_to_upsert=cell_overwrites_to_upsert,
                    cell_overwrites_to_delete=cell_overwrites_to_delete,
                    deleted_row_ids=deleted_row_ids
                )
                prev_row, prev_is_new = unique_results.get(row.row_id, (None, False))
                unique_results[row.row_id] = (row, is_new or prev_is_new)
                
                for col in changed_cols:
                    total_changed_cells.append((row.row_id, col))
                    
        # Capture newly created AuditLog objects before commit/flush
        created_log_objs = [obj for obj in db.new if isinstance(obj, models.AuditLog)]
        
        # Execute Bulk Upserts and Deletes
        bulk_upsert_cell_sources(db, list(cell_sources_to_upsert.values()))
        bulk_upsert_cell_overwrites(db, list(cell_overwrites_to_upsert.values()))
        bulk_delete_cell_overwrites(db, list(cell_overwrites_to_delete))
        
        db.flush()
        
        serialized_logs = []
        for log in created_log_objs:
            serialized_logs.append({
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
            
        db.commit()
        
        if logs_to_cache:
            from audit_cache import audit_cache
            audit_cache.add_logs_batch(logs_to_cache)
            
        results = list(unique_results.values())
        return results, total_changed_cells, serialized_logs, deleted_row_ids

def create_empty_row(db: Session, table_name: str):
    """신규 빈 행을 하나 생성합니다."""
    new_rows = create_empty_rows_batch(db, table_name, 1)
    return new_rows[0] if new_rows else None

def create_empty_rows_batch(db: Session, table_name: str, count: int, user_name: str = "system"):
    """신규 빈 행을 일괄 생성하고 요약 히스토리를 남깁니다."""
    from sqlalchemy.sql import func
    
    tx_id = str(uuid6.uuid7())
    
    with transaction_context(user_name, tx_id, "batch_create"):
        table_model = models.DYNAMIC_TABLES.get(table_name)
        if not table_model:
            raise ValueError(f"Table model for '{table_name}' is not initialized. Please define the table in config/table_config.json and restart the server/watcher processes.")
            
        new_rows = []
        for _ in range(count):
            row = table_model(
                row_id=str(uuid6.uuid7()),
                updated_at=func.now()
            )
            new_rows.append(row)
        
        db.add_all(new_rows)
        
        logs_to_cache = []
        if count > 0:
            for row in new_rows:
                log_dict = create_audit_log(
                    db, table_name, row.row_id, "CREATE",
                    None, "새 행 생성됨", "system", user_name,
                    transaction_id=tx_id,
                    business_key=row.business_key_val,
                    add_to_cache=False
                )
                logs_to_cache.append(log_dict)
        
        db.commit()
        
        if logs_to_cache:
            from audit_cache import audit_cache
            audit_cache.add_logs_batch(logs_to_cache)
            
        return new_rows

def delete_row(db: Session, table_name: str, row_id: str, user_name: str = "system"):
    """단일 행을 삭제합니다 (배치 로직으로 통합)."""
    return delete_rows_batch(db, table_name, [row_id], user_name) > 0

def delete_rows_batch(db: Session, table_name: str, row_ids: list[str], user_name: str = "system"):
    """여러 행을 일괄 삭제하고 개별 히스토리를 남기며 메타데이터도 연쇄 삭제합니다."""
    if not row_ids:
        return 0
        
    tx_id = str(uuid6.uuid7())
    
    with transaction_context(user_name, tx_id, "batch_delete"):
        table_model = models.DYNAMIC_TABLES.get(table_name)
        if not table_model:
            raise ValueError(f"Table model for '{table_name}' is not initialized. Please define the table in config/table_config.json and restart the server/watcher processes.")
            
        # 삭제하기 전 row_id와 business_key_val을 먼저 조회
        rows_to_delete = db.query(table_model).filter(
            table_model.row_id.in_(row_ids)
        ).all()
            
        # 메타데이터 연쇄 삭제
        db.query(models.CellOverwrite).filter(
            models.CellOverwrite.table_name == table_name,
            models.CellOverwrite.row_id.in_(row_ids)
        ).delete(synchronize_session=False)

        db.query(models.CellSource).filter(
            models.CellSource.table_name == table_name,
            models.CellSource.row_id.in_(row_ids)
        ).delete(synchronize_session=False)

        # 기본 데이터 삭제
        deleted_count = db.query(table_model).filter(
            table_model.row_id.in_(row_ids)
        ).delete(synchronize_session=False)
                
        if deleted_count > 0:
            logs_to_cache = []
            for row in rows_to_delete:
                log_dict = create_audit_log(
                    db, table_name, row.row_id, "DELETE", 
                    None, "행 삭제됨", "system", user_name,
                    transaction_id=tx_id,
                    business_key=row.business_key_val,
                    add_to_cache=False
                )
                logs_to_cache.append(log_dict)
            db.commit()
            
            if logs_to_cache:
                from audit_cache import audit_cache
                audit_cache.add_logs_batch(logs_to_cache)
                
            from audit_cache import audit_cache
            audit_cache.remove_deleted_rows(row_ids)
            
        return deleted_count

def get_row_cell(db: Session, table_name: str, row_id: str):
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        return None
    return db.query(table_model).filter(table_model.row_id == row_id).first()


def delete_cell_source_batch(db: Session, table_name: str, cells: list[dict], source_name: str):
    """여러 셀의 특정 데이터 원천(Source)을 일괄 삭제합니다."""
    if not cells:
        return [], []

    row_ids = list(set(c["row_id"] for c in cells))
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        return [], []
        
    rows = db.query(table_model).filter(table_model.row_id.in_(row_ids)).all()
    row_map = {r.row_id: r for r in rows}

    # 1. 특정 소스 일괄 삭제 실행 (동일 트랜잭션 내)
    from sqlalchemy import and_, or_
    delete_conds = []
    for item in cells:
        delete_conds.append(
            and_(
                models.CellSource.table_name == table_name,
                models.CellSource.row_id == item["row_id"],
                models.CellSource.column_name == item["column_name"],
                models.CellSource.source_name == source_name
            )
        )
    db.query(models.CellSource).filter(or_(*delete_conds)).delete(synchronize_session=False)

    # 2. 캐시 일괄 생성 (N+1 SELECT 차단)
    all_sources = db.query(
        models.CellSource.table_name,
        models.CellSource.row_id,
        models.CellSource.column_name,
        models.CellSource.source_name,
        models.CellSource.value,
        models.CellSource.updated_by,
        models.CellSource.ingested_at
    ).filter(
        models.CellSource.table_name == table_name,
        models.CellSource.row_id.in_(row_ids)
    ).all()
    
    sources_cache = {}
    for t_name, r_id, col_name, src_name, val, upd_by, ing_at in all_sources:
        key = (r_id, col_name)
        if key not in sources_cache:
            sources_cache[key] = []
        sources_cache[key].append(LightCellSource(t_name, r_id, col_name, src_name, val, upd_by, ing_at))

    all_overwrites = db.query(
        models.CellOverwrite.table_name,
        models.CellOverwrite.row_id,
        models.CellOverwrite.column_name,
        models.CellOverwrite.is_overwrite,
        models.CellOverwrite.updated_by,
        models.CellOverwrite.updated_at,
        models.CellOverwrite.manual_priority_source
    ).filter(
        models.CellOverwrite.table_name == table_name,
        models.CellOverwrite.row_id.in_(row_ids)
    ).all()
    
    overwrites_cache = {}
    for t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin in all_overwrites:
        overwrites_cache[(r_id, col_name)] = LightCellOverwrite(t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin)

    # 3. 인메모리 비교 루프 실행
    changed_rows = []
    tx_id = str(uuid6.uuid7())
    logs_to_cache = []
    
    cell_overwrites_to_upsert = {}
    cell_overwrites_to_delete = set()

    for item in cells:
        r_id = item["row_id"]
        col_name = item["column_name"]
        row = row_map.get(r_id)
        if not row:
            continue

        key = (r_id, col_name)
        col_srcs = sources_cache.get(key, [])
        ow = overwrites_cache.get(key)

        manual_pin = ow.manual_priority_source if ow else None
        if manual_pin == source_name:
            manual_pin = None
            if ow:
                ow.manual_priority_source = None

        sources_dict = {
            s.source_name: {
                "value": s.value,
                "timestamp": s.ingested_at.isoformat() if s.ingested_at else datetime.now().isoformat(),
                "updated_by": s.updated_by
            }
            for s in col_srcs
        }

        old_val = getattr(row, col_name, None)
        new_val, top_src = compute_priority_value(sources_dict, manual_pin, table_name)
        setattr(row, col_name, new_val)

        is_overwrite = ("user" in sources_dict) or (manual_pin is not None)
        ow_key = (table_name, r_id, col_name)
        if is_overwrite:
            ow_updated_by = ow.updated_by if ow else "system"
            ow_updated_at = ow.updated_at if ow else datetime.now()
            cell_overwrites_to_upsert[ow_key] = {
                "table_name": table_name,
                "row_id": r_id,
                "column_name": col_name,
                "is_overwrite": True,
                "updated_by": ow_updated_by,
                "updated_at": ow_updated_at,
                "manual_priority_source": manual_pin
            }
            cell_overwrites_to_delete.discard(ow_key)
        else:
            if ow:
                cell_overwrites_to_delete.add(ow_key)
                cell_overwrites_to_upsert.pop(ow_key, None)

        if str(old_val) != str(new_val):
            log_dict = create_audit_log(
                db, table_name, r_id, col_name, old_val, new_val,
                f"delete_source:{source_name}", "system",
                transaction_id=tx_id, business_key=row.business_key_val,
                add_to_cache=False
            )
            logs_to_cache.append(log_dict)

        if row not in changed_rows:
            changed_rows.append(row)

    # 4. 벌크 갱신 및 삭제
    bulk_upsert_cell_overwrites(db, list(cell_overwrites_to_upsert.values()))
    bulk_delete_cell_overwrites(db, list(cell_overwrites_to_delete))

    db.commit()
    
    if logs_to_cache:
        from audit_cache import audit_cache
        audit_cache.add_logs_batch(logs_to_cache)
        
    serialized_logs = []
    for log in logs_to_cache:
        log_copy = log.copy()
        if isinstance(log_copy.get("timestamp"), datetime):
            log_copy["timestamp"] = log_copy["timestamp"].isoformat()
        serialized_logs.append(log_copy)
        
    return changed_rows, serialized_logs

def delete_cell_source(db: Session, table_name: str, row_id: str, col_name: str, source_name: str):
    """특정 소스의 데이터를 삭제하고 값을 재계산합니다."""
    changed_rows, logs = delete_cell_source_batch(db, table_name, [{"row_id": row_id, "column_name": col_name}], source_name)
    return changed_rows[0] if changed_rows else None, [col_name] if logs else []

def set_cell_manual_priority_batch(db: Session, table_name: str, updates: list[dict], source_name: Optional[str], updated_by: str = "user"):
    """여러 셀의 표시 우선순위 소스를 수동으로 일괄 지정합니다 (Pin)."""
    if not updates:
        return [], []

    row_ids = list(set(u["row_id"] for u in updates))
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        return [], []
        
    rows = db.query(table_model).filter(table_model.row_id.in_(row_ids)).all()
    row_map = {r.row_id: r for r in rows}

    # 1. 인메모리 캐시 일괄 조회 및 적재
    all_sources = db.query(
        models.CellSource.table_name,
        models.CellSource.row_id,
        models.CellSource.column_name,
        models.CellSource.source_name,
        models.CellSource.value,
        models.CellSource.updated_by,
        models.CellSource.ingested_at
    ).filter(
        models.CellSource.table_name == table_name,
        models.CellSource.row_id.in_(row_ids)
    ).all()
    
    sources_cache = {}
    for t_name, r_id, col_name, src_name, val, upd_by, ing_at in all_sources:
        key = (r_id, col_name)
        if key not in sources_cache:
            sources_cache[key] = []
        sources_cache[key].append(LightCellSource(t_name, r_id, col_name, src_name, val, upd_by, ing_at))

    all_overwrites = db.query(
        models.CellOverwrite.table_name,
        models.CellOverwrite.row_id,
        models.CellOverwrite.column_name,
        models.CellOverwrite.is_overwrite,
        models.CellOverwrite.updated_by,
        models.CellOverwrite.updated_at,
        models.CellOverwrite.manual_priority_source
    ).filter(
        models.CellOverwrite.table_name == table_name,
        models.CellOverwrite.row_id.in_(row_ids)
    ).all()
    
    overwrites_cache = {}
    for t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin in all_overwrites:
        overwrites_cache[(r_id, col_name)] = LightCellOverwrite(t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin)

    # 2. 인메모리 연산 루프
    changed_rows = []
    tx_id = str(uuid6.uuid7())
    logs_to_cache = []
    deleted_row_ids = []
    
    cell_overwrites_to_upsert = {}
    cell_overwrites_to_delete = set()
    
    for item in updates:
        r_id = item["row_id"]
        col_name = item["column_name"]
        row = row_map.get(r_id)
        if not row:
            continue

        key = (r_id, col_name)
        col_srcs = sources_cache.get(key, [])
        ow = overwrites_cache.get(key)

        current_pin = ow.manual_priority_source if ow else None
        effective_source = None if (current_pin == source_name) else source_name

        if effective_source and not any(s.source_name == effective_source for s in col_srcs):
            continue

        sources_dict = {
            s.source_name: {
                "value": s.value,
                "timestamp": s.ingested_at.isoformat() if s.ingested_at else datetime.now().isoformat(),
                "updated_by": s.updated_by
            }
            for s in col_srcs
        }

        old_val = getattr(row, col_name, None)
        new_val, top_src = compute_priority_value(sources_dict, effective_source, table_name)
        setattr(row, col_name, new_val)

        is_overwrite = ("user" in sources_dict) or (effective_source is not None)
        ow_key = (table_name, r_id, col_name)
        if is_overwrite:
            ow_updated_by = ow.updated_by if ow else "system"
            ow_updated_at = ow.updated_at if ow else datetime.now()
            cell_overwrites_to_upsert[ow_key] = {
                "table_name": table_name,
                "row_id": r_id,
                "column_name": col_name,
                "is_overwrite": True,
                "updated_by": updated_by or ow_updated_by,
                "updated_at": datetime.now(),
                "manual_priority_source": effective_source
            }
            cell_overwrites_to_delete.discard(ow_key)
        else:
            if ow:
                cell_overwrites_to_delete.add(ow_key)
                cell_overwrites_to_upsert.pop(ow_key, None)

        if str(old_val) != str(new_val):
            log_dict = create_audit_log(
                db, table_name, r_id, col_name, old_val, new_val,
                f"set_priority:{effective_source}", updated_by,
                transaction_id=tx_id, business_key=row.business_key_val,
                add_to_cache=False
            )
            logs_to_cache.append(log_dict)

        # 복합 비즈니스 키 실시간 재계산 및 갱신 가드
        table_info = TABLE_CONFIG.get(table_name, {})
        composite_src = table_info.get("composite_key_source")
        key_col = table_info.get("business_key")
        composite_sep = table_info.get("composite_key_separator", "_")

        if composite_src and key_col and col_name in composite_src:
            vals = [clean_str_value(getattr(row, col, None)) for col in composite_src]
            if all(v != "" for v in vals):
                new_bk_val = composite_sep.join(vals)
            else:
                new_bk_val = None

            current_bk = getattr(row, "business_key_val", None)
            if current_bk != new_bk_val:
                if new_bk_val is not None:
                    # 중복 충돌 검사
                    conflict_row = db.query(table_model).filter(
                        table_model.business_key_val == new_bk_val,
                        table_model.row_id != row.row_id
                    ).first()
                    
                    if conflict_row:
                        # [Silent Merge & Overwrite] 그냥 덮어씌우고 기존 껍데기 행은 삭제
                        row_to_delete = row
                        row = conflict_row
                        
                        # 1. 임시 행의 모든 실제 값을 충돌 행에 덮어쓰기 병합
                        columns_to_merge = [c.name for c in table_model.__table__.columns]
                        for c_name in columns_to_merge:
                            if c_name in [key_col, "row_id", "business_key_val", "created_at", "updated_at"]:
                                continue
                            
                            is_explicitly_edited = any(u["column_name"] == c_name for u in updates)
                            
                            # [병합 보호 정책] 충돌 행(row)에 이미 사용자 수정(user)이나 핀이 들어있고, 이번에 직접 핀 고정 수정하는 셀이 아니면 기존 값 보존
                            old_ow = overwrites_cache.get((row.row_id, c_name)) if overwrites_cache else None
                            if not old_ow:
                                old_ow = db.query(models.CellOverwrite).filter(
                                    models.CellOverwrite.table_name == table_name,
                                    models.CellOverwrite.row_id == row.row_id,
                                    models.CellOverwrite.column_name == c_name
                                ).first()
                                
                            is_old_user_overwritten = False
                            if old_ow:
                                is_old_user_overwritten = old_ow.is_overwrite or (old_ow.manual_priority_source is not None)
                                
                            if is_old_user_overwritten and not is_explicitly_edited:
                                continue

                            new_v = getattr(row_to_delete, c_name, None)
                            
                            old_v = getattr(row, c_name, None)
                            has_changed = False
                            if new_v is not None:
                                if old_v is None:
                                    has_changed = True
                                else:
                                    has_changed = str(old_v).strip() != str(new_v).strip()
                                    
                            if has_changed:
                                setattr(row, c_name, new_v)
                                
                                # cell_overwrites_to_upsert 에 충돌 병합 기록
                                ow_key = (table_name, row.row_id, c_name)
                                cell_overwrites_to_upsert[ow_key] = {
                                    "table_name": table_name,
                                    "row_id": row.row_id,
                                    "column_name": c_name,
                                    "is_overwrite": True,
                                    "updated_by": "collision_merge",
                                    "updated_at": datetime.now(),
                                    "manual_priority_source": "collision_merge"
                                }
                                cell_overwrites_to_delete.discard(ow_key)
                                
                                # 원천 관리 DB에 진짜 지정했던 소스 혹은 껍데기 행의 진짜 소스로 계승하여 영속 기록
                                from database.models import CellSource
                                # 껍데기 행이 원래 가졌던 진짜 소스 추적
                                old_srcs, _ = _load_metadata_row_cell(
                                    db, table_name, row_to_delete.row_id, c_name,
                                    is_new=False,
                                    sources_cache=None,
                                    overwrites_cache=overwrites_cache,
                                    cell_sources_to_upsert=None,
                                    cell_overwrites_to_upsert=cell_overwrites_to_upsert
                                )
                                effective_src_name = None
                                if old_srcs:
                                    effective_src_name = old_srcs[0].source_name
                                if not effective_src_name:
                                    effective_src_name = source_name or "user"

                                db.query(CellSource).filter(
                                    CellSource.table_name == table_name,
                                    CellSource.row_id == row.row_id,
                                    CellSource.column_name == c_name,
                                    CellSource.source_name == effective_src_name
                                ).delete()
                                
                                new_src = CellSource(
                                    table_name=table_name,
                                    row_id=row.row_id,
                                    column_name=c_name,
                                    source_name=effective_src_name,
                                    value=clean_str_value(new_v),
                                    updated_by=updated_by or "user"
                                )
                                db.add(new_src)
                                
                                # Audit Log 기록
                                log_dict = create_audit_log(
                                    db, table_name, row.row_id, c_name, old_v, new_v,
                                    "collision_merge", updated_by,
                                    transaction_id=tx_id, business_key=row.business_key_val,
                                    add_to_cache=False
                                )
                                logs_to_cache.append(log_dict)
                                
                                if c_name not in changed_cols:
                                    changed_cols.append(c_name)
                                    
                        # 2. 임시 껍데기 행 삭제
                        try:
                            db.delete(row_to_delete)
                            deleted_row_ids.append(row_to_delete.row_id)
                        except Exception:
                            pass
                            
                        # 3. 변경 대상 변경사항 캐시 스위칭
                        if row not in changed_rows:
                            changed_rows.append(row)

                row.business_key_val = new_bk_val
                setattr(row, key_col, new_bk_val)
                
                # 감사 로그 생성
                log_dict = create_audit_log(
                    db, table_name, r_id, key_col, current_bk, new_bk_val,
                    "set_priority_sync", updated_by,
                    transaction_id=tx_id, business_key=new_bk_val,
                    add_to_cache=False
                )
                logs_to_cache.append(log_dict)
            
        if row not in changed_rows:
            changed_rows.append(row)
            
    # 3. 벌크 갱신 및 삭제 수행
    bulk_upsert_cell_overwrites(db, list(cell_overwrites_to_upsert.values()))
    bulk_delete_cell_overwrites(db, list(cell_overwrites_to_delete))

    db.commit()
    
    if logs_to_cache:
        from audit_cache import audit_cache
        audit_cache.add_logs_batch(logs_to_cache)
        
    serialized_logs = []
    for log in logs_to_cache:
        log_copy = log.copy()
        if isinstance(log_copy.get("timestamp"), datetime):
            log_copy["timestamp"] = log_copy["timestamp"].isoformat()
        serialized_logs.append(log_copy)
        
    return changed_rows, serialized_logs, deleted_row_ids

def set_cell_manual_priority(db: Session, table_name: str, row_id: str, col_name: str, source_name: Optional[str], updated_by: str = "user"):
    """수동 소스 우선순위(Pin)를 설정합니다."""
    changed_rows, logs, deleted_row_ids = set_cell_manual_priority_batch(db, table_name, [{"row_id": row_id, "column_name": col_name}], source_name, updated_by)
    return changed_rows[0] if changed_rows else None, [col_name] if logs else [], deleted_row_ids
