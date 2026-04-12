import sys
import os
import sqlite3

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from parsers.generic_ingester import GenericIngester

def verify_advanced_ingestion():
    base_dir = "server/ingestion_workspace/inventory_master"
    config_path = os.path.join(base_dir, "config", "config.json")
    log_path = os.path.join(base_dir, "raws", "sample_batch.log")
    
    print("=== Advanced Ingestion Verification ===")
    
    # 1. Run Ingester
    ingester = GenericIngester(config_path)
    ingester.process_file(log_path)
    
    print("\n=== Database Verification (AuditLog) ===")
    # 2. Check Database for Tags
    db_path = "server/assy_manager.db"
    if not os.path.exists(db_path):
        # Try finding it in the server dir
        db_path = os.path.join("server", "assy_manager.db")
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Query logs for the newly added parts and check if dept_code/batch_id are present
    # Since these are in 'data' JSON field in DataRow, but AuditLog records specific column updates.
    # The Ingester pushes ALL fields in the 'updates' dict.
    
    target_parts = ["PN-TEST-001", "PN-TEST-002", "PN-TEST-003"]
    
    for part in target_parts:
        print(f"\nChecking logs for {part}:")
        # Find row_id for the part
        cursor.execute("SELECT row_id, data FROM data_rows WHERE table_name='inventory_master'")
        rows = cursor.fetchall()
        row_id = None
        for r_id, r_data in rows:
            import json
            data = json.loads(r_data)
            if data.get("part_no", {}).get("value") == part:
                row_id = r_id
                break
        
        if not row_id:
            print(f"  [ERROR] Row for {part} not found!")
            continue
            
        # Check AuditLog for batch_id and dept_code
        cursor.execute("""
            SELECT column_name, new_value 
            FROM audit_logs 
            WHERE row_id = ? AND column_name IN ('batch_id', 'dept_code')
        """, (row_id,))
        logs = cursor.fetchall()
        
        if logs:
            for col, val in logs:
                print(f"  [OK] {col}: {val}")
        else:
            print("  [ERROR] No header tags found in AuditLog!")
            
    conn.close()

if __name__ == "__main__":
    verify_advanced_ingestion()
