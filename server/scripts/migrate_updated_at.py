import sys
import os
import time

# Add server path to sys.path to import database
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from database.database import SessionLocal, engine
from database.models import DataRow
from sqlalchemy import update, func

def migrate():
    print("Starting migration to populate NULL updated_at values...")
    t0 = time.time()
    db = SessionLocal()
    try:
        # PostgreSQL-optimized bulk update
        stmt = update(DataRow).where(DataRow.updated_at == None).values(updated_at=DataRow.created_at)
        result = db.execute(stmt)
        db.commit()
        print(f"Migration completed in {time.time() - t0:.3f}s. Rows updated: {result.rowcount}")
    except Exception as e:
        print(f"Migration failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
