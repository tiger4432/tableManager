# -*- coding: utf-8 -*-
"""저장되는 DT/core 식이 «어느 상자 위에서» 나왔는지를 한 칸도 말하지 않았다.

🔴 S-19 의 셋째 자리다. 거기서 센 폴백 넷 중 이것이 «제일 조용»했다 — 이 파일에는 `logger`
호출이 «하나도» 없고(앞의 둘은 warning·info 를 낸다), 걸리는 것이 «응답»이 아니라 «저장»이다.
`dt_x_*`·`core_*` 여섯 칸이 그 상자 위에서 만들어져 메타에 «적힌다».

🔴 그리고 「빗나감」과 「마스크 없음」은 «같은 식»을 만든다. 마스크가 이 격자를 빗나가면 원점
상자가 웨이퍼 원으로 물러나고, 그건 마스크가 «아예 없을» 때와 같은 상자다. 그러므로 저장된
여섯 칸만 보면 두 경우가 «구별되지 않는다» — 그 사실 자체를 아래에서 못 박는다.

⛔ 토큰을 «새로 짓지 않는다». S-19 이 `map_overlay` 에 둔 그 어휘를 그대로 쓴다 — 그 자리에
둔 이유가 「응답 경로와 저장 메타 경로가 «둘 다» import 한다」였고, 여기가 그 둘째 경로다.
"""
import ast
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import dt_frame_transform                                        # noqa: E402
import map_overlay                                               # noqa: E402

PHYS = {"phys_wafer_dia": 300.0, "phys_chip_x": 60.0, "phys_chip_y": 60.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}
BASE0 = {"grid_cols": 6, "grid_rows": 6, "grid_start_x": 1, "grid_start_y": 1,
         "grid_y_invert": False, "side": "front", "rotation": 0, **PHYS}

#: ROTATION 90, NOT 0. At rotation 0 / front the subject IS the standard frame, so the two
#: boxes cancel and the equation does not depend on the box at all -- every case comes back
#: `X,1,0,Y,1,0` and the whole file would assert nothing.  Measured: rotation 0/front and
#: 270/back are the two degenerate frames; the other six let the box through.
FRAME = dict(BASE0, rotation=90)

#: 이 격자 «안»에 앉는 참조.
HIT_META, HIT_CELLS = dict(BASE0), [(2, 2), (3, 3), (2, 3)]
#: 마스크는 «있는데» 이 격자를 빗나간다 — 참조가 60x60 이라 물리 인덱스가 멀리 앉는다.
MISS_META, MISS_CELLS = dict(BASE0, grid_cols=60, grid_rows=60), [(40, 40), (41, 41)]

EQUATION_KEYS = ("dt_x_base", "dt_x_sign", "dt_x_offset",
                 "dt_y_base", "dt_y_sign", "dt_y_offset")

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample",
                      "table_config.json.sample")


def _dt(frame=None, basis_meta=None, basis_cells=None):
    return dt_frame_transform.dt_equations(dict(frame or FRAME), basis_meta, basis_cells)


# ================================================ 1. 갈림 — 셋이 «다른» 답을 낸다

def test_the_three_origins_are_named_apart():
    assert _dt(basis_meta=HIT_META, basis_cells=HIT_CELLS)["dt_origin_basis"] \
        == map_overlay.ORIGIN_BOX_MASK
    assert _dt(basis_meta=MISS_META, basis_cells=MISS_CELLS)["dt_origin_basis"] \
        == map_overlay.ORIGIN_BOX_MASK_OFF_GRID
    assert _dt()["dt_origin_basis"] == map_overlay.ORIGIN_BOX_CIRCLE


def test_the_silence_this_round_removes(self=None):
    """🔴 이 라운드가 «존재하는 이유». 빗나간 경우와 참조가 «없는» 경우는 저장되는 여섯 칸이
    «한 글자도» 다르지 않다. 그러므로 이 칸이 없으면 두 상태를 가를 방법이 «없다»."""
    missed = _dt(basis_meta=MISS_META, basis_cells=MISS_CELLS)
    none = _dt()

    assert [missed[k] for k in EQUATION_KEYS] == [none[k] for k in EQUATION_KEYS], \
        "the fixture is not exercising the silence"
    assert missed["dt_origin_basis"] != none["dt_origin_basis"]


# ================================================ 2. 무회귀 — «말하기»이지 «바꾸기»가 아니다

def test_the_six_equation_columns_are_unchanged():
    """마스크가 «앉는» 경우만 식이 달라야 한다 — 그것이 이 상자 갈래가 존재하는 이유다."""
    hit = _dt(basis_meta=HIT_META, basis_cells=HIT_CELLS)
    none = _dt()
    for key in EQUATION_KEYS:
        assert key in hit and key in none, "an equation column disappeared: %s" % key
    assert [none[k] for k in EQUATION_KEYS] == [
        "Y", 1, 0, "X", -1, 5], "the no-reference equation moved"


