"""The main grid's pivot (소유자 10-22, 총괄 95d9525b4 · a1d9382fb): a long table keyed (k..., column) read as one row
per key group - its keys less `column` - and one cell per value of `column`, filled from `value`. Two declaration cells
(`"pivot": {"column", "value"}`); the read is the grid's own route (`?pivot=1`), its key and item column filters
the grid's, an item's filter the grid filter's own condition inside one EXISTS, and a cell's write the grid save door
by its row_id (a blank cell: by its keys, which makes the row)."""
from fastapi import HTTPException
from sqlalchemy import Boolean, and_, exists, func, or_, select, tuple_
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import ColumnElement
from sqlalchemy.sql.visitors import InternalTraversal

#: The filter and sort name of an item column - always, so a key column and an item never share a name.
ITEM_PREFIX = "item:"
#: The read's own arguments a pivot does not take - each would narrow or page by long rows, not by key groups.
NOT_TAKEN = ("transaction_id", "enrichment_queue", "target_row_id", "after", "before")


def refusal(table, entry):
    """`(path, sentence)` when the entry's `pivot` cannot be read, else None (none declared included)."""
    from chain import cell_layer

    pivot = entry.get("pivot")
    if pivot is None:
        return None
    path = "tables.%s.pivot" % table
    if not isinstance(pivot, dict) or not all(isinstance(pivot.get(cell), str) and pivot.get(cell).strip()
                                              for cell in ("column", "value")):
        return path, 'pivot is {"column": <a key column>, "value": <the column that fills the cells>}'
    keys = cell_layer.entry_key_columns(entry)
    column, value = pivot["column"], pivot["value"]
    if column not in keys:
        return (path + ".column", "'%s' is not one of the table's keys (%s) - name a key column, or add it to "
                                  "composite_key_source" % (column, ", ".join(keys) or "none declared"))
    if len(keys) < 2:
        return (path + ".column", "the table's only key is '%s' - a pivot row is the keys besides it; add one to "
                                  "composite_key_source" % column)
    if value in keys:
        return path + ".value", "'%s' is a key column - name the column whose values fill the cells" % value
    if value not in (entry.get("column_types") or {}):
        return path + ".value", "'%s' is not a declared column - name one of column_types" % value
    return None


def declared(table, entry):
    """The entry's pivot as {"column", "value"}, or None - none declared, or one `refusal` refuses."""
    pivot = entry.get("pivot")
    return None if pivot is None or refusal(table, entry) else {"column": pivot["column"], "value": pivot["value"]}


class Pivot:
    """One table's pivot as declared: `column`, `value`, `keys` (the row's - the table's keys less `column`)."""

    def __init__(self, table_name, column, value, keys):
        self.table_name, self.column, self.value, self.keys = table_name, column, value, keys


def of(table_name, **asked):
    """The table's pivot, or the read refused by name - a pivot not declared or not readable, or an argument it does
    not take (`NOT_TAKEN`, given in `asked`)."""
    from chain import cell_layer
    from database import crud

    entry = crud.TABLE_CONFIG.get(table_name) or {}
    if entry.get("pivot") is None:
        raise HTTPException(status_code=422, detail="'%s' declares no pivot - add \"pivot\": {\"column\", \"value\"} "
                                                    "to its table declaration" % table_name)
    refused = refusal(table_name, entry)
    if refused:
        raise HTTPException(status_code=422, detail="%s: %s" % refused)
    given = [name for name in NOT_TAKEN if asked.get(name)]
    if given:
        raise HTTPException(status_code=422, detail="a pivot read takes skip, limit, q, filters and order_by - not %s"
                                                    % ", ".join(given))
    column = entry["pivot"]["column"]
    return Pivot(table_name, column, entry["pivot"]["value"],
                 [key for key in cell_layer.entry_key_columns(entry) if key != column])


def split_filters(filters, pivot):
    """`?filters=` -> (the key columns' and the item column's filters as `?filters=` text, {item: its filter}) - the
    item column's narrows the long rows, so the items, their count and the groups follow it. Anything else is refused
    by name; text that is not JSON goes on as it is, to the grid filter's own refusal."""
    import json

    try:
        asked = json.loads(filters) if filters else {}
    except ValueError:
        return filters, {}
    if not isinstance(asked, dict):
        return filters, {}
    keys, items = {}, {}
    for name, spec in asked.items():
        item = item_of(name, pivot)
        if item is None:
            keys[name] = spec
        else:
            items[item] = spec
    return (json.dumps(keys) if keys else None), items


