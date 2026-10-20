# -*- coding: utf-8 -*-
"""e38466810 (owner 10-20 「표 -> 체인 LLM -> 걷기 -> 표」): the agent walk, one hop per chain step.

A product mapper like `contrast_walk`: tracked by exception (.gitignore), named by module and function in two
sample rules that ping-pong (총괄 10-21 ㄱ - a rule is never woken by its own declaration's writes, owner 09-28):
    walk_request -> walk_log     `agent_walk` on a request row: the LLM picks the next node from the cards its
                                 position shows, and a hop row is written (or the end row)
    walk_log -> walk_request     `agent_walk` on log rows: the request's position, step and state follow them -
                                 which wakes the first rule again. No LLM call.
A hop takes two chain depths, so the hops a walk may take are `hop_cap` - the one place that says it. The last hop
and the end row are written by one call, so no row of a walk is past the chain's depth limit.

⚠️ ONLY `agent_walk` AND `meaning_draft` ARE PUBLIC - the chain form lists every public function of two or more
arguments here as a mapper (`mapper_sdk.mapper_candidates`).
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger("Mappers.AgentWalk")

UNWALKED, ON_NODE, STUCK, END = "unwalked", "on_node", "stuck", "end"
HOP, END_ROW = "hop", "end"


def _blank(value) -> bool:
    from database import crud

    return crud.is_blank_value(value)


def _number(value):
    return None if _blank(value) else int(float(value))


def hop_cap(hop_budget):
    """-> (the hops a walk may take, why it stops there): a hop is two chain depths (request -> log -> request), so
    `max_chain_depth // 2`, and the request's `hop_budget` when smaller. The one place this is said (총괄 10-21)."""
    import event_constants
    from chain import ingestion_worker

    depth = event_constants.max_chain_depth(ingestion_worker._RULES_DOCUMENT)
    by_depth = depth // 2
    if hop_budget is not None and hop_budget < by_depth:
        return hop_budget, "hop budget %d" % hop_budget
    return by_depth, "chain depth %d → %d hops" % (depth, by_depth)


def _rows(db, table, **where):
    from database import models

    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        return None
    query = db.query(model)
    for column, value in where.items():
        query = query.filter(getattr(model, column) == value)
    return query.all()


def _as_dict(row, columns):
    return {column: getattr(row, column, None) for column in columns}


def _path(db, request_id):
    """The request's log rows, by step - {step, kind, position, chosen, reason, cards}."""
    import product_tables

    out = []
    for row in _rows(db, product_tables.WALK_LOG_TABLE, request_id=request_id) or ():
        item = _as_dict(row, ("step", "kind", "position", "chosen", "reason", "answer"))
        item["step"] = _number(item["step"])
        try:
            item["cards"] = json.loads(row.cards) if not _blank(row.cards) else []
        except ValueError:
            item["cards"] = []
        out.append(item)
    return sorted(out, key=lambda item: item["step"] or 0)


def _ask(text, ids, end):
    """One LLM answer read back -> (decision, None) or (None, why it was refused). A hop answer goes to a listed
    node or answers; an end answer answers."""
    from utils import llm

    try:
        said = llm.ask_json(text)
    except llm.LlmRefused as refused:
        return None, "the language model call was refused: %s" % refused
    if not end and not _blank(said.get("go")):
        if str(said["go"]).strip() not in ids:
            return None, "'%s' is not one of the listed node identifiers" % said["go"]
        return {"go": ids[str(said["go"]).strip()], "chosen": str(said["go"]).strip(),
                "reason": str(said.get("reason") or "")}, None
    if _blank(said.get("answer")):
        return None, ("the answer has neither 'answer' nor 'go'" if not end else "the answer has no 'answer'")
    evidence = said.get("evidence") or []
    if not isinstance(evidence, list):
        return None, "'evidence' is not a list"
    unknown = [str(each) for each in evidence if str(each).strip() not in ids]
    if unknown:
        return None, "evidence %s is not among the listed node identifiers" % ", ".join(unknown)
    return {"answer": str(said["answer"]), "evidence": [ids[str(each).strip()] for each in evidence],
            "rule_draft": str(said.get("rule_draft") or ""), "reason": str(said.get("reason") or "")}, None


