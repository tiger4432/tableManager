# -*- coding: utf-8 -*-
"""「이 규칙이 «꺼져서» 안 돈 것」과 「돌았는데 «바꿀 게 없던» 것」이 같은 모양이었다.

🔴 여섯 원인이 «한 조용한 반환»(`return True, None`)으로 나갔다 — 이벤트 종류 · 트리거 규칙
없음 · `enabled: false` · `allow_chain_trigger` 미선언 · 앞선 실패에 막힘 · 돌았는데 0.
운영자가 가르는 것은 그 여섯이 아니라 «다섯»이고, 원인은 사유 문자열이 옆에서 말한다.

⚠️ 새 기록면을 «안 만들었다». 이미 있는 활동 레지스트리의 칸 하나이고 수명은 `running` 과
같은 «이 프로세스»다 — 이력이 아니다. 「그때 그 트랜잭션에서」는 다른 알갱이이고 다른 줄이다.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_activity                                            # noqa: E402
import chain_ingestion_worker as ciw                             # noqa: E402
import event_constants as ec                                     # noqa: E402

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class _Ev:
    def __init__(self, table, event_type="CREATE", payload="{}"):
        self.table_name, self.event_type, self.payload = table, event_type, payload


def _rule(name="r", table="t", **kw):
    return dict({"name": name, "trigger_table": table}, **kw)


# ============================================ 1. 돌기 «전»에 정해지는 결과

def test_a_disabled_rule_says_so():
    out, why = ciw._rule_outcome_before_running(_rule(enabled=False), [_Ev("t")])
    assert out == ec.RULE_OUTCOME_SKIPPED_DISABLED
    assert why, "the operator-fixable case must carry its reason"


def test_disabled_beats_not_triggered():
    """⚠️ 둘 다 참일 때 «고칠 수 있는» 쪽이 이긴다 — 「안 걸림」은 데이터의 사실이라 고칠
    대상이 아니고, 그것만 보이면 운영자가 선언을 안 본다."""
    out, _ = ciw._rule_outcome_before_running(_rule(enabled=False), [_Ev("other")])
    assert out == ec.RULE_OUTCOME_SKIPPED_DISABLED


def test_a_rule_nothing_triggered_says_so_without_inventing_a_reason():
    out, why = ciw._rule_outcome_before_running(_rule(), [_Ev("other")])
    assert out == ec.RULE_OUTCOME_SKIPPED_NOT_TRIGGERED
    assert why is None, "there is no operator action here; a sentence would be noise"


def test_a_chain_event_refused_for_want_of_the_opt_in_names_it():
    """🔴 «옵트인»은 `enabled` 가 아니라 이것이다 — 체인이 «만든» 이벤트에만 걸린다."""
    ev = _Ev("t", payload='{"source_name": "chain_ingestion"}')
    out, why = ciw._rule_outcome_before_running(_rule(), [ev])
    assert out == ec.RULE_OUTCOME_SKIPPED_NOT_TRIGGERED
    assert why and "allow_chain_trigger" in why
    #: 선언하면 «돌 자격»이 있고, 결과는 실행이 정한다
    assert ciw._rule_outcome_before_running(
        _rule(allow_chain_trigger=True), [ev]) == (None, None)


def test_an_eligible_rule_leaves_the_answer_to_the_run():
    assert ciw._rule_outcome_before_running(_rule(), [_Ev("t")]) == (None, None)


# ============================================ 2. 갈리는 표본 — 이 줄의 판별식

def test_a_disabled_rule_and_a_rule_that_changed_nothing_differ():
    """🔴 이 라운드가 «존재하는 이유». 둘 다 「아무 일도 없었다」인데 운영자에게는 «다른 일»이다."""
    reg = chain_activity.ChainActivityRegistry()
    reg.record_outcome("off", ec.RULE_OUTCOME_SKIPPED_DISABLED, "rule declares enabled: false")
    reg.record_outcome("quiet", ec.RULE_OUTCOME_RAN_UNCHANGED, "the mapper produced no rows")
    out = reg.outcomes()
    assert out["off"]["outcome"] != out["quiet"]["outcome"]
    assert out["off"]["outcome"] in ec.RULE_OUTCOMES
    assert out["quiet"]["outcome"] in ec.RULE_OUTCOMES


def test_never_evaluated_is_a_value_not_an_absence():
    """부재는 「옛 서버」 «하나»만 뜻해야 한다 — 그래서 선언된 규칙은 씨로 세워 둔다."""
    reg = chain_activity.ChainActivityRegistry()
    reg.seed_rules(["a", "b"])
    assert reg.outcomes()["a"]["outcome"] == ec.RULE_OUTCOME_NEVER_EVALUATED
    reg.record_outcome("a", ec.RULE_OUTCOME_RAN_CHANGED)
    reg.seed_rules(["a", "b"])
    assert reg.outcomes()["a"]["outcome"] == ec.RULE_OUTCOME_RAN_CHANGED, \
        "a reload wiped a result it should only have filled around"


# ============================================ 3. 라우트 — 같은 경로, «값»으로

def test_the_route_carries_it_on_the_same_path_as_running(client):
    chain_activity.registry.record_outcome(
        "gate-probe", ec.RULE_OUTCOME_SKIPPED_DISABLED, "rule declares enabled: false")
    body = client.get("/admin/chain/queue",
                      headers={"X-Admin-Token": os.environ.get("ADMIN_TOKEN", "")}).json()
    assert "rule_outcomes" in body, "the route says nothing about why a rule did nothing"
    row = body["rule_outcomes"]["gate-probe"]
    assert row["last_outcome"] == ec.RULE_OUTCOME_SKIPPED_DISABLED
    assert row["last_reason"]
    assert isinstance(row["last_age_seconds"], (int, float))
    #: 무회귀 — 기존 칸이 그대로
    for key in ("running", "waiting", "loop_in_this_process", "oldest_waiting_seconds"):
        assert key in body


# ============================================ 4. 모양 — 두 사실에 두 이름

def test_finish_still_has_exactly_one_caller():
    """🔴 판정 63 의 멈춤 조건을 «상설»로 세운다. `finish` 가 하는 일은 「도는 목록에서
    뺀다」 하나이고, 거기에 결과 기록을 얹으면 호출자가 여섯이 된다."""
    src = open(os.path.join(SERVER, "chain_ingestion_worker.py"), encoding="utf-8").read()
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "finish"]
    assert len(calls) == 1, "finish grew a second caller - two facts under one name"


def test_the_vocabulary_is_closed_and_the_causes_are_not_values():
    """⛔ 원인 여섯을 값 여섯으로 만들지 않는다 — 그러면 화면이 그것을 다시 다섯으로 접는다."""
    assert ec.RULE_OUTCOMES == {
        "skipped:disabled", "skipped:not_triggered",
        "ran:unchanged", "ran:changed", "failed", "never_evaluated"}
