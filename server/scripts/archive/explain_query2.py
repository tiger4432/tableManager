import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
table_name = 'inventory_master'
limit = 1000

print('--- EXPLAIN ANALYZE Sort OFF (row_id ASC) ---')
res = db.execute(text(f"EXPLAIN ANALYZE SELECT row_id FROM data_rows WHERE table_name = '{table_name}' ORDER BY row_id ASC LIMIT {limit}"))
for r in res:
    print(r[0])

print('\n--- EXPLAIN ANALYZE Search (q=test) ---')
res = db.execute(text(f"EXPLAIN ANALYZE SELECT row_id FROM data_rows WHERE table_name = '{table_name}' AND CAST(data AS text) ILIKE '%test%' ORDER BY updated_at DESC, row_id DESC LIMIT {limit}"))
for r in res:
    print(r[0])
