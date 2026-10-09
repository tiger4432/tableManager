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
import json

from chain import rule_shape


#: The loops the last read of the declaration met, by `loop_of`, from both seats - the order walk
#: and the cascade graph. Said by the dispatcher alone (`say_loops`); a slot reads and keeps quiet.
_FOUND = set()
#: The declaration content the dispatcher last said its loops for.
_SAID_FOR = None


def loop_of(trail) -> tuple:
    """The loop a trail closes, one key whichever node a walk started from (총괄 10-09 「고리 하나 = 줄
    하나」): the descent cut (from the first visit of the node it ends on), the repeat dropped, turned
    to begin at its smallest name."""
    nodes = [str(node) for node in trail]
    loop = nodes[nodes.index(nodes[-1]):-1] or nodes[-1:]
    start = loop.index(min(loop))
    return tuple(loop[start:] + loop[:start])


def cycle_note(trail, ceiling=None) -> str:
    """The one line about a loop (소유자 「고리 홉상한 어쩌고 … 엄청 길게」 -> 총괄's short line).

    🔴 [판정 402] A CYCLE IS A SHAPE, NOT AN ERROR - intended (a mapper one way, a join back) and
    finite by `max_chain_depth`, the cell to change for a longer one."""
    loop = loop_of(trail)
    return "[ChainRules] loop: %s · capped at max_chain_depth=%s" % (
        " -> ".join(loop + loop[:1]), ceiling if ceiling is not None else "default")


def found_cycle(trail):
    """Both seats that meet a loop record it here - the order walk, the cascade graph."""
    _FOUND.add(loop_of(trail))


def forget_cycles():
    """A read of the declaration begins: the loops are this read's."""
    _FOUND.clear()


def say_loops(logger_, declaration, ceiling=None) -> int:
    """Each loop of the declaration, one line, once per declaration CONTENT - a re-read of the same
    declaration says nothing (총괄 10-09). -> lines said."""
    global _SAID_FOR
    stamp = json.dumps(declaration, sort_keys=True, default=str)
    if stamp == _SAID_FOR:
        return 0
    _SAID_FOR = stamp
    for loop in sorted(_FOUND):
        logger_.info(cycle_note(loop + loop[:1], ceiling))
    return len(_FOUND)


def order_rules(rules: list, on_cycle=None) -> list:
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

    ⚰️ A CYCLE BETWEEN DIFFERENT TABLES USED TO BE REFUSED BY NAME, and 판정 402
    ended that: the loop `dt_log → dt_inventory → dt_log` is INTENDED (a mapper one
    way, a join the other) and the drain's `max_chain_depth` already makes it
    finite. So the walk reports the trail through `on_cycle`, leaves those rules in
    the order the declaration gives them, and nothing is refused.
    """
    by_target = {}
    for r in rules:
        by_target.setdefault(r.get("target_table"), []).append(r)

    state = {}   # rule name -> 0 visiting / 1 done
    ordered = []
    found_cycle = []
    in_a_cycle = set()   # 판정 422: the names a cycle actually runs through

    def visit(rule, path):
        name = rule.get("name")
        if state.get(name) == 1:
            return
        if state.get(name) == 0:
            # 🔴 [판정 402] NOT AN ERROR - A SHAPE. There is no total order for this pair, so
            # the walk stops descending and the declaration's own order stands for them. The
            # caller is TOLD (once), and the hop ceiling is what keeps the loop finite at run
            # time. Raising here refused a working declaration and scrolled the log.
            found_cycle.append(True)
            # 🔴 [판정 422] THE MEMBERS, NOT ONLY THE FACT. The trail this walk already hands
            # `on_cycle` contains the DESCENT as well as the loop; the loop itself is the
            # suffix from where `name` first appears. Everything before that is an innocent
            # bystander that reached the loop, and 판정 422 is about not charging it.
            trail = (path[path.index(name):] if name in path else list(path)) + [name]
            in_a_cycle.update(trail)
            if on_cycle is not None:
                on_cycle(path + [name])
            return
        state[name] = 0
        trigger = rule.get("trigger_table")
        for producer in by_target.get(trigger, []):
            # 🔴 AN EDGE THAT CANNOT FIRE CANNOT ORDER ANYTHING (2026-09-15, production
            # cycle). The trigger path already asks two questions before running a
            # rule - `_rule_accepts_event` returns False for a follow_up kind, and a
            # rule declaring enabled: false is SKIPPED_DISABLED - and this walk asked
            # neither. So a switched-off rule kept ordering its neighbours, and the
            # paced right-side rule a unified join emitted THEN (right -> left, follow_up)
            # combined with any live left -> right rule into a "cycle" of one edge that
            # never fires. ⚰️ THAT EXAMPLE IS PAST TENSE SINCE `c41f9c6d`: a unified join no
            # longer carries `follow_up`, so its reference side IS on the trigger path and
            # this walk orders it. The PREDICATE below is unchanged and still right - what
            # it asks is 「is this producer on the trigger path」, and `follow_up` is that
            # property itself, not a stand-in for 「is it a builtin」.
            # The owner met exactly that: 「enable false 여도 고리 인식하나?」
            # Yes, it did. Now the walk asks what the trigger path asks.
            # ⚰️ [소유자 정본] THIS ASKED `producer.get("follow_up")` — 「is this producer on
            #   the trigger path」. Every producer is, so the question is gone with the cell.
            if rule_shape.is_switched_off(producer):
                continue  # not on the trigger path: it fires nothing, it orders nothing
            if (producer.get("trigger_table") == trigger
                    and rule.get("target_table") == trigger):
                continue  # both ends live on `trigger`: no order exists between them
            visit(producer, path + [name])
        state[name] = 1
        ordered.append(rule)

    for r in rules:
        visit(r, [])
    if found_cycle:
        # 🔴 [판정 402] A CYCLE MEANS 「순서는 선언 순」 - FOR ITS OWN MEMBERS (판정 422).
        # Returning `list(rules)` threw away the order of every rule in the set, including
        # rules the loop never touches, so one declared cycle made S-156's ordering inert for
        # everything. This function's own docstring records that happening once before, by a
        # different route: three synthesized rules formed a cycle and 「every load logged a
        # cycle and left the order alone」.
        #
        # ⚠️ THE POSITIONS DO NOT MOVE, which is what keeps 판정 402 true. A partial walk hands
        # back the loop's members in the order the descent happened to unwind - a third order
        # nobody wrote. So the SLOTS the walk assigned stay exactly where they are, and only
        # the members sitting in them are re-seated, in the order the operator declared them.
        # Every rule reaches `ordered` exactly once (a re-entry returns early, but the frame
        # already on the stack still appends), so these two lists are the same length.
        slots = [i for i, r in enumerate(ordered) if r.get("name") in in_a_cycle]
        members = [r for r in rules if r.get("name") in in_a_cycle]
        seated = list(ordered)
        for slot, member in zip(slots, members):
            seated[slot] = member
        return seated
    return ordered
