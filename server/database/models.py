from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime
from sqlalchemy.sql import func
from .database import Base

class DataRow(Base):
    __tablename__ = "data_rows"

    # We use string for row_id to handle potential string keys from parsers
    row_id = Column(String, primary_key=True, index=True)
    
    # Store the entire row data as a JSON blob.
    # We could also normalize this to a Cell table if doing exact cell-level queries,
    # but for a "lazy load row chunks", fetching JSON rows is very efficient and dynamic.
    # For now, let's stick to a dynamic JSON approach to easily extend for Any Table.
    table_name = Column(String, index=True)
    business_key_val = Column(String, index=True) # [고성능 정렬용] BK 값 추출 보관용 가상 컬럼
    data = Column(JSON, default=dict)
    
    # In data JSON:
    # {
    #   "colA": {"value": "abc", "is_overwrite": False},
    #   "colB": {"value": 123, "is_overwrite": True}
    # }

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String, index=True)
    row_id = Column(String, index=True)
    column_name = Column(String)
    
    old_value = Column(JSON, nullable=True) # Previous value
    new_value = Column(JSON)                # New value
    
    source_name = Column(String)            # user, parser_a, etc.
    updated_by = Column(String)             # user_id or agent_name
    
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