def test_the_mask_answer_means_the_mask_really_moved_the_equation():
    """🔴 이 칸이 «거짓»이 될 수 있는 자리. 「마스크 위에 섬다」고 말하면서 식은 원
    상자로 나올 수 있고, 그러면 오류 없이 «조용히 틀린» 칸이 된다."""
    hit = _dt(basis_meta=HIT_META, basis_cells=HIT_CELLS)
    none = _dt()
    assert hit["dt_origin_basis"] == map_overlay.ORIGIN_BOX_MASK
    assert [hit[k] for k in EQUATION_KEYS] != [none[k] for k in EQUATION_KEYS],         "the column says 'mask' but the equation is the circle one"
    #: AND THE WHOLE PAIR, NOT JUST "different".  A one-sided box (source solved against the
    #: mask, target still on the circle) is ALSO different from the circle answer, so "!=" 
    #: alone lets it through -- measured: that mutant escaped this assertion.  A one-sided
    #: box is the silently wrong transform `origin_box_basis` refuses to create.
    assert [hit[k] for k in EQUATION_KEYS] == ["Y", 1, 0, "X", -1, 3],         "the equation is not the one BOTH mask boxes give"


# ================================================ 3. 한 칸인데 상자가 «둘»이다

def test_the_two_boxes_never_disagree():
    """🔴 한 칸으로 «둘»을 말해도 되는 근거. 프레임을 바꿔도 격자의 «물리» 발자국은 안 움직이고
    마스크는 물리 공간에 산다. 그날이 오면 이 단언이 말한다 — 칸이 조용히 한쪽만 말하지 않는다."""
    seen = set()
    for rot in (0, 90, 180, 270):
        for side in ("front", "back"):
            for invert in (False, True):
                frame = dict(FRAME, rotation=rot, side=side, grid_y_invert=invert)
                target = dt_frame_transform.standard_meta(frame)
                for cells, meta in ((HIT_CELLS, HIT_META), (MISS_CELLS, MISS_META), (None, None)):
                    mask = (map_overlay.die_mask_from_reference(meta, cells) or None
                            if cells else None)
                    source_basis = map_overlay.origin_box_basis(frame, mask)
                    seen.add(source_basis)
                    assert source_basis == map_overlay.origin_box_basis(target, mask), \
                        "source and target stood on DIFFERENT boxes: %s" % ((rot, side, invert),)
    assert len(seen) == 3, "the sweep did not exercise all three answers: %s" % seen


# ================================================ 4. 판정은 «한 자리»에서 온다

def test_core_carries_the_same_answer_dt_gave():
    dt = _dt(basis_meta=MISS_META, basis_cells=MISS_CELLS)
    core = dt_frame_transform.core_equations(dict(FRAME), MISS_META, MISS_CELLS)
    assert core["core_origin_basis"] == dt["dt_origin_basis"]


def test_this_file_never_spells_a_token_itself():
    """⛔ 「토큰은 같은 것을 쓴다」는 «의도»로는 안 지켜진다. 리터럴이 «없어야» 지켜진다."""
    path = os.path.join(os.path.dirname(__file__), "..", "dt_frame_transform.py")
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    doc = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            doc.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    lines = src.splitlines()
    code = "\n".join(l for n, l in enumerate(lines, 1)
                     if n not in doc and not l.lstrip().startswith("#"))
    for spelling in ("mask_off_grid", '"circle"', '"absent"', '"mask"'):
        assert spelling not in code, "a second spelling of the token: %s" % spelling
    assert "map_overlay.origin_box_basis(" in code


# ================================================ 5. 선언이 없으면 «조용히 버려진다»

def test_the_shipped_declaration_carries_the_column():
    """🔴 `crud` 는 선언에 없는 칸을 «버린다»(`DROP_UNDECLARED_COLUMN`) — 거절이 아니라 «드롭»이다.
    그러므로 이 칸을 «내기만» 하면 착지는 하고 아무 데도 안 실린다.
    ⚠️ 두 줄 답: 「`dt_x_base` 를 적은 표에 `dt_origin_basis`(문자열) 한 칸을 더 적으면 됩니다」.
       이 시험은 «출하본»이 그 답을 지키는지만 잰다 — 라이브 선언은 조작자의 것이고 안 건드린다."""
    cfg = json.load(open(SAMPLE, encoding="utf-8"))
    checked = 0
    for table in cfg.values():
        cols = (table or {}).get("column_types") or {}
        if "dt_x_base" in cols:
            assert cols.get("dt_origin_basis") == "string", \
                "a table declares the equation and not the box it stood on"
            checked += 1
        if "core_x_base" in cols:
            assert cols.get("core_origin_basis") == "string"
    assert checked >= 1, "the sample stopped declaring the equation columns at all"
