# -*- coding: utf-8 -*-
"""One unhandleable retroactive request must not hold every later one behind it.

⚠️ 예시 op 이 `withdraw` 인 이유(2026-09-23): 이 파일의 주제는 «머리 막힘»이지 어느 op 이
   아니다. 종전엔 `chain_replay` 를 예로 썼는데 그것이 «이 데몬의 일이 아니게» 됐다 —
   체인 워커가 작업 표에서 직접 집는다. 스케줄러를 안 지나는 op 으로 이 기제를 재면
   재는 대상이 아니라 «건너뛰는 갈래»를 재게 된다.

Owner, 2026-09-04, with production stopped: "nothing works because of retro", "another
replay does not get picked up either", and a restart did not help.

The mechanism: the scheduler takes the OLDEST unprocessed RETROACTIVE_RUN row each tick
(`order_by(id.asc()).first()`). The row is only marked processed when the run STARTS, so a
row whose payload cannot be handled threw, was logged, and stayed - first in line, for
ever. Every later request sat behind it, `retry_count` never moved, and both workers
looked healthy. The board's C-4 predicted this exact shape.

🔴 MARKING IT FINISHED IS NOT A NEW POLICY. Ten lines above, this path already chose
at-most-once, because "a run that silently repeats is worse than one an operator has to
press twice" - and retrying for ever a request that cannot even be parsed is the opposite
of that decision.

⛔ Skipping to the next row would have been the other tempting fix, and it is the defect
this whole day was about: the row would wait for ever and the queue would count one that
nobody will ever take.
"""
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import models                                      # noqa: E402


class _Row:
    def __init__(self, id, payload):
        self.id, self.payload = id, payload
        self.processed_chain = False
        self.status = "PENDING"
        self.event_type = "RETROACTIVE_RUN"


class _Session:
    """A session over a list of rows, answering the scheduler's own query shape."""

    def __init__(self, rows):
        self.rows, self.commits = rows, 0

    # -- query chain -------------------------------------------------------
    def query(self, *a, **k):
        self._kind = a[0] if a else None
        return self

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        pending = [r for r in self.rows if not r.processed_chain]
        return pending[0] if pending else None

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


def one_tick(scheduler, session):
    """🔴 DRIVES THE PRODUCT'S OWN METHOD, not a copy of it.

    The first version of this file re-implemented the block and would have stayed green
    with the fix reverted - the exact failure this repository hit twice today. The block
    was therefore extracted from the loop so a test could reach it; `run()` now calls the
    same method.
    """
    scheduler.handle_retroactive_trigger(session)


@pytest.fixture
def scheduler(tmp_path):
    """A real scheduler with only the two things this block calls stubbed: whether a run
    is in flight, and starting one. Everything else is the product's."""
    from run_auto_update import MultiDiscoveryScheduler

    s = MultiDiscoveryScheduler(check_interval=5, server_dir=str(tmp_path))
    s.started = []
    s.retroactive_busy = lambda: False
    s.start_retroactive_run = lambda payload: (s.started.append(payload) or True)
    return s


def test_a_request_that_cannot_be_handled_is_finished_rather_than_re_picked(scheduler):
    """🔴 GATE 1. It threw, so it is over - and it says so in the row, not only in a log."""
    bad = _Row(1, "{not json")
    session = _Session([bad])
    one_tick(scheduler, session)
    assert bad.processed_chain is True
    assert bad.status == "FAILED"


def test_the_request_BEHIND_it_runs_on_the_next_tick(scheduler):
    """🔴 GATE 2, AND THE ONE THAT RESTARTS PRODUCTION. Before this, the second row was
    never reached at all - not on the next tick, not after a restart."""
    bad, good = _Row(1, "{not json"), _Row(2, json.dumps({"op": "withdraw",
                                                          "run_id": "abc"}))
    session = _Session([bad, good])

    one_tick(scheduler, session)          # the bad one is finished
    assert scheduler.started == []
    one_tick(scheduler, session)          # the next tick reaches the good one
    assert [p["run_id"] for p in scheduler.started] == ["abc"]
    assert good.processed_chain is True


def test_an_ordinary_request_is_untouched(scheduler):
    """A request that starts is finished as SUCCESS, with the time - not FAILED, and not
    left PENDING beside the flag (총괄 3c3f2b1f2: it read 「done · unexpected_status」)."""
    good = _Row(1, json.dumps({"op": "withdraw", "run_id": "xyz"}))
    session = _Session([good])
    one_tick(scheduler, session)
    assert good.processed_chain is True
    assert good.status == "SUCCESS"
    assert getattr(good, "processed_at", None) is not None
    assert scheduler.started[0]["run_id"] == "xyz"


def test_a_refused_start_still_leaves_the_row_for_later(scheduler):
    """⚠️ The OTHER refusal must keep its behaviour. `start_retroactive_run` returning
    False means "one is already running, try again later" - deliberately unmarked, and
    nothing here may turn that into FAILED."""
    scheduler.start_retroactive_run = lambda payload: False
    row = _Row(1, json.dumps({"op": "withdraw", "run_id": "later"}))
    session = _Session([row])
    one_tick(scheduler, session)
    assert row.processed_chain is False
    assert row.status == "PENDING"


def test_a_chain_replay_doorbell_is_marked_but_not_run_here(scheduler):
    """게이트 ⑩ 의 단위 쪽 — 리플레이가 «스케줄러 코드를 안 지난다».

    ⛔ 그래도 초인종은 «찍는다». 안 찍으면 `order_by(id.asc())` 가 이 행을 영원히 맨 앞에
       두어 뒤의 모든 요청이 안 닿는다 — 이 파일 전체가 그 사고(2026-09-04)다.
    ⚠️ 찍어도 일은 «안 사라진다». 일은 작업 표에 살고, 워커가 깨어날 때마다 그 표를 훑는다.
    """
    row = _Row(1, json.dumps({"op": "chain_replay", "run_id": "for-worker"}))
    session = _Session([row])

    one_tick(scheduler, session)

    assert scheduler.started == [], "스케줄러가 리플레이를 시작했다 — 게이트 ⑩ 이 깨진다"
    assert row.processed_chain is True, (
        "초인종을 안 찍었다 — 이 행이 맨 앞에 영원히 남아 뒤의 요청을 굶긴다")
