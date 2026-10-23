"""Retroactive (backfill) operation registry.

This module names four existing operations, validates their parameters, calls the
same implementation in dry-run mode for previews, and publishes an outbox event
for apply mode. It does not implement a second executor.

Operations:
- chain_replay (R1)
- withdraw (R2)
- enrichment_backfill
- enrichment_confirm

All four write in bounded chunks. scan_limit bounds only previews and each
response names whether its count is exact or sampled. Protected/user-pinned values
remain guarded by the underlying operation.
"""
import contextlib
import json
import logging
import os
import threading
import time
import uuid

import event_constants
# Who runs a job and whether that process is alive - moved to the heartbeats they read,
# because the collectors ask the same question (총괄 c44a7d2e4). Same names here.
from utils.heartbeat import runner_identity, runner_state as _runner_state  # noqa: E402,F401

logger = logging.getLogger(__name__)

#: Outbox event type the trigger publishes and the auto-update scheduler consumes.
#: Defined in `event_constants` (not here) because the chain worker must skip it
#: like it skips SCHEDULER_RUN_NOW, and that worker has no business importing this
#: module. A control event that reached the chain grouping logic would be read as
#: a data transaction.
RUN_EVENT_TYPE = event_constants.EVENT_RETROACTIVE_RUN

#: `DatabaseOutbox.table_name` is NOT NULL-ish by convention and is what the
#: scheduler logs; a retroactive run has no single table, so it carries this.
RUN_EVENT_TABLE = event_constants.RETROACTIVE_RUN_TABLE

COUNT_EXACT = "exact"
COUNT_SAMPLE = "sample"
COUNT_UPPER_BOUND = "upper_bound"

#: Scan budget for the counts that have to walk rows. Same shape and same reason
#: as `main.ENRICHMENT_DRY_RUN_DEFAULT_LIMIT`: a request path gets a sample.
DEFAULT_SCAN_LIMIT = 200
MAX_SCAN_LIMIT = 2000


def _count_until():
    """When a count that reads row by row stops - the page cap from now: a count answers in the request, with no
    line, so within the 5 s or «at least» (소유자 「5 초」, 총괄 2ea5ee2a7 ②)."""
    import time
    import pacing

    return time.monotonic() + pacing.PAGE_SECONDS_CAP


def _cut_said():
    """The sentence a count cut at `_count_until` ends with."""
    import pacing

    return " - stopped counting at %g s; the run counts the rest as it goes" % pacing.PAGE_SECONDS_CAP
#: How much of a failed run's error its row keeps (`_mark_run`). A rule run's failure record
#: gives way in its reason to fit, so the row holds whole JSON (총괄 ff60fe669 ①).
RUN_ERROR_LIMIT = 2000


#: 🔴 THE CLOSED LIST FROM `task/APPLICATION_RUN_WORDS.md`. An operation CHOOSES one of
#: these for a number it reports; it does not write a sentence. The screen turns the value
#: into words, so a new operation cannot invent a seventh way of saying nothing - the list
#: is closed and operations point INTO it.
#:
#: 🔴 TWO OF THEM READ AS THEIR OPPOSITE, which is the whole reason the vocabulary exists:
#:     already_missing  reads as "nothing to withdraw, so nothing to do"
#:                      means  "it is already gone - run this to put it back"
#:     cannot_point     reads as "nothing to make, so we are finished"
#:                      means  "the old atoms cannot be named - the declaration needs looking at"
#: Both are "zero, and there IS work". `truly_none` is the one that really means none.
#:
#: The field is NULL for an ordinary number, and that null is a statement rather than a
#: gap: it says "this number means what it says". A count that reports a plain exact
#: positive figure has nothing to choose from here, because none of the six is true of it.
ABSENCE_NOT_YET = "not_yet"                  # 아직 — 시작 전, 또는 멈추는 중
ABSENCE_NOT_EXHAUSTIVE = "not_exhaustive"    # 전수가 아님 — 이 수로 완료를 판단하지 않는다
ABSENCE_CANNOT_POINT = "cannot_point"        # 가리킬 수 없음 — 올린다. 태워도 안 고쳐진다
ABSENCE_TRULY_NONE = "truly_none"            # 정말 없음 — 없다. 이것도 정보다
ABSENCE_ALREADY_MISSING = "already_missing"  # 이미 빠져 있음 — 태운다. 복구다
ABSENCE_NOT_APPLICABLE = "not_applicable"    # 해당 없음 — 그 수가 성립하지 않는 자리
#: 🔴 SEVENTH, AND IT IS NOT `not_applicable` (S-143, 판정 322). That one says the number does
#: not HOLD here. This one says the number holds and THIS SEAT did not pay for it: a
#: declaration edit that touches many sources would need one dry-run per source, inline on a
#: preview request, and 「성능 마진 넉넉하게」 forbids buying it there. The difference is
#: actionable - 「cannot be counted」 sends an operator nowhere, 「not counted HERE」 tells them
#: the count exists on the retroactive route - so folding the two would cost that sentence.
ABSENCE_NOT_COUNTED_HERE = "not_counted_here"  # 셀 수 있으나 이 자리에서 안 셈

#: Spelled once so a client can offer exactly these and no more.
ABSENCE_WORDS = (ABSENCE_NOT_YET, ABSENCE_NOT_EXHAUSTIVE, ABSENCE_CANNOT_POINT,
                 ABSENCE_TRULY_NONE, ABSENCE_ALREADY_MISSING, ABSENCE_NOT_APPLICABLE,
                 ABSENCE_NOT_COUNTED_HERE)


class RetroactiveRefused(Exception):
    """Raised when an operation must not proceed. The message states why."""


# ---------------------------------------------------------------------------
# Parameter declaration
# ---------------------------------------------------------------------------

def _p(name, required=True, kind="string", help="", choices=None, form=True, cli=True):
    """One parameter's declaration.

    🔴 `choices` IS FOR ANY PARAMETER WITH A CLOSED SET, not for pace. Only one uses it
    today, but the field means "the server knows what the legal values are and their names",
    and a pace-shaped field would have to be replaced the first time something else has a
    closed set.

    🔴 IT CARRIES LABELS, NOT JUST VALUES. Values alone would make a screen invent the
    words - and inventing words is the thing every brief in this round forbids, because the
    invented ones then go stale against the declaration nobody told them about.

    A CALLABLE is allowed and is how "add a pace, change no code" actually holds: resolved
    when the inventory is asked for, so a new entry in the declaration is visible without a
    restart. `None` means the parameter is free text, and a client showing free text for it
    is correct rather than lazy.

    `form=False` keeps a parameter off the admin form (`inventory`) and still accepts it
    into the run record - a CLI option the button does not offer (총괄 45410384c ③).
    `cli` is the other side of that: True, or - for a parameter no command line offers - the
    reason, one line (총괄 1c3038997). The `cli` line's promise does not cover it.
    """
    return {"name": name, "required": required, "type": kind, "help": help,
            "choices": choices, "form": form, "cli": cli}


def _resolved_choices(param):
    """`choices` as data, whether it was declared as data or as a way to fetch it.

    A failure to READ the choices is not "there are none": it is "we could not find out",
    and answering `[]` would make a screen show an empty dropdown that looks like a
    configuration with nothing in it. `None` puts it back to free text, which at least
    still works.
    """
    choices = param.get("choices")
    if callable(choices):
        try:
            choices = choices()
        except Exception as exc:                   # noqa: BLE001
            logger.warning("could not resolve choices for '%s': %s", param["name"], told(exc), exc_info=exc)
            return None
    return list(choices) if choices else None


def _pace_choices():
    """The pacing table's own entries, in its own words.

    Read from `server/pacing.json` rather than written here, so adding a pace is one entry
    in that file and no change anywhere else - not in this module and not on the screen.
    """
    import pacing

    return [{"value": name, "label": spec.get("label", name), "when": spec.get("when")}
            for name, spec in pacing.load_paces().items()]


def _pace_param():
    """The `pace` parameter, declared ONCE for every operation that takes one.

    🔴 THE SECOND OPERATION IS WHY THIS IS A FUNCTION. One pace-taking operation could
    spell its own; two spelling it separately is how the help of one ends up carrying a
    fact the other's does not - and the fact below is exactly that kind, because it is
    true of every retroactive run and not of the ledger's alone.
    """
    return _p("pace", required=False, choices=_pace_choices,
              help="how hard to push. Slowing yields between units of work so the "
                   "database stays free for everything else; the paces and their names "
                   "are declared in server/pacing.json. Retroactive runs go ONE AT A "
                   "TIME, so a slower pace also makes whatever is queued behind this "
                   "wait that much longer")


# ---------------------------------------------------------------------------
# Counts. Each one calls the operation's OWN dry-run or a cheap query that lives
# in the operation's own module - never a re-derivation of its logic here.
# ---------------------------------------------------------------------------

def _count_chain_replay(db, params, scan_limit):
    from chain import replay

    # 🔴 [S-270] THE SCOPE AND THE PERMISSION COME FROM ONE VALUE. `row_ids` is what
    # narrows the scan, and it is also what makes the reference side a legal subject - the
    # operator has picked the rows, so re-deriving their targets is what the live chain does
    # when they move. Reading it twice from one dict is what keeps them from disagreeing.
    rule = replay.find_rule(params["rule"], row_scoped=bool(params.get("row_ids")))
    s = replay.replay_rule(db, rule, apply=False, limit=scan_limit,
                                 log=lambda m: logger.debug(m),
                                 business_keys=params.get("business_keys"),
                                 row_ids=params.get("row_ids"))
    truncated = s["rows_scanned"] >= scan_limit
    # 🔴 [소유자 2026-09-23 「ㄷ」 · 미리보기 없이 바로 실행] THE UNIT IS ROWS, BECAUSE ROWS ARE
    #   WHAT THIS RUN HANDS OVER. It stages the rows as ordinary trigger events and the chain
    #   worker writes them - so 「how many cells will change」 is not a question this side can
    #   answer without running the rule twice, once to count and once to mean it.
    # ⚰️ [판정 505] IT WAS `cells_proposed`, produced by a dry-run of the rule right here.
    #   505 asked 「which unit does this screen speak in」 and answered 「follow whether
    #   `cells_proposed` can be non-zero」. It cannot be non-zero any more, by construction:
    #   the counting copy of the write judgment is gone, which is what the owner chose.
    #   Safety moved to where the owner put it - the row appears in the queue, and a
    #   withdrawal takes it back.
    # ⚠️ WHAT THE OPERATOR NO LONGER SEES BEFORE PRESSING, named rather than quietly dropped:
    #   how many CELLS would change · how many a human's value protects · which cells the rule
    #   stopped producing (the R2 candidates). The mechanisms behind the last two are
    #   untouched - `crud` still refuses to write a blank and still keeps the human's layer on
    #   top. What is gone is the advance notice.
    affected = s["rows_scanned"]
    return {
        "affected": affected,
        "absence": (ABSENCE_NOT_EXHAUSTIVE if truncated
                    else ABSENCE_TRULY_NONE if not affected else None),
        # 🔴 ENGLISH, like every string this screen renders (소유자 2026-08-31 · 2026-09-23).
        "affected_label": "rows to re-run",
        "count_kind": COUNT_SAMPLE,
        "scanned": s["rows_scanned"],
        "scan_limit": scan_limit,
        "truncated": truncated,
        "detail": (
            f"{s['rows_scanned']} row(s) of {s['trigger_table']} go to the chain worker as "
            f"ordinary changes, so rule '{s['rule']}' writes through the same path a live "
            f"edit does."
        ),
        "extra": {
            "trigger_table": s["trigger_table"],
            "target_table": s["target_table"],
            "self_triggering": s["self_triggering"],
        },
    }


def _count_withdraw(db, params, scan_limit):
    from chain import replay

    table = params["table"]
    source = params["source"]
    written_by, columns = replay.unwritten_scope(params.get("rule"), table, params.get("columns"))
    c = replay.count_withdrawable(db, table, source, columns=columns, written_by=written_by)
    affected = max(0, c["cells_claimed"] - c["pinned"])
    return {
        "affected": affected,
        # An upper bound is not exhaustive either: fewer cells may actually change.
        "absence": ABSENCE_NOT_EXHAUSTIVE if affected else ABSENCE_TRULY_NONE,
        "affected_label": "cells to withdraw (at most)",
        "count_kind": COUNT_UPPER_BOUND,
        "scanned": None,
        # null, not the requested budget: this count is two aggregates and scans no
        # rows, so echoing a scan budget would imply a sample it never took.
        "scan_limit": None,
        "truncated": False,
        "detail": (
            f"'{source}' claims {c['cells_claimed']} cell(s) in '{table}', and "
            f"{c['pinned']} of them are pinned by a person "
            f"(manual_priority_source) and will not be touched. At most {affected} "
            f"are in scope for withdrawal - the number of cells whose VISIBLE value "
            f"actually changes can be smaller (where the source underneath holds the "
            f"same value, the display stays as it is). At most {c['rows_emptied']} row(s) "
            f"are left with no layer and are deleted as shells."
        ),
        "extra": {
            "cells_claimed": c["cells_claimed"],
            "pinned": c["pinned"],
            "rows_emptied": c["rows_emptied"],
            "why_upper_bound": (
                "The number in scope shrinks in only two ways: (1) the row was "
                "already deleted and only its cell_sources remain, (2) the value "
                "revealed after the withdrawal equals the current one. Both need a "
                "cell-by-cell recomputation, which a cheap query cannot answer."
            ),
        },
    }


def _count_resolve(db, params, scan_limit):
    from chain import replay

    s = replay.recompute_display_values(
        db, params["table"], columns=params.get("columns"), apply=False, limit=scan_limit,
        log=lambda m: logger.debug(m))
    truncated = s["rows_scanned"] >= scan_limit
    affected = s["cells_changed"]
    return {
        "affected": affected,
        "absence": (ABSENCE_NOT_EXHAUSTIVE if truncated
                    else ABSENCE_TRULY_NONE if not affected else None),
        "affected_label": "cells whose shown value moves",
        "count_kind": COUNT_SAMPLE if truncated else COUNT_EXACT,
        "scanned": s["rows_scanned"],
        "scan_limit": scan_limit,
        "truncated": truncated,
        "detail": (
            f"{s['cells_examined']} cell(s) with two or more layers in {s['rows_scanned']} "
            f"row(s) of '{params['table']}'; {affected} would show a different value. "
            f"No layer is created or deleted - only the shown value moves, and each moved "
            f"cell gets a history entry."
        ),
        "extra": {"cells_examined": s["cells_examined"],
                  "pinned_changed": s["pinned_changed"]},
    }


def _count_enrichment_backfill(db, params, scan_limit):
    # `enrichment_backfill`, NOT `scripts/backfill_enrichment`: the CLI is not
    # importable from a runtime process (server/scripts is on nobody's sys.path),
    # and importing it here is what made this route raise ModuleNotFoundError.
    from chain import enrichment
    from database import crud

    rule = enrichment.backfill.load_rule(params["rule"], crud.TABLE_CONFIG)
    s = enrichment.backfill.run_backfill(db, rule, apply=False, scan_limit=scan_limit,
                                         log=lambda m: logger.debug(m))
    truncated = s["rows_scanned"] >= scan_limit
    return {
        "affected": s["new_combinations"],
        "absence": (ABSENCE_NOT_EXHAUSTIVE if truncated
                    else ABSENCE_TRULY_NONE if not s["new_combinations"] else None),
        "affected_label": "derived rows to create",
        "count_kind": COUNT_SAMPLE,
        "scanned": s["rows_scanned"],
        "scan_limit": scan_limit,
        "truncated": truncated,
        "detail": (
            f"Sampled {s['rows_scanned']} source row(s) and will create "
            f"{s['new_combinations']} new derived row(s). The "
            f"{s['already_derived']} derived row(s) that already exist are left "
            f"alone."
            + (f" Of those, {s['partial_key_combinations']} have only PART of a "
               f"decision key - rows that were not created before the 2026-08-05 "
               f"ruling, so this number rises even when the data has not changed."
               if s["partial_key_combinations"] else "")
            + (f" {s['skipped_blank_identity']} key(s) were skipped because every "
               f"column that builds the identity of '{s['derived_table']}' is blank "
               f"on them - such a row would have no address, so it could not be "
               f"updated or withdrawn later. Fill those columns in the source, or "
               f"declare an identity on '{s['derived_table']}' that uses columns "
               f"which are present."
               if s["skipped_blank_identity"] else "")
        ),
        "extra": {
            "already_derived": s["already_derived"],
            "distinct_combinations": s["distinct_combinations"],
            # `skipped_blank`에서 개명 — 세는 대상이 바뀌었다(ANY blank → 판단키 전무).
            # 부분 키 행은 사라진 것이 아니라 `partial_key_combinations`로 옮겨갔다.
            #
            # 🔴 세 수에 `_label`을 붙인 이유: 이 화면은 **서버가 라벨을 붙인 수만**
            # 렌더한다(retroactive_view.buildExtras — "adding one later needs no client
            # change"). 라벨이 없으면 숫자는 존재하되 조작자에게 **보이지 않는다**.
            # 종전 dry-run이 정확히 그 상태였고, 사고는 "0으로 보고된 이유를 보고서가
            # 이름 붙이지 않았다"는 것이었다.
            "skipped_no_key": s["skipped_no_key"],
            "skipped_no_key_label": "no decision key (skipped)",
            "skipped_no_key_group": GROUP_NOT_MADE,
            "skipped_blank_identity": s["skipped_blank_identity"],
            "skipped_blank_identity_label": "identity columns all blank (skipped)",
            "skipped_blank_identity_group": GROUP_NOT_MADE,
            "partial_key_combinations": s["partial_key_combinations"],
            "partial_key_combinations_label": "new rows with only part of a decision key",
            # 🔴 이 수는 `new_combinations` 의 «부분집합»이다 — 안 만든 수가 아니다.
            # 낱말이 아니라 «자리»로 갈라야 운영자가 셋을 같은 종류로 안 읽는다.
            "partial_key_combinations_group": GROUP_PART_OF_MADE,
            "source_table": s["source_table"],
            "derived_table": s["derived_table"],
            "sample_new_keys": s["sample_new_keys"][:5],
        },
    }


def _count_enrichment_confirm(db, params, scan_limit):
    from chain.enrichment import analysis
    from chain import enrichment

    rule = _enrichment_rule(params["rule"])
    knob_on = enrichment.candidates.rule_auto_confirm_enabled(rule)
    # ignore_knob=True so a rule whose knob is OFF can still be measured - "what
    # happens if I turn it on" has to be answerable before turning it on. The knob
    # state travels separately so the client can disable the button rather than
    # letting the operator discover the refusal by pressing it.
    s = analysis.run_auto_confirm_sweep(
        db, rule, apply=False, limit=scan_limit, ignore_knob=True,
        log=lambda m: logger.debug(m))
    truncated = s.get("queue_size", 0) >= scan_limit
    detail = (f"Sampled {s.get('queue_size', 0)} queued item(s): "
              f"{s.get('confirmed', 0)} can be confirmed without a person "
              f"({s.get('written_cells', 0)} cell(s)).")
    if s.get("probe_batch_fallbacks"):
        detail += (f" Batch -> key by key: {sum(s['probe_batch_fallbacks'].values())} key(s) asked one at a time "
                   f"after a page's one probe statement failed.")
    if not knob_on:
        detail += (" ⚠️ This rule's auto_confirm knob is off, so the run "
                   "button is refused - the number answers 'what happens if I turn "
                   "it on'.")
    return {
        "affected": s.get("confirmed", 0),
        "absence": (ABSENCE_NOT_EXHAUSTIVE if truncated
                    else ABSENCE_TRULY_NONE if not s.get("confirmed") else None),
        "affected_label": "items confirmable without a person",
        "count_kind": COUNT_SAMPLE,
        "scanned": s.get("queue_size", 0),
        "scan_limit": scan_limit,
        "truncated": truncated,
        "detail": detail,
        "blocked_reason": None if knob_on else "auto_confirm_off",
        "extra": {
            "queue_size": s.get("queue_size", 0),
            "keys_examined": s.get("keys_examined", 0),
            "written_cells": s.get("written_cells", 0),
            "refused": s.get("refused", {}),
            "auto_confirm": knob_on,
            "samples": (s.get("samples") or [])[:5],
        },
    }


def _count_ledger_backfill(db, params, scan_limit):
    """How many rows this source has NOT translated, counted by the ROW INDEX.

    🔴 THE OLD ANSWER WAS A PAGE, AND A PAGE CANNOT SAY A TOTAL. It read one page past
    the cursor, so a full page could only report "at least N" and the route had to carry
    `count_kind` to say which kind of number it was handing over. There is no cursor now
    (판정 163): the index names the rows the ledger holds facts from, so the remainder is
    the relation's count minus the index's count and it is EXACT, every time.

    ⚠️ A SOURCE THAT CANNOT BE COUNTED SAYS SO - one the loader refused has no plan to count
    with. That is `not_applicable` -- the number does not stand up in that place -- and NOT a
    zero. (It used to be a view without `row_id`; views are refused at load, 총괄 f3bc02f6e.)
    """
    from ledger import backfill
    from ledger.setup import load_setup

    source = params["source"]
    engine, setup, world = db.get_bind(), _ledger_setup(params), _ledger_world(params)
    census = backfill.rows_not_yet_translated(engine, setup, source, world=world)

    if census.get("refused"):
        return {
            "affected": 0,
            "affected_label": "rows not yet translated",
            "absence": ABSENCE_NOT_APPLICABLE,
            "count_kind": COUNT_EXACT,
            "scanned": 0,
            "scan_limit": None,
            "truncated": False,
            "detail": (f"'{source}' cannot be counted - how many are left is UNKNOWN, "
                       f"not zero. {census['remedy']}"),
            "extra": {"source": source, "refused": census["refused"]},
        }

    # The rows this run translates are the ones the index does not name - counted apart from
    # the rows the table lost, which the table less the index nets them against (총괄 6091a7ae3
    # ②, the catch-up's own count).
    behind = backfill.rows_to_catch_up(engine, setup, source, world=world, census=census)
    rows, gone = behind["rows_new"], behind["rows_gone"]
    total, indexed = census["relation_rows"], census["indexed_rows"]
    if rows is None:
        return {
            "affected": 0, "affected_label": "rows not yet translated",
            "absence": ABSENCE_NOT_APPLICABLE, "count_kind": COUNT_EXACT, "scanned": total,
            "scan_limit": None, "truncated": False, "detail": census["not_comparable"],
            "extra": {"source": source, "relation_rows": total, "indexed_rows": indexed},
        }
    if not rows:
        detail = (f"'{source}' has NO rows left to translate - {total} row(s) in "
                  f"the table, {indexed} in the index. Running it now does nothing "
                  f"and ends.")
    else:
        detail = (f"'{source}' has {rows} row(s) not yet translated - {total} "
                  f"row(s) in the table, {indexed} in the index. This number is the "
                  f"WHOLE set, not a sample. The run can be stopped while it goes.")
    if census.get("excluded_rows"):
        detail += " %d row(s) the declaration's exclude_when takes out are not counted." % census["excluded_rows"]
    if census.get("said_nothing_rows"):
        detail += (" %d row(s) that say no sentence (no when holds, or every target is blank) are "
                   "not counted." % census["said_nothing_rows"])
    if census.get("excluded_not_subtracted"):
        detail += (" rows exclude_when takes out or that say no sentence not subtracted (%s)."
                   % census["excluded_not_subtracted"])
    if gone:
        detail += (f" ⚠ The index names {gone} row(s) that are NOT in the table - deletions "
                   f"that were never swept.")
    return {
        "affected": rows,
        "affected_label": "rows not yet translated",
        "absence": ABSENCE_TRULY_NONE if not rows else None,
        # \U0001f534 EXACT, ALWAYS, AND THAT IS THE CHANGE. The old answer was `sample`
        # whenever a page came back full, because "at least N" has no word in the shared
        # vocabulary. Subtracting two counts has no page to come back full, so the
        # vocabulary's awkward case simply stops arising -- the fix was not a better word.
        "count_kind": COUNT_EXACT,
        "scanned": total,
        "scan_limit": None,
        "truncated": False,
        "detail": detail,
        "extra": {"source": source, "relation_rows": total, "indexed_rows": indexed,
                  "not_yet_translated": rows, "gone_rows": gone},
    }


def _given(params, *names):
    """The CLI-only options a run carries, only where given - each operation's own default
    stands for the rest. Spelling the defaults here too would make a second author."""
    return {name: params[name] for name in names if name in params}


def _run_ledger_backfill(db, params, log, control=None):
    from ledger import backfill

    s = backfill.run(db.get_bind(), source=params["source"],
                     checkpoint=_checkpoint(control), pace=params.get("pace"),
                     world=_ledger_world(params), **_given(params, "fetch_rows", "max_batches"))
    _final_progress(control, s.get("rows_read"), s)
    return {"rows_read": s.get("rows_read"), "batches": s.get("batches"),
            "inserted": s.get("inserted"), "deduped": s.get("deduped"),
            "molecules": s.get("molecules"), "stopped": bool(s.get("stopped")),
            "cursor_after": s.get("cursor_after")}


def _count_ledger_catch_up(db, params, scan_limit):
    """What the world missed, per source it reads - the three the run takes, each counted by the
    seat that takes it (총괄 71880678a)."""
    from ledger import backfill

    engine, setup, world = db.get_bind(), _ledger_setup(params), _ledger_world(params)
    sources, total, uncounted = {}, 0, []
    for source in sorted(name for name, plan in setup.snapshot.source_plans.items() if plan.runs):
        behind = backfill.rows_to_catch_up(engine, setup, source, world=world)
        if behind["rows_new"] is None:
            uncounted.append(source)
        sources[source] = {box: behind[box] for box in ("rows_new", "rows_drifted", "rows_gone")}
        total += (behind["rows_new"] or 0) + behind["rows_drifted"] + behind["rows_gone"]
    detail = (f"world {world}: {total} row(s) to catch up - made, edited or lost while it did "
              f"not follow live, over {len(sources)} source(s).")
    if uncounted:
        detail += f" New rows of {', '.join(uncounted)} cannot be counted here."
    return {
        "affected": total,
        "affected_label": "rows to catch up",
        "absence": (ABSENCE_NOT_EXHAUSTIVE if uncounted
                    else ABSENCE_TRULY_NONE if not total else None),
        "count_kind": COUNT_EXACT,
        "scanned": None,
        "scan_limit": None,
        "truncated": False,
        "detail": detail,
        "extra": {"world": world, "sources": sources},
    }


def _run_ledger_catch_up(db, params, log, control=None):
    from ledger import backfill

    s = backfill.catch_up(db.get_bind(), _ledger_setup(params), world=_ledger_world(params),
                          checkpoint=_checkpoint(control), pace=params.get("pace"))
    _final_progress(control, s.get("rows"), s)
    return s


