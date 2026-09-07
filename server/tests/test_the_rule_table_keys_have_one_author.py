# -*- coding: utf-8 -*-
"""모델과 가드가 «셋»만 알아서, 선언된 교차 «다섯»이 순서 가드에 한 번도 안 보였다.

🔴 규칙 선언에서 표 이름을 나르는 키는 «일곱»인데(trigger · source · target · map ·
inventory · metadata_target · derivation_source), 순서를 판단하는 자리는 그중 셋만 알았다.
그래서 상류가 실패한 표를 «읽는» 하류 규칙이 그대로 돌았다 — 오류 없이, 낡은 값 위에서.

⚠️ 이 파일이 재는 것은 «열거가 한 자리인가»다. 값이 맞는지가 아니라, 다음 키가 생긴 날
«세 자리 중 하나만» 그것을 모르는 일이 생기는가다 — 그것이 이 결함의 모양이었다.
"""
import ast
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_bindings as cb                                      # noqa: E402

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAMPLE = os.path.join(SERVER, "config", "sample", "chain_rules.json.sample")


def test_the_enumeration_names_every_key_that_carries_a_table():
    assert set(cb.RULE_TABLE_KEYS) == {
        "trigger_table", "source_table", "target_table", "map_table",
        "inventory_table", "metadata_target_table", "derivation_source_table"}


def test_the_role_is_measured_not_read_off_the_name():
    """🔴 `metadata_target_table` 은 이름이 target 인데 «source 로» 읽힌다
    (`dt_inventory_metadata_mapper:81`). 이름으로 역할을 읽으면 그 표가 «쓰기»로 분류되고,
    그러면 그것을 읽는 규칙이 순서 가드에서 다시 빠진다."""
    assert cb.RULE_TABLE_KEYS["metadata_target_table"] == cb.TABLE_ROLE_READ
    assert cb.RULE_TABLE_KEYS["target_table"] == cb.TABLE_ROLE_WRITE


def test_a_comparison_is_not_a_read():
    """가상 조인의 두 키는 «비교»이지 «열기»가 아니다 — 넣으면 과잉 미룸이 아니라 «틀린 뜻»이다."""
    assert "left_table" not in cb.RULE_TABLE_KEYS
    assert "right_table" not in cb.RULE_TABLE_KEYS


def test_reads_is_the_general_slot_and_junk_does_not_enter():
    rule = {"trigger_table": "a", "target_table": "b", "map_table": "c",
            "reads": ["d", "  ", None, 7]}
    assert cb.rule_tables(rule, cb.TABLE_ROLE_READ) == {"a", "c", "d"}
    assert cb.rule_tables(rule, cb.TABLE_ROLE_WRITE) == {"b"}
    assert cb.rule_tables({}, cb.TABLE_ROLE_READ) == set()
    assert cb.rule_tables(None, cb.TABLE_ROLE_WRITE) == set()


def test_the_shipped_declaration_uses_no_key_the_model_does_not_know():
    """선언이 모델을 «넘으면» 그 표는 아무도 안 본다 — 이 줄의 결함 그대로다."""
    rules = json.load(open(SAMPLE, encoding="utf-8"))
    rules = rules.get("rules", rules)
    unknown = {k for r in rules for k in r
               if k.endswith("_table") and k not in cb.RULE_TABLE_KEYS}
    assert unknown == set(), "the shipped rules carry table keys the model cannot see: %s" % unknown


def test_nobody_re_enumerates_the_keys():
    """🔴 ④ — 저자가 «하나»여야 한다. 두 번째 목록은 새 키가 생긴 날 «한쪽만» 모른다."""
    for name in ("chain_ingestion_worker.py", "chain_bindings.py"):
        src = open(os.path.join(SERVER, name), encoding="utf-8").read()
        doc = set()
        tree = ast.parse(src)
        for n in ast.walk(tree):
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) \
                    and isinstance(n.value.value, str):
                doc.update(range(n.lineno, (n.end_lineno or n.lineno) + 1))
        lines = src.splitlines()
        code_lines = [l for i, l in enumerate(lines, 1)
                      if i not in doc and not l.lstrip().startswith("#")]
        #: 한 줄에 표 키가 «둘 이상» 리터럴로 나오면 그것이 두 번째 열거다.
        for line in code_lines:
            if line.strip().startswith(("RULE_TABLE_KEYS", '"trigger_table":')):
                continue
            hits = [k for k in cb.RULE_TABLE_KEYS if '"%s"' % k in line]
            assert len(hits) < 2, "a second enumeration of the table keys: %s" % line.strip()
