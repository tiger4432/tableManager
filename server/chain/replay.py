"""Chain Replay R1 (rule re-application) + R2 (stale source withdrawal)
+ R3 (display-value recompute).

R1 - RE-APPLY A CHAIN RULE TO DATA THAT PREDATES IT
    Chain ingestion is outbox-increment driven: a rule only ever sees rows that
    changed after it was declared. Change the rule and history stays as the old
    rule left it. R1 walks the trigger table's CURRENT contents in keyset pages,
    feeds them through the REAL mapper and the REAL write path, and reports (or
    applies) the result.

    `backfill_enrichment.py` is the special case of this that already existed
    (one rule, one mapper). R1 is that shape generalised to any chain rule, with
    the same defaults: dry-run unless `--apply`, per-page commits so a large run
    is restartable, mapper output used verbatim.

R2 - WITHDRAW A STALE SOURCE'S CONTRIBUTION
    R1 alone cannot fix a rule that used to produce a WRONG value: re-running it
    writes the new value, but if the new rule produces NOTHING for that cell the
    old value just sits there, still winning the priority stack. R2 retracts a
    named source's claim on a cell so that the next source underneath becomes
    visible. This is the H2-b pattern (`_retarget_stale_edges`: what a source
    once asserted and no longer asserts must be actively removed, not left
    behind) moved from edge granularity to cell-version granularity.

    WITHDRAW AT THE LAYER, NOT THE ROW. Deleting the row, or nulling the column,
    would destroy every other source's contribution too. R2 deletes exactly one
    `cell_sources` row and then re-runs `crud.compute_priority_value` over what
    remains, writing the revealed value back to the materialised column. If two
    sources claimed the cell, the operator sees the other one - not a hole.

R1 AND R2 ARE ONE SAFETY PROPERTY FROM TWO SIDES
    R1 must never write a blank (see `SKIP_BLANK` below): "the rule no longer
    produces a value here" is not the same statement as "the value is empty",
    and only R2 can express the first one. So R1 reports the cells whose value
    disappeared as WITHDRAWAL CANDIDATES and refuses to guess. Conversely R2 is
    what makes ② (promoting a repeated judgement to a rule) retractable.

THE USER LAYER IS THE WHOLE SAFETY PROPERTY
    - R1 writes with `source_name="chain_ingestion"` (priority 4), the same
      provenance the live worker uses. A human's value is `user` (priority 0), so
      `compute_priority_value` keeps showing the human's value with no special
      case in this file. R1 does not need to know about users; the layering
      already does.
    - R2 REFUSES to withdraw `user`, and REFUSES to withdraw a source a human
      pinned via `manual_priority_source`. Those two refusals are why no path
      here can remove a value a human entered or chose. They are tested by
      injection, not asserted.

R3 - RE-MATERIALISE THE RESOLUTION OVER LAYERS THAT ARE ALREADY STORED
    R1 and R2 both change WHAT IS STORED. R3 changes nothing stored: it re-runs
    `crud.compute_priority_value` over the layers a cell already has and repairs
    the materialised display column when the answer moved. It exists because
    that answer DID move - `compute_priority_value` used to resolve a tie by dict
    insertion order, which handed every tie to the incumbent, so a corrected
    re-delivery was stored and silently discarded (measured 2026-08-11: 200 of
    200 tied cells on `assy_qa` displayed the older value). Fixing the resolver
    repairs only future writes; the already-materialised wrong values need this
    pass. It shares `_load_cell_state` and `_resolve_cell` with R2 - R2 is
    exactly R3 with one layer excluded - and it refuses to touch a cell with
    fewer than two layers, because such a cell has no tie and a cell with zero
    layers would resolve to a blank.

HOW A WITHDRAWAL BECOMES VISIBLE (not silent)
    Every cell R2 changes gets an `AuditLog` entry with the WITHDRAWN source in
    the message, `old_value` = what was displayed, `new_value` = what is revealed
    (or empty when the stack is now empty). The client's existing cell-history
    timeline reads AuditLog, so an operator who finds a cell changed can click it
    and see "withdrawn: <source>" rather than an unexplained empty cell. No new
    event, no new UI surface - the requirement is met by the primitive that
    already answers "why does this cell say what it says".
"""
import logging
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

import keyset_scan
import outbox_expand
import event_constants
# [ChainKeyGate] The same gate the live chain worker runs. Replay re-runs the same
# mappers, so it must not be able to re-create in bulk the unkeyed rows the worker refuses.
from chain import key_gate

# 🔴 [S-211 ①, 판정 358] 셀 «층»의 연산은 이 모듈의 것이 아니라 «둘 다 쓰는 것»이다.
#    `virtual_join_executor` 가 `withdraw_source` 를 쓰려고 이 모듈을 함수 안에서 import 했고,
#    그 한 줄이 네 모듈짜리 고리의 마지막 이음매였다. 연산이 둘보다 «아래»로 내려갔다.
#    ⚠️ 여기서 읽는 이름들은 «재수출»이 아니라 이 모듈이 그것들을 «쓰기» 때문이다 —
#       `ReplayRefused` 는 스무 자리에서 raise 되고, 헬퍼 셋은 다른 함수들이 부른다.
from chain.cell_layer import DEFAULT_CHUNK_SIZE, PROTECTED_SOURCES, R1_SOURCE_NAME, R2_AUDIT_SOURCE, ReplayRefused, SAMPLE_LIMIT, _claimed_filter, _load_cell_state, _resolve_cell, withdraw_source

WRITE_CHUNK = 1000



# R3 provenance for the audit trail only (it writes no cell_sources row either).
# A recompute changes NO stored fact - it only re-answers "which stored layer wins"
# and re-materialises that answer - so it must be distinguishable in the history
# from a withdrawal, which does delete a claim.
R3_AUDIT_SOURCE = "resolution_recompute"

# Upper bound on the per-cell change list a recompute keeps in memory. The AuditLog
# rows it writes are the permanent, unbounded enumeration; this only bounds what one
# call hands back to a CLI or a report. `truncated["changes"]` says when it bit.
DEFAULT_MAX_REPORT = 10000

# R1 never writes a blank value. See the module docstring: "the rule produces
# nothing here" is R2's statement to make, not R1's.
SKIP_BLANK = True





def resolve_pace(name, paces=None):
    """The shared pacing table, with this module's refusal shape.

    🔴 THE TABLE IS NOT COPIED. `server/pacing.json` already holds the paces every long job
    reads, and a second table here would be a second thing to keep in step - which is
    exactly the drift that lifting it out of `ledger/` was meant to end. What belongs to
    this module is the translation of its refusal into `ReplayRefused`, because every other
    refusal on this path is one and a caller made to catch two exception types for "you
    asked for something undeclared" will eventually catch only one.

    A UNIT HERE IS A PAGE. The table does not know that and does not need to: what a unit
    means belongs to the caller, at the boundary where ITS work is already committed.
    """
    import pacing

    try:
        return pacing.resolve(name, paces)
    except pacing.UnknownPace as exc:
        raise ReplayRefused(str(exc)) from exc


# ---------------------------------------------------------------------------
# Rule loading + ordering (the multi-rule contract)
# ---------------------------------------------------------------------------

