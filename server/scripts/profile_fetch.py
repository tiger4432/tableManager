import sys
import os
import time

os.environ["TESTING"] = "True"
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from database.database import engine, SessionLocal
from database import models, crud
from sqlalchemy import func

def seed_data_if_empty(db, table_model):
    count = db.query(table_model).count()
    if count > 0:
        return
        
    print("Table is empty. Seeding 1,000 rows of 100 columns...")
    import uuid
    
    rows = []
    for r in range(1, 1001):
        row_id = str(uuid.uuid4())
        kwargs = {
            "row_id": row_id,
            "business_key_val": f"ITEM_{r:04d}",
            "created_at": func.now(),
            "updated_at": func.now()
        }
        for i in range(1, 100):
            val = r * 10 + i if i % 2 != 0 else f"str_{r}_{i}"
            kwargs[f"col_{i}"] = {
                "value": val,
                "is_overwrite": False,
                "sources": {
                    "system": {"value": val, "timestamp": "2026-06-13T19:00:00", "updated_by": "system"}
                },
                "updated_by": "system"
            }
        row = table_model(**kwargs)
        rows.append(row)
        
    db.add_all(rows)
    db.commit()
    print("Seeding completed.")

def profile():
    # 1. table_config 로드 및 dynamic models 초기화
    import json
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(script_dir, "config", "table_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)
    models.init_dynamic_models(table_config)

    db = SessionLocal()
    table_name = "large_table_100"
    table_model = models.DYNAMIC_TABLES.get(table_name)

    if not table_model:
        print(f"Error: Table model for '{table_name}' not found.")
        sys.exit(1)

    seed_data_if_empty(db, table_model)

    limit = 1000
    # Fetch IDs first
    id_results = db.query(table_model.row_id)\
                   .order_by(table_model.updated_at.desc())\
                   .limit(limit).all()
    id_list = [r[0] for r in id_results]
    
    if not id_list:
        print("No data found in database.")
        return

    print(f"--- Profiling Fetch Methods limit={limit} ---")
    id_to_idx = {rid: i for i, rid in enumerate(id_list)}
    
    cfg = crud.TABLE_CONFIG.get(table_name, {})
    col_types = cfg.get("column_types", {})
    user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]

    # Method 1: Current jsonb_build_object approach
    try:
        t0 = time.time()
        entities = [
            table_model.row_id,
            table_model.created_at,
            table_model.updated_at
        ]
        for col in user_cols:
            col_attr = getattr(table_model, col)
            entities.append(
                func.jsonb_build_object(
                    "value", col_attr["value"],
                    "is_overwrite", col_attr["is_overwrite"],
                    "updated_by", col_attr["updated_by"]
                )
            )

        raw_rows_m1 = db.query(*entities).filter(table_model.row_id.in_(id_list)).all()
        raw_rows_m1.sort(key=lambda x: id_to_idx.get(x[0], 999999))
        t1 = time.time()
        print(f"[Method 1 (jsonb_build_object)] Fetch time: {t1-t0:.4f}s")
    except Exception as e:
        print(f"[Method 1] Failed: {e}")

    # Method 2: Raw columns fetch (without jsonb_build_object)
    try:
        t0 = time.time()
        entities = [
            table_model.row_id,
            table_model.created_at,
            table_model.updated_at
        ]
        for col in user_cols:
            entities.append(getattr(table_model, col))

        raw_rows_m2 = db.query(*entities).filter(table_model.row_id.in_(id_list)).all()
        raw_rows_m2.sort(key=lambda x: id_to_idx.get(x[0], 999999))
        t1 = time.time()
        print(f"[Method 2 (Raw columns)] Fetch & Sort time: {t1-t0:.4f}s")

        # Test dict conversion speed for Method 2
        t0_dict = time.time()
        data_list = []
        from main import to_local_str
        from datetime import datetime
        for row in raw_rows_m2:
            r_id = row[0]
            c_at_val = row[1]
            u_at_val = row[2]
            
            c_at_str = to_local_str(c_at_val) if isinstance(c_at_val, datetime) else (c_at_val or "")
            u_at_str = to_local_str(u_at_val) if isinstance(u_at_val, datetime) else (u_at_val or "")
            
            r_data = {}
            for idx, col in enumerate(user_cols):
                val = row[3 + idx]
                if val is None:
                    val = {"value": None, "is_overwrite": False, "sources": {}, "updated_by": "system"}
                else:
                    # sources를 제외한 형태로 가공
                    val = {
                        "value": val.get("value"),
                        "is_overwrite": val.get("is_overwrite", False),
                        "updated_by": val.get("updated_by", "system")
                    }
                r_data[col] = val
                
            r_data["created_at"] = {"value": c_at_str, "is_overwrite": False, "updated_by": "system"}
            r_data["updated_at"] = {"value": u_at_str, "is_overwrite": False, "updated_by": "system"}
                
            data_list.append({
                "row_id": r_id, 
                "table_name": table_name, 
                "data": r_data,
                "created_at": c_at_str, 
                "updated_at": u_at_str
            })
        t1_dict = time.time()
        print(f"[Method 2] Dict Conversion time: {t1_dict-t0_dict:.4f}s")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Method 2] Failed: {e}")

    # Method 3: row_to_json approach (raw SQL)
    try:
        t0 = time.time()
        from sqlalchemy import text
        # PostgreSQL row_to_json on table
        sql = text(f"SELECT row_to_json(t) FROM {table_name} t WHERE t.row_id = ANY(:ids)")
        res = db.execute(sql, {"ids": id_list}).all()
        raw_rows_m3 = [r[0] for r in res]
        # sort in memory
        raw_rows_m3.sort(key=lambda x: id_to_idx.get(x.get("row_id"), 999999))
        t1 = time.time()
        print(f"[Method 3 (row_to_json raw SQL)] Fetch & Sort time: {t1-t0:.4f}s")
        
        # Test dict conversion speed for Method 3
        t0_dict = time.time()
        data_list = []
        for row_dict in raw_rows_m3:
            r_id = row_dict["row_id"]
            # row_to_json outputs timestamps as string
            c_at_str = row_dict.get("created_at") or ""
            u_at_str = row_dict.get("updated_at") or ""
            
            # format ISO string to "YYYY-MM-DD HH:MM:SS" if needed, or keep it
            # To match the main output, we can replace T and slice:
            c_at_str = c_at_str.replace("T", " ").split("+")[0][:19]
            u_at_str = u_at_str.replace("T", " ").split("+")[0][:19]
            
            r_data = {}
            for col in user_cols:
                val = row_dict.get(col)
                if val is None:
                    val = {"value": None, "is_overwrite": False, "sources": {}, "updated_by": "system"}
                else:
                    val = {
                        "value": val.get("value"),
                        "is_overwrite": val.get("is_overwrite", False),
                        "updated_by": val.get("updated_by", "system")
                    }
                r_data[col] = val
                
            r_data["created_at"] = {"value": c_at_str, "is_overwrite": False, "updated_by": "system"}
            r_data["updated_at"] = {"value": u_at_str, "is_overwrite": False, "updated_by": "system"}
            
            data_list.append({
                "row_id": r_id,
                "table_name": table_name,
                "data": r_data,
                "created_at": c_at_str,
                "updated_at": u_at_str
            })
        t1_dict = time.time()
        print(f"[Method 3] Dict Conversion time: {t1_dict-t0_dict:.4f}s")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Method 3] Failed: {e}")

    # Method 4: JSONB Deletion operator (col - 'sources')
    try:
        t0 = time.time()
        entities = [
            table_model.row_id,
            table_model.created_at,
            table_model.updated_at
        ]
        for col in user_cols:
            col_attr = getattr(table_model, col)
            # Subtract 'sources' key from JSONB
            entities.append(col_attr - 'sources')

        raw_rows_m4 = db.query(*entities).filter(table_model.row_id.in_(id_list)).all()
        raw_rows_m4.sort(key=lambda x: id_to_idx.get(x[0], 999999))
        t1 = time.time()
        print(f"[Method 4 (col - 'sources')] Fetch & Sort time: {t1-t0:.4f}s")

        # Test dict conversion speed for Method 4
        t0_dict = time.time()
        data_list = []
        from main import to_local_str
        from datetime import datetime
        for row in raw_rows_m4:
            r_id = row[0]
            c_at_val = row[1]
            u_at_val = row[2]
            
            c_at_str = to_local_str(c_at_val) if isinstance(c_at_val, datetime) else (c_at_val or "")
            u_at_str = to_local_str(u_at_val) if isinstance(u_at_val, datetime) else (u_at_val or "")
            
            r_data = {}
            for idx, col in enumerate(user_cols):
                val = row[3 + idx]
                if val is None:
                    val = {"value": None, "is_overwrite": False, "sources": {}, "updated_by": "system"}
                # sources is already removed by PostgreSQL '-' operator
                r_data[col] = val
                
            r_data["created_at"] = {"value": c_at_str, "is_overwrite": False, "updated_by": "system"}
            r_data["updated_at"] = {"value": u_at_str, "is_overwrite": False, "updated_by": "system"}
                
            data_list.append({
                "row_id": r_id, 
                "table_name": table_name, 
                "data": r_data,
                "created_at": c_at_str, 
                "updated_at": u_at_str
            })
        t1_dict = time.time()
        print(f"[Method 4] Dict Conversion time: {t1_dict-t0_dict:.4f}s")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Method 4] Failed: {e}")

    # Method 5: Combined (row_to_json + col - 'sources')
    try:
        t0 = time.time()
        from sqlalchemy import text
        cols_sub = ", ".join([f"\"{col}\" - 'sources' AS \"{col}\"" for col in user_cols])
        sql = text(f"""
            SELECT row_to_json(sub) 
            FROM (
                SELECT row_id, created_at, updated_at, {cols_sub}
                FROM "{table_name}"
                WHERE row_id = ANY(:ids)
            ) sub
        """)
        res = db.execute(sql, {"ids": id_list}).all()
        raw_rows_m5 = [r[0] for r in res]
        raw_rows_m5.sort(key=lambda x: id_to_idx.get(x.get("row_id"), 999999))
        t1 = time.time()
        print(f"[Method 5 (Combined)] Fetch & Sort time: {t1-t0:.4f}s")

        # Test dict conversion speed for Method 5
        t0_dict = time.time()
        data_list = []
        for row_dict in raw_rows_m5:
            r_id = row_dict["row_id"]
            c_at_raw = row_dict.get("created_at") or ""
            u_at_raw = row_dict.get("updated_at") or ""
            
            c_at_str = c_at_raw.replace("T", " ").split("+")[0][:19]
            u_at_str = u_at_raw.replace("T", " ").split("+")[0][:19]
            
            r_data = {}
            for col in user_cols:
                val = row_dict.get(col)
                if val is None:
                    val = {"value": None, "is_overwrite": False, "sources": {}, "updated_by": "system"}
                # sources is already removed in SQL level
                r_data[col] = val
                
            r_data["created_at"] = {"value": c_at_str, "is_overwrite": False, "updated_by": "system"}
            r_data["updated_at"] = {"value": u_at_str, "is_overwrite": False, "updated_by": "system"}
            
            data_list.append({
                "row_id": r_id,
                "table_name": table_name,
                "data": r_data,
                "created_at": c_at_str,
                "updated_at": u_at_str
            })
        t1_dict = time.time()
        print(f"[Method 5] Dict Conversion time: {t1_dict-t0_dict:.4f}s")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Method 5] Failed: {e}")

if __name__ == "__main__":
    profile()
