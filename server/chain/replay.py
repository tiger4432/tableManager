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
from chain.cell_layer import DEFAULT_CHUNK_SIZE, PROTECTED_SOURCES, R1_SOURCE_NAME, R2_AUDIT_SOURCE, ReplayRefused, _claimed_filter, _load_cell_state, _resolve_cell, withdraw_source

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
    """All chain rules via the REAL loader (`chain_ingestion_worker.load_chain_rules`).

    That loader stands the enrichment rules from their `derive.decide`
    declarations like any other, so replay sees exactly the rule set the live
    worker sees - including enrichment. There is no second rule-loading path.
    """
    from chain.ingestion_worker import load_chain_rules
    return [r for r in load_chain_rules() if r.get("enabled", True)]


def find_rule(rule_name: str, rules: list = None, row_scoped: bool = False) -> dict:
    rules = rules if rules is not None else load_rules()
    rule = next((r for r in rules if r.get("name") == rule_name), None)
    if rule is None:
        available = ", ".join(sorted(r.get("name", "?") for r in rules)) or "<none>"
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

    from database import crud, database, models, schemas
    import map_meta_registrar
    # 🪦 [S-214, 판정 370 · 소유자 2026-09-23] `from chain import rule_run` stood here. This
    # module asked the seat to RUN the rule; it now hands the rows over and the worker asks
    # the same seat. The edge 판정 370 was narrowing is gone rather than narrowed.

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
    # 🔴 ONE REPLAY IS ONE TRANSACTION, AND THIS IS THE LINE THAT MAKES IT TRUE.
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
    stage_token = None
    if apply:
        from database.context import request_transaction_id
        # 🔴 "replay_<run>" AND NOT "chain_replay_<run>". The worker prefixes "chain_" to
        #    whatever it is handed (`apply_chain_writes`: `chain_tx_id = f"chain_{tx_id}"`),
        #    so this spelling makes the label that reaches `audit_logs` EXACTLY the one
        #    replay wrote before this round - `chain_replay_<run>`. An operator reading the
        #    ledger does not have to learn a new name for the same run, and the doubled
        #    `chain_chain_replay_<run>` never appears.
        stage_token = request_transaction_id.set("replay_%s" % run_id)
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
        for page in keyset_scan.iter_pages(db, trg_model, columns=[],
                                           condition=selection,
                                           chunk_size=chunk_size, limit=limit,
                                           max_row_id=max_row_id):
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
                    database.stage_collapsed_event(
                        db, "EDIT", trigger_table, [row.row_id for row in page],
                        only_rule=rule.get("name"))
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
                gist = str(page_error).strip().splitlines()
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
                time.sleep(rest_seconds)
    finally:
        if stage_token is not None:
            request_transaction_id.reset(stage_token)

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

def resolve_target(table_name: str, columns: list = None):
    """-> (the table's model, its declared column types), or `ReplayRefused` by name.

    R3's own lookup of the names it is given - asked by the run below and, before anything is
    recorded, by the admin's params judgment (총괄 8e54a261b ④), so both give one sentence.
    """
    from database import crud, models

    model = models.DYNAMIC_TABLES.get(table_name)
    if model is None:
        raise ReplayRefused(f"table model '{table_name}' is not initialized")
    col_types = (crud.TABLE_CONFIG.get(table_name, {}).get("column_types", {}) or {})
    if columns:
        unknown = [c for c in columns if c not in col_types]
        if unknown:
            raise ReplayRefused(f"column(s) not declared on '{table_name}': {unknown}")
    return model, col_types


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

    priority_map = crud.resolve_priority_map(table_name)

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
