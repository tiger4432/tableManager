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
RUN_EVENT_TABLE = "__retroactive__"

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

#: Spelled once so a client can offer exactly these and no more.
ABSENCE_WORDS = (ABSENCE_NOT_YET, ABSENCE_NOT_EXHAUSTIVE, ABSENCE_CANNOT_POINT,
                 ABSENCE_TRULY_NONE, ABSENCE_ALREADY_MISSING, ABSENCE_NOT_APPLICABLE)


class RetroactiveRefused(Exception):
    """Raised when an operation must not proceed. The message states why."""


# ---------------------------------------------------------------------------
# Parameter declaration
# ---------------------------------------------------------------------------

def _p(name, required=True, kind="string", help=""):
    return {"name": name, "required": required, "type": kind, "help": help}


# ---------------------------------------------------------------------------
# Counts. Each one calls the operation's OWN dry-run or a cheap query that lives
# in the operation's own module - never a re-derivation of its logic here.
# ---------------------------------------------------------------------------

def _count_chain_replay(db, params, scan_limit):
    import chain_replay

    rule = chain_replay.find_rule(params["rule"])
    s = chain_replay.replay_rule(db, rule, apply=False, limit=scan_limit,
                                 log=lambda m: logger.debug(m),
                                 business_keys=params.get("business_keys"))
    truncated = s["rows_scanned"] >= scan_limit
    return {
        "affected": s["cells_proposed"],
        "absence": (ABSENCE_NOT_EXHAUSTIVE if truncated
                    else ABSENCE_TRULY_NONE if not s["cells_proposed"] else None),
        "affected_label": "덮어쓸 셀",
        "count_kind": COUNT_SAMPLE,
        "scanned": s["rows_scanned"],
        "scan_limit": scan_limit,
        "truncated": truncated,
        "detail": (
            f"트리거 테이블 {s['rows_scanned']}행을 표본으로 검사해 "
            f"{s['cells_proposed']}개 셀을 다시 씁니다. "
            f"사람이 입력한 값이 지키는 셀 {s['user_protected_cells']}개는 화면상 값이 "
            f"바뀌지 않습니다(레이어만 갱신)."
        ),
        "extra": {
            # Deliberately NOT added into `affected`: R1 never writes a blank.
            "withdrawal_candidates": s["skipped_blank_cells"],
            "withdrawal_candidates_label": "값이 사라진 셀 (쓰지 않음 · R2 후보)",
            "user_protected_cells": s["user_protected_cells"],
            "trigger_table": s["trigger_table"],
            "target_table": s["target_table"],
            "self_triggering": s["self_triggering"],
            "samples": s["samples"][:5],
            "withdrawal_candidate_samples": s["withdrawal_candidates"][:5],
        },
    }


def _count_withdraw(db, params, scan_limit):
    import chain_replay

    table = params["table"]
    source = params["source"]
    columns = params.get("columns")
    c = chain_replay.count_withdrawable(db, table, source, columns=columns)
    affected = max(0, c["cells_claimed"] - c["pinned"])
    return {
        "affected": affected,
        # An upper bound is not exhaustive either: fewer cells may actually change.
        "absence": ABSENCE_NOT_EXHAUSTIVE if affected else ABSENCE_TRULY_NONE,
        "affected_label": "회수할 셀 (최대)",
        "count_kind": COUNT_UPPER_BOUND,
        "scanned": None,
        # null, not the requested budget: this count is two aggregates and scans no
        # rows, so echoing a scan budget would imply a sample it never took.
        "scan_limit": None,
        "truncated": False,
        "detail": (
            f"'{source}'가 '{table}'에서 주장하는 셀은 {c['cells_claimed']}개이고, "
            f"그중 {c['pinned']}개는 사람이 이 소스를 고정(manual_priority_source)해 "
            f"건드리지 않습니다. 최대 {affected}개가 회수 대상입니다 — 실제로 "
            f"'보이는 값'이 바뀌는 셀은 이보다 적을 수 있습니다(아래 소스가 같은 값을 "
            f"가진 경우 표시는 그대로입니다)."
        ),
        "extra": {
            "cells_claimed": c["cells_claimed"],
            "pinned": c["pinned"],
            "why_upper_bound": (
                "회수 대상 수는 두 단계에서만 줄어듭니다: ① 행이 이미 삭제됐는데 "
                "cell_sources만 남은 경우, ② 회수 후 드러나는 값이 지금 값과 같은 경우. "
                "둘 다 셀 단위 재계산이 필요해 값싼 질의로는 답할 수 없습니다."
            ),
        },
    }


