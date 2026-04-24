from pydantic import BaseModel, field_validator
from typing import Dict, Any, Optional
from datetime import datetime, timezone

class CellData(BaseModel):
    value: Any                          # 현재 표출되고 있는 최종 값
    is_overwrite: bool = False          # 사용자(human)에 의한 고정 여부 (== sources['user'] 존재 여부)
    sources: Dict[str, Any] = {}        # { "user": val, "parser_a": val, ... } 각 소스별 원천 데이터
    updated_by: Optional[str] = "system"
    priority_source: Optional[str] = None # 현재 value를 결정한 소스 명칭

class CellUpdate(BaseModel):
    row_id: str
    column_name: str
    value: Any
    source_name: str = "user" 
    updated_by: Optional[str] = "user"

class AuditLogResponse(BaseModel):
    id: int
    table_name: str
    row_id: str
    column_name: str
    old_value: Any
    new_value: Any
    source_name: str
    updated_by: str
    transaction_id: Optional[str] = None
    timestamp: datetime

    @field_validator("timestamp", mode="after")
    @classmethod
    def convert_to_local(cls, v: datetime) -> datetime:
        if v:
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.astimezone()
        return v

    class Config:
        from_attributes = True

class CellUpdateBatch(BaseModel):
    updates: list[CellUpdate]

class CellUpsert(BaseModel):
    business_key_val: Any
    updates: Dict[str, Any]
    source_name: str = "user"
    updated_by: Optional[str] = "user"

class CellUpsertBatch(BaseModel):
    items: list[CellUpsert]

class GeneralUpdateItem(BaseModel):
    row_id: Optional[str] = None           # PK 기반 업데이트 시 사용
    business_key_val: Optional[Any] = None # 비즈니스 키 기반 업서트 시 사용
    updates: Dict[str, Any]                # { "column_name": value }
    source_name: str = "user"
    updated_by: Optional[str] = "system"

class GeneralUpdateBatch(BaseModel):
    updates: list[GeneralUpdateItem]
    transaction_id: Optional[str] = None # [Phase 75] 외부에서 주입하는 트랜잭션 ID 지원
    silent: bool = False                 # [Phase 76] True일 경우 WebSocket 브로드캐스트 생략

class RowDeleteBatch(BaseModel):
    row_ids: list[str]
    user_name: str = "system"

class DataRowBase(BaseModel):
    row_id: str
    table_name: str
    data: Dict[str, CellData]

class DataRowCreate(DataRowBase):
    pass

class DataRowResponse(DataRowBase):
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator("created_at", "updated_at", mode="after")
    @classmethod
    def convert_to_local(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v:
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.astimezone()
        return v

    class Config:
        from_attributes = True

class PaginatedDataResponse(BaseModel):
    table_name: str
    total: int
    skip: int
    limit: int
    data: list[DataRowResponse]

class TargetedRowIdRequest(BaseModel):
    offsets: list[int]
    q: Optional[str] = None
    cols: Optional[str] = None  # [Phase 73.6] 검색 대상 컬럼 제한 (comma separated)
    order_by: str = "row_id"
    order_desc: bool = False

class RowIndexDiscoveryRequest(BaseModel):
    q: Optional[str] = None
    cols: Optional[str] = None
    order_by: str = "row_id"
    order_desc: bool = False

# --- Dashboard Schemas ---
class TableStat(BaseModel):
    table_name: str
    row_count: int
    last_updated: Optional[str] = None
    status: str = "Active" # Active / Idle

class DashboardSummaryResponse(BaseModel):
    total_tables: int
    total_rows: int
    today_updates: int
    table_stats: list[TableStat]
    system_health: str = "Excellent"
