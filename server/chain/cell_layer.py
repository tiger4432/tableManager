# -*- coding: utf-8 -*-
"""셀의 «층» — 누가 claim 했나, 밑에 무엇이 있나, 그리고 claim 을 «철회»하는 것.

🔴 이 모듈이 «가벼운» 것이 전 재산입니다 (S-211 ①, 판정 358). 워커도 실행기도 재생도
   import 하지 않습니다. 그래서 누가 읽어도 고리가 생기지 않습니다.

🔴 무엇을 고쳤나: `virtual_join_executor.retract_rows` 가 레이어를 철회하려고
   `chain_replay.withdraw_source` 를 «함수 안에서» import 했고, 그 한 줄이 네 모듈짜리
   고리의 마지막 이음매였습니다 —
       chain.synthesis -> virtual_join_executor -> chain_replay -> chain_ingestion_worker
       -> chain.synthesis
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

from sqlalchemy import text

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

#: Who deleted a shell row - the history line's name, the chain's write seat and the sweep alike (5eee501eb).
SHELL_DELETER = "chain_shell_rows"


def key_columns(table_name: str) -> set:
    """The columns a row of this table is known by - its `composite_key_source`, else its `business_key`
    (what `crud.unfilled_key_columns` reads too)."""
    from database import crud

    config = crud.TABLE_CONFIG.get(table_name) or {}
    return {str(c) for c in (config.get("composite_key_source") or [config.get("business_key")]) if c}


def shells(db, table_name: str, row_ids) -> list:
    """is_shell, for each of these rows (총괄 5eee501eb · 판정 ㄱ, 소유자 10-09 「키값만 남아 있네」): no layer
    outside the key columns holds a value - a blank the chain wrote is none - every key-column layer is the
    chain's, and no person's layer anywhere, blank or not. And the row shows nothing outside its keys, so a
    value no layer carries is not taken for nothing. The chain's write seat and the sweep ask this one."""
    from database import crud, models

    model = models.DYNAMIC_TABLES.get(table_name)
    ids = list(dict.fromkeys(str(r) for r in row_ids or () if r))
    if model is None or not ids:
        return []
    keys = key_columns(table_name)
    shown = [c for c in (crud.TABLE_CONFIG.get(table_name) or {}).get("column_types") or {} if c not in keys]
    if not shown:      # every row of a table declared only by its keys is its keys - none is a shell
        return []
    found = []
    for i in range(0, len(ids), DEFAULT_CHUNK_SIZE):
        chunk = ids[i:i + DEFAULT_CHUNK_SIZE]
        layers, _pins = _load_cell_state(db, table_name, chunk)
        by_row = {}
        for (row_id, column), named in layers.items():
            by_row.setdefault(row_id, []).extend((column, name, entry["value"]) for name, entry in named.items())
        for row in db.query(model).filter(model.row_id.in_(chunk)).all():
            if any(not crud.is_blank_value(getattr(row, column, None)) for column in shown):
                continue
            if all(crud.layer_writer(name) != crud.USER_SOURCE and (
                    crud.layer_writer(name) == crud.CHAIN_SOURCE if column in keys else crud.is_blank_value(value))
                   for column, name, value in by_row.get(row.row_id, ())):
                found.append(row.row_id)
    return found


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
        "changed": crud.values_differ(old_val, new_val, col_types.get(col, "string")),
    }

