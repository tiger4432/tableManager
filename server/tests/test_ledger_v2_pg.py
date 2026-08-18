"""Stage 6 PostgreSQL E2E for the compiled Ledger v2 transaction.

This module never falls back to SQLite.  It runs only when the operator declares an
isolated PostgreSQL database, creates a disposable Ledger schema plus uniquely named
physical source tables, and proves descriptor issuance against PostgreSQL's real UNIQUE
catalog before compiling the snapshot.
"""
from __future__ import annotations

import contextlib
import copy
from datetime import datetime, timezone
import json
import os

import pandas as pd
import pytest
from sqlalchemy import Column, DateTime, String, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from ledger import backfill, gate, schema
from ledger.setup import DEFAULT_ONTOLOGY_ROOT
from ledger.runtime_v2 import execute_cursor_batch, preview_cursor_batch
from ledger.roleframe import DeclarativeRoleMapper, RoleMapperImplementationRegistry
from ledger.setup_bundle import LedgerSetupValidationError, validate_bundle
from ledger.setup_registry import compile_setup_snapshot
from ledger.source_preparation import (
    DirectJoinSourcePreparer,
    JoinRightRow,
    SQLAlchemyVerifiedJoinBatchReader,
    SourcePreparationError,
    SourcePreparerImplementationRegistry,
)
from ledger.store import CursorVersionConflict, LedgerStore
from ledger_trace import DEFAULT_RESOLVER_CONFIG, SqlClaimLookup, coverage, trace
from ledger_structure import structure
from test_ledger_setup_bundle import logical_bundle, logical_catalog
from test_ledger_setup_registry import trusted_implementations
import virtual_join_config


PG_TEST_URL_ENV = "ASSY_PG_TEST_DATABASE_URL"
RUN_TOKEN = f"{os.getpid()}_{os.environ.get('PYTEST_XDIST_WORKER', 'gw0')}"
SCRATCH_SCHEMA = f"assy_ledger_v2_s6_{RUN_TOKEN}"
SOURCE_TABLE = f"v2s6_input_rows_{RUN_TOKEN}"
RIGHT_TABLE = f"v2s6_reference_rows_{RUN_TOKEN}"
UNIQUE_INDEX = f"uq_v2s6_reference_{RUN_TOKEN}"
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def _resolve_url():
    import db_safety
    from database.database import DEFAULT_PG_URL

    url = os.environ.get(PG_TEST_URL_ENV) or None
    if not url:
        candidate = os.environ.get(db_safety.TEST_DATABASE_URL_ENV) or ""
        url = candidate if candidate.startswith("postgres") else None
    if not url:
        return None, f"no isolated PostgreSQL declared in {PG_TEST_URL_ENV}"
    violations = db_safety.check_test_database(
        url, production_url=DEFAULT_PG_URL, opt_in=url)
    if violations:
        return None, f"declared PostgreSQL is unsafe: {violations[0]}"
    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        return None, "declared test database is not PostgreSQL"
    if (parsed.database or "") == "assy_manager":
        return None, "refusing production database assy_manager"
    return url, None


@contextlib.contextmanager
def _declared(url):
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


def _bundle():
    raw = logical_bundle()
    join = raw["virtual_joins"]["input_to_reference"]
    join["left_table"] = SOURCE_TABLE
    join["right_table"] = RIGHT_TABLE
    raw["sources"]["input_rows"]["relation"] = SOURCE_TABLE
    return raw


def _catalog():
    """The scratch plant's physical schema, under this run's disposable table names.

    Built from `logical_catalog` -- the fixture's PHYSICAL half -- and never from the
    bundle `_bundle()` returns.  The ledger stopped carrying a `tables` section precisely
    so the two halves can disagree; deriving one from the other here would put the
    unfalsifiable check back.  See the docstring on `logical_catalog`.
    """
    catalog = copy.deepcopy(dict(logical_catalog()))
    catalog[SOURCE_TABLE] = catalog.pop("input_rows")
    catalog[RIGHT_TABLE] = catalog.pop("reference_rows")
    catalog[RIGHT_TABLE]["indexes"][0]["name"] = UNIQUE_INDEX
    return catalog


