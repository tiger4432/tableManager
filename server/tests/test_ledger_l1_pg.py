# -*- coding: utf-8 -*-
"""Ledger slice 1 - the proofs that only PostgreSQL can give.

Partitioning, jsonb type preservation, CHECK constraints and `ON CONFLICT` have no
SQLite spelling, so a suite that ran here on in-memory SQLite would prove nothing about
what production does. This project has paid for that lesson three times ("SQLite accepts
what PostgreSQL refuses", most recently 2026-08-05), so these tests run against a real
isolated PostgreSQL or they SKIP - they never quietly downgrade.

ISOLATION
---------
Declared by the operator through `ASSY_PG_TEST_DATABASE_URL` (or a PostgreSQL
`ASSY_TEST_DATABASE_URL`), re-checked through `db_safety.check_test_database`, and
refused by name if it is the production database. Everything - including the SOURCE
table - is built inside a scratch schema that is dropped at teardown, and `public` is
NOT on the search path, so an unqualified statement is physically unable to reach a real
table.

🔴 THE SOURCE FIXTURE IS OURS, NOT THE DATABASE'S
--------------------------------------------------
`lot_event` is recreated inside the scratch schema and seeded here rather than read from
the isolated database's own copy. That copy is shared: this lane found two hand-edited
rows in it, edited by somebody else, between two runs an hour apart. A test whose
expected counts depend on a table other people are editing does not fail - it flaps, and
then it gets deleted.
"""
import contextlib
import copy
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import gate, observability, schema, store as ledger_store   # noqa: E402
from ledger import backfill                                             # noqa: E402

PG_TEST_URL_ENV = "ASSY_PG_TEST_DATABASE_URL"
SCRATCH_SCHEMA = "assy_ledger_l1_pytest" + (
    "_" + os.environ["PYTEST_XDIST_WORKER"]
    if os.environ.get("PYTEST_XDIST_WORKER") else "")


# --------------------------------------------------------------------------- isolation
def _resolve_url():
    import db_safety
    from database.database import DEFAULT_PG_URL

    url = os.environ.get(PG_TEST_URL_ENV) or None
    if not url:
        candidate = os.environ.get(db_safety.TEST_DATABASE_URL_ENV) or ""
        url = candidate if candidate.startswith("postgres") else None
    if not url:
        return None, (
            f"no PostgreSQL test database declared. Set {PG_TEST_URL_ENV} to an "
            f"ISOLATED database, e.g. "
            f"{PG_TEST_URL_ENV}=postgresql://postgres:...@localhost:5432/assy_qa")

    violations = db_safety.check_test_database(url, production_url=DEFAULT_PG_URL,
                                               opt_in=url)
    if violations:
        return None, f"{PG_TEST_URL_ENV} is not usable: {violations[0]}"

    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        return None, f"{PG_TEST_URL_ENV} is not a PostgreSQL URL"
    if (parsed.database or "") == "assy_manager":
        return None, "refusing to run schema DDL against 'assy_manager'"
    return url, None


@contextlib.contextmanager
def _declared_as_test_database(url):
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


SOURCE_DDL = """
CREATE TABLE lot_event (
    business_key_val TEXT PRIMARY KEY,
    lot              TEXT,
    event_type       TEXT,
    parent_lot       TEXT,
    child_lot        TEXT,
    slot_numbers     TEXT,
    wafer_ids        TEXT,
    equipment        TEXT,
    event_time       TEXT
)
"""

DESTINATION_INVENTORY_DDL = """
CREATE TABLE destination_inventory (
    row_id           TEXT PRIMARY KEY,
    business_key_val TEXT,
    container        JSONB
)
"""


def _seed(connection, rows):
    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE lot_event")
        for r in rows:
            cursor.execute(
                "INSERT INTO lot_event (business_key_val, lot, event_type, parent_lot, "
                "child_lot, slot_numbers, wafer_ids, equipment, event_time) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (f"{r['lot']}|{r['event_type']}|{r['event_time']}", r["lot"],
                 r["event_type"], r.get("parent_lot"), r.get("child_lot"),
                 r.get("slot_numbers", ""), r.get("wafer_ids", ""),
                 r.get("equipment"), r["event_time"]))
    connection.commit()


def src(lot, event_type="split", parent_lot=None, child_lot=None, slots="", wafers="",
        event_time="2026-05-03 02:17:00"):
    return {"lot": lot, "event_type": event_type, "parent_lot": parent_lot,
            "child_lot": child_lot, "slot_numbers": slots, "wafer_ids": wafers,
            "event_time": event_time}


#: One split (two rows) + one track_in. 2 lots + 4 wafers + 1 track_in lot + 2 wafers.
BASE_ROWS = [
    src("P", child_lot="C", slots="07:08", wafers="W7:W8"),
    src("C", parent_lot="P", slots="01:02", wafers="W1:W2"),
    src("T", event_type="track_in", slots="01:02:03", wafers="X1::X3",
        event_time="2026-06-01 00:00:00"),
]

CFG = {
    "version": 1,
    "batch": {"molecules_per_transaction": 200},
    "lag": {"probe_interval_seconds": 0},
    "sources": {"lot_event": {
        "occurred_at_column": "event_time",
        "occurred_at_format": "%Y-%m-%d %H:%M:%S",
        "occurred_at_timezone": "UTC",
        "subject_types": ["Lot", "Wafer"],
        "register_entity_types": ["Lot", "Wafer"],
        "list_separator": ":",
        "columns": {"row_identity": "business_key_val", "lot": "lot",
                    "event_type": "event_type", "parent_lot": "parent_lot",
                    "child_lot": "child_lot", "slots": "slot_numbers",
                    "wafers": "wafer_ids", "equipment": "equipment"},
        "vocabulary": {
            "split": {"lineage": "parent_child", "slot_pairing": "slot_preserving"},
            "merge": {"lineage": "parent_child", "slot_pairing": "shared_wafer"},
            "track_in": {"lineage": "none", "slot_pairing": "none"},
        },
    }},
}


@pytest.fixture(scope="module")
def pg():
    url, reason = _resolve_url()
    if url is None:
        pytest.skip(reason)
    try:
        import psycopg2  # noqa: F401
    except Exception as exc:                                     # pragma: no cover
        pytest.skip(f"psycopg2 is not importable: {exc}")

    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool

    with _declared_as_test_database(url):
        # `public` is deliberately OFF the search path: an unqualified statement then
        # cannot reach a real table even if one of these tests is wrong.
        engine = create_engine(
            url, poolclass=NullPool,
            connect_args={"options": f"-csearch_path={SCRATCH_SCHEMA}"})
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except OperationalError as exc:
            engine.dispose()
            pytest.skip(f"PostgreSQL is not reachable: "
                        f"{str(exc).strip().splitlines()[0]}")

        admin = create_engine(url, poolclass=NullPool)
        with admin.begin() as conn:
            # Reclaim a leftover from a run that was killed mid-suite, then build fresh.
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
            conn.execute(text(f'CREATE SCHEMA "{SCRATCH_SCHEMA}"'))
            # Ledger's existing text-search indexes use ``gin_trgm_ops``.  ``public`` is
            # deliberately absent from this test engine's search_path, so the extension
            # must live inside the same disposable schema as the ledger objects.  Dropping
            # the schema at teardown drops the extension too; nothing is installed into
            # the isolated database's public schema and production is never connected.
            conn.execute(text(
                f'CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA "{SCRATCH_SCHEMA}"'))
        with engine.begin() as conn:
            conn.execute(text(SOURCE_DDL))
            conn.execute(text(DESTINATION_INVENTORY_DDL))
        try:
            yield engine
        finally:
            engine.dispose()
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
                # ASK THE CATALOGUE. A reviewer reported a dropped schema on 2026-08-12
                # and left 92 objects behind; "I issued a DROP" is not the same fact as
                # "it is gone".
                left = conn.execute(text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = :s"), {"s": SCRATCH_SCHEMA}).scalar()
                assert left == 0, f"{left} object(s) left behind in {SCRATCH_SCHEMA}"
            admin.dispose()


@pytest.fixture
def ledger(pg):
    """A clean ledger and a seeded source for each test."""
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        connection = pg.raw_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP TABLE IF EXISTS {schema.LEDGER_TABLE} CASCADE")
                cursor.execute(f"DROP TABLE IF EXISTS {schema.CURSOR_TABLE} CASCADE")
                cursor.execute("TRUNCATE destination_inventory")
            connection.commit()
            _seed(connection, BASE_ROWS)
        finally:
            connection.close()
        gate.reset_counters()
        observability.reset_probe_throttle()
        yield pg
        gate.reset_counters()


def run(engine, **kwargs):
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        return backfill.run(engine, copy.deepcopy(CFG), source="lot_event", **kwargs)


def count(engine, where="TRUE", params=()):
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT count(*) FROM {schema.LEDGER_TABLE} WHERE {where}",
                           params)
            return cursor.fetchone()[0]
    finally:
        connection.close()


