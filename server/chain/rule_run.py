# -*- coding: utf-8 -*-
"""The one seat that asks 「which door does this rule go through」 and runs it.

🔴 [S-279, 판정 420 ㉡] 소유자 2026-09-16: 「맵퍼 한 문인데 왜 이름이 달라」 · 「문 가르기
금지」. One chain grammar declares enrich, join and decide; the DISPATCHERS were two - a file
mapper went through `mapper_call.execute_custom_mapper(module, function, ...)` and a
`builtin:` kind through `builtins.run_builtin(kind, ...)` - and every caller that could run a
rule had to ask which, in its own words. The census (판정 419 ①) counted 20 sites asking that
one question in SEVEN spellings, and the cost was not theoretical: taking the join off the
paced follow-up lap took it off the only lap that dispatched it, because the live group path
had no builtin branch at all and reached `execute_custom_mapper(None, None, ...)`.

WHAT THIS FILE IS. `run_rule` is the only function that asks the question, the only author of
the line that says a rule ran, and it answers in ONE shape whichever door was used - so a
caller extends `updates`, reads `written` and checks `refusal` without knowing the kind. That
is the working meaning of 「구분되지 않는다」.

⚠️ THE TWO DOORS STAY. They are not duplicates of each other: one imports a module an
operator wrote, the other looks up a name in a table this repository owns, and both register
their run in `chain.activity`. What was wrong was that the CHOICE between them lived in every
caller. The choice lives here now; the doors are unchanged.

⚠️ WHAT THIS SEAT DOES NOT DO, stated so nobody reads more into it:
  · it does not catch. A mapper that raises raises, exactly as before - `refusal` is the cell
    a builtin fills when it declines in an orderly way, and a throw is not that.
  · it does not decide WHICH rows a rule is handed. Freshness (`followup_already_served`),
    paging and event matching belong to the callers and are untouched.
  · it does not replace the doors' own lines. `execute_custom_mapper` says START/END inside
    itself; that is the door's sentence about the mapper. This seat's line is the sentence
    about the RULE, and it is the one spelled identically for both kinds.
"""
import logging
import time

logger = logging.getLogger(__name__)

#: 🔴 ONE PREFIX FOR BOTH KINDS. Measured before choosing it (2026-09-16): a builtin run was
#: logged as `[ChainBuiltin] ... written=` and a mapper run as `[mapper@<logfile>] ...
#: rows_out=`, so an operator grepping for 「this rule ran」 had to know the kind BEFORE
#: searching - which is the same defect as the two dispatchers, wearing a different coat.
#: (⚠️ the lead's census said the mapper line carries no rule name; re-measured, it has
#:  carried `rule=` since S-246. What actually differed was the PREFIX and the COUNT NAMES.)
RULE_LOG_TAG = "ChainRule"


def builtin_kind(rule):
    """The `builtin:` kind this rule names, or None when a file mapper owns it.

    🔴 THIS IS THE QUESTION, AND IT IS ASKED HERE. Callers that must know the kind WITHOUT
    running it (replay reports it in its stats and gates its dry run on it) ask through this
    function rather than comparing against `BUILTIN_KINDS` themselves - otherwise the seat is
    the only place that RUNS the answer while the answer itself is still derived in six
    places, which is how the spellings multiplied in the first place.
    """
    from chain import builtins

    kind = (rule or {}).get("mapper")
    return kind if kind in builtins.BUILTIN_KINDS else None


def _uniform():
    """The answer's shape, with every cell present whichever door ran.

    `updates`/`map_metadata_updates`/`batches` are what a rule PROPOSES and the caller writes;
    `written` is what a rule wrote FOR ITSELF and the caller must not write again. A kind that
    writes for itself proposes nothing, so a caller can extend all three lists unconditionally
    and get a no-op - that is what lets the branch disappear from the callers.

    ⚠️ `written` IS None, NOT 0, WHEN NOBODY COUNTED. 「안 셌다」 and 「0 이었다」 are different
    facts, and `chain.builtins` already keeps them apart for the same reason.
    """
    return {"updates": [], "map_metadata_updates": [], "batches": [],
            "written": None, "refusal": None}


