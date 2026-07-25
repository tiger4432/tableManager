import os
os.environ["TESTING"] = "True"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import sys

# Ensure server path is available
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from database.database import Base, get_db

from sqlalchemy.pool import StaticPool

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    # Initialize dynamic models with test configuration (SQLite compatible)
    test_table_config = {
        "raw_table_1": {
            "business_key": "EQP_ID",
            "column_types": {
                "EQP_ID": "string"
            }
        },
        "inventory_master": {
            "business_key": "part_no",
            "column_types": {
                "part_no": "string",
                "category": "string",
                "stock_qty": "number",
                "unit_price": "number"
            }
        },
        "production_plan": {
            "business_key": "plan_id",
            "column_types": {
                "plan_id": "string",
                "prod_line": "string",
                "model_name": "string",
                "target_qty": "number",
                "due_date": "string"
            }
        }
    }
    from database import models, crud
    models.init_dynamic_models(test_table_config)
    crud.TABLE_CONFIG.clear()
    crud.TABLE_CONFIG.update(test_table_config)

    # Create the database and tables
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    
    db = TestingSessionLocal()
    
    # We must seed some data to test fetching
    raw_table_model = models.DYNAMIC_TABLES["raw_table_1"]
    import uuid
    for i in range(1, 11):
        r_id = str(uuid.uuid4())
        row = raw_table_model(
            row_id=r_id,
            business_key_val=f"EQP_{i}",
            EQP_ID=f"EQP_{i}"
        )
        db.add(row)
        
        src = models.CellSource(
            table_name="raw_table_1",
            row_id=r_id,
            column_name="EQP_ID",
            source_name="system",
            value=f"EQP_{i}",
            updated_by="system"
        )
        db.add(src)
    db.commit()
    
    yield db
    
    db.close()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
            
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
