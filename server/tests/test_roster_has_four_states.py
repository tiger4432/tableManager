# -*- coding: utf-8 -*-
"""A declared process has four states, and the fourth is the one that gets forgotten.

Twice on 2026-09-05 a list was written with three: declared-and-alive, declared-and-not,
and undeclared. The missing one is declared-and-not-yet - a process writes no heartbeat
file until its first beat, so every restart passes through a window with a declaration
and no heartbeat. Calling that "down" makes /health answer 503 on the most ordinary
operation there is, and an instrument that is red every restart is one nobody reads.

⛔ And an undeclared heartbeat is REPORTED, not hidden: graph at 21 days, ledger at 5 and
watcher at 9 are why this box is permanently unhealthy, and dropping them silently trades
a false alarm for a blind spot.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import health                                                    # noqa: E402
from utils import heartbeat                                      # noqa: E402

NOW = 1_000_000.0
GRACE = heartbeat.DEFAULT_STALE_AFTER_SEC


def test_declared_and_beating_is_running():
    out = health.roster_states({"chain": NOW - 500}, {"chain": {"stale": False, "age_seconds": 1}},
                               now=NOW)
    assert out["chain"]["state"] == health.ROSTER_RUNNING


def test_declared_with_no_beat_yet_is_starting_not_down():
    """🔴 THE STATE THAT WAS MISSING. Started a moment ago, no file written yet."""
    out = health.roster_states({"chain": NOW - 1}, {}, now=NOW)
    assert out["chain"]["state"] == health.ROSTER_STARTING
    assert out["chain"]["grace_seconds"] == GRACE


def test_declared_with_no_beat_long_after_start_is_down():
    out = health.roster_states({"chain": NOW - (GRACE + 60)}, {}, now=NOW)
    assert out["chain"]["state"] == health.ROSTER_DOWN


def test_a_stale_beat_is_down_even_inside_the_grace():
    """A beat that EXISTS and is stale is not a process that has yet to write one - it
    wrote one and stopped."""
    out = health.roster_states({"chain": NOW - 1},
                               {"chain": {"stale": True, "age_seconds": 9000}}, now=NOW)
    assert out["chain"]["state"] == health.ROSTER_DOWN


def test_a_roster_entry_with_no_start_time_is_not_called_down():
    """⚠️ It cannot be aged, so concluding "down" would be a guess."""
    out = health.roster_states({"chain": None}, {}, now=NOW)
    assert out["chain"]["state"] == health.ROSTER_STARTING
    assert out["chain"]["since_start_seconds"] is None


def test_an_undeclared_heartbeat_is_reported_not_dropped():
    out = health.roster_states({}, {"graph": {"stale": True, "age_seconds": 1_800_000}},
                               now=NOW)
    assert out["graph"]["state"] == health.ROSTER_OFF_ROSTER
    assert out["graph"]["age_seconds"] == 1_800_000


def test_the_grace_is_the_existing_threshold_not_a_new_one():
    """A second number here would be a second thing to tune, and this system already has
    one answer to "long enough that silence means something"."""
    out = health.roster_states({"chain": NOW - 1}, {}, now=NOW)
    assert out["chain"]["grace_seconds"] == heartbeat.DEFAULT_STALE_AFTER_SEC


def test_the_four_states_are_distinct_values():
    assert len({health.ROSTER_RUNNING, health.ROSTER_STARTING,
                health.ROSTER_DOWN, health.ROSTER_OFF_ROSTER}) == 4
