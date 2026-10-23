# -*- coding: utf-8 -*-
"""C five stages 8 · 총괄 6deeb723e: a slot's batch reads the reloads (`_reloaded` -> `system_reload.reloads_after`)
before it runs, and that read stood outside the try that says a raised batch and runs it again - a dropped
connection there ended the slot, and the slot's end set its whole line aside. The read is the batch's now: said,
FAILED (the dispatcher rests the line and gives it again), the slot lives, and nothing the files changed is lost.
"""
import asyncio
import logging

from sqlalchemy.exc import OperationalError

from chain import control, slots
from database import config_watcher, database
from runtime import system_reload
from utils import heartbeat


class _Session:
    def rollback(self):
        pass

    def close(self):
        pass


def test_a_dropped_connection_in_the_reload_runs_the_batch_again(monkeypatch, caplog):
    def dropped(session, seen):
        raise OperationalError("SELECT ... FROM system_reloads", {}, Exception("server closed the connection"))

    applied = []
    monkeypatch.setattr(control, "paused", lambda: None)
    monkeypatch.setattr(database, "SessionLocal", _Session)
    monkeypatch.setattr(system_reload, "reloads_after", dropped)
    monkeypatch.setattr(config_watcher, "apply_pending", lambda: applied.append(1) or [])
    monkeypatch.setattr(heartbeat, "record_lap", lambda *a, **k: None)

    with caplog.at_level(logging.ERROR):
        outcome, rules, seen = asyncio.run(slots._run_batch("line-1", ["rule"], 7))

    assert (outcome, rules, seen) == (slots.FAILED, ["rule"], 7)
    assert any("a batch of line line-1 raised - its events wait as they were and run again" in r.getMessage()
               for r in caplog.records)
    assert applied == [], "the files' changes were applied though the read raised - the batch that runs again " \
                          "would not see them"
