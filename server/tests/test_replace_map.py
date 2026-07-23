def test_replace_map_clean_purge(client):
    unique_eqp = "EQP_UNIQUE_999"
    # 1. Insert initial map data (3 cells for EQP_ID = EQP_UNIQUE_999)
    payload1 = {
        "updates": [
            {"updates": {"EQP_ID": unique_eqp}},
            {"updates": {"EQP_ID": unique_eqp}},
            {"updates": {"EQP_ID": unique_eqp}}
        ],
        "replace_map": False
    }
    res1 = client.put("/tables/raw_table_1/data/updates", json=payload1)
    assert res1.status_code == 200

    # Verify 3 rows exist
    check1 = client.get(f"/tables/raw_table_1/data?filters=%7B%22EQP_ID%22%3A%7B%22filterType%22%3A%22text%22%2C%22type%22%3A%22equals%22%2C%22filter%22%3A%22{unique_eqp}%22%7D%7D")
    assert check1.status_code == 200
    rows1 = check1.json()["data"]
    assert len(rows1) == 3

    # 2. Purge existing map for EQP_UNIQUE_999 and replace with ONLY 1 new cell
    payload_purge = {
        "updates": [
            {"updates": {"EQP_ID": unique_eqp}}
        ],
        "replace_map": True
    }
    res_purge = client.put("/tables/raw_table_1/data/updates", json=payload_purge)
    assert res_purge.status_code == 200

    # 3. Check that old 3 rows for unique_eqp were purged and replaced with ONLY 1 row!
    check2 = client.get(f"/tables/raw_table_1/data?filters=%7B%22EQP_ID%22%3A%7B%22filterType%22%3A%22text%22%2C%22type%22%3A%22equals%22%2C%22filter%22%3A%22{unique_eqp}%22%7D%7D")
    assert check2.status_code == 200
    rows2 = check2.json()["data"]
    assert len(rows2) == 1
    assert str(rows2[0]["data"]["EQP_ID"]["value"]) == unique_eqp
