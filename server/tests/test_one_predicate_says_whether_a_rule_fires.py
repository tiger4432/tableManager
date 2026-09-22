# -*- coding: utf-8 -*-
"""[지시 5996b7d49 걸음 ①] 「이 규칙이 이 이벤트에 도나」의 정본 좌석.

원자 셋(`enabled` · `trigger_table` 일치 · `_rule_accepts_event`)이 제품 코드 «아홉 자리»에
사본으로 있었다. 접으면서 셋을 «변이»로 걸어 봤더니 `enabled` 를 빼도 체인 시험 56 이
초록이었다 — 아홉 자리에 있던 조건인데 «재는 자리가 없었다». 그 구멍이 이 파일이다.

🔴 축이 «둘»인 것도 여기서 잰다. `event_type` 은 이벤트 혼자의 성질이고 나머지 셋은
   (규칙, 이벤트) 쌍의 성질이다. 하나로 접으면 `group_id` 가 DELETE 를 다르게 묶는다 —
   그래서 「한 술어」가 아니라 「두 술어」가 맞다는 것을 «돌려서» 말한다.
"""
import os
import sys
import types

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import ingestion_worker as worker                                # noqa: E402

RULE = {"name": "r", "enabled": True, "trigger_table": "t", "target_table": "u"}


def ev(kind="EDIT", table="t", payload=None):
    return types.SimpleNamespace(table_name=table, event_type=kind,
                                 payload=payload if payload is not None else {})


# ---------------------------------------------------------------------------
# 원자 셋 — 하나씩 빼면 하나씩 빨개져야 한다
# ---------------------------------------------------------------------------

def test_a_rule_fires_when_all_three_hold():
    """⚠️ 대조군. 이 줄이 참이어야 아래 False 들이 «막혔다»는 뜻이 된다."""
    assert worker.fires(RULE, ev()) is True


def test_a_switched_off_rule_does_not_fire():
    """🔴 변이가 «살아남은» 조건이다 — `enabled` 를 빼도 체인 시험이 초록이었다.
    지시의 게이트 ② (「꺼 둔 규칙은 will_fire=false + why_not」)가 이 줄 위에 선다."""
    assert worker.fires(dict(RULE, enabled=False), ev()) is False


def test_a_rule_watching_another_table_does_not_fire():
    assert worker.fires(RULE, ev(table="other")) is False


def test_a_chain_produced_event_fires_only_for_a_rule_that_opted_in():
    """체인이 낳은 이벤트는 «규칙마다» 옵트인이다 — 전역으로 살아 있지 않다."""
    chain_born = ev(payload={"source_name": "chain_ingestion"})
    assert worker.fires(RULE, chain_born) is False
    assert worker.fires(dict(RULE, allow_chain_trigger=True), chain_born) is True


# ---------------------------------------------------------------------------
# 축이 둘이라는 것 — `fires` 는 event_type 을 «안 본다»
# ---------------------------------------------------------------------------

def test_the_pair_predicate_does_not_read_the_event_type():
    """🔴 이것이 「두 술어」의 근거다. `group_id` 는 «모든» 종류를 묶으므로 이 술어를
    `_is_trigger_event` «없이» 쓴다. 둘을 한 술어로 접으면 DELETE 행의 그룹 키가 바뀐다."""
    assert worker.fires(RULE, ev("DELETE")) is True
    assert worker._is_trigger_event(ev("DELETE")) is False
    assert worker._is_trigger_event(ev("CREATE")) is True
    assert worker._is_trigger_event(ev("EDIT")) is True


def test_grouping_still_keys_a_delete_by_its_rules_group_key(monkeypatch):
    """`group_id` 가 DELETE 를 «여전히» 규칙의 group_by 로 묶는가 — 위 축 분리가
    지킨 동작이다. `_is_trigger_event` 를 이 자리에 «더하면» 이 줄이 빨개진다."""
    monkeypatch.setattr(worker, "group_key", lambda rule, payload: "k")
    keyed = dict(RULE, group_by=["col"])
    assert worker.group_id(ev("DELETE"), [keyed]) == "group_by:k"


# ---------------------------------------------------------------------------
# 좌석이 «하나»인가 — 텍스트가 주어인 드리프트 오라클
# ---------------------------------------------------------------------------

def test_the_trigger_kind_is_spelled_in_exactly_one_place():
    """🔴 [Q-202 QA] 접기를 하면서 제가 «만진 자리»만 좌석으로 보냈습니다. 같은 물음을
    손으로 철자한 자리가 둘 더 있었고(`_rule_outcome_before_running`·`trigger_tables_in_order`),
    QA 가 짚기 전까지 제 커밋 문장은 「접었다」고 말하고 있었습니다.

    제일 아픈 지적은 그 둘이 «빠뜨린 것과 같은 모양»이었다는 것입니다 — `group_id` 의 예외는
    독스트링에 적혀 있어 「일부러」임이 보이는데, 그 둘은 아무 말이 없었습니다.

    ⚠️ 텍스트가 «주어»인 단언이다(잘라쓰기 아님) — 「이 낱말이 한 자리에만 있다」는
       돌려서는 못 재는 주장이라 소스를 읽는 것이 맞는 계기다.
    """
    import inspect
    import re

    source = inspect.getsource(worker)
    spellings = re.findall(r'event_type (?:not )?in [\(\[]"CREATE", ?"EDIT"[\)\]]', source)
    assert len(spellings) == 1, (
        "「깨우는 종류인가」를 손으로 철자한 자리가 %d 곳이다 — 좌석은 _is_trigger_event "
        "하나여야 한다: %r" % (len(spellings), spellings))
    assert "CREATE" not in inspect.getsource(worker.fires), \
        "`fires` 가 event_type 축을 삼켰다 — 축이 둘인 이유가 사라진다"
