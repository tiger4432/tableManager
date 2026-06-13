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
                "updates": {
                    "EQP_ID": "TEST_EQP_999"
                },
                "source_name": "user",
                "updated_by": "user"
            }
        ]
    }

    # Call PUT
    put_res = client.put("/tables/raw_table_1/data/updates", json=payload)
    assert put_res.status_code == 200
    assert put_res.json()["status"] == "success"

    # Verify state mutation
    check_res = client.get("/tables/raw_table_1/data?skip=0&limit=10")
    rows = check_res.json()["data"]
    
    # find the mutated row
    mutated_row = next(r for r in rows if r["row_id"] == row_id)
    assert mutated_row["data"]["EQP_ID"]["value"] == "TEST_EQP_999"
    assert mutated_row["data"]["EQP_ID"]["is_overwrite"] is True


def test_chained_ingestion(client, db_session):
    # 1. Trigger Table에 데이터 인제션 시뮬레이션
    from database import models
    import uuid
    from database import schemas, crud
    
    prod_row_id = str(uuid.uuid4())
    
    # ContextVars 바인딩 모사
    from database.context import request_user, request_transaction_id, request_source
    token_user = request_user.set("user")
    token_tx = request_transaction_id.set(str(uuid.uuid4()))
    token_src = request_source.set("user")
    
    try:
        # 생산 계획 등록
        batch = schemas.GeneralUpdateBatch(
            updates=[
                schemas.GeneralUpdateItem(
                    row_id=prod_row_id,
                    updates={
                        "model_name": "STEEL_01",
                        "target_qty": 10
                    },
                    source_name="user",
                    updated_by="tester"
                )
            ]
        )
        crud.apply_batch_updates(db_session, "production_plan", batch)
    finally:
        request_user.reset(token_user)
        request_transaction_id.reset(token_tx)
        request_source.reset(token_src)

    # 2. Outbox에 PENDING 이벤트가 적재되었는지 검증
    from database.models import DatabaseOutbox
    events = db_session.query(DatabaseOutbox).filter(
        DatabaseOutbox.table_name == "production_plan",
        DatabaseOutbox.processed_chain == False
    ).all()
    assert len(events) > 0
    
    # 3. 체인 워커 수동 트리거링 (트랜잭션 그룹 단위 호출)
    from chain_ingestion_worker import process_chain_transaction_group, load_chain_rules
    rules = load_chain_rules()
    
    import anyio
    
    async def run_chain():
        tx_id = events[0].payload.get("transaction_id") or "test_tx"
        await process_chain_transaction_group(tx_id, events, db_session, rules)
        for event in events:
            event.processed_chain = True
        db_session.commit()
        
    anyio.run(run_chain)
    
    # 4. Target Table인 inventory_master가 연쇄 업데이트 되었는지 검증
    inv_model = models.DYNAMIC_TABLES["inventory_master"]
    target_row = db_session.query(inv_model).filter(
        inv_model.business_key_val == "INV_STEEL_01"
    ).first()
    
    assert target_row is not None
    assert target_row.stock_qty == 100
    
    src = db_session.query(models.CellSource).filter(
        models.CellSource.table_name == "inventory_master",
        models.CellSource.row_id == target_row.row_id,
        models.CellSource.column_name == "stock_qty"
    ).first()
    assert src is not None
    assert src.updated_by == "chain_worker"
    

def test_cell_sources_api(client):
    # 1. Fetch a valid row_id from raw_table_1
    res = client.get("/tables/raw_table_1/data?skip=0&limit=1")
    assert res.status_code == 200
    rows = res.json()["data"]
    assert len(rows) > 0
    row_id = rows[0]["row_id"]

    # 2. Get cell sources for a column (e.g. EQP_ID)
    sources_res = client.get(f"/tables/raw_table_1/{row_id}/EQP_ID/sources")
    assert sources_res.status_code == 200
    sources_data = sources_res.json()
    assert "sources" in sources_data
    assert "manual_priority_source" in sources_data
    assert "priority_source" in sources_data
    assert "value" in sources_data

    # 3. Query cell sources in batch via POST
    query_payload = {
        "updates": [
            {
                "row_id": row_id,
                "column_name": "EQP_ID"
            }
        ]
    }
    batch_res = client.post("/tables/raw_table_1/cells/sources/query", json=query_payload)
    assert batch_res.status_code == 200
    batch_data = batch_res.json()
    assert batch_data[0]["row_id"] == row_id
    assert batch_data[0]["column_name"] == "EQP_ID"
    assert "sources" in batch_data[0]
    assert "value" in batch_data[0]


