# -*- coding: utf-8 -*-
"""체인 규칙의 «순서» — 선언에서 유도된다. 새 칸이 아니다 (S-156, 판정 385).

🔴 THE ORDER WAS ALREADY DERIVED AND ONLY ONE CALLER READ IT. `replay` has ordered rules
producer-before-consumer since it existed - from `trigger_table` matched against another
rule's `target_table` - while the live worker ran them in FILE order. So 「A must run before
B」 was not a missing cell; it was a derivation with one reader, the fourth time this shape
has come up (S-152 · S-221 · S-154).

🔴 A LIGHT HOUSE, NOT ONE CALLER'S. The worker must not import `replay` - that module opens
the database, the cell layer and the mapper caller - so the shared thing lives here and both
sides import it, the same prescription `chain/mapper_call.py` got (S-214, 판정 370).

⚠️ WHAT THIS CANNOT SEE IS UNCHANGED. A rule that reads a table nothing declares it reads is
invisible here, exactly as it is to every other declaration-driven guard - 「선언으로 표현할 수
없는 교차 테이블 의존」 stays the sanctioned blind spot it is written down as.
"""


class RuleCycleRefused(ValueError):
    """⛔ REFUSED BY NAME. There is no correct order for a cycle across tables, and picking one
    silently would produce a result nobody could reason about."""


def order_rules(rules: list) -> list:
    """Topologically order rules so a producer replays before its consumer.

    The live config makes this mandatory rather than nice-to-have:
        production_plan  -> inventory_master
        inventory_master -> inventory_master     (trigger == target)
    Rule 1's output is rule 2's input, so replaying 2 first would recompute from
    stale data. And rule 2 triggers itself, so it is a self-edge.

    THE SKIP BELONGS TO THE PAIR, NOT TO ONE RULE (S-232-b, ruling 388). The edge
    `P -> X` over table `t` is skipped only when P AND X BOTH read `t` and write
    `t`: that pair is mutually dependent on one table, and mutual dependence on
    one table has no total order to find. It is never decided by comparing NAMES.

    ⚠️ ONE HALF IS NOT ENOUGH, AND THAT WAS RULING 387. A self-feeding `t -> t`
    rule still WRITES `t`, so a different `t -> u` rule that reads `t` genuinely
    depends on it and must run after it. "Moves nothing BETWEEN tables" was never
    the same sentence as "nobody reads it". Narrowing loses nothing the deleted
    name comparison covered: a rule against ITSELF satisfies both halves.

    ⚰️ WHAT THE NAME COMPARISON COST, MEASURED. It skipped a rule only against
    itself, so three DIFFERENT rules all writing the table they trigger on were
    producers for each other and the walk called them a cycle. On this box the
    three synthesized `enrichment_auto_confirm:*` rules (all
    `dt_inventory -> dt_inventory`) did exactly that: every load logged a cycle
    and left the order alone, so S-156's ordering was inert here.

    A cycle between DIFFERENT tables is still refused by name: there is no
    correct order for it, and picking one silently would produce a result nobody
    could reason about - the same split this function's own sentence already made.
    """
    by_target = {}
    for r in rules:
        by_target.setdefault(r.get("target_table"), []).append(r)

    state = {}   # rule name -> 0 visiting / 1 done
    ordered = []

    def visit(rule, path):
        name = rule.get("name")
        if state.get(name) == 1:
            return
        if state.get(name) == 0:
            cycle = " -> ".join(path + [name])
            raise RuleCycleRefused(
                f"chain rules form a cycle across tables and cannot be ordered: {cycle}. "
                f"Replay them one at a time with an explicit order you can justify.")
        state[name] = 0
        trigger = rule.get("trigger_table")
        for producer in by_target.get(trigger, []):
            if (producer.get("trigger_table") == trigger
                    and rule.get("target_table") == trigger):
                continue  # both ends live on `trigger`: no order exists between them
            visit(producer, path + [name])
        state[name] = 1
        ordered.append(rule)

    for r in rules:
        visit(r, [])
    return ordered
