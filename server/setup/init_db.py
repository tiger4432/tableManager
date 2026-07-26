import os
import sys
import json
from sqlalchemy import text

# 프로젝트 루트를 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.database import engine, Base
from database import models  # 모델을 임포트해야 Base.metadata가 채워짐

def setup_database():
    print("[Launcher] AssyManager Database Setup Starting...")
    
    # 1. table_config.json을 로드하여 동적 모델 초기화
    import paths  # single override point (ASSY_DATA_ROOT)
    config_path = paths.config_path("table_config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            table_config = json.load(f)
        models.init_dynamic_models(table_config)
        print("    [OK] Dynamic models initialized from table_config.json.")
    except Exception as e:
        print(f"    [Error] Failed to initialize dynamic models: {e}")
        return

    # 2. pg_trgm 확장 기능 활성화 (PostgreSQL용)
    with engine.connect() as conn:
        print("  - Step 2: Enabling PostgreSQL pg_trgm extension...")
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            conn.commit()
            print("    [OK] pg_trgm extension is ready.")
        except Exception as e:
            print(f"    [Warning] Failed to create extension (can be ignored for SQLite): {e}")

    # 3. 모든 테이블 및 인덱스 생성
    print("  - Step 3: Creating tables and indices from models...")
    try:
        Base.metadata.create_all(bind=engine)
        print("    [OK] All tables and indices are created successfully.")
    except Exception as e:
        print(f"    [Error] Failed to create tables: {e}")
        return

    # 4. 인덱스 최적화 통계 업데이트 (PostgreSQL용)
    with engine.connect() as conn:
        print("  - Step 4: Optimizing indices (ANALYZE)...")
        try:
            conn.execute(text("ANALYZE cell_overwrites;"))
            conn.execute(text("ANALYZE cell_sources;"))
            conn.execute(text("ANALYZE audit_logs;"))
            for table_name in table_config.keys():
                conn.execute(text(f"ANALYZE {table_name};"))
            conn.commit()
            print("    [OK] Optimization complete.")
        except Exception as e:
            print(f"    [Warning] Failed to run ANALYZE (can be ignored for SQLite): {e}")

    print("\n[OK] Database setup finished! You are ready to handle 10M+ rows.")

if __name__ == "__main__":
    setup_database()
