import sys
import os
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
table_name = 'inventory_master'
limit = 2503
skip = 6870
q = '1e'

print('--- Test Default work_mem ---')
t0 = time.time()
db.execute(text("SET LOCAL work_mem = '4MB'")) # PostgreSQL default is 4MB
res = db.execute(text(f"SELECT row_id FROM data_rows WHERE table_name = '{table_name}' AND CAST(data AS text) ILIKE '%{q}%' ORDER BY business_key_val ASC LIMIT {limit} OFFSET {skip}")).fetchall()
t1 = time.time()
print(f"4MB work_mem Time: {t1-t0:.4f}s")

print('\n--- Test 64MB work_mem ---')
t0 = time.time()
db.execute(text("SET LOCAL work_mem = '64MB'"))
res = db.execute(text(f"SELECT row_id FROM data_rows WHERE table_name = '{table_name}' AND CAST(data AS text) ILIKE '%{q}%' ORDER BY business_key_val ASC LIMIT {limit} OFFSET {skip}")).fetchall()
t1 = time.time()
print(f"64MB work_mem Time: {t1-t0:.4f}s")

db.commit()
db.close()
