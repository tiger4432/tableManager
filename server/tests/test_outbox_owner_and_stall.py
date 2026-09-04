# -*- coding: utf-8 -*-
"""Who empties a waiting outbox row, and whether a closed gate is moving.

WHAT HAPPENED, AND WHY BOTH HALVES ARE ONE FILE
------------------------------------------------
2026-09-04: one `RETROACTIVE_RUN` row sat in `database_outbox` with its age growing while
`/health` called the chain worker healthy. Two absences made that unreadable, and they
compound:

  * the queue instrument counts `processed_chain = false` rows and is called "the chain
    queue", so a row the SCHEDULER owns reads as the chain being behind;
  * the run behind it was neither finished nor moving, and nothing anywhere said so - a
    run that legitimately takes an hour and a run that stopped an hour ago are the same
    `running` row, the same closed gate, and the same silence.

🔴 THE STATE THIS ROUND FIXES CANNOT BE PRODUCED ON THE BOX THAT WROTE IT (measured by the
lead PM at 10:0x: outbox pending 0, both workers ok), so every case below is fed to the
judgement directly. Seeding a stuck run to observe one would be manufacturing the answer.
"""
import os
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                          # noqa: E402
import retroactive                                              # noqa: E402


# ----------------------------------------------------------------- who owns a row

def test_the_two_daemons_are_told_apart_by_the_set_not_by_a_literal():
    """`run_auto_update.py` watches exactly these two, and the instrument reads the same
    set. A copy in the instrument is how the two drift while neither is wrong at the time.
    """
    assert (event_constants.outbox_owner(event_constants.EVENT_RETROACTIVE_RUN)
            == event_constants.OUTBOX_OWNER_SCHEDULER)
    assert (event_constants.outbox_owner(event_constants.EVENT_SCHEDULER_RUN_NOW)
            == event_constants.OUTBOX_OWNER_SCHEDULER)
    for data_event in ("CREATE", "EDIT", "DELETE"):
        assert (event_constants.outbox_owner(data_event)
                == event_constants.OUTBOX_OWNER_CHAIN), data_event


@pytest.mark.parametrize("event_type", ["SYSTEM_RELOAD", "SOMETHING_ADDED_LATER", "", None])
def test_an_untraced_event_type_is_unknown_and_is_NOT_folded_into_chain(event_type):
    """🔴 THE GUARD. "assume chain" is the misreading this split exists to end, and it
    would be invisible: the row would simply be added to the chain's depth, exactly as it
    was on 2026-09-04.

    `SYSTEM_RELOAD` is here on purpose. The chain worker marks the LATEST one on a
    throttled branch of its own, so its fate depends on WHICH row it is rather than on its
    type - and a per-type owner cannot say that. Unknown is the true answer.
    """
    assert (event_constants.outbox_owner(event_type)
            == event_constants.OUTBOX_OWNER_UNKNOWN)


# ------------------------------------------------- is the closed gate still moving

class _Runs:
    """A `retroactive_runs` table holding one row, however the query is chained."""

    def __init__(self, row):
        self.row = row

    def query(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        return self.row


def run_row(op="ledger_backfill", state=retroactive.RUN_RUNNING,
            started_ago=3600.0, progressed_ago=None):
    now = datetime.now(timezone.utc)
    return types.SimpleNamespace(
        run_id="abc123", op=op, state=state,
        started_at=now - timedelta(seconds=started_ago),
        last_progress_at=(None if progressed_ago is None
                          else now - timedelta(seconds=progressed_ago)),
        processed_rows=10, total_rows=None)


def test_a_run_that_reported_recently_is_progressing():
    got = retroactive.in_flight(_Runs(run_row(progressed_ago=5.0)))
    assert got["moving"] == retroactive.MOVING_PROGRESSING
    assert got["cancel_reaches"] == retroactive.CANCEL_AT_NEXT_BATCH


def test_a_run_that_reported_and_then_stopped_is_stalled():
    """It got past a batch boundary once, so silence since then is a fault and not just
    an operation that does not report."""
    got = retroactive.in_flight(_Runs(run_row(started_ago=7200.0, progressed_ago=3600.0)))
    assert got["moving"] == retroactive.MOVING_STALLED
    assert got["no_progress_seconds"] >= 3600.0
    assert got["cancel_reaches"] == retroactive.CANCEL_UNKNOWN, (
        "cancel is cooperative and only lands at a batch boundary; a run stopped inside "
        "one never reaches the place that reads the flag")


def test_a_run_that_has_never_reported_is_unreported_and_NOT_called_stalled():
    """🔴 `_mark_run(started=True)` stamps `last_progress_at` AT THE START, so an old
    stamp alone proves nothing - and two of the six registered operations
    (`ledger_rescope`, `enrichment_confirm`, measured 2026-09-04) never pass a
    `_checkpoint` hook, so they never report while they run. Calling their silence a
    stall would name a fault nobody established."""
    row = run_row(op="ledger_rescope", started_ago=7200.0)
    row.last_progress_at = row.started_at                 # stamped once, never advanced
    got = retroactive.in_flight(_Runs(row))
    assert got["moving"] == retroactive.MOVING_UNREPORTED
    assert got["cancel_reaches"] == retroactive.CANCEL_NEVER, (
        "this operation declares cancellable: False - it has no batch boundary to offer")


def test_a_cancel_already_requested_is_still_in_flight():
    """The thread is still alive, so the gate is still closed. Reporting nothing here
    would say the queue is waiting for no reason."""
    got = retroactive.in_flight(
        _Runs(run_row(state=retroactive.RUN_CANCEL_REQUESTED,
                      started_ago=7200.0, progressed_ago=3600.0)))
    assert got is not None and got["state"] == retroactive.RUN_CANCEL_REQUESTED
    assert got["moving"] == retroactive.MOVING_STALLED
    # 🔴 asserted on the QUERY'S OWN set, not through the stub: a stub that answers every
    # `filter()` the same way cannot tell whether this state is selected, and a test that
    # cannot tell would stay green while the state was dropped.
    assert retroactive.RUN_CANCEL_REQUESTED in retroactive.IN_FLIGHT_STATES, (
        "asking a run to stop does not stop it - the gate stays shut until it reaches a "
        "batch boundary, so this state is still in flight")


def test_no_run_in_flight_is_None_rather_than_an_invented_row():
    assert retroactive.in_flight(_Runs(None)) is None


# ------------------------------------------------------------------ the gate itself

@pytest.mark.parametrize("alive", [True, False])
def test_the_gate_answers_only_alive_and_that_is_deliberate(alive):
    """🔴 THE ROUND FAILS IF THIS CHANGES. Opening the gate after a timeout would trade a
    stuck run for two concurrent replays writing the same cells from two sessions - the
    one ordering `start_retroactive_run` says nobody could reason about afterwards. The
    diagnosis above changes what is SAID, never what is allowed."""
    from run_auto_update import MultiDiscoveryScheduler

    thread = types.SimpleNamespace(is_alive=lambda: alive)
    scheduler = types.SimpleNamespace(_retroactive_thread=thread)
    assert MultiDiscoveryScheduler.retroactive_busy(scheduler) is alive


def test_the_gate_is_closed_for_a_stalled_run_exactly_as_for_a_moving_one():
    """Same thread, same answer, whatever the run is doing."""
    from run_auto_update import MultiDiscoveryScheduler

    scheduler = types.SimpleNamespace(
        _retroactive_thread=types.SimpleNamespace(is_alive=lambda: True))
    assert MultiDiscoveryScheduler.retroactive_busy(scheduler) is True
