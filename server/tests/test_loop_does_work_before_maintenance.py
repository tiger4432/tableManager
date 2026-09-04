# -*- coding: utf-8 -*-
"""The loop's first work is fetching and processing; maintenance comes after it.

Maintenance used to run first. Normally that costs nothing - measured 2026-09-05, the
sweep's query is an index scan whose population is zero and it returns immediately - but
when notifications HAVE been lost the sweep fires a broadcast per affected table through
a POST with a three second timeout, and every one of those used to queue up in front of
the fetch. That is the moment the loop must not stall, because it is already the moment
notifications are being lost.

🔴 THE TRAP THIS FILE EXISTS FOR. The obvious way to reorder - move the maintenance to
the bottom of the loop body - turns the safety net OFF, because the body leaves early
via `continue` whenever there is nothing to do. That is the most common path and the one
where maintenance matters most. So maintenance sits in a `finally`, and this test drives
the real loop down the idle path to prove it still runs.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_ingestion_worker as worker                          # noqa: E402


class _Query:
    """Whatever the loop asks of a query, answer 'nothing'."""
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


class _Session:
    def __init__(self, log):
        self.log = log

    def query(self, *a, **k):
        return _Query()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        self.log.append("close")


class _Listener:
    def __init__(self, *a, **k):
        pass

    async def start(self):
        pass

    async def stop(self):
        pass

    def close(self):
        pass

    async def wait(self, timeout):
        await asyncio.sleep(0.01)          # an idle round, cheaply
        return False


@pytest.fixture
def idle_loop(monkeypatch):
    """The real loop, with an empty queue and nothing else moving."""
    calls = {"sweep": 0, "closes": []}

    async def fake_sweep(db, rules, factory):
        calls["sweep"] += 1

    monkeypatch.setattr(worker, "sweep_undelivered_broadcasts", fake_sweep)
    monkeypatch.setattr(worker, "load_chain_rules", lambda: [])
    monkeypatch.setattr(worker, "OutboxListener", _Listener)
    monkeypatch.setattr(worker.internal_event_client, "startup_lines", lambda *a, **k: [])
    monkeypatch.setattr(worker.heartbeat, "beat", lambda *a, **k: None)
    monkeypatch.setattr(worker, "warmup_worker", lambda *a, **k: None)
    monkeypatch.setattr(worker, "SWEEP_INTERVAL_FOR_TEST", 0.0, raising=False)

    factory = lambda: _Session(calls["closes"])                  # noqa: E731
    return calls, factory


def _run_briefly(factory, seconds=0.6):
    async def go():
        try:
            await asyncio.wait_for(worker.start_chain_ingestion_worker(factory), seconds)
        except asyncio.TimeoutError:
            pass
    asyncio.run(go())


def test_the_sweep_still_runs_when_there_is_nothing_to_do(idle_loop):
    """🔴 GATE: moving maintenance must not turn it off.

    An empty queue leaves the loop body through `continue`. If maintenance sat at the
    bottom of the body instead of in `finally`, this count would be zero - the safety
    net silently disabled by a change made for latency.
    """
    calls, factory = idle_loop
    _run_briefly(factory)
    assert calls["sweep"] > 0, \
        "the undelivered-broadcast sweep never ran on an idle loop"


def test_the_session_is_closed_every_round(idle_loop):
    """The maintenance block shares the `finally` with `db.close()`; a maintenance
    failure must not leak the session."""
    calls, factory = idle_loop
    _run_briefly(factory)
    assert len(calls["closes"]) > 1, "the session was not closed each iteration"


def test_a_failing_maintenance_pass_does_not_stop_the_loop(monkeypatch, idle_loop):
    """It runs in a `finally` that is also on the exception path. An exception raised
    there would replace the original error and kill the round."""
    calls, factory = idle_loop
    rounds = {"n": 0}

    async def angry_sweep(db, rules, factory_):
        rounds["n"] += 1
        raise RuntimeError("sweep exploded")

    monkeypatch.setattr(worker, "sweep_undelivered_broadcasts", angry_sweep)
    _run_briefly(factory)
    # The sweep is throttled to once every SWEEP_INTERVAL, so a short run fires it once.
    # What is asserted is that the loop kept going AFTER it threw - many more rounds than
    # sweeps, each closing its session.
    assert rounds["n"] >= 1, "the maintenance pass never ran"
    assert len(calls["closes"]) > rounds["n"] + 1, \
        "the loop stopped after the maintenance failure instead of carrying on"
