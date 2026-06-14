import os
import sys
import uuid
import argparse
from datetime import datetime

# Add server directory to path
script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(script_dir)

from database.database import SessionLocal, engine
from database import models

# Load dynamic models first
try:
    import json
    config_path = os.path.join(script_dir, "config", "table_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)
    models.init_dynamic_models(table_config)
except Exception as e:
    print(f"Failed to initialize dynamic models: {e}")
    sys.exit(1)


def reapply_chain_for_table(table_name: str):
    db = SessionLocal()
    try:
        model_class = models.DYNAMIC_TABLES.get(table_name)
        if not model_class:
            print(f"Error: Table model for '{table_name}' is not initialized or not found.")
            return

        rows = db.query(model_class).all()
        print(f"Found {len(rows)} rows in table '{table_name}'. Generating outbox events...")

        event_count = 0
        for row in rows:
            # 1. Build column data dict
            data_dict = {}
            for col in row.__table__.columns:
                if col.name not in ["row_id", "business_key_val", "created_at", "updated_at"]:
                    val = getattr(row, col.name, None)
                    data_dict[col.name] = {
                        "value": val,
                        "is_overwrite": False,
                        "updated_by": "system"
                    }

            # 2. Construct DatabaseOutbox record
            event_obj = models.DatabaseOutbox(
                event_uuid=str(uuid.uuid4()),
                event_type="EDIT", # Treat as edit to trigger chain rules
                table_name=table_name,
                payload={
                    "row_id": row.row_id,
                    "business_key": row.business_key_val,
                    "data": data_dict,
                    "transaction_id": f"reapply_{uuid.uuid4().hex[:8]}",
                    "updated_by": "reapply_script",
                    "source_name": "reapply_chain",
                    "timestamp": datetime.now().isoformat()
                },
                status="PENDING",
                processed_chain=False # Ensure chain worker picks it up
            )
            db.add(event_obj)
            event_count += 1

        db.commit()
        print(f"Successfully staged {event_count} outbox events to re-apply chains for table '{table_name}'.")
        print("The Chained Ingestion Worker process will automatically pick them up and execute mappers.")
    except Exception as e:
        db.rollback()
        print(f"Failed to stage events: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-apply chained ingestion rules for all existing rows in a table.")
    parser.add_argument("table_name", help="Name of the trigger table (e.g. production_plan)")
    args = parser.parse_args()
    
    reapply_chain_for_table(args.table_name)
