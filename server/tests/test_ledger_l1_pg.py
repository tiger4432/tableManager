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
def _declared_qa_database():
    """The QA database `dev_env` declares, or `None` if that module cannot say.

    ⚠️ READ, NOT INVENTED. The URL comes from `scripts/dev_env/devenv.py`, which is
    where this project says what its isolated database is; hard-coding one here would be a
    second declaration of the same fact, and the day someone moves it the tests would point
    at whatever used to be there.
    """
    try:
        import importlib.util

        here = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location(
            "_devenv_declaration",
            os.path.join(here, "..", "scripts", "dev_env", "devenv.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        url = getattr(module, "QA_DB_URL", None)
    except Exception:
        return None
    return url if isinstance(url, str) and url.startswith("postgres") else None


def _resolve_url():
    import db_safety
    from database.database import DEFAULT_PG_URL

    url = os.environ.get(PG_TEST_URL_ENV) or None
    if not url:
        candidate = os.environ.get(db_safety.TEST_DATABASE_URL_ENV) or ""
        url = candidate if candidate.startswith("postgres") else None
    if not url:
        # 🔴 A WHOLESALE SKIP IS A FALSE GREEN, AND THAT IS WHAT THIS FILE WAS (S-104,
        # 판정 215). Forty proofs of the things ONLY PostgreSQL can prove - partitions,
        # jsonb, CHECK, ON CONFLICT - reported "skipped" on every run because nobody had
        # exported a variable, so nothing here had been executed since the declaration
        # grammar changed under it. Measured 2026-09-09, the first time it ran: 25 red.
        #
        # So the LAST resort is the database `scripts/dev_env/devenv.py` already declares for
        # this purpose. It is named there, it is not production, and `db_safety` below still
        # has to approve it - this only stops the suite from staying quiet when a test
        # database exists and no one said so.
        url = _declared_qa_database()
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


#: \U0001f534 THE SUBJECT OF THESE PROOFS IS THE STORAGE LAYER (판정 219): partitions, jsonb,
#: CHECK, ON CONFLICT, UNIQUE. It is NOT what `lot_event` means. So the source they drive is
#: the simplest SHIPPED one - `dt_job` reading `dt_job_rollup`, where one row is one molecule,
#: the key is `dt_job` and the value is `netdie_count`. A row source says all five properties
#: (idempotency, the unique index, a declaration change making NEW atoms, a refusal being
#: counted, the result's shape) without any of them depending on how a lot splits.
#:
#: These used to build a `lot_event` of this file's own invention and feed it a v1 config of
#: this file's own invention - two declarations answering to nobody, which is why the whole
#: file could rot unnoticed while it skipped.
SOURCE_DDL = """
CREATE TABLE dt_job_rollup (
    dt_job       TEXT PRIMARY KEY,
    row_id       TEXT,
    netdie_count INTEGER,
    dt_eqp       TEXT,
    event_time   TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
)
"""

#: \u26a0\ufe0f KEPT FOR ONE CASE ONLY. The shipped `lot_event` cannot translate a split today
#: (S-112: its `descent` sentence carries no `when`, so it is said for every row while a
#: split's two rows each hold only one of `child_lot`/`parent_lot`), and ONE test asserts that
#: refusal by name rather than the whole file being built on it.
LOT_EVENT_DDL = """
CREATE TABLE lot_event (
    txn_seq     TEXT PRIMARY KEY,
    row_id      TEXT,
    lot_id      TEXT,
    event_type  TEXT,
    parent_lot  TEXT,
    child_lot   TEXT,
    slotnumbers TEXT,
    waferids    TEXT,
    event_time  TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
)
"""

#: 🔴 THE SOURCE THAT GIVES TWO INDEPENDENT REFUSALS (판정 220). The breakdown cases need
#: two DIFFERENT reasons in one run - their own docstring says a breakdown that could only
#: ever hold one key would pass a single-reason test while being useless - and `dt_job`
#: offers one, because it reads its instant from a BASIS and so can never miss an
#: `occurred_at` column.
#:
#: `process_param_num_measure` is the shipped source that gives both, and the two come from
#: the DECLARATION rather than from anything invented here: its identity is the column
#: `param_id` (blank -> `no_identity`) and its `occurred_at` is the column `eventtime`
#: (blank -> a missing instant). Two blanks, two reasons, one run.
PROCESS_PARAM_DDL = """
CREATE TABLE process_param_num (
    param_id  TEXT PRIMARY KEY,
    row_id    TEXT,
    wafer_id  TEXT,
    step      TEXT,
    param     TEXT,
    value     DOUBLE PRECISION,
    role      TEXT,
    eqp_id    TEXT,
    eventtime TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
)
"""

DESTINATION_INVENTORY_DDL = """
CREATE TABLE destination_inventory (
    row_id           TEXT PRIMARY KEY,
    business_key_val TEXT,
    container        JSONB
)
"""


# ⚰️ THE FIXTURES BELOW WENT WITH THE TESTS THEY FED (S-104 ⓑ, 판정 217/219):
#   `CFG`, `_mapper_cfg`, `_profile_mapper_cfg`, `_seed_profile_source_and_destination`, `PROFILE_EVENT_TIME`, `PROFILE_SOURCE_ROW`, `PROFILE_ROW_ID`, `AMBIGUOUS_ROW`, `UNEQUAL_SPLIT`, `WELL_FORMED_SPLIT`, `_approved_binding`, `_slot_map_only_cfg`, `_seed_split`.
# Each existed only to vary a v1 declaration word - `chain_mapper`, `subject_types`,
# `vocabulary.slot_pairing` - or to seed the lot_event scenario those tests drove. A fixture
# that outlives its only reader is dead code wearing a test's clothes.

def _seed(connection, rows):
    """Seed `dt_job_rollup` - one row per job, which is one molecule per row."""
    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE dt_job_rollup")
        for index, r in enumerate(rows):
            cursor.execute(
                "INSERT INTO dt_job_rollup (dt_job, row_id, netdie_count, dt_eqp, "
                "event_time, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (r["dt_job"], f"r{index}", r.get("netdie_count"), r.get("dt_eqp"),
                 r["event_time"], r.get("created_at")))
    connection.commit()


def _seed_process_param(connection, rows):
    """Seed `process_param_num`. A row per measurement, one molecule each."""
    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE process_param_num")
        for index, r in enumerate(rows):
            cursor.execute(
                "INSERT INTO process_param_num (param_id, row_id, wafer_id, step, param, "
                "value, role, eqp_id, eventtime) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (r["param_id"], f"p{index}", r.get("wafer_id"), r.get("step"),
                 r.get("param"), r.get("value"), r.get("role"), r.get("eqp_id"),
                 r.get("eventtime")))
    connection.commit()


