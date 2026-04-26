import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
table_name = 'inventory_master'
limit = 2500
q = '1e'

print('--- EXPLAIN ANALYZE Search WITH ORDER BY ---')
res = db.execute(text(f"EXPLAIN ANALYZE SELECT row_id FROM data_rows WHERE table_name = '{table_name}' AND CAST(data AS text) ILIKE '%{q}%' ORDER BY row_id ASC LIMIT {limit}"))
for r in res:
    print(r[0])

print('\n--- EXPLAIN ANALYZE Search WITHOUT ORDER BY ---')
res = db.execute(text(f"EXPLAIN ANALYZE SELECT row_id FROM data_rows WHERE table_name = '{table_name}' AND CAST(data AS text) ILIKE '%{q}%' LIMIT {limit}"))
for r in res:
    print(r[0])
