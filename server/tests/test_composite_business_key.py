import os
import json
import pytest
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure server path is available
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from database.database import Base
from database import models, crud, schemas
from directory_watcher import IngestionHandler

@pytest.fixture(name="sqlite_db")
def fixture_sqlite_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    test_table_config = {
        "bonding_map_test": {
            "business_key": "pkg_id",
            "composite_key_source": ["base", "x", "y"],
            "composite_key_separator": "_",
            "column_types": {
                "pkg_id": "string",
                "base": "string",
                "x": "number",
                "y": "number",
                "leg": "string"
            },
            "display_columns": ["pkg_id", "base", "x", "y", "leg"]
        }
    }
    
    # Initialize model registry and table config singleton
    models.init_dynamic_models(test_table_config)
    crud.TABLE_CONFIG.update(test_table_config)
    
    # SQLite 호환성을 위해 PostgreSQL 전용 GIN / Trigram 인덱스를 임시 제거
    if "sqlite" in str(engine.url):
        table = Base.metadata.tables.get("data_rows")
        if table is not None:
            table.indexes = {idx for idx in table.indexes if "trgm" not in idx.name and "gin" not in idx.name}
            
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    
    db = TestingSessionLocal()
    yield db, test_table_config
    
    db.close()
    Base.metadata.drop_all(bind=engine)

def test_composite_business_key_ingestion(tmp_path, sqlite_db, monkeypatch):
    """
    테스트 케이스 1: 파일 인제션 시, 파서가 비즈니스 키(pkg_id)를 누락하고 
    base, x, y만 전달하더라도 CRUD 단에서 선제적으로 조립 및 매칭/업서트를 지원하는지 검증합니다.
    """
    db, test_table_config = sqlite_db
    
    workspace_root = tmp_path / "workspace_composite"
    workspace_root.mkdir()
    config_dir = workspace_root / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.json"
    
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(test_table_config["bonding_map_test"], f)
        
    archives_dir = workspace_root / "archives"
    archives_dir.mkdir()
    
    handler = IngestionHandler(
        workspace_path=str(workspace_root),
        config_path=str(config_path),
        archives_path=str(archives_dir),
        default_table_name="bonding_map_test"
    )
    
    # 1차 업서트: pkg_id가 없는 원천 행 전달
    mock_rows_1 = [
        {"base": "CHIPA", "x": 1, "y": 2, "leg": "LEFT"},
        {"base": "CHIPB", "x": 5.0, "y": 10.0, "leg": "RIGHT"}
    ]
    
    import directory_watcher
    original_session_local = directory_watcher.SessionLocal
    directory_watcher.SessionLocal = lambda: db
    
    original_json_load = json.load
    def mock_json_load(fp, *args, **kwargs):
        if hasattr(fp, 'name') and 'table_config.json' in fp.name:
            fp.seek(0)
            data = original_json_load(fp, *args, **kwargs)
            data["bonding_map_test"] = test_table_config["bonding_map_test"]
            return data
        return original_json_load(fp, *args, **kwargs)
    monkeypatch.setattr(json, "load", mock_json_load)
    
    try:
        # 1차 적재
        handler._send_to_upsert(mock_rows_1, uploader="test_user", filename="test_file.csv")
        
        dynamic_model = models.DYNAMIC_TABLES["bonding_map_test"]
        records = db.query(dynamic_model).all()
        assert len(records) == 2
        
        row1 = next(r for r in records if r.base == "CHIPA")
        # pkg_id가 CRUD에서 base_x_y (CHIPA_1_2)로 포맷 및 자동 완성되었는지 확인
        assert row1.pkg_id == "CHIPA_1_2"
        assert row1.business_key_val == "CHIPA_1_2"
        
        row2 = next(r for r in records if r.base == "CHIPB")
        # Float 형(5.0, 10.0) 소수점 이하 .0이 정수 5, 10으로 깔끔하게 정리되었는지 확인
        assert row2.pkg_id == "CHIPB_5_10"
        assert row2.business_key_val == "CHIPB_5_10"
        
        # 2차 업서트: CHIPA_1_2에 해당하는 값을 일부 수정 (동일 비즈니스 키로 덮어쓰기/업서팅 발생 확인)
        mock_rows_2 = [
            {"base": "CHIPA", "x": 1, "y": 2, "leg": "MODIFIED_LEFT"}
        ]
        handler._send_to_upsert(mock_rows_2, uploader="test_user2", filename="test_file.csv")
        
        db.expire_all()
        records_after = db.query(dynamic_model).all()
        assert len(records_after) == 2
        row1_updated = next(r for r in records_after if r.base == "CHIPA")
        assert row1_updated.leg == "MODIFIED_LEFT"
        
    finally:
        directory_watcher.SessionLocal = original_session_local

