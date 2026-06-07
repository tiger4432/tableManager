import sys
import os

# Add server to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))

from database.database import SessionLocal
from database import schemas, crud

def test():
    db = SessionLocal()
    try:
        # Create a dummy batch update to inventory_master
        batch_data = schemas.GeneralUpdateBatch(
            updates=[
                {
                    "business_key_val": "INV_MAT_STEEL_01",
                    "updates": {
                        "stock_qty": 999
                    },
                    "source_name": "chain_ingestion",
                    "updated_by": "chain_worker"
                }
            ],
            transaction_id="chain_test_tx_123",
            silent=False
        )
        
        # Apply updates
        results, changed_cells, created_logs = crud.apply_batch_updates(db, "inventory_master", batch_data)
        print("RESULTS SIZE:", len(results))
        print("CHANGED CELLS:", changed_cells)
        print("CREATED LOGS:", created_logs)
        
        # Rollback so we don't mess up real data
        db.rollback()
    except Exception as e:
        print("ERROR:", e)
    finally:
        db.close()

if __name__ == "__main__":
    test()
