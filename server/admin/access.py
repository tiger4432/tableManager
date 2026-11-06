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
DENIED = "%s may not %s the table %s - an administrator adds the name to access.%s.allow in table_config.json"


def _cell(table):
    from database import crud
    return (crud.TABLE_CONFIG.get(table) or {}).get(ACCESS_KEY) or {}


def _names(user):
    """The names a list entry may match for this account - the signed-in name, case folded as sso reads a upn."""
    return {user.casefold()}


def _on(names, listed):
    return bool(names & {str(name).casefold() for name in (listed or ())})


def may(user, table, what, row=None):
    """Whether `user` may `what` (read | edit) `table`. `row` (its cells) - for a table that declares edit_by, an edit
    is judged on the table that row names; without the row the table's own cell answers."""
    if user is None or not sso.enabled() or sso.is_admin(user):
        return True
    cell = _cell(table)
    if what == EDIT and cell.get(EDIT_BY_KEY) and row is not None and row.get(cell[EDIT_BY_KEY]):
        return may(user, str(row[cell[EDIT_BY_KEY]]), EDIT)
    names = _names(user)
    read = cell.get(READ) or {}
    if _on(names, read.get("deny")) or (read.get("allow") and not _on(names, read["allow"])):
        return False
    if what == READ:
        return True
    edit = cell.get(EDIT) or {}
    if _on(names, edit.get("deny")):
        return False
    return _on(names, edit.get("allow"))


def person(connection: HTTPConnection):
    """The signed-in name on a request or socket, None when nobody is (sign-in off, a worker's token) - also a route's
    dependency, resolved in the API process (the walk's refusal sentence names its reader)."""
    return getattr(getattr(connection, "state", None), "sso_user", None)


def refuse(user, table, what):
    raise HTTPException(status_code=403, detail=DENIED % (user, what, table, what))


def table_door(request: Request):
    """The dependency every route that takes a table carries (`TableRoute`): each table it names, in its path or query.
    A table named only in a body is judged in its route (the test's BODY_TABLE_ROUTES)."""
    path = request.scope["route"].path
    what = READ if request.method in ("GET", "HEAD") or path in READ_POSTS else EDIT
    user = person(request)
    for arg in TABLE_ARGS:
        table = request.path_params.get(arg) or request.query_params.get(arg)
        if not table or (
                what == EDIT and path == ROWS_DOOR and _cell(table).get(EDIT_BY_KEY)):
            continue                                                   # the rows door judges an edit_by table's rows
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

