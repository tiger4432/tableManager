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

import contextlib

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

# ===========================================================================
# PostgreSQL-backed fixture  [2026-08-12]
# ===========================================================================
# WHY THIS EXISTS
#     `crud._pg_multirow_upsert` declines on `dialect.name != "postgresql"`,
#     so the whole accepted branch - the SQL construction, the bind
#     processors, the ON CONFLICT target, the chunk loop - is unreachable from
#     an in-memory-sqlite suite. Measured with a counting spy over the three
#     files named for it: `entered=28 accepted=0 declined=28` across 42
#     passing tests. "A SQLite test cannot reach this code" was true; the
#     reading it invited - "so nothing can" - was not.
#
# WHY THE ENV VAR ABOVE WAS NOT ALREADY ENOUGH
#     `ASSY_TEST_DATABASE_URL` re-points the APPLICATION (the DATABASE_URL pin
#     at the top of this file) and leaves `db_session` on its separately
#     hardcoded sqlite engine, so setting it moves the whole suite onto
#     PostgreSQL - including `bootstrap_database_schema`, which would issue
#     `create_all` into that database's `public` schema. This fixture is the
#     other shape: a SECOND engine, in a scratch schema, while the suite
#     itself stays on sqlite and behaves exactly as before.
#
# 🔴 HOW IT STAYS INSIDE THE #16a ALLOWLIST RATHER THAN AROUND IT.
#     `db_safety.install_global_test_database_guard` refuses every non-sqlite
#     engine in a pytest process unless `ASSY_TEST_DATABASE_URL` names exactly
#     that (backend, host, port, database). This fixture does NOT disarm that
#     guard and does not carry its own credentials: it reads an OPERATOR
#     declaration from `ASSY_PG_TEST_DATABASE_URL`, re-checks it through
#     `db_safety.check_test_database` (so naming the production database is
#     still refused - declaring production does not make it a test database),
#     and then declares that same URL under the name the guard reads, for the
#     narrowest window it can: fixture setup, the test body, fixture teardown.
#     Outside those windows the variable is restored, so
#     `test_dev_env_isolation.py`, which compares the live engine URL against
#     `os.environ.get("ASSY_TEST_DATABASE_URL", ...)` at ITS run time, is
#     unaffected. Nothing but the operator's declared database becomes legal.
#
# Skips, never fails, when no declaration or no server is present.
PG_TEST_URL_ENV = "ASSY_PG_TEST_DATABASE_URL"

#: All DDL lands here, never in `public`. Suffixed with the xdist worker id
#: when there is one, so parallel workers cannot drop each other's schema.
PG_TEST_SCHEMA = "assy_pytest_pg" + (
    "_" + os.environ["PYTEST_XDIST_WORKER"]
    if os.environ.get("PYTEST_XDIST_WORKER") else "")

#: Dynamic tables this fixture needs. Registered into the SHARED
#: `models.DYNAMIC_TABLES` / `Base.metadata` singletons (there is no other
#: kind), so the names carry a `pgqa_` prefix that cannot collide with a real
#: table in the operator's gitignored config - the same discipline
#: `rmscope_test_map` above was named under.
PG_TEST_TABLE_CONFIG = {
    "pgqa_bk_table": {
        "business_key": "part_no",
        "column_types": {"part_no": "string", "qty": "number",
                         "note": "string"},
    },
}


def _resolve_pg_test_url():
    """`(url, None)` when a PostgreSQL test database is declared, else `(None, reason)`.

    A pure decision - nothing is connected to and no environment is written.
    The reason string is what the skip message shows, so an operator who
    expected these tests to run learns which door was shut.
    """
    import db_safety
    from database.database import DEFAULT_PG_URL

    url = os.environ.get(PG_TEST_URL_ENV) or None
    if not url:
        # Second door: an operator who already declared an isolated
        # PostgreSQL for the whole suite has declared one for this too.
        candidate = os.environ.get(db_safety.TEST_DATABASE_URL_ENV) or ""
        url = candidate if candidate.startswith("postgres") else None
    if not url:
        return None, (
            f"no PostgreSQL test database declared. Set {PG_TEST_URL_ENV} to an "
            f"ISOLATED database to run this: "
            f"{PG_TEST_URL_ENV}=postgresql://postgres:...@localhost:5432/assy_qa")

    # The same allowlist decision the production guard takes, asked here so the
    # refusal is a readable skip instead of a RuntimeError from inside a
    # connection attempt. `opt_in=url` = "this URL is what is being declared";
    # `production_url` is what makes declaring production still illegal.
    violations = db_safety.check_test_database(
        url, production_url=DEFAULT_PG_URL, opt_in=url)
    if violations:
        return None, f"{PG_TEST_URL_ENV} is not usable: {violations[0]}"

    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        return None, f"{PG_TEST_URL_ENV} is not a PostgreSQL URL ({url})"
    # Belt and braces over the allowlist above: this fixture creates and DROPS
    # a schema, so it refuses the production database by name even if
    # `DEFAULT_PG_URL` is ever edited to point elsewhere.
    if (parsed.database or "") == "assy_manager":
        return None, "refusing to run schema DDL against 'assy_manager'"
    return url, None


