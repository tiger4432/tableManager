"""The grid read path - the narrowed query a grid page, its count, the export and a chain reader share - importable
without main (총괄 10-22: a chain slot does not import main). Moved here from main.py whole; main re-exports every name,
so a caller of main.<name> reads the same function."""
import logging

from fastapi import HTTPException

import grid_pivot
from column_filter import (ROW_ID_FILTER_NAMES, SET, TEXT_PATTERNS, FilterRefused, filter_column,
                           get_column_filter_condition, model_has_row_id)
from database import crud, models

logger = logging.getLogger("Server")


#: 캐시 키의 구분자. 🔴 이 파일 어디에도 두 번째 사본을 만들지 말 것 - 이 상수와
#: 무효화 쪽 판정이 갈라진 것이 바로 아래 주석의 사고다.
COUNT_CACHE_KEY_SEP = "|"


def build_count_cache_key(table_name: str, *parts) -> str:
    """Count 캐시 키의 유일한 철자.

    🔴 구분자는 여기에만 있다. `invalidate_table_cache`는 이 함수가 만든 키를
    같은 구분자로 되갈라 테이블을 읽는다. 두 철자가 갈라져 있던 동안(무효화 쪽은
    `"_"`, 쓰기 쪽은 `"|"`) **여덟 개 호출 지점 전부가 키를 0개 지웠고**, 그래서
    ① 무효화된 줄 알았던 stale count가 그대로 살아남았고 ② 이 dict이 검색어마다
    한 칸씩 영원히 자랐다. 키 생성과 키 해석을 한 모듈 안에 붙여 둔 이유다.
    """
    return COUNT_CACHE_KEY_SEP.join([table_name, *parts])


def count_cache_table_of(cache_key: str) -> str:
    """캐시 키가 가리키는 테이블명. `build_count_cache_key`의 역연산."""
    return cache_key.split(COUNT_CACHE_KEY_SEP, 1)[0]


def has_row_id(table_name) -> bool:
    """`setup_bundle.reads_a_row_table` over the entry THIS process built the model from
    (`crud.TABLE_CONFIG`), adapted the way the ledger adapts it (총괄 377231278 · 218f907f5).
    ⚠️ Not a re-read of the file: between an edit and the reload the file and the models
    differ, and one bad entry in the file would fail every table's question."""
    from ledger.setup_bundle import _adapt_physical_catalog, reads_a_row_table

    entry = crud.TABLE_CONFIG.get(table_name)
    return reads_a_row_table(_adapt_physical_catalog({table_name: entry}), table_name)


def refuse_row_address(table_name):
    """🔴 THE ONE PLACE a route that addresses a row BY `row_id` refuses a relation without
    one - a view (`ledger_events` on the grid) - by name, instead of the 500 its model's
    missing `row_id` raised."""
    if not has_row_id(table_name):
        raise HTTPException(status_code=422, detail=(
            "'%s' is not a table that has row_id, so a row of it cannot be addressed by "
            "row_id" % table_name))


def total_order_keys(table_model, table_name):
    """The columns that give this relation a TOTAL order — `row_id`, else the catalogue's
    `business_key`, else its `composite_key_source` (S-186 · S-229).

    🔴 PLURAL, BECAUSE FOUR OF THE SHIPPED VIEWS ARE KEYED BY A PAIR OR MORE. Measured in
    `table_config.json.sample`: of eleven `kind: view` relations, FOUR declare neither
    `row_id` nor `business_key` and DO declare `composite_key_source` — `bonding_core_lot`
    (base_id, core_wafer), `bonding_core_die`, `lot_slot_move`, `bonding_die_from_core`.
    Reading one column meant those four were refused under R7 and the operator saw an empty
    grid for a relation the catalogue fully describes.

    🔴 THE COMPOSITE IS NOT A NEW CELL. `composite_key_source` is what composes
    `business_key_val` for an ordinary table — the declaration ALREADY says 「these columns
    are this row's identity」, and an identity is exactly what a total order needs. Adding a
    cell for the order would be a second expression of the same fact.

    🔴 ONE FUNCTION, THREE CALLERS, because the alternative is three places that answer
    「what breaks this table's ties」 and drift. The tiebreaker, the default sort and the
    target-row jump all read it; if any one of them reached for `row_id` directly, a
    relation without that column would order one way and page another.

    ⚠️ `row_id` STAYS THE ANSWER WHEREVER IT EXISTS, and that is the whole reason this is a
    lookup rather than a replacement. S-131 measured what moving the grid's total order
    costs: `idx_<t>_updated (updated_at, row_id)` stops being usable and a page spends
    0.7 s sorting 440,000 rows. Every table that has `row_id` therefore emits the SQL it
    emitted before — asserted by comparing the product's own rendered statement, not a
    hand-written one.

    🔴 R7 IS WHY THIS MAY NOT RETURN None. 「상한 걸린 읽기에는 전순서가 있어야 한다」 — a
    `LIMIT` without a total order hands the operator a different page on every refresh and
    raises nothing. A relation declaring neither is refused by name rather than paged
    arbitrarily.
    """
    column = getattr(table_model, "row_id", None)
    if column is not None:
        return (column,)
    entry = crud.TABLE_CONFIG.get(table_name) or {}
    declared = entry.get("business_key")
    column = getattr(table_model, str(declared), None) if declared else None
    if column is not None:
        return (column,)

    # 🔴 [S-229] THE COMPOSITE THE CATALOGUE ALREADY DECLARES. Every name has to resolve: a
    # composite missing one of its parts is not a narrower key, it is a key that does not
    # identify the row, and ordering by the rest would hand out a different page per refresh
    # — the very thing R7 exists to stop.
    parts = []
    for name in (entry.get("composite_key_source") or ()):
        part = getattr(table_model, str(name), None)
        if part is None:
            parts = []
            break
        parts.append(part)
    if parts:
        return tuple(parts)

    raise HTTPException(
        status_code=422,
        detail=("'%s' has no row_id and declares no usable business_key or "
                "composite_key_source, so a paged read of it has no total order "
                "(SCHEMA_CANON R7). Declare business_key or composite_key_source in "
                "table_config.json." % table_name))


