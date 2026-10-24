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

from sqlalchemy import and_, or_, text

from chain import keyset_scan
import outbox_expand
import event_constants
# ⚰️ `from chain import key_gate` STOOD HERE, for the write batch above. The gate is not
#    retired - the WORKER runs it, on the events this module now stages, which is the single
#    spelling its own comment always claimed ("the SAME gate the live chain worker runs").

# 🔴 [S-211 ①, 판정 358] 셀 «층»의 연산은 이 모듈의 것이 아니라 «둘 다 쓰는 것»이다.
#    `virtual_join_executor` 가 `withdraw_source` 를 쓰려고 이 모듈을 함수 안에서 import 했고,
#    그 한 줄이 네 모듈짜리 고리의 마지막 이음매였다. 연산이 둘보다 «아래»로 내려갔다.
#    ⚠️ 여기서 읽는 이름들은 «재수출»이 아니라 이 모듈이 그것들을 «쓰기» 때문이다 —
#       `ReplayRefused` 는 스무 자리에서 raise 되고, 헬퍼 셋은 다른 함수들이 부른다.
from chain.cell_layer import DEFAULT_CHUNK_SIZE, PROTECTED_SOURCES, R1_SOURCE_NAME, R2_AUDIT_SOURCE, ReplayRefused, _claimed_filter, _load_cell_state, _resolve_cell, key_columns, resolve_target, withdraw_source
from error_said import told

# ⚰️ `WRITE_CHUNK = 1000` stood here - how many proposals this module wrote at once.
#    It writes none. How many rows travel in one event is `OUTBOX_COLLAPSE_CHUNK_ROWS`,
#    and how many the worker writes at once is the worker's - one answer each.



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
# ⚰️ `SKIP_BLANK = True` STOOD HERE, and with it the R2 CANDIDATE LIST.
#    🔴 WHAT THE OPERATOR LOSES, IN ONE LINE: a replay no longer hands back the list of cells
#       whose value the rule stopped producing - the 「use R2 withdraw to reveal the layer
#       underneath」 candidates. The blank is still not written (`crud.apply_batch_updates`
#       refuses one from a source that cannot mean 「emptied」), so nothing is overwritten;
#       what is gone is being TOLD which cells went quiet.
#    [소유자 2026-09-23 「ㄷ」] The judgment had two authors - this flag, keyed on the RULE, and
#    `crud`'s, keyed on the SOURCE - and they sat in different files. One remains: the one
#    beside the write.





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
    """All chain rules via the REAL loader, as it last loaded them (`loaded_chain_rules`).

    That loader stands the enrichment rules from their `derive.decide`
    declarations like any other, so replay sees exactly the rule set the live
    worker sees - including enrichment. There is no second rule-loading path.
    """
    from chain.ingestion_worker import loaded_chain_rules
    from chain import rule_shape
    return [r for r in loaded_chain_rules() if not rule_shape.is_switched_off(r)]


def find_rule(rule_name: str, rules: list = None, row_scoped: bool = False) -> dict:
    """The rule a replay NAMES - off ones too (owner 10-23 「자동 시작은 막고 리플레이로」): off is «nothing wakes
    it», and naming it is the one way it runs. The lists (`load_rules`) keep only the rules that are on."""
    from chain import rule_shape
    from chain.ingestion_worker import loaded_chain_rules

    named = rules is None
    rules = rules if rules is not None else load_rules()
    looked = rules + ([r for r in loaded_chain_rules() if rule_shape.is_switched_off(r)] if named else [])
    # its own name, else the first rule the declaration of that name stands - a decide's dedup half; its confirm half
    # is replayed by its own name, a replay's writes waking no rule (owner 09-26) (lead 10-24)
    rule = (next((r for r in looked if r.get("name") == rule_name), None)
            or next((r for r in looked if rule_shape.stood_for(r) == rule_name), None))
    if rule is None:
        available = ", ".join(sorted({r.get("name", "?") for r in rules}
                                     | {rule_shape.stood_for(r) for r in rules} - {""})) or "<none>"
        raise ReplayRefused(f"chain rule '{rule_name}' not found or disabled; available: {available}")
    # ⛔ [S-242, narrowed by S-270] A COMPANION IS NOT A WHOLE-TABLE BACKFILL SUBJECT. The
    # declaration and its companion recompute the same answer from two sides, so replaying
    # both whole pays twice. The DECLARATION's name is the whole-table replay; the companion
    # is replayed for rows an operator picked. ⚠️ [총괄 e91b96a28] Since `on` names the source,
    # the companion is the side that WRITES (`:target`) - the sentence below names the
    # declaration rather than a side, so it stays true whichever side a companion stands on.
    if replay_is_refused(rule, row_scoped):
        from chain import rule_shape

        owner = rule.get(rule_shape.COMPANION_CELL)
        raise ReplayRefused(
            f"chain rule '{rule_name}' is the second half of declaration '{owner}'; "
            f"replaying it whole redoes what replaying '{owner}' already does. Replay that "
            f"one instead, or pick the rows to replay this one for.")
    return rule


def is_companion(rule: dict) -> bool:
    """Is this a half the LOADER made - a declaration's companion rule?

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

    🔴 A COMPANION IS REFUSED ONLY WHERE S-242'S ARGUMENT HOLDS, AND THAT ARGUMENT IS
    ABOUT SCOPE: replaying a companion whole recomputes what replaying its declaration
    whole already covers - true for the whole table, FALSE when the operator picked rows.
    The grid's banner always sends `row_ids` and `replay_rule` narrows its scan to them, so
    replaying chosen rows is exactly what the live chain does when those rows move.
    (Since 총괄 e91b96a28 the companion is the `:target` half, on the table the join writes.)

    ⛔ ONE SPELLING, BECAUSE A LIST AND AN EXECUTION THAT DISAGREE IS THE S-250 DEFECT -
    a screen offering a name the backfill refuses, or hiding one it would accept.
    """
    return is_companion(rule) and not row_scoped


def replayable_rules_for(table: str, row_scoped: bool = False) -> list:
    """The rules an operator may replay FOR THIS TABLE - the loaded set, filtered (S-250).

    🔴 THE SAME SET THE BACKFILL ACTUALLY RUNS. The grid's list came from
    `GET /admin/chain/rules`, which hands back the FILE - so a unified join was invisible
    (it declares `on.table`, not `trigger_table`), every synthesised rule was missing
    (enrichment and the virtual joins are built by the loader, not written in that file),
    and nothing could be filtered by table at all. A list that is not the set that runs is
    a list that offers names the backfill will refuse.

    ⛔ AND A COMPANION IS ON IT ONLY WHEN THE CALLER SAYS IT WILL PICK ROWS
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


# ⚰️ `_to_payloads` STOOD HERE. It read a page of the trigger table into the nested payload
#    the mapper expects. `outbox_expand._synthesize_payload` does exactly that, for the
#    events this module now stages - which is what PRIMITIVES.md already described as 「파생
#    구현 둘을 하나로 접는다」, finally true with one implementation rather than two.

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


def replay_refusal(rule: dict, force: bool = False):
    """Everything a replay refuses before it reads a row, or `(trigger model, columns)`.

    Asked by the run and by the registry's judge, so a refusal arrives BEFORE a run row is
    written - the 「기록 전 판정」 075174b41 promised (총괄 69aad666e ④).
    """
    _refuse_unless_idempotent(rule, force)
    from database import models

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
    return trg_model, columns


def replay_rule(db, rule: dict, apply: bool = False, limit: int = None,
                chunk_size: int = DEFAULT_CHUNK_SIZE, log=logger.info,
                checkpoint=None, business_keys=None, row_ids=None, pace=None,
                force: bool = False, continued_from=None) -> dict:
    """[R1] Re-run one chain rule over the trigger table's current contents.

    Dry-run (default) reads only and reports what WOULD change, including which
    cells a human's value protects and which cells lost their value (R2
    candidates). Apply commits per write chunk, so a large replay is restartable
    and idempotent - re-running recomputes the same values.

    `continued_from`: the cut run this one resumes (fc1e1e385) - its pages start after that run's cursor, numbered
    on from it; rows and keys that came after its end are at the end (a key is placed by its first row).
    """
    trg_model, columns = replay_refusal(rule, force)

    from chain import ingestion_worker
    from database import crud, database, models, schemas
    import map_meta_registrar
    # 🪦 [S-214, 판정 370 · 소유자 2026-09-23] `from chain import rule_run` stood here. This
    # module asked the seat to RUN the rule; it now hands the rows over and the worker asks
    # the same seat. The edge 판정 370 was narrowing is gone rather than narrowed.

    trigger_table = rule.get("trigger_table")
    target_table = rule.get("target_table")

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
        "rule": rule.get("name"), "trigger_table": trigger_table,
        "target_table": target_table, "self_triggering": is_self_triggering(rule),
        # 🔴 WHAT A STAGING RUN CAN HONESTLY SAY. ⚰️ Fourteen cells stood here - `cells_proposed`,
        # `cells_written`, `skipped_blank_cells`, `user_protected_cells`, `rows_created`,
        # `rows_updated`, `mapper_items`, `map_metadata_items`, `scoped_batches`,
        # `maps_replaced`, `rows_written`, `unkeyed_rows_refused`, `withdrawal_candidates`,
        # `samples` - and every one of them was filled by running the rule HERE. The rule runs
        # in the worker now, so those numbers belong where the writing happens; leaving them
        # at 0 would have read as 「나온 것이 없다」, which is the one thing an operator must be
        # able to tell apart from 「안 돌았다」.
        "rows_scanned": 0, "pages": 0,
        "rows_staged": 0, "events_staged": 0,
        "pages_failed": 0, "page_failures": [],
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
    # ⚰️ [총괄 2026-09-23] `hands_row_ids` AND `stats["self_writing_kind"]` STOOD HERE, both
    #   off `rule_run.self_writing_name`. 판정 503 named what the branch really was - 「THE ARM
    #   IS THE CALLING SHAPE ... those two facts agree only while every registered kind writes
    #   for itself」 - and this round ends that agreement: nothing writes for itself, so the
    #   arm is constant. The seat had already folded the two hands into one
    #   (`handed = payloads or [{"row_id": ...}]`, 판정 562), so no caller loses a shape.
    # 🔴 THE HALF THAT DID NOT DIE WITH IT IS BELOW, ON THE LOOP: per-page isolation.


    # 🪦 `module_name` / `func_name` / `is_batch` were read here and carried to the call. The
    # seat reads them off the rule itself now, so a rule that names its mapper in the ONE cell
    # (the decorator registry) no longer arrives at the door as a pair of Nones.
    # Resolved BEFORE the first page, so an undeclared pace is refused before the run has
    # written anything rather than partway through.
    pages_per_cycle, rest_seconds = resolve_pace(pace)

    # 🔴 [판정 426] `business_key_val` RIDES ALONG, LAST AND OUTSIDE `columns`. It is not a
    # declared data column, so it must not land in `data` - it is its own cell of the payload,
    # and without selecting it here retroactive could not fill the cell the live path fills.
    # 🔴 ONE REPLAY IS ONE TRANSACTION, AND THIS IS THE LINE THAT MAKES IT TRUE. ⚠️ Its pages are groups of their
    #    own since 총괄 ㄴ 10-21 (`ingestion_worker.group_id`), so each commits alone and its label is
    #    `chain_replay_<run>·<event>`; the history folds them back to one line per run (`audit_cache.group_of`).
    #    `stage_collapsed_event` takes its envelope from `_outbox_envelope()`, which reads
    #    `request_transaction_id.get() or str(uuid.uuid4())`. This runs on the WORKER's
    #    thread, where that context var is unset - so without this every page would mint its
    #    own id, the worker would group each page as a separate transaction, and one replay
    #    would arrive as N runs carrying N different `chain_<tx>` labels. The operator asked
    #    for one thing and the screen would show N.
    #    `apply_chain_writes` sets the same var for the same reason; this is that move, on
    #    the staging side.
    # ⚠️ `request_chain_depth` IS LEFT UNSET ON PURPOSE. The staged event starts OUTSIDE the
    #    chain, exactly like a person's edit, so the hop counter begins where it begins for
    #    them and `max_chain_depth` bounds the cascade the same way.
    stage_token, run, start = None, None, {"page": 0, "end": None}
    if apply:
        from database.context import request_transaction_id
        # 🔴 "replay_<run>" AND NOT "chain_replay_<run>". The worker prefixes "chain_" to
        #    whatever it is handed (`apply_chain_writes`: `chain_tx_id = f"chain_{tx_id}"`),
        #    so this spelling makes the label that reaches `audit_logs` EXACTLY the one
        #    replay wrote before this round - `chain_replay_<run>`. An operator reading the
        #    ledger does not have to learn a new name for the same run, and the doubled
        #    `chain_chain_replay_<run>` never appears.
        stage_token = request_transaction_id.set("replay_%s" % run_id)
        from database.context import request_run_id
        run = request_run_id.get()
        start = _cursor_start(db, run, continued_from)
        stats.update(first_page=start["page"] + 1, resumed_after=start["end"])
        if not continued_from and whole_replay_of(db, run) == rule.get("name"):
            # a new whole replay of the rule closes its cut runs - their cursors and tallies (총괄 fc1e1e385)
            close_interrupted(db, rule=rule.get("name"))
            db.commit()
        open_tally(db, run, rule)
    try:
        # ⚰️ A PAYLOAD ENVELOPE STOOD HERE (`chain_replay_<run_id>` / `R1_SOURCE_NAME`), and
        #    the scan selected every declared data column to fill it. Both were for building
        #    payloads in this process. The event carries row ids; the worker reads the rows.
        # 🔴 `columns=[]` SELECTS `row_id` ALONE (`keyset_scan.iter_pages`: 「`model.row_id` is
        #    ALWAYS selected first (the cursor), so callers get it whether they asked or
        #    not」). A replay of a wide table no longer drags its data across for nothing.
        # ⚠️ `_payload_columns` ABOVE STAYS: it is the refusal 「this trigger table declares no
        #    data columns」, which is about whether the rule can say anything at all, not
        #    about what this scan needs.
        size = keyset_scan.PageSize(chunk_size)
        by_key = ingestion_worker.group_by_columns(rule) if apply else []
        if by_key:
            # a group_by rule's key on one page (소유자 10-20): the replay's events name rows, so the worker groups them
            # by the page's transaction - a key cut across pages reached the mapper in parts. A dry run stages nothing,
            # so its pages are today's (a preview reads its scan_limit rows, not every key)
            log(f"[replay] '{rule['name']}' groups by {', '.join(by_key)} - reading every picked row's key first")
            keyed = keyset_scan.keyed_rows(
                db, trg_model, by_key, lambda values: ingestion_worker.spelled_group_key(rule, trigger_table, values),
                condition=selection, max_row_id=max_row_id)
            if start["end"]:
                keyed = {key: ids for key, ids in keyed.items() if ids[0] > start["end"]}
            log(f"[replay] {sum(map(len, keyed.values()))} row(s) in {len(keyed)} key(s); a page ends between keys")
            firsts = {ids[0] for ids in keyed.values()}
            pages = keyset_scan.key_pages(keyed, size, log=log)
        else:
            after = start["end"] if apply and start["end"] else None
            pages = ([row.row_id for row in page] for page in keyset_scan.iter_pages(
                db, trg_model, columns=[],
                condition=(selection if after is None else trg_model.row_id > after if selection is None
                           else and_(selection, trg_model.row_id > after)),
                chunk_size=chunk_size, limit=limit, max_row_id=max_row_id, size=size))
        for page in pages:
            if limit is not None and stats["rows_scanned"] >= limit:
                break
            # The batch boundary, and the only place a stop is safe: the previous page is
            # committed and this one has not begun. `checkpoint(processed)` is called at each batch boundary and returns True to stop. It is one call rather than two because both facts belong to the same instant - where the run has got to, and whether it should go on - and a stop is only safe AT that instant, where the previous batch is committed and the next has not started. Returning True breaks the loop; the operation returns its stats as usual with `stopped` set, because a cancelled run has done real work and must report it.
            if checkpoint is not None and checkpoint(stats["rows_scanned"]):
                stats["stopped"] = True
                log(f"[replay] stopped by request after {stats['rows_scanned']} rows")
                break
            stats["pages"] += 1
            stats["rows_scanned"] += len(page)
            try:
                if apply:
                    # 🔴 [소유자 2026-09-23] 「작은 소급은 바로 아웃박스에 트리거와 «같은 형태»로
                    #   꽂히게」 · 「체인트리거든 소급이든 «같은 로직»으로 돌려」. So this page does
                    #   not run the rule. It writes the event an ordinary edit of these rows
                    #   would have written, and the worker drains it with the same mapper seat,
                    #   the same write door, the same envelope and the same `chain_<tx>` label.
                    # ⚰️ THE PAGE USED TO CALL `rule_run` AND WRITE FOR ITSELF - its own write
                    #   batch, its own key gate, its own transaction label. That was the second
                    #   copy of the chain, and 2026-09-17 it answered differently from the live
                    #   one: `rows_in=4 rows_out=4 written=None`, four rows proposed and dropped.
                    # 🔴 `only_rule` IS THE ONE THING AN ORDINARY EDIT DOES NOT SAY. Without it
                    #   every rule watching this table wakes, which is not what the operator
                    #   picked. The reader seat (`event_constants.only_rule_of`, asked once in
                    #   `ingestion_worker.fires`) was already built and had no writer.
                    # ⚠️ NO `columns` KEY: absent means 「모른다」 and every rule runs. The
                    #   narrowing is `only_rule`'s job - two axes doing it would make the answer
                    #   depend on which one the reader asked.
                    # 🔴 NO CHANNEL on a trigger event (총괄 c2995cdd8): it has to wake the rule
                    #   it names, and the run around it is on the retroactive channel.
                    from database.context import channel
                    number = start["page"] + stats["pages"]
                    # where it ends: a row page at its last row; a key page at its last key's first row
                    end = max(i for i in page if i in firsts) if by_key else page[-1]
                    with channel(None):
                        database.stage_collapsed_event(
                            db, "EDIT", trigger_table, page,
                            only_rule=rule.get("name"), replay=True,
                            page={"n": number, "end": end, "rows": len(page)} if run else None)
                    if run:
                        db.execute(text("UPDATE retroactive_runs SET staged_page = :n WHERE run_id = :run"),
                                   {"n": number, "run": run})
                    db.commit()
                    stats["events_staged"] += 1
                    stats["rows_staged"] += len(page)
            # ⚰️ THE PREVIEW ARM STOOD HERE - 102 lines that ran the rule to COUNT what
            #   would change without writing it. [소유자 2026-09-23] 「ㄷ」(미리보기 없이 바로
            #   실행): 안전은 큐에 뜨는 것과 회수가 잡는다. A counting copy of the write
            #   judgment is a second author for 「what would this write」, and it answered in a
            #   different place from the write itself - which is the shape this whole round
            #   exists to end.
            #   It is where `SKIP_BLANK` lived, and with it the R2 candidate list (see the
            #   tombstone at the top of this file for what the operator loses).
            except Exception as page_error:                            # noqa: BLE001
                # ⛔ ISOLATED PER PAGE (판정 403). One page that throws costs THAT page - counted,
                #   named, and the run goes on - and the session is rolled back so the next page's
                #   SELECT is not talking to an aborted transaction.
                # 🔴 IT MOVED OFF THE BRANCH AND ONTO THE LOOP (총괄 2026-09-23). It used to guard
                #   only the arm for rules that wrote their own rows. Nothing does now, so on the
                #   branch it would protect NOTHING - and the file-mapper path, the one
                #   `test_a_declared_join_can_be_backfilled_like_any_rule` called 「worth fixing and
                #   not this round's subject」, would have gone on killing a whole run per bad page.
                db.rollback()
                gist = told(page_error).strip().splitlines()
                stats["pages_failed"] += 1
                if len(stats["page_failures"]) < 10:
                    stats["page_failures"].append(
                        {"page": stats["pages"], "rows": len(page),
                         "error": gist[-1] if gist else "(no reason)"})
                log("[replay] page %d (%d rows) failed and was skipped: %s"
                    % (stats["pages"], len(page), gist[-1] if gist else "(no reason)"))
                continue


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
                size.rest(rest_seconds)
    finally:
        if stage_token is not None:
            request_transaction_id.reset(stage_token)

    if limit is not None and stats["rows_scanned"] > limit:
        log(f"[replay] limit {limit}: {stats['rows_scanned'] - limit} row(s) past it to keep the last key whole")
    if not apply:
        db.rollback()  # belt and braces: a dry-run holds no writes, make it structural
    return stats


# ⚰️ FOUR HELPERS STOOD HERE AND ALL FOUR WERE THE PREVIEW'S:
#    `_normalize_mapper_item` · `_map_metadata_outputs` · `_scoped_batch_outputs` ·
#    `_count_user_protected`. They turned a mapper's result into proposals so this module
#    could COUNT them. The worker turns the same result into WRITES, which is the only
#    reading of it that survives [소유자 2026-09-23 「ㄷ」].
#    ⚠️ `_count_user_protected` is the one with a real loss attached: it was the number that
#       made 「the user layer is safe」 observable before pressing. The guard itself is
#       untouched - it lives in `crud` and is measured by
#       `tests/test_the_cell_layer_stays_below_its_readers.py` - what is gone is seeing it
#       in advance.

# ---------------------------------------------------------------- a whole replay sweeps what it never named
#: The tally row of a whole replay (`models.ReplayNamedMap`, this `scope`): `rows` counts the staged rows its rule ran
#: on. The run is swept only when that is every row it staged (총괄 c67aa93bb ㄴ).
TALLY = ""
_WHOLE = {}     # run_id -> the rule it replays whole, or "" - a run's params never change


def whole_replay_of(db, run_id):
    """The rule run `run_id` replays WHOLE - a chain_replay with no row_ids, business_keys or limit - or None. Only
    such a run sweeps: a selection or a limit leaves maps it never asked (총괄 c67aa93bb ㄴ)."""
    if not run_id:
        return None
    if run_id not in _WHOLE:
        import json
        from database import models

        row = (db.query(models.RetroactiveRun.op, models.RetroactiveRun.params)
               .filter(models.RetroactiveRun.run_id == run_id).first())
        params = json.loads(row.params) if row is not None and row.params else {}
        whole = (row is not None and row.op == "chain_replay"
                 and not any(params.get(cell) for cell in ("row_ids", "business_keys", "limit")))
        _WHOLE[run_id] = str(params.get("rule") or "") if whole else ""
    return _WHOLE[run_id] or None


def _spelled(scope) -> str:
    import json

    return json.dumps(scope, sort_keys=True, default=str)


def record_named(db, run_id, rule, events, batches):
    """In the group's own transaction: the maps or jobs `batches` (the rule's normalized scoped batches) named and the
    staged rows of `events` it ran on - for a whole replay of this rule, nothing for any other run. A map named
    with nothing written is named too: its batch already emptied it."""
    import chain_bindings

    name = (rule or {}).get("name")
    if not chain_bindings.removes_whole_maps(rule) or whole_replay_of(db, run_id) != name:
        return
    from database import models
    from utils.payload_helper import get_payload_dict

    run_id, staged_as = root_run(db, run_id), run_id
    M = models.ReplayNamedMap
    scopes = {_spelled(scope if scope is not None else {retract[0]: retract[1]})
              for _table, _updates, scope, retract in batches if scope is not None or retract is not None}
    wanted = sorted(scopes)
    for i in range(0, len(wanted), DEFAULT_CHUNK_SIZE):
        piece = wanted[i:i + DEFAULT_CHUNK_SIZE]
        have = {s for (s,) in db.query(M.scope).filter(M.run_id == run_id, M.rule == name, M.scope.in_(piece))}
        db.add_all(M(run_id=run_id, rule=name, scope=s) for s in piece if s not in have)
        db.flush()      # the session does not autoflush: the next ask in this transaction must see these
    rows = 0
    for event in events:
        payload = get_payload_dict(event) or {}
        if (event_constants.replay_of(payload) and event_constants.run_of(payload) == staged_as
                and event_constants.only_rule_of(payload) == name):
            rows += int(payload.get("row_count") or len(payload.get("row_ids") or ()) or 1)
    if rows:
        (db.query(M).filter(M.run_id == run_id, M.rule == name, M.scope == TALLY)
         .update({M.rows: M.rows + rows}, synchronize_session=False))


def open_tally(db, run_id, rule):
    """Before a whole replay stages its first page: the tally its groups count into. None, nothing is swept."""
    import chain_bindings

    name = (rule or {}).get("name")
    if not chain_bindings.removes_whole_maps(rule) or whole_replay_of(db, run_id) != name:
        return
    from database import models

    run_id = root_run(db, run_id)
    M = models.ReplayNamedMap
    if db.query(M.run_id).filter(M.run_id == run_id, M.rule == name, M.scope == TALLY).first() is None:
        db.add(M(run_id=run_id, rule=name, scope=TALLY, rows=0))
        db.commit()


def _gone_maps(db, rule, run_id):
    """`(columns, [key tuple])` - the maps or jobs the rule's layers sit on in its target that this run's batches never
    named, by the target's own values; or `(None, why)` when it cannot be told."""
    import json
    from sqlalchemy import or_, tuple_
    import mapper_sdk
    from chain import rule_shape
    from database import crud, models

    table = rule.get("target_table")
    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        return None, "the target %s has no model in this process" % table
    came_as, keys = mapper_sdk.removal_columns(rule, table)
    named = [spelled for (spelled,) in db.query(models.ReplayNamedMap.scope).filter(
        models.ReplayNamedMap.run_id == run_id, models.ReplayNamedMap.rule == rule.get("name"),
        models.ReplayNamedMap.scope != TALLY)]
    by_columns = {}
    for spelled in named:
        scope = json.loads(spelled)
        by_columns.setdefault(tuple(scope), []).append(tuple(scope.values()))
    covered = set()
    for names, values in by_columns.items():
        columns = [getattr(model, column, None) for column in names]
        if any(c is None for c in columns):
            return None, "a batch named %s, not all columns of %s" % (", ".join(names), table)
        if len(columns) == 1:
            target, values = columns[0], [value for (value,) in values]
        else:
            target = tuple_(*columns)
        for i in range(0, len(values), DEFAULT_CHUNK_SIZE):
            covered.update(r for (r,) in db.query(model.row_id).filter(target.in_(values[i:i + DEFAULT_CHUNK_SIZE])))
    S = models.CellSource
    owned = {r for (r,) in db.query(S.row_id).filter(
        S.table_name == table, S.updated_by == rule_shape.declaration_of(rule),
        or_(S.source_name == crud.CHAIN_SOURCE, S.source_name.like(crud.CHAIN_SOURCE + " (%"))).distinct()}
    gone_rows = sorted(owned - covered)
    found = set()
    key_columns = [getattr(model, column) for column in keys]
    for i in range(0, len(gone_rows), DEFAULT_CHUNK_SIZE):
        for values in db.query(*key_columns).filter(model.row_id.in_(gone_rows[i:i + DEFAULT_CHUNK_SIZE])):
            if all(not crud.is_blank_value(v) for v in values):
                found.add(tuple(values))
    return came_as, sorted(found, key=str)


