import sys
import os
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from database.database import SessionLocal
from sqlalchemy import text

def create_index():
    print("Creating index idx_table_rowid...")
    t0 = time.time()
    db = SessionLocal()
    try:
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_table_rowid ON data_rows (table_name, row_id)"))
        db.commit()
        print(f"Index created in {time.time() - t0:.3f}s")
    except Exception as e:
        print(f"Failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_index()
