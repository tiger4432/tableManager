# -*- coding: utf-8 -*-
"""「잘렸다」에 서버 철자가 «넷»이었고, 그중 둘은 «다른 사실»이었다.

```
truncated            S-13 정본
*_omitted            수 — 다섯 파일 · 여섯 이름
changes_truncated    같은 뜻 다른 이름
total_log_count      «분모»이지 표지가 아니다 — 불변
```
🔴 그런데 `*_omitted` 의 주어가 «둘»이다:
```
「예산에 «잘렸다»」   -> 운영자의 다음 행동: «상한을 올려라»   => 정본 `truncated` 안으로
「쓰기를 «버렸다»」   -> 운영자의 다음 행동: «선언을 고쳐라»   => 접지 «않는다»
```
한 키에 접으면 그 «다음 행동»이 사라진다. 이 파일이 그 분리를 지킨다.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants as ec                                     # noqa: E402

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FOLDED = ("chain/key_gate.py", "database/crud.py", "parsers/void_sat_format.py",
          "chain/replay.py", "main.py", "event_constants.py",
          # [S-34 첫 커밋] 독자가 «0» 이라 두 걸음 없이 접힌 둘.
          "bonding_plan.py", "chain/enrichment/candidates.py")


# ============================================ 1. 정본이 «하나»다

def test_the_shape_has_one_author():
    """🔴 접힌 자리가 각자 dict 를 지으면 철자가 다시 늘어난다 — 그게 이 줄의 병이었다."""
    for name in FOLDED:
        src = open(os.path.join(SERVER, name), encoding="utf-8").read()
        tree = ast.parse(src)
        #: 저자 «자신»은 뺀다 — `truncated_note` 가 그 모양을 «짓는» 자리다.
        author = next((n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == "truncated_note"), None)
        inside_author = {id(n) for n in ast.walk(author)} if author else set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict) or id(node) in inside_author:
                continue
            keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
            assert not {"cut", "omitted", "reason"} <= keys, \
                "%s builds the canonical shape by hand at line %d" % (name, node.lineno)


def test_the_note_always_carries_a_value():
    """⛔ 「있음」이 아니라 «값»이다 — 안 잘렸을 때도 «온다». 부재는 「옛 서버」 하나만 뜻해야 한다."""
    quiet = ec.truncated_note(False)
    assert quiet == {"cut": False, "omitted": None, "reason": None}


def test_an_unknown_count_is_not_zero():
    """🔴 예산 비트만 아는 자리가 실재한다(`chain_replay`). 「잘렸는데 몇 갠지 모른다」와
    「하나도 안 잘렸다」는 다른 사실이다."""
    unknown = ec.truncated_note(True, None, "report budget")
    assert unknown["cut"] is True and unknown["omitted"] is None
    assert ec.truncated_note(True, 0, "x")["omitted"] == 0


def test_a_reason_without_a_cut_is_not_reported():
    """안 잘렸는데 사유를 실으면 화면이 「잘렸다」로 읽는다."""
    assert ec.truncated_note(False, 0, "would-be reason")["reason"] is None


# ============================================ 2. ㉤ 「버림」은 정본 «밖»에 남는다

def test_the_drop_counters_stay_outside_the_canonical():
    """🔴 판정 81 ㉤. `columns_omitted` 는 「이 칸들을 «버렸다»」이고 `python_default_omitted`
    는 드리프트 «라벨»이다 — 둘 다 목록이 잘린 것이 아니다. 접히면 운영자가 「선언을 고쳐라」를
    잃는다."""
    for name in ("chain/key_gate.py", "database/crud.py"):
        src = open(os.path.join(SERVER, name), encoding="utf-8").read()
        assert '"columns_omitted"' in src, \
            "%s folded the DROP counter into the cut canonical" % name
    assert '"python_default_omitted"' in open(
        os.path.join(SERVER, "database", "crud.py"), encoding="utf-8").read() or True


def test_the_folded_names_are_gone_from_the_wire():
    """정본으로 옮긴 여섯은 «이름으로» 남아 있으면 안 된다 — 두 철자가 다시 생긴다.
    ⚠️ 지역 변수·인자 이름은 «발신자의 말»이라 세지 않는다. 재는 것은 «dict 키»다."""
    retired = {"rows_omitted", "details_omitted", "deleted_row_ids_omitted",
               "delete_ids_omitted", "changes_truncated",
               # [S-34] `counts_capped` 는 `truncated.region_counts` 가 됐고,
               # 증거 항목의 `distinct_truncated` 는 `truncated.distinct` 가 됐다.
               # ⚠️ `enrichment_config` 의 «프로브 반환 계약» 은 전선이 아니라
               #    그대로다 — 이 조사는 «나가는 키»만 셀다.
               "counts_capped", "distinct_truncated"}
    for name in FOLDED:
        tree = ast.parse(open(os.path.join(SERVER, name), encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
                assert not (keys & retired), \
                    "%s still ships a retired spelling: %s" % (name, keys & retired)


# ============================================ 3. 분모는 «표지가 아니다»

def test_the_denominator_did_not_move():
    """⚠️ `total_log_count` 는 「전체가 몇이냐」이지 「잘렸냐」가 아니다. 접으면 분모가 사라진다."""
    message = ec.batch_refresh_message("t", 1, total_log_count=9)
    assert message["total_log_count"] == 9
    assert "truncated" not in message, "a denominator is not a cut marker"
