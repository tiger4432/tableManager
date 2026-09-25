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
import json
import logging
import uuid

import event_constants

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

def _p(name, required=True, kind="string", help="", choices=None):
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
    """
    return {"name": name, "required": required, "type": kind, "help": help,
            "choices": choices}


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
            logger.warning("could not resolve choices for '%s': %s", param["name"], exc)
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
    columns = params.get("columns")
    c = replay.count_withdrawable(db, table, source, columns=columns)
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
            f"same value, the display stays as it is)."
        ),
        "extra": {
            "cells_claimed": c["cells_claimed"],
            "pinned": c["pinned"],
            "why_upper_bound": (
                "The number in scope shrinks in only two ways: (1) the row was "
                "already deleted and only its cell_sources remain, (2) the value "
                "revealed after the withdrawal equals the current one. Both need a "
                "cell-by-cell recomputation, which a cheap query cannot answer."
            ),
        },
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
    census = backfill.rows_not_yet_translated(db.get_bind(), load_setup(), source)

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

    rows = census["not_yet"]
    total, indexed = census["relation_rows"], census["indexed_rows"]
    if not rows:
        detail = (f"'{source}' has NO rows left to translate - {total} row(s) in "
                  f"the table, {indexed} in the index. Running it now does nothing "
                  f"and ends.")
    else:
        detail = (f"'{source}' has {rows} row(s) not yet translated - {total} "
                  f"row(s) in the table, {indexed} in the index. This number is the "
                  f"WHOLE set, not a sample. The run can be stopped while it goes.")
    if census.get("index_names_absent_rows"):
        detail += (f" ⚠ The index names {census['index_names_absent_rows']} "
                   f"row(s) that are NOT in the table - deletions that were never "
                   f"swept.")
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
                  "not_yet_translated": rows},
    }


def _run_ledger_backfill(db, params, log, control=None):
    from ledger import backfill

    s = backfill.run(db.get_bind(), source=params["source"],
                     checkpoint=_checkpoint(control), pace=params.get("pace"))
    _final_progress(control, s.get("rows_read"))
    return {"rows_read": s.get("rows_read"), "batches": s.get("batches"),
            "inserted": s.get("inserted"), "deduped": s.get("deduped"),
            "molecules": s.get("molecules"), "stopped": bool(s.get("stopped")),
            "cursor_after": s.get("cursor_after")}


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
    budget would describe a walk this never takes.
    """
    from ledger import backfill
    from ledger.setup import load_setup

    source = params["source"]
    column = params["scope_column"]
    values = params.get("scope_values") or []
    preview = backfill.preview_rescope(
        db.get_bind(), load_setup(), source, column, values)
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
    orphans = backfill.count_orphan_atoms(db.get_bind(), source)
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


def _final_progress(control, rows):
    """Write the finished run's own count, once, when the work is over.

    🔴 A RUN THAT FINISHED IN ONE BATCH HAD NO BATCH BOUNDARY TO REPORT AT, so its progress
    column stayed 0 while its result said 80 rows - and "never started" and "completely
    done" became the same number on the screen. Measured 2026-08-31 on a real
    `ledger_backfill` run.

    The value comes from the SERVER, and from the adapter that already knows which of its
    operation's stats is the row count. Letting a screen parse `result` instead would put
    that per-operation knowledge in the client, where every new operation would need it
    again.
    """
    if control is not None and rows is not None:
        control.progress(rows)


def _checkpoint(control):
    """One hook from a run's control: report where we are, and ask whether to go on.

    ONE call rather than two because both belong to the same instant. A batch boundary is
    the only place a stop is safe - the previous batch is committed, the next has not
    begun - and it is also the only place "how far" is a true number rather than a
    half-written one. Splitting them into two callbacks would let an operation report
    progress somewhere a stop would not be safe.
    """
    if control is None:
        return None

    def hook(processed=None, total=None):
        control.progress(processed, total)
        return control.stop_requested()

    return hook


