from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime

class CellData(BaseModel):
    value: Any
    is_overwrite: bool = False
    updated_by: Optional[str] = "system"

class CellUpdate(BaseModel):
    row_id: str
    column_name: str
    value: Any

class CellUpdateBatch(BaseModel):
    updates: list[CellUpdate]

class DataRowBase(BaseModel):
    row_id: str
    table_name: str
    data: Dict[str, CellData]

class DataRowCreate(DataRowBase):
    pass

class DataRowResponse(DataRowBase):
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class PaginatedDataResponse(BaseModel):
    table_name: str
    total: int
    skip: int
    limit: int
    data: list[DataRowResponse]