def _count_enrichment_backfill(db, params, scan_limit):
    # `enrichment_backfill`, NOT `scripts/backfill_enrichment`: the CLI is not
    # importable from a runtime process (server/scripts is on nobody's sys.path),
    # and importing it here is what made this route raise ModuleNotFoundError.
    import enrichment_backfill
    from database import crud

    rule = enrichment_backfill.load_rule(params["rule"], crud.TABLE_CONFIG)
    s = enrichment_backfill.run_backfill(db, rule, apply=False, scan_limit=scan_limit,
                                         log=lambda m: logger.debug(m))
    truncated = s["rows_scanned"] >= scan_limit
    return {
        "affected": s["new_combinations"],
        "absence": (ABSENCE_NOT_EXHAUSTIVE if truncated
                    else ABSENCE_TRULY_NONE if not s["new_combinations"] else None),
        "affected_label": "새로 만들 파생 행",
        "count_kind": COUNT_SAMPLE,
        "scanned": s["rows_scanned"],
        "scan_limit": scan_limit,
        "truncated": truncated,
        "detail": (
            f"소스 테이블 {s['rows_scanned']}행을 표본으로 검사해 "
            f"{s['new_combinations']}개의 새 파생 행을 만듭니다. "
            f"이미 있는 파생 행 {s['already_derived']}개는 건드리지 않습니다."
            + (f" 그중 {s['partial_key_combinations']}개는 판단키가 **일부만** 있는 "
               f"행입니다 — 2026-08-05 재정 전에는 만들어지지 않던 행이라, 데이터가 "
               f"그대로여도 이 수는 올라갑니다."
               if s["partial_key_combinations"] else "")
            + (f" 판단키가 일부만 있는 행 {s['skipped_unexpressible_key']}건은 "
               f"거절했습니다 — 파생 테이블 '{s['derived_table']}'의 키 선언이 그 "
               f"정체성을 담지 못해, 만들면 다른 행 위에 조용히 병합됩니다. "
               f"table_config.json에 composite_key_source를 판단키 전체로 선언하면 "
               f"풀립니다(서버 로그에 그 한 줄이 찍힙니다)."
               if s["skipped_unexpressible_key"] else "")
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
            "skipped_no_key_label": "판단키 없음 (건너뜀)",
            "partial_key_combinations": s["partial_key_combinations"],
            "partial_key_combinations_label": "판단키 일부만 있는 새 행",
            "skipped_unexpressible_key": s["skipped_unexpressible_key"],
            "skipped_unexpressible_key_label": "부분 판단키 거절 (파생 키 선언)",
            "source_table": s["source_table"],
            "derived_table": s["derived_table"],
            "sample_new_keys": s["sample_new_keys"][:5],
        },
    }


