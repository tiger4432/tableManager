import sys
import os
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from database.database import engine
from sqlalchemy import text

def create_composite_gin():
    # AUTOCOMMIT 모드로 연결하여 CONCURRENTLY 인덱스 생성 허용
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        print("Step 1: Enabling btree_gin extension...")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gin"))
        
        print("Step 2: Creating composite GIN index (table_name + data)...")
        print("This may take a while if you have millions of rows...")
        t0 = time.time()
        # CONCURRENTLY를 사용하여 서비스 중단 없이 인덱스 생성
        conn.execute(text("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_table_data_trgm 
            ON data_rows USING GIN (table_name, (CAST(data AS text)) gin_trgm_ops)
        """))
        print(f"Index created successfully in {time.time() - t0:.2f}s")

if __name__ == "__main__":
    create_composite_gin()
