# -*- coding: utf-8 -*-
"""셀의 «층» — 누가 claim 했나, 밑에 무엇이 있나, 그리고 claim 을 «철회»하는 것.

🔴 이 모듈이 «가벼운» 것이 전 재산입니다 (S-211 ①, 판정 358). 워커도 실행기도 재생도
   import 하지 않습니다. 그래서 누가 읽어도 고리가 생기지 않습니다.

🔴 무엇을 고쳤나: `virtual_join_executor.retract_rows` 가 레이어를 철회하려고
   `chain_replay.withdraw_source` 를 «함수 안에서» import 했고, 그 한 줄이 네 모듈짜리
   고리의 마지막 이음매였습니다 —
       chain_builtins -> virtual_join_executor -> chain_replay -> chain_ingestion_worker
       -> chain_builtins
   «단순 4-고리»라 어떤 엣지 하나를 끊어도 통째로 사라지고, 이 엣지가 «호출 하나»로 제일
   쌀습니다.

🔴 그리고 방향이 «성질»로 정해집니다: 철회는 재생의 «행위»가 아니라 둘 다 쓰는 «연산»입니다.
   실행기가 부르는 것은 「참조 행이 사라졌으니 그 조인 층도 간다」이고, 재생이 부르는 것은
   「이 소스의 claim 을 되돌린다」입니다 — 같은 연산, 다른 사유. 그래서 둘보다 «아래»로 내렸습니다.

⚠️ 같이 내려온 것이 «열»입니다 (제 첫 보고는 「셋」이라 했고 그것이 과소 측정이었습니다):
   상수·예외 다섯 + 사설 헬퍼 셋(`_claimed_filter`·`_load_cell_state`·`_resolve_cell`).
   헬퍼 셋은 `chain_replay` 의 «다른 함수들도» 쓰므로 그쪽이 여기서 읽습니다 — 둘째 철자 0.

⚠️ `ReplayRefused` 의 «이름»은 재생에서 왔습니다. 이름을 바꾸면 이 예외를 잡는 자리
   (`main`·`retroactive`·`frame_confirmation`·CLI)가 전부 바뀜므로 그대로 둡니다 — 이동이
   개명까지 같이 하면 무엇이 깨졌는지 읽기 어려워집니다.
"""
import logging
import uuid

from chain import keyset_scan

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = keyset_scan.DEFAULT_CHUNK_SIZE

SAMPLE_LIMIT = 20

# R1 provenance. Deliberately the SAME name the live worker writes under, so a
# replayed cell is indistinguishable from an incrementally-ingested one - which
# is the point: replay is not a new layer, it is the same layer recomputed.
R1_SOURCE_NAME = "chain_ingestion"

# R2 provenance for the audit trail only (it writes no cell_sources row).
R2_AUDIT_SOURCE = "chain_replay_withdraw"

# Sources R2 must never withdraw. `user` is the only layer that means "a human
# typed this" (crud.SOURCE_PRIORITY comment) - withdrawing it is data loss with
# extra steps, so it is refused at the API, not left to the caller's discretion.
PROTECTED_SOURCES = frozenset({"user"})

class ReplayRefused(Exception):
    """Raised when a replay must not proceed. The message states why."""

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

def cells_stamped_by(db, origin_row_ids, chunk_size: int = DEFAULT_CHUNK_SIZE) -> dict:
    """`{(table_name, source_name): (columns, row_ids)}` for cells these rows fed.

    🔴 [S-280 · 판정 434] THE NOTE READ BACK. `origin_row_id` was written while the input
    row was still there, so this answers 「그 행이 먹인 칸이 어디인가」 after the row is
    gone — which is the one question a deleted row cannot be asked itself.

    READ ONLY, and grouped the way `withdraw_source` takes its arguments, so the caller
    does no regrouping of its own.
    """
    from database import models

    ids = [str(item) for item in (origin_row_ids or ()) if item]
    found = {}
    for i in range(0, len(ids), chunk_size):
        rows = (db.query(models.CellSource.table_name, models.CellSource.source_name,
                         models.CellSource.column_name, models.CellSource.row_id)
                .filter(models.CellSource.origin_row_id.in_(ids[i:i + chunk_size])).all())
        for table_name, source_name, column_name, row_id in rows:
            columns, row_ids = found.setdefault((table_name, source_name), (set(), set()))
            columns.add(column_name)
            row_ids.add(row_id)
    return found


