# -*- coding: utf-8 -*-
"""`replace_map` 봉투 검증이 «두 사본»이었고, 코드가 그 사실을 «주석에 적어 두고» 있었다.

```
chain_ingestion_worker   여섯 규칙을 손으로
chain_replay             같은 여섯을 다시 손으로 — 「두 사본을 손으로 맞춘다」
형제 retract 봉투         이미 «한 독자»(`normalize_retraction_request`) — 같은 모양이 옆에 있었다
```
🔴 「같은 기능에 두 경로」의 교과서다: 둘은 «갈라질 수» 있고, 갈려도 «오류가 안 난다» —
한쪽이 거절하는 봉투를 다른 쪽이 받아 그대로 쓴다.
"""
import ast
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import dt_map_derivation as dmd                                  # noqa: E402

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONSUMERS = ("chain/ingestion_worker.py", "chain/replay.py")
RULE = {"name": "r", "allow_replace_map": True, "allow_retraction": True}


def _code(name):
    src = open(os.path.join(SERVER, name), encoding="utf-8").read()
    tree = ast.parse(src)
    doc = {r for n in ast.walk(tree)
           if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
           and isinstance(n.value.value, str)
           for r in range(n.lineno, (n.end_lineno or n.lineno) + 1)}
    return "\n".join(l for i, l in enumerate(src.splitlines(), 1)
                     if i not in doc and not l.lstrip().startswith("#"))


# ============================================ 1. 독자가 «하나»다

def test_neither_consumer_states_the_rules_itself():
    """🔴 사본이 돌아오면 여기서 말한다. 문장은 «독자»의 것이고 소비자는 그것을 «부를» 뿐이다."""
    for name in CONSUMERS:
        code = _code(name)
        for sentence in ("must explicitly set replace_map=true",
                         "requires a non-empty scope",
                         "cannot redirect scoped batch",
                         "set both replace_map and retract"):
            assert sentence not in code, "%s spells the envelope rule itself: %r" % (name, sentence)


def test_both_consumers_call_the_one_reader():
    for name in CONSUMERS:
        code = _code(name)
        assert "normalize_scoped_batch(" in code, "%s no longer reads the envelope" % name
        assert "require_scoped_batches_allowed(" in code


# ============================================ 2. 여섯 규칙이 «그대로» 산다

@pytest.mark.parametrize("raw,why", [
    ("not a dict", "must be an object"),
    ({"target_table": "other", "replace_map": True, "scope": {"a": 1}}, "cannot redirect"),
    ({"replace_map": True, "retract": {"source_column": "c", "source_value": "v"}},
     "set both replace_map and retract"),
    ({"updates": []}, "must explicitly set replace_map=true"),
    ({"replace_map": True}, "requires a non-empty scope"),
    ({"replace_map": True, "scope": {}}, "requires a non-empty scope"),
])
def test_every_refusal_survived_the_fold(raw, why):
    with pytest.raises(ValueError) as e:
        dmd.normalize_scoped_batch(raw, RULE, "t")
    assert why in str(e.value)


def test_a_retract_envelope_needs_its_own_permission():
    """⚠️ 두 권한이 «각자» 자기 전략을 연다 — retract 만 쓰는 규칙이 purge 권한을 자기에게
    줘야 한다면 쓰지도 않는 권한이 서 있게 된다."""
    with pytest.raises(ValueError) as e:
        dmd.normalize_scoped_batch(
            {"retract": {"source_column": "c", "source_value": "v"}},
            {"name": "r", "allow_replace_map": True}, "t")
    assert "allow_retraction" in str(e.value)


def test_either_permission_opens_the_envelope():
    dmd.require_scoped_batches_allowed({"name": "r", "allow_retraction": True})
    dmd.require_scoped_batches_allowed({"name": "r", "allow_replace_map": True})
    with pytest.raises(ValueError) as e:
        dmd.require_scoped_batches_allowed({"name": "r"})
    assert "allow_replace_map or allow_retraction" in str(e.value)


def test_the_two_strategies_come_back_apart():
    """무회귀 — 한 배치는 «둘 중 하나»만 낸다."""
    _t, _u, scope, retract = dmd.normalize_scoped_batch(
        {"replace_map": True, "scope": {"lot": "L"}}, RULE, "t")
    assert scope == {"lot": "L"} and retract is None
    _t, _u, scope, retract = dmd.normalize_scoped_batch(
        {"retract": {"source_column": "c", "source_value": "v"}}, RULE, "t")
    assert scope is None and retract == ("c", "v")