def cells_stamped_by(db, origin_row_ids, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list:
    """`[(table_name, row_id, column_name, source_name, origin_row_id)]` - the layers these rows fed.

    🔴 [S-280 · 판정 434] THE NOTE READ BACK. `origin_row_id` was written while the input
    row was still there, so this answers 「그 행이 먹인 칸이 어디인가」 after the row is
    gone — which is the one question a deleted row cannot be asked itself.

    READ ONLY, one layer a tuple: a (columns x rows) group per layer name also named cells
    another row fed under a shared name (`chain_ingestion`).
    """
    from database import models

    # Each origin once, in order: per origin, a repeat would be answered twice (QA c762f6820 · 총괄 ③).
    ids = list(dict.fromkeys(str(item) for item in (origin_row_ids or ()) if item))
    one_at_a_time = db.get_bind().dialect.name == "postgresql"
    found = []
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i:i + chunk_size]
        found.extend(tuple(row) for row in (
            db.execute(STAMPED_BY_EACH_ORIGIN, {"ids": chunk}) if one_at_a_time else
            db.query(models.CellSource.table_name, models.CellSource.row_id,
                     models.CellSource.column_name, models.CellSource.source_name,
                     models.CellSource.origin_row_id)
            .filter(models.CellSource.origin_row_id.in_(chunk)).all()))
    return found


#: `cells_stamped_by` on PostgreSQL: each origin asked through `idx_sources_by_origin` on its own.
#: 🔴 OFFSET 0 KEEPS THE LATERAL FROM BEING FOLDED (총괄 d28171060 - 운영에서 그 인덱스의 scans 가 안
#:    늘었다). As one `IN (1,000)` the planner sizes the batch from the statistics - believing an
#:    origin feeds thousands of cells (a join's value row feeds many), it read the whole table:
#:    measured on 3M rows, 1,000 origins not stamped yet, a Seq Scan 370 ms; this, an index
#:    probe per origin, 10 ms.
STAMPED_BY_EACH_ORIGIN = text(
    "SELECT c.table_name, c.row_id, c.column_name, c.source_name, c.origin_row_id"
    "  FROM unnest(CAST(:ids AS varchar[])) AS o(id)"
    "  CROSS JOIN LATERAL (SELECT * FROM cell_sources s WHERE s.origin_row_id = o.id OFFSET 0) c")


def withdraw_by_origin(db, origin_row_ids, apply: bool = False, log=logger.info,
                       table: str = None, columns=None, keep=()) -> dict:
    """Withdraw every cell stamped as having been read FROM one of these rows.

    🔴 [S-280 · 판정 435 ③] THE LAYER THE STAMP NAMES, NOT ITS NAME. Narrowing by the source
    NAME alone is the whole-table withdrawal ruling 433 ③ found standing in `retract_rows`;
    `chain_ingestion` is a shared name (`join_into` writes under it by the owner's own ruling).

    ⛔ A `user` LAYER IS SKIPPED AND COUNTED, NOT RAISED ON. `withdraw_source` refuses that
    source outright, and one such group would otherwise abort the withdrawal of every other
    group in the same deletion. A human's value carrying a chain's origin stamp is a
    contradiction worth a line, not a reason to leave the rest standing.

    🔴 AN EDIT IS THE SAME WITHDRAWAL, NARROWED (총괄 e35500433 · b13de0353): `table` and `columns`
    are the rule that ran, and `keep` {(origin_row_id, row_id)} the rows its write just put that
    origin's output on. A deletion passes none of the three.

    `lost_a_layer` is {table: (columns, row ids)} of the layers withdrawn - what the delete path
    tells the rules (총괄 e11bb4de0 (나)).
    """
    stats = {"mode": "apply" if apply else "dry-run", "groups": 0, "cells_withdrawn": 0,
             "protected_skipped": 0, "lost_a_layer": {}}
    keep = set(keep or ())
    claims_by_table, groups, protected = {}, set(), set()
    for table_name, row_id, column, source_name, origin in cells_stamped_by(db, origin_row_ids):
        if ((table is not None and table_name != table) or (columns is not None and column not in columns)
                or (origin, row_id) in keep):
            continue
        if source_name in PROTECTED_SOURCES:
            stats["protected_skipped"] += 1
            protected.add((table_name, source_name))
            continue
        groups.add((table_name, source_name))
        claims_by_table.setdefault(table_name, {}).setdefault((row_id, column), set()).add(source_name)
        lost_columns, lost_rows = stats["lost_a_layer"].setdefault(table_name, (set(), set()))
        lost_columns.add(column)
        lost_rows.add(row_id)
    for table_name, source_name in sorted(protected):
        log("[withdraw-origin] '%s' on '%s' is a protected layer and was NOT withdrawn "
            "— a human's value cannot carry a chain's origin, so this is worth reading",
            source_name, table_name)
    stats["groups"] = len(groups)
    # 🔴 ONE WITHDRAWAL PER TABLE, NOT ONE PER LAYER NAME (총괄 10-07 ①). A copy names its layer per
    # source row, so a group was a row: 1,000 rows were 1,000 `withdraw_source` calls, each its own
    # queries and commit - measured 332 s on PostgreSQL. One pass, the same per-cell order.
    for table_name, claims in sorted(claims_by_table.items()):
        target = resolve_target(table_name, sorted({col for _row, col in claims}))
        one = _withdraw_cells(db, table_name, target,
                              {cell: sorted(names) for cell, names in claims.items()},
                              apply=apply, log=log,
                              label="%d source(s) claim" % len({g for g in groups if g[0] == table_name}))
        stats["cells_withdrawn"] += one.get("cells_withdrawn", 0)
    return stats


