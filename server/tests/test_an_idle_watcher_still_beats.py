# -*- coding: utf-8 -*-
"""S-142 ①. The integrated watcher beats while it waits, not only when it works.

Found by `/runtime` the day it landed: on a healthy box the route published
`watcher alive: false`. In integrated mode the periodic sweep thread is the watcher's only
always-running loop, and it beat nothing — an idle deployment therefore had no watcher
heartbeat at all, and `/health` and `/runtime` both said so.

🔴 BEATING ONCE PER SWEEP WOULD NOT HAVE FIXED IT, AND THAT IS THE POINT OF THIS FILE.
The sweep runs every 300 s; `heartbeat.DEFAULT_STALE_AFTER_SEC` is 60. A beat per sweep
reads stale for 240 of every 300 seconds — the same red light, now with a mechanism behind
it and a commit message claiming it was fixed. The wait is sliced instead, at a cadence
DERIVED from the staleness threshold so the two cannot drift apart.

⚠️ AND THE SWEEP'S OWN SCHEDULE DOES NOT MOVE. An operator who timed it at five minutes
still times it at five minutes; only the waiting is subdivided.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
parsers_dir = os.path.join(server_dir, "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

import directory_watcher as dw                                       # noqa: E402
from utils import heartbeat                                          # noqa: E402


class _Stop:
    """`threading.Event`'s two methods this loop uses, with the waits recorded."""

    def __init__(self, stop_after):
        self.waits = []
        self._left = stop_after

    def wait(self, seconds):
        self.waits.append(seconds)
        self._left -= 1
        return self._left <= 0          # True = stopping


class _Loop:
    """The real `_periodic_sweep_loop`, bound to a stand-in that records."""

    def __init__(self, stop_after):
        self._stop_event = _Stop(stop_after)
        self.sweeps = []

    def _sweep_safely(self, arg, reason):
        self.sweeps.append(reason)

    run = dw.WorkspaceWatcher._periodic_sweep_loop


@pytest.fixture(name="beats")
def fixture_beats(monkeypatch):
    seen = []
    monkeypatch.setattr(dw.heartbeat, "beat",
                        lambda name, **kw: seen.append(name) or True)
    return seen


# ---------------------------------------------------------------------------
# 1. The defect: an idle loop that says nothing
# ---------------------------------------------------------------------------

def test_the_loop_beats_while_it_waits(beats):
    """KILLS: a loop that beats only after a sweep. Three slices, three beats, and the
    sweep has not come round yet."""
    loop = _Loop(stop_after=4)
    loop.run()

    assert beats == [dw.HEARTBEAT_NAME] * 3
    assert loop.sweeps == [], "no sweep is due yet - only the waiting happened"


def test_the_beat_is_frequent_enough_to_read_as_alive():
    """🔴 THE NUMBER THAT MAKES THE FIX A FIX. A beat slower than the staleness window is
    a beat that publishes `stale` between beats, which is what the route was already
    showing."""
    assert dw.HEARTBEAT_SLICE_SECONDS < heartbeat.DEFAULT_STALE_AFTER_SEC
    # DERIVED, not typed: raising the staleness window must widen this on its own.
    assert dw.HEARTBEAT_SLICE_SECONDS == max(
        1.0, heartbeat.DEFAULT_STALE_AFTER_SEC / 3.0)


def test_one_beat_per_sweep_would_not_have_been_enough():
    """The rejected fix, scored rather than described: at 300 s between beats the watcher
    spends most of its life stale."""
    assert dw.PERIODIC_SWEEP_INTERVAL_SECONDS > heartbeat.DEFAULT_STALE_AFTER_SEC * 4


# ---------------------------------------------------------------------------
# 2. What must not have changed: the sweep's own schedule
# ---------------------------------------------------------------------------

def test_the_sweep_still_fires_on_its_own_interval(beats):
    """The slices add up to exactly the interval, so a five-minute sweep is still five
    minutes. Counted rather than asserted from the constant, because the arithmetic is
    the thing that could go wrong."""
    per_sweep = int(dw.PERIODIC_SWEEP_INTERVAL_SECONDS // dw.HEARTBEAT_SLICE_SECONDS)
    loop = _Loop(stop_after=per_sweep + 1)
    loop.run()

    assert loop.sweeps == ["periodic"], loop.sweeps
    assert sum(loop._stop_event.waits[:per_sweep]) == pytest.approx(
        dw.PERIODIC_SWEEP_INTERVAL_SECONDS)


def test_a_stop_is_honoured_inside_a_slice(beats):
    """⛔ THE SHUTDOWN MUST NOT WAIT OUT THE SWEEP. Slicing the wait is what makes a stop
    land within one slice instead of within five minutes - the opposite failure would be a
    process that takes 300 s to die."""
    loop = _Loop(stop_after=1)
    loop.run()

    assert beats == [], "it stopped during the first slice, before any beat"
    assert loop.sweeps == []
    assert loop._stop_event.waits == [dw.HEARTBEAT_SLICE_SECONDS]


def test_the_loop_never_waits_a_negative_slice(beats):
    """Arithmetic guard: the last slice before a sweep is the remainder, and a remainder
    that went negative would make `Event.wait` raise."""
    loop = _Loop(stop_after=int(
        dw.PERIODIC_SWEEP_INTERVAL_SECONDS // dw.HEARTBEAT_SLICE_SECONDS) + 3)
    loop.run()
    assert all(w >= 0 for w in loop._stop_event.waits), loop._stop_event.waits
