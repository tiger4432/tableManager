import sys
import os
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from database.database import SessionLocal
from database import models
from utils.time_utils import to_local_str

def profile():
    db = SessionLocal()
    limit = 1000
    skip = 0
    table_name = "inventory_master"

    print(f"--- Profiling Fetch limit={limit} ---")
    
    # 1. ID Scan
    t0 = time.time()
    id_results = db.query(models.DataRow.row_id)\
                   .filter(models.DataRow.table_name == table_name)\
                   .order_by(models.DataRow.updated_at.desc())\
                   .limit(limit).all()
    id_list = [r[0] for r in id_results]
    t1 = time.time()
    print(f"[Phase 1] ID Scan: {t1-t0:.4f}s")
    
    # 2. ORM Fetch
    t0 = time.time()
    rows = db.query(models.DataRow).filter(models.DataRow.row_id.in_(id_list)).all()
    id_to_idx = {rid: i for i, rid in enumerate(id_list)}
    rows.sort(key=lambda x: id_to_idx.get(x.row_id, 999999))
    t1 = time.time()
    print(f"[Phase 2] ORM Fetch & Sort: {t1-t0:.4f}s")

    # 3. Entity Fetch
    t0 = time.time()
    raw_rows = db.query(
        models.DataRow.row_id, 
        models.DataRow.table_name, 
        models.DataRow.data, 
        models.DataRow.created_at, 
        models.DataRow.updated_at
    ).filter(models.DataRow.row_id.in_(id_list)).all()
    raw_rows.sort(key=lambda x: id_to_idx.get(x[0], 999999))
    t1 = time.time()
    print(f"[Phase 2] Entity Fetch & Sort: {t1-t0:.4f}s")
    
    # 4. ORM Dict Conversion
    t0 = time.time()
    data_list_orm = []
    for row in rows:
        data_list_orm.append({
            "row_id": row.row_id, 
            "table_name": row.table_name, 
            "data": row.data,
            "created_at": to_local_str(row.created_at), 
            "updated_at": to_local_str(row.updated_at)
        })
    t1 = time.time()
    print(f"[Phase 3] ORM Dict Conversion: {t1-t0:.4f}s")

    # 5. Entity Dict Conversion
    t0 = time.time()
    data_list_entity = []
    for r_id, t_name, r_data, c_at, u_at in raw_rows:
        c_at_str = to_local_str(c_at)
        u_at_str = to_local_str(u_at if u_at else c_at)
        if "created_at" not in r_data:
            r_data["created_at"] = {"value": c_at_str, "is_overwrite": False, "updated_by": "system"}
        if "updated_at" not in r_data:
            r_data["updated_at"] = {"value": u_at_str, "is_overwrite": False, "updated_by": "system"}
        else:
            r_data["updated_at"]["value"] = u_at_str
            
        data_list_entity.append({
            "row_id": r_id, 
            "table_name": t_name, 
            "data": r_data,
            "created_at": c_at_str, 
            "updated_at": u_at_str
        })
    t1 = time.time()
    print(f"[Phase 3] Entity Dict Conversion: {t1-t0:.4f}s")

if __name__ == "__main__":
    profile()
