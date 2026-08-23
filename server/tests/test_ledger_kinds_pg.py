# -*- coding: utf-8 -*-
"""`GET /api/ledger/kinds` — the catalogue, asserted on the answers that are EASY TO LOSE.

WHY PostgreSQL OR SKIP
-----------------------
The whole endpoint is catalogue work — `to_regclass`, `pg_relation_size`,
`pg_class.reltuples`, `= ANY(%s)`. SQLite has none of it, so a suite that ran here on
in-memory SQLite would prove nothing about what the route does ("SQLite accepts what
PostgreSQL refuses", paid for three times in this project). Scratch schema, or skip.

WHAT IS PINNED HERE, AND WHY EACH ONE IS A DEFECT WAITING TO HAPPEN
--------------------------------------------------------------------
1. **A kind with zero observations is LISTED, with `atoms: 0`.** The tempting
   implementation filters it out for tidiness, and the operator then cannot tell
   「이 시스템은 박리를 모른다」from「박리 데이터가 아직 없다」.
2. **An ABSENT relation gives `atoms: null`, never `0`.** Absent is not a measured
   zero. This is the distinction the client renders as "no number" vs「0」.
3. **`has_denominator` is SERVED.** A method-less kind must carry `false` on the wire,
   not leave the client to infer it from a list length.
4. **`classes` come from the registry**, per kind, and are not shared between kinds.
5. **No kind name is hardcoded.** The registry is swapped for a fixture whose kinds are
   named nothing like `void`, and the catalogue follows it.
"""
import contextlib
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger_api import finding_kinds                                  # noqa: E402
from ledger_api import ledger_kinds                                   # noqa: E402

PG_TEST_URL_ENV = "ASSY_PG_TEST_DATABASE_URL"
SCRATCH_SCHEMA = "assy_kinds_pytest" + (
    "_" + os.environ["PYTEST_XDIST_WORKER"]
    if os.environ.get("PYTEST_XDIST_WORKER") else "")

DDL = """
CREATE TABLE inspection_run (
    run_uid TEXT PRIMARY KEY, method TEXT,
    base_wafer_id TEXT, base_x INT, base_y INT, stack_gate INT,
    recipe_id TEXT, eqp_id TEXT, observed_at TIMESTAMPTZ
);
CREATE TABLE bubble_obs (
    bubble_uid TEXT PRIMARY KEY, run_uid TEXT,
    base_wafer_id TEXT, base_x INT, base_y INT, span_x DOUBLE PRECISION, unit TEXT
);
CREATE TABLE crack_obs (
    crack_uid TEXT PRIMARY KEY, run_uid TEXT,
    base_wafer_id TEXT, base_x INT, base_y INT, span_x DOUBLE PRECISION, unit TEXT
);
"""

#: 🔴 NOT `void`. The registry under test is deliberately named nothing like the default
#: kind, so a `finding_kind='void'` literal anywhere in the catalogue path fails here.
#: `smudge` has an observation relation that is NEVER CREATED (atoms must be null) and
#: `crack` has NO METHOD (has_denominator must be false, runs must be null).
REGISTRY = {
    "bubble": {"label": "기포", "observed_by": ["ultrasound"],
               "observation_table": "bubble_obs", "extent_columns": ["span_x"],
               "classes": ["interfacial", "bulk"]},
    "crack":  {"label": "크랙", "observed_by": [],
               "observation_table": "crack_obs", "extent_columns": ["span_x"]},
    "smudge": {"label": "얼룩", "observed_by": ["ultrasound"],
               "observation_table": "smudge_obs", "extent_columns": ["span_x"]},
}


def _resolve_url():
    import db_safety
    from database.database import DEFAULT_PG_URL

    url = os.environ.get(PG_TEST_URL_ENV) or None
    if not url:
        candidate = os.environ.get(db_safety.TEST_DATABASE_URL_ENV) or ""
        url = candidate if candidate.startswith("postgres") else None
    if not url:
        return None, (f"no PostgreSQL test database declared. Set {PG_TEST_URL_ENV} to "
                      f"an ISOLATED database, e.g. postgresql://…@localhost:5432/assy_qa")
    violations = db_safety.check_test_database(url, production_url=DEFAULT_PG_URL,
                                               opt_in=url)
    if violations:
        return None, f"{PG_TEST_URL_ENV} is not usable: {violations[0]}"
    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        return None, f"{PG_TEST_URL_ENV} is not a PostgreSQL URL"
    if (parsed.database or "") == "assy_manager":
        # 🔴 This file runs DDL. The dev database is not its playground.
        return None, "refusing to run schema DDL against 'assy_manager'"
    return url, None


@contextlib.contextmanager
def _declared_as_test_database(url):
    """`db_safety` refuses any PostgreSQL connection a test has not declared. Same
    spelling as `test_ledger_siblings_pg.py` — the guard is the point, not an obstacle."""
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


