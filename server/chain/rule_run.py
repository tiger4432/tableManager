# -*- coding: utf-8 -*-
"""The one seat that asks 「which door does this rule go through」 and runs it.

🔴 [S-279, 판정 420 ㉡] 소유자 2026-09-16: 「맵퍼 한 문인데 왜 이름이 달라」 · 「문 가르기
금지」. One chain grammar declares enrich, join and decide; the DISPATCHERS were two - a file
mapper went through `mapper_call.execute_custom_mapper(module, function, ...)` and a
`builtin:` kind through `synthesis.run_builtin(kind, ...)` - and every caller that could run a
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
import contextvars
import importlib
import itertools
import logging
import time

from sqlalchemy import event
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# 🔴 [판정 562] IMPORTED FOR ITS EFFECT, AND THIS IS THE SEAT THE OLD ARRANGEMENT USED.
#   `chain.synthesis` was imported here too, and importing it FILLED the kind table - which
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


def layer_of_a_rules_write(name, origin_row_id=None) -> str:
    """The layer a rule's proposed cell goes under (총괄 09f3cd289 ①, 소유자 10-09 「모든 맵퍼의 소스네임은
    chain_ingestion 에서 못 바꾸게」): chain_ingestion whatever its mapper wrote - an item naming none
    was the person's layer - and a row layer keeps its bracket. An item read from a row is that row's
    layer, `chain_ingestion (<origin_row_id>)` (총괄 8ec008914 - one layer per source row, so taking a
    row back takes only its own). The names the product gave a meaning stay: auto-confirm's two and
    the enrichment backfill's. Asked at the one seat the chain writes through (`ingestion_worker`'s
    write loop)."""
    from chain.enrichment import backfill, candidates
    from database import crud

    writer = crud.layer_writer(name)
    if writer in (candidates.SOURCE_NAME, candidates.SOURCE_NAME_PARTIAL_KEY, backfill.SOURCE_NAME):
        return name
    if origin_row_id:
        return crud.merged_layer_name(CHAIN_SOURCE, origin_row_id)
    if writer == CHAIN_SOURCE:
        return name
    return CHAIN_SOURCE + str(name or "")[len(writer):]


def outgoing_depth(incoming):
    """The hop number a write caused by a rule woken at `incoming` carries.

    🔴 ONE ARITHMETIC. The `+ 1` was written in the group step and again in the follow-up lap;
    「한 천장, 두 답」 is about two COMPUTATIONS of one number, and a caller that keeps its own
    scope shape (the group step's runs across a try/finally it needs for its error return) can
    still take the VALUE from here and cannot drift.
    """
    return (incoming or 0) + 1


def outgoing_channel(woken_by_a_replay=False):
    """The channel a write caused by a rule goes out on: the chain's - or, when the group
    was woken by a replay's trigger events (`only_rule`), the replay's own, which wakes no rule
    (총괄 c2995cdd8). One author for the two doors that stamp it."""
    import event_constants
    return (event_constants.CHANNEL_RETROACTIVE if woken_by_a_replay
            else event_constants.CHANNEL_CHAIN)


@contextlib.contextmanager
def chain_envelope(depth=None, woken_by_a_replay=False, cascade=False, written_by=(), run=None):
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
    from database.context import (outbox_mode, request_cascade, request_chain_depth,
                                  request_channel, request_run_id, request_source,
                                  request_written_by)
    import event_constants

    token_source = request_source.set(CHAIN_SOURCE)
    # Whose write this is - the declaration's, so none of its rules is woken by it (ebefd20e8).
    token_written_by = request_written_by.set(tuple(written_by) or None)
    token_depth = request_chain_depth.set(outgoing_depth(depth))
    # [⓪] The channel beside the source: crud re-sets the source to the item's layer and
    # never this, so a write whose layer is not `chain_ingestion` still reads as the chain.
    token_channel = request_channel.set(outgoing_channel(woken_by_a_replay))
    token_cascade = request_cascade.set(bool(cascade))
    # [RUN] what a run's events woke is that run's work too (총괄 b3a4334db).
    token_run = request_run_id.set(run)
    try:
        with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
            yield
    finally:
        # Reset together: a depth left set stamps the NEXT write, and the next write may not
        # be the chain's at all.
        request_run_id.reset(token_run)
        request_cascade.reset(token_cascade)
        request_channel.reset(token_channel)
        request_chain_depth.reset(token_depth)
        request_written_by.reset(token_written_by)
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
    # 🔴 A MISS HERE IS 「not registered」, WHICH AT BOOT MEANT 「not imported YET」.
    #    This seat is what `load_chain_rules` and the save gate ask, and it runs
    #    before the warmup that walks the package - so the fill belongs on the miss,
    #    once, rather than in whichever caller happens to be early today.
    if name not in mapper_sdk.MAPPER_REGISTRY:
        mapper_sdk.ensure_discovered()
    # 🔴 [판정 562] ONE TABLE. The second one was the kind table, and the mappers built
    #   from a declaration are registered in THIS one - so a name that used to be found
    #   over there is found here, under the same spelling.
    return mapper_sdk.MAPPER_REGISTRY.get(name)


# ⚰️ [판정 562] `hands(rule)` STOOD HERE. It answered 「is this rule called with row ids or
#   with payloads」, which only had two answers because there were two doors. 판정 503 made
#   it a REGISTERED fact rather than one derived from the address, and 508 caught that the
#   first cut had only moved the proxy down a level. Both were right about the level and
#   the question itself is now gone: one door, `(db, payload[, rule=])`, every rule.


# ⚰️ [총괄 2026-09-23] `self_writing_name(rule)` AND `writes_itself(rule)` STOOD HERE.
#   The first had two readers, both in `replay`, and neither was a flag: one PICKED THE PAGE
#   LOOP'S ARM - whether a failed page costs that page or the whole run - and one was the
#   stat `admin/retroactive` reads to choose between 「다시 계산할 행」 and 「덮어쓸 셀」, the
#   number an operator approves a backfill on. Nothing writes for itself now, so both
#   answers are constant and both readers are gone.
# 🔴 THE SYMPTOM, KEPT AS THE CONTROL GROUP: restore the arm while the join already
#   proposes and the consent screen reads 「덮어쓸 셀 0」 in front of a run that rewrites
#   every row - the accident named above `retroactive.py`'s own pre-count.

def rule_label(rule):
    """What this rule IS on a screen - join / decide / mapper. The seat answers, from what
    the kinds REGISTERED rather than from a list kept by hand.

    🔴 [판정 498 ④] `rule_shape` compared the rule against two imported constants,
    which reads like a reference and behaves like a hand-kept list: register a fourth kind and
    it is silently labelled 「mapper」 with nothing red anywhere. The label now travels with
    the registration, so whoever adds a kind says what it is called in the same line.

    ⚰️ AND THE ENRICHMENT PAIR IS ANSWERED BY ITS REGISTRATIONS NOW. A branch here read the
    rule's NAME (`startswith(DEDUP_PREFIX)`) to return 「decide」, because one `decide`
    declaration makes two chain rules and only one of them was a registered mapper. That
    branch was the dedup half's label, declared in a second place and keyed on an ADDRESS -
    rename the synthesized prefix and the label silently became 「mapper」. Both halves now
    register with `label: "decide"`, which is still the DECLARATION's word rather than the
    half's: an operator reading a list of rules for one table should not have to know which
    half they got.
    """
    from chain import dynamic_mappers

    label = dynamic_mappers.label_for((rule or {}).get("mapper"))
    if label is not None:
        return label
    return "mapper"


#: rule name -> did its last run that proposed rows carry `origin_row_id` on them. This process's
#: runs only: after a restart a rule is 「not known yet」 until it runs again.
_ORIGIN_SEEN = {}


def item_cell(item, name):
    """One cell of a proposed item, whether the mapper built a dict or a `GeneralUpdateItem`."""
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)


def signed(result, declaration, rule=None, kept_out=None, handed=None, unmatched=None):
    """A proposal signed by the rule that made it (총괄 bc9710454 가-1 ㄱ): every item it proposes - updates, map
    metadata, its batches' items and its further pages as they are asked - carries the rule's declaration in
    `updated_by`, which the write puts on the layer row. A recount that came back blank takes back its own rule's
    plain chain layer by it, and not another rule's that wrote the cell after it.

    🔴 AND KEPT TO WHAT THE RULE WRITES (총괄 a7b67be28 ㄱ): a rule that lists its `target_columns` has every other
    cell taken out of its updates and its batches' items here - whichever kind of mapper made them - counted into
    `kept_out` {column: cells} for `say_kept_out`. Map metadata goes to another table and is not narrowed.

    🔴 AND EACH ITEM WITH THE ROW IT CAME FROM (총괄 09f58844f ⑦): `handed` the rows the call was handed - an item
    its mapper left without one gets it here (`origin_by_key`), `unmatched` [rows, of] counting those it could not
    for `say_origin_unknown`."""
    import chain_bindings

    if not isinstance(result, dict):
        return result
    batched = [item for batch in result.get("batches") or () for item in (item_cell(batch, "updates") or ())]
    written = chain_bindings.written_columns(rule)
    if written is not None:
        for item in itertools.chain(result.get("updates") or (), batched):
            cells = item_cell(item, "updates") or {}
            for column in [column for column in cells if column not in written]:
                del cells[column]
                kept_out[column] = kept_out.get(column, 0) + 1
    for item in itertools.chain(result.get("updates") or (), result.get("map_metadata_updates") or (), batched):
        if isinstance(item, dict):
            item["updated_by"] = declaration
        else:
            item.updated_by = declaration
    if handed is not None:
        origin_by_key(rule, handed, itertools.chain(result.get("updates") or (), batched), unmatched)
    more = result.get("next_page")
    if more is not None:
        def page():
            out, missed = {}, [0, 0]
            answer = signed(more(), declaration, rule, out, handed, missed)
            say_kept_out(rule, out)
            say_origin_unknown(rule, missed)
            return answer
        result["next_page"] = page
    return result


def say_kept_out(rule, kept_out):
    """The one line a run (or a further page) says about the cells its rule's `target_columns` kept out."""
    if kept_out:
        logger.info("[%s] rule %s: %d cell(s) in %s not in its written columns, not written", RULE_LOG_TAG,
                    (rule or {}).get("name"), sum(kept_out.values()), sorted(kept_out))


def origin_by_key(rule, handed, items, unmatched=None):
    """⑦ (총괄 09f58844f): an item its mapper left without the row it came from - its frame cut to the columns it
    writes drops `mapper_sdk.ORIGIN_MARK` - gets the handed row whose values in the target's key columns
    (`cell_layer.key_columns`) are the item's, when exactly ONE handed row has them. None or several: left without,
    and counted in `unmatched` [rows, of]. A rule whose mapper declares it stamps nothing (an aggregate) is not asked,
    nor an item writing only the cells its mapper gathers from many rows (a join's `take ... fn`, 총괄 10-23)."""
    mapper = (rule or {}).get("mapper")
    gathered = dynamic_mappers.gathered_columns(mapper, rule)
    items = [item for item in items if not item_cell(item, "origin_row_id")
             and not (gathered and set(item_cell(item, "updates") or ()) <= gathered)]
    if not items or dynamic_mappers.stamps_origin(mapper, rule) is False:
        return
    from chain import cell_layer

    keys = sorted(cell_layer.key_columns((rule or {}).get("target_table")))
    import mapper_sdk

    # the handed rows read as a mapper reads them - one flat row each, the cell envelopes dropped
    frame, rows = mapper_sdk.payloads_to_df(list(handed or ())), {}
    if keys and "row_id" in frame.columns and all(key in frame.columns for key in keys):
        for record in frame[["row_id", *keys]].itertuples(index=False):
            rows.setdefault(tuple(str(value) for value in record[1:]), []).append(str(record[0]))
    missed = 0
    for item in items:
        cells = item_cell(item, "updates") or {}
        found = rows.get(tuple(str(cells[key]) for key in keys)) if keys and all(key in cells for key in keys) else None
        if found is None or len(found) != 1:
            missed += 1
        elif isinstance(item, dict):
            item["origin_row_id"] = found[0]
        else:
            item.origin_row_id = found[0]
    if unmatched is not None:
        unmatched[0] += missed
        unmatched[1] += len(items)


def say_origin_unknown(rule, unmatched):
    """The one line a run (or a further page) says about its rows that carry no row they came from (⑦)."""
    if unmatched and unmatched[0]:
        from chain import cell_layer

        logger.warning("[ChainRetract] origin unknown - rule %s: %d of %d row(s) carry no row they came from and match "
                       "no single handed row by %s - deleting or editing their source will not take them back",
                       (rule or {}).get("name"), unmatched[0], unmatched[1],
                       sorted(cell_layer.key_columns((rule or {}).get("target_table"))))


def output_stamps(items):
    """True when any of these proposed items carries the row it was read from, False when none
    does, None when there are none to ask."""
    items = list(items or ())
    return any(item_cell(item, "origin_row_id") for item in items) if items else None


def stamps_its_origin(rule):
    """Does this rule's output say which row it came from? True · False · None (not known yet).

    🔴 [총괄 4c3417ccb ③] ASKED OF THE OUTPUT - the last run of this rule that proposed rows. Until
    a run says, the mapper's declared fact answers (`mapper_sdk.register(…, facts=)`), and a mapper
    that declares nothing is not known yet.
    """
    seen = _ORIGIN_SEEN.get((rule or {}).get("name"))
    if seen is not None:
        return seen
    # what its mapper declares - a kind the product builds, or a file mapper (총괄 016a766af)
    return dynamic_mappers.stamps_origin((rule or {}).get("mapper"), rule)


def columns_a_rule_writes(rule, items=(), more=False):
    """The columns this rule writes, or None - not known.

    This run's rows when it proposed any. 🔴 [총괄 10-08] A run that proposed none still owns what it
    wrote before - a join whose value row moved to a key no left row carries proposes nothing, and
    its old cells have to go - so then its mapper's declaration answers (`dynamic_mappers.
    columns_declared_for` - a kind the product builds, or a file mapper that registered `columns`,
    총괄 016a766af). ⚰️ What it last wrote in this process answered after that - a slot that had not run the rule
    answered «not known» (총괄 09f58844f ⑥); the write seat hands every page's rows, and reads the layers the rule
    left when neither answers (`ingestion_worker._columns_its_layers_hold`).
    A rule that lists its `target_columns` answers with them first (총괄 a7b67be28 ㄱ).
    """
    import chain_bindings

    listed = chain_bindings.written_columns(rule)
    if listed is not None:
        return listed
    columns = {column for item in items or () for column in (item_cell(item, "updates") or ())}
    if more:
        # an answer with more pages (`next_page`) is its first page here - with the declaration, or a join whose first
        # page skipped a blank take in every row leaves that column's old cells (총괄 a02ad0f2b ㄱ)
        columns |= set(dynamic_mappers.columns_declared_for(rule) or ())
    if columns:
        return columns
    declared = dynamic_mappers.columns_declared_for(rule)
    return set(declared) if declared else None


def retraction_refusal(rule):
    """None if this rule's answer can be withdrawn when its input row is deleted or edited, or
    the operator sentence saying it cannot — 「이 규칙은 되돌릴 수 없다」.

    🔴 [판정 434 ④] THE SEAT ANSWERS, AND IT ANSWERS BY NAME. A retraction aims with
    `cell_sources.origin_row_id`, so a rule whose output never carries it leaves cells
    nothing can find — and the note's NULL cannot carry that meaning, because NULL already
    means 「이 행은 도장이 생기기 전에 쓰였다」. So it is said out loud here instead.

    ⚠️ NOT KNOWN YET IS SILENCE (총괄 4c3417ccb ③). A rule that has not run in this process has
    said nothing about its output, and a warning on every deletion would be a guess.
    """
    if stamps_its_origin(rule) is not False:
        return None
    name = (rule or {}).get("name") or "<이름 없는 규칙>"
    return ("%s: 「%s」 규칙의 출력에 «어느 행에서 왔는지»가 실리지 않습니다 — 그래서 그 행이 "
            "지워지거나 고쳐져도 이 규칙이 쓴 칸은 «그대로 남습니다»" % (name, rule_label(rule)))


def _uniform():
    """The answer's shape, with every cell present whichever door ran.

    `updates`/`map_metadata_updates`/`batches` are what a rule PROPOSES and the caller writes;
    `written` is what a rule wrote FOR ITSELF and the caller must not write again. A kind that
    writes for itself proposes nothing, so a caller can extend all three lists unconditionally
    and get a no-op - that is what lets the branch disappear from the callers.

    ⚠️ `written` IS None, NOT 0, WHEN NOBODY COUNTED. 「안 셌다」 and 「0 이었다」 are different
    facts, and `chain.synthesis` already keeps them apart for the same reason.

    `next_page` holds, per proposal that pages, the call for its remaining pages and what its first page said
    (`rows_total` · `pages` · `first` - 총괄 e10c58e5e · 634c06fc3) - this seat only carries them; the write door asks
    the calls, at the rule's place in the order, and says each page against them.
    """
    return {"updates": [], "map_metadata_updates": [], "batches": [],
            "written": None, "refusal": None, "next_page": [], "stamps_origin": None}


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
#: `fetch`: the mapper's read half (`FETCH`), or None - what it reads, read by the fetch seat (`prepare`) before any
#: rule runs and handed to the call as `fetched=` (총괄 78eec1ec1 «데이터 받기»).
Resolved = collections.namedtuple("Resolved", "call who accepts_rule fetch", defaults=(None,))

#: The attribute a mapper carries its read half on: `fetch(db, unit, rule=rule)` -> what that call is `fetched=`.
FETCH = "fetch"

#: What the fetch seat hands a rule's run: the mapper, the rows it is handed, the calls it is handed them in (one
#: for a batch rule, one a row otherwise) and what each call's mapper read (`fetched`, one a call, None without a
#: read half). `failed`: what a read raised - raised by `run_rule` where the call's would be, so it is said and
#: counted the same way.
Prepared = collections.namedtuple("Prepared", "bound handed offered units fetched failed", defaults=(None,))


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

    ⚰️ [총괄 2026-09-23] A PARAGRAPH HERE EXPLAINED `writes_itself` - 「IS READ, NOT
    INFERRED ... it comes off the registration now (`synthesis.SELF_WRITING_KINDS`)」. There
    is no fact left to read: a mapper REPORTS what it wrote and the seat adds that up, which
    is what that paragraph wanted and could not have while a registration answered first.


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
    return Resolved(call, who, mapper_accepts_rule(call), getattr(call, FETCH, None))


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


def gates_of(rule) -> dict:
    """{gate: [columns]} - a rule's row gates (`require` · `exclude`)."""
    import chain_bindings

    return {gate: list((rule or {}).get(gate) or ()) for gate in chain_bindings.ROW_GATE_KEYS}


def gate_misses(gates, cells, table=None) -> list:
    """[(gate, item, by values)] a row of `cells` {column: value} of `table` fails - [] when the rule takes it. THE row-gate
    judgement: a column name - `require` wants it filled, `exclude` blank (`crud.is_blank_value`); {column: [values]} -
    `require` wants one of them, `exclude` none (총괄 9a5206e0b), a value and the cell spelled by the one key speller by
    the column's declared type (`map_overlay.canonical_bind_value`, 1460cfef2 - 1 · 1.0 · 001 one value, "" a blank).
    `gate_conditions` is the same judgement in SQL, so the rows a rule is handed and the rows a recount counts are one
    set (총괄 63c747046). `item`: the column, or «column [values]» - `held_back` says the two in their own words."""
    import chain_bindings
    import map_overlay
    from database import crud

    out = []
    for gate in chain_bindings.ROW_GATE_KEYS:
        for column, values in chain_bindings.gate_items(gates.get(gate)):
            if values is None:
                hit = not crud.is_blank_value(cells.get(column))
            else:
                hit = map_overlay.canonical_bind_value(table, column, cells.get(column)) in {
                    map_overlay.canonical_bind_value(table, column, value) for value in values}
            if hit == (gate == chain_bindings.EXCLUDE_KEY):
                out.append((gate, column if values is None else "%s [%s]" % (column, ", ".join(map(str, values))),
                            values is not None))
    return out


def gate_conditions(gates, model) -> list:
    """`gate_misses` in SQL over `model`'s columns: one condition per gate item, true for a row the rule takes."""
    import chain_bindings
    from sqlalchemy import not_
    from database import crud

    out = []
    for gate in chain_bindings.ROW_GATE_KEYS:
        for column, values in chain_bindings.gate_items(gates.get(gate)):
            if values is None:
                out.append((crud.not_blank_sql_condition if gate == chain_bindings.REQUIRE_KEY
                            else crud.blank_sql_condition)(crud.column_text_sql(getattr(model, column))))
            else:
                one_of = _one_of_sql(model, column, values)
                out.append(one_of if gate == chain_bindings.REQUIRE_KEY else not_(one_of))
    return out


def _one_of_sql(model, column, values):
    """`column` is one of `values` - never NULL: the cell and the values spelled by the one key speller's SQL twin
    (`notation_norm.key_expression_sql`, a datetime through `assy_key_instant`), a number compared as a number (1 · 1.0 ·
    001 one value on either database); a blank value is a blank cell."""
    import map_overlay
    import notation_norm
    from sqlalchemy import false, func, or_

    table = model.__table__.name
    spelled = {map_overlay.canonical_bind_value(table, column, value) for value in values}
    blank = None in spelled
    spelled.discard(None)
    cell = getattr(model, column)
    if map_overlay.declared_column_type(table, column) == "number":
        numbers = []
        for value in spelled:
            try:
                numbers.append(float(value))
            except ValueError:
                pass                                   # a word on a number column - no cell is it
        found = func.coalesce(cell.in_(sorted(numbers)), False) if numbers else false()
        return or_(found, cell.is_(None)) if blank else found
    expression = func.trim(notation_norm.key_expression_sql(cell, None, map_overlay.key_time_zone(table, column)))
    return expression.in_(sorted(spelled) + ([""] if blank else []))


def held_back(rule, handed) -> tuple:
    """-> (the rows handed to the rule, {column: rows held back because it was empty}).

    🔴 [총괄 49052cbdd, 소유자 「특정 칼럼 집합이 다 찬 행만 복사」] A rule's `require` names
    trigger-table columns a row must have filled; a row with any of them empty is not handed
    over at all - before the mapper, so it never has to guard against them. 「Empty」 is the
    product's one judgement (`crud.is_blank_value`). Asked HERE because every kind and every
    replay hands its rows through this seat - and the enrichment backfill calls it too
    (총괄 2276e38cf ③), so the live chain and the backfill cannot answer `require` apart.
    The line is said here for the same reason: one event, one sentence, whoever asked.

    `exclude` (총괄 016a766af) is the other half, judged in the same pass: a row with any of
    those columns filled is not handed over either.

    An edit that took a row OUT of the gates (its old values passed, its new ones do not) is, to a rule that reads
    rows that left (`allow_delete_trigger`), a row that left: handed as a deletion is - no data, the row as it was -
    so the key it left is recounted without it (총괄 63c747046 (b)). A row that was never in is not handed."""
    import chain_bindings
    import event_constants

    gates = gates_of(rule)
    if not any(gates.values()):
        return handed, {}
    table = (rule or {}).get("trigger_table")
    reads_leaving = chain_bindings.takes_deletions(rule)
    #: the words of a miss, by gate and by item - a name item misses on blank or filled, a value item on its values
    words = {(chain_bindings.REQUIRE_KEY, False): "required column(s) empty",
             (chain_bindings.REQUIRE_KEY, True): "required value(s) missing",
             (chain_bindings.EXCLUDE_KEY, False): "excluding column(s) filled",
             (chain_bindings.EXCLUDE_KEY, True): "excluding value(s) found"}
    kept, missed, left = [], {said: collections.Counter() for said in words}, 0
    for payload in handed:
        data = payload.get("data") if isinstance(payload, dict) else None
        old = event_constants.old_values_of(payload)
        # a deletion has no data - its row is judged as it was (총괄 355ee9840 3)
        now = {column: (cell or {}).get("value") if isinstance(cell, dict) else cell
               for column, cell in data.items()} if data else dict(old)
        misses = gate_misses(gates, now, table)
        if not misses:
            kept.append(payload)
            continue
        for gate, item, by_values in misses:
            missed[gate, by_values][item] += 1
        was = {**now, **old}
        if reads_leaving and data and old and not gate_misses(gates, was, table):
            kept.append({**payload, "data": {}, event_constants.OLD_VALUES_KEY: was})
            left += 1
    said = [(words[said], missed[said]) for said in words if missed[said]]
    if said:
        logger.info("[Chain] %s: %d row(s) not handed over - %s%s",
                    (rule or {}).get("name") or "<unnamed rule>", len(handed) - len(kept) + left,
                    "; ".join("%s: %s" % (line, ", ".join("%s=%d" % pair for pair in sorted(c.items())))
                              for line, c in said),
                    " - %d of them handed as rows that left (an edit took them out)" % left if left else "")
    return kept, {item: n for said in missed for item, n in missed[said].items()}


def prepare(db, rule, payloads=None, row_ids=None) -> Prepared:
    """THE FETCH SEAT (총괄 78eec1ec1 «데이터 받기»): the rows `rule` is handed (`held_back`), the calls it is handed
    them in - the WHOLE group in one call for a batch rule, one call a row otherwise; an empty batch still calls, a
    group `require` emptied does not (총괄 2276e38cf ②) - and what each call's mapper reads, read here by its read
    half (`FETCH`). The group path asks this before any rule runs, so no rule reads while rules run and write; a
    path that does not ask it yet gets it from `run_rule`, the same seat."""
    from chain.mapper_call import without_missing

    bound = resolve(rule)
    # 🔴 [판정 562] ONE HAND. A caller that has only row ids hands them AS payloads -
    #   the mapper reads `row_id` off each either way, and the group path already builds
    #   its `row_ids` from exactly that cell. Two shapes of hand was the calling half of
    #   the two doors.
    handed = list(payloads or ()) or [{"row_id": rid} for rid in (row_ids or ())]
    offered = len(handed)
    handed, _empty = held_back(rule, with_the_whole_keys(db, rule, handed))
    batched = (rule or {}).get("is_batch", False)
    units = [without_missing(handed)] if batched and (handed or not offered) else [
        without_missing(one) for one in handed]
    try:
        fetched = [bound.fetch(db, unit, rule=rule) if bound.fetch else None for unit in units]
    except Exception as exc:                                          # noqa: BLE001
        return Prepared(bound, handed, offered, units, [], exc)
    return Prepared(bound, handed, offered, units, fetched)


def with_the_whole_keys(db, rule, handed) -> list:
    """`handed` and the rows there are now of each `group_by` key a handed row is in or left, read from the trigger
    table - a row once (소유자 10-22 「ㅇㅇ 넓혀」: a group_by rule answers for its key, so it is handed the key whole,
    the way a whole-map rule is handed its map). The key is `spelled_group_key`'s, the one the grouping makes."""
    from chain import ingestion_worker
    from database import models
    import event_constants
    import outbox_expand
    from sqlalchemy import and_, or_

    columns = ingestion_worker.group_by_columns(rule)
    table = str((rule or {}).get("trigger_table") or "")
    model = models.DYNAMIC_TABLES.get(table)
    if not columns or model is None or not handed:
        return handed
    keys, values, blank = set(), {column: set() for column in columns}, set()
    for payload in handed:
        data = payload.get("data") or {}
        now = {column: cell.get("value") if isinstance(cell, dict) else cell for column, cell in data.items()}
        old = event_constants.old_values_of(payload)
        for row in ([now] if now else []) + ([dict(now, **old)] if old else []):
            keys.add(ingestion_worker.spelled_group_key(rule, table, row))
            for column in columns:
                value = row.get(column)
                (blank.add(column) if value is None or str(value).strip() == "" else values[column].add(value))
    if not keys:
        return handed
    conditions = [or_(*([getattr(model, c).in_(sorted(values[c], key=str))] if values[c] else []) +
                      ([getattr(model, c).is_(None)] if c in blank else [])) for c in columns]
    seen = {payload.get("row_id") for payload in handed}
    names = outbox_expand._data_columns(model)
    more = []
    for row in db.query(model).filter(and_(*conditions)):
        if row.row_id in seen:
            continue
        payload = outbox_expand._synthesize_payload(row, names, {})
        if ingestion_worker.spelled_group_key(rule, table, payload.get("data") or {}) in keys:
            seen.add(row.row_id)
            more.append(payload)
    return handed + more


#: Statements a mapper ran during its call (`_count_reads`), while a run counts them.
_READS = contextvars.ContextVar("rule_run_reads", default=None)
#: The rules this process has said read outside the fetch - once each.
_SAID_READING = set()


def _count_reads(conn, cursor, statement, parameters, context, executemany):
    """A read during a mapper's call, counted for `run_rule` - a SELECT, nothing else."""
    reads = _READS.get()
    if reads is not None and (str(statement).split(None, 1) or [""])[0].upper() in ("SELECT", "WITH"):
        reads[0] += 1


def count_reads():
    """Count mappers' reads in this process (`_count_reads`), once - attached where the chain worker and a slot warm
    up (`ingestion_worker.warmup_worker`), so a process that runs no rule (the API, the watcher, the scheduler) carries
    no hook on its engines (총괄 10-22)."""
    if not event.contains(Engine, "before_cursor_execute", _count_reads):
        event.listen(Engine, "before_cursor_execute", _count_reads)


def run_rule(db, rule, payloads=None, row_ids=None, done=None, depth=None,
             woken_by_a_replay=False, cascade=False, run=None, prepared=None):
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

    prepared = prepared or prepare(db, rule, payloads, row_ids)
    bound, handed, offered = prepared.bound, prepared.handed, prepared.offered
    # 🔴 [판정 562] THE ENVELOPE IS ALWAYS OPEN NOW, and that is a deliberate widening.
    #   It used to open only for a rule REGISTERED as self-writing, because only a
    #   `builtin:` kind could write during its own call. Any mapper receives `db` and may
    #   write, and a write made inside a rule's call IS a chain write - so dressing it as
    #   one (source, hop, collapsed events) is what the envelope was always for. Leaving
    #   it shut for file mappers keeps the hop uncountable for exactly the writes
    #   판정 402's ceiling exists to bound.
    # ⚠️ IT DOES NOT NEST. A proposing rule's rows are written by the CALLER, after this
    #   returns, in the caller's own envelope - nothing enters two.
    from chain import rule_shape
    declaration = rule_shape.declaration_of(rule)
    envelope = chain_envelope(depth, woken_by_a_replay, cascade,
                              written_by=(declaration,), run=run)
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
            if prepared.failed is not None:
                raise prepared.failed
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
            # ⚠️ [총괄 2276e38cf ②, 소유자 「맵퍼 에러 방지」] EXCEPT A GROUP `require` EMPTIED:
            #   rows were offered and every one was held back, so there is nothing to tell.
            # 🔴 THE CALLS ARE THE FETCH SEAT'S (`prepare`): the same fan-out, and each call handed what its
            #    mapper's read half read. A mapper that reads in its call anyway is said once (총괄 78eec1ec1).
            results, kept_out, unmatched = [], {}, [0, 0]
            reads = [0]
            token = _READS.set(reads)
            try:
                with stage_timing():
                    for one, got in zip(prepared.units, prepared.fetched):
                        rows = one if isinstance(one, list) else [one]
                        kwargs = dict({"rule": rule} if bound.accepts_rule else {},
                                      **({"fetched": got} if bound.fetch else {}))
                        results.append(signed(without_missing(bound.call(db, one, **kwargs)), declaration,
                                              rule, kept_out, rows, unmatched))
            finally:
                _READS.reset(token)
            if reads[0] and name not in _SAID_READING:
                _SAID_READING.add(name)
                logger.info("[%s] rule=%s reads outside the fetch: %d statement(s) in its mapper's call - "
                            "what it reads is not handed by the fetch seat", RULE_LOG_TAG, name, reads[0])
            say_kept_out(rule, kept_out)
            say_origin_unknown(rule, unmatched)
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
                # A proposal may say there is more: a call returning the next page in the same
                # shape. Any proposal can carry it; nothing here asks which rule it came from.
                if result.get("next_page") is not None:
                    answer["next_page"].append({
                        "call": result["next_page"], "rows_total": result.get("rows_total"),
                        "pages": result.get("pages"), "first": len(result.get("updates") or ())})
            # 🔴 WHAT ITS OUTPUT SAYS ABOUT WHERE IT CAME FROM (총괄 4c3417ccb ③) - the edit's
            #    withdrawal reads it here, a deletion's warning from `_ORIGIN_SEEN`.
            proposed = list(answer["updates"]) + [item for batch in answer["batches"]
                                                  for item in (item_cell(batch, "updates") or ())]
            answer["stamps_origin"] = output_stamps(proposed)
            if answer["stamps_origin"] is not None:
                _ORIGIN_SEEN[name] = answer["stamps_origin"]
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
