# -*- coding: utf-8 -*-
"""S-156 (판정 385). 규칙 «사이» 순서는 새 칸이 아니라 «이미 유도된 것»이고, 워커가 안 읽었다.

🔴 THE ORDER WAS ALREADY DERIVED AND ONE CALLER READ IT. `replay` has ordered rules
producer-before-consumer since it existed - `trigger_table` matched against another rule's
`target_table` - while the live worker ran them in the order they were typed in the file. So
「A must run before B」 was never a missing cell; it was a derivation with a single reader,
the fourth time this shape came up in one round (S-152 · S-221 · S-154).

🔴 NO NEW CELL, ON PURPOSE. A cell would be a SECOND expression of the order, free to
disagree with the declaration it restates - the 「같은 기능에 두 경로」 defect one level up.

⚠️ WHAT THIS CANNOT SEE IS UNCHANGED. A rule that reads a table nothing declares it reads is
invisible here, exactly as it is to every other declaration-driven guard: 「선언으로 표현할 수
없는 교차 테이블 의존」 stays the sanctioned blind spot it is written down as.

🔴 [S-232, 판정 387·388] AND THE EXCEPTION BELONGS TO THE PAIR. S-156 landed INERT on this
box: the walk skipped a self-edge by comparing NAMES, so three DIFFERENT rules that each
write the table they trigger on were producers for each OTHER, every load reported a cycle,
and the order was left alone. 「자기 자신인가」는 이름이 아니라 «성질»이다 — but the property
is a fact about the PAIR, not about one rule: the edge `P -> X` over `t` is skipped only when
P AND X both read `t` and write `t`. Ruling 387 skipped every edge out of a self-feeding
rule, which was one conjunct too wide - such a rule still WRITES its table, so a different
rule reading that table depends on it. 388 narrowed it, and narrowing loses nothing the name
comparison covered: a rule against ITSELF satisfies both halves.
"""
import json
import os
import subprocess
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import ingestion_worker as worker                           # noqa: E402
from chain import replay, rule_order                                   # noqa: E402
from chain.cell_layer import ReplayRefused                             # noqa: E402


def _rule(name, trigger, target, **cells):
    base = {"name": name, "trigger_table": trigger, "target_table": target,
            "enabled": True, "mapper": "s156_mapper"}
    base.update(cells)
    return base


#: `b` consumes what `a` writes; the file lists them the wrong way round on purpose.
CONSUMER = _rule("b_consumer", "middle", "last")
PRODUCER = _rule("a_producer", "first", "middle")


# ---------------------------------------------------------------------------
# 🔴 gate ⓐ — the derivation itself
# ---------------------------------------------------------------------------

def test_a_producer_is_ordered_before_its_consumer():
    ordered = rule_order.order_rules([CONSUMER, PRODUCER])

    assert [rule["name"] for rule in ordered] == ["a_producer", "b_consumer"]


def test_rules_that_do_not_feed_each_other_keep_the_file_order():
    """⚠️ THE NO-REGRESSION, and it is what most deployments see: with nothing to order, the
    answer has to be the order the operator typed."""
    left = _rule("left", "t1", "out1")
    right = _rule("right", "t2", "out2")

    assert [r["name"] for r in rule_order.order_rules([left, right])] == ["left", "right"]
    assert [r["name"] for r in rule_order.order_rules([right, left])] == ["right", "left"]


def test_a_rule_that_triggers_itself_is_not_ordered_before_itself():
    """⚠️ A SELF-EDGE IS NOT A CYCLE. `inventory_master -> inventory_master` is a live shape;
    the snapshot guard inside `replay_rule` is what handles it, not the ordering."""
    loop = _rule("self_feeding", "same", "same")

    assert [r["name"] for r in rule_order.order_rules([loop])] == ["self_feeding"]


# ---------------------------------------------------------------------------
# 🔴 S-232 (판정 387) — the exception is the PROPERTY, and the name comparison is gone
# ---------------------------------------------------------------------------

