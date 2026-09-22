# -*- coding: utf-8 -*-
"""A run row that cannot be updated is the most expensive silence in this system.

`_mark_run` writes on its own session and swallowed every failure at debug level. When
that update fails the WORK still runs - only the record stops - so the row keeps saying
`queued` with no `started_at` and every screen reads "waiting" while the operation is in
flight. Measured cause 2026-09-05: deploying the `runner` column before its migration
makes each UPDATE raise UndefinedColumn, and nothing above debug would ever say so.

⛔ AND IT STILL MUST NOT RAISE. A bookkeeping failure that kills the run is worse than a
loud one, so it is reported and counted instead - and the count travels with the queue,
because a log line nobody tails is the same silence in a different place.
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from admin import retroactive                                               # noqa: E402


@pytest.fixture(autouse=True)
def clean():
    del retroactive._RECORD_FAILURES[:]
    yield
    del retroactive._RECORD_FAILURES[:]


class _Exploding:
    """A session whose UPDATE fails the way a missing column does."""
    def query(self, *a, **k):
        raise RuntimeError("UndefinedColumn: retroactive_runs.runner")

    def rollback(self):
        pass

    def close(self):
        pass


def test_the_failure_is_reported_at_error_not_debug(monkeypatch, caplog):
    monkeypatch.setattr(retroactive, "SessionLocal", _Exploding, raising=False)
    monkeypatch.setattr("database.database.SessionLocal", _Exploding)
    with caplog.at_level(logging.ERROR):
        retroactive._mark_run("run-1", state="running", started=True)
    said = "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)
    assert "run-1" in said
    assert "migrations" in said, "the message does not point at the likely cause"


def test_the_run_is_not_killed_by_a_bookkeeping_failure(monkeypatch):
    """⛔ The work must survive losing its own record."""
    monkeypatch.setattr("database.database.SessionLocal", _Exploding)
    retroactive._mark_run("run-2", state="running", started=True)   # must not raise


def test_the_failure_travels_as_a_value(monkeypatch):
    """🔴 A log line nobody tails is the same silence somewhere else."""
    monkeypatch.setattr("database.database.SessionLocal", _Exploding)
    retroactive._mark_run("run-3", state="running", started=True)
    failures = retroactive.record_failures()
    assert [f["run_id"] for f in failures] == ["run-3"]
    assert "UndefinedColumn" in failures[0]["error"]


def test_no_failure_is_the_normal_empty_answer():
    assert retroactive.record_failures() == []


def test_the_list_is_bounded(monkeypatch):
    """It must not grow without limit while a deployment stays broken."""
    monkeypatch.setattr("database.database.SessionLocal", _Exploding)
    for i in range(40):
        retroactive._mark_run("run-%d" % i, state="running", started=True)
    assert len(retroactive.record_failures()) == 20


# ---------------------------------------------------------------------------
# 게이트 ⑭ — 둘이 «동시에» 집으면 하나만 이기고, 진 쪽이 그것을 «안다»
# ---------------------------------------------------------------------------
# 🔴 옮기기의 «전제 조건»이다. `_mark_run` 은 `run_id` 하나로 필터하는 무조건 갱신이었고,
#    오늘까지 안전했던 이유는 기제가 아니라 «집는 놈이 하나»라서였다(실측: started=True 호출 1).
#    체인 워커가 같은 표에서 집는 순간 그 전제가 거짓이 되고, 둘이 같은 queued 행을 읽으면
#    둘 다 이긴다 — 리플레이가 두 번 돌고, 매퍼가 멱등이라 «결과가 맞아 보이며» 안 터진다.
#
# ⛔ 「안 터졌다」는 이 게이트의 답이 아니다. 그래서 «억지로 동시에» 만든다 — 진짜 스레드
#    둘을 배리어에 세워 같은 순간에 놓는다. 스위트의 메모리 SQLite 는 스레드를 못 건너므로
#    이 시험은 «자기 파일 DB»를 쓴다.

@pytest.fixture
def real_run_row(tmp_path, monkeypatch):
    """queued 인 작업 행 하나가 든 «진짜» DB. 스레드 둘이 같이 열 수 있어야 한다."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database import models
    from database.database import Base

    url = "sqlite:///%s" % (tmp_path / "claims.db").as_posix()
    engine = create_engine(url, connect_args={"check_same_thread": False})
    models.RetroactiveRun.__table__.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine)

    s = Session()
    s.add(models.RetroactiveRun(run_id="race-1", op="chain_replay", params="{}",
                                state=retroactive.RUN_QUEUED))
    s.commit()
    s.close()

    monkeypatch.setattr("database.database.SessionLocal", Session)
    monkeypatch.setattr(retroactive, "SessionLocal", Session, raising=False)
    yield Session
    engine.dispose()


