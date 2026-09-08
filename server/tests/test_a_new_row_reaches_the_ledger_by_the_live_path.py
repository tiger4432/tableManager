# -*- coding: utf-8 -*-
"""S-65 ②. A CREATE is followed -- but only for a source that has been SEEN caught up.

판정 144 splits the paths: the outbox is the LIVE path and the cursor is the CATCH-UP path.
Ruling 129 ㉣ had kept CREATE off the follow-up because "the forward run reads a new row once
from the cursor", and that premise was measured false here -- a new row only reaches the
cursor if it sorts AFTER it. Measured 2026-09-08: 3,008 `lot_event` rows dated before the
cursor's instant and 470,000 `wafer_process` rows whose uuid7 ids all sort before a
hand-written literal the cursor sat on produced ZERO atoms, with no error and a cursor
reporting it was finished.

⚰️ THE "ONLY FOR A CAUGHT-UP SOURCE" HALF WENT WITH THE CURSOR (판정 171). It existed to stop
the two paths doing the same work; there is one path now, so the question has one answer.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import followup                                          # noqa: E402


def test_create_is_followed_now():
    assert "CREATE" in followup.FOLLOWED_EVENT_TYPES
    assert followup.FOLLOWED_EVENT_TYPES == ("CREATE", "EDIT", "DELETE")


def test_a_create_is_queued_like_any_other_followed_event():
    """⚠️ AND THE CHAIN WORKER NEEDED NO CHANGE. Its seat already passes `event.event_type`
    straight through, so widening this tuple is the whole wiring -- worth asserting, because
    a future narrowing of the tuple would silently stop following creates."""
    followup.reset()
    try:
        assert followup.enqueue("dt_map", ["r1", "r2"], "CREATE") is True
        assert followup.queue_depth() == 1
    finally:
        followup.reset()


def test_an_unfollowed_type_is_still_refused():
    followup.reset()
    try:
        assert followup.enqueue("dt_map", ["r1"], "TRUNCATE") is False
        assert followup.queue_depth() == 0
    finally:
        followup.reset()