def _decide(sight, recipe, state, end):
    """The cards for `state`, asked; a refused answer is asked once more with why. -> (context, decision, refusal,
    calls made)."""
    from utils import text_links

    context = text_links.walk_context(sight, recipe, state, end=end)
    decision, why = _ask(context["text"], context["ids"], end)
    if decision is not None:
        return context, decision, None, 1
    again = context["text"] + "\nYour last answer was refused: %s. Answer again." % why
    decision, why_again = _ask(again, context["ids"], end)
    return context, decision, (None if decision is not None else why_again), 2


def _one_hop(db, position, limit):
    from utils import text_links

    return text_links._walked([position], (), 1, fanout_limit=limit)


def _edge_limit(recipe, state):
    for row in recipe:
        if str(row.get("state")) == state and str(row.get("card")) == "edges" and not _blank(row.get("card_limit")):
            return int(float(row["card_limit"]))
    return None


def _log_item(request_id, step, kind, **cells):
    from database import crud, schemas

    return schemas.GeneralUpdateItem(updates={"request_id": request_id, "step": step, "kind": kind, **cells},
                                     source_name=crud.CHAIN_SOURCE)


def _end_item(request_id, step, why, sight, recipe, end_state_ok=True):
    """The end row: the end state's cards asked for the answer (one call), or - with no recipe for it or a refused
    answer - the end row saying why. -> (item, calls made)."""
    from ledger import walk_cards

    calls, cells = 0, {"reason": why}
    if end_state_ok:
        try:
            context, decision, refused, calls = _decide(sight, recipe, END, True)
        except walk_cards.UnknownCard as unknown:
            cells["reason"] = "%s; %s" % (why, unknown)
        else:
            cells["recipe_print"] = context["print"]
            cells["cards"] = json.dumps(context["cards"], ensure_ascii=False, default=str)
            if decision is None:
                cells["reason"] = "%s; the end answer was refused twice: %s" % (why, refused)
            else:
                cells.update(answer=decision["answer"], evidence=json.dumps(decision["evidence"]),
                             rule_draft=decision["rule_draft"])
    return _log_item(request_id, step, END_ROW, **cells), calls