def test_priority_toggle_api(client, db_session):
    from database import models
    from datetime import datetime

    # 1. Fetch a row to modify from raw_table_1
    res = client.get("/tables/raw_table_1/data?skip=0&limit=1")
    row = res.json()["data"][0]
    row_id = row["row_id"]
    
    # Add a cell source to satisfy the validation
    db_session.add(models.CellSource(
        table_name="raw_table_1",
        row_id=row_id,
        column_name="EQP_ID",
        source_name="pipeline_parser",
        value="TEST_VAL",
        ingested_at=datetime.now(),
        updated_by="system"
    ))
    db_session.commit()
    
    # 2. Put manual priority source as 'pipeline_parser'
    payload = {
        "source_name": "pipeline_parser",
        "updated_by": "tester"
    }
    put_res = client.put(f"/tables/raw_table_1/{row_id}/EQP_ID/priority", json=payload)
    assert put_res.status_code == 200
    
    # Verify it was pinned
    sources_res = client.get(f"/tables/raw_table_1/{row_id}/EQP_ID/sources")
    assert sources_res.json()["manual_priority_source"] == "pipeline_parser"
    
    # 3. Pin to 'pipeline_parser' AGAIN (re-click) -> should toggle pin OFF (become None)
    put_res2 = client.put(f"/tables/raw_table_1/{row_id}/EQP_ID/priority", json=payload)
    assert put_res2.status_code == 200
    
    # Verify it was unpinned (None)
    sources_res2 = client.get(f"/tables/raw_table_1/{row_id}/EQP_ID/sources")
    assert sources_res2.json()["manual_priority_source"] is None


def test_numeric_filtering_and_blank_checks(client, db_session):
    from database import models
    import json

    inv_model = models.DYNAMIC_TABLES["inventory_master"]
    
    # Seed test rows for inventory_master
    qtys = [10, 20, 30, None]
    for i, qty in enumerate(qtys):
        r_id = f"test_row_{i}"
        row = inv_model(
            row_id=r_id,
            business_key_val=f"PART_{i}",
            part_no=f"PART_{i}",
            stock_qty=qty
        )
        db_session.add(row)
    db_session.commit()

    # Case 1: greaterThan 15
    f_greater = {"stock_qty": {"type": "greaterThan", "filter": "15"}}
    res = client.get(f"/tables/inventory_master/data?filters={json.dumps(f_greater)}")
    assert res.status_code == 200
    rows = res.json()["data"]
    assert len(rows) == 2
    assert all(r["data"]["stock_qty"]["value"] in [20, 30] for r in rows)

    # Case 2: lessThan 25
    f_less = {"stock_qty": {"type": "lessThan", "filter": "25"}}
    res = client.get(f"/tables/inventory_master/data?filters={json.dumps(f_less)}")
    assert res.status_code == 200
    rows = res.json()["data"]
    assert len(rows) == 2
    assert all(r["data"]["stock_qty"]["value"] in [10, 20] for r in rows)

    # Case 3: inRange 15 to 35
    f_range = {"stock_qty": {"type": "inRange", "filter": "15", "filterTo": "35"}}
    res = client.get(f"/tables/inventory_master/data?filters={json.dumps(f_range)}")
    assert res.status_code == 200
    rows = res.json()["data"]
    assert len(rows) == 2

    # Case 4: blank
    f_blank = {"stock_qty": {"type": "blank"}}
    res = client.get(f"/tables/inventory_master/data?filters={json.dumps(f_blank)}")
    assert res.status_code == 200
    rows = res.json()["data"]
    assert len(rows) == 1
    assert rows[0]["data"]["stock_qty"]["value"] is None

    # Case 5: notBlank
    f_not_blank = {"stock_qty": {"type": "notBlank"}}
    res = client.get(f"/tables/inventory_master/data?filters={json.dumps(f_not_blank)}")
    assert res.status_code == 200
    rows = res.json()["data"]
    assert len(rows) == 3


