"""What a table's cells look like (owner 11-06, lead L2): colour rules and hand paint - rows of the shipped look table
(`grid_order.LOOK_TABLE`), beside the places. A rule (look_axis `rule`, look_key its id, position its order) gives a cell
its role when `rule_when` (the expression language; [value] the cell's value) holds and the cell's writer is its
`written_by` - each blank = any - on `rule_columns` (a JSON list; blank = every column). A paint (look_axis `paint`,
look_key «<row_id>/<column>») gives one cell its role by hand. A blank role is no look: a paint wiped, a rule taken off.
The screen judges a cell (client2/src/grid_look.js lookOf); this reads a page's looks."""
import json

from grid_order import _looks

RULE, PAINT = "rule", "paint"


def paint_key(row_id, column):
    """A paint's look_key - the row's id, then the column (a row id holds no «/»)."""
    return "%s/%s" % (row_id, column)


def _columns(text):
    """A rule's columns - a JSON list of names; blank or not a list = every column (None)."""
    try:
        names = json.loads(text) if text else None
    except ValueError:
        return None
    if not isinstance(names, list) or not names:
        return None
    return [str(name) for name in names]


def read(db, table_name, rows):
    """The looks of a page of `rows` (dicts with row_id and data, `fetch_and_merge_metadata`'s): {"rules": [in order],
    "paints": {paint_key: {"role", "row_id"}}} - None when the table has neither. A rule that asks who wrote a cell has
    each cell of its columns given `written_by` (`crud.writer_kind`) - only then are the layers' names read."""
    look = _looks()
    if look is None:
        return None
    found = db.query(look.row_id, look.look_axis, look.look_key, look.position, look.role, look.rule_when,
                     look.rule_columns, look.written_by).filter(
        look.look_table == table_name, look.look_axis.in_((RULE, PAINT)), look.role.isnot(None)).all()
    if not found:
        return None
    ids = {row.get("row_id") for row in rows}
    rules, paints = [], {}
    for row_id, axis, key, position, role, when, columns, written_by in found:
        if axis == RULE:
            rules.append({"id": key, "row_id": row_id, "position": position or key, "role": role, "when": when,
                          "columns": _columns(columns), "written_by": written_by})
        elif key.split("/", 1)[0] in ids:
            paints[key] = {"role": role, "row_id": row_id}
    rules.sort(key=lambda rule: (rule["position"], rule["id"]))
    asking = [rule["columns"] for rule in rules if rule["written_by"]]
    if asking:
        _writers(db, table_name, rows, None if None in asking else {name for names in asking for name in names})
    return {"rules": rules, "paints": paints}


def _writers(db, table_name, rows, columns):
    """Each cell of `columns` (None = all) gets `written_by` - its winning layer's writer. The page read names only a
    person's or a merge's layer (`priority_source`); any other winner is ranked here from the layers' names and
    times, by the ranking the value was chosen by (`crud.compute_priority_value`)."""
    from database import crud, models

    ids = [row["row_id"] for row in rows if row.get("row_id") is not None]
    if not ids:
        return
    query = db.query(models.CellSource.row_id, models.CellSource.column_name, models.CellSource.source_name,
                     models.CellSource.ingested_at).filter(models.CellSource.table_name == table_name,
                                                           models.CellSource.row_id.in_(ids))
    if columns is not None:
        query = query.filter(models.CellSource.column_name.in_(sorted(columns)))
    layers, ranks = {}, {}   # ranks: the declared rank of each name, asked once for the page
    for row_id, column, name, at in query.all():
        layers.setdefault((row_id, column), {})[name] = at
    for row in rows:
        for column, cell in (row.get("data") or {}).items():
            if (columns is not None and column not in columns) or not isinstance(cell, dict) or "priority_source" not in cell:
                continue
            source, said = cell.get("priority_source"), layers.get((row.get("row_id"), column))
            if source is None and said:
                _, source = crud.compute_priority_value({name: {} for name in said}, cell.get("manual_priority_source"),
                                                        table_name, ingested_at_by_source=said, ranks=ranks)
            cell["written_by"] = crud.writer_kind(source)
