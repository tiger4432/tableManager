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
import uuid

logger = logging.getLogger(__name__)

import keyset_scan

DEFAULT_CHUNK_SIZE = keyset_scan.DEFAULT_CHUNK_SIZE
WRITE_CHUNK = 1000
SAMPLE_LIMIT = 20

# R1 provenance. Deliberately the SAME name the live worker writes under, so a
# replayed cell is indistinguishable from an incrementally-ingested one - which
# is the point: replay is not a new layer, it is the same layer recomputed.
R1_SOURCE_NAME = "chain_ingestion"

# R2 provenance for the audit trail only (it writes no cell_sources row).
R2_AUDIT_SOURCE = "chain_replay_withdraw"

# R3 provenance for the audit trail only (it writes no cell_sources row either).
# A recompute changes NO stored fact - it only re-answers "which stored layer wins"
# and re-materialises that answer - so it must be distinguishable in the history
# from a withdrawal, which does delete a claim.
R3_AUDIT_SOURCE = "resolution_recompute"

# Upper bound on the per-cell change list a recompute keeps in memory. The AuditLog
# rows it writes are the permanent, unbounded enumeration; this only bounds what one
# call hands back to a CLI or a report. `changes_truncated` says when it bit.
DEFAULT_MAX_REPORT = 10000

# R1 never writes a blank value. See the module docstring: "the rule produces
# nothing here" is R2's statement to make, not R1's.
SKIP_BLANK = True

# Sources R2 must never withdraw. `user` is the only layer that means "a human
# typed this" (crud.SOURCE_PRIORITY comment) - withdrawing it is data loss with
# extra steps, so it is refused at the API, not left to the caller's discretion.
PROTECTED_SOURCES = frozenset({"user"})


class ReplayRefused(Exception):
    """Raised when a replay must not proceed. The message states why."""


# ---------------------------------------------------------------------------
# Rule loading + ordering (the multi-rule contract)
# ---------------------------------------------------------------------------

def load_rules() -> list:
    """All chain rules via the REAL loader (`chain_ingestion_worker.load_chain_rules`).

    That loader also synthesises the enrichment dedup rules from
    enrichment_rules.json, so replay sees exactly the rule set the live worker
    sees - including enrichment. There is no second rule-loading path.
    """
    from chain_ingestion_worker import load_chain_rules
    return [r for r in load_chain_rules() if r.get("enabled", True)]


def find_rule(rule_name: str, rules: list = None) -> dict:
    rules = rules if rules is not None else load_rules()
    rule = next((r for r in rules if r.get("name") == rule_name), None)
    if rule is None:
        available = ", ".join(sorted(r.get("name", "?") for r in rules)) or "<none>"
        raise ReplayRefused(f"chain rule '{rule_name}' not found or disabled; available: {available}")
    return rule


def order_rules(rules: list) -> list:
    """Topologically order rules so a producer replays before its consumer.

    The live config makes this mandatory rather than nice-to-have:
        production_plan  -> inventory_master
        inventory_master -> inventory_master     (trigger == target)
    Rule 1's output is rule 2's input, so replaying 2 first would recompute from
    stale data. And rule 2 triggers itself, so it is a self-edge.

    SELF-EDGES ARE IGNORED FOR ORDERING and handled by the snapshot guard in
    `replay_rule` instead (a rule cannot be ordered before itself). A cycle
    between DIFFERENT tables is refused by name: there is no correct order for
    it, and picking one silently would produce a result nobody could reason
    about.
    """
    by_target = {}
    for r in rules:
        by_target.setdefault(r.get("target_table"), []).append(r)

    state = {}   # rule name -> 0 visiting / 1 done
    ordered = []

    def visit(rule, path):
        name = rule.get("name")
        if state.get(name) == 1:
            return
        if state.get(name) == 0:
            cycle = " -> ".join(path + [name])
            raise ReplayRefused(
                f"chain rules form a cycle across tables and cannot be ordered: {cycle}. "
                f"Replay them one at a time with an explicit order you can justify.")
        state[name] = 0
        trigger = rule.get("trigger_table")
        for producer in by_target.get(trigger, []):
            if producer.get("name") == name:
                continue  # self-edge: the snapshot guard handles it, not the order
            visit(producer, path + [name])
        state[name] = 1
        ordered.append(rule)

    for r in rules:
        visit(r, [])
    return ordered


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


