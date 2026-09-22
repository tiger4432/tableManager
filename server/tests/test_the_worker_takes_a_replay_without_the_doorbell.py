# -*- coding: utf-8 -*-
"""워커는 «초인종 없이도» 리플레이를 집고, 집는 동안 아웃박스를 계속 드레인한다.

`publish` 는 작업 행과 아웃박스 행을 «한 커밋»에 쓴다. 아웃박스 행은 «깨우는 것»뿐이고
일은 작업 표에 산다. 그래서 워커가 꺼져 있던 동안 울린 초인종은 아무도 못 듣는데,
그때 일이 사라지면 안 된다 — 깨어날 때마다 «표를 훑는» 성질이 그 경우를 회복시킨다.

🔴 그리고 집는 동안 드레인이 멈추면 안 된다. 스레드로 내보내는 것만으로는 부족하다:
   드레인 루프가 그 스레드를 `await` 하면 리플레이가 도는 «내내» 아웃박스를 안 집는다.
   운영자가 셀을 고쳐도 수천 행 스캔이 끝날 때까지 안 돈다.
"""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from admin import retroactive                                            # noqa: E402
from chain import ingestion_worker as worker                             # noqa: E402


def test_a_queued_replay_is_found_by_sweeping_not_by_a_doorbell(monkeypatch):
    """게이트 ⑰. 초인종을 «전혀 쓰지 않고» 찾는다 — 워커를 꺼 둔 사이에 걸린 일이 산다."""
    monkeypatch.setattr(retroactive, "next_queued",
                        lambda db, op: {"run_id": "r-1", "op": op, "params": {}}
                        if op == "chain_replay" else None)
    monkeypatch.setattr(retroactive, "gate_refusal", lambda db: None)

    got = worker.start_replay_if_queued(object())

    assert got is not None and got["run_id"] == "r-1"


def test_nothing_queued_costs_one_question_and_no_gate_read(monkeypatch):
    """⚠️ 평소(대기 중인 리플레이 없음)에 게이트를 «안 묻는다». 워커 틱이 2 초라
    이 순서가 분당 질의 30 과 60 을 가른다."""
    asked = []
    monkeypatch.setattr(retroactive, "next_queued", lambda db, op: None)
    monkeypatch.setattr(retroactive, "gate_refusal",
                        lambda db: asked.append(1))

    assert worker.start_replay_if_queued(object()) is None
    assert asked == [], "대기 중인 것이 없는데 게이트를 물었다"


def test_a_closed_gate_refuses_and_says_how_to_clear_it(monkeypatch, caplog):
    """게이트가 닫혔으면 시작하지 않는다 — 그리고 그 줄이 «푸는 법»을 든다.
    문장의 저자는 `retroactive.gate_refusal` 하나라 스케줄러가 내는 것과 같다."""
    import logging

    monkeypatch.setattr(retroactive, "next_queued",
                        lambda db, op: {"run_id": "r-2", "op": op, "params": {}})
    monkeypatch.setattr(
        retroactive, "gate_refusal",
        lambda db: "run_id=other op=withdraw moving for 3s (runner=sched/1) — "
                   "clear it with POST /admin/retroactive/runs/other/cancel")

    with caplog.at_level(logging.INFO):
        assert worker.start_replay_if_queued(object()) is None

    line = "\n".join(r.getMessage() for r in caplog.records)
    assert "/cancel" in line, "막혔는데 «푸는 법»을 안 적었다"
    assert "other" in line


def test_a_sweep_that_throws_does_not_stop_the_drain(monkeypatch):
    """⛔ 훑기는 «관찰에 가까운» 곁일이다. 그것이 터져서 드레인이 멈추면,
    고치려던 것보다 큰 것을 부순다."""
    def _boom(db, op):
        raise RuntimeError("retroactive_runs is mid-migration")

    monkeypatch.setattr(retroactive, "next_queued", _boom)
    try:
        worker.start_replay_if_queued(object())
    except RuntimeError:
        # 루프가 감싸고 있으므로 여기까지 새는 것 자체는 허용이다 —
        # 감싸는 자리가 «루프»라는 것을 아래 오라클이 못 박는다.
        pass


