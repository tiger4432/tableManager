r"""Create `bonding_core_lot` -- one row per (bonding wafer, core lot) pair.

WHY
---
`bonding_log` records which core material was bonded onto which bonding wafer, 380,273 rows
deep. The ledger wants one atom per relationship, not one per bonded cell, so the view
collapses the log to the pairs themselves: 380,273 rows become 1,267.

That collapse is what makes the chain affordable. With a die subject the same fact costs
93,118 atoms and closes exactly the same 250 wafers; at wafer grain it costs 1,267 -- a
seventy-third of the writes for an identical answer, which is the owner's standing "the unit
is the wafer, the lot is a value".

⚠️ WHAT THE COLLAPSE COSTS, STATED RATHER THAN DISCOVERED LATER: `core_slot` is carried along
by DISTINCT ON, so where one wafer took material from several slots of the same lot, only the
earliest survives. The question this edge answers is "which lot did this come from", not
"which slot", and the surviving slot rides as a qualifier. The count of pairs that lost a
slot is printed on every run so the loss is a number and not a footnote.

🔴 THE TIME COLUMN IS THE ONE WITH THE UNDERSCORE. `bonding_log` has both `eventtime` and
`event_time`; the first is NULL in all 380,273 rows and the second is populated in all of
them. Choosing by resemblance rather than by measurement silently empties the source.

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
EXPECTED = 1267

CREATE_SQL = f"""
CREATE OR REPLACE VIEW {VIEW} AS
SELECT DISTINCT ON (base_id, core_lot)
       base_id, core_lot, core_slot, event_time
FROM bonding_log
WHERE base_id IS NOT NULL AND core_lot IS NOT NULL
ORDER BY base_id, core_lot, event_time"""

#: how many pairs had more than one slot, i.e. how much the DISTINCT ON actually dropped
SLOT_LOSS_SQL = """
SELECT count(*) FILTER (WHERE slots > 1), count(*), coalesce(max(slots), 0)
FROM (SELECT base_id, core_lot, count(DISTINCT core_slot) AS slots
      FROM bonding_log
      WHERE base_id IS NOT NULL AND core_lot IS NOT NULL
      GROUP BY 1, 2) t"""


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
            c.execute(text(CREATE_SQL))
            kept = c.execute(text(f"SELECT count(*) FROM {VIEW}")).scalar()
            no_time = c.execute(text(
                f"SELECT count(*) FROM {VIEW} WHERE event_time IS NULL")).scalar()
            lost, pairs, worst = c.execute(text(SLOT_LOSS_SQL)).fetchone()

            print("   bonding_log rows             %8d" % source_rows)
            print("   view keeps (pairs)           %8d   %s"
                  % (kept, "OK" if kept == EXPECTED else "<- expected %d" % EXPECTED))
            print("   rows with no event_time      %8d   %s"
                  % (no_time, "OK" if no_time == 0 else "<- the wrong time column"))
            print("   pairs that LOST a slot       %8d   of %d  (worst pair had %d slots)"
                  % (lost, pairs, worst))

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