def load_rules() -> list:
    """All chain rules via the REAL loader (`chain_ingestion_worker.load_chain_rules`).

    That loader also synthesises the enrichment dedup rules from
    enrichment_rules.json, so replay sees exactly the rule set the live worker
    sees - including enrichment. There is no second rule-loading path.
    """
    from chain.ingestion_worker import load_chain_rules
    return [r for r in load_chain_rules() if r.get("enabled", True)]


def find_rule(rule_name: str, rules: list = None, row_scoped: bool = False) -> dict:
    rules = rules if rules is not None else load_rules()
    rule = next((r for r in rules if r.get("name") == rule_name), None)
    if rule is None:
        available = ", ".join(sorted(r.get("name", "?") for r in rules)) or "<none>"
        raise ReplayRefused(f"chain rule '{rule_name}' not found or disabled; available: {available}")
    # ⛔ [S-242, narrowed by S-270] THE REFERENCE SIDE IS NOT A BACKFILL SUBJECT - WHEN THE
    # WHOLE TABLE IS THE SUBJECT. Replaying the companion walks every reference row and
    # re-finds its targets, which replaying the target side already does for every row, so
    # an operator running both pays twice for one answer. That is an argument about SCOPE:
    # with `row_ids` the operator has picked the reference rows, `replay_rule` narrows its
    # scan to them, and re-deriving those rows' targets is precisely what the live chain
    # does when they move. The decision is `replay_is_refused`, shared with the list.
    if replay_is_refused(rule, row_scoped):
        raise ReplayRefused(
            f"chain rule '{rule_name}' is the follow-up half of a declaration; replaying it "
            f"whole would redo, once per reference row, what replaying the target-side rule "
            f"already does for every row. Replay that one instead, or pick the rows to "
            f"replay this one for.")
    return rule


def is_reference_side(rule: dict) -> bool:
    """Is this a half the LOADER made - the companion that watches the table it READS?

    🔴 THE CELL, BECAUSE THE SHAPE WAS A GUESS (S-270). This asked
    `trigger == right_table != target`, and that is true of a companion AND of a sole
    declaration whose `on.table` IS the reference table - which is legal, is what the
    owner had written, and was therefore hidden from the replay list and refused by name
    with a pointer at a rule that does not exist. 「Did the loader make this as a second
    half」 is a fact the loader HAS; re-deriving it from three other cells is the
    「대리를 성질로 읽는다」 shape. `companion_rules` stamps it now.

    ⚰️ The first cut before that asked 「is it `follow_up`」 and both halves are paced, so
    it refused the very rule an operator should replay. Three readings of one question is
    what a cell ends.
    """
    from chain import rule_shape

    return bool((rule or {}).get(rule_shape.COMPANION_CELL))


def replay_is_refused(rule: dict, row_scoped: bool = False) -> bool:
    """May this rule NOT be replayed? The ONE predicate the refusal, the list and the
    route all pass through (S-270).

    🔴 THE REFERENCE SIDE IS REFUSED ONLY WHERE S-242'S ARGUMENT HOLDS, AND THAT ARGUMENT
    IS ABOUT SCOPE. It said: replaying the companion re-finds every reference row's
    targets, which replaying the target side already covers - true when the whole table
    is replayed, and FALSE when the operator picked rows. The grid's banner always sends
    `row_ids` and `replay_rule` narrows its scan to them, so replaying a chosen reference
    row is exactly what the live chain does when that row moves; the target-side rule
    triggers on a table that grid cannot select, so there is no 「run that one instead」
    available to the operator there.

    ⛔ ONE SPELLING, BECAUSE A LIST AND AN EXECUTION THAT DISAGREE IS THE S-250 DEFECT -
    a screen offering a name the backfill refuses, or hiding one it would accept.
    """
    return is_reference_side(rule) and not row_scoped


def replayable_rules_for(table: str, row_scoped: bool = False) -> list:
    """The rules an operator may replay FOR THIS TABLE - the loaded set, filtered (S-250).

    🔴 THE SAME SET THE BACKFILL ACTUALLY RUNS. The grid's list came from
    `GET /admin/chain/rules`, which hands back the FILE - so a unified join was invisible
    (it declares `on.table`, not `trigger_table`), every synthesised rule was missing
    (enrichment and the virtual joins are built by the loader, not written in that file),
    and nothing could be filtered by table at all. A list that is not the set that runs is
    a list that offers names the backfill will refuse.

    ⛔ AND THE REFERENCE SIDE IS ON IT ONLY WHEN THE CALLER SAYS IT WILL PICK ROWS
    (S-270), through `replay_is_refused` - the SAME predicate `find_rule` uses, so the
    list cannot offer a name the backfill refuses nor hide one it would accept. The grid's
    banner always sends `row_ids`, so it asks with `row_scoped=True`; a caller replaying a
    whole table asks without, and the companion stays off the list for the reason S-242
    gave.

    ⚠️ 「ENABLED」 IS ALREADY DECIDED UPSTREAM: `load_rules` keeps only enabled rules, so
    a switched-off declaration cannot appear here and this function does not re-ask.
    """
    from chain import rule_shape

    wanted = str(table or "")
    out = []
    for rule in load_rules():
        if str(rule.get("trigger_table") or "") != wanted:
            continue
        if replay_is_refused(rule, row_scoped):
            continue
        out.append({"name": rule.get("name"),
                    "trigger_table": rule.get("trigger_table"),
                    "target_table": rule.get("target_table"),
                    "kind": rule_shape.declared_kind(rule)})
    out.sort(key=lambda entry: str(entry["name"] or ""))
    return out


def order_rules(rules: list) -> list:
    """생산자가 소비자보다 먼저 — 저자는 `chain.rule_order` 다 (S-156).

    ⚰️ IT USED TO RE-RAISE A CYCLE AS `ReplayRefused`, and 판정 402 ended that: a cycle is a
    SHAPE, not an error, and the drain's `max_chain_depth` is what keeps it finite. A replay
    of rules that loop is a replay in declaration order, which is what the shared walk now
    returns - there is no refusal left for this module to translate.
    """
    from chain.rule_order import order_rules as _ordered

    return _ordered(rules)


def is_self_triggering(rule: dict) -> bool:
    return bool(rule.get("trigger_table")) and rule.get("trigger_table") == rule.get("target_table")


# ---------------------------------------------------------------------------
# R1 — rule re-application
# ---------------------------------------------------------------------------

def _payload_columns(rule: dict, model) -> list:
    """Which trigger-table columns to load into the synthetic payload.

    All declared data columns: a mapper is a pure function of the payload
    (verified: `mappers/base.payloads_to_df` flattens `data[col]["value"]` and
    the live mappers take no filepath), so the payload must carry what the outbox
    payload would have carried. Guessing a subset would make replay diverge from
    the live path in a way that only shows up on the mapper that needed the
    column we dropped.
    """
    from database import crud

    declared = list((crud.TABLE_CONFIG.get(rule["trigger_table"], {})
                     .get("column_types", {}) or {}).keys())
    have = {c.name for c in model.__table__.columns}
    return [c for c in declared if c in have]