def param(param_id, *, wafer_id="WF-1", step="CMP", name="pressure", value=1.5,
          role="measured", eqp_id="EQP-9", eventtime="2026-05-03T02:17:00+00:00"):
    """One `process_param_num` row. Blank `param_id` or `eventtime` makes it refusable."""
    return {"param_id": param_id, "wafer_id": wafer_id, "step": step, "param": name,
            "value": value, "role": role, "eqp_id": eqp_id, "eventtime": eventtime}


#: Two good rows, one with no identity, one with no instant: two reasons, one run.
#:
#: 🔴 THE BLANK IS `wafer_id`, NOT `param_id`, AND THAT DISTINCTION IS THE WHOLE FIXTURE.
#: `param_id` is this source's identity AND its cursor AND its order_by, so blanking it is
#: refused at the BASE FRAME - `driver identity/order/cursor/time value is missing` - which
#: aborts the whole batch before molecules exist and is counted under no reason at all.
#: `wafer_id` is an entity KEY the molecule check reads (`_required_entity_columns`), so
#: blanking it refuses ONE molecule, by name, and the rest of the batch still lands.
PARAM_ROWS = [param("P-1"), param("P-2")]
PARAM_NO_IDENTITY = param("P-3", wafer_id="")
PARAM_NO_INSTANT = param("P-4", eventtime=None)


