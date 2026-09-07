# -*- coding: utf-8 -*-
"""표 키에 리터럴 기본값이 있으면, 키를 «빼는» 순간 조용히 그 표를 열거나 쓴다.

🔴 컬럼에는 이미 그 규율이 있었다(`chain_bindings.resolve_column` — 이름 대어 거절). 표에만
없었고, 출하 템플릿 여섯에 «열넷»이 서 있었다. 철자는 «셋»이다:
```
rule.get(k, "d")              열
(rule or {}).get(k) or D      셋
rule.get(k) or "d"            하나
```
⚠️ 그래서 이 검사는 «세 철자 전부»를 안다. 하나만 알면 다음 기본값이 나머지 둘 중 하나로
들어오고, 그것이 이 부류가 재발하는 모양이다.

⛔ 라이브 맵퍼(`server/mappers/*.py`)는 «조작자의 파일»이라 여기서 안 잰다. 재는 것은
«출하본»이고, 그것이 이 저장소가 책임지는 것이다.
"""
import ast
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_bindings as cb                                      # noqa: E402
import pytest                                                    # noqa: E402

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAPPERS = os.path.join(SERVER, "mappers")
SAMPLE = os.path.join(SERVER, "config", "sample", "chain_rules.json.sample")


def _shipped_mappers():
    """출하되는 맵퍼 — `.py.sample` 과 커밋된 `.py`. 라이브 사본은 «아니다»."""
    for name in sorted(os.listdir(MAPPERS)):
        if name.endswith(".py.sample") or name.startswith("ledger_v2_"):
            yield os.path.join(MAPPERS, name)


def _table_key_defaults(path):
    """`(줄, 철자)` — 표 키를 리터럴/상수로 «메우는» 자리 전부."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    found = []

    def is_table_get(node):
        return (isinstance(node, ast.Call)
                and getattr(node.func, "attr", None) == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in cb.RULE_TABLE_KEYS)

    for node in ast.walk(tree):
        #: 철자 ①  rule.get("k", "d")
        if is_table_get(node) and len(node.args) > 1:
            found.append((node.lineno, "get(k, default)"))
        #: 철자 ②③  ....get("k") or <무엇이든>
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            for value in node.values[:-1]:
                if is_table_get(value):
                    found.append((node.lineno, "get(k) or fallback"))
    return found


# ============================================ 1. 부류 — 출하본에 기본값 «0»

def test_no_shipped_mapper_defaults_a_table_key():
    offenders = {os.path.basename(p): _table_key_defaults(p) for p in _shipped_mappers()}
    offenders = {k: v for k, v in offenders.items() if v}
    assert offenders == {}, "a table key falls back to a literal: %s" % offenders


def test_the_check_knows_all_three_spellings():
    """🔴 검사 자신을 잰다 — 철자 하나만 알면 다음 기본값이 나머지 둘로 들어온다."""
    import tempfile
    src = ('def f(rule):\n'
           '    a = rule.get("map_table", "x")\n'
           '    b = (rule or {}).get("source_table") or SOME\n'
           '    c = rule.get("target_table") or "y"\n')
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "probe.py")
        open(p, "w", encoding="utf-8").write(src)
        found = _table_key_defaults(p)
    assert {s for _ln, s in found} == {"get(k, default)", "get(k) or fallback"}
    assert len(found) == 3, "one of the three spellings is invisible: %s" % found


# ============================================ 2. 거절이 «이름을 댄다»

def test_a_missing_key_is_refused_by_rule_and_key_name():
    with pytest.raises(cb.ColumnBindingRefused) as e:
        cb.resolve_table({"name": "my_rule"}, "map_table")
    assert "my_rule" in str(e.value) and "map_table" in str(e.value), \
        "the operator cannot act on a refusal that names neither"


def test_a_declared_key_resolves_and_is_trimmed():
    assert cb.resolve_table({"name": "r", "map_table": "  dt_log "}, "map_table") == "dt_log"


def test_an_unknown_key_is_refused_against_the_enumeration():
    """⛔ 목적별 새 키를 «만들어 부르는» 것도 막는다 — 열거가 저자다."""
    with pytest.raises(cb.ColumnBindingRefused):
        cb.resolve_table({"name": "r", "made_up_table": "x"}, "made_up_table")


# ============================================ 3. 출하 선언이 «키를 다 적는다»

def test_the_shipped_rules_declare_every_key_their_mapper_resolves():
    """🔴 기본값을 뺐으니 선언이 «채워져» 있어야 한다 — 아니면 출하본이 자기 규칙을 거절한다."""
    rules = {r.get("name"): r for r in
             (json.load(open(SAMPLE, encoding="utf-8")).get("rules") or [])}
    for path in _shipped_mappers():
        module = os.path.basename(path).replace(".py.sample", "").replace(".py", "")
        tree = ast.parse(open(path, encoding="utf-8").read())
        keys = {n.args[1].value for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and getattr(n.func, "attr", None) == "resolve_table"
                and len(n.args) > 1 and isinstance(n.args[1], ast.Constant)}
        for rule in rules.values():
            if (rule.get("mapper_module") or "").endswith(module):
                missing = [k for k in keys if not rule.get(k)]
                assert missing == [], \
                    "shipped rule '%s' omits %s, which its mapper now refuses on" % (
                        rule.get("name"), missing)