def _to_payloads(page, columns: list, envelope: dict) -> list:
    """Synthesize the payload shape the mappers expect - THE shape, not a subset of it.

    🔴 [S-279, 판정 426] THIS USED TO BUILD TWO KEYS. `{"row_id", "data"}` is what
    `payloads_to_df` reads, and building only that was true of every mapper the repository can
    see - but mappers are written by the USER and live under a gitignored path, so 「nobody
    reads the other five」 is a claim this repository cannot make. A mapper reading
    `business_key` worked on the trigger path and returned nothing here, silently.

    ⚠️ THE FIVE ENVELOPE CELLS ARE ALL FILLABLE, which is why 「소급엔 두 칸이면 충분」 was not
    accepted: `business_key` comes off the row, `transaction_id` is this replay run's own id,
    `updated_by` names the run, `source_name` is the chain, and `timestamp` is now.
    """
    payloads = []
    for row in page:
        # row[0] is row_id (keyset_scan contract), then the requested columns, and
        # `business_key_val` last - appended by the caller for exactly this cell.
        payloads.append(outbox_expand.synthesize_payload(
            row[0], row[len(columns) + 1],
            dict(zip(columns, row[1:len(columns) + 1])),
            envelope))
    return payloads


def _refuse_unless_idempotent(rule, force):
    """⛔ [S-155, 판정 384] A REPLAY IS A RE-FEED, AND A BIGGER ONE THAN A RETRY.

    A retry hands one failed group back to the mapper; a replay hands it the trigger table's
    WHOLE CURRENT CONTENTS. So a rule that declared it cannot be fed twice is refused here by
    name, and `force` is the only way past - the operator saying it out loud.

    ⚠️ ONE AUTHOR FOR THE TWO CALLERS. `replay_all` asks BEFORE it starts, so a rule declaring
    `false` stops the run at the top rather than half way through, with earlier rules already
    applied.
    """
    if (rule or {}).get("idempotent") is False and not force:
        raise ReplayRefused(
            "chain rule '%s' declares idempotent: false, so re-running it may not "
            "reproduce its own writes - pass force to replay it anyway"
            % ((rule or {}).get("name"),))