def _run_ledger_rescope(db, params, log, control=None):
    from ledger import backfill
    from ledger.setup import load_setup

    s = backfill.rescope(
        db.get_bind(), load_setup(), params["source"], params["scope_column"],
        params.get("scope_values") or [], apply=True)
    log(f"[rescope] {s['source']} {s['scope_column']}: rows {s['rows_in_scope']}, "
        f"withdrawn {s['withdrawn']}, written {s['inserted']} of {s['attempted']}")
    _final_progress(control, s.get("rows_in_scope"))
    return {"withdrawn": s["withdrawn"], "attempted": s["attempted"],
            "inserted": s["inserted"], "deduped": s["deduped"],
            "rows_in_scope": s["rows_in_scope"], "applied": s["applied"]}


def _run_chain_replay(db, params, log, control=None):
    from chain import replay

    # 🔴 [S-270] THE SCOPE AND THE PERMISSION COME FROM ONE VALUE. `row_ids` is what
    # narrows the scan, and it is also what makes the reference side a legal subject - the
    # operator has picked the rows, so re-deriving their targets is what the live chain does
    # when they move. Reading it twice from one dict is what keeps them from disagreeing.
    rule = replay.find_rule(params["rule"], row_scoped=bool(params.get("row_ids")))
    s = replay.replay_rule(db, rule, apply=True, log=log,
                                 checkpoint=_checkpoint(control),
                                 business_keys=params.get("business_keys"),
                                 row_ids=params.get("row_ids"),
                                 pace=params.get("pace"))
    _final_progress(control, s.get("rows_scanned"))
    # 🔴 THIS RUN NO LONGER WRITES, SO IT MUST NOT REPORT WRITES. It hands the rows to the
    #    worker as ordinary trigger events and the worker writes them, later, in its own
    #    transaction. `cells_written` / `rows_created` / `rows_updated` would all be 0 here
    #    and a 0 reads as 「아무것도 안 나왔다」 - the one thing this screen exists to tell
    #    apart from 「안 돌았다」. What is true at this instant is how many rows went over and
    #    in how many events, so that is what it says.
    # ⚠️ THE WORKER'S SIDE OF THE NUMBER IS READ WHERE THE WORKER REPORTS IT - the queue and
    #    the chain log, under the same `chain_<tx>` label every other change uses.
    return {"rows_staged": s["rows_staged"], "events_staged": s["events_staged"],
            "rows_scanned": s["rows_scanned"]}


def _run_withdraw(db, params, log, control=None):
    from chain import replay

    s = replay.withdraw_source(db, params["table"], params["source"],
                                     columns=params.get("columns"), apply=True, log=log,
                                     checkpoint=_checkpoint(control))
    _final_progress(control, s.get("cells_claimed", s.get("cells_withdrawn")))
    return {"cells_withdrawn": s["cells_withdrawn"], "revealed": s["revealed"],
            "emptied": s["emptied"], "pinned_skipped": s["pinned_skipped"]}


def _run_enrichment_backfill(db, params, log, control=None):
    from chain import enrichment
    from database import crud

    rule = enrichment.backfill.load_rule(params["rule"], crud.TABLE_CONFIG)
    s = enrichment.backfill.run_backfill(db, rule, apply=True, log=log,
                                         checkpoint=_checkpoint(control))
    _final_progress(control, s.get("rows_scanned"))
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
    # 🔴 NO CHECKPOINT, AND THAT IS REPORTED RATHER THAN FAKED. `run_auto_confirm_sweep`
    # collects the whole queue and then hands it to `confirm_keys` in ONE call; the commits
    # are chunked a level below that, inside `apply_batch_updates`. A hook at this level
    # could therefore only stop the run BEFORE any writing began, and a cancel that works
    # only in the first instant is worse than none - an operator would press it mid-run and
    # watch it do nothing. The registry entry declares `cancellable: False` so the screen
    # does not offer the button at all.
    from chain.enrichment import analysis

    # ignore_knob stays FALSE here: the knob is where a human consents to
    # automatic writes, and `run_auto_confirm_sweep` refuses apply without it.
    s = analysis.run_auto_confirm_sweep(
        db, _enrichment_rule(params["rule"]), apply=True, ignore_knob=False, log=log)
    _final_progress(control, s.get("queue_size"))
    return {"confirmed": s.get("confirmed", 0), "written_cells": s.get("written_cells", 0),
            "queue_size": s.get("queue_size", 0)}


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
# The registry
# ---------------------------------------------------------------------------

