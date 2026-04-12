import os
import sys

# 서버 루트를 path에 추가하여 내부 모듈 임포트 가능하게 함
script_dir = os.path.dirname(os.path.abspath(__file__))
server_root = os.path.abspath(os.path.join(script_dir, ".."))
sys.path.append(server_root)

from database.database import SessionLocal
from database import models, crud
from sqlalchemy.orm.attributes import flag_modified

def migrate():
    db = SessionLocal()
    table_name = "production_plan"
    
    print(f"Starting migration for {table_name}...")
    
    # 1. 대상 행 조회
    rows = db.query(models.DataRow).filter(models.DataRow.table_name == table_name).all()
    print(f"Total rows to check: {len(rows)}")
    
    # 2. 정규 컬럼명 목록 (lowercase)
    # table_config.json 에서 가져옴
    config = crud.TABLE_CONFIG.get(table_name, {})
    canonical_cols = config.get("display_columns", [])
    if not canonical_cols:
        print("No canonical columns found in config. Skipping.")
        return

    updated_count = 0
    for row in rows:
        needs_update = False
        data = row.data
        
        # 현재 행의 모든 키 추출
        current_keys = list(data.keys())
        
        for key in current_keys:
            # 대문자 필드인 경우 (단, 이미 정규 컬럼인 경우는 제외)
            if key not in canonical_cols:
                # 대소문자 무시하고 매칭되는 정규 필드 찾기
                match = None
                for c_col in canonical_cols:
                    if key.lower() == c_col.lower():
                        match = c_col
                        break
                
                if match:
                    print(f"  [Merge] Row {row.row_id}: {key} -> {match}")
                    needs_update = True
                    
                    # 소스 데이터 병합
                    if match not in data:
                        data[match] = {
                            "value": None, "is_overwrite": False, "sources": {},
                            "updated_by": "system", "priority_source": None
                        }
                    
                    # 중복 필드의 소스들을 정규 필드로 이동
                    src_sources = data[key].get("sources", {})
                    if isinstance(src_sources, dict):
                        data[match]["sources"].update(src_sources)
                    
                    # 중복 필드 삭제
                    del data[key]
                    
                    # 최종 값 재계산
                    new_val, top_src = crud.compute_priority_value(data[match]["sources"])
                    data[match]["value"] = new_val
                    data[match]["priority_source"] = top_src
                    data[match]["is_overwrite"] = ("user" in data[match]["sources"])

        if needs_update:
            flag_modified(row, "data")
            updated_count += 1

    if updated_count > 0:
        db.commit()
        print(f"Migration completed. {updated_count} rows fixed.")
    else:
        print("No data mismatch found.")
    
    db.close()

if __name__ == "__main__":
    migrate()