# ----------------------------------------------------------------------- idempotency
def test_the_cursor_makes_a_second_run_read_nothing(ledger):
    """Net 1. The brief's risk 1: a re-run must not duplicate atoms."""
    first = run(ledger)
    assert first["inserted"] > 0
    total = count(ledger)

    second = run(ledger)
    assert second["rows_read"] == 0
    assert second["attempted"] == 0
    assert count(ledger) == total


def _mapper_cfg():
    cfg = copy.deepcopy(CFG)
    cfg["sources"]["lot_event"]["chain_mapper"] = {
        "mapper_id": "lot-event", "version": 1,
    }
    return cfg


PROFILE_EVENT_TIME = "2026-08-17T01:02:03+00:00"
PROFILE_SOURCE_ROW = src(
    "PROFILE", event_type="track_in", slots="01", wafers="W-PROFILE",
    event_time=PROFILE_EVENT_TIME)
PROFILE_ROW_ID = (
    f"{PROFILE_SOURCE_ROW['lot']}|{PROFILE_SOURCE_ROW['event_type']}|"
    f"{PROFILE_SOURCE_ROW['event_time']}")


def _approved_binding(kind, *, status="approved", **values):
    return {
        "kind": kind,
        **values,
        "binding_origin": "user_declared",
        "approval_status": status,
    }


def _profile_mapper_cfg(*, nested_key_status="approved"):
    cfg = copy.deepcopy(CFG)
    cfg["profiles"] = {"lot-transfer-v1": {
        "profile_version": 1,
        "source": "lot_event",
        "packs": ["transfer@1"],
        "mappings": [{
            "mapping_id": "movement",
            "use": "transfer/movement",
            "bind": {
                "subject": _approved_binding("column", column="wafers"),
                "from": _approved_binding(
                    "constant", value="source_position"),
                "to": _approved_binding(
                    "declared_lookup",
                    lookup_id="destination_inventory",
                    key=_approved_binding(
                        "column", status=nested_key_status,
                        column="row_identity"),
                    select="container"),
                "occurred_at": _approved_binding(
                    "column", column="event_time"),
            },
        }],
    }}
    cfg["sources"]["lot_event"]["chain_mapper"] = {
        "mapper_id": "canonical-profile",
        "version": 1,
        "profile_id": "lot-transfer-v1",
    }
    return cfg


def _seed_profile_source_and_destination(engine, matches):
    connection = engine.raw_connection()
    try:
        _seed(connection, [PROFILE_SOURCE_ROW])
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE destination_inventory")
            for index in range(matches):
                cursor.execute(
                    "INSERT INTO destination_inventory "
                    "(row_id, business_key_val, container) "
                    "VALUES (%s, %s, %s::jsonb)",
                    (f"destination-{index}", PROFILE_ROW_ID,
                     '{"type":"dt_slot","keys":{"dt_lot":"D1",'
                     '"dt_slot":"01"},"position":null}'),
                )
        connection.commit()
    finally:
        connection.close()


def _destination_count(engine):
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM destination_inventory")
            return cursor.fetchone()[0]
    finally:
        connection.close()


@contextlib.contextmanager
def _rebuilt_mapper_registry():
    """Let fault-injection tests fingerprint their temporary mapper, then forget it."""
    from ledger.chain_mapper import default_ledger_mapper_registry

    default_ledger_mapper_registry.cache_clear()
    try:
        yield
    finally:
        default_ledger_mapper_registry.cache_clear()


def test_lot_event_chain_mapper_runs_the_existing_cursor_gate_and_store_end_to_end(
        ledger, monkeypatch):
    """The required migrated source path, against isolated PostgreSQL."""
    from datetime import timezone
    from ledger import dry_run
    from ledger import chain_mapper
    import pandas as pd

    # Capture the actual validated LedgerFrame on both sides of the dry-run/execute
    # fork.  This proves parity at the requested boundary rather than inferring it from
    # atom counts after storage has discarded molecule_ref/derivation.
    mapped_frames = []
    run_mapper = chain_mapper.run_registered_mapper

    def capture_mapper(*args, **kwargs):
        frame = run_mapper(*args, **kwargs)
        mapped_frames.append(frame.copy(deep=True))
        return frame

    monkeypatch.setattr(chain_mapper, "run_registered_mapper", capture_mapper)

    cfg = _mapper_cfg()
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        preview = dry_run.preview(ledger, cfg, "lot_event", rows=20)
        preview_frames = list(mapped_frames)
        preview_check = ledger.raw_connection()
        try:
            with preview_check.cursor() as cursor_sql:
                cursor_sql.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = current_schema() AND table_name IN (%s, %s)",
                    (schema.LEDGER_TABLE, schema.CURSOR_TABLE))
                assert cursor_sql.fetchone()[0] == 0
        finally:
            preview_check.close()
        landed = backfill.run(ledger, cfg, source="lot_event")
        execute_frames = mapped_frames[len(preview_frames):]

    assert preview["writes"] == 0 and preview["read_only_enforced"] is True
    assert preview["atoms"] == landed["attempted"]
    assert landed["inserted"] > 0
    assert "mapper:lot-event@1:" in landed["translator_ver"]
    cursor = read_cursor_row(ledger)
    assert cursor["translator_ver"] == landed["translator_ver"]
    assert cursor["cursor_value"] == {"event_time": BASE_ROWS[-1]["event_time"]}
    assert len(preview_frames) == len(execute_frames) == 2
    for dry_frame, execute_frame in zip(preview_frames, execute_frames):
        pd.testing.assert_frame_equal(
            dry_frame.reset_index(drop=True), execute_frame.reset_index(drop=True))

    connection = ledger.raw_connection()
    try:
        with connection.cursor() as cursor_sql:
            cursor_sql.execute(
                f"SELECT count(DISTINCT source_event_id), "
                f"bool_and(source_event_state = 'source_molecule'), "
                f"bool_and(source_translator_ver LIKE %s) "
                f"FROM {schema.LEDGER_TABLE}",
                ("%|mapper:lot-event@1:%",))
            events, all_molecules, provenance = cursor_sql.fetchone()
            cursor_sql.execute(
                f"SELECT predicate, subject_type, subject_keys, object_kind, "
                f"object_payload, occurred_at, source_who, source_translator_ver, "
                f"source_raw_ref, source_event_id::text, source_event_state "
                f"FROM {schema.LEDGER_TABLE}")
            columns = [item[0] for item in cursor_sql.description]
            stored = [dict(zip(columns, row)) for row in cursor_sql.fetchall()]
            cursor_sql.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name LIKE '%cursor%' "
                "ORDER BY table_name")
            cursor_tables = [row[0] for row in cursor_sql.fetchall()]
    finally:
        connection.close()
    assert events == preview["molecules"] == 2
    assert all_molecules is True and provenance is True
    assert cursor_tables == [schema.CURSOR_TABLE], (
        "the migrated source created a second/Chain cursor table")
    assert len(stored) == preview["atoms"]
    assert all(row["source_who"] == "lot_event" for row in stored)
    assert all(row["source_raw_ref"].startswith("lot_event:") for row in stored)
    assert all(row["source_event_state"] == "source_molecule" for row in stored)
    derived = next(row for row in stored if row["predicate"] == "derived_from")
    assert derived["subject_type"] == "Lot"
    assert derived["subject_keys"] == {"lot": "C"}
    assert derived["object_kind"] == "entity_ref"
    assert derived["object_payload"] == {"type": "Lot", "keys": {"lot": "P"}}
    assert derived["occurred_at"].astimezone(timezone.utc).isoformat() == (
        "2026-05-03T02:17:00+00:00")
    preview_ids = {row["source_event_id"] for row in preview["atoms_rendered"]}
    stored_ids = {row["source_event_id"] for row in stored}
    assert stored_ids == preview_ids

    # Reset exercises the same mapper and the existing unique index. No second ledger
    # or Chain cursor exists, and replay does not duplicate the same claims.
    before = count(ledger)
    with _declared_as_test_database(url):
        replay = backfill.run(ledger, cfg, source="lot_event", reset_cursor=True)
    assert replay["attempted"] > 0
    assert replay["inserted"] == 0
    assert replay["deduped"] == replay["attempted"]
    assert count(ledger) == before


