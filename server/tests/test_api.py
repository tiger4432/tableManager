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


    