def filter_refused(table_name, item, refused):
    """The 422 a filter that cannot narrow the rows answers (`column_filter.FilterRefused`) - by its item's name."""
    return HTTPException(status_code=422, detail=f"The filter for '{table_name}' cannot be built (item '{item}'): "
                                                 f"{refused}. Nothing is returned rather than the unfiltered table.")


def apply_column_filters(query, table_model, table_name, filters):
    """`?filters=` (AG-Grid filter model) -> query. Shared by the grid and the export."""
    if not filters:
        return query
    #: Which filter item was being built when something went wrong, so the refusal below
    #: can name it. `None` means the failure happened before any item -- a `?filters=`
    #: that is not JSON at all.
    failing_item = None
    try:
        import json
        filter_dict = json.loads(filters)
        for col_name, f_info in filter_dict.items():
            failing_item = col_name
            # A relation without a row_id column (a view that does not declare it) is refused by
            # name, as every other filter that cannot be built (lead d692af408).
            if col_name in ROW_ID_FILTER_NAMES and not model_has_row_id(table_model):
                raise HTTPException(status_code=422, detail=(
                    f"'{table_name}' has no row_id, so it cannot be filtered by '{col_name}'"))
            cond = get_column_filter_condition(table_model, col_name, f_info)
            if cond is not None:
                query = query.filter(cond)
    except HTTPException:
        # A deliberate refusal must not be swallowed by the catch-all below and turned
        # back into the silent 200 it exists to prevent.
        raise
    except FilterRefused as refused:
        raise filter_refused(table_name, failing_item, refused) from refused
    except Exception as e:
        # 🔴 A FILTER THAT CANNOT BE BUILT IS REFUSED, NOT DROPPED (S-71). This used to log
        # and fall through, and the response then carried the WHOLE table while still
        # implying the column had been filtered: measured 2026-09-08 on `dt_map`, a filter
        # whose shape the parser could not read came back with 1,006,147 rows instead of
        # 400, HTTP 200, and nothing in the answer saying which half was wrong.
        #
        # ⚠️ ONE RULE, BOTH REASONS. This used to be paired with a 400 one block above for a
        # virtual-join column whose expression could not be built; that block is gone with
        # the read-time join (S-283), and this refusal - the general one - is what remains.
        where = (f"item '{failing_item}'" if failing_item else "the filters parameter")
        raise HTTPException(
            status_code=400,
            detail=(f"The filter for '{table_name}' cannot be built ({where}): {e}. "
                    f"Nothing is returned rather than the unfiltered table.")) from e
    return query


