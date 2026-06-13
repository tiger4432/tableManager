import sys
import os
import time
import json

# server 디렉토리를 sys.path에 추가하여 내부 임포트 정합성 확보
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from database.database import SessionLocal, engine, Base
from database import models

def main():
    print("=" * 60)
    print(" 🚀 Starting Data Migration: JSONB -> Relational Columns")
    print("=" * 60)
    
    # 1. Load config and initialize dynamic models
    config_path = os.path.join(server_dir, "config", "table_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)
        
    models.init_dynamic_models(table_config)
    
    # 2. Create tables if not exists
    print("[Migration] Ensuring new relational tables exist...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # 2.5 Truncate target tables to ensure clean migration
        print("[Migration] Cleaning up existing target tables (truncating)...")
        from sqlalchemy import text
        for table_name in table_config.keys():
            db.execute(text(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE'))
        db.commit()

        # 3. Check legacy data count
        # (DataRow 모델이 여전히 models.py에 정의되어 있으므로 조회 가능)
        legacy_query = db.query(models.DataRow)
        total_legacy_rows = legacy_query.count()
        print(f"[Migration] Total legacy rows to migrate: {total_legacy_rows:,}")
        
        if total_legacy_rows == 0:
            print("[Migration] No data found in legacy 'data_rows' table. Migration skipped.")
            return
            
        # 4. Migrate in batches of 1,000
        batch_size = 1000
        migrated_count = 0
        table_stats = {t: 0 for t in table_config.keys()}
        
        print("[Migration] Migrating data rows...")
        t_start = time.time()
        
        # O(N) 순회를 위해 offset 기반으로 청크 페칭
        offset = 0
        while offset < total_legacy_rows:
            batch_rows = legacy_query.order_by(models.DataRow.created_at.asc()).offset(offset).limit(batch_size).all()
            if not batch_rows:
                break
                
            new_objs = []
            for row in batch_rows:
                table_name = row.table_name
                table_model = models.DYNAMIC_TABLES.get(table_name)
                
                if not table_model:
                    print(f"⚠️ [Warning] Table model not found for table '{table_name}'. Skipping row '{row.row_id}'.")
                    continue
                    
                # 신규 물리 모델 인스턴스 생성
                new_row = table_model(
                    row_id=row.row_id,
                    business_key_val=row.business_key_val,
                    created_at=row.created_at,
                    updated_at=row.updated_at
                )
                
                # 기존 JSONB 'data' 안의 값을 각 컬럼 속성에 대입
                # (각 속성 값은 {"value": ..., "sources": ..., "is_overwrite": ...} 의 중첩 딕셔너리 구조를 그대로 지님)
                if isinstance(row.data, dict):
                    for col_name, cell_data in row.data.items():
                        # 메타 컬럼 제외
                        if col_name in ["row_id", "created_at", "updated_at", "business_key_val"]:
                            continue
                        # 해당 컬럼이 모델에 실제로 존재하면 대입
                        if hasattr(new_row, col_name):
                            setattr(new_row, col_name, cell_data)
                
                new_objs.append(new_row)
                table_stats[table_name] = table_stats.get(table_name, 0) + 1
            
            # 신규 테이블들에 병렬로 bulk 저장
            if new_objs:
                db.add_all(new_objs)
                db.flush() # ID 등 일시 갱신
                
            migrated_count += len(new_objs)
            offset += batch_size
            print(f"  - Migrated {migrated_count:,} / {total_legacy_rows:,} rows...")
            
        db.commit()
        t_duration = time.time() - t_start
        print(f"✅ [Migration] Data migration complete in {t_duration:.2f}s.")
        print("-" * 60)
        
        # 5. DB Level Count Verification (대조 검증)
        print("[Migration] Verifying table row counts...")
        total_new_rows = 0
        for table_name, table_model in models.DYNAMIC_TABLES.items():
            new_count = db.query(table_model).count()
            total_new_rows += new_count
            expected = table_stats.get(table_name, 0)
            print(f"  - Table '{table_name}': Count={new_count:,} (Expected={expected:,})")
            if new_count != expected:
                print(f"  ❌ [Error] Count mismatch for table '{table_name}'!")
                
        print(f"  - Total New Rows: {total_new_rows:,}")
        print(f"  - Total Legacy Rows: {total_legacy_rows:,}")
        if total_new_rows == total_legacy_rows:
            print("🎉 [Migration] Row count verification SUCCESS: 100% matched.")
        else:
            print("⚠️ [Migration] Row count verification WARNING: Mismatch detected.")
            
    except Exception as e:
        db.rollback()
        print(f"❌ [Migration] Error during migration: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()