def replay_rule(db, rule: dict, apply: bool = False, limit: int = None,
                chunk_size: int = DEFAULT_CHUNK_SIZE, log=logger.info,
                checkpoint=None, business_keys=None, row_ids=None, pace=None,
                force: bool = False) -> dict:
    """[R1] Re-run one chain rule over the trigger table's current contents.

    Dry-run (default) reads only and reports what WOULD change, including which
    cells a human's value protects and which cells lost their value (R2
    candidates). Apply commits per write chunk, so a large replay is restartable
    and idempotent - re-running recomputes the same values.
    """
    _refuse_unless_idempotent(rule, force)

    from database import crud, models, schemas
    import map_meta_registrar
    # 🪦 [S-214, 판정 370] `execute_custom_mapper` lived in the worker and this line was the
    # whole of the `replay -> worker` edge: a shared primitive in one caller's house. It moved
    # to `chain.mapper_call`, and now this function does not name either door at all - it asks
    # `rule_run` to run the rule and does not care which one answered (S-279, 판정 420 ㉡-2ⓐ).
    from chain import rule_run

    trigger_table = rule.get("trigger_table")
    target_table = rule.get("target_table")
    if not trigger_table or not target_table:
        raise ReplayRefused(f"rule '{rule.get('name')}' declares no trigger_table/target_table")

    trg_model = models.DYNAMIC_TABLES.get(trigger_table)
    if trg_model is None:
        raise ReplayRefused(
            f"trigger table model '{trigger_table}' is not initialized "
            f"(is it registered in table_config.json?)")
    if models.DYNAMIC_TABLES.get(target_table) is None:
        raise ReplayRefused(f"target table model '{target_table}' is not initialized")

    columns = _payload_columns(rule, trg_model)
    if not columns:
        raise ReplayRefused(f"trigger table '{trigger_table}' has no declared data columns")

    # SELF-WRITE GUARD (mandatory, not optional): rule 'inv' has
    # trigger_table == target_table, so without a snapshot bound the scan would
    # keep meeting rows it had just written and never terminate.
    max_row_id = None
    if is_self_triggering(rule):
        max_row_id = keyset_scan.current_max_row_id(db, trg_model)
        log(f"[replay] '{rule['name']}' is self-triggering ({trigger_table} -> {target_table}); "
            f"scan bounded at row_id <= {max_row_id!r}")

    stats = {
        "mode": "apply" if apply else "dry-run",
        # 🔴 [판정 498] READ OFF THE RESOLVER, NOT ASKED AS 「is this a builtin」. The
        # published cell keeps its name because operators and `admin/retroactive` read it;
        # what changed is where the answer comes from. A self-writing rule is named by the
        # key it registered under, which for every kind today is exactly what this said.
        # ⚠️ FILLED BELOW, because resolving can now REFUSE (a rule naming code nothing
        # implements is refused by name rather than left to throw an ImportError), and a
        # refusal about the RULE must not overtake the refusals about the operator's own
        # SELECTION - 「business_keys was given but empty」 is what they need to hear first.
        "self_writing_kind": None,
        "rule": rule.get("name"), "trigger_table": trigger_table,
        "target_table": target_table, "self_triggering": is_self_triggering(rule),
        "rows_scanned": 0, "pages": 0, "mapper_items": 0,
        "cells_proposed": 0, "cells_written": 0,
        "skipped_blank_cells": 0, "user_protected_cells": 0,
        "rows_created": 0, "rows_updated": 0,
        "map_metadata_items": 0, "scoped_batches": 0, "maps_replaced": 0,
        # [ChainKeyGate] Rows the gate refused because the mapper produced no value for
        # their key column(s). Reported alongside `skipped_blank_cells` rather than
        # folded into it: a skipped CELL still writes its row, a refused ROW writes
        # nothing, and an operator reading a replay report has to be able to tell a
        # value that went missing from a row that never existed.
        # [S-242] A `builtin:` kind WRITES ITSELF and returns what it wrote, so there are no
        # proposed cells to count for it - `rows_written` is its answer, beside the file
        # mapper's cells rather than folded into them. Two different facts under one name is
        # how a report comes to be read wrong.
        "rows_written": 0, "pages_failed": 0, "page_failures": [],
        "unkeyed_rows_refused": 0, "unkeyed_key_columns": {},
        "withdrawal_candidates": [], "samples": [],
    }

    run_id = uuid.uuid4().hex[:8]

    # 🔴 THE SELECTION GOES BESIDE `limit`, NOT INSTEAD OF IT, and it goes into the QUERY
    # rather than into a filter after the fetch. `limit` bounds how much is SCANNED;
    # this says WHICH ROWS. They are different questions and this table has both - the
    # brief is explicit that adding a fourth meaning to `limit` is how the next person
    # gets it wrong.
    #
    # `business_key_val` is the axis because `replay_rule` already carries it through its
    # stats and its samples: the operator sees those keys on the screen, so selecting by
    # anything else would mean picking rows by one name and replaying them by another.
    #
    # The column is read off the TRIGGER model, because the trigger table is what this loop
    # pages - the target is where the writes land. Measured 2026-08-31 on the trigger side
    # of all eleven declared rules: every one of them has `business_key_val`. (Measuring the
    # target side first gave the same verdict for the wrong reason, which is why the table
    # is named here rather than left to be inferred from the variable.)
    selection = None
    # 🔴 [S-254] THE GRID SENDS THE IDENTITY IT ACTUALLY HOLDS. A screen shows COLUMN
    # values; on a `composite_key_source` table the stored `business_key_val` is an
    # ASSEMBLED string (`GEN-dt_cell_key-…`) that appears in no column, so the banner sent
    # what it could see (`DT_JOB_ID PROBE-…`) and the scan matched nothing - `rows_scanned
    # 0`, no error, and an operator who pressed the button and watched nothing happen.
    # The two worlds never met. `row_id` is the one identity the grid carries for every
    # table, plain-keyed or composite.
    #
    # ⚠️ BESIDE `business_keys`, NOT INSTEAD OF IT. A plain-keyed table's operator
    # thinks in business keys, the CLI takes them, and that call is unchanged - what was
    # missing was a way to say 「these rows」 when the key is not a thing anyone can see.
    if row_ids is not None and business_keys is not None:
        # ⛔ TWO SELECTIONS ARE TWO ANSWERS TO 「which rows」. Silently AND-ing them
        # would replay the intersection, which is neither of the things the caller asked
        # for, and silently preferring one would make the other cell a lie.
        raise ReplayRefused(
            "both row_ids and business_keys were given; they are two answers to 「which "
            "rows」. Send one - the grid holds row_ids, the CLI takes business keys.")
    if row_ids is not None:
        ids = [str(value).strip() for value in row_ids if str(value).strip()]
        if not ids:
            raise ReplayRefused(
                "row_ids was given but empty; an empty selection would replay the whole "
                "rule instead of nothing. Omit it to replay everything, on purpose.")
        selection = trg_model.row_id.in_(ids)
        log(f"[replay] selection: {len(ids)} row id(s)")
    elif business_keys is not None:
        keys = [str(k).strip() for k in business_keys if str(k).strip()]
        if not keys:
            # An empty selection would scan the whole table and replay ALL of it, which is
            # the opposite of what the caller asked for. Refused by name rather than
            # treated as "no filter".
            raise ReplayRefused(
                "business_keys was given but empty; an empty selection would replay the "
                "whole rule instead of nothing. Omit it to replay everything, on purpose.")
        selection = trg_model.business_key_val.in_(keys)
        log(f"[replay] selection: {len(keys)} business key(s)")
    # [S-242] Which pass this rule goes through, decided ONCE before the first page and
    # REPORTED rather than inferred: a reader guessing from the counts would be wrong about
    # the first file mapper that legitimately proposes nothing.
    # [501 a] ASKED WITHOUT RESOLVING, AND THAT IS THE WHOLE REPAIR. `resolve` imports the
    #   operator's module - right when something is about to RUN, wrong for a caller that
    #   only DESCRIBES the rule. 498 put it here, before the first page, so a dry run of a
    #   rule whose module is absent stopped reporting and started raising. Both facts below
    #   are registrations and a dict lookup answers them; the callable is resolved by
    #   `run_rule` when a page is actually run.
    # (It also stood here TWICE - the reorder that moved it past the selection checks left
    #  the old line standing. One call, one answer.)
    # [503] THE ARM IS THE CALLING SHAPE, not 「does it write its own rows」. This branch
    #   decides whether to hand `row_ids` or `payloads`, and those two facts agree only
    #   while every registered kind writes for itself. `hands` answers it without
    #   resolving, so 501 a's repair stands.
    hands_row_ids = rule_run.hands(rule) == rule_run.HANDS_ROW_IDS
    # [판정 505] THE CELL IS NAMED FOR WHAT IT HOLDS. It was `builtin_kind`, the screen
    #   read it back as `is_builtin`, and it carries neither: it is the kind name WHEN the
    #   rule writes its own rows, and `None` otherwise. Three names for one fact, and all
    #   three said 「address」 (is it a builtin) while the value said 「property」 - which is
    #   the thing 판정 496 settled: builtin is how a rule NAMES its code, not a kind of rule.
    stats["self_writing_kind"] = rule_run.self_writing_name(rule)

    # 🪦 `module_name` / `func_name` / `is_batch` were read here and carried to the call. The
    # seat reads them off the rule itself now, so a rule that names its mapper in the ONE cell
    # (the decorator registry) no longer arrives at the door as a pair of Nones.
    # Resolved BEFORE the first page, so an undeclared pace is refused before the run has
    # written anything rather than partway through.
    pages_per_cycle, rest_seconds = resolve_pace(pace)

    # 🔴 [판정 426] `business_key_val` RIDES ALONG, LAST AND OUTSIDE `columns`. It is not a
    # declared data column, so it must not land in `data` - it is its own cell of the payload,
    # and without selecting it here retroactive could not fill the cell the live path fills.
    envelope = {"transaction_id": "chain_replay_%s" % run_id,
                "updated_by": "chain_replay_%s" % run_id,
                "source_name": R1_SOURCE_NAME,
                "timestamp": datetime.now(timezone.utc).isoformat()}
    for page in keyset_scan.iter_pages(db, trg_model,
                                       columns=([getattr(trg_model, c) for c in columns]
                                                + [trg_model.business_key_val]),
                                       condition=selection,
                                       chunk_size=chunk_size, limit=limit, max_row_id=max_row_id):
        # The batch boundary, and the only place a stop is safe: the previous page is
        # committed and this one has not begun. `checkpoint(processed)` is called at each batch boundary and returns True to stop. It is one call rather than two because both facts belong to the same instant - where the run has got to, and whether it should go on - and a stop is only safe AT that instant, where the previous batch is committed and the next has not started. Returning True breaks the loop; the operation returns its stats as usual with `stopped` set, because a cancelled run has done real work and must report it.
        if checkpoint is not None and checkpoint(stats["rows_scanned"]):
            stats["stopped"] = True
            log(f"[replay] stopped by request after {stats['rows_scanned']} rows")
            break
        stats["pages"] += 1
        stats["rows_scanned"] += len(page)
        payloads = _to_payloads(page, columns, envelope)

        # 🔴 [S-242] A `builtin:` KIND IS RUN THE WAY THE WORKER RUNS IT. `replay` knew only
        # `mapper_module`/`mapper_function`, which a builtin rule leaves empty - so
        # `importlib.import_module(None)` threw and a migrated join had NO backfill at all.
        # Live and retroactive were two doors to one rule; this is the second door learning
        # the first one's move.
        if hands_row_ids:
            # ⛔ ISOLATED ON THIS BRANCH ONLY (판정 403). One page that throws costs THAT
            # page - counted, named, and the run goes on - and the session is rolled back so
            # the next page's SELECT is not talking to an aborted transaction. The file
            # mapper's call below is byte for byte what it was: whether IT should isolate is
            # a different question, and answering it here would change a path this round
            # promised not to touch.
            page_ids = [getattr(row, "row_id", None) for row in page]
            page_ids = [row_id for row_id in page_ids if row_id]
            if not apply:
                # A dry run of a self-writing kind would have to WRITE to say what it would
                # do. It says what it would be handed instead, which is the honest answer.
                stats["mapper_items"] += len(page_ids)
                continue
            try:
                # 🔴 AND THE PAGE'S EVENTS COLLAPSE NOW (판정 421, 소유자 ⓐ). Measured before
                # wiring: `replay.py` called `outbox_mode` ZERO times, so this was the last
                # door that did not - the group path collapses, the follow-up lap collapses,
                # and a backfill of the SAME rule over the SAME rows made one event per row.
                # 「같은 기능에 두 경로」 in its quiet form: whatever watches the target table
                # saw a different shape depending on which door the write came in through,
                # and nothing raised. The scope lives in the seat, so this line does not
                # mention it - which is the point.
                outcome = rule_run.run_rule(db, rule, row_ids=page_ids)
            except Exception as page_error:                            # noqa: BLE001
                db.rollback()
                gist = str(page_error).strip().splitlines()
                stats["pages_failed"] += 1
                if len(stats["page_failures"]) < 10:
                    stats["page_failures"].append(
                        {"page": stats["pages"], "rows": len(page_ids),
                         "error": gist[-1] if gist else "(no reason)"})
                log("[replay] page %d (%d rows) failed and was skipped: %s"
                    % (stats["pages"], len(page_ids), gist[-1] if gist else "(no reason)"))
                continue
            stats["mapper_items"] += len(page_ids)
            stats["rows_written"] += int(outcome.get("written") or 0)
            if outcome.get("refusal"):
                stats["pages_failed"] += 1
                if len(stats["page_failures"]) < 10:
                    stats["page_failures"].append(
                        {"page": stats["pages"], "rows": len(page_ids),
                         "error": outcome["refusal"]})
            db.commit()
            continue

        # The REAL mapper invocation path. `is_batch` fan-out moved INTO the seat with the
        # door it belongs to, so both spellings of 「run this rule over this page」 - here and
        # in the worker's group step - are now one call and cannot drift apart.
        #
        # ⚠️ ONE MERGED ANSWER WHERE THERE WERE N. The loop below read `updates`,
        # `map_metadata_updates` and `batches` off each result; the seat concatenates those
        # three lists across its calls and every reader below takes only its own key, so the
        # totals and the envelope validation are unchanged. Measured, not assumed.
        results = [rule_run.run_rule(db, rule, payloads=payloads)]

        items, metadata_items, scoped_batches = [], [], []
        for res in results:
            if not isinstance(res, dict):
                continue
            for raw in res.get("updates") or ():
                stats["mapper_items"] += 1
                item = _normalize_mapper_item(raw)
                updates = item.get("updates") or {}
                kept = {}
                for col, val in updates.items():
                    if SKIP_BLANK and crud.is_blank_value(val):
                        # Absence is not zero. Record it as an R2 candidate and
                        # write nothing - a blank here would look like a value.
                        stats["skipped_blank_cells"] += 1
                        if len(stats["withdrawal_candidates"]) < SAMPLE_LIMIT:
                            stats["withdrawal_candidates"].append({
                                "business_key_val": item.get("business_key_val"),
                                "column": col,
                                "why": "mapper produced no value for this cell under the "
                                       "current rule; use R2 withdraw to reveal the layer "
                                       "underneath instead of writing a blank",
                            })
                        continue
                    kept[col] = val
                if not kept:
                    continue
                stats["cells_proposed"] += len(kept)
                if len(stats["samples"]) < SAMPLE_LIMIT:
                    stats["samples"].append({"business_key_val": item.get("business_key_val"),
                                             "updates": dict(list(kept.items())[:5])})
                items.append(schemas.GeneralUpdateItem(
                    business_key_val=item.get("business_key_val"),
                    updates=kept,
                    source_name=R1_SOURCE_NAME,
                    updated_by=f"chain_replay_{run_id}",
                ))

            # Replay is the same mapper contract as live chain ingestion.  S3
            # returns these two envelopes instead of ordinary `updates`; the
            # old replay loop silently discarded both, so an Admin replay could
            # report success while replacing zero DT-map cells.
            for raw in _map_metadata_outputs(res, rule, target_table):
                stats["mapper_items"] += 1
                item = _normalize_mapper_item(raw)
                updates = item["updates"]
                stats["cells_proposed"] += len(updates)
                stats["map_metadata_items"] += 1
                metadata_items.append(schemas.GeneralUpdateItem(
                    business_key_val=item.get("business_key_val"), updates=updates,
                    source_name=R1_SOURCE_NAME, updated_by=f"chain_replay_{run_id}"))

            for scope, retract, raws in _scoped_batch_outputs(res, rule, target_table):
                batch_items = []
                for raw in raws:
                    stats["mapper_items"] += 1
                    item = _normalize_mapper_item(raw)
                    updates = item["updates"] or {}
                    if not updates:
                        continue
                    stats["cells_proposed"] += len(updates)
                    batch_items.append(schemas.GeneralUpdateItem(
                        business_key_val=item.get("business_key_val"), updates=updates,
                        source_name=R1_SOURCE_NAME, updated_by=f"chain_replay_{run_id}"))
                if batch_items:
                    stats["scoped_batches"] += 1
                    scoped_batches.append((scope, retract, batch_items))

        if apply and (items or metadata_items or scoped_batches):
            # 🔴 [판정 421, 완성] THE MAPPER HALF OF RETROACTIVE GOES OUT IN THE SAME ENVELOPE.
            # ㉡-2ⓐ put the collapse in the seat, which covered the door a BUILTIN writes
            # through - and a file mapper does not write through it at all: it proposes, and
            # these lines write. So a backfill through the builtin door made one event per page
            # and a backfill of the same rows through the mapper door made one PER ROW. The
            # lead's own measurement for 판정 421 was 「replay.py calls outbox_mode ZERO times」,
            # which is both halves; the six-cell gate (판정 424 ㉠) is what caught that only one
            # of them had moved.
            #
            # Metadata first is the live worker's ordering too: absent-only map
            # registration must not synthesize a frame before the explicit
            # standard frame and valid_die_ref arrive.
            with rule_run.chain_envelope():
                if metadata_items:
                    _apply_replay_batch(db, schemas, crud, map_meta_registrar.META_TABLE,
                                        metadata_items, run_id, stats, stats["pages"],
                                        rule_name=rule.get("name"))
                for i in range(0, len(items), WRITE_CHUNK):
                    _apply_replay_batch(db, schemas, crud, target_table,
                                        items[i:i + WRITE_CHUNK],
                                        run_id, stats, stats["pages"],
                                        rule_name=rule.get("name"))
                for scope, retract, batch_items in scoped_batches:
                    _apply_replay_batch(db, schemas, crud, target_table, batch_items,
                                        run_id, stats, stats["pages"],
                                        replace_map=scope is not None, scope=scope,
                                        retract=retract, rule_name=rule.get("name"))
                    if scope is not None:
                        stats["maps_replaced"] += 1
        elif items:
            # Dry-run: count the cells a human's value would keep protected. This
            # is the number that makes "the user layer is safe" observable rather
            # than merely argued.
            stats["user_protected_cells"] += _count_user_protected(db, target_table, items)

        # 🔴 THE YIELD IS AT THE END OF THE PAGE, NOT THE TOP, AND THAT IS THE WHOLE
        # SAFETY ARGUMENT. Sleeping is only pacing if this session is holding nothing while
        # it sleeps; hold a transaction and it is OCCUPATION, which is the thing being
        # complained about rather than a cure for it. At the top of the body the page's
        # own SELECT has already run - `iter_pages` queries, then yields - so a sleep there
        # would sit on that read snapshot for `rest_seconds`. Here every write of this page
        # is committed (`crud.apply_batch_updates` commits per chunk, `apply_retraction`
        # commits its deletes) and the next page has not been read.
        #
        # The `rollback` is what makes that true in EVERY case rather than in the common
        # one: a page whose mapper produced nothing never reached a commit, so its SELECT's
        # transaction would still be open. It discards nothing - the writes are already
        # committed - and in dry-run mode it is the same belt-and-braces this function ends
        # with. `iter_pages` reads its next cursor BEFORE yielding, so the rollback cannot
        # take the keyset out from under it.
        #
        # A UNIT IS A PAGE, counted in `pages` - the same boundary the cancel checkpoint
        # uses, for the same reason. Cancel is the handle that STOPS; this is the handle
        # that SLOWS, and most of the time slowing is enough that nobody has to stop.
        if pages_per_cycle and rest_seconds and stats["pages"] % pages_per_cycle == 0:
            db.rollback()
            time.sleep(rest_seconds)

    if not apply:
        db.rollback()  # belt and braces: a dry-run holds no writes, make it structural
    return stats