def _sweep(db, rule, run_id):
    """The gone maps, emptied by the chain's write door - `_removal_batches` with nothing written, so the batches are
    the ones a live run gives a map that produced nothing. -> the count, or a sentence why not."""
    from collections import defaultdict
    import pandas as pd
    import dt_map_derivation
    import mapper_sdk
    from chain import ingestion_worker, rule_shape
    from database import crud

    came_as, gone = _gone_maps(db, rule, run_id)
    if came_as is None:
        return gone
    if not gone:
        return 0
    table, name = rule.get("target_table"), rule.get("name")
    batches = mapper_sdk._removal_batches(rule, table, pd.DataFrame(gone, columns=came_as), pd.DataFrame(),
                                          source_name=crud.CHAIN_SOURCE, updated_by=name)["batches"]
    scoped = [dt_map_derivation.normalize_scoped_batch(batch, rule, table) for batch in batches]
    ok, error = ingestion_worker.apply_chain_writes(
        db, "replay_sweep_%s" % run_id, rule, 0, defaultdict(set, {table: {name}}), defaultdict(list), [],
        scoped, defaultdict(list, {table: [name]}), [], woken_by_a_replay=True,
        declarations_by_target=defaultdict(set, {table: {rule_shape.declaration_of(rule)}}), run=run_id)
    if not ok:
        db.rollback()
        return "the write refused: %s" % (str(error).strip().splitlines() or [""])[-1]
    return len(gone)


def sweep_finished_replays(log=logger.info, session_factory=None):
    """Each wake of the chain worker: every whole replay whose run ended and whose staged rows all ran is judged
    ONCE - its rule's maps the run's batches never named are emptied, through the chain's write door (총괄 c67aa93bb
    ㄴ). A run cancelled, failed, or with a staged row its rule did not run on is not swept and says why. Its rows
    here go either way - except a cut run's (`interrupted_runs`, 총괄 fc1e1e385): its tally stays for its Resume,
    and a resumed chain is judged at its last run, over the rows of all its runs. -> how many runs were judged."""
    import json
    from database import models
    from database.database import SessionLocal
    from chain import table_locks

    M, R, outbox = models.ReplayNamedMap, models.RetroactiveRun, models.DatabaseOutbox
    db = (session_factory or SessionLocal)()
    judged = 0
    try:
        for root, name, rows in db.query(M.run_id, M.rule, M.rows).filter(M.scope == TALLY).all():
            chain = _chain_of(db, root)
            run_id = chain[-1]
            run = db.query(R).filter(R.run_id == run_id).with_for_update().first()
            if run is not None and run.state in ("queued", "running", "cancel_requested"):
                db.rollback()
                continue
            narrow, line = event_constants.queue_line_rows(outbox, run_id)
            # whatever its state: a run released or cancelled with pages still waiting is judged once they ran - it may be
            # cut then, its tally kept for Resume (board: a dead worker's run released with 2 pages waiting lost its tally)
            if run is not None and db.query(outbox.id).filter(
                    outbox.processed_chain == False, narrow, line).first() is not None:  # noqa: E712
                db.rollback()
                continue
            if run is not None and interrupted_runs(db, run_id=run_id):
                db.rollback()           # kept for its Resume, its × or the rule's next whole replay
                continue
            result = json.loads(run.result) if run is not None and run.result else {}
            # the rows the chain's pages committed - its last run's cursor counts on from the run it resumed; a run
            # staged before the cursor counts its staged rows
            models.ensure_run_columns(db.get_bind())
            through = db.execute(text("SELECT cursor_rows FROM retroactive_runs WHERE run_id = :r"),
                                 {"r": run_id}).scalar()
            staged = through if through is not None else int(result.get("rows_staged") or 0)
            why = None
            if run is None or run.state != "done":
                why = "the run %s" % (run.state if run is not None else "is gone")
            elif result.get("pages_failed"):
                why = "%d page(s) failed to stage" % result["pages_failed"]
            elif staged != int(rows or 0):
                why = "the rule ran on %d of the %d staged row(s)" % (rows or 0, staged)
            rule = None
            if why is None:
                try:
                    rule = find_rule(name)
                except ReplayRefused as refused:
                    why = str(refused)
            if why is None:
                try:
                    with table_locks.hold(db, {rule.get("target_table"), rule.get("trigger_table")}):
                        swept = _sweep(db, rule, root)
                except table_locks.NotHeld as not_held:
                    # not judged this wake - its tally stays for the next (총괄 1ff4dcc6c ④)
                    db.rollback()
                    log("[ReplaySweep] run %s %s: not judged this wake - %s" % (run_id, name, not_held))
                    continue
                why = swept if isinstance(swept, str) else None
                if why is None:
                    log("[ReplaySweep] run %s %s: %d map(s) its batches never named emptied in %s"
                        % (" <- ".join(reversed(chain)), name, swept, rule.get("target_table")))
            if why is not None:
                log("[ReplaySweep] run %s %s: not swept - %s" % (" <- ".join(reversed(chain)), name, why))
            db.query(M).filter(M.run_id == root, M.rule == name).delete(synchronize_session=False)
            db.commit()
            judged += 1
    finally:
        db.close()
    return judged


# ---------------------------------------------------------------- a cut replay resumes after its cursor (fc1e1e385)
#: A run's cursor (`models.RUN_CURSOR_COLUMNS`): `cursor_page` the last page whose processing committed, moved only
#: from the page before it in that page's own commit (`advance_cursors`) - so a page that did not commit holds it
#: there; `cursor_end` where that page ends; `cursor_rows` the rows through it; `staged_page` the last page staged;
#: `continued_by` the run that resumed it.
_ROOT = {}      # run_id -> the first run of its continued_from chain - a run's params never change


def root_run(db, run_id):
    """The first run of `run_id`'s `continued_from` chain - whose tally a resumed whole replay counts into."""
    import json
    from database import models

    if run_id not in _ROOT:
        at, seen = run_id, set()
        while at and at not in seen:
            seen.add(at)
            row = db.query(models.RetroactiveRun.params).filter(models.RetroactiveRun.run_id == at).first()
            back = (json.loads(row.params) if row is not None and row.params else {}).get("continued_from")
            if not back:
                break
            at = back
        _ROOT[run_id] = at
    return _ROOT[run_id]


