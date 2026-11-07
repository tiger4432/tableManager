# -*- coding: utf-8 -*-
"""총괄 49792d3f6 A (소유자 「체인은 뭐 10 분째 스타팅이냐」): the business-key index build does not hold the chain's start
for ever. Since the one builder (`models._ensure_one_index`, 1bcc2fa03): a session holding the table open past the
wait before the build puts the build off (BLOCKED here) and is named; a short writer is waited out by the build itself
(총괄 11-06). The build is `uq.index_ddl` on the test schema's table (its search path)."""
import os
import sys
import threading
import time

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import ingestion_worker as worker                                   # noqa: E402
from conftest import PG_TEST_SCHEMA                                            # noqa: E402
from database import models                                                    # noqa: E402
from migrations import add_business_key_unique_index as uq                     # noqa: E402

pytestmark = pytest.mark.pg
TABLE, NAME = "bkx_held", "uq_bkx_held_bk"


def _cancel_the_build_after(engine, seconds):
    """The test's cap, not the product's: a build that waits for a holder after all would hang the run - cancelled
    after `seconds` it ends, and the cell is red (총괄 11-07)."""
    def cancel():
        with engine.connect() as conn:
            conn.execute(text("SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE datname = current_database() "
                              "AND pid <> pg_backend_pid() AND query = :q"), {"q": uq.index_ddl(TABLE, NAME)})
            conn.commit()
    timer = threading.Timer(seconds, cancel)
    timer.daemon = True
    timer.start()
    return timer


def _held_past_the_wait(pg_engine, monkeypatch):
    """The table made, a writer left open on it past the wait before the build -> (that connection, its pid)."""
    monkeypatch.setattr(models, "INDEX_WAIT_BEFORE_SECONDS", 1.0)
    monkeypatch.setattr(models, "INDEX_WAIT_POLL_SECONDS", 0.2)
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
        conn.execute(text('CREATE TABLE "%s"."%s" (business_key_val text)' % (PG_TEST_SCHEMA, TABLE)))
    holder = pg_engine.connect()
    pid = holder.execute(text("SELECT pg_backend_pid()")).scalar()
    holder.execute(text("INSERT INTO \"%s\".\"%s\" VALUES ('k1')" % (PG_TEST_SCHEMA, TABLE)))   # an open write
    time.sleep(1.5)                                                                  # open longer than the wait
    return holder, pid


def _build(pg_engine):
    cap = _cancel_the_build_after(pg_engine, 20)
    try:
        return worker._build_unique_index_waiting(pg_engine, uq, TABLE, NAME)
    finally:
        cap.cancel()


def test_a_build_held_by_a_transaction_left_open_is_put_off_names_the_holder_and_leaves_no_index(pg_engine,
                                                                                                monkeypatch):
    holder, holder_pid = _held_past_the_wait(pg_engine, monkeypatch)
    valid = ("SELECT count(*) FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid JOIN pg_namespace n ON "
             "n.oid = c.relnamespace WHERE n.nspname = :s AND c.relname = :n AND i.indisvalid")
    try:
        started = time.monotonic()
        first, detail = _build(pg_engine)
        took = time.monotonic() - started
        holder.rollback()                                                      # what held it ends
        second, _detail = _build(pg_engine)
        with pg_engine.connect() as conn:
            built = conn.execute(text(valid), {"s": PG_TEST_SCHEMA, "n": NAME}).scalar()
    finally:
        holder.rollback()
        holder.close()
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
    assert (first, second, built) == (uq.BLOCKED, uq.OK_CREATED, 1) and took < 15, (first, second, built, took)
    assert "not built - waited 1s for pid %d holding %s (idle in transaction, open " % (holder_pid, TABLE) in detail, \
        detail


def test_a_leftover_is_rebuilt_though_the_census_read_the_table_first(pg_engine, monkeypatch):
    """총괄 4593442f9 re-review ①: the census reads the table (AccessShareLock) on the connection the loop keeps - the
    read ends before the drop and the build, or the CONCURRENTLY drop waits on its own process and the leftover stays.
    The leftover is a build that failed on a duplicate key."""
    from sqlalchemy.orm import sessionmaker

    state = ("SELECT i.indisvalid FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid JOIN pg_namespace n ON "
             "n.oid = c.relnamespace WHERE n.nspname = :s AND c.relname = :n")
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
        conn.execute(text('CREATE TABLE "%s"."%s" (business_key_val text)' % (PG_TEST_SCHEMA, TABLE)))
    with pg_engine.begin() as conn:
        conn.execute(text("INSERT INTO \"%s\".\"%s\" VALUES ('k1'), ('k1')" % (PG_TEST_SCHEMA, TABLE)))
    assert _build(pg_engine)[0] == uq.FAILED
    with pg_engine.begin() as conn:
        conn.execute(text('DELETE FROM "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
    with pg_engine.connect() as conn:
        assert conn.execute(text(state), {"s": PG_TEST_SCHEMA, "n": NAME}).scalar() is False, "CANARY: a leftover"

    def census(conn, table, **kw):
        conn.execute(text('SELECT business_key_val, count(*) FROM "%s"."%s" GROUP BY 1' % (PG_TEST_SCHEMA, table)))
        return {"surplus": 0, "table": table}

    monkeypatch.setattr(uq, "tables_with_business_key", lambda conn: [TABLE])
    monkeypatch.setattr(uq, "existing_unique_index", lambda conn, t: (NAME, False))
    monkeypatch.setattr(uq, "duplicate_census", census)
    monkeypatch.setattr(uq, "unique_index_name", lambda t: NAME)
    try:
        out = worker._ensure_business_key_unique_indexes_sync(sessionmaker(bind=pg_engine))
        with pg_engine.connect() as conn:
            valid = conn.execute(text(state), {"s": PG_TEST_SCHEMA, "n": NAME}).scalar()
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
    assert ([built[:2] for built in out["built"]], valid) == ([(TABLE, uq.OK_CREATED)], True), (out, valid)
    assert "is INVALID from an earlier failure; dropping and rebuilding" in out["built"][0][2], out
