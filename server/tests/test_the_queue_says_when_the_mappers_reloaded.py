# -*- coding: utf-8 -*-
"""The answer to "does a restart clear this?" existed and could not leave the process.

`QueueHeadWatch` has recorded the instant a SYSTEM_RELOAD re-imported the mapper modules
since the stall watcher landed. It leaves as TEXT inside one sentence -- "last mapper
reload 42s" -- and only after the queue head has already been stuck for a minute. So the
one question it answers ("is the state in this process, in the module cache, rather than
in the data?") could be asked only by someone already reading the log of an already
stalled system.

Nothing here MEASURES anything new. The registry the queue view already reads records the
same instant, and the route publishes it as a number beside the depth.

⚠️ NEVER-RELOADED IS `None`, NOT `0`. `0` reads as "just now", which is the opposite fact,
and the loop starting is not a reload -- so uptime and reload age are two values, not one.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import activity                                            # noqa: E402


@pytest.fixture(autouse=True)
def clean_registry():
    activity.registry.clear()
    yield
    activity.registry.clear()


def test_a_process_that_never_reloaded_says_none_rather_than_zero():
    """🔴 THE WHOLE POINT OF TWO FIELDS. A loop that has been up for an hour and never
    reloaded is not a loop that reloaded an hour ago."""
    activity.registry.attach()
    ages = activity.registry.ages()
    assert ages["mapper_reload_age_seconds"] is None
    assert ages["loop_uptime_seconds"] is not None


def test_a_loop_that_never_started_reports_neither():
    ages = activity.registry.ages()
    assert ages["loop_uptime_seconds"] is None
    assert ages["mapper_reload_age_seconds"] is None


def test_the_reload_age_starts_counting_when_the_reload_is_noted():
    activity.registry.attach()
    activity.registry.note_reload()
    first = activity.registry.ages()["mapper_reload_age_seconds"]
    assert first is not None and first < 5
    time.sleep(0.01)
    assert activity.registry.ages()["mapper_reload_age_seconds"] >= first


def test_the_two_ages_are_independent():
    """Attaching does not stamp a reload, and reloading does not restart the uptime --
    which is what makes "a restart clears it" answerable from the pair."""
    activity.registry.attach()
    attached_first = activity.registry.ages()["loop_uptime_seconds"]
    time.sleep(0.01)
    activity.registry.note_reload()
    after = activity.registry.ages()
    assert after["loop_uptime_seconds"] >= attached_first
    assert after["mapper_reload_age_seconds"] < after["loop_uptime_seconds"]


def test_clear_forgets_both():
    activity.registry.attach()
    activity.registry.note_reload()
    activity.registry.clear()
    # [P-6] The purge names joined this dict. The equality is kept EXACT rather than
    # relaxed to a subset: this assertion's job is to notice a field arriving or
    # leaving, and a subset check would stop doing that in both directions.
    assert activity.registry.ages() == {"loop_uptime_seconds": None,
                                              "mapper_reload_age_seconds": None,
                                              "outbox_purge_age_seconds": None,
                                              "outbox_purge_deleted": None,
                                              "outbox_purge_capped": None}


# ------------------------------------------------------------------- the seam, both ways

def test_the_loop_notes_the_reload_on_the_registry_the_route_reads():
    """🔴 THE SEAM. `QueueHeadWatch` keeping its own copy is fine; the defect was that it
    kept the ONLY copy. Both calls have to sit at the reload site or this lands the value
    somewhere the route still cannot see."""
    import inspect

    from chain import ingestion_worker as worker

    body = inspect.getsource(worker.start_chain_ingestion_worker)
    assert "head_watch.note_reload()" in body
    assert "activity.registry.note_reload()" in body, (
        "the reload is recorded only where the queue view cannot read it again")


def test_the_route_publishes_both_names():
    """The route spreads `ages()`, so a field added there arrives without a second author
    -- and a field REMOVED there disappears from the response with no test noticing. This
    pins the two names the screen reads."""
    import inspect

    import main

    body = inspect.getsource(main.get_chain_queue_depth)
    assert "activity.registry.ages()" in body
    assert set(activity.registry.ages()) == {"loop_uptime_seconds",
                                                   "mapper_reload_age_seconds",
                                                   "outbox_purge_age_seconds",
                                                   "outbox_purge_deleted",
                                                   "outbox_purge_capped"}