def _count_enrichment_confirm(db, params, scan_limit):
    import enrichment_analysis
    import enrichment_candidates

    rule = _enrichment_rule(params["rule"])
    knob_on = enrichment_candidates.rule_auto_confirm_enabled(rule)
    # ignore_knob=True so a rule whose knob is OFF can still be measured - "what
    # happens if I turn it on" has to be answerable before turning it on. The knob
    # state travels separately so the client can disable the button rather than
    # letting the operator discover the refusal by pressing it.
    s = enrichment_analysis.run_auto_confirm_sweep(
        db, rule, apply=False, limit=scan_limit, ignore_knob=True,
        log=lambda m: logger.debug(m))
    truncated = s.get("queue_size", 0) >= scan_limit
    detail = (f"큐 {s.get('queue_size', 0)}건을 표본으로 검사해 "
              f"{s.get('confirmed', 0)}건이 사람 없이 확정 가능합니다"
              f"({s.get('written_cells', 0)}개 셀).")
    if not knob_on:
        detail += (" ⚠️ 이 규칙은 auto_confirm 노브가 꺼져 있어 실행 버튼은 거부됩니다 — "
                   "숫자는 '켜면 무슨 일이 일어나는가'입니다.")
    return {
        "affected": s.get("confirmed", 0),
        "absence": (ABSENCE_NOT_EXHAUSTIVE if truncated
                    else ABSENCE_TRULY_NONE if not s.get("confirmed") else None),
        "affected_label": "사람 없이 확정 가능한 건",
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
    """One page PAST THE CURSOR, fetched the way the run fetches it.

    🔴 THE FIRST DRAFT OF THIS ASKED THE WRONG QUESTION AND WAS CAUGHT BY MEASURING IT.
    It called `preview_first_batch`, which compiles the relation's FIRST page rather than
    the page after the cursor, and reported 199 rows waiting on `dt_transfer` at the same
    moment the run itself read ZERO. That count would have sent an operator to press a
    button that did nothing - the failure this whole round is about.

    A full page means "at least this many"; a short page means "exactly this many", and
    `count_kind` carries which. Reporting a full page as a total would be the fake total
    the brief forbids, and an operator would start a long run believing it was short.
    """
    from ledger import backfill
    from ledger.setup import load_setup

    source = params["source"]
    rows, complete = backfill.rows_past_cursor(db.get_bind(), load_setup(), source)
    if not rows:
        detail = (f"'{source}' 의 커서 뒤에 읽을 행이 «없습니다». 지금 돌리면 아무것도 "
                  f"하지 않고 끝납니다.")
    elif complete:
        detail = (f"'{source}' 의 커서 뒤에 «{rows}건»이 남았습니다. 한 배치에 다 들어가는 "
                  f"양이라 이 수가 «전부»입니다.")
    else:
        detail = (f"'{source}' 의 커서 뒤에 «최소 {rows}건»이 남았습니다 — 한 페이지가 "
                  f"가득 찼으니 뒤에 더 있고, 전체가 몇 건인지는 «모릅니다». 세는 것이 곧 "
                  f"실행이라서입니다. 도는 중에 멈출 수 있습니다.")
    return {
        "affected": rows,
        "affected_label": "커서 뒤에 남은 행",
        "absence": (ABSENCE_TRULY_NONE if not rows
                    else None if complete else ABSENCE_NOT_EXHAUSTIVE),
        # EXACT only when the page came back short, because then the page IS the remainder.
        #
        # 🔴 A FULL PAGE IS `sample`, NOT `upper_bound`, AND THE NEXT READER WILL WANT TO
        # "FIX" THAT. A full page means "at least N", which is a LOWER bound, and the
        # vocabulary has no word for one. `upper_bound` would lie in the opposite
        # direction - the operator would read "at most N" when the truth may be fifty
        # thousand. `sample` is right because a page IS a sample of the remainder, and the
        # application vocabulary folds `sample` into "not exhaustive", which sets the
        # behaviour that matters: do not judge completion by this number. One case is not
        # enough to add a lower bound to a shared vocabulary.
        "count_kind": COUNT_EXACT if complete else COUNT_SAMPLE,
        "scanned": rows,
        "scan_limit": None,
        "truncated": not complete,
        "detail": detail,
        "extra": {"source": source, "rows_past_cursor": rows, "is_all": complete},
    }


def _run_ledger_backfill(db, params, log, control=None):
    from ledger import backfill

    s = backfill.run(db.get_bind(), source=params["source"],
                     checkpoint=_checkpoint(control))
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
        f"'{source}'가 {column} 범위({len(values)}개 값)의 행 {rows}건에서 쓴 원자 "
        f"{withdraw}개를 회수하고, 지금 선언으로 {remake}개를 다시 만듭니다. "
        f"두 수가 다르면 그 차이가 이번 교정의 결과입니다. "
        f"이 소스의 읽기 위치(커서)는 움직이지 않습니다.")
    if remake and not withdraw:
        # Seen for real on 2026-08-31: a run that died between the two commits left the
        # withdrawal done and the remake absent. The operator needs to be told that this
        # is a REPAIR rather than a no-op, because the headline number is 0.
        detail += (" ⚠️ 회수할 것이 0인데 다시 만들 것이 있습니다 — 이 범위의 원자가 지금 "
                   "원장에 «없다»는 뜻이고, 실행하면 채워 넣습니다.")
    if rows and not remake:
        # The refs come from the CURRENT translation, so there is nothing to aim with.
        detail += (" ⚠️ 범위에 행은 있는데 만들어지는 원자가 «0» 입니다 — 낡은 원자를 "
                   "가리킬 방법이 없어 회수도 못 합니다. 선언을 먼저 보셔야 합니다.")
    # 🔴 A SOURCE-LEVEL FACT, KEPT OUT OF THE SCOPE NUMBERS. A row that was deleted cannot
    # be named by a scope - the scope is a predicate over the relation and the relation no
    # longer carries the row - so this cannot be "orphans in this scope" and is not added
    # to anything above. It rides in `extra` with its OWN count_kind, because the scope
    # count is exact while this one is a sample on a large source, and one `count_kind`
    # cannot honestly describe both.
    orphans = backfill.count_orphan_atoms(db.get_bind(), source)
    if orphans["rows_gone"]:
        detail += (f" \u26a0\ufe0f 이 소스에는 «가리키는 행이 사라진» 원자가 "
                   f"{orphans['atoms']}건 있습니다 — 이 범위 작업과 «별개»입니다.")
    elif orphans["truncated"]:
        # A sampled zero is not an exhaustive zero, and saying "0" without saying which
        # would be read as "none exist".
        detail += (f" 행이 사라진 원자는 표본 {orphans['refs_scanned']}건에서는 "
                   f"«0» 입니다(전체 {orphans['refs_total']}건 중 표본).")
    # 🔴 THIS ONE IS CHOSEN FROM A PAIR, NOT FROM ONE NUMBER, and the entry says so in
    # advance. "Withdrew nothing" alone cannot tell `truly_none` from `already_missing` -
    # the difference is whether there is anything to put BACK, which is the other half of
    # the pair. Getting it wrong is not cosmetic: `already_missing` is the state a run that
    # died between its two commits leaves behind, and reading it as "nothing to do" is how
    # fourteen atoms stayed missing overnight on 2026-08-31.
    return {
        "affected": withdraw,
        "affected_label": "회수할 원자",
        "absence": _rescope_absence(withdraw, remake, rows),
        "count_kind": COUNT_EXACT,
        "scanned": rows,
        "scan_limit": None,
        "truncated": False,
        "detail": detail,
        "extra": dict(preview, source_orphans=orphans),
    }


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
    return {"withdrawn": s["withdrawn"], "attempted": s["attempted"],
            "inserted": s["inserted"], "deduped": s["deduped"],
            "rows_in_scope": s["rows_in_scope"], "applied": s["applied"]}


