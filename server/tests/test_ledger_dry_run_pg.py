# -*- coding: utf-8 -*-
"""The dry run's zero-write guarantee — the proof only PostgreSQL can give.

A dry run that merely「doesn't call the writer」is a promise about today's code, and the
save path it guards is exactly where this project's proportionality rule (R-2026-08-14-J)
says mutation-grade rigour belongs. So the guarantee is a DATABASE fact here:

  * the preview's transaction is opened `READ ONLY`, read back from the server rather
    than assumed, and
  * an INSERT on that transaction is refused by PostgreSQL with SQLSTATE 25006.

⚠️ A THIRD ASSERTION USED TO LIVE HERE AND IT WAS THE STRONGEST ONE. It ran a full
preview over a real source and asserted the ledger's row count and the translator cursor
were untouched WHILE the preview produced atoms — the only one that did not care how the
guarantee was implemented. It drove `dry_run.preview` through the v1 translators, which
were retired on 2026-08-18, so it went with them rather than being weakened into a green
sentence. `begin_read_only` is what remains of the mechanism and it is asserted below
against PostgreSQL itself; the end-to-end arm has to come back when the v2 preview is
wired to this route, and it is the reason `begin_read_only` must not be inlined away.

ISOLATION is the same as `test_ledger_l1_pg.py`'s and for the same reasons - a scratch
schema, `public` off the search path, and a SKIP rather than a quiet downgrade to SQLite.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import dry_run, schema                                   # noqa: E402
from test_ledger_l1_pg import (BASE_ROWS, CFG, SOURCE_DDL, _declared_as_test_database,
                               _resolve_url, _seed)                  # noqa: E402

SCRATCH_SCHEMA = "assy_ledger_dryrun_pytest" + (
    "_" + os.environ["PYTEST_XDIST_WORKER"]
    if os.environ.get("PYTEST_XDIST_WORKER") else "")


@pytest.fixture(scope="module")
def pg():
    url, reason = _resolve_url()
    if url is None:
        pytest.skip(reason)
    try:
        import psycopg2  # noqa: F401
    except Exception as exc:                                         # pragma: no cover
        pytest.skip(f"psycopg2 is not importable: {exc}")

    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool

    with _declared_as_test_database(url):
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
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
            conn.execute(text(f'CREATE SCHEMA "{SCRATCH_SCHEMA}"'))
            # `ensure_schema` builds a partial TRIGRAM index over registrations, so
            # `pg_trgm` is a prerequisite of the ledger schema (`setup/init_db.py` calls
            # it a bootstrap step). `public` is off this suite's search path by design, so
            # an extension installed there is unreachable - it goes INTO the scratch
            # schema instead and dies with it on the DROP ... CASCADE below.
            try:
                conn.execute(text(
                    f'CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA "{SCRATCH_SCHEMA}"'))
            except Exception as exc:
                pytest.skip(f"pg_trgm is not installable on this box, so the ledger "
                            f"schema cannot be built here: {exc}")
        with engine.begin() as conn:
            conn.execute(text(SOURCE_DDL))
        connection = engine.raw_connection()
        try:
            _seed(connection, BASE_ROWS)
            # The ledger tables are built HERE, by the test, precisely so that the
            # preview never has to - `ensure_schema` issues DDL and would be refused.
            schema.ensure_schema(connection)
            connection.commit()
        finally:
            connection.close()
        try:
            yield engine
        finally:
            engine.dispose()
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
                left = conn.execute(text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = :s"), {"s": SCRATCH_SCHEMA}).scalar()
                assert left == 0, f"{left} object(s) left behind in {SCRATCH_SCHEMA}"
            admin.dispose()


def test_the_previews_transaction_is_read_only_ACCORDING_TO_POSTGRES(pg):
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        connection = pg.raw_connection()
        try:
            assert dry_run.begin_read_only(connection) is True
            with pytest.raises(Exception) as caught:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"INSERT INTO {schema.CURSOR_TABLE} (source) VALUES "
                        f"('smuggled')")
            # 25006 = read_only_sql_transaction. Asserted by CODE rather than by message
            # text, because a message is localised and a SQLSTATE is a contract.
            assert getattr(caught.value, "pgcode", None) == "25006", (
                f"expected PostgreSQL to refuse the write with 25006, got "
                f"{caught.value!r}")
        finally:
            connection.rollback()
            connection.close()


def test_even_DDL_is_refused_on_the_previews_transaction(pg):
    """`ensure_schema` is the writer a preview is most likely to reach by accident -
    it is called by every driver's first line and it issues CREATE TABLE."""
    url, _ = _resolve_url()
    with _declared_as_test_database(url):
        connection = pg.raw_connection()
        try:
            assert dry_run.begin_read_only(connection) is True
            with pytest.raises(Exception) as caught:
                schema.ensure_schema(connection)
            assert getattr(caught.value, "pgcode", None) == "25006"
        finally:
            connection.rollback()
            connection.close()