@contextlib.contextmanager
def _declared_as_test_database(url):
    """Declare `url` under the name `db_safety` reads, for this block only."""
    import db_safety
    key = db_safety.TEST_DATABASE_URL_ENV
    previous = os.environ.get(key)
    os.environ[key] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


@pytest.fixture(scope="session")
def pg_engine():
    """An Engine on a scratch SCHEMA of the declared isolated database.

    The ORM models are mapped to schema-less `Table` objects and
    `_pg_multirow_upsert` emits `INSERT INTO cell_sources` unqualified, so the
    redirection has to happen at the connection: `-csearch_path=<schema>` with
    `public` NOT on the path, which makes an unqualified write physically
    unable to reach the real tables. The DDL itself is explicit rather than
    ambient - `Table.to_metadata(MetaData(schema=...), schema=None)` for every
    table in `Base.metadata`.

    CLEANS UP AFTER ITSELF, at both ends. Teardown drops the schema and then
    ASKS THE CATALOGUE whether it is gone (a reviewer reported a dropped
    schema on 2026-08-12 and left 92 objects behind); setup drops a leftover
    of the same name first, so a run killed mid-suite is reclaimed by the next
    one instead of accumulating.
    """
    url, reason = _resolve_pg_test_url()
    if url is None:
        pytest.skip(reason)
    try:
        import psycopg2  # noqa: F401
    except Exception as exc:                                  # pragma: no cover
        pytest.skip(f"psycopg2 is not importable: {exc}")

    from sqlalchemy import create_engine, text, MetaData
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool
    from database import models

    # Registered BEFORE the metadata is copied, so the scratch schema carries
    # the dynamic tables these tests drive.
    models.init_dynamic_models(PG_TEST_TABLE_CONFIG)

    with _declared_as_test_database(url):
        engine = create_engine(
            url, poolclass=NullPool,
            connect_args={"options": f"-csearch_path={PG_TEST_SCHEMA}"})
        try:
            with engine.begin() as conn:
                conn.execute(text("SELECT 1"))
        except OperationalError as exc:
            engine.dispose()
            pytest.skip(f"PostgreSQL is not reachable at the declared URL: "
                        f"{str(exc).strip().splitlines()[0]}")

        scratch = MetaData(schema=PG_TEST_SCHEMA)
        for table in list(Base.metadata.tables.values()):
            table.to_metadata(scratch, schema=None)

        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{PG_TEST_SCHEMA}" CASCADE'))
            conn.execute(text(f'CREATE SCHEMA "{PG_TEST_SCHEMA}"'))
        scratch.create_all(engine)

        # The UNIQUE business-key index that makes a cross-process collision an
        # IntegrityError instead of a duplicate row. ⚠️ The isolated database
        # has ZERO `uq_bk_*` indexes of its own and this must not change that:
        # it is built on the scratch table only, inside the scratch schema, and
        # it goes with the DROP SCHEMA below. Named by the migration's own
        # naming function so the detector's `uq_bk_` prefix test is exercised
        # against the real spelling rather than a lookalike.
        import migrations.add_business_key_unique_index as bk_migration
        for table_name in PG_TEST_TABLE_CONFIG:
            index_name = bk_migration.unique_index_name(table_name)
            with engine.begin() as conn:
                conn.execute(text(
                    f'CREATE UNIQUE INDEX "{index_name}" ON '
                    f'"{PG_TEST_SCHEMA}"."{table_name}" (business_key_val)'))

        try:
            yield engine
        finally:
            with engine.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{PG_TEST_SCHEMA}" CASCADE'))
            # Asserted, not assumed. A reported drop that did not happen is how
            # the last leftover schema got there.
            with engine.connect() as conn:
                left = conn.execute(text(
                    "SELECT count(*) FROM information_schema.schemata "
                    "WHERE schema_name = :s"), {"s": PG_TEST_SCHEMA}).scalar()
            engine.dispose()
            assert left == 0, (
                f"the scratch schema {PG_TEST_SCHEMA!r} survived teardown; "
                f"drop it by hand before the next run")


@pytest.fixture(scope="function")
def pg_session(pg_engine):
    """A Session on `pg_engine`, emptied after every test.

    `autoflush=False` matches `database.SessionLocal`, because the flush
    semantics of the code under test differ between the two settings and a
    fixture that quietly used the other one would be testing a session this
    application never creates.
    """
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from database import crud, models

    url, _ = _resolve_pg_test_url()
    models.init_dynamic_models(PG_TEST_TABLE_CONFIG)
    crud.TABLE_CONFIG.update(PG_TEST_TABLE_CONFIG)

    Maker = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)
    with _declared_as_test_database(url):
        db = Maker()
        try:
            yield db
        finally:
            db.rollback()
            db.close()
            # TRUNCATE rather than a per-test transaction rollback: the code
            # under test COMMITS (`_apply_batch_updates_once` does), and a
            # competing-writer test commits on a second connection on purpose.
            names = ", ".join(
                f'"{PG_TEST_SCHEMA}"."{t}"' for t in
                ["cell_sources", "cell_overwrites", "audit_logs",
                 "database_outbox", *PG_TEST_TABLE_CONFIG])
            with pg_engine.begin() as conn:
                conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


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
