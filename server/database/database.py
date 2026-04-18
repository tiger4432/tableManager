from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

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
