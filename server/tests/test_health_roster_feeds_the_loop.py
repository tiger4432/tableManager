# -*- coding: utf-8 -*-
"""/health judges the processes the launcher declared, and knows when one is starting.

Two defects, one cause. The expected-workers list fell back to "every heartbeat file on
disk", so anything that ever ran stayed on the roll - a graph worker retired weeks ago is
why this box reads permanently unhealthy. And the loop's "starting" branch, which already
existed with its own grace, tests `uptime` from the supervisor's child record: with no
supervisor there is no cinfo, so a process that has merely not written its first beat yet
falls through to "missing" and UNHEALTHY. Every restart answered 503 for that window.

⛔ NO SECOND JUDGE. An earlier attempt added a classifier beside this loop; the loop
already answers the same question in more detail (wedged, foreign_beat, unknown), so the
classifier was removed and the loop is fed the material it was missing instead.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import health                                                    # noqa: E402
from utils import heartbeat                                      # noqa: E402


def workers_of(monkeypatch, roster, beats):
    """The real decision table, called directly - it is pure, which is why it can be.

    The supervisor is empty on purpose: a box with no supervisor is the case that was
    broken, because that is when `cinfo` is None and the "starting" branch went dark.
    """
    monkeypatch.setattr(heartbeat, "read_roster", lambda: roster)
    payload, _status = health.compute_health(
        {"status": health.STATUS_OK}, beats, {}, {"status": health.STATUS_OK},
        heartbeat.DEFAULT_STALE_AFTER_SEC)
    return payload["checks"]["workers"]


def test_only_declared_processes_are_expected(monkeypatch):
    """🔴 The retired worker no longer decides whether the box is healthy."""
    w = workers_of(monkeypatch, {"chain": None},
                   {"chain": {"stale": False, "age_seconds": 1, "beats": 9},
                    "graph": {"stale": True, "age_seconds": 1_800_000, "beats": 162}})
    assert w["chain"]["status"] == health.STATUS_OK
    assert w["graph"]["status"] == "off_roster"


def test_an_off_roster_heartbeat_is_named_not_dropped(monkeypatch):
    """⛔ Hiding it would trade a false alarm for a blind spot - the file is still there."""
    w = workers_of(monkeypatch, {"chain": None},
                   {"chain": {"stale": False, "age_seconds": 1},
                    "ledger": {"stale": True, "age_seconds": 455_000}})
    assert w["ledger"]["age_seconds"] == 455_000
    assert "no launcher roster" in w["ledger"]["detail"]


def test_a_just_started_process_is_starting_not_missing(monkeypatch):
    """🔴 THE RESTART 503. Declared, started a moment ago, no beat written yet."""
    import time
    w = workers_of(monkeypatch, {"chain": time.time() - 2}, {})
    assert w["chain"]["status"] == "starting"


def test_a_long_declared_process_with_no_beat_is_still_missing(monkeypatch):
    """The grace must not swallow the real failure it sits next to."""
    import time
    w = workers_of(monkeypatch, {"chain": time.time() - (health.STARTUP_GRACE_SEC + 60)}, {})
    assert w["chain"]["status"] == "missing"


def test_an_empty_roster_still_reports_what_it_can_see(monkeypatch):
    """⚠️ "Nobody published a roster" is not "nothing should be running". A box whose
    launcher predates this must not go quiet."""
    w = workers_of(monkeypatch, {}, {"chain": {"stale": False, "age_seconds": 1}})
    assert "chain" in w and w["chain"]["status"] == health.STATUS_OK


def test_the_classifier_is_gone():
    """One judgement, one place. The loop above answers this in more detail."""
    assert not hasattr(health, "roster_states"), \
        "a second judge is back beside the loop that already decides this"
