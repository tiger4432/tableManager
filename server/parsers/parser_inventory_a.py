import httpx
import json
import random

SERVER_URL = "http://127.0.0.1:8000"
TABLE_NAME = "inventory_master"
SOURCE_NAME = "parser_a"
UPDATED_BY = "agent_i_v1"

def run_parser(part_no="PN-99999", stock_qty=None):
    """
    Simulates parsing inventory data and pushes it to the server using Upsert API.
    """
    print(f"[{SOURCE_NAME}] Starting ingestion for {TABLE_NAME} (Part: {part_no})...")
    
    if stock_qty is None:
        stock_qty = random.randint(100, 999)

    # Prepare Upsert Payload
    # business_key_val will be used by the server to find the row (e.g., searching for part_no)
    payload = {
        "business_key_val": part_no,
        "updates": {
            "part_no": part_no, # Ensure the business key itself is pushed/verified
            "stock_qty": stock_qty,
            "lead_time_days": random.randint(5, 20),
            "category": "HighPriority" if stock_qty > 500 else "Normal"
        },
        "source_name": SOURCE_NAME,
        "updated_by": UPDATED_BY
    }

    # Upsert API Call
    url = f"{SERVER_URL}/tables/{TABLE_NAME}/upsert"

    try:
        response = httpx.put(url, json=payload, timeout=5.0)
        if response.status_code == 200:
            result = response.json()
            row_id = result.get("row_id")
            is_new = result.get("is_new", False)
            status = "CREATED" if is_new else "UPDATED"
            print(f"Successfully {status} row {row_id} via Upsert.")
            return result
        else:
            print(f"Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_parser()
