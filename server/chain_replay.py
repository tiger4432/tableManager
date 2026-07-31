"""Chain Replay R1 (rule re-application) + R2 (stale source withdrawal).

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

        items = []
        for res in results:
            if not (res and isinstance(res, dict) and res.get("updates")):
                continue
            for raw in res["updates"]:
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

        if apply and items:
            for i in range(0, len(items), WRITE_CHUNK):
                batch = schemas.GeneralUpdateBatch(
                    updates=items[i:i + WRITE_CHUNK],
                    transaction_id=f"chain_replay_{run_id}_{stats['pages']:06d}",
                    silent=False)
                results_rows, changed_cells, _logs, _deleted = crud.apply_batch_updates(
                    db, target_table, batch)
                stats["cells_written"] += len(changed_cells or [])
                for _row, is_new in results_rows:
                    if is_new:
                        stats["rows_created"] += 1
                    else:
                        stats["rows_updated"] += 1
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
        # two per cell.
        remaining = {}
        for row_id, col, src, val, ing in (
                db.query(models.CellSource.row_id, models.CellSource.column_name,
                         models.CellSource.source_name, models.CellSource.value,
                         models.CellSource.ingested_at)
                .filter(models.CellSource.table_name == table_name,
                        models.CellSource.row_id.in_(chunk)).all()):
            remaining.setdefault((row_id, col), {})[src] = {"value": val, "ingested_at": ing}
        pins = {}
        for row_id, col, pin in (
                db.query(models.CellOverwrite.row_id, models.CellOverwrite.column_name,
                         models.CellOverwrite.manual_priority_source)
                .filter(models.CellOverwrite.table_name == table_name,
                        models.CellOverwrite.row_id.in_(chunk)).all()):
            pins[(row_id, col)] = pin

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

                survivors = {s: d for s, d in (remaining.get(cell) or {}).items()
                             if s != source_name}
                old_val = getattr(row, col, None)
                new_val, top_src = crud.compute_priority_value(
                    survivors, pins.get(cell), table_name)
                if new_val is not None:
                    new_val = crud.cast_value_by_type(new_val, col_types.get(col, "string"), col)

                stats["cells_withdrawn"] += 1
                if survivors:
                    stats["revealed"] += 1
                else:
                    stats["emptied"] += 1
                changed = crud.clean_str_value(old_val) != crud.clean_str_value(new_val)
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
