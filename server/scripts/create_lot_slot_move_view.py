r"""Create `lot_slot_move` -- one row per seat-to-seat move a lot event records.

🔴 WHY THIS EXISTS: `merge_slot_join` and `split_slot_carry` bind `from` and `to` to the SAME
`slots` column, and subject and target to the SAME `lot` column. A slot CHANGE therefore cannot
be written down at all -- which is why 443 `slot_map` atoms collapse to 46 subjects x 49 objects
with one pair repeating 25 times. The information is not missing from the source; it is missing
from the row shape.

    lot=CL-2601-002-A4  child_lot=CL-2601-005-A5  slots=01:05:07…  wafers=WF.010201:…
                        ^ the counterparty's slot for that wafer is NOT on this row

`slot_numbers` and `wafer_ids` are colon-separated lists paired BY POSITION. Exploding both with
ORDINALITY and joining on the ordinal gives (lot, slot, wafer); pairing two such rows on the
wafer id gives the move -- from seat to seat.

🔴 BOTH DIRECTIONS, THEN DEDUPED. A move can be recorded by the giving lot (`child_lot` set) or
by the receiving lot (`parent_lot` set), and neither side records all of them:

    child direction only    97 edges
    parent direction only  197 rows, but they hold duplicates
    UNION, deduped         135 edges      <- 38 moves only the receiving side saw

The dedup is identity dedup -- the SAME move seen from two sides -- not a fold that drops
information, so "one row is one move" still holds. The gate asserts it: row count must equal the
distinct-tuple count.

🔴 `event_type` IS CARRIED, NOT INFERRED. The source records split / merge / track_in, and an
earlier draft of this view dropped it on the grounds that "the lot names say which way it went".
That is a derivation standing in for a record, which is the failure this project keeps meeting.

⚠️ WHICH ROW'S TYPE, MEASURED: taking the GIVING row's type in both arms breaks the contract --
187 rows for 135 moves, because a move seen from both sides then carries two types. Taking the
type of the row that RECORDED each arm keeps 135 = 135. So the type belongs to the record, not
to the move, and the dedup stays honest.

📌 `track_in` never becomes a move: 0 of the 5 track_in rows have a child_lot or a parent_lot,
so there is no counterparty to pair with. That is correct -- a track-in is not a move.

🔴 THE GATE IS 21. Independently of this view, the ledger's own `slot_map` qualifiers say 21
moves change slot. Two unrelated paths -- pairing lot_event rows here, and reading the existing
atoms' qualifiers -- have to land on the same 21. If they do not, the pairing is wrong.

USAGE -- dry run by default; the gate runs before the commit either way:

    python scripts/create_lot_slot_move_view.py
    python scripts/create_lot_slot_move_view.py --apply --i-accept-writing-to-owner-database

ROLLBACK:

    DROP VIEW lot_slot_move;
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import text                                          # noqa: E402
from database import database as db                                  # noqa: E402

VIEW = "lot_slot_move"
EXPECTED_ROWS = 135
EXPECTED_CHANGES = 21

#: (lot, slot, wafer), one row per occupied seat, from the two positionally-paired lists.
SEATS = """
    SELECT e.lot, e.parent_lot, e.child_lot, e.event_time, e.event_type, s.slot, w.wafer
      FROM lot_event e
      CROSS JOIN LATERAL unnest(string_to_array(e.slot_numbers, ':'))
                  WITH ORDINALITY AS s(slot, i)
      CROSS JOIN LATERAL unnest(string_to_array(e.wafer_ids, ':'))
                  WITH ORDINALITY AS w(wafer, j)
     WHERE s.i = w.j
       AND e.slot_numbers IS NOT NULL AND e.wafer_ids IS NOT NULL
"""

DROP_SQL = f"DROP VIEW IF EXISTS {VIEW}"

CREATE_SQL = f"""
CREATE VIEW {VIEW} AS
SELECT a.lot AS from_lot, a.slot AS from_slot,
       b.lot AS to_lot,   b.slot AS to_slot,
       a.wafer, a.event_time, a.event_type
  FROM ({SEATS}) a
  JOIN ({SEATS}) b ON b.lot = a.child_lot AND b.wafer = a.wafer
 WHERE a.child_lot IS NOT NULL