def _rescope_absence(withdraw, remake, rows):
    """Which of the six a scoped redo's numbers mean. Chosen from the PAIR, not from one.

    "Withdrew nothing" alone cannot tell `truly_none` from `already_missing`: the
    difference is whether there is anything to put BACK, and that is the other half of the
    pair. This is not cosmetic - `already_missing` is exactly the state a run that died
    between its two commits leaves behind, and reading it as "nothing to do" is how
    fourteen atoms stayed missing overnight on 2026-08-31.

    Separated from the count so it can be tested on all four corners without a database;
    the live path only ever produces some of them.
    """
    if withdraw:
        return None                          # 거둔 것이 있다 — 평범한 수다
    if remake:
        return ABSENCE_ALREADY_MISSING       # 거둘 것 0 · 다시 만들 것 N -> 복구다
    if rows:
        return ABSENCE_CANNOT_POINT          # 행은 있는데 짚을 것이 없다 -> 선언 문제
    return ABSENCE_TRULY_NONE                # 범위에 행 자체가 없다


def _count_ledger_rescope(db, params, scan_limit):
    """The operation's OWN dry-run, not a re-derivation of it.

    `count_kind` is EXACT and `scan_limit` is null because the SCOPE is the budget: this
    compiles exactly the rows the operator named and nothing besides. Echoing a scan
    budget would describe a walk this never takes. A whole source's stale atoms are the one
    read that stops at `_count_until` - then «at least» (총괄 2ea5ee2a7 ②).
    """
    from ledger import backfill

    source = params["source"]
    if params.get("whole_source"):
        # 총괄 8d10633ae ㉡ · 3a109bfd9 ③: the rescope's own whole-source preview - the table's
        # rows, the rows it lost and their atoms. Not translated: that would be the whole job.
        said = backfill.rescope(db.get_bind(), _ledger_setup(params), source, None, None,
                                apply=False, whole_source=True, world=_ledger_world(params),
                                until=_count_until())
        total, gone, atoms = said["relation_rows"], said["gone_rows"], said["gone_atoms"]
        stale, cut = said["stale_atoms"], bool(said.get("stale_cut"))
        stale_said = ("at least %d atom(s) (%d atom(s) of '%s' read%s)" % (stale, said["stale_read"], source,
                                                                         _cut_said())
                      if cut else "%d atom(s)" % stale)
        where = "; ".join("%s: %s" % (table, ", ".join("%s %d" % pair for pair in sorted(by.items())))
                          for table, by in sorted(said["stale_tables"].items())) or "none"
        extra = {"source": source, "whole_source": True, "relation_rows": total, "gone_rows": gone,
                 "gone_atoms": atoms, "stale_atoms": stale, "stale_refs": said["stale_refs"],
                 "stale_tables": said["stale_tables"], "stale_read": said["stale_read"], "stale_cut": cut}
        if total is None:
            # 총괄 e027f669d: a name today's declaration does not have - its atoms, all of them
            return {
                "affected": stale, "affected_label": "atoms withdrawn (at least)" if cut else "atoms withdrawn",
                "absence": ABSENCE_TRULY_NONE if not stale and not cut else None,
                "count_kind": COUNT_SAMPLE if cut else COUNT_EXACT,
                "scanned": said["stale_read"] if cut else stale, "scan_limit": None, "truncated": cut,
                "detail": (f"'{source}' is not in today's declaration: withdraws every atom it "
                           f"wrote - {stale_said} by table and predicate: {where}. Nothing is "
                           f"re-translated. Cannot be undone."),
                "extra": extra}
        return {
            "affected": total, "affected_label": "rows re-translated",
            "absence": None, "count_kind": COUNT_EXACT, "scanned": total,
            "scan_limit": None, "truncated": False,
            "detail": (f"Re-translates every row of '{source}' ({total} row(s) in the "
                       f"table) from today's declaration: page by page, each page's old "
                       f"atoms withdrawn and new ones written in one commit. Withdraws "
                       f"{atoms} atom(s) of {gone} row(s) the table no longer has. The "
                       f"re-translation is not previewed - that would be the whole job. "
                       f"Withdraws {stale_said} it wrote from tables today's declaration "
                       f"does not read, by table and predicate: {where}."),
            "extra": extra}
    column = params["scope_column"]
    values = params.get("scope_values") or []
    preview = backfill.preview_rescope(
        db.get_bind(), _ledger_setup(params), source, column, values,
        world=_ledger_world(params))
    preview.pop("refs", None)
    rows = preview["rows_in_scope"]
    withdraw, remake = preview["withdraw"], preview["remake"]
    detail = (
        f"Withdraws {withdraw} atom(s) that '{source}' wrote from {rows} row(s) "
        f"in the {column} scope ({len(values)} value(s)), and remakes {remake} from "
        f"today's declaration. If the two numbers differ, that difference is what "
        f"this correction changes. This source's read position (the cursor) does "
        f"not move.")
    if remake and not withdraw:
        # Seen for real on 2026-08-31: a run that died between the two commits left the
        # withdrawal done and the remake absent. The operator needs to be told that this
        # is a REPAIR rather than a no-op, because the headline number is 0.
        detail += (" ⚠️ There is nothing to withdraw but something to remake - "
                   "this scope's atoms are NOT in the ledger right now, and running "
                   "it fills them in.")
    if rows and not remake:
        # The refs come from the CURRENT translation, so there is nothing to aim with.
        detail += (" ⚠️ The scope holds rows but remakes 0 atoms - there is no "
                   "way to aim at the stale atoms, so they cannot be withdrawn "
                   "either. Look at the declaration first.")
    # 🔴 A SOURCE-LEVEL FACT, KEPT OUT OF THE SCOPE NUMBERS. A row that was deleted cannot
    # be named by a scope - the scope is a predicate over the relation and the relation no
    # longer carries the row - so this cannot be "orphans in this scope" and is not added
    # to anything above. It rides in `extra` with its OWN count_kind, because the scope
    # count is exact while this one is a sample on a large source, and one `count_kind`
    # cannot honestly describe both.
    orphans = backfill.count_orphan_atoms(db.get_bind(), source, world=_ledger_world(params))
    if orphans["rows_gone"]:
        detail += (f" \u26a0\ufe0f This source holds {orphans['atoms']} atom(s) "
                   f"whose row is GONE - SEPARATE from this scope's work.")
    elif orphans["truncated"]:
        # A sampled zero is not an exhaustive zero, and saying "0" without saying which
        # would be read as "none exist".
        detail += (f" Atoms whose row is gone are 0 IN THE SAMPLE of "
                   f"{orphans['refs_scanned']} (out of {orphans['refs_total']} "
                   f"in all).")
    # 🔴 THIS ONE IS CHOSEN FROM A PAIR, NOT FROM ONE NUMBER, and the entry says so in
    # advance. "Withdrew nothing" alone cannot tell `truly_none` from `already_missing` -
    # the difference is whether there is anything to put BACK, which is the other half of
    # the pair. Getting it wrong is not cosmetic: `already_missing` is the state a run that
    # died between its two commits leaves behind, and reading it as "nothing to do" is how
    # fourteen atoms stayed missing overnight on 2026-08-31.
    return {
        "affected": withdraw,
        "affected_label": "atoms to withdraw",
        "absence": _rescope_absence(withdraw, remake, rows),
        "count_kind": COUNT_EXACT,
        "scanned": rows,
        "scan_limit": None,
        "truncated": False,
        "detail": detail,
        "extra": dict(preview, source_orphans=orphans),
    }


def _final_progress(control, rows, stats):
    """Write the finished run's own count, once, when the work is over - and keep the
    operation's unreduced answer on the control for a CLI that prints it (총괄 45410384c
    ④). The stored result stays the reduced dict the adapter returns.

    🔴 A RUN THAT FINISHED IN ONE BATCH HAD NO BATCH BOUNDARY TO REPORT AT, so its progress
    column stayed 0 while its result said 80 rows - and "never started" and "completely
    done" became the same number on the screen. Measured 2026-08-31 on a real
    `ledger_backfill` run.

    The value comes from the SERVER, and from the adapter that already knows which of its
    operation's stats is the row count. Letting a screen parse `result` instead would put
    that per-operation knowledge in the client, where every new operation would need it
    again.
    """
    if control is None:
        return
    control.stats = stats
    if rows is not None:
        control.progress(rows)


def _checkpoint(control):
    """One hook from a run's control: report where we are, and ask whether to go on.

    ONE call rather than two because both belong to the same instant. A batch boundary is
    the only place a stop is safe - the previous batch is committed, the next has not
    begun - and it is also the only place "how far" is a true number rather than a
    half-written one. Splitting them into two callbacks would let an operation report
    progress somewhere a stop would not be safe.

    `hook.step` is the other seat a page passes, inside it: `RunControl.step` - the time and a
    line, never a count or a stop (총괄 e71f7d6f1).
    """
    if control is None:
        return None
    seen = [_reload_mark()]

    def hook(processed=None, total=None):
        control.progress(processed, total)
        seen[0] = _reload_between_pages(seen[0])
        return control.stop_requested()

    hook.step = control.step
    return hook


def _reload_mark():
    """Where a run's reloads start - the newest SYSTEM_RELOAD row now; None when it cannot be read (the first page
    boundary then reads it)."""
    from runtime import system_reload

    try:
        return system_reload.reload_mark()
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[Retroactive] the reload mark could not be read - the first page boundary reads it: %s",
                       told(exc))
        return None


def _reload_between_pages(seen):
    """At a page boundary, the declarations this process saw change and the Reload button's rows - the slot's own
    boundary reload (`ingestion_worker.reload_at_boundary`, 총괄 1ff4dcc6c ⑤). The run's own `rule` dict, read at its
    start, stays as it was. A reload that does not read is said and tried at the next page - the run goes on.
    -> the last row seen."""
    from chain import ingestion_worker
    from runtime import system_reload

    if seen is None:
        return _reload_mark()
    try:
        applied, seen = ingestion_worker.reload_at_boundary(system_reload.RETROACTIVE, seen)
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[Retroactive] the declarations were not read again at this page - the next page tries: %s",
                       told(exc))
        return seen
    if applied:
        logger.info("[Retroactive] declarations read again at a page boundary")
    return seen


def _rescope(db, params, control, key_range=None):
    """The run's re-translate - the whole of it, or one slice's `key_range` (`run_slice`)."""
    from ledger import backfill

    return backfill.rescope(
        db.get_bind(), _ledger_setup(params), params["source"], params.get("scope_column"),
        params.get("scope_values") or [], apply=True,
        page_rows=backfill.RESCOPE_PAGE_ROWS, checkpoint=_checkpoint(control),
        whole_source=bool(params.get("whole_source")), world=_ledger_world(params), key_range=key_range)


def _run_ledger_rescope(db, params, log, control=None):
    s = _rescope_in_slices(db, params, control) if params.get("whole_source") else None
    if s is None:
        s = _rescope(db, params, control)
    # 🔴 a refused molecule was withdrawn and not remade - said beside «written», never left to read as a
    #    success (총괄 10-12: «rows 4, withdrawn 4, written 4 of 4» while 2 rows lost their atoms). A key value
    #    refused over the row index's limit is counted by key value and keeps its old atoms (gate's reason says)
    from ledger.gate import REFUSE_ROW_INDEX_KEY_TOO_LONG

    refused = s.get("refused") or {}
    why = ", ".join("%s %d%s" % (reason, n, " key values, old atoms kept" if reason == REFUSE_ROW_INDEX_KEY_TOO_LONG
                                 else "") for reason, n in sorted(refused.items()))
    log(f"[rescope] {s['source']} {s['scope_column']}: rows {s['rows_in_scope']}, "
        f"withdrawn {s['withdrawn']}, written {s['inserted']} of {s['attempted']}, "
        f"refused {sum(refused.values())}" + (f" ({why})" if why else "")
        + (f", from tables the declaration does not read {s['stale_withdrawn']}"
           if "stale_withdrawn" in s else "")
        + (f", rows without a page key (not read) {s['rows_without_page_key']}"
           if "rows_without_page_key" in s else ""))
    _final_progress(control, s.get("rows_in_scope"), s)
    return {"withdrawn": s["withdrawn"], "attempted": s["attempted"],
            "inserted": s["inserted"], "deduped": s["deduped"],
            "rows_in_scope": s["rows_in_scope"], "applied": s["applied"],
            "refused": sum(refused.values()), **({"refused_reasons": why} if why else {}),
            **{key: s[key] for key in ("stale_withdrawn", "stale_forgotten", "stale_pages", "rows_without_page_key")
               if key in s}}


def _rescope_in_slices(db, params, control):
    """A whole source's re-translate in `translate_slices` processes at once (총괄 fd550df13 ㄱ · 0cd396d3d) - or None:
    one slice (`backfill.slice_bounds` says when), a source the declaration no longer has, or no run row for a slice to
    read its run from - and this process runs it. The pages are the slices'; what runs once - the lines every page
    pays, the rows the relation lost, the stale atoms - is this process's, before and after them."""
    from ledger import backfill, schema

    if control is None or control.run_id in (None, "?"):
        return None
    engine, setup, world = db.get_bind(), _ledger_setup(params), _ledger_world(params)
    plan, _scoped = backfill.rescope_scope(setup, params["source"], None, None, whole_source=True)
    if plan is None:
        return None
    wanted, cores = translate_slices()
    started = time.monotonic()
    if wanted > 1:
        # the cut counts the relation and reads it at N-1 offsets - minutes on a large one, said before
        control.say("cutting %s into %d slices - counting its rows" % (plan.relation, wanted))
    bounds, total = backfill.slice_bounds(engine, plan, wanted)
    control.say("%d slice%s (cores %d)%s" % (len(bounds), "s" if len(bounds) > 1 else "", cores,
                                             " - cut in %.1f s" % (time.monotonic() - started) if wanted > 1 else ""))
    if len(bounds) == 1:
        return None
    # the slices find the world made - none of them races another to make it
    schema.ensure_world(engine, schema.world_names(world))
    backfill.say_what_every_page_pays(engine, plan, world, True)
    backfill.analyze_stale_partitions(engine, world)
    control.own_beat = False
    try:
        s = _summed(_run_slices(control, bounds, total))
    finally:
        control.own_beat = True
    if s.get("rows_in_scope"):
        s.pop("scope_empty", None)                 # empty only when every slice was
    if s.get("stopped"):
        control.stop_requested()                   # the × the slices stopped on - the run ends cancelled
    else:
        s.update(backfill.whole_source_tail(engine, setup, params["source"], plan,
                                            checkpoint=_checkpoint(control), world=world))
    return s


def _run_slices(control, bounds, total):
    """Each of `bounds` in a slice process of its own (`_spawn_slice`), all at once; -> their answers. The run row has
    one writer: this process sums the slices' counts onto it, its page line saying their state. A × reaches each slice
    through the row. A slice that ends without its answer lets the others go - their stdin closes and they stop at a
    page boundary - and the run fails naming what each left."""
    import queue

    from utils.logger import relay_lines

    count, said = len(bounds), queue.Queue()
    procs, rows, answers, ended = {}, {}, {}, {}
    moved = time.monotonic()
    try:
        for index, key_range in enumerate(bounds, 1):
            proc = procs[index] = _spawn_slice(control.run_id, index, count)
            rows[index] = 0
            proc.stdin.write(json.dumps(key_range) + "\n")
            proc.stdin.flush()
            threading.Thread(target=_slice_answers, args=(index, proc, said), daemon=True,
                             name="slice-%d-answers" % index).start()
            threading.Thread(target=relay_lines, args=(
                proc.stderr, "[slice %d/%d pid %d]" % (index, count, proc.pid), "Retroactive"),
                daemon=True, name="slice-%d-log" % index).start()
        control.say("%d slice processes started - waiting for their first pages" % count)
        while len(ended) < count:
            try:
                index, answer = said.get(timeout=LOOK_SECONDS)
            except queue.Empty:
                continue
            if answer is None:
                ended[index] = procs[index].wait()
                state = _slice_state(index, answers, ended)
                control.say("slice %d/%d %s: %d rows%s" % (index, count, state, rows[index], (
                    " - exit code %s without its answer; letting the others go" % ended[index]
                    if state == "failed" else "")))
                if state == "failed":
                    for other, proc in procs.items():
                        if other not in ended:
                            _let_go(proc)
            elif "result" in answer:
                answers[index] = answer["result"]
                rows[index] = answers[index].get("rows_in_scope", rows[index])
            else:
                rows[index] = answer.get("rows", rows[index])
            # the run's count and page line every BEAT_SECONDS at most and when a slice ends - each slice's pages are
            # its own lines; a line a slice page was N lines a page and a run-row write each
            if answer is None or time.monotonic() - moved >= BEAT_SECONDS:
                states = [_slice_state(index, answers, ended) for index in procs]
                control.progress(sum(rows.values()), total, note="slices %d: %s" % (count, " · ".join(
                    "%d %s" % (states.count(state), state) for state in SLICE_STATES if state in states)))
                moved = time.monotonic()
    finally:
        for proc in procs.values():                # a spawn or this loop that raised leaves no slice writing
            _let_go(proc)
    failed = [index for index in procs if index not in answers]
    if failed:
        raise RuntimeError(
            "slice %s ended without its answer - its lines in retroactive.log say why; the slices' pages written "
            "stay (%s), the rest of the source is not re-translated: run it again" % (
                ", ".join("%d/%d" % (index, count) for index in failed),
                " · ".join("%d/%d %d rows %s" % (index, count, rows[index], _slice_state(index, answers, ended))
                           for index in procs)))
    return [answers[index] for index in procs]


#: A slice's state in its run's page line, in this order.
SLICE_STATES = ("working", "done", "stopped", "failed")


def _slice_state(index, answers, ended):
    if index in answers:
        return "stopped" if answers[index].get("stopped") else "done"
    return "failed" if index in ended else "working"


def _summed(answers):
    """The slices' answers as one run's: numbers and `refused` reasons added, a flag set when any slice's is, anything
    else the first slice's."""
    out = {}
    for answer in answers:
        for key, value in answer.items():
            if isinstance(value, bool):
                out[key] = out.get(key, False) or value
            elif isinstance(value, (int, float)):
                out[key] = out.get(key, 0) + value
            elif isinstance(value, dict):
                into = out.setdefault(key, {})
                for reason, n in value.items():
                    into[reason] = into.get(reason, 0) + n
            else:
                out.setdefault(key, value)
    return out