def withdraw_by_origin(db, origin_row_ids, apply: bool = False, log=logger.info) -> dict:
    """Withdraw every cell stamped as having been read FROM one of these rows.

    🔴 [S-280 · 판정 435 ③] `columns` AND `row_ids` AND `apply`, all three. Narrowing by
    the source NAME alone is the whole-table withdrawal ruling 433 ③ found standing in
    `retract_rows`; narrowing by (columns x rows) resolves even a shared channel name —
    `chain_ingestion`, which `join_into` writes under by the owner's own ruling — down to
    exactly the cells one rule wrote on the rows it wrote them on.

    ⛔ A `user` LAYER IS SKIPPED AND COUNTED, NOT RAISED ON. `withdraw_source` refuses that
    source outright, and one such group would otherwise abort the withdrawal of every other
    group in the same deletion. A human's value carrying a chain's origin stamp is a
    contradiction worth a line, not a reason to leave the rest standing.
    """
    stats = {"mode": "apply" if apply else "dry-run", "groups": 0, "cells_withdrawn": 0,
             "protected_skipped": 0}
    for (table_name, source_name), (columns, row_ids) in sorted(
            cells_stamped_by(db, origin_row_ids).items()):
        if source_name in PROTECTED_SOURCES:
            stats["protected_skipped"] += len(columns) * len(row_ids)
            log("[withdraw-origin] '%s' on '%s' is a protected layer and was NOT withdrawn "
                "— a human's value cannot carry a chain's origin, so this is worth reading",
                source_name, table_name)
            continue
        stats["groups"] += 1
        one = withdraw_source(db, table_name, source_name, columns=sorted(columns),
                              row_ids=sorted(row_ids), apply=apply, log=log)
        stats["cells_withdrawn"] += one.get("cells_withdrawn", 0)
    return stats


def withdraw_source(db, table_name: str, source_name: str, columns: list = None,
                    row_ids: list = None, apply: bool = False,
                    chunk_size: int = DEFAULT_CHUNK_SIZE, log=logger.info,
                    checkpoint=None) -> dict:
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
    # existing databases by scripts/ops_setup_db_performance.py Step 3.10, which then
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

    # 🔴 THE OUTBOX LABEL. Same defect, same shape, same fix as R3 - see
    # `recompute_display_values` for why the label is separable from the layer.
    # R2 reveals a cell by `setattr`, so the global `before_flush` staged its
    # events under the context DEFAULTS: `source_name="user"`, `updated_by="system"`
    # and a fresh uuid4 per event. Measured on assy_qa: withdrawing 4 cells staged
    # 4 events with 4 distinct transaction ids, the live rule set accepted every
    # one, and a connected client received 4 `batch_row_upsert` messages for
    # `dt_job_attribution` - a table nobody withdrew anything from.
    #
    # ⚠️ WHY THIS IS SAFE HERE EVEN THOUGH R2 DELETES A LAYER - the question R3 did
    # not have to answer. The deletion predicate is built from the `source_name`
    # PARAMETER (`_claimed_filter`, and the `CellSource.source_name == source_name`
    # filter in the delete below), never from `request_source`. So do the two
    # refusals: `source_name in PROTECTED_SOURCES` and `pins.get(cell) ==
    # source_name`. The context var and the parameter share a concept and nothing
    # else - there is no path from one to the other. Verified by measurement rather
    # than by this paragraph: the SAME fixture run with and without this block
    # deletes the same 4 layers, skips the same human-pinned cell, and leaves a
    # survivor set with an identical sha256
    # (`test_withdraw_deletes_the_same_layers_whatever_the_outbox_label`).
    #
    # ⚠️ AND IT TAKES NOTHING AWAY FROM THE OPERATOR. A withdrawal CHANGES THE
    # DISPLAYED VALUE, so "does the client still hear about it" is a real question -
    # and the measured answer is that the client never heard about the withdrawn
    # cells in the first place. The chain worker broadcasts what the chain WROTE
    # (target tables), never the table the events came from, so before this change
    # the only messages a client got named `dt_job_attribution`. Those were the
    # spurious cascade, not the withdrawal. What an operator reads to understand a
    # withdrawal is the AuditLog rows below, and they still carry
    # `source_name=R2_AUDIT_SOURCE` - the outbox `source_name` is the loop-filter
    # CHANNEL, not the provenance record.
    with crud.transaction_context(R2_AUDIT_SOURCE, tx_id, R1_SOURCE_NAME):
        for i in range(0, len(all_row_ids), chunk_size):
            if checkpoint is not None and checkpoint(i):
                stats["stopped"] = True
                log(f"[withdraw] stopped by request after {i} rows")
                break
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
                            # 🔴 ONE SPELLING FOR THE LAYER WINNER. This said `revealed_source` and the block
                            #    below said `winning_source`, for the SAME value from the same
                            #    helper -- the name was restating what the container already
                            #    says. A dict sitting next to `row_id`/`column` is that cell's
                            #    answer; the preview's return dict is the preview's. Subject in
                            #    the name means one more name per container, which is how this
                            #    got to three (ruling 40).
                            "top_source": top_src,
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
