"""The AG-Grid filter DSL -> SQLAlchemy translator, in a module every process can import.

WHY THIS IS NOT IN `main.py`
    It used to be, and `enrichment_analysis` reached it with a lazy `import main`
    inside a function body. That works in the web process, where `main` is already
    the loaded application module, and it works from a CLI. It does NOT work in the
    worker processes: `run_auto_update.py` puts every collector's own directory on
    `sys.path[0]` (and `parsers/directory_watcher.py` does the same for each table's
    `scripts/` directory), so in those processes `main` is not a stable name - a user
    file called `main.py` in any of those directories binds first and the translator
    is simply not there. The failure is an AttributeError raised deep inside a queue
    walk, and the same operation from the CLI succeeds, because the CLI never inserts
    those directories.

    This is the second time the same shape has been paid for: `chain_ingestion_worker`
    did `from main import to_local_str`, and the fix was the same one - move the shared
    helper to a module that is not a process entry point (`utils/time_format.py`).
    `main.py` re-exports this name, so `main.get_column_filter_condition` keeps
    resolving for anything that still spells it that way.

WHAT USES IT
    `GET /tables/{t}/data` and `GET /tables/{t}/export` (via main's shared query
    construction), and `enrichment_config.queue_predicate_condition`, which builds
    the NAMED enrichment queue predicate out of this vocabulary. Those must be the
    SAME translator: the worklist, the badge, the admin count and the retroactive
    sweep cannot be allowed to disagree about which rows are in the queue.

    🔴 THE QUEUE PREDICATE IS COMPOSED FROM THIS, NOT EXPRESSED IN THIS DSL
    [2026-08-05]. It needs a cross-column OR ("ANY target field still blank") and
    this grammar has none - `operator`/`conditions` combine specs for ONE column.
    The queue used to be shipped to the client as a filter dict and applied here,
    which silently meant EVERY target blank and dropped partly filled rows out of
    the worklist. The repair was a named server-side predicate, NOT a wider DSL:
    widening this grammar hands the new surface to every existing caller to answer
    a question only one rule asks. Resist the same request next time.

    The blank / notBlank spellings are NOT defined here - they delegate to
    `crud.blank_sql_condition` / `crud.not_blank_sql_condition`, which is the one
    funnel for that rule (see the comment at the `blank` branch below).
"""
from database import crud

