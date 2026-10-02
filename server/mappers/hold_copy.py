# -*- coding: utf-8 -*-
"""총괄 3211e9000 · 3ba1d1dd4 — 보류 포함 행 복사 (소유자 10-02 「df, db 받고 db 에서 df 키 조회해서
2개 이상이면 보류 아니면 합의」).

The owner's `copy_one_row` (RELEASE_LOG 10-01) with its columns as `params` and three lines more:
count the distinct value sets of `columns` among the source rows of this row's key; two or more
writes the hold blank, otherwise AGREED. The hold is one more item of the same updates (one
commit), under the plain chain layer - its blank is a chain write and empties the cell.

Two rules call it. On the source table it copies and holds; on the target table (trigger =
target, `source_table` named) it only recounts the hold - a deleted source row or a person's edit.

⚠️ NOT `@mapper`: the decorator hands its author (df, db) and no rule, so `params` could not be
read. The raw function goes into the same registry with its `params`.
"""
from __future__ import annotations

NAME = "copy_rows_with_hold"
PARAMS = ("key_columns", "columns", "hold_column", "source_table")
AGREED = "agreed"


def copy_rows_with_hold(db, payload, rule=None):
    import pandas as pd
    from database import crud
    from mapper_sdk import df_to_updates, payloads_to_df, sql

    df = payloads_to_df(payload)
    if df.empty:
        return {"updates": []}
    params = rule["params"]
    keys, columns, hold = list(params["key_columns"]), list(params["columns"]), params["hold_column"]
    target = rule["target_table"]
    row = df.astype(object).to_dict("records")[0]
    holds_only = rule["trigger_table"] == target
    source = params["source_table"] if holds_only else rule["trigger_table"]
    result = {"updates": []}
    if not holds_only:
        layer = crud.merged_layer_name(crud.CHAIN_SOURCE, row["row_id"])
        result = df_to_updates(df[list(dict.fromkeys(keys + columns))], target,
                               source_name=layer, updated_by=NAME)
        for item in result["updates"]:
            item["origin_row_id"] = row["row_id"]

    same_key = " AND ".join('"%s" IS NOT DISTINCT FROM :k%d' % (key, i) for i, key in enumerate(keys))
    claims = sql(db, 'SELECT COUNT(*) AS n FROM (SELECT DISTINCT %s FROM "%s" WHERE %s) claims'
                 % (", ".join('"%s"' % column for column in columns), source, same_key),
                 {"k%d" % i: row[key] for i, key in enumerate(keys)})
    held = pd.DataFrame([{**{key: row[key] for key in keys},
                          hold: "" if int(claims.at[0, "n"]) > 1 else AGREED}])
    result["updates"] += df_to_updates(held, target, source_name=crud.CHAIN_SOURCE,
                                       updated_by=NAME)["updates"]
    return result


def _register():
    import mapper_sdk
    mapper_sdk.register(NAME, copy_rows_with_hold, params=PARAMS)


_register()
