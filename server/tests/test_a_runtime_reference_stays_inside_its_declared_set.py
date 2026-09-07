# -*- coding: utf-8 -*-
"""판정 65 의 «조건». 이 시험이 없으면 그 판정은 «가정»이다.

🔴 `core_alignment_mapper` 는 정렬 기준 표를 «실행 시점»에 고른다 — `resolve_alignment_view` 가
`reference_spec` 을 받아 그 표를 열고, 그 표는 순서 가드가 보는 「선언된 읽기」에 «없었다».
그런데 실측하면 «표는 선언»이고 «map_id 만» 실행 시점이다:
```
_reference_spec:  "%s:%s" % (rule["reference"]["table"], template.format(**fields))
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 선언   ^^^^^^^^^^^^^^^^^ 실행
```
그러므로 «집합»은 선언이 알고, 가드가 그것을 합집합으로 들 수 있다.

⛔ 해석기는 «불변»이다. 반환에 「읽은 표」를 더하는 것은 실행 «뒤»라 순서 판단에 늦고,
반경이 `alignment_view_service` 전체가 된다.
"""
import ast
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_bindings as cb                                      # noqa: E402

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAPPER = os.path.join(SERVER, "mappers", "core_alignment_mapper.py")
SAMPLE = os.path.join(SERVER, "config", "sample", "chain_rules.json.sample")

RULE = {"name": "r", "trigger_table": "dt_log", "target_table": "dt_inventory",
        "reference": {"table": "valid_die_ref", "map_id_template": "{product}_{dt_type}",
                      "fields": ["product", "dt_type"]}}


def test_the_declared_set_holds_the_table_the_spec_will_name():
    assert cb.reference_tables(RULE) == {"valid_die_ref"}
    assert "valid_die_ref" in cb.rule_tables(RULE, cb.TABLE_ROLE_READ)


def test_the_runtime_half_is_the_map_id_never_the_table():
    """🔴 판정 65 의 조건 그 자체 — 실행 시점 값이 무엇이든 «표»는 선언된 그것이다."""
    sys.path.insert(0, os.path.join(SERVER, "mappers"))
    import importlib
    mod = importlib.import_module("mappers.core_alignment_mapper")

    for identity in ({"product": "PRD-A", "dt_type": "DT13"},
                     {"product": "x:y", "dt_type": "z"},          # 구분자를 품은 값
                     {"product": "  P  ", "dt_type": "T"}):
        spec = mod._reference_spec(RULE, identity)
        assert spec is not None
        table = spec.split(":", 1)[0]
        assert table in cb.reference_tables(RULE), \
            "the spec named a table outside the declared set: %r" % spec


def test_nothing_else_can_supply_the_table_half():
    """⚠️ 값 단언만으로는 「내가 떠올린 identity」만 잰다. 그래서 «모양»도 못 박는다 —
    표를 «선언 말고 다른 곳»에서 읽으면 집합이 거짓이 되고, 그때 가드가 다시 눈먼다."""
    tree = ast.parse(open(MAPPER, encoding="utf-8").read())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_reference_spec")
    #: 이 함수 안에서 `table` 에 «대입»되는 것은 선언 블록에서 온 것 하나여야 한다.
    sources = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "table":
                    sources.append(ast.dump(node.value))
    assert len(sources) == 1, "the table half has more than one source: %s" % sources
    #: 그 하나가 «선언 블록의 그 키»에서 온다 — 다른 데서 오면 집합이 거짓이 된다.
    assert "'%s'" % cb.REFERENCE_TABLE_KEY in sources[0],         "the table half no longer comes from the declaration: %s" % sources[0]


def test_the_shipped_rule_that_declares_a_reference_is_covered():
    rules = json.load(open(SAMPLE, encoding="utf-8")).get("rules") or []
    declaring = [r for r in rules if (r.get("reference") or {}).get("table")]
    assert declaring, "the fixture is not exercising a declared reference"
    for r in declaring:
        table = r["reference"]["table"]
        assert table in cb.rule_tables(r, cb.TABLE_ROLE_READ), \
            "shipped rule '%s' reads '%s' and the guard cannot see it" % (r.get("name"), table)
