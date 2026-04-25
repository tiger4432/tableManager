import os
import sys
from sqlalchemy import text

# 프로젝트 루트를 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.database import engine, Base
from database import models
from scripts.init_db import setup_database

def reset_database():
    print("⚠️  AssyManager Database RESET Starting...")
    print("‼️  This will DELETE ALL DATA in the database.")
    
    # 1. 모든 테이블 삭제
    with engine.connect() as conn:
        print("  - Step 1: Dropping all existing tables...")
        try:
            # metadata에 등록된 모든 테이블 삭제
            Base.metadata.drop_all(bind=engine)
            conn.commit()
            print("    [OK] All tables dropped.")
        except Exception as e:
            print(f"    [Error] Failed to drop tables: {e}")

    # 2. 초기화 스크립트 호출하여 다시 생성 (pg_trgm 확장 및 인덱스 포함)
    print("\n  - Step 2: Re-initializing database structure...")
    setup_database()

if __name__ == "__main__":
    reset_database()