def test_composite_business_key_draft_state(sqlite_db):
    """
    테스트 케이스 2: 컬럼의 일부가 비어 있는 '드래프트 행'들은 비즈니스 키 조립이 보류(None)되며,
    여러 개의 빈 행들이 동시에 존재하더라도 유일성 충돌 없이 자유롭게 생성되는지 검증합니다.
    """
    db, test_table_config = sqlite_db
    
    # 1. 빈 행 2개 배치 추가 요청 ( updates에 base, x, y 모두 None 또는 비어있음 )
    batch_updates = schemas.GeneralUpdateBatch(
        updates=[
            schemas.GeneralUpdateItem(
                business_key_val=None,
                updates={"base": None, "x": None, "y": None, "leg": "DRAFT_1"},
                source_name="user",
                updated_by="tester"
            ),
            schemas.GeneralUpdateItem(
                business_key_val=None,
                updates={"base": None, "x": None, "y": None, "leg": "DRAFT_2"},
                source_name="user",
                updated_by="tester"
            )
        ]
    )
    
    # execute batch updates (에러 없이 2개 행이 등록되어야 함)
    results, changed_cells, logs, _ = crud.apply_batch_updates(db, "bonding_map_test", batch_updates)
    
    dynamic_model = models.DYNAMIC_TABLES["bonding_map_test"]
    records = db.query(dynamic_model).all()
    assert len(records) == 2
    
    # 둘 다 business_key_val 및 pkg_id가 None 상태인지 확인
    for r in records:
        assert r.business_key_val is None
        assert r.pkg_id is None

def test_composite_business_key_collision_prevention(sqlite_db):
    """
    테스트 케이스 3: 편집을 통해 원천 구성 컬럼(base, x, y)이 완비되는 순간 비즈니스 키가 
    자동으로 재조립되고, 만약 타 행과 겹칠 경우 예외를 내며 수정을 차단(롤백)하는지 검증합니다.
    """
    db, test_table_config = sqlite_db
    dynamic_model = models.DYNAMIC_TABLES["bonding_map_test"]
    
    # 1. 기존에 완성된 키를 가진 행 하나 생성 (CHIPA_1_2)
    row_exist = dynamic_model(
        row_id="exist-row-uuid",
        business_key_val="CHIPA_1_2",
        pkg_id="CHIPA_1_2",
        base="CHIPA",
        x=1,
        y=2,
        leg="LEFT"
    )
    db.add(row_exist)
    
    # 2. 미완성 드래프트 상태의 행 생성
    row_draft = dynamic_model(
        row_id="draft-row-uuid",
        business_key_val=None,
        pkg_id=None,
        base="CHIPA",
        x=None,
        y=None,
        leg="DRAFT"
    )
    db.add(row_draft)
    db.commit()
    
    # 3. 드래프트 행의 x, y 값을 기입해 'CHIPA_1_2' 키를 완성하려고 시도 (충돌 발생 시나리오)
    batch_conflict = schemas.GeneralUpdateBatch(
        updates=[
            schemas.GeneralUpdateItem(
                row_id="draft-row-uuid",
                updates={"x": 1, "y": 2},
                source_name="user",
                updated_by="tester"
            )
        ]
    )
    
    # 대안 B 적용으로 충돌 예외 대신 기존 행으로 병합 및 드래프트 빈 껍데기 행 삭제 수행
    crud.apply_batch_updates(db, "bonding_map_test", batch_conflict)
    
    # 롤백 방지용 커밋 수행 후 검증
    db.commit()
    
    # 임시 드래프트 행(draft-row-uuid)이 병합 후 삭제되었는지 검증
    row_draft_check = db.query(dynamic_model).filter(dynamic_model.row_id == "draft-row-uuid").first()
    assert row_draft_check is None
    
    # 기존에 선점하고 있던 행(exist-row-uuid)은 온전히 유지되는지 검증
    row_exist_check = db.query(dynamic_model).filter(dynamic_model.row_id == "exist-row-uuid").first()
    assert row_exist_check is not None
    assert row_exist_check.business_key_val == "CHIPA_1_2"
    
    # 4. 다른 안 겹치는 조합(CHIPA_5_5)으로 수정 시도 시 성공적으로 완성 및 동기화되는지 검증
    row_draft_retry = dynamic_model(
        row_id="draft-row-uuid",
        business_key_val=None,
        pkg_id=None,
        base="CHIPA",
        x=None,
        y=None,
        leg="DRAFT"
    )
    db.add(row_draft_retry)
    db.commit()

    batch_success = schemas.GeneralUpdateBatch(
        updates=[
            schemas.GeneralUpdateItem(
                row_id="draft-row-uuid",
                updates={"x": 5, "y": 5},
                source_name="user",
                updated_by="tester"
            )
        ]
    )
    
    crud.apply_batch_updates(db, "bonding_map_test", batch_success)
    
    db.expire_all()
    row_draft_updated = db.query(dynamic_model).filter(dynamic_model.row_id == "draft-row-uuid").first()
    assert row_draft_updated.x == 5
    assert row_draft_updated.y == 5
    # 비즈니스 키 컬럼(pkg_id)과 business_key_val 필드가 CHIPA_5_5로 동기화 완료되었는지 확인
    assert row_draft_updated.pkg_id == "CHIPA_5_5"
    assert row_draft_updated.business_key_val == "CHIPA_5_5"


