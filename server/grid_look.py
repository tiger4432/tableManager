"""What a table's cells look like (owner 11-06, lead L2): colour rules and hand paint - rows of the shipped look table
(`grid_order.LOOK_TABLE`), beside the places. A rule (look_axis `rule`, look_key its id, position its order) gives a cell
its role when `rule_when` (the expression language; [value] the cell's value) holds and the cell's writer is its
`written_by` - each blank = any - on `rule_columns` (a JSON list; blank = every column), drawn as its `shape` (`FILL`,
`LINE`); a role is a design role's word or a picked colour «#rrggbb» (owner 11-09), carried as written. A paint
(look_axis `paint`, look_key «<row_id>/<column>») gives one cell its role by hand. A blank role is no look: a paint
wiped, a rule taken off. The rules every table has: the look table's declaration (`DECLARED`, the
lowest layer), then rows of look_table `EVERY`, then each table's own rows (`fold`). The screen judges a cell
(client2/src/grid_look.js lookOf); this reads a page's looks."""
import json

from grid_order import _looks

RULE, PAINT = "rule", "paint"
#: The look_table of a rule every table has (owner 11-08 1ㄱ) - a table's row of the same look_key covers it there.
EVERY = "*"
#: The look table declaration's cell of the rules every table has - each a row's cells with its look_key, under the
#: `EVERY` rows (owner 11-08 1ㄱ: shipped there, no row written at start; an administrator's change is an `EVERY` row).
DECLARED = "rules"
#: A rule's shape (owner 11-08 2ㄱ): FILL its role's tint behind the text (blank = FILL), LINE a left edge and the text
#: in its role's colour - drawn over a fill, so a person's cell still says so under another rule's colour.
FILL, LINE = "fill", "line"
#: The writers a page read's `priority_source` names without the layers - a cell it leaves unnamed is neither's.
NAMED_WRITERS = frozenset({"person", "merge"})


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


def _cells(position, role, when, columns, written_by, shape, row_id=None) -> dict:
    """A rule's cells as `fold` reads them - from a look row or the declaration (`DECLARED`)."""
    return {"row_id": row_id, "position": position, "role": role, "when": when, "columns": _columns(columns),
            "written_by": written_by, "shape": shape}


def _declared() -> dict:
    """{look_key: cells} - the look table declaration's `DECLARED` rules."""
    from database import crud
    from grid_order import LOOK_TABLE

    return {str(rule["look_key"]): _cells(rule.get("position"), rule.get("role"), rule.get("rule_when"),
                                          rule.get("rule_columns"), rule.get("written_by"), rule.get("shape"))
            for rule in (crud.TABLE_CONFIG.get(LOOK_TABLE) or {}).get(DECLARED) or () if rule.get("look_key")}


def fold(*layers) -> list:
    """The rules a table's cells are judged by, in position order. `layers` lowest first, each {look_key: its cells}: a
    key is its lowest layer's rule, every cell a higher layer writes covering it there, and a higher layer's blank role
    turns it off - kept with role None, `under` the role it turns off (the Colours tab's «On here»). `every`: the rule
    is a lower layer's (every table's). A key of the top layer alone is a rule only while its role is written."""
    out, top = {}, len(layers) - 1
    for depth, layer in enumerate(layers):
        for key, cells in layer.items():
            below = out.get(key)
            if below is None:
                if cells.get("role"):
                    out[key] = dict(cells, id=key, every=depth < top, under=None)
                continue
            covered = {cell: value for cell, value in cells.items()
                       if cell not in ("role", "row_id", "position") and value not in (None, "")}
            out[key] = dict(below, **covered, role=cells.get("role") or None,
                            under=below["role"] or below["under"])
    return sorted(out.values(), key=lambda rule: (rule["position"], rule["id"]))