def _chain_of(db, root):
    """`[root, its continuation, ...]` - each run's `continued_by`, to the last."""
    from database import models

    models.ensure_run_columns(db.get_bind())
    chain = [root]
    while len(chain) < 1000:
        nxt = db.execute(text("SELECT continued_by FROM retroactive_runs WHERE run_id = :r"),
                         {"r": chain[-1]}).scalar()
        if not nxt or nxt in chain:
            break
        chain.append(nxt)
    return chain


def _cursor_start(db, run, continued_from):
    """Before the first page: the run's cursor at the run it resumes (`continued_from`'s), else before page 1.
    The first thing a replay does with its run row - the cursor's columns are added here, with this session holding
    nothing (an ALTER waits on any open read of the table, this process's own too). -> `{"page", "end"}`."""
    from database import models

    if not run:
        return {"page": 0, "end": None}
    db.commit()
    models.ensure_run_columns(db.get_bind())
    page, end, rows = 0, None, 0
    if continued_from:
        before = db.execute(text("SELECT cursor_page, cursor_end, cursor_rows FROM retroactive_runs "
                                 "WHERE run_id = :r"), {"r": continued_from}).first()
        if before is not None and before[0] is not None:
            page, end, rows = before[0], before[1], before[2] or 0
    db.execute(text("UPDATE retroactive_runs SET cursor_page = :p, cursor_end = :e, cursor_rows = :n, "
                    "staged_page = :p WHERE run_id = :r"), {"p": page, "e": end, "n": rows, "r": run})
    db.commit()
    return {"page": page, "end": end}


def advance_cursors(db, events):
    """In a chain group's SUCCESS commit, before it (the write seat, 총괄 fc1e1e385): each replay page these events
    finish moves its run's cursor - only from the page before it, so a page that failed or was set aside holds the
    cursor where it was. A page of several events moves it at its last, when the others ran (SUCCESS and not set
    aside - a set-aside event ends SUCCESS with its mark, `event_constants.cancelled_columns`). -> pages moved."""
    from database import models
    from utils.payload_helper import get_payload_dict

    pages, ids = {}, {event.id for event in events}
    for event in events:
        payload = get_payload_dict(event) or {}
        page, run = event_constants.replay_page_of(payload), event_constants.run_of(payload)
        if page and run and page.get("part", 1) == page.get("parts", 1):
            pages[(run, page["n"])] = page
    if not pages:
        return 0
    models.ensure_run_columns(db.get_bind())
    outbox, moved = models.DatabaseOutbox, 0
    for (run, n), page in sorted(pages.items()):
        if page.get("parts", 1) > 1 and db.query(outbox.id).filter(
                outbox.payload[event_constants.RUN_KEY].as_string() == run,
                outbox.payload[event_constants.REPLAY_PAGE_KEY]["n"].as_integer() == n,
                or_(outbox.status != "SUCCESS", outbox.payload[event_constants.CANCEL_MARK].as_string().isnot(None)),
                outbox.id.notin_(ids)).first() is not None:
            continue
        moved += db.execute(text(
            "UPDATE retroactive_runs SET cursor_page = :n, cursor_end = :end, "
            "cursor_rows = coalesce(cursor_rows, 0) + :rows WHERE run_id = :run AND cursor_page = :before"),
            {"n": n, "end": page.get("end"), "rows": int(page.get("rows") or 0), "run": run,
             "before": n - 1}).rowcount or 0
    return moved


def interrupted_runs(db, run_id=None, rule=None):
    """The replay runs cut short (총괄 fc1e1e385) - ONE JUDGEMENT, asked by the queue, Resume, × and the sweep: a run
    with a cursor, ended (done · cancelled · failed), not continued, and either cut while staging or with a page
    staged after its cursor - and none of its events waiting (those still run). A run staged before the cursor
    existed has none and is never one. -> `[{"run_id", "op", "rule", "state", "pages", "cursor_end", "total_rows",
    "finished_at", "params"}]` - `cursor_end` the last committed page's end key, `total_rows` None when not known."""
    import json
    from database import models

    if not models.ensure_run_columns(db.get_bind(), add=False):
        return []                                  # no replay has staged a page here since the cursor existed
    rows = db.execute(text(
        "SELECT run_id, op, params, state, cursor_page, staged_page, cursor_rows, cursor_end, total_rows, finished_at "
        "FROM retroactive_runs "
        "WHERE op = 'chain_replay' AND cursor_page IS NOT NULL AND continued_by IS NULL "
        "AND state IN ('done', 'cancelled', 'failed') AND (state <> 'done' OR cursor_page < staged_page)"
        + (" AND run_id = :run" if run_id else "") + " ORDER BY finished_at"),
        {"run": run_id} if run_id else {}).fetchall()
    outbox, found = models.DatabaseOutbox, []
    for run, op, params, state, done, staged, rows_done, cursor_end, total_rows, finished_at in rows:
        params = json.loads(params) if params else {}
        if rule is not None and params.get("rule") != rule:
            continue
        # its own pages, as the gate reads them (`retroactive._replay_still_waiting`) - not what their writes woke
        narrow, line = event_constants.queue_line_rows(outbox, run)
        if db.query(outbox.id).filter(outbox.processed_chain == False, narrow, line,  # noqa: E712
                                      outbox.payload[event_constants.REPLAY_KEY].as_boolean() == True).first() is not None:  # noqa: E712
            continue
        found.append({"run_id": run, "op": op, "rule": params.get("rule"), "state": state, "params": params,
                      "pages": {"done": done, "staged": staged, "rows_done": rows_done},
                      "cursor_end": cursor_end, "total_rows": total_rows, "finished_at": finished_at})
    return found


def close_interrupted(db, run_id=None, rule=None):
    """× on a cut run's line, and a new whole replay of its rule (총괄 fc1e1e385) - ONE way a cut run closes: not
    continued, its cursor and its chain's tally cleared, nothing swept. The caller commits. -> the runs closed."""
    from database import models

    closed = []
    for found in interrupted_runs(db, run_id=run_id, rule=rule):
        db.execute(text("UPDATE retroactive_runs SET cursor_page = NULL, cursor_end = NULL, cursor_rows = NULL, "
                        "staged_page = NULL WHERE run_id = :r"), {"r": found["run_id"]})
        db.query(models.ReplayNamedMap).filter(
            models.ReplayNamedMap.run_id == root_run(db, found["run_id"])).delete(synchronize_session=False)
        closed.append(found["run_id"])
        logger.info("[ReplaySweep] run %s %s: closed - not continued, its tally cleared (%s)", found["run_id"],
                    found["rule"], "× on its line" if run_id else "a new whole replay of the rule")
    return closed


def resume_run(db, run_id, by=None):
    """Resume on a cut run's line (총괄 fc1e1e385): a new run of the same params that `continued_from` it - its pages
    after the cut run's cursor - queued in the commit that marks the cut run `continued_by` it.
    -> `{"run_id", "continued_from", "from_page"}`."""
    import json
    from admin import retroactive
    from database import models

    models.ensure_run_columns(db.get_bind())          # before this session reads the table (`_cursor_start`)
    row = (db.query(models.RetroactiveRun).filter(models.RetroactiveRun.run_id == run_id)
           .with_for_update().first())
    if row is None:
        raise retroactive.RetroactiveRefused("unknown run_id '%s'" % run_id)
    found = interrupted_runs(db, run_id=run_id)
    if not found:
        raise retroactive.RetroactiveRefused(
            "run_id=%s is not a cut replay - a replay whose pages all ran, one still running or waiting in the chain "
            "queue, one already resumed or closed, or one staged before resuming existed has nothing to resume"
            % run_id)
    params = dict(json.loads(row.params) if row.params else {}, continued_from=run_id)
    new = uuid.uuid4().hex[:12]
    db.execute(text("UPDATE retroactive_runs SET continued_by = :new WHERE run_id = :r AND continued_by IS NULL"),
               {"new": new, "r": run_id})
    retroactive.publish(db, "chain_replay", params, requested_by=by, run_id=new)
    return {"run_id": new, "continued_from": run_id, "from_page": found[0]["pages"]["done"] + 1}


def replay_all(db, apply: bool = False, limit: int = None,
               chunk_size: int = DEFAULT_CHUNK_SIZE, log=logger.info,
               force: bool = False, run_one=None) -> dict:
    """[R1] Replay every enabled rule in dependency order, each EXACTLY ONCE.

    Replaying each rule once is the second half of the loop guard: cascading
    re-fire is what turns `inventory_master -> inventory_master` into an infinite
    run. The first half is the snapshot bound inside `replay_rule`. The third,
    which needs no code here, is the live worker's existing filter - replay
    writes carry `source_name="chain_ingestion"`, and
    `process_chain_transaction_group` already drops those events, so a replay
    cannot make the running worker cascade either.

    `run_one(rule) -> stats` runs one rule instead of `replay_rule` - the CLI's write goes
    through the retroactive run record that way, one record per rule, in this order.
    A rule `replay_is_refused` names is not replayed whole here either (S-270's one predicate).
    """
    rules = order_rules([r for r in load_rules() if not replay_is_refused(r)])
    # ⛔ ASKED BEFORE ANYTHING RUNS (S-155). Refusing inside the loop would stop the run with
    #    the rules above it already applied, which is a worse state than not starting.
    for rule in rules:
        _refuse_unless_idempotent(rule, force)
    log(f"[replay] order: {' -> '.join(r.get('name', '?') for r in rules)}")
    out = {"mode": "apply" if apply else "dry-run",
           "order": [r.get("name") for r in rules], "rules": []}
    for rule in rules:
        out["rules"].append(run_one(rule) if run_one else replay_rule(
            db, rule, apply=apply, limit=limit, chunk_size=chunk_size, log=log, force=force))
    return out


# ---------------------------------------------------------------------------
# R2 — stale source withdrawal
# ---------------------------------------------------------------------------







def unwritten_scope(rule_name, table_name, columns=None):
    """`(written_by, columns)` for R2: with a rule, its own layers (its declaration) on the columns of `table_name` it
    does not write - outside `chain_bindings.written_columns`, narrowed by `columns` when given (총괄 a7b67be28 ㄱ).
    Without one, `(None, columns)`. Refused when the rule writes elsewhere, lists no `target_columns`, or leaves
    no column out - an empty list here would mean every column."""
    import chain_bindings
    from chain import rule_shape

    if not rule_name:
        return None, columns
    rule = find_rule(rule_name, row_scoped=True)
    if rule.get("target_table") != table_name:
        raise ReplayRefused(f"chain rule '{rule_name}' writes '{rule.get('target_table')}', not '{table_name}'")
    written = chain_bindings.written_columns(rule)
    if written is None:
        raise ReplayRefused(f"chain rule '{rule_name}' lists no target_columns - write the list first")
    outside = [c for c in sorted(chain_bindings.declared_columns(table_name) or ())
               if c not in written and (not columns or c in columns)]
    if not outside:
        raise ReplayRefused(f"chain rule '{rule_name}' writes every column of '{table_name}' asked - nothing to withdraw")
    return (rule_shape.declaration_of(rule),), outside