UNION
SELECT b.lot AS from_lot, b.slot AS from_slot,
       a.lot AS to_lot,   a.slot AS to_slot,
       a.wafer, a.event_time, a.event_type
  FROM ({SEATS}) a
  JOIN ({SEATS}) b ON b.lot = a.parent_lot AND b.wafer = a.wafer
 WHERE a.parent_lot IS NOT NULL"""

#: The independent number: what the atoms already in the ledger say, read from their qualifiers.
LEDGER_CHANGES_SQL = """
SELECT count(*) FROM ledger_events
 WHERE predicate = 'slot_map'
   AND object_payload -> 'qualifiers' ->> 'from'
    IS DISTINCT FROM object_payload -> 'qualifiers' ->> 'to'"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '300s'"))
        try:
            events = c.execute(text("SELECT count(*) FROM lot_event")).scalar()
            c.execute(text(DROP_SQL))
            c.execute(text(CREATE_SQL))
            rows = c.execute(text(f"SELECT count(*) FROM {VIEW}")).scalar()
            distinct = c.execute(text(
                f"SELECT count(*) FROM (SELECT DISTINCT from_lot, from_slot, to_lot, to_slot, "
                f"wafer, event_time FROM {VIEW}) t")).scalar()
            changes = c.execute(text(
                f"SELECT count(*) FROM {VIEW} WHERE from_slot <> to_slot")).scalar()
            wafers = c.execute(text(f"SELECT count(DISTINCT wafer) FROM {VIEW}")).scalar()
            no_time = c.execute(text(
                f"SELECT count(*) FROM {VIEW} WHERE event_time IS NULL")).scalar()
            typed = c.execute(text(
                f"SELECT count(*) FROM {VIEW} WHERE event_type IS NOT NULL")).scalar()
            ledger_changes = c.execute(text(LEDGER_CHANGES_SQL)).scalar()

            print("   lot_event rows               %8d" % events)
            print("   view rows (one per move)     %8d   %s"
                  % (rows, "OK" if rows == EXPECTED_ROWS else "<- expected %d" % EXPECTED_ROWS))
            print("   distinct move tuples         %8d   %s"
                  % (distinct, "OK - a row IS a move"
                     if distinct == rows else "<- rows are NOT one per move"))
            print("   moves that CHANGE slot       %8d   %s"
                  % (changes, "OK" if changes == EXPECTED_CHANGES
                     else "<- expected %d" % EXPECTED_CHANGES))
            print("   the ledger's own count       %8d   %s"
                  % (ledger_changes, "OK - two paths agree"
                     if ledger_changes == changes else "<- the pairing disagrees with the atoms"))
            print("   distinct wafers moved        %8d" % wafers)
            print("   rows with no event_time      %8d   %s"
                  % (no_time, "OK" if no_time == 0 else "<- no time to order the chain by"))
            print("   rows carrying event_type     %8d   %s"
                  % (typed, "OK - the record is kept" if typed == rows
                     else "<- %d moves lost what the source recorded" % (rows - typed)))
            for kind, n in c.execute(text(
                    f"SELECT event_type, count(*) FROM {VIEW} GROUP BY 1 ORDER BY 2 DESC")):
                print("      %-12s %8d" % (kind, n))

            ok = (rows == EXPECTED_ROWS and distinct == rows
                  and changes == EXPECTED_CHANGES and changes == ledger_changes
                  and no_time == 0 and typed == rows)
            print("\n   GATE: %s" % ("PASS" if ok else "FAIL"))
            if ok and args.apply and args.allow_owner:
                c.commit()
                print("COMMITTED.  Rollback: DROP VIEW %s;" % VIEW)
            else:
                c.rollback()
                print("ROLLED BACK." if not ok else "DRY RUN - rolled back.")
                return 0 if ok else 1
        except Exception:
            c.rollback()
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
