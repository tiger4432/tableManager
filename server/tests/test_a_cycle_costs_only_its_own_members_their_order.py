# -*- coding: utf-8 -*-
"""S-279 · 판정 422. A declared cycle loses the order of its OWN members, and nobody else's.

🔴 판정 402 IS UNCHANGED AND IS THE POINT. A cycle is 「오류가 아니라 모양」 - the loop
`dt_log → dt_inventory → dt_log` (a mapper one way, a join the other) is INTENDED, and what
makes it finite is the hop ceiling, not a refusal at load time. So a cycle's members have no
total order and the declaration's own order is the only one anybody can reason about.

⚠️ WHAT WAS WRONG IS WHO THAT SENTENCE WAS APPLIED TO. `order_rules` answered a cycle with
`return list(rules)` - the order of EVERY rule in the set, including rules the loop never
touches. One declared loop therefore made S-156's ordering inert for the whole deployment, and
silently: the operator line says 「순서는 선언 순」 and reads as though that were the intent.

🪦 AND IT HAD HAPPENED BEFORE, BY ANOTHER ROUTE. That function's own docstring records three
synthesized `enrichment_auto_confirm:*` rules forming a cycle among themselves, after which
「every load logged a cycle and left the order alone, so S-156's ordering was inert here」. The
repair then was to stop calling those a cycle. This is the same disease arriving as a real one.
"""
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import rule_order                                          # noqa: E402

#: The declared loop 판정 402 named: a mapper one way, a join's reference side the other.
R1 = {"name": "r1_enrich", "enabled": True,
      "trigger_table": "dt_log", "target_table": "dt_inventory",
      "mapper_module": "m", "mapper_function": "f"}
R2 = {"name": "r2_join_reference", "enabled": True,
      "trigger_table": "dt_inventory", "target_table": "dt_log",
      "mapper": "declared:join"}

#: A producer and its consumer that the loop does not touch at all.
R3 = {"name": "r3_producer", "enabled": True,
      "trigger_table": "dt_orders", "target_table": "dt_plan",
      "mapper_module": "m", "mapper_function": "f"}
R4 = {"name": "r4_consumer", "enabled": True,
      "trigger_table": "dt_plan", "target_table": "dt_report",
      "mapper_module": "m", "mapper_function": "f"}


def _names(rules):
    trails = []
    return [r["name"] for r in rule_order.order_rules(rules, on_cycle=trails.append)], trails


def test_a_rule_outside_the_cycle_keeps_the_order_the_walk_computed():
    """🔴 THE ASSERTION 판정 422 ASKED FOR, and it is RED before the repair: `r3` produces what
    `r4` consumes, and a cycle somewhere else in the set used to cost them that."""
    ordered, trails = _names([R4, R3, R1, R2])

    assert trails, "no cycle was found, so this fixture proves nothing about cycles"
    assert ordered.index("r3_producer") < ordered.index("r4_consumer"), (
        "a cycle between two OTHER rules threw away the order of a producer and its "
        "consumer that the loop never touches: %s" % ordered)


def test_the_cycles_own_members_keep_the_declaration_order(request):
    """⚠️ 판정 402, INTACT. The members have no total order to find, so the operator's own is
    what they get - and it must be the DECLARATION's, not the order the descent unwound in,
    which is a third order nobody wrote."""
    forward, _ = _names([R1, R2, R3, R4])
    backward, _ = _names([R2, R1, R3, R4])

    assert forward.index("r1_enrich") < forward.index("r2_join_reference"), forward
    assert backward.index("r2_join_reference") < backward.index("r1_enrich"), backward


def test_every_rule_comes_back_exactly_once():
    """⛔ THE SILENT FAILURE MODE OF A RE-SEATING REPAIR. Moving members into slots can drop
    one or duplicate one, and either would be invisible - a dropped rule simply stops firing."""
    given = [R4, R3, R1, R2]
    ordered, _ = _names(given)

    assert sorted(ordered) == sorted(r["name"] for r in given), ordered
    assert len(ordered) == len(given), ordered


def test_a_set_with_no_cycle_is_untouched_by_any_of_this():
    """The control. Without a loop nothing here applies, and the walk's own answer stands."""
    ordered, trails = _names([R4, R3])

    assert trails == []
    assert ordered.index("r3_producer") < ordered.index("r4_consumer"), ordered


def test_the_operator_line_says_which_rules_lost_their_order():
    """🔴 [판정 422 ④] THE LINE READ AS 「전부」. 「순서는 선언 순」 with a trail beside it is read
    by an operator as 「the whole set is in declaration order now」, which is what the code did
    and is no longer what it does. A line that is no longer true is not unhelpful - it is
    false, and 상설 ①'s discriminant is 「이 줄이 참인가」."""
    said = rule_order.cycle_note(["r1_enrich", "r2_join_reference", "r1_enrich"], ceiling=5)

    assert "max_chain_depth=5" in said
    assert "끼리만" in said, (
        "the line still reads as though every rule in the set fell back to declaration "
        "order: %s" % said)
