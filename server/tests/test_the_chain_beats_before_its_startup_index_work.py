# -*- coding: utf-8 -*-
"""⑤ startup DDL (총괄 948ee98b5 · 3ef5fe54f): the chain worker's first beat goes out before its
unique index work, that work runs beside the loop with a time limit, a DDL that waits past the
limit is deferred by name to the next start or reload, and a reload runs it again.

Production: a `DROP INDEX CONCURRENTLY` at startup waited on a query nobody would end, the new
worker never beat, the heartbeat kept the old pid - foreign_beat - and the queue did not drain.
"""
import asyncio
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

import db_safety                                                             # noqa: E402
from chain import ingestion_worker as worker                                 # noqa: E402
from chain import unique_key                                                 # noqa: E402
from chain.join_key_index import INDEX_PREFIX                                # noqa: E402


# ---------------------------------------------------------------------------
# the loop: its first beat, then the index work beside it
# ---------------------------------------------------------------------------

class _Stop(BaseException):
    """A `BaseException`: the loop catches `Exception` and would carry on."""


class _Query:
    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def first(self):
        return None

    def all(self):
        return []


class _Listener:
    waits = 0

    def __init__(self, *a, **k):
        pass

    async def start(self):
        pass

    async def stop(self):
        pass

    def close(self):
        pass

    async def wait(self, timeout):
        type(self).waits += 1
        await asyncio.sleep(0)
        return False


class _Session:
    """Ends the loop after `ticks` idle waits - and lets the index work go at that moment, so
    「still waiting when the loop had ticked」 is what `released` records."""

    def __init__(self, release, ticks=5):
        self.release, self.ticks = release, ticks

    def query(self, *a, **k):
        if _Listener.waits >= self.ticks:
            self.release.set()
            raise _Stop()
        return _Query()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


async def _nothing(*_a, **_k):
    return None


def test_the_first_beat_goes_out_before_the_index_work_and_the_loop_does_not_wait_for_it(
        monkeypatch):
    _Listener.waits = 0
    beats, runs, release = [], [], threading.Event()

    def index_work(rules, factory):
        # a DDL waiting on a lock: it holds until the loop has ticked. EVERY run is kept -
        # a run before the loop would otherwise hide behind the loop's own run
        runs.append({"beats_at_start": len(beats)})
        runs[-1]["released"] = release.wait(10)

    monkeypatch.setattr(worker, "another_chain_loop_is_running", lambda *a, **k: None)
    monkeypatch.setattr(worker, "OutboxListener", _Listener)
    monkeypatch.setattr(worker, "load_chain_rules", lambda: [])
    monkeypatch.setattr(worker, "warmup_worker", lambda *a, **k: None)
    monkeypatch.setattr(worker, "sweep_undelivered_broadcasts", _nothing)
    monkeypatch.setattr(worker, "run_ledger_followup", _nothing)
    monkeypatch.setattr(worker, "run_ledger_row_census", _nothing)
    monkeypatch.setattr(worker.internal_event_client, "startup_lines", lambda *a, **k: [])
    monkeypatch.setattr(worker.heartbeat, "beat",
                        lambda name, *a, **k: beats.append(name) if name == "chain" else None)
    monkeypatch.setattr(worker, "_ensure_declared_indexes_sync", index_work)
    session = _Session(release)

    async def go():
        try:
            await asyncio.wait_for(worker.start_chain_ingestion_worker(lambda: session), 30.0)
        except (_Stop, asyncio.TimeoutError):
            pass

    asyncio.run(go())

    assert len(runs) == 1, runs
    assert runs[0]["beats_at_start"] >= 1, "the index work ran before the worker's first beat"
    assert runs[0]["released"], "the loop waited for the index work instead of ticking beside it"
    assert _Listener.waits >= 5


def test_a_reload_asks_again_after_the_run_before_it(monkeypatch):
    """Each run forgets what the last one answered - a changed declaration and a deferred index
    are both asked again - and a reload's run starts only when the previous one has ended."""
    from chain import synthesis

    calls = []

    def ensure(db, rules):
        calls.append(("start", dict(unique_key._TRIED)))
        time.sleep(0.2)
        calls.append(("end", None))
        return {"ensured": [], "skipped": []}

    monkeypatch.setattr(synthesis, "ensure_declared_unique_keys", ensure)
    monkeypatch.setattr(synthesis, "retract_unrequired_indexes_once", lambda db: {})
    unique_key._TRIED["r"] = {"state": "deferred"}

    class _Db:
        def close(self):
            pass

    async def go():
        first = worker._start_index_work([], _Db)
        second = worker._start_index_work([], _Db, after=first)
        await second

    asyncio.run(go())

    assert [step for step, _memo in calls] == ["start", "end", "start", "end"], calls
    assert calls[0][1] == {}, "the run answered from the last run's memory"


def test_the_loop_starts_it_after_its_beat_and_again_after_every_reload():
    """⚠️ A text oracle: the reload branch cannot run without the process around it."""
    source = inspect.getsource(worker.start_chain_ingestion_worker)

    assert source.count("_start_index_work(") == 2
    assert "after=index_work" in source
    assert "ensure_declared_unique_keys" not in inspect.getsource(worker.warmup_worker)


