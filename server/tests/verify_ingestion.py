import httpx
import time
import sys
import os

# Add parent directory to path to import parser if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from parsers.parser_inventory_a import run_parser

SERVER_URL = "http://127.0.0.1:8000"
TABLE_NAME = "inventory_master"

def verify_multi_source():
    print("=== Multi-Source Ingestion Verification ===")
    
    # 1. Get a target row
    resp = httpx.get(f"{SERVER_URL}/tables/{TABLE_NAME}/data?limit=1")
    if resp.status_code != 200 or not resp.json()["data"]:
        print("Error: Could not find data to test. Seed the database first.")
        print(f"Status: {resp.status_code}, Response: {resp.text}")
        return
    
    row = resp.json()["data"][0]
    row_id = row["row_id"]
    print(f"Target Row ID: {row_id}")

    # 2. Scenario 1: User Overwrite
    # We'll set 'category' manually as 'user' source
    user_val = "USER_FIXED_VALUE"
    print(f"\n[Step 1] User updates 'category' to '{user_val}'")
    update_payload = {
        "updates": [
            {
                "row_id": row_id,
                "column_name": "category",
                "value": user_val,
                "source_name": "user",
                "updated_by": "test_script"
            }
        ]
    }
    httpx.put(f"{SERVER_URL}/tables/{TABLE_NAME}/cells/batch", json=update_payload)

    # 3. Scenario 2: Parser Update on the same cell
    parser_val = "PARSER_VALUE"
    print(f"[Step 2] Parser attempts to update 'category' to '{parser_val}'")
    parser_payload = {
        "updates": [
            {
                "row_id": row_id,
                "column_name": "category",
                "value": parser_val,
                "source_name": "parser_a",
                "updated_by": "agent_i_v1"
            }
        ]
    }
    httpx.put(f"{SERVER_URL}/tables/{TABLE_NAME}/cells/batch", json=parser_payload)

    # 4. Check results
    resp = httpx.get(f"{SERVER_URL}/tables/{TABLE_NAME}/{row_id}")
    cell = resp.json()["data"]["category"]
    
    print("\n[Result Check]")
    print(f"Final Value: {cell['value']} (Expected: {user_val})")
    print(f"Sources: {cell['sources']}")
    # In schemas.py, is_overwrite is basically 'user' in sources
    print(f"Is Overwrite: {cell['is_overwrite']} (Expected: True)")
    print(f"Priority Source: {cell['priority_source']} (Expected: user)")

    if cell['value'] == user_val and cell['sources'].get('parser_a') == parser_val:
        print("\n[SUCCESS] Scenario 1: User value takes priority.")
    else:
        print("\n[FAILED] Scenario 1.")

    # 5. Scenario 3: Parser update on a cell WITHOUT user value
    print(f"\n[Step 3] Parser updates 'stock_qty' (no user value)")
    new_qty = 9999
    parser_payload_2 = {
        "updates": [
            {
                "row_id": row_id,
                "column_name": "stock_qty",
                "value": new_qty,
                "source_name": "parser_a",
                "updated_by": "agent_i_v1"
            }
        ]
    }
    httpx.put(f"{SERVER_URL}/tables/{TABLE_NAME}/cells/batch", json=parser_payload_2)

    resp = httpx.get(f"{SERVER_URL}/tables/{TABLE_NAME}/{row_id}")
    cell_qty = resp.json()["data"]["stock_qty"]
    
    print("\n[Result Check]")
    print(f"Final Value: {cell_qty['value']} (Expected: {new_qty})")
    print(f"Priority Source: {cell_qty['priority_source']} (Expected: parser_a)")

    if cell_qty['value'] == new_qty:
        print("\n[SUCCESS] Scenario 2: Parser value reflected directly.")
    else:
        print("\n[FAILED] Scenario 2.")

if __name__ == "__main__":
    verify_multi_source()
