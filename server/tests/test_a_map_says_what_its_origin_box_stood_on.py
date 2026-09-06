# -*- coding: utf-8 -*-
"""폴백이 «조용했다» — 원점 상자가 웨이퍼 원으로 물러나도 응답이 아무 말도 안 했다.

🔴 THE TWO FALLBACKS RETURN THE SAME BOX. 마스크가 «없어서» 원으로 그린 맵과, 마스크가
«있는데 이 격자를 빗나가서» 원으로 물러난 맵은 좌표가 한 글자도 다르지 않다. 그래서 상자만
보면 두 맵이 «같아 보이고», 그 둘을 가르는 것은 이름뿐이다 — 이 파일이 그 이름을 채점한다.
`test_the_two_fallbacks_return_the_same_box` 가 그 사실 자체를 못 박는다: 그 단언이 초록인
동안에는 이 칸 말고 두 상태를 가를 방법이 «없다».

⚠️ 이 라운드는 «말하기»이지 «바꾸기»가 아니다. 상자 값은 넷 다 오늘과 같고,
`test_the_boxes_are_what_they_were` 가 그것을 네 갈래 «전부»에서 못 박는다.

🔵 그리고 판정은 «한 자리»다 — `origin_box` 는 `origin_box_with_basis` 의 앞 절반이라
상자와 그 상자의 이름이 갈릴 수 없다. 두 번째로 유도하면 갈려도 «오류가 안 난다».
"""
import ast
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import map_overlay                                                # noqa: E402

#: 300mm 웨이퍼에 60mm 칩 — 원이 6x6 격자를 «세게» 자른다(36칸 중 12칸).
#: 안 자르는 픽스처를 쓰면 원 구현과 마스크 구현이 «우연히» 같은 답을 낸다.
PHYS = {"phys_wafer_dia": 300.0, "phys_chip_x": 60.0, "phys_chip_y": 60.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}
GRID6 = {"grid_cols": 6, "grid_rows": 6, "grid_start_x": 1, "grid_start_y": 1,
         "grid_y_invert": False, "side": "front", "rotation": 0, **PHYS}

#: 이 격자 «안»에 앉는 마스크 — 상자를 마스크가 정한다.
HITS = map_overlay.die_mask_from_reference(GRID6, {(2, 2), (3, 3), (2, 3)})
#: 마스크는 «있는데» 이 격자를 빗나간다. 참조가 60x60 격자라 물리 인덱스가 멀리 앉는다.
MISSES = map_overlay.die_mask_from_reference(dict(GRID6, grid_cols=60, grid_rows=60),
                                             {(40, 40), (41, 41)})


def _basis(meta, mask=None):
    #: 나르개가 부르는 그 철자로 재다.
    return map_overlay.origin_box_basis(meta, mask)


# ------------------------------------------------ ① 갈림 — 두 이름이 «어긋나는» 그 자리

def test_a_map_whose_reference_resolved_can_still_stand_on_the_circle():
    """🔴 THE ROUND'S DISCRIMINANT (판정 48). `SOURCE_REF` 는 「«마스크»가 어디서 왔나」이고
    이 칸은 「«상자»가 무엇 위에 섰나」다. 같은 맵에서 «둘이 어긋난다» — 참조는 풀렸는데
    상자는 원이다. 그래서 이 칸은 `SOURCE_*` 의 사본이 아니다.

    ⛔ 두 이름이 «같은 답을 내는» 표본으로는 이것을 증명하지 못한다(같은 답을 내는 표본은
       판별식이 아니다). 그래서 여기서 둘을 «나란히» 잰다."""
    meta = dict(GRID6, valid_die_ref="TPL_1")
    resolved = map_overlay.resolve_valid_die_basis(meta, lambda ref: {(2, 2)})

    assert resolved["source"] == map_overlay.SOURCE_REF
    assert _basis(meta, MISSES) == map_overlay.ORIGIN_BOX_MASK_OFF_GRID
    assert resolved["source"] != _basis(meta, MISSES), \
        "the two names never disagree — this column would be a copy of SOURCE_*"


