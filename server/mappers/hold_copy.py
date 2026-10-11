# -*- coding: utf-8 -*-
"""총괄 3211e9000 · 3ba1d1dd4 · 32bab7896 · cb3d3c1bf — 보류 포함 행 복사 (소유자 10-02 「df, db 받고 db 에서
df 키 조회해서 2개 이상이면 보류 아니면 합의」 · 「나 로」).

The owner's `copy_one_row` (RELEASE_LOG 10-01) with its columns as `params`, for a batch: one row
or many - a rule with `is_batch: true` hands the batch, one without hands one row, and both go
the same way as one frame. Each row's columns land under that row's own layer
`chain_ingestion (<row_id>)` with `origin_row_id`; one query per 1,000 keys counts, per key, the
distinct value sets of `columns` among the source rows of that key. Exactly one is AGREED; none
(every source row deleted) or two and more holds the row blank. The hold is one item per key in
the same updates (one commit), under the plain chain layer - its blank is a chain write. A row
that blank leaves with only the chain's keys goes after the write (총괄 5eee501eb - the chain's
write seat asks `cell_layer.shells`).

Two rules call it. On the source table it copies and holds; on the target table (trigger =
target, `source_table` named) it only recounts the hold - a source row deleted or moved to another key
(its layer is withdrawn either way, 총괄 b13de0353), or a person's edit.

🔴 THE KEYS ARE COMPARED WITH `=` WHERE THEY HAVE A VALUE: `IS NOT DISTINCT FROM` takes no
index, so on a table of a million rows every count was a full scan. A key holding a NULL is
compared NULL-safe, by itself.
⚠️ NOT `@mapper`: the decorator hands its author (df, db) and no rule, so `params` could not be
read. The raw function goes into the same registry with its `params`.
"""
from __future__ import annotations

NAME = "copy_rows_with_hold"
#: what each argument must be - a list written as text was read a letter at a time (총괄 67dffd619)
PARAMS = {"key_columns": list, "columns": list, "hold_column": str, "source_table": str}
AGREED = "agreed"


def copy_rows_with_hold(db, payloads, rule=None):
    import pandas as pd
    from database import crud
    from mapper_sdk import df_to_updates, payloads_to_df

    df = payloads_to_df(payloads)
    if df.empty:
        return {"updates": []}
    import chain_bindings

    params = rule["params"]
    keys, columns, hold = list(params["key_columns"]), list(params["columns"]), params["hold_column"]
    target = rule["target_table"]
    rows = df.astype(object).where(df.notna(), None).to_dict("records")
    holds_only = _holds_only(rule)
    source = params["source_table"] if holds_only else rule["trigger_table"]
    result = {"updates": []}
    if not holds_only:
        result = df_to_updates(df[list(dict.fromkeys(keys + columns))], target,
                               source_name=crud.CHAIN_SOURCE, updated_by=NAME)
        for item, row in zip(result["updates"], rows):
            item["source_name"] = crud.merged_layer_name(crud.CHAIN_SOURCE, row["row_id"])
            item["origin_row_id"] = row["row_id"]

    from chain.keyset_scan import DEFAULT_CHUNK_SIZE

    batch_keys = list(dict.fromkeys(tuple(row[key] for key in keys) for row in rows))
    claims = {}
    gates = {gate: rule.get(stamp) or () for gate, stamp in chain_bindings.SOURCE_GATE_KEYS.items()}
    for start in range(0, len(batch_keys), DEFAULT_CHUNK_SIZE):   # 10,000 keys overran the parser
        claims.update(_claims(db, source, keys, columns, batch_keys[start:start + DEFAULT_CHUNK_SIZE], gates))
    held = pd.DataFrame([{**dict(zip(keys, key)), hold: AGREED if claims.get(key) == 1 else ""}
                         for key in batch_keys])
    result["updates"] += df_to_updates(held, target, source_name=crud.CHAIN_SOURCE,
                                       updated_by=NAME)["updates"]
    return result


def _claims(db, source, keys, columns, batch_keys, gates=None) -> dict:
    """{asked key: distinct value sets of `columns` among `source`'s rows of that key}. A row the copy's
    row gates hold back is not a claim (`gates` {gate: columns} - 총괄 016a766af · 0117a0048), judged
    by `_gated` in this query.

    The asked keys join a VALUES list (총괄 043915ab0 ②: the row `IN` was an OR chain the planner
    answered with a scan of the whole table) - `=` for the keys with a value in every part, a second
    query NULL-safe for the keys holding a NULL. Each VALUES row carries its key's place in
    `batch_keys`, so the answer is keyed by the key ASKED, not by the database's spelling of it (a
    text '3' asked of an integer column). VALUES columns are column1, column2 ... in PostgreSQL and
    SQLite alike; in PostgreSQL each value is CAST to its column's type in the database (`_key_types`)
    - a VALUES column takes its type from its values, and integer = text raised (19b975908)."""
    from mapper_sdk import sql

    table, types = '"%s"' % source, _key_types(db, source, keys)

    def value(n, i, name):
        return "CAST(:k%d_%d AS %s)" % (n, i, types[name]) if name in types else ":k%d_%d" % (n, i)

    picked = ", ".join(['k.column1 AS "__asked"'] + ['%s."%s"' % (table, name) for name in columns])
    claims = {}
    for compare, group in (("=", [(n, key) for n, key in enumerate(batch_keys) if None not in key]),
                           ("IS NOT DISTINCT FROM", [(n, key) for n, key in enumerate(batch_keys) if None in key])):
        if not group:
            continue
        values = ", ".join("(%d, %s)" % (n, ", ".join(value(n, i, name) for i, name in enumerate(keys)))
                           for n, _key in group)
        on = " AND ".join('%s."%s" %s k.column%d' % (table, name, compare, i + 2) for i, name in enumerate(keys))
        found = sql(db, 'SELECT "__asked", COUNT(*) AS "__claims" FROM (SELECT DISTINCT %s FROM %s JOIN (VALUES %s) AS k'
                        ' ON %s WHERE 1 = 1%s) claims GROUP BY "__asked"'
                        % (picked, table, values, on, _gated(db, source, gates)),
                    {"k%d_%d" % (n, i): part for n, key in group for i, part in enumerate(key)})
        claims.update({batch_keys[int(record["__asked"])]: int(record["__claims"]) for record in found.to_dict("records")})
    return claims


