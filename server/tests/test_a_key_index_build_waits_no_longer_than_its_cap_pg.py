# -*- coding: utf-8 -*-
"""총괄 49792d3f6 A (소유자 「체인은 뭐 10 분째 스타팅이냐」): the business-key index build waits for the transactions on its
table no longer than its cap; then the leftover is dropped and the session holding the table is named. The build is
the migration's own (`build_index`) aimed at the test schema's table - the product's DDL names public."""
import logging
import os
import sys
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import ingestion_worker as worker                                   # noqa: E402
import db_safety                                                               # noqa: E402
from conftest import PG_TEST_SCHEMA                                            # noqa: E402
from migrations import add_business_key_unique_index as uq                     # noqa: E402

pytestmark = pytest.mark.pg
TABLE, NAME = "bkx_held", "uq_bkx_held_bk"


def _build_here(conn, table, name):
    """uq.build_index's statement on the test schema's table, its errors read as uq.build_index reads them."""
    try:
        conn.execute(text('CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS %s ON "%s"."%s" (business_key_val)'
                          % (uq.quote_ident(name), PG_TEST_SCHEMA, table)))
    except Exception as e:                                                     # noqa: BLE001
        return (uq.BLOCKED if db_safety.waited_past_the_lock_timeout(e) else uq.FAILED), str(e).splitlines()[0]
    return uq.OK_CREATED, "built"


def test_a_build_held_by_an_open_transaction_gives_up_names_the_holder_and_leaves_no_index(pg_engine, caplog,
                                                                                          monkeypatch):
    import db_safety as safety

    monkeypatch.setattr(safety, "DDL_LOCK_TIMEOUT", "2s")
    seat = SimpleNamespace(build_index=_build_here, BLOCKED=uq.BLOCKED, quote_ident=uq.quote_ident)
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
        conn.execute(text('CREATE TABLE "%s"."%s" (business_key_val text)' % (PG_TEST_SCHEMA, TABLE)))
    holder = pg_engine.connect()
    holder_pid = holder.execute(text("SELECT pg_backend_pid()")).scalar()
    holder.execute(text("INSERT INTO \"%s\".\"%s\" VALUES ('k1')" % (PG_TEST_SCHEMA, TABLE)))   # an open write holds it
    valid = ("SELECT count(*) FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid JOIN pg_namespace n ON "
             "n.oid = c.relnamespace WHERE n.nspname = :s AND c.relname = :n AND i.indisvalid")
    try:
        caplog.set_level(logging.WARNING)
        started = time.monotonic()
        first, _detail = worker._build_unique_index_waiting(pg_engine, seat, TABLE, NAME)
        took = time.monotonic() - started
        holder.rollback()                                                      # what held it ends
        second, _detail = worker._build_unique_index_waiting(pg_engine, seat, TABLE, NAME)
        with pg_engine.connect() as conn:
            built = conn.execute(text(valid), {"s": PG_TEST_SCHEMA, "n": NAME}).scalar()
    finally:
        holder.rollback()
        holder.close()
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
    said = [r.getMessage() for r in caplog.records if "not built - waited 2s" in r.getMessage()]
    assert (first, second, built) == (uq.BLOCKED, uq.OK_CREATED, 1) and took < 30, (first, second, built, took)
    assert said and "pid %d" % holder_pid in said[0], said
