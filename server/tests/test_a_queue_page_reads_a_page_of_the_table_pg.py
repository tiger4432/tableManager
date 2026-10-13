"""총괄 ff4eb2cf0 6: the queue's pages are row_id ranges of the derived table - one statement reads at most a page of
the table wherever the waiting rows sit. With the predicate in the WHERE alone the gap before a sparse queue was one
statement (8.68 s at 4M rows, the first 50 waiting). Here 3,000 derived rows, the last five waiting: every statement
derived_pages sends reads at most a page of the table (its scans' rows, EXPLAIN ANALYZE of the statement as sent),
and the pages hold the five."""
import json
import os
import sys

import pytest
from sqlalchemy import MetaData, create_engine, event, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import PG_TEST_SCHEMA, retire_dynamic_model                 # noqa: E402
from chain.enrichment import analysis                                     # noqa: E402
from database import crud, models                                         # noqa: E402
from support.isolated_pg import scratch_connect_args                      # noqa: E402
from tests.support.enrich_decl import write_rules                         # noqa: E402

import test_backfill_enrichment as be                                     # noqa: E402

pytestmark = pytest.mark.pg
S = PG_TEST_SCHEMA
ROWS, WAITING, PAGE = 3000, 5, 100


class _Page:
    """A page of PAGE rows, every time."""

    def next(self):
        return PAGE

    def rest(self, *_args):
        pass


@pytest.fixture(name="db")
def fixture_db(pg_engine, monkeypatch, tmp_path):
    engine = create_engine(pg_engine.url, pool_size=2, connect_args=scratch_connect_args(S))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT current_schema()")).scalar() == S
    for name in be.BKFL_TABLES:
        retire_dynamic_model(name)
    models.init_dynamic_models(be.BKFL_TABLES)
    saved = dict(crud.TABLE_CONFIG)
    crud.TABLE_CONFIG.update(be.BKFL_TABLES)
    scratch = MetaData(schema=S)
    for name in be.BKFL_TABLES:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(engine)
    write_rules(tmp_path, monkeypatch, {"bkfl_rule": be.RULES_FILE["bkfl_rule"]})
    with engine.begin() as conn:
        # row_ids in key order; every row's target filled but the last WAITING
        conn.execute(text(
            'INSERT INTO "%s".bkfl_test_derived (row_id, business_key_val, job_id, equipment, event_time, wafer_id) '
            "SELECT lpad(g::text, 6, '0'), 'E_' || g, 'E_' || g, 'E', g::text, CASE WHEN g > :filled THEN NULL ELSE 'W' END "
            "FROM generate_series(1, :rows) g" % S), {"rows": ROWS, "filled": ROWS - WAITING})
        conn.execute(text('ANALYZE "%s".bkfl_test_derived' % S))
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()
        with engine.begin() as conn:
            for name in be.BKFL_TABLES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (S, name)))
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in be.BKFL_TABLES:
            retire_dynamic_model(name)
        engine.dispose()


def _scanned(conn, statement, parameters):
    """The rows a statement's scans of the derived table touched - kept and filtered out - by EXPLAIN ANALYZE."""
    plan = conn.exec_driver_sql("EXPLAIN (ANALYZE, FORMAT JSON) " + statement, parameters).scalar()
    plan = plan if isinstance(plan, list) else json.loads(plan)
    total, nodes = 0, [plan[0]["Plan"]]
    while nodes:
        node = nodes.pop()
        if node.get("Relation Name") == "bkfl_test_derived" or "Index Only Scan" in node.get("Node Type", ""):
            total += int(node.get("Actual Rows", 0)) + int(node.get("Rows Removed by Filter", 0))
        nodes += node.get("Plans", [])
    return total


def test_every_statement_reads_at_most_a_page_of_the_table(db):
    from admin import retroactive
    rule = retroactive._enrichment_rule("bkfl_rule")
    sent = []

    def seen(_conn, _cursor, statement, parameters, *_rest):
        if "bkfl_test_derived" in statement:
            sent.append((statement, parameters))
    event.listen(db.get_bind(), "before_cursor_execute", seen)
    try:
        pages = list(analysis.derived_pages(db, rule, scope=analysis.SCOPE_QUEUE, size=_Page()))
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", seen)
    assert sorted(r["row_id"] for page in pages for r in page) == ["%06d" % g for g in range(ROWS - WAITING + 1, ROWS + 1)]
    assert len(sent) >= ROWS // PAGE                                       # canary: it paged the table
    with db.get_bind().connect() as conn:
        read = [_scanned(conn, statement, parameters) for statement, parameters in sent]
    assert max(read) <= PAGE, sorted(read)[-3:]
