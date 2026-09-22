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
from admin import retroactive                                              # noqa: E402


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
            started_ago=3600.0, progressed_ago=None, params='{"source": "lot_event"}',
            requested_by="kim", queued_ago=7200.0, runner=None):
    """A stand-in for one `RetroactiveRun`.

    ⚠️ IT HAS TO CARRY EVERY FIELD THE READER TOUCHES. A `SimpleNamespace` raises
    `AttributeError` for anything it was not given, so a column added to the real row and
    to `in_flight` kills this whole file - not one assertion, the import-time collection of
    every test in it. `runner` landed on 2026-09-06 and did exactly that: seven tests here
    died on a field none of them is about.

    🔴 `None` IS THE DEFAULT AND IS A REAL VALUE. Rows written before the column existed
    have no runner, and `in_flight` reports that as `None` rather than guessing - so the
    default here is the same "unknown", not a placeholder name that would make every test
    silently exercise the identified case.
    """
    now = datetime.now(timezone.utc)
    return types.SimpleNamespace(
        run_id="abc123", op=op, state=state,
        params=params, requested_by=requested_by,
        queued_at=(None if queued_ago is None
                   else now - timedelta(seconds=queued_ago)),
        started_at=now - timedelta(seconds=started_ago),
        last_progress_at=(None if progressed_ago is None
                          else now - timedelta(seconds=progressed_ago)),
        runner=runner,
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
def test_the_gate_never_opens_and_now_also_sees_other_processes(alive):
    """🔴 불변식은 그대로다 — 이 게이트는 «절대 더 열리지 않는다». 시간이 지났다고 여는 것은
    멎은 실행을 「같은 셀을 두 세션이 쓰는」 순서와 바꾸는 일이고, 그건 `start_retroactive_run`
    이 「나중에 아무도 설명 못 한다」고 적어 둔 바로 그것이다.

    🔴 바뀐 것은 «범위»다(2026-09-22). 종전엔 `_retroactive_thread` «하나»만 봤다 — 이 프로세스
       안의 손잡이다. 체인 리플레이가 워커로 가고 회수는 여기 남으므로, 게이트가 지키라고
       쓰인 그 쌍이 «프로세스 둘»에 놓인다. 손잡이만 보면 그 경우에 계속 「열림」이라 답한다.
    ⚠️ 그래서 «더 닫히는» 쪽으로만 바뀌었다. 이 시험이 지키는 불변식과 같은 방향이다.

    증인이 «둘»이고 서로를 못 덮는다:
       손잡이  행을 «못 쓴» 실행을 잡는다 (2026-09-05: `runner` 컬럼 이전 배포로 UPDATE 가
              전부 터져 행은 queued 인데 일은 돌고 있었다)
       표     «다른 프로세스»의 실행을 잡는다 — 손잡이로는 아예 안 보인다
    """
    from run_auto_update import MultiDiscoveryScheduler

    thread = types.SimpleNamespace(is_alive=lambda: alive)
    scheduler = types.SimpleNamespace(_retroactive_thread=thread,
                                      retroactive_moving_state=lambda: None)
    assert MultiDiscoveryScheduler.retroactive_busy(scheduler) is alive


def test_a_run_in_another_process_closes_the_gate_here():
    """🔴 이것이 이 라운드가 연 «구멍»이다. 손잡이는 죽어 있고 표가 「돌고 있다」고 말한다 —
    리플레이가 워커에서 돌고 회수가 여기서 시작되려는 정확히 그 순간이다.
    종전 코드는 여기서 「열림」이라 답했고, 두 작업이 같은 표의 같은 셀을 썼을 것이다.
    """
    from run_auto_update import MultiDiscoveryScheduler

    scheduler = types.SimpleNamespace(
        _retroactive_thread=types.SimpleNamespace(is_alive=lambda: False),
        retroactive_moving_state=lambda: {"run_id": "other-proc-1", "op": "chain_replay"})
    assert MultiDiscoveryScheduler.retroactive_busy(scheduler) is True


def test_the_gate_is_closed_for_a_stalled_run_exactly_as_for_a_moving_one():
    """Same thread, same answer, whatever the run is doing."""
    from run_auto_update import MultiDiscoveryScheduler

    scheduler = types.SimpleNamespace(
        _retroactive_thread=types.SimpleNamespace(is_alive=lambda: True),
        retroactive_moving_state=lambda: None)
    assert MultiDiscoveryScheduler.retroactive_busy(scheduler) is True


# ------------------------------------------- why it is running, not only that it is

def test_the_blocking_run_says_WHY_it_is_running():
    """🔴 THE QUEUE POINTS AT THIS ROW AS THE REASON EVERYTHING BEHIND IT WAITS, and an
    operator could not tell WHICH request was holding the line. The three facts have been
    on the runs list all along; the window that matters had none of them.
    """
    got = retroactive.in_flight(_Runs(run_row(progressed_ago=5.0)))
    assert got["params"] == {"source": "lot_event"}
    assert got["requested_by"] == "kim"
    assert got["queued_at"], got


def test_an_unnamed_requester_travels_as_null_not_as_a_display_word():
    """🔴 THE VALUE, NOT THE WORD. A display word chosen here would make this contract a
    second shape - every other field settled today (blocks_activation, partial_apply, the
    refusal codes, the four source states) carries a value and lets the screen write the
    sentence. And the two windows on this row must answer alike: `runs()` returns the
    column raw, so this does too."""
    got = retroactive.in_flight(_Runs(run_row(progressed_ago=5.0, requested_by=None)))
    assert got["requested_by"] is None


def test_an_absent_author_is_not_recorded_as_a_word_that_reads_like_a_person():
    """🔴 "admin" ANSWERS "who asked for this" with something nobody said, and it lands in
    the table where it outlives the request. The column is nullable; absent stays absent.
    ⚠️ Rows already carrying it are left alone - correcting them would be editing the
    record. Only what is written from here changes."""
    import inspect
    from database import models

    assert models.RetroactiveRun.__table__.c.requested_by.nullable is True


def test_the_two_windows_describe_one_row_with_the_same_names():
    """⛔ `runs()` and `in_flight` both show this row. Different spellings of the same
    three facts would let one window contradict the other."""
    got = retroactive.in_flight(_Runs(run_row(progressed_ago=5.0)))
    for field in ("run_id", "op", "params", "requested_by", "queued_at", "state"):
        assert field in got, field


# ---------------------------------------------------------------- 게이트 ⑯: 거절의 출구

def test_a_refusal_names_the_run_and_the_way_out(caplog, monkeypatch):
    """🔴 게이트가 «프로세스를 건너» 닫히므로, 막은 실행이 이 프로세스에 «없을 수» 있다.
    그러면 운영자가 여기서 「뭐가 도나」를 찾아도 아무것도 안 나온다 — 식별자와 푸는 법이
    «같은 줄»에 있어야 한다. 사유만 적힌 거절은 운영자를 «막힌 채로» 둔다.

    ⚠️ 억지로 만든 상황이다: 이 프로세스엔 도는 것이 «없고»(손잡이 죽음) 표만 말한다.
    """
    import logging

    from run_auto_update import MultiDiscoveryScheduler

    # ⚠️ 문장을 «짓는 곳»을 세운다 — 스케줄러 메서드가 아니라 `retroactive.gate_refusal` 이다.
    #    저자가 하나라서 워커가 내는 거절도 «같은 문장»이고, 이 시험은 그 저자를 잰다.
    monkeypatch.setattr(
        retroactive, "gate_refusal",
        lambda db: ("run_id=held-by-worker op=chain_replay moving for 12s "
                    "(runner=worker/7) — clear it with "
                    "POST /admin/retroactive/runs/held-by-worker/cancel"))
    scheduler = types.SimpleNamespace(
        _retroactive_thread=types.SimpleNamespace(is_alive=lambda: False),
        retroactive_moving_state=lambda: {"run_id": "held-by-worker"},
        retroactive_busy=lambda: True,
        _retroactive_last=None)

    with caplog.at_level(logging.WARNING):
        started = MultiDiscoveryScheduler.start_retroactive_run(
            scheduler, {"run_id": "mine-2", "op": "withdraw"})

    assert started is False
    line = "\n".join(r.getMessage() for r in caplog.records)

    # 무엇이 막나 — «식별자»로. 「소급이 돈다」만으로는 못 찾는다
    assert "held-by-worker" in line
    # 언제부터 — 수로
    assert "12" in line
    # 🔴 다음 행동 — 이것이 없으면 운영자는 막힌 채로 끝난다
    assert "/cancel" in line and "held-by-worker" in line.split("/cancel")[0]
    # 그리고 «내» 요청이 사라지지 않았다는 것도 말해야 한다
    assert "mine-2" in line