def _spawn_slice(run_id, index, count):
    """A slice process (`admin.retroactive_run --slice`) - its pipes utf-8 both ways."""
    import subprocess
    import sys

    import paths

    return subprocess.Popen(
        [sys.executable, "-m", "admin.retroactive_run", "--slice", "%d/%d" % (index, count), run_id],
        cwd=paths.SERVER_DIR, env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _slice_answers(index, proc, said):
    """A slice's answers (`run_slice`), a JSON line each, onto `said` - then None: its stdout closed, it ended."""
    for raw in proc.stdout:
        try:
            said.put((index, json.loads(raw)))
        except ValueError:
            continue
    said.put((index, None))


def _let_go(proc):
    try:
        proc.stdin.close()
    except (OSError, ValueError):
        pass


def run_slice(run_id, asks, answer, log):
    """One slice of a run's whole-source re-translate, in a process of its own (`_rescope_in_slices`): its key range the
    first line of `asks`, its count and its answer through `answer` - never onto the run row. The rest of `asks` is the
    run's process holding it: when it closes - that process gone, or a sibling dead - this stops at its next page
    boundary. A × reaches it through the run row, as every run's does."""
    from database import crud, models
    from database.context import channel, retroactive_run
    from database.database import SessionLocal

    key_range = tuple(json.loads(asks.readline()))
    session = SessionLocal()
    try:
        row = (session.query(models.RetroactiveRun)
               .filter(models.RetroactiveRun.run_id == run_id).first())
        if row is None:
            raise RetroactiveRefused("run_id=%s is gone - no slice of it to run" % run_id)
        op, params = row.op, json.loads(row.params) if row.params else {}
    finally:
        session.close()
    models.init_dynamic_models(crud.TABLE_CONFIG)
    params = validate(op, params)
    control = RunControl(run_id, op=op, log=log, report=lambda processed: answer({"rows": processed}))

    def held():
        for _line in asks:
            pass
        if not control.stopped:
            control.say("the run's process let this slice go - it stops at its page boundary")
            control.stopped = True

    threading.Thread(target=held, name="slice-held", daemon=True).start()
    db = SessionLocal()
    try:
        with channel(ec.CHANNEL_RETROACTIVE), retroactive_run(run_id), _beating(control, db.get_bind()):
            s = _rescope(db, params, control, key_range=key_range)
    finally:
        db.close()
    answer({"result": s})
    return s


def _run_chain_replay(db, params, log, control=None):
    from chain import replay

    # 🔴 [S-270] THE SCOPE AND THE PERMISSION COME FROM ONE VALUE. `row_ids` is what
    # narrows the scan, and it is also what makes the reference side a legal subject - the
    # operator has picked the rows, so re-deriving their targets is what the live chain does
    # when they move. Reading it twice from one dict is what keeps them from disagreeing.
    rule = replay.find_rule(params["rule"], row_scoped=bool(params.get("row_ids")))
    # [146b208cb] The trigger events carry the ask, and what they wake writes with it.
    from database.context import cascade
    with cascade(params.get("cascade") is True):
        s = replay.replay_rule(db, rule, apply=True, log=log,
                               checkpoint=_checkpoint(control),
                               business_keys=params.get("business_keys"),
                               row_ids=params.get("row_ids"),
                               pace=params.get("pace"),
                               continued_from=params.get("continued_from"),
                               **_given(params, "limit", "chunk_size"))
    _final_progress(control, s.get("rows_scanned"), s)
    # 🔴 THIS RUN NO LONGER WRITES, SO IT MUST NOT REPORT WRITES. It hands the rows to the
    #    worker as ordinary trigger events and the worker writes them, later, in its own
    #    transaction. `cells_written` / `rows_created` / `rows_updated` would all be 0 here
    #    and a 0 reads as 「아무것도 안 나왔다」 - the one thing this screen exists to tell
    #    apart from 「안 돌았다」. What is true at this instant is how many rows went over and
    #    in how many events, so that is what it says.
    # ⚠️ THE WORKER'S SIDE OF THE NUMBER IS READ WHERE THE WORKER REPORTS IT - the queue and
    #    the chain log, under the same `chain_<tx>` label every other change uses.
    return {"rows_staged": s["rows_staged"], "events_staged": s["events_staged"],
            "rows_scanned": s["rows_scanned"], "pages_failed": s.get("pages_failed", 0),
            "pages": s.get("pages"), "first_page": s.get("first_page")}


def _scope(params):
    """The three narrowing criteria a set-aside takes - every one given narrows."""
    return {"tables": params.get("tables") or (), "rules": params.get("rules") or (),
            "transactions": params.get("transactions") or ()}


def _judge_set_aside(params):
    from chain import replay

    scope = _scope(params)
    if not any(scope.values()):
        raise RetroactiveRefused(
            "name at least one table, rule or transaction - setting aside the whole queue "
            "is not something a form should do in one click")
    known = {r.get("name") for r in replay.load_rules()}
    unknown = sorted(set(scope["rules"]) - known)
    if unknown:
        raise RetroactiveRefused(f"no chain rule is declared under {unknown}")


def _count_set_aside(db, params, scan_limit):
    from chain import set_aside

    found = set_aside.set_aside(db, apply=False, until=_count_until(), **_scope(params))
    cut = bool(found.get("cut"))
    return {"affected": found["events"],
            "absence": ABSENCE_TRULY_NONE if not found["events"] else ABSENCE_NOT_APPLICABLE,
            "affected_label": "waiting events to set aside (%s%d row(s))" % (
                "at least - " if cut else "", found["rows"]),
            "count_kind": COUNT_SAMPLE if cut else COUNT_EXACT, "scanned": None, "scan_limit": None,
            "truncated": cut,
            "detail": "by table: %s%s" % (found["by_table"] or "none", _cut_said() if cut else "")}


def _run_set_aside(db, params, log, control=None):
    from chain import set_aside

    s = set_aside.set_aside(db, apply=True, reason=params["reason"],
                            checkpoint=_checkpoint(control), **_scope(params))
    _final_progress(control, s["events"], s)
    return {"events_set_aside": s["events"], "rows": s["rows"]}


def _count_rerun_set_aside(db, params, scan_limit):
    from chain import set_aside

    rows = set_aside.rows_set_aside(db, **_scope(params))
    total = sum(len(ids) for ids in rows.values())
    return {"affected": total,
            "absence": ABSENCE_TRULY_NONE if not total else ABSENCE_NOT_APPLICABLE,
            "affected_label": "rows named by set-aside events",
            "count_kind": COUNT_EXACT, "scanned": None, "scan_limit": None,
            "truncated": False,
            "detail": "by table: %s" % ({t: len(ids) for t, ids in rows.items()} or "none")}


def _run_rerun_set_aside(db, params, log, control=None):
    """Replay the rows the set-aside events named - every enabled rule on each table (or the
    rules named), in the declaration's order, ONCE and without `cascade`: what those rules
    write wakes no rule downstream. 총괄 2dbbfd1e5 had it cascade; the owner reversed that
    (09-27 「큰 소급 치워둔거니 한번만」) - only the grid's click replay cascades.
    A deleted row has nothing to replay: its deletion goes back as the deletion it was - staged with its old values
    through the door a deletion is staged by, one rule each - so a rule without lineage (a join's or a decide's
    recount) takes it as it takes a live one (총괄 g26). One its event kept no old values of is said, not staged.
    An edited row whose events kept old values goes back the same way, as the edit it was - its old key is what
    such a rule withdraws from (총괄 g31)."""
    import chain_bindings
    from chain import replay, rule_shape, set_aside
    from database.context import channel
    from database.database import stage_collapsed_event

    rows = set_aside.rows_set_aside(db, **_scope(params))
    changed = set_aside.changes_set_aside(db, **_scope(params))
    wanted = set(_scope(params)["rules"])
    staged, again = 0, {"EDIT": 0, "DELETE": 0}
    for table in sorted(set(rows) | set(changed)):
        rules = replay.order_rules([
            r for r in replay.load_rules()
            if r.get("trigger_table") == table and not rule_shape.is_switched_off(r)
            and (not wanted or r.get("name") in wanted)])
        moved = changed.get(table, {})
        gone = {row_id: was for row_id, (kind, was) in moved.items() if kind == "DELETE"}
        edited = {row_id: was for row_id, (kind, was) in moved.items() if kind != "DELETE" and was}
        ids = [row_id for row_id in rows.get(table, ()) if row_id not in gone and row_id not in edited]
        lost = [row_id for row_id, was in gone.items() if not was]
        if lost:
            log("[rerun_set_aside] %s: old values not kept - this deletion cannot be replayed; rows: %s"
                % (table, ", ".join(lost)))
        kept = {row_id: was for row_id, was in gone.items() if was}
        for rule in rules:
            if ids:
                one = _run_chain_replay(db, {"rule": rule.get("name"), "row_ids": ids},
                                        log, control)
                staged += one["rows_staged"]
            for kind, back in (("EDIT", edited), ("DELETE", kept if chain_bindings.takes_deletions(rule) else {})):
                if back:
                    with channel(None):
                        stage_collapsed_event(db, kind, table, list(back), only_rule=rule.get("name"), replay=True,
                                              old=list(back.values()))
                    db.commit()
                    again[kind] += len(back)
    return {"rows_staged": staged, "edits_staged": again["EDIT"], "deletions_staged": again["DELETE"],
            "tables": len(set(rows) | set(changed))}


#: The run a chain group queued for a `run_in: operation` rule (총괄 be0abe305 ②). ⚰️ No group queues
#: it now - `run_in` is retired (총괄 72f419bd1); it stays registered so its old runs still list.
RULE_ROWS_OP = "rule_rows"


def _queued_rule(name):
    from chain import replay

    rule = next((r for r in replay.load_rules() if r.get("name") == name), None)
    if rule is None:
        raise RetroactiveRefused("no enabled chain rule is declared under %r" % (name,))
    return rule


def _judge_rule_rows(params):
    _queued_rule(params["rule"])


def _count_rule_rows(db, params, scan_limit):
    total = len(params.get("rows") or ()) or len(params["events"])
    return {"affected": total, "absence": ABSENCE_NOT_APPLICABLE,
            "affected_label": "queued trigger rows", "count_kind": COUNT_EXACT,
            "scanned": None, "scan_limit": None, "truncated": False,
            "detail": "rule %s, transaction %s" % (params["rule"], params["transaction"])}


def _narrowed(event, rows):
    """The queued part of one stored event: a collapsed event keeps only the queued rows, on a
    copy that is never added to the session; a per-row event is kept or left out whole."""
    from database import models
    from utils.payload_helper import get_payload_dict

    payload = get_payload_dict(event)
    if event_constants.is_collapsed_payload(payload):
        return models.DatabaseOutbox(
            event_uuid=event.event_uuid, table_name=event.table_name,
            event_type=event.event_type, processed_chain=True,
            payload=dict(payload, row_ids=[r for r in payload.get("row_ids") or ()
                                           if str(r) in rows]))
    row = payload.get("row_id")
    return event if row is None or str(row) in rows else None


def _run_rule_rows(db, params, log, control=None):
    """The rows a chain group queued for a `run_in: operation` rule, through the SAME group body
    the worker runs - one mapper call, one retraction, one write, one failure sentence; only
    WHEN differs (총괄 be0abe305 ②). A run is one page: a cancel lands before it."""
    from chain import ingestion_worker
    from database import models

    rule = _queued_rule(params["rule"])
    rows = set(params.get("rows") or ())
    total = len(rows) or len(params["events"])
    checkpoint = _checkpoint(control)
    if checkpoint is not None and checkpoint(0, total):
        return {"rows": 0, "stopped": True}
    stored = (db.query(models.DatabaseOutbox)
              .filter(models.DatabaseOutbox.event_uuid.in_(list(params["events"])))
              .order_by(models.DatabaseOutbox.id).all())
    gone = sorted(set(params["events"]) - {e.event_uuid for e in stored})
    if gone:
        raise RetroactiveRefused("the queued events are no longer in the outbox: %s" % gone[:5])
    events = [e for e in (_narrowed(e, rows) for e in stored) if e is not None]
    ok, error, broadcasts = ingestion_worker._process_chain_transaction_group_sync(
        params["transaction"], events, db, [rule])
    if not ok:
        db.rollback()
        # the chain's own record of a failed group - the same function, one attempt
        record = ingestion_worker._failure_record(events, error, params["transaction"], 1)
        text = json.dumps(record, ensure_ascii=False, default=str)
        over = len(text) - RUN_ERROR_LIMIT
        if over > 0:        # each character cut is at least one less in the JSON; '…' is one.
            # The middle goes: the head names the rule, the tail is the error raised.
            reason = record["reason"]
            keep = max(0, len(reason) - over - 1)
            record["reason"] = reason[:keep // 2] + "…" + reason[len(reason) - (keep - keep // 2):]
            text = json.dumps(record, ensure_ascii=False, default=str)
        raise RetroactiveRefused(text)
    db.commit()
    _send_broadcasts(broadcasts)
    log("[Retroactive] %s: rule %s wrote %d queued row(s) of transaction %s"
        % (RULE_ROWS_OP, rule.get("name"), total, params["transaction"]))
    stats = {"rows": total}
    _final_progress(control, total, stats)
    return stats


def _send_broadcasts(messages):
    """What the group body asks to announce, on the route the worker announces it on. A failed
    send is logged and swallowed, as the worker's is - the write is already committed."""
    import internal_event_client

    for message in messages or ():
        try:
            _url, res, note = internal_event_client.send_internal_event(
                internal_event_client.api_base_url(), "/internal/events/broadcast", message,
                timeout=3)
            if not res.ok:
                logger.error("[Retroactive] broadcast failed: %s -> %s %s",
                             _url, res.status_code, note or "")
        except Exception as exc:                                   # noqa: BLE001
            logger.error("[Retroactive] broadcast failed: %s", told(exc))


def _run_withdraw(db, params, log, control=None):
    from chain import replay

    written_by, columns = replay.unwritten_scope(params.get("rule"), params["table"], params.get("columns"))
    s = replay.withdraw_source(db, params["table"], params["source"],
                                     columns=columns, apply=True, log=log,
                                     checkpoint=_checkpoint(control), written_by=written_by)
    _final_progress(control, s.get("cells_claimed", s.get("cells_withdrawn")), s)
    return {"cells_withdrawn": s["cells_withdrawn"], "revealed": s["revealed"],
            "emptied": s["emptied"], "pinned_skipped": s["pinned_skipped"], "rows_deleted": s["rows_deleted"]}


def _count_fold_file_layers(db, params, scan_limit):
    from chain import replay

    s = replay.fold_file_layers(db, params["table"], apply=False, limit=scan_limit,
                                log=lambda m: logger.debug(m))
    truncated = s["rows_scanned"] >= scan_limit
    affected = s["layers_deleted"] + s["chain_renamed"] + s["chain_deleted"] + s["shown_changed"]

    def cells(key):
        return "; ".join("%s · %s" % (cell["row_id"], cell["column"]) for cell in s["first"][key])

    detail = (
        f"Files: {s['cells_folded']} cell(s) in {s['rows_scanned']} row(s) of '{params['table']}' "
        f"hold file layers that repeat a newer one: layers {s['layers_before']} -> "
        f"{s['layers_after']}, the deepest cell {s['deepest_before']} -> {s['deepest_after']}. "
        f"Chain, outside the key columns: {s['chain_renamed']} plain layer(s) become their source row's layer, "
        f"{s['chain_deleted']} whose row's layer is already there go, "
        f"{s['chain_unstamped']} have no source row and stay.")
    if s["chain_differs"]:
        detail += (f" {s['chain_differs']} of those hold a value no row layer of the cell holds "
                   f"(first: {cells('chain_differs')}).")
    if s["chain_copies"]:
        detail += (f" {s['chain_copies']} chain layer(s) a collision merge kept now rank as the chain's "
                   f"(first cells: {cells('chain_copies')}).")
    detail += (f" Shown values that move: {s['shown_changed']}"
               + (f" (first: {cells('shown_changed')})" if s["shown_changed"] else "")
               + " - each gets one history line. Cannot be undone - what goes is the record of which "
               "older layer said the same value. Afterwards give the space back with: "
               "python server/scripts/tune_layer_tables.py --table cell_sources --vacuum")
    return {
        "affected": affected,
        "absence": (ABSENCE_NOT_EXHAUSTIVE if truncated
                    else ABSENCE_TRULY_NONE if not affected else None),
        "affected_label": "layers to fold or rename, and shown values that move",
        "count_kind": COUNT_SAMPLE if truncated else COUNT_EXACT,
        "scanned": s["rows_scanned"],
        "scan_limit": scan_limit,
        "truncated": truncated,
        "detail": detail,
        "extra": {key: s[key] for key in ("cells_folded", "layers_deleted", "layers_before", "layers_after",
                                          "deepest_before", "deepest_after", "chain_renamed", "chain_deleted",
                                          "chain_unstamped", "chain_differs", "chain_copies", "shown_changed",
                                          "first")},
    }


def _run_fold_file_layers(db, params, log, control=None):
    from chain import replay

    s = replay.fold_file_layers(db, params["table"], apply=True, log=log,
                                checkpoint=_checkpoint(control),
                                **_given(params, "limit", "chunk_size", "pace"))
    _final_progress(control, s.get("rows_scanned"), s)
    return {key: s[key] for key in ("layers_deleted", "cells_folded", "layers_before",
                                    "layers_after", "rows_scanned", "chain_renamed", "chain_deleted",
                                    "chain_unstamped", "chain_differs", "chain_copies", "shown_changed")}


def _fold_args(params):
    """The fold's own cells of the operation's params - one spelling for the count, the run and the judge."""
    return {key: params.get(key) for key in ("prefer_column", "prefer_text", "mark_column",
                                             "only_column", "only_text")}


def _count_fold_duplicate_rows(db, params, scan_limit):
    from chain import replay

    s = replay.fold_duplicate_rows(db, params["table"], params["keys"], params.get("order"),
                                   keep=params.get("keep", "min"), log=lambda m: logger.debug(m),
                                   only_identical=bool(params.get("only_identical")), **_fold_args(params))
    _keys, _model, prefer, scope, mark = replay.fold_target(params["table"], params["keys"], params.get("order"),
                                                            params.get("keep", "min"), **_fold_args(params))
    keep = params.get("keep", "min")
    by = params.get("order") or "layers"
    which = ("the row with the most cell layers" if keep == replay.FOLD_KEEP_MOST_LAYERS
             else "the %s %s" % ("earliest" if keep == "min" else "latest", params["order"]))
    losers = s["rows_to_mark" if mark else "rows_to_delete"]

    def said(row):
        return "%s%s" % (row.get(by), " (%s=%s)" % (prefer[0], row.get(prefer[0])) if prefer else "")
    differing = "; ".join(
        "%s: %s" % (", ".join("%s=%s" % pair for pair in one["key"].items()),
                    " | ".join(", ".join("%s=%s" % (column, row.get(column)) for column in one["columns"])
                               for row in one["rows"]))
        for one in s["differing_sample"])
    shown = "; ".join(
        "%s: keeps %s, %s %s%s" % (
            ", ".join("%s=%s" % pair for pair in one["key"].items()),
            said(one["kept"] or {}), "marks" if mark else "deletes",
            ", ".join(said(d) for d in one["deleted"]),
            " and %d more" % (one["rows"] - 1 - len(one["deleted"]))
            if one["rows"] - 1 > len(one["deleted"]) else "")
        for one in s["sample"])
    return {
        "affected": losers,
        "absence": ABSENCE_TRULY_NONE if not losers else None,
        "affected_label": "rows to mark" if mark else "rows to delete",
        "count_kind": COUNT_EXACT,
        "scanned": s["rows"],
        "scan_limit": scan_limit,
        "truncated": False,
        "detail": (
            f"{s['keys_folded']} key(s) of ({', '.join(params['keys'])}) in '{params['table']}' "
            f"hold more than one row: {losers} row(s) {'are marked' if mark else 'go'}, {s['rows_kept']} stay. Per key "
            + (f"a row whose {prefer[0]} holds '{prefer[1]}' (any case) stays first - {s['keys_preferred']} "
               f"key(s) keep one - then " if prefer else "")
            + f"{which} stays (a blank one last, a tie the smaller row id). "
            f"{s['rows_blank_key']} row(s) with a blank key part are left as they are. Index on the keys: "
            f"{s['key_index']}."
            + (f" Only rows whose {scope[0]} holds '{scope[1]}' (any case) fold - {s['rows_out_of_scope']} "
               f"row(s) outside are left as they are." if scope else "")
            + (f" {s['rows_already_marked']} row(s) marked before rank no more." if mark else "")
            + (f" For example {shown}." if shown else "")
            + (f" {s['keys_differing']} key(s) hold rows whose values differ - by column "
               f"{', '.join('%s %d' % item for item in s['differing_columns'].items())}: "
               + ("they are left as they are (only_identical)." if s["only_identical"] else
                  f"they fold too, {s['rows_differing']} row(s) and their values go - only_identical leaves them.")
               + f" For example {differing}." if s["keys_differing"] else " No key's rows differ in their values.")
            + (f" Each is marked «{replay.FOLD_MARK % '<the row kept>'}» in {mark} - nothing is deleted - and "
               f"the rules that exclude by {mark} ({', '.join(s['rules_woken']) or 'none'}) run on them and take "
               f"back what they fed; "
               + (f"then the recount rules ({', '.join(s['rules_recounting'])}) run on the rows they fed. "
                  if s["rules_recounting"]
                  else "no recount rule paired - holds stay as they are. ")
               + "Empty the mark to bring a row back." if mark else
               " Each row goes as a grid delete does - its layers and a history line with it, and "
               "the chain takes back what it fed. Cannot be undone.")),
        "extra": {key: s[key] for key in ("keys_folded", "keys_preferred", "rows_kept", "rows_blank_key",
                                          "rows_out_of_scope", "rows_already_marked", "rules_woken",
                                          "rules_recounting", "sample", "keys_differing", "rows_differing",
                                          "differing_columns", "differing_sample")
                  } | {"rows_to_mark" if mark else "rows_to_delete": losers},
    }


def _run_fold_duplicate_rows(db, params, log, control=None):
    from chain import replay

    s = replay.fold_duplicate_rows(db, params["table"], params["keys"], params.get("order"),
                                   keep=params.get("keep", "min"), apply=True,
                                   pace=params.get("pace"), log=log, checkpoint=_checkpoint(control),
                                   only_identical=bool(params.get("only_identical")), **_fold_args(params))
    done = "rows_marked" if "rows_marked" in s else "rows_deleted"
    _final_progress(control, s[done], s)
    return {key: s[key] for key in (done, "rows_to_mark" if done == "rows_marked" else "rows_to_delete",
                                    "keys_folded", "keys_preferred", "rows_blank_key", "rows_out_of_scope",
                                    "keys_differing", "pages", "stopped", "key_index")}


def _judge_fold_duplicate_rows(params):
    from chain import cell_layer, replay

    try:
        replay.fold_target(params["table"], params["keys"], params.get("order"), params.get("keep", "min"),
                           **_fold_args(params))
    except cell_layer.ReplayRefused as e:
        raise RetroactiveRefused(str(e)) from None


def _count_fold_units(db, params, scan_limit):
    from chain import replay

    s = replay.fold_units(db, params["rule"], log=lambda m: logger.debug(m))
    return {
        "affected": s["rows_to_mark"],
        "absence": ABSENCE_TRULY_NONE if not (s["rows_to_mark"] or s["marks_withdrawn"]) else None,
        "affected_label": "rows to mark",
        "count_kind": COUNT_EXACT,
        "scanned": s["rows_proposed"],
        "scan_limit": scan_limit,
        "truncated": False,
        "detail": (f"{s['units']} unit row(s) in {s['groups']} group(s), {s['units_losing']} losing: "
                   f"{s['rows_to_mark']} of the {s['rows_proposed']} row(s) of '{s['table']}' the rule names get "
                   f"its mark ({s['rows_higher_layer']} keep showing a higher layer's value), "
                   f"{s['rows_already_marked']} are marked so already, {s['marks_withdrawn']} old mark(s) are "
                   f"withdrawn. No chain rule wakes - replay the copy rule next."),
        "extra": {key: s[key] for key in ("units", "groups", "units_losing", "rows_proposed", "rows_higher_layer",
                                          "rows_already_marked", "marks_withdrawn")},
    }


def _run_fold_units(db, params, log, control=None):
    from chain import replay

    s = replay.fold_units(db, params["rule"], apply=True, pace=params.get("pace"), log=log,
                          checkpoint=_checkpoint(control))
    _final_progress(control, s["rows_marked"], s)
    return {key: s[key] for key in ("rows_marked", "rows_to_mark", "rows_already_marked", "marks_withdrawn",
                                    "pages", "seconds", "stopped")}


def _judge_fold_units(params):
    from chain import cell_layer, replay

    try:
        replay.fold_units_target(params["rule"])
    except cell_layer.ReplayRefused as e:
        raise RetroactiveRefused(str(e)) from None


def _count_remove_shell_rows(db, params, scan_limit):
    from chain import replay

    s = replay.remove_shell_rows(db, params["table"], log=lambda m: logger.debug(m))
    shown = "; ".join(", ".join("%s=%s" % pair for pair in one.items()) for one in s["sample"])
    return {
        "affected": s["rows_to_delete"],
        "absence": ABSENCE_TRULY_NONE if not s["rows_to_delete"] else None,
        "affected_label": "rows to delete",
        "count_kind": COUNT_EXACT,
        "scanned": s["rows_read"],
        "scan_limit": scan_limit,
        "truncated": False,
        "detail": (f"{s['rows_read']} row(s) of '{params['table']}' show nothing outside their keys; "
                   f"{s['rows_to_delete']} of them have only the chain's key layers left - no value, no "
                   f"person's layer - and go as a grid delete does, a history line with each. Cannot be undone."
                   + (f" For example {shown}." if shown else "")),
        "extra": {key: s[key] for key in ("rows_read", "rows_to_delete", "sample")},
    }


def _count_delete_every_row(db, params, scan_limit):
    import chain_bindings
    from chain import cell_layer, replay
    from database import models

    table = params["table"]
    if params.get("how") == FULL_RESET:
        try:
            s = replay.full_reset(db, table, log=lambda m: logger.debug(m))
        except replay.ReplayRefused as e:
            raise RetroactiveRefused(str(e)) from None
        atoms = "; ".join("%s %d" % item for item in sorted(s["ledger_atoms"].items())) or "no source reads it"
        return {
            "affected": s["rows"],
            "absence": ABSENCE_TRULY_NONE if not s["rows"] else None,
            "affected_label": "rows to delete",
            "count_kind": COUNT_EXACT,
            "scanned": s["rows"],
            "scan_limit": scan_limit,
            "truncated": False,
            "detail": (f"Full reset of '{table}': {s['rows']} row(s), {s['layers']} cell layer(s) - {s['user_layers']} "
                       f"of them a person's - and {s['overwrites']} pin(s) go in one transaction. Cannot be undone. "
                       f"No chain rule is told: {', '.join(s['chain_rules']) or 'none reads it'}. Ledger atoms taken "
                       f"back afterwards: {atoms}. Run it with confirm_rows {s['rows']}."),
            "extra": {key: s[key] for key in ("rows", "layers", "user_layers", "overwrites", "ledger_atoms",
                                              "chain_rules")},
        }
    s = replay.delete_every_row(db, table, log=lambda m: logger.debug(m))
    kept = (db.query(models.CellSource.row_id).filter(models.CellSource.table_name == table,
                                                      models.CellSource.source_name.in_(cell_layer.PROTECTED_SOURCES))
            .distinct().count())
    taking = sorted("%s -> %s" % (rule.get("name"), rule.get("target_table")) for rule in replay.load_rules()
                    if rule.get("trigger_table") == table and chain_bindings.takes_deletions(rule))
    return {
        "affected": s["rows_to_delete"],
        "absence": ABSENCE_TRULY_NONE if not s["rows_to_delete"] else None,
        "affected_label": "rows to delete",
        "count_kind": COUNT_EXACT,
        "scanned": s["rows_read"],
        "scan_limit": scan_limit,
        "truncated": False,
        "detail": (f"Every row of '{table}' - {s['rows_to_delete']} - goes as a grid delete does: its layers and a "
                   f"history line with each; {kept} of them hold a person's value, which goes too. Cannot be undone. "
                   f"The file checklist is kept - to read the files again use 'Read all again' on the file page. "
                   + (f"Rules that take deletions from '{table}' do not run on these: {', '.join(taking)} - "
                      f"replay them afterwards if their tables should follow." if taking
                      else f"No rule takes deletions from '{table}'.")),
        "extra": {"rows_read": s["rows_read"], "rows_to_delete": s["rows_to_delete"], "rows_with_person": kept,
                  "rules_taking_deletions": taking, "sample": s["sample"]},
    }


def _run_delete_every_row(db, params, log, control=None):
    from chain import replay

    if params.get("how") == FULL_RESET:
        try:
            s = replay.full_reset(db, params["table"], confirm_rows=params.get("confirm_rows"), apply=True,
                                  by=getattr(control, "run_id", None) or replay.EVERY_ROW_DELETER, log=log)
        except replay.ReplayRefused as e:
            raise RetroactiveRefused(str(e)) from None
        _final_progress(control, s["rows_deleted"], s)
        return {"rows_deleted": s["rows_deleted"], "layers_deleted": s["layers_deleted"],
                "overwrites_deleted": s["overwrites_deleted"],
                "ledger_atoms_withdrawn": sum(s["ledger_withdrawn"].values())}
    s = replay.delete_every_row(db, params["table"], apply=True, pace=params.get("pace"), log=log,
                                checkpoint=_checkpoint(control))
    _final_progress(control, s["rows_deleted"], s)
    return {key: s[key] for key in ("rows_deleted", "rows_to_delete", "rows_read", "pages", "stopped")}


def _run_remove_shell_rows(db, params, log, control=None):
    from chain import replay

    s = replay.remove_shell_rows(db, params["table"], apply=True, pace=params.get("pace"), log=log,
                                 checkpoint=_checkpoint(control))
    _final_progress(control, s["rows_deleted"], s)
    return {key: s[key] for key in ("rows_deleted", "rows_to_delete", "rows_read", "pages", "stopped")}


def _count_fold_withdrawal_events(db, params, scan_limit):
    from chain import cell_layer

    s = cell_layer.fold_withdrawal_events(db, log=lambda m: logger.debug(m))
    before = sum(b for b, _a in s["by_table"].values())
    return {
        "affected": before,
        "absence": ABSENCE_TRULY_NONE if not before else None,
        "affected_label": "row-by-row withdrawal events to fold",
        "count_kind": COUNT_EXACT,
        "scanned": None,
        "scan_limit": None,
        "truncated": False,
        "detail": (cell_layer.fold_said(s) + " Each table's events become collapsed ones naming the same "
                   "rows, 1,000 rows each, in the commit that deletes them; the chain reads those rows as "
                   "they are when it runs."),
        "extra": {key: s[key] for key in ("by_table", "rows", "retrying", "running")},
    }


def _run_fold_withdrawal_events(db, params, log, control=None):
    from chain import cell_layer

    s = cell_layer.fold_withdrawal_events(db, apply=True, log=log, checkpoint=_checkpoint(control))
    folded = sum(b for b, _a in s["by_table"].values())
    _final_progress(control, folded, s)
    return {"events_folded": folded, "events_made": sum(a for _b, a in s["by_table"].values()),
            "rows": s["rows"], "left_retrying": s["retrying"], "left_running": s["running"],
            "pages": s["pages"], "stopped": s["stopped"]}




def _count_fold_written_notation(db, params, scan_limit):
    from chain import replay

    s = replay.fold_written_notation(db, params["table"], apply=False, limit=scan_limit,
                                     log=lambda m: logger.debug(m))
    truncated = s["rows_scanned"] >= scan_limit
    # a row re-keyed or merged is a change too - a table keyed by a number may move nothing else
    affected = s["cells_folded"] + s["keys_changed"] + s["rows_merged"]
    if not s["written_columns"] and not s["text_columns"] and not s["rows_scanned"]:
        return {"affected": 0, "absence": ABSENCE_NOT_APPLICABLE,
                "affected_label": "cells and row keys whose spelling changes",
                "count_kind": COUNT_EXACT, "scanned": 0, "scan_limit": scan_limit,
                "truncated": False,
                "detail": (f"'{params['table']}' has no \"write\" column in "
                           f"notation_rules.json and no text column - nothing is folded."),
                "extra": {}}
    left = s["time_left"]
    detail = (
        f"{s['cells_folded']} cell(s) and {s['layers_folded']} stored layer(s) in {s['rows_scanned']} "
        f"row(s) of '{params['table']}' take the declared spelling; {s['keys_changed']} row "
        f"key(s) change. Cannot be undone - the spelling that was stored stays in each cell's "
        f"history line.")
    if s["keys_not_rebuilt"]:
        detail += (f" {s['keys_not_rebuilt']} row(s) are skipped: the fold moves a key part, and "
                   f"the row's cells no longer spell its stored key, so its identity is left alone.")
    if s["rows_merged"]:
        sample = "; ".join(f"{m['business_key_val']} -> row {m['into']} ({m['folded_key']})"
                           for m in s["merged"][:3])
        detail += (f" {s['rows_merged']} row(s) fold onto another row's key - {s['same_key_groups']} key(s) "
                   f"held by more than one row as stored, {s['split_key_groups']} key(s) met by spelling; "
                   f"the run merges each into the key's first row (e.g. {sample}) and then builds the "
                   f"table's business-key unique index; a merge cannot be undone.")
    if s["moves_again"]:
        detail += (f" {s['moves_again']} value(s) change again on a second fold - the run "
                   f"stops there; fix the declaration first.")
    if left:
        detail += (f" The time rule leaves values as written - no matching format: "
                   f"{left.get('unmatched', 0)}, time zone written: {left.get('zoned', 0)}.")
    detail += (" Afterwards run Fold file layers on this table, then give the space back: "
               "python server/scripts/tune_layer_tables.py --table cell_sources --vacuum")
    return {
        "affected": affected,
        "absence": (ABSENCE_NOT_EXHAUSTIVE if truncated
                    else ABSENCE_TRULY_NONE if not affected else None),
        "affected_label": "cells and row keys whose spelling changes",
        "count_kind": COUNT_SAMPLE if truncated else COUNT_EXACT,
        "scanned": s["rows_scanned"],
        "scan_limit": scan_limit,
        "truncated": truncated,
        "detail": detail,
        "extra": {key: s[key] for key in ("layers_folded", "keys_changed", "rows_merged", "same_key_groups",
                                          "split_key_groups", "merged", "keys_not_rebuilt", "not_rebuilt",
                                          "moves_again", "again", "time_left")},
    }


def _run_fold_written_notation(db, params, log, control=None):
    from chain import replay

    s = replay.fold_written_notation(db, params["table"], apply=True, log=log,
                                     checkpoint=_checkpoint(control),
                                     **_given(params, "limit", "chunk_size", "pace"))
    _final_progress(control, s.get("rows_scanned"), s)
    out = {key: s[key] for key in ("cells_folded", "layers_folded", "keys_changed",
                                   "rows_merged", "same_key_groups", "split_key_groups", "keys_not_rebuilt",
                                   "moves_again", "stopped_on_moves_again", "rows_scanned")}
    if s["rows_merged"] and not s["stopped"]:
        # a table that held a key twice could not take its uq_bk_ index, and the builder runs at the scheduler's
        # start only - so it builds it here, after the merge (총괄 10-20)
        out["unique_index"] = _build_key_index_after_merge(db, params["table"], log)
    return out


def _build_key_index_after_merge(db, table, log):
    """The start-up builder for this one table, in the run's schema - on PostgreSQL, the one it builds on."""
    from sqlalchemy.orm import sessionmaker
    from chain.ingestion_worker import _ensure_business_key_unique_indexes_sync

    bind = db.get_bind()
    db.commit()                    # the run's read ends - a CONCURRENTLY build waits for every session on the table
    if bind.dialect.name != "postgresql":
        log(f"[notation] '{table}' business-key unique index not built: the builder works on PostgreSQL only")
        return {"skipped": bind.dialect.name}
    index = _ensure_business_key_unique_indexes_sync(sessionmaker(bind=bind), only=[table])
    found = {kind: [list(entry) for entry in index[kind]] for kind in index}
    log(f"[notation] '{table}' business-key unique index after the merge: {found}")
    return found


def _run_resolve(db, params, log, control=None):
    from chain import replay

    s = replay.recompute_display_values(db, params["table"], columns=params.get("columns"),
                                        apply=True, log=log, checkpoint=_checkpoint(control),
                                        **_given(params, "limit", "chunk_size"))
    _final_progress(control, s.get("rows_scanned"), s)
    return {"cells_changed": s["cells_changed"], "cells_examined": s["cells_examined"],
            "rows_scanned": s["rows_scanned"]}


def _run_enrichment_backfill(db, params, log, control=None):
    from chain import enrichment
    from database import crud

    rule = enrichment.backfill.load_rule(params["rule"], crud.TABLE_CONFIG,
                                         **_given(params, "force_disabled"))
    s = enrichment.backfill.run_backfill(db, rule, apply=True, log=log,
                                         checkpoint=_checkpoint(control),
                                         **_given(params, "limit", "chunk_size"))
    _final_progress(control, s.get("rows_scanned"), s)
    # 🔴 [판정 b3b6e8d55] 안 만든 행의 수가 여기서 «버려지고» 있었다 — 실행이 화면에
    # 닿는 통로는 `result_sentence` 한 문장뿐이라(판정 33), 이 dict 에 없는 수는 운영자가
    # 볼 길이 «없다». 그래서 다섯을 다 싣고, 0 도 싣는다: 0 이 안 보이면 「없음」과
    # 「안 세어 봄」이 같은 그림이다.
    return {"created_rows": s["created_rows"],
            "created_rows_label": "rows created",
            "updated_rows": s["updated_rows"],
            "updated_rows_label": "rows updated",
            "rows_scanned": s["rows_scanned"],
            "rows_scanned_label": "rows scanned",
            "skipped_no_key": s["skipped_no_key"],
            "skipped_no_key_label": "not created - no decision key",
            "skipped_no_key_group": GROUP_NOT_MADE,
            "skipped_blank_identity": s["skipped_blank_identity"],
            "skipped_blank_identity_label":
                "not created - identity columns all blank",
            "skipped_blank_identity_group": GROUP_NOT_MADE}


def _run_enrichment_confirm(db, params, log, control=None):
    # 🔴 THE CHECKPOINT IS BETWEEN PAGES OF THE QUEUE (총괄 8d8abfb5d). The sweep used to hand
    #    the whole queue to `confirm_keys` in one call, so a hook here could only stop it
    #    before any writing began; the sweep now pages the queue at the write chunk and asks
    #    between pages.
    from chain.enrichment import analysis
    from chain.enrichment import candidates

    # ignore_knob stays FALSE here: the knob is where a human consents to
    # automatic writes, and `run_auto_confirm_sweep` refuses apply without it.
    from chain.enrichment import config as enrichment_config

    caps = enrichment_config.load_read_caps(overrides=_given(
        params, enrichment_config.CAP_PROBE_SCAN_ROWS,
        enrichment_config.CAP_PROBE_DISTINCT_VALUES))
    s = analysis.run_auto_confirm_sweep(
        db, _enrichment_rule(params["rule"]), apply=True, ignore_knob=False, log=log,
        caps=caps, page_rows=candidates.CHUNK_SIZE, checkpoint=_checkpoint(control),
        **_given(params, "limit"))
    # The rows the pages reached - the whole queue when it finished, fewer when a cancel
    # stopped it. `queue_size` would call a stopped run's unread pages processed.
    _final_progress(control, s.get("rows_examined"), s)
    return {"confirmed": s.get("confirmed", 0), "written_cells": s.get("written_cells", 0),
            "queue_size": s.get("queue_size", 0),
            **({"probe_batch_fallbacks": sum(s["probe_batch_fallbacks"].values())} if s.get("probe_batch_fallbacks") else {})}


def _enrichment_rule(name):
    from chain import enrichment
    from database import crud

# 🔴 [판정 636] 「없다」와 「무엇이 있나」가 «같은 목록»에서 나와야 합니다 —
    #    한쪽만 넓히면 거절 문구가 자기가 안 본 것을 「없다」고 말합니다.
    from chain import enrich_declarations

    rules = enrich_declarations.declarations(known_tables=crud.TABLE_CONFIG)
    rule = next((r for r in rules if r["name"] == name), None)
    if rule is None:
        available = ", ".join(sorted(r["name"] for r in rules)) or "<none>"
        raise RetroactiveRefused(
            f"enrichment rule '{name}' not found or invalid; available: {available}")
    return rule


# ---------------------------------------------------------------------------
# Params judgments - the operation's OWN lookup, asked by `validate` (총괄 d34247b3d ㉠).
# The CLI asked it before recording and the admin publish did not, so one rule name had two
# answers: a refusal, or a queued run that failed in the child.
# ---------------------------------------------------------------------------

#: How often a backfill asks whether the day's file has been ingested (and whether to stop).
BACKFILL_POLL_SECONDS = 5


def _backfill_target(params):
    """(table, path, header, start) - read through the side-effect-free marker module, so the
    judge and the count can run in the API process."""
    import collector_markers
    import paths

    try:
        table, path, header = collector_markers.backfill_target(paths.DATA_ROOT,
                                                                params["collector"])
        return table, path, header, collector_markers.backfill_start(params["start"])
    except collector_markers.CollectorRefused as e:
        raise RetroactiveRefused(str(e)) from None


def _judge_collector_backfill(params):
    import collector_markers

    *_target, start = _backfill_target(params)
    if not collector_markers.backfill_windows(start):
        raise RetroactiveRefused("start '%s' is not in the past (KST) - there is no day to "
                                 "collect" % params["start"])


def _count_collector_backfill(db, params, scan_limit):
    import collector_markers

    table, _path, _header, start = _backfill_target(params)
    days = len(collector_markers.backfill_windows(start))
    return {
        "affected": days,
        "absence": ABSENCE_TRULY_NONE if not days else None,
        "affected_label": "days to collect",
        "count_kind": COUNT_EXACT,
        "scanned": days,
        "scan_limit": scan_limit,
        "truncated": False,
        "detail": (f"'{params['collector']}' runs once per 24 hours from "
                   f"{start.strftime('%Y-%m-%d %H:%M')} (KST) to now, and each day's file is "
                   f"ingested into '{table}' before the next day runs."),
        "extra": {"table": table},
    }


def _count_retype_column(db, params, scan_limit):
    from sqlalchemy import text
    from admin import retype

    table, column = params["table"], params["column"]
    physical = retype.family(db.get_bind(), table, column)
    cell = retype.CELLS.get((physical, params["type"]))
    values = retype.bad_values(db, table, column, cell) if cell else None
    do, said = retype.verdict(params["type"], physical, values, retype.key_uses(table, column) if cell else ())
    rows = db.execute(text('SELECT count(*) FROM "%s"' % table.replace('"', '""'))).scalar() if physical else 0
    return {
        "affected": rows if do == retype.CONVERT else 0,
        "absence": None if do == retype.CONVERT else ABSENCE_TRULY_NONE,
        "affected_label": "rows to convert",
        "count_kind": COUNT_EXACT,
        "scanned": rows,
        "scan_limit": scan_limit,
        "truncated": False,
        "detail": ("%s.%s is %s in the database; declared %s. %s" % (
            table, column, physical, params["type"],
            said or ("The column is converted with its indexes in one transaction, est. lock %s s (box rate)"
                     % retype.lock_estimate(db, table) if do == retype.CONVERT else "Nothing to convert."))),
        "extra": {"family": physical, "verdict": do, "bad_values": list(values or ())},
    }


def _retype_types():
    from admin import retype

    return sorted({declared for _family, declared in retype.CELLS})


def _run_retype_column(db, params, log, control=None):
    from admin import retype

    return retype.convert(db, params["table"], params["column"], params["type"], log, _checkpoint(control))


def _run_collector_backfill(db, params, log, control=None):
    """One day at a time: fill the script with that day's window, run it, wait until its
    file has passed the ingestion queue, then the next day. A day whose file fails stops
    the run and names the day; starting again from that day finishes it."""
    import collector_markers
    import paths
    import run_auto_update

    table, path, header, start = _backfill_target(params)
    windows = collector_markers.backfill_windows(start)
    collector = run_auto_update.GenericScriptRunnerCollector(
        table_name=table, script_path=path, cron_expression=header["schedule"],
        filename_prefix=header["filename_prefix"], server_dir=paths.DATA_ROOT,
        window=header["window"], window_format=header["window_format"])
    hook = _checkpoint(control)
    done = 0
    for window in windows:
        day = window[0].strftime("%Y-%m-%d %H:%M")
        collector.run_window = window
        try:
            written = collector.execute()
        except Exception as e:                                      # noqa: BLE001
            raise _day_refused(day, "collecting %s (KST) failed (%s: %s)"
                               % (day, type(e).__name__, e)) from e
        if written and not _wait_until_ingested(db, table, written, day, hook, done,
                                                len(windows)):
            break
        done += 1
        log(f"[collector_backfill] {params['collector']} {day} (KST) - day {done} of "
            f"{len(windows)} " + ("ingested" if written else "had nothing to collect"))
        if hook and hook(done, len(windows)):
            break
    # 🔴 [총괄 3a1446982] WHERE THE NEXT RUN PICKS UP: the end of the last finished window -
    #    for a run that reached the end that is the moment its last window was cut at, which
    #    start + days cannot give.
    stats = {"days": len(windows), "days_done": done,
             "done_until": collector_markers.backfill_text(
                 windows[done - 1][1] if done else start)}
    _final_progress(control, done, stats)
    return stats


def _collector_backfill_next_start(run: dict):
    """Where this collector's backfill picks up after `run`, in the shape `backfill_start`
    reads (총괄 3a1446982, 소유자 「다시 돌리니 처음부터 다시 도네」). The screen prefills Start
    with it; the operator may change it. None while the run is still going.

    DONE and CANCELLED wrote `done_until`. FAILED writes no result, so its finished days -
    `processed_rows`, one per day - name the failed day's own start. A DONE record from
    before `done_until` does not say where its last window was cut, so it says nothing.
    """
    import collector_markers

    if run.get("state") not in (RUN_DONE, RUN_CANCELLED, RUN_FAILED):
        return None
    done_until = (run.get("result") or {}).get("done_until")
    if done_until:
        return done_until
    if run.get("state") == RUN_DONE:
        return None
    try:
        start = collector_markers.backfill_start((run.get("params") or {}).get("start"))
    except collector_markers.CollectorRefused:
        return None
    return collector_markers.backfill_text(
        start + collector_markers.BACKFILL_SLICE * int(run.get("processed_rows") or 0))


def _day_refused(day, what):
    """The one sentence a day-by-day backfill stops on, whatever failed: what, and the day to
    start again from (총괄 69aad666e B - a script that raised used to end the run with no day)."""
    return RetroactiveRefused("%s - fix it, then start again from %s" % (what, day))


def _wait_until_ingested(db, table, written, day, hook, done, total) -> bool:
    """True once the file has passed the ingestion queue, False when a stop was asked while
    waiting. A file that FAILED stops the run by name. Asked of the checklist (`checkpoint.checked`),
    by the path and stat the collector wrote."""
    import os
    import time

    from ingestion import checkpoint

    where, stat = os.path.abspath(written), checkpoint.read_file_stat(written)
    while True:
        status = checkpoint.checked(db, table, [(where, stat)]).get(where)
        db.rollback()                      # the next look reads what has committed since
        if status in ("SUCCESS", checkpoint.STATUS_FAILED):
            if status == checkpoint.STATUS_FAILED:
                raise _day_refused(day, "the file collected for %s (KST) failed to ingest (%s)"
                                   % (day, os.path.basename(written)))
            return True
        if hook and hook(done, total):
            return False
        time.sleep(BACKFILL_POLL_SECONDS)


def _judge_chain_replay(params):
    from chain import replay

    try:
        replay.replay_refusal(replay.find_rule(params["rule"],
                                               row_scoped=bool(params.get("row_ids"))))
    except replay.ReplayRefused as e:
        raise RetroactiveRefused(str(e)) from None


def _judge_withdraw(params):
    from chain import cell_layer

    # `withdraw_source` refuses it AGAIN - this is convenience, that one is the safety property.
    if params.get("source") in cell_layer.PROTECTED_SOURCES:
        raise RetroactiveRefused(
            f"refusing to withdraw source '{params['source']}': it is the layer that means "
            f"'a human typed this'. There is no supported way to remove a human's value "
            f"from here - edit the cell instead.")
    _judge_table(params)
    from chain import replay
    try:
        replay.unwritten_scope(params.get("rule"), params["table"], params.get("columns"))
    except replay.ReplayRefused as e:
        raise RetroactiveRefused(str(e)) from None


def _judge_enrichment_backfill(params):
    from chain import enrichment
    from database import crud

    try:
        enrichment.backfill.load_rule(params["rule"], crud.TABLE_CONFIG,
                                      **_given(params, "force_disabled"))
    except enrichment.backfill.BackfillRefused as e:
        raise RetroactiveRefused(str(e)) from None


def _judge_enrichment_confirm(params):
    _enrichment_rule(params["rule"])


def _judge_table(params):
    """The one table-and-columns lookup R2 and R3 run first (총괄 bf9d3367a)."""
    from chain import cell_layer

    try:
        cell_layer.resolve_target(params["table"], params.get("columns"))
    except cell_layer.ReplayRefused as e:
        raise RetroactiveRefused(str(e)) from None


#: «Delete every row of a table»'s `how` for the one-transaction reset (소유자 10-23).
FULL_RESET = "full_reset"


def _judge_delete_every_row(params):
    """The table, and `confirm_rows` with a full reset only. The preview is judged here too, so a full reset's
    missing `confirm_rows` is the run's refusal (`replay.full_reset`), not this one."""
    _judge_table(params)
    if "confirm_rows" in params and params.get("how") != FULL_RESET:
        raise RetroactiveRefused("'delete_every_row' takes confirm_rows with how full_reset only")


def _ledger_world(params):
    """The ledger world a job runs in, by name (총괄 3b6dacd2f). A job stored before worlds
    carries the root it read instead: the default root IS the default world - by name,
    whichever world operates now - and any other root is refused by name - reading it as the
    default would read a different declaration. A job naming no world runs in the operating
    one; a world not declared is refused by name.
    """
    from ledger import schema

    root = params.get("ontology_root")
    world = params.get("world")
    if root is not None:
        if (os.path.normcase(os.path.normpath(str(root)))
                != os.path.normcase(os.path.normpath(
                    schema.world_names(schema.DEFAULT_WORLD).declaration_root))):
            raise RetroactiveRefused(
                f"this job reads the declaration at {root}, which is no ledger world's root - "
                f"run it again naming a world (--world)")
        world = world or schema.DEFAULT_WORLD
    try:
        return schema.require_world(world).name
    except (LookupError, ValueError) as exc:
        raise RetroactiveRefused(str(exc)) from None


def _ledger_setup(params):
    from ledger import schema
    from ledger.setup import load_setup

    return load_setup(schema.require_world(_ledger_world(params)).declaration_root)


def _judge_ledger_backfill(params):
    """Is the source declared - the first step of the run's own `_require_declared_source`.
    Only that step: a refused or retired source is a name that exists, and its count and
    run answer it as they did (총괄 8e54a261b ④)."""
    from ledger.setup import LedgerSetupError

    try:
        _ledger_setup(params).require_source(params["source"])
    except LedgerSetupError as e:
        raise RetroactiveRefused(str(e)) from None


def _judge_ledger_catch_up(params):
    """The world is declared - `_ledger_world` refuses it by name otherwise."""
    _ledger_world(params)


def _judge_ledger_rescope(params):
    """The run's own order - the one declared-source check, then the scope (총괄 06bb8f474)."""
    from ledger import backfill
    from ledger.setup import LedgerSetupError

    try:
        backfill.rescope_scope(_ledger_setup(params), params["source"],
                               params.get("scope_column"), params.get("scope_values") or [],
                               whole_source=bool(params.get("whole_source")))
    except LedgerSetupError as e:
        raise RetroactiveRefused(str(e)) from None


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

#: Per-operation facts a client cannot infer from the id, and must not guess.
#:
#: `deletes` and `restartable` are explicit so a client never infers mutation
#: semantics from an operation id.
#: 🔴 Whether this operation can be asked to stop BETWEEN BATCHES. False is not a defect
#: and not a TODO: it is a fact about where the operation's commits are chunked, and a
#: screen that offered cancel anyway would show a button that does nothing.
#: `judge` is the operation's own params judgment, asked by `validate` before anything
#: is recorded. None: the run is the first to judge them.
#: `examples` (the admin help's catalog, with `what_is_missing` and `next`) are the operator's own questions, an input
#: sample rendered nowhere - a screen that shows them as hints needs English samples beside them (총괄 10-23).
OPERATIONS = {
    "chain_replay": {
        "label": "Replay chain rules over old data (R1)",
        "what_is_missing": "data older than the rule has never been seen by that rule",
        "examples": ["체인 룰을 새로 만들었거나 고쳤는데 옛날 행에는 반영이 안 됐다", "조인을 고쳤는데 옛 행의 칸이 비어 있어", "이 규칙 예전 데이터에 다시 돌려줘"],
        "next": ["chain_replay of each rule that reads this rule's table, one by one - a replay wakes no rule (owner 09-26)"],
        "params": [_p("rule", help="chain rule name (GET /admin/chain/rules)"),
                   _p("business_keys", required=False, kind="csv",
                      help="replay only these rows, by business_key_val; omit for the "
                           "whole rule. This selects WHICH rows - `limit` still bounds "
                           "how many are scanned"),
                   # 🔴 [S-254] THE GRID HOLDS `row_id`, NOT THE STORED BUSINESS KEY.
                   # On a `composite_key_source` table that key is an ASSEMBLED string
                   # appearing in no column, so a screen sending what it can SEE matched
                   # nothing and the run reported `rows_scanned 0` with no error.
                   _p("row_ids", required=False, kind="csv",
                      help="replay only these rows, by row_id - the identity a grid "
                           "holds for every table. Use this from a screen; "
                           "`business_keys` is for a plain-keyed table's operator and "
                           "the CLI. Sending both is refused"),
                   _pace_param(),
                   _p("limit", required=False, kind="int", form=False,
                      help="bound the source rows scanned"),
                   _p("chunk_size", required=False, kind="int", form=False,
                      help="rows per write chunk"),
                   _p("cascade", required=False, kind="bool", form=False,
                      cli="grid click only - owner 09-27",
                      help="let what this replay writes wake the opted-in chain rules, "
                           "as the chain does - only the grid's click replay sends it"),
                   _p("continued_from", required=False, form=False, cli="Resume on a cut run's line only",
                      help="the cut replay run this one resumes - its pages after that run's last committed "
                           "page (POST /admin/retroactive/runs/{run_id}/resume writes it)")],
        "count": _count_chain_replay,
        "run": _run_chain_replay,
        "judge": _judge_chain_replay,
        "cli": ("server/scripts/chain_replay_cli.py replay <rule> "
                "[--business-keys a,b,c] [--row-ids r1,r2] [--pace slow] "
                "[--limit N] [--chunk-size N] --apply"),
        "deletes": None,
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("crud.apply_batch_updates commits per 1000-item write "
                               "chunk; a pace yields at the page boundary, after those "
                               "commits and before the next page is read"),
        "cli_only": ["replay-all (every rule in dependency order)"],
    },
    "withdraw": {
        "label": "Withdraw a stale source (R2)",
        "what_is_missing": "a wrong value an old rule wrote still wins the priority stack",
        "examples": ["옛 룰이 만든 틀린 값이 아직 이기고 있다", "이 소스가 쓴 값 다 빼줘"],
        "next": ["chain_replay of the rule that should hold the value - the withdrawal already shows what the layers left decide and removes the rows it emptied"],
        "params": [_p("table"), _p("source"),
                   _p("columns", required=False, kind="csv",
                      help="comma-separated column allowlist"),
                   _p("rule", required=False,
                      help="only this chain rule's layers, on the columns outside its target_columns")],
        "count": _count_withdraw,
        "run": _run_withdraw,
        "judge": _judge_withdraw,
        "cli": "server/scripts/chain_replay_cli.py withdraw <table> <source> [--rule <rule>] --apply",
        # It deletes a source's CLAIM, not the cell: the revealed value is recomputed and
        # written, and every changed cell gets an AuditLog entry naming the withdrawn source.
        # A row it leaves with no layer goes as a shell, as any withdrawal's does (총괄 69b8b029c).
        "deletes": "cell_sources rows (one source's claim on a cell), and the rows left with no layer",
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": "explicit commit per row chunk",
        "cli_only": ["--columns is available here too; nothing else exists on this path"],
    },
    "set_aside": {
        "label": "Set queued chain events aside",
        "what_is_missing": "the chain queue holds work that must not run now",
        "examples": ["사고 중 체인 대기열에 지금 돌면 안 되는 일이 쌓였다", "이 표 사건 지금 돌리지 마"],
        "next": ["rerun_set_aside when they should run"],
        "params": [_p("tables", required=False, kind="csv",
                      help="only events on these tables"),
                   _p("rules", required=False, kind="csv",
                      help="only events these chain rules would run on"),
                   _p("transactions", required=False, kind="csv",
                      help="only events of these transaction ids"),
                   _p("reason", help="why - written into each event set aside")],
        "count": _count_set_aside,
        "run": _run_set_aside,
        "judge": _judge_set_aside,
        "cli": ("server/scripts/outbox_triage.py --set-aside [--tables a,b] [--rules r] "
                "[--transactions t] --reason <why> --apply"),
        "deletes": None,
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": "one commit per 1000 events; a cancel stops between them",
        "cli_only": [],
        "downstream_note": ("Events set aside do not run - put them back with "
                            "'Run set-aside events again'"),
    },
    "rerun_set_aside": {
        "label": "Run set-aside events again",
        "what_is_missing": "events set aside during an incident never ran",
        "examples": ["치워 둔 사건을 이제 돌려", "사고 끝났으니 밀린 거 실행"],
        "next": ["chain_replay of the rules below them, one by one - this wakes none"],
        "params": [_p("tables", required=False, kind="csv",
                      help="only events set aside on these tables"),
                   _p("rules", required=False, kind="csv",
                      help="only these chain rules"),
                   _p("transactions", required=False, kind="csv",
                      help="only events of these transaction ids")],
        "count": _count_rerun_set_aside,
        "run": _run_rerun_set_aside,
        "judge": _judge_set_aside,
        "cli": ("server/scripts/outbox_triage.py --rerun-set-aside [--tables a,b] "
                "[--rules r] [--transactions t] --apply"),
        "deletes": None,
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": "chain_replay's own - one commit per staged page",
        "cli_only": [],
        "downstream_note": ("It replays the rows those events named, each rule once - "
                            "nothing downstream runs; replay a row from the grid to cascade"),
    },
    RULE_ROWS_OP: {
        "label": "Run a rule's queued rows (retired)",
        "what_is_missing": ("rows a run_in: operation rule's group queued before run_in was retired - "
                            "rules run in the chain now"),
        "examples": [],
        "next": [],
        "retired": True,
        "params": [_p("rule", help="the chain rule"),
                   _p("transaction", help="the transaction whose group queued the rows"),
                   _p("events", kind="csv", help="the outbox events that named the rows"),
                   _p("rows", required=False, kind="csv",
                      help="the trigger row ids this run carries")],
        "count": _count_rule_rows,
        "run": _run_rule_rows,
        "judge": _judge_rule_rows,
        "cli": ("python -c \"from admin import retroactive; retroactive.run_here("
                "'rule_rows', {'rule': '<rule>', 'transaction': '<tx>', "
                "'events': '<uuid,...>', 'rows': '<row id,...>'})\" - the chain worker queues "
                "these; by hand only to run a failed one again"),
        "deletes": None,
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": "one commit for the run - its rows are one group's write",
        "cli_only": [],
        "downstream_note": ("What it writes wakes the rules downstream, as the chain's own "
                            "write does"),
    },
    "resolve": {
        "label": "Recompute shown values from stored layers (R3)",
        "what_is_missing": "a cell shows a value its own stored layers no longer pick",
        "examples": ["칸에 여러 소스가 쌓여 있는데 옛 층이 표시되고 있다", "소스 창엔 맞는 값인데 셀은 옛 값이야"],
        "next": [],
        "params": [_p("table"),
                   _p("columns", required=False, kind="csv",
                      help="comma-separated column allowlist"),
                   _p("limit", required=False, kind="int", form=False,
                      help="bound the rows scanned"),
                   _p("chunk_size", required=False, kind="int", form=False,
                      help="rows per page")],
        "count": _count_resolve,
        "run": _run_resolve,
        "judge": _judge_table,
        "cli": ("server/scripts/chain_replay_cli.py resolve <table> [--columns a,b] "
                "[--limit N] [--chunk-size N] --apply"),
        # Only the shown column moves, from layers already stored; no layer is created or
        # deleted. Every moved cell gets an AuditLog row.
        "deletes": None,
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("one commit per page of rows; a stop lands between pages and "
                               "there is no resume - a re-run starts from the first page, "
                               "and recomputing from stored layers twice gives the same "
                               "answer"),
        "cli_only": ["--list-all (prints every moved cell)"],
    },
    "fold_written_notation": {
        "label": "Fold stored values into the declared spelling",
        "what_is_missing": ("a \"write\" column keeps the spellings stored before it was declared, "
                            "a text column keeps numbers stored before text took them, and a row keyed "
                            "by a number keeps the key spelling it was stored with («1.0» · «001»)"),
        "examples": ["표기 write 칸을 선언했는데 그 전에 저장된 값이 옛 철자다", "1.0 이랑 1 이 다른 값으로 잡혀"],
        "next": ["fold_file_layers, then python server/scripts/tune_layer_tables.py --table cell_sources --vacuum - the folded layers that now repeat go, and the space comes back"],
        "params": [_p("table"),
                   _pace_param(),
                   _p("limit", required=False, kind="int", form=False,
                      help="bound the rows scanned"),
                   _p("chunk_size", required=False, kind="int", form=False,
                      help="rows per page")],
        "count": _count_fold_written_notation,
        "run": _run_fold_written_notation,
        "judge": _judge_table,
        "cli": ("python -c \"from admin import retroactive; retroactive.run_here("
                "'fold_written_notation', {'table': '<table>', 'pace': '<pace>', 'limit': N, "
                "'chunk_size': N})\" - pace, limit and chunk_size optional"),
        # 총괄 2dc2c1baf · c6a8c069c ㉡: in place - a layer's value, the shown value and the key
        # move; no layer is created or deleted and no `ingested_at` moves. A row whose folded key
        # another row holds, or whose cells no longer spell its key, is skipped; a value a second
        # fold moves again stops the run.
        "deletes": None,
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("one commit per page of rows; a stop lands between pages and "
                               "a re-run folds only what is left"),
        "cli_only": [],
    },
    # The id is the first fold's: old run records and the CLI name it (총괄 10-11) - it folds chain layers too.
    "fold_file_layers": {
        "label": "Fold layers that repeat another",
        "what_is_missing": ("a cell re-delivered file after file keeps one layer per file; the chain's "
                            "layer is one per source row"),
        "examples": ["칸마다 파일 층이 여러 겹 쌓여 있다", "소스 창에 같은 값이 수십 줄이야"],
        "next": ["python server/scripts/tune_layer_tables.py --table cell_sources --vacuum - gives the space back"],
        "params": [_p("table"),
                   _pace_param(),
                   _p("limit", required=False, kind="int", form=False,
                      help="bound the rows scanned"),
                   _p("chunk_size", required=False, kind="int", form=False,
                      help="rows per page")],
        "count": _count_fold_file_layers,
        "run": _run_fold_file_layers,
        "judge": _judge_table,
        "cli": ("python -c \"from admin import retroactive; retroactive.run_here("
                "'fold_file_layers', {'table': '<table>', 'pace': '<pace>', 'limit': N, "
                "'chunk_size': N})\" - pace, limit and chunk_size optional"),
        # Per cell `crud.stacked_layers` (총괄 225b2c658 · 8ec008914): file layers that repeat one go, the
        # chain's plain layer outside the key columns becomes its source row's or goes when that row's layer is
        # there; a shown value the layers now answer otherwise is written with one history line (R3's write).
        "deletes": ("cell_sources rows (file layers that repeat a newer layer's value; plain chain "
                    "layer stamped with a row whose layer is already there, outside the key columns)"),
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("one commit per page of rows; a stop lands between pages and "
                               "a re-run finds only what is left"),
        "cli_only": [],
    },
    "fold_duplicate_rows": {
        "label": "Fold duplicate rows",
        "what_is_missing": "rows that should be one per key went in more than once",
        "examples": ["키마다 한 행이어야 하는데 같은 키의 행이 여럿 들어갔다", "같은 키 행 중 층 많은 것만 남기고 값이 다른 키는 건드리지 마"],
        "next": [],
        "params": [_p("table"),
                   _p("keys", kind="csv",
                      help="the columns whose values make a key; rows sharing them fold to one; "
                           "a row with a blank key part is left as it is"),
                   _p("order", required=False,
                      help="the column that picks the row to keep - with keep earliest or latest"),
                   _p("keep", required=False,
                      choices=[{"value": "min", "label": "Keep the earliest"},
                               {"value": "max", "label": "Keep the latest"},
                               {"value": "most_layers", "label": "Keep the row with the most layers",
                                "when": "no order - the row with the most cell layers stays, a tie the smaller row id"}],
                      help="which row of a key stays, by order; earliest when not given"),
                   _p("only_identical", required=False, kind="bool",
                      help="leave a key whose rows differ in their values as it is - the preview names the "
                           "columns and values either way"),
                   _p("prefer_column", required=False,
                      help="a column whose text puts a row first among its key's rows; with prefer_text"),
                   _p("prefer_text", required=False,
                      help="the text that column holds (any case) for the row to stay first"),
                   _p("mark_column", required=False,
                      help="a text column: the rows that fold are marked there instead of deleted - "
                           "the rules that exclude by it stop taking them"),
                   _p("only_column", required=False,
                      help="only rows whose column holds only_text fold; the rest are left as they are"),
                   _p("only_text", required=False, help="the text only_column holds (any case)"),
                   _pace_param()],
        "count": _count_fold_duplicate_rows,
        "run": _run_fold_duplicate_rows,
        "judge": _judge_fold_duplicate_rows,
        "cli": ("server/scripts/chain_replay_cli.py fold-rows <table> --keys <a,b> [--order <column>] "
                "[--keep min|max|most_layers] [--only-identical] [--prefer-column <column> --prefer-text <text>] "
                "[--mark-column <column>] [--only-column <column> --only-text <text>] [--pace slow] --apply"),
        # 총괄 d72dc0283: through crud.delete_rows_batch, the grid's delete - each row's layers
        # and history line go with it and the chain takes back what it fed. With mark_column
        # (016a766af) nothing is deleted.
        "deletes": "table rows (all but one per key), with their cell layers - none with mark_column",
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("one commit per page of up to 1,000 rows, sized to the page time "
                               "(crud.delete_rows_batch); a stop "
                               "lands between pages and a re-run finds only what is left"),
        "cli_only": [],
        "downstream_note": ("Each deleted row reaches the chain as a deletion - what it fed is "
                            "taken back and the rules that recount run; with a mark column the rules "
                            "that exclude by it run on the marked rows and take back what they fed"),
    },
    "fold_units": {
        "label": "Mark the losing units' rows (fold rule)",
        "what_is_missing": "per group one unit wins; the other units' rows are not marked yet",
        "examples": ["웨이퍼마다 이긴 잡 하나만 남겨야 하는데 진 잡의 로그 행이 표시 안 됐다", "접기 규칙 빨리 돌려줘"],
        "next": ["chain_replay of the copy rule - the marks wake no rule (setup step 6)"],
        "params": [_p("rule", help="the fold_by_unit chain rule on the unit table (GET /admin/chain/rules)"),
                   _pace_param()],
        "count": _count_fold_units,
        "run": _run_fold_units,
        "judge": _judge_fold_units,
        "cli": "server/scripts/chain_replay_cli.py fold-units <rule> [--pace slow] --apply",
        # 총괄 10-11: the write door's per-cell judgement, written set-based; then the edited unit rows'
        # withdrawal the worker runs (replay.fold_units).
        "deletes": "the rule's old marks a unit row no longer makes - its chain layer on the mark column",
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("one commit per page of rows (replay.FOLD_UNITS_PAGE); a stop lands between pages "
                               "and a re-run writes only what is left"),
        "cli_only": [],
        # 총괄 10-11: the end withdrawal does queue events - on the retroactive channel, waking no rule (application)
        "downstream_note": ("No chain rule wakes - the marks carry no event and no screen is told of them; "
                            "withdrawing old marks queues retroactive-channel edit events, which wake no rule. "
                            "Replay the copy rule next (setup step 6)"),
    },
    "delete_every_row": {
        "label": "Delete every row of a table",
        "what_is_missing": "a table to start again - every row goes; reading its files again is «Read all again»",
        "examples": ["표 하나를 통째로 다시 지어야 한다", "이 표 싹 비우고 처음부터 다시 읽고 싶어"],
        "next": ["Read all again on the file page - the file checklist is kept", "row by row: chain_replay of the rules that take deletions from this table, if their tables should follow"],
        "params": [_p("table"), _pace_param(),
                   _p("how", required=False, choices=[
                       {"value": "by_row", "label": "Row by row",
                        "when": "the grid's delete, a page at a time - what the rows fed is taken back by the chain"},
                       {"value": FULL_RESET, "label": "Full reset",
                        "when": "one transaction, for a table of millions - no chain rule is told, a person's "
                                "values go too, the ledger atoms of the sources reading the table are taken back"}],
                      help="row by row when left empty"),
                   _p("confirm_rows", required=False, kind="int",
                      help="full reset only: the rows the preview said - refused when the table has moved since")],
        "count": _count_delete_every_row,
        "run": _run_delete_every_row,
        "judge": _judge_delete_every_row,
        "cli": ("server/scripts/chain_replay_cli.py delete-every-row <table> [--pace slow] "
                "[--how full_reset --confirm-rows N] --apply"),
        # 총괄 4435b9b29 (소유자 10-21 「다시 로드랑 지우기 분리해」): remove_shell_rows' paging, judged «every row».
        "deletes": "every row of the table, with its cell layers and a history line each",
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("one commit per page of up to 1,000 rows, sized to the page time "
                               "(crud.delete_rows_batch); a stop "
                               "lands between pages and a re-run finds only what is left. A full reset is one "
                               "transaction - a stop does not land inside it"),
        "cli_only": [],
        "downstream_note": ("Each deleted row reaches the chain as a deletion - what it fed is "
                            "taken back; the deletion wakes no rule - replay the rules that take deletions "
                            "from this table if their tables should follow. A full reset tells the chain "
                            "nothing. The file checklist is not touched"),
    },
    "remove_shell_rows": {
        "label": "Remove rows with no source left",
        "what_is_missing": "rows the chain filled whose sources are all gone - only the chain's keys are left",
        "examples": ["원본이 다 지워졌는데 공식 표에 키만 남은 행이 쌓여 있다", "값 없이 키만 있는 행 지워줘"],
        "next": [],
        "params": [_p("table"), _pace_param()],
        "count": _count_remove_shell_rows,
        "run": _run_remove_shell_rows,
        "judge": _judge_table,
        "cli": "server/scripts/chain_replay_cli.py remove-shells <table> [--pace slow] --apply",
        # 총괄 5eee501eb: the judgement the chain's write seat asks (cell_layer.shells), through
        # crud.delete_rows_batch - each row's layers and a history line go with it.
        "deletes": "table rows left with only the chain's key layers, with their cell layers",
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("one commit per page of up to 1,000 rows, sized to the page time "
                               "(crud.delete_rows_batch); a stop "
                               "lands between pages and a re-run finds only what is left"),
        "cli_only": [],
        "downstream_note": ("Each deleted row reaches the chain as a deletion - what it fed is "
                            "taken back; the deletion wakes no rule"),
    },
    "fold_withdrawal_events": {
        "label": "Fold row-by-row withdrawal events",
        "what_is_missing": "withdrawals queued one chain event per row before they wrote collapsed ones",
        "examples": ["회수가 행마다 사건을 낸 채 쌓여 체인이 느리다", "거둔 뒤로 대기열이 안 줄어"],
        "next": [],
        "params": [],
        "count": _count_fold_withdrawal_events,
        "run": _run_fold_withdrawal_events,
        "judge": None,
        "cli": "server/scripts/chain_replay_cli.py fold-withdraw-events --apply",
        # 총괄 eddf9e38e ②: replaced in the same commit by collapsed events naming the same rows.
        "deletes": "waiting chain events a withdrawal staged row by row, replaced by collapsed ones",
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("one commit per page of 10,000 events; a stop lands between pages and "
                               "a re-run finds only what is left"),
        "cli_only": [],
        "downstream_note": ("The chain runs the collapsed events as it would have run the row-by-row "
                            "ones - every rule on those rows, reading them as they are then"),
    },
    "ledger_backfill": {
        "label": "Translate the rows not yet in the ledger",
        "what_is_missing": "the declaration reads this source, but some of its rows are not in the ledger yet",
        "examples": ["원장에 이 소스의 원자가 없거나 도중에 멈춰 있다", "새 소스를 선언했는데 걷기에 안 나와"],
        "next": [],
        "params": [_p("source", help="ledger source id (GET /api/ledger/declaration)"),
                   _pace_param(),
                   _p("fetch_rows", required=False, kind="int", form=False,
                      help="rows read per page"),
                   _p("max_batches", required=False, kind="int", form=False,
                      help="stop after this many pages"),
                   _p("world", required=False, form=True,
                      help="a ledger world (branch) by name; none = the operating world")],
        "count": _count_ledger_backfill,
        "run": _run_ledger_backfill,
        "judge": _judge_ledger_backfill,
        "cli": ("server/ledger/backfill.py --source <source> [--pace slow] "
                "[--fetch-rows N] [--max-batches N] [--world <name>]"),
        "deletes": None,
        # 🔴 THIS IS THE ONE THE OWNER NAMED: "백필 돌리다 서버 렉먹는데 백필만 못꺼서
        # 서버 재기동". It commits per page and a rerun asks the row index again for the rows
        # still missing, so asking it to stop between pages costs nothing and gives that
        # back - the server stays up and every other job with it.
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": "atoms and the row index in one commit per page",
        "cli_only": ["--scope-column/--scope-values (that is `ledger_rescope` here)"],
    },
    "ledger_catch_up": {
        "label": "Catch a ledger world up",
        "what_is_missing": ("the world did not follow its tables live for a while, so rows "
                            "made, edited or deleted meanwhile are not in its ledger"),
        "examples": ["원장이 못 본 수정이 있다 — 표 값이 바뀌었는데 원자가 옛 값 그대로", "가지를 다시 켰는데 옛 값이야"],
        "next": ["python -m ledger census --source <source> - the source panel keeps the numbers it measured until a census runs again"],
        "params": [_p("world", help="a ledger world by name (GET /admin/ontology-explorer/worlds)"),
                   _pace_param()],
        "count": _count_ledger_catch_up,
        "run": _run_ledger_catch_up,
        "judge": _judge_ledger_catch_up,
        "cli": "server/ledger/backfill.py --world <world> --catch-up [--pace slow]",
        "deletes": ("ledger_events rows (the atoms of rows the table lost, and the old atoms of "
                    "rows edited since)"),
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("each step's own - one commit per page of rows; a stop lands "
                               "between pages and sources, and a re-run finds only what is left"),
        "cli_only": [],
    },
    "ledger_rescope": {
        "label": "Re-translate a ledger scope",
        "what_is_missing": "corrected input never reached the ledger, so that scope alone holds stale values",
        "examples": ["원장 해석을 고쳤는데 이미 적재된 원자는 옛 해석 그대로다", "이 랏만 원장 다시 번역해줘"],
        "next": [],
        "params": [_p("source", help="ledger source id (GET /api/ledger/declaration)"),
                   _p("scope_column", required=False,
                      help="a column this source's read declares; anything else is "
                           "refused by name with the declared list"),
                   _p("scope_values", required=False, kind="csv",
                      help="comma-separated values of that column"),
                   _p("whole_source", required=False, kind="bool", form=False,
                      help="every row of the source instead of a scope"),
                   _p("world", required=False, form=True,
                      help="a ledger world (branch) by name; none = the operating world")],
        "count": _count_ledger_rescope,
        "run": _run_ledger_rescope,
        "judge": _judge_ledger_rescope,
        "cli": ("server/ledger/backfill.py --source <source> --scope-column <column> "
                "--scope-values <a,b,c> | --whole-source [--world <name>] --apply"),
        # It deletes this source's atoms from the NAMED rows and nothing else:
        # `source_who` is in the delete predicate, so an atom another source wrote about
        # the same die is unreachable from here however the scope is spelled.
        "deletes": "ledger_events rows (this source's atoms from the named rows only)",
        # A page's withdrawal and remake are one commit (S-60), and a cancel lands between
        # pages (총괄 8d8abfb5d): done pages are whole, the rest untouched. Re-running the
        # same scope redoes it from the first page - the remake dedupes what is already there.
        "reads_as": "pair",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("one commit per page of scope rows - its withdrawal and remake "
                               "together - then its stale index rows; a stop lands between "
                               "pages"),
        "cli_only": [],
    },
    "enrichment_backfill": {
        "label": "Create enrichment derived rows",
        "what_is_missing": "the derived rows were never created at all",
        "examples": ["파생 테이블에 행 자체가 없다", "워크리스트에도 안 떠"],
        "next": ["enrichment_confirm when the new rows' target cell stays empty"],
        "params": [_p("rule", help="enrichment rule name (chain_rules.json)"),
                   _p("limit", required=False, kind="int", form=False,
                      help="caps NEW identities, not the scan"),
                   _p("force_disabled", required=False, kind="bool", form=False,
                      help="run even if the rule is disabled"),
                   _p("chunk_size", required=False, kind="int", form=False,
                      help="source scan chunk size")],
        "count": _count_enrichment_backfill,
        "run": _run_enrichment_backfill,
        "judge": _judge_enrichment_backfill,
        "cli": ("server/scripts/backfill_enrichment.py <rule> [--limit N] "
                "[--force-disabled] [--chunk-size N] --apply"),
        "deletes": None,
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": "crud.apply_batch_updates commits per source chunk",
        "cli_only": [],
    },
    "enrichment_confirm": {
        "label": "Auto-confirm single candidates",
        "what_is_missing": "the derived rows exist but the target cell is empty",
        "examples": ["파생 행은 있는데 타깃 칸이 비어 있다", "후보가 하나뿐인데 왜 안 채워져"],
        "next": [],
        "params": [_p("rule", help="enrichment rule name (chain_rules.json)"),
                   _p("limit", required=False, kind="int", form=False,
                      help="cap the number of rows examined"),
                   _p("probe_scan_rows", required=False, kind="int", form=False,
                      help="max rows one candidate probe scans"),
                   _p("probe_distinct_values", required=False, kind="int", form=False,
                      help="max distinct values one probe may see")],
        "count": _count_enrichment_confirm,
        "run": _run_enrichment_confirm,
        "judge": _judge_enrichment_confirm,
        "cli": ("server/scripts/enrichment_insights.py confirm <rule> [--limit N] "
                "[--probe-scan-rows N] [--probe-distinct-values N] --apply"),
        "deletes": None,
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("the queue is written a page at a time (the write chunk), each "
                               "page committed; a stop lands between pages"),
        "cli_only": ["--ignore-knob (measure a rule whose knob is off)",
                     "classify / propose subcommands", "all rules at once"],
    },
    "collector_backfill": {
        "label": "Backfill a collector day by day",
        "what_is_missing": "a source added today has no data for the days before it",
        "downstream_note": ("The files it collects are ingested as usual, and the chain runs "
                            "on them"),
        "examples": ["오늘 붙인 수집기에 지난 날들의 데이터가 없다", "지난주 것도 가져와"],
        "next": ["collector_backfill again from the line's next_start when it stopped short"],
        "params": [_p("collector", help="<table>/<script.py> of a collector that declares "
                                         "'# window:'"),
                   _p("start", help="first day, KST - YYYY-MM-DD (that day's 00:00) or "
                                    "YYYY-MM-DD HH:MM")],
        "count": _count_collector_backfill,
        "run": _run_collector_backfill,
        "judge": _judge_collector_backfill,
        "next_start": _collector_backfill_next_start,
        "cli": ("python -c \"from admin import retroactive; retroactive.run_here("
                "'collector_backfill', {'collector': '<table>/<script.py>', "
                "'start': 'YYYY-MM-DD'})\""),
        "deletes": None,
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("one day at a time - the day's file is ingested (the file "
                               "checkpoint says DONE) before the next day runs; a stop lands "
                               "between days, and a failed day stops the run and names it"),
        "cli_only": [],
    },
    "retype_column": {
        "label": "Convert a column's type",
        "what_is_missing": "a column the table declaration names a number that the database still holds as text",
        "downstream_note": ("The table is locked while it converts; afterwards the declaration says the new type "
                            "and every process reads the column as it"),
        "examples": ["숫자 칸인데 DB 엔 글자로 들어가 있다", "칸 타입 바꿨는데 정렬이 글자처럼 돼"],
        "next": [],
        "params": [_p("table"), _p("column"),
                   _p("type", help="the declared type", choices=lambda: sorted(_retype_types()))],
        "count": _count_retype_column,
        "run": _run_retype_column,
        "judge": _judge_table,
        "cli": ("python -c \"from admin import retroactive; retroactive.run_here("
                "'retype_column', {'table': '<table>', 'column': '<column>', 'type': 'number'})\""),
        "deletes": None,
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("one transaction - the values checked, the indexes reading the column dropped, "
                               "the column converted, those indexes built again; then the declaration's one cell. A "
                               "stop lands before the transaction begins; once it has, it ends"),
        "cli_only": [],
    },
}

#: The upkeep doors outside this tab, in the catalog's cells - what the operator means to do, their questions, and
#: the door to call next (소유자 10-23 ㄴ). Not runs: each door is its own route or command, named in `doors`.
DOORS_OUTSIDE = {
    "read_files_again": {
        "label": "Read files again",
        "what_is_missing": "files already read keep the parse they had - the parser or the table's reading changed since",
        "examples": ["파서(또는 칸 선언)를 고쳤는데 이미 들어간 파일의 행은 옛 해석 그대로다", "이 파일 지금 다시 읽어줘",
                     "이 폴더 실패한 파일만 다시", "표 선언에 칸을 더했는데 이미 들어간 파일에는 그 칸이 비어 있다"],
        "doors": [
            {"name": "now", "how": ("the file page's Retry · Read all again · Retry failed files under a folder "
                                    "(POST /admin/file-ingestion/retry-failed) · Read now"),
             "when": ("the rows the file log names, picked by state, folder and time, read where the log says they "
                      "are; a file gone from there is not handed")},
            {"name": "next sweep", "how": "python server/scripts/replay_ingestion.py --path <file> [--table <table>] --apply",
             "when": ("a file still where its source's sweep looks - its log row's stamp emptied, the next sweep "
                      "reads it as the source's pattern takes it; a file moved away is not read")}],
        "next": [("after a table_config change (a column added) the watcher keeps the read files as read and hands "
                  "the failed ones only - Read all again on the file page reads the rest with the new declaration "
                  "(owner 10-23)")],
    },
}


#: The states a run row can be in. `cancel_requested` is a REQUEST, not an outcome:
#: the operation is still running when it is set, and becomes `cancelled` only when the
#: operation itself has stopped between batches. Collapsing the two would make a run look
#: finished while it was still writing.
RUN_QUEUED = "queued"
RUN_RUNNING = "running"
import event_constants as ec                                      # noqa: E402
import error_said
from error_said import told

RUN_DONE = "done"
RUN_CANCEL_REQUESTED = "cancel_requested"
RUN_CANCELLED = "cancelled"
RUN_FAILED = "failed"

#: What each state is CALLED on a screen, shipped with the run list (lead a274c90f0: the row
#: ends in its state word instead of a fade). The token stays the key.
RUN_STATE_NAMES = {
    RUN_QUEUED: "Queued", RUN_RUNNING: "Running", RUN_CANCEL_REQUESTED: "Stopping",
    RUN_DONE: "Done", RUN_CANCELLED: "Cancelled", RUN_FAILED: "Failed",
}

#: How a run that is still `running` is MOVING. `running` alone cannot say it: a backfill
#: that legitimately takes an hour and one that stopped an hour ago are the same row, the
#: same gate, and the same silence. On 2026-09-04 that silence is what an operator saw -
#: one outbox row aging with no reason attached to it anywhere.
MOVING_PROGRESSING = "progressing"
MOVING_STALLED = "stalled"
MOVING_UNREPORTED = "unreported"

#: Whether a cancel request can reach this run AT ALL.
#:
#: 🔴 THE ANSWER IS OFTEN NO, AND SAYING SO IS THE POINT. Stopping is cooperative and only
#: happens at a batch boundary (`RunControl`), so a run stuck INSIDE a batch never reaches
#: the place that reads the flag - and two registered operations declare
#: `cancellable: False`, which means they have no batch boundary to offer in the first
#: place. A screen that shows a cancel button in either case shows a button that does
#: nothing, which this repository has already ruled against once.
CANCEL_AT_NEXT_BATCH = "at_next_batch"
CANCEL_UNKNOWN = "unknown"
CANCEL_NEVER = "never"

#: The states in which a run still holds the scheduler's gate closed.
#:
#: 🔴 `cancel_requested` BELONGS HERE. Asking a run to stop does not stop it - the flag is
#: read at a batch boundary and the thread stays alive until it reaches one, so the gate
#: stays shut and the outbox row keeps waiting. Leaving this state out would report "no
#: run in flight" beside a queue that is demonstrably waiting for something, which is the
#: same silence this whole round is about.
IN_FLIGHT_STATES = (RUN_RUNNING, RUN_CANCEL_REQUESTED)


def _hb_stale_after():
    """The existing "silence has lasted long enough" constant. Read, never redefined."""
    from utils import heartbeat as _hb
    return _hb.DEFAULT_STALE_AFTER_SEC


def queue_view(db, now=None):
    """The queue's own state, for the three the owner asked to tell apart.

    🔴 `last_pickup` IS THE FIRST FIELD, not one of four. The picker is the scheduler's
    tick; if it is alive a run waits one tick, and if it is not, a run waits forever -
    measured 2026-09-05, three runs at 3.0s, 3.0s and 320.5s, with nothing in between.
    So "how long has the queue been" does not separate "about to run" from "nothing is
    picking up", and the age of the last pickup does. A short queue with an old pickup is
    the state that used to look like an empty one.

    ⛔ NO DISTRIBUTION. An earlier instruction asked for one; the measurement retired it.
    The waits are two peaks - one tick, or unbounded - and drawing a spread would draw a
    middle that does not exist.

    ⛔ AND NO PREDICTED START TIME. The spread between the peaks is a hundredfold, so a
    single "starts in N seconds" would be false most of the time. Values go out; the
    reading is the screen's.

    Nouns and numbers, no sentences: a phrase composed here is a phrase the screen has to
    render verbatim, and the wording is not the server's to choose.
    """
    from datetime import datetime, timezone

    from database import models

    now = now or datetime.now(timezone.utc)

    def _age(dt):
        d = _utc(dt)
        return None if d is None else round(max(0.0, (now - d).total_seconds()), 1)

    # WHEN THE PICKER LAST TOOK SOMETHING. `started_at` is stamped by the tick that picked
    # the run up, so its newest value is the picker's own last sign of life - read from the
    # same table as everything else rather than from a second mechanism.
    last_started = (db.query(models.RetroactiveRun.started_at)
                    .filter(models.RetroactiveRun.started_at.isnot(None))
                    .order_by(models.RetroactiveRun.started_at.desc()).first())
    last_at = _utc(last_started[0]) if last_started else None

    waiting_rows = (db.query(models.RetroactiveRun)
                    .filter(models.RetroactiveRun.state == RUN_QUEUED)
                    .order_by(models.RetroactiveRun.queued_at.asc()).all())
    waiting = [{
        "run_id": r.run_id,
        "op": r.op,
        # RAW, and None when the row carries none - the word for "unknown" is the screen's.
        "requested_by": r.requested_by,
        "queued_at": _utc(r.queued_at).isoformat() if r.queued_at else None,
        "waiting_seconds": _age(r.queued_at),
    } for r in waiting_rows]

    # 🔴 THE SERVER COUNTS THE POSITION. The list can be capped or reordered on the way to
    # a screen, and a screen counting its own rows would then answer a different question
    # than the one it looks like it is answering.
    for position, item in enumerate(waiting, start=1):
        item["ahead"] = position - 1

    # 5-bis: rows that claim to be running while nobody on this host owns the pid. Only
    # decidable for runs stamped by THIS host - a pid on another machine is not something
    # this process may call dead, so it is reported as unknown rather than orphaned.
    orphaned = []
    running_rows = in_flight_rows(db).all()
    for r in running_rows:
        owner = _runner_state(r.runner)
        if owner in ("orphaned", "unknown"):
            orphaned.append({"run_id": r.run_id, "op": r.op, "runner": r.runner,
                             "owner": owner, "started_seconds": _age(r.started_at)})

    return {
        "last_pickup_at": last_at.isoformat() if last_at else None,
        "last_pickup_age_seconds": _age(last_at),
        "picker_interval_seconds": PICKER_INTERVAL_SECONDS,
        # 🔴 THE BOUNDARY, FROM THE CONSTANT THIS SYSTEM ALREADY HAS. A reader given only
        # an age has to invent the line it is judged against, and an invented threshold is
        # one more number to keep in step. `DEFAULT_STALE_AFTER_SEC` is already this
        # system's answer to "long enough that silence means something".
        #
        # ⚠️ AND IT ONLY MEANS ANYTHING WHEN SOMETHING IS WAITING. An idle queue has an old
        # last-pickup for the ordinary reason that nothing has been queued, so reading this
        # against the age alone would call a healthy system stalled. The pair is
        # `waiting_count > 0` AND `last_pickup_age_seconds > stall_after_seconds`; the
        # values go out and the reading stays the screen's, as with everything else here.
        "stall_after_seconds": _hb_stale_after(),
        "waiting_count": len(waiting),
        "waiting": waiting,
        "orphaned": orphaned,
        # 🔴 "THE ROWS BELOW MAY BE WRONG." When a run row cannot be updated the work still
        # runs and the row still says queued, so every number above it is stale in a way
        # nothing else can detect. Published as a value, not left in a log.
        "record_failures": record_failures(),
    }


#: The scheduler tick that picks queued runs up (`SchedulerDaemon.check_interval`). Published
#: so a reader can say "one tick" without knowing the scheduler's internals - and so that
#: "last pickup" has something to be compared against.
PICKER_INTERVAL_SECONDS = 5


def in_flight_rows(db):
    """The run rows that are running - THE judgement for this source (총괄 5996d7f54). The gate,
    the queue's orphan list and `runtime.running` all ask here."""
    from database import models

    return (db.query(models.RetroactiveRun)
            .filter(models.RetroactiveRun.state.in_(IN_FLIGHT_STATES)))


def in_flight(db, now=None, stall_after=None):
    """The run the scheduler's gate is closed on, and whether it is still moving.

    Returns ``None`` when no run is recorded as in flight. Otherwise a dict carrying the
    run, its `moving` state, and whether a cancel could reach it.

    🔴 IT READS THE `retroactive_runs` TABLE, NOT THE THREAD. The thread is in the
    scheduler process and the reader of this is the web process, so the thread is not
    observable from here at all - which is exactly why the stall was invisible. The table
    is written by `RunControl` on its own session precisely so it survives the operation's
    transaction, and that is what makes it readable from outside.

    ⚠️ AND THAT MEANS THE ROW CAN OUTLIVE THE PROCESS. A scheduler killed mid-run leaves
    `running` behind forever, and this will keep reporting it as in flight. The report is
    still the true one for an operator - the work is not going to finish and the run has
    to be pressed again - but it is not proof that a thread exists.

    ⚠️ `unreported` IS NOT `stalled`. `_mark_run(started=True)` stamps `last_progress_at`
    at the start, and only four of the six registered operations pass a `_checkpoint` hook
    (measured 2026-09-04: `ledger_rescope` and `enrichment_confirm` never report progress
    while they run). For those two, and for any run that stops before its first batch
    boundary, "no progress since the start" is all that is known - and calling that a
    stall would name a fault that has not been established.
    """
    from datetime import datetime, timezone

    from database import models

    if stall_after is None:
        # The threshold `/health` already uses for "claimed work that stopped
        # progressing". One spelling of "long enough to be a stall" for both.
        from utils import heartbeat
        stall_after = heartbeat.DEFAULT_STALL_AFTER_SEC
    now = now or datetime.now(timezone.utc)

    row = (in_flight_rows(db)
           # ⚰️ `.nullslast()` REMOVED (S-131 의 같은 부류, S-130 커밋에 같이).
           # `DESC NULLS LAST` 는 btree 가 «뒤로 읽어» 줄 수 있는 순서가 아니라
           # 인덱스를 못 쓰게 만든다 — 그 절이 그리드에서 0.25 s 를 먹였다.
           # 이 표는 작아서 비용은 작지만, 남겨 두면 다음 사람이 「거기만 있었다」고 읽는다.
           .order_by(models.RetroactiveRun.started_at.desc())
           .first())
    if row is None:
        return None

    started, progressed = _utc(row.started_at), _utc(row.last_progress_at)
    since = None if progressed is None else max(0.0, (now - progressed).total_seconds())
    reported = bool(started and progressed and progressed > started)

    if since is not None and since <= stall_after:
        moving = MOVING_PROGRESSING
    elif reported:
        moving = MOVING_STALLED
    else:
        moving = MOVING_UNREPORTED

    try:
        cancellable = bool(operation(row.op)["cancellable"])
    except RetroactiveRefused:
        cancellable = False
    if not cancellable:
        cancel = CANCEL_NEVER
    elif moving == MOVING_PROGRESSING:
        cancel = CANCEL_AT_NEXT_BATCH
    else:
        cancel = CANCEL_UNKNOWN

    return {
        "run_id": row.run_id,
        "op": row.op,
        # 🔴 WHY IT IS RUNNING, NOT JUST THAT IT IS. The queue shows this row as the reason
        # everything behind it waits, and an operator looking at it could not tell WHICH
        # request was holding the line - the same three facts the runs list has carried all
        # along. Same names as `runs()` so the two windows cannot describe one row
        # differently.
        # ⚠️ `requested_by` travels RAW, and `None` when the row carries none. The word an
        # operator reads for that is the screen's to choose - a display word decided here
        # would make this contract a second shape, and every other field settled today
        # (blocks_activation, partial_apply, the refusal codes, the four source states)
        # went the other way. `runs()` answers the same field the same way.
        "params": json.loads(row.params) if row.params else {},
        "requested_by": row.requested_by,
        "queued_at": row.queued_at.isoformat() if row.queued_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "state": row.state,
        "moving": moving,
        # 🔴 «WHO» IS HOLDING THE GATE, and it travels raw. A run row can outlive its
        # process, so an operator asking "is anything actually doing this" had nothing to
        # look at. NULL means the row predates this column - unknown, not "nobody".
        "runner": row.runner,
        # 🔴 THE GATE'S OWN STATE, SAID OUT LOUD. `moving` was computed here and thrown
        # away: the response carried "a run is in flight" and the screen could not tell
        # "about to finish" from "stopped and blocking everything behind it". Those are
        # the three states the owner asked to be able to see, and the second one is the
        # one that looks like nothing at all.
        "gate_blocked": moving in (MOVING_STALLED, MOVING_UNREPORTED),
        "no_progress_seconds": None if since is None else round(since, 1),
        "stall_after_seconds": stall_after,
        "processed_rows": row.processed_rows,
        "total_rows": row.total_rows,
        "cancel_reaches": cancel,
        "recovery": ("This run cannot be stopped with a cancel. Collect the log "
                     "first, restart the scheduler, and run it AGAIN - the guarantee "
                     "is at-most-once, so it did not finish."),
    }


#: ingestion_settings.json - the stage lines inside a page (총괄 d9be013cb, 소유자 「재번역 디버그 로그 다 띄워」). Default on;
#: off leaves the page lines and the beat. Read at every page boundary, so a change takes the next page.
DEBUG_SETTING = "retroactive_debug"
#: ingestion_settings.json - seconds a statement of the run's process runs before the beat says it; null or 0: never.
SLOW_STATEMENT_SETTING = "retroactive_slow_statement_seconds"
SLOW_STATEMENT_DEFAULT = 2.0
#: Seconds between two beat lines of a running run (총괄 d9be013cb «5 초마다»), and between two looks for a slow statement.
BEAT_SECONDS = 5.0
LOOK_SECONDS = 1.0
#: How much of a statement a beat line shows, and a slow statement's line.
BEAT_QUERY_CHARS, SLOW_QUERY_CHARS = 120, 400
#: ingestion_settings.json - how many processes a whole source's re-translate runs in (`_rescope_in_slices`): a positive
#: integer; absent or anything else half the cores, `TRANSLATE_SLICES_MOST` at most (총괄 0cd396d3d).
TRANSLATE_SLICES_SETTING = "ledger_translate_slices"
TRANSLATE_SLICES_MOST = 4
_REFUSED_SETTINGS = set()


def retroactive_debug(settings=None) -> bool:
    """`retroactive_debug`: true or false, absent true - anything else says so once and reads true."""
    import validation
    from ingestion.settings import read_ingestion_settings

    settings = read_ingestion_settings() if settings is None else settings
    value = settings.get(DEBUG_SETTING, True)
    why = validation.flag_refusal(DEBUG_SETTING, value)
    if why is None:
        return value
    if DEBUG_SETTING not in _REFUSED_SETTINGS:
        _REFUSED_SETTINGS.add(DEBUG_SETTING)
        logger.warning("[Retroactive] ingestion_settings.json: %s - read as true", why)
    return True


def slow_statement_seconds(settings=None):
    """`retroactive_slow_statement_seconds`: a positive number; null or 0 none; absent or anything else the default."""
    from ingestion.settings import read_ingestion_settings

    settings = read_ingestion_settings() if settings is None else settings
    value = settings.get(SLOW_STATEMENT_SETTING, SLOW_STATEMENT_DEFAULT)
    if value is None or value == 0:
        return None
    good = isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
    return float(value) if good else SLOW_STATEMENT_DEFAULT


def translate_slices(settings=None):
    """-> `(slices, cores)`: `ledger_translate_slices` - a whole number from 1 to the cores; absent the default, anything
    else says so once and reads the default (총괄 9752e91f7: 64 was 64 processes, 0 · -2 · '8' the default unsaid)."""
    from ingestion.settings import read_ingestion_settings

    cores = os.cpu_count() or 1
    default = min(TRANSLATE_SLICES_MOST, max(1, cores // 2))
    settings = read_ingestion_settings() if settings is None else settings
    value = settings.get(TRANSLATE_SLICES_SETTING, default)
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= cores:
        return value, cores
    if TRANSLATE_SLICES_SETTING not in _REFUSED_SETTINGS:
        _REFUSED_SETTINGS.add(TRANSLATE_SLICES_SETTING)
        logger.warning("[Retroactive] ingestion_settings.json: %s is %r - a whole number from 1 to %d (the cores); "
                       "read as %d", TRANSLATE_SLICES_SETTING, value, cores, default)
    return default, cores


@contextlib.contextmanager
def _beating(control, engine):
    """The run's stage seat (`keyset_scan.RUN_CONTROL`) and its beat on the run's database `engine`, around the run
    (총괄 d9be013cb). 🔴 The run's backends are the connections of `engine` its own thread holds - not its process's:
    a run inside the chain worker named every chain connection its own (총괄 bdc08ec39 ⑦)."""
    from sqlalchemy import event

    from chain import keyset_scan

    here, held = threading.get_ident(), {}

    def taken(dbapi_conn, record, _proxy):
        if threading.get_ident() == here:
            with contextlib.suppress(Exception):
                held[id(record)] = dbapi_conn.get_backend_pid()

    def given_back(_dbapi_conn, record):
        held.pop(id(record), None)

    token = keyset_scan.RUN_CONTROL.set(control)
    stop = threading.Event()
    # pg_stat_activity is PostgreSQL's - another database runs with the stage lines alone
    beat = (threading.Thread(target=_beat, args=(control, stop, engine.url, held), name="retroactive-beat",
                             daemon=True)
            if engine.url.get_backend_name() == "postgresql" else None)
    if beat is not None:
        event.listen(engine, "checkout", taken)
        event.listen(engine, "checkin", given_back)
        beat.start()
    try:
        yield
    finally:
        keyset_scan.RUN_CONTROL.reset(token)  # first - whatever below raises, this thread's run control is not left set
        stop.set()
        control.stop_telling()            # before the run's ending notice - no RUNNING after its DONE (QA 10-14 ④)
        if beat is not None:
            event.remove(engine, "checkout", taken)
            event.remove(engine, "checkin", given_back)
            beat.join(timeout=3 * LOOK_SECONDS)


def _beat_said(control, rows, now):
    """One beat line: the stage the page in progress is in and its seconds, then each busy backend of the run's."""
    stages = list(control.stages)
    where = ("%s %.1f s · %s rows" % (" > ".join(name for name, _since, _rows in stages), now - stages[-1][1],
                                       stages[-1][2] if stages[-1][2] is not None else "-")
             if stages else "between stages")
    import db_waits

    backends = []
    for row in rows:
        shown = dict(row, query=(row["query"] or "")[:BEAT_QUERY_CHARS])
        if row["blocker"] is not None:
            shown["blocker"] = dict(row["blocker"], query=(row["blocker"]["query"] or "")[:BEAT_QUERY_CHARS])
        backends.append("pid %s %s" % (row["pid"], db_waits.wait_sentence(shown)))
    return "[%s] beat: page %d · %s · db: %s" % (
        control.op, control._pages + 1, where,
        " ; ".join(backends) if backends else "no busy backend - the time is in this process")


def _beat(control, stop, url, held):
    """THE BEAT (총괄 d9be013cb, 소유자 「실시간으로 뭐가 돌고 뭘 기다리는지」): every BEAT_SECONDS one line (`_beat_said`);
    every LOOK_SECONDS a look for a statement of the run's `held` backends (`_beating`) past
    `retroactive_slow_statement_seconds` - a line when it
    is seen running, one when it is gone. Asked over a read-only connection of its own (the run's are busy), a
    transaction a look (a snapshot of pg_stat_activity holds for its transaction).
    🔴 SILENT ONLY ABOUT ITSELF: whatever raises here says once what went quiet, and the run goes on."""
    import db_safety
    import db_waits
    from database.database import connection_name

    probe = conn = None
    try:
        app = connection_name()
        probe = db_safety.open_readonly_engine(url, application_name=app + "_probe",
                                               statement_timeout_ms=db_waits.STALL_PROBE_TIMEOUT_MS)
        conn = probe.raw_connection()
        slow, seen, last = slow_statement_seconds(), {}, time.monotonic()
        while not stop.wait(LOOK_SECONDS):
            try:
                rows = db_waits.backend_waits(conn, pids=list(held.values()), chars=SLOW_QUERY_CHARS)
            finally:
                # the DBAPI connection's own transaction: a look inside the last one reads its snapshot again
                conn.rollback()
            now = time.monotonic()
            running = {}
            for row in rows:
                if slow and row["state"] == "active" and (row["query_age"] or 0) >= slow:
                    running[(row["pid"], round(now - row["query_age"]))] = row
            for key, row in running.items():
                if key not in seen:
                    control._log("[%s] slow statement: pid %s running %.1f s (%s): %s" % (
                        control.op, row["pid"], row["query_age"], row["wait"] or "no wait", row["query"]))
                seen[key] = (now, row["query_age"])
            for key in [key for key in seen if key not in running]:
                at, age = seen.pop(key)
                control._log("[%s] slow statement ended: pid %s after about %.1f s" % (
                    control.op, key[0], age + (now - at)))
            if now - last >= BEAT_SECONDS:
                if control.own_beat:
                    control._log(_beat_said(control, rows, now))
                control.tell()
                slow, last = slow_statement_seconds(), now
    except Exception as exc:                               # noqa: BLE001 - the beat's own failure, said below
        control._log("[%s] beat stopped - %s: %s; no more beat or slow-statement lines for this run, the run goes on"
                     % (control.op, type(exc).__name__, told(exc).strip().splitlines()[0] if told(exc).strip() else ""))
    finally:
        for closing in (conn, probe):
            try:
                if closing is not None:
                    closing.close() if closing is conn else closing.dispose()
            except Exception:                              # noqa: BLE001 - closing a probe that broke
                pass


class RunControl:
    """What an operation asks between batches: "should I stop" and "here is where I am".

    🔴 IT USES ITS OWN SESSION, DELIBERATELY, and that is the whole mechanism rather than a
    tidiness choice. The cancel flag is set by a WEB REQUEST in another process, and the
    operation is inside a long transaction of its own; reading the flag on the operation's
    session would read that transaction's snapshot and never see the flag at all. Writing
    progress on the operation's session is the mirror failure - a rollback of the batch
    would erase the record of how far the run had got, exactly when a reader needs it most.

    🔴 STOPPING IS COOPERATIVE AND THAT IS WHY IT IS SAFE. Every operation this wraps
    commits per page and declares itself restartable, so a stop BETWEEN batches leaves
    committed work and a resumable position - never a half-written batch. Killing the
    process is what this exists to replace: the owner's report is that a heavy backfill
    could only be stopped by restarting the server, which takes every other job with it.
    """

    def __init__(self, run_id, session_factory=None, op=None, log=None, report=None):
        self.run_id = run_id
        #: A slice's (`run_slice`): where its count goes - the run row's is the slices' sum, written by the run's process.
        self.report = report
        #: False while the run's slices beat for it (`_rescope_in_slices`) - this process has no page of its own then.
        self.own_beat = True
        #: [S-37] 진행을 «말하려면» 무엇의 진행인지가 있어야 한다. run_id 만으로는
        #: 화면이 「무슨 일이 도는가」를 못 말한다 — S-36 이 대기열에서 고친 그 부족이다.
        self.op = op
        self.stopped = False
        #: False after a notice nobody heard (`announce`) - the rest of this run says nothing more.
        self.announcing = True
        #: The operation's own answer, unreduced - what a CLI prints (`_final_progress`).
        self.stats = None
        self._session_factory = session_factory
        #: When the progress time last moved, on this process's clock - a step's seconds start here.
        self._moved = time.monotonic()
        #: The run's own log (`log` of `execute` / `run_here`) - a step line goes where the run's lines go.
        self._log = log or logger.info
        #: The last page boundary's count, clock and number - what the page line (`_page_line`) measures from - and the
        #: run's start, whose rate the time left is told by (a page's own rate swings on a one-row page).
        self._said, self._boundary, self._pages = 0, time.monotonic(), 0
        self._began, self._total = self._boundary, None
        #: The stages the page in progress is inside, outermost first - `(name, since, rows)` (`stage`, the beat reads it).
        self.stages = []
        #: The stage lines on or off - `retroactive_debug`, read again at every page boundary.
        self.debug = retroactive_debug()
        #: The run's last line before its pages and since when - what `tell` says while no stage is open.
        self._phase = ("Starting", self._began)
        #: False once telling failed - said once, the run goes on - or the run's beat ended (`tell`, `stop_telling`).
        self.telling = True
        self._told = threading.Lock()

    def _session(self):
        if self._session_factory is not None:
            return self._session_factory()
        from database.database import SessionLocal
        return SessionLocal()

    def stop_requested(self) -> bool:
        """True once somebody has asked this run to stop. Cheap: one indexed read.

        Sticky on purpose - once it has answered True it keeps answering True without
        asking again, so an operation that checks in several places cannot get a False
        after a True and carry on.
        """
        if self.stopped:
            return True
        if not self.run_id:
            return False
        from database import models

        session = self._session()
        try:
            state = (session.query(models.RetroactiveRun.state)
                     .filter(models.RetroactiveRun.run_id == self.run_id).scalar())
        except Exception as exc:                   # noqa: BLE001
            # A failure to ASK is not an answer of "stop". Refusing to stop here is the
            # safe direction: the work continues and is restartable either way, whereas a
            # stop invented by a broken query would look to the operator like a cancel
            # they never requested.
            logger.debug("cancel check failed for run_id=%s: %s", self.run_id, told(exc), exc_info=exc)
            return False
        finally:
            session.close()
        self.stopped = state == RUN_CANCEL_REQUESTED
        return self.stopped

    def progress(self, processed=None, total=None, note=None) -> None:
        """Record how far this run has got. `total=None` stays NULL - unknown, not zero. `note` ends the page line."""
        self._page_line(processed, total, note)
        self._phase = (note or "Page %d done" % self._pages, time.monotonic())      # the stage until the next (`tell`)
        self.debug = retroactive_debug()
        if self.report is not None:
            if processed is not None:                  # a step that only asks to go on moves no slice's count
                self.report(processed)
            self._moved = time.monotonic()
            return
        if not self.run_id:
            return
        values = {}
        if processed is not None:
            values["processed_rows"] = int(processed)
        if total is not None:
            values["total_rows"] = int(total)
        self._stamp(values)
        # [S-37] 쓰는 «자리 옆»에서 한 번 더 말한다. 여기가 아니면 「DB 는 갱신됐는데
        # 아무도 못 들었다」가 다시 생긴다 — 그 둘이 갈라지는 것이 이 라운드의 결함이다.
        import event_constants
        self.announce(event_constants.PROGRESS_STATUS_RUNNING, processed=processed, total=total)
        self._moved = time.monotonic()      # the next step's seconds leave out this boundary's notice

    def _page_line(self, processed, total, note=None) -> None:
        """THE PAGE LINE (소유자 10-12 「모든 소급은 5 초에 한 번은 진행 상황이 보이게」): at each page boundary that moved
        the count, `[<op>] page k: <rows> rows · <seconds> s · <rows/s> rows/s · <done> / <total> · ~<left> left[ · note]`
        - the total and the time left only when the op counted its rows."""
        # the total once told holds for the run's later lines (the op's headline at its end comes without it)
        total = self._total = total if total is not None else self._total
        if processed is None or processed == self._said:
            return
        now = time.monotonic()
        if processed < self._said:
            # another count began - a later step's (from 0 again) or the op's headline at its end: lines go on from it
            self._said, self._boundary = processed, now
            return
        rows, seconds = processed - self._said, now - self._boundary
        rate = rows / seconds if seconds > 0 else 0
        self._pages += 1
        done = ("%d done" % processed if not total else "%d / %d · ~%s left" % (
            processed, total, _clock(pace(processed, total, now - self._began)[1] or 0)))
        self._log("[%s] page %d: %d rows · %.1f s · %d rows/s · %s%s" % (
            self.op, self._pages, rows, seconds, rate, done, " · %s" % note if note else ""))
        self._said, self._boundary = processed, now

    def step(self, name, page, pages, rows, seconds=None, note=None) -> None:
        """A step of page `page` (of `pages`, None = unknown) returned (총괄 e71f7d6f1, 소유자 「죄다 stalled」 ·
        「깜깜이」): one line `[<op>] page k/K: <step> · <rows> rows · <seconds> s[ · <note>]`, then the progress time -
        no count, no notice, no stop (a stop is safe only at the page boundary). Called by the op's own thread
        when the step returns, never from a timer: a step that does not return - a lock wait - leaves the
        time where it was, and `in_flight` reads it stalled. `seconds`: the step's own (a `stage`), else since
        the last line."""
        seconds = time.monotonic() - self._moved if seconds is None else seconds
        self._step_line(name, page if not pages else "%d/%d" % (page, pages), rows, seconds, note)
        if self.run_id:
            self._stamp({})
        self._moved = time.monotonic()

    def _step_line(self, name, page, rows, seconds, note):
        self._log("[%s] page %s: %s · %s rows · %.2f s%s" % (
            self.op, page, name, rows, seconds, " · %s" % note if note else ""))

    def say(self, sentence) -> None:
        """One line of this run's own - `[<op>] <sentence>` - on or off, whatever `debug` says. It is the run's stage
        (`tell`) until the next line or a stage of a page."""
        self._log("[%s] %s" % (self.op, sentence))
        self._phase = (sentence, time.monotonic())

    def tell(self) -> None:
        """THE RUN'S STAGE, TOLD (총괄 10-14, 소유자 «러닝은 뜨는데 토스트 진행 상황이 안 나옴»), every beat: the stage of the
        page in progress, or the run's last line before its pages, and its seconds - on the run record (phase · phase_at,
        not the progress time: a stage that does not end must still read as stalled) and in the progress notice with
        rows a second and the time left (`pace`). 🔴 Silent only about itself: a failure is said once, the run goes on."""
        if not self.run_id or self.report is not None:
            return                                    # a slice: the run's process tells the run's stage
        with self._told:                              # one at a time, and none once `stop_telling` returned
            if not self.telling:
                return
            now = time.monotonic()
            if self.stages:
                name, since, _rows = self.stages[-1]
                phase = "Page %d: %s" % (self._pages + 1, name)
            else:
                phase, since = self._phase
            from datetime import datetime, timedelta, timezone

            from sqlalchemy import text

            from database import models

            session = self._session()
            try:
                models.ensure_run_columns(session.get_bind())
                session.execute(text("UPDATE retroactive_runs SET phase = :phase, phase_at = :at WHERE run_id = :run"),
                                {"phase": phase[:200], "run": self.run_id,
                                 "at": datetime.now(timezone.utc) - timedelta(seconds=now - since)})
                session.commit()
            except Exception as exc:                                    # noqa: BLE001 - said once below
                session.rollback()
                self.telling = False
                logger.warning("[Retroactive] run_id=%s: its stage could not be written - none more for this run: %s",
                               self.run_id, told(exc), exc_info=exc)
                return
            finally:
                session.close()
            rate, left = pace(self._said, self._total, now - self._began)
            import event_constants
            self.announce(event_constants.PROGRESS_STATUS_RUNNING, processed=self._said, total=self._total,
                          phase=phase, phase_seconds=round(now - since), rows_per_second=rate and round(rate, 1),
                          seconds_left=left and round(left))

    def stop_telling(self) -> None:
        """No stage told after this returns - one in flight finishes first (its notice before the run's ending one)."""
        with self._told:
            self.telling = False

    @contextlib.contextmanager
    def stage(self, name, rows=None):
        """A stage inside the page in progress (`keyset_scan.stage`, 총괄 d9be013cb): in `stages` while it runs - the
        beat says the innermost and how long it has run - and its step line when it ends, while `debug` is on: a
        line only - the run row's time moves once a page, at its boundary (총괄 bdc08ec39 ③: it was an UPDATE and a
        COMMIT a stage, 14 a page). Yields a dict: a `note` ends the line, a `rows` there replaces the one given."""
        entry = (name, time.monotonic(), rows)
        self.stages.append(entry)
        said = {}
        try:
            yield said
        finally:
            if entry in self.stages:
                self.stages.remove(entry)
            if self.debug:
                self._step_line(name, self._pages + 1, said.get("rows", rows), time.monotonic() - entry[1],
                                said.get("note"))

    def _stamp(self, values) -> None:
        """`last_progress_at` = now, with `values`, on this control's own session."""
        from datetime import datetime, timezone

        from database import models

        session = self._session()
        try:
            values = dict(values, last_progress_at=datetime.now(timezone.utc))
            (session.query(models.RetroactiveRun)
             .filter(models.RetroactiveRun.run_id == self.run_id).update(values))
            session.commit()
        except Exception as exc:                   # noqa: BLE001
            # Progress is a report, never the work. A run must not fail because its
            # bookkeeping did.
            session.rollback()
            logger.debug("progress write failed for run_id=%s: %s", self.run_id, told(exc), exc_info=exc)
        finally:
            session.close()

    def announce(self, status, processed=None, total=None, **told) -> None:
        """`announce_progress` for this run, until one is not heard (총괄 10-11 ④: with the server down each notice
        waited ~2 s on this box - a page's worth of work, every page). One line then; the run record still says it.
        `told`: the stage and its pace (`tell`)."""
        if not self.run_id or not self.announcing:
            return
        if not announce_progress(self.run_id, self.op, status, processed=processed, total=total, **told):
            self.announcing = False
            logger.warning("[Retroactive] run_id=%s op=%s: a progress notice was not heard - none more for this "
                           "run; the Retroactive tab reads the run record", self.run_id, self.op)


def _utc(dt):
    """A time the database gave - an aware one as it is, a naive one (SQLite) as UTC; None stays None."""
    from datetime import timezone

    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))


def pace(processed, total, seconds):
    """-> `(rows a second, seconds left)` of a run `seconds` in that has done `processed` of `total` - None where it is
    not known. The page line's time left and the stage notice's and runs list's two values: one calculation."""
    if not processed or not seconds or seconds <= 0:
        return None, None
    rate = processed / seconds
    return rate, (max(total - processed, 0) / rate if total else None)


def _clock(seconds):
    """`42 s` · `7 min` · `3.1 h` - a page line's time left."""
    return "%d s" % seconds if seconds < 120 else "%d min" % (seconds / 60) if seconds < 7200 else "%.1f h" % (seconds / 3600)


def announce_progress(run_id, op, status, processed=None, total=None, **told):
    """소급 실행의 진행을 «인제션과 같은 봉투·같은 길»로 낸다 (S-37, 판정 98).

    🔴 왜 있나: 진행은 오늘 `retroactive_runs` 에 «DB 로만» 적히고, 그리드 화면은 발신이
       «0** 이라 아무것도 못 듣는다. 관리 화면만 폴링으로 본다. 결함 부류는 「발신 없음」이고,
       고칠 것은 «쓰는 자리 옆»에서 한 번 더 말하는 것뿐이다.
    ⚠️ 실패해도 «일을 실패시키지 않는다** — 진행은 보고이지 작업이 아니다. 그 규율은 바로
       위 `RunControl.progress` 가 DB 쓰기에 대해 이미 세운 것과 같다.
    """
    if not run_id:
        return False
    try:
        import event_constants
        import internal_event_client
        payload = event_constants.progress_event(
            status, processed_rows=processed, total_rows=total,
            progress=(None if not total or processed is None else int(processed * 100 / total)),
            run_id=run_id, op=op, **told)
        # 길·헤더·판별자는 `internal_event_client` 가 짓는다 — 이 프로세스가 «셋째 철자»를
        # 만들지 않는 것이 판정 98 의 요지다.
        _url, res, note = internal_event_client.send_internal_event(
            internal_event_client.api_base_url(),
            "/internal/events/broadcast", payload, timeout=3)
        if not res.ok:
            suffix = " | %s" % note if note else ""
            logger.error("[Retroactive] progress notification failed: %s -> %s%s",
                         _url, res.status_code, suffix)
            return False
        return True
    except Exception as exc:                       # noqa: BLE001
        logger.debug("progress notification failed for run_id=%s: %s", run_id, error_said.told(exc), exc_info=exc)
        return False


def request_cancel(db, run_id: str) -> dict:
    """Ask a run to stop - or RELEASE it when there is nobody left to ask.

    🔴 [소유자 2026-09-23 「캔슬 보냈는데도 계속 뜸」] CANCEL MEANS 「tell the operation to
       stop」, and the operation stops itself between batches by reading this value. When
       the process that started it is GONE that value is never read: the row moves
       `running` -> `cancel_requested`, both of which are `IN_FLIGHT_STATES`, so the gate
       stays shut forever and every queued replay behind it never starts. The operator's
       only remaining way out was SQL, which is what 소유자 had to be handed.

    ⚠️ SO THIS IS THE SAME DOOR, NOT A SECOND ONE. What was missing was the answer to
       「what does 「stop」 mean when nobody is listening」, and `_runner_state` already
       answers whether anyone is - by the HEARTBEAT, so it asks 「is that process alive」
       and not 「is this run progressing」. That difference is the whole safety of this:
       two operations (ledger_rescope, enrichment_confirm) report no progress at all while
       running perfectly, and a release keyed on progress would kill them.

    ⛔ `unknown` IS NOT RELEASED (총괄 판정 2026-09-23 ②). A row with no runner stamp
       predates the column, and 「probably a ghost」 is a guess. 「모르면 안 한다」.
    """
    from database import models

    row = (db.query(models.RetroactiveRun)
           .filter(models.RetroactiveRun.run_id == run_id).first())
    if row is None:
        raise RetroactiveRefused(f"unknown run_id '{run_id}'")
    op, runner = row.op, row.runner
    # 🔴 A FINISHED RUN IS ANSWERED BY ITS STATE, NOT REFUSED (총괄 e2b5b6f35). A replay is `done`
    #    while the events it staged still wait, and the refusal ended the stop there. Nothing is
    #    written: `done` stays `done` - a finished run never reads as cancelled.
    if row.state in (RUN_DONE, RUN_CANCELLED, RUN_FAILED):
        return {"run_id": run_id, "op": op, "state": row.state, "released": False}
    # 🔴 A QUEUED RUN HAS NOBODY TO ASK (총괄 10-08). `cancel_requested` is read only by a
    #    runner, and it is an IN_FLIGHT state - on a run that never started it closed the gate for
    #    ever and every run behind it waited for SQL. So it ends now, `cancelled`, if it is still
    #    queued; one a daemon took in between goes on to the running answer below.
    if row.state == RUN_QUEUED and _mark_run(run_id, state=RUN_CANCELLED, finished=True,
                                             expect_state=RUN_QUEUED):
        db.expire_all()
        logger.info("[Retroactive] cancelled run_id=%s op=%s before it started", run_id, op)
        moved = (db.query(models.RetroactiveRun)
                 .filter(models.RetroactiveRun.run_id == run_id).first())
        return {"run_id": run_id, "op": op,
                "state": moved.state if moved else None, "released": True}
    if _runner_state(runner) == "orphaned":
        # 🔴 `failed`, NOT `cancelled` (총괄 판정 ①). Nobody stopped it - the process
        #    died - and its work did not finish and never will. `cancelled` would tell the
        #    operator they stopped it themselves, which is not true, and it is the word a
        #    hand-written UPDATE would have to disagree with.
        # ⚠️ NEVER SILENTLY. The reason rides on the row, because an automatic release
        #    that leaves no trace is the option this one was chosen INSTEAD of.
        from datetime import datetime, timezone

        why = ("released as a ghost lock: the runner that started it is not alive "
               "(runner=%s; judged against the heartbeat at %s). Its work did not "
               "finish - run it again." % (runner or "?",
                                           datetime.now(timezone.utc).isoformat()))
        _mark_run(run_id, state=RUN_FAILED, finished=True, error=why)
        db.expire_all()
        logger.warning("[Retroactive] released a ghost lock run_id=%s op=%s runner=%s",
                       run_id, op, runner)
        # 🔴 READ BACK, NEVER RESTATED. `_mark_run` writes the state on its own session,
        #    and a constant here would be a SECOND author of it: the answer would keep
        #    saying `failed` however that write actually landed. Measured - a mutation
        #    that wrote `cancelled` left this reply unchanged and no gate noticed.
        moved = (db.query(models.RetroactiveRun)
                 .filter(models.RetroactiveRun.run_id == run_id).first())
        return {"run_id": run_id, "op": op,
                "state": moved.state if moved else None, "released": True}

    row.state = RUN_CANCEL_REQUESTED
    db.commit()
    logger.info("[Retroactive] cancel requested run_id=%s op=%s", run_id, op)
    return {"run_id": run_id, "op": op, "state": row.state, "released": False}


def _stages_of(db, run_ids):
    """-> {run_id: (phase, phase_at)} of these runs (`RunControl.tell`), read once on a connection of its own; {} on a
    database the columns are not on yet (QA 10-14 ②: the list never adds them - their writer does - nor waits)."""
    if not run_ids:
        return {}
    from sqlalchemy import bindparam, text

    try:
        with db.get_bind().connect() as conn:
            found = conn.execute(text("SELECT run_id, phase, phase_at FROM retroactive_runs WHERE run_id IN :ids")
                                 .bindparams(bindparam("ids", expanding=True)), {"ids": list(run_ids)}).all()
    except Exception as exc:                                            # noqa: BLE001 - the list goes on, stageless
        logger.debug("[Retroactive] run stages not read: %s", told(exc), exc_info=exc)
        return {}
    from datetime import datetime

    # a raw read on SQLite hands the time back as text
    return {run_id: (phase, datetime.fromisoformat(at) if isinstance(at, str) else at) for run_id, phase, at in found}


def runs(db, limit: int = 50) -> list:
    """The recent runs, newest first. One list for every request-type operation.

    ⚠️ File ingestion is NOT here and must not be moved here: it keeps its own row per file
    in `file_ingestion_checkpoints` with total/processed/chunk already on it. A screen reads
    that table directly.
    """
    from datetime import datetime, timezone

    from database import models

    rows = (db.query(models.RetroactiveRun)
            .order_by(models.RetroactiveRun.queued_at.desc())
            .limit(max(1, min(int(limit or 50), 500))).all())
    now = datetime.now(timezone.utc)
    stages = _stages_of(db, [row.run_id for row in rows if row.state in IN_FLIGHT_STATES])

    def told(row):
        """A run in flight's stage and pace (`RunControl.tell`, `pace`) - null otherwise, and null where unknown."""
        if row.state not in IN_FLIGHT_STATES:
            return {"phase": None, "phase_seconds": None, "rows_per_second": None, "seconds_left": None}
        rate, left = pace(row.processed_rows, row.total_rows,
                          row.started_at and (now - _utc(row.started_at)).total_seconds())
        phase, phase_at = stages.get(row.run_id, (None, None))
        return {"phase": phase,
                "phase_seconds": phase_at and round((now - _utc(phase_at)).total_seconds()),
                "rows_per_second": rate and round(rate, 1), "seconds_left": left and round(left)}
    listed = [{
        "run_id": row.run_id,
        # 🔴 화면이 `result` 를 «해석하지 않습니다». 연산마다 키가 다르고
        #    선언이 그 모양을 안 고정하므로, 「이 수를 이 이름으로」를 화면이
        #    정하면 그것이 계약을 «지어내는» 것입니다 (총괄 판정 33).
        "result_sentence": run_result_sentence(row.result),
        "op": row.op,
        # An operation no longer registered is retired - its old runs still list, by name (총괄 a4d135a06).
        "label": (OPERATIONS.get(row.op) or {}).get("label") or "%s (retired)" % row.op,
        "params": json.loads(row.params) if row.params else {},
        "requested_by": row.requested_by,
        "state": row.state,
        "processed_rows": row.processed_rows,
        # NULL travels as null, never as 0: "unknown" and "none" are different answers.
        "total_rows": row.total_rows,
        "result": json.loads(row.result) if row.result else None,
        "error": row.error,
        "queued_at": row.queued_at.isoformat() if row.queued_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "last_progress_at": (row.last_progress_at.isoformat()
                             if row.last_progress_at else None),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        **told(row),
    } for row in rows]
    # Where a run picks up next, from the operation that knows (총괄 3a1446982) - null for an
    # operation with no such idea, and for a run still going.
    for run in listed:
        next_start = (OPERATIONS.get(run["op"]) or {}).get("next_start")
        run["next_start"] = next_start(run) if next_start else None
    return listed


def operation(op: str) -> dict:
    spec = OPERATIONS.get(op)
    if spec is None:
        raise RetroactiveRefused(
            f"unknown retroactive operation '{op}'; available: "
            f"{', '.join(sorted(OPERATIONS))}")
    return spec


#: What a run's writes do to the chain - true of every operation, because they all run through
#: `_run_to_the_end`'s retroactive channel (소유자 09-26, 총괄 c2995cdd8). An operation whose
#: writes happen somewhere else says its own sentence (`downstream_note` in its spec).
DOWNSTREAM_NOTE = ("Downstream chain rules are not triggered by a retroactive run - run them "
                   "too if they read what this changed")


def inventory() -> list:
    """The operations, their parameters, and where the CLI equivalent is.

    Config only - no DB query, so it has `GET /admin/config/resolve`'s posture and
    can sit on any request path. The CLI line is carried deliberately: the buttons
    cover the common shape of each operation and the CLI still covers the rest
    (`--limit`, `--force-disabled`, `--label`, `replay-all`, per-column withdrawal).
    """
    return [
        {"op": op, "label": s["label"], "what_is_missing": s["what_is_missing"],
         "downstream_note": s.get("downstream_note", DOWNSTREAM_NOTE),
         "params": [dict(p, choices=_resolved_choices(p)) for p in s["params"] if p["form"]],
         "cli": s["cli"], "cli_only": s["cli_only"],
         "deletes": s["deletes"], "restartable": s["restartable"],
         "cancellable": s["cancellable"], "reads_as": s["reads_as"],
         "commit_granularity": s["commit_granularity"]}
        for op, s in sorted(OPERATIONS.items())
    ]


# ---------------------------------------------------------------------------
# Validation - the ONE place a parameter set is judged, so the route and the
# worker cannot disagree about what a valid request is.
# ---------------------------------------------------------------------------

def validate(op: str, params: dict) -> dict:
    """-> the normalized parameter dict, or raise `RetroactiveRefused`."""
    spec = operation(op)
    params = params or {}
    known = {p["name"] for p in spec["params"]}
    unknown = sorted(set(params) - known)
    if unknown:
        raise RetroactiveRefused(
            f"unknown parameter(s) for '{op}': {unknown}; accepted: {sorted(known)}")

    out = {}
    for p in spec["params"]:
        raw = params.get(p["name"])
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if p["required"]:
                raise RetroactiveRefused(
                    f"'{op}' requires parameter '{p['name']}' ({p['help'] or p['type']})")
            continue
        if p["type"] == "csv":
            value = [c.strip() for c in str(raw).split(",") if c.strip()] \
                if isinstance(raw, str) else [str(c).strip() for c in raw if str(c).strip()]
            if not value:
                continue
        elif p["type"] == "int":
            try:
                value = int(str(raw).strip())
            except ValueError:
                raise RetroactiveRefused(
                    f"'{op}' parameter '{p['name']}' must be a whole number; got {raw!r}")
        elif p["type"] == "bool":
            from database import crud

            try:
                value = crud.boolean_text_read(raw, p["name"])
            except ValueError as refused:
                raise RetroactiveRefused(f"'{op}' parameter {refused}") from None
        else:
            value = str(raw).strip()
        out[p["name"]] = value

    for p in spec["params"]:
        allowed = _resolved_choices(p)
        if allowed is None or p["name"] not in out:
            continue
        legal = {str(c["value"]) for c in allowed if isinstance(c, dict)} or {
            str(c) for c in allowed}
        if str(out[p["name"]]) not in legal:
            # Convenience, like the withdraw check below: the operation refuses this again
            # where the value is actually used, and THAT one is the safety property. This
            # one just turns a job that dies in a worker log into a 400 the operator sees.
            raise RetroactiveRefused(
                f"'{op}' parameter '{p['name']}' must be one of "
                f"{sorted(legal)}; got {out[p['name']]!r}")

    # The operation's own judgment, so the operator gets a 400 instead of a queued job that
    # dies in a worker log - and the publish, the count and a CLI get one answer.
    if spec["judge"] is not None:
        spec["judge"](out)
    return out


# ---------------------------------------------------------------------------
# Count (read-only) and publish (the trigger)
# ---------------------------------------------------------------------------

def clamp_scan_limit(limit) -> int:
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_SCAN_LIMIT
    return max(1, min(limit or DEFAULT_SCAN_LIMIT, MAX_SCAN_LIMIT))


def count(db, op: str, params: dict, scan_limit: int = DEFAULT_SCAN_LIMIT) -> dict:
    """Read-only. Never writes, and rolls back structurally on the way out.

    The per-operation dry-runs already roll back themselves; the rollback here is
    the belt to their braces and covers the cheap-query operations too, so "a count
    route never writes" is a property of this function rather than of five callees.
    """
    spec = operation(op)
    params = validate(op, params)
    scan_limit = clamp_scan_limit(scan_limit)
    try:
        out = spec["count"](db, params, scan_limit)
    finally:
        db.rollback()
    out.setdefault("blocked_reason", None)
    # Present on every count, so "this number means what it says" is an ANSWER rather
    # than a count that forgot to choose.
    out.setdefault("absence", None)
    # NOTE: `scan_limit` is set by the count function, NOT here. Two of the five do
    # not scan rows at all and report null; overwriting that with the requested
    # budget would tell a reader a sample was taken when none was.
    out.setdefault("scan_limit", None)
    out.update({"op": op, "mode": "dry-run", "params": params,
                "label": spec["label"], "cli": spec["cli"],
                "deletes": spec["deletes"], "restartable": spec["restartable"],
                "cancellable": spec["cancellable"],
                "reads_as": spec["reads_as"],
                "commit_granularity": spec["commit_granularity"]})
    return out


def publish(db, op: str, params: dict, requested_by: str = None, run_id: str = None) -> dict:
    """Queue the run and return. Does NOT execute anything.

    Same mechanism as `POST /admin/auto-update/run-now`: one `DatabaseOutbox` row.
    The NOTIFY that wakes the consumer is NOT issued here any more - staging the row
    is what announces it (`database.notify_on_outbox_change`, 2026-09-22). This used
    to spell the NOTIFY by hand, and three other sites that did not spell it were
    silent for exactly that reason. A retroactive
    run walks a whole table, so a synchronous handler would hold the request until
    the browser gave up - and would hold a web-server worker while doing it.
    """

    from database import models

    spec = operation(op)
    params = validate(op, params)
    # `run_id` given: a caller that names the run in the same commit (`chain.replay.resume_run`)
    run_id = run_id or uuid.uuid4().hex[:12]
    # 🔴 NO INVENTED AUTHOR. "admin" is a word that reads like a person, and writing it
    # ANSWERS "who asked for this" with something nobody said. The column is nullable;
    # absent stays absent, and the screen decides how to show that.
    # ⚠️ Rows already carrying "admin" are left alone - correcting them would be editing
    # the record itself. Only what is written from here changes.
    payload = {"run_id": run_id, "op": op, "params": params,
               "requested_by": requested_by or None}

    # 🔴 [소유자 2026-09-23] 「스케줄러 쓰지 말라했는데 스케줄러가 왜 나와?」 - AND THIS ROW IS
    #    WHERE THAT LINE CAME FROM. Measured: for `chain_replay` the row was picked up by
    #    `run_auto_update` (:858, which filters by TYPE and never asks `outbox_owner`), which
    #    logged 「op=chain_replay is the chain worker's」, marked it processed and did nothing
    #    else. The work has never been in this row - it is in the `RetroactiveRun` row below,
    #    and `ingestion_worker.start_replay_if_queued` SWEEPS that table every 2 s precisely
    #    so a missed wake-up cannot kill a job (its own docstring: 「초인종에만 기대면 놓친
    #    초인종이 일을 «죽인다»」). So for this op the row's only effect was to put the
    #    scheduler's name on a screen the owner was reading.
    # ⚠️ THE OTHER OPS STILL GET IT. They ARE the scheduler's, and `start_retroactive_run`
    #    is what the row wakes - dropping it for them would leave those runs queued until the
    #    next restart. The axis is 「who empties this」, and `outbox_owner` is where it is
    #    already declared; this asks it rather than spelling a second answer.
    if event_constants.outbox_owner(RUN_EVENT_TYPE, op) != event_constants.OUTBOX_OWNER_CHAIN:
        db.add(models.DatabaseOutbox(
            event_uuid=str(uuid.uuid4()),
            table_name=RUN_EVENT_TABLE,
            event_type=RUN_EVENT_TYPE,
            # An object, not a JSON string, so the queue's SQL reads its `run_id` and folds it
            # into its run's line (총괄 b3a4334db). Both readers take either shape.
            payload=payload,
            processed_chain=False,
        ))
    # 🔴 THE SAME COMMIT AS THE OUTBOX ROW. A queued event with no run row is a job nobody
    # can see or cancel; a run row with no event is a job that never starts and sits at
    # `queued` forever. Either half alone is worse than neither.
    db.add(models.RetroactiveRun(
        run_id=run_id, op=op,
        params=json.dumps(params, ensure_ascii=False),
        requested_by=requested_by or None,
        state=RUN_QUEUED,
    ))
    db.commit()
    logger.info(f"[Retroactive] queued run_id={run_id} op={op} params={params}")
    return {"status": "queued", "run_id": run_id, "op": op, "params": params,
            "label": spec["label"]}


# ---------------------------------------------------------------------------
# The worker side
# ---------------------------------------------------------------------------


def gate_refusal(db):
    """게이트가 닫혀 있으면 «운영자가 읽고 풀 수 있는» 한 줄, 열려 있으면 `None`.

    🔴 저자가 «하나»여야 하는 이유. 이 판단(「지금 소급을 하나 더 시작해도 되나」)을 데몬이
       둘 묻게 됐다 — 스케줄러(회수·원장)와 체인 워커(리플레이). 사본을 두면 한쪽이 게이트를
       넓혀도 다른 쪽은 모르고, 그때 둘이 같은 표의 같은 셀을 «두 세션»에서 쓴다.
       그것이 이 게이트가 애초에 막으라고 쓰인 경우다.

    ⚠️ «판단»은 여기 하나이고, 「루프에서 어떻게 빠져나가나」는 데몬마다 다르다 —
       스케줄러는 `threading.Thread`, 워커는 asyncio 태스크다. 그건 사본이 아니라
       프로세스가 가진 «도구가 다른» 것이라 각자 자리에 남는다.

    ⚠️ 거절은 «사유»와 «다음 행동»을 둘 다 든다. 게이트가 프로세스를 건너므로 막은 실행이
       읽는 쪽 프로세스에 «없을 수» 있고, 그러면 「여기서 뭐가 도나」로는 아무것도 안 나온다.
    """
    blocking = in_flight(db)
    if not blocking:
        return _replay_still_waiting(db)
    # 🔴 「취소해라」만으로는 «그 취소가 안전한지»를 못 읽는다 (소유자 2026-09-23
    #    「qued replay waiting ~~~ 계속 뜨는데 어케함」). runner 가 살아 있으면 취소는 «도는
    #    일»을 끊는 것이고, 죽었으면 취소가 이 자물쇠를 «푸는» 유일한 길이다 — 판단이
    #    정반대인데 문장이 같았다. 생사는 `_runner_state` 가 이미 답한다(심박).
    run_id, op = blocking["run_id"], blocking["op"]
    owner = _runner_state(blocking.get("runner"))
    where = "POST /admin/retroactive/runs/%s/cancel" % run_id
    if owner == "orphaned":
        return ("run_id=%s op=%s is held by runner=%s, and that process is NOT alive — "
                "cancelling RELEASES this lock (the run is marked failed, not cancelled: "
                "its work did not finish). %s"
                % (run_id, op, blocking.get("runner"), where))
    if owner == "unknown":
        return ("run_id=%s op=%s is held by runner=%s, and whether that process is alive "
                "CANNOT BE JUDGED from here (a row written before runs carried a runner "
                "stamp). Cancelling asks it to stop; it cannot release the lock. %s"
                % (run_id, op, blocking.get("runner"), where))
    # The seconds are SINCE THE LAST PROGRESS - 「progressing for 0.0s」 read as a run that
    # had just started (총괄 d34247b3d ㉡).
    last = ("no progress reported yet" if blocking["moving"] == MOVING_UNREPORTED
            else "last progress %ss ago" % blocking.get("no_progress_seconds"))
    return ("run_id=%s op=%s is %s, %s (runner=%s is alive — cancelling stops work that "
            "is actually running) — %s"
            % (run_id, op, blocking["moving"], last, blocking.get("runner"), where))


def _replay_still_waiting(db):
    """A replay run is `done` once it has staged its pages, while the chain still runs them (C 간섭 ②, 총괄
    1ff4dcc6c): the gate stays closed until they have run - every retroactive run waits, whatever table it writes.
    -> the sentence, or None. Reads the waiting rows only (`idx_outbox_unprocessed`)."""
    from sqlalchemy import func

    from database import models

    outbox = models.DatabaseOutbox
    run_of = outbox.payload[event_constants.RUN_KEY].as_string()
    waiting = (db.query(run_of, func.count(), func.min(outbox.table_name))
               .filter(outbox.processed_chain == False,                       # noqa: E712 - the index's spelling
                       outbox.payload[event_constants.REPLAY_KEY].as_boolean() == True,  # noqa: E712
                       run_of.isnot(None))
               .group_by(run_of).order_by(func.min(outbox.id)).first())
    if waiting is None:
        return None
    run_id, events, table = waiting
    return ("run_id=%s chain_replay has staged its pages, and %d of its event(s) on %s still wait in the chain "
            "queue - every retroactive run, on any table, waits until they have run. × on that queue line stops them "
            "(POST /admin/chain/queue/cancel {\"key\": \"%s\"})" % (run_id, events, table, run_id))


#: The lock every claim takes (총괄 f453968fe ⓒ). Checking the gate and writing the running
#: row were two steps, so two claimers in two processes could both pass the check.
GATE_LOCK_NAME = "retroactive_gate"


def claim(op=None, params=None, run_id=None, beat_as=None):
    """Check the gate and take it by writing the row - one transaction, one lock.

    `run_id` given: that queued row becomes running (a daemon's claim). None: a new row is
    written running (`run_here`). `beat_as` beats that heartbeat AFTER the gate passes and
    before the stamp - a refused caller must not overwrite the running one's heartbeat.
    The daemons' own `gate_refusal` calls before this are readers for their log line; the
    only check followed by a write is here.

    :return: the run_id; `None` when the queued row is no longer queued (taken, cancelled,
        finished) - nothing to claim. A run_id with no row at all is a hand call and wins.
    :raises RetroactiveRefused: the gate is closed - its own sentence.
    """
    from datetime import datetime, timezone

    from sqlalchemy import text

    from database import models
    from database.database import SessionLocal

    session = SessionLocal()
    try:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:name))"),
                            {"name": GATE_LOCK_NAME})
        refusal = gate_refusal(session)
        if refusal:
            raise RetroactiveRefused(refusal)
        if beat_as:
            from utils import heartbeat
            heartbeat.beat(beat_as, force=True)
        now = datetime.now(timezone.utc)
        stamp = {"state": RUN_RUNNING, "started_at": now, "last_progress_at": now,
                 "runner": runner_identity()}
        if run_id is None:
            run_id = uuid.uuid4().hex[:12]
            session.add(models.RetroactiveRun(
                run_id=run_id, op=op, params=json.dumps(params or {}, ensure_ascii=False),
                requested_by=os_user(), **stamp))
        elif not (session.query(models.RetroactiveRun)
                  .filter(models.RetroactiveRun.run_id == run_id,
                          models.RetroactiveRun.state == RUN_QUEUED)
                  .update(stamp, synchronize_session=False)):
            exists = (session.query(models.RetroactiveRun.run_id)
                      .filter(models.RetroactiveRun.run_id == run_id).first())
            session.rollback()
            return None if exists else run_id
        session.commit()
        return run_id
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def next_queued(db, op):
    """그 op 의 «가장 오래 기다린» queued 실행의 payload, 없으면 `None`. 집지는 «않는다».

    ⛔ 여기서 집지 않는 것이 의도다. 집는 자리는 `execute` «하나»이고(거기 조건부 전이와
       게이트 ⑭ 가 붙어 있다), 여기서 한 번 더 집으면 집는 자리가 둘이 되어 `execute` 는
       「이미 running」을 보고 «자기 일을 건너뛴다». 찾기와 집기를 나눠 두면 둘이 같은 행을
       찾아도 이기는 쪽은 여전히 하나다.
    """
    # ⚠️ 이 파일은 `models` 를 «함수 안»에서 든다(8 자리). 이 줄이 빠져서 훑기가 박스에서
    #    2 초마다 NameError 로 죽었고, 시험 29 는 초록이었다 — 시험이 이 함수를 «통째로»
    #    monkeypatch 해서 진짜 몸통이 «한 번도 안 돌았기» 때문이다.
    from database import models

    row = (db.query(models.RetroactiveRun)
           .filter(models.RetroactiveRun.state == RUN_QUEUED,
                   models.RetroactiveRun.op == op)
           .order_by(models.RetroactiveRun.queued_at.asc())
           .first())
    if row is None:
        return None
    return {"run_id": row.run_id, "op": row.op,
            "params": json.loads(row.params) if row.params else {}}


