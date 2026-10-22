# -*- coding: utf-8 -*-
"""A step outside a group that touches the database runs as the group does - on a thread, the loop beating every
slice, under a claim that names the step (총괄 10-22: «체인 순간 wedge»). On the loop it stopped the beat, and a
lock or a slow read past 60 s read «wedged».

  seat          the slot's line read (`slots._run_batch`) - a slow one, the beat goes on and the claim names it
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import ingestion_worker as worker                         # noqa: E402
from chain import slots                                              # noqa: E402
from utils import heartbeat                                          # noqa: E402

SLOW = 0.6


def test_a_slow_line_read_keeps_the_slot_beating_and_names_its_step(monkeypatch):
    beats, seen_stage = [], []

    def slow_read(db, line=None, run=False):
        time.sleep(SLOW)
        seen_stage.extend(c["stage"] for c in heartbeat.open_claims() if c["name"] == worker.GROUP_BEAT)
        return []

    class Session:
        def rollback(self):
            pass

        def close(self):
            pass

    import database.database
    monkeypatch.setattr(database.database, "SessionLocal", Session)
    monkeypatch.setattr(worker, "reload_at_boundary", lambda who, seen: (False, seen))
    monkeypatch.setattr(worker, "pending_chain_events", slow_read)
    monkeypatch.setattr(heartbeat, "HEARTBEAT_SLICE_SECONDS", 0.05)
    real_beat = heartbeat.beat
    monkeypatch.setattr(heartbeat, "beat", lambda name, **k: beats.append((name, time.monotonic())) or
                        real_beat(name, **k))

    started = time.monotonic()
    outcome, _rules, _seen = asyncio.run(slots._run_batch("line-k", False, [], 0))
    assert outcome == slots.DRAINED
    during = [at for name, at in beats if name == worker.GROUP_BEAT and started + 0.1 < at < started + SLOW]
    assert len(during) >= 3, "the loop did not beat while the read ran: %d" % len(during)
    assert seen_stage == ["line read"], seen_stage