def _hop(db, request, recipe_rows):
    """One request row -> its next log row(s)."""
    import product_tables
    from ledger import trace_router, walk_cards

    request_id = request.request_id
    path = _path(db, request_id)
    if any(row["kind"] == END_ROW for row in path) or str(request.state or "") == END:
        return []
    hops = [row for row in path if row["kind"] == HOP]
    step = len(hops)
    cap, why_cap = hop_cap(_number(request.hop_budget))
    call_budget = _number(request.call_budget)
    calls_left = None if call_budget is None else call_budget - len(path)
    position = request.position if not _blank(request.position) else (
        request.start_node if not _blank(request.start_node) else None)
    recipe = [row for row in recipe_rows if str(row.get("recipe")) == str(request.recipe or "")]
    meanings_rows = [_as_dict(row, ("target_kind", "target_name", "meaning"))
                     for row in _rows(db, product_tables.MEANING_TABLE) or ()]
    sight = walk_cards.Sight(question=str(request.question or ""), declaration=trace_router._declaration(),
                             path=hops, meanings=meanings_rows, hops_left=cap - step, calls_left=calls_left, db=db)
    if not recipe:
        item, _calls = _end_item(request_id, step + 1, "recipe '%s' has no rows - write its rows in walk_recipe"
                                 % (request.recipe or ""), sight, recipe, end_state_ok=False)
        return [item]
    if step >= cap or (calls_left is not None and calls_left <= 1):
        item, _calls = _end_item(request_id, step + 1, why_cap if step >= cap else "call budget %d" % call_budget,
                                 sight, recipe)
        return [item]
    if position is None:
        state = UNWALKED
    else:
        sight.at = [position]
        sight.answer = _one_hop(db, position, _edge_limit(recipe, ON_NODE))
        walked = {row["position"] for row in hops} | {position}
        branches = walk_cards.edges(sight)["items"]
        state = ON_NODE if any(i not in walked for b in branches for i in b["sample"]) else STUCK
    try:
        context, decision, refused, calls = _decide(sight, recipe, state, False)
    except walk_cards.UnknownCard as unknown:
        item, _calls = _end_item(request_id, step + 1, str(unknown), sight, recipe, end_state_ok=False)
        return [item]
    cards = json.dumps(context["cards"], ensure_ascii=False, default=str)
    if decision is None:
        return [_log_item(request_id, step + 1, END_ROW, state=state, cards=cards, recipe_print=context["print"],
                          reason="the answer was refused twice: %s" % refused)]
    if "answer" in decision:
        return [_log_item(request_id, step + 1, END_ROW, state=state, cards=cards, recipe_print=context["print"],
                          answer=decision["answer"], evidence=json.dumps(decision["evidence"]),
                          rule_draft=decision["rule_draft"], reason=decision["reason"])]
    hop = _log_item(request_id, step + 1, HOP, position=decision["go"], state=state, cards=cards,
                    chosen=decision["chosen"], reason=decision["reason"], recipe_print=context["print"])
    calls_left = None if calls_left is None else calls_left - calls
    if step + 1 < cap and (calls_left is None or calls_left > 1):
        return [hop]
    # the last hop and the end row in one call: no row of the walk is past the chain's depth limit (총괄 10-21)
    sight.path = hops + [{"step": step + 1, "kind": HOP, "position": decision["go"], "chosen": decision["chosen"],
                          "reason": decision["reason"], "cards": context["cards"]}]
    sight.at, sight.answer, sight.hops_left, sight.calls_left = [decision["go"]], None, 0, calls_left
    end, _calls = _end_item(request_id, step + 2, why_cap if step + 1 >= cap else "call budget %d" % call_budget,
                            sight, recipe)
    return [hop, end]


def _recipe_rows(db):
    import product_tables

    return [_as_dict(row, ("recipe", "state", "card_order", "card", "card_limit", "argument", "instruction"))
            for row in _rows(db, product_tables.WALK_RECIPE_TABLE) or ()]


def _advance(db, rows):
    """Log rows -> their requests' position, step and state (the end row's step and «end» last)."""
    from database import crud, schemas

    latest = {}
    for row in sorted(rows, key=lambda r: (_number(r.step) or 0, r.kind == END_ROW)):
        if _blank(row.request_id):
            continue
        cells = {"request_id": row.request_id, "step": _number(row.step)}
        if row.kind == END_ROW:
            cells["state"] = END
        else:
            cells.update(position=row.position, state=ON_NODE)
        latest[row.request_id] = cells
    return [schemas.GeneralUpdateItem(updates=cells, source_name=crud.CHAIN_SOURCE) for cells in latest.values()]


def agent_walk(db, payload, rule=None):
    """The rows handed in -> the walk's next rows: request rows -> log rows (`_hop`); log rows -> their requests
    (`_advance`). Which by the rule's trigger table - the two sample rules' only difference."""
    import product_tables
    from chain.dynamic_mappers import _row_ids
    from database import models

    trigger = str((rule or {}).get("trigger_table") or "")
    model = models.DYNAMIC_TABLES.get(trigger)
    row_ids = _row_ids(payload)
    if model is None or not row_ids:
        return {"updates": [], "refusal": "no walk rows reached this mapper"}
    rows = db.query(model).filter(model.row_id.in_(list(row_ids))).all()
    if trigger == product_tables.WALK_LOG_TABLE:
        return {"updates": _advance(db, rows)}
    recipe = _recipe_rows(db)
    updates = []
    for request in rows:
        if _blank(request.request_id):
            logger.warning("[AgentWalk] %s: a request row with no request_id - nothing walked", request.row_id)
            continue
        updates.extend(_hop(db, request, recipe))
    return {"updates": updates}