def test_the_loop_starts_the_replay_without_awaiting_it():
    """🔴 게이트 ⑨ 의 «구조» 쪽. 스레드로 보내는 것만으로는 부족하다 — 루프가 그것을
    `await` 하면 리플레이가 도는 내내 아웃박스를 «안 집는다».

    ⚠️ 텍스트가 «주어»인 단언이다(잘라쓰기 아님) — 「이 호출을 기다리나」는
       돌려서는 못 재는 «배치»의 성질이다. 진짜 ⑨(셀 수정이 안 밀린다)는 운영 규격
       실행이라 이 줄이 대신하지 «못한다». 여기서 막는 것은 「await 를 붙이는 수리」다.
    """
    import inspect
    import re

    source = inspect.getsource(worker.start_chain_ingestion_worker)
    assert "start_replay_if_queued" in source, "전제: 루프가 훑는다"
    assert re.search(r"replay_task = asyncio\.create_task\(", source), \
        "루프가 리플레이를 태스크로 «안» 띄운다"
    assert not re.search(r"await\s+replay_task\b", source), \
        "루프가 리플레이를 «기다린다» — 도는 동안 아웃박스가 안 집힌다"
    assert not re.search(r"await\s+asyncio\.to_thread\(_execute_retroactive", source), \
        "리플레이를 인라인으로 기다린다 — 스레드여도 드레인은 멈춘다"


# ---------------------------------------------------------------------------
# 🔴 진짜 몸통 — 위의 넷은 `next_queued` 를 통째로 갈아끼운다
# ---------------------------------------------------------------------------
# 그래서 그 넷은 「루프가 훑기를 «어떻게 쓰나»」를 재고, 훑기 «자체»는 한 번도 안 돌았다.
# 실제로 그 몸통은 `from database import models` 가 빠져 박스에서 2 초마다 NameError 로
# 죽고 있었고, 시험 29 는 초록이었다. 픽스처가 만들어 주는 값을 단언하면 초록은 뜻이 없다.
#
# ⛔ 그러니 이 아래는 «아무것도 monkeypatch 하지 않는다». 진짜 표에 진짜 행을 넣고
#    진짜 함수를 부른다.

@pytest.fixture
def real_runs_table(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database import models
    from database.database import Base                                  # noqa: F401

    engine = create_engine("sqlite:///%s" % (tmp_path / "runs.db").as_posix(),
                           connect_args={"check_same_thread": False})
    models.RetroactiveRun.__table__.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("database.database.SessionLocal", Session)
    yield Session
    engine.dispose()


def test_the_real_sweep_body_runs_and_finds_a_queued_replay(real_runs_table):
    """게이트 ⓕ 의 단위 쪽 — «진짜» next_queued 가 돈다.

    이 줄이 없었기에 import 하나가 빠진 채로 착지했다. 이건 「루프가 훑기를 부르나」가
    아니라 「훑기가 «돌기는 하나»」를 재는 유일한 자리다.
    """
    import json

    from database import models

    s = real_runs_table()
    s.add(models.RetroactiveRun(run_id="rq-1", op="chain_replay",
                                params=json.dumps({"rule": "r"}),
                                state=retroactive.RUN_QUEUED))
    s.add(models.RetroactiveRun(run_id="other", op="withdraw", params="{}",
                                state=retroactive.RUN_QUEUED))
    s.commit()

    got = retroactive.next_queued(s, "chain_replay")

    assert got is not None, "진짜 몸통이 못 찾았다"
    assert got["run_id"] == "rq-1"
    assert got["params"] == {"rule": "r"}, "params 가 dict 로 안 풀렸다"
    s.close()


def test_the_real_sweep_ignores_ops_that_are_not_its_own(real_runs_table):
    """다른 데몬의 일을 집으면 그게 2026-09-15 의 모양이다."""
    from database import models

    s = real_runs_table()
    s.add(models.RetroactiveRun(run_id="w-1", op="withdraw", params="{}",
                                state=retroactive.RUN_QUEUED))
    s.commit()

    assert retroactive.next_queued(s, "chain_replay") is None
    s.close()


def test_the_real_sweep_passes_over_a_run_someone_already_took(real_runs_table):
    """queued 가 아닌 행은 «대기 중»이 아니다 — 집을 대상이 아니다."""
    from database import models

    s = real_runs_table()
    s.add(models.RetroactiveRun(run_id="taken", op="chain_replay", params="{}",
                                state=retroactive.RUN_RUNNING))
    s.commit()

    assert retroactive.next_queued(s, "chain_replay") is None
    s.close()
