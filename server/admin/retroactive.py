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

def _p(name, required=True, kind="string", help="", choices=None, form=True):
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
    """
    return {"name": name, "required": required, "type": kind, "help": help,
            "choices": choices, "form": form}


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


def _given(params, *names):
    """The CLI-only options a run carries, only where given - each operation's own default
    stands for the rest. Spelling the defaults here too would make a second author."""
    return {name: params[name] for name in names if name in params}


def _run_ledger_backfill(db, params, log, control=None):
    from ledger import backfill

    s = backfill.run(db.get_bind(), source=params["source"],
                     checkpoint=_checkpoint(control), pace=params.get("pace"),
                     **_given(params, "fetch_rows", "max_batches", "ontology_root"))
    _final_progress(control, s.get("rows_read"), s)
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
    """
    if control is None:
        return None

    def hook(processed=None, total=None):
        control.progress(processed, total)
        return control.stop_requested()

    return hook


def _run_ledger_rescope(db, params, log, control=None):
    from ledger import backfill

    s = backfill.rescope(
        db.get_bind(), _ledger_setup(params), params["source"], params["scope_column"],
        params.get("scope_values") or [], apply=True,
        page_rows=backfill.RESCOPE_PAGE_ROWS, checkpoint=_checkpoint(control))
    log(f"[rescope] {s['source']} {s['scope_column']}: rows {s['rows_in_scope']}, "
        f"withdrawn {s['withdrawn']}, written {s['inserted']} of {s['attempted']}")
    _final_progress(control, s.get("rows_in_scope"), s)
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
    # [146b208cb] The trigger events carry the ask, and what they wake writes with it.
    from database.context import cascade
    with cascade(params.get("cascade") is True):
        s = replay.replay_rule(db, rule, apply=True, log=log,
                               checkpoint=_checkpoint(control),
                               business_keys=params.get("business_keys"),
                               row_ids=params.get("row_ids"),
                               pace=params.get("pace"),
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
            "rows_scanned": s["rows_scanned"]}


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

    found = set_aside.set_aside(db, apply=False, **_scope(params))
    return {"affected": found["events"],
            "absence": ABSENCE_TRULY_NONE if not found["events"] else ABSENCE_NOT_APPLICABLE,
            "affected_label": "waiting events to set aside (%d row(s))" % found["rows"],
            "count_kind": COUNT_EXACT, "scanned": None, "scan_limit": None,
            "truncated": False,
            "detail": "by table: %s" % (found["by_table"] or "none")}


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
    rules named), in the declaration's order, with `cascade`: it gives back what the chain
    would have done, downstream included (총괄 2dbbfd1e5)."""
    from chain import replay, rule_shape, set_aside

    rows = set_aside.rows_set_aside(db, **_scope(params))
    wanted = set(_scope(params)["rules"])
    staged = 0
    for table, ids in sorted(rows.items()):
        rules = replay.order_rules([
            r for r in replay.load_rules()
            if r.get("trigger_table") == table and not rule_shape.is_switched_off(r)
            and (not wanted or r.get("name") in wanted)])
        for rule in rules:
            one = _run_chain_replay(db, {"rule": rule.get("name"), "row_ids": ids,
                                         "cascade": True}, log, control)
            staged += one["rows_staged"]
    return {"rows_staged": staged, "tables": len(rows)}


def _run_withdraw(db, params, log, control=None):
    from chain import replay

    s = replay.withdraw_source(db, params["table"], params["source"],
                                     columns=params.get("columns"), apply=True, log=log,
                                     checkpoint=_checkpoint(control))
    _final_progress(control, s.get("cells_claimed", s.get("cells_withdrawn")), s)
    return {"cells_withdrawn": s["cells_withdrawn"], "revealed": s["revealed"],
            "emptied": s["emptied"], "pinned_skipped": s["pinned_skipped"]}


def _count_fold_file_layers(db, params, scan_limit):
    from chain import replay

    s = replay.fold_file_layers(db, params["table"], apply=False, limit=scan_limit,
                                log=lambda m: logger.debug(m))
    truncated = s["rows_scanned"] >= scan_limit
    affected = s["layers_deleted"]
    return {
        "affected": affected,
        "absence": (ABSENCE_NOT_EXHAUSTIVE if truncated
                    else ABSENCE_TRULY_NONE if not affected else None),
        "affected_label": "file layers that repeat a newer one",
        "count_kind": COUNT_SAMPLE if truncated else COUNT_EXACT,
        "scanned": s["rows_scanned"],
        "scan_limit": scan_limit,
        "truncated": truncated,
        "detail": (
            f"{s['cells_folded']} cell(s) in {s['rows_scanned']} row(s) of '{params['table']}' "
            f"hold file layers that repeat a newer one: layers {s['layers_before']} -> "
            f"{s['layers_after']}, the deepest cell {s['deepest_before']} -> "
            f"{s['deepest_after']}. Cannot be undone - what goes is the record of which older "
            f"file said the same value; every cell keeps its value and its history. "
            f"Afterwards give the space back with: python server/scripts/tune_layer_tables.py "
            f"--table cell_sources --vacuum"
        ),
        "extra": {key: s[key] for key in ("cells_folded", "layers_before", "layers_after",
                                          "deepest_before", "deepest_after")},
    }


def _run_fold_file_layers(db, params, log, control=None):
    from chain import replay

    s = replay.fold_file_layers(db, params["table"], apply=True, log=log,
                                checkpoint=_checkpoint(control),
                                **_given(params, "limit", "chunk_size", "pace"))
    _final_progress(control, s.get("rows_scanned"), s)
    return {key: s[key] for key in ("layers_deleted", "cells_folded", "layers_before",
                                    "layers_after", "rows_scanned")}


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
    stats = {"days": len(windows), "days_done": done}
    _final_progress(control, done, stats)
    return stats


def _day_refused(day, what):
    """The one sentence a day-by-day backfill stops on, whatever failed: what, and the day to
    start again from (총괄 69aad666e B - a script that raised used to end the run with no day)."""
    return RetroactiveRefused("%s - fix it, then start again from %s" % (what, day))


def _wait_until_ingested(db, table, written, day, hook, done, total) -> bool:
    """True once the file has passed the ingestion queue, False when a stop was asked while
    waiting. A file that FAILED stops the run by name. Asked of the file checkpoint ledger,
    by the path and stat the collector wrote."""
    import os
    import time

    from ingestion import checkpoint

    where, stat = os.path.abspath(written), checkpoint.read_file_stat(written)
    while True:
        row = checkpoint.find_terminal_by_path_stat(db, table, where, stat)
        status = row.status if row is not None else None
        db.rollback()                      # the next look reads what has committed since
        if status is not None:
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


def _ledger_setup(params):
    from ledger.setup import load_setup

    return (load_setup(params["ontology_root"]) if "ontology_root" in params
            else load_setup())


def _judge_ledger_backfill(params):
    """Is the source declared - the first step of the run's own `_require_declared_source`.
    Only that step: a refused or retired source is a name that exists, and its count and
    run answer it as they did (총괄 8e54a261b ④)."""
    from ledger.setup import LedgerSetupError

    try:
        _ledger_setup(params).require_source(params["source"])
    except LedgerSetupError as e:
        raise RetroactiveRefused(str(e)) from None


def _judge_ledger_rescope(params):
    """The run's own order - the one declared-source check, then the scope (총괄 06bb8f474)."""
    from ledger import backfill
    from ledger.setup import LedgerSetupError

    try:
        backfill.rescope_scope(_ledger_setup(params), params["source"],
                               params["scope_column"], params.get("scope_values") or [])
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
                   _pace_param(),
                   _p("limit", required=False, kind="int", form=False,
                      help="bound the source rows scanned"),
                   _p("chunk_size", required=False, kind="int", form=False,
                      help="rows per write chunk"),
                   _p("cascade", required=False, kind="bool", form=False,
                      help="let what this replay writes wake the opted-in chain rules, "
                           "as the chain does - the grid's click replay sends it")],
        "count": _count_chain_replay,
        "run": _run_chain_replay,
        "judge": _judge_chain_replay,
        "cli": ("server/scripts/chain_replay_cli.py replay <rule> "
                "[--business-keys a,b,c] [--row-ids r1,r2] [--pace slow] "
                "[--limit N] [--chunk-size N] [--cascade] --apply"),
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
        "params": [_p("table"), _p("source"),
                   _p("columns", required=False, kind="csv",
                      help="comma-separated column allowlist")],
        "count": _count_withdraw,
        "run": _run_withdraw,
        "judge": _judge_withdraw,
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
    "set_aside": {
        "label": "Set queued chain events aside",
        "what_is_missing": "the chain queue holds work that must not run now",
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
        "downstream_note": ("It replays the rows those events named, and cascades like the "
                            "chain would have"),
    },
    "resolve": {
        "label": "Recompute shown values from stored layers (R3)",
        "what_is_missing": "a cell shows a value its own stored layers no longer pick",
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
    "fold_file_layers": {
        "label": "Fold file layers that repeat a newer one",
        "what_is_missing": "a cell re-delivered file after file keeps one layer per file",
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
        # Only cell_sources rows go - no row, shown value or history entry moves (총괄
        # 225b2c658). Per cell, file layers of one priority class holding one value keep the
        # newest and a pinned one (`crud.stacked_file_layers`).
        "deletes": "cell_sources rows (file layers that repeat a newer layer's value)",
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": ("one commit per page of rows; a stop lands between pages and "
                               "a re-run finds only what is left"),
        "cli_only": [],
    },
    "ledger_backfill": {
        "label": "Translate the rows not yet in the ledger",
        "what_is_missing": "the declaration reads this source, but some of its rows are not in the ledger yet",
        "params": [_p("source", help="ledger source id (GET /api/ledger/declaration)"),
                   _pace_param(),
                   _p("fetch_rows", required=False, kind="int", form=False,
                      help="rows read per page"),
                   _p("max_batches", required=False, kind="int", form=False,
                      help="stop after this many pages"),
                   _p("ontology_root", required=False, form=False,
                      help="the Ledger config root to read")],
        "count": _count_ledger_backfill,
        "run": _run_ledger_backfill,
        "judge": _judge_ledger_backfill,
        "cli": ("server/ledger/backfill.py --source <source> [--pace slow] "
                "[--fetch-rows N] [--max-batches N] [--ontology-root <dir>]"),
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
    "ledger_rescope": {
        "label": "Re-translate a ledger scope",
        "what_is_missing": "corrected input never reached the ledger, so that scope alone holds stale values",
        "params": [_p("source", help="ledger source id (GET /api/ledger/declaration)"),
                   _p("scope_column",
                      help="a column this source's read declares; anything else is "
                           "refused by name with the declared list"),
                   _p("scope_values", kind="csv",
                      help="comma-separated values of that column"),
                   _p("ontology_root", required=False, form=False,
                      help="the Ledger config root to read")],
        "count": _count_ledger_rescope,
        "run": _run_ledger_rescope,
        "judge": _judge_ledger_rescope,
        "cli": ("server/ledger/backfill.py --source <source> --scope-column <column> "
                "--scope-values <a,b,c> [--ontology-root <dir>] --apply"),
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
        "params": [_p("collector", help="<table>/<script.py> of a collector that declares "
                                         "'# window:'"),
                   _p("start", help="first day, KST - YYYY-MM-DD (that day's 00:00) or "
                                    "YYYY-MM-DD HH:MM")],
        "count": _count_collector_backfill,
        "run": _run_collector_backfill,
        "judge": _judge_collector_backfill,
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
        #: The operation's own answer, unreduced - what a CLI prints (`_final_progress`).
        self.stats = None
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
            value = {"true": True, "false": False}.get(str(raw).strip().lower())
            if value is None:
                raise RetroactiveRefused(
                    f"'{op}' parameter '{p['name']}' must be true or false; got {raw!r}")
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
    # The seconds are SINCE THE LAST PROGRESS - 「progressing for 0.0s」 read as a run that
    # had just started (총괄 d34247b3d ㉡).
    last = ("no progress reported yet" if blocking["moving"] == MOVING_UNREPORTED
            else "last progress %ss ago" % blocking.get("no_progress_seconds"))
    return ("run_id=%s op=%s is %s, %s (runner=%s is alive — cancelling stops work that "
            "is actually running) — %s"
            % (run_id, op, blocking["moving"], last, blocking.get("runner"), where))


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

    control = RunControl(run_id if run_id != "?" else None, op=op)
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
    except RetroactiveRefused as e:
        _mark_run(run_id, state=RUN_FAILED, finished=True, error=str(e))
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
                  error="its process could not start: %s" % exc)
        log("[Retroactive] run_id=%s could not start its process: %s" % (run_id, exc))
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
    control = RunControl(run_id, op=op)
    try:
        out = _run_to_the_end(run_id, op, spec, params, log, control, raise_failure=True)
    except Exception:
        raise                                   # the ending already wrote `failed`
    except BaseException:
        # Ctrl-C. What committed stays and the rest did not run - a cancel, not a failure.
        # Without this the row stays `running` and holds the gate for every later run.
        _mark_run(run_id, state=RUN_CANCELLED, finished=True,
                  error="interrupted in the terminal that ran it")
        announce_progress(run_id, op, ec.PROGRESS_STATUS_CANCELLED)
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
        from database.context import channel
        with channel(ec.CHANNEL_RETROACTIVE):
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
    "rows_staged": "rows staged", "events_staged": "events staged",
    "rows_scanned": "rows scanned", "rows_read": "rows read",
    "cells_withdrawn": "cells withdrawn", "revealed": "values revealed",
    "emptied": "cells emptied", "pinned_skipped": "pinned, skipped",
    "cells_changed": "cells changed", "cells_examined": "cells examined",
    "confirmed": "confirmed", "written_cells": "cells written", "queue_size": "queue size",
    "batches": "batches", "molecules": "molecules", "stopped": "stopped early",
    "days": "days in the window", "days_done": "days collected",
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
