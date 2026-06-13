import time
import sys
import os

# Add server directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from server.database.database import SessionLocal, engine
from server.database import models, crud

def profile():
    db = SessionLocal()
    try:
        # Load config
        config = crud.TABLE_CONFIG
        models.init_dynamic_models(config)
        table_name = "large_table_100"
        table_model = models.DYNAMIC_TABLES.get(table_name)
        if not table_model:
            print("large_table_100 table model not found")
            return
            
        print("1. Fetching 1000 rows...")
        t0 = time.time()
        rows = db.query(table_model).limit(1000).all()
        print(f"Fetch rows time: {time.time() - t0:.4f}s")
        
        if not rows:
            print("No rows found, cannot profile merge metadata")
            return
            
        row_ids = [r.row_id for r in rows]
        user_cols = [f"col_{i}" for i in range(1, 100)]
        
        print(f"2. Querying overwrites (1000 IDs) - OPTIMIZED...")
        t0 = time.time()
        overwrites = db.query(
            models.CellOverwrite.row_id,
            models.CellOverwrite.column_name,
            models.CellOverwrite.updated_by,
            models.CellOverwrite.manual_priority_source
        ).filter(
            models.CellOverwrite.table_name == table_name,
            models.CellOverwrite.row_id.in_(row_ids)
        ).all()
        overwrites_map = {}
        for row_id, column_name, updated_by, manual_priority_source in overwrites:
            overwrites_map[(row_id, column_name)] = (updated_by, manual_priority_source)
        print(f"Query overwrites and map building time: {time.time() - t0:.4f}s")
        
        print(f"3. Querying sources and Map building (1000 IDs) - BYPASSED FOR GRID PERFORMANCE...")
        t0 = time.time()
        sources_map = {} # Bypass
        print(f"Query sources and Map building time: {time.time() - t0:.4f}s")
        
        print("5. Looping and building return dict - OPTIMIZED...")
        t0 = time.time()
        data_list = []
        for row in rows:
            r_dict = row.__dict__
            r_id = r_dict.get("row_id") or row.row_id
            r_data = {}
            c_at_str = str(r_dict.get("created_at") or row.created_at)
            u_at_str = str(r_dict.get("updated_at") or row.updated_at)
            
            for col in user_cols:
                val_raw = r_dict.get(col) if col in r_dict else getattr(row, col, None)
                key = (r_id, col)
                
                ow_tuple = overwrites_map.get(key)
                col_srcs = sources_map.get(key, {})
                
                updated_by = ow_tuple[0] if ow_tuple else "system"
                manual_pin = ow_tuple[1] if ow_tuple else None
                
                r_data[col] = {
                    "value": val_raw,
                    "is_overwrite": ("user" in col_srcs) or (manual_pin is not None),
                    "sources": col_srcs,
                    "updated_by": updated_by
                }
                if manual_pin:
                    r_data[col]["manual_priority_source"] = manual_pin
            data_list.append(r_data)
        print(f"Looping time: {time.time() - t0:.4f}s")
        
    finally:
        db.close()

if __name__ == "__main__":
    profile()
