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
        "subject_type": "Lot",
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
        with engine.begin() as conn:
            conn.execute(text(SOURCE_DDL))
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
            f"source_translator_ver, source_raw_ref) VALUES "
            f"(gen_random_uuid(), 'Lot', %s::jsonb, %s, %s, %s::jsonb, "
            f"'2026-05-03T00:00:00+00', 'w', 'v', 'r')")

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
        values = ("Lot", Json({"lot": "DUP"}), "register", None, None, when,
                  "w", "v", "r", None)
        with connection.cursor() as cursor:
            for _ in range(2):
                cursor.execute(
                    f"INSERT INTO {schema.LEDGER_TABLE} ({', '.join(ROW_COLUMNS)}) "
                    f"VALUES (gen_random_uuid(), %s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", values)
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
                f"source_translator_ver, source_raw_ref) VALUES "
                f"(gen_random_uuid(), 'Lot', '{{\"lot\":\"X\"}}'::jsonb, 'register', "
                f"'value', '2026-05-03T00:00:00+00', 'w', 'v', 'r')")
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
                f"source_raw_ref) VALUES (gen_random_uuid(), 'Lot', "
                f"'{{\"lot\":\"X\"}}'::jsonb, 'register', '1999-01-01T00:00:00+00', "
                f"'w', 'v', 'r')")
        connection.commit()
    except psycopg2.Error as exc:
        connection.rollback()
        raise ValueError(f"no partition accepted it: {exc}") from exc
    finally:
        connection.close()
    raise AssertionError("a row landed with no partition to hold it")


PG_INJECTIONS = [
    ("transaction boundary removed", _inject_missing_transaction_boundary),
    ("duplicate atom past the unique index", _inject_duplicate_atom_past_the_unique_index),
    ("register carrying an object", _inject_register_with_an_object),
    ("atom outside every partition", _inject_atom_outside_every_partition),
]

EXPECTED_PG_INJECTIONS = 4


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