def test_canonical_profile_dry_run_execute_gate_store_and_cursor_end_to_end(
        ledger, monkeypatch):
    """One validated Profile drives the real PostgreSQL path without a second cursor."""
    import pandas as pd
    from ledger import chain_mapper, config as ledger_config, dry_run

    _seed_profile_source_and_destination(ledger, matches=1)
    cfg = _profile_mapper_cfg()
    ledger_config.validate(cfg)

    mapped_frames = []
    real_run = chain_mapper.run_registered_mapper

    def capture(*args, **kwargs):
        frame = real_run(*args, **kwargs)
        mapped_frames.append(frame.copy(deep=True))
        return frame

    monkeypatch.setattr(chain_mapper, "run_registered_mapper", capture)
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        preview = dry_run.preview(ledger, cfg, "lot_event", rows=20)
        preview_frames = list(mapped_frames)
        landed = backfill.run(ledger, cfg, source="lot_event")
        execute_frames = mapped_frames[len(preview_frames):]

    assert preview["writes"] == 0 and preview["read_only_enforced"] is True
    assert preview["atoms"] == landed["attempted"] == landed["inserted"] == 1
    assert len(preview_frames) == len(execute_frames) == 1
    pd.testing.assert_frame_equal(
        preview_frames[0].reset_index(drop=True),
        execute_frames[0].reset_index(drop=True))
    assert _destination_count(ledger) == 1, "lookup adapter mutated its source table"

    cursor = read_cursor_row(ledger)
    assert cursor["cursor_value"] == {"event_time": PROFILE_EVENT_TIME}
    assert "mapper:canonical-profile@1:" in cursor["translator_ver"]
    assert "profile:lot-transfer-v1:" in cursor["translator_ver"]
    connection = ledger.raw_connection()
    try:
        with connection.cursor() as sql_cursor:
            sql_cursor.execute(
                f"SELECT predicate, subject_keys, object_payload, source_raw_ref, "
                f"source_event_id::text, source_event_state "
                f"FROM {schema.LEDGER_TABLE}")
            stored = sql_cursor.fetchone()
    finally:
        connection.close()
    assert stored[0] == "transferred"
    assert stored[1] == {"wafer": "W-PROFILE"}
    assert stored[2]["to"] == {
        "type": "dt_slot", "keys": {"dt_lot": "D1", "dt_slot": "01"},
        "position": None,
    }
    assert stored[3].startswith("lot_event:")
    assert stored[5] == "source_molecule"
    assert {row["source_event_id"] for row in preview["atoms_rendered"]} == {stored[4]}


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_canonical_profile_unapproved_binding_writes_no_atom_and_no_cursor(
        ledger, status):
    from ledger import config as ledger_config, dry_run
    from ledger.chain_mapper import LedgerMapperError

    _seed_profile_source_and_destination(ledger, matches=1)
    cfg = _profile_mapper_cfg(nested_key_status=status)
    ledger_config.validate(cfg)  # structurally valid draft; readiness is runtime-only
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        with pytest.raises(LedgerMapperError) as preview_error:
            dry_run.preview(ledger, cfg, "lot_event", rows=20)
        with pytest.raises(LedgerMapperError) as execute_error:
            backfill.run(ledger, cfg, source="lot_event")
    assert preview_error.value.code == execute_error.value.code == "binding_not_approved"
    assert count(ledger) == 0
    assert read_cursor_row(ledger) is None
    assert _destination_count(ledger) == 1


@pytest.mark.parametrize(("matches", "code"), [
    (0, "lookup_not_found"),
    (2, "lookup_not_unique"),
])
def test_canonical_profile_lookup_cardinality_failure_writes_no_atom_and_no_cursor(
        ledger, matches, code):
    from ledger import config as ledger_config, dry_run
    from ledger.chain_mapper import LedgerMapperError

    _seed_profile_source_and_destination(ledger, matches=matches)
    cfg = _profile_mapper_cfg()
    ledger_config.validate(cfg)
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        with pytest.raises(LedgerMapperError) as preview_error:
            dry_run.preview(ledger, cfg, "lot_event", rows=20)
        with pytest.raises(LedgerMapperError) as execute_error:
            backfill.run(ledger, cfg, source="lot_event")
    assert preview_error.value.code == execute_error.value.code == code
    assert count(ledger) == 0
    assert read_cursor_row(ledger) is None
    assert _destination_count(ledger) == matches


def test_chain_mapper_crash_writes_no_atom_and_does_not_move_cursor(
        ledger, monkeypatch):
    """An unexpected Python mapper failure is typed and consumes no source event."""
    import mappers.ledger_lot_event_mapper as mapper_module
    from ledger.chain_mapper import LedgerMapperError

    def crashes(_db, _payload, rule=None):
        del rule
        raise RuntimeError("injected mapper crash")

    monkeypatch.setattr(mapper_module, "map_lot_event_to_ledger_frame", crashes)
    cfg = _mapper_cfg()
    url, _ = _resolve_url()
    with _rebuilt_mapper_registry():
        with _declared_as_test_database(url):
            with pytest.raises(LedgerMapperError) as exc:
                backfill.run(ledger, cfg, source="lot_event")
    assert exc.value.code == "mapper_failed"
    assert count(ledger) == 0
    assert read_cursor_row(ledger) is None


def test_chain_mapper_schema_failure_writes_no_atom_and_does_not_move_cursor(
        ledger, monkeypatch):
    """A bad mapper result cannot reach gate/store or consume the source event."""
    import pandas as pd
    import mappers.ledger_lot_event_mapper as mapper_module
    from ledger.ledger_frame import LedgerFrameError

    def invalid_result(_db, _payload, rule=None):
        del rule
        return pd.DataFrame()

    monkeypatch.setattr(
        mapper_module, "map_lot_event_to_ledger_frame", invalid_result)
    cfg = _mapper_cfg()
    url, _ = _resolve_url()
    with _rebuilt_mapper_registry():
        with _declared_as_test_database(url):
            with pytest.raises(LedgerFrameError):
                backfill.run(ledger, cfg, source="lot_event")
    assert count(ledger) == 0
    assert read_cursor_row(ledger) is None


def test_chain_mapper_semantic_refusal_writes_no_atom_and_does_not_move_cursor(ledger):
    """The converted source stops on a mapper refusal instead of consuming it."""
    connection = ledger.raw_connection()
    try:
        _seed(connection, [AMBIGUOUS_ROW])
    finally:
        connection.close()
    cfg = _mapper_cfg()
    url, _ = _resolve_url()
    from ledger.chain_mapper import LedgerMapperRefused

    with _declared_as_test_database(url):
        with pytest.raises(LedgerMapperRefused):
            backfill.run(ledger, cfg, source="lot_event")
    assert count(ledger) == 0
    assert read_cursor_row(ledger) is None


def test_chain_mapper_later_event_failure_discards_prior_unflushed_event(ledger):
    """A later mapper refusal cannot make an earlier event in the batch land alone."""
    good = src(
        "GOOD", event_type="track_in", slots="01", wafers="WG",
        event_time="2026-06-01 00:00:00")
    connection = ledger.raw_connection()
    try:
        _seed(connection, [good, AMBIGUOUS_ROW])
    finally:
        connection.close()
    cfg = _mapper_cfg()
    url, _ = _resolve_url()
    from ledger.chain_mapper import LedgerMapperRefused

    with _declared_as_test_database(url):
        with pytest.raises(LedgerMapperRefused):
            backfill.run(ledger, cfg, source="lot_event")
    assert count(ledger) == 0
    assert read_cursor_row(ledger) is None


