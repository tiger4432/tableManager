import os
os.environ["TESTING"] = "True"

# [Isolation, board issue #16a] main.py USED TO run
# `Base.metadata.create_all(bind=engine)` at *module import* against whatever
# DATABASE_URL resolved to. With DATABASE_URL unset that default is the live
# production database (database.py DEFAULT_PG_URL), so merely collecting this
# suite issued DDL to production. That DDL now lives in
# main.bootstrap_database_schema() and this file calls it explicitly below - but
# the pin stays, and stays FIRST, because it is the thing that made the old leak
# harmless and the thing that keeps every later import honest.
#
# Pin the suite to an isolated database BEFORE `from main import app` below.
# This is a hard assignment, not setdefault: an ambient DATABASE_URL in the shell
# (e.g. a developer pointing at production) must not be able to leak in. To run
# the suite against a different isolated database, set ASSY_TEST_DATABASE_URL.
os.environ["DATABASE_URL"] = os.environ.get(
    "ASSY_TEST_DATABASE_URL", "sqlite:///:memory:"
)

# [Isolation] Same class of leak as the DATABASE_URL pin above. An operator who
# has exported ASSY_ADMIN_TOKEN in their shell (which is exactly what production
# setup tells them to do) would otherwise run the suite with the admin gate
# ENFORCING, so every existing /admin test would 401 - and, worse, the reverse:
# a suite that only ever runs with the variable set would never exercise the
# unset branch. Delete it here and let each test set what it needs via
# monkeypatch, so the suite's behaviour does not depend on whose shell it runs
# in. Tests for the configured case live in test_admin_auth.py.
os.environ.pop("ASSY_ADMIN_TOKEN", None)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import sys

# Ensure server path is available
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from database.database import Base, get_db

# [Isolation, board issue #16a] The DDL that used to run at `import main` now
# runs at boot (main.bootstrap_database_schema, called from the startup event).
# The suite still needs it, and needs it HERE rather than from TestClient:
# startup runs on a worker thread, and for `sqlite:///:memory:` SQLAlchemy hands
# every thread its own separate database, so tables created during startup are
# invisible to a test that opens `database.SessionLocal` on the main thread.
# test_api.py::test_file_ingestion_callback_direct does exactly that (it drives
# the real directory_watcher) and had been relying on the import-time DDL.
# Running it explicitly here keeps that dependency visible instead of accidental,
# and it is safe because DATABASE_URL was pinned to an isolated database above.
import main as _main
_main.bootstrap_database_schema()

from sqlalchemy.pool import StaticPool

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# [Isolation] Same class of leak as the DATABASE_URL pin above, found the hard
# way: the ingestion path now publishes a heartbeat (work claims), so any test
# that drives `process_with_retry` - test_std_parser.py and
# test_workspace_config_deprecation.py both do - wrote a real
# `server/config/worker_heartbeats/watcher.json` into the USER'S LIVE TREE.
#
# Nothing was destroyed (it creates a new file), but a stray watcher beat in
# production is not harmless: /health reads heartbeats off disk, so a dead
# pytest process's beat would be reported as a stale worker and serve a 503 on a
# perfectly healthy system.
#
# Session-scoped and autouse so it cannot be forgotten by a future test. Tests
# that want their own heartbeat directory still monkeypatch over this per
# function; that is strictly narrower and restores back to this.
@pytest.fixture(scope="session", autouse=True)
def _heartbeats_never_touch_the_live_tree(tmp_path_factory):
    from utils import heartbeat
    d = str(tmp_path_factory.mktemp("worker_heartbeats"))
    orig_dir, orig_path = heartbeat.heartbeat_dir, heartbeat.heartbeat_path
    heartbeat.heartbeat_dir = lambda: d
    heartbeat.heartbeat_path = lambda name: os.path.join(d, f"{name}.json")
    try:
        yield d
    finally:
        heartbeat.heartbeat_dir = orig_dir
        heartbeat.heartbeat_path = orig_path


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
        },
        # [U6] Map-shaped table WITH a declared map_key_columns contract - exercises the
        # declared replace_map scope path (raw_table_1 above exercises the legacy
        # fallback). Name prefixed 'rmscope_test_' so it can never collide with a real
        # table in the user's gitignored config (see server-pm memory: bonding_log trap).
        "rmscope_test_map": {
            "business_key": "die_key",
            "map_key_columns": ["ref_table", "map_key"],
            "column_types": {
                "die_key": "string",
                "ref_table": "string",
                "map_key": "string",
                "x": "number",
                "y": "number",
                "val": "string"
            }
        },
        # [cross-scope] Two map-shaped tables that differ in ONE property: whether the
        # map key is inside the composite business key. That property decides whether a
        # `replace_map` push can reach a row belonging to a DIFFERENT map, so the pair
        # exists to hold both arms of it. See test_replace_map_cross_scope.py.
        #
        # UNSAFE arm - copies `dt_log`'s real shape: the business key is the physical
        # destination cell (job, cx, cy) and the map key (lot, slot) sits OUTSIDE it,
        # deliberately, because in dt_log those two columns are inference targets
        # ("a guess must never sit inside an identity"). Two different maps can
        # therefore mint the same business key.
        "xscope_test_map": {
            "business_key": "cell_key",
            "composite_key_source": ["job", "cx", "cy"],
            "composite_key_separator": "_",
            "map_key_columns": ["lot", "slot"],
            "column_types": {
                "cell_key": "string",
                "job": "string",
                "lot": "string",
                "slot": "string",
                "cx": "number",
                "cy": "number",
                "bn": "string"
            }
        },
        # SAFE arm - the map key IS inside the composite key (the shape every other map
        # table ships with: valid_die_ref, bonding_log, core_wafer_map, ...). A business
        # key then names its own map, so a cross-map collision is impossible by
        # construction and the control test below proves that rather than assuming it.
        "xscope_safe_map": {
            "business_key": "cell_key",
            "composite_key_source": ["lot", "slot", "cx", "cy"],
            "composite_key_separator": "_",
            "map_key_columns": ["lot", "slot"],
            "column_types": {
                "cell_key": "string",
                "lot": "string",
                "slot": "string",
                "cx": "number",
                "cy": "number",
                "bn": "string"
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
