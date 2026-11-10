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
from ledger.setup_bundle import entry_key_columns  # noqa: F401 - one row-key rule

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

def claimed_lines(db, table_name: str):
    """(t__lines Core Table, column -> bit) the claim filter is built over - read, no slots (lines.built_lines)."""
    from database import lines

    return lines.built_lines(db, table_name)


def _claimed_filter(lt, bits: dict, source_name: str, columns: list = None, written_by=None, batch=None):
    """The predicate for "lines `source_name` claims on a table" over its t__lines `lt` (`claimed_lines`): its head
    lines naming one of `columns` (every column when None). A head line that withdrew the column still matches - the
    reader drops it by its withdrawn bit, as `lines.layers` does.

    Extracted so `count_withdrawable` and `withdraw_source` cannot answer different questions: a count that used a
    slightly different filter from the operation it previews is a count that lies, and it would lie silently.

    A name whose bracketed layers rank as it (`crud.layer_ranks_as` - the chain's layer per source row, 총괄
    8ec008914) claims those layers too. `batch`: one write's lines only (B's R2 batch, after 11-14).
    """
    from sqlalchemy import or_

    from database import crud, lines

    named = lt.c.source_name == source_name
    tag = "\x00"
    copy = crud.merged_layer_name(source_name, tag)
    if crud.layer_ranks_as(copy) == source_name:
        named = or_(named, lt.c.source_name.startswith(copy.split(tag)[0], autoescape=True))
    masks = {}
    for col, bit in bits.items():
        if not columns or col in columns:
            chunk = bit // lines.BITS_PER_CHUNK
            masks[chunk] = masks.get(chunk, 0) | lines._mask(bit)
    conds = [named, or_(*[lt.c[f"head_{c}"].op("&")(m) != 0 for c, m in sorted(masks.items())])]
    if written_by:      # one rule's layers - the declaration that wrote them (`replay.unwritten_scope`)
        conds.append(lt.c.written_by.in_(list(written_by)))
    if batch is not None:
        conds.append(lt.c.batch == batch)
    return conds


