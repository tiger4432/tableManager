import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
table_name = 'inventory_master'
limit = 2500

print('\n--- EXPLAIN ANALYZE Search (q=1) ---')
res = db.execute(text(f"EXPLAIN SELECT row_id FROM data_rows WHERE table_name = '{table_name}' AND CAST(data AS text) ILIKE '%1%' ORDER BY business_key_val ASC LIMIT {limit}"))
for r in res:
    print(r[0])

print('\n--- EXPLAIN ANALYZE Search (q=1e) ---')
res = db.execute(text(f"EXPLAIN SELECT row_id FROM data_rows WHERE table_name = '{table_name}' AND CAST(data AS text) ILIKE '%1e%' ORDER BY business_key_val ASC LIMIT {limit}"))
for r in res:
    print(r[0])
