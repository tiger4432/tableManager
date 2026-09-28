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

import pytest

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


# ---------------------------------------------------------------------------
# 「이 규칙만」 — 사건이 들고 온 제한
# ---------------------------------------------------------------------------

RULE_Y = {"name": "rule_y", "enabled": True, "trigger_table": "t", "target_table": "u"}
RULE_X = dict(RULE, name="rule_x")


def test_an_event_with_no_restriction_wakes_every_matching_rule():
    """⚠️ 대조군. 이 줄이 참이어야 아래의 False 가 «제한 때문»이라는 뜻이 된다."""
    import event_constants as ec

    plain = ev()
    assert ec.only_rule_of(plain.payload) is None
    assert worker.fires(RULE_X, plain) is True
    assert worker.fires(RULE_Y, plain) is True


def test_a_restricted_event_wakes_only_the_rule_it_names():
    import event_constants as ec

    only_x = ev(payload={ec.ONLY_RULE_KEY: "rule_x"})
    assert worker.fires(RULE_X, only_x) is True
    assert worker.fires(RULE_Y, only_x) is False


def test_the_restriction_is_read_through_a_stored_json_payload():
    """🔴 운영의 페이로드는 «문자열»로 저장돼 있다. dict 로만 재면 그 초록이 거짓이다 —
    파싱을 안 거치는 자리를 통과시켜 버린다."""
    import json

    import event_constants as ec

    stored = ev(payload=json.dumps({ec.ONLY_RULE_KEY: "rule_x"}))
    assert worker.fires(RULE_X, stored) is True
    assert worker.fires(RULE_Y, stored) is False


def test_an_empty_restriction_is_not_a_restriction():
    """빈 문자열은 «이름이 아니다». 제한으로 읽으면 아무 규칙도 못 도는 행이 된다 —
    조용히 아무 일도 안 일어나고, 그것이 제일 진단하기 어려운 상태다."""
    import event_constants as ec

    for empty in ("", "   ", None):
        e = ev(payload={ec.ONLY_RULE_KEY: empty})
        assert worker.fires(RULE_X, e) is True, "빈 값 %r 이 제한으로 읽혔다" % (empty,)


def test_the_restriction_is_asked_in_exactly_one_place():
    """🔴 [Q-202 와 같은 모양] 이 비교를 열한 호출 자리에 «따로» 적으면 열두째가 빠지고,
    빠진 자리는 「제한 없음」으로 읽혀 그 표의 모든 규칙이 깨어난다.

    ⚠️ 텍스트가 «주어»인 단언이다(잘라쓰기 아님).
    """
    import inspect
    import re

    source = inspect.getsource(worker)
    asked = re.findall(r"only_rule_of\(", source)
    assert len(asked) == 1, (
        "제한을 묻는 자리가 %d 곳이다 — `fire_refusal` 하나여야 한다: %d" % (len(asked), len(asked)))
    # [총괄 2a1be19e9] `fires` 는 `fire_refusal` 의 참/거짓이다 — 좌석은 그 안에 있다.
    assert "only_rule_of(" in inspect.getsource(worker.fire_refusal), \
        "`fire_refusal` 이 제한을 안 묻는다 — 좌석이 옮겨갔다"
    assert "fire_refusal(" in inspect.getsource(worker.fires)


# ---------------------------------------------------------------------------
# 「켜졌나」 — 판정 함수 하나 (총괄 69aad666e ①)
# ---------------------------------------------------------------------------

#: `enabled` 의 값 -> 켜졌나. 워커가 읽어 온 그대로 — 없음·참은 켜짐, false·0·null 은 꺼짐
ENABLED = [("absent", True), (True, True), (1, True), (False, False), (0, False), (None, False)]


@pytest.mark.parametrize("value, on", ENABLED)
def test_every_seat_reads_one_enabled_alike(value, on):
    """🔴 `enabled: 0`·`null` 이 파생 표로는 «세지고» 워커는 «안 깨웠다» — 한쪽은 `is False`,
    한쪽은 참거짓으로 읽었다. 같은 값을 판정·술어·파생 표·통합 선언이 같게 읽는다."""
    from chain import enrichment, rule_shape

    rule = dict(RULE, mapper=enrichment.config.DEDUP_MAPPER)
    unified = {"name": "r", "derive": {"kind": "decide"}}
    if value == "absent":
        rule.pop("enabled")
    else:
        rule["enabled"] = unified["enabled"] = value

    assert rule_shape.is_switched_off(rule) is (not on)
    assert worker.fires(rule, ev()) is on
    assert (rule["target_table"] in enrichment.config.derived_tables([rule])) is on
    assert rule_shape.is_switched_off(rule_shape.from_declaration(unified)) is (not on)


def test_enabled_is_read_in_exactly_one_place():
    """🔴 「이 규칙이 켜졌나」를 열아홉 자리가 사본으로 읽었고 둘이 다르게 읽었다. 규칙의
    `enabled` 를 «읽는» 자리는 `rule_shape.is_switched_off` 하나 — 나머지는 선언 모양 사이의
    «복사»와, 이미 판정된 명단 행을 읽는 한 줄뿐이다.

    ⚠️ 텍스트가 «주어»인 단언이다(잘라쓰기 아님) — AST 로 센다.
    """
    import ast
    import pathlib

    allowed = {("chain/rule_shape.py", name) for name in (
        "from_chain_rule", "from_declaration", "with_declared_cells", "to_declaration",
        "is_switched_off")}
    allowed.add(("chain/ingestion_worker.py", "load_chain_rules"))   # rule_census 의 행
    root = pathlib.Path(SERVER_DIR)
    files = sorted(root.glob("chain/**/*.py")) + [root / "admin" / "retroactive.py",
                                                  root / "main.py"]
    stray, judged = [], 0
    for path in files:
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            reads = (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                     and node.func.attr == "get" and node.args
                     and isinstance(node.args[0], ast.Constant)
                     and node.args[0].value == "enabled") or (
                isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load)
                and isinstance(node.slice, ast.Constant) and node.slice.value == "enabled")
            if not reads:
                continue
            up = node
            while up in parents and not isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef)):
                up = parents[up]
            where = (rel, getattr(up, "name", "<module>"))
            judged += where == ("chain/rule_shape.py", "is_switched_off")
            if where not in allowed:
                stray.append("%s:%d %s" % (rel, node.lineno, where[1]))
    assert judged == 1, "판정 함수 안의 읽기를 못 찾았다 — 계기가 고장이다 (%d)" % judged
    assert stray == [], "`enabled` 를 판정 함수 밖에서 읽는 자리: %r" % stray
