# -*- coding: utf-8 -*-
"""「잘렸다」의 마지막 철자 셋이 정본 축-지도로 접힌다 (S-34 ② · 판정 99).

첫 커밋(`28316e71`)은 «독자 0» 인 둘만 접었다. 남은 셋은 클라 독자가 있었고, 그 독자
(`client2/src/truncation.js` 의 `saysTruncated`)가 정본 «축-지도»를 «몰랐다** — 잘린 응답에
`false` 를 돌려줬다(node 로 실측). 그래서 순서가 바뀌었다: 클라가 먼저 배우고(`187ab50d`),
서버가 «한 걸음»에 접는다. 옛 키를 남기지 않는 이유는 독자가 두 모양을 다 읽기 때문이다.

접힌 셋 — 그리고 «넷»:
    map_alignment   units_truncated · maps_truncated  -> truncated: {units, maps}
    config_explorer references_truncated              -> truncated: {references}
    transfer_plan   truncated(bool) · cells_truncated -> truncated: {units, cells}   (bins 블록)
🔴 `maps_truncated` 는 지시서 목록에 «없었다**. `units_truncated` «바로 옆»에 있었고 독자가
   0 이라, 하나만 접으면 두 철자가 나란히 남는다 — 그것이 이 라운드가 없애는 모양이다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants as ec                                     # noqa: E402
import transfer_plan                                             # noqa: E402
from test_transfer_plan import tp_env                             # noqa: F401,E402

NOTE_KEYS = {"cut", "omitted", "reason"}


def _axes(truncated):
    assert isinstance(truncated, dict), truncated
    for axis, note in truncated.items():
        assert isinstance(note, dict), (axis, note)
        assert set(note) == NOTE_KEYS, (axis, note)
    return set(truncated)


# ---------------------------------------------------------------------------
# ㉠  세 응답이 축-지도를 낸다 — 그리고 축마다 «따로» 답한다
# ---------------------------------------------------------------------------

def test_the_bins_block_speaks_two_axes(tp_env, client):
    """transfer_plan 의 bins 는 「잘렸다」를 «불리언 둘»로 말했다 — 같은 사실의 두 철자."""
    from test_transfer_plan import _seed_scenario, _seed_bins
    _seed_scenario(tp_env)
    _seed_bins(tp_env)
    res = client.get("/api/transfer-plan/source-summary",
                     params={"stage": "bonding", "lot": "TAPE-X", "slot": "01",
                             "bins": "1"})
    assert res.status_code == 200, res.text
    bins = res.json().get("bins")
    assert bins is not None, res.json()
    assert _axes(bins["truncated"]) == {"units", "cells"}, bins["truncated"]
    # 옛 철자는 «없다**.
    assert "cells_truncated" not in bins, sorted(bins)
    assert not isinstance(bins["truncated"], bool)


def test_the_unavailable_bins_block_still_answers(tp_env, client):
    """⚠️ 「못 셌다」도 «축을 싣는다** — 키가 없으면 「안 잘렸다」와 구별이 안 된다."""
    block = transfer_plan._bins_unavailable("nope", "lot", None)
    assert _axes(block["truncated"]) == {"units", "cells"}
    assert all(n["cut"] is False for n in block["truncated"].values())


# ---------------------------------------------------------------------------
# ㉢  transfer_plan 의 응답 키로서의 `truncated` 는 «불리언 0회»
# ---------------------------------------------------------------------------

def test_no_response_key_named_truncated_is_a_bare_boolean():
    """🔴 판별식은 «dict 키»다 — 지역 변수 이름은 발신자의 말이라 세지 않는다(S-5 규율).

    ⚠️ `warnings[]` 항목 «안»의 `truncated` 는 이 조사 밖이다. 그것은 응답 키가 아니라
       경고 항목의 자기 칸이고, 판정 86 ②가 `result_truncated` 를 그 이유로 닫았다.
    """
    import ast

    src = open(os.path.join(os.path.dirname(__file__), "..", "transfer_plan.py"),
               encoding="utf-8").read()
    tree = ast.parse(src)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
        if "type" in keys or "effect" in keys:
            continue                      # a warnings[] entry, not a response
        for k, v in zip(node.keys, node.values):
            if (isinstance(k, ast.Constant) and k.value == "truncated"
                    and isinstance(v, ast.Constant) and isinstance(v.value, bool)):
                offenders.append(node.lineno)
    assert offenders == [], offenders


# ---------------------------------------------------------------------------
# 저자는 «하나» — 세 모듈이 같은 함수로 짓는다
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module", ["map_alignment", "ledger.config_explorer",
                                    "transfer_plan"])
def test_every_folded_module_uses_the_one_note_builder(module):
    """축을 «손으로» 지으면 `omitted`/`reason` 규율이 모듈마다 갈린다."""
    import importlib

    mod = importlib.import_module(module)
    assert getattr(mod, "event_constants", None) is ec, (
        "%s does not reach the canonical note builder" % module)


def test_the_note_shape_is_what_the_client_reader_expects():
    """🔵 클라의 `saysTruncated` 는 «`cut` 키를 가진 값이 하나라도 있나»로 축-지도를 가른다.

    그 판별식이 서버가 짓는 모양과 맞는지를 여기서 «값으로» 못 박는다 — 두 쪽이 갈리면
    화면이 잘린 목록을 온전하다고 그리고, 오류는 0 이다.
    """
    note = ec.truncated_note(True, 3, "cap")
    assert "cut" in note and note["cut"] is True
    clean = ec.truncated_note(False)
    assert clean["cut"] is False and clean["reason"] is None