def execute(payload: dict, log=logger.info, claimed=False) -> dict:
    """Run one queued operation to completion. `claimed=True`: the caller already took the
    row through `claim` (the scheduler, before it hands the run on), so this does not.

    ⚠️ 「스케줄러에서만 불린다」고 적혀 있었고 2026-09-23 에 거짓이 됐다 — 체인 리플레이가
       체인 워커에서 이 문을 지난다. 여는 쪽이 둘이므로 «집기»가 이 함수 안에 있는 것이
       중요하다: 둘이 같은 행을 찾아도 이기는 쪽은 하나다(게이트 ⑭).

    Opens its own session and bootstraps the dynamic models the same way every CLI
    in `server/scripts/` does, because the scheduler process does not otherwise
    hold them.

    Never raises: a failed retroactive run must not take the scheduler daemon down
    (same rule as `config_backup.run_scheduled`).
    """
    from database import crud, models

    op = (payload or {}).get("op")
    run_id = (payload or {}).get("run_id", "?")
    out = {"run_id": run_id, "op": op, "status": "ok", "result": None, "error": None}
    try:
        spec = operation(op)
        if not crud.TABLE_CONFIG:
            raise RetroactiveRefused(
                "table_config.json is empty or missing - nothing is registered")
        # Before `validate`: its judgments look tables up (총괄 8e54a261b ④).
        models.init_dynamic_models(crud.TABLE_CONFIG)
        params = validate(op, (payload or {}).get("params") or {})
    except RetroactiveRefused as e:
        out.update(status="refused", error=str(e))
        log(f"[Retroactive] run_id={run_id} REFUSED: {e}")
        if claimed:
            # Already running in the table - a refusal here must not leave it there.
            _mark_run(run_id, state=RUN_FAILED, finished=True, error=str(e))
        return out

    control = RunControl(run_id if run_id != "?" else None, op=op, log=log)
    # 🔴 «집기»다 — `claim` 하나가 잠금 아래에서 관문을 묻고 queued -> running 을 쓴다.
    #    `run_id == "?"` 는 작업 행이 없는 손 호출이라 집을 것이 없다 — 그때는 그냥 돈다.
    if not claimed and run_id and run_id != "?":
        try:
            won = claim(run_id=run_id)
        except RetroactiveRefused as e:
            won, why = None, str(e)
        else:
            why = "run_id=%s was already claimed by another runner" % run_id
        if won is None:
            # 진 쪽이 «그 사실을 안다». 조용히 계속 돌면 둘이 같은 일을 하고,
            # 매퍼가 멱등이라 결과가 맞아 보여 아무도 못 알아챈다.
            out.update(status="skipped", error=why)
            log("[Retroactive] run_id=%s op=%s SKIPPED: %s" % (run_id, op, why))
            return out
    return _run_to_the_end(run_id, op, spec, params, log, control)


