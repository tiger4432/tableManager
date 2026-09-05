# -*- coding: utf-8 -*-
"""Two chain loops on one queue, and neither of them observable.

`main.py` starts the loop from the web server's startup event unconditionally, so running
`run_chain_worker.py` beside it gives two. Measured 2026-09-04: two pids alternating in
one heartbeat file, the same outbox rows picked up twice, and restarting the standalone
worker leaving the older code live inside uvicorn - so "restart the chain worker" did not
restart the chain worker.

⛔ AND THE GUARD MUST NOT FIRE ON A RESTART. A killed worker leaves a heartbeat that stays
fresh for another minute; refusing to start then would break the most ordinary operation
there is. Three conditions all have to hold - fresh, not me, and alive - and anything it
cannot establish means "start", which is today's behaviour.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_ingestion_worker as worker                          # noqa: E402


def entry(**kw):
    base = {"pid": 999001, "stale": False, "age_seconds": 1.2}
    base.update(kw)
    return {"chain": base}


def arrange(monkeypatch, hb_entry, alive=True):
    monkeypatch.setattr(worker.heartbeat, "read_all", lambda **k: hb_entry)
    import psutil
    monkeypatch.setattr(psutil, "pid_exists", lambda pid: alive)


def test_a_live_foreign_loop_is_reported(monkeypatch):
    arrange(monkeypatch, entry(), alive=True)
    got = worker.another_chain_loop_is_running()
    assert got and "999001" in got


def test_a_stale_beat_does_not_count(monkeypatch):
    """Someone WAS running. That is not someone running."""
    arrange(monkeypatch, entry(stale=True), alive=True)
    assert worker.another_chain_loop_is_running() is None


def test_a_dead_pid_does_not_count(monkeypatch):
    """🔴 THE RESTART CASE. The beat is still fresh because it was written a moment before
    the process was killed; the pid is gone. Refusing here would block every restart."""
    arrange(monkeypatch, entry(), alive=False)
    assert worker.another_chain_loop_is_running() is None


def test_my_own_beat_does_not_count(monkeypatch):
    arrange(monkeypatch, entry(pid=os.getpid()), alive=True)
    assert worker.another_chain_loop_is_running() is None


def test_no_heartbeat_at_all_means_start(monkeypatch):
    arrange(monkeypatch, {}, alive=True)
    assert worker.another_chain_loop_is_running() is None


def test_an_unreadable_heartbeat_means_start(monkeypatch):
    def boom(**k):
        raise OSError("no heartbeat directory")
    monkeypatch.setattr(worker.heartbeat, "read_all", boom)
    assert worker.another_chain_loop_is_running() is None


def test_without_psutil_it_starts_rather_than_guessing(monkeypatch):
    """It cannot tell whether the pid is alive, so it does what it did before this guard
    existed. A guard that stops the only worker on a box with a missing dependency is
    worse than no guard."""
    arrange(monkeypatch, entry(), alive=True)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def no_psutil(name, *a, **k):
        if name == "psutil":
            raise ImportError("no psutil here")
        return real_import(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", no_psutil)
    assert worker.another_chain_loop_is_running() is None


def test_standing_down_is_not_silent(monkeypatch, caplog):
    """⛔ A process that does nothing and says nothing is indistinguishable from one that
    is working. That is the class this whole day was spent removing."""
    import asyncio
    import logging

    arrange(monkeypatch, entry(), alive=True)
    with caplog.at_level(logging.WARNING):
        asyncio.run(worker.start_chain_ingestion_worker(None))

    said = "\n".join(r.getMessage() for r in caplog.records)
    assert "NOT starting" in said and "999001" in said
