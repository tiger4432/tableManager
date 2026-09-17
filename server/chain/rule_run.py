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
import collections
import contextlib
import importlib
import logging
import time

logger = logging.getLogger(__name__)

# 🔴 [판정 562] IMPORTED FOR ITS EFFECT, AND THIS IS THE SEAT THE OLD ARRANGEMENT USED.
#   `chain.builtins` was imported here too, and importing it FILLED the kind table - which
#   is why a rule naming `builtin:join_into` resolved in any process that had imported this
#   module. Measured after removing it: the loader refused every join by name because the
#   built mappers were only installed by `discover()`, which a process loading rules need
#   never have called.
# ⚠️ SO THE IMPORT IS NOT DECORATION. Taking it out moves 「the joins resolve」 from
#   「anything that can run a rule」 to 「anything that warmed up first」, silently.
from chain import dynamic_mappers  # noqa: F401  (installs the built mappers)

#: 🔴 ONE PREFIX FOR BOTH KINDS. Measured before choosing it (2026-09-16): a builtin run was
#: logged as `[ChainBuiltin] ... written=` and a mapper run as `[mapper@<logfile>] ...
#: rows_out=`, so an operator grepping for 「this rule ran」 had to know the kind BEFORE
#: searching - which is the same defect as the two dispatchers, wearing a different coat.
#: (⚠️ the lead's census said the mapper line carries no rule name; re-measured, it has
#:  carried `rule=` since S-246. What actually differed was the PREFIX and the COUNT NAMES.)
RULE_LOG_TAG = "ChainRule"


#: The `source_name` every chain-caused write leaves on its outbox envelope. One spelling,
#: here, because `_outbox_envelope` reads it from a context var and ten mappers spelling it in
#: the rows they return is the ROW's source column, which is a different cell.
CHAIN_SOURCE = "chain_ingestion"


def outgoing_depth(incoming):
    """The hop number a write caused by a rule woken at `incoming` carries.

    🔴 ONE ARITHMETIC. The `+ 1` was written in the group step and again in the follow-up lap;
    「한 천장, 두 답」 is about two COMPUTATIONS of one number, and a caller that keeps its own
    scope shape (the group step's runs across a try/finally it needs for its error return) can
    still take the VALUE from here and cannot drift.
    """
    return (incoming or 0) + 1


