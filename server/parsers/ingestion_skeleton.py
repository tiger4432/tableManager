import httpx
import json
import uuid

# Configuration
SERVER_URL = "http://127.0.0.1:8000"
TABLE_NAME = "inventory_master"

def run_upsert_example():
    """
    비즈니스 키(예: part_no)를 기반으로 Upsert를 수행하는 표준 예제.
    행의 존재 여부를 미리 조회할 필요 없이, 서버가 알아서 생성 또는 업데이트를 처리합니다.
    """
    print(f"Starting Upsert ingestion for table: {TABLE_NAME}...")

    # Upsert API의 핵심은 business_key_val 입니다.
    # 서버의 TABLE_BUSINESS_KEYS 설정에 따라 inventory_master는 'part_no'를 기준으로 검색합니다.
    payload = {
        "business_key_val": "PN-2026-NEW", 
        "updates": {
            "part_no": "PN-2026-NEW",
            "category": "Electronics",
            "stock_qty": 500,
            "location": "Warehouse-C"
        },
        "source_name": "parser_skeleton",
        "updated_by": "agent_i_v2"
    }

    url = f"{SERVER_URL}/tables/{TABLE_NAME}/upsert"

    try:
        response = httpx.put(url, json=payload, timeout=10.0)
        if response.status_code == 200:
            result = response.json()
            print(f"Success: {result}")
            # result['is_new'] 가 True면 신규 생성, False면 기존 데이터 업데이트임.
        else:
            print(f"Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error during ingestion: {e}")

def run_batch_legacy():
    """
    기존의 row_id 기반 Batch Update 방식 (row_id를 이미 알고 있을 때 사용)
    """
    updates = [
        {
            "row_id": "TARGET-UUID", 
            "column_name": "stock_qty",
            "value": 100,
            "source_name": "parser_legacy"
        }
    ]
    url = f"{SERVER_URL}/tables/{TABLE_NAME}/cells/batch"
    # ... 호출 로직 ...

if __name__ == "__main__":
    print("[Ingestion Agent Skeleton v2 Started]")
    run_upsert_example()
