# -*- coding: utf-8 -*-
"""총괄 3a262cc76 — 대조 한 줄 -> 걷기가 순위 매긴 후보 행들 (파생 행).

A product mapper in the owner's shape: a module in `mappers`, found by `discover`, named in a
declaration by module and function (`derive.mapper: {mapper_module, mapper_function}`) and
offered by the chain form like the owner's. Tracked by exception (.gitignore) - it is a fixed
function no declaration builds.

🔴 THE RANKING IS THE WALK ROUTE'S. `contrast_walk` calls `ledger.trace_router.evidence_subgraph`
- the function behind GET /api/ledger/subgraph - with the run's own arguments, so a stored factor
row and what the route answers for the same arguments are one computation. Nothing here ranks.
🔴 `until` BINDS THE WALK: atoms after it are not read, so a replay writes the same rows. A run
without one is refused by name rather than walked unbound.
⚠️ ONLY `contrast_walk` IS PUBLIC. The chain form lists every public function of two or more
arguments in this package as a mapper (`mapper_sdk.mapper_candidates`), so helpers stay `_`.
⚠️ THE ROUTE MODULE IS IMPORTED WHEN A RUN IS WALKED, NOT HERE: `discover` imports this file in
every process at start, and nothing it pulls in at import time should be a router.
🔴 THE RUN ROW SAYS IT WAS COMPUTED (총괄 2dd93d4a9 1): the same call writes back to the run
row - computed_at, candidates, and the two facts of the whole walk (contrast, complete), which
the factor rows no longer repeat. A run never walked has all four empty; one that found nothing
has computed_at and candidates 0.
"""
from __future__ import annotations

import inspect
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("Mappers.ContrastWalk")

#: Run cells that hold a JSON list.
LIST_CELLS = ("positive", "negative", "follow")
#: Run cells passed to the walk route as they are (blank -> the route's own default).
NUMBER_CELLS = ("hops", "node_limit", "edge_limit", "backbone_hops", "seed_limit")
TEXT_CELLS = ("direction", "seed_type", "world")


def _route():
    from ledger import trace_router

    return trace_router.evidence_subgraph


def _route_default(name):
    """The route's own default for one argument - one author, the route's signature."""
    default = inspect.signature(_route()).parameters[name].default
    return getattr(default, "default", default)


def _blank(value) -> bool:
    from database import crud

    return crud.is_blank_value(value)


def _walk_arguments(row) -> tuple:
    """The run row -> (keyword arguments for the walk route, refusal or None)."""
    args = {}
    for cell in LIST_CELLS:
        raw = getattr(row, cell, None)
        if _blank(raw):
            args[cell] = []
            continue
        try:
            value = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            return None, "%s is not a JSON list: %r" % (cell, raw)
        if not isinstance(value, list):
            return None, "%s is not a JSON list: %r" % (cell, raw)
        args[cell] = [str(item) for item in value if not _blank(item)]
    for cell in NUMBER_CELLS:
        raw = getattr(row, cell, None)
        args[cell] = _route_default(cell) if _blank(raw) else int(float(raw))
    for cell in TEXT_CELLS:
        raw = getattr(row, cell, None)
        args[cell] = _route_default(cell) if _blank(raw) else str(raw).strip()
    raw = getattr(row, "include_superseded", None)
    if _blank(raw):
        args["include_superseded"] = _route_default("include_superseded")
    else:
        from database import crud

        try:
            args["include_superseded"] = crud.boolean_text_read(raw, "include_superseded")
        except ValueError as refused:
            return None, str(refused)
    for cell in ("since", "until"):
        raw = getattr(row, cell, None)
        args[cell] = None if _blank(raw) else (raw.isoformat() if hasattr(raw, "isoformat")
                                               else str(raw))
    if args["until"] is None:
        return None, "until is empty - the walk would read what arrives after this run"
    return args, None


