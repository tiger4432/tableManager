# -*- coding: utf-8 -*-
"""`derive: {kind: "ask"}` - a group's rows asked of the language model, the answer written as rows of a table.

One body for every «AI fills a table from rows» declaration (lead 10-27: modeling structure, step mapping, item text
- each a declaration, never a kind of its own). Every table, column and word comes from the declaration:

    input    {group_by: [column, ...], order_by: column, text: [column, ...], window: N, overlap: K}
    output   {carry: {output column: input column}, cells: [column, ...], line: column, item: column}
    items    {table, step: {column, drop_leading}, item: column}       - lines under each matching row
    reuse    {key: [column | {column, drop_leading}, ...], within: {cell, table, column, carry: {its column: input}}}
    common   {cell, table, column, none, about}   - `cell` must be one of that column's values, else the word `none`;
             `about` another column of that table, shown beside each value
    prompts  {common: text, memo: {table, key, text}, memory: {scope: [column, ...], limit: N}}
    memory   {table, columns: {purpose, key, cell, ai, right, memo, who, when}}   - a person's corrections

A group (the `group_by` values of a row handed) is read whole in `order_by` order. Without `window` it is one text;
with it, its rows are cut `window` at a time with `overlap` rows each side as context, and only the windows holding a
row handed are asked (lead 10-27 ㄴ). A row whose `reuse` key an earlier answer already holds takes that answer and is
not asked - unless a reused `within.cell` value is not among this group's `within` values (lead 10-27 ㄱ). The rows are
written through the chain's write: a person's cell (user layer) is not overwritten when the rule runs again, and rows
the answer no longer gives go to the write's gone seat, scoped to the rows asked.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger("Chain")

ASK_MAPPER = "declared:ask"
ANSWER_KEY = "rows"

PROMPT = """<<common>>
<<memo>>
<<memory>>
Answer one JSON object: {"texts": [{"id": <the text's id>, "rows": [<row>, ...]}, ...]} - one item for each text
below, in any order. A row is an object with exactly these keys: <<cells>>. A value you cannot tell is null.
<<choices>>
<<texts>>"""
CONTEXT_MARK = "(context only - do not answer this line)"
#: the parts of a memory row - each a column the declaration names (`memory.columns`)
MEMORY_ROLES = ("purpose", "key", "cell", "ai", "right", "memo", "who", "when")
MEMORY_HEADING = "Past corrections - a person fixed these answers of yours; answer the same place the same way:"


def _spec(rule):
    return (rule or {}).get("params") or {}


def skeleton_node():
    """The form of `derive.ask` - every cell a name the operator writes (the report's node shapes)."""
    import chain_bindings

    def leaf(hint="free"):
        return {"kind": "leaf", "hint": hint}

    def record(*keys):
        return {"kind": "record", "fields": [{"key": k, "required": False, "node": leaf()} for k in keys]}

    def columns():
        return chain_bindings.list_node("column", leaf())

    def dropped():
        return {"kind": "record", "fields": [{"key": "column", "required": True, "node": leaf()},
                                             {"key": "drop_leading", "required": False, "node": leaf("number")}]}

    def mapping():
        return {"kind": "map", "keyed_by": "name", "member": "column", "of": leaf()}

    return {"kind": "record", "fields": [
        {"key": "input", "required": True, "node": {"kind": "record", "fields": [
            {"key": "group_by", "required": True, "node": columns()},
            {"key": "order_by", "required": True, "node": leaf()},
            {"key": "text", "required": True, "node": columns()},
            {"key": "window", "required": False, "node": leaf("number")},
            {"key": "overlap", "required": False, "node": leaf("number")}]}},
        {"key": "output", "required": True, "node": {"kind": "record", "fields": [
            {"key": "carry", "required": False, "node": mapping()},
            {"key": "cells", "required": True, "node": columns()},
            {"key": "line", "required": False, "node": leaf()},
            {"key": "item", "required": False, "node": leaf()}]}},
        {"key": "items", "required": False, "node": {"kind": "record", "fields": [
            {"key": "table", "required": True, "node": leaf()},
            {"key": "step", "required": True, "node": dropped()},
            {"key": "item", "required": True, "node": leaf()}]}},
        {"key": "reuse", "required": False, "node": {"kind": "record", "fields": [
            {"key": "key", "required": True, "node": chain_bindings.list_node("part", dropped())},
            {"key": "within", "required": False, "node": {"kind": "record", "fields": [
                {"key": k, "required": False, "node": leaf()} for k in ("cell", "table", "column")] + [
                {"key": "carry", "required": False, "node": mapping()}]}}]}},
        {"key": "common", "required": False, "node": record("cell", "table", "column", "none", "about")},
        {"key": "prompts", "required": False, "node": {"kind": "record", "fields": [
            {"key": "common", "required": False, "node": leaf()},
            {"key": "memo", "required": False, "node": record("table", "key", "text")},
            memory_nodes()[1]]}},
        memory_nodes()[0]]}


def memory_nodes():
    """The form of `memory` and of `prompts.memory` - one shape for every kind that reads a person's corrections
    (an ask rule; a report reads them too, `report_shape.skeleton_node`)."""
    import chain_bindings

    leaf = {"kind": "leaf", "hint": "free"}
    return ({"key": "memory", "required": False, "node": {"kind": "record", "fields": [
                {"key": "table", "required": True, "node": leaf},
                {"key": "columns", "required": True, "node": {"kind": "record", "fields": [
                    {"key": role, "required": False, "node": leaf} for role in MEMORY_ROLES]}}]}},
            {"key": "memory", "required": False, "node": {"kind": "record", "fields": [
                {"key": "scope", "required": False, "node": chain_bindings.list_node("column", leaf)},
                {"key": "limit", "required": False, "node": {"kind": "leaf", "hint": "number"}}]}})


def written_columns(rule) -> list:
    """The output columns an ask rule writes - its carried keys, its line and item, then its cells; its memory half
    the memory table's columns but the person's memo."""
    from chain import rule_shape

    if (rule or {}).get(rule_shape.COMPANION_CELL):
        named = (_spec(rule).get("memory") or {}).get("columns") or {}
        return [named[role] for role in MEMORY_ROLES if role != "memo" and named.get(role)]
    out = _spec(rule).get("output") or {}
    return list(dict.fromkeys([*(out.get("carry") or {}), *[out[k] for k in ("line", "item") if out.get(k)],
                               *(out.get("cells") or ())]))


def dropped(value, part):
    """A value as a part names it: `{column, drop_leading}` takes that many characters off the front (owner 10-27: a
    measured step carries the product's two-character prefix) - the one place a prefix is taken off. None when blank."""
    from database import crud

    if crud.is_blank_value(value):
        return None
    n = int((part or {}).get("drop_leading") or 0) if isinstance(part, dict) else 0
    return str(value)[n:]


def _column(part):
    return part["column"] if isinstance(part, dict) else part


def _model(table):
    from database import models

    model = models.DYNAMIC_TABLES.get(str(table or ""))
    if model is None:
        raise ValueError("table %r has no model in this process" % (table,))
    return model


def _where(query, model, values):
    for column, value in values.items():
        column = getattr(model, column)
        query = query.filter(column == value) if value is not None else query.filter(column.is_(None))
    return query


def _groups(db, table, spec, row_ids):
    """{group values: ([row, ...], {order value of a row handed})} - each group a row handed belongs to, read whole
    in `order_by` order."""
    from database import crud

    put = spec.get("input") or {}
    by = list(put.get("group_by") or ())
    model = _model(table)
    handed = db.query(*(getattr(model, c) for c in by + [put["order_by"]])).filter(
        model.row_id.in_(list(row_ids))).all()
    wanted = {}
    for row in handed:
        g = tuple(None if crud.is_blank_value(v) else str(v) for v in row[:len(by)])
        if not all(v is None for v in g):
            wanted.setdefault(g, set()).add(None if row[-1] is None else str(row[-1]))
    columns = by + [put["order_by"]] + list(put.get("text") or ())
    columns += [_column(p) for p in ((spec.get("reuse") or {}).get("key") or ()) if _column(p) not in columns]
    out = {}
    for g in sorted(wanted, key=lambda g: tuple("" if v is None else v for v in g)):
        query = _where(db.query(*(getattr(model, c) for c in columns)), model, dict(zip(by, g)))
        out[g] = ([dict(zip(columns, row)) for row in query.order_by(getattr(model, put["order_by"])).all()], wanted[g])
    return out


def _windows(rows, handed, spec):
    """[(start, owned rows, context before, context after)] - the windows to ask: the group whole without `window`,
    else the cuts holding a row handed (lead 10-27 ㄴ)."""
    put = spec.get("input") or {}
    size, overlap = int(put.get("window") or 0), int(put.get("overlap") or 0)
    if not size:
        return [(None, rows, [], [])]
    order = put["order_by"]
    out = []
    for at in range(0, len(rows), size):
        owned = rows[at:at + size]
        if any(str(row.get(order)) in handed for row in owned):
            out.append((str(owned[0].get(order)), owned, rows[max(0, at - overlap):at],
                        rows[at + size:at + size + overlap]))
    return out


def _items(db, spec, orders):
    """{order value: [item id, ...]} - the item table's rows whose step, its prefix dropped, is a line's order value."""
    items = spec.get("items") or {}
    if not items.get("table"):
        return {}
    model = _model(items["table"])
    out = {}
    for step, item in db.query(getattr(model, items["step"]["column"]), getattr(model, items["item"])).all():
        at = dropped(step, items["step"])
        if at in orders and item is not None:
            out.setdefault(at, []).append(str(item))
    return {k: sorted(set(v)) for k, v in out.items()}


def _line(row, spec, items, context=False):
    put = spec.get("input") or {}
    cols = [put["order_by"]] + list(put.get("text") or ())
    text = " | ".join("" if row.get(c) is None else str(row.get(c)) for c in cols)
    if context:
        return "%s  %s" % (text, CONTEXT_MARK)
    return "\n".join([text] + ["  item %s" % i for i in items.get(str(row.get(put["order_by"])), ())])


def _text(rows, spec, items=None, before=(), after=()):
    items = items or {}
    return "\n".join([_line(r, spec, items, True) for r in before] + [_line(r, spec, items) for r in rows]
                     + [_line(r, spec, items, True) for r in after])


def _reuse_key(row, spec):
    parts = (spec.get("reuse") or {}).get("key") or ()
    key = tuple(dropped(row.get(_column(p)), p) for p in parts)
    return key if parts and not all(v is None for v in key) else None


def _answers_held(db, rule, spec):
    """{reuse key: [answer cells, ...]} - what earlier answers wrote, read off the output table and keyed by the
    input row each answered (its group + line), so a row of the same key in another group takes it."""
    out_spec = spec.get("output") or {}
    put = spec.get("input") or {}
    if not (spec.get("reuse") or {}).get("key") or not out_spec.get("line"):
        return {}
    target, source = _model(rule.get("target_table")), _model(rule.get("trigger_table"))
    carry = out_spec.get("carry") or {}
    kept = [c for c in out_spec.get("cells") or ()] + ([out_spec["item"]] if out_spec.get("item") else [])
    reuse_cols = [_column(p) for p in spec["reuse"]["key"]]
    inputs = {}
    for row in db.query(*(getattr(source, c) for c in list(carry.values()) + [put["order_by"]] + reuse_cols)).all():
        n = len(carry)
        inputs[tuple(None if v is None else str(v) for v in row[:n + 1])] = dict(zip(reuse_cols, row[n + 1:]))
    held = {}
    for row in db.query(*(getattr(target, c) for c in list(carry) + [out_spec["line"]] + kept)).all():
        n = len(carry)
        source_row = inputs.get(tuple(None if v is None else str(v) for v in row[:n + 1]))
        key = _reuse_key(source_row or {}, spec)
        if key is not None:
            held.setdefault(key, {}).setdefault(row[:n + 1], []).append(dict(zip(kept, row[n + 1:])))
    # one earlier group's answer per key - the first, by its group and line
    return {key: by[sorted(by, key=lambda k: tuple("" if v is None else str(v) for v in k))[0]]
            for key, by in held.items()}


def _within(db, spec, group):
    """The values a reused `within.cell` may take in this group (e.g. its structures), or None when not declared."""
    within = (spec.get("reuse") or {}).get("within") or {}
    if not within.get("cell"):
        return None
    model = _model(within["table"])
    query = _where(db.query(getattr(model, within["column"])), model,
                   {own: group.get(src) for own, src in (within.get("carry") or {}).items()})
    return {str(v) for (v,) in query.all() if v is not None}


def _memo(db, spec, group):
    memo = (spec.get("prompts") or {}).get("memo") or {}
    if not memo.get("table"):
        return ""
    model = _model(memo["table"])
    found = db.query(getattr(model, memo["text"])).filter(getattr(model, memo["key"]) == group[0]).all()
    return "\n".join(str(v) for (v,) in found if v is not None)


def _choices(db, spec):
    common = spec.get("common") or {}
    if not common.get("cell"):
        return None, ""
    model = _model(common["table"])
    said = {}
    for value, about in db.query(getattr(model, common["column"]), getattr(model, common.get("about") or common["column"])):
        if value is not None:
            said.setdefault(str(value), set()).add(str(about) if common.get("about") and about is not None else None)
    values = sorted(said)
    shown = [v if said[v] == {None} else "%s (%s)" % (v, "; ".join(sorted(a for a in said[v] if a))) for v in values]
    return set(values), "%s is one of: %s - or %s when none fits.%s\n" % (
        common["cell"], json.dumps(shown, ensure_ascii=False), json.dumps(common.get("none")),
        " Answer the value alone, without the words in brackets." if common.get("about") else "")


def _key_of(table, row):
    """A row's business key as the output table's write spells it - `crud.compose_business_key`, the one spelling."""
    from database import crud

    entry = crud.TABLE_CONFIG.get(table) or {}
    columns = list(entry.get("composite_key_source") or [entry.get("business_key")])
    return crud.compose_business_key(table, [row.get(c) for c in columns], columns)


def _gone(db, rule, carried, answered, lines=None):
    """The group's rows in the output table whose key this answer no longer gives -> `gone` items owned by this rule:
    the write's gone seat takes this rule's cells and leaves a person's row (owner 10-28 «남김», the seat is B's).
    `lines`: only the rows of these line values - a window asked speaks for its own lines alone."""
    from chain import rule_shape
    from database import crud

    model = _model(rule.get("target_table"))
    query = _where(db.query(model.business_key_val), model, carried)
    line = (_spec(rule).get("output") or {}).get("line")
    if lines is not None and line:
        query = query.filter(getattr(model, line).in_(sorted(lines)))
    return [{"business_key_val": key, "updates": {}, "source_name": crud.CHAIN_SOURCE, "gone": True,
             "own": [rule_shape.declaration_of(rule)]} for (key,) in query.all() if key not in answered]


def _situation(row):
    return json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)


def _shown(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)


def remember(db, rule, row_ids):
    """The memory half: the output rows handed -> a memory row for each AI cell a person corrected, and `gone` for
    the memory rows of those output rows no correction holds any more (a person put the AI's value back, or their
    layer went). A person's value equal to the AI's corrects nothing. The judgement is `cell_layer.person_cells`.
    The AI's cells: an ask's `output.cells`, a report's text slots its `results` names."""
    from chain import cell_layer, report_shape, rule_shape
    from database import crud

    spec = _spec(rule)
    named = (spec.get("memory") or {}).get("columns") or {}
    out_spec = spec.get("output") or {}
    table, asker = rule.get("trigger_table"), str(rule.get(rule_shape.COMPANION_CELL) or "")
    model = _model(table)
    where = sorted(cell_layer.key_columns(table))                # the situation: the output row's key
    rows = {str(r[0]): dict(zip(where, r[1:])) for r in db.query(model.row_id, *(getattr(model, c) for c in where))
            .filter(model.row_id.in_([str(i) for i in row_ids or ()])).all()}
    texts = set(report_shape.text_slots(spec))
    cells = set(out_spec.get("cells") or ()) | {column for cell, column in report_shape.result_cells(spec)
                                                if cell in texts}
    updates, said = [], set()
    for (row_id, column), layers in sorted(cell_layer.person_cells(db, table, list(rows)).items()):
        person = [l for n, l in layers.items() if crud.layer_writer(n) == crud.USER_SOURCE]
        ai = [l for n, l in layers.items() if crud.layer_writer(n) == crud.CHAIN_SOURCE and l.get("updated_by") == asker]
        if column not in cells or row_id not in rows or not person or not ai:
            continue
        mine = max(person, key=lambda l: str(l.get("ingested_at")))
        if _shown(mine["value"]) == _shown(ai[0]["value"]):
            continue
        written = {named.get("purpose"): asker, named.get("key"): _situation(rows[row_id]), named.get("cell"): column,
                   named.get("ai"): _shown(ai[0]["value"]), named.get("right"): _shown(mine["value"]),
                   named.get("who"): mine.get("updated_by"), named.get("when"): str(mine.get("ingested_at"))}
        written = {k: v for k, v in written.items() if k}
        said.add(_key_of(rule.get("target_table"), written))
        updates.append({"source_name": crud.CHAIN_SOURCE, "updated_by": asker, "updates": written})
    memory = _model(rule.get("target_table"))
    held = db.query(memory.business_key_val).filter(
        getattr(memory, named["purpose"]) == asker,
        getattr(memory, named["key"]).in_(sorted({_situation(r) for r in rows.values()}))).all()
    updates += [{"business_key_val": key, "updates": {}, "source_name": crud.CHAIN_SOURCE, "gone": True,
                 "own": [rule_shape.declaration_of(rule)]} for (key,) in held if key not in said]
    return {"updates": updates, "refusal": None, "calls": 0}


def memory_lines(db, spec, purpose, situation):
    """The «past corrections» lines of a prompt: this purpose's memory rows whose `prompts.memory.scope` values are
    this text's, newest first, `limit` of them (default 5). The one reader - an ask prompt and a report prompt call it."""
    memory, reading = spec.get("memory") or {}, (spec.get("prompts") or {}).get("memory")
    named = memory.get("columns") or {}
    if not memory.get("table") or not isinstance(reading, dict) or not purpose:
        return ""
    model = _model(memory["table"])
    roles = [r for r in ("key", "cell", "ai", "right", "memo", "when") if named.get(r)]
    found = [dict(zip(roles, row)) for row in db.query(*(getattr(model, named[r]) for r in roles))
             .filter(getattr(model, named["purpose"]) == purpose).all()]
    scope = list(reading.get("scope") or ())
    picked = [m for m in found if all(str(json.loads(m.get("key") or "{}").get(c)) == str(situation.get(c))
                                      for c in scope)]
    picked.sort(key=lambda m: str(m.get("when") or ""), reverse=True)
    lines = ["- %s %s: you said %s; correct: %s%s" % (m.get("key"), m.get("cell"), m.get("ai"), m.get("right"),
                                                       " - note: %s" % m["memo"] if m.get("memo") else "")
             for m in picked[:int(reading.get("limit") or 5)]]
    return "\n".join([MEMORY_HEADING] + lines) if lines else ""


def prompt(db, spec, request, choices_line, purpose=None):
    """The prompt of one request [(id, text)] - also what a Test run shows. `purpose`: whose corrections it carries."""
    from database import crud

    memos = [m for m in (_memo(db, spec, json.loads(ident)) for ident, _t in request) if m]
    by = list((spec.get("input") or {}).get("group_by") or ())
    carry = (spec.get("output") or {}).get("carry") or {}
    remembered = [memory_lines(db, spec, purpose, {out: group.get(src) for out, src in carry.items()})
                  for group in (dict(zip(by, json.loads(ident))) for ident, _t in request)] if purpose else []
    common = (spec.get("prompts") or {}).get("common")
    out_spec = spec.get("output") or {}
    keys = [out_spec[k] for k in ("line", "item") if out_spec.get(k)] + list(out_spec.get("cells") or ())
    return (PROMPT
            .replace("<<common>>", "" if crud.is_blank_value(common) else str(common))
            .replace("<<memo>>", "\n".join(memos))
            .replace("<<memory>>", "\n".join(dict.fromkeys(m for m in remembered if m)))
            .replace("<<cells>>", ", ".join(json.dumps(c) for c in keys))
            .replace("<<choices>>", choices_line)
            .replace("<<texts>>", "\n\n".join("[%s]\n%s" % pair for pair in request)))


def answer(db, rule, row_ids):
    """The rows handed -> {"updates": [a row of the output table each, and gone items], "refusal", "calls"}."""
    from database import crud
    from utils import llm

    from chain import rule_shape

    if (rule or {}).get(rule_shape.COMPANION_CELL):
        return remember(db, rule, row_ids)
    spec = _spec(rule)
    name = str((rule or {}).get("name") or "")
    put, out_spec = spec.get("input") or {}, spec.get("output") or {}
    groups = _groups(db, (rule or {}).get("trigger_table"), spec, row_ids)
    if not groups:
        return {"updates": [], "refusal": "no row of a group reached this rule"}
    allowed, choices_line = _choices(db, spec)
    common = spec.get("common") or {}
    by, order, line_col, item_col = list(put.get("group_by") or ()), put["order_by"], out_spec.get("line"), \
        out_spec.get("item")
    cells = list(out_spec.get("cells") or ())
    held = _answers_held(db, rule, spec)
    key_columns = set((crud.TABLE_CONFIG.get(rule.get("target_table")) or {}).get("composite_key_source") or ())
    texts, plan, updates = [], {}, []
    for g, (rows, handed) in groups.items():
        group = dict(zip(by, g))
        carried = {out: group.get(src) for out, src in (out_spec.get("carry") or {}).items()}
        within = _within(db, spec, group)
        items = _items(db, spec, {str(r.get(order)) for r in rows})
        for start, owned, before, after in _windows(rows, handed, spec):
            ask, reused = [], []
            for row in owned:
                taken = held.get(_reuse_key(row, spec)) if held else None
                mine = items.get(str(row.get(order)), [])
                # an earlier answer's item rows are reused only for this line's own items; an item of this line it does
                # not hold sends the line to the model (another product's step carries other items - owner 10-28)
                taken = [t for t in taken or () if not (item_col and t.get(item_col)) or str(t[item_col]) in mine]
                held_items = {str(t[item_col]) for t in taken if item_col and t.get(item_col)}
                if taken and not set(mine) - held_items and (
                        within is None or all(t.get(spec["reuse"]["within"]["cell"]) is None or
                                              str(t.get(spec["reuse"]["within"]["cell"])) in within for t in taken)):
                    reused += [dict(t, **{line_col: str(row.get(order))}) for t in taken]
                else:
                    ask.append(row)
            ident = json.dumps(list(g) + ([start] if start is not None else []), ensure_ascii=False)
            plan[ident] = (carried, {str(r.get(order)) for r in owned} if line_col else None, reused)
            if ask:
                texts.append((ident, _text(ask, spec, items, before, after)))

    def read(_text_of, answered_items):
        out = []
        for item in answered_items:
            if not isinstance(item, dict):
                continue
            row = {c: None if crud.is_blank_value(item.get(c)) else item.get(c)
                   for c in [c for c in (line_col, item_col) if c] + cells}
            if allowed is not None and row.get(common["cell"]) is not None and str(row[common["cell"]]) not in allowed:
                row[common["cell"]] = common.get("none")
            out.append(row)
        if not out:
            raise llm.LlmRefused("the answer has no row")
        return out

    got, why, asked = llm.ask_batch(texts, lambda request: prompt(db, spec, request, choices_line, rule_shape.declaration_of(rule)), read, ANSWER_KEY,
                                    llm.settings()["batch_chars"], logger) if texts else ({}, {}, 0)
    for ident, (carried, lines, reused) in plan.items():
        if ident in why:
            continue                                            # a refused text says nothing is gone
        answered = set()
        for row in list(got.get(ident, ())) + reused:
            if lines is not None and str(row.get(line_col)) not in lines:
                continue                                        # a context line or a line not of this window
            # a key column stays in the row though blank (a step row has no item): a blank part among filled ones is a
            # part (73f5c5959), a key column the row does not carry is no key - the key gate refuses it
            written = {c: v for c, v in {**carried, **row}.items() if v is not None or c in key_columns}
            answered.add(_key_of(rule.get("target_table"), written))
            updates.append({"source_name": crud.CHAIN_SOURCE, "updated_by": name, "updates": written})
        updates.extend(_gone(db, rule, carried, answered, lines))
    from chain.rule_run import RULE_LOG_TAG
    logger.info("[%s] %s: asked %d text(s) in %d call(s), %d window(s) reused whole - %d row(s), %d refused",
                RULE_LOG_TAG, name, len(texts), asked, len(plan) - len(texts), len(updates), len(why))
    size = dict(texts)
    # which group and how long its text was, so the operator sees «which product and why» (lead 10-27)
    refusal = "; ".join("%s (%d chars): %s" % (ident, len(size.get(ident, "")), said)
                        for ident, said in why.items()) or None
    return {"updates": updates, "refusal": refusal, "calls": asked}