def count_withdrawable(db, table_name: str, source_name: str, columns: list = None, written_by=None) -> dict:
    """[R2 preview] How many cells would a withdrawal touch, without touching any.

    Two aggregate queries, no row materialisation, no per-cell recompute - so this
    is the half of `withdraw_source` that can sit on a request path. The first
    counts the source's claims among the table's layers - the source is the lookup
    index's last column (`idx_sources_by_source` is retired, S-118; `withdraw_source`
    step 1); the second is driven from `cell_overwrites` and is therefore
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
    from sqlalchemy import and_, case, func

    from database import models

    claimed = db.query(func.count()).select_from(models.CellSource).filter(
        *_claimed_filter(table_name, source_name, columns, written_by)).scalar() or 0

    # Cells this source claims AND a human pinned TO this source. Joined rather
    # than counted separately: a pin naming this source on a cell it does not
    # claim changes nothing, and counting it would understate the result.
    pinned = db.query(func.count()).select_from(models.CellSource).join(
        models.CellOverwrite,
        and_(models.CellOverwrite.table_name == models.CellSource.table_name,
             models.CellOverwrite.row_id == models.CellSource.row_id,
             models.CellOverwrite.column_name == models.CellSource.column_name),
    ).filter(
        *_claimed_filter(table_name, source_name, columns, written_by),
        models.CellOverwrite.manual_priority_source == models.CellSource.source_name,
    ).scalar() or 0

    # Rows every layer of which this withdrawal takes - at most the shells it leaves, which go (총괄 69b8b029c):
    # a pinned cell, or a value no layer carries, keeps one.
    cs = models.CellSource
    whole = (db.query(cs.row_id).filter(cs.table_name == table_name).group_by(cs.row_id)
             .having(func.min(case((and_(*_claimed_filter(table_name, source_name, columns, written_by)), 1),
                                   else_=0)) == 1).subquery())
    emptied = db.query(func.count()).select_from(whole).scalar() or 0

    return {"cells_claimed": int(claimed), "pinned": int(pinned), "rows_emptied": int(emptied)}




# ---------------------------------------------------------------------------
# R3 - re-materialise the resolution over cells that already have their layers
# ---------------------------------------------------------------------------

def _write_resolved(db, table_name, row, col, decision, tx_id):
    """R3's write of a cell whose stored layers answer another value: the column and one history line
    (`R3_AUDIT_SOURCE`, `resolved:<winner>`). The layer fold writes the cells it moves the same way."""
    from database import crud

    setattr(row, col, decision["new_value"])
    crud.create_audit_log(db, table_name, row.row_id, col, decision["old_value"], decision["new_value"],
                          R3_AUDIT_SOURCE, f"resolved:{decision['top_source']}", transaction_id=tx_id,
                          business_key=getattr(row, "business_key_val", None))


#: Cells each of the fold's lists names, for the dry run (총괄 4dd303f01 「앞 다섯」).
FOLD_SAMPLE = 5


def fold_file_layers(db, table_name: str, apply: bool = False,
                     chunk_size: int = DEFAULT_CHUNK_SIZE, limit: int = None, pace: str = None,
                     log=logger.info, checkpoint=None) -> dict:
    """The layer fold over what one table has already stacked (총괄 225b2c658 · 8ec008914 · 4dd303f01) -
    the write path stops the stacking, this removes what stacked before it. The name is the first
    fold's: old run records and the CLI name it.

    Per cell, `crud.stacked_layers`: file layers that repeat one go; the chain's plain layer stamped
    with a source row becomes that row's (`chain_ingestion (<row>)`), or goes when that row's layer is
    there; one with no source row stays (총괄 10-11 «다»), and so does a key column's. A cell of two layers and more holding a chain row layer,
    whose layers now answer another value (a row layer ranks as the chain's), gets R3's write - the
    value and one history line. One commit per page; a stop lands between pages and a re-run finds
    only what is left.
    """
    from sqlalchemy import literal, update

    from database import crud, models

    from chain import keyset_scan

    model, col_types = resolve_target(table_name)
    keys = key_columns(table_name)
    pages_per_cycle, rest_seconds = resolve_pace(pace)
    stats = {"mode": "apply" if apply else "dry-run", "table": table_name,
             "rows_scanned": 0, "pages": 0, "cells_folded": 0, "layers_deleted": 0,
             "layers_before": 0, "layers_after": 0, "deepest_before": 0, "deepest_after": 0,
             "chain_renamed": 0, "chain_deleted": 0, "chain_unstamped": 0, "chain_differs": 0,
             "chain_copies": 0, "shown_changed": 0,
             "first": {"chain_differs": [], "chain_copies": [], "shown_changed": []}, "stopped": False}
    cells = models.CellSource.__table__.c
    # 🔴 ONE STATEMENT PER PAGE AND COLUMN, the row's layer spelled from its own origin_row_id - one UPDATE per
    #    layer took 1,196 s for 53,520 on the box's dt_log copy (the dry run, 83 s). The two halves around the
    #    origin are `merged_layer_name`'s, so the name has one spelling.
    before, after_tag = crud.merged_layer_name(crud.CHAIN_SOURCE, "\x00").split("\x00")

    def rename(column, row_ids):
        db.execute(update(models.CellSource.__table__)
                   .where(cells.table_name == table_name, cells.column_name == column,
                          cells.source_name == crud.CHAIN_SOURCE, cells.row_id.in_(row_ids))
                   .values(source_name=literal(before) + cells.origin_row_id + literal(after_tag)))

    def first(key, entry):
        if len(stats["first"][key]) < FOLD_SAMPLE:
            stats["first"][key].append(entry)

    tx_id = f"{R3_AUDIT_SOURCE}_{uuid.uuid4().hex[:8]}"
    with crud.transaction_context(R3_AUDIT_SOURCE, tx_id, R1_SOURCE_NAME):   # the label R3's writes carry
        size = keyset_scan.PageSize(chunk_size)
        for page in keyset_scan.iter_pages(db, model, columns=[], chunk_size=chunk_size,
                                           limit=limit, size=size):
            if checkpoint is not None and checkpoint(stats["rows_scanned"]):
                stats["stopped"] = True
                log(f"[fold] stopped by request after {stats['rows_scanned']} rows")
                break
            stats["pages"] += 1
            stats["rows_scanned"] += len(page)
            cell_sources, pins = _load_cell_state(db, table_name, [r[0] for r in page])
            gone, renames, asked = [], [], []
            for (row_id, col), layers in cell_sources.items():
                if col not in col_types:
                    continue
                pin = pins.get((row_id, col))
                fold = crud.stacked_layers(layers, col_types[col], table_name, pin, key=col in keys)
                drop = fold["file"] + fold["chain"]
                after = {name: entry for name, entry in layers.items() if name not in drop}
                for was, now in fold["renamed"].items():
                    after[now] = after.pop(was)
                stats["layers_before"] += len(layers)
                stats["layers_after"] += len(after)
                stats["deepest_before"] = max(stats["deepest_before"], len(layers))
                stats["deepest_after"] = max(stats["deepest_after"], len(after))
                stats["cells_folded"] += bool(fold["file"])
                stats["layers_deleted"] += len(fold["file"])
                stats["chain_deleted"] += len(fold["chain"])
                stats["chain_renamed"] += len(fold["renamed"])
                plain = layers.get(crud.CHAIN_SOURCE)
                stats["chain_unstamped"] += bool(col not in keys and plain is not None
                                                 and not plain.get("origin_row_id"))
                if fold["differs"]:
                    stats["chain_differs"] += 1
                    first("chain_differs", {"row_id": row_id, "column": col})
                if fold["copies"]:
                    stats["chain_copies"] += fold["copies"]
                    first("chain_copies", {"row_id": row_id, "column": col})
                gone.extend((table_name, row_id, col, name) for name in drop)
                renames.extend((col, row_id) for _was in fold["renamed"])
                if len(layers) > 1 and any(name != crud.CHAIN_SOURCE and crud.layer_ranks_as(name)
                                           == crud.CHAIN_SOURCE for name in after):
                    asked.append((row_id, col, after, pin))
            rows = {}
            if asked:
                rows = {row.row_id: row for row in db.query(model).filter(
                    model.row_id.in_(sorted({row_id for row_id, *_rest in asked}))).all()}
            moved = []
            for row_id, col, after, pin in asked:
                row = rows.get(row_id)
                if row is None:
                    continue
                decision = _resolve_cell(table_name, col_types, row, col, after, pin)
                if decision["changed"]:
                    stats["shown_changed"] += 1
                    first("shown_changed", {"row_id": row_id, "column": col, "old_value": decision["old_value"],
                                            "new_value": decision["new_value"], "top_source": decision["top_source"]})
                    moved.append((row, col, decision))
            if apply and (gone or renames or moved):
                crud.bulk_delete_cell_sources(db, gone)
                by_column = {}
                for col, row_id in renames:
                    by_column.setdefault(col, []).append(row_id)
                for col, row_ids in sorted(by_column.items()):
                    rename(col, row_ids)
                for row, col, decision in moved:
                    _write_resolved(db, table_name, row, col, decision, tx_id)
                db.commit()
            if pages_per_cycle and rest_seconds and stats["pages"] % pages_per_cycle == 0:
                size.rest(rest_seconds)
    if not apply:
        db.rollback()
    log(f"[fold] '{table_name}' {stats['mode']}: {stats['layers_deleted']} file layer(s) in "
        f"{stats['cells_folded']} cell(s) repeat a newer one - layers {stats['layers_before']} "
        f"-> {stats['layers_after']}, deepest cell {stats['deepest_before']} -> "
        f"{stats['deepest_after']}; chain plain layers off the keys {stats['chain_renamed']} renamed to their row's, "
        f"{stats['chain_deleted']} whose row layer is there deleted, {stats['chain_differs']} kept differing "
        f"({stats['chain_unstamped']} without a source row); {stats['chain_copies']} chain merge copies; "
        f"{stats['shown_changed']} shown value(s) move")
    return stats


#: Who deleted, in the history of each row `fold_duplicate_rows` takes.
FOLD_ROWS_BY = "fold_duplicate_rows"
#: Rows one `crud.delete_rows_batch` takes - a page; a stop and a pace land between pages.
FOLD_ROWS_PAGE = 1000
#: Keys the dry run shows, and rows of each.
FOLD_ROWS_SAMPLE_KEYS, FOLD_ROWS_SAMPLE_ROWS = 3, 4
#: Keys whose rows differ that the dry run shows, with the values.
FOLD_ROWS_DIFFERING_KEYS = 5
#: «keep» by the row's cell layers - the most stays, a tie the smaller row id (was dedupe_business_key_rows.py, 소유자
#: 10-23 ㄴ).
FOLD_KEEP_MOST_LAYERS = "most_layers"


def _layer_count(model, table_name):
    """How many cell layers the row holds - `keep` most_layers ranks by it."""
    from sqlalchemy import func, select

    from database import models

    cs = models.CellSource
    return select(func.count()).where(cs.table_name == table_name, cs.row_id == model.row_id).scalar_subquery()


def _blank_key(model, keys):
    """A row with a blank part in its key (`crud.blank_sql_condition`) - not folded: rows whose
    coordinates are blank are different rows (총괄 9c8b9f919 · 소유자 10-09 「ㅇㅇ 있어」)."""
    from sqlalchemy import String, cast, or_

    from database import crud

    return or_(*[crud.blank_sql_condition(cast(getattr(model, k), String)) for k in keys])


def _prefer_of(column, text, names=("prefer_column", "prefer_text")):
    """(column, text) of one pair, or None - both written or neither: the fold's prefer (총괄
    1d2a7e0fd) and its scope (`only_column` · `only_text`, 83c05cfbb) - one reading."""
    from database import crud

    column = None if crud.is_blank_value(column) else str(column).strip()
    text = None if crud.is_blank_value(text) else str(text).strip()
    if (column is None) != (text is None):
        raise ReplayRefused("%s and %s go together - write both or neither (given: %s)"
                            % (names[0], names[1], names[0] if column else names[1]))
    return (column, text) if column else None


def _holds(model, pair):
    """A row whose `pair[0]` column holds `pair[1]` (any case) - prefer and scope ask this one."""
    from sqlalchemy import String, cast

    return cast(getattr(model, pair[0]), String).icontains(pair[1], autoescape=True)


def _ranked_duplicates(model, keys, order, keep, prefer=None, among=(), judged=(), compared=(), by=None):
    """Every row that meets `among` (what is read), with `ranks` - a value in each key part and every labelled
    condition of `judged` met, each carried as its own column - and its place among the ranking rows of its key
    (`n`, 1 = kept), the row kept (`kept`) and how many rank (`c`): first a row whose `prefer` column holds its text
    (any case), then by `order` - `min` earliest, `max` latest - a blank `order` last; a tie, the smaller row_id
    kept. A key is its columns as stored (`p0` …), so an index on them can hand the rows over in order, and a row
    that does not rank is read in the same pass - the fold counted those apart in four more reads (총괄 5ad030347).
    `by` ranks in place of the `order` column (most first unless `keep` is min). Each `compared` column says whether
    the key's ranking rows differ in it (`d0` …, `differs` any) - a blank is no value - and carries its text (`v0` …)."""
    from sqlalchemy import String, and_, case, cast, false, func, literal, not_, null, or_, select

    from database import crud

    parts = [getattr(model, k) for k in keys]
    by = getattr(model, order) if by is None else by
    blank = _blank_key(model, keys)
    ranks = and_(not_(blank), *[condition.element for condition in judged])
    preferred = _holds(model, prefer) if prefer else false()
    ranked = [case((ranks, 0), else_=1), case((preferred, 0), else_=1),
              case((crud.blank_sql_condition(cast(by, String)), 1), else_=0),
              by.asc() if keep == "min" else by.desc(), model.row_id.asc()]
    texts = [case((crud.blank_sql_condition(cast(getattr(model, column), String)), null()),
                  else_=cast(getattr(model, column), String)) for column in compared]

    def over_key(aggregate):
        return aggregate.filter(ranks).over(partition_by=parts)
    differ = [or_(over_key(func.min(t)).is_distinct_from(over_key(func.max(t))),
                  and_(over_key(func.count(t)) > 0, over_key(func.count(t)) < over_key(func.count())))
              for t in texts]
    return select(model.row_id.label("row_id"), by.label("order_value"),
                  (getattr(model, prefer[0]) if prefer else literal(None)).label("prefer_value"),
                  case((preferred, 1), else_=0).label("preferred"),
                  *[part.label("p%d" % i) for i, part in enumerate(parts)],
                  *[cast(part, String).label("k%d" % i) for i, part in enumerate(parts)],
                  blank.label("blank_key"), ranks.label("ranks"), *judged,
                  func.count().filter(ranks).over(partition_by=parts, order_by=ranked, rows=(None, 0)).label("n"),
                  func.first_value(model.row_id).over(partition_by=parts, order_by=ranked).label("kept"),
                  func.count().filter(ranks).over(partition_by=parts).label("c"),
                  (or_(*differ) if differ else false()).label("differs"),
                  *[d.label("d%d" % i) for i, d in enumerate(differ)],
                  *[t.label("v%d" % i) for i, t in enumerate(texts)]).where(*among).subquery()


def fold_target(table_name, keys, order, keep="min", prefer_column=None, prefer_text=None,
                mark_column=None, only_column=None, only_text=None):
    """What a fold names, judged once - by the fold and by the operation's judge before anything is
    recorded. -> (keys, model, prefer pair, scope pair, mark column) or `ReplayRefused`."""
    from database import crud

    keys = [k for k in (keys or []) if k]
    if not keys:
        raise ReplayRefused("name at least one key column - the rows that fold share its values")
    if keep not in ("min", "max", FOLD_KEEP_MOST_LAYERS):
        raise ReplayRefused(f"keep is 'min' (the earliest order), 'max' (the latest) or '{FOLD_KEEP_MOST_LAYERS}' "
                            f"(the row with the most cell layers), not '{keep}'")
    order = None if crud.is_blank_value(order) else str(order).strip()
    if (keep == FOLD_KEEP_MOST_LAYERS) == bool(order):
        raise ReplayRefused(f"keep '{FOLD_KEEP_MOST_LAYERS}' ranks by cell layers - leave order empty"
                            if order else "name the order column - it picks the row to keep")
    prefer = _prefer_of(prefer_column, prefer_text)
    scope = _prefer_of(only_column, only_text, ("only_column", "only_text"))
    mark = None if crud.is_blank_value(mark_column) else str(mark_column).strip()
    model, col_types = resolve_target(table_name, list(keys) + ([order] if order else []) + ([prefer[0]] if prefer else [])
                                      + ([scope[0]] if scope else []) + ([mark] if mark else []))
    if mark and col_types.get(mark) != "string":
        raise ReplayRefused(f"mark_column '{mark}' is a {col_types.get(mark)} column - the mark is text, "
                            f"declare a string column for it")
    return keys, model, prefer, scope, mark


def fold_duplicate_rows(db, table_name: str, keys, order: str, keep: str = "min",
                        apply: bool = False, pace: str = None, log=logger.info,
                        checkpoint=None, prefer_column=None, prefer_text=None,
                        mark_column=None, only_column=None, only_text=None, only_identical=False) -> dict:
    """Per key one row stays - the first by `order`, or by its cell layers with keep most_layers (`_ranked_duplicates`; a row whose
    `prefer_column` holds `prefer_text` before the rest; a row with a blank key part is not
    touched, `_blank_key`) - and the rest are
    deleted through the product's delete door, `crud.delete_rows_batch`, a page at a time, so
    their layers, holds and ledger atoms are taken back as for a deletion from the grid (총괄
    d72dc0283 · 소유자 10-09 「해당 dtwaferid 중에서 최소 시간으로 접으면 되긴 함」). The rows to
    go are chosen once; a stop lands between pages and a re-run finds only what is left.

    `mark_column` (총괄 016a766af, 소유자 「접는 거 아예 삭제하지 말고」): the rest are not deleted - each
    gets «folded into <the kept row>» there through the product's write door, and every rule on the
    table whose `exclude` names that column runs on them through the replay door (no channel ·
    `only_rule` · EDIT): it is not handed them any more, so what they fed is taken back (`edited`).
    A marked row ranks no more. `only_column` · `only_text` (83c05cfbb): only rows whose column holds
    the text rank - the rest stay as they are, counted.

    A key whose ranking rows differ in a declared column outside the keys is counted, by column, with the first keys'
    values - whether it folds or not; `only_identical` (소유자 10-23, was dedupe_business_key_rows.py's default) leaves
    those keys as they are.
    """
    from sqlalchemy import String, cast, false, func, not_, select

    from database import crud

    keys, model, prefer, scope, mark = fold_target(table_name, keys, order, keep, prefer_column, prefer_text,
                                                   mark_column, only_column, only_text)
    pages_per_cycle, rest_seconds = resolve_pace(pace)
    judged = [func.coalesce(_holds(model, scope), false()).label("in_scope")] if scope else []
    if mark:
        judged.append(not_(crud.not_blank_sql_condition(cast(getattr(model, mark), String))).label("unmarked"))
    # the declared columns but the fold's keys, the mark and the table's own key - each row's identity, as row_id is
    config = crud.TABLE_CONFIG.get(table_name) or {}
    identity = set(config.get("composite_key_source") or []) | {config.get("business_key")}
    compared = [column for column in config.get("column_types") or {} if column in model.__table__.columns
                and column not in keys and column != mark and column not in identity]
    ranked = _ranked_duplicates(model, keys, order, keep, prefer, judged=judged, compared=compared,
                                by=_layer_count(model, table_name) if keep == FOLD_KEEP_MOST_LAYERS else None)
    said_as = order or "layers"
    woken = _excluding_by(table_name, mark) if mark else []
    recounts = _recounting(woken, mark) if woken else []
    found = _key_index(db, table_name, keys)
    index = ("%s%s" % (found["name"], "" if found["state"] in ("present", "unknown") else " (%s)" % found["state"])
             if found else "none - declare one on (%s) in the table's indexes" % ", ".join(keys))
    stats = {"mode": "apply" if apply else "dry-run", "table": table_name,
             "rows": 0, "keys_folded": 0, "keys_preferred": 0, "rows_to_mark" if mark else "rows_to_delete": 0,
             "rows_kept": 0, "rows_blank_key": 0, "rows_out_of_scope": 0, "rows_already_marked": 0,
             "rows_marked" if mark else "rows_deleted": 0, "pages": 0, "stopped": False, "sample": [],
             "rules_woken": [rule.get("name") for rule in woken], "rules_recounting": [
                 rule.get("name") for rule in recounts], "key_index": index,
             "only_identical": bool(only_identical), "keys_differing": 0, "rows_differing": 0,
             "differing_columns": {}, "differing_sample": []}
    to_go, done = ("rows_to_mark", "rows_marked") if mark else ("rows_to_delete", "rows_deleted")
    # 🔴 ONE READ OF THE TABLE (총괄 5ad030347 · 2e8c6ac9c): the counts, the sample and the rows to go come out of
    #    one pass in key order - five passes before the first line, 10.58 s at 1M. Without an index on the keys
    #    the table is sorted before the first row; the line says so before the sort starts.
    log(f"[fold-rows] '{table_name}': reading its rows by ({', '.join(keys)}) - index on the keys: {index}"
        + ("" if found else "; the first row comes after the sort"))
    losers, shown, differing = [], [], []
    for row in db.execute(_fold_read(keys, ranked, scope, mark, losers=apply, compared=len(compared),
                                     only_identical=only_identical).execution_options(yield_per=FOLD_ROWS_PAGE)):
        # by place, not by name: 800,000 rows to go read by name were 5 s of a 13 s read (box 1M, by place 8 s)
        part = row[0]
        if part == 1:
            losers.append((row[1], row[2]))
        elif part == 0:
            stats.update(rows=row.a0, rows_blank_key=row.a1, rows_out_of_scope=row.a2, rows_already_marked=row.a3,
                         keys_folded=row.a5, keys_preferred=row.a6, keys_differing=row.a7, rows_differing=row.a8,
                         differing_columns={column: getattr(row, "a%d" % (9 + i)) for i, column in enumerate(compared)
                                            if getattr(row, "a%d" % (9 + i))}, **{to_go: row.a4})
        elif part == 3:
            differing.append(row)
        else:
            shown.append(row)
    for row in sorted(differing, key=lambda row: (*[getattr(row, "k%d" % i) for i in range(len(keys))], row.n)):
        key = tuple(getattr(row, "k%d" % i) for i in range(len(keys)))
        if not stats["differing_sample"] or stats["differing_sample"][-1]["key"] != dict(zip(keys, key)):
            if len(stats["differing_sample"]) == FOLD_ROWS_DIFFERING_KEYS:
                break
            stats["differing_sample"].append({"key": dict(zip(keys, key)), "rows": [], "columns": [
                column for i, column in enumerate(compared) if getattr(row, "d%d" % i)]})
        one = stats["differing_sample"][-1]
        one["rows"].append({"row_id": row.row_id, **{column: getattr(row, "v%d" % compared.index(column))
                                                     for column in one["columns"]}})
    sample = {}
    for row in sorted(shown, key=lambda row: row.a0):
        key = tuple(getattr(row, "k%d" % i) for i in range(len(keys)))
        if key not in sample and len(sample) == FOLD_ROWS_SAMPLE_KEYS:
            break
        one = sample.setdefault(key, {"key": dict(zip(keys, key)), "rows": row.c, "kept": None, "deleted": []})
        seen = {"row_id": row.row_id, said_as: row.order_value, **({prefer[0]: row.prefer_value} if prefer else {})}
        if row.n == 1:
            one["kept"] = seen
        else:
            one["deleted"].append((row.n, seen))
    for one in sample.values():
        one["deleted"] = [seen for _n, seen in sorted(one["deleted"], key=lambda pair: pair[0])]
    stats["sample"] = list(sample.values())
    stats["rows_kept"] = stats["rows"] - stats[to_go]
    if apply and losers:
        losers.sort()
        size, start = keyset_scan.PageSize(FOLD_ROWS_PAGE), 0
        while start < len(losers):
            if checkpoint is not None and checkpoint(stats[done], len(losers)):
                stats["stopped"] = True
                log(f"[fold-rows] stopped by request after {stats[done]} of {len(losers)} rows")
                break
            page = losers[start:start + size.next()]
            start += len(page)
            stats[done] += (_mark_folded(db, table_name, mark, page, woken, recounts) if mark else
                            crud.delete_rows_batch(db, table_name, [r for r, _k in page], FOLD_ROWS_BY))
            stats["pages"] += 1
            if pages_per_cycle and rest_seconds and stats["pages"] % pages_per_cycle == 0:
                size.rest(rest_seconds)
    log(f"[fold-rows] '{table_name}' {stats['mode']}: {stats['keys_folded']} key(s) of ({', '.join(keys)}) "
        f"hold more than one row - keep "
        + (f"a row whose {prefer[0]} holds '{prefer[1]}' ({stats['keys_preferred']} key(s)), then " if prefer else "")
        + ("the most cell layers, " if keep == FOLD_KEEP_MOST_LAYERS else f"the {'earliest' if keep == 'min' else 'latest'} {order}, ")
        + f"{stats[to_go]} row(s) to {'mark' if mark else 'delete'}, {stats[done]} {'marked' if mark else 'deleted'}, "
        f"{stats['rows_blank_key']} row(s) with a blank key part"
        + (f", {stats['rows_out_of_scope']} out of scope" if scope else "")
        + (f", {stats['rows_already_marked']} marked before" if mark else "") + " left as they are")
    return stats