#: Per-operation facts a client cannot infer from the id, and must not guess.
#:
#: `deletes` and `restartable` are explicit so a client never infers mutation
#: semantics from an operation id.
#: 🔴 Whether this operation can be asked to stop BETWEEN BATCHES. False is not a defect
#: and not a TODO: it is a fact about where the operation's commits are chunked, and a
#: screen that offered cancel anyway would show a button that does nothing.
OPERATIONS = {
    "chain_replay": {
        "label": "Replay chain rules over old data (R1)",
        "what_is_missing": "data older than the rule has never been seen by that rule",
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
                   _pace_param()],
        "count": _count_chain_replay,
        "run": _run_chain_replay,
        "cli": ("server/scripts/chain_replay_cli.py replay <rule> "
                "[--business-keys a,b,c] [--row-ids r1,r2] [--pace slow] --apply"),
        "deletes": None,
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("crud.apply_batch_updates commits per 1000-item write "
                               "chunk; a pace yields at the page boundary, after those "
                               "commits and before the next page is read"),
        "cli_only": ["replay-all (every rule in dependency order)", "--limit", "--chunk-size"],
    },
    "withdraw": {
        "label": "Withdraw a stale source (R2)",
        "what_is_missing": "a wrong value an old rule wrote still wins the priority stack",
        "params": [_p("table"), _p("source"),
                   _p("columns", required=False, kind="csv",
                      help="comma-separated column allowlist")],
        "count": _count_withdraw,
        "run": _run_withdraw,
        "cli": "server/scripts/chain_replay_cli.py withdraw <table> <source> --apply",
        # It deletes a source's CLAIM, not the cell and not the row: the revealed
        # value is recomputed and written, and every changed cell gets an AuditLog
        # entry naming the withdrawn source.
        "deletes": "cell_sources rows (one source's claim on a cell)",
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": "explicit commit per row chunk",
        "cli_only": ["--columns is available here too; nothing else exists on this path"],
    },
    "ledger_backfill": {
        "label": "Translate the ledger forward (everything after the cursor)",
        "what_is_missing": "the declaration reads this source, but rows after the cursor are not in the ledger yet",
        "params": [_p("source", help="ledger source id (GET /api/ledger/declaration)"),
                   _pace_param()],
        "count": _count_ledger_backfill,
        "run": _run_ledger_backfill,
        "cli": "server/ledger/backfill.py --source <source> [--pace slow]",
        "deletes": None,
        # 🔴 THIS IS THE ONE THE OWNER NAMED: "백필 돌리다 서버 렉먹는데 백필만 못꺼서
        # 서버 재기동". It commits per page and resumes from the cursor, so asking it to
        # stop between pages costs nothing and gives that back - the server stays up and
        # every other job with it.
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": "atoms and cursor in one commit per page",
        "cli_only": ["--fetch-rows", "--max-batches", "--ontology-root",
                     "--scope-column/--scope-values (that is `ledger_rescope` here)"],
    },
    "ledger_rescope": {
        "label": "Re-translate a ledger scope",
        "what_is_missing": "corrected input never reached the ledger, so that scope alone holds stale values",
        "params": [_p("source", help="ledger source id (GET /api/ledger/declaration)"),
                   _p("scope_column",
                      help="a column this source's read declares; anything else is "
                           "refused by name with the declared list"),
                   _p("scope_values", kind="csv",
                      help="comma-separated values of that column")],
        "count": _count_ledger_rescope,
        "run": _run_ledger_rescope,
        "cli": ("server/ledger/backfill.py --source <source> --scope-column <column> "
                "--scope-values <a,b,c> --apply"),
        # It deletes this source's atoms from the NAMED rows and nothing else:
        # `source_who` is in the delete predicate, so an atom another source wrote about
        # the same die is unreachable from here however the scope is spelled.
        "deletes": "ledger_events rows (this source's atoms from the named rows only)",
        # The withdrawal and the remake are two commits, so a run that dies between them
        # leaves the atoms withdrawn and not yet rewritten. Re-running the same scope
        # finishes it - measured on 2026-08-31, when exactly that happened.
        "reads_as": "pair",
        "cancellable": False,
        "restartable": True,
        "commit_granularity": "one commit for the withdrawal, one for the remake",
        "cli_only": ["--ontology-root (read a different config root)"],
    },
    "enrichment_backfill": {
        "label": "Create enrichment derived rows",
        "what_is_missing": "the derived rows were never created at all",
        "params": [_p("rule", help="enrichment rule name (chain_rules.json)")],
        "count": _count_enrichment_backfill,
        "run": _run_enrichment_backfill,
        "cli": "server/scripts/backfill_enrichment.py <rule> --apply",
        "deletes": None,
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": "crud.apply_batch_updates commits per source chunk",
        "cli_only": ["--limit (caps NEW identities, not the scan)", "--force-disabled",
                     "--chunk-size"],
    },
    "enrichment_confirm": {
        "label": "Auto-confirm single candidates",
        "what_is_missing": "the derived rows exist but the target cell is empty",
        "params": [_p("rule", help="enrichment rule name (chain_rules.json)")],
        "count": _count_enrichment_confirm,
        "run": _run_enrichment_confirm,
        "cli": "server/scripts/enrichment_insights.py confirm <rule> --apply",
        "deletes": None,
        "reads_as": "number",
        "cancellable": False,
        "restartable": True,
        "commit_granularity": "crud.apply_batch_updates commits per write chunk",
        "cli_only": ["--limit", "--ignore-knob (measure a rule whose knob is off)",
                     "classify / propose subcommands", "all rules at once"],
    },
}