def _claimed_cells(row, bits: dict, columns=None) -> list:
    """The columns a claimed line still says (head, not withdrawn) - of `columns` when given."""
    from database import lines

    by_bit = {bit: col for col, bit in bits.items() if not columns or col in columns}
    chunks = 1 + max((b // lines.BITS_PER_CHUNK for b in bits.values()), default=0)
    heads = [row[f"head_{c}"] for c in range(chunks)]
    gone = [row[f"withdrawn_{c}"] for c in range(chunks)]
    return sorted(lines._columns_of(heads, by_bit) - lines._columns_of(gone, by_bit))


def _load_cell_state(db, table_name: str, chunk_row_ids: list, columns=None):
    """Stored sources + human pins for a chunk of rows: TWO batched queries, not two per cell.

    Extracted so R2 (`withdraw_source`) and R3 (`recompute_display_values`) cannot
    assemble the resolver's input differently. Two functions that build the input to
    one decision in two ways are two decisions, and the difference would only show up
    on the cells where it matters.

    `ingested_at` travels with every layer because `crud.compute_priority_value` reads
    it to break a tie between equally-ranked sources - see its docstring. Dropping it
    here would silently put the resolution back on dict order. `columns` keeps both reads to those
    columns (None = every column).
    """
    from database import lines

    sources = {cell: dict(sorted(named.items()))
               for cell, named in lines.layers(db, table_name, chunk_row_ids, columns).items()}

    return sources, pins_of(db, table_name, chunk_row_ids, columns)


def pins_of(db, table_name: str, row_ids, columns=None) -> dict:
    """{(row_id, column): the source a person pinned there, or None} of these rows - one read of `cell_overwrites`."""
    from database import models

    co = models.CellOverwrite
    in_columns = [co.column_name.in_(list(columns))] if columns else []
    return {(row_id, col): pin for row_id, col, pin in (
        db.query(co.row_id, co.column_name, co.manual_priority_source)
        .filter(co.table_name == table_name, co.row_id.in_(list(row_ids)), *in_columns).all())}

#: Who deleted a shell row - the history line's name, the chain's write seat and the sweep alike (5eee501eb).
SHELL_DELETER = "chain_shell_rows"
#: Who deleted a row whose key no source row holds any more - a decide's recount (총괄 옛 키).
GONE_DELETER = "chain_no_source_rows"


def rule_layer_names() -> tuple:
    """The layer names a rule writes under its declaration (`updated_by` = `rule_shape.declaration_of`, what
    `rule_run.signed` stamps): the chain's, and a decide's auto-confirm stamps. «This rule's layer» to
    `cells_written_by` and `person_rows` alike (총괄 10-28)."""
    from chain.enrichment import candidates
    from database import crud

    return crud.CHAIN_SOURCE, candidates.SOURCE_NAME, candidates.SOURCE_NAME_PARTIAL_KEY


def person_cells(db, table_name: str, row_ids) -> dict:
    """{(row_id, column): {source_name: {"value", "ingested_at", "updated_by"}}} - every layer of each cell a person
    wrote a layer on, blank or not (`crud.layer_writer`). THE ONE «did a person write here» judgement: a gone row
    (`person_rows`) and an AI rule's memory of a person's correction (`chain.ask_rule`, lead 10-28) both read it."""
    from database import crud, lines

    return {cell: named for cell, named in lines.layers(db, table_name, row_ids).items()
            if any(crud.layer_writer(name) == crud.USER_SOURCE for name in named)}


def person_rows(db, table_name: str, row_ids, own=None) -> dict:
    """{row_id: [what keeps it]} - the rows a part other than the chain taking them back keeps. THE ONE «is a part
    left that keeps this row» (`shells`, `ingestion_worker._settle`; owner 11-10 «체인이 낸 행 부분만 없애면 됨»):
      a person's part     a layer they wrote, blank or not (`person_cells`), or a pin (`manual_priority_source`)
      a writer not the chain - a file's key layer, or a value it wrote
      a chain that made the row - a value under a layer name that also holds a key column of the row
    A chain that only attached values to a row another made (no key-column layer of its own there) keeps nothing
    (lead 11-10, the owner's official master): the row goes and that chain hears the DELETE. `own` {row_id: rules}:
    the rules taking the row back - their layers (and the backfill's old name for them) keep nothing either."""
    from chain.enrichment import backfill
    from database import crud, models

    from database import lines

    co = models.CellOverwrite
    ids = list(dict.fromkeys(str(r) for r in row_ids or () if r))
    found = {row_id: {crud.USER_SOURCE} for row_id, _column in person_cells(db, table_name, ids)}
    keys, mine, own = key_columns(table_name), rule_layer_names(), own or {}
    for i in range(0, len(ids), DEFAULT_CHUNK_SIZE):
        chunk = ids[i:i + DEFAULT_CHUNK_SIZE]
        for (row_id,) in db.query(co.row_id).filter(co.table_name == table_name, co.row_id.in_(chunk),
                                                     co.manual_priority_source.isnot(None)):
            found.setdefault(row_id, set()).add(crud.USER_SOURCE)
        layers = {}
        for row_id, column, name, value, by in [(r, c, n, e["value"], e["updated_by"])
                                                for (r, c), named in lines.layers(db, table_name, chunk).items()
                                                for n, e in named.items()]:
            writer = crud.layer_writer(name)
            # by the writer the name folds to - a merge renames a layer «chain_ingestion (<key>)» (총괄 10-14 4)
            if writer == backfill.SOURCE_NAME or (writer in mine and by in own.get(row_id, ())):
                continue
            layers.setdefault(row_id, []).append((column, name, value))
        for row_id, named in layers.items():
            made = {name for column, name, _value in named if column in keys}
            for column, name, value in named:
                chain = crud.layer_ranks_as(name) == crud.CHAIN_SOURCE
                if (not chain and (column in keys or not crud.is_blank_value(value))) or (
                        chain and column not in keys and name in made and not crud.is_blank_value(value)):
                    found.setdefault(row_id, set()).add(name)
    return {row_id: sorted(names) for row_id, names in found.items()}


def key_columns(table_name: str) -> set:
    """The columns a row of this table is known by - its `composite_key_source`, else its `business_key`
    (what `crud.unfilled_key_columns` reads too)."""
    from database import crud

    return set(entry_key_columns(crud.TABLE_CONFIG.get(table_name) or {}))




def shells(db, table_name: str, row_ids) -> list:
    """is_shell, for each of these rows (총괄 5eee501eb · 판정 ㄱ, 소유자 10-09 「키값만 남아 있네」): nothing keeps it
    (`person_rows` - a person's part, a writer not the chain, a chain that made it; a chain that only attached values
    keeps nothing, lead 11-10), and it shows nothing outside its keys that no layer carries - a value no layer carries
    is not taken for nothing. The chain's write seat and the sweep ask this one."""
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
        kept = person_rows(db, table_name, chunk)
        for row in db.query(model).filter(model.row_id.in_(chunk)).all():
            layered = {column for column, _name, _value in by_row.get(row.row_id, ())}
            # a shown value no layer carries is not taken for nothing; one a layer carries, person_rows judged
            if row.row_id in kept or any(not crud.is_blank_value(getattr(row, column, None))
                                         for column in shown if column not in layered):
                continue
            found.append(row.row_id)
    return found


def delete_shells(db, table_name: str, gone) -> list:
    """The rows `gone` (`shells`' answer), deleted by the grid's door - their layers and a history line go with them,
    one DELETE on the chain's channel, so a rule that takes chain events hears it (lead 11-10) - and said once. Every seat that takes layers back asks `shells` and hands its answer
    here; a chain write asks after its recount (총괄 69b8b029c, 소유자 10-21 「체인 껍데기는 여전함」). -> `gone`."""
    from database import crud

    for i in range(0, len(gone), DEFAULT_CHUNK_SIZE):
        crud.delete_rows_batch(db, table_name, gone[i:i + DEFAULT_CHUNK_SIZE], SHELL_DELETER)
    if gone:
        logger.info("[ChainShell] table=%s rows_deleted=%d - nothing but the chain's keys and values another chain attached was left", table_name, len(gone))
    return gone


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
    new_val, top_src = crud.compute_priority_value(survivors, pin, table_name, cell=(table_name, col, row))
    if new_val is not None:
        new_val = crud.cast_value_by_type(new_val, col_types.get(col, "string"), col)
    return {
        "survivors": survivors,
        "old_value": old_val,
        "new_value": new_val,
        "top_source": top_src,
        "changed": crud.values_differ(old_val, new_val, col_types.get(col, "string")),
    }

def unowned_layers(db, after_id, size: int = DEFAULT_CHUNK_SIZE) -> tuple:
    """One page of `cell_sources` by id after `after_id`: `([(table, written by)] of the chain's layers no rule owns -
    written before ownership (owner 11-06 step 2), the last id read, the rows read)`. The census of «Not adopted».
    READ ONLY."""
    from database import crud, models

    S = models.CellSource
    rows = (db.query(S.id, S.table_name, S.source_name, S.updated_by).filter(S.id > after_id)
            .order_by(S.id).limit(size).all())
    bases = crud._ownable_bases()
    found = [(table, by) for _id, table, name, by in rows
             if crud.layer_writer(name) in bases and crud.layer_owner(name) is None]
    return found, (rows[-1][0] if rows else after_id), len(rows)


def cells_stamped_by(db, table_name, origin_row_ids) -> list:
    """`[(table_name, row_id, column_name, source_name, origin_row_id)]` - the layers these rows fed.

    🔴 [S-280 · 판정 434] THE NOTE READ BACK. The line carries its source row (`input_row`), written while the input
    row was still there, so this answers 「그 행이 먹인 칸이 어디인가」 after the row is gone — the one question a
    deleted row cannot be asked itself. `table_name` None: every declared table whose lines are built (a caller
    that does not know which tables the rows fed). READ ONLY, one layer a tuple.
    """
    from database import crud, lines

    tables = [table_name] if table_name else [t for t, cfg in (crud.TABLE_CONFIG or {}).items()
                                               if isinstance(cfg, dict) and lines.keeps_lines(t, cfg)]
    return [(t, *cell) for t in tables for cell in lines.stamped_by(db, t, origin_row_ids)]


def cells_written_by(db, table_name: str, cells, declarations, chunk_size: int = DEFAULT_CHUNK_SIZE,
                     rows=()) -> list:
    """`[(table_name, row_id, column_name, source_name, origin_row_id)]` - what `declarations` own (owner 11-06 step
    2) on these cells `(row_id, column)` and on every cell of `rows`: a layer the rule wrote (`updated_by` is the rule,
    `rule_run.signed`) under a rule's name (`rule_layer_names`, bracketed or not - its owned layer
    `crud.owned_layer_name`, a source row's layer, a merge's copy), and an `enrichment_backfill` layer - the
    backfill's old name for that write (총괄 가 옛 백필 ㄱ). Not a rule's that wrote the cell after it. What settle
    takes back when its answer leaves it out. READ ONLY, the shape `cells_stamped_by` answers."""
    from chain.enrichment import backfill
    from database import crud, lines

    names = rule_layer_names() + (backfill.SOURCE_NAME,)
    declared = set(declarations or ())

    def theirs(source, entry):
        return crud.layer_writer(source) in names and (entry["updated_by"] in declared
                                                       or source == backfill.SOURCE_NAME)

    found = []
    whole = list(dict.fromkeys(str(r) for r in rows or () if r))
    for (row_id, column), named in lines.layers(db, table_name, whole).items():
        found.extend((table_name, row_id, column, source, entry["origin_row_id"])
                     for source, entry in named.items() if theirs(source, entry))
    whole = set(whole)
    wanted = {cell for cell in dict.fromkeys(cells or ()) if cell[0] not in whole}
    if wanted:
        read = lines.layers(db, table_name, sorted({r for r, _c in wanted}), {c for _r, c in wanted})
        for (row_id, column), named in read.items():
            if (row_id, column) in wanted:
                found.extend((table_name, row_id, column, source, entry["origin_row_id"])
                             for source, entry in named.items() if theirs(source, entry))
    return found


def withdraw_by_origin(db, origin_row_ids, apply: bool = False, log=logger.info,
                       table: str = None, columns=None, keep=()) -> dict:
    """Withdraw every cell stamped as having been read FROM one of these rows (`withdraw_layers` over
    `cells_stamped_by`).

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
    return withdraw_layers(db, cells_stamped_by(db, table, origin_row_ids), apply, log, table, columns, keep)


def withdraw_layers(db, layers, apply: bool = False, log=logger.info, table: str = None, columns=None,
                    keep=()) -> dict:
    """Withdraw these layers `[(table_name, row_id, column, source_name, origin_row_id)]` - what `cells_stamped_by`
    or `cells_written_by` found - narrowed by `table` · `columns` · `keep` (`withdraw_by_origin`)."""
    stats = {"mode": "apply" if apply else "dry-run", "groups": 0, "cells_withdrawn": 0,
             "protected_skipped": 0, "lost_a_layer": {}}
    keep = set(keep or ())
    claims_by_table, groups, protected = {}, set(), set()
    for table_name, row_id, column, source_name, origin in layers:
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
                              _pages_of({cell: sorted(names) for cell, names in claims.items()}),
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
                    checkpoint=None, written_by=None) -> dict:
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
    if source_name in PROTECTED_SOURCES:
        raise ReplayRefused(
            f"refusing to withdraw source '{source_name}': it is the layer that means "
            f"'a human typed this'. Withdrawing it would remove a human's value, which "
            f"this tool does not do. Edit the cell instead.")
    target = resolve_target(table_name, columns)

    # 1) Cells this source claims, a page of the table's own rows at a time (`read`): the next rows by the table's
    #    key (`keyset_scan.iter_pages`), their claims asked by id. Keyed on cell_sources the read took the row_id
    #    index through other tables' layers - one statement 10.4 s after another table's 13M layers were deleted,
    #    no progress line and no stop meanwhile (box, 1M). The price, kept by the owner's 5-second rule: where the
    #    source claims few rows the whole run pages the whole table, 3.0-4.4x longer and 6.3x at most (1M rows, 9M
    #    layers, one row in 1,000 claimed - QA's turns, 총괄 ff4eb2cf0) - 총괄 5ad030347 · 10-13.
    from sqlalchemy import select

    lt, bits = claimed_lines(db, table_name)
    q = select(lt).where(*_claimed_filter(lt, bits, source_name, columns, written_by))
    asked = [chunk_size]

    class _Asked:
        """The size `_withdraw_cells` asked for the page being read."""
        def next(self):
            return asked[0]
    pages = keyset_scan.iter_pages(db, target[0], columns=[], chunk_size=chunk_size, size=_Asked(),
                                   condition=target[0].row_id.in_(list(row_ids)) if row_ids else None)

    def read(size):
        """(the page's rows this source claims, their claims), None past the last row."""
        asked[0] = size
        page = next(pages, None)
        if page is None:
            return None
        ids = [row_id for (row_id,) in page]
        claims = {}
        for line in db.execute(q.where(lt.c.row_id.in_(ids))).mappings():
            for col in _claimed_cells(line, bits, columns):
                claims.setdefault((line["row_id"], col), []).append(line["source_name"])
        claimed = {row_id for row_id, _col in claims}
        return [row_id for row_id in ids if row_id in claimed], {cell: sorted(names) for cell, names in claims.items()}

    stats = {"mode": "apply" if apply else "dry-run", "table": table_name, "source": source_name}
    gone = []

    def its_shells(row_ids):
        # a row this withdrawal left a shell goes, as any withdrawal's does (총괄 69b8b029c) - in the page's own
        # commit: after every page it was a commit of its own, and a death between left the shells (총괄 g33 · g85)
        db.flush()
        gone.extend(delete_shells(db, table_name, shells(db, table_name, sorted(row_ids))))
    stats.update(_withdraw_cells(db, table_name, target, read, apply=apply, chunk_size=chunk_size,
                                 log=log, checkpoint=checkpoint, label=f"'{source_name}' claims",
                                 page_done=its_shells))
    stats["rows_deleted"] = len(gone)
    if apply:
        db.commit()
    return stats


def _pages_of(claims: dict):
    """`read(size)` for `_withdraw_cells` over claims already in hand, their rows in the dict's order."""
    by_row = {}
    for cell, names in claims.items():
        by_row.setdefault(cell[0], {})[cell] = names
    rows, at = list(by_row), [0]

    def read(size):
        chunk = rows[at[0]:at[0] + size]
        at[0] += len(chunk)
        return (chunk, {cell: names for row_id in chunk for cell, names in by_row[row_id].items()}) if chunk else None
    return read


def _withdraw_cells(db, table_name: str, target, read, apply: bool = False,
                    chunk_size: int = DEFAULT_CHUNK_SIZE, log=logger.info, checkpoint=None,
                    label: str = "", page_done=None) -> dict:
    """R2's one pass over the claims `read(size)` hands a page at a time - `(row ids,
    {(row_id, column): [source_name, ...]})` of at most `size` rows, none in it on a page that holds none, None at
    the end. `page_done(row ids)`, applied: what else that page's step writes, before it ends.

    A page is ONE `write_lines` call (cell-source overhaul, lead 11-11): a withdraw line a (row, source) naming the
    columns that source takes back - the merge then shows what the lines left, the audit row and the collapsed event
    are write_lines'. A cell a person pinned to that source is skipped and counted. A dry run writes the same page
    and rolls it back - the preview is the write's own answer, not a second resolver."""
    from database import crud
    from database.write_lines import write_lines

    stats = {"mode": "apply" if apply else "dry-run", "table": table_name,
             "cells_matched": 0, "cells_withdrawn": 0,
             "revealed": 0, "emptied": 0, "pinned_skipped": 0,
             "value_unchanged": 0, "samples": []}
    log(f"[withdraw] {label} in '{table_name}' - counting as it goes")

    tx_id = f"{R2_AUDIT_SOURCE}_{uuid.uuid4().hex[:8]}"
    # 🔴 THE OUTBOX LABEL (`recompute_display_values` says why it is separable from the layer) and COLLAPSED: a
    #    1,000-row delete fed 1,000 per-row events to the chain and the ledger follow-up (총괄 eddf9e38e).
    import event_constants
    from database.context import outbox_mode
    with crud.transaction_context(R2_AUDIT_SOURCE, tx_id, R1_SOURCE_NAME), \
            outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        # a run that reports its pages sizes them (`PageSize`); the chain's own withdrawal (`withdraw_by_origin`, no
        # checkpoint) keeps the fixed size - one write, one event (총괄 a02ad0f2b NO-GO ①)
        size, i = (keyset_scan.PageSize(chunk_size) if checkpoint is not None else None), 0
        step, pages = keyset_scan.step_of(checkpoint), 0
        while True:
            if checkpoint is not None and checkpoint(i):
                stats["stopped"] = True
                log(f"[withdraw] stopped by request after {i} rows")
                break
            got = read(size.next() if size else chunk_size)
            if got is None:
                break
            chunk, claims = got
            pages += 1
            step("read", pages, None, len(chunk))
            if not chunk:
                continue
            i += len(chunk)
            stats["cells_matched"] += sum(len(names) for names in claims.values())
            pins = pins_of(db, table_name, chunk)
            taken = {}                                  # (row_id, source) -> its columns, in claim order
            for (row_id, col), names in sorted(claims.items()):
                for source_name in names:
                    if pins.get((row_id, col)) == source_name:
                        stats["pinned_skipped"] += 1
                        if len(stats["samples"]) < SAMPLE_LIMIT:
                            stats["samples"].append({
                                "row_id": row_id, "column": col, "action": "skipped",
                                "why": f"a human pinned '{source_name}' on this cell "
                                       f"(manual_priority_source); withdrawing it would "
                                       f"override that choice"})
                        continue
                    taken.setdefault((row_id, source_name), []).append(col)
            items = [{"row_id": row_id, "line_kind": "withdraw", "columns": cols, "source_name": source_name,
                      "written_by": R2_AUDIT_SOURCE} for (row_id, source_name), cols in taken.items()]
            answer = write_lines(db, table_name, items, kind="withdraw", transaction_id=tx_id) if items else None
            for it, said in zip(items, (answer or {}).get("items") or ()):
                if said["work"] != "withdraw":          # the source spoke in none of these columns any more
                    continue
                change = answer["changed"].get(said["row_id"]) or {}
                was, now = change.get("old") or {}, change.get("new") or {}
                for col in said["columns"]:
                    stats["cells_withdrawn"] += 1
                    stats["revealed" if not crud.is_blank_value(now.get(col)) else "emptied"] += 1
                    moved = was.get(col) != now.get(col)
                    stats["value_unchanged"] += not moved
                    if len(stats["samples"]) < SAMPLE_LIMIT:
                        stats["samples"].append({"row_id": said["row_id"], "column": col, "action": "withdraw",
                                                 "old_value": was.get(col), "new_value": now.get(col),
                                                 "top_source": None, "source": it["source_name"]})
            if not apply:
                db.rollback()                           # the preview's page, unwritten - its locks let go
                continue
            if page_done is not None:
                page_done(chunk)
            from session_contract import end_step
            end_step(db)

    if not apply:
        db.rollback()
    log(f"[withdraw] {stats['mode']}: {label} {stats['cells_matched']} cell(s) across {i} row(s) in "
        f"'{table_name}' - {stats['cells_withdrawn']} cell(s) withdrawn "
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
    from sqlalchemy import and_, case, delete, null
    from database import crud
    from database.context import cascade, channel, request_chain_depth, retroactive_run, written_by
    from database.database import stage_collapsed_event
    from database.models import DatabaseOutbox as outbox
    from runtime import running

    chunk = event_constants.OUTBOX_COLLAPSE_CHUNK_ROWS
    p = outbox.payload
    # a page is the queue's next waiting events by id (the partial index) and the mark is judged on them - in the
    # WHERE it read on to the next marked event, the whole waiting queue before the first page (총괄 5ad030347)
    # the payload's lists ride only on events that carry the withdrawal's mark - every other waiting event's
    # row_ids came along and were dropped (총괄 59c0bfb8c 7)
    marked = and_(p["updated_by"].as_string() == R2_AUDIT_SOURCE, p["source_name"].as_string() == R1_SOURCE_NAME)
    read = (db.query(outbox.id, outbox.table_name, outbox.event_type, outbox.status,
                     event_constants.queue_line_key(outbox), p["row_id"].as_string(),
                     case((marked, p["row_ids"]), else_=null()),
                     p[event_constants.CHAIN_DEPTH_KEY].as_integer(), p[event_constants.CHANNEL_KEY].as_string(),
                     p[event_constants.CASCADE_KEY].as_boolean(), case((marked, p[event_constants.WRITTEN_BY_KEY]), else_=null()),
                     p[event_constants.RUN_KEY].as_string(), p["updated_by"].as_string(), p["source_name"].as_string(),
                     case((marked, p[event_constants.OLD_VALUES_KEY]), else_=null()))
            .filter(outbox.processed_chain == False))  # noqa: E712 - 부분 인덱스의 술어 철자
    out = {"by_table": {}, "rows": 0, "retrying": 0, "running": 0, "pages": 0, "stopped": False}
    after, folded, size, step = 0, 0, keyset_scan.PageSize(page), keyset_scan.step_of(checkpoint)
    while True:
        if checkpoint is not None and checkpoint(folded):
            out["stopped"] = True
            log(f"[withdraw fold] stopped by request after {folded} event(s)")
            break
        found = read.filter(outbox.id > after).order_by(outbox.id).limit(size.next()).all()
        if not found:
            break
        after, out["pages"] = found[-1][0], out["pages"] + 1
        step("read", out["pages"], None, len(found))
        chosen, lines = {}, running.chain_lines_running()
        for event_id, table, kind, status, line, row_id, row_ids, depth, chan, casc, wrote, run, who, source, old in found:
            if (who, source) != (R2_AUDIT_SOURCE, R1_SOURCE_NAME) or event_constants.is_collapsed_payload(
                    {"row_ids": row_ids}) or not row_id:
                continue
            state = event_constants.chain_state_of(False, status, running=lines.get(line))["state"]
            if state == event_constants.CHAIN_STATE_RETRYING:
                out["retrying"] += 1
            elif state != event_constants.CHAIN_STATE_WAITING:
                out["running"] += 1
            else:
                chosen[event_id] = (table, kind, row_id,
                                    (depth, chan, bool(casc), tuple(sorted(wrote or ())), run), old)
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
        for table, kind, row_id, envelope, old in chosen.values():
            # a row's old values are its first event's - what it was before the withdrawals (총괄 10-14 3)
            groups.setdefault((table, kind, envelope), {}).setdefault(row_id, old if isinstance(old, dict) else {})
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
                    stage_collapsed_event(db, kind, table, list(rows), old=list(rows.values()))
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
