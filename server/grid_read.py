"""The grid read path - the narrowed query a grid page, its count, the export and a chain reader share - importable
without main (총괄 10-22: a chain slot does not import main). Moved here from main.py whole; main re-exports every name,
so a caller of main.<name> reads the same function."""
import logging

from fastapi import HTTPException

import grid_pivot
from column_filter import ROW_ID_FILTER_NAMES, get_column_filter_condition, model_has_row_id
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
        from admin.audit_cache import in_group

        refuse_row_address(table_name)
        subquery = db.query(models.AuditLog.row_id).filter(
            models.AuditLog.table_name == table_name,
            in_group(models.AuditLog.transaction_id, transaction_id)
        )
        query = query.filter(table_model.row_id.in_(subquery))

    # [NEW] AG-Grid 컬럼 필터링
    key_filters, items = grid_pivot.split_filters(filters, pivot) if pivot else (filters, {})
    query = apply_column_filters(query, table_model, table_name, key_filters)
    if pivot:
        query = grid_pivot.narrow(query, table_model, pivot, items)

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
