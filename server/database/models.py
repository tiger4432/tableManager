from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, Index, text
from sqlalchemy.sql import func
from .database import Base

from sqlalchemy.dialects.postgresql import JSONB

class DataRow(Base):
    __tablename__ = "data_rows"

    # We use string for row_id to handle potential string keys from parsers
    row_id = Column(String, primary_key=True, index=True)
    
    # Store the entire row data as a JSON blob (PostgreSQL의 경우 JSONB 적용)
    table_name = Column(String, index=True)
    business_key_val = Column(String, index=True) # [고성능 정렬용] BK 값 추출 보관용 가상 컬럼
    data = Column(JSON().with_variant(JSONB, "postgresql"), default=dict)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # [핵심] 1,000만 건 규모의 데이터 최적화 색인 일람
    __table_args__ = (
        # [A] 테이블별 품번 정렬용 복합 색인 (Covering Index 전환: row_id 추가)
        Index("idx_table_bk", "table_name", "business_key_val", "row_id"),
        
        # [B] 테이블별 최신순 정렬용 복합 색인 (Covering Index 전환: row_id 추가)
        Index("idx_table_updated", "table_name", "updated_at", "row_id"),
        
        # [B-2] 테이블별 기본 정렬(정렬 OFF)용 복합 색인
        Index("idx_table_rowid", "table_name", "row_id"),
        
        # [C] JSONB 전용 GIN 색인: 데이터 내부 키/밸류 구조적 검색 지원 (@> 등)
        Index("idx_data_gin", "data", postgresql_using="gin"),

        # [D] 고성능 복합 GIN Trigram 색인: 테이블 범위 한정 + 데이터 전체 텍스트 검색 (ILIKE 가속)
        # 1,000만 건 환경에서 특정 테이블 내의 'q=' 검색 성능을 극대화합니다.
        Index("idx_table_data_trgm", "table_name", text("(CAST(data AS text)) gin_trgm_ops"), postgresql_using="gin"),
    )

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
    transaction_id = Column(String, index=True, nullable=True) # [Phase 2] 배치 작업 그룹화용 ID
    
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