def _normalize_mapper_item(raw) -> dict:
    """Mapper items may be dicts or pydantic `GeneralUpdateItem`s. One reader."""
    if isinstance(raw, dict):
        return raw
    return {"business_key_val": getattr(raw, "business_key_val", None),
            "updates": getattr(raw, "updates", None) or {}}


def _map_metadata_outputs(result: dict, rule: dict, target_table: str):
    """Validate the explicit map-metadata envelope shared with the live worker."""
    outputs = result.get("map_metadata_updates") or ()
    if outputs and not rule.get("allow_map_metadata_upsert", False):
        raise ReplayRefused(f"rule '{rule.get('name')}' returned map metadata without allow_map_metadata_upsert")
    for raw in outputs:
        item = _normalize_mapper_item(raw)
        updates = item.get("updates")
        if not isinstance(updates, dict) or updates.get("target_table") != target_table:
            raise ReplayRefused("chain map metadata update must name this rule's target table")
        if not isinstance(updates.get("map_id"), str) or not updates["map_id"]:
            raise ReplayRefused("chain map metadata update requires a non-empty map_id")
        yield item


def _scoped_batch_outputs(result: dict, rule: dict, target_table: str):
    """Validate and expose removal-scoped batches without broadening their scope.

    Yields `(scope, retract, updates)` where exactly ONE of `scope` / `retract` is set.
    `scope` removes by MAP (`replace_map`); `retract` removes by SOURCE, which is the
    only strategy that works once several sources converge on one map key. The
    envelope's validation is `dt_map_derivation.normalize_retraction_request`, shared
    with the live worker - the `replace_map` envelope already has two hand-kept copies
    and this one does not get a third.
    """
    outputs = result.get("batches") or ()
    if outputs:
        # 🔴 [C-15] 봉투 검증은 `dt_map_derivation` 의 «한 독자»가 한다 — 이 자리와 워커에
        #    «두 사본»이 있었고 그 사실이 위 docstring 에 적혀 있었다. 거절 «타입»만 여기
        #    것으로 감싼다(형제 `normalize_retraction_request` 와 같은 모양).
        try:
            dt_map_derivation.require_scoped_batches_allowed(rule)
        except ValueError as e:
            raise ReplayRefused(str(e))
    for raw in outputs:
        try:
            _target, updates, scope, retract = dt_map_derivation.normalize_scoped_batch(
                raw, rule, target_table)
        except ValueError as e:
            raise ReplayRefused(str(e))
        yield scope, retract, updates


