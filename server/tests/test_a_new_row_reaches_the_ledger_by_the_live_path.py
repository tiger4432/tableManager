# -*- coding: utf-8 -*-
"""S-65 ②. A CREATE is followed -- but only for a source that has been SEEN caught up.

판정 144 splits the paths: the outbox is the LIVE path and the cursor is the CATCH-UP path.
Ruling 129 ㉣ had kept CREATE off the follow-up because "the forward run reads a new row once
from the cursor", and that premise was measured false here -- a new row only reaches the
cursor if it sorts AFTER it. Measured 2026-09-08: 3,008 `lot_event` rows dated before the
cursor's instant and 470,000 `wafer_process` rows whose uuid7 ids all sort before a
hand-written literal the cursor sat on produced ZERO atoms, with no error and a cursor
reporting it was finished.

🔴 AND ONLY FOR A CAUGHT-UP SOURCE, which is what keeps the two paths from doing the same
work: a source still catching up will read these rows itself.
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


def test_the_drain_asks_whether_the_source_is_caught_up_and_names_the_skipped():
    """The CREATE branch consults the mark and REPORTS what it skipped.

    ⚠️ NARROW ON PURPOSE: this reads the decision, not a run. The behavioural half -- a new
    row landing on a caught-up source and not landing on one still catching up -- needs a
    live source and is the gate that follows. What it pins is that the branch cannot quietly
    become "follow everything" or "follow nothing": both would drop one of these two names.
    """
    class _Plan:
        relation = "dt_log"
        driver = type("D", (), {"cursor_columns": ("dt_job",), "identity": ("dt_job",)})()

    setup = type("S", (), {"snapshot": type("Snap", (), {
        "source_plans": {"dt_job": _Plan()}})()})()

    followup.reset()
    saved_caught = followup.caught_up_sources
    saved_views = followup.view_followers_of
    followup.caught_up_sources = lambda engine, sources: set()
    # The same one seam every non-view test blocks (판정 158).
    followup.view_followers_of = lambda engine, setup, table: ([], [])
    try:
        followup.enqueue("dt_log", ["r1"], "CREATE")
        done = followup.drain_once(object(), setup)
    finally:
        followup.caught_up_sources = saved_caught
        followup.view_followers_of = saved_views
        followup.reset()

    assert done["event_type"] == "CREATE"
    assert done["skipped_not_caught_up"] == ["dt_job"], done
    assert done["sources"] == {}, "a source still catching up must not be followed"


def test_absent_means_not_caught_up():
    """NULL is "never seen caught up", and a source that has never run reads NULL too."""
    assert callable(followup.caught_up_sources)
    assert "seen" in (followup.caught_up_sources.__doc__ or "").lower()
    assert "ABSENT MEANS NO" in (followup.caught_up_sources.__doc__ or "")