def test_two_runners_claiming_at_once_produce_exactly_one_winner(real_run_row):
    import threading

    from database import models

    start = threading.Barrier(2)
    verdicts = []
    lock = threading.Lock()

    def claim():
        start.wait(timeout=5)          # 같은 순간에 놓는다
        won = retroactive._mark_run("race-1", state=retroactive.RUN_RUNNING,
                                    started=True,
                                    expect_state=retroactive.RUN_QUEUED)
        with lock:
            verdicts.append(won)

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=10)

    assert len(verdicts) == 2, "전제: 둘 다 실제로 집기를 «시도»했다"
    assert verdicts.count(True) == 1, (
        "둘이 동시에 집었는데 이긴 쪽이 %d 이다 — 1 이어야 한다. 2 면 리플레이가 "
        "«조용히 두 번» 돈다(매퍼가 멱등이라 결과는 맞아 보인다)" % verdicts.count(True))
    assert verdicts.count(False) == 1, "진 쪽이 «졌다는 것을 알아야» 한다"

    s = real_run_row()
    row = s.query(models.RetroactiveRun).filter_by(run_id="race-1").one()
    assert row.state == retroactive.RUN_RUNNING
    s.close()


def test_a_second_claim_on_a_running_row_loses(real_run_row):
    """순차로도 같은 답이어야 한다 — 조건이 «상태»에 걸려 있다는 뜻이다."""
    first = retroactive._mark_run("race-1", state=retroactive.RUN_RUNNING, started=True,
                                  expect_state=retroactive.RUN_QUEUED)
    second = retroactive._mark_run("race-1", state=retroactive.RUN_RUNNING, started=True,
                                   expect_state=retroactive.RUN_QUEUED)
    assert first is True
    assert second is False


def test_finishing_a_run_is_not_conditional(real_run_row):
    """⚠️ 끝내는 전이는 «조건 없이» 옮긴다.

    이미 집어서 돌던 일이 자기 결과를 못 적으면 그 행은 영원히 running 으로 남는다 —
    「두 번 도는 것」보다 「끝난 줄 모르는 것」이 화면에서 더 오래 거짓말한다.
    """
    from database import models

    retroactive._mark_run("race-1", state=retroactive.RUN_RUNNING, started=True,
                          expect_state=retroactive.RUN_QUEUED)
    out = retroactive._mark_run("race-1", state=retroactive.RUN_DONE, finished=True,
                                result={"ok": True})
    assert out is None, "조건을 안 줬으면 앞과 같이 None 을 돌려준다"

    s = real_run_row()
    row = s.query(models.RetroactiveRun).filter_by(run_id="race-1").one()
    assert row.state == retroactive.RUN_DONE
    s.close()


def test_a_claim_that_explodes_reports_that_it_did_not_win(monkeypatch):
    """🔴 「모르겠다」의 «안전한 쪽»은 「못 집었다」다.

    이겼다고 답하면 둘이 도는 쪽으로 틀리고, 못 집었다고 답하면 아무도 안 도는 쪽으로
    틀린다. 뒤쪽은 큐에 남아 다음 틱이 다시 집지만, 앞쪽은 조용히 두 번 돈다.
    """
    monkeypatch.setattr(retroactive, "SessionLocal", _Exploding, raising=False)
    monkeypatch.setattr("database.database.SessionLocal", _Exploding)
    won = retroactive._mark_run("boom", state=retroactive.RUN_RUNNING, started=True,
                                expect_state=retroactive.RUN_QUEUED)
    assert won is False


def test_a_run_with_no_row_at_all_is_not_treated_as_lost(real_run_row):
    """🔴 조건부 UPDATE 의 0 은 «두 뜻»이다 — 「남이 가져갔다」와 「행이 아예 없다».

    접었더니 test_retroactive_admin.py 에서 «일곱»이 빨개졌고, 전부 작업 행 없이 직접
    부르는 길(CLI·시험·publish 를 안 거친 호출)이 「졌다」로 읽힌 것이었다. 경쟁할 상대가
    없는데 안 도는 것은 집기가 아니라 «중단»이다.
    """
    won = retroactive._mark_run("no-such-run", state=retroactive.RUN_RUNNING,
                                started=True, expect_state=retroactive.RUN_QUEUED)
    assert won is True, (
        "집을 «행이 없는데» 졌다고 답했다 — 작업 행 없이 부르는 길이 전부 조용히 멈춘다")
