import os
import sys
from sqlalchemy import text

# 프로젝트 루트를 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.database import engine, Base
from database import models # 모델을 임포트해야 Base.metadata가 채워짐

def setup_database():
    print("🚀 AssyManager Database Setup Starting...")
    
    # 1. pg_trgm 확장 기능 활성화 (Trigram 검색의 핵심)
    with engine.connect() as conn:
        print("  - Step 1: Enabling PostgreSQL pg_trgm extension...")
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            conn.commit()
            print("    [OK] pg_trgm extension is ready.")
        except Exception as e:
            print(f"    [Warning] Failed to create extension: {e}")
            print("    (Make sure you have superuser privileges on the database)")

    # 2. 모든 테이블 및 인덱스 생성
    print("  - Step 2: Creating tables and indices from models...")
    try:
        # 이 시점에 models.py의 Index("idx_data_trgm", ...) 정의가 반영되어 함께 생성됩니다.
        Base.metadata.create_all(bind=engine)
        print("    [OK] All tables and indices are created successfully.")
    except Exception as e:
        print(f"    [Error] Failed to create tables: {e}")
        return

    # 3. 인덱스 최적화 통계 업데이트
    with engine.connect() as conn:
        print("  - Step 3: Optimizing indices (ANALYZE)...")
        conn.execute(text("ANALYZE data_rows;"))
        conn.commit()
        print("    [OK] Optimization complete.")

    print("\n✅ Database setup finished! You are ready to handle 10M+ rows.")

if __name__ == "__main__":
    setup_database()