#: The states a run row can be in. `cancel_requested` is a REQUEST, not an outcome:
#: the operation is still running when it is set, and becomes `cancelled` only when the
#: operation itself has stopped between batches. Collapsing the two would make a run look
#: finished while it was still writing.
RUN_QUEUED = "queued"
RUN_RUNNING = "running"
import event_constants as ec                                      # noqa: E402

RUN_DONE = "done"
RUN_CANCEL_REQUESTED = "cancel_requested"
RUN_CANCELLED = "cancelled"
RUN_FAILED = "failed"

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

    def _utc(dt):
        return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))

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
    running_rows = (db.query(models.RetroactiveRun)
                    .filter(models.RetroactiveRun.state.in_(IN_FLIGHT_STATES)).all())
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


def _runner_state(runner):
    """`owned` / `orphaned` / `unknown` for a `host/pid` stamp.

    ⚠️ ONLY THIS HOST IS DECIDABLE. A pid on another machine cannot be called dead from
    here, and calling it dead is how "never finishes" would become "two at once". Rows
    with no stamp at all predate the column and are unknown, not orphaned.
    """
    parts = str(runner or "").split("/")
    if len(parts) != 3 or parts[0] in ("", "?"):
        # Rows written before the stamp carried a heartbeat name, or by a process that had
        # not beaten yet. Unknown, and unknown is not orphaned.
        return "unknown"
    name, _host, pid = parts
    try:
        from utils import heartbeat as _hb
        entry = _hb.read_all().get(name)
    except Exception:                                            # noqa: BLE001
        return "unknown"
    if entry is None or entry.get("stale"):
        # 🔴 THE HEARTBEAT IS WHY THE HOST STOPPED MATTERING. Asking `host/pid` meant a
        # run stamped on another machine could never be judged from here, so every such
        # row was "unknown" forever. The name is answerable from anywhere that can read
        # the heartbeats, so the unknown disappears rather than being handled.
        return "orphaned"
    beating = entry.get("pid")
    # Fresh beat, different pid: the process that started this run is gone and a newer one
    # of the same kind is beating. The run it left behind is nobody's.
    return "owned" if str(beating) == str(pid) else "orphaned"


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

    row = (db.query(models.RetroactiveRun)
           .filter(models.RetroactiveRun.state.in_(IN_FLIGHT_STATES))
           # ⚰️ `.nullslast()` REMOVED (S-131 의 같은 부류, S-130 커밋에 같이).
           # `DESC NULLS LAST` 는 btree 가 «뒤로 읽어» 줄 수 있는 순서가 아니라
           # 인덱스를 못 쓰게 만든다 — 그 절이 그리드에서 0.25 s 를 먹였다.
           # 이 표는 작아서 비용은 작지만, 남겨 두면 다음 사람이 「거기만 있었다」고 읽는다.
           .order_by(models.RetroactiveRun.started_at.desc())
           .first())
    if row is None:
        return None

    def _utc(dt):
        if dt is None:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

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

    def __init__(self, run_id, session_factory=None, op=None):
        self.run_id = run_id
        #: [S-37] 진행을 «말하려면» 무엇의 진행인지가 있어야 한다. run_id 만으로는
        #: 화면이 「무슨 일이 도는가」를 못 말한다 — S-36 이 대기열에서 고친 그 부족이다.
        self.op = op
        self.stopped = False
        self._session_factory = session_factory

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
            logger.debug("cancel check failed for run_id=%s: %s", self.run_id, exc)
            return False
        finally:
            session.close()
        self.stopped = state == RUN_CANCEL_REQUESTED
        return self.stopped

    def progress(self, processed=None, total=None) -> None:
        """Record how far this run has got. `total=None` stays NULL - unknown, not zero."""
        if not self.run_id:
            return
        from datetime import datetime, timezone

        from database import models

        session = self._session()
        try:
            values = {"last_progress_at": datetime.now(timezone.utc)}
            if processed is not None:
                values["processed_rows"] = int(processed)
            if total is not None:
                values["total_rows"] = int(total)
            (session.query(models.RetroactiveRun)
             .filter(models.RetroactiveRun.run_id == self.run_id).update(values))
            session.commit()
        except Exception as exc:                   # noqa: BLE001
            # Progress is a report, never the work. A run must not fail because its
            # bookkeeping did.
            session.rollback()
            logger.debug("progress write failed for run_id=%s: %s", self.run_id, exc)
        finally:
            session.close()
        # [S-37] 쓰는 «자리 옆»에서 한 번 더 말한다. 여기가 아니면 「DB 는 갱신됐는데
        # 아무도 못 들었다」가 다시 생긴다 — 그 둘이 갈라지는 것이 이 라운드의 결함이다.
        import event_constants
        announce_progress(self.run_id, self.op, event_constants.PROGRESS_STATUS_RUNNING,
                          processed=processed, total=total)