def _run_chain_replay(db, params, log, control=None):
    import chain_replay

    rule = chain_replay.find_rule(params["rule"])
    s = chain_replay.replay_rule(db, rule, apply=True, log=log,
                                 checkpoint=_checkpoint(control),
                                 business_keys=params.get("business_keys"))
    return {"cells_written": s["cells_written"], "rows_created": s["rows_created"],
            "rows_updated": s["rows_updated"], "rows_scanned": s["rows_scanned"],
            "withdrawal_candidates": s["skipped_blank_cells"]}


def _run_withdraw(db, params, log, control=None):
    import chain_replay

    s = chain_replay.withdraw_source(db, params["table"], params["source"],
                                     columns=params.get("columns"), apply=True, log=log,
                                     checkpoint=_checkpoint(control))
    return {"cells_withdrawn": s["cells_withdrawn"], "revealed": s["revealed"],
            "emptied": s["emptied"], "pinned_skipped": s["pinned_skipped"]}


def _run_enrichment_backfill(db, params, log, control=None):
    import enrichment_backfill
    from database import crud

    rule = enrichment_backfill.load_rule(params["rule"], crud.TABLE_CONFIG)
    s = enrichment_backfill.run_backfill(db, rule, apply=True, log=log,
                                         checkpoint=_checkpoint(control))
    return {"created_rows": s["created_rows"], "updated_rows": s["updated_rows"],
            "rows_scanned": s["rows_scanned"]}


