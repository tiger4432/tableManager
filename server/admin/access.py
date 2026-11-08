# -*- coding: utf-8 -*-
"""Who may read or edit a table (owner 11-06) - THE seat. Every door asks `may`; nothing else reads `access`.

A table declaration's cell, absent = the default:
    "access": {"read": {"allow": [...], "deny": [...]}, "edit": {"allow": [...], "deny": [...]}, "edit_by": "<column>"}
read   allow empty = everyone · allow listed = only those · deny always wins
edit   only those on edit.allow, and never without read · deny always wins · admins (auth_config admins) always
edit_by  a row of this table is an edit of the table its <column> names (sys_looks: look_table) - judged there
Sign-in off, or a caller that is not a signed-in person (a worker on its token): the answer is today's - yes.
Names only (owner 11-06 ①: groups are not kept); a group list would join `_names` below.
"""
from fastapi import HTTPException, Request
from starlette.requests import HTTPConnection

from admin import sso
from runtime.offloop_json import OffLoopJSONRoute

READ, EDIT = "read", "edit"
ACCESS_KEY = "access"
EDIT_BY_KEY = "edit_by"
#: A POST that only reads - judged as a read (the sources popup's batch query).
READ_POSTS = frozenset({"/tables/{table_name}/cells/sources/query"})
#: The names a route takes a table by, besides {table_name} in its path - a query or path argument of these names.
TABLE_ARGS = ("table_name", "table", "target_table", "map_table")
#: The door that knows each row it writes - an edit_by table's rows are judged there, row by row (`may(row=)`).
ROWS_DOOR = "/tables/{table_name}/data/updates"
#: The doors that delete rows - deleting a row edits it (lead 11-08), so an edit_by table's are judged there row by row
#: too (`may_delete`). Until then they answered the table's own cell (cb4310be8 «other edit doors on that table answer
#: its own cell») - widened for these two; the other edit doors still do.
DELETE_DOORS = ("/tables/{table_name}/rows/{row_id}", "/tables/{table_name}/rows/batch_delete")
DENIED = "%s may not %s the table %s - an administrator adds the name to access.%s.allow in table_config.json"
DENIED_BY = "%s is denied by access.%s.deny of %s - remove the name there"   # an allow would not lift a deny


def _cell(table):
    from database import crud
    return (crud.TABLE_CONFIG.get(table) or {}).get(ACCESS_KEY) or {}


def _names(user):
    """The names a list entry may match for this account - the signed-in name, case folded as sso reads a upn."""
    return {user.casefold()}


def _on(names, listed):
    return bool(names & {str(name).casefold() for name in (listed or ())})


def _judged(table, what, row):
    """The table an edit of `row` is judged on - the one it names when `table` declares edit_by, else `table`."""
    by = _cell(table).get(EDIT_BY_KEY)
    return str(row[by]) if what == EDIT and by and row is not None and row.get(by) else table


def _refused_on(user, table, what, row):
    """(table, read | edit, deny | allow) - the cell that refuses `user` this `what` (read | edit) on `table`, None
    when none does. `row` (its cells) - for a table that declares edit_by, an edit its own cell lets past (its read, its
    edit.deny) is judged on the table that row names; without the row the table's own cell answers."""
    if user is None or not sso.enabled() or sso.is_admin(user):
        return None
    cell = _cell(table)
    names = _names(user)
    read = cell.get(READ) or {}
    if _on(names, read.get("deny")):
        return table, READ, "deny"
    if read.get("allow") and not _on(names, read["allow"]):
        return table, READ, "allow"
    if what == READ:
        return None
    edit = cell.get(EDIT) or {}
    if _on(names, edit.get("deny")):
        return table, EDIT, "deny"
    judged = _judged(table, what, row)
    if judged != table:
        return _refused_on(user, judged, EDIT, None)
    return None if _on(names, edit.get("allow")) else (table, EDIT, "allow")


def may(user, table, what, row=None):
    """Whether `user` may `what` (read | edit) `table` - `_refused_on` names no table."""
    return _refused_on(user, table, what, row) is None


def person(connection: HTTPConnection):
    """The signed-in name on a request or socket, None when nobody is (sign-in off, a worker's token) - also a route's
    dependency, resolved in the API process (the walk's refusal sentence names its reader)."""
    return getattr(getattr(connection, "state", None), "sso_user", None)


def refuse(user, table, what, row=None):
    """The refusal - the cell that refused (`_refused_on`) and its next step: a deny's name removed, an allow's added."""
    at, cell, kind = _refused_on(user, table, what, row) or (table, what, "allow")
    raise HTTPException(status_code=403, detail=DENIED_BY % (user, cell, at) if kind == "deny" else
                        DENIED % (user, what, at, cell))