def test_several_rules_that_each_feed_their_own_table_are_not_a_cycle():
    """🔴 THIS IS THE DEFECT THAT MADE S-156 INERT, and it needed THREE rules to show: with
    one, a name comparison and a property comparison give the same answer. Measured on this
    box before the fix - the three synthesized `enrichment_auto_confirm:*` rules all trigger
    on `dt_inventory` AND target it, so they were producers for each other, the walk said
    `a -> b -> a`, and every load left the order exactly as the file had it.

    ⚠️ AND THE ORDER IS THE GIVEN ONE, not merely 「no exception raised」. Mutual dependence
    on ONE table has no total order to find, so the answer has to be the order the operator
    typed - the same answer `test_rules_that_do_not_feed_each_other_keep_the_file_order`
    demands for rules with nothing between them."""
    trio = [_rule(name, "dt_inventory", "dt_inventory") for name in ("a", "b", "c")]

    assert [r["name"] for r in rule_order.order_rules(trio)] == ["a", "b", "c"]
    assert [r["name"] for r in rule_order.order_rules(list(reversed(trio)))] == ["c", "b", "a"]


def test_a_rule_that_fills_a_table_still_runs_before_the_rule_that_feeds_itself_there():
    """⚠️ THE NO-REGRESSION 판정 387 NAMED, and it is the live pair in `order_rules`' own
    docstring: `production_plan -> inventory_master` must precede
    `inventory_master -> inventory_master`, because the second recomputes from what the first
    wrote. Only the SELF-FEEDING rule is skipped as a producer; the one that moves data
    BETWEEN tables still orders everything downstream of it, from either file order."""
    fills = _rule("p1_fills", "production_plan", "inventory_master")
    feeds_itself = _rule("p2_self", "inventory_master", "inventory_master")

    assert [r["name"] for r in rule_order.order_rules([fills, feeds_itself])] == [
        "p1_fills", "p2_self"]
    assert [r["name"] for r in rule_order.order_rules([feeds_itself, fills])] == [
        "p1_fills", "p2_self"]


def test_a_self_feeding_rule_still_orders_a_rule_that_reads_the_table_it_writes():
    """🔴 THE ORDER A RULING CAME BACK FOR (판정 388), AND THE ASSERTION IS WHY. Ruling 387
    skipped every edge out of a self-feeding rule; this case was written to PIN the extent of
    that, because it was a behaviour change nothing else would have shown. It went to the
    channel as a measurement, 판정 388 read it and narrowed the condition to BOTH ends - so
    what this file asserts today is the opposite of what it asserted for one commit.

    🔴 `A(t -> t)` WRITES `t`, AND `B(t -> u)` READS IT. Moving nothing BETWEEN tables is not
    the same sentence as nobody reading it, so B genuinely depends on A and runs after it -
    from either file order. Only a PAIR that both read and write `t` has no order to find."""
    self_feeder = _rule("feeds_t_from_t", "t", "t")
    consumer = _rule("reads_t_writes_u", "t", "u")

    assert [r["name"] for r in rule_order.order_rules([consumer, self_feeder])] == [
        "feeds_t_from_t", "reads_t_writes_u"]
    assert [r["name"] for r in rule_order.order_rules([self_feeder, consumer])] == [
        "feeds_t_from_t", "reads_t_writes_u"]


def test_a_cycle_across_tables_is_named_once_and_never_refused():
    """🔴 [판정 402] A CYCLE IS A SHAPE, NOT AN ERROR. ⚰️ This used to raise: there is no total
    order for the pair, and the walk called that a refusal. But `dt_log → dt_inventory` by
    mapper and `dt_inventory → dt_log` by join is an INTENDED loop, and what keeps it finite
    is the hop ceiling the drain already enforces - so refusing it at load refused a
    declaration that works, on every load, in the log the operator needs for other things
    (「사이클 오류 계속 뜨네」).

    ⚠️ AND THE RULES STILL STAND. The walk stops descending into the loop and the
    declaration's own order holds for those two, which is the only honest answer when no
    total order exists."""
    there = _rule("there", "x", "y")
    back = _rule("back", "y", "x")
    trails = []

    ordered = rule_order.order_rules([there, back], on_cycle=trails.append)

    assert sorted(r["name"] for r in ordered) == ["back", "there"], "both rules stand"
    assert trails and "there" in trails[0] and "back" in trails[0]
    note = rule_order.cycle_note(trails[0], 5)
    assert "there -> back" in note and "max_chain_depth=5" in note