def item_of(name, pivot):
    """The item `name` filters (`item:<item>`), or None for a key column or the item column - the names a pivot read
    takes, its filters' and its value lists' (`grid_read.column_values`) one judgment; anything else refused by name."""
    if name.startswith(ITEM_PREFIX):
        return name[len(ITEM_PREFIX):]
    if name in pivot.keys or name == pivot.column:
        return None
    if name == pivot.value:
        raise HTTPException(status_code=422, detail=(
            "'%s' fills the pivot's cells - filter it per item inside the pivot as %s<item>" % (name, ITEM_PREFIX)))
    raise HTTPException(status_code=422, detail=(
        "'%s' is not a key column (%s) or the item column (%s) of the pivot - filter an item column as %s<item>"
        % (name, ", ".join(pivot.keys), pivot.column, ITEM_PREFIX)))


def index_names(table_name, order_by, filters):
    """A slow pivot read's sort and filter names as the columns an automatic index serves - an item's is `value`."""
    import json

    from database import crud

    value = ((crud.TABLE_CONFIG.get(table_name) or {}).get("pivot") or {}).get("value")

    def named(name):
        return value if isinstance(name, str) and name.startswith(ITEM_PREFIX) else name

    try:
        asked = json.loads(filters) if filters else None
    except ValueError:
        asked = None
    if isinstance(asked, dict):
        filters = json.dumps({named(name): spec for name, spec in asked.items()})
    return named(order_by), filters


class _SameKeyPart(ColumnElement):
    """`a` is `b`, an absent part the same as an absent part (10-24: «a,빈값 a,빈값 같은거로 처리»)."""
    type = Boolean()
    inherit_cache = True
    _traverse_internals = [("a", InternalTraversal.dp_clauseelement), ("b", InternalTraversal.dp_clauseelement)]

    def __init__(self, a, b):
        self.a, self.b = a, b


@compiles(_SameKeyPart)
def _same_key_part(part, compiler, **kw):
    return compiler.process(part.a.is_not_distinct_from(part.b), **kw)


@compiles(_SameKeyPart, "postgresql")
def _same_key_part_on_postgresql(part, compiler, **kw):
    # IS NOT DISTINCT FROM takes neither an index nor a hash or merge join - every group re-read the table (A 11-05,
    # 10M rows: over 60 s); an array's = holds NULL equal to NULL and hashes (B, box throwaway DB: 400k rows 0.3 s)
    return "ARRAY[%s] = ARRAY[%s]" % (compiler.process(part.a, **kw), compiler.process(part.b, **kw))


def _same_keys(one, other, pivot):
    """`one`'s row has `other`'s keys - NULL is NULL (a key part may be absent). `other`: a model, or a subquery's
    columns (`.c`)."""
    return and_(*(_SameKeyPart(getattr(one, key), getattr(other, key)) for key in pivot.keys))


def group_rows(db, model, pivot):
    """(an alias of the table, the query of its rows with `model`'s row's keys) - what a search of a key group reads."""
    held = aliased(model)
    return held, db.query(held).filter(_same_keys(held, model, pivot))


def narrow(query, model, pivot, items):
    """The long rows of the key groups whose items pass `items`: each item's filter an EXISTS of that item's row with
    the grid filter's own condition on `value`; a filter that takes the blank cell («blank», or a set holding null -
    `_takes_blank`) takes a group with no such row with a value too."""
    from column_filter import get_column_filter_condition

    for item, spec in items.items():
        held = aliased(model)
        met = get_column_filter_condition(held, pivot.value, spec)
        if met is None:
            continue
        found = exists().where(_same_keys(held, model, pivot), getattr(held, pivot.column) == item, met)
        if _takes_blank(spec):
            valued = aliased(model)
            found = or_(found, ~exists().where(
                _same_keys(valued, model, pivot), getattr(valued, pivot.column) == item,
                get_column_filter_condition(valued, pivot.value, {"type": "notBlank"})))
        query = query.filter(found)
    return query


