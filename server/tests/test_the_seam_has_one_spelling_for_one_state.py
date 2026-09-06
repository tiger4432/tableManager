# -*- coding: utf-8 -*-
"""한 사실에 철자가 «둘»이었고, 계약은 «운영이 안 쓰는» 쪽을 채점하고 있었다.

```
클라   validDieBasis()  ->  'ref' · 'circle' · 'refused'          계약이 이 낱말로 채점한다
서버 A  SOURCE_*        =  "ref"/"circle"/"refused"               운영 호출 «0» (전수: 17 중 17 이 시험·계약)
서버 B  REFERENCE_*     =  "resolved"/"absent"/"refused"          운영이 «이것»을 썼다
```
🔴 같은 세 상태다. ref↔resolved · circle↔absent · refused↔refused. 갈라져도 «오류가 안 난다» —
계약의 초록이 «운영»에 대해 아무 말도 하지 않던 것이 그 갈라짐의 값이었다.

✅ 그래서 운영이 «값을 빌려온다». 번역 함수가 아니라 «같은 객체»다 — 그러면 갈라질 수가 없다.
⚠️ 접기가 화면을 안 움직이는 근거: 이 값은 `reference.state` 로 나가지만 클라에 «독자가 없다»
   (`map2/decode.js:461` 이 `referenceState` 로 풀고, client2 전수에서 그 이름이 «그 한 줄»뿐).
"""
import ast
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import map_alignment                                             # noqa: E402
import map_overlay                                               # noqa: E402

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

PAIRS = ((map_alignment.REFERENCE_RESOLVED, map_overlay.SOURCE_REF),
         (map_alignment.REFERENCE_ABSENT, map_overlay.SOURCE_CIRCLE),
         (map_alignment.REFERENCE_REFUSED, map_overlay.SOURCE_REFUSED))


def _code_only(path):
    """🔴 인용은 호출이 아니다 — 주석과 docstring 을 «먼저» 걷어낸다."""
    src = open(path, encoding="utf-8").read()
    doc = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            doc.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    lines = src.splitlines()
    return "\n".join(l for n, l in enumerate(lines, 1)
                     if n not in doc and not l.lstrip().startswith("#"))


# ============================================ 1. 두 철자가 «갈라질 수 없다»

def test_the_production_states_are_the_contract_symbols():
    for produced, contracted in PAIRS:
        assert produced is contracted, \
            "production spells this state itself: %r vs %r" % (produced, contracted)


def test_the_response_field_carries_the_contract_vocabulary():
    """⛔ «있음»이 아니라 «값»이다 — 화면과 계약이 읽는 낱말 그 자체를 잰다."""
    assert map_alignment._ref_state(map_alignment.REFERENCE_ABSENT)["state"] == "circle"
    assert map_alignment._ref_state(map_alignment.REFERENCE_RESOLVED)["state"] == "ref"
    assert map_alignment._ref_state(map_alignment.REFERENCE_REFUSED)["state"] == "refused"


def test_the_retired_spelling_is_not_written_by_hand_anywhere():
    """다음 사람이 「resolved」를 다시 적으면 그 자리에서 철자가 둘이 된다."""
    code = _code_only(os.path.join(SERVER, "map_alignment.py"))
    for retired in ('"resolved"', "'resolved'"):
        assert retired not in code, "the retired spelling came back: %s" % retired


def test_the_three_states_did_not_collapse_into_each_other():
    """⚠️ 접는 것과 «뭉개는» 것은 다르다. 셋은 여전히 «서로 다른» 세 답이다."""
    values = {map_alignment.REFERENCE_RESOLVED, map_alignment.REFERENCE_ABSENT,
              map_alignment.REFERENCE_REFUSED}
    assert len(values) == 3, "two states became one: %s" % values


# ============================================ 2. 클라의 «넷째» 값 — 재고, 짓지 않는다

def test_the_clients_fourth_value_is_not_a_server_state():
    """🔴 판정 55 가 「그 라운드에서 재라, 짓지 말고」라 한 그 물음.

    클라의 `validDieBasis()` 는 `'template'` 도 낸다. 실측: 그것은 «저작 캔버스» 상태다 —
    `map_editor.js:10326·10348` 이 편집 중인 템플릿의 키에서 만들고, `:8937` 이 그 상태를
    «캐시 불가»로 표시한다. 브라우저 세션의 «진행 중» 사실이라 서버에는 대응 상태가 없고,
    있을 자리도 없다(서버는 저작 캔버스를 안 본다 — `map_overlay.origin_box` 의 docstring 이
    「저작 중」을 클라가 원으로 그리는 경우로 이미 적어 두었다).

    ⛔ 그러므로 «지어내지 않는다». 벡터도 안 늘린다. 이 단언은 그 부재를 «기록»한다 —
       다음 사람이 이 넷째 값을 보고 서버 상태를 만들지 않도록."""
    for name in ("map_overlay.py", "map_alignment.py"):
        code = _code_only(os.path.join(SERVER, name))
        assert '"template"' not in code and "'template'" not in code, \
            "%s grew a 'template' state - that is a client authoring mode, not a server fact" % name
    assert not hasattr(map_overlay, "SOURCE_TEMPLATE")