def announce_progress(run_id, op, status, processed=None, total=None):
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
            progress=(None if not total else int(processed * 100 / total)),
            run_id=run_id, op=op)
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
        logger.debug("progress notification failed for run_id=%s: %s", run_id, exc)
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
    if row.state in (RUN_DONE, RUN_CANCELLED, RUN_FAILED):
        raise RetroactiveRefused(
            f"run '{run_id}' already finished ({row.state}); there is nothing running to "
            f"stop. Its work is committed and this cannot undo it.")

    op, runner = row.op, row.runner
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


def runs(db, limit: int = 50) -> list:
    """The recent runs, newest first. One list for every request-type operation.

    ⚠️ File ingestion is NOT here and must not be moved here: it keeps its own row per file
    in `file_ingestion_checkpoints` with total/processed/chunk already on it. A screen reads
    that table directly.
    """
    from database import models

    rows = (db.query(models.RetroactiveRun)
            .order_by(models.RetroactiveRun.queued_at.desc())
            .limit(max(1, min(int(limit or 50), 500))).all())
    return [{
        "run_id": row.run_id,
        # 🔴 화면이 `result` 를 «해석하지 않습니다». 연산마다 키가 다르고
        #    선언이 그 모양을 안 고정하므로, 「이 수를 이 이름으로」를 화면이
        #    정하면 그것이 계약을 «지어내는» 것입니다 (총괄 판정 33).
        "result_sentence": run_result_sentence(row.result),
        "op": row.op,
        "label": (OPERATIONS.get(row.op) or {}).get("label"),
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
    } for row in rows]