def _to_payloads(page, columns: list) -> list:
    """Synthesize the outbox payload shape the mappers expect.

    Same construction as `backfill_enrichment.run_backfill`: {"row_id", "data":
    {col: {"value": v}}}. `payloads_to_df` reads exactly these two keys.
    """
    payloads = []
    for row in page:
        # row[0] is row_id (keyset_scan contract), then the requested columns.
        payloads.append({
            "row_id": row[0],
            "data": {col: {"value": val} for col, val in zip(columns, row[1:])},
        })
    return payloads


def replay_rule(db, rule: dict, apply: bool = False, limit: int = None,
                chunk_size: int = DEFAULT_CHUNK_SIZE, log=logger.info) -> dict:
    """[R1] Re-run one chain rule over the trigger table's current contents.

    Dry-run (default) reads only and reports what WOULD change, including which
    cells a human's value protects and which cells lost their value (R2
    candidates). Apply commits per write chunk, so a large replay is restartable
    and idempotent - re-running recomputes the same values.
    """
    from database import crud, models, schemas
    import map_meta_registrar
    from chain_ingestion_worker import execute_custom_mapper

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
        "rule": rule.get("name"), "trigger_table": trigger_table,
        "target_table": target_table, "self_triggering": is_self_triggering(rule),
        "rows_scanned": 0, "pages": 0, "mapper_items": 0,
        "cells_proposed": 0, "cells_written": 0,
        "skipped_blank_cells": 0, "user_protected_cells": 0,
        "rows_created": 0, "rows_updated": 0,
        "map_metadata_items": 0, "scoped_batches": 0, "maps_replaced": 0,
        "withdrawal_candidates": [], "samples": [],
    }

    run_id = uuid.uuid4().hex[:8]
    is_batch = bool(rule.get("is_batch"))
    module_name, func_name = rule.get("mapper_module"), rule.get("mapper_function")

    for page in keyset_scan.iter_pages(db, trg_model, columns=[getattr(trg_model, c) for c in columns],
                                       chunk_size=chunk_size, limit=limit, max_row_id=max_row_id):
        stats["pages"] += 1
        stats["rows_scanned"] += len(page)
        payloads = _to_payloads(page, columns)

        # The REAL mapper invocation path (rule kwarg support, error handling).
        if is_batch:
            results = [execute_custom_mapper(module_name, func_name, db, payloads, rule=rule)]
        else:
            results = [execute_custom_mapper(module_name, func_name, db, p, rule=rule)
                       for p in payloads]

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
                    if SKIP_BLANK and crud.clean_str_value(val) == "":
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

            for scope, raws in _scoped_batch_outputs(res, rule, target_table):
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
                    scoped_batches.append((scope, batch_items))

        if apply and (items or metadata_items or scoped_batches):
            # Metadata first is the live worker's ordering too: absent-only map
            # registration must not synthesize a frame before the explicit
            # standard frame and valid_die_ref arrive.
            if metadata_items:
                _apply_replay_batch(db, schemas, crud, map_meta_registrar.META_TABLE,
                                    metadata_items, run_id, stats, stats["pages"])
            for i in range(0, len(items), WRITE_CHUNK):
                _apply_replay_batch(db, schemas, crud, target_table, items[i:i + WRITE_CHUNK],
                                    run_id, stats, stats["pages"])
            for scope, batch_items in scoped_batches:
                _apply_replay_batch(db, schemas, crud, target_table, batch_items,
                                    run_id, stats, stats["pages"], replace_map=True, scope=scope)
                stats["maps_replaced"] += 1
        elif items:
            # Dry-run: count the cells a human's value would keep protected. This
            # is the number that makes "the user layer is safe" observable rather
            # than merely argued.
            stats["user_protected_cells"] += _count_user_protected(db, target_table, items)

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
    """Validate and expose replace-map batches without broadening their scope."""
    outputs = result.get("batches") or ()
    if outputs and not rule.get("allow_replace_map", False):
        raise ReplayRefused(f"rule '{rule.get('name')}' returned scoped batches without allow_replace_map")
    for raw in outputs:
        if not isinstance(raw, dict) or not raw.get("replace_map"):
            raise ReplayRefused("chain scoped batch must explicitly set replace_map=true")
        if (raw.get("target_table") or target_table) != target_table:
            raise ReplayRefused("chain scoped batch cannot redirect to another target table")
        scope = raw.get("scope")
        if not isinstance(scope, dict) or not scope:
            raise ReplayRefused("chain scoped batch requires a non-empty scope")
        yield scope, raw.get("updates") or ()


