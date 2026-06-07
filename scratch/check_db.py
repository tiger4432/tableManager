import sys
import os

# Add server to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))

from database.database import SessionLocal
from database import models

def main():
    db = SessionLocal()
    try:
        # Check outbox size
        total_outbox = db.query(models.DatabaseOutbox).count()
        pending_outbox = db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain == False).count()
        print(f"Total outbox events: {total_outbox}")
        print(f"Pending chain ingestion events: {pending_outbox}")
        
        # Look at the last 10 outbox events
        print("\nLast 10 outbox events:")
        recent_events = db.query(models.DatabaseOutbox).order_by(models.DatabaseOutbox.id.desc()).limit(10).all()
        for e in recent_events:
            print(f"ID: {e.id}, EventType: {e.event_type}, Table: {e.table_name}, ProcessedChain: {e.processed_chain}, Source: {e.payload.get('source_name')}, Tx: {e.payload.get('transaction_id')}")
            
        # Look at recent audit logs
        print("\nRecent 10 Audit Logs:")
        recent_logs = db.query(models.AuditLog).order_by(models.AuditLog.id.desc()).limit(10).all()
        for l in recent_logs:
            print(f"ID: {l.id}, Table: {l.table_name}, Col: {l.column_name}, Old: {l.old_value}, New: {l.new_value}, Source: {l.source_name}, User: {l.updated_by}, Tx: {l.transaction_id}")
            
    except Exception as e:
        print(f"Error checking database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
