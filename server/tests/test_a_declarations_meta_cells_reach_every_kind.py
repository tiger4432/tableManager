# -*- coding: utf-8 -*-
"""판정 640 — 통합 선언의 «메타 칸»이 종류에 상관없이 규칙에 실린다.

> 소유자: 「ㄴ으로 해 문 하나 무조건, 이후 가드는 그 위에 올리기」
> 소유자: 「하위 레벨에서 분기를 두지마 같은 로직으로 짜고 상위 계층에서 제어해」

🔴 THE DEFECT, MEASURED BEFORE THE FIX. `expand_declaration` had two arms: join and mapper
went through `as_chain_rule`, which merged `limits` · `extra` · `axis` · `enabled`; `decide`
returned BEFORE that line. So the same four cells, written at the top level of the same
grammar, reached two kinds and vanished for the third - and `notes` said nothing, while an
unknown cell INSIDE `derive.decide` was named. The control below is the sharpest form: an
author writing `allow_chain_trigger: false` on a decide declaration got `true`.

⚠️ THE TABLE HAS NO BLANK CELLS ON PURPOSE (판정 640). A row left out reads as 「통과」, and
the two 「안 적었을 때」 rows are the ones that would be: they assert the values the PRODUCT
chooses are still the product's, because a merge that fires unconditionally is exactly the
kind of change that could overwrite them with `None`.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import rule_shape                                         # noqa: E402

DECIDE = {"name": "m640", "on": {"table": "m640_src"}, "into": {"table": "m640_dst"},
          "derive": {"kind": "decide",
                     "decide": {"key": ["k"], "fields": ["f"], "auto_confirm": True}}}

JOIN = {"name": "m640_join", "on": {"table": "L"}, "into": {"table": "L"},
        "derive": {"kind": "join", "join": {
            "right_table": "R", "on": [{"left": "a", "right": "a"}],
            "take": [{"from": "b", "into": "c"}]}}}

MAPPER = {"name": "m640_mapper", "on": {"table": "L"}, "into": {"table": "L"},
          "derive": {"kind": "mapper", "mapper": {
              "mapper_module": "x", "mapper_function": "y"}}}

#: 최상위에 적는 «메타 칸» 넷. 문법이 아는 축(`is_batch`)과 모르는 칸(`extra`)을 같이 싣는다.
WRITTEN = {"allow_chain_trigger": False, "is_batch": False,
           "limits": {"idempotent": True, "max_group_rows": 7},
           "extra": {"note_x": "hello"}}


def _stood(declaration, written=None):
    raw = dict(declaration)
    raw.update(written or {})
    stood, refusal, notes = rule_shape.expand_declaration(raw, None)
    assert refusal is None, refusal
    return {rule["name"]: rule for rule in stood}, notes


def _halves(written=None):
    rules, notes = _stood(DECIDE, written)
    return (rules["enrichment_dedup:m640"],
            rules["enrichment_auto_confirm:m640"], notes)


# ---------------------------------------------------------------------------
# 표 — decide 의 두 반쪽 × 적었을 때 / 안 적었을 때
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("half", ["dedup", "auto_confirm"])
def test_a_written_meta_cell_reaches_both_halves_of_decide(half):
    """🔴 이 파일의 주제. 넷 다, 반쪽 둘 다."""
    dedup, confirm, _notes = _halves(WRITTEN)
    rule = dedup if half == "dedup" else confirm

    assert rule["allow_chain_trigger"] is False, half
    assert rule["is_batch"] is False, half
    assert rule["idempotent"] is True, half
    assert rule["max_group_rows"] == 7, half
    assert rule["note_x"] == "hello", half


def test_the_dedup_half_keeps_the_products_answers_when_nothing_was_written():
    """⚠️ 「안 적었을 때」는 «빈 칸»이 아니라 단언이다 — 무조건 도는 합치기가 제품의 답을
    `None` 으로 덮을 수 있는 자리이고, 그 회귀는 조용하다."""
    dedup, _confirm, _notes = _halves()

    assert "allow_chain_trigger" not in dedup, (
        "dedup 반쪽은 체인 트리거를 «선언하지 않는» 것이 오늘의 값이다")
    assert dedup["is_batch"] is True
    assert "idempotent" not in dedup and "note_x" not in dedup


def test_the_auto_confirm_half_keeps_the_products_answers_when_nothing_was_written():
    _dedup, confirm, _notes = _halves()

    assert confirm["allow_chain_trigger"] is True, (
        "auto-confirm 은 dedup 의 쓰기가 깨우므로 «제품이» 켜 둔다")
    assert confirm["is_batch"] is True
    assert "idempotent" not in confirm and "note_x" not in confirm


# ---------------------------------------------------------------------------
# 🔴 대조군 — 이 결함의 «자기 증상»
# ---------------------------------------------------------------------------

def test_writing_the_opposite_is_not_silently_flipped():
    """⚰️ 이 줄이 이 라운드 «전»의 증상이다: 운영자가 `false` 라고 «반대»를 적어도 결과가
    `true` 였고, notes 도 비어 있었다. 되돌아오면 이 줄이 먼저 운다."""
    dedup, confirm, _notes = _halves({"allow_chain_trigger": False})

    assert dedup.get("allow_chain_trigger") is False
    assert confirm.get("allow_chain_trigger") is False


def test_the_same_cells_still_reach_join_and_its_reference_side_and_mapper():
    """⚠️ 회귀 칸. 640 이 「join · join:reference · mapper 는 오늘과 같음」이라 적었고,
    이 파일이 그것을 «단언»한다 — 좌석을 빼면서 그쪽을 잃으면 여기서 빨개진다."""
    joins, _notes = _stood(JOIN, {"allow_chain_trigger": True,
                                  "limits": {"idempotent": True}})

    assert sorted(joins) == ["m640_join", "m640_join:reference"]
    for name, rule in joins.items():
        assert rule["allow_chain_trigger"] is True, name
        assert rule["idempotent"] is True, name

    mappers, _notes = _stood(MAPPER, {"is_batch": False})

    assert list(mappers) == ["m640_mapper"]
    assert mappers["m640_mapper"]["is_batch"] is False


# ---------------------------------------------------------------------------
# ⚠️ 좌석 자신
# ---------------------------------------------------------------------------

def test_the_merge_is_safe_to_apply_twice():
    """🔴 이것이 「종류를 묻지 않고 전부에 적용」을 «가능하게» 하는 성질이다. 이 성질이
    깨지면 좌석은 「이 팔은 이미 했나」를 물어야 하고, 그 물음이 문을 다시 가른다."""
    internal = rule_shape.from_declaration(dict(DECIDE, **WRITTEN))
    once = rule_shape.with_declared_cells({"name": "x"}, internal)
    twice = rule_shape.with_declared_cells(dict(once), internal)

    assert once == twice


def test_the_grammars_own_axis_still_wins_over_a_hand_written_extra():
    """🔴 [판정 551] 순서는 «안 바뀌었다» — `axis` 가 마지막이다. 종전에 `extra` 가 `axis` 를
    덮어, 운영자가 「한 행씩」이라 선언한 규칙이 배치로 불렸다."""
    internal = rule_shape.from_declaration(
        dict(DECIDE, is_batch=False, extra={"is_batch": True}))

    merged = rule_shape.with_declared_cells({}, internal)

    assert merged["is_batch"] is False