def _apply_replay_batch(db, schemas, crud, table_name, items, run_id, stats, page,
                        replace_map=False, scope=None, retract=None, rule_name=None):
    batch = schemas.GeneralUpdateBatch(
        updates=items, transaction_id=f"chain_replay_{run_id}_{page:06d}", silent=False,
        replace_map=replace_map, scope=scope)

    # [ChainKeyGate] Replay is the same mapper contract as live chain ingestion, so it is
    # the SAME gate - this is the replay side of the one funnel, not a second copy of the
    # rule. Without it a replay could re-create in bulk exactly the unkeyed rows the live
    # worker now refuses. Note the interaction with `SKIP_BLANK` above: a blank key column
    # is stripped from `updates` there, which is precisely what makes the item unkeyable
    # here.
    kept, report = key_gate.screen(
        table_name, batch.updates, rule_names=(rule_name,) if rule_name else (),
        transaction_id=batch.transaction_id)
    if report["refused_rows"]:
        batch.updates = kept
        stats["unkeyed_rows_refused"] += report["refused_rows"]
        for col, n in report["by_column"].items():
            stats["unkeyed_key_columns"][col] = stats["unkeyed_key_columns"].get(col, 0) + n
        if not kept:
            # Same reasoning as the live worker: a `replace_map` whose every row was
            # refused would purge the map and write nothing.
            logger.error(
                "🔴 [ChainKeyGate] replay of '%s' onto '%s': every row of this batch (%d) "
                "carried no key value in %s. Nothing written, no map replaced.",
                rule_name or "<unknown rule>", table_name, report["refused_rows"],
                sorted(report["by_column"]))
            return

    results_rows, changed_cells, _logs, _deleted = crud.apply_batch_updates(db, table_name, batch)
    stats["cells_written"] += len(changed_cells or [])
    for _row, is_new in results_rows:
        if is_new:
            stats["rows_created"] += 1
        else:
            stats["rows_updated"] += 1

    # [Retraction] Same strategy and same order as the live worker: after the committed
    # write, remove what THIS SOURCE owns and no longer derives. A replay that upserted
    # without retracting would leave exactly the stale rows the live path removes, so
    # the two would disagree about the table they both claim to rebuild.
    if retract:
        import dt_map_derivation
        source_column, source_value = retract
        derived_keys = dt_map_derivation.derived_keys_of(batch.updates, table_name,
                                                         source_column)
        plan = dt_map_derivation.plan_retraction(
            db, table_name, source_column, source_value, derived_keys,
            #: 선언을 읽는 것은 «규칙을 쥔 여기»다 — 순수 함수는 값만 받는다.
            slow_warn_ms=event_constants.slow_warn_ms(
                (rule or {}).get("slow_warn_ms"),
                (rule or {}).get("name") or "<unnamed rule>"))
        logger.info("%s", dt_map_derivation.format_retraction_summary(plan))
        if plan.get("declined"):
            stats["retractions_declined"] = stats.get("retractions_declined", 0) + 1
        elif plan.get("delete_row_ids"):
            stats["rows_retracted"] = stats.get("rows_retracted", 0) + (
                dt_map_derivation.apply_retraction(db, plan))
        stats["rows_retraction_protected"] = (
            stats.get("rows_retraction_protected", 0) + plan.get("protected", 0))


def _count_user_protected(db, target_table: str, items: list) -> int:
    """How many proposed cells already carry a `user` value (so the replay would
    write its layer but NOT change what anyone sees)?

    Batched on `idx_sources_lookup_source`; the point is to state the safety
    property in numbers during a dry-run instead of only in a docstring.
    """
    from database import models

    by_key = {}
    for it in items:
        bk = getattr(it, "business_key_val", None)
        cols = list((getattr(it, "updates", None) or {}).keys())
        if bk and cols:
            by_key.setdefault(bk, set()).update(cols)
    if not by_key:
        return 0

    model = models.DYNAMIC_TABLES.get(target_table)
    if model is None:
        return 0
    bks = list(by_key)
    protected = 0
    for i in range(0, len(bks), WRITE_CHUNK):
        chunk = bks[i:i + WRITE_CHUNK]
        rows = db.query(model.row_id, model.business_key_val).filter(
            model.business_key_val.in_(chunk)).all()
        row_to_bk = {r: bk for r, bk in rows}
        if not row_to_bk:
            continue
        src = (db.query(models.CellSource.row_id, models.CellSource.column_name)
               .filter(models.CellSource.table_name == target_table,
                       models.CellSource.row_id.in_(list(row_to_bk)),
                       # The index seam: this string and the partial index's predicate
                       # have to be the same one, or the index quietly stops being used.
                       models.CellSource.source_name == models.HUMAN_SOURCE_NAME)
               .all())
        for row_id, col in src:
            if col in by_key.get(row_to_bk.get(row_id), ()):
                protected += 1
    return protected