def test_both_ddl_seats_read_one_time_limit():
    """총괄 3ef5fe54f: the same value is the same constant. unique_key's reading of it is
    scored by the PG cells below (the limit set there is 1 s, and they end in seconds)."""
    from ledger import schema

    source = inspect.getsource(schema)
    assert "SET LOCAL lock_timeout = '%s'\" % db_safety.DDL_LOCK_TIMEOUT" in source
    assert "'20s'" not in source and "'20s'" not in inspect.getsource(unique_key)


# ---------------------------------------------------------------------------
# PostgreSQL: the limit, the deferral, and the retry
# ---------------------------------------------------------------------------

def _holding(pg_engine, table):
    """An open transaction that wrote to `table` - what a `CONCURRENTLY` DDL waits for."""
    holder = pg_engine.connect()
    holder.begin()
    holder.execute(text("INSERT INTO %s (k) VALUES ('held')" % table))
    return holder


@pytest.mark.pg
def test_an_index_that_waits_past_the_limit_is_deferred_by_name_and_built_on_the_next_run(
        pg_engine, monkeypatch, caplog):
    monkeypatch.setattr(db_safety, "DDL_LOCK_TIMEOUT", "1s")
    table = "ddl_wait_build"
    # ⚠️ IN `public`, AS IN PRODUCTION: the cancelled build leaves an INVALID index under the
    #    same name, and `invalid_leftovers` looks for it in `public` - in the scratch schema the
    #    retry could not see it and failed with 「already exists」.
    with pg_engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS public.%s" % table))
        c.execute(text("CREATE TABLE public.%s (k text)" % table))
    db = sessionmaker(bind=pg_engine)()
    holder = _holding(pg_engine, table)
    try:
        unique_key.forget()
        started = time.time()
        with caplog.at_level("WARNING"):
            report = unique_key.ensure_once(db, "r", table, ["k"])
        assert report["state"] == "deferred", report
        assert time.time() - started < 10, "the DDL did not read the limit it was given"
        assert any("다음 기동/리로드로 미룹니다" in r.getMessage() and table in r.getMessage()
                   for r in caplog.records)

        holder.rollback()
        unique_key.forget()
        again = unique_key.ensure_once(db, "r", table, ["k"])
        assert again["state"] == "ok" and again["created"], again.get("error")
        assert again["dropped"], "the cancelled build's INVALID leftover was not cleared"
    finally:
        holder.close()
        db.rollback()
        db.close()
        unique_key.forget()
        with pg_engine.begin() as c:
            c.execute(text("DROP TABLE IF EXISTS public.%s" % table))


@pytest.mark.pg
def test_a_retraction_that_waits_past_the_limit_is_deferred_by_name_and_the_index_stays(
        pg_engine, monkeypatch, caplog):
    monkeypatch.setattr(db_safety, "DDL_LOCK_TIMEOUT", "1s")
    table, index = "ddl_wait_drop", INDEX_PREFIX + "ddl_wait_drop_k"
    with pg_engine.begin() as c:
        c.execute(text("CREATE TABLE %s (k text)" % table))
        c.execute(text('CREATE UNIQUE INDEX "%s" ON %s (k)' % (index, table)))
    db = sessionmaker(bind=pg_engine)()
    holder = _holding(pg_engine, table)
    try:
        # only this index is unrequired - the database's other product indexes are left alone
        required = {name for _t, name in unique_key.product_indexes(db) if name != index}
        unique_key.forget_retractions()
        started = time.time()
        with caplog.at_level("WARNING"):
            report = unique_key.retract_unrequired_once(db, required)
        assert index not in report["dropped"], report
        assert time.time() - started < 10
        assert any("걷지 못했습니다" in r.getMessage() and index in r.getMessage()
                   and "23505" in r.getMessage() for r in caplog.records)
        assert index in {name for _t, name in unique_key.product_indexes(db)}
    finally:
        holder.rollback()
        holder.close()
        db.rollback()
        db.close()
        unique_key.forget_retractions()
        with pg_engine.begin() as c:
            c.execute(text("DROP TABLE IF EXISTS %s" % table))


@pytest.mark.pg
def test_the_pool_gets_the_connection_back_without_the_limit(pg_engine, monkeypatch):
    """A session setting outlives `close()`: the next user of that pooled connection did not
    ask for a 1 s lock limit."""
    monkeypatch.setattr(db_safety, "DDL_LOCK_TIMEOUT", "1s")
    one = create_engine(pg_engine.url, pool_size=1, max_overflow=0)
    try:
        connection = unique_key._open_ddl_connection(one)
        assert connection.execute(text("SHOW lock_timeout")).scalar() == "1s"
        unique_key._close_ddl_connection(connection)
        with one.connect() as again:
            assert again.execute(text("SHOW lock_timeout")).scalar() != "1s"
    finally:
        one.dispose()
