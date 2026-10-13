"""Lead 568388892 ①: the paced census's row estimate (`backfill.rows_not_yet_translated(exact_rows=False)`) reads THIS
search path's table - `column_stats.estimated_rows`, by the relation's oid - and counts it when it was never analysed.
It used to find `pg_class` by name, and a never-analysed table here (reltuples -1, filtered out) read another schema's
same-named table: a world in a scratch schema said 478,716 rows of public's table (test_ledger_worlds…catches_up)."""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.pg

TABLE = "x568_rows"


@pytest.fixture
def two_schemas(pg_engine):
    """An engine whose search path is a schema of this test's own: TABLE with 3 rows, never analysed, and a cursor
    saying 3 indexed; another schema of this test's own holds TABLE with 50 rows, analysed."""
    from tests.conftest import PG_TEST_SCHEMA
    from tests.support.isolated_pg import scratch_connect_args
    from ledger import schema

    here, other = PG_TEST_SCHEMA + "_x568a", PG_TEST_SCHEMA + "_x568b"
    cursor = schema.world_names(None).cursor
    with pg_engine.begin() as conn:
        for name in (here, other):
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
            conn.execute(text(f'CREATE SCHEMA "{name}"'))
        conn.execute(text(f'CREATE TABLE "{other}"."{TABLE}" (row_id text)'))
        conn.execute(text(f'INSERT INTO "{other}"."{TABLE}" SELECT g::text FROM generate_series(1, 50) g'))
        conn.execute(text(f'ANALYZE "{other}"."{TABLE}"'))
        conn.execute(text(f'CREATE TABLE "{here}"."{TABLE}" (row_id text)'))
        conn.execute(text(f'INSERT INTO "{here}"."{TABLE}" VALUES (\'a\'), (\'b\'), (\'c\')'))
        conn.execute(text(f'CREATE TABLE "{here}"."{cursor}" (source text, rows_indexed bigint)'))
        conn.execute(text(f'INSERT INTO "{here}"."{cursor}" VALUES (\'s\', 3)'))
    engine = create_engine(pg_engine.url, poolclass=NullPool, connect_args=scratch_connect_args(here))
    try:
        yield engine
    finally:
        engine.dispose()
        with pg_engine.begin() as conn:
            for name in (here, other):
                conn.execute(text(f'DROP SCHEMA "{name}" CASCADE'))


def test_the_paced_estimate_reads_this_schemas_table(two_schemas, monkeypatch):
    from ledger import backfill

    # a remainder asks what the read takes out - this plan reads nothing, so it takes nothing out
    monkeypatch.setattr(backfill, "_missing_rows_taken_out", lambda *a, **k: (0, 0, None))

    plan = SimpleNamespace(relation=TABLE, planned=True, driver=SimpleNamespace(unit="row"))
    setup = SimpleNamespace(snapshot=SimpleNamespace(source_plans={"s": plan}))
    report = backfill.rows_not_yet_translated(two_schemas, setup, "s", exact_rows=False)
    assert (report["relation_rows"], report["relation_rows_estimated"], report["indexed_rows"], report["not_yet"]) \
        == (3, False, 3, 0), report
