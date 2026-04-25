import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine, text
from database.database import SQLALCHEMY_DATABASE_URL

print(f"Optimizing Search for DB: {SQLALCHEMY_DATABASE_URL}")
engine = create_engine(SQLALCHEMY_DATABASE_URL)

sql_commands = [
    "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
    "DROP INDEX IF EXISTS idx_data_trgm;",
    # JSONB 전체 데이터를 텍스트로 변환하여 Trigram GIN 인덱스 생성
    # 이 인덱스는 'data::text ILIKE %q%' 패턴의 검색을 비약적으로 가속합니다.
    "CREATE INDEX idx_data_trgm ON data_rows USING gin (CAST(data AS text) gin_trgm_ops);",
    "ANALYZE data_rows;"
]

with engine.connect() as conn:
    for sql in sql_commands:
        print(f"Executing: {sql}")
        try:
            conn.execute(text(sql))
            conn.commit()
            print("  - Success")
        except Exception as e:
            print(f"  - Error: {e}")

print("Search optimization (Trigram Index) completed.")