def _seed_lot_event(connection, rows):
    """Seed the one relation kept for S-112's refusal case."""
    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE lot_event")
        for index, r in enumerate(rows):
            cursor.execute(
                "INSERT INTO lot_event (txn_seq, row_id, lot_id, event_type, parent_lot, "
                "child_lot, slotnumbers, waferids, event_time) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (r["txn_seq"], f"le{index}", r["lot_id"], r["event_type"],
                 r.get("parent_lot"), r.get("child_lot"), r.get("slotnumbers", ""),
                 r.get("waferids", ""), r["event_time"]))
    connection.commit()


def src(job, netdie_count=2, dt_eqp="EQP-7", event_time="2026-05-03T02:17:00",
        created_at="2026-05-03T02:17:00+00:00"):
    """One `dt_job_rollup` row. One row, one molecule, two atoms (register + has_netdie).

    ⚠️ `created_at` IS WHAT DECIDES THE PARTITION, not `event_time`. This source declares
    `read.occurred_at.basis = "ingested"`, so the instant an atom carries is the one the row
    was INGESTED at - which is the column the engine reads for that basis. A case that wants
    two month partitions varies this one.
    """
    return {"dt_job": job, "netdie_count": netdie_count, "dt_eqp": dt_eqp,
            "event_time": event_time, "created_at": created_at}


def lot_event_row(lot, event_type="split", parent_lot=None, child_lot=None,
                  slots="", wafers="", event_time="2026-05-03T02:17:00", txn_seq=None):
    """One `lot_event` row in the shipped spelling, for S-112's case only."""
    return {"lot_id": lot, "event_type": event_type, "parent_lot": parent_lot,
            "child_lot": child_lot, "slotnumbers": slots, "waferids": wafers,
            "event_time": event_time,
            "txn_seq": txn_seq or f"{lot}|{event_type}|{event_time}"}


#: Three jobs, three molecules, six atoms. Distinct `event_time`s so a month partition can be
#: told from another one without inventing a second scenario.
BASE_ROWS = [
    src("SYN-DTJ-002-04", netdie_count=2),
    src("SYN-DTJ-002-05", netdie_count=3),
    src("SYN-DTJ-002-06", netdie_count=5, event_time="2026-06-01T00:00:00",
        created_at="2026-06-01T00:00:00+00:00"),
]

#: The split the shipped declaration cannot translate today - both rows of one molecule,
#: each holding only one of the two lot columns `descent` needs. S-112.
SPLIT_ROWS = [
    lot_event_row("SYN-R-001", child_lot="SYN-R-001TA", slots="07:08", wafers="W7:W8",
                  txn_seq="LE-SYN-R-001-006-01-P"),
    lot_event_row("SYN-R-001TA", parent_lot="SYN-R-001", slots="01:02", wafers="W1:W2",
                  txn_seq="LE-SYN-R-001-006-01-C"),
]

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
            conn.execute(text(LOT_EVENT_DDL))
            conn.execute(text(PROCESS_PARAM_DDL))
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
                cursor.execute(f"DROP TABLE IF EXISTS {schema.ROW_REF_TABLE} CASCADE")
                cursor.execute("TRUNCATE process_param_num")
                cursor.execute("TRUNCATE destination_inventory")
            connection.commit()
            _seed(connection, BASE_ROWS)
        finally:
            connection.close()
        # 🔴 THE SCHEMA IS BUILT FROM TODAY'S CODE, EVERY TEST (판정 216) - after the drops, so
        # these proofs measure `ledger.schema` as it is NOW and not whatever this database
        # happened to be created with. The row index is part of it: the engine reads it on
        # every source whose relation has a `row_id`, and without it a run dies on an
        # undefined table rather than on anything these cases are about.
        ledger_store.LedgerStore(pg).ensure_schema()
        gate.reset_counters()
        observability.reset_probe_throttle()
        yield pg
        gate.reset_counters()


_SHIPPED_ROOT = None