def _fold_read(keys, ranked, scope, mark, losers=True, compared=0, only_identical=False):
    """The fold's one read: `ranked` once (a CTE, read three times) - one row of counts (`part` 0: rows, blank key,
    out of scope, marked before, to go, keys folded, keys preferred - `a0` … `a6`), the rows to go when `losers`
    (`part` 1, the row kept beside each) and the preview's rows (`part` 2: the first by the key's text and place, as it always
    chose them; `a0` their order). The counts and the order stay in the database - every row through the client,
    sorted, was slower than the five reads it replaced (box, 1M: 27.6 s to the first page against 8.9 s).
    The keys whose ranking rows differ are counted (`a7` keys, `a8` rows to go, `a9` … per compared column) and their
    first rows read (`part` 3); `only_identical` folds none of them."""
    from sqlalchemy import BigInteger, and_, cast, func, literal, not_, null, select, union_all
    from sqlalchemy.types import NullType

    r = select(ranked).cte("fold_ranked")
    c = r.c
    keyed = not_(c.blank_key)
    folds = and_(c.ranks, not_(c.differs)) if only_identical else c.ranks
    kept = and_(folds, c.n == 1, c.c > 1)
    leads = and_(c.ranks, c.n == 1, c.c > 1, c.differs)
    counts = [func.count(), func.count().filter(c.blank_key),
              func.count().filter(and_(keyed, not_(c.in_scope))) if scope else literal(0),
              func.count().filter(and_(keyed, *([c.in_scope] if scope else []), not_(c.unmarked))) if mark else literal(0),
              func.count().filter(and_(folds, c.n > 1)), func.count().filter(kept),
              func.count().filter(and_(kept, c.preferred == 1)),
              func.count().filter(leads), func.count().filter(and_(c.ranks, c.n > 1, c.differs)),
              *[func.count().filter(and_(leads, c["d%d" % i])) for i in range(compared)]]
    labels = [c["k%d" % i] for i in range(len(keys))]
    shape = [c.row_id, c.kept, c.n, c.c, c.preferred, c.order_value, c.prefer_value, *labels,
             *[c["d%d" % i] for i in range(compared)], *[c["v%d" % i] for i in range(compared)]]

    def blank(col):
        return (null() if isinstance(col.type, NullType) else cast(null(), col.type)).label(col.name)
    head = select(literal(0).label("part"), *[blank(col) for col in shape],
                  *[cast(n, BigInteger).label("a%d" % i) for i, n in enumerate(counts)]).select_from(r)
    togo = select(literal(1).label("part"), c.row_id, c.kept, *[blank(col) for col in shape[2:]],
                  *[cast(null(), BigInteger).label("a%d" % i) for i in range(len(counts))]).where(folds, c.n > 1)
    shown = (select(*shape).where(folds, c.c > 1, c.n <= FOLD_ROWS_SAMPLE_ROWS)
             .order_by(*labels, c.n).limit(FOLD_ROWS_SAMPLE_KEYS * FOLD_ROWS_SAMPLE_ROWS).subquery())
    # numbered above the LIMIT: under it the window sorted every row whole (box 1M, 800k rows: 1.5 s more)
    sample = select(literal(2).label("part"), *[shown.c[col.name] for col in shape],
                    func.row_number().over(order_by=[*[shown.c[col.name] for col in labels], shown.c.n]).label("a0"),
                    *[cast(null(), BigInteger).label("a%d" % i) for i in range(1, len(counts))])
    differ = (select(*shape).where(c.ranks, c.c > 1, c.differs, c.n <= FOLD_ROWS_SAMPLE_ROWS)
              .order_by(*labels, c.n).limit(FOLD_ROWS_DIFFERING_KEYS * FOLD_ROWS_SAMPLE_ROWS).subquery())
    differing = select(literal(3).label("part"), *[differ.c[col.name] for col in shape],
                       *[cast(null(), BigInteger).label("a%d" % i) for i in range(len(counts))])
    # a dry run and the preview count the rows to go and take none of them (1M: 800,000 rows, 총괄 59c0bfb8c 3)
    return union_all(head, togo, sample, differing) if losers else union_all(head, sample, differing)

def _key_index(db, table_name, keys):
    """The index the table's own declaration («indexes» in table_config.json) has on `keys` in their order, as
    the index master reads it - {name, state} - or None: an operator writes one there (총괄 5ad030347). One that gives
    the rows in their order (`models.orders_rows_by`) - a search index on them does not."""
    from database import crud, models

    for row in models.index_states(db.get_bind(), tables={table_name: crud.TABLE_CONFIG.get(table_name)})["declared"]:
        if row["source"] == "table" and row["table"] == table_name and models.orders_rows_by(row, keys):
            return {"name": row["name"], "state": row["state"]}
    return None


#: Rows one page of the shell sweep reads - the shells among them judged and deleted at once - and the keys its
#: preview shows (5eee501eb). A page of 1,000 made a 1M table 1,000 commits (box: fewer deleted in 45 s than the
#: whole-table read it replaced); the page size rule still keeps a page within its time.
SHELL_PAGE = 20000
SHELL_SAMPLE = 5


def remove_shell_rows(db, table_name: str, apply: bool = False, pace: str = None, log=logger.info,
                      checkpoint=None) -> dict:
    """The shells already on `table_name` (총괄 5eee501eb, 소유자 10-09 「공식표에 껍데기 행 잔뜩 쌓여 있음」):
    the rows `cell_layer.shells` judges - the judgement the chain's write seat asks - deleted through the
    grid's door, `crud.delete_rows_batch`, a page at a time. A page is the table's next rows by row_id
    (`keyset_scan.iter_pages`), and «shows nothing outside its keys» is judged on those rows - in the WHERE it
    read on to the next match, the table whole at 1M (총괄 5ad030347); `rows_read` counts the rows that do. A stop
    lands between pages and a re-run finds only what is left."""
    from sqlalchemy import and_, true

    from chain import cell_layer
    from database import crud

    model, col_types = cell_layer.resolve_target(table_name)
    keys = cell_layer.key_columns(table_name)
    shown_blank = and_(true(), *[crud.blank_sql_condition(crud.column_text_sql(getattr(model, column)))
                                 for column in col_types if column not in keys])

    def judged(read):
        page = [row_id for row_id, blank in read if blank]
        return page, (cell_layer.shells(db, table_name, page) if page else [])
    stats = _delete_by_pages(db, table_name, model, keys, [shown_blank.label("shown_blank")], judged,
                             cell_layer.SHELL_DELETER, "remove-shells", apply, pace, log, checkpoint)
    log(f"[remove-shells] '{table_name}' {stats['mode']}: {stats['rows_read']} row(s) show nothing outside "
        f"their keys, {stats['rows_to_delete']} of them only the chain's keys left, {stats['rows_deleted']} deleted")
    return stats


#: Who the history says deleted a row the «Delete every row of a table» op took (총괄 4435b9b29).
EVERY_ROW_DELETER = "delete_every_row"


def delete_every_row(db, table_name: str, apply: bool = False, pace: str = None, log=logger.info,
                     checkpoint=None) -> dict:
    """Every row of `table_name` deleted through the grid's door, `crud.delete_rows_batch`, a page at a time -
    each row's layers and a history line go with it, and each deletion reaches the chain as the grid's does
    (소유자 10-21 「테이블 하나 다 지우는 법」 · 「다시 로드랑 지우기 분리해」, 총괄 4435b9b29). The file
    checklist is not touched: reading the files again is its own op. The same paging as `remove_shell_rows`,
    judged «every row»; a stop lands between pages and a re-run finds only what is left."""
    from chain import cell_layer

    model, _col_types = cell_layer.resolve_target(table_name)
    keys = cell_layer.key_columns(table_name)

    def judged(read):
        page = [row[0] for row in read]
        return page, page
    stats = _delete_by_pages(db, table_name, model, keys, [], judged, EVERY_ROW_DELETER, "delete-every-row",
                             apply, pace, log, checkpoint)
    log(f"[delete-every-row] '{table_name}' {stats['mode']}: {stats['rows_to_delete']} row(s), "
        f"{stats['rows_deleted']} deleted")
    return stats


#: The history's source on a full reset's one summary line.
FULL_RESET_SOURCE = "full_reset"


def full_reset(db, table_name: str, confirm_rows: int = None, apply: bool = False, by: str = EVERY_ROW_DELETER,
               setup=None, rules=None, log=logger.info) -> dict:
    """«Delete every row of a table» as a full reset (소유자 10-23 「완전 초기화 목적」 - was scripts/empty_table.py,
    총괄 35b76ba92): the rows, the table's cell layers and pins in ONE transaction with one summary history line, then
    every ledger source reading the table re-read whole, so the atoms of the rows it lost go. A raw DELETE - the
    grid's door is ~2.5 s per 10,000 rows, too slow for a million - so no outbox event: no chain rule is told, and a
    person's values go too. The dry run says what goes; `apply` takes `confirm_rows`, the rows the dry run said,
    and refuses a table that moved since."""
    from chain.ingestion_worker import loaded_chain_rules, watches_table
    from database import crud, models
    from ledger import backfill, followup, schema
    from ledger.setup import load_setup

    try:
        crud.refuse_write_to_view(table_name)
    except crud.ReadOnlyRelation as exc:
        raise ReplayRefused(str(exc)) from exc
    if table_name not in models.DYNAMIC_TABLES:
        raise ReplayRefused("'%s' is not a declared table (table_config)" % table_name)
    setup = load_setup() if setup is None else setup
    rules = loaded_chain_rules() if rules is None else rules
    layers = dict(db.execute(text(
        "SELECT source_name, count(*) FROM cell_sources WHERE table_name = :t GROUP BY source_name"),
        {"t": table_name}).fetchall())
    found = {
        "mode": "apply" if apply else "dry-run", "table": table_name,
        "rows": db.execute(text('SELECT count(*) FROM "%s"' % table_name)).scalar(),
        "layers": sum(layers.values()),
        "user_layers": sum(n for name, n in layers.items() if crud.layer_writer(name) == crud.USER_SOURCE),
        "overwrites": db.execute(text("SELECT count(*) FROM cell_overwrites WHERE table_name = :t"),
                                 {"t": table_name}).scalar(),
        "ledger_atoms": {source: db.execute(text("SELECT count(*) FROM %s WHERE source_who = :s"
                                                 % schema.LEDGER_TABLE), {"s": source}).scalar()
                         for source in followup.sources_for_table(setup, table_name)},
        "chain_rules": sorted(rule["name"] for rule in rules if watches_table(rule, table_name)),
    }
    if not apply:
        return found
    if confirm_rows is None or int(confirm_rows) != found["rows"]:
        raise ReplayRefused("'%s' has %d row(s) now, not %s - read the preview again and give its count"
                            % (table_name, found["rows"], confirm_rows))
    tx = "%s_%s" % (FULL_RESET_SOURCE, uuid.uuid4().hex[:8])
    found["rows_deleted"] = db.execute(text('DELETE FROM "%s"' % table_name)).rowcount
    found["layers_deleted"] = db.execute(text("DELETE FROM cell_sources WHERE table_name = :t"),
                                         {"t": table_name}).rowcount
    found["overwrites_deleted"] = db.execute(text("DELETE FROM cell_overwrites WHERE table_name = :t"),
                                             {"t": table_name}).rowcount
    crud.create_audit_log(db, table_name, "*", "*", found["rows"], 0, FULL_RESET_SOURCE, by, transaction_id=tx)
    db.commit()
    found["transaction_id"] = tx
    found["ledger_withdrawn"] = {
        source: backfill.rescope(db.get_bind(), setup, source, None, (), apply=True, whole_source=True,
                                 world=schema.DEFAULT_WORLD).get("gone_withdrawn", 0)
        for source in found["ledger_atoms"]}
    log(f"[full-reset] '{table_name}': {found['rows_deleted']} row(s), {found['layers_deleted']} layer(s), "
        f"{found['overwrites_deleted']} pin(s) deleted in {tx}; ledger atoms withdrawn {found['ledger_withdrawn']}")
    return found


def _delete_by_pages(db, table_name, model, keys, columns, judged, deleter, tag, apply, pace, log, checkpoint):
    """The paged delete both ops above run: `judged(read page)` -> (rows looked at, rows to delete), deleted
    through `crud.delete_rows_batch` under `deleter`, a commit a write page, a stop between pages."""
    from database import crud

    pages_per_cycle, rest_seconds = resolve_pace(pace)
    stats = {"mode": "apply" if apply else "dry-run", "table": table_name, "rows_read": 0,
             "rows_to_delete": 0, "rows_deleted": 0, "pages": 0, "stopped": False, "sample": []}
    # the reads double to SHELL_PAGE whatever the deletes take (a page time no read reaches); the deletes keep the page time, a commit each - one
    # 20,000-row delete was one 9.7 s transaction where shells crowd (총괄 59c0bfb8c 4)
    size, write = keyset_scan.PageSize(SHELL_PAGE, seconds=10 ** 6), keyset_scan.PageSize()
    step, reads = keyset_scan.step_of(checkpoint), 0

    def stop():
        if apply and checkpoint is not None and checkpoint(stats["rows_deleted"], None):
            stats["stopped"] = True
            log(f"[{tag}] stopped by request after {stats['rows_deleted']} rows")
        return stats["stopped"]
    for read in keyset_scan.iter_pages(db, model, columns=columns, chunk_size=SHELL_PAGE, size=size):
        reads += 1
        step("read", reads, None, len(read))
        if stop():
            break
        page, gone = judged(read)
        if not page:
            continue
        stats["rows_read"] += len(page)
        stats["rows_to_delete"] += len(gone)
        if len(stats["sample"]) < SHELL_SAMPLE and gone:
            stats["sample"] += [{key: getattr(row, key, None) for key in sorted(keys)} for row in db.query(model)
                                .filter(model.row_id.in_(gone[:SHELL_SAMPLE - len(stats["sample"])])).all()]
        while apply and gone and not (stats["pages"] and stop()):
            n = write.next()
            piece, gone = gone[:n], gone[n:]
            stats["rows_deleted"] += crud.delete_rows_batch(db, table_name, piece, deleter)
            stats["pages"] += 1
            if pages_per_cycle and rest_seconds and stats["pages"] % pages_per_cycle == 0:
                write.rest(rest_seconds)
        if stats["stopped"]:
            break
    return stats