CATALOG = _catalog()


def _known_tables(catalog):
    return {
        table: {"column_types": dict(config["columns"])}
        for table, config in catalog.items()
    }


def _registries():
    preparer_registry = SourcePreparerImplementationRegistry()
    preparer_registry.register("prepare-input", 1, DirectJoinSourcePreparer)
    mapper_registry = RoleMapperImplementationRegistry()
    mapper_registry.register("map-transition-role", 1, DeclarativeRoleMapper)
    return preparer_registry.seal(), mapper_registry.seal()


@pytest.fixture(scope="module")
def pg_v2(tmp_path_factory):
    url, reason = _resolve_url()
    if url is None:
        pytest.skip(reason)
    try:
        import psycopg2  # noqa: F401
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"psycopg2 unavailable: {exc}")

    with _declared(url):
        admin = create_engine(url, poolclass=NullPool)
        runtime = create_engine(
            url, poolclass=NullPool,
            connect_args={"options": f"-csearch_path={SCRATCH_SCHEMA},public"},
        )
        extension_created = False
        with admin.begin() as connection:
            existing = connection.execute(text(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_trgm')"
            )).scalar()
            if not existing:
                connection.execute(text("CREATE EXTENSION pg_trgm"))
                extension_created = True
            connection.execute(text(
                f'DROP TABLE IF EXISTS public."{SOURCE_TABLE}" CASCADE'))
            connection.execute(text(
                f'DROP TABLE IF EXISTS public."{RIGHT_TABLE}" CASCADE'))
            connection.execute(text(
                f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
            connection.execute(text(f'CREATE SCHEMA "{SCRATCH_SCHEMA}"'))
            connection.execute(text(f'''
                CREATE TABLE public."{SOURCE_TABLE}" (
                    record_id TEXT PRIMARY KEY,
                    join_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    event_at TIMESTAMPTZ NOT NULL,
                    event_key TEXT NOT NULL
                )'''))
            connection.execute(text(f'''
                CREATE TABLE public."{RIGHT_TABLE}" (
                    row_id TEXT PRIMARY KEY,
                    updated_at TIMESTAMPTZ NOT NULL,
                    join_id TEXT NOT NULL,
                    target_id TEXT NOT NULL
                )'''))
            connection.execute(text(
                f'CREATE UNIQUE INDEX "{UNIQUE_INDEX}" '
                f'ON public."{RIGHT_TABLE}" (join_id)'))

        raw = _bundle()
        config_path = tmp_path_factory.mktemp("ledger_v2_s6") / "virtual_joins.json"
        config_path.write_text(json.dumps(raw["virtual_joins"]), encoding="utf-8")
        Maker = sessionmaker(bind=admin, autoflush=False)
        verifier_session = Maker()
        try:
            verified = tuple(virtual_join_config.load_verified_rules(
                verifier_session, path=str(config_path),
                known_tables=_known_tables(CATALOG)))
        finally:
            verifier_session.close()
        assert len(verified) == 1
        assert verified[0].unique_index == UNIQUE_INDEX
        compiled = compile_setup_snapshot(
            validate_bundle(raw, catalog=CATALOG), trusted_implementations(),
            verified, catalog=CATALOG)

        RightBase = declarative_base()

        class RightModel(RightBase):
            __tablename__ = RIGHT_TABLE
            __table_args__ = {"schema": "public"}
            row_id = Column(String, primary_key=True)
            updated_at = Column(DateTime(timezone=True), nullable=False)
            join_id = Column(String, nullable=False)
            target_id = Column(String, nullable=False)

        from database import models
        previous_model = models.DYNAMIC_TABLES.get(RIGHT_TABLE)
        models.DYNAMIC_TABLES[RIGHT_TABLE] = RightModel
        store = LedgerStore(runtime, who="ledger-v2-stage6")
        store.ensure_schema()

        try:
            yield {
                "admin": admin, "runtime": runtime, "compiled": compiled,
                "store": store, "sessionmaker": sessionmaker(
                    bind=runtime, autoflush=False),
            }
        finally:
            if previous_model is None:
                models.DYNAMIC_TABLES.pop(RIGHT_TABLE, None)
            else:
                models.DYNAMIC_TABLES[RIGHT_TABLE] = previous_model
            runtime.dispose()
            with admin.begin() as connection:
                connection.execute(text(
                    f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
                connection.execute(text(
                    f'DROP TABLE IF EXISTS public."{SOURCE_TABLE}" CASCADE'))
                connection.execute(text(
                    f'DROP TABLE IF EXISTS public."{RIGHT_TABLE}" CASCADE'))
                if extension_created:
                    connection.execute(text("DROP EXTENSION IF EXISTS pg_trgm"))
                left = connection.execute(text(
                    "SELECT count(*) FROM information_schema.schemata "
                    "WHERE schema_name=:schema"), {"schema": SCRATCH_SCHEMA}).scalar()
                assert left == 0
            admin.dispose()


@pytest.fixture
def clean_pg_v2(pg_v2):
    with pg_v2["runtime"].begin() as connection:
        connection.execute(text(f"TRUNCATE {schema.LEDGER_TABLE} CASCADE"))
        connection.execute(text(f"TRUNCATE {schema.CURSOR_TABLE}"))
    with pg_v2["admin"].begin() as connection:
        connection.execute(text(f'TRUNCATE public."{SOURCE_TABLE}"'))
        connection.execute(text(f'TRUNCATE public."{RIGHT_TABLE}"'))
    gate.reset_counters()
    yield pg_v2
    gate.reset_counters()


def _seed(case, *, with_right=True):
    with case["admin"].begin() as connection:
        connection.execute(text(f'''
            INSERT INTO public."{SOURCE_TABLE}"
                (record_id, join_id, source_id, event_at, event_key)
            VALUES ('R-0001', 'J-0001', 'IN-0001', :event_at, 'E-0001')
        '''), {"event_at": NOW})
        if with_right:
            connection.execute(text(f'''
                INSERT INTO public."{RIGHT_TABLE}"
                    (row_id, updated_at, join_id, target_id)
                VALUES ('RIGHT-1', :updated_at, 'J-0001', 'OUT-J-0001')
            '''), {"updated_at": NOW})


def _base_batch(case):
    columns = case["compiled"].source_plans["input_rows"]
    physical = tuple(sorted({
        *columns.driver.identity, *columns.driver.group_by,
        *columns.driver.order_by, *columns.driver.cursor_columns,
        columns.driver.occurred_at.column,
        *columns.driver.preparation.preparer.input_columns,
        *(column for column in columns.driver.mapper.input_columns
          if column not in columns.driver.preparation.preparer.output_columns),
    }))
    assert "target_id" not in physical
    selected = ", ".join(f'"{column}"' for column in physical)
    with case["admin"].connect() as connection:
        rows = connection.execute(text(
            f'SELECT {selected} FROM public."{SOURCE_TABLE}" '
            'ORDER BY event_at, record_id LIMIT 1000')).mappings().all()
    return pd.DataFrame([dict(row) for row in rows], columns=physical)


def _cursor(base):
    return {"event_at": base.iloc[-1]["event_at"],
            "record_id": base.iloc[-1]["record_id"]}


def _counts(case):
    with case["runtime"].connect() as connection:
        atoms = connection.execute(text(
            f"SELECT count(*) FROM {schema.LEDGER_TABLE}")).scalar()
        cursors = connection.execute(text(
            f"SELECT count(*) FROM {schema.CURSOR_TABLE}")).scalar()
    return atoms, cursors


def test_postgres_bundle_to_read_apis_is_one_compiler_and_one_transaction(clean_pg_v2):
    case = clean_pg_v2
    _seed(case)
    base = _base_batch(case)
    session = case["sessionmaker"]()
    try:
        dry = preview_cursor_batch(
            case["compiled"], "input_rows", base, _cursor(base),
            SQLAlchemyVerifiedJoinBatchReader(session), *_registries())
        result = execute_cursor_batch(
            case["compiled"], "input_rows", base, _cursor(base),
            SQLAlchemyVerifiedJoinBatchReader(session), *_registries(), case["store"])
    finally:
        session.rollback()
        session.close()

    assert result.preview.candidate_semantics == dry.candidate_semantics
    assert result.store_result["inserted"] == dry.atom_count == 1
    assert _counts(case) == (1, 1)
    raw = case["runtime"].raw_connection()
    try:
        cursor = case["store"].read_cursor(raw, "input_rows")
        cov = coverage(raw, config=DEFAULT_RESOLVER_CONFIG)
        graph = structure(raw, config=DEFAULT_RESOLVER_CONFIG)
        walked = trace(
            "NO-LOT", lookup=SqlClaimLookup(raw, relation=schema.LEDGER_TABLE),
            config=DEFAULT_RESOLVER_CONFIG)
    finally:
        raw.close()
    assert cursor["translator_ver"] == result.preview.translator_version
    assert cursor["cursor_value"] == dict(result.preview.cursor_value)
    assert cov["state"] == "ready"
    assert graph["state"] == "ready"
    assert walked["hops"] and walked["terminal_reason"]
    with case["admin"].connect() as connection:
        assert connection.execute(text(
            f'SELECT count(*) FROM public."{SOURCE_TABLE}"')).scalar() == 1
        assert connection.execute(text(
            f'SELECT count(*) FROM public."{RIGHT_TABLE}"')).scalar() == 1


def test_postgres_missing_join_and_ambiguous_reader_leave_atom0_cursor0(clean_pg_v2):
    case = clean_pg_v2
    _seed(case, with_right=False)
    base = _base_batch(case)
    session = case["sessionmaker"]()
    try:
        with pytest.raises(SourcePreparationError) as missing:
            execute_cursor_batch(
                case["compiled"], "input_rows", base, _cursor(base),
                SQLAlchemyVerifiedJoinBatchReader(session), *_registries(),
                case["store"])
    finally:
        session.rollback()
        session.close()
    assert missing.value.code == "source_preparation_missing"
    assert _counts(case) == (0, 0)

    class AmbiguousReader(SQLAlchemyVerifiedJoinBatchReader):
        def read_chunk(self, descriptor, keys):
            key = keys[0]
            return {key: (
                JoinRightRow(key, {"row_id": "A"}, {"target_id": "A"}, NOW),
                JoinRightRow(key, {"row_id": "B"}, {"target_id": "B"}, NOW),
            )}

    session = case["sessionmaker"]()
    try:
        with pytest.raises(SourcePreparationError) as ambiguous:
            execute_cursor_batch(
                case["compiled"], "input_rows", base, _cursor(base),
                AmbiguousReader(session), *_registries(), case["store"])
    finally:
        session.rollback()
        session.close()
    assert ambiguous.value.code == "source_preparation_ambiguous"
    assert _counts(case) == (0, 0)


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_postgres_unapproved_binding_stops_before_atom_or_cursor(clean_pg_v2, status):
    case = clean_pg_v2
    raw = _bundle()
    raw["profiles"]["input-transition@1"]["mappings"][0]["bind"]["subject"][
        "keys"]["input_id"]["approval_status"] = status

    with pytest.raises(LedgerSetupValidationError) as exc:
        compile_setup_snapshot(
            validate_bundle(raw, catalog=CATALOG), trusted_implementations(),
            tuple(case["compiled"].verified_joins.values()), catalog=CATALOG)
    assert exc.value.code == "binding_not_approved"
    assert _counts(case) == (0, 0)


def test_postgres_cursor_snapshot_conflict_rolls_back_insert_and_cursor(clean_pg_v2):
    case = clean_pg_v2
    _seed(case)
    base = _base_batch(case)
    with case["runtime"].begin() as connection:
        connection.execute(text(f'''
            INSERT INTO {schema.CURSOR_TABLE}
                (source, translator_ver, cursor_value)
            VALUES ('input_rows', 'ledger-v2:older-snapshot', '{{}}'::jsonb)
        '''))
    session = case["sessionmaker"]()
    try:
        with pytest.raises(CursorVersionConflict):
            execute_cursor_batch(
                case["compiled"], "input_rows", base, _cursor(base),
                SQLAlchemyVerifiedJoinBatchReader(session), *_registries(),
                case["store"])
    finally:
        session.rollback()
        session.close()

    assert _counts(case) == (0, 1)
    raw = case["runtime"].raw_connection()
    try:
        stored = case["store"].read_cursor(raw, "input_rows")
    finally:
        raw.close()
    assert stored["translator_ver"] == "ledger-v2:older-snapshot"
    assert stored["cursor_value"] == {}


def test_postgres_replay_dedupes_and_same_snapshot_cursor_restarts_safely(clean_pg_v2):
    case = clean_pg_v2
    _seed(case)
    base = _base_batch(case)
    results = []
    for _ in range(2):
        session = case["sessionmaker"]()
        try:
            results.append(execute_cursor_batch(
                case["compiled"], "input_rows", base, _cursor(base),
                SQLAlchemyVerifiedJoinBatchReader(session), *_registries(),
                case["store"]))
        finally:
            session.rollback()
            session.close()

    assert results[0].store_result["inserted"] == 1
    assert results[1].store_result["inserted"] == 0
    assert results[1].store_result["deduped"] == 1
    assert _counts(case) == (1, 1)


def test_postgres_gate_refusal_stops_before_store_transaction(clean_pg_v2, monkeypatch):
    case = clean_pg_v2
    _seed(case)
    base = _base_batch(case)

    def refuse(*args, **kwargs):
        raise gate.MoleculeRefused("input_rows", "test_refusal", "forced gate refusal")

    monkeypatch.setattr(gate, "screen_compiled_molecule", refuse)
    session = case["sessionmaker"]()
    try:
        with pytest.raises(gate.MoleculeRefused):
            execute_cursor_batch(
                case["compiled"], "input_rows", base, _cursor(base),
                SQLAlchemyVerifiedJoinBatchReader(session), *_registries(),
                case["store"])
    finally:
        session.rollback()
        session.close()
    assert _counts(case) == (0, 0)


def test_postgres_right_unique_index_is_used_by_the_join_probe(clean_pg_v2):
    case = clean_pg_v2
    _seed(case)
    with case["admin"].begin() as connection:
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(row[0] for row in connection.execute(text(
            f'EXPLAIN SELECT target_id FROM public."{RIGHT_TABLE}" '
            "WHERE join_id = 'J-0001'")))
    assert UNIQUE_INDEX in plan
    assert "Index Scan" in plan


def test_stage7_manifest_selected_lot_event_uses_existing_store_cursor_transaction(
        clean_pg_v2):
    case = clean_pg_v2
    with case["runtime"].begin() as connection:
        connection.execute(text("""
            CREATE TABLE lot_event (
                lot_id TEXT NOT NULL,
                event_time TIMESTAMPTZ NOT NULL,
                txn_seq TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                parent_lot TEXT,
                child_lot TEXT,
                slotnumbers TEXT,
                waferids TEXT
            )
        """))
        connection.execute(text("""
            INSERT INTO lot_event
                (lot_id, event_time, txn_seq, event_type, parent_lot,
                 child_lot, slotnumbers, waferids)
            VALUES
                ('P', :event_at, 'R1', 'split', '', 'C', '1:2', 'W1:W2'),
                ('C', :event_at, 'R2', 'split', 'P', '', '3', 'W3')
        """), {"event_at": NOW})

    first = backfill.run(
        case["runtime"], {}, source="lot_event", fetch_rows=100,
        max_batches=1, ontology_root=DEFAULT_ONTOLOGY_ROOT)
    second = backfill.run(
        case["runtime"], {}, source="lot_event", fetch_rows=100,
        max_batches=1, ontology_root=DEFAULT_ONTOLOGY_ROOT)

    assert first["molecules"] == 1
    assert first["inserted"] == 10
    assert first["cursor"]["txn_seq"] == "R2"
    assert second["rows_read"] == 0
    assert second["inserted"] == 0
    with case["runtime"].connect() as connection:
        assert connection.execute(text(
            f"SELECT count(*) FROM {schema.LEDGER_TABLE}"
        )).scalar() == 10
        cursor = connection.execute(text(
            f"SELECT cursor_value FROM {schema.CURSOR_TABLE} "
            "WHERE source='lot_event'"
        )).scalar_one()
    assert cursor["txn_seq"] == "R2"