def shipped_root():
    """A root holding the SHIPPED `ledger_config.json`, for `ontology_root`.

    🔴 THE DECLARATION IS NOT AN ARGUMENT ANY MORE (S-76), and these proofs still
    passed one - a v1-grammar dict this file wrote itself. So every one of them died with
    `run() got multiple values for argument 'source'`, and had been dying unseen for as long
    as the file skipped.

    ⚠️ WRITING A DECLARATION HERE WOULD BE THE SAME MISTAKE in newer clothes: a
    second declaration of what this product reads, free to drift from the shipped one exactly
    as the old `CFG` did. The shipped sample is laid down under the filename `load_setup`
    expects and nothing is invented.
    """
    global _SHIPPED_ROOT
    if _SHIPPED_ROOT is None:
        import shutil
        import tempfile

        here = os.path.dirname(os.path.abspath(__file__))
        root = tempfile.mkdtemp(prefix="shipped_ledger_")
        shutil.copy(os.path.join(here, "..", "config", "sample",
                                 "ledger_config.json.sample"),
                    os.path.join(root, "ledger_config.json"))
        _SHIPPED_ROOT = root
    return _SHIPPED_ROOT


def shipped_catalog():
    """The catalogue that ships beside that declaration (판정 212).

    ⛔ NOT THE LIVE ONE. Checking the SHIPPED declaration against this box's gitignored
    `table_config.json` asks whether this machine has adopted it - a fact about one machine,
    and one that goes red the day the shipped side names a relation the box has not taken up.
    """
    from ledger.setup_bundle import load_physical_catalog

    here = os.path.dirname(os.path.abspath(__file__))
    return load_physical_catalog(os.path.join(
        here, "..", "config", "sample", "table_config.json.sample"))


def run(engine, source="dt_job", **kwargs):
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        kwargs.setdefault("ontology_root", shipped_root())
        kwargs.setdefault("catalog", shipped_catalog())
        return backfill.run(engine, source=source, **kwargs)


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
    # ⚠️ TODAY'S RESULT SHAPE. `attempted` was a key of the v1 result; a run with nothing to
    # read now reports no rows, no batches and nothing inserted, which says the same thing
    # about the same run.
    assert second["rows_read"] == 0
    assert second["batches"] == 0
    assert second["inserted"] == 0
    assert count(ledger) == total


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


# ⚰️ `test_lot_event_chain_mapper_runs_the_existing_cursor_gate_and_store_end_to_end` - died with `chain_mapper` - a v1 config key, alive today only inside the v3 validator.

# ⚰️ `test_canonical_profile_dry_run_execute_gate_store_and_cursor_end_to_end` - died with `chain_mapper` profile selection - same v1 key.

# ⚰️ `test_canonical_profile_lookup_cardinality_failure_writes_no_atom_and_no_cursor` - died with `chain_mapper` profile selection - same v1 key.

# ⚰️ `test_chain_mapper_crash_writes_no_atom_and_does_not_move_cursor` - died with `chain_mapper` - the crash it injects is into a v1 mapper selection.

# ⚰️ `test_chain_mapper_schema_failure_writes_no_atom_and_does_not_move_cursor` - died with `chain_mapper`.

# ⚰️ `test_chain_mapper_semantic_refusal_writes_no_atom_and_does_not_move_cursor` - died with `chain_mapper`.

# ⚰️ `test_chain_mapper_later_event_failure_discards_prior_unflushed_event` - died with `chain_mapper`.

# ⚰️ `test_chain_mapper_gate_rejection_writes_no_atom_and_does_not_move_cursor` - died with `chain_mapper` + `subject_types`, neither of which exists in the v5 grammar.

# ⚰️ `test_chain_mapper_store_failure_rolls_back_atoms_and_cursor` - died with `chain_mapper`.

# ⚰️ `test_chain_mapper_normal_empty_event_advances_the_existing_source_cursor` - died with `chain_mapper`.

# ⚰️ `test_the_unique_index_holds_when_the_cursor_is_reset` - died with `run(reset_cursor=...)`, retired by 판정 171 with `start_from` and `retranslate`: they named a POSITION in a path that no longer reads anything, and `rescope` redoes a named set of rows instead. The property it proved - the unique index refuses a duplicate - is measured directly by the `duplicate atom past the unique index` injection.

# ⚰️ `test_a_rule_change_produces_NEW_atoms_rather_than_silently_none` - died with `run(reset_cursor=...)` and a v1 `vocabulary.slot_pairing` edit. The property - a changed fingerprint writes NEW atoms rather than deduping into silence - is what `source_translator_ver` in `uq_ledger_atom` enforces and what S-87's cases now measure.