#: What a folded row's mark says (총괄 016a766af) - the row it folded into.
FOLD_MARK = "folded into %s"


def _excluding_by(table_name, mark):
    """The enabled rules on `table_name` whose `exclude` names `mark` - what a marked row is for."""
    import chain_bindings

    return [rule for rule in load_rules() if rule.get("trigger_table") == table_name
            and mark in (rule.get(chain_bindings.EXCLUDE_KEY) or ())]


def _recounting(woken, mark):
    """The rules that recount on the targets of `woken` by `mark` - a rule on such a target whose
    `source_exclude` (stamped at load by the mapper that pairs them) names it."""
    import chain_bindings

    targets, names = {r.get("target_table") for r in woken}, {r.get("name") for r in woken}
    return [rule for rule in load_rules() if rule.get("trigger_table") in targets and rule.get("name") not in names
            and mark in (rule.get(chain_bindings.SOURCE_EXCLUDE_KEY) or ())]


def _mark_folded(db, table_name, mark, page, woken, recounts=()) -> int:
    """One page of the fold by mark (총괄 016a766af): «folded into <kept>» in `mark` through the
    product's write door (collapsed - a page is volume), then for every rule in `woken` the page's
    rows through the replay door - no channel, `only_rule`, EDIT (총괄 c2995cdd8's shape): 소유자 09-26
    「소급은 연쇄 안 함」 means no rule at random, and these are the rules the mark exists for (총괄 10-09).
    🔴 Then, in the same run line, the rules that recount on those rules' target (`recounts`) on the
    rows the page fed - its downstream is run by running it too (event_constants CHANNEL_RETROACTIVE,
    소유자 09-26); no `cascade`: the withdrawal goes out on the retroactive channel and wakes no rule
    (총괄 10-09 - the grid's click replay is the one exception the owner made).
    -> rows marked."""
    import event_constants
    from chain import cell_layer
    from database import crud, schemas
    from database.context import channel, outbox_mode
    from database.database import stage_collapsed_event

    with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, table_name, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(row_id=row_id, updates={mark: FOLD_MARK % kept},
                                      source_name=FOLD_ROWS_BY, updated_by=FOLD_ROWS_BY)
            for row_id, kept in page]))
    db.commit()
    fed = {}
    if recounts:
        for target, row_id, *_rest in cell_layer.cells_stamped_by(db, [row_id for row_id, _kept in page]):
            fed.setdefault(target, set()).add(row_id)
    with channel(None):
        for rule in woken:
            stage_collapsed_event(db, "EDIT", table_name, [row_id for row_id, _kept in page],
                                  only_rule=rule.get("name"), replay=True)
        for rule in recounts:
            if fed.get(rule.get("trigger_table")):
                stage_collapsed_event(db, "EDIT", rule.get("trigger_table"), sorted(fed[rule.get("trigger_table")]),
                                      only_rule=rule.get("name"), replay=True)
    db.commit()
    return len(page)


#: Rows of a fold rule's answer one page of `fold_units` judges and writes in one commit.
FOLD_UNITS_PAGE = 20000
#: The most whole groups fold-units asks the rule seat for at once (`fold_units`).
FOLD_UNITS_GROUPS = 1000


def fold_units_target(rule_name):
    """What fold-units names, judged once - by the run and by the operation's judge before anything is
    recorded. -> (rule, unit table model, log table model, mark column) or `ReplayRefused`."""
    from mappers import fold_unit

    rule = find_rule(rule_name)
    params = rule.get("params") or {}
    if rule.get("mapper") != fold_unit.NAME:
        raise ReplayRefused(f"chain rule '{rule_name}' runs '{rule.get('mapper')}' - fold-units runs a "
                            f"'{fold_unit.NAME}' rule")
    units, logs = params.get("unit_table"), rule.get("target_table")
    if rule.get("trigger_table") != units:
        on_units = [r.get("name") for r in load_rules() if r.get("mapper") == fold_unit.NAME
                    and r.get("trigger_table") == units and r.get("target_table") == logs]
        raise ReplayRefused(f"chain rule '{rule_name}' is triggered by '{rule.get('trigger_table')}' - name the "
                            f"rule on the unit table '{units}': {', '.join(on_units) or 'none is declared'}")
    mark = params.get("mark_column")
    if mark in key_columns(logs):
        raise ReplayRefused(f"mark_column '{mark}' is a key column of '{logs}' - a write there re-keys rows, "
                            f"which fold-units does not do")
    return rule, resolve_target(units)[0], resolve_target(logs, [mark])[0], mark


def fold_units(db, rule_name: str, apply: bool = False, pace: str = None, log=logger.info,
               checkpoint=None) -> dict:
    """A fold rule's answer over every unit row, written without the chain's queue (총괄 10-11, 소유자
    「접는 거 일단 스크립트로 빨리 하는 거 줘, 맵퍼 말고」). The answer is the rule seat's (`rule_run.run_rule`,
    `next_page` followed); a page of it goes through the write door's own per-cell judgement and is written
    set-based (`_fold_units_page`), one commit a page. After the last page, the withdrawal the worker runs
    for edited unit rows (`_withdraw_and_tell`, keep = every row the answer named): a unit that now wins
    takes its old marks back. No event for the marks and no broadcast - setup ⑥ (copy replay) follows them."""
    from sqlalchemy import func, select

    from chain import cell_layer, ingestion_worker, rule_run, rule_shape
    from chain.mapper_call import without_missing

    started = time.monotonic()
    rule, units, logs, mark = fold_units_target(rule_name)
    params, log_table = rule["params"], rule["target_table"]
    pages_per_cycle, rest_seconds = resolve_pace(pace)
    prefer = ((params["prefer_column"], params["prefer_text"])
              if params.get("prefer_column") and params.get("prefer_text") else None)
    ranked = _ranked_duplicates(units, [params["group"]], params["order"], "min", prefer)
    groups, losing = db.execute(select(func.count().filter(ranked.c.ranks, ranked.c.n == 1),
                                       func.count().filter(ranked.c.ranks, ranked.c.n > 1)).select_from(ranked)).one()
    unit_ids = [row_id for (row_id,) in db.execute(select(units.row_id).order_by(units.row_id))]
    import map_overlay

    keyed = keyset_scan.keyed_rows(db, units, [params["group"]], lambda values: map_overlay.canonical_bind_value(
        params["unit_table"], params["group"], values[params["group"]]))
    keyed.pop(None, None)                          # a unit with no group is asked by none ('' and spaces are no group)
    in_order = list(keyed)
    columns = outbox_expand._data_columns(units)
    answers = []
    stats = {"mode": "apply" if apply else "dry-run", "rule": rule_name, "table": log_table, "units": len(unit_ids),
             "groups": groups, "units_losing": losing, "rows_proposed": 0, "rows_to_mark": 0,
             "rows_marked": 0, "rows_higher_layer": 0, "rows_already_marked": 0, "rows_gone": 0, "rows_refused": 0,
             "version_gate": {}, "marks_withdrawn": None, "pages": 0, "page_seconds": [],
             "retraction_seconds": None, "stopped": False, "seconds": None}
    tx_id = "chain_fold_units_%s" % uuid.uuid4().hex[:8]
    keep = set()

    total = None                                   # counted as it goes - the answer is asked a few groups at a time
    size = keyset_scan.PageSize(FOLD_UNITS_PAGE)
    step = keyset_scan.step_of(checkpoint)

    def asked():
        """The rule seat asked whole groups at a time - one first, twice as many each call, at most
        FOLD_UNITS_GROUPS - so the first page does not wait on every group's answer (총괄 2ea5ee2a7, 응용: 12.2 s
        before the first line); a group is asked once, so no mark is proposed twice. Its paging records
        (`next_page`) followed."""
        at, n = 0, 1
        while at < len(in_order):
            part, at, n = in_order[at:at + n], at + n, min(n * 2, FOLD_UNITS_GROUPS)
            ids = sorted(row_id for key in part for row_id in keyed[key])
            _model, found = outbox_expand.load_rows_by_ids(db, params["unit_table"], ids)
            # the fetch seat first, as the group path asks it (총괄 78eec1ec1): the rule runs on what was read
            answer = rule_run.run_rule(db, rule, prepared=rule_run.prepare(db, rule, payloads=[
                outbox_expand._synthesize_payload(found[row_id], columns, {}) for row_id in ids if row_id in found]))
            answers.append(answer)
            step("rule", stats["pages"] + 1, None, len(ids))
            yield answer["updates"]
            for record in answer["next_page"]:
                call = record["call"]
                while call is not None:
                    result = without_missing(call()) or {}
                    yield result.get("updates") or ()
                    call = result.get("next_page")

    def pages():
        page, n = [], size.next()
        for updates in asked():
            page.extend(updates)
            while len(page) >= n:
                yield page[:n]
                page, n = page[n:], size.next()
        while page:
            yield page[:n]
            page, n = page[n:], size.next()

    for proposed in pages():
        step("read", stats["pages"] + 1, None, len(proposed))
        if checkpoint is not None and checkpoint(stats["rows_proposed"], total):
            stats["stopped"] = True
            log(f"[fold-units] stopped by request after {stats['rows_proposed']} of {total} rows")
            break
        page_started = time.monotonic()
        counts, items = _fold_units_page(db, log_table, logs, mark, proposed, tx_id, apply, on_fold=lambda: step(
            "fold", stats["pages"] + 1, None, len(proposed)))
        keep |= ingestion_worker._rows_written_from(db, log_table, items)
        for reason, n in counts.pop("version_gate", {}).items():
            stats["version_gate"][reason] = stats["version_gate"].get(reason, 0) + n
        for key, value in counts.items():
            stats[key] += value
        stats["rows_proposed"] += len(proposed)
        stats["pages"] += 1
        step("write", stats["pages"], None, len(proposed))
        stats["page_seconds"].append(round(time.monotonic() - page_started, 2))
        if pages_per_cycle and rest_seconds and stats["pages"] % pages_per_cycle == 0:
            size.rest(rest_seconds)
    # the worker's edit withdrawal (`apply_chain_writes`): the unit rows handed, the columns the rule writes
    if not stats["stopped"] and unit_ids and rule_run.stamps_its_origin(rule):
        written = rule_run.columns_a_rule_writes(
            rule, answers[0]["updates"] if answers else [],
            more=len(answers) > 1 or bool(answers and answers[0]["next_page"]))
        if written:
            retraction_started = time.monotonic()
            if apply:
                taken = ingestion_worker._withdraw_and_tell(
                    db, params["unit_table"], unit_ids, "edited", declarations=(rule_shape.declaration_of(rule),),
                    table=log_table, columns=written, keep=keep)
            else:
                taken = cell_layer.withdraw_by_origin(db, unit_ids, apply=False, log=lambda m: None,
                                                      table=log_table, columns=written, keep=keep)
                db.rollback()
            stats["marks_withdrawn"] = taken.get("cells_withdrawn", 0)
            stats["retraction_seconds"] = round(time.monotonic() - retraction_started, 2)
    stats["seconds"] = round(time.monotonic() - started, 2)
    log(f"[fold-units] '{rule_name}' {stats['mode']}: {stats['rows_to_mark']} of {stats['rows_proposed']} row(s) "
        f"to mark, {stats['rows_already_marked']} marked so already, {stats['marks_withdrawn']} old mark(s) "
        f"withdrawn, {stats['pages']} page(s), {stats['seconds']} s")
    return stats


def _fold_units_forced(item, plain, layers, overwrite, clean, col_type, key_column, gated, table_name):
    """'empty' · 'same' · None - the two cells whose write-door answer is already decided (총괄 10-11, speed):
    no layer and no overwrite on the cell, or its one layer is this item's own, saying the same, and shown.
    None - the door judges it (`crud.apply_row_update_internal`): any other layer, an overwrite row, a
    version-gated table, a row whose business key the door would re-read, a spelling the notation folded."""
    from database import crud

    business_key, shown, key_value = plain
    if (gated or overwrite is not None or len(item.updates) != 1 or item.business_key_val
            or item._written_spelling or crud.is_blank_value(clean)):
        return None
    if key_column and key_value is not None and (
            isinstance(key_value, dict)
            or crud.compose_business_key(table_name, [key_value], [key_column]) not in ("", business_key)):
        return None
    if not layers:
        return "empty"
    own = layers[0]
    if (len(layers) == 1 and own.source_name == item.source_name and own.updated_by == item.updated_by
            and own.origin_row_id == item.origin_row_id and not crud.values_differ(own.value, clean, col_type)
            and not crud.values_differ(shown, own.value, col_type)):
        return "same"
    return None


