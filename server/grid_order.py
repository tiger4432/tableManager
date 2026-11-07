"""A table read in the order its rows were entered, and the places people dragged them to (owner 11-06, lead ①②④): a
table that declares `"order": "entered"` is read by `ENTERED` - each row, and in pivot view each key group and each
item, at its first row_id (uuid7, so arrival order - crud's row-id ordering contract) unless a row of `LOOK_TABLE`
gives it a place: `position`, a text between its neighbours' keys that the screen writes on a drag. The look row's key
is the thing's first row_id. A place is built of row-id characters and digits, and never parts from its neighbour at a
«-», so it sorts the same under any collation that orders uuid7 text by arrival."""
from fastapi import HTTPException
from sqlalchemy import func, select

#: The sort name the screen sends, and the declaration's word.
ENTERED = "entered"
#: The shipped table of the places people wrote (server/declarations/table_config.json).
LOOK_TABLE = "sys_looks"
ROW, GROUP, ITEM = "row", "group", "item"


def refusal(table, entry):
    """`(path, sentence)` when the entry's `order` is not one this product reads, else None (none declared included)."""
    order = entry.get("order")
    if order is None or order == ENTERED:
        return None
    return "tables.%s.order" % table, "order is \"%s\" - rows read in the order they were entered" % ENTERED


def declared(table, entry):
    """The entry's `order` as the screen reads it - `ENTERED`, or None."""
    return ENTERED if entry.get("order") == ENTERED and not refusal(table, entry) else None


def _looks():
    from database import models

    return models.DYNAMIC_TABLES.get(LOOK_TABLE)


def key(table_name, axis, first):
    """The order key of what `first` (its first row_id) is on `axis`: its dragged place, else `first`."""
    look = _looks()
    if look is None:
        return first
    place = (select(look.position).where(look.look_table == table_name, look.look_axis == axis,
                                         look.look_key == first)
             .limit(1).scalar_subquery())
    return func.coalesce(place, first)


def sort(table_model, table_name):
    """The ORDER BY expression of `ENTERED` over a table's rows - None for a relation without row_id."""
    row_id = getattr(table_model, "row_id", None)
    return None if row_id is None else key(table_name, ROW, row_id)


def row_keys(db, table_name, rows):
    """Each row dict of a page gets `order_key` - its place, else its row_id (what a drag reads its neighbours by)."""
    ids = [row["row_id"] for row in rows if row.get("row_id") is not None]
    look = _looks()
    placed = {}
    if ids and look is not None:
        placed = dict(db.query(look.look_key, look.position).filter(
            look.look_table == table_name, look.look_axis == ROW, look.look_key.in_(ids)).all())
    for row in rows:
        if row.get("row_id") is not None:
            row["order_key"] = placed.get(row["row_id"]) or row["row_id"]


def target_offset_filter(db, query, table_model, table_name, target_row_id):
    """The rows before `target_row_id` in `ENTERED` order - what a jump to that row counts."""
    from sqlalchemy import and_, or_

    expr = sort(table_model, table_name)
    if expr is None:
        raise HTTPException(status_code=422, detail="'%s' has no row_id to read in entered order" % table_name)
    at = db.query(expr).filter(table_model.row_id == target_row_id).scalar()
    return query.filter(or_(expr < at, and_(expr == at, table_model.row_id < target_row_id)))
