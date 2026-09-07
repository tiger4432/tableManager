# -*- coding: utf-8 -*-
"""문지기는 «왜»를 이름으로 아는데 그것을 내놓는 라우트가 없었다 (S-39).

`ledger/gate.py` 는 거절을 «사유 이름»(닫힌 열둘)으로 세고, 각 거절의 상세 문장과 주소를
표본으로 들고 있다. 그리고 그 상세 문장은 «이미 다음 행동을 말한다** —
「… declare it there and this atom lands」.

그런데 그 수·표본을 읽는 라우트가 «하나도 없었다**(main·ledger_api 전수 0). 그래서 화면은
「몇 행이 안 들어갔나」만 보이고 «왜»는 안 보였고, 그 공백에서 운영자는 시간 선언을
의심했다 — 사유 열둘 중 시간에 관한 것은 «둘»뿐인데.

🔴 그러므로 이 라운드는 «사실을 만들지 않는다**. 나르개를 하나 놓는다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import gate                                          # noqa: E402

ROUTE = "/admin/ontology-explorer/refusals"
DETAIL = ("'Equipment' is outside this source's subject_types [Lot, Wafer] - "
          "declare it there and this atom lands")


def _get(client):
    res = client.get(ROUTE, headers={"X-Admin-Token": os.environ.get("ADMIN_TOKEN", "")})
    assert res.status_code == 200, res.text
    return res.json()


#: 🔴 표본이 «둘»이어야 「자르면 빨개진다」를 재다. 하나로 재면 `[:1]` 가 아무것도
#: 안 바꾸고 단언은 초록이다 — 실측 2026-09-07: 그 변이가 «살아 나왔다**.
SECOND_DETAIL = "'Tool' is outside this source's subject_types - declare it there"


@pytest.fixture()
def refused(client):
    gate.reset_counters()
    gate._record("syn_lot_event", gate.REFUSE_UNDECLARED_SUBJECT_TYPE, 26, DETAIL,
                 addresses=[{"code": "EQ-1", "path": "payload.equipment"}])
    gate._record("syn_lot_event", gate.REFUSE_UNDECLARED_SUBJECT_TYPE, 4, SECOND_DETAIL)
    yield client
    gate.reset_counters()


# ---------------------------------------------------------------------------
# ㉠  거절 하나 -> 소스 · 사유 · 수 · 표본 detail 이 «그대로»
# ---------------------------------------------------------------------------

def test_one_refusal_arrives_whole(refused):
    """🔴 이 라운드의 요지. 문지기가 아는 넷이 «한 자리»에서 다 보인다."""
    body = _get(refused)
    src = body["sources"]["syn_lot_event"]
    assert src["rows_refused"] == 2
    assert src["atoms_lost"] == 30, "atoms built and thrown away with their molecules"

    reason = src["reasons"][gate.REFUSE_UNDECLARED_SUBJECT_TYPE]
    assert reason["count"] == 2
    # 🔴 표본은 «전부» 온다. 하나만 단언하면 라우트가 잘라도 초록이다.
    assert len(reason["samples"]) == 2, reason["samples"]
    # 문장이 «그대로» 온다. 잘리거나 바꿔 쓰이면 그 안의 «다음 행동»이 사라진다.
    assert [x["detail"] for x in reason["samples"]] == [DETAIL, SECOND_DETAIL]
    assert all("declare it there" in x["detail"] for x in reason["samples"])
    assert reason["samples"][0]["addresses"] == [
        {"code": "EQ-1", "path": "payload.equipment"}]
    assert reason["samples"][1]["addresses"] == [], "an absent address is empty, not invented"


def test_the_reason_is_not_folded_into_a_count(refused):
    """사유가 이름으로 남아야 운영자가 «어디를 고칠지» 안다.

    시간 사유는 열둘 중 «둘»뿐이다 — 수만 보이면 나머지 열도 시간 문제로 읽힌다.
    """
    body = _get(refused)
    reasons = body["sources"]["syn_lot_event"]["reasons"]
    assert list(reasons) == [gate.REFUSE_UNDECLARED_SUBJECT_TYPE], reasons
    assert gate.REFUSE_NO_TIME_DECLARATION not in reasons


def test_two_reasons_on_one_source_stay_apart(client):
    """한 소스가 «여러 이유»로 거절될 수 있고, 합치면 고칠 자리가 하나로 보인다."""
    gate.reset_counters()
    try:
        gate._record("syn_lot_event", gate.REFUSE_UNDECLARED_SUBJECT_TYPE, 26, DETAIL)
        gate._record("syn_lot_event", gate.REFUSE_NO_RAW_REF, 0, "no raw ref")
        gate._record("syn_lot_event", gate.REFUSE_NO_RAW_REF, 0, "no raw ref")

        reasons = _get(client)["sources"]["syn_lot_event"]["reasons"]
        assert set(reasons) == {gate.REFUSE_UNDECLARED_SUBJECT_TYPE, gate.REFUSE_NO_RAW_REF}
        assert reasons[gate.REFUSE_NO_RAW_REF]["count"] == 2
        assert reasons[gate.REFUSE_UNDECLARED_SUBJECT_TYPE]["count"] == 1
    finally:
        gate.reset_counters()


# ---------------------------------------------------------------------------
# ㉡  사유 낱말은 문지기의 상수 «그것»
# ---------------------------------------------------------------------------

def test_the_declared_set_is_the_gates_own(refused):
    """두 저자 금지. 화면이 자기 목록을 따로 들면 문지기가 사유를 하나 더할 때 갈린다."""
    body = _get(refused)
    assert body["declared_reasons"] == sorted(gate.REFUSAL_REASONS)
    assert len(gate.REFUSAL_REASONS) == 12, "the closed set moved; this round's premise did too"
    for reasons in (s["reasons"] for s in body["sources"].values()):
        assert set(reasons) <= gate.REFUSAL_REASONS, reasons


# ---------------------------------------------------------------------------
# ㉢  «언제부터»인가 — 프로세스 집계라 재기동이면 0
# ---------------------------------------------------------------------------

def test_the_answer_says_when_it_started_counting(refused):
    """🔴 `since` 가 없으면 「거절이 없었다」와 「방금 떠서 아직 모른다」가 «같은 응답»이다.

    운영자에게 그 둘은 정반대 행동이다 — 하나는 「됐다」, 하나는 「더 기다려라」.
    """
    body = _get(refused)
    assert body["since"], body
    from datetime import datetime
    stamped = datetime.fromisoformat(body["since"])
    assert stamped.tzinfo is not None, "a bare local time cannot be compared to anything"


def test_an_empty_process_is_not_silence(client):
    """거절이 «하나도 없어도» 라우트는 답한다 — 그리고 언제부터인지 말한다."""
    gate.reset_counters()
    body = _get(client)
    assert body["sources"] == {}
    assert body["since"], "an empty answer without `since` reads as 'nothing is wrong'"
    assert body["declared_reasons"] == sorted(gate.REFUSAL_REASONS)


# ---------------------------------------------------------------------------
# 표본은 문지기가 이미 자른다 — 그 절단을 «말한다»
# ---------------------------------------------------------------------------

def test_the_sample_cap_is_spoken_not_silent(client):
    """20건까지만 표본이 남는다. 안 말하면 「거절이 20건」과 「20건까지만 봤다」가 같아 보인다."""
    gate.reset_counters()
    try:
        for i in range(gate.MAX_REFUSAL_SAMPLES + 5):
            gate._record("syn_lot_event", gate.REFUSE_NO_RAW_REF, 0, "r%d" % i)

        body = _get(client)
        cut = body["truncated"]["samples"]
        assert cut["cut"] is True
        assert cut["omitted"] == 5, cut
        assert cut["reason"], "a cut axis names why"
        assert body["samples_cap"] == gate.MAX_REFUSAL_SAMPLES
        # 🔴 수는 «안 잘린다** — 표본만 잘린다. 그 둘이 같이 잘리면 「얼마나」를 잃는다.
        assert body["sources"]["syn_lot_event"]["reasons"][
            gate.REFUSE_NO_RAW_REF]["count"] == gate.MAX_REFUSAL_SAMPLES + 5
    finally:
        gate.reset_counters()


def test_an_uncut_answer_says_so(refused):
    """세 상태 중 「쟀고 안 잘렸다」 — 키가 없는 것과 다르다."""
    cut = _get(refused)["truncated"]["samples"]
    assert cut["cut"] is False and cut["omitted"] is None and cut["reason"] is None