def get_column_filter_condition(table_model, col_name: str, f_info: dict, col_expr_override=None):
    """AG-Grid filter spec -> SQLAlchemy condition.

    `col_expr_override`: evaluate the filter against THIS expression instead of looking
    `col_name` up on the model. A virtual-join column has no stored column to look up -
    its displayed value is a COALESCE over the left column and the joined right columns
    (`virtual_join_executor.resolved_expression`). Passing the expression in reuses this
    entire operator vocabulary (contains / equals / startsWith / inRange / ...) rather
    than growing a second, thinner filter translator beside it.

    An override is always treated as text: the resolved value's domain includes
    `unresolved_label` ("미상"), so it is a string expression even when the underlying
    right column is declared numeric.
    """
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy import cast, String, func, or_, and_

    # 1. Handle compound filter conditions (AND / OR)
    if "operator" in f_info:
        operator = f_info.get("operator")
        conditions = f_info.get("conditions", [])
        sqlalchemy_conds = []
        for cond_info in conditions:
            sub_cond = get_column_filter_condition(table_model, col_name, cond_info,
                                                  col_expr_override=col_expr_override)
            if sub_cond is not None:
                sqlalchemy_conds.append(sub_cond)
        if not sqlalchemy_conds:
            return None
        return and_(*sqlalchemy_conds) if operator == "AND" else or_(*sqlalchemy_conds)

    # 2. Handle simple filter condition
    f_val = f_info.get("filter")
    f_type = f_info.get("type", "contains")

    # [N7/N8] An override compares TEXT, but a client filtering a typed virtual column
    # may send the value as a NUMBER or a BOOLEAN (AG-Grid does for number- and
    # boolean-typed columns). Comparing a text expression against a typed bind is a
    # dialect lottery - Postgres errors, SQLite silently matches nothing. Render it to
    # the same canonical text the expression produces, through the twin of the funnel
    # that built the expression (`crud.column_text_sql` <-> `crud.comparison_text_value`):
    # int spelling for numbers (3.0 -> '3'), `'true'`/`'false'` for booleans,
    # `TEMPORAL_TEXT_FORMAT` for timestamps. Strings pass through untouched - this is a
    # type bridge, not a second trim.
    if col_expr_override is not None and f_val is not None and not isinstance(f_val, str):
        f_val = crud.comparison_text_value(f_val)

    # Allow blank/notBlank even if f_val is not present
    if f_type not in ["blank", "notBlank"] and f_val is None:
        return None

    # Column path resolution and numeric check
    is_numeric = False
    if col_expr_override is not None:
        # No model lookup: this column is computed, not stored.
        col_expr = cast(col_expr_override, String)
    elif col_name in ["created_at", "updated_at"]:
        target_col = table_model.created_at if col_name == "created_at" else table_model.updated_at
        col_expr = cast(target_col, String)
    elif col_name in ["row_id", "id"]:
        col_expr = table_model.row_id
    else:
        if not hasattr(table_model, col_name):
            return None
        raw_col = getattr(table_model, col_name)
        from sqlalchemy.sql.sqltypes import Numeric, Float, Integer
        is_numeric = isinstance(raw_col.type, (Numeric, Float, Integer))
        
        # Check if we should treat it as numeric filter
        numeric_operators = ["equals", "notEqual", "lessThan", "lessThanOrEqual", "greaterThan", "greaterThanOrEqual", "inRange"]
        if is_numeric and f_type in numeric_operators:
            col_expr = raw_col
        else:
            from sqlalchemy import cast, String
            col_expr = cast(raw_col, String)
            
    # Condition mapping based on type
    #
    # NOTE on an override (virtual-join column): the resolved expression COALESCEs to
    # `unresolved_label`, which `virtual_join_config` guarantees is a non-empty string.
    # So `blank` matches nothing and `notBlank` matches everything - and that is the
    # honest answer, because no cell in that column ever DISPLAYS as blank. "Show me the
    # rows the join could not resolve" is `equals <unresolved_label>`, not `blank`.
    #
    # 🔴 THE OPERATOR'S "Blank" FILTER RUNS THROUGH HERE, and it must be the SAME
    # predicate as everywhere else. It used to be an inline copy, and contract-keeper
    # proved what that costs: patching `crud.blank_sql_condition` changed nothing in the
    # AG-Grid blank filter, because this - the busiest caller of the rule - was running
    # its own spelling. The funnel existed and the one path an operator actually touches
    # walked around it.
    #
    # The `is_numeric` special-case that used to live here is GONE, not moved: for
    # `blank`/`notBlank` these operators are deliberately absent from `numeric_operators`
    # above, so `col_expr` is ALWAYS already `cast(raw_col, String)`. A cast numeric is
    # never the empty string when it is non-NULL, so `IS NULL OR = ''` and the old
    # `IS NULL` return the same rows - one redundant disjunct, one fewer spelling.
    #
    # That pre-cast is also the precondition `crud.blank_sql_condition` documents: it
    # compares against `''`, so the caller owns making the expression text-typed. Every
    # caller here does.
    if f_type == "blank":
        return crud.blank_sql_condition(col_expr)
    elif f_type == "notBlank":
        return crud.not_blank_sql_condition(col_expr)


    if is_numeric and f_type in ["equals", "notEqual", "lessThan", "lessThanOrEqual", "greaterThan", "greaterThanOrEqual", "inRange"]:
        if f_type == "inRange":
            try:
                val_from = float(f_info.get("filter"))
                val_to = float(f_info.get("filterTo"))
                return and_(col_expr >= val_from, col_expr <= val_to)
            except (ValueError, TypeError):
                return None
        else:
            try:
                val = float(f_val)
            except (ValueError, TypeError):
                return None
            
            if f_type == "equals":
                return col_expr == val
            elif f_type == "notEqual":
                return col_expr != val
            elif f_type == "lessThan":
                return col_expr < val
            elif f_type == "lessThanOrEqual":
                return col_expr <= val
            elif f_type == "greaterThan":
                return col_expr > val
            elif f_type == "greaterThanOrEqual":
                return col_expr >= val
    else:
        # String comparison
        if f_type == "contains":
            return col_expr.ilike(f"%{f_val}%")
        elif f_type == "notContains":
            return ~col_expr.ilike(f"%{f_val}%")
        elif f_type == "equals":
            return col_expr == f_val
        elif f_type == "notEqual":
            return col_expr != f_val
        elif f_type == "startsWith":
            return col_expr.ilike(f"{f_val}%")
        elif f_type == "endsWith":
            return col_expr.ilike(f"%{f_val}")
        else:
            return col_expr.ilike(f"%{f_val}%")