def test_user_vs_user_conflict_merge(sqlite_db):
    """
    테스트 케이스 4: 비즈니스 키 충돌 발생 시, 기존 행에 저장되어 있던 값(user_a에 의한 덮어쓰기)과
    새로 병합되는 행의 값(user_b에 의한 덮어쓰기)이 모두 사용자가 기입한 값일 때,
    새로운 사용자 입력값(덮어쓰는 값)이 기존의 사용자 입력값을 덮어씌우는지 검증합니다.
    """
    db, test_table_config = sqlite_db
    dynamic_model = models.DYNAMIC_TABLES["bonding_map_test"]

    # 1. 기존에 존재하던 사용자 입력값 레코드 삽입
    row_exist = dynamic_model(
        row_id="exist-row-uuid",
        business_key_val="CHIPA_1_2",
        pkg_id="CHIPA_1_2",
        base="CHIPA",
        x=1,
        y=2,
        leg="GOOD"
    )
    db.add(row_exist)
    
    # exist-row-uuid 에 대한 user_a의 CellOverwrite 생성
    ow_exist = models.CellOverwrite(
        table_name="bonding_map_test",
        row_id="exist-row-uuid",
        column_name="leg",
        is_overwrite=True,
        updated_by="user_a"
    )
    db.add(ow_exist)

    # exist-row-uuid 에 대한 CellSource 생성
    src_exist = models.CellSource(
        table_name="bonding_map_test",
        row_id="exist-row-uuid",
        column_name="leg",
        source_name="user",
        value="GOOD",
        updated_by="user_a"
    )
    db.add(src_exist)
    db.commit()

    # 2. 새로운 사용자 수정 예정인 draft 행 생성
    row_draft = dynamic_model(
        row_id="draft-row-uuid",
        business_key_val=None,
        pkg_id=None,
        base="CHIPA",
        x=None,
        y=None,
        leg="FAIL"
    )
    db.add(row_draft)
    
    # draft-row-uuid 에 대한 user_b의 CellOverwrite 생성
    ow_draft = models.CellOverwrite(
        table_name="bonding_map_test",
        row_id="draft-row-uuid",
        column_name="leg",
        is_overwrite=True,
        updated_by="user_b"
    )
    db.add(ow_draft)

    # draft-row-uuid 에 대한 CellSource 생성
    src_draft = models.CellSource(
        table_name="bonding_map_test",
        row_id="draft-row-uuid",
        column_name="leg",
        source_name="user",
        value="FAIL",
        updated_by="user_b"
    )
    db.add(src_draft)
    db.commit()

    # 3. draft 행의 x, y 값을 기입해 'CHIPA_1_2' 키를 완성 시도 (사용자 b에 의한 업데이트)
    batch_conflict = schemas.GeneralUpdateBatch(
        updates=[
            schemas.GeneralUpdateItem(
                row_id="draft-row-uuid",
                updates={"x": 1, "y": 2},
                source_name="user",
                updated_by="user_b"
            )
        ]
    )

    crud.apply_batch_updates(db, "bonding_map_test", batch_conflict)
    db.commit()

    # 4. 병합 후 exist-row-uuid의 leg 값이 신규 덮어씌워진 값인 "FAIL"로 업데이트되었는지 검증
    db.expire_all()
    row_exist_check = db.query(dynamic_model).filter(dynamic_model.row_id == "exist-row-uuid").first()
    assert row_exist_check is not None
    assert row_exist_check.leg == "FAIL"  # 기존의 "GOOD"에서 새로운 user 값 "FAIL"로 병합 덮어씌우기 적용 완료

    # 5. 기존에 존재했던 user_a의 "GOOD" 값이 "user (old_exist_exist-)" 라는 백업 소스로 보존되었는지 검증
    backup_src = db.query(models.CellSource).filter(
        models.CellSource.table_name == "bonding_map_test",
        models.CellSource.row_id == "exist-row-uuid",
        models.CellSource.column_name == "leg",
        models.CellSource.source_name == "user (old_exist_exist-)"
    ).first()
    assert backup_src is not None
    assert backup_src.value == "GOOD"


