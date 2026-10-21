# -*- coding: utf-8 -*-
"""총괄 4ee0a1946 (B 2af64170d): an API that takes no notification held a chain slot ~100 s - a batch's 50 map
messages, one refused connection ~2 s each, sent one after another after the commit while the table's next line
waited. Both senders (a batch's `_dispatch_broadcasts`, the undelivered sweep) stop at their first refusal and ask
one judgement (`api_took`); what they did not send stays undelivered for the next sweep. The line is said when the
API stops taking them and when it takes them again - not per refusal.
"""
import logging

import pytest

from chain import ingestion_worker as ciw
from test_broadcast_recovery import RULES, FakeDB, FakeRow


def _posts(monkeypatch, answers):
    """`answers` is what the API says, one per post, the last repeated."""
    posted = []

    async def fake_post(endpoint, payload):
        posted.append(payload)
        return answers[min(len(posted), len(answers)) - 1]

    monkeypatch.setattr(ciw, "post_event_async", fake_post)
    return posted


@pytest.fixture(autouse=True)
def _api_took_the_last_one(monkeypatch):
    monkeypatch.setattr(ciw, "_API_TAKES", [True])


def _said(caplog):
    return [r.getMessage() for r in caplog.records if "notifications " in r.getMessage()]


@pytest.mark.anyio
async def test_a_batch_stops_at_its_first_refusal_and_leaves_its_rows_unstamped(monkeypatch, caplog):
    stamped = []
    monkeypatch.setattr(ciw, "_stamp_broadcast_at_sync", lambda factory, ids: stamped.append(list(ids)))
    batch = [([1, 2], ["m1", "m2", "m3"], None), ([3], ["m4", "m5"], None)]

    posted = _posts(monkeypatch, [False])
    with caplog.at_level(logging.INFO):
        await ciw._dispatch_broadcasts(batch, None)
    assert (posted, stamped) == (["m1"], []), "a refused API was asked again, or a group read as delivered"
    assert len(_said(caplog)) == 1 and "3 waiting, next try in 5 s" in _said(caplog)[0]

    posted = _posts(monkeypatch, [False])
    caplog.clear()
    with caplog.at_level(logging.INFO):
        await ciw._dispatch_broadcasts(batch, None)
    assert posted == ["m1"] and _said(caplog) == [], "said again while nothing changed"

    posted = _posts(monkeypatch, [True])
    with caplog.at_level(logging.INFO):
        await ciw._dispatch_broadcasts(batch, None)
    assert posted == ["m1", "m2", "m3", "m4", "m5"] and stamped == [[1, 2], [3]]
    assert "delivered again" in _said(caplog)[-1]


@pytest.mark.anyio
async def test_a_sweep_stops_at_its_first_refusal(monkeypatch):
    rows = [FakeRow(1, "standalone_a", tx="t1"), FakeRow(2, "standalone_b", tx="t2"), FakeRow(3, "tblA_src", tx="t3")]
    db = FakeDB(rows)

    posted = _posts(monkeypatch, [False])
    await ciw.sweep_undelivered_broadcasts(db, RULES, lambda: FakeDB([]))
    assert len(posted) == 1 and all(r.broadcast_at is None for r in rows)

    posted = _posts(monkeypatch, [True])
    await ciw.sweep_undelivered_broadcasts(db, RULES, lambda: FakeDB([]))
    assert len(posted) == 4, "canary: the sweep refreshes four tables (three sources and the chain target)"
    assert all(r.broadcast_at is not None for r in rows)