#: The heartbeat a run in its own process beats under - a CLI's, and the scheduler's child's
#: (총괄 f453968fe ①) - so a killed one is judged 「nobody's」 60 s later and a screen cancel
#: releases its lock (총괄 45410384c ②).
RUN_HERE_HEARTBEAT = "retroactive"
RUN_HERE_BEAT_SECONDS = 10


class RunCancelled(Exception):
    """A run in this process was cancelled from the screen and stopped between pages."""


def run_here(op: str, params: dict, log=print) -> dict:
    """A run that executes in THIS process - a CLI's - through the same record, gate,
    cancel and ending as a queued one (총괄 8a1f32f99 ① · 3d03bc819 · 80d61ae05).

    No doorbell and no `queued` state: the row is written `running`, stamped with this
    process, so no daemon can claim it - a queued row could be won by the scheduler or the
    chain worker, and the CLI would print 「skipped」 while the work ran elsewhere.

    :return: the ending's answer plus `stats`, the operation's own unreduced result.
    :raises RetroactiveRefused: bad params, nothing registered, or the gate is closed -
        before anything is written.
    :raises RunCancelled: cancelled from the screen; what committed stays.
    An exception from the operation reaches the caller after the row says `failed`.
    """
    from database import crud, models

    spec = operation(op)
    if not crud.TABLE_CONFIG:
        raise RetroactiveRefused(
            "table_config.json is empty or missing - nothing is registered")
    # Before `validate`: its judgments look tables up (총괄 8e54a261b ④).
    models.init_dynamic_models(crud.TABLE_CONFIG)
    params = validate(op, params)
    # The heartbeat is beaten inside the claim, after the gate passes and before the stamp:
    # `runner_identity` names it, and a refused CLI must not overwrite a running one's.
    run_id = claim(op, params, beat_as=RUN_HERE_HEARTBEAT)
    return _run_in_this_process(run_id, op, spec, params, log)


