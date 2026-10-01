"""`lot_event`'s two parallel lists -> one row per (lot, slot, wafer).

WHY THIS IS A CHAIN RULE AND NOT A VIEW. A view built by a script exists on the box that
ran the script and nowhere else, so a declaration pointing at it ships a source that simply
does not appear anywhere the script never ran. Production spreads derived tables with the
chain; the owner's instruction was to derive this one from `lot_event` the same way
(2026-08-31: 「어느 slot trace가 아니라 lot event에서 파생하라고」).

🔴 THE DELIMITER IS DECLARED, NOT ASSUMED. A separator is a property of the feed, and this
box's happens to be `:`. Reading it off the rule means another environment states its own
instead of finding that every wafer id came out glued together - a failure that produces
rows rather than an error, so nobody would see it until a map was wrong. So is every column
name, read and written (총괄 0cb2ab958 가1): from `params`, no default, a missing cell refused
by name, the written ones checked against the target table, the key column the target's own.

🔴 AND A ROW WHOSE TWO LISTS DISAGREE IS REFUSED, NOT TRIMMED. Zipping to the shorter list
loses the wafers past the end SILENTLY: the row still lands, the count still looks
plausible, and the missing wafers are indistinguishable from wafers that were never in the
lot. Measured on this box before writing this: 80 rows carry both lists, 907 pairs, and
ZERO rows disagree - so the refusal costs nothing today and exists for the day a feed
changes shape.
"""
from __future__ import annotations

import pandas as pd

import chain_bindings
import mapper_sdk

SOURCE_NAME = "chain_ingestion"
UPDATED_BY = "chain_lot_slot_wafer"

#: What it reads off the trigger table, as the rule's params name it.
INPUT_CELLS = ("slot_list_column", "wafer_list_column", "list_delimiter", "lot_column",
               "time_column", "event_type_column")
#: The target-table columns it writes (the key column besides: the target declares it).
OUTPUT_CELLS = ("target_lot_column", "target_slot_column", "target_wafer_column",
                "target_time_column", "target_event_type_column")


class ListPairingRefused(ValueError):
    """A trigger row whose two lists cannot be paired. Named, never trimmed."""


def _value(payload, key):
    cell = (payload.get("data") or {}).get(key)
    if isinstance(cell, dict):
        return cell.get("value")
    return cell


def _split(raw, delimiter):
    if raw is None:
        return []
    return [part.strip() for part in str(raw).split(delimiter) if part.strip()]


def build_lot_slot_wafer_rows(db, payloads, rule=None):
    """One row per (lot, slot, wafer, time). Returns chain batches.

    The business key is the four together because that is what makes a row unique: the same
    lot and slot hold different wafers at different times, and a key without the time would
    make two real events collide into one row - which is the second guard the brief asked
    for, expressed as a key rather than as a check.
    """
    target_table = chain_bindings.resolve_table(rule, "target_table")
    params = chain_bindings.params_of(
        rule, required=INPUT_CELLS + OUTPUT_CELLS,
        columns_of={cell: target_table for cell in OUTPUT_CELLS})
    slot_col, wafer_col, delimiter, lot_col, time_col, type_col = (
        params[c] for c in INPUT_CELLS)
    out_lot, out_slot, out_wafer, out_time, out_type = (params[c] for c in OUTPUT_CELLS)
    from database import crud      # lazy, as mapper_sdk.df_to_updates reads it
    key_column = (crud.TABLE_CONFIG.get(target_table) or {}).get("business_key")

    rows = []
    refused = []
    for payload in payloads or []:
        slots = _split(_value(payload, slot_col), delimiter)
        wafers = _split(_value(payload, wafer_col), delimiter)
        if not slots or not wafers:
            # Not a refusal: a lot event that carries no lists is simply not about slots.
            continue
        if len(slots) != len(wafers):
            refused.append({
                lot_col: _value(payload, lot_col),
                time_col: _value(payload, time_col),
                slot_col: len(slots), wafer_col: len(wafers)})
            continue
        lot = _value(payload, lot_col)
        when = _value(payload, time_col)
        event_type = _value(payload, type_col)
        for slot, wafer in zip(slots, wafers):
            # The key is stated rather than left to be composed: it IS the uniqueness guard
            # the brief asked for. The same lot and slot hold different wafers at different
            # times, so a key without the time collides two real events.
            rows.append({out_lot: lot, out_slot: slot, out_wafer: wafer, out_time: when,
                         out_type: event_type, key_column: f"{lot}|{slot}|{wafer}|{when}"})

    if refused:
        # 🔴 RAISED, NOT LOGGED. The chain records a mapper error as a failed rule, which is
        # visible; a log line during a sweep of thousands of rows is not. And the count is
        # in the message, because "some rows disagreed" cannot be acted on.
        raise ListPairingRefused(
            f"{len(refused)} trigger row(s) have a different number of slots and wafers, "
            f"so their pairing is not knowable; trimming to the shorter list would drop "
            f"wafers silently. First: {refused[:3]}")

    # 🔴 A DICT, NOT A LIST. `chain_replay` wraps an `is_batch` mapper's return in a list of
    # its own and then reads `.get("updates")` on each element, so returning a list of
    # batches produces a list where a dict is expected - and the chain reports zero items
    # rather than an error. Measured: the same payloads that make 907 updates here came
    # back as `mapper_items: 0` through the chain until this changed. `target_table` is not
    # ours to state either; the RULE declares it, which is why the chain never asked.
    return mapper_sdk.df_to_updates(pd.DataFrame(rows), target_table,
                                    source_name=SOURCE_NAME, updated_by=UPDATED_BY)