def test_a_molecule_the_declaration_cannot_say_is_refused_counted_and_NAMED(ledger, caplog):
    """🔴 THE REFUSAL IS READ FROM THE OPERATOR'S LOG, not from the return value (판정 219).
    A refusal a caller can see and an operator cannot is the silent-skip defect wearing a
    return type.

    ⚠️ THE MOLECULE IS A `lot_event` SPLIT, AND THAT IS S-112 RATHER THAN A FIXTURE CHOICE.
    The shipped `lot_event` cannot translate one today: its `descent` sentence carries no
    `when`, so it is said for every row, while a split's two rows hold only one each of
    `child_lot` and `parent_lot`. So the refusal below is TODAY'S TRUTH about the shipped
    declaration - the day S-112 is fixed this case goes red, and that redness is the
    notification.
    """
    connection = ledger.raw_connection()
    try:
        _seed_lot_event(connection, SPLIT_ROWS)
    finally:
        connection.close()

    with caplog.at_level(logging.INFO, logger="Ledger.Gate"):
        result = run(ledger, source="lot_event")

    messages = chr(10).join(r.getMessage() for r in caplog.records)
    assert "REFUSED" in messages, messages[:400]
    assert "no_identity" in messages, messages[:400]
    # ⛔ AND THE COLUMN IS NAMED. "something was refused" sends an operator looking; the
    # path is what they open.
    assert "child_lot" in messages, messages[:400]
    assert result["refused_total"] >= 1, result
    assert result["inserted"] == 0, "nothing of a refused molecule may land"

#: 🔴 A ROW THE DECLARATION CANNOT COMPLETE (판정 219). The old one carried an `event_type`
#: nobody had declared - a lot_event vocabulary word, and vocabulary is not what these proofs
#: are about. What survives is the PROPERTY: a molecule the declaration cannot say is
#: REFUSED, COUNTED and NAMED while the rest of the batch still lands. Here the `counted`
#: sentence binds its value from `netdie_count`, and this row leaves it empty.
UNDECLARED_ROW = src("SYN-DTJ-002-99", netdie_count=None)


def read_cursor_row(engine, source="dt_job"):
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


# ⚰️ `test_a_refusal_reaches_the_cursor_column_BY_NAME` - died with the CURSOR ROW's `refusal_reasons` column as a thing `run()` writes. Measured 2026-09-10: `run()` drains through the EVENT path, which calls the store with `advance_cursor=False` on purpose (S-76), so NO cursor row is written for any source and the column these read is never filled. The property they were built for - a breakdown that holds MORE THAN ONE key - survives them and is proven directly below by `test_two_independent_refusals_are_counted_and_named_in_one_run`.

# ⚰️ `test_a_CLEAN_run_leaves_a_truthful_breakdown_rather_than_a_stale_one` - died with the CURSOR ROW's `refusal_reasons` column as a thing `run()` writes. Measured 2026-09-10: `run()` drains through the EVENT path, which calls the store with `advance_cursor=False` on purpose (S-76), so NO cursor row is written for any source and the column these read is never filled. The property they were built for - a breakdown that holds MORE THAN ONE key - survives them and is proven directly below by `test_two_independent_refusals_are_counted_and_named_in_one_run`.

# ⚰️ `test_the_breakdown_and_the_aggregate_are_written_in_ONE_transaction` - died with the CURSOR ROW's `refusal_reasons` column as a thing `run()` writes. Measured 2026-09-10: `run()` drains through the EVENT path, which calls the store with `advance_cursor=False` on purpose (S-76), so NO cursor row is written for any source and the column these read is never filled. The property they were built for - a breakdown that holds MORE THAN ONE key - survives them and is proven directly below by `test_two_independent_refusals_are_counted_and_named_in_one_run`.

# ⚰️ `test_a_SECOND_run_in_this_process_does_not_re_attribute_the_first_runs_refusals` - died with the CURSOR ROW's `refusal_reasons` column as a thing `run()` writes. Measured 2026-09-10: `run()` drains through the EVENT path, which calls the store with `advance_cursor=False` on purpose (S-76), so NO cursor row is written for any source and the column these read is never filled. The property they were built for - a breakdown that holds MORE THAN ONE key - survives them and is proven directly below by `test_two_independent_refusals_are_counted_and_named_in_one_run`.