def test_replay_has_no_cycle_refusal_left_to_translate():
    """⚰️ IT USED TO RE-RAISE THE CYCLE AS `ReplayRefused`, so replay's callers could catch one
    name. 판정 402 removed the refusal itself, and a translation of something that is never
    raised is dead code wearing a docstring - so replay just orders and replays.

    ⚠️ THE OTHER `ReplayRefused` CASES ARE UNTOUCHED; what went is the CYCLE one."""
    there = _rule("there", "x", "y")
    back = _rule("back", "y", "x")

    assert sorted(r["name"] for r in replay.order_rules([there, back])) == ["back", "there"]
    assert not hasattr(rule_order, "RuleCycleRefused"), (
        "the exception class outlived the last place that raised it")


def test_the_order_does_not_depend_on_the_hash_seed():
    """🔴 판정 385 NAMED THIS GATE, and S-228 is why: a set of table names walked in a
    different order per process is exactly what made a rule order meaningless before."""
    probe = (
        "import sys; sys.path.insert(0, %r)\n"
        "from chain import rule_order\n"
        "rules = %r\n"
        "print('|'.join(r['name'] for r in rule_order.order_rules(rules)))\n"
    ) % (SERVER_DIR, [CONSUMER, PRODUCER, _rule("c", "last", "end"),
                      _rule("d", "t9", "spare")])

    def under(seed):
        done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                              env=dict(os.environ, PYTHONHASHSEED=seed), cwd=SERVER_DIR)
        assert done.returncode == 0, done.stderr[-2000:]
        return done.stdout.strip().splitlines()[-1]

    assert under("0") == under("1")


# ---------------------------------------------------------------------------
# 🔴 gate ⓑ — the worker reads it, at load
# ---------------------------------------------------------------------------

@pytest.fixture()
def load(tmp_path, monkeypatch):
    """Drives the real `load_chain_rules` over a file we write.

    ⚠️ THE MAPPER HAS TO RESOLVE or the loader refuses the rule before it can be ordered -
    「cannot run」 is judged first, and an unrunnable rule is dropped, not sorted.

    ⛔ AND THE SYNTHESIZED RULES ARE HELD OUT, because they come from the BOX's live
    enrichment declaration. Measured here: this box synthesizes three `auto_confirm` rules
    that all trigger on `dt_inventory` AND target it, so the order walk reports a cycle
    between them and leaves every order alone - the subject of this file would then be the
    box's config rather than the loader. That false cycle is reported separately; it is
    older than this round and `replay_all` already meets it."""
    import mapper_sdk
    from chain import synthesis

    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "s156_mapper", lambda db, payloads,
                        rule=None: {"updates": []})
    monkeypatch.setattr(synthesis, "synthesize_chain_rules", lambda **kwargs: [])

    def run(rules):
        path = tmp_path / "chain_rules.json"
        path.write_text(json.dumps({"rules": rules}), encoding="utf-8")
        monkeypatch.setattr(worker, "RULES_PATH", str(path))
        kept = worker.load_chain_rules()
        wrote = {r.get("name") for r in rules if isinstance(r, dict)}
        return [r.get("name") for r in kept if r.get("name") in wrote]

    return run


def test_the_loader_hands_the_worker_rules_in_that_order(load):
    """🔴 THE SEAT. The worker's rule loop walks `rules` in order, so ordering the list ONCE
    at load is what makes every downstream seat see the declared order."""
    assert load([CONSUMER, PRODUCER]) == ["a_producer", "b_consumer"]


def test_a_cycle_at_load_names_itself_and_does_not_stop_the_chain(load, caplog):
    """⛔ ONE UNORDERABLE PAIR MUST NOT COST THE OTHER RULES. This loader's posture is
    「거절된 분자는 세고 건너뛴다」 - raising here would turn a bad pair into 「no chain at
    all」, which is the failure S-177 and S-180 both exist to prevent. The cycle is named in
    the log, in the shared sentence, and the order is left as the file had it."""
    import logging

    there = _rule("there", "x", "y")
    back = _rule("back", "y", "x")

    with caplog.at_level(logging.INFO):
        names = load([there, back])

    assert names == ["there", "back"], "the rules still load, in the declaration's order"
    said = " ".join(record.getMessage() for record in caplog.records)
    assert "고리" in said and "there" in said, said
    # ⚰️ AND THE CYCLE IS NOT AN ERROR ANY MORE (판정 402). The operator watched this scroll
    # past on every load; a shape the product handles is not something to alarm about.
    # ⚠️ ABOUT THE CYCLE LINE ONLY - this loader emits other ERROR lines for other reasons
    # (a rule set that differs from the previous load, for one), and swallowing those into
    # this assertion would make it fail for facts it is not about.
    assert not [r for r in caplog.records
                if r.levelno >= logging.ERROR and "고리" in r.getMessage()], (
        "a cycle is still being reported as a fault")


