# -*- coding: utf-8 -*-
"""Owner 11-09 «전면 가상전환» (the owner paused every world in operation): a paused ledger does no work.

  every world paused     the follow-up takes nothing, says no failure, and the event waits unmarked (it failed every
                         lap: an empty follower list fell to the operating world's setup, None)
  a world switched on    the queue is taken, into that world
  the operating world    the row census loads no declaration and scans nothing
  paused
"""
import asyncio
import os
import sys

import pytest
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pacing                                                       # noqa: E402
from database import models                                         # noqa: E402
from ledger import followup, schema                                 # noqa: E402
from ledger import worker as ledger_worker                          # noqa: E402


class Stop(Exception):
    pass


def _laps(monkeypatch, loop_fn, factory, n=15):
    """`n` laps of a ledger loop, its rests recorded instead of slept."""
    laps = []

    async def fake_sleep(seconds):
        laps.append(seconds)
        if len(laps) == n:
            raise Stop

    monkeypatch.setattr(ledger_worker.asyncio, "sleep", fake_sleep)
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(Stop):
            loop.run_until_complete(loop_fn(factory))
    finally:
        loop.close()
    return laps


def test_every_world_paused_the_follow_up_takes_nothing_and_fails_nothing(db_session, monkeypatch, caplog):
    db_session.add(models.DatabaseOutbox(event_uuid="paused-1", event_type="EDIT", table_name="dt_log",
                                         payload={"row_id": "r1"}, processed_chain=True))
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind())
    engine = db_session.get_bind()
    assert followup.outbox_depth(engine) == 1, "canary: one event waits for the ledger"
    monkeypatch.setattr(pacing, "job_pace", lambda job: (None, 0))
    monkeypatch.setattr(schema, "live_worlds", lambda: [])
    followup.REPEATS.clear()
    caplog.set_level("WARNING", logger=ledger_worker.logger.name)

    assert len(_laps(monkeypatch, ledger_worker.run_ledger_followup, factory)) == 15
    said = [r.getMessage() for r in caplog.records if "[LedgerFollowUp]" in r.getMessage()]
    assert said == [] and followup.outbox_depth(engine) == 1, said

    taken = []
    monkeypatch.setattr(schema, "live_worlds", lambda: [schema.DEFAULT_WORLD])
    monkeypatch.setattr(ledger_worker, "_compiled_setup", lambda world: "its setup")
    monkeypatch.setattr(followup, "drain_outbox_once", lambda eng, setup, followers, rows=None: taken.append(followers))
    ledger_worker._drain_ledger_followup_sync(factory)
    assert taken == [[(schema.DEFAULT_WORLD, "its setup")]], "canary: a world switched on, the queue is taken"


def test_the_operating_world_paused_the_census_scans_nothing(monkeypatch):
    loaded = []
    monkeypatch.setattr(pacing, "job_pace", lambda job: (1, 0))
    monkeypatch.setattr(ledger_worker, "_load_setup_sync", lambda factory: loaded.append(1) or object())
    monkeypatch.setattr("ledger.backfill.census_sources", lambda setup: ([], []))

    monkeypatch.setattr(schema, "live", lambda world=None: False)
    laps = _laps(monkeypatch, ledger_worker.run_ledger_row_census, None, n=3)
    assert loaded == [] and laps == [60.0, 60.0, 60.0]

    monkeypatch.setattr(schema, "live", lambda world=None: True)
    _laps(monkeypatch, ledger_worker.run_ledger_row_census, None, n=3)
    assert loaded == [1, 1, 1], "canary: live, each lap reads the declaration"
