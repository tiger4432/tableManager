import sys
import os
import time
from sqlalchemy import text

# 프로젝트 루트를 경로에 추가
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.database import engine

def setup_performance():
    print("🚀 AssyManager DB Performance Setup Starting...")
    
    # AUTOCOMMIT 모드로 실행 (CONCURRENTLY 인덱스 생성 지원)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        
        # 1. 필수 확장 프로그램 설치
        print("\nStep 1: Enabling PostgreSQL Extensions...")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gin"))
        print("Done.")

        # 2. 최적화 인덱스 일괄 생성
        # CONCURRENTLY 옵션으로 서비스 중인 서버에서도 안전하게 실행 가능합니다.
        indices = [
            # [A] 테이블별 품번 정렬 (Covering Index)
            ("idx_table_bk", "data_rows", "USING btree (table_name, business_key_val, row_id)"),
            
            # [B] 테이블별 최신순 정렬 (Covering Index)
            ("idx_table_updated", "data_rows", "USING btree (table_name, updated_at, row_id)"),
            
            # [C] 테이블별 기본 정렬 (row_id)
            ("idx_table_rowid", "data_rows", "USING btree (table_name, row_id)"),
            
            # [D] JSONB 데이터 구조 검색용 GIN
            ("idx_data_gin", "data_rows", "USING gin (data)"),
            
            # [E] 테이블 범위 한정 풀텍스트 검색용 복합 GIN Trigram (핵심 최적화)
            ("idx_table_data_trgm", "data_rows", "USING gin (table_name, (CAST(data AS text)) gin_trgm_ops)")
        ]

        print("\nStep 2: Creating Optimized Indices (this may take a few minutes)...")
        for idx_name, table, definition in indices:
            print(f" - Creating {idx_name} on {table}...")
            t0 = time.time()
            try:
                conn.execute(text(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON {table} {definition}"))
                print(f"   Success ({time.time() - t0:.2f}s)")
            except Exception as e:
                print(f"   Failed to create {idx_name}: {e}")

        # 3. 통계 정보 갱신
        print("\nStep 3: Refreshing Statistics (ANALYZE)...")
        conn.execute(text("ANALYZE data_rows"))
        print("Done.")

    print("\n✅ All performance optimizations have been applied successfully!")

if __name__ == "__main__":
    setup_performance()