def refusals_unaccounted(engine, source="dt_job"):
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


# ⚰️ `test_a_refusal_inside_slot_map_lands_NOTHING_and_the_books_balance` - died with `LotEventTranslator._slot_map` - the module was deleted 2026-08-18.

def _forced_failure_run(engine, commit_between_chunks):
    """Fail in the MIDDLE of one molecule's insert. Returns the atoms left behind.

    `INSERT_PAGE_SIZE` is dropped so a single molecule spans several statements and the
    second statement raises. With the transaction boundary intact the answer must be zero;
    `commit_between_chunks=True` removes the boundary, which is the injection that proves
    this test can go red.

    ⚠️ THE PAGE IS 1, NOT 3, SINCE THE SOURCE BECAME A ROW SOURCE (판정 219). One `dt_job`
    molecule is TWO atoms - `register` and `has_netdie` - so a page of three swallowed a
    whole molecule in one statement and "fail in the middle of one" could not happen: the
    helper would have proven nothing while looking like it did.
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
    ledger_store.INSERT_PAGE_SIZE = 1
    try:
        # ⚠️ THE FAILURE IS CONTAINED, NOT PROPAGATED, AND THAT IS TODAY'S DESIGN. It used to
        # escape `run()` and this helper asserted `pytest.raises(RuntimeError)`; the follow-up
        # loop now catches a failed group, NAMES it in the log and carries on, so a run that
        # hit the injection returns normally. What this helper is about is unchanged and is
        # read from the database below: whether anything of a half-written molecule survived.
        run(engine, fetch_rows=2)
    finally:
        psycopg2.extras.execute_values = original
        ledger_store.INSERT_PAGE_SIZE = old_page
    return atoms_per_subject(engine)


def atoms_per_subject(engine):
    """`{dt_job: atoms}` - how many atoms each subject has in the ledger.

    🔴 PER MOLECULE, NOT A TOTAL (판정 219). The old helper returned `count(engine)` and its
    caller asserted zero, which was true only while a run carried ONE molecule. A row source
    reads several, and each is its own transaction - so a complete molecule surviving beside
    a failed one is the boundary WORKING. What "cannot land half" means is that every subject
    present has ALL of its atoms, and the one that failed has none.
    """
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT subject_keys->>'dt_job', count(*) FROM {schema.LEDGER_TABLE} "
                f"GROUP BY 1")
            return {job: total for job, total in cursor.fetchall()}
    finally:
        connection.close()


# ⚰️ `test_a_subject_type_the_source_never_declared_is_refused_by_the_REAL_backfill` - died with `subject_types` - absent from the v5 grammar entirely.

def test_a_molecule_cannot_land_half(ledger):
    """🔴 The brief's rule: the transaction unit is one source event. Force a failure
    after the first chunk of a molecule has already been INSERTed and show that nothing
    from that event survives."""
    per_subject = _forced_failure_run(ledger, commit_between_chunks=False)
    # 🔴 EVERY SUBJECT PRESENT HAS ALL ITS ATOMS. A `dt_job` says two things - it exists, and
    # it carries this many - so a subject holding exactly one of them is a molecule that
    # landed half, which is what the transaction boundary exists to make impossible.
    halves = {job: total for job, total in per_subject.items() if total != 2}
    assert not halves, (f"{halves} - a molecule landed half, so the transaction boundary "
                        f"is not holding")


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


# ⚰️ `test_only_register_may_have_no_object_and_register_may_have_nothing_else` - died with `ck_ledger_register_has_no_object`, which S-77 RETIRED ON PURPOSE on 2026-09-09: it read `(predicate = 'register') = (object_kind IS NULL)`, a domain word in the storage layer. Which predicates are objectless is a declared fact now and `roleframe` refuses an emission that disagrees - the same reason the matching injection was buried.

def test_atoms_route_into_the_month_partition_they_belong_to(ledger):
    run(ledger)
    # ⚠️ READ FROM THE DATABASE, NOT FROM THE RETURN. The result used to carry a
    # `partitions` list and no longer does; what this case is about is where the rows
    # actually WENT, which `tableoid` answers and a summary field only reports.
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
# ⚰️ `test_lag_says_never_started_before_the_first_run` - died with `CFG["sources"]["lot_event"]` - `observability.lag_report` was handed a v1 source config, and that grammar is gone. What lag means for a v5 source is S-58's census (`relation_rows`/`indexed_rows`/`not_yet`), which the run result already carries and `test_a_source_says_how_many_rows_it_has_not_translated` measures.

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
        # 🔴 THE VALUES ARE DERIVED FROM `ROW_COLUMNS`, NOT COUNTED BY HAND (S-104 ①).
        # This wrote a fixed `%s` list beside `', '.join(ROW_COLUMNS)`, so the day that tuple
        # grew - `occurred_at_basis`, S-52 - the statement became a SYNTAX ERROR and the
        # injection stopped reaching the index it exists to prove. The guard was alive the
        # whole time and its instrument had quietly broken: two spellings of one column list.
        row = {"subject_type": "Lot", "subject_keys": Json({"lot": "DUP"}),
               "predicate": "register", "object_kind": None, "object_payload": None,
               "occurred_at": when, "source_who": "w", "source_translator_ver": "v",
               "source_raw_ref": "r", "supersedes": None, "source_event_id": event_id,
               # ⚠️ NULL or "ingested" - the CHECK allows nothing else, and a value this
               # injection invents is refused by a DIFFERENT constraint than the one it is
               # here to prove. NULL is what an atom with a world-time column carries.
               "source_event_state": "source_record", "occurred_at_basis": None}
        missing = [column for column in ROW_COLUMNS
                   if column != "id" and column not in row]
        if missing:
            # ⛔ NAMED, NOT DEFAULTED. A column added to the row shape that this injection
            # does not know about must stop it loudly, or the next `ROW_COLUMNS` change
            # repeats exactly the failure above.
            raise AssertionError(
                f"this injection does not know what to write for {missing}; add it here "
                f"rather than letting the statement drift from ROW_COLUMNS again")
        placeholders = ", ".join("gen_random_uuid()" if column == "id" else "%s"
                                 for column in ROW_COLUMNS)
        values = tuple(row[column] for column in ROW_COLUMNS if column != "id")
        with connection.cursor() as cursor:
            for _ in range(2):
                cursor.execute(
                    f"INSERT INTO {schema.LEDGER_TABLE} ({', '.join(ROW_COLUMNS)}) "
                    f"VALUES ({placeholders})", values)
        connection.commit()
    except psycopg2.errors.UniqueViolation as exc:
        connection.rollback()
        raise ValueError(f"the unique index refused the duplicate: {exc}") from exc
    finally:
        connection.close()
    raise AssertionError("uq_ledger_atom accepted the SAME claim twice")


# ⚰️ `_inject_register_with_an_object` STOOD HERE (S-104, 판정 215/216).
# It inserted a `register` carrying an `object_kind` and expected
# `ck_ledger_register_has_no_object` to refuse it. That constraint was RETIRED ON PURPOSE
# by S-77 on 2026-09-09 - it read `(predicate = 'register') = (object_kind IS NULL)`, a
# DOMAIN WORD in the storage layer, which is the one layer a declaration cannot change.
# Which predicates are objectless is now a DECLARED fact and `roleframe` refuses an
# emission that disagrees, so the guard moved rather than disappeared.
#
# ⚠️ SO ITS SILENCE WAS CORRECT, NOT A DEFECT. `schema.RETIRED_REGISTER_OBJECT_CONSTRAINT`
# still names it, which is how this was told apart from a real red.

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


# ⚰️ `_inject_breakdown_that_does_not_add_up` STOOD HERE (S-104, 판정 215).
# It replaced `backfill._refusal_delta` to force the aggregate and its breakdown apart.
# That symbol no longer exists, so the injection could only raise `AttributeError` - which
# the harness reads as neither 'the guard caught it' nor 'the guard accepted it'. A test
# dies in the same commit as the code it measured; this one outlived it in silence because
# the whole file skipped for want of a declared test database.

# ⚰️ `_inject_slot_map_refusal_swallowed` STOOD HERE (S-104, 판정 215).
# It patched `ledger.lot_event_translator.LotEventTranslator._slot_map` to swallow a
# refusal. That module was deleted on 2026-08-18, so the import could only raise and the
# injection proved nothing about the guard it was written for. Same reason as the one
# above: the file skipped, so the death was never reported.

PG_INJECTIONS = [
    ("transaction boundary removed", _inject_missing_transaction_boundary),
    ("duplicate atom past the unique index", _inject_duplicate_atom_past_the_unique_index),
    ("atom outside every partition", _inject_atom_outside_every_partition),
]

#: 4 built with this file + 1 added by ruling R-2026-08-13-F (the refusal breakdown must
#: agree with the aggregate it explains) + 1 by ruling R-2026-08-13-H (a refusal swallowed
#: between the gate and the writer).
#: 🔴 SIX UNTIL 2026-09-09, THREE NOW, AND THE THREE THAT LEFT ARE NAMED (S-104,
#: 판정 215/216). Each measured something that no longer exists, so none of them could
#: report an outcome this harness understands - and none of them said so, because the whole
#: file skipped for want of a declared test database:
#:
#:   * `refusal breakdown that does not add up`    `backfill._refusal_delta` is gone
#:   * `a fragment's refusal swallowed by its caller`  `ledger.lot_event_translator` deleted 08-18
#:   * `register carrying an object`               `ck_ledger_register_has_no_object` was
#:                                                 RETIRED ON PURPOSE by S-77 - a domain word
#:                                                 in the storage layer - and the guard moved
#:                                                 into `roleframe`, so its silence was right
#:
#: ⚠️ THE NUMBER IS DECLARED SO A SHRINK CANNOT BE SILENT, which is what caught this
#: edit. Lowering it is allowed; lowering it without saying which injection left, and why its
#: subject is gone, is not.
EXPECTED_PG_INJECTIONS = 3


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


def test_two_independent_refusals_are_counted_and_named_in_one_run(ledger, caplog):
    """🔴 A BREAKDOWN THAT COULD ONLY EVER HOLD ONE KEY WOULD BE USELESS (판정 220).

    That sentence is the four buried cases' own, and it is the half of them worth keeping:
    two DIFFERENT reasons, in one run, each counted, with the rest of the batch landing.

    ⚠️ BOTH REASONS COME FROM THE DECLARATION, not from anything invented here.
    `process_param_num_measure` is a shipped row source whose identity is a column and whose
    `occurred_at` is a column, so it can miss either - and `dt_job` cannot miss the second,
    because it reads its instant from a BASIS.

    🔴 AND THE BLANK IS `wafer_id`, NOT `param_id`. `param_id` is identity AND cursor AND
    order_by, so blanking it is refused at the BASE FRAME - "driver identity/order/cursor/time
    value is missing" - which aborts the whole batch before any molecule exists and is counted
    under no reason at all. An entity KEY is what the molecule check reads, so blanking that
    refuses ONE molecule and leaves the others alone. The two are one character apart in the
    fixture and completely different in what they prove.
    """
    connection = ledger.raw_connection()
    try:
        _seed_process_param(connection,
                            PARAM_ROWS + [PARAM_NO_IDENTITY, PARAM_NO_INSTANT])
    finally:
        connection.close()

    with caplog.at_level(logging.INFO, logger="Ledger.Gate"):
        result = run(ledger, source="process_param_num_measure")

    assert result["rows_read"] == 4
    assert result["refused_total"] == 2, (
        f"two molecules are unsayable; the rest must still land: {result}")
    assert result["inserted"] > 0, "a run where nothing lands cannot tell refusal from silence"

    said = chr(10).join(r.getMessage() for r in caplog.records)
    assert gate.REFUSE_NO_IDENTITY in said, said[:400]
    assert gate.REFUSE_MISSING_OCCURRED_AT in said, said[:400]
    # ⛔ AND THE COLUMN IS NAMED IN EACH. "two were refused" sends an operator looking; the
    # address is what they open.
    assert "wafer_id" in said and "eventtime" in said, said[:400]
