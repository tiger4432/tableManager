import sys
import os

# Ensure server path is available
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.database import engine
from sqlalchemy import text

def drop_legacy_table():
    print("Connecting to PostgreSQL and dropping legacy 'data_rows' table...")
    with engine.connect() as conn:
        try:
            conn.execute(text("DROP TABLE IF EXISTS data_rows CASCADE;"))
            conn.commit()
            print("Successfully dropped legacy 'data_rows' table and associated indexes/constraints.")
        except Exception as e:
            print(f"Error dropping 'data_rows' table: {e}")
            sys.exit(1)

if __name__ == "__main__":
    drop_legacy_table()
