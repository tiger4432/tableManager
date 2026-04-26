import time
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from database.database import SQLALCHEMY_DATABASE_URL
from database import models
import os

engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///assy_manager.db"))
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

table_name = "inventory_master"
skip = 73062
limit = 891

print(f"Profiling query for {table_name}, skip={skip}, limit={limit}...")

# 1. Original Query
start = time.time()
query = db.query(models.DataRow).filter(models.DataRow.table_name == table_name)
bk_null_last = (models.DataRow.business_key_val == None).asc()
bk_sort = models.DataRow.business_key_val.asc()
results = query.order_by(bk_null_last, bk_sort, models.DataRow.row_id.asc()).offset(skip).limit(limit).all()
print(f"Original DB Fetch time: {time.time() - start:.3f}s")

# 2. Optimized Query (Late Row Lookup)
start = time.time()
# First, just fetch IDs
subquery = db.query(models.DataRow.row_id).filter(models.DataRow.table_name == table_name)
subquery = subquery.order_by(bk_null_last, bk_sort, models.DataRow.row_id.asc()).offset(skip).limit(limit).subquery()

# Then fetch full rows using IDs
optimized_results = db.query(models.DataRow).join(subquery, models.DataRow.row_id == subquery.c.row_id).all()
# Need to sort again because join might lose order
optimized_results.sort(key=lambda x: (x.business_key_val is None, x.business_key_val, x.row_id))

print(f"Optimized DB Fetch time: {time.time() - start:.3f}s")

db.close()