def test_chain_mapper_gate_rejection_writes_no_atom_and_does_not_move_cursor(ledger):
    """A valid frame rejected by the existing gate cannot land partially."""
    cfg = _mapper_cfg()
    cfg["sources"]["lot_event"]["subject_types"] = ["Lot"]
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        with pytest.raises(gate.MoleculeRefused):
            backfill.run(ledger, cfg, source="lot_event")
    assert count(ledger) == 0
    assert read_cursor_row(ledger) is None


def test_chain_mapper_store_failure_rolls_back_atoms_and_cursor(ledger, monkeypatch):
    """The mapper path retains LedgerStore's one-transaction atom/cursor boundary."""
    from ledger.store import LedgerStore

    def fail_cursor(*_args, **_kwargs):
        raise RuntimeError("injected cursor write failure")

    monkeypatch.setattr(LedgerStore, "_advance_cursor", fail_cursor)
    cfg = _mapper_cfg()
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        with pytest.raises(RuntimeError, match="injected cursor write failure"):
            backfill.run(ledger, cfg, source="lot_event")
    assert count(ledger) == 0
    assert read_cursor_row(ledger) is None


def test_chain_mapper_normal_empty_event_advances_the_existing_source_cursor(ledger):
    """A deliberate 0-Claim event follows the lineage source's existing cursor policy."""
    empty_row = src(
        "EMPTY", event_type="track_in", event_time="2026-07-01 00:00:00")
    connection = ledger.raw_connection()
    try:
        _seed(connection, [empty_row])
    finally:
        connection.close()
    cfg = _mapper_cfg()
    cfg["sources"]["lot_event"]["vocabulary"]["track_in"].update({
        "emit_register": False,
        "emit_has_wafer": False,
    })
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        result = backfill.run(ledger, cfg, source="lot_event")
    assert result["rows_read"] == 1 and result["molecules"] == 1
    assert result["attempted"] == result["inserted"] == 0
    assert count(ledger) == 0
    cursor = read_cursor_row(ledger)
    assert cursor["cursor_value"] == {"event_time": empty_row["event_time"]}
    assert cursor["molecules_done"] == 1


def test_the_unique_index_holds_when_the_cursor_is_reset(ledger):
    """Net 2, proven SEPARATELY. Net 1 alone would pass this file while net 2 was
    broken and nobody would know until an operator re-ran a backfill."""
    run(ledger)
    total = count(ledger)

    again = run(ledger, reset_cursor=True)
    assert again["attempted"] > 0, "the reset did not actually re-read anything, so " \
                                   "this test would prove nothing"
    assert again["inserted"] == 0
    assert again["deduped"] == again["attempted"]
    assert count(ledger) == total


def test_a_rule_change_produces_NEW_atoms_rather_than_silently_none(ledger):
    """Re-translating under a different convention is a different CLAIM, so it must
    land beside the old one - `source_translator_ver` is part of the atom's identity."""
    run(ledger)
    before = count(ledger)

    other = copy.deepcopy(CFG)
    other["sources"]["lot_event"]["vocabulary"]["split"]["slot_pairing"] = "shared_wafer"
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        again = backfill.run(ledger, other, source="lot_event", reset_cursor=True)
    assert again["inserted"] > 0
    assert count(ledger) > before


# ------------------------------------------------------------------ what does NOT land
def test_a_blank_wafer_id_produces_no_has_wafer_atom_in_the_database(ledger):
    run(ledger)
    slots = count(ledger,
                  "predicate = 'has_wafer' AND subject_keys = '{\"lot\":\"T\"}'::jsonb")
    assert slots == 2, "the track_in row declares three slots and two wafer ids"
    # Scoped to lot T on purpose: the split rows in the same fixture legitimately
    # occupy slot 02, and an unscoped count would pass for the wrong reason.
    assert count(ledger, "predicate = 'has_wafer' "
                         "AND subject_keys = '{\"lot\":\"T\"}'::jsonb "
                         "AND object_payload->'qualifiers'->>'slot' = '02'") == 0


def test_an_undeclared_event_type_is_refused_counted_and_NAMED_IN_THE_LOG(ledger, caplog):
    """🔴 Read from the OPERATOR'S LOG, not from the return value.

    A refusal a caller can see and an operator cannot is the silent-skip defect wearing
    a return type. The brief asks for this specific evidence.
    """
    connection = ledger.raw_connection()
    try:
        _seed(connection, BASE_ROWS + [
            src("Z", event_type="scrapped", slots="01", wafers="W9",
                event_time="2026-06-02 00:00:00")])
    finally:
        connection.close()

    with caplog.at_level(logging.INFO, logger="Ledger.Gate"):
        result = run(ledger)

    messages = "\n".join(r.getMessage() for r in caplog.records)
    assert "REFUSED" in messages
    assert "undeclared_vocabulary" in messages
    assert "scrapped" in messages
    assert "produced nothing" in messages

    assert result["refused_molecules"] == 1
    assert gate.refusals()[("lot_event", gate.REFUSE_UNDECLARED_VOCABULARY)] == 1
    assert gate.rows_refused()["lot_event"] == 1
    assert count(ledger, "subject_keys = '{\"lot\":\"Z\"}'::jsonb") == 0
    assert "undeclared_vocabulary" in (gate.note() or "")


# ================================================== THE REFUSAL BREAKDOWN (R-2026-08-13-F)
#
# Before this column, named refusal reasons could not be read out of the database at all:
# `gate._refusals` is process-local to THIS process, the web server deliberately never
# imports `server/ledger`, and the heartbeat note the gate writes is dropped by `/health`.
# The cursor row carried two aggregate integers and no names.
#
# 🔴 THE INVARIANT THE RULING PINS: the aggregates are the AUTHORITY and the JSONB is
# their breakdown, so `sum(refusal_reasons[*].count) == molecules_refused` at write time.
# If the breakdown were written outside the cursor-advance transaction it would drift, and
# that disagreement would then read as a false alarm on the very screen built to show
# trouble - a status strip that cries wolf about its own bookkeeping is worse than none.

#: A source row that fills BOTH sides of a pair. Refused as `ambiguous_pair` - a SECOND
#: reason in the same run, so the breakdown is proven to be per-reason rather than one
#: blob wearing a name.
AMBIGUOUS_ROW = src("A", event_type="split", parent_lot="P", child_lot="C",
                    slots="01", wafers="W1", event_time="2026-06-03 00:00:00")

#: An event_type nobody declared. Refused as `undeclared_vocabulary`.
UNDECLARED_ROW = src("Z", event_type="scrapped", slots="01", wafers="W9",
                     event_time="2026-06-02 00:00:00")


def read_cursor_row(engine, source="lot_event"):
    connection = engine.raw_connection()
    try:
        return ledger_store.LedgerStore(engine).read_cursor(connection, source)
    finally:
        connection.close()


def breakdown_disagreement(engine, source="lot_event"):
    """`None` when the breakdown adds up to the aggregate it explains, else why not.

    Read back from the DATABASE rather than from the run's return value: the whole
    point of the column is that a process which is not this one can see the names, so
    a check that consulted `gate.refusals()` would prove nothing about what was
    STORED. Returns a sentence rather than asserting, so the fault-injection round can
    use the same judgement without raising `AssertionError` on the arm where the guard
    works (both shared harnesses read that as success).
    """
    row = read_cursor_row(engine, source)
    if row is None:
        return f"no cursor row for {source!r} at all"
    reasons = row.get("refusal_reasons")
    if reasons is None:
        return (f"molecules_refused={row['molecules_refused']} and refusal_reasons is "
                f"NULL - the writer did not record the breakdown")
    explained = sum(int(entry["count"]) for entry in reasons.values())
    if explained != row["molecules_refused"]:
        return (f"the breakdown explains {explained} refusal(s) but the aggregate beside "
                f"it says {row['molecules_refused']}: {reasons}")
    return None