@pytest.fixture(scope="module")
def pg():
    url, reason = _resolve_url()
    if url is None:
        pytest.skip(reason)
    try:
        import psycopg2                                              # noqa: F401
    except Exception as exc:                                         # pragma: no cover
        pytest.skip(f"psycopg2 is not importable: {exc}")
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool

    with _declared_as_test_database(url):
        admin = create_engine(url, poolclass=NullPool)
        try:
            with admin.begin() as conn:
                conn.execute(text("SELECT 1"))
        except OperationalError as exc:
            admin.dispose()
            pytest.skip(f"PostgreSQL is not reachable: "
                        f"{str(exc).strip().splitlines()[0]}")
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
            conn.execute(text(f'CREATE SCHEMA "{SCRATCH_SCHEMA}"'))
        engine = create_engine(
            url, poolclass=NullPool,
            connect_args={"options": f"-csearch_path={SCRATCH_SCHEMA}"})
        raw = engine.raw_connection()
        with raw.cursor() as cur:
            cur.execute(DDL)
            # Two runs of the one declared method, and ONE bubble. `crack_obs` stays
            # empty on purpose: its zero has to survive to the wire.
            cur.execute("INSERT INTO inspection_run (run_uid, method) VALUES "
                        "('R1','ultrasound'), ('R2','ultrasound'), ('R3','other')")
            cur.execute("INSERT INTO bubble_obs (bubble_uid, run_uid) VALUES ('B1','R1')")
        raw.commit()
        try:
            yield raw
        finally:
            raw.close()
            engine.dispose()
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
                # ASK THE CATALOGUE - "I issued a DROP" is not the same fact as
                # "it is gone".
                left = conn.execute(text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = :s"), {"s": SCRATCH_SCHEMA}).scalar()
                assert left == 0, f"{left} object(s) left behind in {SCRATCH_SCHEMA}"
            admin.dispose()


@pytest.fixture(autouse=True)
def declarations():
    finding_kinds.set_registry(REGISTRY)
    yield
    finding_kinds.set_registry(None)


def _row(body, kind):
    for row in body["kinds"]:
        if row["kind"] == kind:
            return row
    return None


def test_the_catalogue_follows_the_registry_and_names_no_kind_of_its_own(pg):
    """🔴 The generalisation, asserted: a registry with no `void` in it comes back whole.

    If any part of the catalogue path carried a kind literal, this registry - whose
    three kinds are named nothing like the default - would come back short.
    """
    body = ledger_kinds.catalog(pg)
    assert [r["kind"] for r in body["kinds"]] == ["bubble", "crack", "smudge"]
    assert body["default"] == "bubble", (
        "`void` is not declared by this registry, so the default must be the first "
        "DECLARED kind - serving an undeclared default sends the console to a 422")
    assert _row(body, "bubble")["label"] == "기포"


def test_a_kind_with_no_observations_is_listed_with_a_measured_zero(pg):
    """🔴 0 IS AN ANSWER. Hiding the row would make declared-and-empty unreadable."""
    body = ledger_kinds.catalog(pg)
    crack = _row(body, "crack")
    assert crack is not None, "a kind with no observations was dropped from the picker"
    assert crack["atoms"] == 0 and crack["atoms_exact"] is True
    assert _row(body, "bubble")["atoms"] == 1


def test_an_absent_relation_is_null_and_never_a_zero(pg):
    """🔴 `smudge_obs` does not exist. Unmeasured is not measured-as-nothing."""
    smudge = _row(ledger_kinds.catalog(pg), "smudge")
    assert smudge["atoms"] is None, (
        "an absent observation relation was reported as 0 observations - the operator "
        "reads that as 'this kind has never been seen' rather than 'not deployed'")
    assert smudge["atoms_exact"] is False


def test_the_server_answers_whether_a_denominator_exists(pg):
    """🔴 SERVED, not left to `observed_by.length` on the client."""
    body = ledger_kinds.catalog(pg)
    assert _row(body, "bubble")["has_denominator"] is True
    crack = _row(body, "crack")
    assert crack["has_denominator"] is False
    assert crack["runs"] is None, (
        "a kind with no declared method has no run population; 0 there reads as "
        "'the scan exists and nobody ran it'")


def test_runs_count_only_the_methods_that_look_for_this_kind(pg):
    """The denominator's size is the DECLARED methods' runs - `R3` is somebody else's."""
    assert _row(ledger_kinds.catalog(pg), "bubble")["runs"] == 2


def test_each_kind_carries_its_own_closed_class_set(pg):
    body = ledger_kinds.catalog(pg)
    assert _row(body, "bubble")["classes"] == ["interfacial", "bulk"]
    assert _row(body, "crack")["classes"] == [], (
        "a kind that declares no classes must not borrow the neighbouring kind's set")


def test_state_says_which_world_the_console_is_in(pg):
    """`ready` here; the empty and absent worlds are asserted against a registry whose
    relations are empty / missing entirely, without touching the schema."""
    assert ledger_kinds.catalog(pg)["state"] == "ready"

    finding_kinds.set_registry({"crack": REGISTRY["crack"]})       # relation exists, 0 rows
    assert ledger_kinds.catalog(pg)["state"] == "empty"

    finding_kinds.set_registry({"smudge": REGISTRY["smudge"]})     # no relation at all
    absent = ledger_kinds.catalog(pg)
    assert absent["state"] == "absent"
    assert absent["kinds"], "an undeployed box still declares its kinds"
