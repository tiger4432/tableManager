import json
import time

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


def test_file_ingestion_callback_direct(db_session, tmp_path):
    """아카이브 재처리 → on_file_processed_callback 통지.

    [격리] 이전 판은 워크스페이스 루트를 `dirname(__file__)/..`로 잡아 **라이브**
    `server/ingestion_workspace/inventory_master/`에 mock을 세웠고, 그 과정에서
    사용자의 `config/config.json`을 테스트 페이로드로 덮어썼다(cleanup도 안 했다).
    `IngestionHandler`는 workspace/config/archives 경로를 전부 생성자 인자로 받으므로
    tmp_path를 주는 것으로 격리가 끝난다.

    [config.json 미생성] 워크스페이스 config.json은 폐기된 개념이다(하위호환 읽기만 남음).
    `config_path=None`은 생성자가 명시 허용하며(`config_path: str | None`), 테이블명은
    별칭 → 레거시 config → `default_table_name` 순서라 이 테스트에선 3순위로 해석된다
    — 즉 폐기된 파일을 세우지 않아도 동일하게 성립한다.
    """
    from database import models
    from directory_watcher import IngestionHandler
    import os

    # 1. Setup mock workspace (폴더명=테이블명 규약을 보존해야 해석 경로가 같다)
    workspace_root = tmp_path / "inventory_master"
    archives_dir = workspace_root / "archives"
    archives_dir.mkdir(parents=True)
    config_path = None

    dummy_file_path = str(archives_dir / "test_direct_callback.csv")
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
        workspace_path=str(workspace_root),
        config_path=config_path,
        archives_path=str(archives_dir),
        default_table_name="inventory_master",
        on_file_processed_callback=mock_callback
    )

    # 격리 가드 — 워크스페이스가 정말 tmp인가 (라이브 경로로 되돌아가면 여기서 깨진다)
    assert str(tmp_path) in handler.workspace_path

    try:
        # Directly run parsing synchronously
        res = handler.process_archived_file_sync(failed_log, db_session)
        assert res is True
        assert len(called_back) == 1
        assert called_back[0][0] == "inventory_master"
        assert called_back[0][1] == "test_direct_callback.csv"
        assert called_back[0][2] == "SUCCESS"
        # 폐기된 워크스페이스 config.json을 세우지 않았음을 고정
        assert not os.path.exists(str(workspace_root / "config" / "config.json"))
    finally:
        # 파일 정리는 불필요(tmp_path는 pytest가 회수) — DB 부작용만 정리한다
        db_session.query(models.DatabaseOutbox).delete()
        db_session.commit()


def test_bulk_upsert_deduplication(db_session):
    from database import models
    from database.crud import bulk_upsert_cell_sources, bulk_upsert_cell_overwrites
    
    # Verify cell_sources deduplication (keep last)
    mappings_sources = [
        {
            "table_name": "inventory_master",
            "row_id": "row-dedup-1",
            "column_name": "part_no",
            "source_name": "test_src",
            "value": '"ABC-1"',
            "updated_by": "system"
        },
        {
            "table_name": "inventory_master",
            "row_id": "row-dedup-1",
            "column_name": "part_no",
            "source_name": "test_src",
            "value": '"ABC-2"',
            "updated_by": "user1"
        }
    ]
    bulk_upsert_cell_sources(db_session, mappings_sources)
    db_session.commit()
    
    srcs = db_session.query(models.CellSource).filter(
        models.CellSource.row_id == "row-dedup-1",
        models.CellSource.column_name == "part_no"
    ).all()
    assert len(srcs) == 1
    assert srcs[0].value == '"ABC-2"'
    assert srcs[0].updated_by == "user1"
    
    # Verify cell_overwrites deduplication (keep last)
    mappings_overwrites = [
        {
            "table_name": "inventory_master",
            "row_id": "row-dedup-1",
            "column_name": "part_no",
            "is_overwrite": True,
            "updated_by": "system",
            "manual_priority_source": "src1"
        },
        {
            "table_name": "inventory_master",
            "row_id": "row-dedup-1",
            "column_name": "part_no",
            "is_overwrite": True,
            "updated_by": "user2",
            "manual_priority_source": "src2"
        }
    ]
    bulk_upsert_cell_overwrites(db_session, mappings_overwrites)
    db_session.commit()
    
    ows = db_session.query(models.CellOverwrite).filter(
        models.CellOverwrite.row_id == "row-dedup-1",
        models.CellOverwrite.column_name == "part_no"
    ).all()
    assert len(ows) == 1
    assert ows[0].updated_by == "user2"
    assert ows[0].manual_priority_source == "src2"