def test_a_refusal_reaches_the_cursor_column_BY_NAME(ledger):
    """🔴 FIRE THE PATH, DO NOT MERELY WRITE IT.

    A backfill that REFUSES something, and then the reason read back out of the column
    by a reader holding nothing but a database connection. Two different reasons in one
    run, because a breakdown that could only ever hold one key would pass a
    single-reason test while being useless.
    """
    connection = ledger.raw_connection()
    try:
        _seed(connection, BASE_ROWS + [UNDECLARED_ROW, AMBIGUOUS_ROW])
    finally:
        connection.close()

    result = run(ledger)
    assert result["refused_molecules"] == 2, (
        "the fixture did not refuse anything, so this test would prove nothing")

    row = read_cursor_row(ledger)
    reasons = row["refusal_reasons"]
    assert set(reasons) == {gate.REFUSE_UNDECLARED_VOCABULARY, gate.REFUSE_AMBIGUOUS_PAIR}, (
        f"the column does not name what was refused: {reasons}")
    assert reasons[gate.REFUSE_UNDECLARED_VOCABULARY]["count"] == 1
    assert reasons[gate.REFUSE_AMBIGUOUS_PAIR]["count"] == 1
    # `last_at` is stamped by the DATABASE clock in the same transaction as the count,
    # so it is comparable with `updated_at` beside it rather than with this machine's.
    assert reasons[gate.REFUSE_AMBIGUOUS_PAIR]["last_at"].endswith("+00:00")
    assert breakdown_disagreement(ledger) is None
    # And the atoms of the refused molecules did not land - the breakdown describes
    # molecules that were REALLY refused, not ones that were counted and written anyway.
    assert count(ledger, "subject_keys = '{\"lot\":\"Z\"}'::jsonb") == 0


def test_a_CLEAN_run_leaves_a_truthful_breakdown_rather_than_a_stale_one(ledger):
    """🔴 THE OTHER ARM. A guard tested on one arm is half-tested.

    Three facts, and the third is the one a "latest run wins" design would get wrong:

      1. a first run with nothing refused writes `{}` - the writer has owned this row
         and refused nothing. NOT NULL, which means "this row predates the column";
      2. a later run that refuses something adds to it;
      3. a clean run AFTER that leaves the earlier breakdown standing, because the
         aggregate beside it also still counts those refusals. The breakdown explains
         `molecules_refused`, and `molecules_refused` accumulates - so a clean run that
         emptied the breakdown would produce exactly the disagreement this column exists
         to prevent. What tells the operator the entry is old is `last_at`, which does
         NOT move when nothing of that reason happened.
    """
    clean = run(ledger)
    assert clean["refused_molecules"] == 0
    row = read_cursor_row(ledger)
    assert row["refusal_reasons"] == {}, (
        f"a clean run must write an EMPTY breakdown, not NULL (which means 'predates "
        f"the column') and not a fabricated one: {row['refusal_reasons']}")
    assert row["molecules_refused"] == 0
    assert breakdown_disagreement(ledger) is None

    # 2. now refuse something.
    connection = ledger.raw_connection()
    try:
        _seed(connection, BASE_ROWS + [UNDECLARED_ROW])
    finally:
        connection.close()
    dirty = run(ledger, reset_cursor=True)
    assert dirty["refused_molecules"] == 1
    after_refusal = read_cursor_row(ledger)
    stamped = after_refusal["refusal_reasons"][gate.REFUSE_UNDECLARED_VOCABULARY]
    assert stamped["count"] == 1
    assert breakdown_disagreement(ledger) is None

    # 3. and a clean run afterwards must not erase it, invent one, or re-stamp it.
    connection = ledger.raw_connection()
    try:
        _seed(connection, BASE_ROWS)
    finally:
        connection.close()
    again = run(ledger, reset_cursor=True)
    assert again["refused_molecules"] == 0
    final = read_cursor_row(ledger)
    assert final["molecules_refused"] == 1, "the aggregate lost a refusal it had counted"
    assert final["refusal_reasons"][gate.REFUSE_UNDECLARED_VOCABULARY] == stamped, (
        "a clean run moved an entry nothing happened to - `last_at` would then say a "
        "quiet reason fired just now, which is how a stale entry hides its own age")
    assert breakdown_disagreement(ledger) is None


def test_the_breakdown_and_the_aggregate_are_written_in_ONE_transaction(ledger):
    """The invariant across MANY batches, which is where a delta can go wrong.

    `molecules_per_transaction = 1` makes every molecule its own flush, so the run
    writes the cursor a dozen times and each write carries a delta rather than a running
    total. Summing a running total once per batch is the obvious way to write this and
    it over-counts by a factor of the batch count - a defect that a single-batch test
    cannot see, because with one batch the delta and the total are the same number.
    """
    connection = ledger.raw_connection()
    try:
        _seed(connection, BASE_ROWS + [UNDECLARED_ROW, AMBIGUOUS_ROW])
    finally:
        connection.close()

    per_molecule = copy.deepcopy(CFG)
    per_molecule["batch"]["molecules_per_transaction"] = 1
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        result = backfill.run(ledger, per_molecule, source="lot_event")

    assert result["batches"] >= 4, (
        f"only {result['batches']} batch(es) - the fixture did not exercise the "
        f"multi-batch path this test exists for")
    assert result["refused_molecules"] == 2
    assert breakdown_disagreement(ledger) is None
    row = read_cursor_row(ledger)
    assert sum(e["count"] for e in row["refusal_reasons"].values()) == 2


def test_a_SECOND_run_in_this_process_does_not_re_attribute_the_first_runs_refusals(
        ledger):
    """`gate._refusals` lives for the whole process, so the delta's baseline has to be
    taken from the gate AS IT IS at the start of a run rather than from zero.

    Otherwise the first batch of run 2 claims every refusal run 1 already recorded, the
    breakdown exceeds the aggregate, and the screen reports a bookkeeping fault. This is
    not a hypothetical process shape: this test file runs several backfills in one
    interpreter, and so does an operator sweeping two sources.
    """
    connection = ledger.raw_connection()
    try:
        _seed(connection, BASE_ROWS + [UNDECLARED_ROW])
    finally:
        connection.close()

    first = run(ledger)
    assert first["refused_molecules"] == 1
    assert gate.refusals()[("lot_event", gate.REFUSE_UNDECLARED_VOCABULARY)] == 1

    # 🔴 NO `gate.reset_counters()` here. The counters SURVIVING is the condition under
    # test; resetting them would test a process that does not exist.
    second = run(ledger, reset_cursor=True)
    assert second["refused_molecules"] == 1
    assert gate.refusals()[("lot_event", gate.REFUSE_UNDECLARED_VOCABULARY)] == 2

    assert breakdown_disagreement(ledger) is None
    row = read_cursor_row(ledger)
    assert row["molecules_refused"] == 2
    assert row["refusal_reasons"][gate.REFUSE_UNDECLARED_VOCABULARY]["count"] == 2


# =============================================== THE HALF REFUSAL (R-2026-08-13-H)
#
# Measured on a real backfill before the fix: the gate counted `atomicity_violation`, the
# log said "1 source row(s) produced nothing", `refused_molecules` was 0 and THREE atoms
# of that molecule were in the database. The cursor then read `molecules_refused = 0`
# beside a breakdown summing to 1, i.e. `refusals_unaccounted = -1` - the sign the ruling
# reserves for a real bookkeeping fault.
#
# 🔴 THE ROUTE IS `emit_has_wafer: false`, and it is not incidental. With has_wafer on,
# the same rows are read through the same `_positional_pairs` in an earlier loop, which
# refuses first and never reaches the slot map. Declaring it false is the reachable route
# the ruling names, and it is a config line rather than a patched function.

#: `emit_has_wafer: false` + a strategy that reads BOTH rows of the molecule.
SLOT_MAP_ONLY_SPLIT = {"lineage": "parent_child", "slot_pairing": "shared_wafer",
                       "emit_has_wafer": False}

#: The parent row lists two slots and one wafer. Under `shared_wafer` the parent row is
#: read ONLY by the slot map, so the refusal happens where the ruling says it does.
UNEQUAL_SPLIT = [src("P", child_lot="C", slots="07:08", wafers="W7"),
                 src("C", parent_lot="P", slots="01:02", wafers="W7:W8")]