def replay_all(db, apply: bool = False, limit: int = None,
               chunk_size: int = DEFAULT_CHUNK_SIZE, log=logger.info,
               force: bool = False) -> dict:
    """[R1] Replay every enabled rule in dependency order, each EXACTLY ONCE.

    Replaying each rule once is the second half of the loop guard: cascading
    re-fire is what turns `inventory_master -> inventory_master` into an infinite
    run. The first half is the snapshot bound inside `replay_rule`. The third,
    which needs no code here, is the live worker's existing filter - replay
    writes carry `source_name="chain_ingestion"`, and
    `process_chain_transaction_group` already drops those events, so a replay
    cannot make the running worker cascade either.
    """
    rules = order_rules(load_rules())
    # ⛔ ASKED BEFORE ANYTHING RUNS (S-155). Refusing inside the loop would stop the run with
    #    the rules above it already applied, which is a worse state than not starting.
    for rule in rules:
        _refuse_unless_idempotent(rule, force)
    log(f"[replay] order: {' -> '.join(r.get('name', '?') for r in rules)}")
    out = {"mode": "apply" if apply else "dry-run",
           "order": [r.get("name") for r in rules], "rules": []}
    for rule in rules:
        out["rules"].append(replay_rule(db, rule, apply=apply, limit=limit,
                                        chunk_size=chunk_size, log=log, force=force))
    return out


# ---------------------------------------------------------------------------
# R2 — stale source withdrawal
# ---------------------------------------------------------------------------







def count_withdrawable(db, table_name: str, source_name: str, columns: list = None) -> dict:
    """[R2 preview] How many cells would a withdrawal touch, without touching any.

    Two aggregate queries, no row materialisation, no per-cell recompute - so this
    is the half of `withdraw_source` that can sit on a request path. The first
    rides `idx_sources_by_source` (see `withdraw_source` step 1 for the measured
    before/after); the second is driven from `cell_overwrites` and is therefore
    bounded by the number of manual pins, not by `cell_sources`.

    Returns ``{cells_claimed, pinned}``. ``cells_claimed - pinned`` is an UPPER
    BOUND on `withdraw_source`'s `cells_withdrawn`, not an equality, and the two
    gaps are worth naming because a surface that reported it as exact would
    overstate the operation:

      * a `cell_sources` row whose dynamic row no longer exists is counted here and
        skipped there (`withdraw_source` looks the row up and `continue`s on None),
      * and `cells_withdrawn` is itself larger than the number of cells whose
        DISPLAYED value changes, because the revealed source may carry the same
        value (`value_unchanged`).

    Closing either gap requires the per-cell recompute that is the run itself.
    """
    from sqlalchemy import and_, func

    from database import models

    claimed = db.query(func.count()).select_from(models.CellSource).filter(
        *_claimed_filter(table_name, source_name, columns)).scalar() or 0

    # Cells this source claims AND a human pinned TO this source. Joined rather
    # than counted separately: a pin naming this source on a cell it does not
    # claim changes nothing, and counting it would understate the result.
    pinned = db.query(func.count()).select_from(models.CellSource).join(
        models.CellOverwrite,
        and_(models.CellOverwrite.table_name == models.CellSource.table_name,
             models.CellOverwrite.row_id == models.CellSource.row_id,
             models.CellOverwrite.column_name == models.CellSource.column_name),
    ).filter(
        *_claimed_filter(table_name, source_name, columns),
        models.CellOverwrite.manual_priority_source == source_name,
    ).scalar() or 0

    return {"cells_claimed": int(claimed), "pinned": int(pinned)}




# ---------------------------------------------------------------------------
# R3 - re-materialise the resolution over cells that already have their layers
# ---------------------------------------------------------------------------