def test_internal_events_endpoints(client):
    # Test POST /internal/events/batch-refresh
    payload_refresh = {
        "table_name": "inventory_master",
        "change_count": 5
    }
    response = client.post("/internal/events/batch-refresh", json=payload_refresh)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # Test POST /internal/events/file-processed
    payload_processed = {
        "table_name": "inventory_master",
        "filename": "test_file.csv",
        "status": "SUCCESS"
    }
    response = client.post("/internal/events/file-processed", json=payload_processed)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_internal_events_updates_cache_and_broadcasts(client):
    from audit_cache import audit_cache
    # Initialize cache & force loaded state for testing add_logs_batch
    audit_cache.groups = []
    audit_cache.is_loaded = True

    # 1. Test batch-refresh updates web server's audit cache
    payload_refresh = {
        "table_name": "inventory_master",
        "change_count": 1,
        "created_logs": [
            {
                "id": 9999,
                "table_name": "inventory_master",
                "row_id": "test_row_123",
                "column_name": "unit_price",
                "old_value": "10.0",
                "new_value": "20.0",
                "source_name": "batch_ingester",
                "updated_by": "test_agent",
                "transaction_id": "tx_refresh_test",
                "business_key": "bk_refresh_test",
                "timestamp": "2026-06-14T20:30:00+09:00"
            }
        ]
    }
    response = client.post("/internal/events/batch-refresh", json=payload_refresh)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # Verify audit cache updated
    assert len(audit_cache.groups) > 0
    assert audit_cache.groups[0]["transaction_id"] == "tx_refresh_test"
    assert len(audit_cache.groups[0]["logs"]) == 1
    assert audit_cache.groups[0]["logs"][0].row_id == "test_row_123"

    # Reset cache
    audit_cache.groups = []

    # 2. Test broadcast updates cache and routes
    payload_broadcast = {
        "event": "batch_row_upsert",
        "table_name": "inventory_master",
        "transaction_id": "tx_broadcast_test",
        "created_logs": [
            {
                "id": 9998,
                "table_name": "inventory_master",
                "row_id": "test_row_456",
                "column_name": "qty",
                "old_value": "5",
                "new_value": "15",
                "source_name": "chain_ingestion",
                "updated_by": "chain_worker",
                "transaction_id": "tx_broadcast_test",
                "business_key": "bk_broadcast_test",
                "timestamp": "2026-06-14T20:45:00+09:00"
            }
        ]
    }
    response = client.post("/internal/events/broadcast", json=payload_broadcast)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # Verify audit cache updated
    assert len(audit_cache.groups) > 0
    assert audit_cache.groups[0]["transaction_id"] == "tx_broadcast_test"
    assert len(audit_cache.groups[0]["logs"]) == 1
    assert audit_cache.groups[0]["logs"][0].row_id == "test_row_456"


def test_automatic_schema_alteration(db_session):
    from database import models
    from sqlalchemy import inspect, Column, String

    test_engine = db_session.get_bind()
    table_name = "raw_table_1"
    inspector = inspect(test_engine)
    assert inspector.has_table(table_name)

    # 1. Check current columns in database
    db_cols = {c["name"] for c in inspector.get_columns(table_name)}
    assert "new_test_alter_col" not in db_cols

    # 2. Add column to SQLAlchemy Table object programmatically
    model_class = models.DYNAMIC_TABLES[table_name]
    table_obj = model_class.__table__
    
    if "new_test_alter_col" not in table_obj.columns:
        new_col = Column("new_test_alter_col", String, nullable=True)
        table_obj.append_column(new_col)

    # 3. Execute sync_dynamic_tables_schema
    models.sync_dynamic_tables_schema(test_engine)

    # 4. Verify columns in DB again
    new_inspector = inspect(test_engine)
    new_db_cols = {c["name"] for c in new_inspector.get_columns(table_name)}
    assert "new_test_alter_col" in new_db_cols


