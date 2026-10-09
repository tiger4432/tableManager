# -*- coding: utf-8 -*-
"""The schema sync's ADD COLUMN waits `db_safety.DDL_LOCK_TIMEOUT` at most (총괄 3c26854c3 ·
a696ee4e8, 소유자 「7번 ㄱ」).

Without a limit an ALTER queued behind a long transaction held the process that called it -
the API's boot, the watcher's, the chain worker's import, a config save - and every reader
and writer of that table queued behind the ALTER. With it the ALTER gives up by name, the
process and the other tables go on, and the next start or config save adds the column. What
is NOT true: 「only that column is late」 - until it stands, the model names it in every
SELECT and INSERT, so the table itself fails, by that column's name.
"""
import ast
import inspect
import os
import sys
import threading
import time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import db_safety                                                    # noqa: E402
from database import models                                         # noqa: E402

HELD, FREE = "ss_held", "ss_free"
CONFIG = {name: {"business_key": "k", "composite_key_source": ["k"],
                 "column_types": {"k": "string", "late": "string"},
                 "display_columns": ["k", "late"]} for name in (HELD, FREE)}
#: The four seats the order names; each must reach the one function. The chain worker's is a startup
#: step since 5b-2 (총괄 bdb356d3f) - in its loop module, not at `run_chain_worker.py`'s import.
CALLERS = ["main.py", "run_watcher.py", os.path.join("chain", "ingestion_worker.py"),
           os.path.join("database", "config_watcher.py")]


class _Code(Exception):
    def __init__(self, message, pgcode=None):
        super().__init__(message)
        self.pgcode = pgcode


class _Wrapped(Exception):
    def __init__(self, orig):
        super().__init__(str(orig))
        self.orig = orig


def test_one_judge_says_a_ddl_waited_out_its_lock():
    assert db_safety.waited_past_the_lock_timeout(_Code("x", "55P03"))
    assert db_safety.waited_past_the_lock_timeout(_Wrapped(_Code("x", "55P03")))
    assert db_safety.waited_past_the_lock_timeout(
        Exception("canceling statement due to lock timeout"))
    assert not db_safety.waited_past_the_lock_timeout(
        Exception("canceling statement due to statement timeout"))
    assert not db_safety.waited_past_the_lock_timeout(_Code("duplicate key", "23505"))


def test_every_seat_that_asked_the_question_asks_the_one_judge():
    from chain import unique_key
    from ledger import schema

    for module in (unique_key, schema, models):
        source = inspect.getsource(module)
        assert "db_safety.waited_past_the_lock_timeout(" in source, module.__name__
        assert "canceling statement" not in source and "55P03\"" not in source, module.__name__


@pytest.mark.parametrize("caller", CALLERS)
def test_each_of_the_four_seats_reaches_the_function(caller):
    tree = ast.parse(open(os.path.join(SERVER_DIR, caller), encoding="utf-8").read())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr == "sync_dynamic_tables_schema"]
    assert calls, caller


@pytest.fixture(name="two_tables")
def fixture_two_tables(pg_engine, monkeypatch):
    """Two declared tables whose `late` column the database does not have yet."""
    monkeypatch.setattr(db_safety, "DDL_LOCK_TIMEOUT", "1s")
    models.init_dynamic_models(CONFIG)
    monkeypatch.setattr(models, "DYNAMIC_TABLES",
                        {name: models.DYNAMIC_TABLES[name] for name in CONFIG})
    with pg_engine.begin() as c:
        for name in CONFIG:
            models.DYNAMIC_TABLES[name].__table__.create(bind=c, checkfirst=True)
            c.execute(text('ALTER TABLE "%s" DROP COLUMN late' % name))
    try:
        yield
    finally:
        with pg_engine.begin() as c:
            for name in CONFIG:
                c.execute(text('DROP TABLE IF EXISTS "%s"' % name))


def _columns(pg_engine, table):
    with pg_engine.connect() as c:
        return {row[0] for row in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t AND table_schema = current_schema()"), {"t": table})}


def _sync_in_a_thread(engine):
    out = {}

    def run():
        try:
            models.sync_dynamic_tables_schema(engine)
        except BaseException as exc:                                # noqa: BLE001
            out["error"] = exc
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, out


@pytest.mark.pg
def test_a_held_table_is_deferred_by_name_and_the_rest_goes_on(pg_engine, two_tables, caplog):
    holder = pg_engine.connect()
    holder.begin()
    holder.execute(text('SELECT count(*) FROM "%s"' % HELD))
    try:
        started = time.time()
        with caplog.at_level("ERROR"):
            thread, out = _sync_in_a_thread(pg_engine)
            thread.join(10)
            waited = time.time() - started
            # Without the limit this is where it stayed - release it so the thread can end.
            if thread.is_alive():
                holder.rollback()
                thread.join(30)
        assert waited < 10, "the ALTER did not read the limit - it waited behind the holder"
        assert "error" not in out, out
        said = [r.getMessage() for r in caplog.records if HELD in r.getMessage()]
        assert any("'late'" in m and "was not added" in m and "1s" in m
                   and "every read and write" in m for m in said), said
        assert "late" not in _columns(pg_engine, HELD)
        assert "late" in _columns(pg_engine, FREE), "the table nobody held was held up too"

        # The meaning, measured: the table itself fails, by the column's name.
        db = sessionmaker(bind=pg_engine)()
        try:
            with pytest.raises(Exception) as failed:
                db.query(models.DYNAMIC_TABLES[HELD]).first()
            assert "late" in str(failed.value)
        finally:
            db.rollback()
            db.close()
    finally:
        holder.rollback()
        holder.close()

    models.sync_dynamic_tables_schema(pg_engine)
    assert "late" in _columns(pg_engine, HELD), "the next call did not add it"


@pytest.mark.pg
def test_the_pool_gets_its_connection_back_without_the_limit(pg_engine, two_tables):
    from support import isolated_pg

    with pg_engine.connect() as c:
        schema = c.execute(text("SELECT current_schema()")).scalar()
    one = create_engine(pg_engine.url, pool_size=1, max_overflow=0,
                        connect_args=isolated_pg.scratch_connect_args(schema))
    try:
        models.sync_dynamic_tables_schema(one)
        with one.connect() as again:
            assert again.execute(text("SHOW lock_timeout")).scalar() != "1s"
        assert "late" in _columns(pg_engine, HELD)
    finally:
        one.dispose()
