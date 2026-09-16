# -*- coding: utf-8 -*-
"""S-247. 거절·경고 줄은 «다음에 무엇을 하나»를 싣는다 — 물어볼 데가 없기 때문에.

> 소유자 2026-09-15: 「난 이 에러를 **이해할 수가 없다, 조치를 뭘 해야 하는지 안 알려줌**」
> 같은 날: 「**운영은 보안 땜에 못 붙여**」

🔴 두 문장이 하나의 요구다. 운영 로그는 밖으로 나올 수 없으므로 — 붙여 넣고 물어볼 수가
없으므로 — 줄이 «혼자» 답해야 한다. 무엇이 일어났는지만 말하는 줄은, 읽는 사람이 뒤에 더
물을 수 있을 때만 완성된 줄이다.

⛔ AND A LINE WITHOUT AN ACTION IS NOT NEUTRAL HERE. 「중복 키」 로 읽히는 줄 넷이 있고, 그중
둘의 수리는 «정반대»다 — 좁은 키는 «선언»을 고치고(데이터를 접으면 사실이 사라진다), 진짜
중복은 «데이터»를 고친다(선언을 넓히면 중복이 남는다). 조치 없는 줄은 운영자를 반반의
확률로 틀린 수리로 보낸다.

⚠️ WHAT THIS FILE SCORES. The SHAPE and the ACTION of the rendered line - not that the
logger emitted it, and not the Korean prose beyond the one clause an operator acts on.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import operator_line                                               # noqa: E402

NEXT = "→ 다음: "


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the shape, and the fact that a line WITHOUT an action cannot be built
# ---------------------------------------------------------------------------

def test_the_line_carries_where_who_what_and_what_to_do_next():
    """⚠️ THE BRACKET IS THE SEARCH TERM. It is how an operator finds this line in a log
    at all, so every seat wears the same one - and the subject after the colon is the rule
    or the table they have to go and look at."""
    rendered = operator_line.line("join_into", "inv_confirm", "세 행이 둘 이상과 맞았습니다",
                                  operator_line.restart_to_apply())

    assert rendered.startswith("[join_into:inv_confirm] ")
    assert NEXT in rendered
    assert rendered.split(NEXT)[1]


def test_the_action_is_chosen_from_this_module_not_written_at_the_call_site():
    """🔴 THE CLOSED VOCABULARY IS THE POINT. Two seats that both say 「duplicate key」 need
    OPPOSITE repairs; if each wrote its own sentence they would drift apart exactly where
    being wrong is most expensive."""
    assert "합치십시오" in operator_line.fold_the_data("t", ["a"])
    assert "데이터를 합치면 사실이 사라집니다" in operator_line.widen_the_key("선언", "컬럼")
    assert "null_policy" in operator_line.fill_or_declare_null("t", ["a"])
    assert "재기동" in operator_line.restart_to_apply()
    assert "없음" in operator_line.nothing_to_do()


def test_the_two_opposite_repairs_never_read_the_same():
    """⛔ THE ONE THING THIS ROUND EXISTS TO PREVENT. 「행을 합쳐라」 and 「선언을 넓혀라」
    are the wrong answer to each other's question, and both arrive under the word
    「중복」."""
    fold = operator_line.fold_the_data("dt_inventory", ["dt_job"])
    widen = operator_line.widen_the_key("table_config", "컬럼")

    assert fold != widen
    # ⚠️ THE OPERATIVE VERB IS WHAT AN OPERATOR ACTS ON. `widen` mentions merging only
    # to FORBID it, so a crude substring check would call the two the same sentence.
    assert "합치십시오" in fold and "합치십시오" not in widen
    assert "적으십시오" in widen and "적으십시오" not in fold
    assert "데이터를 합치면 사실이 사라집니다" in widen


def test_at_most_three_samples_and_the_rest_are_counted():
    """⚠️ THREE, AND THE TOTAL. Showing three without saying how many there are reads as
    「셋뿐」 - and a thousand-row list is a dump, not a diagnosis."""
    assert operator_line.samples_of([1, 2]) == "1, 2"
    assert operator_line.samples_of([1, 2, 3, 4, 5]) == "1, 2, 3 외 2"
    assert operator_line.samples_of([]) == ""


def test_a_name_list_never_reaches_the_operator_as_a_python_repr():
    """⚠️ `['slot']` MAKES THE READER DECODE BRACKETS BEFORE READING THE SENTENCE."""
    assert "[" not in operator_line.fold_the_data("t", ["a", "b"])
    assert "a, b" in operator_line.fold_the_data("t", ["a", "b"])


# ---------------------------------------------------------------------------
# 🔴 ⓑ — the four seats, each with the action its own symptom needs
# ---------------------------------------------------------------------------

def _rendered_lines(caplog):
    return [record.getMessage() for record in caplog.records]


def test_the_fan_out_warning_sends_the_operator_to_the_data(caplog):
    """🔴 DATA, NOT DECLARATION. The right table holds two rows under one join key;
    widening the declaration would not change that, and this line has to say so because
    the sibling line two seats away means the opposite."""
    import logging

    from chain import join_into

    # ⚠️ EVERY ROW FANS OUT, so the write door is never reached and the subject stays
    # the LINE. A fixture with one clean row would build an update and fail on its shape,
    # which is a different test failing for a different reason.
    rows = [_Row(1), _Row(1), _Row(2), _Row(2)]
    spec = {"right_table": "dt_job_attribution",
            "on": [{"left": "dt_job", "right": "dt_job"}], "take": []}
    with caplog.at_level(logging.WARNING):
        join_into._write(_NoWrite(), "dt_inventory", rows, spec, "inv_confirm")

    line = [m for m in _rendered_lines(caplog) if "[join_into:inv_confirm]" in m]
    assert len(line) == 1, _rendered_lines(caplog)
    assert NEXT in line[0]
    assert "합치십시오" in line[0] and "dt_job_attribution" in line[0]


def test_the_index_report_says_the_product_will_build_it_after_a_restart():
    """⚠️ 「없습니다」 IS NOT AN ERROR THE OPERATOR FIXES. The product builds it (S-235) -
    so the action is a restart, and saying nothing here is what sends somebody to write
    `CREATE UNIQUE INDEX` by hand."""
    from chain import unique_key

    rendered = unique_key.describe("dt_inventory", ["dt_job"], {"state": "missing"})

    assert rendered.startswith("[VirtualJoinIndex:dt_inventory] ")
    assert "재기동" in rendered.split(NEXT)[1]


def test_the_blank_key_report_says_absence_and_points_at_the_catalogue():
    """🔴 A BLANK KEY IS NOT A DUPLICATE, AND THE REPAIR IS NEITHER OF THE OTHER TWO."""
    from chain import unique_key

    rendered = unique_key.describe(
        "dt_inventory", ["dt_job"],
        {"state": "blank_keys", "blank_keys": [{"key": [None], "rows": 12}]})

    action = rendered.split(NEXT)[1]
    assert "null_policy" in action
    assert "합치" not in action


def test_the_duplicate_list_still_ends_with_one_action():
    """⚠️ THIS ONE IS A LIST - the values ARE the diagnosis - and the last line still has
    to be the sentence the operator acts on."""
    from chain import unique_key

    rendered = unique_key.describe(
        "dt_inventory", ["dt_job"],
        {"state": "duplicates", "duplicates": [{"key": ["J1"], "rows": 2}]})

    assert rendered.splitlines()[-1].startswith(NEXT)
    assert "합치십시오" in rendered.splitlines()[-1]


def test_the_business_key_conflict_sends_the_operator_to_the_DECLARATION():
    """🔴 THE OPPOSITE REPAIR, UNDER THE SAME WORD. Here 「중복」 means the table's own
    identity does not tell two rows apart - folding the data would destroy a fact. An
    operator who reaches for the fix that worked on the join-key line gets it backwards,
    and before this round the line gave them nothing to tell the two apart with."""
    import inspect

    from database import crud

    body = inspect.getsource(crud.apply_batch_updates)

    assert "operator_line.widen_the_key" in body
    assert "BKConflict" in body


def test_the_write_gate_names_both_halves_and_both_send_you_to_the_data():
    """⚠️ TWO HALVES, ONE SYMPTOM. A pair inside one batch and a row colliding with one
    already stored are different detections with the same repair - and before this round
    only one of the two even said which rows."""
    import inspect

    from database import crud

    body = inspect.getsource(crud.refuse_virtual_join_duplicates)

    assert body.count("operator_line.line(") == 2
    assert body.count("operator_line.fold_the_data(") == 2


# ---------------------------------------------------------------------------
# ⚠️ ⓒ — one author, measured rather than trusted
# ---------------------------------------------------------------------------

def test_the_cycle_note_goes_through_the_author_it_claimed_to_follow(caplog):
    """🔴 [S-247-b] ONE AUTHOR QUIETLY BECAME TWO, IN THE ROUND THAT MADE IT ONE. This
    line's own docstring said it was 「in the shape S-247 gave every operator line」 while
    spelling that shape BY HAND - and the tell was measurable without reading it:
    `nothing_to_do` had zero callers, so the vocabulary entry had no reader at all. That is
    the same defect this whole day has been about, committed by me, in the fix for it."""
    from chain import rule_order

    note = rule_order.cycle_note(["there", "back", "there"], 5)

    assert note.startswith("[ChainRules:there -> back -> there] ")
    assert NEXT in note
    assert operator_line.nothing_to_do(
        "더 긴 고리가 필요하면 chain_rules.json 의 max_chain_depth") in note


def test_the_nothing_action_says_only_what_is_true_of_every_caller():
    """⚠️ MY FIRST CUT BAKED ONE CALLER'S FACT INTO THE SENTENCE - 「이 줄은 건너뛴 것을
    셉니다」 - which is false of a cycle note and is why it had no callers. What is
    caller-specific arrives through `unless`."""
    assert "건너뛴" not in operator_line.nothing_to_do()
    assert "없음" in operator_line.nothing_to_do()
    assert "max_chain_depth" in operator_line.nothing_to_do("max_chain_depth")


@pytest.mark.parametrize("module_name,function_name", [
    ("chain.join_into", "_write"),
    ("database.crud", "refuse_virtual_join_duplicates"),
    ("database.crud", "apply_batch_updates"),
    ("chain.unique_key", "describe"),
    ("chain.rule_order", "cycle_note"),
])
def test_every_seat_goes_through_the_one_renderer(module_name, function_name):
    """🔴 ONE AUTHOR, OR THE SHAPE DRIFTS SEAT BY SEAT. The screen's sentences already had
    one (`virtual_join/refusal.py`); the LOG's did not - and the log is the only channel
    that exists in production, because it cannot be pasted out and asked about."""
    import importlib
    import inspect

    module = importlib.import_module(module_name)
    body = inspect.getsource(getattr(module, function_name))

    assert "operator_line" in body, function_name


class _Row:
    """A SELECT row the way `_write` reads one: `.matched` and `._mapping`."""

    def __init__(self, row_id):
        self.matched = True
        self._mapping = {"row_id": row_id}


class _NoWrite:
    """⚠️ THE SUBJECT IS THE LINE, so the write door is not reached: every row in the
    fixture fanned out, and `_write` returns before it builds an update."""

    def __getattr__(self, _name):
        raise AssertionError("the write path must not be reached by this fixture")
