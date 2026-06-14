from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, Index, text, BigInteger
from sqlalchemy.sql import func
from .database import Base, is_sqlite

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
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # [핵심] 1,000만 건 규모의 데이터 최적화 색인 일람
    _table_args_list = [
        # [A] 테이블별 품번 정렬용 복합 색인 (Covering Index 전환: row_id 추가)
        Index("idx_table_bk", "table_name", "business_key_val", "row_id"),
        
        # [B] 테이블별 최신순 정렬용 복합 색인 (Covering Index 전환: row_id 추가)
        Index("idx_table_updated", "table_name", "updated_at", "row_id"),
        
        # [B-2] 테이블별 기본 정렬(정렬 OFF)용 복합 색인
        Index("idx_table_rowid", "table_name", "row_id"),
    ]
    if not is_sqlite:
        _table_args_list.extend([
            # [C] JSONB 전용 GIN 색인: 데이터 내부 키/밸류 구조적 검색 지원 (@> 등)
            Index("idx_data_gin", "data", postgresql_using="gin"),

            # [D] 고성능 복합 GIN Trigram 색인: 테이블 범위 한정 + 데이터 전체 텍스트 검색 (ILIKE 가속)
            Index("idx_table_data_trgm", "table_name", text("(CAST(data AS text)) gin_trgm_ops"), postgresql_using="gin"),
        ])
    __table_args__ = tuple(_table_args_list)

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
    business_key = Column(String, nullable=True, index=True)


class DatabaseOutbox(Base):
    __tablename__ = "database_outbox"

    id = Column(Integer, primary_key=True, index=True)
    event_uuid = Column(String, unique=True, index=True, nullable=False)
    event_type = Column(String(50), nullable=False)
    table_name = Column(String(100), nullable=False)
    payload = Column(JSON().with_variant(JSONB, "postgresql"), default=dict, nullable=False)
    status = Column(String(20), default="PENDING", index=True)
    retry_count = Column(Integer, default=0)
    processed_chain = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_outbox_pending", "status", postgresql_where=text("status = 'PENDING'")),
    )


class FileIngestionLog(Base):
    __tablename__ = "file_ingestion_logs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    filepath = Column(String)
    table_name = Column(String, index=True)
    status = Column(String(20), default="FAILED", index=True) # "FAILED", "SUCCESS", "PENDING"
    error_message = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CellOverwrite(Base):
    __tablename__ = "cell_overwrites"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, index=True)
    table_name = Column(String, nullable=False, index=True)
    row_id = Column(String, nullable=False, index=True)
    column_name = Column(String, nullable=False, index=True)
    is_overwrite = Column(Boolean, default=True)
    updated_by = Column(String, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    manual_priority_source = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_overwrites_lookup", "table_name", "row_id"),
        Index("idx_overwrites_lookup_col", "table_name", "row_id", "column_name", unique=True),
    )

class CellSource(Base):
    __tablename__ = "cell_sources"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, index=True)
    table_name = Column(String, nullable=False, index=True)
    row_id = Column(String, nullable=False, index=True)
    column_name = Column(String, nullable=False, index=True)
    source_name = Column(String, nullable=False)
    value = Column(JSON, nullable=True)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_sources_lookup", "table_name", "row_id", "column_name"),
        Index("idx_sources_lookup_source", "table_name", "row_id", "column_name", "source_name", unique=True),
    )


DYNAMIC_TABLES = {}

from sqlalchemy.orm import registry
mapper_registry = registry()

def init_dynamic_models(config_dict: dict):
    """
    table_config.json 설정을 기반으로 SQLAlchemy Table 객체들을 동적으로 빌드하고
    Imperative Mapping을 사용하여 완전한 ORM 모델 클래스로 매핑해 DYNAMIC_TABLES에 등록합니다.
    """
    from sqlalchemy import Table, Column, String, DateTime, Float, Index
    from sqlalchemy.sql import func
    
    for table_name, table_cfg in config_dict.items():
        if table_name in DYNAMIC_TABLES:
            continue
            
        # 1. 모든 동적 물리 테이블이 공유할 메타데이터 컬럼들
        columns = [
            Column("row_id", String, primary_key=True, index=True),
            Column("business_key_val", String, index=True, nullable=True),
            Column("created_at", DateTime(timezone=True), server_default=func.now(), index=True),
            Column("updated_at", DateTime(timezone=True), server_default=func.now(), index=True),
        ]
        
        # 2. table_config에 정의된 사용자 컬럼들을 native 타입으로 바인딩
        col_types = table_cfg.get("column_types", {})
        for col_name, type_str in col_types.items():
            if col_name in ["created_at", "updated_at"]:
                continue
            if type_str == "number":
                sql_type = Float
            elif type_str == "datetime":
                sql_type = DateTime(timezone=True)
            else:
                sql_type = String
            columns.append(Column(col_name, sql_type, nullable=True))
            
        # 3. 1,000만 행 스케일에 최적화된 복합 색인(Covering Index) 정의
        idx_bk_name = f"idx_{table_name}_bk"
        idx_updated_name = f"idx_{table_name}_updated"
        
        table_args = (
            Index(idx_bk_name, "business_key_val", "row_id"),
            Index(idx_updated_name, "updated_at", "row_id"),
        )
        
        # 4. Table 객체 동적 생성 및 metadata 등록
        table_obj = Table(
            table_name,
            Base.metadata,
            *columns,
            *table_args,
            extend_existing=True
        )
        
        # 5. 동적 PascalCase 클래스 생성 및 Imperative Mapping 바인딩
        class_name = "".join(part.capitalize() for part in table_name.split("_"))
        dynamic_class = type(class_name, (object,), {
            "__table__": table_obj
        })
        
        mapper_registry.map_imperatively(dynamic_class, table_obj)
        DYNAMIC_TABLES[table_name] = dynamic_class


def sync_dynamic_tables_schema(engine):
    """
    DYNAMIC_TABLES의 정의와 실제 DB 물리 테이블의 스키마를 비교하여,
    설정에는 존재하지만 DB에는 없는 컬럼들을 ALTER TABLE DDL을 통해 자동으로 추가합니다.
    """
    from sqlalchemy import inspect
    from sqlalchemy.schema import CreateColumn
    
    inspector = inspect(engine)
    dialect = engine.dialect
    
    with engine.begin() as conn:
        for table_name, model_class in DYNAMIC_TABLES.items():
            if not inspector.has_table(table_name):
                continue
                
            db_cols = {c["name"].lower() for c in inspector.get_columns(table_name)}
            table_obj = model_class.__table__
            
            for column in table_obj.columns:
                col_name = column.name
                if col_name.lower() not in db_cols:
                    col_ddl = str(CreateColumn(column).compile(dialect=dialect)).strip()
                    alter_query = f"ALTER TABLE {table_name} ADD COLUMN {col_ddl}"
                    print(f"[Schema Sync] Altering table '{table_name}': {alter_query}")
                    try:
                        from sqlalchemy import text
                        conn.execute(text(alter_query))
                        print(f"[Schema Sync] Successfully added column '{col_name}' to table '{table_name}'.")
                    except Exception as err:
                        print(f"[Schema Sync] Failed to add column '{col_name}' to table '{table_name}': {err}")
