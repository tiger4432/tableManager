# -*- coding: utf-8 -*-
"""판정 500. 선언된 규칙 하나하나에 「이 규칙을 집는 경로가 몇인가」를 묻고, 하나가 아니면 이름을 댄다.

> 소유자 2026-09-17: 「결국 이것도 같은 체인이니 같은 문 알지? 체인으로 트리거 되는데 체인이네」
> 그리고 그 뒤: 「**왜 이런일이 벌어져?**」

🔴 THE CLASS, NOT THE INSTANCE. The instance was a rule nothing ran: `follow_up: true` on a
FILE mapper falls out of the group step (deferred) and out of the paced pass (which can only
run a rule that writes its own rows), so it sat enabled, said nothing, and showed 「아직 평가
안 됨」 forever. The class is that NOTHING COMPARED THE TWO SIDES:

    the grammar says 「you may write this cell」          - one place (`RULE_ROUTING_OPTIONAL`)
    each execution path says 「I take rules like this」   - each in its own place

Nobody held those up against each other. And because opt-in is the default, 「nobody picked it
up」 and 「there was nothing to do」 have the SAME SHAPE - silence - so it cannot be seen.

⚠️ AND THAT DIAGNOSIS WAS ALREADY WRITTEN, IN PROSE. CLAUDE.md, 2026-09-06: 「옵트인이
기본이라 「안 돌았다」와 「돌 필요가 없었다」가 «같은 모양»이다」. Prose turns nothing red, and
the same shape came back eleven days later. This file is that paragraph as a gate.

🔴 THE PATHS ANSWER FOR THEMSELVES. `PICKUP_PATHS` holds each path's OWN predicate - the
function that path calls to select - so a path that narrows tomorrow makes some rule's count
fall to zero and the boot names it. A roll call that re-spelled the predicates would be
measuring a copy, which is the defect it exists to catch, one layer up.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import ingestion_worker as worker                          # noqa: E402

#: The rule the operator can write today and nothing would run - 판정 500 ⓑ's own example.
#: 🔴 A REAL SHAPE, NOT A CONTRIVANCE: `follow_up` is in `RULE_ROUTING_OPTIONAL` and the
#: authoring form offers it as a flag (`chain_skeleton.json`), so any rule may carry it.
UNRUNNABLE = {"name": "operator_wrote_follow_up_on_a_mapper", "trigger_table": "t",
              "mapper_module": "some.module", "mapper_function": "build", "follow_up": True}

#: The two shapes that ARE run, one per path.
ON_THE_GROUP_STEP = {"name": "plain_mapper", "trigger_table": "t",
                     "mapper_module": "some.module", "mapper_function": "build"}
ON_THE_PACED_PASS = {"name": "auto_confirm_like", "trigger_table": "t",
                     "mapper": "declared:decide", "follow_up": True}


def _paths(rule):
    return worker.rules_by_pickup_count([rule])[rule["name"]]


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the instance
# ---------------------------------------------------------------------------

def test_a_rule_no_path_picks_up_is_refused_by_name(caplog):
    """🔴 THE GATE OF THIS ROUND. ⛔ 「선언에 적을 수 있는데 안 도는 상태를 남기지 마십시오」.

    The refusal has to NAME the rule, because the operator's next move is to open their file
    and find it - and it has to say what to do instead, because 「this cannot run」 without a
    way out is a dead end wearing a diagnosis.
    """
    import logging

    with caplog.at_level(logging.ERROR):
        kept = worker.refuse_rules_no_path_picks_up([ON_THE_GROUP_STEP, UNRUNNABLE])

    assert [r["name"] for r in kept] == ["plain_mapper"], (
        "the unrunnable rule was kept, so it goes on sitting enabled and silent")
    said = " ".join(r.getMessage() for r in caplog.records)
    assert UNRUNNABLE["name"] in said, "refused without naming the rule"
    assert "follow_up" in said, "the refusal does not say which cell caused it"
    # ⚠️ THE WAY OUT IS PART OF THE SENTENCE - 「거절의 사유와 다음 행동」.
    assert "Drop `follow_up`" in said or "writes for itself" in said


def test_the_two_shapes_that_do_run_are_each_taken_by_exactly_one_path():
    """⚠️ THE CONTROL. A gate that only proves the bad case goes red would also pass if
    EVERYTHING were refused - and that failure would look like a very thorough gate."""
    assert _paths(ON_THE_GROUP_STEP) == ["the group step"]
    assert _paths(ON_THE_PACED_PASS) == ["the follow-up pass"]
    assert _paths(UNRUNNABLE) == []


def test_nothing_is_refused_when_every_rule_has_its_path(caplog):
    """⛔ SILENCE IS THE NORMAL ANSWER. A roll call that spoke on every boot would be read
    past within a week, and then it would be there for nobody."""
    import logging

    with caplog.at_level(logging.ERROR):
        kept = worker.refuse_rules_no_path_picks_up([ON_THE_GROUP_STEP, ON_THE_PACED_PASS])

    assert len(kept) == 2
    assert not caplog.records, [r.getMessage() for r in caplog.records]


# ---------------------------------------------------------------------------
# 🔴 ⓑ — the class: it must fire for a path that narrows TOMORROW
# ---------------------------------------------------------------------------

def test_a_path_that_narrows_makes_the_boot_name_what_it_dropped(monkeypatch, caplog):
    """🔴 THIS IS WHY IT IS A ROLL CALL AND NOT A CHECK FOR ONE CELL.

    The instance above is fixed by one refusal; the CLASS is that any path may narrow and
    take rules out of the set silently. Here the group step's own predicate is narrowed - the
    same edit somebody could make tomorrow for a good reason - and a rule that ran this
    morning has no path by lunchtime. The boot says its name.

    ⚠️ NARROWED AT `PICKUP_PATHS`, WHICH IS WHERE A REAL NARROWING WOULD LAND. Patching the
    roll call instead would test the test.
    """
    import logging

    monkeypatch.setattr(worker, "PICKUP_PATHS",
                        (("the group step", lambda rule: False),
                         ("the follow-up pass", worker.picked_up_by_the_follow_up_pass)))

    with caplog.at_level(logging.ERROR):
        kept = worker.refuse_rules_no_path_picks_up([ON_THE_GROUP_STEP, ON_THE_PACED_PASS])

    assert [r["name"] for r in kept] == ["auto_confirm_like"]
    assert "plain_mapper" in " ".join(r.getMessage() for r in caplog.records)


def test_a_rule_two_paths_would_run_is_refused_too(monkeypatch, caplog):
    """🔴 TWO IS THE SAME DEFECT WITH THE OPPOSITE SIGN. One change running a rule twice is
    not 「extra safety」 - for a rule that writes, it is the write happening twice."""
    import logging

    monkeypatch.setattr(worker, "PICKUP_PATHS",
                        (("the group step", lambda rule: True),
                         ("the follow-up pass", lambda rule: True)))

    with caplog.at_level(logging.ERROR):
        kept = worker.refuse_rules_no_path_picks_up([ON_THE_GROUP_STEP])

    assert kept == []
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "plain_mapper" in said and "2 execution paths" in said


# ---------------------------------------------------------------------------
# 🔴 ⓒ — the table question, which the two passes used to answer differently
# ---------------------------------------------------------------------------

def test_the_off_switch_reaches_the_paced_pass_too():
    """🔴 MEASURED ON 2026-09-17, NOT INFERRED: `enabled: false` did NOT stop the paced pass.

    `load_chain_rules` keeps disabled rules - every group-path caller filters `enabled`
    itself - and the paced pass filtered `follow_up` and the table and nothing else. So a
    rule the operator had switched OFF went on running there, once per follow-up batch.
    Same class as 「DB 를 여전히 만지는 스위치는 반쪽 스위치다」: the switch was half a switch.
    """
    off = dict(ON_THE_PACED_PASS, name="switched_off", enabled=False)

    assert worker.watches_table(ON_THE_PACED_PASS, "t") is True
    assert worker.watches_table(off, "t") is False, (
        "a rule declaring enabled: false is still watched by this path")
    # ⚠️ AND THE SWITCH IS NOT THE PATH. A disabled rule still HAS a path - it is simply
    # turned off - so the roll call must not report it as unrunnable.
    assert _paths(off) == ["the follow-up pass"]


def test_the_table_question_has_one_author():
    """⚠️ ASKED THE WAY BOTH PASSES ASK IT. `trigger_table` is the cell; what differed was
    whether `enabled` came with it, which is exactly how one pass came to obey a switch the
    other ignored."""
    assert worker.watches_table(ON_THE_GROUP_STEP, "t") is True
    assert worker.watches_table(ON_THE_GROUP_STEP, "other") is False
    assert worker.watches_table(None, "t") is False
    assert worker.watches_table({}, "t") is False


def test_the_paced_pass_no_longer_carries_a_kind_in_its_name():
    """⚠️ [판정 500 ③] A NAME IS A CLAIM. `_run_builtin_followups` and
    `_followup_builtin_rules` said 「builtin」, which 판정 496 settled is one of three ways a
    rule NAMES its code rather than a kind of rule - and 499 had just shown what a stale kind
    name in this area costs."""
    assert hasattr(worker, "_run_the_follow_up_pass")
    assert hasattr(worker, "_rules_for_the_follow_up_pass")
    assert not hasattr(worker, "_run_builtin_followups")
    assert not hasattr(worker, "_followup_builtin_rules")
