"""`lot_event` rows -> one row per descent (parent lot, child lot, kind, time).

WHY THE CHAIN AND NOT THE LEDGER (총괄 e14416950, owner 10-01 「준비기는 ㄱ으로」). A descent is
told by TWO rows - the parent's (`child_lot` filled) and the child's (`parent_lot` filled) - and
the ledger translates one molecule at a time, so pairing them was a preparer's job. Here each row
names its descent on its own: both rows of a pair write the SAME row (same business key), so no
pairing is needed and a half-arrived pair already says what it knows.

A row naming no lot (its lot cell blank) writes nothing: an old generation is dropped (owner
08-21 「옛 세대는 버린다」) - counted on one line per batch. A row naming BOTH a parent and a child
is refused by name: it does not say which descent it is, and writing two would invent one.

🔴 EVERY COLUMN NAME IS THE RULE'S (총괄 0cb2ab958 가1): read from `params`, no default, a
missing cell refused by name; the four it writes are checked against the target table, and the
key column is the one the target declares.
"""
from __future__ import annotations

import logging

import pandas as pd

import chain_bindings
import mapper_sdk

logger = logging.getLogger("Mappers.LotLineage")

SOURCE_NAME = "chain_ingestion"
UPDATED_BY = "chain_lot_lineage"


#: The trigger-table columns it reads, as the rule's params name them.
INPUT_CELLS = ("lot_column", "parent_column", "child_column", "time_column",
               "event_type_column")
#: The target-table columns it writes (the key column besides: the target declares it).
OUTPUT_CELLS = ("target_parent_column", "target_child_column", "target_event_type_column",
                "target_time_column")


class DescentRefused(ValueError):
    """A trigger row that names both a parent and a child. Named, never split in two."""


def _value(payload, key):
    cell = (payload.get("data") or {}).get(key)
    if isinstance(cell, dict):
        return cell.get("value")
    return cell


def _text(value):
    return "" if value is None else str(value).strip()


def build_lot_lineage_rows(db, payloads, rule=None):
    """One row per (parent, child, kind, time). Returns chain batches."""
    target = chain_bindings.resolve_table(rule, "target_table")
    params = chain_bindings.params_of(rule, required=INPUT_CELLS + OUTPUT_CELLS,
                                      columns_of={cell: target for cell in OUTPUT_CELLS})
    lot_col, parent_col, child_col, time_col, type_col = (params[c] for c in INPUT_CELLS)
    out_parent, out_child, out_type, out_time = (params[c] for c in OUTPUT_CELLS)
    from database import crud      # lazy, as mapper_sdk.df_to_updates reads it
    key_column = (crud.TABLE_CONFIG.get(target) or {}).get("business_key")
    rows, refused, no_lot = [], [], 0
    for payload in payloads or []:
        lot = _text(_value(payload, lot_col))
        parent = _text(_value(payload, parent_col))
        child = _text(_value(payload, child_col))
        if not parent and not child:
            continue
        if not lot:
            no_lot += 1
            continue
        if parent and child:
            refused.append({lot_col: lot, parent_col: parent, child_col: child,
                            time_col: _value(payload, time_col)})
            continue
        parent, child = (parent, lot) if parent else (lot, child)
        when = _value(payload, time_col)
        kind = _value(payload, type_col)
        rows.append({out_parent: parent, out_child: child, out_type: kind, out_time: when,
                     key_column: f"{parent}|{child}|{kind}|{when}"})
    if no_lot:
        logger.info("[Chain] lot_lineage: %d row(s) name a relative but no lot (%s blank) - an "
                    "old generation, not written (owner 08-21)", no_lot, lot_col)
    if refused:
        raise DescentRefused(
            f"{len(refused)} trigger row(s) name both {parent_col} and {child_col}, so which "
            f"descent they tell is not knowable; fill one. First: {refused[:3]}")
    return mapper_sdk.df_to_updates(pd.DataFrame(rows), target, source_name=SOURCE_NAME,
                                    updated_by=UPDATED_BY)