@contextlib.contextmanager
def chain_envelope(depth=None):
    """The envelope a chain-caused write goes out in: source, hop, collapsed events.

    🔴 [S-279, 판정 423] THE THREE CELLS HAD FOUR DIFFERENT ANSWERS. Measured 2026-09-16
    across every path that writes because a rule ran:

        group builtin (`:1484`)   source ✗   depth ✗   collapsed ✓
        group mapper  (`:1681`)   source ✓   depth ✓   collapsed ✓
        follow-up lap (`:2852`)   source ✗   depth ✓   collapsed ✓
        retroactive               source ✗   depth ✗   collapsed ✓ (and ✗ before 판정 421)

    ⚠️ THE `source ✓` IS ABOUT THIS VARIABLE, NOT ABOUT THE ENVELOPE (판정 425, measured by the
    lead). `crud.apply_batch_updates` opens its own `transaction_context` and sets
    `request_source` AGAIN, to the ITEM'S LAYER NAME, and `_outbox_envelope` reads it at that
    moment - so a write whose layer is `enrichment_auto_confirm` leaves with THAT on the
    envelope, and `_rule_accepts_event` reads it as 「not the chain」 and never asks about
    `allow_chain_trigger`. The opt-in is inert at that door. 🔴 NOT FIXED HERE AND DELIBERATELY:
    the easy repair renames the layer, which is what the join paid in `join_into.py:239-248`,
    and the layer's identity is how an operator reads 「why is this cell this value」. The real
    defect is one variable carrying two facts - the cell's LAYER and the write's CHANNEL - and
    splitting them is queued as S-280.

    The depth column is the one that costs something. 판정 402 removed the load-time refusal
    of cycles on the stated ground that 「고리는 오류가 아니라 모양이다 — 막는 것은
    max_chain_depth 다」; a hop that carries no depth is a hop the ceiling cannot count, so a
    loop through a join reset the counter to zero every lap and the ceiling never fired. The
    group path's own comment at `:2825` already named this class - 「THE LAP IS A HOP ... one
    ceiling, two answers」 - and S-278 reintroduced it at a new address.

    ⚠️ THE SCOPE IS NOT ALWAYS THIS ONE, AND THAT IS DELIBERATE. A rule causes writes from two
    places: a builtin writes for ITSELF inside `run_rule`, which uses this manager, and a
    mapper's proposals are written by the CALLER after `run_rule` returns. Stripping the
    caller's stamps - the literal reading of 판정 423-a - would leave the mapper half of every
    group with no source and no depth at all, so the group step keeps its own scope: it spans a
    try/finally it needs for its error return, and turning that into a `with` is a refactor this
    round was not asked for. What it does NOT keep is the values - it sets `CHAIN_SOURCE` and
    `outgoing_depth()` from here. 「한 천장, 두 답」 forbids two COMPUTATIONS of one number, and
    there is now one.

    ⚠️ `user` AND `transaction_id` ARE NOT HERE. They belong to the caller's transaction, not
    to the rule - the group step's `chain_<tx>` is its own identity and replay's is another.
    """
    from database.context import outbox_mode, request_chain_depth, request_source
    import event_constants

    token_source = request_source.set(CHAIN_SOURCE)
    token_depth = request_chain_depth.set(outgoing_depth(depth))
    try:
        with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
            yield
    finally:
        # Reset together: a depth left set stamps the NEXT write, and the next write may not
        # be the chain's at all.
        request_chain_depth.reset(token_depth)
        request_source.reset(token_source)


# ⚰️ [판정 562] `builtin_kind(rule)` STOOD HERE - 「which `builtin:` kind is this, or None
#   for a file mapper」. Every caller of it was choosing a door or reading a fact off the
#   table behind that door, and there is one door now. The facts that were REAL (what an
#   operator's list calls this rule, and whether what it writes can be withdrawn) moved to
#   the template registration in `chain.dynamic_mappers`; the facts about the ADDRESS
#   (`hands`, `writes_itself`) had nothing to answer once the address stopped mattering.
# 🔴 SAID PLAINLY BECAUSE THE OPPOSITE IS THE FAILURE MODE: a repair that MOVES a proxy
#   one level down and calls it removed is how the same defect returns under a new name
#   (판정 508 caught exactly that in 503's first cut).


def writes_itself(rule):
    """Does this rule write its own rows, or propose them for somebody else to write?

    🔴 [판정 497 ⓒ · 498 ④] THE FOLLOW-UP LAP ASKED 「is this a builtin」 AND MEANT THIS.
    The lap exists to hand a batch to rules that perform their own writes, and `builtin:` was
    standing in for that - an address standing in for a behaviour. They select the same three
    rules today, so nothing moves; they stop being the same the day a kind registers
    `writes_itself=False`, and on that day the address question would have handed the lap
    batch to a rule that cannot use it.

    ⚠️ ANSWERED WITHOUT RESOLVING. `resolve` is the fuller question but it IMPORTS an
    operator's module to answer, and this one is asked over every loaded rule while a cache is
    being built. Only a registered kind writes for itself, so the registration answers alone.
    """
    from chain import dynamic_mappers

    return dynamic_mappers.writes_itself((rule or {}).get("mapper"))