def _run_enrichment_confirm(db, params, log, control=None):
    # 🔴 NO CHECKPOINT, AND THAT IS REPORTED RATHER THAN FAKED. `run_auto_confirm_sweep`
    # collects the whole queue and then hands it to `confirm_keys` in ONE call; the commits
    # are chunked a level below that, inside `apply_batch_updates`. A hook at this level
    # could therefore only stop the run BEFORE any writing began, and a cancel that works
    # only in the first instant is worse than none - an operator would press it mid-run and
    # watch it do nothing. The registry entry declares `cancellable: False` so the screen
    # does not offer the button at all.
    import enrichment_analysis

    # ignore_knob stays FALSE here: the knob is where a human consents to
    # automatic writes, and `run_auto_confirm_sweep` refuses apply without it.
    s = enrichment_analysis.run_auto_confirm_sweep(
        db, _enrichment_rule(params["rule"]), apply=True, ignore_knob=False, log=log)
    return {"confirmed": s.get("confirmed", 0), "written_cells": s.get("written_cells", 0),
            "queue_size": s.get("queue_size", 0)}


def _enrichment_rule(name):
    import enrichment_config
    from database import crud

    rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
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
        "label": "체인 규칙 소급 적용 (R1)",
        "what_is_missing": "규칙보다 오래된 데이터를 그 규칙이 한 번도 보지 못했다",
        "params": [_p("rule", help="chain rule name (GET /admin/chain/rules)"),
                   _p("business_keys", required=False, kind="csv",
                      help="replay only these rows, by business_key_val; omit for the "
                           "whole rule. This selects WHICH rows - `limit` still bounds "
                           "how many are scanned")],
        "count": _count_chain_replay,
        "run": _run_chain_replay,
        "cli": "server/scripts/chain_replay_cli.py replay <rule> --apply",
        "deletes": None,
        "reads_as": "number",
        "cancellable": True,
        "restartable": True,
        "commit_granularity": "crud.apply_batch_updates commits per 1000-item write chunk",
        "cli_only": ["replay-all (every rule in dependency order)", "--limit", "--chunk-size"],
    },
    "withdraw": {
        "label": "낡은 소스 회수 (R2)",
        "what_is_missing": "옛 규칙이 쓴 잘못된 값이 아직 우선순위 스택에서 이기고 있다",
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
        "label": "원장 전진 번역 (커서 뒤 전부)",
        "what_is_missing": "선언은 이 소스를 읽는데 커서 뒤의 행이 아직 원장에 없다",
        "params": [_p("source", help="ledger source id (GET /api/ledger/declaration)")],
        "count": _count_ledger_backfill,
        "run": _run_ledger_backfill,
        "cli": "server/ledger/backfill.py --source <source>",
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
        "label": "원장 범위 재번역",
        "what_is_missing": "고친 입력이 원장에 닿지 못해 그 범위만 낡은 값으로 남아 있다",
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
        "label": "Enrichment 파생 행 생성",
        "what_is_missing": "파생 행이 아예 만들어지지 않았다",
        "params": [_p("rule", help="enrichment rule name (enrichment_rules.json)")],
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
        "label": "단일 후보 자동 확정",
        "what_is_missing": "파생 행은 있는데 대상 셀이 비어 있다",
        "params": [_p("rule", help="enrichment rule name (enrichment_rules.json)")],
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
RUN_DONE = "done"
RUN_CANCEL_REQUESTED = "cancel_requested"
RUN_CANCELLED = "cancelled"
RUN_FAILED = "failed"


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

    def __init__(self, run_id, session_factory=None):
        self.run_id = run_id
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


def request_cancel(db, run_id: str) -> dict:
    """Ask a run to stop. Sets a value; kills nothing.

    Refuses by name on a run that has already finished, rather than reporting success for
    a request that can have no effect - "cancelled" on a finished run would tell an
    operator their data was left half-done when it was not.
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
    row.state = RUN_CANCEL_REQUESTED
    db.commit()
    logger.info("[Retroactive] cancel requested run_id=%s op=%s", run_id, row.op)
    return {"run_id": run_id, "op": row.op, "state": row.state}


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
         "params": s["params"], "cli": s["cli"], "cli_only": s["cli_only"],
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
    import chain_replay

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

    # R2's first refusal, re-stated here so the operator gets a 400 instead of a
    # queued job that dies in a worker log. `withdraw_source` refuses it AGAIN -
    # this check is convenience, that one is the safety property.
    if op == "withdraw" and out.get("source") in chain_replay.PROTECTED_SOURCES:
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

    Same mechanism as `POST /admin/auto-update/run-now`: one `DatabaseOutbox` row
    plus `NOTIFY outbox_event`, consumed by the auto-update scheduler. A retroactive
    run walks a whole table, so a synchronous handler would hold the request until
    the browser gave up - and would hold a web-server worker while doing it.
    """
    from sqlalchemy import text

    from database import models

    spec = operation(op)
    params = validate(op, params)
    run_id = uuid.uuid4().hex[:12]
    payload = {"run_id": run_id, "op": op, "params": params,
               "requested_by": requested_by or "admin"}

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
        requested_by=requested_by or "admin",
        state=RUN_QUEUED,
    ))
    db.commit()
    try:
        db.execute(text("NOTIFY outbox_event;"))
        db.commit()
    except Exception as notify_err:  # sqlite / non-PostgreSQL
        logger.debug(f"PostgreSQL NOTIFY skip or failed: {notify_err}")

    logger.info(f"[Retroactive] queued run_id={run_id} op={op} params={params}")
    return {"status": "queued", "run_id": run_id, "op": op, "params": params,
            "label": spec["label"]}


