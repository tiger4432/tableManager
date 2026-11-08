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

One rule calls it, on the source table: it copies and holds, and counts again the hold of a key a row left - deleted,
moved to another key or out of the rule's require / exclude (lead 11-08 ㄱ: the recount rule on the target table, 총괄
e11bb4de0, retired - two rules on one hold cell showed the older count). A recount rule still declared is refused by
name at load.

🔴 THE KEYS ARE COMPARED WITH `=` WHERE THEY HAVE A VALUE: `IS NOT DISTINCT FROM` takes no
index, so on a table of a million rows every count was a full scan. A key holding a NULL is
compared NULL-safe, by itself.
⚠️ NOT `@mapper`: the decorator hands its author (df, db) and no rule, so `params` could not be
read. The raw function goes into the same registry with its `params`.
"""
from __future__ import annotations


NAME = "copy_rows_with_hold"
#: what each argument must be - a list written as text was read a letter at a time (총괄 67dffd619)
PARAMS = {"key_columns": list, "columns": list, "hold_column": str,
          # the retired recount's - read by none, kept so its rule is refused as retired, not as a misspelling
          "source_table": str}
AGREED = "agreed"


def copy_rows_with_hold(db, payloads, rule=None):
    import pandas as pd
    from database import crud
    from mapper_sdk import df_to_updates, payloads_to_df

    import chain_bindings
    import event_constants

    # a deleted row (no data, its old values) copies nothing - the write seat settles the layer it fed - and the key it
    # left is counted again here, as the key an edit moved a row off or took it out of the gates (lead 11-08 ㄱ: the
    # recount rule retired, this is the one seat that counts a hold)
    listed = [payloads] if isinstance(payloads, dict) else list(payloads or ())
    df = payloads_to_df([p for p in listed if not isinstance(p, dict) or p.get("data")
                         or not event_constants.old_values_of(p)])
    params = rule["params"]
    keys, columns, hold = list(params["key_columns"]), list(params["columns"]), params["hold_column"]
    target, source = rule["target_table"], rule["trigger_table"]
    rows = df.astype(object).where(df.notna(), None).to_dict("records") if not df.empty else []
    result = {"updates": []}
    if rows:
        result = df_to_updates(df[list(dict.fromkeys(keys + columns))], target,
                               source_name=crud.CHAIN_SOURCE, updated_by=NAME)
        for item, row in zip(result["updates"], rows):     # the write seat names its row layer
            item["origin_row_id"] = row["row_id"]

    from chain.keyset_scan import DEFAULT_CHUNK_SIZE

    def chunked(asked, table, read, gates=None):
        found = {}
        for start in range(0, len(asked), DEFAULT_CHUNK_SIZE):   # 10,000 keys overran the parser
            found.update(_claims(db, table, keys, read, asked[start:start + DEFAULT_CHUNK_SIZE], gates))
        return found

    live = list(dict.fromkeys(tuple(row[key] for key in keys) for row in rows))
    left = list(dict.fromkeys(key for key in (event_constants.key_left(p, keys) for p in listed if isinstance(p, dict))
                              if key is not None and not any(crud.is_blank_value(v) for v in key)))
    held = chunked(left, target, []) if left else {}                # the keys with a row to hold, read once
    left = [key for key in left if key in held]
    batch_keys, spelled = [], set()
    for key in live + left:
        owner = _spelled(target, keys, key)
        if owner not in spelled:                       # one hold a key, whichever spelling it came in
            spelled.add(owner)
            batch_keys.append((key, owner))
    if not batch_keys:
        return result
    gates = {gate: rule.get(gate) or () for gate in chain_bindings.ROW_GATE_KEYS}
    claims = chunked([key for key, _owner in batch_keys], source, columns, gates)
    held = pd.DataFrame([{**dict(zip(keys, key)), hold: AGREED if claims.get(key) == 1 else ""}
                         for key, _owner in batch_keys])
    items = df_to_updates(held, target, source_name=crud.CHAIN_SOURCE, updated_by=NAME)["updates"]
    for item, (_key, owner) in zip(items, batch_keys):
        item["owner_key"] = owner                      # the hold's one layer per key (`rule_run.owner_of`)
    result["updates"] += items
    return result


def _spelled(target, keys, key) -> str:
    """The target row's key as the write spells it (`crud.assemble_composite_business_key`), else its parts."""
    from database import crud, schemas

    one = schemas.GeneralUpdateItem(updates=dict(zip(keys, key)), source_name=crud.CHAIN_SOURCE)
    crud.assemble_composite_business_key(target, one)
    return str(one.business_key_val) if one.business_key_val is not None else "|".join(
        "" if part is None else str(part) for part in key)


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
    from chain.rule_run import gate_conditions
    from database import models

    dialect = db.get_bind().dialect
    return "".join(" AND (%s)" % condition.compile(dialect=dialect, compile_kwargs={"literal_binds": True})
                   for condition in gate_conditions(gates or {}, models.DYNAMIC_TABLES.get(source)))


def _writes(rule) -> list:
    """The columns this rule writes - what a run that proposed nothing still owns (총괄 016a766af): the keys, the copied
    columns and the hold."""
    params = (rule or {}).get("params") or {}
    return list(dict.fromkeys(list(params.get("key_columns") or ()) + list(params.get("columns") or ())
                              + ([params["hold_column"]] if params.get("hold_column") else [])))


#: The load line of a recount rule (lead 11-08 ㄱ) - it would copy the target table onto itself.
RECOUNT_RETIRED = ("the recount is retired - delete this rule; its copy rule into %s counts the holds again (lead "
                   "11-08)")


def _recount_retired(rules) -> list:
    """At load: a rule of this mapper on its own target - the retired recount - refused by name.
    -> [(rule, code, sentence)]"""
    return [(rule, "recount_retired", RECOUNT_RETIRED % rule.get("target_table")) for rule in rules
            if rule.get("trigger_table") == rule.get("target_table")]


def _register():
    import mapper_sdk
    mapper_sdk.register(NAME, copy_rows_with_hold, params=PARAMS, facts={
        "columns": _writes, "stamps_origin": True, "at_load": _recount_retired})


_register()