def _walk(db, args):
    """The walk route, called with every argument spelled out (a direct call leaves FastAPI's
    `Query` sentinels in anything left out)."""
    positive = args["positive"]
    return _route()(
        node_id=positive[0] if positive else None,
        positive=positive[1:] or None, negative=args["negative"] or None,
        hops=args["hops"], direction=args["direction"],
        since=args["since"], until=args["until"],
        node_limit=args["node_limit"], edge_limit=args["edge_limit"],
        follow=args["follow"] or None, backbone_hops=args["backbone_hops"],
        collect=None, seed_type=args["seed_type"], seed_limit=args["seed_limit"],
        group_by=None, measure=None, response_format="json", db=db,
        include_superseded=args["include_superseded"], world=args["world"])


def contrast_walk(db, payload, rule=None):
    """The run rows handed in -> what the factor table should hold, as update items stamped
    with the run row they came from (`origin_row_id`, as the join's body stamps)."""
    from fastapi import HTTPException

    from chain.dynamic_mappers import _row_ids
    from database import crud, models, schemas

    trigger = str((rule or {}).get("trigger_table") or "")
    model = models.DYNAMIC_TABLES.get(trigger)
    row_ids = _row_ids(payload)
    if model is None or not row_ids:
        return {"updates": [], "refusal": "no run rows reached this mapper"}
    name = str((rule or {}).get("name") or "")
    updates, refusals, runs = [], [], []
    for row in db.query(model).filter(model.row_id.in_(list(row_ids))).all():
        run_id = getattr(row, "run_id", None)
        if _blank(run_id):
            refusals.append("%s: run_id is empty" % row.row_id)
            continue
        args, why = _walk_arguments(row)
        if why:
            refusals.append("%s: %s" % (run_id, why))
            continue
        try:
            answer = _walk(db, args)
        except HTTPException as refused:
            detail = refused.detail if isinstance(refused.detail, dict) else {}
            refusals.append("%s: %s" % (run_id, detail.get("message") or refused.detail))
            continue
        block = answer.get("propagation") or {}
        ranked = block.get("ranked") or ()
        runs.append(schemas.GeneralUpdateItem(
            row_id=row.row_id,
            updates={"run_id": run_id, "computed_at": datetime.now(timezone.utc),
                     "candidates": len(ranked), "contrast": block.get("contrast"),
                     "complete": crud.boolean_text_value(block.get("complete"))},
            origin_row_id=row.row_id, source_name=crud.CHAIN_SOURCE, updated_by=name))
        for item in ranked:
            reach = list(item.get("reach") or [None, None])
            reachable = list(item.get("reachable") or [None, None])
            updates.append(schemas.GeneralUpdateItem(
                # ⚠️ `node_id`, not the response's `id`: the write door never writes a column
                #    named `id` (crud's system columns) - measured, every candidate of a run
                #    collapsed into one row.
                updates={"run_id": run_id, "node_id": item.get("id"),
                         "type": item.get("type"), "label": item.get("label"),
                         "reach_positive": reach[0], "reach_negative": reach[1],
                         "reachable_positive": reachable[0],
                         "reachable_negative": reachable[1],
                         "rank": item.get("rank"),
                         # the column is text; a bool reads back `1` on one database and is
                         # refused on another
                         "top": crud.boolean_text_value(item.get("top")),
                         "tied": crud.boolean_text_value(item.get("tied")),
                         "incomparable": crud.boolean_text_value(item.get("incomparable")),
                         "evidence": json.dumps(item.get("evidence") or [],
                                                ensure_ascii=False)},
                origin_row_id=row.row_id, source_name=crud.CHAIN_SOURCE, updated_by=name))
    for why in refusals:
        logger.warning("[ContrastWalk] %s: %s - nothing written for it", name or "contrast", why)
    return {"updates": updates,
            "batches": [{"target_table": trigger, "updates": runs}] if runs else [],
            "refusal": "; ".join(refusals) if refusals and not runs else None}