def _fold_units_page(db, table_name, model, mark, proposed, tx_id, apply, on_fold=lambda: None):
    """One page of a fold rule's answer, judged as the write door judges it and written as it writes it.
    The steps `_apply_batch_updates_once` takes before its loop and the worker's layer naming run as they
    are; a cell `_fold_units_forced` decides takes that answer, every other one goes through
    `crud.apply_row_update_internal` with the batch path's accumulators. Written: the history lines and
    the shown values from one array per column (one statement each), layers and overwrites by the door's
    bulk writers. `on_fold` is called once the page is judged, before it is written. -> (counts, the page's items)"""
    from collections import Counter

    from sqlalchemy import String, any_, bindparam, inspect
    from sqlalchemy.dialects.postgresql import ARRAY
    from sqlalchemy.orm import load_only

    from chain import rule_run
    from database import crud, models, schemas

    if db.get_bind().dialect.name != "postgresql":
        raise ReplayRefused("fold-units writes with PostgreSQL arrays - this database is %s"
                            % db.get_bind().dialect.name)
    batch = schemas.GeneralUpdateBatch(updates=proposed, transaction_id=tx_id)
    for item in batch.updates:
        item.source_name = rule_run.layer_of_a_rules_write(item.source_name, item.origin_row_id)
    items = list(batch.updates)
    config = crud.TABLE_CONFIG.get(table_name) or {}
    col_type = (config.get("column_types") or {}).get(mark, "string")
    key_column, gated = config.get("business_key"), bool(config.get("version_column"))
    counts = Counter()
    crud.refuse_write_to_view(table_name)
    crud._fold_written_notation(db, table_name, batch)
    with crud.transaction_context(items[0].updated_by if items else "system", tx_id,
                                  items[0].source_name if items else "batch"):
        crud.fill_nokey_keys(table_name, batch)
        for item in batch.updates:
            crud.assemble_composite_business_key(table_name, item)
        counts["rows_refused"] += len(crud.refuse_virtual_join_duplicates(db, table_name, batch))
        ids = list(dict.fromkeys(item.row_id for item in batch.updates if item.row_id))
        read = [model.row_id, model.business_key_val, getattr(model, mark)] + (
            [getattr(model, key_column)] if key_column else [])
        plain, sources, overwrites = {}, {}, {}
        cs, co = models.CellSource, models.CellOverwrite
        page = bindparam("page", ids, type_=ARRAY(String))      # one read of each kind a page, not one per 1,000
        for row in db.query(*read).filter(model.row_id == any_(page)):
            plain[row[0]] = (row[1], row[2], row[3] if key_column else None)
        for layer in (db.query(cs.table_name, cs.row_id, cs.column_name, cs.source_name, cs.value, cs.updated_by,
                               cs.ingested_at, cs.origin_row_id)
                      .filter(cs.table_name == table_name, cs.row_id == any_(page), cs.column_name == mark)
                      .order_by(cs.source_name.asc())):
            sources.setdefault((layer[1], layer[2]), []).append(crud.LightCellSource(*layer))
        for ow in (db.query(co.table_name, co.row_id, co.column_name, co.is_overwrite, co.updated_by,
                            co.updated_at, co.manual_priority_source)
                   .filter(co.table_name == table_name, co.row_id == any_(page), co.column_name == mark)):
            overwrites[(ow[1], ow[2])] = crud.LightCellOverwrite(*ow)
        # a row the answer named that is no longer there is not created (the door would make a row of a mark)
        judged = [item for item in batch.updates if item.row_id in plain]
        counts["rows_gone"] += len(batch.updates) - len(judged)
        batch_now = crud.batch_write_instant(db)
        history, layers, ow_put, ow_gone = crud.ByRowLogs(), crud.ByRow(), crud.ByRow(), crud.ByRowSet()
        folded, moved, door = set(), {}, []
        for item in judged:
            business_key, old, _key = plain[item.row_id]
            cell = (item.row_id, mark)
            clean = crud.cast_value_by_type(item.updates.get(mark), col_type, mark, table_name)
            forced = _fold_units_forced(item, plain[item.row_id], sources.get(cell), overwrites.get(cell), clean,
                                        col_type, key_column, gated, table_name)
            if forced is None:
                door.append(item)
            elif forced == "same":
                counts["rows_already_marked"] += 1
            else:
                layers[(table_name, item.row_id, mark, item.source_name)] = {
                    "table_name": table_name, "row_id": item.row_id, "column_name": mark,
                    "source_name": item.source_name, "value": clean, "updated_by": item.updated_by,
                    "origin_row_id": item.origin_row_id, "ingested_at": crud.layer_instant()}
                counts["rows_to_mark"] += 1
                if crud.values_differ(old, clean, col_type):
                    moved.setdefault(frozenset((mark, "updated_at")), []).append([item.row_id, clean])
                    history.append(crud.row_update_line(
                        db, table_name, item.row_id, [mark], {mark: clean}, {mark: old}, False, item.source_name,
                        item.updated_by, tx_id, business_key, add_to_cache=False))
        if door:
            loaded = [getattr(model, name) for name in dict.fromkeys(
                name for name in ("row_id", "business_key_val", mark, config.get("version_column"), key_column)
                if name)]
            rows = {row.row_id: row for row in db.query(model).options(load_only(*loaded)).filter(
                model.row_id == any_(bindparam("door", [item.row_id for item in door], type_=ARRAY(String))))}
            row_cache, layers_read = {}, crud.LayersRead(rows, [mark])     # the page read the mark's cells
            for row in rows.values():
                row_cache[row.row_id] = row
                if row.business_key_val:
                    row_cache[row.business_key_val] = row
            probed = crud.ProbedIdentity(row_ids=frozenset(), business_keys=frozenset())
            version_stats = {"rows": len(door)} if gated else None
            with db.no_autoflush:
                for item in door:
                    row, _is_new, changed = crud.apply_row_update_internal(
                        db, table_name, item, row_cache=row_cache, sources_cache=sources,
                        overwrites_cache=overwrites, transaction_id=tx_id, logs_to_cache=history,
                        cell_sources_to_upsert=layers, cell_overwrites_to_upsert=ow_put,
                        cell_overwrites_to_delete=ow_gone, deleted_row_ids=[], version_stats=version_stats,
                        layers_read=layers_read, probed_identity=probed, drop_stats=crud._new_drop_stats(),
                        batch_now=batch_now, cell_sources_to_delete=folded)
                    layer = layers.get((table_name, item.row_id, mark, item.source_name))
                    if layer is None:
                        counts["rows_already_marked"] += 1
                        continue
                    counts["rows_to_mark"] += 1
                    if mark not in changed and crud.values_differ(getattr(row, mark), layer["value"], col_type):
                        counts["rows_higher_layer"] += 1
            for row in rows.values():
                names = frozenset(inspect(row).committed_state)
                if names:
                    moved.setdefault(names, []).append([row.row_id] + [getattr(row, name) for name in sorted(names)
                                                                       if name != "updated_at"])
                db.expunge(row)
            if version_stats is not None:
                counts["version_gate"] = dict(version_stats.get("counts") or {})
        on_fold()
        if not apply:
            db.rollback()
            return counts, batch.updates
        _insert_by_arrays(db, models.AuditLog.__table__, history)
        crud.bulk_upsert_cell_sources(db, list(layers.values()))
        crud.bulk_upsert_cell_overwrites(db, list(ow_put.values()))
        crud.bulk_delete_cell_overwrites(db, list(ow_gone))
        crud.bulk_delete_cell_sources(db, [key for key in folded if key not in layers])
        for names, shown in moved.items():
            crud.update_by_arrays(db, model.__table__, sorted(names), shown, batch_now)
        db.commit()
    counts["rows_marked"] += counts["rows_to_mark"]
    return counts, batch.updates


def _insert_by_arrays(db, table, mappings):
    """The rows of `mappings` (every column but the key) into `table` in one statement."""
    from sqlalchemy import text
    from database import crud

    if not mappings:
        return
    columns = [column for column in table.columns if not column.primary_key]
    params, casts = crud.array_params(db, columns, [[one.get(column.name) for column in columns] for one in mappings])
    db.execute(text('INSERT INTO "%s" (%s) SELECT * FROM unnest(%s)' % (
        table.name, ", ".join('"%s"' % column.name for column in columns), ", ".join(casts))), params)


#: The writer of the history line a notation backfill leaves on each cell it folds.
NOTATION_BACKFILL_SOURCE = "notation_backfill"

#: Rows a page of `fold_written_notation` reads, judges and writes in one commit (총괄 10-11, speed: 4M rows).
NOTATION_FOLD_PAGE = 20000
#: The dialects a page of it is folded by value on (`_fold_by_values` writes with PostgreSQL arrays);
#: on any other every row takes the row path.
FOLD_BY_VALUE_DIALECTS = ("postgresql",)


def fold_written_notation(db, table_name: str, apply: bool = False,
                          chunk_size: int = NOTATION_FOLD_PAGE, limit: int = None,
                          pace: str = None, max_report: int = DEFAULT_MAX_REPORT,
                          log=logger.info, checkpoint=None) -> dict:
    """Notation stage three (총괄 2dc2c1baf), widened to the whole write fold (총괄 c6a8c069c ㉡):
    what a column stored before today's fold is folded IN PLACE by the two steps the write funnel
    runs - a `write` column's notation fold (`notation_norm.fold_for_write`), then, on every text
    column, the cast (`crud.cast_value_by_type`, which stores a number in `clean_str_value`'s
    spelling). Every layer's value, the shown value and the row's business key.

    A cell whose layers moved shows what the folded layers now decide - `cell_layer._resolve_cell`
    over `_load_cell_state`, the one layer -> shown pair R2 and R3 use; a cell whose layers did not
    move has its shown value folded.

    🔴 A KEY MOVES ONLY WHEN THE FOLD MOVED ONE OF ITS PARTS, and only when the row's unfolded
    parts still spell its stored key. Otherwise the row is skipped and named (`not_rebuilt`):
    measured on the box 10-01, 135,472 rows in 11 tables whose cells no longer spell their stored
    key (a time part read back as a datetime, an older separator, probe rows), and rebuilding the
    key from those cells would have changed their identity.

    ⛔ NOT THROUGH THE WRITE DOOR: re-sending a stored layer moves its `ingested_at` ahead of a
    newer layer of its class and changes the shown VALUE, not its spelling (measured, 0d9a69a63).
    Here only a layer's `value` is updated.
    A row whose folded key another row holds is MERGED into that row (owner 10-06 「예」) through
    `crud.merge_into_key_holders`, as the write door and the key fix do - after its own cells and
    layers are folded, so the holder takes folded values; three or more meet in row_id order. A
    merge cannot be undone; the dry run counts and names them. A value a second fold would move again is counted by the dry
    run and stops the run before the page holding it is written (47aba5d44 ③). One history line
    per shown cell that changes; the rows' outbox events carry the change to the ledger. One
    commit per page.

    🔴 ON POSTGRESQL A PAGE IS FOLDED BY VALUE (총괄 10-11, 소유자 「노테이션 소급 엄청 빨리」): each
    distinct spelling of the page is folded once and what moves is written set-based
    (`_fold_by_values` · `_write_by_values`); a row whose key part could move is judged by the row
    path (`plan_rows`, the one every row takes on another dialect) and written with the page - only
    a row that merges, and the row it merges into, keep the ORM write. Same end state, measured A = B.
    """
    from sqlalchemy import func

    import notation_norm
    from database import crud, models
    from chain import keyset_scan

    model, col_types = resolve_target(table_name)
    pages_per_cycle, rest_seconds = resolve_pace(pace)
    written = notation_norm.written_columns(table_name)
    physical = model.__table__.columns
    # The text half of the write fold: every column the funnel's cast stores as text - a String
    # column, the same physical question the key seats ask.
    text_columns = [column for column in col_types if column in physical
                    and notation_norm.is_text_type(physical[column].type)]
    folded = sorted(set(written) | set(text_columns))
    config = crud.TABLE_CONFIG.get(table_name, {})
    key_col = config.get("business_key")
    composite_src = config.get("composite_key_source")
    parts_of_key = composite_src or ([key_col] if key_col else [])
    numbered = any(col_types.get(column) == "number" for column in parts_of_key)
    stats = {"mode": "apply" if apply else "dry-run", "table": table_name,
             "written_columns": list(written), "text_columns": text_columns,
             "rows_scanned": 0, "pages": 0,
             "cells_folded": 0, "layers_folded": 0, "keys_changed": 0, "rows_merged": 0,
             "same_key_groups": 0, "split_key_groups": 0,
             "merged": [], "keys_not_rebuilt": 0, "not_rebuilt": [],
             "moves_again": 0, "again": [], "time_left": {},
             "stopped": False, "stopped_on_moves_again": False}
    if not folded and not numbered:
        log(f"[notation] '{table_name}' has no \"write\" column, no text column and no number key - "
            f"nothing to fold")
        return stats
    aliases = notation_norm.aliases_by_column(db)
    claimed = {}                        # folded key -> the row that took it in this run
    tx_id = f"{NOTATION_BACKFILL_SOURCE}_{uuid.uuid4().hex[:8]}"
    by_value = db.get_bind().dialect.name in FOLD_BY_VALUE_DIALECTS

    def fold_value(column, value):
        """(stored, verdict, [column, value, stored, again] or None) - THE fold of one stored value."""
        stored, verdict = notation_norm.fold_for_write(table_name, column, value, aliases)
        again = None
        if stored != value:
            moved = notation_norm.moves_again(
                stored, notation_norm.write_spec(table_name, column)["rules"],
                aliases.get((table_name, column)) or {})
            if moved is not None:
                again = [column, value, stored, moved]
        if column in text_columns:
            stored = crud.cast_value_by_type(stored, col_types.get(column, "string"), column,
                                             table_name)
        return stored, verdict, again

    def fold(column, value, again):
        stored, verdict, moved = fold_value(column, value)
        if verdict in notation_norm.TIME_LEFT_AS_WRITTEN:
            stats["time_left"][verdict] = stats["time_left"].get(verdict, 0) + 1
        if moved:
            again.append(moved)
        return stored

    def twins_of(rows):
        """{row_id: the key's first row} - rows whose stored key a row with a smaller row_id stores too: a
        same-spelling duplicate (owner 10-20 - two «1» rows, and the table could not take its uq_bk_ index)."""
        keys = sorted({row.business_key_val for row in rows if row.business_key_val})
        if not keys:
            return {}
        firsts = dict(db.query(model.business_key_val, func.min(model.row_id))
                      .filter(model.business_key_val.in_(keys))
                      .group_by(model.business_key_val).having(func.count() > 1).all())
        return {row.row_id: firsts[row.business_key_val] for row in rows
                if row.business_key_val in firsts and firsts[row.business_key_val] != row.row_id}

    same_groups, split_groups = set(), set()

    def plan_rows(page, again, fold, twins=None):
        """The row path over `page` (rows of the model): each row's cells, layers, key and merge."""
        twins = twins_of(page) if twins is None else twins
        plans = {}
        for row in page:
            cells = {}
            for column in folded:
                old = getattr(row, column, None)
                new = fold(column, old, again)
                if new != old:
                    cells[column] = (old, new)
            plans[row.row_id] = {"row": row, "cells": cells, "layers": [], "key": None}
        if not plans:
            return plans
        moved = {}
        for layer_id, row_id, column, source, value in (
                db.query(models.CellSource.id, models.CellSource.row_id,
                         models.CellSource.column_name, models.CellSource.source_name,
                         models.CellSource.value)
                .filter(models.CellSource.table_name == table_name,
                        models.CellSource.row_id.in_(list(plans)),
                        models.CellSource.column_name.in_(folded)).all()):
            new = fold(column, value, again)
            if new != value:
                plans[row_id]["layers"].append({"id": layer_id, "value": new})
                moved.setdefault((row_id, column), {})[source] = new
        if moved:
            sources, pins = _load_cell_state(db, table_name, sorted({r for r, _ in moved}))
            for (row_id, column), now in moved.items():
                layers = {source: dict(layer, value=now.get(source, layer["value"]))
                          for source, layer in sources.get((row_id, column), {}).items()}
                row, cells = plans[row_id]["row"], plans[row_id]["cells"]
                old = getattr(row, column, None)
                new = _resolve_cell(table_name, col_types, row, column, layers,
                                    pins.get((row_id, column)))["new_value"]
                if new != old:
                    cells[column] = (old, new)
                else:
                    cells.pop(column, None)
        for plan in plans.values():
            row, cells = plan["row"], plan["cells"]
            if not any(column in cells for column in parts_of_key):
                plan["key"] = numbered and respelled_key(table_name, row, parts_of_key) or None
                continue
            before, after = (
                None if crud.every_key_part_blank(parts)        # a blank part among filled ones is a part
                else crud.compose_business_key(table_name, [crud.fold_key_value(table_name, c, p)
                                                            for c, p in zip(parts_of_key, parts)], parts_of_key)
                for parts in ([getattr(row, c, None) for c in parts_of_key],
                              [cells[c][1] if c in cells else getattr(row, c, None)
                               for c in parts_of_key]))
            if not after or after == row.business_key_val:
                continue
            if before != row.business_key_val:
                plan["not_rebuilt"] = after
            else:
                plan["key"] = after
        wanted = {plan["key"] for plan in plans.values() if plan["key"]}
        # the key's first row holds it - one answer when the key is held twice
        holders = dict(db.query(model.business_key_val, func.min(model.row_id))
                       .filter(model.business_key_val.in_(list(wanted)))
                       .group_by(model.business_key_val).all()) \
            if wanted else {}
        for row_id, plan in list(plans.items()):
            key = plan["key"]
            if "not_rebuilt" in plan:
                stats["keys_not_rebuilt"] += 1
                if len(stats["not_rebuilt"]) < max_report:
                    stats["not_rebuilt"].append({
                        "row_id": row_id, "business_key_val": plan["row"].business_key_val,
                        "folded_key": plan["not_rebuilt"]})
                del plans[row_id]
            elif key and (key in claimed or holders.get(key, row_id) != row_id):
                into = (holders[key] if holders.get(key, row_id) != row_id
                        else claimed[key])
                plan["key"], plan["into"] = None, into
                stats["rows_merged"] += 1
                split_groups.add(key)
                if len(stats["merged"]) < max_report:
                    stats["merged"].append({"row_id": row_id,
                                            "business_key_val": plan["row"].business_key_val,
                                            "folded_key": key, "into": into})
            elif key:
                claimed[key] = row_id
            elif row_id in twins:
                plan["into"] = twins[row_id]
                stats["rows_merged"] += 1
                same_groups.add(plan["row"].business_key_val)
                if len(stats["merged"]) < max_report:
                    stats["merged"].append({"row_id": row_id,
                                            "business_key_val": plan["row"].business_key_val,
                                            "folded_key": plan["row"].business_key_val, "into": twins[row_id]})
        return plans

    def quiet(column, value, _again):
        """The row path's fold on a page folded by value - that page already counted every value."""
        return fold_value(column, value)[0]

    total = db.query(func.count(model.row_id)).scalar() or 0
    total = min(total, limit) if limit is not None else total
    columns = [getattr(model, column.key) for column in physical if column.key != "row_id"] if by_value else None
    step, size = keyset_scan.step_of(checkpoint), keyset_scan.PageSize(chunk_size)
    with crud.transaction_context(NOTATION_BACKFILL_SOURCE, tx_id, NOTATION_BACKFILL_SOURCE):
        for page in keyset_scan.iter_pages(db, model, columns=columns, chunk_size=chunk_size, limit=limit,
                                           size=size):
            step("read", stats["pages"] + 1, None, len(page))
            if checkpoint is not None and checkpoint(stats["rows_scanned"], total):
                stats["stopped"] = True
                log(f"[notation] stopped by request after {stats['rows_scanned']} rows")
                break
            stats["pages"] += 1
            stats["rows_scanned"] += len(page)
            if by_value:
                values = _fold_by_values(db, table_name, page, folded, parts_of_key, col_types, fold_value)
                for verdict, n in values["time_left"].items():
                    stats["time_left"][verdict] = stats["time_left"].get(verdict, 0) + n
                again = values["again"]
                if numbered:
                    values["hard"].update(row_id for row_id, row in values["rows"].items()
                                          if respelled_key(table_name, row, parts_of_key))
                twins = twins_of(list(values["rows"].values()))
                values["hard"].update(twins)
                plans = plan_rows([values["rows"][row_id] for row_id in sorted(values["hard"])], [], quiet,
                                  twins)
                # A row that merges, and the row it merges into, keep the ORM write: the shell is
                # deleted at the flush and the holder changed again by the merge, one event each.
                # Every other planned row - its key moved onto nothing or did not move - is
                # written by value with the page (총괄 10-11 · RUN.md 「키 칸도 한꺼번에」).
                meet = {plan["into"] for plan in plans.values() if plan.get("into")}
                orm = {row.row_id: row for row in db.query(model).filter(model.row_id.in_(sorted(
                    row_id for row_id, plan in plans.items() if plan.get("into") or row_id in meet)))} \
                    if meet else {}
                for row_id, plan in list(plans.items()):
                    if row_id in orm:
                        plan["row"] = orm[row_id]
                        continue
                    del plans[row_id]
                    values["cells"].update(((row_id, column), cell) for column, cell in plan["cells"].items())
                    values["layers"].update((layer["id"], layer["value"]) for layer in plan["layers"])
                    if plan["key"]:
                        values["keys"][row_id] = plan["key"]
            else:
                values, again = None, []
                plans = plan_rows(page, again, fold)
                again = [(entry, 1) for entry in again]
            step("fold", stats["pages"], None, len(page))
            for entry, n in again:
                stats["moves_again"] += n
                stats["again"].extend([entry] * min(n, max(0, max_report - len(stats["again"]))))
            if again and apply:
                stats["stopped"] = stats["stopped_on_moves_again"] = True
                log(f"[notation] '{table_name}' stopped before page {stats['pages']}: "
                    f"{sum(n for _entry, n in again)} value(s) change again on a second fold - fix "
                    f"the declaration or the alias rows first")
                break
            changed = [plan for plan in plans.values()
                       if plan["cells"] or plan["layers"] or plan["key"]]
            stats["cells_folded"] += sum(len(plan["cells"]) for plan in changed)
            stats["layers_folded"] += sum(len(plan["layers"]) for plan in changed)
            stats["keys_changed"] += sum(1 for plan in changed if plan["key"])
            if values:
                stats["cells_folded"] += len(values["cells"])
                stats["layers_folded"] += len(values["layers"])
                stats["keys_changed"] += len(values["keys"])
            # a re-spelled key may move no cell: a page that only re-keys or merges is written too (owner 10-20)
            merging = any(plan.get("into") for plan in plans.values())
            if apply and (changed or merging or values and (values["cells"] or values["layers"] or values["keys"])):
                if values:
                    _write_by_values(db, table_name, model, values, tx_id)
                for plan in changed:
                    row = plan["row"]
                    if plan["key"]:
                        row.business_key_val = plan["key"]
                    for column, (old, new) in plan["cells"].items():
                        setattr(row, column, new)
                        crud.create_audit_log(
                            db, table_name, row.row_id, column, old, new,
                            NOTATION_BACKFILL_SOURCE, NOTATION_BACKFILL_SOURCE,
                            transaction_id=tx_id, business_key=row.business_key_val)
                layers = [layer for plan in changed for layer in plan["layers"]]
                if layers:
                    db.bulk_update_mappings(models.CellSource, layers)
                crud.merge_into_key_holders(
                    db, table_name,
                    sorted((row_id, plan["into"]) for row_id, plan in plans.items()
                           if plan.get("into")),
                    source_name=NOTATION_BACKFILL_SOURCE,
                    updated_by=NOTATION_BACKFILL_SOURCE, transaction_id=tx_id)
                db.commit()
            step("write", stats["pages"], None, len(page))
            if pages_per_cycle and rest_seconds and stats["pages"] % pages_per_cycle == 0:
                size.rest(rest_seconds)
    stats["same_key_groups"], stats["split_key_groups"] = len(same_groups), len(split_groups)
    log(f"[notation] '{table_name}' {stats['mode']}: {stats['cells_folded']} cell(s) and "
        f"{stats['layers_folded']} layer(s) folded in {stats['rows_scanned']} row(s), "
        f"{stats['keys_changed']} key(s) changed, {stats['keys_not_rebuilt']} row(s) skipped "
        f"(their cells no longer spell their stored key), {stats['rows_merged']} row(s) "
        f"{'merged' if apply else 'to merge'} into the row holding their folded key "
        f"({stats['same_key_groups']} key(s) held twice as stored, {stats['split_key_groups']} met by spelling), "
        f"{stats['moves_again']} value(s) change again")
    return stats