def _apply_replay_batch(db, schemas, crud, table_name, items, run_id, stats, page,
                        replace_map=False, scope=None):
    batch = schemas.GeneralUpdateBatch(
        updates=items, transaction_id=f"chain_replay_{run_id}_{page:06d}", silent=False,
        replace_map=replace_map, scope=scope)
    results_rows, changed_cells, _logs, _deleted = crud.apply_batch_updates(db, table_name, batch)
    stats["cells_written"] += len(changed_cells or [])
    for _row, is_new in results_rows:
        if is_new:
            stats["rows_created"] += 1
        else:
            stats["rows_updated"] += 1


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
                       models.CellSource.source_name == "user")
               .all())
        for row_id, col in src:
            if col in by_key.get(row_to_bk.get(row_id), ()):
                protected += 1
    return protected


def replay_all(db, apply: bool = False, limit: int = None,
               chunk_size: int = DEFAULT_CHUNK_SIZE, log=logger.info) -> dict:
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
    log(f"[replay] order: {' -> '.join(r.get('name', '?') for r in rules)}")
    out = {"mode": "apply" if apply else "dry-run",
           "order": [r.get("name") for r in rules], "rules": []}
    for rule in rules:
        out["rules"].append(replay_rule(db, rule, apply=apply, limit=limit,
                                        chunk_size=chunk_size, log=log))
    return out


# ---------------------------------------------------------------------------
# R2 — stale source withdrawal
# ---------------------------------------------------------------------------

def _claimed_filter(table_name: str, source_name: str, columns: list = None):
    """The predicate for "cells `source_name` claims on `table_name`".

    Extracted so `count_withdrawable` and `withdraw_source` cannot answer
    different questions: a count that used a slightly different filter from the
    operation it previews is a count that lies, and it would lie silently.
    """
    from database import models

    conds = [models.CellSource.table_name == table_name,
             models.CellSource.source_name == source_name]
    if columns:
        conds.append(models.CellSource.column_name.in_(list(columns)))
    return conds


def _load_cell_state(db, table_name: str, chunk_row_ids: list):
    """Stored sources + human pins for a chunk of rows: TWO batched queries, not two per cell.

    Extracted so R2 (`withdraw_source`) and R3 (`recompute_display_values`) cannot
    assemble the resolver's input differently. Two functions that build the input to
    one decision in two ways are two decisions, and the difference would only show up
    on the cells where it matters.

    `ingested_at` travels with every layer because `crud.compute_priority_value` reads
    it to break a tie between equally-ranked sources - see its docstring. Dropping it
    here would silently put the resolution back on dict order.
    """
    from database import models

    sources = {}
    for row_id, col, src, val, ing in (
            db.query(models.CellSource.row_id, models.CellSource.column_name,
                     models.CellSource.source_name, models.CellSource.value,
                     models.CellSource.ingested_at)
            .filter(models.CellSource.table_name == table_name,
                    models.CellSource.row_id.in_(chunk_row_ids))
            .order_by(models.CellSource.source_name.asc()).all()):
        sources.setdefault((row_id, col), {})[src] = {"value": val, "ingested_at": ing}

    pins = {}
    for row_id, col, pin in (
            db.query(models.CellOverwrite.row_id, models.CellOverwrite.column_name,
                     models.CellOverwrite.manual_priority_source)
            .filter(models.CellOverwrite.table_name == table_name,
                    models.CellOverwrite.row_id.in_(chunk_row_ids)).all()):
        pins[(row_id, col)] = pin

    return sources, pins


