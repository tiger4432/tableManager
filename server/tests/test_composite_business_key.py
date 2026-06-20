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
from database import models
from directory_watcher import IngestionHandler

@pytest.fixture(name="sqlite_db")
def fixture_sqlite_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # 1. Setup composite key config
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
    
    from database import models, crud
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

def test_composite_business_key_generation(tmp_path, sqlite_db, monkeypatch):
    db, test_table_config = sqlite_db
    
    # 1. Setup mock workspace
    workspace_root = tmp_path / "workspace_composite"
    workspace_root.mkdir()
    
    config_dir = workspace_root / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.json"
    
    # Write same configuration to config.json
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
    
    # 2. Mock parsed rows LACKING the 'pkg_id' business key
    mock_rows = [
        {"base": "CHIPA", "x": 1, "y": 2, "leg": "LEFT"},
        {"base": "CHIPB", "x": 5, "y": 10, "leg": "RIGHT"}
    ]
    
    # Mock table_config.json loading to include bonding_map_test
    original_json_load = json.load
    
    def mock_json_load(fp, *args, **kwargs):
        if hasattr(fp, 'name') and 'table_config.json' in fp.name:
            fp.seek(0)
            data = original_json_load(fp, *args, **kwargs)
            data["bonding_map_test"] = test_table_config["bonding_map_test"]
            return data
        return original_json_load(fp, *args, **kwargs)
        
    monkeypatch.setattr(json, "load", mock_json_load)
    
    # Run _send_to_upsert under the mock database session
    # Since _send_to_upsert usually instantiates SessionLocal(), we will monkeypatch it
    import directory_watcher
    original_session_local = directory_watcher.SessionLocal
    directory_watcher.SessionLocal = lambda: db
    
    try:
        # Run upsert
        handler._send_to_upsert(mock_rows, uploader="test_user", filename="test_file.csv")
        
        # 3. Query the dynamic DB table to verify
        dynamic_model = models.DYNAMIC_TABLES["bonding_map_test"]
        records = db.query(dynamic_model).all()
        
        assert len(records) == 2
        
        # Verify first row composite key
        row1 = next(r for r in records if r.base == "CHIPA")
        assert row1.pkg_id == "CHIPA_1_2"
        assert row1.x == 1
        assert row1.y == 2
        assert row1.leg == "LEFT"
        
        # Verify second row composite key
        row2 = next(r for r in records if r.base == "CHIPB")
        assert row2.pkg_id == "CHIPB_5_10"
        assert row2.x == 5
        assert row2.y == 10
        assert row2.leg == "RIGHT"
        
    finally:
        directory_watcher.SessionLocal = original_session_local