def _key_types(db, source, keys) -> dict:
    """{key column: its type in the database} - PostgreSQL only. Elsewhere {}: SQLite compares by the
    column's affinity, and a CAST to DATETIME there would read '2026-10-10 …' as 2026."""
    if db.get_bind().dialect.name != "postgresql":
        return {}
    from mapper_sdk import sql

    found = sql(db, "SELECT a.attname AS name, format_type(a.atttypid, a.atttypmod) AS type FROM pg_attribute a"
                    " WHERE a.attrelid = to_regclass(:t) AND a.attnum > 0 AND NOT a.attisdropped",
                {"t": '"%s"' % source})
    return {record["name"]: record["type"] for record in found.to_dict("records") if record["name"] in keys}


def _gated(db, source, gates) -> str:
    """` AND <each require column filled> AND <each exclude column blank>` for `source`, or '' - the row
    gates `rule_run.held_back` judges, in `crud`'s SQL judgement, compiled."""
    import chain_bindings
    from database import crud, models

    judge = {chain_bindings.REQUIRE_KEY: crud.not_blank_sql_condition,
             chain_bindings.EXCLUDE_KEY: crud.blank_sql_condition}
    asked = [(judge[gate], column) for gate in chain_bindings.ROW_GATE_KEYS for column in (gates or {}).get(gate) or ()]
    if not asked:
        return ""
    model, dialect = models.DYNAMIC_TABLES[source], db.get_bind().dialect
    return "".join(" AND (%s)" % condition(crud.column_text_sql(getattr(model, column))).compile(
        dialect=dialect, compile_kwargs={"literal_binds": True}) for condition, column in asked)


def _holds_only(rule) -> bool:
    """The recount half: it runs on the target table and reads `params.source_table`."""
    return (rule or {}).get("trigger_table") == (rule or {}).get("target_table")


def _writes(rule) -> list:
    """The columns this rule writes - what a run that proposed nothing still owns (총괄 016a766af):
    the keys and the hold, and on the copy half the copied columns."""
    params = (rule or {}).get("params") or {}
    return list(dict.fromkeys(list(params.get("key_columns") or ())
                              + ([] if _holds_only(rule) else list(params.get("columns") or ()))
                              + ([params["hold_column"]] if params.get("hold_column") else [])))


def _paired(rules) -> list:
    """At load (총괄 016a766af · 0117a0048): a copy rule's row gates (`require` · `exclude`) are what its
    recount counts by too - stamped as `source_<gate>` on both halves, the copy's own on the copy and the
    pair's on the recount (the copies from its `source_table` into its target). -> [(recount, sentence)]
    for a recount whose copies gate by different columns - it cannot know which, so it is refused by name."""
    import chain_bindings

    stamps = chain_bindings.SOURCE_GATE_KEYS

    def gated(rule):
        return tuple((gate, tuple(rule.get(gate) or ())) for gate in chain_bindings.ROW_GATE_KEYS)

    copies = {}
    for rule in rules:
        if not _holds_only(rule):
            copies.setdefault((rule.get("trigger_table"), rule.get("target_table")), []).append(rule)
            for gate, columns in gated(rule):
                if columns:
                    rule[stamps[gate]] = list(columns)
    refused = []
    for rule in rules:
        if not _holds_only(rule):
            continue
        said = sorted({gated(copy) for copy in copies.get(
            ((rule.get("params") or {}).get("source_table"), rule.get("target_table")), ())})
        if len(said) > 1:
            refused.append((rule, "its copy rules into %s require or exclude by different columns %s - the "
                                  "hold count cannot know which; write the same require and exclude on every "
                                  "copy rule" % (rule.get("target_table"),
                                                 [{gate: list(columns) for gate, columns in s} for s in said])))
        elif said:
            for gate, columns in said[0]:
                if columns:
                    rule[stamps[gate]] = list(columns)
    return refused


def _register():
    import mapper_sdk
    mapper_sdk.register(NAME, copy_rows_with_hold, params=PARAMS, facts={
        "columns": _writes, "stamps_origin": lambda rule: not _holds_only(rule), "at_load": _paired})


_register()
