# -*- coding: utf-8 -*-
"""한 불리언이 «두 질문»에 답하던 자리 — 「정렬 결정이 있나」와 「사람이 확정했나」.

🔴 THE WORKLIST CALLED A MAP PENDING AND THE OVERLAY CALLED THE SAME MAP CONFIRMED, and both
were reading the same mark. The mark itself already separates them: the human path writes
`confirmation_uid` (the key of the confirmation ROW) plus `confirmed_by`/`confirmed_at`, and
the two chain mappers (`chain_alignment`, `chain_core_alignment`) write their own name and
NOT those three. What lied was neither writer — it was the reading line that folded the mark
with `bool()`.

⚠️ THE TOKEN IS NOT SPLIT. `GEOMETRY_CONFIRMED` is read as a TRUST token by
`map_alignment` (`:516`, `:4751`); moving it would move that ruling too, and that is a map
domain question with no precedent (ruling 29). A field is added instead, and the most
important assertion in this file is the one that says the token did not move.

🔵 그리고 판정은 «한 자리»다. The same question is needed per-axis (`orientation_declaration`)
and per-map (`maps[]`), and two spellings of one predicate is the shape this repository spent
tonight closing — `_bare` under one name with four bodies.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import map_overlay                                                # noqa: E402

KEY = map_overlay.FRAME_CONFIRMED_KEY

#: 사람이 확정한 표지 — `frame_confirmation.py` 가 싣는 셋.
PERSON = {"confirmation_uid": "conf-1", "confirmed_by": "kk", "confirmed_at": "2026-09-07"}
#: 체인 맵퍼가 남기는 표지 — 자기 이름뿐이고 그 셋이 «없다».
CHAIN = {"source": "chain_alignment"}


def meta(mark=None, **extra):
    m = {"rotation": 90, "side": "front"}
    if mark is not None:
        m[KEY] = mark
    m.update(extra)
    return m


# ------------------------------------------------------------------ the question itself

def test_a_person_mark_answers_yes():
    assert map_overlay.confirmed_by_person(meta(PERSON)) is True


def test_a_chain_mark_answers_no():
    """🔴 THE WHOLE ROUND. This is the map the worklist calls pending; the answer here has to
    agree with it."""
    assert map_overlay.confirmed_by_person(meta(CHAIN)) is False


def test_no_mark_at_all_answers_no():
    assert map_overlay.confirmed_by_person(meta()) is False
    assert map_overlay.confirmed_by_person({}) is False
    assert map_overlay.confirmed_by_person(None) is False


def test_a_mark_that_is_not_a_dict_answers_no_rather_than_throwing():
    """A mark written by an older writer, or a bare string, must not take the read down with
    it — an alignment answer that throws is worse than one that says 「no」."""
    for junk in ("confirmed", 1, [], True):
        assert map_overlay.confirmed_by_person(meta(junk)) is False


def test_the_answer_is_a_boolean_not_the_mark():
    """⚠️ ONE BOOLEAN, PER THE ORDER. A dict, a reason string or a person's name here would be
    the shape the payload note under `maps[]` refuses: 40 maps carrying axis dicts grew a
    cell-less payload by 72%, and the same argument applies to this field."""
    assert isinstance(map_overlay.confirmed_by_person(meta(PERSON)), bool)


# ------------------------------------------- 🔴 the no-regression that matters most

def test_the_trust_token_still_attaches_to_both_kinds_of_map():
    """🔴 GATE ㉡. `GEOMETRY_CONFIRMED` must land on exactly the maps it landed on before —
    the human-marked one AND the chain-marked one. If this round had moved the token instead
    of adding a field, `map_alignment`'s trust ruling would have moved with it."""
    for mark in (PERSON, CHAIN):
        declared = map_overlay.orientation_declaration(meta(mark))
        for axis in ("rotation", "side"):
            assert declared[axis]["source"] == map_overlay.GEOMETRY_CONFIRMED, (mark, axis)


def test_and_the_new_field_is_what_separates_them():
    """The token is the same for both; the field is not. That pair is the repair."""
    person = map_overlay.orientation_declaration(meta(PERSON))
    chain = map_overlay.orientation_declaration(meta(CHAIN))
    assert person["rotation"]["source"] == chain["rotation"]["source"]
    assert person["rotation"]["confirmed_by_person"] is True
    assert chain["rotation"]["confirmed_by_person"] is False


def test_an_unreadable_value_is_still_not_promoted_by_a_confirmation():
    """No-regression on the older rule: a confirmation must not turn a value that cannot be
    read into a confirmed one."""
    declared = map_overlay.orientation_declaration(
        {"rotation": "nonsense", "side": "front", KEY: PERSON})
    assert declared["rotation"]["source"] == map_overlay.GEOMETRY_UNPARSABLE
    assert "confirmed_by_person" not in declared["rotation"]


# --------------------------------------------------------------- one place, two callers

def _code_only(text):
    """🔴 COMMENTS ARE NOT CODE, AND THIS IS THE THIRD TIME TONIGHT. The C-33 counter read
    four retired bodies quoted in a docstring; the S-5 harness found a dead spelling in the
    repair's own citation of it; and the first spelling of the two assertions below found
    `confirmation_uid` in the comment that EXPLAINS why the key is not tested here. A citation
    is not a call, and an assertion that cannot tell them apart is measuring prose.
    """
    kept = []
    for line in text.split("\n"):
        if line.strip().startswith("#"):
            continue
        kept.append(line.split("  #")[0])
    return "\n".join(kept)


def _without_docstring(function):
    import ast

    tree = ast.parse(function.lstrip())
    node = tree.body[0]
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)):
        node.body = node.body[1:]
    return ast.unparse(node)


def test_the_per_axis_reader_goes_through_the_same_place():
    """🔴 ASSERTED ON THE CODE, BECAUSE SHARING IS THE PROPERTY. Two spellings that agree
    today is precisely what `_bare` was, and a behaviour test would pass just as well if the
    predicate had been copied into the alignment payload."""
    import inspect

    body = _code_only(_without_docstring(
        inspect.getsource(map_overlay.orientation_declaration)))
    assert "confirmed_by_person(" in body
    assert "confirmation_uid" not in body, "the axis reader spells the test again"


def test_the_per_map_field_goes_through_it_too():
    import inspect

    import map_alignment

    src = _code_only(inspect.getsource(map_alignment))
    assert "map_overlay.confirmed_by_person(" in src, \
        "the per-map field does not come from the one place"
    assert src.count('"confirmation_uid"') == 0
