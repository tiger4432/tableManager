"""Create `lot_slot_wafer` — one row per (lot, slot, wafer) out of `lot_event`'s lists.

WHY A VIEW AND NOT A MAPPER.  `has_wafer@1`'s subject is `lot_slot@1`, which has TWO
identity keys.  `ledger/roleframe.py::_entity_value` refuses a mapper-supplied Entity
reference that does not carry exactly one:

    if len(keys) != 1:
        raise RoleFrameError("invalid_sentence_contract", ...,
                             "a mapper-supplied Entity reference carries one identity key")

So `lot_event#in_slot`, which lived in a custom mapper, could never emit a single atom --
and it did not: measured 2026-08-30, `has_wafer` had ZERO atoms in the ledger while every
other declared predicate had some.  The refusal is loud when the source runs, but the source
had not run since the rebuild, so what an operator saw was an absence, not an error.

A `declarative-role` source does not hit that contract: the framework builds both keys from
columns itself.  `lot_slot_move` already emits `slot_map@1` over the same two-key entity
that way, so this is the existing road rather than a new one -- the view only has to present
the data ROW-WISE, which is what `lot_event` does not do.

THE LISTS ARE POSITIONAL.  `slotnumbers` and `waferids` are colon-joined and pair up by
position; measured before building this, 80 of 80 rows have equal lengths.  `unnest(a, b)`
zips them, so a length mismatch would surface as NULLs rather than silently shifting one
list against the other -- the WHERE clause drops those rather than minting a wrong seat.

Slots keep their text form (`'01'`, not `1`).  `lot_slot_move` stores them the same way, and
the walk matches keys with JSONB equality, where `"01"`, `"1"` and `1` are three different
things.  Do not "normalise" either side alone.

Rollback:  DROP VIEW lot_slot_wafer;
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

VIEW = "lot_slot_wafer"

DDL = f"""
CREATE OR REPLACE VIEW {VIEW} AS
SELECT
    e.lot_id                                   AS lot,
    btrim(u.slot)                              AS slot,
    btrim(u.wafer)                             AS wafer,
    e.event_type                               AS event_type,
    e.event_time                               AS event_time,
    e.lot_id || '|' || btrim(u.slot) || '|' || btrim(u.wafer) || '|' || e.event_time
                                               AS lot_slot_wafer_key
FROM lot_event e,
     unnest(string_to_array(e.slotnumbers, ':'),
            string_to_array(e.waferids,    ':')) AS u(slot, wafer)
WHERE NULLIF(e.lot_id, '')      IS NOT NULL
  AND NULLIF(btrim(u.slot), '') IS NOT NULL
  AND NULLIF(btrim(u.wafer),'') IS NOT NULL
"""

logger = logging.getLogger("create_lot_slot_wafer_view")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s | %(message)s")
    from database.database import engine

    with engine.begin() as conn:
        conn.execute(text(DDL))

    with engine.connect() as conn:
        source_rows = conn.execute(text(
            "SELECT count(*) FROM lot_event WHERE NULLIF(slotnumbers,'') IS NOT NULL")).scalar()
        kept = conn.execute(text(f"SELECT count(*) FROM {VIEW}")).scalar()
        keys = conn.execute(text(
            f"SELECT count(*) FROM (SELECT DISTINCT lot_slot_wafer_key FROM {VIEW}) t")).scalar()
        seats = conn.execute(text(
            f"SELECT count(*) FROM (SELECT DISTINCT lot, slot FROM {VIEW}) t")).scalar()
        wafers = conn.execute(text(f"SELECT count(DISTINCT wafer) FROM {VIEW}")).scalar()
        ragged = conn.execute(text(
            "SELECT count(*) FROM lot_event"
            " WHERE NULLIF(slotnumbers,'') IS NOT NULL AND NULLIF(waferids,'') IS NOT NULL"
            "   AND array_length(string_to_array(slotnumbers,':'),1)"
            "    <> array_length(string_to_array(waferids,':'),1)")).scalar()

    logger.info("%s: %d list rows -> %d rows, %d seats, %d wafers",
                VIEW, source_rows, kept, seats, wafers)
    # The business key must be unique or the source's cursor cannot advance deterministically.
    if keys != kept:
        logger.error("business key is NOT unique: %d rows but %d distinct keys", kept, keys)
        return 1
    # Ragged rows are dropped by the zip rather than mis-paired, but a nonzero count means
    # the upstream table changed shape and someone should look before trusting the seats.
    if ragged:
        logger.warning("%d lot_event row(s) have mismatched list lengths; their extra "
                       "entries are dropped, not paired", ragged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