def _takes_blank(spec):
    """An item filter that takes the blank cell - «blank», or a set holding null (A ea92380da, lead 11-05): in a pivot a
    group without that item's row shows the same blank cell."""
    if not isinstance(spec, dict) or "operator" in spec:
        return False
    return spec.get("type") == "blank" or (spec.get("filterType") == "set" and None in (spec.get("values") or ()))


def groups(query, model, pivot):
    """One row per key group of `narrow`'s rows - what a pivot read counts and pages."""
    keys = [getattr(model, key) for key in pivot.keys]
    return query.with_entities(*keys).group_by(*keys)


def order(groups, model, pivot, order_by, order_desc):
    """`groups` (`groups`' query) in order: a key column, or one item's value - a group without it last either way -
    then the keys. An item's value is one LEFT JOIN to that item's rows, not a read per group (B 11-05: 400k rows
    405 s -> 1.5 s, box throwaway DB)."""
    keys = [getattr(model, key) for key in pivot.keys]
    if order_by in (None, "", "row_id"):
        return groups.order_by(*keys)
    if order_by in pivot.keys:
        first = getattr(model, order_by)
        return groups.order_by(first.desc() if order_desc else first.asc(), *keys)
    if order_by.startswith(ITEM_PREFIX):
        held = aliased(model)
        cells = (select(*(getattr(held, key) for key in pivot.keys), getattr(held, pivot.value).label("value"))
                 .where(getattr(held, pivot.column) == order_by[len(ITEM_PREFIX):]).subquery())
        cell = func.min(cells.c.value)
        return (groups.outerjoin(cells, _same_keys(model, cells.c, pivot))
                .order_by((cell.desc() if order_desc else cell.asc()).nulls_last(), *keys))
    raise HTTPException(status_code=422, detail=("cannot sort a pivot by '%s' - sort by a key column (%s) or an item "
                                                 "column as %s<item>" % (order_by, ", ".join(pivot.keys), ITEM_PREFIX)))


def item_names(query, model, pivot, most):
    """(the first `most` items of the narrowed rows, how many more) - one DISTINCT, and a count only past `most`."""
    from database import crud

    column = getattr(model, pivot.column)
    found = [row[0] for row in query.with_entities(column).filter(column.isnot(None)).distinct()
             .order_by(column).limit(most + 1).all()]
    more = 0
    if len(found) > most:
        found = found[:most]
        more = query.with_entities(func.count(func.distinct(column))).order_by(None).scalar() - most
    return [crud.comparison_text_value(item) for item in found], more


def rows_of(query, model, pivot, page):
    """The long rows of these key groups (`page`: key tuples) - by IN, and by each key part's absence where one is
    absent."""
    keys = [getattr(model, key) for key in pivot.keys]
    whole = [group for group in page if None not in group]
    absent = [and_(*(key.is_(None) if part is None else key == part for key, part in zip(keys, group)))
              for group in page if None in group]
    found = ([(keys[0].in_([group[0] for group in whole]) if len(keys) == 1 else tuple_(*keys).in_(whole))]
             if whole else [])
    return query.filter(or_(*(found + absent))) if found or absent else None


def fold(pivot, page, raw_rows, merged, items):
    """The page's key groups in `page`'s order, each {key: value, ..., "cells": {item: {"value", "row_id"}}} - the
    value as the grid shows it (`merged`, the layer merge of `raw_rows`), an item not in `items` left out."""
    from database import crud

    shown = set(items)
    at = {group: {"cells": {}} for group in page}
    for row, said in zip(raw_rows, merged):
        group = tuple(getattr(row, key) for key in pivot.keys)
        out = at.get(group)
        if out is None:
            continue
        cells = said.get("data") or {}
        for key in pivot.keys:
            out.setdefault(key, (cells.get(key) or {}).get("value"))
        item = crud.comparison_text_value(getattr(row, pivot.column))
        if item in shown:
            out["cells"][item] = {"value": (cells.get(pivot.value) or {}).get("value"), "row_id": said.get("row_id")}
    return [at[group] for group in page]
