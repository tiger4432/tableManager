# -*- coding: utf-8 -*-
"""소급 실행은 진행을 «DB 에만» 적고 아무에게도 말하지 않았다 (S-37).

파일 인제션은 진행을 `file_ingestion_progress` 로 방송하고 그리드 화면이 그것을 듣는다.
소급/체인 실행은 `retroactive_runs.processed_rows/total_rows` 에 «쓰기만» 하고 발신이
«0** 이라, 그리드에서 무거운 소급을 돌리면 화면은 아무 말도 하지 않는다. 관리 화면만
폴링으로 본다.

결함 부류는 「발신 없음」이다 — 사실은 «이미 있고**, 나르개가 없다.

🔴 이 파일이 재는 것 넷:
    ㉠ 진행을 «쓸 때마다» 이벤트가 «하나»   (DB 는 갱신되는데 발신 0 이면 빨강)
    ㉡ 봉투를 짓는 함수가 «하나»            (인제션과 «같은** `event_constants.progress_event`)
    ㉣ 인제션 봉투는 «바이트 동일**          (이 라운드가 그것을 안 건드렸다)
    ㉤ 끝나면 «끝났다고** 말한다             (완료·취소·실패 — 안 내면 표시가 영원히 돈다)
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants as ec                                     # noqa: E402
import retroactive                                               # noqa: E402


# ---------------------------------------------------------------------------
# ㉡ · ㉣  봉투 — 저자 하나, 인제션은 바이트 동일
# ---------------------------------------------------------------------------

#: S-37 «이전» `run_watcher.trigger_ws_progress` 가 손으로 짓던 그 dict, 그대로.
INGESTION_BEFORE = {
    "event": "file_ingestion_progress",
    "table_name": "dt_map",
    "filename": "w.csv",
    "progress": 50,
    "processed_rows": 5,
    "total_rows": 10,
    "status": "PROCESSING",
}


def test_the_ingestion_envelope_is_byte_identical():
    """㉣ 이 라운드는 인제션 진행을 «한 글자도** 안 바꾼다 — 키도, 순서도, 값도."""
    made = ec.progress_event(
        ec.PROGRESS_STATUS_RUNNING, progress=50, processed_rows=5, total_rows=10,
        table_name="dt_map", filename="w.csv")
    assert made == INGESTION_BEFORE
    assert list(made) == list(INGESTION_BEFORE), "key ORDER moved; the wire is not identical"


def test_the_two_producers_share_one_author():
    """㉡ 소급 봉투는 «같은 함수»에서 나온다 — 주어만 다르다.

    두 발신자가 각자 dict 를 지으면 갈라져도 오류가 «안 난다**: 한쪽만 키를 하나 더
    실으면 화면은 그 발신자에 대해서만 조용히 덜 안다.
    """
    ingestion = ec.progress_event(ec.PROGRESS_STATUS_RUNNING, progress=1,
                                  table_name="t", filename="f")
    retro = ec.progress_event(ec.PROGRESS_STATUS_RUNNING, progress=1,
                              run_id="abc", op="withdraw")
    assert ingestion["event"] == retro["event"] == ec.EVENT_INGESTION_PROGRESS
    # 봉투의 «뼈대»는 같고 주어만 갈린다.
    skeleton = {"event", "progress", "processed_rows", "total_rows", "status"}
    assert set(ingestion) - skeleton == {"table_name", "filename"}
    assert set(retro) - skeleton == {"run_id", "op"}


def test_an_unknown_total_stays_unknown():
    """0 은 「하나도 안 했다」이고 None 은 「모른다」다. 총계는 실제로 모를 수 있다."""
    made = ec.progress_event(ec.PROGRESS_STATUS_RUNNING, run_id="r", op="o")
    assert made["total_rows"] is None and made["processed_rows"] is None
    assert made["progress"] is None


# ---------------------------------------------------------------------------
# ㉠  진행을 쓸 때마다 이벤트가 하나
# ---------------------------------------------------------------------------

class _Sent:
    def __init__(self):
        self.calls = []

    def __call__(self, base_url, endpoint, payload, timeout):
        self.calls.append((endpoint, payload))
        return ("%s%s" % (base_url, endpoint),
                type("R", (), {"ok": True, "status_code": 200})(), None)


@pytest.fixture()
def sent(monkeypatch):
    import internal_event_client
    box = _Sent()
    monkeypatch.setattr(internal_event_client, "send_internal_event", box)
    return box


def test_every_progress_write_is_also_spoken(sent, monkeypatch):
    """🔴 결함 그 자체. 종전에는 이 자리가 «DB 만** 갱신했다.

    DB 쓰기는 여기서 재지 않는다 — 세션 팩토리를 갈아 끼워 그 절반을 침묵시키고,
    남는 것이 「발신이 있었나」다. 발신이 사라지면 이 단언이 빨개진다.
    """
    class _NullSession:
        def query(self, *a, **k):
            return self

        def filter(self, *a, **k):
            return self

        def update(self, *a, **k):
            return 1

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    control = retroactive.RunControl("run-abc", session_factory=_NullSession, op="withdraw")
    control.progress(processed=30, total=120)

    assert len(sent.calls) == 1, sent.calls
    endpoint, payload = sent.calls[0]
    assert endpoint == "/internal/events/broadcast"
    assert payload["event"] == ec.EVENT_INGESTION_PROGRESS
    assert payload["run_id"] == "run-abc" and payload["op"] == "withdraw"
    assert payload["processed_rows"] == 30 and payload["total_rows"] == 120
    assert payload["progress"] == 25, "percent is derived, not invented"
    assert payload["status"] == ec.PROGRESS_STATUS_RUNNING


def test_a_run_with_no_id_says_nothing(sent):
    """⚠️ 발신은 «주어가 있을 때만». run_id 없는 CLI 실행이 이름 없는 진행을 방송하면
    화면은 그것을 어느 실행에 붙일지 모른다."""
    control = retroactive.RunControl(None, op="withdraw")
    control.progress(processed=1, total=2)
    assert sent.calls == []


# ---------------------------------------------------------------------------
# ㉤  끝나면 끝났다고 말한다
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", [ec.PROGRESS_STATUS_DONE, ec.PROGRESS_STATUS_CANCELLED])
def test_a_finished_run_says_so(sent, status):
    """안 내면 진행 표시가 «영원히** 돈다 — 그것은 「도는 중」과 구별이 안 된다."""
    assert retroactive.announce_progress("run-z", "withdraw", status) is True
    (endpoint, payload), = sent.calls
    assert payload["status"] == status
    assert payload["run_id"] == "run-z"


def test_a_refused_notification_never_fails_the_run(monkeypatch):
    """진행은 «보고이지 작업이 아니다**. 허브가 죽어도 소급 실행은 계속된다."""
    import internal_event_client

    def boom(*a, **k):
        raise RuntimeError("hub is down")

    monkeypatch.setattr(internal_event_client, "send_internal_event", boom)
    assert retroactive.announce_progress("run-z", "withdraw",
                                         ec.PROGRESS_STATUS_RUNNING) is False