#: The same molecule with equal lists: two shared wafers, so it lands with two slot maps.
WELL_FORMED_SPLIT = [src("P", child_lot="C", slots="07:08", wafers="W7:W8"),
                     src("C", parent_lot="P", slots="01:02", wafers="W7:W8")]

#: Kept beside the split so every run below also lands SOMETHING. A test whose only
#: molecule is refused cannot tell "refused" from "translated nothing at all".
TRACK_IN_ROWS = [r for r in BASE_ROWS if r["event_type"] == "track_in"]

#: Every atom of the split molecule, whichever side it is uttered from: the two lot
#: registers, the `derived_from` whose subject is C, and any slot map (subject P).
SPLIT_SUBJECTS = ("subject_keys IN ('{\"lot\":\"P\"}'::jsonb, '{\"lot\":\"C\"}'::jsonb) "
                  "OR object_payload->'keys'->>'lot' IN ('P','C')")


def _slot_map_only_cfg():
    cfg = copy.deepcopy(CFG)
    cfg["sources"]["lot_event"]["vocabulary"]["split"] = dict(SLOT_MAP_ONLY_SPLIT)
    return cfg


def _seed_split(engine, split_rows):
    connection = engine.raw_connection()
    try:
        _seed(connection, list(split_rows) + TRACK_IN_ROWS)
    finally:
        connection.close()


def refusals_unaccounted(engine, source="lot_event"):
    """`molecules_refused` minus what the breakdown explains, from the READER.

    Computed by `ledger_trace._cursor_rows` - the code that puts the number on the
    operator's screen - rather than re-derived here. A test that re-implements the
    arithmetic proves the arithmetic, not the screen.
    """
    from datetime import timezone as _tz

    import ledger_trace
    connection = engine.raw_connection()
    try:
        rows = ledger_trace._cursor_rows(connection, schema.CURSOR_TABLE, _tz.utc)
    finally:
        connection.close()
    for entry in rows:
        if entry.get("source") == source:
            return entry.get("refusals_unaccounted")
    return None


def test_a_refusal_inside_slot_map_lands_NOTHING_and_the_books_balance(ledger, caplog):
    """Ruling R-2026-08-13-H, both arms, through the REAL backfill.

    The refusing arm asserts three separate things, because any one of them alone can be
    true for the wrong reason: nothing of that molecule is in the database, the refusal is
    COUNTED and NAMED where a reader with only a connection can see it, and
    `refusals_unaccounted` is 0 rather than the -1 that was measured.
    """
    _seed_split(ledger, UNEQUAL_SPLIT)
    url, _ = _resolve_url()

    with caplog.at_level(logging.INFO, logger="Ledger.Gate"):
        with _declared_as_test_database(url):
            refused_run = backfill.run(ledger, _slot_map_only_cfg(), source="lot_event")

    assert "atomicity_violation" in "\n".join(r.getMessage() for r in caplog.records)
    assert refused_run["refused_molecules"] == 1, (
        "the aggregate did not count the refusal the gate recorded - that disagreement IS "
        "the defect, and it reads as refusals_unaccounted = -1")
    assert gate.refusals()[("lot_event", gate.REFUSE_ATOMICITY)] == 1
    assert count(ledger, SPLIT_SUBJECTS) == 0, (
        "atoms of a refused molecule are in the database - the molecule landed half")
    assert count(ledger) > 0, (
        "the run wrote nothing at all, so 'no atoms of the split' would be true for the "
        "wrong reason")

    row = read_cursor_row(ledger)
    assert row["refusal_reasons"][gate.REFUSE_ATOMICITY]["count"] == 1
    assert breakdown_disagreement(ledger) is None
    assert refusals_unaccounted(ledger) == 0, (
        "the reader still sees a bookkeeping fault on this cursor")

    # --- the other arm: the SAME declaration, a well formed molecule, lands whole.
    gate.reset_counters()
    _seed_split(ledger, WELL_FORMED_SPLIT)
    with _declared_as_test_database(url):
        landed = backfill.run(ledger, _slot_map_only_cfg(), source="lot_event",
                              reset_cursor=True)

    assert landed["refused_molecules"] == 0 and gate.refusals() == {}
    assert count(ledger, "predicate = 'slot_map'") == 2, (
        "the shared wafers produced no slot map, so the refusing arm would prove nothing "
        "about this configuration")
    assert count(ledger, "predicate = 'derived_from'") == 1
    assert count(ledger, "predicate = 'has_wafer' AND (" + SPLIT_SUBJECTS + ")") == 0, (
        "`emit_has_wafer: false` was ignored, so the refusal above did not come from the "
        "slot map path this ruling is about")
    assert refusals_unaccounted(ledger) == 0, (
        "a clean run left the aggregate and its breakdown disagreeing")


# ------------------------------------------------------------------- half landing
def _forced_failure_run(engine, commit_between_chunks):
    """Fail in the MIDDLE of one molecule's insert. Returns the atoms left behind.

    `INSERT_PAGE_SIZE` is dropped to 3 so a single molecule spans several statements,
    and the second statement raises. With the transaction boundary intact the answer
    must be zero; `commit_between_chunks=True` removes the boundary, which is the
    injection that proves this test can go red.
    """
    import psycopg2.extras
    original = psycopg2.extras.execute_values
    calls = {"n": 0}

    def failing(cursor, sql, argslist, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("injected failure in the middle of a molecule")
        original(cursor, sql, argslist, **kwargs)
        if commit_between_chunks:
            cursor.connection.commit()

    old_page = ledger_store.INSERT_PAGE_SIZE
    psycopg2.extras.execute_values = failing
    ledger_store.INSERT_PAGE_SIZE = 3
    try:
        with pytest.raises(RuntimeError):
            run(engine, fetch_rows=2)
    finally:
        psycopg2.extras.execute_values = original
        ledger_store.INSERT_PAGE_SIZE = old_page
    return count(engine)


def test_a_subject_type_the_source_never_declared_is_refused_by_the_REAL_backfill(
        ledger, caplog):
    """Ruling R-2026-08-13-D, proven where it has to be true: through `backfill.run`.

    🔴 WIRING, NOT PREDICATE. The unit file proves the gate refuses such an atom when it
    is handed one. That is not the same claim as "the declaration reaches the gate on the
    path production uses" - and this project has shipped a check nobody called before
    (`landed is not wired`, 2026-08-08). The field this ruling retired was itself exactly
    that: read into an attribute, passed to nothing.

    BOTH ARMS, on the same fixture: `Wafer` withdrawn from the declaration refuses every
    molecule that mentions a wafer, and putting it back lands them.
    """
    narrowed = copy.deepcopy(CFG)
    narrowed["sources"]["lot_event"]["subject_types"] = ["Lot"]
    url, _ = _resolve_url()

    with caplog.at_level(logging.INFO, logger="Ledger.Gate"):
        with _declared_as_test_database(url):
            refused_run = backfill.run(ledger, narrowed, source="lot_event")

    messages = "\n".join(r.getMessage() for r in caplog.records)
    assert "undeclared_subject_type" in messages, (
        "the operator's log does not name the refusal; a refusal only the caller can see "
        "is the silent-skip defect wearing a return type")
    assert refused_run["refused_molecules"] == 2, (
        "both molecules of the fixture mention wafers, so both must be refused whole")
    assert refused_run["attempted"] == 0 and count(ledger) == 0, (
        "the molecule is all-or-nothing: a refused Wafer atom takes its Lot atoms with it")
    assert gate.refusals()[("lot_event", gate.REFUSE_UNDECLARED_SUBJECT_TYPE)] == 2

    # --- the other arm: the SAME rows, with the type declared, land.
    gate.reset_counters()
    allowed = run(ledger, reset_cursor=True)
    assert allowed["inserted"] > 0
    assert count(ledger, "subject_type = 'Wafer'") > 0, (
        "no Wafer atom landed even with the type declared - the refusal above would then "
        "prove nothing about the declaration")
    assert gate.refusals() == {}


def test_a_molecule_cannot_land_half(ledger):
    """🔴 The brief's rule: the transaction unit is one source event. Force a failure
    after the first chunk of a molecule has already been INSERTed and show that nothing
    from that event survives."""
    left = _forced_failure_run(ledger, commit_between_chunks=False)
    assert left == 0, (f"{left} atom(s) survived a failure mid-molecule - the "
                       f"transaction boundary is not holding")


def test_the_cursor_does_not_advance_past_a_failed_batch(ledger):
    _forced_failure_run(ledger, commit_between_chunks=False)
    connection = ledger.raw_connection()
    try:
        assert ledger_store.LedgerStore(ledger).read_cursor(connection, "lot_event") is None
    finally:
        connection.close()


# ------------------------------------------------------------- type preservation, real
def test_integer_zero_and_string_zero_survive_the_jsonb_round_trip(ledger):
    """Design section 3: the render audit where integer 0 and string "0" became the
    same thing, and NULL became empty. Asserted against the real column, because the
    guarantee belongs to jsonb, not to Python."""
    from datetime import datetime, timezone
    from ledger.envelope import Atom, assert_type_preserving

    st = ledger_store.LedgerStore(ledger)
    st.ensure_schema()
    payload = {"type": "Lot", "keys": {"lot": "TYPES"},
               "qualifiers": {"int_zero": 0, "str_zero": "0", "true": True,
                              "one": 1, "float_one": 1.5, "null": None,
                              "empty": "", "nested": [0, "0", False]}}
    atom = Atom(subject_type="Lot", subject_keys={"lot": "TYPES"},
                predicate="derived_from", object_kind="entity_ref",
                object_payload=payload,
                occurred_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
                source_who="test", source_translator_ver="t", source_raw_ref="r")
    connection = ledger.raw_connection()
    try:
        st.ensure_partitions(connection, [atom.occurred_at])
        st.insert_atoms(connection, [atom])
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT object_payload FROM {schema.LEDGER_TABLE} WHERE id = %s",
                (str(atom.id),))
            back = cursor.fetchone()[0]
    finally:
        connection.close()

    # 12 scalars: type, keys.lot, seven qualifiers, three list elements. The count is
    # asserted so a walk that silently visits nothing cannot report success.
    assert assert_type_preserving(payload, back) == 12
    assert back["qualifiers"]["int_zero"] == 0 and isinstance(
        back["qualifiers"]["int_zero"], int)
    assert back["qualifiers"]["str_zero"] == "0" and isinstance(
        back["qualifiers"]["str_zero"], str)
    assert back["qualifiers"]["null"] is None
    assert back["qualifiers"]["empty"] == ""