def runnable(name):
    """The callable a rule NAME can run as, or None - BOTH tables, one reader.

    🔴 [판정 498 ①] TWO TABLES, AND EVERY READER OF THEM IS HERE. A name may live in
    the decorator registry or in the builtin table, and three places used to look: this seat,
    the loader grammar check (「can this run」) and the dev bench. Three readers of two tables
    is how a name comes to be runnable in one place and unknown in another.

    ⚠️ THIS ANSWERS ABOUT A NAME, NOT ABOUT A RULE. `resolve` is the richer question and
    needs the whole rule (it also has to know how to hand it its rows); this is what a
    load-time check can ask when all it has is the spelling in the file.
    """
    import mapper_sdk

    if not name:
        return None
    # 🔴 [판정 562] ONE TABLE. The second one was the kind table, and the mappers built
    #   from a declaration are registered in THIS one - so a name that used to be found
    #   over there is found here, under the same spelling.
    return mapper_sdk.MAPPER_REGISTRY.get(name)


# ⚰️ [판정 562] `hands(rule)` STOOD HERE. It answered 「is this rule called with row ids or
#   with payloads」, which only had two answers because there were two doors. 판정 503 made
#   it a REGISTERED fact rather than one derived from the address, and 508 caught that the
#   first cut had only moved the proxy down a level. Both were right about the level and
#   the question itself is now gone: one door, `(db, payload[, rule=])`, every rule.


def self_writing_name(rule):
    """The registered kind a SELF-WRITING rule runs as, or None - answered WITHOUT resolving.

    🔴 [판정 501 ⓐ] `resolve` HAS A SIDE EFFECT AND THIS QUESTION MUST NOT PAY FOR IT.
    Resolving imports the operator's module, which is right when something is about to be
    RUN and wrong when a caller only wants to describe the rule. Replay asked `resolve` for
    exactly two facts - this name and `writes_itself` - and paid an `importlib` for them
    BEFORE its first page, so a dry run of a rule whose module is absent stopped being a
    report and became an exception. Both facts are registrations: a dict lookup answers them.

    ⚠️ NOT `builtin_kind` AT THE CALLER. That is the same question and the seat owns it;
    a caller spelling it is 「종류를 묻는 자리」 outside the seat again (판정 498 ④).
    """
    from chain import builtins

    from chain import dynamic_mappers

    name = (rule or {}).get("mapper")
    return name if dynamic_mappers.writes_itself(name) else None


def rule_label(rule):
    """What this rule IS on a screen - join / decide / mapper. The seat answers, from what
    the kinds REGISTERED rather than from a list kept by hand.

    🔴 [판정 498 ④] `rule_shape` compared the rule against two imported constants,
    which reads like a reference and behaves like a hand-kept list: register a fourth kind and
    it is silently labelled 「mapper」 with nothing red anywhere. The label now travels with
    the registration, so whoever adds a kind says what it is called in the same line.

    ⚠️ THE ENRICHMENT PAIR IS NOT A BUILTIN PAIR. One `decide` declaration becomes two
    chain rules and only the auto-confirm half is a builtin; the dedup half is a file mapper.
    Both answer 「decide」 because an operator reading a list of rules for one table should see
    what the DECLARATION says, not which half of it they happened to get.
    """
    from chain import dynamic_mappers

    label = dynamic_mappers.label_for((rule or {}).get("mapper"))
    if label is not None:
        return label

    from enrichment import config as enrichment_config

    name = str((rule or {}).get("name") or "")
    if (name.startswith(enrichment_config.DEDUP_PREFIX)
            or name.startswith(enrichment_config.AUTO_CONFIRM_PREFIX)):
        return "decide"
    return "mapper"


