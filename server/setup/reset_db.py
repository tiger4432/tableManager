import os
import sys
import json
from sqlalchemy import text

# 프로젝트 루트를 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.database import engine, Base, is_sqlite
from database import models
from setup.init_db import setup_database

def reset_database():
    print("[WARNING] AssyManager Database RESET Starting...")
    print("[WARNING] This will DELETE ALL DATA in the database.")
    
    # 1. table_config.json을 로드하여 동적 모델 초기화 (Base.metadata에 등록하여 drop_all이 가능하게 함)
    import paths  # single override point (ASSY_DATA_ROOT)
    config_path = paths.config_path("table_config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            table_config = json.load(f)
        models.init_dynamic_models(table_config)
        print("    [OK] Dynamic models registered for clean teardown.")
    except Exception as e:
        print(f"    [Warning] Failed to load table_config: {e}")

    # 2. PostgreSQL 환경인 경우, 락(Lock) 충돌을 방지하기 위해 다른 활성 커넥션 강제 종료
    if not is_sqlite:
        print("  - Step 2: Disconnecting other active database sessions to avoid DDL locks...")
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text("""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND pid <> pg_backend_pid();
                """))
            print("    [OK] Active database sessions terminated.")
        except Exception as e:
            print(f"    [Warning] Failed to terminate active sessions: {e}")

    # 3. 모든 테이블 삭제
    with engine.connect() as conn:
        print("  - Step 3: Dropping all existing tables...")
        try:
            Base.metadata.drop_all(bind=engine)
            conn.commit()
            print("    [OK] All tables dropped.")
        except Exception as e:
            print(f"    [Error] Failed to drop tables: {e}")

    # 4. 초기화 스크립트 호출하여 다시 생성 (pg_trgm 확장 및 인덱스 포함)
    print("\n  - Step 4: Re-initializing database structure...")
    setup_database()

if __name__ == "__main__":
    reset_database()
