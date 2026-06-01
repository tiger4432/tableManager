import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, "..", "server"))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from database.database import SessionLocal
from database import models

db = SessionLocal()
try:
    # Query all audit logs created today
    logs = db.query(models.AuditLog).filter(
        models.AuditLog.timestamp >= "2026-06-02"
    ).all()
    print(f"Total audit logs created today (2026-06-02): {len(logs)}")
    for log in logs:
        print(f"ID: {log.id}, Table: {log.table_name}, Key: {log.business_key}, Column: {log.column_name}, Old: {log.old_value}, New: {log.new_value}, Source: {log.source_name}")
finally:
    db.close()