def apply_enrichment_queue_predicate(query, table_model, table_name, rule_name, scope):
    """`?enrichment_queue=<rule name>` -> query. THE named queue predicate.

    🔴 THIS IS NOT A FILTER, AND THAT IS THE POINT  [2026-08-05, user ruling]
        "Which rows still need work" is one specific question the rule already
        declares the answer to. It used to be shipped to the client as a filter
        dict (`queue_filters`) and applied through `?filters=`, which put its
        DEFINITION in the caller: every consumer ANDs the per-column specs, so on
        a multi-target rule the queue meant EVERY target blank and filling one
        column dropped the row out of the list while its sibling was still empty.
        A row leaving the queue with work in it - the same shape as N36.

        The queue needs a cross-column OR. Rather than grow the public filter DSL
        (a surface every existing caller would inherit) the client now asks for
        the predicate BY NAME and the server composes it from the rule's own
        `target_fields`. `?filters=` is untouched and still means what it meant.

    A 400 rather than a silent fallback: answering an unfiltered page to a caller
    who asked for the queue would return MORE rows than were asked for while the
    response implied the queue - the same refusal `?cols=` makes.
    """
    if not rule_name:
        return query
    # 🔴 [판정 636] 평면 파일 «하나»가 아니라 «이 제품이 세운 선언 전부»를 봅니다 —
    #    통합 `derive.decide` 로 적힌 것도 포함입니다. 거절 문구는 아래 그대로입니다.
    from chain import enrich_declarations, enrichment

    rule = enrich_declarations.find(rule_name, known_tables=crud.TABLE_CONFIG)
    if rule is None:
        raise HTTPException(
            status_code=400,
            detail=(f"Enrichment rule '{rule_name}' was not found - no queue condition can be built, "
                    f"so nothing is returned."))
    if rule["derived_table"] != table_name:
        # The predicate is composed from THIS rule's target fields; against any
        # other table those columns mean nothing (or do not exist).
        raise HTTPException(
            status_code=400,
            detail=(f"Rule '{rule_name}' keeps its queue in table '{rule['derived_table']}' "
                    f"(asked: '{table_name}')."))
    try:
        cond = enrichment.config.queue_predicate_condition(
            table_model, rule, scope=scope or enrichment.config.QUEUE_SCOPE_QUEUE)
    except enrichment.config.QueuePredicateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return query.filter(cond)


def search_scope_columns(table_name, cols):
    """The columns a grid search reads: `?cols=` when sent, else the declared scope (`crud.resolve_search_columns`). One
    answer for the search condition and for what a stopped search says to index (총괄 d16033b63)."""
    if cols:
        return [c.strip() for c in cols.split(",") if c.strip()]
    col_types = (crud.TABLE_CONFIG.get(table_name, {}) or {}).get("column_types", {})
    # 🔴 THE DECLARED SCOPE, DEFAULTING TO THE IDENTITY (S-125, 판정 255). This used to
    # be every declared column UNIONED with every virtual-join column, which on
    # `dt_log` meant 31 ILIKE arms over casts and SIX aliased LEFT JOINs to
    # `dt_inventory` on one key - 2,174 ms for one keystroke's worth of search. The
    # rule lives in `crud.resolve_search_columns` because the config load has to reach
    # the same verdict from a different set of known columns.
    col_list, unknown_declared = crud.resolve_search_columns(table_name, set(col_types))
    col_list = list(col_list)
    if unknown_declared:
        # Named, not dropped: an entry nothing matches is a scope the operator
        # believes is in force. WARNING rather than a refusal - the fallback already
        # searched something, and a 500 here would take the grid down over a typo.
        logger.warning(
            f"[Search] Table '{table_name}' declares search_columns that nothing can "
            f"search: {sorted(unknown_declared)}. They are not in column_types; the "
            f"search used {col_list}."
        )
    return col_list


