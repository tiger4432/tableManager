from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import os
import uuid
from datetime import datetime

# 데이터베이스 연결 URL (환경 변수가 있으면 사용, 없으면 PostgreSQL 기본값, 최종적으로 SQLite)
# 형식: postgresql://[사용자]:[비밀번호]@[호스트]:[포트]/[DB명]
DEFAULT_PG_URL = "postgresql://postgres:admin@localhost:5432/assy_manager"
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_PG_URL)

# SQLite 호환성을 위해 체크 (SQLite 파일이 존재하고 URL에 sqlite가 포함된 경우)
is_sqlite = "sqlite" in SQLALCHEMY_DATABASE_URL

# 엔진 설정 (PostgreSQL용 커넥션 풀링 최적화 포함)
if is_sqlite:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_size=20,           # 커넥션 풀 크기 (1,000만 행 동시 접속 대응)
        max_overflow=10,        # 피크 시 추가 허용 커넥션
        pool_recycle=3600,      # 커넥션 재사용 시간
        connect_args={"options": "-c client_encoding=utf8"} # [핵심] DB 연결 시 UTF-8 강제
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@event.listens_for(Session, "before_flush")
def auto_stage_database_outbox(session, flush_context, instances):
    from .models import DataRow
    
    for obj in session.new:
        if isinstance(obj, DataRow):
            stage_event(session, "CREATE", obj.table_name, obj)
            
    for obj in session.dirty:
        if isinstance(obj, DataRow):
            stage_event(session, "EDIT", obj.table_name, obj)
            
    for obj in session.deleted:
        if isinstance(obj, DataRow):
            stage_event(session, "DELETE", obj.table_name, obj)


def stage_event(session, event_type, table_name, data_row):
    from .models import DatabaseOutbox
    from .context import request_user, request_transaction_id, request_source
    
    tx_id = request_transaction_id.get() or str(uuid.uuid4())
    user = request_user.get()
    source = request_source.get()
    
    event_obj = DatabaseOutbox(
        event_uuid=str(uuid.uuid4()),
        event_type=event_type,
        table_name=table_name or "unknown",
        payload={
            "row_id": data_row.row_id,
            "business_key": data_row.business_key_val,
            "data": data_row.data,
            "transaction_id": tx_id,
            "updated_by": user,
            "source_name": source,
            "timestamp": datetime.now().isoformat()
        },
        status="PENDING"
    )
    session.add(event_obj)
