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
    data = Column(JSON, default=dict)
    
    # In data JSON:
    # {
    #   "colA": {"value": "abc", "is_overwrite": False},
    #   "colB": {"value": 123, "is_overwrite": True}
    # }

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