def apply_search_filter(query, table_model, table_name, q, cols,
                        scope_report=None):
    """`?q=` (+ optional `?cols=` scope) -> query. Shared by the grid and the export.

    🔴 The `?cols=` refusal is the reason this is one function. A column named in the
    scope that builds NO condition used to be dropped silently, and because the filter is
    only applied when at least one condition survives, a scope consisting ENTIRELY of such
    columns skipped filtering and returned the WHOLE TABLE with 200 - while the response
    implied that column had been searched.
    """
    if not q:
        return query
    from sqlalchemy import cast, String, or_
    safe_q = q.replace("%", "\\%").replace("_", "\\_")

    col_list = search_scope_columns(table_name, cols)

    conditions = []
    unsearchable = []
    for col in col_list:
        # ⚠️ A framework column the model does not carry (a view: 총괄 01cad807c) falls
        #   through to `unsearchable` below, like any other column the relation lacks.
        if col in ["created_at", "updated_at"] and getattr(table_model, col, None) is not None:
            target_col = table_model.created_at if col == "created_at" else table_model.updated_at
            conditions.append(models.search_text(target_col).ilike(f"%{safe_q}%", escape="\\"))
        elif col in ["row_id", "id"]:
            # 🔴 THE ROW'S IDENTITY, NOT A COLUMN NAMED row_id (총괄 4e508835a). The
            #   total-order key IS `row_id` wherever it exists - the same SQL - and a
            #   view's declared key otherwise (`ledger_events` searches its `id`).
            #   ⚠️ A declared key is CAST like every other column here: the declaration can
            #   say `string` over a uuid (`ledger_events.id`), and PostgreSQL refuses ILIKE.
            row_id = getattr(table_model, "row_id", None)
            for key in total_order_keys(table_model, table_name):
                text_key = key if key is row_id else models.search_text(key)
                conditions.append(text_key.ilike(f"%{safe_q}%", escape="\\"))
        elif col == "business_key_val" and getattr(table_model, col, None) is not None:
            conditions.append(table_model.business_key_val.ilike(f"%{safe_q}%", escape="\\"))
        elif hasattr(table_model, col):
            conditions.append(models.search_text(getattr(table_model, col)).ilike(f"%{safe_q}%", escape="\\"))
        else:
            unsearchable.append(col)

    # Only when the caller SCOPED the search (`?cols=`) and nothing in that scope is
    # searchable. The unscoped path cannot reach here (it always contributes row_id and
    # business_key_val).
    if unsearchable and not conditions:
        raise HTTPException(
            status_code=400,
            detail=(f"Table '{table_name}' cannot be searched by {', '.join(unsearchable)} - "
                    f"those columns are not in it. Nothing is returned rather than an unsearched list."))
    if unsearchable:
        logger.warning("[Search] '%s': ignoring unsearchable column(s) %s in ?cols=",
                       table_name, ", ".join(unsearchable))

    if conditions:
        if scope_report is not None:
            # ⚠️ THE COUNT, NEVER THE NAMES OR THE TERM (판정 255). The
            # timing line is always on; how MANY arms a search built is the
            # shape of the query, which is what a plan question needs.
            scope_report["arms"] = len(conditions)
            # the columns searched - each said indexed or not in the answer (총괄 d16033b63), never in the log line
            scope_report["columns"] = [col for col in col_list if col not in unsearchable]
        query = query.filter(or_(*conditions))
    return query


def transaction_rows(db, table_model, table_name, transaction_id):
    """The rows transaction `transaction_id` changed, as a filter: the rows of its lines (cell-source overhaul - the
    (batch) index; a formula writes lines too, C 11-10); none in a relation without lines."""
    import sqlalchemy as sa

    from admin import audit_history
    from database import lines

    refuse_row_address(table_name)
    if not lines.has_lines(db, table_name):
        return sa.false()
    return table_model.row_id.in_(audit_history.group_line_rows(table_name, transaction_id))


def narrowed_table_query(db, table_name, table_model, *, q=None, cols=None,
                         transaction_id=None, filters=None,
                         enrichment_queue=None, enrichment_queue_scope=None,
                         scope_report=None, pivot=None):
    """The narrowed query AND the count-cache key that belongs to it. ONE assembly.

    `pivot` (`grid_pivot.of`): the filters split - the key columns' here, the items' by `grid_pivot.narrow`.

    🔴 THE ROWS AND THE COUNT OF THEM MUST BE READ FROM THE SAME SENTENCE. `/data` and
    `/data/count` answer the same question in two halves, and a second interpretation of
    `?filters=` would make them disagree WITHOUT ERRORING - the grid would show rows the
    footer says are not there, and nothing in either response would say which is wrong.
    So the two get one function, not two blocks that look alike.

    The cache key comes back from here for the same reason: a route that spelled its own
    would split the cache in half, and `invalidate_table_cache` would clear one of them.

    ⚠️ THE CSV EXPORT IS A THIRD BLOCK AND IS NOT TOUCHED HERE. It already differs - it
    never applies the named queue predicate - so folding it in would change what an export
    contains, which is a different decision from this one. Consolidating it is its own item.
    """
    query = db.query(table_model)

    # [NEW] 트랜잭션 필터링
    if transaction_id:
        query = query.filter(transaction_rows(db, table_model, table_name, transaction_id))

    # [NEW] AG-Grid 컬럼 필터링
    key_filters, items = grid_pivot.split_filters(filters, pivot) if pivot else (filters, {})
    query = apply_column_filters(query, table_model, table_name, key_filters)
    if pivot:
        try:
            query = grid_pivot.narrow(query, table_model, pivot, items)
        except FilterRefused as refused:
            raise filter_refused(table_name, pivot.value, refused) from refused

    # [2026-08-05] 이름 붙은 큐 술어 (일반 필터 DSL이 표현할 수 없는 컬럼 간 OR)
    query = apply_enrichment_queue_predicate(query, table_model, table_name,
                                             enrichment_queue, enrichment_queue_scope)

    # ── [Step 0] 검색 필터 구성 (실제 컬럼 기준 ilike 다중 OR 검색) ──
    # ⚠️ AN OUT-PARAM, NOT A FOURTH RETURN VALUE. This function's own docstring
    # says why the 3-tuple is load-bearing, and two call sites unpack it; the codebase
    # already answers 「extra detail for the caller who asks」 with `drop_report`.
    if pivot and q:             # a key group is searched by any of its long rows (총괄 10-22)
        held, group_rows = grid_pivot.group_rows(db, table_model, pivot)
        query = query.filter(apply_search_filter(group_rows, held, table_name, q, cols,
                                                 scope_report=scope_report).exists())
    else:
        query = apply_search_filter(query, table_model, table_name, q, cols,
                                    scope_report=scope_report)

    # [Fix] transaction_id 필터링 시에도 캐시 정합성을 보장하기 위해 키에 포함
    cache_key_parts = ["total_count"]
    if q: cache_key_parts.append(f"q:{q}")
    if cols: cache_key_parts.append(f"cols:{cols}")
    if transaction_id: cache_key_parts.append(f"tx:{transaction_id}")
    if filters: cache_key_parts.append(f"filters:{filters}")
    # The named queue predicate narrows the query exactly like `?filters=` does, so
    # it must narrow the CACHE KEY too. Omitting it would serve the unfiltered
    # table total as the queue remainder for 5 seconds - a progress bar reading
    # 0% with everything answered, which is N36 wearing the other face.
    if enrichment_queue:
        cache_key_parts.append(f"eq:{enrichment_queue}:{enrichment_queue_scope or ''}")
    # One world's copy of a per-world relation counts its own rows (`grid_model`).
    if table_model.__table__.schema:
        cache_key_parts.append(f"in:{table_model.__table__.schema}")
    if pivot:
        cache_key_parts.append("pivot")
    # 🔴 키 철자는 `build_count_cache_key` 하나뿐이다. 여기서 `"|".join(...)`을 다시
    #    쓰면 무효화 쪽 판정과 갈라져 여덟 개 호출 지점이 전부 죽는다(그 사고의 재발).
    return query, build_count_cache_key(table_name, *cache_key_parts)


