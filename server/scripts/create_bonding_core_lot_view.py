r"""Create `bonding_core_lot` -- every (bonding wafer, core wafer) pair the bonding log records.

🔴 EVERY PAIR, BECAUSE A BONDING WAFER REALLY DOES TAKE FROM MANY CORE WAFERS.
An earlier shape collapsed this to one row per (bonding wafer, core lot) with DISTINCT ON.
MEASURED 2026-08-25, that was not a summary but an invention: a bonding wafer draws dies from
as many as 25 core wafers, and the collapse named one of them as if it were the source. It was
also arbitrary -- base_id, core_lot and event_time are identical across the fanned rows, so
DISTINCT ON kept whichever row the plan happened to produce, and a rerun could keep another.
Adding a tiebreak moved the count from 293 to 312, which is how the arbitrariness was caught.

Dropping the collapse fixes both, and removes code rather than adding it.

WHAT IT COSTS, PRICED BEFORE CHOOSING: 3,650 atoms instead of 312, buying zero extra closed
wafers -- closure is 150 either way. What it buys is truth. The 312-row version asserted a
single origin that was false for 3,338 of the pairs, and "one of twenty-five, chosen by the
query planner" is a worse answer than twenty-five.

⚠️ THE SLOT JOIN NEEDS BOTH SIDES IN THE SAME TYPE: `core_wafer_map` holds '02' and
`bonding_log` holds 2.0. Compared as text the join yields zero, which reads as absence rather
than as a type mismatch.

🔴 THE TIME COLUMN IS THE ONE WITH THE UNDERSCORE. `bonding_log` has both `eventtime` and
`event_time`; the first is NULL in all 380,273 rows. Choosing by resemblance empties the
source silently.

This is an INNER join, so a core lot with no map row produces no edge. That gap is counted and
printed on every run rather than left to be rediscovered as a mystery.

USAGE -- dry run by default; the gate runs before the commit either way:

    python scripts/create_bonding_core_lot_view.py
    python scripts/create_bonding_core_lot_view.py --apply --i-accept-writing-to-owner-database

ROLLBACK:

    DROP VIEW bonding_core_lot;
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

VIEW = "bonding_core_lot"
EXPECTED = 3650

SLOT_MATCH = "regexp_replace(m.core_slot::text, '\\D', '', 'g')::int = b.core_slot::int"

#: DROP then CREATE, not CREATE OR REPLACE: the column list changed (core_lot left, core_wafer
#: arrived), and Postgres refuses to replace a view whose columns differ. Both statements run
#: inside the one transaction the gate commits, so the view is never missing to anyone else.
DROP_SQL = f"DROP VIEW IF EXISTS {VIEW}"

CREATE_SQL = f"""
CREATE VIEW {VIEW} AS
SELECT DISTINCT b.base_id, m.wafer_id AS core_wafer, b.core_slot, b.event_time
FROM bonding_log b
JOIN core_wafer_map m
  ON m.core_lot = b.core_lot
 AND {SLOT_MATCH}
WHERE b.base_id IS NOT NULL AND b.core_lot IS NOT NULL"""

UNRESOLVED_SQL = f"""
SELECT count(*) FROM (
    SELECT DISTINCT b.base_id, b.core_lot FROM bonding_log b
    WHERE b.base_id IS NOT NULL AND b.core_lot IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM core_wafer_map m
                      WHERE m.core_lot = b.core_lot AND {SLOT_MATCH})) t"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '300s'"))
        try:
            source_rows = c.execute(text("SELECT count(*) FROM bonding_log")).scalar()
            c.execute(text(DROP_SQL))
            c.execute(text(CREATE_SQL))
            kept = c.execute(text(f"SELECT count(*) FROM {VIEW}")).scalar()
            no_time = c.execute(text(
                f"SELECT count(*) FROM {VIEW} WHERE event_time IS NULL")).scalar()
            wafers = c.execute(text(
                f"SELECT count(DISTINCT base_id) FROM {VIEW}")).scalar()
            worst = c.execute(text(
                f"SELECT max(n) FROM (SELECT base_id, count(*) AS n FROM {VIEW} "
                "GROUP BY 1) t")).scalar()
            unresolved = c.execute(text(UNRESOLVED_SQL)).scalar()

            print("   bonding_log rows             %8d" % source_rows)
            print("   view rows (BW x core wafer)  %8d   %s"
                  % (kept, "OK" if kept == EXPECTED else "<- expected %d" % EXPECTED))
            print("   rows with no event_time      %8d   %s"
                  % (no_time, "OK" if no_time == 0 else "<- the wrong time column"))
            print("   distinct bonding wafers      %8d   (up to %d core wafers each)"
                  % (wafers, worst))
            print("   (BW, lot) pairs UNRESOLVED   %8d   (no map row -- no edge, by design)"
                  % unresolved)

            ok = kept == EXPECTED and no_time == 0
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
