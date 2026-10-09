"""총괄 d28171060 (소유자 10-09 「인덱스 스캔이 안 느네 소스오리진」 · 운영 pg_stats n_distinct = 289): the origin
lookup (`cell_layer.cells_stamped_by`) takes `idx_sources_by_origin` even when the statistics believe each
origin feeds hundreds of cells - the belief under which one `IN (1,000)` read the whole `cell_sources`.

Asserted on the statement the product SENDS, captured as it goes out, not on a copy of it.
"""
import hashlib
import os
import sys

import pytest
from sqlalchemy import MetaData, create_engine, event, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import cell_layer                                          # noqa: E402
from database import models                                           # noqa: E402

ROWS = 200_000
#: One origin feeds this many cells - a copy writes a row's columns.
FED = 7
#: What production's statistics believed (소유자 10-09: 289) - pinned, so the belief is the test's.
BELIEVED_DISTINCT = 300
BATCH = 1000


def _origin(n):
    return hashlib.md5(("origin%d" % n).encode()).hexdigest()


@pytest.fixture(name="origins", scope="module")
def fixture_origins(pg_engine):
    """A `cell_sources` of its own schema - the model's table and indexes - with the low belief pinned."""
    from tests.support.isolated_pg import scratch_connect_args, scratch_schema

    schema = scratch_schema("assy_pytest_origin")
    engine = create_engine(pg_engine.url, poolclass=NullPool, connect_args=scratch_connect_args(schema))
    with engine.begin() as conn:
        conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema))
        conn.execute(text('CREATE SCHEMA "%s"' % schema))
    scratch = MetaData(schema=schema)
    models.CellSource.__table__.to_metadata(scratch, schema=None)
    scratch.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO cell_sources (table_name, row_id, column_name, source_name, value, origin_row_id)"
            " SELECT 't', md5('row' || g), 'c' || (g % 10), 'chain_ingestion', '\"v\"'::json,"
            "        md5('origin' || (g / :fed)) FROM generate_series(0, :n - 1) g"), {"n": ROWS, "fed": FED})
        conn.execute(text("ALTER TABLE cell_sources ALTER COLUMN origin_row_id SET (n_distinct = %d)"
                          % BELIEVED_DISTINCT))
        conn.execute(text("ANALYZE cell_sources"))
    try:
        yield engine
    finally:
        with engine.begin() as conn:
            conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema))
        engine.dispose()


def _plan(engine, statement, parameters):
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute("EXPLAIN " + statement, parameters)
        return "\n".join(row[0] for row in cursor.fetchall())
    finally:
        raw.close()


def _batch():
    return [_origin(n) for n in range(0, ROWS // FED, (ROWS // FED) // BATCH)][:BATCH]


@pytest.mark.pg
def test_the_lookup_takes_the_origin_index_under_a_low_belief(origins):
    sent = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "cell_sources" in statement:
            sent.append((statement, parameters))

    event.listen(origins, "before_cursor_execute", capture)
    session = sessionmaker(bind=origins)()
    try:
        found = cell_layer.cells_stamped_by(session, _batch())
    finally:
        session.close()
        event.remove(origins, "before_cursor_execute", capture)

    assert len(found) == BATCH * FED, "every cell of every origin asked - the lookup still answers"
    [(statement, parameters)] = sent
    plan = _plan(origins, statement, parameters)
    assert "idx_sources_by_origin" in plan and "Seq Scan on cell_sources" not in plan, plan


@pytest.mark.pg
def test_one_in_list_reads_the_whole_table_under_the_same_belief(origins):
    """The control: under this belief the old shape - one `IN (1,000)` - is a Seq Scan, so the cell above
    measures the shape rather than a table too small to scan."""
    session = sessionmaker(bind=origins)()
    try:
        query = (session.query(models.CellSource.table_name, models.CellSource.row_id,
                               models.CellSource.column_name, models.CellSource.source_name,
                               models.CellSource.origin_row_id)
                 .filter(models.CellSource.origin_row_id.in_(_batch())))
        statement = str(query.statement.compile(dialect=postgresql.dialect(),
                                                compile_kwargs={"literal_binds": True}))
    finally:
        session.close()
    assert "Seq Scan on cell_sources" in _plan(origins, statement, None)