def run_claimed(run_id: str, log=print) -> dict:
    """The scheduler's child (총괄 7d2c5845b · f453968fe ③): run a row the scheduler already
    claimed, in THIS process, the way `run_here` runs a CLI's - one way to run in a process
    of its own. The row must still be `running`: a screen cancel or a release while the
    child was starting ends it here instead.

    :raises RetroactiveRefused: the row is gone, not running, or its params are refused.
    """
    from database import crud, models
    from database.database import SessionLocal
    from utils import heartbeat

    session = SessionLocal()
    try:
        row = (session.query(models.RetroactiveRun)
               .filter(models.RetroactiveRun.run_id == run_id).first())
        if row is None or row.state != RUN_RUNNING:
            raise RetroactiveRefused("run_id=%s is %s, not running - nothing to run"
                                     % (run_id, row.state if row else "unknown"))
        op, params = row.op, json.loads(row.params) if row.params else {}
    finally:
        session.close()
    try:
        spec = operation(op)
        if not crud.TABLE_CONFIG:
            raise RetroactiveRefused(
                "table_config.json is empty or missing - nothing is registered")
        # Before `validate`: its judgments look tables up (총괄 8e54a261b ④).
        models.init_dynamic_models(crud.TABLE_CONFIG)
        params = validate(op, params)
    except Exception as e:                       # noqa: BLE001 - any judgement that breaks ends the row
        # 🔴 총괄 10-09: a judgement that raised anything but a refusal (an ImportError in the scheduler's
        #    child) left the row running - and a running row closes the operations gate for every run.
        _mark_run(run_id, state=RUN_FAILED, finished=True,
                  error=str(e) if isinstance(e, RetroactiveRefused)
                  else "the run could not be judged - %s: %s" % (type(e).__name__, e))
        raise
    heartbeat.beat(RUN_HERE_HEARTBEAT, force=True)
    _restamp_runner(run_id, runner_identity())
    return _run_in_this_process(run_id, op, spec, params, log)


