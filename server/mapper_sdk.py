# -*- coding: utf-8 -*-
"""What a chain mapper's author should not have to write.

The owner's shape for a mapper is three steps:

    ① payloads          -> DataFrame
    ② DataFrame + SQL   -> DataFrame        <- the only one the author writes
    ③ DataFrame         -> updates payload

and the goal is that ① and ③ leave the author's file. This module is where they go.

🔴 IT LIVES HERE AND NOT IN `mappers/` BECAUSE `mappers/` DOES NOT SHIP. `.gitignore`
excludes `server/mappers/*` and re-admits only `*.sample` and `ledger_v2_*.py`, so a
module put beside the mappers would exist on the box that wrote it and nowhere else -
the same failure a declaration pointing at a hand-made view has. Authors import it by
name; nothing here asks to be inherited from.

🔴 AND NO DOMAIN MODULE IS IMPORTED HERE. A mapper that never touches a map must not
drag the map engine in behind it, so this file knows about payloads, frames and the
table declaration, and about nothing else.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


def _python_scalar(value):
    """A numpy scalar as the Python value the writer's type check expects.

    🔴 MEASURED 2026-09-03: on this pandas, `astype(object).to_dict("records")` already
    hands back `int`, `float`, `bool`, `Timestamp` and `str` - NOTHING with `.item()`. So
    on the frame path below this function is a pass-through today, and that is written
    down rather than left for someone to discover by deleting it and seeing nothing go
    red.

    It stays, and it is tested directly, because the conversion is part of the contract
    the guide states rather than an artefact of one pandas version: older pandas returned
    `numpy.int64` from `to_dict`, and a `numpy.int64` is not an `int` to everything
    downstream. What must not happen is a branch nobody can reach that still reads like a
    handled case - so the test feeds it numpy scalars directly.
    """
    return value.item() if hasattr(value, "item") else value


class MapperContractError(ValueError):
    """The frame cannot be turned into a payload the writer would accept. Named, never
    silently emitted - every failure this raises is one that otherwise lands rows the
    upsert can never find again."""


def payloads_to_df(payloads: List[Dict[str, Any]]) -> pd.DataFrame:
    """Outbox payloads -> one flat row each. Step ①.

    The cell shape is `{col: {"value": x, ...}}`; this keeps the value and drops the
    envelope, and carries `row_id` through because identity is not a data column.

    This is the SAME implementation `mappers/utils.payloads_to_df` holds, so that
    `BaseMapper` - which the owner keeps for the production mappers that inherit it -
    and this SDK cannot answer differently. Two doors, one judgement.
    """
    if not payloads:
        return pd.DataFrame()

    flat_rows = []
    for p in payloads:
        flat_row = {"row_id": p.get("row_id")}
        for col_name, cell in (p.get("data") or {}).items():
            flat_row[col_name] = (cell["value"]
                                  if isinstance(cell, dict) and "value" in cell
                                  else cell)
        flat_rows.append(flat_row)
    return pd.DataFrame(flat_rows)


def df_to_updates(df, table_name: str, *, source_name: str, updated_by: str) -> dict:
    """DataFrame -> the `{"updates": [...]}` a chain mapper returns. Step ③.

    🔴 THE AUTHOR DOES NOT DECIDE THE BUSINESS KEY, AND THAT IS THE POINT OF THIS
    FUNCTION. Whether a target composes its key from several columns or carries one
    outright is a fact about the DECLARATION, and getting it wrong is silent in both
    directions:

        composite target, key spelled by the mapper
            `assemble_composite_business_key` returns at its first statement when the
            item already has a `business_key_val`, so the mapper's string wins and the
            declaration stops being followed. The day its separator or column list
            changes, only that mapper's keys drift and nothing errors.

        non-composite target, key left to the framework
            nothing lifts `updates[business_key]` into `business_key_val` -
            `_get_or_create_row` resolves identity from `row_id`/`business_key_val`
            alone - so the write has NO identity. The row lands, the upsert can never
            find it again, and every run inserts another copy. `unfilled_key_columns`
            answers `[]` for such an item, so the pre-write gate does not catch it
            either.

    Both were measured on 2026-09-02, and both are the kind that is found much later by
    someone counting rows. So the author emits columns and this function reads
    `TABLE_CONFIG` to decide which of the two the target is.

    🔴 AND A MISSING KEY COLUMN IS REFUSED RATHER THAN EMITTED. On a composite target an
    absent source column assembles nothing and the key stays `None`; on a plain one an
    absent key column produces the identity-less write above. Both are refused here, by
    name, because a batch that lands without identity cannot be distinguished afterwards
    from one that was never sent.

    NaN and NaT become `None`, not the string "nan". `pd.read_sql` turns SQL NULL into
    NaN - a float - so a bare `to_dict("records")` turns "there was no value" into "the
    value is nan", which is a value. Measured 2026-09-02 on `lot_event.parent_lot`.
    numpy scalars become Python scalars for the same reason: what reaches the writer has
    to be what the declaration's type check expects.
    """
    from database import crud            # lazy: `crud` imports back into this layer

    if df is None or len(df) == 0:
        return {"updates": []}

    config = crud.TABLE_CONFIG.get(table_name) or {}
    composite_src = config.get("composite_key_source")
    key_col = config.get("business_key")

    # 🔴 `astype(object)` FIRST. On a column pandas typed as float, assigning None puts
    # NaN back; widening to object is what lets the None survive to the payload.
    clean = df.astype(object).where(pd.notna(df), None)

    columns = list(clean.columns)
    if composite_src:
        missing = [c for c in composite_src if c not in columns]
        if missing:
            raise MapperContractError(
                f"'{table_name}' composes its key from {list(composite_src)} and the "
                f"frame has no {missing}. Emitting anyway would land rows whose key is "
                f"None - they insert, they never match again, and nothing errors.")
    elif key_col:
        if key_col not in columns:
            raise MapperContractError(
                f"'{table_name}' carries the key '{key_col}' and the frame has no such "
                f"column. Emitting anyway would land rows with no identity - the upsert "
                f"cannot find them again and every run inserts another copy.")

    updates = []
    for record in clean.to_dict("records"):
        values = {k: _python_scalar(v) for k, v in record.items()}
        item = {"updates": values,
                "source_name": source_name, "updated_by": updated_by}
        if not composite_src and key_col:
            # The plain case, and the ONLY one where this function names the key: the
            # framework does not lift it out of `updates`, so somebody has to, and it is
            # not the author's job to remember which tables those are.
            identity = values.get(key_col)
            if crud.is_blank_value(identity):
                raise MapperContractError(
                    f"'{table_name}' carries the key '{key_col}' and a row leaves it "
                    f"blank. That row would land with no identity; refused rather than "
                    f"written.")
            item["business_key_val"] = crud.clean_str_value(identity)
        updates.append(item)
    return {"updates": updates}
