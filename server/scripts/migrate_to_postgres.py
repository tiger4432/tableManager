"""
migrate_to_postgres.py
SQLite 데이터를 PostgreSQL(admin)로 이관하는 마이그레이션 스크립트.
"""

import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# [경로 보정] scripts 폴더로 이동됨에 따라 상위 폴더(server/)를 path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
server_root = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.append(server_root)

from database import models
from database.database import Base, DEFAULT_PG_URL

# 1. 원본 (SQLite) 설정
SQLITE_PATH = os.path.join(server_root, "assy_manager.db")
SQLITE_URL = f"sqlite:///{SQLITE_PATH}"

print(f"[*] Starting migration...")
print(f"[*] Source (SQLite): {SQLITE_URL}")
print(f"[*] Target (PostgreSQL): {DEFAULT_PG_URL}")

sqlite_engine = create_engine(SQLITE_URL)
pg_engine = create_engine(DEFAULT_PG_URL)

SqliteSession = sessionmaker(bind=sqlite_engine)
PgSession = sessionmaker(bind=pg_engine)

def sanitize_to_utf8(data):
    """재귀적으로 데이터를 탐색하여 비유효 UTF-8 문자를 제거합니다."""
    if isinstance(data, dict):
        return {k: sanitize_to_utf8(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_to_utf8(v) for v in data]
    elif isinstance(data, str):
        return data.encode("utf-8", "ignore").decode("utf-8")
    else:
        return data

def migrate():
    # 2. 타겟 DB에 스키마 생성
    print("[1/3] Creating schema in PostgreSQL...")
    models.Base.metadata.create_all(bind=pg_engine)
    
    sqlite_db = SqliteSession()
    pg_db = PgSession()
    
    try:
        # 3. data_rows 이관
        print("[2/3] Migrating data_rows...")
        rows = sqlite_db.query(models.DataRow).all()
        print(f"    - Found {len(rows)} rows to migrate.")
        
        # PostgreSQL에 중복 삽입 방지를 위해 기존 데이터 삭제 (Clean Start)
        pg_db.query(models.DataRow).delete()
        
        for i, row in enumerate(rows):
            # 새 객체 생성 (데이터 정제 포함)
            new_row = models.DataRow(
                row_id=row.row_id,
                table_name=row.table_name,
                business_key_val=row.business_key_val,
                data=sanitize_to_utf8(row.data),
                created_at=row.created_at,
                updated_at=row.updated_at
            )
            pg_db.add(new_row)
            if (i + 1) % 500 == 0: # 이전 수정 반영: 500단위
                print(f"    - ... {i + 1} rows processed.")
        
        # 4. audit_logs 이관
        print("[3/3] Migrating audit_logs...")
        logs = sqlite_db.query(models.AuditLog).all()
        print(f"    - Found {len(logs)} logs to migrate.")
        
        pg_db.query(models.AuditLog).delete()
        
        for i, log in enumerate(logs):
            new_log = models.AuditLog(
                table_name=log.table_name,
                row_id=log.row_id,
                column_name=log.column_name,
                old_value=sanitize_to_utf8(log.old_value),
                new_value=sanitize_to_utf8(log.new_value),
                source_name=log.source_name,
                updated_by=log.updated_by,
                timestamp=log.timestamp
            )
            pg_db.add(new_log)
            if (i + 1) % 500 == 0: # 이전 수정 반영: 500단위
                print(f"    - ... {i + 1} logs processed.")
        
        print("[*] Committing changes to PostgreSQL...")
        pg_db.commit()
        print("[*] SUCCESS: Migration completed successfully!")
        
    except Exception as e:
        print(f"[!] ERROR during migration: {e}")
        pg_db.rollback()
    finally:
        sqlite_db.close()
        pg_db.close()

if __name__ == "__main__":
    confirm = input("기존 PostgreSQL 데이터를 삭제하고 SQLite 데이터를 덮어씌웁니다. 진행하시겠습니까? (y/n): ")
    if confirm.lower() == 'y':
        migrate()
    else:
        print("Migration cancelled.")