def retraction_refusal(rule):
    """None if this rule's answer can be withdrawn when its input row is deleted, or the
    operator sentence saying it cannot — 「이 종류는 되돌릴 수 없다」.

    🔴 [판정 434 ④] THE SEAT ANSWERS, AND IT ANSWERS BY NAME. A retraction aims with
    `cell_sources.origin_row_id`, so a kind whose writer never stamps it leaves cells
    nothing can find — and the note's NULL cannot carry that meaning, because NULL already
    means 「이 행은 도장이 생기기 전에 쓰였다」. Two facts under one spelling is the defect
    this whole round is about, so the second one is said out loud here instead.

    ⚠️ A FILE MAPPER IS 「말 안 함」 AND NOT 「못 한다」. `GeneralUpdateItem.origin_row_id`
    is on the schema every mapper already builds, so a mapper CAN stamp; whether the live
    ones do is not countable from here (`server/mappers/` is the owner's and gitignored).
    Naming them as unable would be a claim about rows I cannot see.
    """
    from chain import builtins

    from chain import dynamic_mappers

    mapper_name = (rule or {}).get("mapper")
    label = dynamic_mappers.label_for(mapper_name)
    name = (rule or {}).get("name") or "<이름 없는 규칙>"
    if label is None:
        return ("%s: 파일 맵퍼는 자기가 읽은 행을 «적을 수 있지만», 이 맵퍼가 적는지는 "
                "제품이 모릅니다 — 도장이 없으면 이 규칙이 쓴 칸은 철회되지 않습니다" % name)
    if dynamic_mappers.stamps_origin(mapper_name):
        return None
    return ("%s: 「%s」 종류는 자기 답이 «어느 행에서 왔는지»를 안 적습니다 — 그래서 그 행이 "
            "지워져도 이 규칙이 쓴 칸은 «그대로 남습니다»" % (name, label))


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


#: How a resolved rule takes its input. The seat hands one or the other and nothing else
#: branches on it - the difference between a fact about what a rule DOES and a fact about
#: where its code happens to live.
#: 🔴 [판정 508] DEFINED WITH THE REGISTRAR, because that is where a kind DECLARES which
#: one it takes. Re-exported here so every existing read of `rule_run.HANDS_*` is unchanged
#: and there is still one spelling.

#: What the seat knows about a rule BEFORE it runs anything.
#: 🔴 [판정 562] `hands` AND `writes_itself` ARE GONE FROM HERE. Both were answered before
#: the call so the seat could pick a door: one door takes row ids and writes for itself,
#: the other takes payloads and proposes. There is one door, so 「how is it called」 has one
#: answer, and 「did it write」 is read off the result instead of being registered.
Resolved = collections.namedtuple("Resolved", "call who accepts_rule")


class UnresolvableRule(ValueError):
    """A rule names code that cannot be found - said with the name, not with a stack."""