# ------------------------------------------------------------------ storage-level guards
def _expect_integrity_error(engine, sql, params):
    import psycopg2
    connection = engine.raw_connection()
    try:
        with pytest.raises((psycopg2.errors.CheckViolation,
                            psycopg2.errors.UniqueViolation,
                            psycopg2.errors.NotNullViolation)):
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
            connection.commit()
        connection.rollback()
    finally:
        connection.close()


def test_only_register_may_have_no_object_and_register_may_have_nothing_else(ledger):
    ledger_store.LedgerStore(ledger).ensure_schema()
    connection = ledger.raw_connection()
    try:
        schema.ensure_partition(connection, __import__("datetime").datetime(
            2026, 5, 3, tzinfo=__import__("datetime").timezone.utc))
    finally:
        connection.close()

    base = (f"INSERT INTO {schema.LEDGER_TABLE} (id, subject_type, subject_keys, "
            f"predicate, object_kind, object_payload, occurred_at, source_who, "
            f"source_translator_ver, source_raw_ref, source_event_id, "
            f"source_event_state) VALUES "
            f"(gen_random_uuid(), 'Lot', %s::jsonb, %s, %s, %s::jsonb, "
            f"'2026-05-03T00:00:00+00', 'w', 'v', 'r', gen_random_uuid(), "
            f"'source_record')")

    # a register carrying an object
    _expect_integrity_error(ledger, base,
                            ('{"lot":"A"}', "register", "value", '1'))
    # a non-register carrying none
    _expect_integrity_error(ledger, base,
                            ('{"lot":"A"}', "has_wafer", None, None))
    # a subject key that is not a structured object
    _expect_integrity_error(ledger, base,
                            ('"P_C"', "register", None, None))


def test_atoms_route_into_the_month_partition_they_belong_to(ledger):
    result = run(ledger)
    assert set(result["partitions"]) == {"ledger_events_2026_05",
                                         "ledger_events_2026_06"}
    connection = ledger.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT tableoid::regclass::text, count(*) FROM {schema.LEDGER_TABLE} "
                f"GROUP BY 1 ORDER BY 1")
            routed = dict(cursor.fetchall())
    finally:
        connection.close()
    # `regclass::text` drops the schema when it is on the search path, which it is.
    assert set(routed) == {"ledger_events_2026_05", "ledger_events_2026_06"}
    assert sum(routed.values()) == count(ledger)


def test_the_ledger_is_partitioned_at_all(ledger):
    """A `CREATE TABLE` that quietly lost its `PARTITION BY` would pass every other
    test in this file, and re-adding it later is a full table rewrite."""
    ledger_store.LedgerStore(ledger).ensure_schema()
    connection = ledger.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT relkind FROM pg_class WHERE oid = to_regclass(%s)",
                           (schema.LEDGER_TABLE,))
            assert cursor.fetchone()[0] == "p", "ledger_events is not a partitioned table"
    finally:
        connection.close()


# ---------------------------------------------------------------------------- lag
def test_lag_says_never_started_before_the_first_run(ledger):
    ledger_store.LedgerStore(ledger).ensure_schema()
    st = ledger_store.LedgerStore(ledger)
    connection = ledger.raw_connection()
    try:
        report = observability.lag_report(st, "lot_event",
                                          CFG["sources"]["lot_event"],
                                          st.read_cursor(connection, "lot_event"))
    finally:
        connection.close()
    assert report["never_started"] is True
    assert report["cursor_position"] is None


def test_lag_counts_the_rows_behind_a_held_back_cursor(ledger):
    """The graph worker's defect was 'fresh-looking while behind'. Hold the cursor at
    the first event and the report must say how far behind it is."""
    run(ledger, start_from="2026-01-01 00:00:00", max_batches=1, fetch_rows=2)

    st = ledger_store.LedgerStore(ledger)
    connection = ledger.raw_connection()
    try:
        cursor_row = st.read_cursor(connection, "lot_event")
    finally:
        connection.close()
    observability.reset_probe_throttle()
    report = observability.lag_report(st, "lot_event", CFG["sources"]["lot_event"],
                                      cursor_row, force_probe=True)
    assert report["source_head"] == "2026-06-01 00:00:00"
    assert report["rows_behind"] == 1
    assert report["world_time_lag_seconds"] > 0
    assert "rows_behind=1" in observability.lag_note(report)


def test_lag_distinguishes_not_behind_from_not_asked(ledger):
    """Collapsing 'zero' and 'unknown' into one absent field is how a lag report starts
    lying by omission."""
    run(ledger)
    st = ledger_store.LedgerStore(ledger)
    connection = ledger.raw_connection()
    try:
        cursor_row = st.read_cursor(connection, "lot_event")
    finally:
        connection.close()

    observability.reset_probe_throttle()
    asked = observability.lag_report(st, "lot_event", CFG["sources"]["lot_event"],
                                     cursor_row, probe_interval=3600)
    assert asked["probe_allowed"] is True and asked["rows_behind"] == 0

    throttled = observability.lag_report(st, "lot_event", CFG["sources"]["lot_event"],
                                         cursor_row, probe_interval=3600)
    assert throttled["probe_allowed"] is False
    assert throttled["rows_behind"] is None
    assert "rows_behind=?" in observability.lag_note(throttled)


# ================================================================= FAULT INJECTION ROUND
#
# 🔴 The same discipline as the unit file: each PostgreSQL-level guard is made to go red
# by re-introducing the defect it exists for, and the COUNT of injections is asserted so
# an empty loop cannot report success.

def _inject_missing_transaction_boundary(engine):
    left = _forced_failure_run(engine, commit_between_chunks=True)
    if left == 0:
        raise AssertionError(
            "committing between chunks left no atoms behind, so the half-landing test "
            "would pass even with the boundary removed - the test proves nothing")
    raise ValueError(f"{left} atoms survived, as they must when the boundary is gone")


