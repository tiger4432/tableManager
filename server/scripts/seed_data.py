import sys
import os
import uuid
import random
import json
from datetime import datetime, timedelta
from sqlalchemy import text

# [경로 보정] scripts 폴더로 이동됨에 따라 상위 폴더(server/)를 path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
server_root = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.append(server_root)

from database.database import SessionLocal, engine
from database import models

def clear_db(table_config):
    db = SessionLocal()
    print("Clearing existing metadata tables...")
    try:
        db.query(models.CellOverwrite).delete()
        db.query(models.CellSource).delete()
        db.query(models.AuditLog).delete()
        
        for table_name in table_config.keys():
            table_model = models.DYNAMIC_TABLES.get(table_name)
            if table_model:
                print(f"Clearing dynamic table: {table_name}...")
                db.query(table_model).delete()
                
        db.commit()
        print("Database cleared.")
    except Exception as e:
        db.rollback()
        print(f"Failed to clear database: {e}")
    finally:
        db.close()

def seed_row(db, table_name, row_id, business_key_val, data_dict, source_name="system", updated_by="system"):
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        return
        
    # 1. Native row insert
    db_row = table_model(
        row_id=row_id,
        business_key_val=business_key_val,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    for col, val in data_dict.items():
        if hasattr(db_row, col):
            setattr(db_row, col, val)
            
    db.add(db_row)
    
    # 2. Cell sources insertion
    for col, val in data_dict.items():
        if col in ["created_at", "updated_at"]:
            continue
        cell_src = models.CellSource(
            table_name=table_name,
            row_id=row_id,
            column_name=col,
            source_name=source_name,
            value=val,
            updated_by=updated_by,
            ingested_at=datetime.now()
        )
        db.add(cell_src)

def seed():
    # Load table config and init dynamic models
    config_path = os.path.join(server_root, "config", "table_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)
    models.init_dynamic_models(table_config)
    
    # Clear DB first
    clear_db(table_config)
    
    db = SessionLocal()
    try:
        # 1. Seeding inventory_master (1000 rows)
        print("Seeding inventory_master (1000 rows)...")
        categories = ["IC", "Passive", "Connector", "Mechanical", "PCB"]
        locations = ["Warehouse-A", "Warehouse-B", "Line-1-Shelf", "Line-2-Shelf"]
        for i in range(1, 1001):
            row_id = str(uuid.uuid4())
            part_no = f"PN-{10000+i}"
            data = {
                "part_no": part_no,
                "category": random.choice(categories),
                "stock_qty": float(random.randint(0, 5000)),
                "unit_price": round(random.uniform(0.1, 500.0), 2)
            }
            seed_row(db, "inventory_master", row_id, part_no, data)

        # 2. Seeding production_plan (500 rows)
        print("Seeding production_plan (500 rows)...")
        models_list = ["Model-X", "Model-Y", "Model-Z", "Alpha-1", "Beta-2"]
        lines = ["Line-A", "Line-B", "Line-C"]
        start_date = datetime.now()
        for i in range(1, 501):
            row_id = str(uuid.uuid4())
            plan_id = f"PLN-{20260000+i}"
            data = {
                "plan_id": plan_id,
                "prod_line": random.choice(lines),
                "model_name": random.choice(models_list),
                "target_qty": float(random.choice([50, 100, 200, 500])),
                "due_date": (start_date + timedelta(days=i//10)).strftime("%Y-%m-%d")
            }
            seed_row(db, "production_plan", row_id, plan_id, data)

        # 3. Seeding large_table_100 (100 rows)
        print("Seeding large_table_100 (100 rows)...")
        for i in range(1, 101):
            row_id = str(uuid.uuid4())
            item_id = f"ITEM-{str(i).zfill(3)}"
            data = {
                "item_id": item_id
            }
            # Fill 10-20 random cols for large table
            for col_idx in range(1, 100):
                col_name = f"col_{col_idx}"
                if random.random() > 0.5:
                    if col_idx % 2 == 0:
                        data[col_name] = f"Val-{random.randint(1, 100)}"
                    else:
                        data[col_name] = float(random.randint(10, 1000))
            seed_row(db, "large_table_100", row_id, item_id, data)

        db.commit()
        print("Seed complete.")
        
        # Verify row counts
        for table_name in table_config.keys():
            table_model = models.DYNAMIC_TABLES.get(table_name)
            if table_model:
                count = db.query(table_model).count()
                print(f"Table {table_name}: {count} rows")
    except Exception as e:
        db.rollback()
        print(f"Failed to seed data: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