def resolve(rule):
    """A rule -> what to CALL, how to HAND it its rows, and whether its result can be SEEN
    without being applied. The one place in the product where a name becomes a callable.

    🔴 [판정 497·498] THREE WAYS TO NAME CODE, ONE PLACE THAT UNDERSTANDS THEM. A rule names
    its implementation as a `builtin:` key, as a `@mapper` registry name, or as an import
    path. Two of those three were already folded together inside the mapper door; the third
    sat outside as 「the builtin door」, and that is the whole of what the split was - not two
    kinds of rule, but two places that turned a name into something to call.

    🔴 `writes_itself` IS READ, NOT INFERRED. It used to be derived from 「is this a
    builtin」, which is a fact about an address rather than about behaviour, and a caller
    wanting 「can I see this without applying it」 had to ask the kind and decide for itself -
    which is how a dry run and a live lap grew separate branches from one inference. It comes
    off the registration now (`builtins.SELF_WRITING_KINDS`), so a builtin that PROPOSED its
    rows would be handled by every seat without one of them being edited.

    🔴 AN UNFINDABLE NAME IS REFUSED BY NAME. The builtin arm always did; the mapper arm let
    `importlib` throw, so an operator who mistyped a module got an ImportError stack instead
    of a sentence naming their rule and the spelling it used.

    ⚠️ RESIDUE, STATED RATHER THAN HIDDEN: `accepts_rule` is still read off the function by
    inspection instead of off a registration line. It exists only because a mapper may be
    written `(db, payload)` or `(db, payload, rule=)`, and 판정 498 puts that CONVENTION out
    of this round's scope - so the inspection cannot leave with it. What did change is that
    it happens once, here, rather than inside the door on every call.

    ⚠️ IMPORTING IS RESOLUTION, NOT RUNNING. The import-path arm imports the operator module
    exactly where the mapper door used to; nothing is executed, so a dry run can ask this
    function everything it needs without touching a row.
    """
    # ⚰️ THE KIND ARM STOOD HERE (판정 562 · 571). A rule naming a `builtin:` kind was
    #   looked up in a table this repository kept, and that table was the second door -
    #   the whole of what 「문 가르기」 named. Those names are registered mappers now
    #   (`chain.dynamic_mappers`, built in process from the declaration), so the arm below
    #   finds them without knowing they were ever special.
    import chain_bindings
    import mapper_sdk
    from chain.mapper_call import mapper_accepts_rule

    name = (rule or {}).get("name") or "<unnamed rule>"
    one_cell, module_name, function_name = chain_bindings.mapper_cells(rule)
    registered = runnable(one_cell)
    if registered is not None:
        call, who = registered, one_cell
    elif module_name and function_name:
        try:
            call = getattr(importlib.import_module(module_name), function_name)
        except (ImportError, AttributeError) as exc:
            raise UnresolvableRule(
                "rule %r names %s.%s and it could not be loaded (%s: %s)"
                % (name, module_name, function_name, type(exc).__name__, exc)) from exc
        who = "%s.%s" % (module_name, function_name)
    else:
        # 🔴 IT SAYS WHAT *IS* KNOWN, and that half is older than this seat. ⚰️ The deleted
        #    `run_builtin` listed the registered kinds when it refused, and an operator who
        #    mistypes `builtin:join_to` needs the list far more than they need the spelling
        #    they already typed. Only the kinds - the `@mapper` registry is an operator's own
        #    file and can be any length, so naming it here would bury the useful half.
        raise UnresolvableRule(
            "rule %r names no implementation this product can find: mapper=%r "
            "mapper_module=%r mapper_function=%r (known builtin kinds: %s)"
            % (name, one_cell, module_name, function_name,
               ", ".join(sorted(mapper_sdk.MAPPER_REGISTRY)) or "none registered"))
    # A file mapper PROPOSES: its rows come back as `updates` for the caller to write, which
    # is exactly what lets a dry run count them without writing anything.
    return Resolved(call, who, mapper_accepts_rule(call))


