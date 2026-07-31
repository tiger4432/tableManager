"""The five retroactive (backfill) operations, as ONE registry.

WHAT THIS IS NOT
----------------
Not an implementation. Every operation here already exists and already defaults to
dry-run. This module is the *directory*: it names them, validates their parameters,
calls their existing dry-run for a count, and publishes an outbox event to make the
worker call their existing apply. A second executor is exactly the failure this
repository has already paid for (three `compose_map_id` implementations, three
answers).

    id                     count comes from                run comes from
    ---------------------- ------------------------------- --------------------------
    chain_replay      (R1)  chain_replay.replay_rule        same, apply=True
    withdraw          (R2)  chain_replay.count_withdrawable chain_replay.withdraw_source
    enrichment_backfill     backfill_enrichment.run_backfill same, apply=True
    enrichment_confirm      enrichment_analysis.run_auto_confirm_sweep  same, apply=True
    graph_orphans           graph_orphans.count_zero_edge_nodes  graph_orphans.run_scheduled

THE FIVE ARE NOT ONE KIND OF THING, AND SAYING THEY ARE IS A LIE THAT COSTS DATA
--------------------------------------------------------------------------------
An earlier draft of this docstring asserted, of all five, that they "commit per
page so a large run is restartable". **That is false for `graph_orphans`**, and it
is the dangerous direction to be wrong in - an operator who reads it will
interrupt a long run believing the completed chunks are safe.

VERIFIED AT SOURCE 2026-07-31, per operation:

* ``chain_replay`` (R1), ``enrichment_backfill``, ``enrichment_confirm`` write via
  ``crud.apply_batch_updates``, which commits inside each call, and each of the
  three calls it once per write chunk. Interrupting loses at most the chunk in
  flight.
* ``withdraw`` (R2) commits explicitly once per row chunk, in its own loop.
* ``graph_orphans`` does NOT. ``graph_orphans.apply_sweep`` deletes in 1000-id
  chunks but issues its single ``commit()`` **after the loop** (the only commit in
  that file). Interrupt it and the whole deletion rolls back. That is survivable
  precisely because it is a delete of derived data - nothing is half-swept, and a
  resync remints anything that should exist - but it is NOT restartable in the
  sense the other four are, and progress made is not progress kept.

Two further ways ``graph_orphans`` is not the same kind of operation, both of
which the surface has to carry so a client cannot word one confirmation for five
buttons:

* It is the only one that deletes an ENTITY (``graph_nodes`` rows). R2 also
  deletes, but it deletes one source's CLAIM on a cell (``cell_sources`` rows) and
  then recomputes and audit-logs the revealed value, so a human can see what
  happened and why. A swept node leaves no per-node record.
* Its CLI refuses ``--apply`` against a non-isolated data root without
  ``--allow-production``. That gate lives in ``scripts/graph_orphan_sweep.py``, NOT
  in ``graph_orphans.run_scheduled``, which is what this module calls and what the
  auto-update scheduler has been running daily against production all along. So the
  button grants no capability the daemon does not already exercise - but it does
  NOT reproduce the CLI's prompt, and an operator who knows the CLI will expect one.

"LIMIT" MEANS THREE DIFFERENT THINGS IN THE FIVE CLIs, SO THIS SURFACE AVOIDS THE WORD
---------------------------------------------------------------------------------------
``chain_replay_cli --limit`` bounds rows scanned. ``backfill_enrichment --limit``
bounds NEW derived identities created while the source scan runs to the end of the
table regardless. ``enrichment_insights --limit`` bounds rows examined.
``graph_orphan_sweep`` has no ``--limit`` at all (``--limit-print`` is output
formatting). One word, three meanings, and a surface that presented them under a
single "limit" control would be presenting three contracts as one.

So the parameter here is called ``scan_limit``, it is NOT exposed as an operation
parameter, it exists only to bound the PREVIEW, and it is reported back as ``null``
for the two operations whose count does not scan rows - because echoing a number
that did nothing is how a reader concludes it did something.

THE COUNT IS NOT FREE, AND THIS MODULE SAYS SO INSTEAD OF PRETENDING
--------------------------------------------------------------------
"How many would this affect?" is, for three of the five, *the dry-run itself* —
a full walk of a table through a mapper. At 10M rows that is minutes to hours and
cannot sit on a request path. Rather than ship a route that times out, every count
declares which of three kinds of number it produced:

``COUNT_EXACT``
    A cheap query answered the whole question. Cost is independent of table size.
``COUNT_SAMPLE``
    A bounded scan of the first ``limit`` rows. ``truncated`` says whether the
    population ran out before the budget did. The number is about the sample, not
    the table, and ``detail`` says so in words the client renders verbatim.
``COUNT_UPPER_BOUND``
    A cheap query answered a *superset*. The exact number needs the expensive pass
    the run itself performs. Stated as a ceiling, never as the answer.

This is the `GET /admin/enrichment/auto-confirm/dry-run` posture (F9) generalised:
that route already looks at a 200-row sample and declares `truncated` rather than
passing a partial count off as a queue depth.

WHAT THE NUMBER MEANS IS PART OF THE ANSWER
-------------------------------------------
R1 produces two counts that must never be added together: cells it WOULD WRITE
(`cells_proposed`) and cells whose value vanished under the current rule
(`skipped_blank_cells`). The second is a WITHDRAWAL CANDIDATE list — R1 refuses to
write a blank, because "the rule produces nothing here" and "the value is empty"
are different statements and only R2 can make the first. A surface that reported
their sum would overstate the writing operation with the count of the one thing R1
deliberately will not do. So `affected` is the write count alone, and the
withdrawal candidates travel in a separately named field.

THE USER LAYER IS NOT REACHABLE FROM HERE
-----------------------------------------
R2 refuses `chain_replay.PROTECTED_SOURCES` outright and skips any cell a human
pinned via `manual_priority_source`. Both refusals live in `withdraw_source` and
this module routes INTO that function, so admin cannot bypass them. The parameter
check below re-states the first refusal only so the operator gets a 400 instead of
a queued job that fails in a worker log — it reads `chain_replay.PROTECTED_SOURCES`
rather than repeating the literal, because two lists drift and one does not.
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
                                 log=lambda m: logger.debug(m))
    truncated = s["rows_scanned"] >= scan_limit
    return {
        "affected": s["cells_proposed"],
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
    import backfill_enrichment
    from database import crud

    rule = backfill_enrichment.load_rule(params["rule"], crud.TABLE_CONFIG)
    s = backfill_enrichment.run_backfill(db, rule, apply=False, scan_limit=scan_limit,
                                         log=lambda m: logger.debug(m))
    truncated = s["rows_scanned"] >= scan_limit
    return {
        "affected": s["new_combinations"],
        "affected_label": "새로 만들 파생 행",
        "count_kind": COUNT_SAMPLE,
        "scanned": s["rows_scanned"],
        "scan_limit": scan_limit,
        "truncated": truncated,
        "detail": (
            f"소스 테이블 {s['rows_scanned']}행을 표본으로 검사해 "
            f"{s['new_combinations']}개의 새 파생 행을 만듭니다. "
            f"이미 있는 파생 행 {s['already_derived']}개는 건드리지 않습니다."
        ),
        "extra": {
            "already_derived": s["already_derived"],
            "distinct_combinations": s["distinct_combinations"],
            "skipped_blank": s["skipped_blank"],
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


def _count_graph_orphans(db, params, scan_limit):
    import graph_orphans

    n = graph_orphans.count_zero_edge_nodes(db)
    return {
        "affected": n,
        "affected_label": "고아 후보 노드 (최대)",
        "count_kind": COUNT_UPPER_BOUND,
        "scanned": None,
        "scan_limit": None,   # one aggregate; no rows are walked
        "truncated": False,
        "detail": (
            f"엣지가 하나도 없는 노드가 {n}개입니다. 실제 삭제 대상은 이보다 적습니다 — "
            f"스윕은 '지금 어떤 매핑으로도 다시 만들 수 없는' 노드만 지우고, 한 라벨이 "
            f"인구의 절반 넘게 사라지면 그 라벨을 통째로 거부합니다. 그 두 판정은 매핑된 "
            f"테이블을 전부 훑어야 나오므로 요청 경로에서 계산하지 않습니다. "
            f"⚠️ 이 연산만 성격이 다릅니다: 노드를 **삭제**하고, 중간에 끊기면 "
            f"완료된 청크까지 포함해 **전부 롤백**됩니다(다른 넷은 청크 단위로 커밋되어 "
            f"이어서 재실행할 수 있습니다)."
        ),
        "extra": {
            "why_upper_bound": (
                "엣지 0개는 고아의 필요조건이지 충분조건이 아닙니다 — SplitCondition 같은 "
                "DOE 어휘는 정상적으로 엣지가 없습니다. 생산 가능성 판정이 그 차이를 "
                "만들고, 그것이 비싼 절반입니다."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Runs. apply=True on the SAME functions, called from the scheduler process.
# ---------------------------------------------------------------------------

def _run_chain_replay(db, params, log):
    import chain_replay

    rule = chain_replay.find_rule(params["rule"])
    s = chain_replay.replay_rule(db, rule, apply=True, log=log)
    return {"cells_written": s["cells_written"], "rows_created": s["rows_created"],
            "rows_updated": s["rows_updated"], "rows_scanned": s["rows_scanned"],
            "withdrawal_candidates": s["skipped_blank_cells"]}


def _run_withdraw(db, params, log):
    import chain_replay

    s = chain_replay.withdraw_source(db, params["table"], params["source"],
                                     columns=params.get("columns"), apply=True, log=log)
    return {"cells_withdrawn": s["cells_withdrawn"], "revealed": s["revealed"],
            "emptied": s["emptied"], "pinned_skipped": s["pinned_skipped"]}


def _run_enrichment_backfill(db, params, log):
    import backfill_enrichment
    from database import crud

    rule = backfill_enrichment.load_rule(params["rule"], crud.TABLE_CONFIG)
    s = backfill_enrichment.run_backfill(db, rule, apply=True, log=log)
    return {"created_rows": s["created_rows"], "updated_rows": s["updated_rows"],
            "rows_scanned": s["rows_scanned"]}


def _run_enrichment_confirm(db, params, log):
    import enrichment_analysis

    # ignore_knob stays FALSE here: the knob is where a human consents to
    # automatic writes, and `run_auto_confirm_sweep` refuses apply without it.
    s = enrichment_analysis.run_auto_confirm_sweep(
        db, _enrichment_rule(params["rule"]), apply=True, ignore_knob=False, log=log)
    return {"confirmed": s.get("confirmed", 0), "written_cells": s.get("written_cells", 0),
            "queue_size": s.get("queue_size", 0)}


def _run_graph_orphans(db, params, log):
    import graph_orphans

    # `run_scheduled` opens its own session (it is the scheduler's own entry point)
    # and already logs its outcome, refusals included.
    out = graph_orphans.run_scheduled(apply_deletions=True)
    plan = out.get("plan") or {}
    declined = plan.get("declined") or {}
    # The DECLINED set is reported, never dropped. `graph_orphans`' own docstring
    # says why: "A sweep whose skipped set is invisible reads as 'nothing to do'."
    # The CLI encodes the same thing as exit code 3, which is a BUDGET REFUSAL and
    # not a failure - so it is surfaced here as its own field rather than folded
    # into `status`, where a caller would read it as an error.
    return {
        "status": out["status"],
        "deleted": out.get("applied"),
        "blockers": out.get("blockers") or [],
        "declined_labels": sorted(declined),
        "declined_nodes": sum(d.get("orphans", 0) for d in declined.values()),
        "declined_detail": {k: {"orphans": v.get("orphans"),
                                "population": v.get("population"),
                                "reason": v.get("reason")}
                            for k, v in sorted(declined.items())},
    }


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
#: `deletes` and `restartable` exist because one confirmation wording cannot fit
#: all five: four add or overwrite values and resume from where an interruption
#: left them, and `graph_orphans` deletes rows and rolls the whole run back. Every
#: value here was checked against source on 2026-07-31 (see the module docstring),
#: not inferred from the CLI help text - the CLI help is what was wrong.
OPERATIONS = {
    "chain_replay": {
        "label": "체인 규칙 소급 적용 (R1)",
        "what_is_missing": "규칙보다 오래된 데이터를 그 규칙이 한 번도 보지 못했다",
        "params": [_p("rule", help="chain rule name (GET /admin/chain/rules)")],
        "count": _count_chain_replay,
        "run": _run_chain_replay,
        "cli": "server/scripts/chain_replay_cli.py replay <rule> --apply",
        "deletes": None,
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
        "restartable": True,
        "commit_granularity": "explicit commit per row chunk",
        "cli_only": ["--columns is available here too; nothing else exists on this path"],
    },
    "enrichment_backfill": {
        "label": "Enrichment 파생 행 생성",
        "what_is_missing": "파생 행이 아예 만들어지지 않았다",
        "params": [_p("rule", help="enrichment rule name (enrichment_rules.json)")],
        "count": _count_enrichment_backfill,
        "run": _run_enrichment_backfill,
        "cli": "server/scripts/backfill_enrichment.py <rule> --apply",
        "deletes": None,
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
        "restartable": True,
        "commit_granularity": "crud.apply_batch_updates commits per write chunk",
        "cli_only": ["--limit", "--ignore-knob (measure a rule whose knob is off)",
                     "classify / propose subcommands", "all rules at once"],
    },
    "graph_orphans": {
        "label": "그래프 고아 노드 스윕",
        "what_is_missing": "엣지도 없고 어떤 매핑으로도 다시 만들 수 없는 노드가 남아 있다",
        "params": [],
        "count": _count_graph_orphans,
        "run": _run_graph_orphans,
        "cli": "server/scripts/graph_orphan_sweep.py --apply",
        # The one that is not like the others. See the module docstring.
        "deletes": "graph_nodes rows (derived data; a resync remints what should exist)",
        "restartable": False,
        "commit_granularity": (
            "ONE commit after the whole delete loop - an interrupted run rolls back "
            "entirely, including chunks already deleted"),
        "cli_only": ["--label (restrict to labels)", "--max-fraction", "--min-population",
                     "--ignore-rejected",
                     "--allow-production (a CLI-only gate: run_scheduled, which this "
                     "button and the daily scheduler both call, has no such gate)"],
    },
}


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
    # NOTE: `scan_limit` is set by the count function, NOT here. Two of the five do
    # not scan rows at all and report null; overwriting that with the requested
    # budget would tell a reader a sample was taken when none was.
    out.setdefault("scan_limit", None)
    out.update({"op": op, "mode": "dry-run", "params": params,
                "label": spec["label"], "cli": spec["cli"],
                "deletes": spec["deletes"], "restartable": spec["restartable"],
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
    (same rule as `config_backup.run_scheduled` and `graph_orphans.run_scheduled`).
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

    db = SessionLocal()
    try:
        log(f"[Retroactive] run_id={run_id} op={op} params={params} START")
        out["result"] = spec["run"](db, params, log)
        log(f"[Retroactive] run_id={run_id} op={op} DONE: {out['result']}")
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        out.update(status="error", error=str(e))
        log(f"[Retroactive] run_id={run_id} op={op} FAILED: {e}")
    finally:
        db.close()
    return out
