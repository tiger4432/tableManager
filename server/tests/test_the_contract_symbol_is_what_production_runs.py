# -*- coding: utf-8 -*-
"""계약이 «죽은 함수»를 채점하고 있었다 — 초록이 «운영»에 대해 아무 말도 안 했다.

```
resolve_valid_die_basis   호출 17 · 전부 시험·계약 · 운영 «0»
운영 `_resolve_reference` 는 같은 판정을 «자기 손»으로 했다
```
🔴 그래서 계약의 초록은 「클라 = 안 도는 함수」를 보증했을 뿐이다. 이제 운영의 «선언 갈래»가
그 함수를 «지난다» — 판정이 그 안에서 일어나고 DB 절반은 resolver 로 «주입»된다.

⛔ 번역층이 아니다. 상태 토큰이 «같은 객체»이고(S-15 ④ ①), 캐시·캡은 «코어 밖»에 남는다 —
코어가 순수해야 벡터가 그것을 부를 수 있고, 그 순수성이 계약의 «전제»다.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import map_alignment as ma                                       # noqa: E402
import map_overlay                                               # noqa: E402

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
#: 선언은 있는데 «못 읽는다» — 읽기까지 가지 않으므로 DB 가 필요 없다.
BROKEN = {"grid_metadata": None, map_overlay.VALID_DIE_REF_KEY: 0}


def _decl_branch_code():
    src = open(os.path.join(SERVER, "map_alignment.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_resolve_reference")
    doc = {r for n in ast.walk(fn)
           if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
           and isinstance(n.value.value, str)
           for r in range(n.lineno, (n.end_lineno or n.lineno) + 1)}
    lines = src.splitlines()
    return "\n".join(l for i, l in enumerate(lines, 1)
                     if fn.lineno <= i <= (fn.end_lineno or fn.lineno)
                     and i not in doc and not l.lstrip().startswith("#"))


# ============================================ 1. 운영이 «그 함수»를 지난다

def test_production_calls_the_contract_symbol():
    code = _decl_branch_code()
    assert "map_overlay.resolve_valid_die_basis(" in code, \
        "production still makes this judgement by hand; the contract's green means nothing for it"
    assert "map_overlay.parse_valid_die_ref(" not in code, \
        "the declaration is still parsed a second time - two judges again"


def test_the_core_stays_pure_so_the_vectors_can_call_it():
    """⛔ 캐시·캡을 코어 «안»으로 끌어들이면 벡터가 그것을 못 부르고, 그러면 계약이
    다시 «운영이 아닌 것»을 채점한다."""
    import inspect
    core = inspect.signature(map_overlay.resolve_valid_die_basis).parameters
    assert set(core) == {"meta", "resolver", "table"}, \
        "the contract core grew an argument the vectors cannot supply: %s" % list(core)
    assert hasattr(ma, "_memoized_reference"), \
        "the cache moved into the core rather than staying beside it"


# ============================================ 2. 판정이 «한 자리»에서 온다

def test_productions_refusal_is_the_cores_refusal():
    """🔴 이 라운드의 판별식. 같은 메타에 대해 운영이 내는 사유가 «코어가 만든 그 문장»이다 —
    코어를 변이하면 계약이 빨개지고 «이 단언도» 빨개진다. 전에는 후자가 «안» 빨개졌다."""
    core = map_overlay.resolve_valid_die_basis(BROKEN, lambda ref: None)
    assert core["source"] == map_overlay.SOURCE_REFUSED

    produced = ma._resolve_reference(None, {}, None, [{"meta": BROKEN}], 10)
    assert produced["state"] == ma.REFERENCE_REFUSED
    assert produced["reason"] == core["reason"], \
        "production wrote its own sentence; the core's is what the contract scores"


def test_a_map_with_no_declaration_is_absent_not_refused():
    """무회귀 — 「선언이 없다」는 «흔한 정상»이고 거절이 아니다. 코어는 그것을 `circle` 이라
    부르고 운영은 `absent` 라 부르는데, S-15 ④ ① 이후 그 둘은 «같은 객체»다."""
    produced = ma._resolve_reference(None, {}, None, [{"meta": {"rotation": 0}}], 10)
    assert produced["state"] == ma.REFERENCE_ABSENT
    assert ma.REFERENCE_ABSENT is map_overlay.SOURCE_CIRCLE
