# -*- coding: utf-8 -*-
"""총괄 a10d88cd7 — a text's mentions of nodes: each row of a text table names the nodes its text spells,
one mention row each (the type, the key, and the row's `copy_columns`) in the table the rule writes.

The dictionary is every key of the types the rule lists (`node_types`, single-key entity types only), read
from the operating world's ledger - a node is any atom naming it, either side (`gaps._nodes_of_type_sql`). The
match is `text_links._matches`: spaces and ASCII case ignored, the longest leftmost first, and a key starting or
ending with a letter or digit only where the text does not continue that word (L1234 is not in L12345).
A text row hands every mention it still makes each time, so an edit takes back what it no longer names and a
deleted row takes back all of its own (`stamps_origin`).
⚠️ The whole of each type is read once a run - the box's 17,121 wafers 2.2 s, 103,863 defects 1.0 s (10-21).
"""
from __future__ import annotations

NAME = "link_mentions"
#: what each argument must be - a list written as text was read a letter at a time (총괄 67dffd619)
PARAMS = {"text_column": str, "copy_columns": list, "type_column": str, "key_column": str, "node_types": list}
CHUNK = 1000


def link_mentions(db, payloads, rule=None):
    import pandas as pd
    from database import crud, models
    from mapper_sdk import df_to_updates, payloads_to_df
    from utils import text_links

    df = payloads_to_df(payloads)
    if df.empty:
        return {"updates": []}
    params = rule["params"]
    texts, copied = models.DYNAMIC_TABLES[rule["trigger_table"]], list(params["copy_columns"])
    index = text_links._dictionary(_names(db, params.get("node_types")), [])
    ids = [str(r) for r in df["row_id"]]
    out = []
    for start in range(0, len(ids), CHUNK):
        for row in (db.query(texts.row_id, getattr(texts, params["text_column"]),
                             *[getattr(texts, column) for column in copied])
                    .filter(texts.row_id.in_(ids[start:start + CHUNK]))):
            if crud.is_blank_value(row[1]):
                continue
            named = {(found["node_type"], found["node_key"])
                     for _s, _e, _words, rows in text_links._matches(str(row[1]), index) for _kind, found in rows}
            out += [dict(zip(copied, row[2:]), **{params["type_column"]: node_type, params["key_column"]: key},
                         row_id=row[0]) for node_type, key in sorted(named)]
    if not out:
        return {"updates": []}
    frame = pd.DataFrame(out)
    result = df_to_updates(frame.drop(columns=["row_id"]), rule["target_table"], source_name=crud.CHAIN_SOURCE,
                           updated_by=NAME)
    for item, origin in zip(result["updates"], frame["row_id"]):     # the write seat names its row layer
        item["origin_row_id"] = origin
    return result


def _names(db, node_types) -> list:
    """[{node_type, node_key, phrase}] - every key of each listed type, its own phrase. A list that is empty, names a
    type the entities do not declare, or one with more than one key is refused by name."""
    from ledger_api import declared_entities
    from mapper_sdk import MapperContractError

    types = [str(t).strip() for t in (node_types or ()) if str(t).strip()]
    if not types:
        raise MapperContractError("node_types is empty - list the entity types whose keys a text can name")
    names = []
    for bare in types:
        keys = declared_entities.identity_keys(bare)
        if len(keys) != 1:
            raise MapperContractError(
                "node_types: %r %s" % (bare, "is not a declared entity type" if not keys else
                                       "has %d keys (%s) - a text names a node by one key" % (len(keys), ", ".join(keys))))
        names += [{"node_type": bare, "node_key": key, "phrase": key} for key in _keys_of(db, bare, keys[0])]
    return names


def _keys_of(db, bare, axis) -> list:
    """Every text value of `axis` among the type's nodes in the operating world's ledger."""
    from ledger import gaps, schema

    relation = schema.walk_relation((schema.require_world(None),))
    found = db.connection().exec_driver_sql(
        "SELECT keys FROM (%s) n" % gaps._nodes_of_type_sql(whole=True).format(table=relation), {"bare": bare})
    return [value for (keys,) in found for value in [(keys or {}).get(axis)] if isinstance(value, str) and value]


def _writes(rule) -> list:
    params = (rule or {}).get("params") or {}
    return list(dict.fromkeys(list(params.get("copy_columns") or ())
                              + [params[c] for c in ("type_column", "key_column") if params.get(c)]))


def _register():
    import mapper_sdk
    mapper_sdk.register(NAME, link_mentions, params=PARAMS, facts={
        "columns": _writes, "stamps_origin": lambda rule: True})


_register()