MEANING_ASK = ('Write one short meaning for each name above - what the thing is, or what the relation says - in the'
               ' language of the names. Answer one JSON object: {"meanings": {"<kind>:<name>": "<meaning>", ...}}.')


def _meaning_lines(db, rows, declaration):
    """One line per name to draft: an entity's keys and first nodes, a predicate's subject and object types."""
    from declaration_names import bare_name
    from ledger import gaps, walk_cards

    entities = {bare_name(name): spec or {} for name, spec in ((declaration or {}).get("entities") or {}).items()}
    vocabulary = {bare_name(name): spec or {} for name, spec in gaps._vocabulary(declaration).items()}
    sight = walk_cards.Sight(db=db)
    lines = []
    for row in rows:
        kind, name = str(row.target_kind), str(row.target_name)
        if kind == "entity":
            found = walk_cards.key_values(sight, name, 3) or {}
            lines.append("%s:%s - keys %s; nodes %s" % (kind, name, list(entities.get(name, {}).get("keys") or []),
                                                        [node["keys"] for node in found.get("nodes") or ()]))
        else:
            spec = vocabulary.get(name, {})
            lines.append("%s:%s - from %s to %s (%s)" % (
                kind, name, [bare_name(s) for s in gaps._subjects(spec)],
                [bare_name(t) for t in gaps._targets(spec)], gaps._object_kind(spec)))
    return lines


def meaning_draft(db, payload, rule=None):
    """Meaning rows handed in whose meaning is blank and no person or draft has written -> the LLM's drafts, in its
    own layer (`crud.LLM_DRAFT_SOURCE`, below a person's). A person who emptied a meaning keeps it empty (S-243)."""
    import product_tables
    from chain.dynamic_mappers import _row_ids
    from database import crud, models, schemas
    from ledger import trace_router
    from utils import llm

    model = models.DYNAMIC_TABLES.get(product_tables.MEANING_TABLE)
    row_ids = _row_ids(payload)
    if model is None or not row_ids:
        return {"updates": [], "refusal": "no meaning rows reached this mapper"}
    rows = [row for row in db.query(model).filter(model.row_id.in_(list(row_ids))).all() if _blank(row.meaning)]
    layer = models.CellSource
    written = {row_id for (row_id,) in db.query(layer.row_id).filter(
        layer.table_name == product_tables.MEANING_TABLE, layer.column_name == "meaning",
        layer.row_id.in_([row.row_id for row in rows]),
        layer.source_name.in_([crud.USER_SOURCE, crud.LLM_DRAFT_SOURCE]))} if rows else set()
    rows = [row for row in rows if row.row_id not in written]
    if not rows:
        return {"updates": []}
    try:
        said = llm.ask_json("\n".join(_meaning_lines(db, rows, trace_router._declaration()) + [MEANING_ASK]))
    except llm.LlmRefused as refused:
        return {"updates": [], "refusal": "the language model call was refused: %s" % refused}
    drafts = said.get("meanings") if isinstance(said.get("meanings"), dict) else {}
    updates = []
    for row in rows:
        draft = drafts.get("%s:%s" % (row.target_kind, row.target_name))
        if not _blank(draft):
            updates.append(schemas.GeneralUpdateItem(
                updates={"target_kind": row.target_kind, "target_name": row.target_name, "meaning": str(draft)},
                source_name=crud.LLM_DRAFT_SOURCE, updated_by=str((rule or {}).get("name") or "")))
    if len(updates) < len(rows):
        logger.warning("[AgentWalk] meaning_draft: %d of %d name(s) came back without a draft", len(rows) - len(updates),
                       len(rows))
    return {"updates": updates}