def respelled_key(table_name, row, parts_of_key):
    """The row's key in the one spelling when its stored key is that key in an old NUMBER spelling - else None
    (owner 10-20: «1.0» · «001» rows re-keyed to «1», and rows meeting there merged; dates wait for the owner).

    Old spelling means: the stored key split by the separator gives one piece per key part, every piece and the
    row's own value of that part spell alike by the one speller (`crud.key_part`), and a piece that differs from
    that spelling is a number column's. A key that differs any other way - a mapper's key beside another column
    value, a separator inside a value - is not touched."""
    import map_overlay
    from database import crud

    stored = getattr(row, "business_key_val", None)
    values = [getattr(row, column, None) for column in parts_of_key]
    if not stored or not values or any(crud.is_blank_key_part(value) for value in values):
        return None
    key = crud.compose_business_key(table_name, values, parts_of_key)
    if key == stored:
        return None
    separator = crud.TABLE_CONFIG.get(table_name, {}).get("composite_key_separator", "_")
    pieces = [stored] if len(parts_of_key) == 1 else str(stored).split(separator)
    if len(pieces) != len(parts_of_key):
        return None
    for column, piece, value in zip(parts_of_key, pieces, values):
        spelled = crud.clean_str_value(crud.key_part(table_name, column, value))
        if crud.clean_str_value(crud.key_part(table_name, column, piece)) != spelled:
            return None
        if piece != spelled and map_overlay.declared_column_type(table_name, column) != "number":
            return None
    return key


def _fold_by_values(db, table_name, page, folded, key_parts, col_types, fold_value) -> dict:
    """One page of `fold_written_notation` folded by value (총괄 10-11). Each distinct shown value and
    each distinct stored layer text of a folded column is folded once (`fold_value`) and counted as
    often as it stands - so `time_left` and the moves-again count are the row path's, page-wide.
    A row whose key part could move (its shown value or a layer of it moves) is `hard`: the row path
    judges it whole and its answer joins this page's (`keys`: row id -> moved key, the caller's). For
    every other row: a cell with a layer that moves shows what its layers decide -
    one stored text among them is that text folded and cast as `_resolve_cell` casts it, more than
    one is `_resolve_cell` over `_load_cell_state`; a cell with none has its shown value folded.
    -> {hard: row ids, cells: {(row_id, column): (old, new)}, layers: {layer id: new value},
        keys: {}, rows: {row_id: page row}, again: [(entry, n)], time_left: {verdict: n}}"""
    import json
    from collections import Counter

    from sqlalchemy import String, Text, any_, bindparam, cast, func, select
    from sqlalchemy.dialects.postgresql import ARRAY

    import notation_norm
    from database import crud, models

    cs = models.CellSource
    said = cast(cs.value, Text)                     # a layer's stored JSON text - one key per spelling
    rows = {row.row_id: row for row in page}
    out = {"hard": set(), "cells": {}, "layers": {}, "keys": {}, "rows": rows, "again": [], "time_left": Counter()}
    memo = {}

    def judge(column, key, value, n):
        hit = memo.get((column, key))
        if hit is None:
            hit = memo[(column, key)] = fold_value(column, value)
        stored, verdict, again = hit
        if verdict in notation_norm.TIME_LEFT_AS_WRITTEN:
            out["time_left"][verdict] += n
        if again:
            out["again"].append((again, n))
        return stored

    shown = {}                                      # column -> {(type, shown value): folded}
    for column in folded:
        for (kind, value), n in Counter((type(v), v) for v in (getattr(row, column) for row in page)).items():
            stored = judge(column, (kind, value), value, n)
            if stored != value:
                shown.setdefault(column, {})[(kind, value)] = stored
    layered = {}                                    # column -> {stored text: folded value}
    ids = bindparam("ids", list(rows), type_=ARRAY(String))
    # a read of the page's layers names the page's row_id range - what the index reads in order; by its id list
    # alone the plan turned to a whole read of cell_sources from about 10,000 ids at 13M layers (box, 총괄
    # 5ad030347). The list stays: a deleted row's layers in the range are not the page's
    in_page = (cs.table_name == table_name, cs.row_id >= page[0].row_id, cs.row_id <= page[-1].row_id)
    for column, text, n in db.execute(select(cs.column_name, said, func.count())
                                      .where(*in_page, cs.column_name.in_(folded), cs.row_id == any_(ids))
                                      .group_by(cs.column_name, said)):
        value = None if text is None else json.loads(text)
        # a layer saying what a shown value says shares its fold; a JSON object goes by its text
        stored = judge(column, text if isinstance(value, (dict, list)) else (type(value), value), value, n)
        if stored != value:
            layered.setdefault(column, {})[text] = stored

    def moving(column, among):
        """The rows of `among` with a layer of `column` whose text moves."""
        return select(cs.row_id).where(
            *in_page, cs.column_name == column, cs.row_id == any_(among),
            said == any_(bindparam("moves", list(layered[column]), type_=ARRAY(Text))))

    for column in key_parts:
        moves = shown.get(column, {})
        out["hard"].update(row_id for row_id, row in rows.items()
                           if (type(getattr(row, column)), getattr(row, column)) in moves)
        if column in layered:
            out["hard"].update(row_id for (row_id,) in db.execute(moving(column, ids)))
    easy = [row_id for row_id in rows if row_id not in out["hard"]]
    among = bindparam("easy", easy, type_=ARRAY(String))

    def show(row_id, column, new):
        old = getattr(rows[row_id], column)
        if new != old:
            out["cells"][(row_id, column)] = (old, new)

    for column in folded:
        decided = set()
        if column in layered and easy:
            moves, cells = layered[column], {}
            for layer_id, row_id, source, text in db.execute(
                    select(cs.id, cs.row_id, cs.source_name, said)
                    .where(*in_page, cs.column_name == column, cs.row_id.in_(moving(column, among)))):
                cells.setdefault(row_id, []).append((source, text))
                if text in moves:
                    out["layers"][layer_id] = moves[text]
            disagree = []
            for row_id, layers in cells.items():
                texts = {text for _source, text in layers}
                if len(texts) > 1:
                    disagree.append(row_id)
                    continue
                new = moves[texts.pop()]            # one text, and it moves: whichever layer wins
                show(row_id, column, None if new is None else
                     crud.cast_value_by_type(new, col_types.get(column, "string"), column))
            if disagree:
                sources, pins = _load_cell_state(db, table_name, disagree, columns=[column])
                for row_id in disagree:
                    now = {source: moves[text] for source, text in cells[row_id] if text in moves}
                    layers = {source: dict(layer, value=now.get(source, layer["value"]))
                              for source, layer in sources.get((row_id, column), {}).items()}
                    show(row_id, column, _resolve_cell(table_name, col_types, rows[row_id], column, layers,
                                                       pins.get((row_id, column)))["new_value"])
            decided = set(cells)
        moves = shown.get(column)
        if moves:
            for row_id in easy:
                value = getattr(rows[row_id], column)
                if row_id not in decided and (type(value), value) in moves:
                    out["cells"][(row_id, column)] = (value, moves[(type(value), value)])
    return out


class _RowAsWritten:
    """A page row read with its folded cells - what the flush hook reads off the ORM row it stages."""

    def __init__(self, table, row, cells):
        self.__table__, self._row, self._cells = table, row, cells

    def __getattr__(self, name):
        # by the row's names, not its attributes - a column named `t` or `count` is a Row method (총괄 10-14 e)
        if name in self._cells:
            return self._cells[name]
        if name in self._row._mapping:
            return self._row._mapping[name]
        raise AttributeError(name)


def _write_by_values(db, table_name, model, values, tx_id):
    """A page folded by value (`_fold_by_values`), written as the row path writes it: the layers'
    values and the shown values by arrays, one history line per shown cell (`crud.create_audit_log`),
    and each changed row's event as the flush hook stages it (`database.row_event` · collapsed when
    the context says so). The caller commits."""
    import event_constants
    from database import crud, database, models
    from database.context import request_outbox_mode

    if values["layers"]:
        crud.update_by_arrays(db, models.CellSource.__table__, ["value"],
                          [[layer_id, new] for layer_id, new in values["layers"].items()], None, key="id")
    # a row whose key alone moved (an old number spelling, owner 10-20) is written too
    by_row = {row_id: {} for row_id in values["keys"]}
    for (row_id, column), cell in values["cells"].items():
        by_row.setdefault(row_id, {})[column] = cell
    shown, history, written = {}, [], {}
    for row_id, cells in by_row.items():
        # a moved key is written with the row's cells, and its history lines carry it - as the row
        # path sets `business_key_val` before `create_audit_log`
        now = written[row_id] = {column: new for column, (_old, new) in cells.items()}
        if row_id in values["keys"]:
            now["business_key_val"] = values["keys"][row_id]
        shown.setdefault(frozenset(now), []).append([row_id] + [now[column] for column in sorted(now)])
        key = now.get("business_key_val", values["rows"][row_id].business_key_val)
        for column, (old, new) in cells.items():
            history.append(crud.create_audit_log(
                db, table_name, row_id, column, old, new, NOTATION_BACKFILL_SOURCE, NOTATION_BACKFILL_SOURCE,
                transaction_id=tx_id, business_key=key, add_to_cache=False))
    for names, rows in shown.items():
        crud.update_by_arrays(db, model.__table__, sorted(names), rows, None)
    _insert_by_arrays(db, models.AuditLog.__table__, history)
    if not by_row:
        return
    # what each row's cells were - the event's old values, as the flush hook stages an edit's (총괄 355ee9840 4)
    was = {row_id: {column: database.json_value(old) for column, (old, _new) in cells.items()}
           for row_id, cells in by_row.items()}
    if request_outbox_mode.get() == event_constants.OUTBOX_MODE_COLLAPSED:
        database.stage_collapsed_event(db, "EDIT", table_name, list(by_row),
                                       {column for now in written.values() for column in now},
                                       old=[was[row_id] for row_id in by_row])
        return
    db.execute(models.DatabaseOutbox.__table__.insert(), [
        database.row_event("EDIT", table_name, _RowAsWritten(model.__table__, values["rows"][row_id], now),
                           old=was[row_id])
        for row_id, now in written.items()])
    database._notify_outbox_once(db)


def recompute_display_values(db, table_name: str, columns: list = None,
                             row_ids: list = None, apply: bool = False,
                             chunk_size: int = DEFAULT_CHUNK_SIZE, limit: int = None,
                             max_report: int = DEFAULT_MAX_REPORT,
                             log=logger.info, checkpoint=None) -> dict:
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
    from database import crud

    from chain import keyset_scan

    model, col_types = resolve_target(table_name, columns)
    wanted_cols = set(columns) if columns else None

    stats = {"mode": "apply" if apply else "dry-run", "table": table_name,
             "rows_scanned": 0, "pages": 0, "cells_examined": 0,
             "pinned_examined": 0, "cells_changed": 0, "changed_by_tiebreak": 0,
             "changed_by_stale_materialisation": 0, "pinned_changed": 0,
             "changes": [], "stopped": False,
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
            # The page boundary: every earlier page is committed, this one has not begun -
            # the one place a stop is safe (`checkpoint` as in `replay_rule`). There is no
            # position to resume from; a re-run starts over, and recomputing from the stored
            # layers twice gives the same answer (총괄 7ed82bd78).
            if checkpoint is not None and checkpoint(stats["rows_scanned"]):
                stats["stopped"] = True
                log(f"[recompute] stopped by request after {stats['rows_scanned']} rows")
                break
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
                top_rank = crud.get_source_priority(decision["top_source"], table_name)
                tied = sum(1 for s in srcs if crud.get_source_priority(s, table_name) == top_rank)
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
                    _write_resolved(db, table_name, row, col, decision, tx_id)
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