#: A value list's length - one more is read, to say `more` (총괄 11-05).
VALUES_CAP = 10000


def column_values(db, table_name, table_model, column, *, search=None, filters=None, pivot=None, **narrowing):
    """`column`'s distinct values over the grid's narrowing less its own filter (총괄 11-05: the list a set filter picks
    from, as a spreadsheet's) - sorted, the blank cells one None at the end, at most `VALUES_CAP` (`more`); `search`
    keeps the values that contain it, as the text filter's contains. A value is the one its `equals` matches
    (`filter_column`). On a pivot `column` is a name its read takes (`grid_pivot.item_of`): an item's (`item:<item>`)
    values are that item's rows' `value`, and its blank also a group without that item's row (`grid_pivot.narrow`).
    Nothing else narrowing and a btree leading on the column: one index probe per value (`_skipped_values`) - else
    DISTINCT over the narrowed rows."""
    import json

    from sqlalchemy import case

    item = grid_pivot.item_of(column, pivot) if pivot is not None else None
    try:
        expr, is_numeric = filter_column(table_model, column if item is None else pivot.value)
    except FilterRefused as refused:
        raise filter_refused(table_name, column, refused) from refused
    try:
        asked = json.loads(filters) if filters else None
    except ValueError:
        asked = None
    if isinstance(asked, dict):
        kept = {name: spec for name, spec in asked.items() if name != column}
        filters = json.dumps(kept) if kept else None
    found = None
    if item is None and not (search or filters or any(narrowing.values())):
        found = _skipped_values(db, table_model, column, is_numeric)
    absent = False
    if found is None:
        query, _ = narrowed_table_query(db, table_name, table_model, filters=filters, pivot=pivot, **narrowing)
        if item is not None:
            absent = not search and db.query(grid_pivot.narrow(
                query, table_model, pivot, {item: {"filterType": SET, "values": [None]}}).exists()).scalar()
            query = query.filter(getattr(table_model, pivot.column) == item)
        text = models.search_text(expr) if is_numeric else expr
        if search:
            query = query.filter(text.ilike(TEXT_PATTERNS["contains"].format(search)))
        value = case((crud.blank_sql_condition(text), None), else_=expr)
        found = [row[0] for row in query.with_entities(value).distinct().order_by(value.asc().nullsfirst())
                 .limit(VALUES_CAP + 2)]
    blank = absent or (bool(found) and found[0] is None)
    found = found[1:] if found and found[0] is None else found
    return {"column": column, "values": found[:VALUES_CAP] + ([None] if blank else []), "more": len(found) > VALUES_CAP}