def _resolve_cell(table_name: str, col_types: dict, row, col: str,
                  cell_sources: dict, pin, exclude_source: str = None) -> dict:
    """Re-answer "what should this cell display" from its STORED layers.

    The one place R2 and R3 agree, and the reason they must: R2 is exactly R3 with
    one layer removed. Returns the decision without writing it, so a dry-run and an
    apply run the identical computation.
    """
    from database import crud

    survivors = {s: d for s, d in (cell_sources or {}).items() if s != exclude_source}
    old_val = getattr(row, col, None)
    new_val, top_src = crud.compute_priority_value(survivors, pin, table_name)
    if new_val is not None:
        new_val = crud.cast_value_by_type(new_val, col_types.get(col, "string"), col)
    return {
        "survivors": survivors,
        "old_value": old_val,
        "new_value": new_val,
        "top_source": top_src,
        "changed": crud.clean_str_value(old_val) != crud.clean_str_value(new_val),
    }


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


def withdraw_source(db, table_name: str, source_name: str, columns: list = None,
                    row_ids: list = None, apply: bool = False,
                    chunk_size: int = DEFAULT_CHUNK_SIZE, log=logger.info) -> dict:
    """[R2] Retract `source_name`'s claim on cells, revealing the layer beneath.

    For each affected cell: delete that one `cell_sources` row, recompute
    `crud.compute_priority_value` over the REMAINING sources, write the revealed
    value to the materialised column, and record an AuditLog entry naming the
    withdrawn source.

    Refusals (both tested by injection, both the reason this is not T1):
      - `source_name` in PROTECTED_SOURCES -> refused outright. There is no
        supported way to withdraw a human's value from here.
      - a cell whose `manual_priority_source` pins THIS source -> skipped and
        counted as `pinned_skipped`. The pin is a human saying "show me this
        one"; silently honouring the withdrawal would override that choice.
    """
    from database import crud, models

    if source_name in PROTECTED_SOURCES:
        raise ReplayRefused(
            f"refusing to withdraw source '{source_name}': it is the layer that means "
            f"'a human typed this'. Withdrawing it would remove a human's value, which "
            f"this tool does not do. Edit the cell instead.")
    model = models.DYNAMIC_TABLES.get(table_name)
    if model is None:
        raise ReplayRefused(f"table model '{table_name}' is not initialized")

    col_types = (crud.TABLE_CONFIG.get(table_name, {}).get("column_types", {}) or {})
    if columns:
        unknown = [c for c in columns if c not in col_types]
        if unknown:
            raise ReplayRefused(f"column(s) not declared on '{table_name}': {unknown}")

    stats = {"mode": "apply" if apply else "dry-run", "table": table_name,
             "source": source_name, "cells_matched": 0, "cells_withdrawn": 0,
             "revealed": 0, "emptied": 0, "pinned_skipped": 0,
             "value_unchanged": 0, "samples": []}

    # 1) Cells this source claims.
    #
    # COST, corrected by measurement 2026-07-31 (the earlier note here guessed,
    # and guessed generously). `idx_sources_lookup_source` is
    # (table_name, row_id, column_name, source_name) -- `source_name` LAST -- so
    # it cannot serve this predicate at all, and PostgreSQL did not fall back to
    # an in-index filter: it fell back to a full parallel Seq Scan of the WHOLE
    # `cell_sources` table. On 13,148,355 rows that was 861ms and 263,369 buffers
    # to return 75,000 matches.
    #
    # `idx_sources_by_source` (table_name, source_name, column_name, row_id)
    # exists for this predicate -- declared in models.py CellSource and built on
    # existing databases by scripts/setup_db_performance.py Step 3.10, which then
    # EXPLAINs this exact statement to prove the planner uses it. With it the same
    # query is an Index Only Scan: 10.9ms, 1,106 buffers, 0 rows discarded.
    # `count_withdrawable` below rides the same index for the same reason.
    q = (db.query(models.CellSource.row_id, models.CellSource.column_name)
         .filter(*_claimed_filter(table_name, source_name, columns)))
    if row_ids:
        q = q.filter(models.CellSource.row_id.in_(list(row_ids)))
    claimed = q.all()
    stats["cells_matched"] = len(claimed)
    if not claimed:
        return stats

    by_row = {}
    for row_id, col in claimed:
        by_row.setdefault(row_id, set()).add(col)
    log(f"[withdraw] '{source_name}' claims {len(claimed)} cell(s) across {len(by_row)} row(s) "
        f"in '{table_name}'")

    tx_id = f"{R2_AUDIT_SOURCE}_{uuid.uuid4().hex[:8]}"
    all_row_ids = list(by_row)

    for i in range(0, len(all_row_ids), chunk_size):
        chunk = all_row_ids[i:i + chunk_size]
        rows = {r.row_id: r for r in db.query(model).filter(model.row_id.in_(chunk)).all()}

        # Remaining sources + pins for the whole chunk: two batched queries, not
        # two per cell. Shared with R3 so the two operations cannot assemble the
        # resolver's input differently.
        remaining, pins = _load_cell_state(db, table_name, chunk)

        delete_keys = []
        for row_id in chunk:
            row = rows.get(row_id)
            if row is None:
                continue
            for col in sorted(by_row.get(row_id, ())):
                cell = (row_id, col)
                if pins.get(cell) == source_name:
                    stats["pinned_skipped"] += 1
                    if len(stats["samples"]) < SAMPLE_LIMIT:
                        stats["samples"].append({
                            "row_id": row_id, "column": col, "action": "skipped",
                            "why": f"a human pinned '{source_name}' on this cell "
                                   f"(manual_priority_source); withdrawing it would "
                                   f"override that choice"})
                    continue

                decision = _resolve_cell(table_name, col_types, row, col,
                                         remaining.get(cell), pins.get(cell),
                                         exclude_source=source_name)
                survivors = decision["survivors"]
                old_val = decision["old_value"]
                new_val = decision["new_value"]
                top_src = decision["top_source"]
                changed = decision["changed"]

                stats["cells_withdrawn"] += 1
                if survivors:
                    stats["revealed"] += 1
                else:
                    stats["emptied"] += 1
                if not changed:
                    stats["value_unchanged"] += 1
                if len(stats["samples"]) < SAMPLE_LIMIT:
                    stats["samples"].append({
                        "row_id": row_id, "column": col, "action": "withdraw",
                        "old_value": old_val, "new_value": new_val,
                        "revealed_source": top_src,
                        "remaining_sources": sorted(survivors)})

                if apply:
                    delete_keys.append(cell)
                    if changed:
                        setattr(row, col, new_val)
                        # Make the withdrawal legible in the place the client
                        # already looks to answer "why does this cell say this".
                        crud.create_audit_log(
                            db, table_name, row_id, col, old_val, new_val,
                            R2_AUDIT_SOURCE, f"withdraw:{source_name}",
                            transaction_id=tx_id,
                            business_key=getattr(row, "business_key_val", None))

        if apply and delete_keys:
            # Grouped by column so the delete is a handful of bounded IN lists
            # (one per column) instead of one OR clause per cell - a chunk of
            # 1000 rows x N columns would otherwise build a several-thousand-term
            # predicate that no planner handles well.
            by_col = {}
            for r, c in delete_keys:
                by_col.setdefault(c, []).append(r)
            for col, rids in by_col.items():
                for j in range(0, len(rids), chunk_size):
                    db.query(models.CellSource).filter(
                        models.CellSource.table_name == table_name,
                        models.CellSource.source_name == source_name,
                        models.CellSource.column_name == col,
                        models.CellSource.row_id.in_(rids[j:j + chunk_size]),
                    ).delete(synchronize_session=False)
            db.commit()

    if not apply:
        db.rollback()
    log(f"[withdraw] {stats['mode']}: {stats['cells_withdrawn']} cell(s) withdrawn "
        f"({stats['revealed']} revealed another source, {stats['emptied']} left empty, "
        f"{stats['pinned_skipped']} skipped as human-pinned)")
    return stats


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
    `max_report`, and `changes_truncated` says whether the list ran out of budget.
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
             "changes": [], "changes_truncated": False}

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
                        "winning_source": decision["top_source"],
                        "reason": reason,
                        "sources": sorted(srcs),
                    })
                else:
                    stats["changes_truncated"] = True

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