def recompute_display_values(db, table_name: str, columns: list = None,
                             row_ids: list = None, apply: bool = False,
                             chunk_size: int = DEFAULT_CHUNK_SIZE, limit: int = None,
                             max_report: int = DEFAULT_MAX_REPORT,
                             log=logger.info) -> dict:
    """[R3] Re-run the resolution over stored layers and repair the materialised column.

    WHY THIS EXISTS AND WHY R1/R2 CANNOT DO IT
        The winning value is MATERIALISED: `apply_row_update_internal` ends with
        `setattr(row, col, new_val)` and every read serves that column, not the
        layers. So fixing `crud.compute_priority_value` fixes only the cells written
        AFTER the fix. Every cell that resolved wrongly in the past keeps displaying
        the wrong value until something re-delivers it - and nothing will, because
        the re-delivery is exactly what the defect discarded. R1 re-runs a MAPPER
        (it needs a rule and it writes a new layer); R2 DELETES a claim. Neither
        re-answers "which stored layer wins" without changing what is stored, and
        that is the whole operation here: **no `cell_sources` row is created,
        deleted or modified.** Only the display column moves.

    🔴 CELLS WITH FEWER THAN TWO LAYERS ARE NEVER TOUCHED, and that is a safety
        property, not an optimisation. A cell with one layer has no tie to resolve,
        so it cannot be a victim of the defect this repairs; and a cell with ZERO
        layers would resolve to `(None, None)` and this pass would BLANK a column
        that some other write path owns. The gate is the reason a full-table run
        cannot destroy data it does not understand.

    WHAT A HUMAN SEES AFTERWARDS
        Every cell whose displayed value moves gets an `AuditLog` row
        (`source_name=R3_AUDIT_SOURCE`, `updated_by="resolved:<winning source>"`,
        with old and new value), so the client's existing cell-history timeline
        explains the change. A value that changes with no history entry is the same
        class of defect as the one being repaired, so the audit write is not
        optional here and `apply` does both or neither.

    COST. One pass over `cell_sources` for the table, driven by a keyset walk of the
        table's `row_id` (`keyset_scan.iter_pages`) so memory is bounded by
        `chunk_size` and no page pays an OFFSET. The per-page source load is served
        by `idx_sources_lookup` (table_name, row_id, ...). It commits per page, so a
        large run is restartable and an interrupt loses at most the page in flight.

    Returns the stats dict; `changes` enumerates the affected cells up to
    `max_report`, and `truncated["changes"]` says whether the list ran out of budget.
    The AuditLog rows are the unbounded record.
    """
    from database import crud, models

    import keyset_scan

    model = models.DYNAMIC_TABLES.get(table_name)
    if model is None:
        raise ReplayRefused(f"table model '{table_name}' is not initialized")

    col_types = (crud.TABLE_CONFIG.get(table_name, {}).get("column_types", {}) or {})
    if columns:
        unknown = [c for c in columns if c not in col_types]
        if unknown:
            raise ReplayRefused(f"column(s) not declared on '{table_name}': {unknown}")
    wanted_cols = set(columns) if columns else None

    priority_map = crud.resolve_priority_map(table_name)

    stats = {"mode": "apply" if apply else "dry-run", "table": table_name,
             "rows_scanned": 0, "pages": 0, "cells_examined": 0,
             "pinned_examined": 0, "cells_changed": 0, "changed_by_tiebreak": 0,
             "changed_by_stale_materialisation": 0, "pinned_changed": 0,
             "changes": [],
             # 정본 — 이 자리는 «예산 비트»만 안다. 몇 개가 빠졌는지는 모르므로 `omitted` 가
             # None 이고, 그것이 0 과 «다른» 사실이다.
             "truncated": {"changes": event_constants.truncated_note(False)}}

    condition = model.row_id.in_(list(row_ids)) if row_ids else None
    tx_id = f"{R3_AUDIT_SOURCE}_{uuid.uuid4().hex[:8]}"

    # 🔴 THE OUTBOX LABEL, AND WHY IT IS NOT THE `cell_sources` LAYER.
    #
    # R3 repairs a display column with a bare `setattr`, so the ONLY thing that
    # tells the rest of the system a row moved is the outbox row that
    # `database.auto_stage_database_outbox` stages from `session.dirty`. That
    # staging reads its `source_name`/`updated_by`/`transaction_id` from the
    # context vars via `database._outbox_envelope`, and R3 used to set NONE of
    # them - so every repaired row emitted an event whose payload said
    # `source_name="user"`, `updated_by="system"` and a FRESH uuid4 per event
    # (measured on assy_qa: 5 repaired rows -> 5 events, 5 distinct tx ids).
    # Downstream that is indistinguishable from a human typing in the grid:
    # `chain_ingestion_worker._rule_accepts_event` lets it through, so repairing
    # one cell on a trigger table re-ran every mapper hanging off that table, and
    # one-uuid-per-event made N repaired rows into N serialised worker groups.
    #
    # ⚠️ THE LABEL AND THE LAYER ARE DIFFERENT FIELDS FROM DIFFERENT SOURCES, and
    # conflating them would be a far worse defect than the one this fixes.
    #   * the LAYER is `cell_sources.source_name`, written from
    #     `update_item.source_name` (crud.py, `apply_row_update_internal`),
    #   * the LABEL is the outbox payload's `source_name`, read from the
    #     `request_source` context var and NOWHERE ELSE - `_outbox_envelope` is
    #     its only reader in the whole server tree.
    # They coincide only on the batch path, because `_apply_batch_updates_once`
    # COPIES `batch.updates[0].source_name` into the context var. R3 never calls
    # it: R3 creates, alters and deletes ZERO `cell_sources` rows, which is its
    # defining property (see the docstring), so setting the context var here
    # cannot add a layer. Verified by measurement, not by reading - the sha256 of
    # the full `cell_sources` snapshot for the repaired rows is identical before
    # and after, with and without this block
    # (`test_recompute_creates_no_cell_sources_layer`).
    #
    # The provenance a human reads is NOT lost to the relabel: it lives in the
    # AuditLog rows below, which keep `source_name=R3_AUDIT_SOURCE`. The outbox
    # `source_name` is the loop-filter CHANNEL, not the provenance record.
    #
    # `R1_SOURCE_NAME` rather than a new literal, because the filter tests that
    # exact string; a second spelling would silently opt R3 back into every
    # downstream rule. This is OPT-IN, not suppression: a rule that declares
    # `allow_chain_trigger` still fires, exactly as it does for R1.
    #
    # One `tx_id` for the whole run (the same one the AuditLog rows carry, so the
    # two can be joined) collapses N serialised worker groups into one, and the
    # scope is the whole loop rather than the commit because an autoflush on any
    # query inside it - the next page's keyset query - is enough to stage.
    with crud.transaction_context(R3_AUDIT_SOURCE, tx_id, R1_SOURCE_NAME):
        for page in keyset_scan.iter_pages(db, model, condition=condition,
                                           chunk_size=chunk_size, limit=limit):
            stats["pages"] += 1
            stats["rows_scanned"] += len(page)
            page_ids = [r.row_id for r in page]
            by_id = {r.row_id: r for r in page}
            cell_sources, pins = _load_cell_state(db, table_name, page_ids)

            page_changed = False
            for cell, srcs in cell_sources.items():
                row_id, col = cell
                if wanted_cols is not None and col not in wanted_cols:
                    continue
                if col not in col_types:
                    continue
                row = by_id.get(row_id)
                if row is None:
                    continue
                # The safety gate. See the docstring: one layer has no tie, zero layers
                # would blank the column.
                if len(srcs) < 2:
                    continue

                stats["cells_examined"] += 1
                pin = pins.get(cell)
                if pin is not None:
                    stats["pinned_examined"] += 1
                decision = _resolve_cell(table_name, col_types, row, col, srcs, pin)
                if not decision["changed"]:
                    continue

                # WHY the change happened, so the report separates "this repair did it"
                # from "this cell was already out of step with its own layers". A tie is
                # the defect's signature: two or more layers sharing the winning rank,
                # which is where the old code fell through to dict order.
                top_rank = priority_map.get(decision["top_source"], 99)
                tied = sum(1 for s in srcs if priority_map.get(s, 99) == top_rank)
                reason = "tiebreak" if tied > 1 else "stale_materialisation"

                stats["cells_changed"] += 1
                if reason == "tiebreak":
                    stats["changed_by_tiebreak"] += 1
                else:
                    stats["changed_by_stale_materialisation"] += 1
                # A PINNED cell that still moves is worth its own counter and it is not a
                # contradiction: the pin decides WHICH LAYER wins (`compute_priority_value`
                # short-circuits on it), it does not freeze the materialised column. So this
                # counts cells where the display had drifted away from the layer a human
                # explicitly chose - the pin is being honoured here, not overridden. It was
                # previously called `pinned_unchanged` while being incremented on exactly the
                # cells that DID change, which read as the opposite of what it measured.
                if pin is not None:
                    stats["pinned_changed"] += 1

                if len(stats["changes"]) < max_report:
                    stats["changes"].append({
                        "row_id": row_id, "column": col,
                        "business_key_val": getattr(row, "business_key_val", None),
                        "old_value": decision["old_value"],
                        "new_value": decision["new_value"],
                        # Same value, same name (ruling 40).
                        "top_source": decision["top_source"],
                        "reason": reason,
                        "sources": sorted(srcs),
                    })
                else:
                    stats["truncated"]["changes"] = event_constants.truncated_note(
                        True, None, "report budget (max_report) reached")

                if apply:
                    setattr(row, col, decision["new_value"])
                    crud.create_audit_log(
                        db, table_name, row_id, col,
                        decision["old_value"], decision["new_value"],
                        R3_AUDIT_SOURCE, f"resolved:{decision['top_source']}",
                        transaction_id=tx_id,
                        business_key=getattr(row, "business_key_val", None))
                    page_changed = True

            if apply and page_changed:
                db.commit()

    if not apply:
        db.rollback()
    log(f"[recompute] {stats['mode']}: {stats['cells_changed']} cell(s) would change "
        f"({stats['changed_by_tiebreak']} by tiebreak, "
        f"{stats['changed_by_stale_materialisation']} already out of step) "
        f"out of {stats['cells_examined']} multi-layer cell(s) in {stats['rows_scanned']} row(s)")
    return stats