def operation(op: str) -> dict:
    spec = OPERATIONS.get(op)
    if spec is None:
        raise RetroactiveRefused(
            f"unknown retroactive operation '{op}'; available: "
            f"{', '.join(sorted(OPERATIONS))}")
    return spec


def inventory() -> list:
    """The operations, their parameters, and where the CLI equivalent is.

    Config only - no DB query, so it has `GET /admin/config/resolve`'s posture and
    can sit on any request path. The CLI line is carried deliberately: the buttons
    cover the common shape of each operation and the CLI still covers the rest
    (`--limit`, `--force-disabled`, `--label`, `replay-all`, per-column withdrawal).
    """
    return [
        {"op": op, "label": s["label"], "what_is_missing": s["what_is_missing"],
         "params": [dict(p, choices=_resolved_choices(p)) for p in s["params"]], "cli": s["cli"], "cli_only": s["cli_only"],
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
    from chain import replay

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

    # R2's first refusal, re-stated here so the operator gets a 400 instead of a
    # queued job that dies in a worker log. `withdraw_source` refuses it AGAIN -
    # this check is convenience, that one is the safety property.
    if op == "withdraw" and out.get("source") in replay.PROTECTED_SOURCES:
        raise RetroactiveRefused(
            f"refusing to withdraw source '{out['source']}': it is the layer that means "
            f"'a human typed this'. There is no supported way to remove a human's value "
            f"from here - edit the cell instead.")
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


def publish(db, op: str, params: dict, requested_by: str = None) -> dict:
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
    run_id = uuid.uuid4().hex[:12]
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
            payload=json.dumps(payload, ensure_ascii=False),
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
        return None
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
    return ("run_id=%s op=%s %s for %ss (runner=%s is alive — cancelling stops work that "
            "is actually running) — %s"
            % (run_id, op, blocking["moving"], blocking.get("no_progress_seconds"),
               blocking.get("runner"), where))


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


def execute(payload: dict, log=logger.info) -> dict:
    """Run one queued operation to completion.

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
    from database.database import SessionLocal

    op = (payload or {}).get("op")
    run_id = (payload or {}).get("run_id", "?")
    out = {"run_id": run_id, "op": op, "status": "ok", "result": None, "error": None}
    try:
        spec = operation(op)
        params = validate(op, (payload or {}).get("params") or {})
    except RetroactiveRefused as e:
        out.update(status="refused", error=str(e))
        log(f"[Retroactive] run_id={run_id} REFUSED: {e}")
        return out

    if not crud.TABLE_CONFIG:
        out.update(status="refused",
                   error="table_config.json is empty or missing - nothing is registered")
        log(f"[Retroactive] run_id={run_id} REFUSED: {out['error']}")
        return out
    models.init_dynamic_models(crud.TABLE_CONFIG)

    control = RunControl(run_id if run_id != "?" else None, op=op)
    # 🔴 «집기»다. queued 일 때만 running 으로 옮기고, 옮겼는지를 읽는다.
    #    `run_id == "?"` 는 작업 행이 없는 손 호출(CLI)이라 집을 것이 없다 — 그때는 그냥 돈다.
    if run_id and run_id != "?":
        if not _mark_run(run_id, state=RUN_RUNNING, started=True,
                         expect_state=RUN_QUEUED):
            # 진 쪽이 «그 사실을 안다». 조용히 계속 돌면 둘이 같은 일을 하고,
            # 매퍼가 멱등이라 결과가 맞아 보여 아무도 못 알아챈다.
            out.update(status="skipped",
                       error="run_id=%s was already claimed by another runner" % run_id)
            log("[Retroactive] run_id=%s op=%s SKIPPED: already claimed" % (run_id, op))
            return out
    else:
        _mark_run(run_id, state=RUN_RUNNING, started=True)
    db = SessionLocal()
    try:
        log(f"[Retroactive] run_id={run_id} op={op} params={params} START")
        out["result"] = spec["run"](db, params, log, control)
        # 🔴 STOPPED AND FINISHED ARE DIFFERENT OUTCOMES. A cancelled run has committed
        # everything it wrote and has more left to do; reporting it as `done` would tell
        # an operator the operation had covered the whole table.
        if control.stopped:
            out.update(status="cancelled")
            _mark_run(run_id, state=RUN_CANCELLED, finished=True, result=out["result"])
            log(f"[Retroactive] run_id={run_id} op={op} CANCELLED: {out['result']}")
            announce_progress(control.run_id, op, ec.PROGRESS_STATUS_CANCELLED)
        else:
            _mark_run(run_id, state=RUN_DONE, finished=True, result=out["result"])
            log(f"[Retroactive] run_id={run_id} op={op} DONE: {out['result']}")
            announce_progress(control.run_id, op, ec.PROGRESS_STATUS_DONE)
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
        announce_progress(control.run_id, op, ec.PROGRESS_STATUS_CANCELLED)
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


def runner_identity() -> str:
    """Who is running this, as `host/pid`.

    🔴 READ WHEN THE RUN STARTS, NOT AT IMPORT. A process that forks, or one re-executed
    in place, would otherwise stamp the identity of whatever imported this module first -
    and an identity that can be inherited is worse than none, because it looks specific.

    ⚠️ IT RECORDS, IT DOES NOT JUDGE. Nothing reaps a run on the strength of this. Without
    an identity "it died" and "it is slow" are the same row; with one they still are,
    until somebody decides what evidence of death looks like. This is the material for
    that decision, not the decision.
    """
    import os as _os
    import socket as _socket
    try:
        from utils import heartbeat as _hb
        name = _hb.own_name() or "?"
    except Exception:                                            # noqa: BLE001
        name = "?"
    try:
        return "%s/%s/%d" % (name, _socket.gethostname(), _os.getpid())
    except Exception:                                            # noqa: BLE001
        return "%s/?/%d" % (name, _os.getpid())


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
    return " · ".join("%s %s" % (labels.get(k, k), v)
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
            values["error"] = str(error)[:2000]
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
            "migrations in server/migrations/ have been applied.", run_id, exc)
        if expect_state is not None:
            # 🔴 집기가 «터지면» 「못 집었다」로 답한다. 「모르겠다」의 안전한 쪽이 그것이다 —
            #    이겼다고 답하면 둘이 도는 쪽으로 틀리고, 못 집었다고 답하면 «아무도 안 도는»
            #    쪽으로 틀린다. 뒤쪽은 큐에 남아 다음 틱이 다시 집지만, 앞쪽은 조용히 두 번 돈다.
            return False
    finally:
        session.close()