#: Anything the child prints - a crash's traceback - lands here, beside its own lines in
#: `retroactive.log`: the `<name>_stdout.log` every process of this stack has.
CHILD_STDOUT_LOG = "retroactive_stdout.log"


def spawn_claimed(run_id, log=logger.info):
    """Start the scheduler's child for a row it just claimed (총괄 f453968fe ③) and name the
    child as the row's runner. Until the child beats, that name has no heartbeat and the gate
    reads the run as nobody's - the existing mechanism, no new one. A start that fails ends
    the row `failed` here. :return: the child's pid, or None."""
    import socket
    import subprocess
    import sys

    import paths

    try:
        with open(paths.log_path(CHILD_STDOUT_LOG), "a", encoding="utf-8") as sink:
            child = subprocess.Popen(
                [sys.executable, "-m", "admin.retroactive_run", run_id], cwd=paths.SERVER_DIR,
                stdout=sink, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:                                     # noqa: BLE001
        _mark_run(run_id, state=RUN_FAILED, finished=True,
                  error="its process could not start: %s" % told(exc))
        log("[Retroactive] run_id=%s could not start its process: %s" % (run_id, told(exc)))
        return None
    _restamp_runner(run_id, "%s/%s/%d" % (RUN_HERE_HEARTBEAT, socket.gethostname(), child.pid))
    log("[Retroactive] run_id=%s runs in its own process pid=%d - its log is retroactive.log"
        % (run_id, child.pid))
    return child.pid


def _restamp_runner(run_id, runner):
    """Name the process that holds a running row - the child, once it beats. Own session."""
    from database import models
    from database.database import SessionLocal

    session = SessionLocal()
    try:
        (session.query(models.RetroactiveRun)
         .filter(models.RetroactiveRun.run_id == run_id)
         .update({"runner": runner}, synchronize_session=False))
        session.commit()
    finally:
        session.close()


def _run_in_this_process(run_id, op, spec, params, log):
    """A claimed row, run in the process that holds it - a CLI's (`run_here`) or the
    scheduler's child (`run_claimed`): heartbeat, the one ending, and the file's removal."""
    import threading

    from utils import heartbeat

    stop = threading.Event()

    def beat_until_stopped():
        while not stop.wait(RUN_HERE_BEAT_SECONDS):
            heartbeat.beat(RUN_HERE_HEARTBEAT, force=True)

    beating = threading.Thread(target=beat_until_stopped, name="run-here-heartbeat",
                               daemon=True)
    beating.start()
    control = RunControl(run_id, op=op, log=log)
    try:
        out = _run_to_the_end(run_id, op, spec, params, log, control, raise_failure=True)
    except Exception:
        raise                                   # the ending already wrote `failed`
    except BaseException:
        # Ctrl-C. What committed stays and the rest did not run - a cancel, not a failure.
        # Without this the row stays `running` and holds the gate for every later run.
        _mark_run(run_id, state=RUN_CANCELLED, finished=True,
                  error="interrupted in the terminal that ran it")
        control.announce(ec.PROGRESS_STATUS_CANCELLED)
        raise
    finally:
        # Every ending that reaches here - done, cancelled, failed, Ctrl-C - takes its file
        # with it (총괄 f453968fe ⓑ). A killed process never gets here, and the file it
        # leaves is what lets the gate call its run nobody's.
        stop.set()
        beating.join(RUN_HERE_BEAT_SECONDS)
        heartbeat.forget(RUN_HERE_HEARTBEAT)
    if out["status"] == "cancelled":
        raise RunCancelled("run_id=%s op=%s was cancelled from the screen; what it "
                           "committed stays: %s" % (run_id, op, out["result"]))
    return dict(out, stats=control.stats)


def _run_to_the_end(run_id, op, spec, params, log, control, raise_failure=False) -> dict:
    """Run a claimed run's operation and write how it ended: done, cancelled or failed.

    🔴 THE ONE ENDING (총괄 b39604b58). `execute` (a queued run a daemon claimed) and
       `run_here` (a run in its own process) both finish here, so 「how a run ends」 has
       one spelling. A daemon must never raise (`raise_failure=False`); a terminal wants
       the operation's own exception, after the row says `failed`.
    """
    from database.database import SessionLocal

    out = {"run_id": run_id, "op": op, "status": "ok", "result": None, "error": None}
    db = SessionLocal()
    try:
        log(f"[Retroactive] run_id={run_id} op={op} params={params} START")
        # 🔴 [소유자 09-26 · 총괄 c2995cdd8] EVERY OPERATION'S WRITES go out on the retroactive
        #   channel, which wakes no rule - one seat, because every run ends here. A collector
        #   backfill writes files; the watcher ingests them on its own channel.
        # 🔴 [총괄 b3a4334db] AND EVERY EVENT THEY STAGE SAYS WHICH RUN, so one job is one line
        #   in the queue whatever transactions its operations write in.
        from database.context import channel, retroactive_run
        with channel(ec.CHANNEL_RETROACTIVE), retroactive_run(run_id), _beating(control, db.get_bind()):
            out["result"] = spec["run"](db, params, log, control)
        # 🔴 STOPPED AND FINISHED ARE DIFFERENT OUTCOMES. A cancelled run has committed
        # everything it wrote and has more left to do; reporting it as `done` would tell
        # an operator the operation had covered the whole table.
        if control.stopped:
            out.update(status="cancelled")
            # 「취소로 끝난 실행은 자기 대기 이벤트를 남기지 않는다」(총괄 e2b5b6f35 ㉠) - whoever
            # stopped it, an app stop too: a page committed after the stop's own set-aside still
            # waits, and the worker eating it would run half a retroactive in silence. Before the
            # row reads cancelled. Who stopped it is on no column of the row, so the reason says
            # only that it was cancelled. Brought back by `rerun_set_aside`.
            from chain import set_aside
            set_aside.set_aside_line(db, run_id, set_aside.OPERATOR, run=True,
                                     reason="run %s cancelled" % run_id)
            _mark_run(run_id, state=RUN_CANCELLED, finished=True, result=out["result"])
            log(f"[Retroactive] run_id={run_id} op={op} CANCELLED: {out['result']}")
            control.announce(ec.PROGRESS_STATUS_CANCELLED)
        else:
            _mark_run(run_id, state=RUN_DONE, finished=True, result=out["result"])
            log(f"[Retroactive] run_id={run_id} op={op} DONE: {out['result']}")
            control.announce(ec.PROGRESS_STATUS_DONE)
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        out.update(status="error", error=str(e))
        _mark_run(run_id, state=RUN_FAILED, finished=True, error=str(e))
        log(f"[Retroactive] run_id={run_id} op={op} FAILED: {e}")
        # ⚠️ 실패도 «끝»이다. 안 내면 화면의 진행 표시가 «영원히» 돌고,
        #    그것은 「도는 중」과 구별이 안 된다.
        control.announce(ec.PROGRESS_STATUS_CANCELLED)
        if raise_failure:
            raise
    finally:
        db.close()
    return out


#: Run rows this process could not update, and why. Kept because the failure is silent
#: by nature: the work continues and the row simply stops describing it, so nothing else
#: in the system would ever notice. Bounded - only the most recent matters for "is
#: bookkeeping broken right now".
_RECORD_FAILURES = []


def _record_failure(run_id, exc):
    import time as _time
    _RECORD_FAILURES.append({"run_id": run_id, "at": _time.time(),
                             "error": "%s: %s" % (type(exc).__name__, exc)})
    del _RECORD_FAILURES[:-20]


def record_failures():
    """Run-row updates that did not land. Empty is the normal answer.

    ⚠️ NOT EMPTY MEANS THE QUEUE VIEW IS LYING, not that a run failed. The runs are fine;
    what stopped is the record of them, which is why this is published beside the queue
    instead of being left in a log.
    """
    return list(_RECORD_FAILURES)


def os_user():
    """The OS account a CLI run was started from (총괄 d34247b3d ㉢) - who ran it, not an invented
    author. Unreadable stays absent, as the publish leaves an unnamed `requested_by`."""
    import getpass
    try:
        return getpass.getuser() or None
    except Exception:                                            # noqa: BLE001
        return None


#: 수를 «설명하는» 칸들의 꼬리. 이 칸들은 수가 아니므로 문장에 «값으로» 서지 않는다 —
#: 안 빼면 운영자 문장에 `skipped_no_key_group not_made` 처럼 raw 키 이름이 선다(실측).
#: 🔴 [판정 ddcf2b685] `_group` 은 «옆에 만든 새 규약»이 아니라 `_label` 과 같은 자리다:
#: 하나는 「뭐라고 읽나」, 하나는 「어느 묶음인가」. 그래서 건너뛰기도 «한 규칙»이다.
NUMBER_DESCRIBERS = ("_label", "_group")

#: 묶음 이름 — 🔴 [판정 bd25c6e28] «배관 값»이고 브라우저에 렌더되지 않습니다.
#: 운영자가 «읽는» 것은 `_label` 이고, 묶음이 하는 일은 그 수를 «어디에 놓나»뿐입니다.
#: 그래서 문장에서도 빠지고(아래 건너뛰기), 화면도 이 낱말을 그리지 않습니다.
GROUP_NOT_MADE = "not_made"
#: 만든 행의 «부분집합». 안 만든 수 옆에 서면 운영자가 같은 종류로 읽으므로 자리가 갈린다.
GROUP_PART_OF_MADE = "part_of_made"


def _describes_a_number(key: str) -> bool:
    return any(key.endswith(tail) for tail in NUMBER_DESCRIBERS)


#: What each result number is CALLED - one table for every registered operation (lead
#: dc8bf5af8: the result line printed its keys). Still one rule, no branch per operation:
#: an operation's own `<key>_label` wins, then this table, then the key as written.
#: ⚠️ `cursor_after` is left out: the implementer's via-events retirement removes it.
RESULT_NAMES = {
    "withdrawn": "atoms withdrawn", "attempted": "atoms attempted",
    "inserted": "atoms inserted", "deduped": "already in the ledger",
    "rows_in_scope": "rows in scope", "applied": "applied",
    "refused": "molecules refused", "refused_reasons": "refused for",
    "rows_staged": "rows staged", "events_staged": "events staged",
    "rows_scanned": "rows scanned", "rows_read": "rows read",
    "cells_withdrawn": "cells withdrawn", "revealed": "values revealed",
    "emptied": "cells emptied", "pinned_skipped": "pinned, skipped",
    "cells_changed": "cells changed", "cells_examined": "cells examined",
    "confirmed": "confirmed", "written_cells": "cells written", "queue_size": "queue size",
    "batches": "batches", "molecules": "molecules", "stopped": "stopped early",
    "days": "days in the window", "days_done": "days collected",
    "done_until": "collected up to (KST)", "key_index": "index on the keys",
    "probe_batch_fallbacks": "batch -> key by key (keys)",
}


def _result_value(value) -> str:
    """A result value as read: a boolean is yes / no, not Python's `False`."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def run_result_sentence(stored) -> str | None:
    """연산이 돌려준 수들 -> 화면이 «그대로 그릴» 한 문장. 없으면 None.

    🔴 낱말을 «지어내지 않습니다» — 연산이 쓴 키를 그대로 씁니다.
    연산별 갈래를 만드는 순간 이 함수가 «등록부가 범용이라는 성질»을 깨고,
    그러면 새 연산이 항목 하나가 아니라 «이 함수의 갈래»가 됩니다.
    ⚠️ 빈 dict 는 None 입니다 — 「수가 없다」와 「빈 문장」은 다릅니다.

    🔴 [판정 c1861f8ec] 연산이 `<키>_label` 을 같이 실으면 그 낱말로 읽습니다. 갈래가
    아니라 «규칙 한 줄»입니다 — 이 함수는 어느 연산인지 여전히 모르고, 라벨을 안 단
    연산의 문장은 한 글자도 안 바뀝니다. 같은 물음(「이 수를 운영자가 뭐라고 읽나」)에
    카운트 경로가 이미 `*_label` 로 답하고 있어서, 실행만 다른 기제로 답하면 한 물음에
    답이 둘이 됩니다.
    """
    if not stored:
        return None
    try:
        values = json.loads(stored) if isinstance(stored, str) else stored
    except Exception:                                            # noqa: BLE001
        return None
    if not isinstance(values, dict) or not values:
        return None
    labels = {k[:-len("_label")]: v for k, v in values.items()
              if k.endswith("_label")}
    return " · ".join("%s %s" % (labels.get(k) or RESULT_NAMES.get(k, k), _result_value(v))
                      for k, v in values.items() if not _describes_a_number(k))


def _mark_run(run_id, *, state, started=False, finished=False, result=None, error=None,
              expect_state=None):
    """Move the run row. On its OWN session, and never fatal.

    Same reason `RunControl` holds its own: this has to survive the operation's rollback,
    because "the run failed" is exactly the moment the row must not roll back with it.

    🔴 `expect_state` 가 「집기」를 «집기로» 만든다. 없이 부르면 `run_id` «하나»로 필터하는
       무조건 갱신이고, 그것이 오늘까지 안전했던 이유는 기제가 아니라 «집는 놈이 하나»라서다
       (2026-09-22 실측: started=True 호출 «1»). 체인 워커가 같은 표에서 집는 순간 그 전제가
       거짓이 되고, 둘이 같은 queued 행을 읽으면 «둘 다» 이긴다 — 리플레이가 두 번 돌고,
       매퍼가 멱등이라 결과는 맞아 보이며 아무것도 안 터진다.
       `expect_state` 를 주면 그 상태일 때만 옮기고, «옮겼는지»를 돌려준다.

    ⚠️ 끝내는 전이(done · failed · cancelled)는 «조건 없이» 옮긴다. 이미 집어서 돌던 일이
       자기 결과를 못 적는 것이 더 나쁘다 — 그 행은 영원히 running 으로 남는다.

    :return: `expect_state` 를 줬으면 「내가 옮겼나」. 안 줬으면 `None` (앞과 같다).
    """
    if not run_id or run_id == "?":
        return None
    from datetime import datetime, timezone

    from database import models
    from database.database import SessionLocal

    session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        values = {"state": state}
        if started:
            values["started_at"] = now
            values["last_progress_at"] = now
            values["runner"] = runner_identity()
        if finished:
            values["finished_at"] = now
        if result is not None:
            values["result"] = json.dumps(result, ensure_ascii=False, default=str)
        if error is not None:
            values["error"] = str(error)[:RUN_ERROR_LIMIT]
        q = session.query(models.RetroactiveRun).filter(
            models.RetroactiveRun.run_id == run_id)
        if expect_state is not None:
            q = q.filter(models.RetroactiveRun.state == expect_state)
        changed = q.update(values, synchronize_session=False)
        session.commit()
        if expect_state is not None:
            if changed:
                return True
            # 🔴 0 은 «두 뜻»이다 — 조건부 UPDATE 는 「남이 가져갔다」와 「행이 아예 없다」를
            #    같은 0 으로 준다. 둘을 접으면 작업 행 «없이» 직접 부르는 길(CLI·시험·
            #    publish 를 안 거친 호출)이 전부 「졌다」가 되어 조용히 안 돈다.
            #    실측 2026-09-22: 접었더니 test_retroactive_admin.py 에서 일곱이 빨개졌고,
            #    전부 「집을 행이 없는데 졌다고 답한」 것이었다.
            # ⚠️ 그래서 «열어» 본다. 행이 없으면 경쟁할 상대가 없으므로 그냥 적고 이긴다.
            exists = (session.query(models.RetroactiveRun)
                      .filter(models.RetroactiveRun.run_id == run_id).first())
            if exists is None:
                (session.query(models.RetroactiveRun)
                 .filter(models.RetroactiveRun.run_id == run_id)
                 .update(values, synchronize_session=False))
                session.commit()
                return True
            return False
    except Exception as exc:                       # noqa: BLE001
        session.rollback()
        # 🔴 NOT `debug`. This failing means the run row no longer describes the run: the
        # work goes on, and the row keeps saying `queued` with no `started_at`, so every
        # screen reads "waiting" while the operation is actually running. Measured cause
        # 2026-09-05: deploying the `runner` column before its migration makes every
        # UPDATE raise UndefinedColumn, and at debug level nobody would ever see it.
        #
        # ⛔ AND STILL NOT `raise`. Losing the record must not kill the run - a bookkeeping
        # failure that takes down the work is worse than one that is merely loud.
        # So it is reported at ERROR and counted, and the count goes out with the queue
        # (`queue_view`), the same shape as `gate_blocked`: the fact travels as a value
        # rather than as a log line nobody is tailing.
        _record_failure(run_id, exc)
        logger.error(
            "[Retroactive] run row update FAILED for run_id=%s: %s. The run itself is "
            "unaffected, but its row no longer tracks it - a screen will read this as "
            "waiting while it runs. If this is a fresh deployment, check that the "
            "migrations in server/migrations/ have been applied.", run_id, told(exc), exc_info=exc)
        if expect_state is not None:
            # 🔴 집기가 «터지면» 「못 집었다」로 답한다. 「모르겠다」의 안전한 쪽이 그것이다 —
            #    이겼다고 답하면 둘이 도는 쪽으로 틀리고, 못 집었다고 답하면 «아무도 안 도는»
            #    쪽으로 틀린다. 뒤쪽은 큐에 남아 다음 틱이 다시 집지만, 앞쪽은 조용히 두 번 돈다.
            return False
    finally:
        session.close()
