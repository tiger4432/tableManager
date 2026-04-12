import httpx
import time
import sys
import os

SERVER_URL = "http://127.0.0.1:8000"
TABLE_NAME = "inventory_master"
TEST_PART_NO = "PN-V2-TEST-999"

def verify_upsert_scenario():
    print("=== Agent I v2: Upsert Ingestion Verification ===")
    
    # 1. First run: Clean Insert
    print(f"\n[Step 1] First ingestion for part: {TEST_PART_NO}")
    payload = {
        "business_key_val": TEST_PART_NO,
        "updates": {
            "part_no": TEST_PART_NO,
            "stock_qty": 555,
            "category": "NewArrival"
        },
        "source_name": "parser_a",
        "updated_by": "agent_i_v2"
    }
    
    resp1 = httpx.put(f"{SERVER_URL}/tables/{TABLE_NAME}/upsert", json=payload)
    if resp1.status_code == 200:
        res = resp1.json()
        row_id = res['row_id']
        is_new = res['is_new']
        print(f"Result: Created={is_new}, RowID={row_id}")
    else:
        print(f"Error Step 1: {resp1.status_code} - {resp1.text}")
        return

    # 2. Second run: Update existing
    print(f"\n[Step 2] Second ingestion for same part: {TEST_PART_NO} (stock 555 -> 777)")
    payload["updates"]["stock_qty"] = 777
    
    resp2 = httpx.put(f"{SERVER_URL}/tables/{TABLE_NAME}/upsert", json=payload)
    if resp2.status_code == 200:
        res = resp2.json()
        row_id2 = res['row_id']
        is_new2 = res['is_new']
        print(f"Result: Created={is_new2}, RowID={row_id2}")
        
        if is_new2:
            print("[FAILED] Row was created again instead of being updated.")
        elif row_id != row_id2:
            print("[FAILED] RowID changed during update.")
        else:
            print("[SUCCESS] Row updated correctly without duplication.")
    else:
        print(f"Error Step 2: {resp2.status_code} - {resp2.text}")
        return

    # 3. Verify history
    print(f"\n[Step 3] Verifying history for RowID: {row_id}")
    history_resp = httpx.get(f"{SERVER_URL}/tables/{TABLE_NAME}/rows/{row_id}/history")
    if history_resp.status_code == 200:
        logs = history_resp.json()
        print(f"Total history logs found: {len(logs)}")
        p_a_logs = [l for l in logs if l['source_name'] == 'parser_a']
        print(f"Logs from 'parser_a': {len(p_a_logs)}")
        if len(p_a_logs) >= 3: 
            print("[SUCCESS] History logs recorded correctly.")
        else:
            print(f"Warning: Expected more logs, got {len(p_a_logs)}")
    else:
        print(f"Error Step 3: {history_resp.status_code}")

if __name__ == "__main__":
    verify_upsert_scenario()
