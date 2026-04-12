def test_get_tables_data(client):
    response = client.get("/tables/raw_table_1/data?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "total" in data
    
    rows = data["data"]
    assert len(rows) > 0
    # verify format
    first_row = rows[0]
    assert "row_id" in first_row
    assert "data" in first_row
    assert "EQP_ID" in first_row["data"]
    assert first_row["data"]["EQP_ID"]["is_overwrite"] is False

def test_put_batch_update(client):
    # Fetch first to get a valid row_id
    res = client.get("/tables/raw_table_1/data?skip=0&limit=1")
    row_id = res.json()["data"][0]["row_id"]

    # Emulate client bulk update
    payload = {
        "updates": [
            {
                "row_id": row_id,
                "column_name": "EQP_ID",
                "value": "TEST_EQP_999"
            }
        ]
    }

    # Call PUT
    put_res = client.put("/tables/raw_table_1/cells/batch", json=payload)
    assert put_res.status_code == 200
    assert put_res.json()["status"] == "success"

    # Verify state mutation
    check_res = client.get("/tables/raw_table_1/data?skip=0&limit=10")
    rows = check_res.json()["data"]
    
    # find the mutated row
    mutated_row = next(r for r in rows if r["row_id"] == row_id)
    assert mutated_row["data"]["EQP_ID"]["value"] == "TEST_EQP_999"
    assert mutated_row["data"]["EQP_ID"]["is_overwrite"] is True
    