def test_the_mask_decides_when_it_sits_on_this_grid():
    assert _basis(GRID6, HITS) == map_overlay.ORIGIN_BOX_MASK


def test_no_mask_at_all_is_the_circle():
    """가장 흔한 정상 상태다 — 「거절」이 아니라 「선언이 없다」."""
    assert _basis(GRID6, None) == map_overlay.ORIGIN_BOX_CIRCLE
    assert _basis(GRID6, frozenset()) == map_overlay.ORIGIN_BOX_CIRCLE


def test_a_map_with_no_grid_has_no_box_at_all():
    """격자 없는 맵은 `maps[]` 에 «실재로» 들어온다(§stamp_meta_refusal 이 `meta is None` 을
    다룬다). 값이 없으면 그 칸의 «부재»가 「옛 서버」와 「상자가 없는 맵」 «둘»을 뜻하게 된다."""
    assert _basis(None) == map_overlay.ORIGIN_BOX_ABSENT
    assert _basis({}) == map_overlay.ORIGIN_BOX_ABSENT
    assert _basis({"rotation": 0}) == map_overlay.ORIGIN_BOX_ABSENT


# ------------------------------------------------ ② 이 라운드가 «존재하는 이유»

def test_the_two_fallbacks_return_the_same_box():
    """🔴 여기가 「조용하다」의 정의다. 마스크가 없어서 원인 맵과, 마스크가 빗나가서 원인
    맵은 «좌표가 같다». 그러므로 이 칸이 없으면 두 상태를 «가를 수단이 없다»."""
    circle, circle_name = map_overlay.origin_box_with_basis(GRID6, None)
    missed, missed_name = map_overlay.origin_box_with_basis(GRID6, MISSES)

    assert circle == missed, "the fixture is not exercising the silence"
    assert circle_name != missed_name


# ------------------------------------------------ ③ 무회귀 — «말하기»이지 «바꾸기»가 아니다

def test_the_boxes_are_what_they_were():
    """네 갈래 «전부». 한 갈래만 재면 옮겨진 갈래를 못 본다."""
    assert map_overlay.origin_box(GRID6, HITS) == (2, 3, 2, 3)
    assert map_overlay.origin_box(GRID6, MISSES) == (1, 4, 1, 4)
    assert map_overlay.origin_box(GRID6, None) == (1, 4, 1, 4)
    assert map_overlay.origin_box(None) is None


def test_the_name_only_spelling_agrees_wherever_the_box_exists():
    """이름«만» 내는 철자가 «다른 판정»이 되면 안 된다 — 상자가 서는 메타에서는
    짝의 이름과 한 글자도 달라선 안 되고, 안 서는 메타에서만 총체적이다."""
    for meta in (GRID6, dict(GRID6, rotation=270), dict(GRID6, side="back")):
        for mask in (HITS, MISSES, None):
            assert map_overlay.origin_box_basis(meta, mask) == (
                map_overlay.origin_box_with_basis(meta, mask)[1])


def test_the_name_answers_where_the_box_itself_refuses():
    """🔴 나르개가 «오늘 도는 화면»을 500 으로 만들지 않는다. 기하가 못 서는 맵은
    응답에 «정상적으로» 들어오고(`GEOMETRY_UNPARSABLE` 이 그래서 있다), `origin_box` 는
    그런 메타에 던진다 — 그 거절은 «그대로 둔다»(§`origin_box_basis`)."""
    broken = dict(GRID6, phys_wafer_dia=None)
    try:
        map_overlay.origin_box(broken)
    except (TypeError, ValueError):
        pass
    else:
        raise AssertionError("origin_box stopped refusing - dt_frame_transform pairs boxes "
                             "and a one-sided None is a silently wrong transform")
    assert map_overlay.origin_box_basis(broken) == map_overlay.ORIGIN_BOX_ABSENT