def _skipped_values(db, table_model, column, is_numeric):
    """`column`'s values in the shape `column_values` reads them (a None first when a cell is blank) by a recursive
    skip over a btree that leads with it - one index probe per value, not the table (box throwaway DB 10M rows: 33 ms
    against DISTINCT's 0.5-0.9 s); None when PostgreSQL has no such index, or the column's text is not its value."""
    from sqlalchemy import String, exists, text

    table = getattr(table_model, "__table__", None)
    bind = db.get_bind()
    if bind.dialect.name != "postgresql" or table is None or column not in table.columns:
        return None
    raw = table.columns[column]
    if not (is_numeric or isinstance(raw.type, String)):
        return None
    held = models.catalogue_indexes(db.connection().connection.dbapi_connection, table.name)
    if not any(models.orders_rows_by(index, [column]) for index in held):
        return None
    prep = bind.dialect.identifier_preparer
    rel, col = prep.format_table(table), prep.quote(column)
    first = "IS NOT NULL" if is_numeric else "> ''"
    values = [row[0] for row in db.execute(text(
        "WITH RECURSIVE s(v) AS ((SELECT {c} FROM {t} WHERE {c} {first} ORDER BY {c} LIMIT 1) UNION ALL "
        "SELECT (SELECT {c} FROM {t} WHERE {c} > s.v ORDER BY {c} LIMIT 1) FROM s WHERE s.v IS NOT NULL) "
        "SELECT v FROM s WHERE v IS NOT NULL LIMIT :most".format(c=col, t=rel, first=first)), {"most": VALUES_CAP + 1})]
    # a number is blank only as NULL - its text is never '' (`column_filter`'s blank branch)
    blank = db.query(exists().where(raw.is_(None) if is_numeric else crud.blank_sql_condition(raw))).scalar()
    return ([None] if blank else []) + values

# moved whole from main.py (lead 11-08) - a chain worker merges its items as the page does
from datetime import datetime  # noqa: E402

from sqlalchemy.orm import Session  # noqa: E402

from utils.time_format import to_local_str  # noqa: E402
from utils.wire_format import wire_text  # noqa: E402


