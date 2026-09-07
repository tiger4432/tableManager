# -*- coding: utf-8 -*-
"""걷기 응답이 «아무도 안 읽는» 세대를 싣고 있었다 — 그리고 「다를 때」가 미정의였다.

```
`schema_version: 3`   독자 0 (클라 소스 · 하니스 · 계약 · 서버 시험 «전수»)
                      「2 와 3 의 차이」 미기록 · 「다르면 무엇을 하나」 미정의
형제                  파일별 schema_version 은 «이미 은퇴»했고, 문서 세대는 `setup_version` 하나가 말한다
```
🔴 읽는 이가 없고 «뜻도 안 적힌» 버전 칸은 계약이 아니라 «장식»이고, 장식은 다음 사람에게
「여기 계약이 있다」고 «거짓»을 말한다. 그래서 뺀다.

⛔ `setup_version` 을 대신 «넣지» 않는다. 세대가 필요해지는 날 먼저 적을 것은 「다를 때의
«행동»」이고 그건 계약 라운드다 — 값을 먼저 넣으면 그때 또 「읽는 이 없는 칸」이 된다.
"""
import ast
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WALK = os.path.join(SERVER, "ledger_api", "ledger_subgraph.py")
FIXTURE = os.path.abspath(os.path.join(
    SERVER, "..", "client2", "tests", "fixtures", "rnd_board_reach.json"))


def _walk_response_keys():
    """걷기 응답의 «최상위 키» — 그 반환 dict 하나를 AST 로 읽는다."""
    tree = ast.parse(open(WALK, encoding="utf-8").read())
    best = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
        if {"state", "seed", "nodes", "edges"} <= keys:
            best = keys
    assert best is not None, "the walk response dict moved; this file must follow it"
    return best


def test_the_generation_is_gone_from_the_answer():
    assert "schema_version" not in _walk_response_keys()


def test_nothing_else_moved():
    """무회귀 — 이 라운드는 «빼기»이지 «바꾸기»가 아니다."""
    keys = _walk_response_keys()
    for expected in ("state", "generated_at", "seed", "nodes", "edges", "seeds",
                     "propagation", "walk", "limits", "truncated", "message"):
        assert expected in keys, "the round took a column with it: %s" % expected


def test_the_walk_module_makes_no_other_generation_claim():
    """⚠️ «코드»에서 0 이어야 한다 — 묘비 주석은 그 자리에 «왜 없는지»를 적는 자리다."""
    src = open(WALK, encoding="utf-8").read()
    tree = ast.parse(src)
    doc = {r for n in ast.walk(tree)
           if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
           and isinstance(n.value.value, str)
           for r in range(n.lineno, (n.end_lineno or n.lineno) + 1)}
    code = "\n".join(l for i, l in enumerate(src.splitlines(), 1)
                     if i not in doc and not l.lstrip().startswith("#"))
    assert "schema_version" not in code
    assert "setup_version" not in code, \
        "a generation came back under another name; the ACTION on a mismatch comes first"


def test_the_recorded_sample_does_not_advertise_it_either():
    """🔵 기록된 응답 표본이 서버가 «안 보내는» 키를 들고 있으면 다음 독자가 속는다."""
    body = json.load(open(FIXTURE, encoding="utf-8"))
    assert "schema_version" not in body
    assert body, "the fixture emptied out - that is a different failure"


def test_the_other_subjects_keep_their_own_version():
    """⛔ 「schema_version」이라는 «낱말»을 지운 것이 아니다 — 걷기 응답의 «그 칸»을 뺀 것이다.
    설정 번들과 소스 프로필은 자기 세대를 계속 말한다(그쪽은 「다를 때」가 적혀 있다)."""
    from ledger import source_profile
    assert hasattr(source_profile, "PROFILE_SCHEMA_VERSION")