def _inject_duplicate_atom_past_the_unique_index(engine):
    """Write the same atom twice with `ON CONFLICT` disabled. The index must refuse."""
    import psycopg2
    from datetime import datetime, timezone
    from ledger.envelope import Atom, ROW_COLUMNS
    from psycopg2.extras import Json

    st = ledger_store.LedgerStore(engine)
    st.ensure_schema()
    when = datetime(2026, 5, 3, tzinfo=timezone.utc)
    connection = engine.raw_connection()
    try:
        st.ensure_partitions(connection, [when])
        event_id = __import__("uuid").uuid4()
        values = ("Lot", Json({"lot": "DUP"}), "register", None, None, when,
                  "w", "v", "r", None, event_id, "source_record")
        with connection.cursor() as cursor:
            for _ in range(2):
                cursor.execute(
                    f"INSERT INTO {schema.LEDGER_TABLE} ({', '.join(ROW_COLUMNS)}) "
                    f"VALUES (gen_random_uuid(), %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", values)
        connection.commit()
    except psycopg2.errors.UniqueViolation as exc:
        connection.rollback()
        raise ValueError(f"the unique index refused the duplicate: {exc}") from exc
    finally:
        connection.close()
    raise AssertionError("uq_ledger_atom accepted the SAME claim twice")


def _inject_register_with_an_object(engine):
    import psycopg2
    from datetime import datetime, timezone
    st = ledger_store.LedgerStore(engine)
    st.ensure_schema()
    connection = engine.raw_connection()
    try:
        st.ensure_partitions(connection, [datetime(2026, 5, 3, tzinfo=timezone.utc)])
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {schema.LEDGER_TABLE} (id, subject_type, subject_keys, "
                f"predicate, object_kind, occurred_at, source_who, "
                f"source_translator_ver, source_raw_ref, source_event_id, "
                f"source_event_state) VALUES "
                f"(gen_random_uuid(), 'Lot', '{{\"lot\":\"X\"}}'::jsonb, 'register', "
                f"'value', '2026-05-03T00:00:00+00', 'w', 'v', 'r', "
                f"gen_random_uuid(), 'source_record')")
        connection.commit()
    except psycopg2.errors.CheckViolation as exc:
        connection.rollback()
        raise ValueError(f"the CHECK constraint refused it: {exc}") from exc
    finally:
        connection.close()
    raise AssertionError("a register carrying an object was accepted")


def _inject_atom_outside_every_partition(engine):
    """A partitioned table with no matching partition must REFUSE, not silently drop.

    There is deliberately no DEFAULT partition: a default would accept a row whose
    `occurred_at` is nonsense (a bad time-column declaration, say) and hide it in a
    heap nobody queries.
    """
    import psycopg2
    st = ledger_store.LedgerStore(engine)
    st.ensure_schema()
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {schema.LEDGER_TABLE} (id, subject_type, subject_keys, "
                f"predicate, occurred_at, source_who, source_translator_ver, "
                f"source_raw_ref, source_event_id, source_event_state) VALUES "
                f"(gen_random_uuid(), 'Lot', "
                f"'{{\"lot\":\"X\"}}'::jsonb, 'register', '1999-01-01T00:00:00+00', "
                f"'w', 'v', 'r', gen_random_uuid(), 'source_record')")
        connection.commit()
    except psycopg2.Error as exc:
        connection.rollback()
        raise ValueError(f"no partition accepted it: {exc}") from exc
    finally:
        connection.close()
    raise AssertionError("a row landed with no partition to hold it")


def _inject_breakdown_that_does_not_add_up(engine):
    """Make the breakdown and the aggregate disagree, and see whether anything notices.

    The defect being re-introduced is the one ruling R-2026-08-13-F names: a breakdown
    written somewhere other than the aggregate's own transaction, which drifts. Here it
    is forced directly - the delta is swallowed while `refused` still counts - because
    the shape of the drift matters more than the mechanism that produced it.

    🔴 IT RETURNS NORMALLY WHEN THE GUARD ACCEPTS THE DEFECT, and raises `ValueError`
    when the guard catches it. Never `AssertionError` on the accepting arm: the shared
    harnesses treat that as "the guard raised", so an injection written the other way
    around reports success while proving nothing (`eb1ae8b`'s lane hit exactly this).
    """
    connection = engine.raw_connection()
    try:
        _seed(connection, BASE_ROWS + [UNDECLARED_ROW])
    finally:
        connection.close()

    original = backfill._refusal_delta
    backfill._refusal_delta = lambda gate_mod, source, baseline: (
        {}, original(gate_mod, source, baseline)[1])
    try:
        result = run(engine)
    finally:
        backfill._refusal_delta = original

    if result["refused_molecules"] != 1:
        # The injection did not reach the state it exists to create. Reported as the
        # guard ACCEPTING (a normal return), because "my mutation changed nothing" and
        # "the guard is fine" look identical from outside and only one of them is true.
        return
    complaint = breakdown_disagreement(engine)
    if complaint is None:
        return
    raise ValueError(f"the invariant caught the drift: {complaint}")


def _inject_slot_map_refusal_swallowed(engine):
    """The half refusal of 2026-08-13, put back and run against the real database.

    `... or []` cannot be written any more - the helper returns a list or unwinds - so the
    swallow is re-created as what a future author would type instead: a caller that
    catches the refusal and carries on with an empty list. If atoms then land beside a
    counted refusal, this file's guard has been proven to see the thing it was written
    for, down to the sign of `refusals_unaccounted`.

    🔴 RETURNS NORMALLY when the swallow changes nothing. Never `AssertionError` on that
    arm - the harness reads it as "the guard raised".
    """
    from ledger import lot_event_translator as translator_module

    _seed_split(engine, UNEQUAL_SPLIT)
    original = translator_module.LotEventTranslator._slot_map

    def swallowing(self, molecule, strategy, occurred_at):
        try:
            return original(self, molecule, strategy, occurred_at)
        except gate.MoleculeRefused:
            return []

    translator_module.LotEventTranslator._slot_map = swallowing
    url, _ = _resolve_url()
    try:
        with _declared_as_test_database(url):
            result = backfill.run(engine, _slot_map_only_cfg(), source="lot_event")
    finally:
        translator_module.LotEventTranslator._slot_map = original

    landed = count(engine, SPLIT_SUBJECTS)
    if not landed or result["refused_molecules"]:
        return                     # the swallow changed nothing this guard could see
    raise ValueError(
        f"the swallow left {landed} atom(s) of a refused molecule in the database with "
        f"refused_molecules={result['refused_molecules']} and refusals_unaccounted="
        f"{refusals_unaccounted(engine)} - the guard sees the half refusal")


PG_INJECTIONS = [
    ("transaction boundary removed", _inject_missing_transaction_boundary),
    ("duplicate atom past the unique index", _inject_duplicate_atom_past_the_unique_index),
    ("register carrying an object", _inject_register_with_an_object),
    ("atom outside every partition", _inject_atom_outside_every_partition),
    ("refusal breakdown that does not add up", _inject_breakdown_that_does_not_add_up),
    ("a fragment's refusal swallowed by its caller", _inject_slot_map_refusal_swallowed),
]

#: 4 built with this file + 1 added by ruling R-2026-08-13-F (the refusal breakdown must
#: agree with the aggregate it explains) + 1 by ruling R-2026-08-13-H (a refusal swallowed
#: between the gate and the writer).
EXPECTED_PG_INJECTIONS = 6


def test_pg_injection_count_is_declared():
    assert len(PG_INJECTIONS) == EXPECTED_PG_INJECTIONS


@pytest.mark.parametrize("name,injection", PG_INJECTIONS,
                         ids=[n for n, _ in PG_INJECTIONS])
def test_pg_guard_goes_red_under_injection(ledger, name, injection):
    with pytest.raises((AssertionError, ValueError)) as caught:
        injection(ledger)
    # An AssertionError here means the GUARD accepted the defect. A ValueError means
    # the guard refused it, which is the outcome being proven. Distinguishing them is
    # the whole point - both are "an exception was raised".
    assert not isinstance(caught.value, AssertionError), str(caught.value)
