# -*- coding: utf-8 -*-
"""A person's named markings (owner 11-06 Tables, lead 11-07 S-mark ㄱ'): the rows of one table a person picked,
kept on the server under a handle the server makes, so the walk's seeds (`trace_router.reach`) and the grid's page
(`/tables/{t}/data?marking=`) read the same values and no URL carries them.

One row a marking - (owner, id) - its table, column, the values (jsonb) and a revision that moves on every save. View
state, not a table's edit: written only through `POST /markings` (READ on the marked table), with no audit and no
outbox; the screen deletes it (`DELETE /markings/{id}`), nothing sweeps it. Not a ledger source."""
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import column_filter
from admin import access
from database import crud, models
from database.database import get_db

router = APIRouter(tags=["markings"], route_class=access.TableRoute)


def _owner(user):
    """The key's owner: the signed-in name, "" when nobody is (sign-in off, a worker, a direct call's sentinel)."""
    return user if isinstance(user, str) else ""


def read(db, marking_id, user):
    """(table, column, values, rev) of `user`'s marking `marking_id` - THE reader the walk and the grid both call. Not
    theirs or gone: 404; a table they may not read: 403."""
    user = user if isinstance(user, str) else None
    held = db.get(models.Marking, (_owner(user), str(marking_id)))
    if held is None:
        raise HTTPException(status_code=404, detail={"reason": "marking_unknown",
                                                     "message": "no marking %s of yours" % marking_id})
    if not access.may(user, held.table_name, access.READ):
        access.refuse(user, held.table_name, access.READ)
    return held.table_name, held.column_name, list(held.marked or []), held.rev


def as_reach(db, asked, user):
    """A reach body that names a `marking` - the table, column and values it holds in their places; with `values` (or
    a table or column) too, refused: the seeds would be said twice."""
    twice = [name for name in ("table", "column", "values") if name in asked]
    if twice:
        raise HTTPException(status_code=422, detail={
            "reason": "seeds_defined_twice", "argument": "reach",
            "message": "reach takes a marking or {table, column, values}, not both - %s said too" % ", ".join(twice)})
    table, column, values, rev = read(db, asked["marking"], user)
    return {**{k: v for k, v in asked.items() if k != "marking"}, "table": table, "column": column,
            "values": values}, {"id": str(asked["marking"]), "rev": rev}


def as_filters(db, table, marking_id, filters, user):
    """The grid's `filters` with `user`'s marking `marking_id` on its column (the grid's set filter) - a marking of
    another table, or a column the filters already narrow, refused by name."""
    marked_table, column, values, _rev = read(db, marking_id, user)
    if marked_table != table:
        raise HTTPException(status_code=422, detail={
            "reason": "marking_of_another_table",
            "message": "marking %s holds rows of %s, not %s" % (marking_id, marked_table, table)})
    said = json.loads(filters) if filters else {}
    if column in said:
        raise HTTPException(status_code=422, detail={
            "reason": "column_filtered_twice",
            "message": "%s is narrowed by the filters and by marking %s - drop one" % (column, marking_id)})
    said[column] = {"filterType": column_filter.SET, "values": values}
    return json.dumps(said)


@router.post("/markings")
def save_marking(request: Request, body: dict = Body(...), db: Session = Depends(get_db)):
    """Keep a marking: {table, column, values: [...]} -> {id, rev}; with `id`, that marking of yours overwritten."""
    user = access.person(request)
    table, column, values = body.get("table"), body.get("column"), body.get("values")
    if not isinstance(table, str) or not isinstance(column, str) or not isinstance(values, list):
        raise HTTPException(status_code=422, detail={"reason": "marking_not_spelled",
                                                     "message": "a marking is {table, column, values: [...]} "
                                                                "and, to overwrite one, its id"})
    if table not in crud.TABLE_CONFIG:
        raise HTTPException(status_code=404, detail={"reason": "table_unknown", "message": "no table %s" % table})
    if not access.may(user, table, access.READ):
        access.refuse(user, table, access.READ)
    marking_id = str(body.get("id") or uuid.uuid4().hex)
    held = db.get(models.Marking, (_owner(user), marking_id))
    if held is None and body.get("id"):
        raise HTTPException(status_code=404, detail={"reason": "marking_unknown",
                                                     "message": "no marking %s of yours" % marking_id})
    if held is None:
        held = models.Marking(owner=_owner(user), id=marking_id, rev=0)
        db.add(held)
    held.table_name, held.column_name, held.marked = table, column, list(values)
    held.rev, held.touched_at = held.rev + 1, datetime.now(timezone.utc)
    db.commit()
    return {"id": marking_id, "rev": held.rev}


@router.delete("/markings/{marking_id}")
def drop_marking(marking_id: str, request: Request, db: Session = Depends(get_db)):
    """The screen removes a marking of yours - nothing else does."""
    gone = db.query(models.Marking).filter(models.Marking.owner == _owner(access.person(request)),
                                           models.Marking.id == marking_id).delete()
    db.commit()
    return {"id": marking_id, "deleted": bool(gone)}