def test_audit_log_no_redundant_logs(client, db_session):
    from database import models, schemas, crud
    import uuid

    inv_model = models.DYNAMIC_TABLES["inventory_master"]
    row_id = str(uuid.uuid4())
    
    # 1. Create a row with stock_qty = 100.0 (float)
    row = inv_model(
        row_id=row_id,
        business_key_val="PART_99",
        part_no="PART_99",
        category="Connector",
        stock_qty=100.0
    )
    db_session.add(row)
    db_session.commit()

    # Clear any audit logs and outbox events from conftest seeding
    db_session.query(models.AuditLog).delete()
    db_session.query(models.DatabaseOutbox).delete()
    db_session.commit()

    # 2. Perform ingestion update with the same logical values (int 100, trailing spaces, same string)
    payload = {
        "updates": [
            {
                "row_id": row_id,
                "updates": {
                    "stock_qty": 100,            # Same numeric value (100 vs 100.0)
                    "category": "Connector   ", # Same string with trailing whitespace
                    "part_no": "PART_99"        # Exactly the same
                },
                "source_name": "pipeline_parser",
                "updated_by": "system"
            }
        ]
    }

    res = client.put("/tables/inventory_master/data/updates", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # 3. Verify that NO audit logs or outbox events were written!
    count = db_session.query(models.AuditLog).count()
    assert count == 0, f"Expected 0 audit logs, got {count}"

    # Clean up outbox to avoid leaking
    db_session.query(models.DatabaseOutbox).delete()
    db_session.commit()


def test_file_ingestion_callback_direct(db_session):
    from database import models
    from directory_watcher import IngestionHandler
    import os
    import json

    # 1. Setup mock workspace
    server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    workspace_root = os.path.join(server_dir, "ingestion_workspace", "inventory_master")
    os.makedirs(workspace_root, exist_ok=True)
    
    config_dir = os.path.join(workspace_root, "config")
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"table_name": "inventory_master", "columns": ["part_no", "category"]}, f)
    
    # Create mock archived file
    archives_dir = os.path.join(workspace_root, "archives")
    os.makedirs(archives_dir, exist_ok=True)
    dummy_file_path = os.path.join(archives_dir, "test_direct_callback.csv")
    with open(dummy_file_path, "w", encoding="utf-8") as f:
        f.write("part_no,category\nTEST_PART_DIR,TestCategoryWS\n")

    # Create failed log
    failed_log = models.FileIngestionLog(
        filename="test_direct_callback.csv",
        filepath=dummy_file_path,
        table_name="inventory_master",
        status="FAILED",
        error_message="Simulated failure",
        retry_count=0
    )
    db_session.add(failed_log)
    db_session.commit()

    called_back = []
    def mock_callback(table_name, filename, status, error_msg):
        called_back.append((table_name, filename, status, error_msg))

    handler = IngestionHandler(
        workspace_path=workspace_root,
        config_path=config_path,
        archives_path=archives_dir,
        default_table_name="inventory_master",
        on_file_processed_callback=mock_callback
    )

    try:
        # Directly run parsing synchronously
        res = handler.process_archived_file_sync(failed_log, db_session)
        assert res is True
        assert len(called_back) == 1
        assert called_back[0][0] == "inventory_master"
        assert called_back[0][1] == "test_direct_callback.csv"
        assert called_back[0][2] == "SUCCESS"
    finally:
        # Clean up
        if os.path.exists(dummy_file_path):
            try:
                os.remove(dummy_file_path)
            except:
                pass
        db_session.query(models.DatabaseOutbox).delete()
        db_session.commit()



