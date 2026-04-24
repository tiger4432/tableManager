import os
from sqlalchemy import create_engine, text
from database.database import SQLALCHEMY_DATABASE_URL

print(f"Target DB: {SQLALCHEMY_DATABASE_URL}")
engine = create_engine(SQLALCHEMY_DATABASE_URL)

sql_commands = [
    "DROP INDEX IF EXISTS idx_table_bk;",
    "CREATE INDEX idx_table_bk ON data_rows (table_name, business_key_val, row_id);",
    "DROP INDEX IF EXISTS idx_table_updated;",
    "CREATE INDEX idx_table_updated ON data_rows (table_name, updated_at, row_id);",
    "ANALYZE data_rows;" # Update statistics for the optimizer
]

with engine.connect() as conn:
    for sql in sql_commands:
        print(f"Executing: {sql}")
        conn.execute(text(sql))
        conn.commit()

print("Indicies upgraded to Covering Indexes successfully.")
