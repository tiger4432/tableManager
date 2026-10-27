# -*- coding: utf-8 -*-
"""`derive: {kind: "ask"}` - a group's rows asked of the language model, the answer written as rows of a table.

One body for every «AI fills a table from rows» declaration (lead 10-27: modeling structure, step mapping, item text
- each a declaration, never a kind of its own). Every table, column and word comes from the declaration:

    input    {group_by: [column, ...], order_by: column, text: [column, ...]}      - the trigger table's rows
    output   {carry: {output column: input column}, cells: [column, ...]}         - a row per answered item
    common   {cell, table, column, none}   - `cell` must be one of that column's values, else the word `none`
    prompts  {common: text, memo: {table, key, text}}

A group (the `group_by` values of a row handed) is read whole in `order_by` order - one text, one line a row - and
asked through `llm.ask_batch` (key «rows»). The rows are written through the chain's write as every mapper's are: a
person's cell (user layer) is not overwritten when the rule runs again.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger("Chain")

ASK_MAPPER = "declared:ask"
ANSWER_KEY = "rows"

PROMPT = """<<common>>
<<memo>>
Answer one JSON object: {"texts": [{"id": <the text's id>, "rows": [<row>, ...]}, ...]} - one item for each text
below, in any order. A row is an object with exactly these keys: <<cells>>. A value you cannot tell is null.
<<choices>>
<<texts>>"""


def _spec(rule):
    return (rule or {}).get("params") or {}


def skeleton_node():
    """The form of `derive.ask` - every cell a name the operator writes (the report's node shapes)."""
    import chain_bindings

    def leaf():
        return {"kind": "leaf", "hint": "free"}

    def record(*keys):
        return {"kind": "record", "fields": [{"key": k, "required": False, "node": leaf()} for k in keys]}

    def columns():
        return chain_bindings.list_node("column", leaf())

    return {"kind": "record", "fields": [
        {"key": "input", "required": True, "node": {"kind": "record", "fields": [
            {"key": "group_by", "required": True, "node": columns()},
            {"key": "order_by", "required": True, "node": leaf()},
            {"key": "text", "required": True, "node": columns()}]}},
        {"key": "output", "required": True, "node": {"kind": "record", "fields": [
            {"key": "carry", "required": False, "node": {"kind": "map", "keyed_by": "name", "member": "column",
                                                         "of": leaf()}},
            {"key": "cells", "required": True, "node": columns()}]}},
        {"key": "common", "required": False, "node": record("cell", "table", "column", "none")},
        {"key": "prompts", "required": False, "node": {"kind": "record", "fields": [
            {"key": "common", "required": False, "node": leaf()},
            {"key": "memo", "required": False, "node": record("table", "key", "text")}]}}]}


def written_columns(rule) -> list:
    """The output columns an ask rule writes - its carried keys, then its cells (the chain keeps a mapper to them)."""
    out = _spec(rule).get("output") or {}
    return list(dict.fromkeys([*(out.get("carry") or {}), *(out.get("cells") or ())]))


def _model(table):
    from database import models

    model = models.DYNAMIC_TABLES.get(str(table or ""))
    if model is None:
        raise ValueError("table %r has no model in this process" % (table,))
    return model


def _groups(db, table, spec, row_ids):
    """{group values: [row, ...]} - each group a row handed belongs to, read whole in `order_by` order."""
    from database import crud

    put = spec.get("input") or {}
    by = list(put.get("group_by") or ())
    model = _model(table)
    handed = db.query(*(getattr(model, c) for c in by)).filter(model.row_id.in_(list(row_ids))).distinct().all()
    wanted = {tuple(None if crud.is_blank_value(v) else str(v) for v in row) for row in handed}
    wanted = {g for g in wanted if not all(v is None for v in g)}
    columns = by + [put["order_by"]] + list(put.get("text") or ())
    out = {}
    for g in sorted(wanted, key=lambda g: tuple("" if v is None else v for v in g)):
        query = db.query(*(getattr(model, c) for c in columns))
        for column, value in zip(by, g):
            query = query.filter(getattr(model, column) == value) if value is not None else \
                query.filter(getattr(model, column).is_(None))
        out[g] = [dict(zip(columns, row)) for row in query.order_by(getattr(model, put["order_by"])).all()]
    return out


def _text(rows, spec):
    put = spec.get("input") or {}
    cols = list(put.get("text") or ())
    return "\n".join(" | ".join("" if row.get(c) is None else str(row.get(c)) for c in [put["order_by"]] + cols)
                     for row in rows)


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
    values = sorted({str(v) for (v,) in db.query(getattr(model, common["column"])).distinct().all() if v is not None})
    return set(values), "%s is one of: %s - or %s when none fits.\n" % (
        common["cell"], json.dumps(values, ensure_ascii=False), json.dumps(common.get("none")))


def _key_of(table, row):
    """A row's business key as the output table's write spells it - `crud.compose_business_key`, the one spelling."""
    from database import crud

    entry = crud.TABLE_CONFIG.get(table) or {}
    columns = list(entry.get("composite_key_source") or [entry.get("business_key")])
    return crud.compose_business_key(table, [row.get(c) for c in columns], columns)


def _gone(db, rule, carried, answered):
    """The group's rows in the output table whose key this answer no longer gives -> `gone` items owned by this rule:
    the write's gone seat takes this rule's cells and leaves a person's row (owner 10-28 «남김», the seat is B's)."""
    from chain import rule_shape
    from database import crud

    model = _model(rule.get("target_table"))
    query = db.query(model.business_key_val)
    for column, value in carried.items():
        column = getattr(model, column)
        query = query.filter(column == value) if value is not None else query.filter(column.is_(None))
    return [{"business_key_val": key, "updates": {}, "source_name": crud.CHAIN_SOURCE, "gone": True,
             "own": [rule_shape.declaration_of(rule)]} for (key,) in query.all() if key not in answered]


def prompt(db, spec, request, choices_line):
    """The prompt of one request [(id, text)] - also what a Test run shows."""
    from database import crud

    memos = [m for m in (_memo(db, spec, json.loads(ident)) for ident, _t in request) if m]
    common = (spec.get("prompts") or {}).get("common")
    return (PROMPT
            .replace("<<common>>", "" if crud.is_blank_value(common) else str(common))
            .replace("<<memo>>", "\n".join(memos))
            .replace("<<cells>>", ", ".join(json.dumps(c) for c in (spec.get("output") or {}).get("cells") or ()))
            .replace("<<choices>>", choices_line)
            .replace("<<texts>>", "\n\n".join("[%s]\n%s" % pair for pair in request)))


def answer(db, rule, row_ids):
    """The rows handed -> {"updates": [a row of the output table each], "refusal": ...} (a mapper's answer)."""
    from database import crud
    from utils import llm

    spec = _spec(rule)
    name = str((rule or {}).get("name") or "")
    groups = _groups(db, (rule or {}).get("trigger_table"), spec, row_ids)
    if not groups:
        return {"updates": [], "refusal": "no row of a group reached this rule"}
    allowed, choices_line = _choices(db, spec)
    out_spec = spec.get("output") or {}
    cells = list(out_spec.get("cells") or ())
    common = spec.get("common") or {}
    texts = [(json.dumps(list(g), ensure_ascii=False), _text(rows, spec)) for g, rows in groups.items()]

    def read(_text_of, items):
        rows = []
        for item in items:
            if not isinstance(item, dict):
                continue
            row = {c: None if crud.is_blank_value(item.get(c)) else item.get(c) for c in cells}
            if allowed is not None and row.get(common["cell"]) is not None and str(row[common["cell"]]) not in allowed:
                row[common["cell"]] = common.get("none")
            rows.append(row)
        if not rows:
            raise llm.LlmRefused("the answer has no row")
        return rows

    got, why, asked = llm.ask_batch(texts, lambda request: prompt(db, spec, request, choices_line), read, ANSWER_KEY,
                                    llm.settings()["batch_chars"], logger)
    updates = []
    for ident, rows in got.items():
        group = dict(zip((spec.get("input") or {}).get("group_by") or (), json.loads(ident)))
        carried = {out: group.get(src) for out, src in (out_spec.get("carry") or {}).items()}
        answered = set()
        for row in rows:
            written = {c: v for c, v in {**carried, **row}.items() if v is not None}
            answered.add(_key_of(rule.get("target_table"), written))
            updates.append({"source_name": crud.CHAIN_SOURCE, "updated_by": name, "updates": written})
        updates.extend(_gone(db, rule, carried, answered))      # a refused group says nothing is gone
    from chain.rule_run import RULE_LOG_TAG
    logger.info("[%s] %s: asked %d group(s) in %d call(s) - %d row(s), %d refused", RULE_LOG_TAG, name, len(texts),
                asked, len(updates), len(why))
    size = dict(texts)
    # which group and how long its text was, so the operator sees «which product and why» (lead 10-27)
    refusal = "; ".join("%s (%d chars): %s" % (ident, len(size.get(ident, "")), said)
                        for ident, said in why.items()) or None
    return {"updates": updates, "refusal": refusal, "calls": asked}