def resolve_target(table_name: str, columns: list = None):
    """-> (the table's model, its declared column types), or `ReplayRefused` by name.

    The one lookup of a table and its columns for R2 (`withdraw_source`) and R3
    (`replay.recompute_display_values`) - and, before anything is recorded, for the admin's
    params judgment (총괄 8e54a261b ④ · bf9d3367a), so all of them say one sentence.
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
    from database import models

    if source_name in PROTECTED_SOURCES:
        raise ReplayRefused(
            f"refusing to withdraw source '{source_name}': it is the layer that means "
            f"'a human typed this'. Withdrawing it would remove a human's value, which "
            f"this tool does not do. Edit the cell instead.")
    target = resolve_target(table_name, columns)

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
    claims = {}
    for row_id, col in q.all():
        claims.setdefault((row_id, col), []).append(source_name)
    stats = {"mode": "apply" if apply else "dry-run", "table": table_name, "source": source_name}
    stats.update(_withdraw_cells(db, table_name, target, claims, apply=apply, chunk_size=chunk_size,
                                 log=log, checkpoint=checkpoint, label=f"'{source_name}' claims"))
    return stats


def _withdraw_cells(db, table_name: str, target, claims: dict, apply: bool = False,
                    chunk_size: int = DEFAULT_CHUNK_SIZE, log=logger.info, checkpoint=None,
                    label: str = "") -> dict:
    """R2's one pass over `claims` {(row_id, column): [source_name, ...]}.

    A cell claimed by several sources withdraws them in that order, each seeing what the one
    before it left on apply - what one `withdraw_source` call per source did, in one pass."""
    from sqlalchemy import tuple_
    from database import crud, models

    model, col_types = target
    stats = {"mode": "apply" if apply else "dry-run", "table": table_name,
             "cells_matched": sum(len(names) for names in claims.values()), "cells_withdrawn": 0,
             "revealed": 0, "emptied": 0, "pinned_skipped": 0,
             "value_unchanged": 0, "samples": []}
    if not claims:
        return stats

    by_row = {}
    for row_id, col in claims:
        by_row.setdefault(row_id, set()).add(col)
    log(f"[withdraw] {label} {stats['cells_matched']} cell(s) across {len(by_row)} row(s) "
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
    # PARAMETER (`_claimed_filter`, and the (source_name, row_id) pairs the claims
    # carry into the delete below), never from `request_source`. So do the two
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
    # 🔴 [총괄 eddf9e38e] COLLAPSED, CHOSEN HERE: a withdrawal is the fourth path that carries
    #    volume - in per-row mode each revealed row was one event, and a 1,000-row delete fed
    #    1,000 of them to the chain and the ledger follow-up (ca0d23b08: drain 1,003).
    import event_constants
    from database.context import outbox_mode
    with crud.transaction_context(R2_AUDIT_SOURCE, tx_id, R1_SOURCE_NAME), \
            outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
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
            carried = {}
            for row_id in chunk:
                row = rows.get(row_id)
                if row is None:
                    continue
                for col, source_name in ((c, s) for c in sorted(by_row.get(row_id, ()))
                                         for s in claims[(row_id, c)]):
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
                                             carried.get(cell, remaining.get(cell)), pins.get(cell),
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
                        carried[cell] = survivors  # the next source on this cell sees this one gone
                        delete_keys.append((source_name, row_id, col))
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
                for s, r, c in delete_keys:
                    by_col.setdefault(c, []).append((s, r))
                for col, pairs in by_col.items():
                    for j in range(0, len(pairs), chunk_size):
                        db.query(models.CellSource).filter(
                            models.CellSource.table_name == table_name,
                            models.CellSource.column_name == col,
                            tuple_(models.CellSource.source_name, models.CellSource.row_id)
                            .in_(pairs[j:j + chunk_size]),
                        ).delete(synchronize_session=False)
                db.commit()

    if not apply:
        db.rollback()
    log(f"[withdraw] {stats['mode']}: {stats['cells_withdrawn']} cell(s) withdrawn "
        f"({stats['revealed']} revealed another source, {stats['emptied']} left empty, "
        f"{stats['pinned_skipped']} skipped as human-pinned)")
    return stats


#: Waiting events one page of the withdrawal fold reads, and commits, at once (총괄 eddf9e38e).
FOLD_PAGE_EVENTS = 10000


def fold_withdrawal_events(db, apply: bool = False, page: int = FOLD_PAGE_EVENTS, checkpoint=None,
                           log=logger.info) -> dict:
    """The per-row events withdrawals staged before they wrote collapsed (총괄 eddf9e38e ②), folded per
    table into collapsed ones - `stage_collapsed_event`, 1,000 rows each - and deleted in the SAME
    commit. Chosen by the withdrawal's mark alone (who `R2_AUDIT_SOURCE`, source `R1_SOURCE_NAME`) and
    the one state seat (`event_constants.chain_state_of`): waiting folds; a line the chain runs now
    (`runtime.running.chain_lines_running`) and a RETRYING event are left - counted apart.
    ⚠️ The purge doors never delete a waiting event; this one does because its replacement lands in
    the same transaction - its rows, and its envelope but the transaction: depth, channel, cascade,
    written_by and run are set per group (a run's own `run_id` would move them onto its line), the
    transaction is new per group in the withdrawal's shape. Locked like `set_aside._mark` (5250ca1bd).
    -> `{"by_table": {table: [events, collapsed events]}, "rows", "retrying", "running", "pages",
    "stopped"}` - the dry run counts what apply does, page by page."""
    import event_constants
    from contextlib import ExitStack
    from sqlalchemy import delete
    from database import crud
    from database.context import cascade, channel, request_chain_depth, retroactive_run, written_by
    from database.database import stage_collapsed_event
    from database.models import DatabaseOutbox as outbox
    from runtime import running

    chunk = event_constants.OUTBOX_COLLAPSE_CHUNK_ROWS
    p = outbox.payload
    read = (db.query(outbox.id, outbox.table_name, outbox.event_type, outbox.status,
                     event_constants.queue_line_key(outbox), p["row_id"].as_string(), p["row_ids"],
                     p[event_constants.CHAIN_DEPTH_KEY].as_integer(), p[event_constants.CHANNEL_KEY].as_string(),
                     p[event_constants.CASCADE_KEY].as_boolean(), p[event_constants.WRITTEN_BY_KEY],
                     p[event_constants.RUN_KEY].as_string())
            .filter(outbox.processed_chain == False,  # noqa: E712 - 부분 인덱스의 술어 철자
                    p["updated_by"].as_string() == R2_AUDIT_SOURCE,
                    p["source_name"].as_string() == R1_SOURCE_NAME))
    out = {"by_table": {}, "rows": 0, "retrying": 0, "running": 0, "pages": 0, "stopped": False}
    after, folded = 0, 0
    while True:
        if checkpoint is not None and checkpoint(folded):
            out["stopped"] = True
            log(f"[withdraw fold] stopped by request after {folded} event(s)")
            break
        found = read.filter(outbox.id > after).order_by(outbox.id).limit(page).all()
        if not found:
            break
        after, out["pages"] = found[-1][0], out["pages"] + 1
        chosen, lines = {}, running.chain_lines_running()
        for event_id, table, kind, status, line, row_id, row_ids, depth, chan, casc, wrote, run in found:
            if event_constants.is_collapsed_payload({"row_ids": row_ids}) or not row_id:
                continue
            state = event_constants.chain_state_of(False, status, running=lines.get(line))["state"]
            if state == event_constants.CHAIN_STATE_RETRYING:
                out["retrying"] += 1
            elif state != event_constants.CHAIN_STATE_WAITING:
                out["running"] += 1
            else:
                chosen[event_id] = (table, kind, row_id,
                                    (depth, chan, bool(casc), tuple(sorted(wrote or ())), run))
        if apply and chosen:
            # 🔴 IN ID ORDER, ONLY WHAT STILL WAITS - a row a group ends meanwhile is waited for, then
            #    no longer waiting: it keeps that ending and stays out of the fold.
            ids, held = sorted(chosen), []
            for start in range(0, len(ids), chunk):
                held += [i for (i,) in db.query(outbox.id).filter(
                    outbox.id.in_(ids[start:start + chunk]), outbox.processed_chain == False)  # noqa: E712
                    .order_by(outbox.id).with_for_update()]
            chosen = {i: chosen[i] for i in held}
        groups = {}
        for table, kind, row_id, envelope in chosen.values():
            groups.setdefault((table, kind, envelope), {})[row_id] = None
            out["by_table"].setdefault(table, [0, 0])[0] += 1
        for (table, kind, (depth, chan, casc, wrote, run)), rows in groups.items():
            out["by_table"][table][1] += -(-len(rows) // chunk)
            out["rows"] += len(rows)
            if apply:
                with ExitStack() as stack:
                    stack.enter_context(crud.transaction_context(
                        R2_AUDIT_SOURCE, f"{R2_AUDIT_SOURCE}_{uuid.uuid4().hex[:8]}", R1_SOURCE_NAME))
                    for door in (channel(chan), cascade(casc), written_by(wrote), retroactive_run(run)):
                        stack.enter_context(door)
                    stack.callback(request_chain_depth.reset, request_chain_depth.set(depth))
                    stage_collapsed_event(db, kind, table, list(rows))
        if apply and chosen:
            ids = sorted(chosen)
            for start in range(0, len(ids), chunk):
                db.execute(delete(outbox).where(outbox.id.in_(ids[start:start + chunk]))
                           .execution_options(synchronize_session=False))
            db.commit()
        folded += len(chosen)
    log("[withdraw fold] %s: %s" % ("apply" if apply else "dry-run", fold_said(out)))
    return out


def fold_said(s) -> str:
    """`fold_withdrawal_events`' answer in one sentence - its log line, the preview and the CLI."""
    return (("; ".join("'%s' %d event(s) -> %d" % (t, b, a) for t, (b, a) in sorted(s["by_table"].items()))
             or "No waiting withdrawal event goes row by row")
            + " - %d row(s). Left as they are: %d event(s) the chain already tried (RETRYING), %d on a line "
              "the chain runs now." % (s["rows"], s["retrying"], s["running"])
            + (" STOPPED by request - run it again for the rest." if s.get("stopped") else ""))
