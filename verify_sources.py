import httpx
import json

def test_source_management():
    base_url = "http://127.0.0.1:8000"
    table_name = "inventory_master"
    
    # 1. Create a row first
    res = httpx.post(f"{base_url}/tables/{table_name}/new")
    new_row = res.json()
    row_id = new_row.get("row_id")
    print(f"Created new row: {row_id}")
    
    col_name = "category"
    
    # 2. Add multiple sources to a cell
    # Source: parser_a
    httpx.put(f"{base_url}/tables/{table_name}/batch/cell", json={
        "updates": [
            {"row_id": row_id, "column_name": col_name, "value": "AutoValue_A", "source_name": "parser_a"}
        ]
    })
    # Source: user (manual override)
    httpx.put(f"{base_url}/tables/{table_name}/batch/cell", json={
        "updates": [
            {"row_id": row_id, "column_name": col_name, "value": "UserValue", "source_name": "user"}
        ]
    })
    
    # 3. Get sources
    res = httpx.get(f"{base_url}/tables/{table_name}/{row_id}/{col_name}/sources")
    sources_info = res.json()
    print(f"Initial Sources: {list(sources_info['sources'].keys())}")
    print(f"Current Value: {sources_info['value']} (Priority: {sources_info['priority_source']})")
    
    # 4. Set Manual Priority to parser_a (even though user is usually higher)
    res = httpx.put(f"{base_url}/tables/{table_name}/{row_id}/{col_name}/priority", json={"source_name": "parser_a"})
    print(f"Set Manual Priority Result: {res.status_code}")
    
    res = httpx.get(f"{base_url}/tables/{table_name}/{row_id}/{col_name}/sources")
    sources_info = res.json()
    print(f"Value after Manual Priority: {sources_info['value']} (Manual: {sources_info['manual_priority_source']})")
    
    # 5. Delete 'user' source
    res = httpx.delete(f"{base_url}/tables/{table_name}/{row_id}/{col_name}/sources/user")
    print(f"Delete Source Result: {res.status_code}")
    
    res = httpx.get(f"{base_url}/tables/{table_name}/{row_id}/{col_name}/sources")
    sources_info = res.json()
    print(f"Sources after deletion: {list(sources_info['sources'].keys())}")
    print(f"Final Value: {sources_info['value']}")

if __name__ == "__main__":
    test_source_management()
