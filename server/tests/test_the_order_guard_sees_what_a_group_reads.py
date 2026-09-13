# -*- coding: utf-8 -*-
"""순서 가드가 그룹의 «쓰기»만 봐서, 선언된 교차 «다섯»이 한 번도 안 보였다.

🔴 상류 규칙이 실패한 표를 하류 규칙이 «읽는» 경우 — 예: `dt_metadata_to_dt_inventory` 가
실패하면 `dt_inventory_to_standard_dt_map` 은 target 이 `dt_map` 이라 «돌았다». 트리거가 방금
실패한 그 표인데도. 그 답은 «낡은 값 위»에서 나오고 오류가 «안 난다».

⚠️ 그리고 이 라운드는 「읽기«로» 바꾸기」가 아니다 — 실측(출하 아홉): 어느 규칙에서도
`target_table` 이 자기 읽기 집합 «안»에 없다. 읽기만으로 바꾸면 오늘의 미룸이 통째로 사라진다.
그래서 «합집합»이고, 그래야 판정 61 이 말한 「대체이지 추가가 아니다」가 실제로 참이 된다.
"""
import ast
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_bindings as cb                                      # noqa: E402
from chain import ingestion_worker as ciw                             # noqa: E402

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAMPLE = os.path.join(SERVER, "config", "sample", "chain_rules.json.sample")


class _Ev:
    def __init__(self, table, event_type="CREATE", payload="{}"):
        self.table_name, self.event_type, self.payload = table, event_type, payload


#: 상류는 `m` 을 «쓰고», 하류는 `m` 을 «읽는다» — 이 줄이 말하는 교차 그대로.
UPSTREAM = {"name": "up", "trigger_table": "a", "target_table": "m"}
DOWNSTREAM = {"name": "down", "trigger_table": "b", "target_table": "z", "map_table": "m"}
RULES = [UPSTREAM, DOWNSTREAM]


# ============================================ 1. 교차가 «보인다»

def test_a_group_that_reads_the_failed_table_is_seen():
    """🔴 이 라운드의 판별식. 하류 그룹의 «쓰기»는 z 뿐이라 예전 술어로는 «안 걸렸다»."""
    blocked = ciw._group_target_tables([_Ev("a")], RULES)      # 상류가 쓰는 표
    assert blocked == {"m"}

    downstream_writes = ciw._group_target_tables([_Ev("b")], RULES)
    downstream_reads = ciw._group_read_tables([_Ev("b")], RULES)

    assert not (downstream_writes & blocked), \
        "the fixture does not exercise the gap - the old predicate already caught it"
    assert downstream_reads & blocked == {"m"}


def test_todays_judgement_is_inside_the_new_one():
    """⚠️ 「대체이지 축소가 아니다」 — 쓰기가 겹치는 그룹은 «여전히» 걸려야 한다."""
    rules = [UPSTREAM, {"name": "same", "trigger_table": "b", "target_table": "m"}]
    blocked = ciw._group_target_tables([_Ev("a")], rules)
    writes = ciw._group_target_tables([_Ev("b")], rules)
    reads = ciw._group_read_tables([_Ev("b")], rules)
    assert writes & blocked == {"m"}, "the pre-existing case stopped being caught"
    assert (writes | reads) & blocked == {"m"}


def test_an_unrelated_group_is_not_deferred():
    """무회귀 — 교차가 «없는» 그룹은 오늘과 같이 돈다. 과잉 미룸도 결함이다."""
    rules = [UPSTREAM, {"name": "far", "trigger_table": "b", "target_table": "z"}]
    blocked = ciw._group_target_tables([_Ev("a")], rules)
    writes = ciw._group_target_tables([_Ev("b")], rules)
    reads = ciw._group_read_tables([_Ev("b")], rules)
    assert not ((writes | reads) & blocked)


# ============================================ 2. 실측 — 「읽기만」이면 오늘이 사라진다

def test_no_shipped_rule_reads_the_table_it_writes():
    """🔴 판정 61 은 「오늘의 target∩target 이 새 술어 «안»에 있다」고 적었는데, 출하 아홉에서
    «아홉 다» 그렇지 않다. 그래서 합집합이라야 그 문장이 참이 된다 — 이 단언이 그 근거다."""
    rules = json.load(open(SAMPLE, encoding="utf-8"))
    rules = rules.get("rules", rules)
    for r in rules:
        writes = cb.rule_tables(r, cb.TABLE_ROLE_WRITE)
        reads = cb.rule_tables(r, cb.TABLE_ROLE_READ)
        assert not (writes <= reads and writes), \
            "%s writes into its own read set - re-check the union argument" % r.get("name")


# ============================================ 3. 모양 — 뜻을 «안» 바꾼 것과 바꾼 것

def test_the_writes_helper_kept_its_meaning_for_its_other_consumer():
    """⚠️ `_group_target_tables` 는 소비자가 «둘»이고 둘째는 «미전달 행 스윕»이다.
    거기에 읽기를 섞으면 순서와 무관한 그 경로가 같이 움직인다."""
    src = open(os.path.join(SERVER, "chain/ingestion_worker.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_group_target_tables")
    body = "\n".join(src.splitlines()[fn.lineno - 1:(fn.end_lineno or fn.lineno)])
    assert "rule_tables" not in body and "TABLE_ROLE_READ" not in body, \
        "the writes helper grew a read notion; its second consumer is not about ordering"


def test_the_guard_asks_about_everything_the_group_touches():
    src = open(os.path.join(SERVER, "chain/ingestion_worker.py"), encoding="utf-8").read()
    assert "group_touches = group_targets | _group_read_tables(" in src
    assert "if blocked_targets and (group_touches & blocked_targets):" in src, \
        "the guard still judges on writes alone"