def test_the_box_half_is_the_first_element_of_the_pair():
    """두 철자가 «갈릴 수 없다»는 것 — `origin_box` 가 이 함수의 앞 절반이다."""
    for mask in (HITS, MISSES, None):
        assert map_overlay.origin_box(GRID6, mask) == \
            map_overlay.origin_box_with_basis(GRID6, mask)[0]


# ------------------------------------------------ ④ 모양 — «맵당 한 칸», 그리고 «항상» 온다

def test_the_value_is_one_string_per_map():
    """dict 로 자라면 40맵에서 payload 가 +72% 라는 것을 나르개 블록이 적어 두었다."""
    for mask in (HITS, MISSES, None, frozenset()):
        assert isinstance(_basis(GRID6, mask), str)
    assert isinstance(_basis(None), str)


def test_the_token_is_never_absent_so_a_missing_field_means_an_old_server():
    """🔴 이것이 「값이 셋」의 «근거»다(판정 48). 어떤 메타를 줘도 이름이 나온다 — 그래야
    화면에서 그 칸의 «없음»이 「옛 서버」 «하나»만 뜻한다."""
    junk = [None, {}, {"grid_cols": "x"}, {"grid_cols": 6},
            {"grid_cols": 6, "grid_rows": 6},          # 격자는 있는데 규격이 없다
            GRID6, dict(GRID6, rotation=270), dict(GRID6, side="back"),
            dict(GRID6, phys_wafer_dia=None),          # 🔴 `origin_box` 는 이 넷에 던진다
            dict(GRID6, phys_chip_x="n"),
            {k: v for k, v in GRID6.items() if k != "phys_edge_margin"}]
    names = {map_overlay.ORIGIN_BOX_MASK, map_overlay.ORIGIN_BOX_CIRCLE,
             map_overlay.ORIGIN_BOX_MASK_OFF_GRID, map_overlay.ORIGIN_BOX_ABSENT}
    for meta in junk:
        for mask in (HITS, MISSES, None):
            got = map_overlay.origin_box_basis(meta, mask)
            assert got in names, (meta, mask, got)


# ------------------------------------------------ ⑤ 철자 하나 — 나르개가 «그 함수»를 부른다

def _code_only(path):
    """🔴 인용은 호출이 아니다. 주석과 docstring 을 «먼저» 걷어낸다 — 이 저장소가 세 번
    값을 치른 자리다(설명하는 문장이 자기가 설명하는 낱말을 들고 있다)."""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    spans = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            spans.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return "\n".join(line for n, line in enumerate(src.splitlines(), 1)
                     if n not in spans and not line.lstrip().startswith("#"))


def test_the_carrier_calls_the_one_decision_site():
    """나르개가 «자기 판정»을 쓰면 상자와 이름이 갈릴 수 있고, 갈려도 오류가 안 난다."""
    body = _code_only(os.path.join(os.path.dirname(__file__), "..", "map_alignment.py"))
    assert "origin_basis=map_overlay.origin_box_basis(" in body, \
        "the maps[] row no longer carries the column"
    assert body.count("origin_box_basis(") == 1 and "origin_box_with_basis(" not in body, \
        "a second caller derives the name — two spellings of one predicate"


def test_the_contract_trio_did_not_grow_a_fourth_value():
    """⛔ `SOURCE_*` 는 계약 심볼이고 클라 `validDieBasis()` 가 «같은 벡터»로 채점된다.
    거기에 값을 더하는 것이 판정 29 가 막은 그 부류다."""
    assert (map_overlay.SOURCE_REF, map_overlay.SOURCE_CIRCLE,
            map_overlay.SOURCE_REFUSED) == ("ref", "circle", "refused")
    body = _code_only(map_overlay.__file__)
    assert body.count("SOURCE_CIRCLE = ") == 1 and body.count("SOURCE_REF = ") == 1
