# -*- coding: utf-8 -*-
"""A collector backfill says where the next run picks up (총괄 3a1446982, 소유자 「오토 업데이트
백필 커서가 없는듯? 다시 돌리니 처음부터 다시 도네」 -> ㄱ: the Start box is prefilled).

🔴 THE LAST WINDOW OF A RUN THAT REACHED THE END IS CUT AT ITS «NOW», so start + days is
tomorrow's midnight - in the future, which the judge refuses. Done and cancelled runs write
`done_until`; a failed run writes no result, and its finished days (one progress per day)
name the failed day. Whatever the answer, running again from it leaves no gap and no overlap.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

import collector_markers as cm
from admin import retroactive
from database import models
from ingestion import checkpoint
from test_a_collector_is_backfilled_day_by_day import (  # noqa: F401 - the fixture is used
    DB, KEY, KST, Control, fixture_workspace, ingests)

START = "2026-09-25"
NOW = datetime(2026, 9, 29, 13, 5, 42, 654321, tzinfo=KST)
LATER = NOW + timedelta(days=3)


@pytest.fixture(autouse=True)
def _now(monkeypatch):
    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW
    monkeypatch.setattr(cm, "datetime", Fixed)


def _run(control):
    return retroactive._run_collector_backfill(DB, {"collector": KEY, "start": START},
                                               lambda m: None, control)


def _next(state, result=None, processed=None):
    return retroactive._collector_backfill_next_start({
        "op": "collector_backfill", "state": state, "params": {"collector": KEY, "start": START},
        "result": result, "processed_rows": processed})


def _windows(start_text, now):
    return cm.backfill_windows(cm.backfill_start(start_text), now=now)


def _no_gap_no_overlap(done_windows, next_start):
    """The windows run so far, then the windows from `next_start` - end to end, once each."""
    whole = done_windows + _windows(next_start, LATER)
    assert all(a[1] == b[0] for a, b in zip(whole, whole[1:])), "a gap or an overlap"
    assert whole[0][0] == cm.backfill_start(START) and whole[-1][1] == LATER.replace(microsecond=0)


def test_a_run_that_reached_the_end_picks_up_where_its_last_window_was_cut(workspace, monkeypatch):
    ingests(monkeypatch, [])
    windows = _windows(START, NOW)
    assert len(windows) == 5 and windows[-1][1] < windows[-1][0] + cm.BACKFILL_SLICE

    stats = _run(Control())

    assert stats["done_until"] == "2026-09-29 13:05:42"
    assert _next(retroactive.RUN_DONE, stats, 5) == "2026-09-29 13:05:42"
    _no_gap_no_overlap(windows, _next(retroactive.RUN_DONE, stats, 5))


def test_a_run_cancelled_after_two_days_picks_up_at_the_third_days_midnight(workspace, monkeypatch):
    ingests(monkeypatch, [])

    stats = _run(Control(stop_after_days=2))

    assert _next(retroactive.RUN_CANCELLED, stats, 2) == "2026-09-27"
    _no_gap_no_overlap(_windows(START, NOW)[:2], "2026-09-27")


def test_a_run_that_failed_on_the_third_day_picks_up_at_that_day(workspace, monkeypatch):
    ingests(monkeypatch, [checkpoint.STATUS_DONE, checkpoint.STATUS_DONE, checkpoint.STATUS_FAILED])
    control = Control()

    with pytest.raises(retroactive.RetroactiveRefused):
        _run(control)

    processed = max(p for p, _t in control.progressed if p is not None)
    assert processed == 2
    assert _next(retroactive.RUN_FAILED, None, processed) == "2026-09-27"
    _no_gap_no_overlap(_windows(START, NOW)[:2], "2026-09-27")


def test_no_day_done_picks_up_at_the_start_as_written(workspace, monkeypatch):
    ingests(monkeypatch, [checkpoint.STATUS_FAILED])
    control = Control()
    with pytest.raises(retroactive.RetroactiveRefused):
        _run(control)

    assert _next(retroactive.RUN_FAILED, None, 0) == START
    assert _next(retroactive.RUN_FAILED, None, None) == START


@pytest.mark.parametrize("state", ["queued", "running", "cancel_requested"])
def test_a_run_still_going_has_nothing_to_pick_up(state):
    assert _next(state, {"done_until": "2026-09-27"}, 2) is None


def test_a_finished_record_from_before_done_until_does_not_guess():
    """Where its last window was cut is not written, and start + days would be a guess."""
    assert _next(retroactive.RUN_DONE, {"days": 5, "days_done": 5}, 5) is None


def test_the_result_line_names_where_it_got_to():
    assert retroactive.run_result_sentence(
        {"days": 5, "days_done": 2, "done_until": "2026-09-27"}) == (
        "days in the window 5 · days collected 2 · collected up to (KST) 2026-09-27")


def test_the_runs_list_carries_it(db_session):
    """On the response the admin already reads - null for an operation with no such idea."""
    def add(run_id, op, state, result=None, processed=None, minutes=0):
        db_session.add(models.RetroactiveRun(
            run_id=run_id, op=op, state=state, processed_rows=processed,
            params=json.dumps({"collector": KEY, "start": START}),
            result=json.dumps(result) if result else None,
            queued_at=datetime(2026, 9, 29, tzinfo=timezone.utc) + timedelta(minutes=minutes)))
    add("r_failed", "collector_backfill", retroactive.RUN_FAILED, processed=2, minutes=1)
    add("r_done", "collector_backfill", retroactive.RUN_DONE,
        {"days": 5, "days_done": 5, "done_until": "2026-09-29 13:05:42"}, 5, minutes=2)
    add("r_other", "ledger_backfill", retroactive.RUN_DONE, {"inserted": 1}, 1, minutes=3)
    db_session.commit()

    by_id = {run["run_id"]: run["next_start"] for run in retroactive.runs(db_session)}

    assert by_id["r_failed"] == "2026-09-27"
    assert by_id["r_done"] == "2026-09-29 13:05:42"
    assert by_id["r_other"] is None
