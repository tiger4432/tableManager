from sqlalchemy import create_engine, text
import os

DEFAULT_PG_URL = "postgresql://postgres:admin@localhost:5432/assy_manager"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_PG_URL)

def migrate():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print("[Migration] Adding transaction_id column to audit_logs...")
        try:
            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN transaction_id VARCHAR;"))
            conn.execute(text("CREATE INDEX idx_audit_logs_tx_id ON audit_logs (transaction_id);"))
            conn.commit()
            print("[Migration] Success!")
        except Exception as e:
            print(f"[Migration] Error or already exists: {e}")

if __name__ == "__main__":
    migrate()
