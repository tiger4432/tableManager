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
    for start in range(0, len(batch_keys), DEFAULT_CHUNK_SIZE):   # 10,000 keys overran the parser
        claims.update(_claims(db, source, keys, columns, batch_keys[start:start + DEFAULT_CHUNK_SIZE],
                              rule.get(chain_bindings.SOURCE_EXCLUDE_KEY) or ()))
    held = pd.DataFrame([{**dict(zip(keys, key)), hold: AGREED if claims.get(key) == 1 else ""}
                         for key in batch_keys])
    result["updates"] += df_to_updates(held, target, source_name=crud.CHAIN_SOURCE,
                                       updated_by=NAME)["updates"]
    return result


def _claims(db, source, keys, columns, batch_keys, exclude=()) -> dict:
    """{key: distinct value sets of `columns` among `source`'s rows of that key} - one query. A row
    with an `exclude` column filled is not a claim (총괄 016a766af) - the seat's own blank judgement
    (`crud.blank_sql_condition`), compiled into this query."""
    from mapper_sdk import sql

    params, valued, nulled = {}, [], []
    for n, key in enumerate(batch_keys):
        for i, value in enumerate(key):
            params["k%d_%d" % (n, i)] = value
        if any(value is None for value in key):
            nulled.append(" AND ".join('"%s" IS NOT DISTINCT FROM :k%d_%d' % (name, n, i)
                                       for i, name in enumerate(keys)))
        else:
            valued.append("(%s)" % ", ".join(":k%d_%d" % (n, i) for i in range(len(keys))))
    where = (["(%s) IN (%s)" % (", ".join('"%s"' % name for name in keys), ", ".join(valued))]
             if valued else []) + ["(%s)" % clause for clause in nulled]
    names = ", ".join('"%s"' % name for name in dict.fromkeys(keys + columns))
    found = sql(db, 'SELECT %s, COUNT(*) AS n FROM (SELECT DISTINCT %s FROM "%s" WHERE (%s)%s) claims '
                    'GROUP BY %s' % (", ".join('"%s"' % name for name in keys), names, source,
                                     " OR ".join(where), _unexcluded(db, source, exclude),
                                     ", ".join('"%s"' % name for name in keys)),
                params)
    found = found.astype(object).where(found.notna(), None)
    return {tuple(record[name] for name in keys): int(record["n"])
            for record in found.to_dict("records")}


def _unexcluded(db, source, exclude) -> str:
    """` AND <each exclude column blank>` for `source`, or '' - `crud`'s SQL judgement, compiled."""
    if not exclude:
        return ""
    from database import crud, models

    model, dialect = models.DYNAMIC_TABLES[source], db.get_bind().dialect
    return "".join(" AND (%s)" % crud.blank_sql_condition(crud.column_text_sql(getattr(model, column))).compile(
        dialect=dialect, compile_kwargs={"literal_binds": True}) for column in exclude)


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
    """At load (총괄 016a766af): a copy rule's `exclude` is what its recount counts by too - stamped as
    `source_exclude` on both halves, the copy's own on the copy and the pair's on the recount (the
    copies from its `source_table` into its target). -> [(recount, sentence)] for a recount whose
    copies exclude by different columns - it cannot know which, so it is refused by name."""
    import chain_bindings

    exclude, stamped = chain_bindings.EXCLUDE_KEY, chain_bindings.SOURCE_EXCLUDE_KEY
    copies = {}
    for rule in rules:
        if not _holds_only(rule):
            copies.setdefault((rule.get("trigger_table"), rule.get("target_table")), []).append(rule)
            if rule.get(exclude):
                rule[stamped] = list(rule[exclude])
    refused = []
    for rule in rules:
        if not _holds_only(rule):
            continue
        said = sorted({tuple(copy.get(exclude) or ()) for copy in copies.get(
            ((rule.get("params") or {}).get("source_table"), rule.get("target_table")), ())})
        if len(said) > 1:
            refused.append((rule, "its copy rules into %s exclude by different columns %s - the hold "
                                  "count cannot know which; write one exclude on every copy rule"
                                  % (rule.get("target_table"), [list(s) for s in said])))
        elif said and said[0]:
            rule[stamped] = list(said[0])
    return refused


def _register():
    import mapper_sdk
    mapper_sdk.register(NAME, copy_rows_with_hold, params=PARAMS, facts={
        "columns": _writes, "stamps_origin": lambda rule: not _holds_only(rule), "at_load": _paired})


_register()
