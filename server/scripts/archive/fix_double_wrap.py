"""
DB 복구 스크립트: 이중 래핑된 cell value 평탄화
마이그레이션 오류로 value 안에 또 다른 CellData 구조가 중첩된 경우를 수정합니다.
"""
import os, sys

script_dir = os.path.dirname(os.path.abspath(__file__))
server_root = os.path.abspath(os.path.join(script_dir, ".."))
sys.path.append(server_root)

from database.database import SessionLocal
from database import models
from sqlalchemy.orm.attributes import flag_modified

def flatten_value(val):
    """value가 또 다른 CellData dict인 경우 재귀적으로 실제 값을 추출합니다."""
    depth = 0
    while isinstance(val, dict) and "value" in val and depth < 5:
        val = val["value"]
        depth += 1
    return val

def fix_double_wrapped():
    db = SessionLocal()
    
    rows = db.query(models.DataRow).all()
    print(f"총 {len(rows)}개 행 검사 중...")
    
    fixed_count = 0
    for row in rows:
        needs_fix = False
        for key, cell in row.data.items():
            if isinstance(cell, dict) and "value" in cell:
                raw_val = cell["value"]
                flat_val = flatten_value(raw_val)
                if flat_val != raw_val:
                    print(f"  [Fix] {row.table_name}/{row.row_id}/{key}: {type(raw_val).__name__} -> {repr(flat_val)[:60]}")
                    cell["value"] = flat_val
                    needs_fix = True
        
        if needs_fix:
            flag_modified(row, "data")
            fixed_count += 1
    
    if fixed_count > 0:
        db.commit()
        print(f"[OK] Migration complete. {fixed_count} rows fixed.")
    else:
        print("[OK] No double-wrapped values found. DB is clean.")
    
    db.close()

if __name__ == "__main__":
    fix_double_wrapped()