def test_dynamic_schema_hot_reloading(db_session):
    from database import models
    from sqlalchemy import inspect
    
    test_engine = db_session.get_bind()
    table_name = "raw_table_1"
    
    # 1. Check DYNAMIC_TABLES exists and get class
    assert table_name in models.DYNAMIC_TABLES
    model_class = models.DYNAMIC_TABLES[table_name]
    
    # Verify the test column doesn't exist yet
    assert "hot_reloaded_col" not in model_class.__table__.columns
    
    # 2. Simulate new config dictionary with a new column
    from database import crud
    config_copy = dict(crud.TABLE_CONFIG)
    if table_name not in config_copy:
        config_copy[table_name] = {"business_key": "part_no", "column_types": {}}
    else:
        config_copy[table_name] = dict(config_copy[table_name])
        config_copy[table_name]["column_types"] = dict(config_copy[table_name].get("column_types", {}))
    
    # Add new column definition
    config_copy[table_name]["column_types"]["hot_reloaded_col"] = "string"
    
    # 3. Call init_dynamic_models with the updated config
    models.init_dynamic_models(config_copy)
    
    # Verify model class table was dynamically updated
    assert "hot_reloaded_col" in model_class.__table__.columns
    
    # 4. Synchronize schema to physical SQLite DB
    models.sync_dynamic_tables_schema(test_engine)
    
    # 5. Verify columns in DB using inspect
    inspector = inspect(test_engine)
    db_cols = {c["name"] for c in inspector.get_columns(table_name)}
    assert "hot_reloaded_col" in db_cols


def test_map_presets_api(client, tmp_path, monkeypatch):
    """map-presets CRUD.

    [격리] 이 API는 파일(`server/config/maps.json`)이 저장소다. 격리하지 않으면
    **사용자의 라이브 config를 읽고 그 위에 써버린다**(실제로 라이브 파일에 과거
    테스트 산물 `custom_*` 프리셋이 남아 있었다). 그래서 `MAPS_CONFIG_PATH`를
    tmp_path로 갈아끼우고, 단언 대상도 **테스트가 스스로 심은 프리셋**으로 한다
    — `maps.json.sample`에만 있는 키를 라이브에서 찾던 이전 구조는 환경에 따라
    상시 실패했고, 상시 실패는 스위트 전체의 신호를 죽인다.
    """
    import main

    maps_path = tmp_path / "maps.json"
    seeded = {
        "presets": {
            "pytest_seed_std": {
                "name": "Pytest Seed", "phys_wafer_dia": 300.0,
                "phys_chip_x": 2.5, "phys_chip_y": 2.5,
                "phys_offset_x": 0.0, "phys_offset_y": 0.0,
                "phys_edge_margin": 3.0, "rotation": 0, "side": "front",
            }
        }
    }
    maps_path.write_text(json.dumps(seeded), encoding="utf-8")
    monkeypatch.setattr(main, "MAPS_CONFIG_PATH", str(maps_path))

    # 격리 가드 — 저장소가 정말 tmp로 갈아끼워졌는가 (아래 단언들의 전제)
    assert str(tmp_path) in main.MAPS_CONFIG_PATH

    # 1. Test GET /api/map-presets
    get_res = client.get("/api/map-presets")
    assert get_res.status_code == 200
    res_data = get_res.json()
    assert res_data["status"] == "success"
    # 심은 것 '만' 보여야 한다 — 라이브 파일이 새어 들어오면 여기서 깨진다
    assert set(res_data["presets"]) == {"pytest_seed_std"}

    # 2. Test POST /api/map-presets (Save custom preset)
    custom_key = f"pytest_custom_{int(time.time())}"
    payload = {
        "preset_key": custom_key,
        "name": "Pytest Custom Spec",
        "phys_wafer_dia": 300,
        "phys_chip_x": 8.5,
        "phys_chip_y": 9.5,
        "phys_offset_x": 1.0,
        "phys_offset_y": -1.0,
        "phys_edge_margin": 3.0,
        "rotation": 90,
        "side": "front"
    }
    post_res = client.post("/api/map-presets", json=payload)
    assert post_res.status_code == 200
    post_data = post_res.json()
    assert post_data["status"] == "success"
    assert post_data["preset_key"] == custom_key

    # Verify preset was saved
    verify_res = client.get("/api/map-presets")
    presets = verify_res.json()["presets"]
    assert custom_key in presets
    assert presets[custom_key]["phys_chip_x"] == 8.5

    # 3. Test DELETE /api/map-presets/{preset_key}
    del_res = client.delete(f"/api/map-presets/{custom_key}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # Verify preset was deleted
    after_del_res = client.get("/api/map-presets")
    assert custom_key not in after_del_res.json()["presets"]

    # 4. 쓰기가 전부 tmp 파일에만 떨어졌는가 (사용자 자산 오염 회귀 가드)
    on_disk = json.loads(maps_path.read_text(encoding="utf-8"))
    assert set(on_disk["presets"]) == {"pytest_seed_std"}





