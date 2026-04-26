import sys
import os
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
table_name = 'inventory_master'
limit = 2500
q = '1e'

print('--- Test CTE Early Exit ---')
query = f"""
WITH matched AS (
    SELECT row_id, updated_at FROM data_rows 
    WHERE table_name = '{table_name}' AND CAST(data AS text) ILIKE '%{q}%'
    LIMIT 10000
)
SELECT row_id FROM matched
ORDER BY updated_at DESC
LIMIT {limit}
"""

t0 = time.time()
res = db.execute(text(query)).fetchall()
t1 = time.time()
print(f"CTE Query Time: {t1-t0:.4f}s. Rows returned: {len(res)}")
