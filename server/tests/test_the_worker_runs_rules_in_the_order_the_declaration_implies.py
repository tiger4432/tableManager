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


def test_a_cycle_across_tables_is_refused_by_name():
    """🔴 THERE IS NO CORRECT ORDER FOR IT, and picking one silently would produce a result
    nobody could reason about."""
    there = _rule("there", "x", "y")
    back = _rule("back", "y", "x")

    with pytest.raises(rule_order.RuleCycleRefused) as caught:
        rule_order.order_rules([there, back])

    assert "cycle" in str(caught.value)
    assert "there" in str(caught.value) and "back" in str(caught.value)


def test_replay_still_raises_its_own_refusal_with_the_same_sentence():
    """⚠️ ONE SENTENCE, TWO NAMES. `ReplayRefused` is what replay's callers already catch, so
    the refusal is re-raised under that name rather than making every caller learn a second
    one - and the words come from the shared home, so they cannot drift apart."""
    there = _rule("there", "x", "y")
    back = _rule("back", "y", "x")

    with pytest.raises(rule_order.RuleCycleRefused) as home:
        rule_order.order_rules([there, back])
    with pytest.raises(ReplayRefused) as through_replay:
        replay.order_rules([there, back])

    assert str(through_replay.value) == str(home.value)


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
    from chain import builtins

    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "s156_mapper", lambda db, payloads,
                        rule=None: {"updates": []})
    monkeypatch.setattr(builtins, "synthesize_chain_rules", lambda **kwargs: [])

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

    with caplog.at_level(logging.ERROR):
        names = load([there, back])

    assert names == ["there", "back"], "the rules still load"
    said = " ".join(record.getMessage() for record in caplog.records)
    assert "cycle" in said and "there" in said, said
