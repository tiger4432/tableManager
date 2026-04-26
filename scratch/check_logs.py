from sqlalchemy.orm import Session
from server.database.database import SessionLocal
from server.database import models
from sqlalchemy import desc

db = SessionLocal()
try:
    logs = db.query(models.AuditLog).order_by(desc(models.AuditLog.id)).limit(20).all()
    print(f"{'ID':<10} | {'TX_ID':<40} | {'ROW_ID':<40} | {'TIMESTAMP'}")
    print("-" * 120)
    for log in logs:
        print(f"{log.id:<10} | {str(log.transaction_id):<40} | {log.row_id:<40} | {log.timestamp}")
finally:
    db.close()