def run_rule(db, rule, payloads=None, row_ids=None, done=None):
    """Run ONE chain rule over the input it was handed, whichever door it goes through.

    `payloads` are expanded trigger rows a file mapper is handed; `row_ids` are the rows a
    `builtin:` kind resolves for itself. `done` is the follow-up lap's batch and is passed on
    only when given, because the group path does not have one and a kind that does not accept
    it would refuse the call.
    """
    started = time.monotonic()
    name = (rule or {}).get("name") or "<unnamed rule>"
    target = (rule or {}).get("target_table") or "<none>"
    kind = builtin_kind(rule)
    answer = _uniform()

    if kind is not None:
        handed = list(row_ids or ())
        if not handed:
            # Nothing was handed, so nothing ran - and a line claiming a run would be a false
            # sentence. Every caller already skips this case; it is stated here so the next
            # one does not have to remember to.
            return answer
        from chain import builtins
        from database.context import outbox_mode
        import event_constants

        # 🔴 COLLAPSED, BECAUSE A BUILTIN WRITES FOR ITSELF. A file mapper's rows go out
        # through the caller's `apply_batch_updates`, which is already inside an
        # `outbox_mode(COLLAPSED)` scope; a builtin never passes through it, so without this
        # 1,000 written rows became 「1,000 outbox events, 1,000 queue items, 1,000 laps and
        # 1,000 lines」 - the owner's 「한 행당 로그 하나」, removed from the follow-up lap by
        # S-249 ⓔ-1 and from the group path by S-278 A-bis. Two of the three callers wrap
        # this call today and the third (replay) predates the ruling; putting it in the seat
        # is how it stops being something each caller has to remember.
        extra = {"done": done} if done is not None else {}
        with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
            outcome = builtins.run_builtin(kind, db, rule, row_ids=handed, **extra) or {}
        answer["written"] = outcome.get("written")
        answer["refusal"] = outcome.get("refusal")
        who, rows_in = kind, len(handed)
    else:
        from chain.mapper_call import execute_custom_mapper

        module_name = (rule or {}).get("mapper_module")
        func_name = (rule or {}).get("mapper_function")
        handed = list(payloads or ())
        # A batch rule is handed the WHOLE group in one call and a per-row rule one call per
        # row - the same fan-out both live callers already do. An empty batch still calls,
        # because a batch mapper is entitled to be told its group was empty; an empty per-row
        # list is zero calls, because there is no row to speak about.
        if (rule or {}).get("is_batch", False):
            results = [execute_custom_mapper(module_name, func_name, db, handed, rule=rule)]
        else:
            results = [execute_custom_mapper(module_name, func_name, db, one, rule=rule)
                       for one in handed]
        for result in results:
            if not isinstance(result, dict):
                continue
            for cell in ("updates", "map_metadata_updates", "batches"):
                answer[cell].extend(result.get(cell) or ())
        # ⚠️ THE ONE CELL FIRST, BECAUSE `None.None` WOULD BE A FALSE LINE. A rule may name
        # its mapper in `mapper` (the decorator registry, S-188 ⓓ) and carry no module or
        # function at all; the door already resolves that, and the line has to say the same
        # name the door used rather than two literal Nones.
        who = (rule or {}).get("mapper") or "%s.%s" % (module_name, func_name)
        rows_in = len(handed)

    # 🔴 ONE LINE, ONE VOCABULARY. `rows_in` is what the rule was handed, `updates` what it
    # proposed, `written` what it wrote itself - the same three names whichever door ran, so
    # an operator reads the two kinds with one query and can see at a glance which of the two
    # a rule is (`updates=0 written=5` writes for itself; `updates=5 written=None` proposes).
    logger.info("[%s] rule=%s kind=%s target=%s rows_in=%d updates=%d written=%s refusal=%s "
                "elapsed=%.3fs",
                RULE_LOG_TAG, name, who, target, rows_in, len(answer["updates"]),
                answer["written"], answer["refusal"], time.monotonic() - started)
    return answer