def read(db, table_name, rows):
    """The looks of a page of `rows` (dicts with row_id and data, `fetch_and_merge_metadata`'s): {"rules": [in order],
    "paints": {paint_key: {"role", "row_id"}}} - None when the table has neither. A rule that asks who wrote a cell has
    each cell of its columns that one of the asked writers wrote given `written_by` (`crud.writer_kind`, `_writers`)."""
    look = _looks()
    if look is None:
        return None
    found = db.query(look.row_id, look.look_table, look.look_axis, look.look_key, look.position, look.role,
                     look.rule_when, look.rule_columns, look.written_by, look.shape).filter(
        look.look_table.in_((table_name, EVERY)), look.look_axis.in_((RULE, PAINT))).all()
    ids = {row.get("row_id") for row in rows}
    layers, paints = {EVERY: {}, table_name: {}}, {}
    for row_id, table, axis, key, position, role, when, columns, written_by, shape in found:
        if axis == RULE:
            layers[table][key] = _cells(position or key, role, when, columns, written_by, shape, row_id=row_id)
        elif table == table_name and role and key.split("/", 1)[0] in ids:
            paints[key] = {"role": role, "row_id": row_id}
    rules = [dict(rule, shape=rule["shape"] or FILL) for rule in fold(_declared(), layers[EVERY], layers[table_name])]
    if not rules and not paints:
        return None
    asking = [rule for rule in rules if rule["role"] and rule["written_by"]]
    if asking:
        columns = [rule["columns"] for rule in asking]
        _writers(db, table_name, rows, None if None in columns else {name for names in columns for name in names},
                 {rule["written_by"] for rule in asking})
    return {"rules": rules, "paints": paints}


def _writers(db, table_name, rows, columns, kinds):
    """A cell of `columns` (None = all) whose winning layer's writer is one of `kinds`, the writers the rules ask,
    says it in `written_by`; any other cell says none - no rule's writer is its (lead 11-09). The page read's
    `priority_source` names the winner when set (a person's or a merge's layer, a pinned one; every winner when the
    sources were read). A cell it leaves unnamed is ranked from the layers' names and times
    (`crud.compute_priority_value`) when `kinds` asks a writer beyond `NAMED_WRITERS`, and then only the cells holding
    a layer of a writer `kinds` asks - the winner is one of its layers (lead 11-09: the rules every table has ask a
    model, and every page read every layer of its cells - 0.22 s -> 0.99 s on a 1,000-row page of the box's dt_log)."""
    from database import crud, models

    ids = set()     # the rows of the cells the page read left unnamed
    for row in rows:
        for column, cell in (row.get("data") or {}).items():
            if (columns is None or column in columns) and isinstance(cell, dict) and "priority_source" in cell:
                if cell["priority_source"] is not None:
                    _said(cell, crud.writer_kind(cell["priority_source"]), kinds)
                elif row.get("row_id") is not None:
                    ids.add(row.get("row_id"))
    asked = set(kinds) - NAMED_WRITERS
    if not ids or not asked:
        return
    S = models.CellSource
    query = db.query(S.row_id, S.column_name).filter(S.table_name == table_name, S.row_id.in_(sorted(ids)),
                                                     crud.writer_kind_clause(S.source_name, kinds))
    if columns is not None:
        query = query.filter(S.column_name.in_(sorted(columns)))
    held = set(query.distinct().all())
    if not held:
        return
    layers, ranks = {}, {}   # ranks: the declared rank of each name, asked once for the page
    for row_id, column, name, at in db.query(S.row_id, S.column_name, S.source_name, S.ingested_at).filter(
            S.table_name == table_name, S.row_id.in_(sorted({row for row, _c in held})),
            S.column_name.in_(sorted({column for _r, column in held}))):
        if (row_id, column) in held:
            layers.setdefault((row_id, column), {})[name] = at
    by_id = {row.get("row_id"): row for row in rows}
    for (row_id, column), said in layers.items():
        cell = (by_id[row_id].get("data") or {}).get(column)
        if not isinstance(cell, dict) or "priority_source" not in cell or cell["priority_source"] is not None:
            continue
        _, source = crud.compute_priority_value({name: {} for name in said}, cell.get("manual_priority_source"),
                                                table_name, ingested_at_by_source=said, ranks=ranks)
        _said(cell, crud.writer_kind(source), kinds)


def _said(cell, writer, kinds):
    """`written_by` on `cell` when `writer` is one the rules ask."""
    if writer in kinds:
        cell["written_by"] = writer