# ---------------------------------------------------------------------------
# The worker side
# ---------------------------------------------------------------------------

def execute(payload: dict, log=logger.info) -> dict:
    """Run one queued operation to completion. Called ONLY from the scheduler.

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

    control = RunControl(run_id if run_id != "?" else None)
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
        else:
            _mark_run(run_id, state=RUN_DONE, finished=True, result=out["result"])
            log(f"[Retroactive] run_id={run_id} op={op} DONE: {out['result']}")
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        out.update(status="error", error=str(e))
        _mark_run(run_id, state=RUN_FAILED, finished=True, error=str(e))
        log(f"[Retroactive] run_id={run_id} op={op} FAILED: {e}")
    finally:
        db.close()
    return out


def _mark_run(run_id, *, state, started=False, finished=False, result=None, error=None):
    """Move the run row. On its OWN session, and never fatal.

    Same reason `RunControl` holds its own: this has to survive the operation's rollback,
    because "the run failed" is exactly the moment the row must not roll back with it.
    """
    if not run_id or run_id == "?":
        return
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
        if finished:
            values["finished_at"] = now
        if result is not None:
            values["result"] = json.dumps(result, ensure_ascii=False, default=str)
        if error is not None:
            values["error"] = str(error)[:2000]
        (session.query(models.RetroactiveRun)
         .filter(models.RetroactiveRun.run_id == run_id).update(values))
        session.commit()
    except Exception as exc:                       # noqa: BLE001
        session.rollback()
        logger.debug("run row update failed for run_id=%s: %s", run_id, exc)
    finally:
        session.close()