def fetch_and_merge_metadata(db: Session, table_name: str, rows: list, user_cols: list, include_sources: bool = True) -> list:
    """
    기본 데이터 테이블의 row 객체들에 cell_overwrites 및 cell_sources 정보를 병합하여 
    API 응답 포맷인 { value, is_overwrite, sources, updated_by } 딕셔너리로 합성합니다.
    include_sources=False이면 cell_sources 조회를 생략하여 대량 조회 성능을 최적화합니다.
    """
    if not rows:
        return []

    # 🔴 A VIEW HAS NO LAYERING METADATA, so there is nothing to merge (S-186). Cell
    # sources and overwrites are written by the write door, and that door refuses this
    # relation by name - so every row of a view has exactly one value per column, the one
    # the view selected. Asking for its `row_id` here raised `AttributeError` and the route
    # answered 500, which is the FIFTH seat in this path that assumed the framework
    # columns: the sort, the tiebreaker, the paging, the jump, and now the merge.
    #
    # ⚠️ SHAPED LIKE A NORMAL ROW, not skipped. The grid reads `{value, is_overwrite,
    # sources, updated_by}` per cell, so returning the raw ORM objects here would move the
    # break one layer up into the serializer.
    from ledger.setup_bundle import catalog_kind

    if catalog_kind(crud.TABLE_CONFIG.get(table_name)) == "view":
        # 🔴 THE SAME WRAPPER EVERY ROW USES. The grid reads `{row_id, table_name, data,
        # created_at, updated_at}` for EVERY row (`grid.js` reaches for `dataObj.data[col]`),
        # so a flat dict here stopped it drawing a view it had been drawing — the response
        # SHAPE is a contract even where the content underneath is thinner.
        #
        # ⚠️ THE CELL IS `{value}` AND NOTHING ELSE. A view has no layering, and writing
        # `is_overwrite: False` / `sources: {}` would be INVENTING an absent marker as a
        # value — 「없는 것」 and 「0인 것」 must not render the same, which is the defect this
        # repository has paid for more than once.
        #
        # ⚠️ Times go through `to_local_str`: a raw datetime makes the payload
        # non-JSON-native and the route's own warning prices that at ~10x.
        # 🔴 [S-229] THE ROW'S IDENTITY IS ITS KEY, COMPOSED THE WAY THE TABLE DECLARES.
        # The grid needs one `row_id` per row, and a composite-keyed view has no single
        # column carrying it - so the parts are joined by `crud.compose_business_key`, the
        # one spelling of an identity, rather than by a separator invented here.
        key_names = [key.key for key in
                     total_order_keys(models.DYNAMIC_TABLES.get(table_name), table_name)]
        out = []
        for row in rows:
            cells = {}
            for col in user_cols:
                value = getattr(row, col, None)
                cells[col] = {"value": wire_text(
                    to_local_str(value) if isinstance(value, datetime) else value)}
            out.append({
                "row_id": (getattr(row, key_names[0], None) if len(key_names) == 1
                           else crud.compose_business_key(
                               table_name, [getattr(row, name, None) for name in key_names],
                               key_names)),
                "table_name": table_name,
                "data": cells,
                "created_at": to_local_str(getattr(row, "created_at", None)),
                "updated_at": to_local_str(getattr(row, "updated_at", None)),
            })
        return out

    row_ids = [r.row_id for r in rows]
    
    # 1. cell_overwrites 일괄 로딩 (Tuple 쿼리로 ORM 인스턴스화 오버헤드 제거)
    overwrites = db.query(
        models.CellOverwrite.row_id,
        models.CellOverwrite.column_name,
        models.CellOverwrite.is_overwrite,
        models.CellOverwrite.updated_by,
        models.CellOverwrite.manual_priority_source
    ).filter(
        models.CellOverwrite.table_name == table_name,
        models.CellOverwrite.row_id.in_(row_ids)
    ).all()
    
    overwrites_map = {}
    for row_id, column_name, is_ow, updated_by, manual_priority_source in overwrites:
        overwrites_map[(row_id, column_name)] = (is_ow, updated_by, manual_priority_source)
        
    # 2. cell_sources 일괄 로딩 (include_sources가 True일 때만 실행)
    sources_map = {}
    ingested_map = {}
    if include_sources:
        # [ORDER BY source_name] Same reason as the crud SELECTs: this list feeds
        # `compute_priority_value`, so its order is stated rather than inherited from
        # the heap. `source_name` is UNIQUE per cell (`idx_sources_lookup_source`).
        #
        # [tiebreak] `ingested_at` is selected because recency breaks a tie between
        # equally-ranked sources. Without it this READ path would resolve ties
        # alphabetically while the WRITE path resolved them by recency, so the
        # `priority_source` badge could name a different layer than the materialised
        # `value` actually came from.
        sources = db.query(
            models.CellSource.row_id,
            models.CellSource.column_name,
            models.CellSource.source_name,
            models.CellSource.value,
            models.CellSource.ingested_at
        ).filter(
            models.CellSource.table_name == table_name,
            models.CellSource.row_id.in_(row_ids)
        ).order_by(models.CellSource.source_name.asc()).all()

        for row_id, column_name, source_name, value, ingested_at in sources:
            key = (row_id, column_name)
            if key not in sources_map:
                sources_map[key] = {}
                ingested_map[key] = {}
            sources_map[key][source_name] = value
            ingested_map[key][source_name] = ingested_at

    data_list = []
    for row in rows:
        r_dict = row.__dict__
        r_id = r_dict.get("row_id") or row.row_id
        r_data = {}
        c_at_str = to_local_str(r_dict.get("created_at") or row.created_at)
        u_at_str = to_local_str(r_dict.get("updated_at") or row.updated_at)
        
        for col in user_cols:
            val_raw = r_dict.get(col) if col in r_dict else getattr(row, col, None)
            key = (r_id, col)
            
            ow_info = overwrites_map.get(key)
            col_srcs = sources_map.get(key, {})
            
            is_ow = ow_info[0] if ow_info else False
            updated_by = ow_info[1] if ow_info else "system"
            manual_pin = ow_info[2] if ow_info else None
            
            # [성능 최적화] include_sources=False 일 때는 소스 쿼리를 건너뛰었으므로 Overwrite 테이블 정보로 즉시 유도
            if not include_sources:
                # a pin answers first - a cell pinned to a file's layer shows that layer, whoever pinned it (owner
                # 11-08 ㄱ: the overwrite row a pin writes names the person who pinned, and read as «user» it painted
                # the cell «Written by person»)
                # the layers the overwrite row shows; the ranking stays compute_priority_value's
                shown = {}
                if manual_pin is not None:
                    shown[manual_pin] = {}
                elif updated_by == "collision_merge":
                    shown["collision_merge"] = {}
                elif is_ow or updated_by == "user":
                    shown["user"] = {}
                _, priority_source = crud.compute_priority_value(shown, manual_pin, table_name, cell=(table_name, col, row))
            else:
                # `col_srcs` is `{source: value}` because that dict IS the client-facing
                # cell contract and cannot carry a timestamp; the timestamps travel
                # beside it. The response shape is unchanged.
                _, priority_source = crud.compute_priority_value(
                    col_srcs, manual_pin, table_name,
                    ingested_at_by_source=ingested_map.get(key), cell=(table_name, col, row))

            is_collision = (priority_source == "collision_merge") or (include_sources and "collision_merge" in col_srcs)
            has_overwrite = is_ow or (manual_pin is not None) or is_collision or (include_sources and "user" in col_srcs)
            
            r_data[col] = {
                # S-190: the SAME function the view arm and the export use. A dynamic
                # table builds only String/Float/DateTime columns so nothing here is a
                # dict today -- it is here so 「this cell as text」 has one author and not
                # one per arm.
                "value": wire_text(val_raw),
                "is_overwrite": has_overwrite,
                "is_collision_merge": is_collision,
                "sources": col_srcs,
                "updated_by": updated_by,
                "manual_priority_source": manual_pin,
                "priority_source": priority_source
            }
                
        r_data["created_at"] = {"value": c_at_str, "is_overwrite": False, "sources": {}, "updated_by": "system"}
        r_data["updated_at"] = {"value": u_at_str, "is_overwrite": False, "sources": {}, "updated_by": "system"}
        
        # 🔴 그래프 동기화 컬럼 «셋»은 여기서 빠졌습니다 (2026-09-02). 2026-08-31 에
        # `system_cols` 목록에서는 빠졌는데 «채우는 자리»가 안 빠져서, 선언한 표가 «0개»인
        # 컬럼 셋이 그리드 «모든 행»에 셀 모양으로 실려 나가고 있었습니다 —
        # 라우트 자기 타이머의 `Dict Conv` 칸에서, 페이지마다, 행마다.
        # 실측: 라이브 table_config 44개 표 중 셋 중 «하나라도» column_types/display_columns
        # 에 선언한 표 «0». 즉 아무도 묻지 않은 것을 나르고 있었습니다.
        # DB 컬럼(models.py)은 «진짜 컬럼»이고 그대로 있습니다 — 그것을 지우는 것은 별건입니다.

        # dynamic data attribute 바인딩
        row.data = r_data
        
        data_list.append({
            "row_id": r_id,
            "table_name": table_name,
            "data": r_data,
            "created_at": c_at_str,
            "updated_at": u_at_str
        })

    # ⚰️ [S-283] THE VERIFIED JOIN'S `expose` COLUMNS WERE ATTACHED HERE, and only here,
    # because this is the single serialization point for row payloads (grid page, single-row
    # read, batch-update response, WS items) - so a joined column could not be present on one
    # of those and absent on another. Read-time joins are retired (ruling 461): a payload now
    # carries the table's stored columns and nothing is computed into it on the way out.


    return data_list

