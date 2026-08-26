r"""Create `bonding_die_from_core` -- the rows of `bonding_core_die` that actually name a core die.

🔴 WHY A SECOND RELATION, MEASURED RATHER THAN GUESSED. The report left one thing undecided:
what the framework does with a mapping whose target keys are NULL on most rows. The dry run
answered it before anything was written:

    SourcePreparationError: event_frame.rows[0].core_wafer:
        entity identity value is missing after preparation

That is not a per-molecule refusal and not a skipped mapping -- preparation raises and the whole
SOURCE stops, so keeping both facts on one relation would take the DT-seat edges down with the
core ones. The Lead PM wrote the branch in advance: split the relation, and let `bonded_from`
read one that is filtered to rows carrying a core wafer.

    bonding_core_die       371,593   every bonded die   -> the DT-seat fact (transfer@1)
    bonding_die_from_core   18,545   those with a core  -> the lineage fact (bonded_from@1)

🔴 THE CORE SEGMENT CLOSES AT 5%, NOT 25%. 93,118 rows name a core lot and slot, but only 18,545
resolve to a wafer: 529 of the 657 (core_lot, core_slot) pairs have no row in `core_wafer_map`.
Reading it as 25% would send someone hunting a defect that is really absent source data.

⚠️ NOTHING IS FOLDED. This is a WHERE over the existing view, so a row here is the same one die
it is there; the gate checks that the count matches the view's own non-null count exactly.

USAGE -- dry run by default; the gate runs before the commit either way:

    python scripts/create_bonding_die_from_core_view.py
    python scripts/create_bonding_die_from_core_view.py --apply --i-accept-writing-to-owner-database

ROLLBACK:

    DROP VIEW bonding_die_from_core;
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

VIEW = "bonding_die_from_core"
SOURCE = "bonding_core_die"
EXPECTED = 18545

DROP_SQL = f"DROP VIEW IF EXISTS {VIEW}"
CREATE_SQL = f"""
CREATE VIEW {VIEW} AS
SELECT base_id, bx, by, core_wafer, cx, cy, core_seat, core_lot, core_slot, event_time
FROM {SOURCE}
WHERE core_wafer IS NOT NULL AND cx IS NOT NULL AND cy IS NOT NULL"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '300s'"))
        try:
            base = c.execute(text(f"SELECT count(*) FROM {SOURCE}")).scalar()
            expect = c.execute(text(
                f"SELECT count(*) FROM {SOURCE} WHERE core_wafer IS NOT NULL "
                "AND cx IS NOT NULL AND cy IS NOT NULL")).scalar()
            c.execute(text(DROP_SQL))
            c.execute(text(CREATE_SQL))
            kept = c.execute(text(f"SELECT count(*) FROM {VIEW}")).scalar()
            dies = c.execute(text(
                f"SELECT count(*) FROM (SELECT DISTINCT base_id, bx, by, core_wafer, cx, cy "
                f"FROM {VIEW}) t")).scalar()
            wafers = c.execute(text(f"SELECT count(DISTINCT core_wafer) FROM {VIEW}")).scalar()
            no_time = c.execute(text(
                f"SELECT count(*) FROM {VIEW} WHERE event_time IS NULL")).scalar()
            seed = c.execute(text(
                f"SELECT count(DISTINCT core_wafer) FROM {VIEW} "
                "WHERE base_id = 'SYN-BW-101-16'")).scalar()

            print("   %-28s %8d" % (SOURCE, base))
            print("   rows with a core die         %8d" % expect)
            print("   view rows                    %8d   %s"
                  % (kept, "OK" if kept == expect else "<- the WHERE lost rows"))
            print("   expected (measured earlier)  %8d   %s"
                  % (EXPECTED, "OK" if kept == EXPECTED else "<- moved since"))
            print("   distinct (bonded die, core die) %5d   %s"
                  % (dies, "OK - a row IS a pair" if dies == kept else "<- rows collide"))
            print("   distinct core wafers         %8d" % wafers)
            print("   rows with no event_time      %8d   %s"
                  % (no_time, "OK" if no_time == 0 else "<- no time on the edge"))
            print("   SYN-BW-101-16 -> core wafers %8d   %s"
                  % (seed, "OK - the owner's 29" if seed == 29 else "<- the gate wants 29"))

            ok = (kept == expect and kept == EXPECTED and dies == kept
                  and no_time == 0 and seed == 29)
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