def may_delete(request, db, table, row_ids):
    """A delete door's judgment of an edit_by table's rows: each row an edit of the table its edit_by column names - a
    row not there, or its column blank, the table's own cell. Refused by name at the first row refused. Answers
    `edits_by_row` - read before the rows go, for the delete's message (lead 11-08) - None without edit_by."""
    edits = edits_by_row(db, table, row_ids)
    if edits is None:
        return None                                                    # `table_door` judged the table
    by, user = _cell(table)[EDIT_BY_KEY], person(request)
    for row_id in row_ids:
        row = {by: edits[row_id]} if row_id in edits else None        # the judged table reads as itself (`_judged`)
        if not may(user, table, EDIT, row=row):
            refuse(user, table, EDIT, row=row)
    return edits


def edits_by_row(db, table, row_ids):
    """{row_id: the table it is an edit of (`_judged`)} for the rows there - None when `table` declares no edit_by
    (nothing read). One read by row id, a statement per 900."""
    by = _cell(table).get(EDIT_BY_KEY)
    if not by:
        return None
    return {row_id: _judged(table, EDIT, {by: value}) for row_id, value in _edit_by_cells(db, table, by, row_ids).items()}


def edit_of_row(table, row):
    """The table `row` (a row object of `table`, in hand) is an edit of (`_judged`) - None when `table` declares no
    edit_by. No read: the seat that deletes a row writes this before it goes (lead 11-08 ③)."""
    by = _cell(table).get(EDIT_BY_KEY)
    return _judged(table, EDIT, {by: getattr(row, by, None)}) if by else None


def tables_in(table, edits, row_ids):
    """The tables `row_ids` are edits of, sorted, from a {row_id: table} map (`edits_by_row`, `edit_of_row`'s) - None
    when `table` declares no edit_by."""
    if edits is None or not _cell(table).get(EDIT_BY_KEY):
        return None
    return sorted({edits[row_id] for row_id in row_ids if row_id in edits})


def edits_of(db, table, rows):
    """The tables these written rows are edits of, sorted - None when `table` declares no edit_by (nothing read). By
    row id: a committed row is expired, and reading its cell would reload it one statement each."""
    if not _cell(table).get(EDIT_BY_KEY):
        return None                                                    # the rows are not even looked at
    from sqlalchemy import inspect

    ids = [inspect(row).identity[0] for row in rows]
    return tables_in(table, edits_by_row(db, table, ids), ids)


def _edit_by_cells(db, table, by, row_ids):
    """{row_id: its edit_by cell} for the rows there."""
    from database import models

    model = models.DYNAMIC_TABLES.get(table)
    ids, named = list(row_ids), {}
    for at in range(0, len(ids) if model is not None else 0, 900):     # under SQLite's 999 parameters
        named.update(db.query(model.row_id, getattr(model, by)).filter(model.row_id.in_(ids[at:at + 900])).all())
    return named


def table_door(request: Request):
    """The dependency every route that takes a table carries (`TableRoute`): each table it names, in its path or query.
    A table named only in a body is judged in its route (the test's BODY_TABLE_ROUTES)."""
    path = request.scope["route"].path
    what = READ if request.method in ("GET", "HEAD") or path in READ_POSTS else EDIT
    user = person(request)
    for arg in TABLE_ARGS:
        table = request.path_params.get(arg) or request.query_params.get(arg)
        if not table or (
                what == EDIT and path in (ROWS_DOOR, *DELETE_DOORS) and _cell(table).get(EDIT_BY_KEY)):
            continue                                                   # its door judges an edit_by table's rows
        if not may(user, table, what):
            refuse(user, table, what)


class TableRoute(OffLoopJSONRoute):
    """The app's route class: a route that takes a table (`takes_a_table`) carries `table_door` - a new one does too."""

    def __init__(self, path, endpoint, **kwargs):
        if takes_a_table(path, endpoint):
            from fastapi import Depends
            kwargs["dependencies"] = list(kwargs.get("dependencies") or []) + [Depends(table_door)]
        super().__init__(path, endpoint, **kwargs)


def takes_a_table(path, endpoint):
    """Whether a route names a table in its path or by an argument of a TABLE_ARGS name."""
    import inspect
    return "{table_name}" in path or bool(set(inspect.signature(endpoint).parameters) & set(TABLE_ARGS))


def hidden_tables(request: Request) -> tuple:
    """The tables this request's person may not read, sorted - () for sign-in off, a worker, an admin. The walk's
    dependency: resolved in the API process and handed to the walk's process with its other arguments."""
    user = person(request)
    if user is None or not sso.enabled() or sso.is_admin(user):
        return ()
    from database import crud
    return tuple(sorted(table for table in crud.TABLE_CONFIG if not may(user, table, READ)))


def may_read_all(user, tables):
    """Whether `user` may read every one of `tables` - None (never recorded) is an administrator's only."""
    if user is None or not sso.enabled() or sso.is_admin(user):
        return True
    return tables is not None and all(may(user, table, READ) for table in tables)


def tables_seen(user, tables):
    """The subset of `tables` this user may read - the content exits' filter (walk, lists, sockets)."""
    return {table for table in tables if may(user, table, READ)}