# ---------------------------------------------------------------------------
# 🔴 2026-09-15 — a rule that cannot fire cannot order anything (production cycle)
# ---------------------------------------------------------------------------

def test_a_switched_off_rule_does_not_close_a_cycle():
    """🔴 THE OWNER'S QUESTION, VERBATIM: 「enable false 여도 고리 인식하나?」 It did. The
    trigger path skips a disabled rule (SKIPPED_DISABLED) but the ordering walk never
    asked, so a rule the operator had switched OFF kept closing cycles with live ones."""
    there = _rule("there", "x", "y")
    back = _rule("back", "y", "x", enabled=False)

    # No cycle from either file order, both rules kept, and the SAME answer either way -
    # the walk is a post-order DFS, so the answer is a property of the graph, not of the
    # file order. Pinning the reversed input to a reversed output was my own mistake.
    forward = [r["name"] for r in rule_order.order_rules([there, back])]
    reverse = [r["name"] for r in rule_order.order_rules([back, there])]
    assert sorted(forward) == ["back", "there"] and forward == reverse, (forward, reverse)


def test_a_paced_follow_up_does_not_close_a_cycle():
    """🔴 THE SHAPE A UNIFIED JOIN EMITS (S-237): its right-side rule is `right -> left`
    with follow_up=True, which never runs on the trigger path at all. With any live
    `left -> right` rule that read as a cycle of one edge that cannot fire."""
    live = _rule("inventory_to_attribution", "dt_inventory", "dt_job_attribution")
    paced = _rule("attribution_to_inventory", "dt_job_attribution", "dt_inventory",
                  follow_up=True)

    assert [r["name"] for r in rule_order.order_rules([live, paced])] == [
        "inventory_to_attribution", "attribution_to_inventory"]


def test_a_real_cycle_between_two_live_rules_is_still_named():
    """⚠️ THE NO-REGRESSION, in its post-402 shape: the walk still SEES the loop and still
    says which rules make it - what changed is that seeing it is not a refusal."""
    there = _rule("there", "x", "y")
    back = _rule("back", "y", "x")
    trails = []

    ordered = rule_order.order_rules([there, back], on_cycle=trails.append)

    assert len(ordered) == 2
    assert trails and "there" in trails[0] and "back" in trails[0]


def test_a_switched_off_producer_no_longer_orders_its_consumer():
    """🔴 THE EXTENT, PINNED - the same discipline as the 판정 388 test. A disabled rule
    that writes `t` used to be ordered before a live rule reading `t`; it is not any
    more, because it writes nothing. If that changes back, this goes red, on purpose."""
    off_producer = _rule("fills_t_but_off", "s", "t", enabled=False)
    consumer = _rule("reads_t", "t", "u")

    assert [r["name"] for r in rule_order.order_rules([consumer, off_producer])] == [
        "reads_t", "fills_t_but_off"]


def test_the_cycle_line_is_said_once_rather_than_on_every_load():
    """🔴 THE DRAIN RE-READS THE RULES FILE EVERY BATCH, so a line said on every load is a
    line that scrolls the log - which is exactly what the operator reported. Once per trail
    per process, and a declaration change forgets it."""
    import logging

    class _Spy(logging.Logger):
        def __init__(self):
            super().__init__("s249")
            self.said = []

        def info(self, message, *args):
            self.said.append(message % args if args else message)

    rule_order.forget_cycles()
    spy = _Spy()
    trail = ["a", "b", "a"]

    assert rule_order.say_cycle_once(spy, trail, 3) is True
    assert rule_order.say_cycle_once(spy, trail, 3) is False
    assert len(spy.said) == 1

    rule_order.forget_cycles()
    assert rule_order.say_cycle_once(spy, trail, 3) is True
    assert len(spy.said) == 2