def rows_counted(value):
    """How many rows this is - handed in or proposed out, counted by ONE function.

    🔴 [판정 498] THE QUEUE VIEW COMPARES THESE NUMBERS ACROSS RULES, so they have to be
    counted the same way. They were not: the builtin door measured what it was HANDED off its
    kwargs while the mapper door measured what came BACK, across three result shapes, and the
    screen put the two side by side as though they meant one thing.
    """
    from chain.mapper_call import result_row_count

    if isinstance(value, dict):
        return result_row_count(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 1 if value else 0


def run_rule(db, rule, payloads=None, row_ids=None, done=None, depth=None):
    """Run ONE chain rule over the input it was handed, whichever way it names its code.

    `payloads` are expanded trigger rows a proposing rule is handed; `row_ids` are the rows a
    self-writing rule resolves for itself. `done` is the follow-up lap batch, passed on only
    when given, because the group path has none and an implementation that does not accept it
    would refuse the call.

    🔴 [판정 497·498] FOUR STEPS, ONE PLACE: resolve the name, register the run, call it,
    answer in one shape - and say ONE line about it. Each of those used to happen twice, once
    per door. The queue registration was the clearest case: S-246 fixed 「a builtin does not
    appear in the queue」 by writing the registration a SECOND time rather than by having one.

    🔴 THE MISSING-VALUE CLEANUP CAME UP HERE RATHER THAN AWAY. A mapper is entitled to
    assume it (owner report 2026-09-04, `cannot convert float NaN to integer`), so it is
    applied to what goes IN and what comes OUT for every rule, instead of only for the rules
    that happened to enter through the mapper door.
    """
    started = time.monotonic()
    name = (rule or {}).get("name") or "<unnamed rule>"
    target = (rule or {}).get("target_table") or "<none>"
    answer = _uniform()

    from chain import activity
    from chain.mapper_call import stage_timing, without_missing

    bound = resolve(rule)
    # 🔴 [판정 562] ONE HAND. A caller that has only row ids hands them AS payloads -
    #   the mapper reads `row_id` off each either way, and the group path already builds
    #   its `row_ids` from exactly that cell. Two shapes of hand was the calling half of
    #   the two doors.
    handed = list(payloads or ()) or [{"row_id": rid} for rid in (row_ids or ())]
    # 🔴 [판정 562] THE ENVELOPE IS ALWAYS OPEN NOW, and that is a deliberate widening.
    #   It used to open only for a rule REGISTERED as self-writing, because only a
    #   `builtin:` kind could write during its own call. Any mapper receives `db` and may
    #   write, and a write made inside a rule's call IS a chain write - so dressing it as
    #   one (source, hop, collapsed events) is what the envelope was always for. Leaving
    #   it shut for file mappers keeps the hop uncountable for exactly the writes
    #   판정 402's ceiling exists to bound.
    # ⚠️ IT DOES NOT NEST. A proposing rule's rows are written by the CALLER, after this
    #   returns, in the caller's own envelope - nothing enters two.
    envelope = chain_envelope(depth)
    # 🔴 THE LINE IS IN `finally`, SO A RULE THAT THREW STILL SAYS SO (판정 498 ③).
    # ⚰️ LEVELLING THE TWO VOCABULARIES DOWN WOULD HAVE LOST A SENTENCE THE OWNER ASKED FOR.
    #    The mapper door wrote START/END/RAISED; the builtin door wrote one line and NOTHING on
    #    a throw. Folding them by keeping the survivor would have made a raising rule log
    #    nothing at all - and 「I grepped and found no line」 reading as 「it did not run」 is the
    #    exact day (2026-09-04) this logging exists because of. One vocabulary, one line, and
    #    `error=` is the cell that tells a throw from `updates=0`.
    error = None
    # 🔴 [판정 498] THE ROW COUNT THE SCREEN AND THE LOG BOTH READ, COUNTED ONCE. The line used
    # to print `len(updates)`, which is a lie for the shape that answers in `batches`:
    # `dt_standard_map_mapper` returns a whole map's worth of cells there, and a whole map
    # would have been logged as 「0」 - the exact number an operator is trying to tell apart
    # from 「did not run」. It is whatever `run.produced` was told, so the queue view and the
    # log cannot disagree about one run.
    rows_out = None
    try:
        # 🔴 [판정 525] NO `no_rows_reason=` HERE. 「the rule wrote no rows」 was a restatement
        #   of `rows_out=0`, and it displaced the sentence the operator needed. Each arm
        #   below says what it actually knows, and says nothing when it knows nothing.
        with activity.running(name, bound.who, target, len(handed)) as run, envelope:
            # ⚰️ THE ROW-IDS ARM STOOD HERE (판정 562 · 571). It called a registered kind
            #   as `(db, rule, row_ids=, done=)` and read `written`/`refusal` back. Both
            #   CELLS survive - the body below reads them off any mapper's result - and
            #   the SIGNATURE does not: `(db, payload[, rule=])` is the one convention,
            #   which 판정 498 froze and this change does not touch.
            # ⚠️ AND THE SURVIVOR IS NOT AN ARM. It is what running a rule means, so it is
            #   not left behind an `if` with nothing on the other side.
            # A batch rule is handed the WHOLE group in one call and a per-row rule one call
            # per row - the same fan-out both live callers already do. An empty batch still
            # calls, because a batch mapper is entitled to be told its group was empty; an
            # empty per-row list is zero calls, because there is no row to speak about.
            batched = (rule or {}).get("is_batch", False)
            handed_out = [without_missing(handed)] if batched else [
                without_missing(one) for one in handed]
            results = []
            with stage_timing():
                for one in handed_out:
                    if bound.accepts_rule:
                        results.append(without_missing(bound.call(db, one, rule=rule)))
                    else:
                        results.append(without_missing(bound.call(db, one)))
            for result in results:
                if not isinstance(result, dict):
                    continue
                for cell in ("updates", "map_metadata_updates", "batches"):
                    answer[cell].extend(result.get(cell) or ())
                # 🔴 [판정 562 · 563] A MAPPER MAY NOW SAY WHY. This arm read three cells
                #   and `refusal` was filled only in the row_ids arm, so 「왜 0 인가」 was
                #   something only a registered kind could answer - and the kinds are
                #   going away. A mapper built from a declaration has to be able to say
                #   what `join_into` says today, or the move loses 판정 525's sentences.
                # ⚠️ FIRST ONE WINS. A batch rule makes exactly one call, so this only
                #   matters for a per-row rule: the first row that explains itself is the
                #   explanation, and a later silent row does not erase it.
                if answer["refusal"] is None and result.get("refusal"):
                    answer["refusal"] = result["refusal"]
                # 🔴 [판정 562 · 567] A MAPPER MAY WRITE FOR ITSELF AND SAY SO. This was
                #   `writes_itself`, a REGISTERED fact the seat had to look up before
                #   calling - and a fact about the rule's ADDRESS rather than about what
                #   it did. Read off the result, nobody is asked in advance and a mapper
                #   that writes some rows and proposes others is describable.
                # ⚠️ ABSENT IS NOT ZERO (판정 509 의 부류). A mapper that reports no count
                #   has not said it wrote nothing, so the cell stays None until one does.
                if result.get("written") is not None:
                    answer["written"] = ((answer["written"] or 0)
                                         + int(result["written"]))
            # ⚠️ PROPOSED PLUS WRITTEN. A rule does one or the other, so this equals whichever
            #    it did - and a rule that did both is counted once for each, which is what
            #    「이 규칙이 낸 행」 means to the operator reading the queue.
            rows_out = (sum(rows_counted(r) for r in results)
                        + (answer["written"] or 0))
            # 🔴 [판정 525 ②] WHAT THE PRODUCT KNOWS, AND ONLY THAT. `server/mappers/*.py`
            #   are the owner's files and this round keeps them at 0 lines, so the seat
            #   cannot ask a file mapper why. What it CAN say is the pair of counts, and
            #   that pair separates the two zeros 523 ③ asked about: 「아무것도 안 넘어왔다」
            #   and 「넘겼는데 안 나왔다」 are different sentences, not one restatement.
            # ⚠️ THE MAPPER'S OWN WORDS FIRST. The pair of counts below is what the
            #    product can say when the mapper said nothing. A mapper that DID explain
            #    itself must not have that sentence replaced by a restatement of 0 -
            #    which is the whole of 판정 525, now reachable from the mapper door too.
            run.produced(rows_out, reason=None if rows_out else (
                answer["refusal"] or (
                    "이 규칙이 볼 행이 넘어오지 않았습니다"
                    if not handed else
                    "%d 행을 넘겼고 맵퍼가 낸 행이 없습니다" % len(handed))))

    except Exception as exc:                                          # noqa: BLE001
        error = "%s: %s" % (type(exc).__name__, exc)
        raise
    finally:
        # 🔴 ONE LINE, ONE VOCABULARY (판정 498 ③). `rows_in` is what the rule was handed,
        # `rows_out` what it produced, `written` what it wrote for itself, `error` what it
        # threw - the same names whichever way the rule named its code, so an operator reads
        # every rule with one query and sees at a glance which a rule is (`rows_out=5
        # written=5` writes for itself; `rows_out=5 written=None` proposes for the caller to
        # write). The mapper door said START/END/RAISED under a second tag; an operator
        # grepping 「did this rule run」 had to know the kind before they could ask.
        # ⚠️ AND `rows_out=None` IS NOT `rows_out=0`. A rule that reported no count has not
        # said it produced nothing, which is the same distinction the outcome keeps.
        logger.info(
            "[%s] rule=%s kind=%s target=%s rows_in=%d rows_out=%s written=%s refusal=%s "
            "error=%s elapsed=%.3fs",
            RULE_LOG_TAG, name, bound.who, target, len(handed), rows_out,
            answer["written"], answer["refusal"], error, time.monotonic() - started)
    return answer