def cell_layers(db, table_name: str, rows: dict, cells: list) -> dict:
    """{(row_id, column): {"sources", "manual_priority_source", "priority_source", "value"}} - each of `cells` (of
    `rows`, {row_id: row}) as the sources panel reads it: every layer with its time and writer, the pin, and the
    winner `crud.compute_priority_value` picks."""
    from database import crud, models

    if not cells:
        return {}
    row_ids = sorted({row_id for row_id, _ in cells})
    columns = sorted({column for _, column in cells})
    layers = {}
    # [ORDER BY source_name] this feeds `compute_priority_value`; a SELECT that feeds a decision states its order
    for s in db.query(models.CellSource).filter(
            models.CellSource.table_name == table_name, models.CellSource.row_id.in_(row_ids),
            models.CellSource.column_name.in_(columns)).order_by(models.CellSource.source_name.asc()):
        layers.setdefault((s.row_id, s.column_name), {})[s.source_name] = {
            "value": s.value, "timestamp": s.ingested_at.isoformat() if s.ingested_at else None,
            "updated_by": s.updated_by}
    pins = {(ow.row_id, ow.column_name): ow.manual_priority_source for ow in db.query(models.CellOverwrite).filter(
        models.CellOverwrite.table_name == table_name, models.CellOverwrite.row_id.in_(row_ids),
        models.CellOverwrite.column_name.in_(columns))}
    out = {}
    for row_id, column in cells:
        sources, pin, row = layers.get((row_id, column), {}), pins.get((row_id, column)), rows[row_id]
        _, winner = crud.compute_priority_value(sources, pin, table_name, cell=(table_name, column, row))
        out[(row_id, column)] = {"sources": sources, "manual_priority_source": pin, "priority_source": winner,
                                 "value": getattr(row, column)}
    return out


def read_as_page(db, table_name: str, rows: list, user_cols: list, include_sources: bool, writers: bool = True):
    """(merged rows, looks): `rows` as the page reads them - the page read and every batch_row_upsert item, so a
    screen that did not make the write colours a cell as a read would (lead 11-08, 클라B's L2). `writers` False: the
    cells' writers the layers would name are left to the page's `grid_look.WRITERS` read (owner 11-10 ㄱ)."""
    import grid_look

    merged = fetch_and_merge_metadata(db, table_name, rows, user_cols, include_sources=include_sources)
    return merged, grid_look.read(db, table_name, merged, writers=writers)
