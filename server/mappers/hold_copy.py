# -*- coding: utf-8 -*-
"""총괄 3211e9000 · 3ba1d1dd4 · 32bab7896 · cb3d3c1bf — 보류 포함 행 복사 (소유자 10-02 「df, db 받고 db 에서
df 키 조회해서 2개 이상이면 보류 아니면 합의」 · 「나 로」).

The owner's `copy_one_row` (RELEASE_LOG 10-01) with its columns as `params`, for a batch: one row
or many - a rule with `is_batch: true` hands the batch, one without hands one row, and both go
the same way as one frame. Each row's columns land under that row's own layer
`chain_ingestion (<row_id>)` with `origin_row_id`; one query per 1,000 keys counts, per key, the
distinct value sets of `columns` among the source rows of that key. Exactly one is AGREED; none
(every source row deleted) or two and more holds the row blank. The hold is one item per key in
the same updates (one commit), under the plain chain layer - its blank is a chain write.

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
    params = rule["params"]
    keys, columns, hold = list(params["key_columns"]), list(params["columns"]), params["hold_column"]
    target = rule["target_table"]
    rows = df.astype(object).where(df.notna(), None).to_dict("records")
    holds_only = rule["trigger_table"] == target
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
    for start in range(0, len(batch_keys), DEFAULT_CHUNK_SIZE):   # 10,000 keys overran the parser
        claims.update(_claims(db, source, keys, columns,
                              batch_keys[start:start + DEFAULT_CHUNK_SIZE]))
    held = pd.DataFrame([{**dict(zip(keys, key)), hold: AGREED if claims.get(key) == 1 else ""}
                         for key in batch_keys])
    result["updates"] += df_to_updates(held, target, source_name=crud.CHAIN_SOURCE,
                                       updated_by=NAME)["updates"]
    return result


def _claims(db, source, keys, columns, batch_keys) -> dict:
    """{key: distinct value sets of `columns` among `source`'s rows of that key}. The keys with a
    value in every column join a VALUES list (총괄 043915ab0 ②: the row `IN` became an OR chain the
    planner answered with a scan of the whole table); a key holding a NULL is compared NULL-safe,
    by itself, in a second query only when there is one. A VALUES list's columns are column1,
    column2 ... in PostgreSQL and SQLite alike."""
    from mapper_sdk import sql

    valued = [(n, key) for n, key in enumerate(batch_keys) if all(value is not None for value in key)]
    nulled = [(n, key) for n, key in enumerate(batch_keys) if any(value is None for value in key)]

    def params_of(group):
        return {"k%d_%d" % (n, i): value for n, key in group for i, value in enumerate(key)}

    froms = []
    if valued:
        values = ", ".join("(%s)" % ", ".join(":k%d_%d" % (n, i) for i in range(len(keys))) for n, _ in valued)
        on = " AND ".join('s."%s" = k.column%d' % (name, i + 1) for i, name in enumerate(keys))
        froms.append(('"%s" s JOIN (VALUES %s) AS k ON %s' % (source, values, on), params_of(valued)))
    if nulled:
        match = " OR ".join("(%s)" % " AND ".join('s."%s" IS NOT DISTINCT FROM :k%d_%d' % (name, n, i)
                                                  for i, name in enumerate(keys)) for n, _ in nulled)
        froms.append(('"%s" s WHERE %s' % (source, match), params_of(nulled)))
    names = ", ".join('s."%s" AS "%s"' % (name, name) for name in dict.fromkeys(keys + columns))
    grouped = ", ".join('"%s"' % name for name in keys)
    claims = {}
    for where, params in froms:
        found = sql(db, 'SELECT %s, COUNT(*) AS n FROM (SELECT DISTINCT %s FROM %s) claims GROUP BY %s'
                        % (grouped, names, where, grouped), params)
        found = found.astype(object).where(found.notna(), None)
        claims.update({tuple(record[name] for name in keys): int(record["n"])
                       for record in found.to_dict("records")})
    return claims


def _register():
    import mapper_sdk
    mapper_sdk.register(NAME, copy_rows_with_hold, params=PARAMS)


_register()
