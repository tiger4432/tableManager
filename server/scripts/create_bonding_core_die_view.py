r"""Create `bonding_core_die` -- one row per bonded DIE, with the DT lot-slot seat it came from.

🔴 WHY THIS EXISTS: `bonded_from` binds wafer -> wafer, so the owner's target walk cannot even
start. Its relation `bonding_core_lot` is a four-column DISTINCT over `bonding_log` that
collapses 380,273 rows to 3,650 and never selects x or y -- the coordinates the walk needs are
dropped before the declaration ever sees them. The fix belongs in the relation: the material is
already in `bonding_log`, only the projection was narrow.

    bonding_log      380,273 rows   base_id + bx,by   dt_lot,dt_slot + dt_x,dt_y   cx,cy
    bonding_core_lot   3,650 rows   base_id, core_wafer, core_slot, event_time     (no x,y)

🔴 ONE ROW IS ONE DIE, AND THAT IS THE CONTRACT. No DISTINCT, no GROUP BY. Measured 2026-08-26:
371,593 rows pass the predicate and there are 371,593 distinct (base_id, bx, by) -- the rows are
already one per die, so any folding here would be inventing, exactly as the collapse in
`bonding_core_lot` did. The (subject die, target die) pair is likewise unique 371,593/371,593.

🔴 `core_wafer_map` IS NOT JOINED. Measured: the same LEFT JOIN the lot view uses fans 371,593
rows out to 6,444,693 -- roughly seventeen map rows per (core_lot, core_slot). The lot view can
afford that because it folds with DISTINCT afterwards; here folding is forbidden, so the join
would multiply every die by seventeen. The core side travels as `core_lot`/`core_slot`/`cx`/`cy`
straight off `bonding_log` instead, and the `dt_job -> core` segment is already served by
`dt_transfer / core-die-to-dt-die`.

WHAT IS FILTERED AND WHY HERE: rows missing any of the seven key columns are excluded. A v5
`read` declares only unit/identity/group_by/order_by/occurred_at -- there is no filter axis --
so a null-keyed row would become an atom with a null key. The relation is the only place this
can be said.

    380,273 in the log
    371,593 with base_id, bx, by, dt_lot, dt_slot, dt_x, dt_y all present   <- the view
      8,680 dropped for a missing key
     93,118 of the kept rows also carry cx, cy (24.5% -- the core segment closes that far)

🔴 `dt_seat` IS COMPOSED HERE, NOT IN THE DECLARATION. `die@1` keys on a single `mat_id`, and
the working die bindings (`dt_transfer / core-die-to-dt-die`) show the grammar only offers
`{kind: column}` and `{kind: constant}` -- there is no concat. So the seat's identity
`dt_lot|dt_slot` is a column the relation provides, the same way the relation provides
everything else the binding names.

⚠️ THE TIME COLUMN IS THE ONE WITH THE UNDERSCORE. `bonding_log` has `eventtime` and
`event_time`; the first is NULL in all 380,273 rows, and choosing by resemblance empties the
source silently. Measured here: 0 kept rows have a null `event_time`.

⚠️ `bonding_core_lot` IS LEFT ALONE. It still feeds today's wafer-level `bonded_from` and is the
place to roll back to.

USAGE -- dry run by default; the gate runs before the commit either way:

    python scripts/create_bonding_core_die_view.py
    python scripts/create_bonding_core_die_view.py --apply --i-accept-writing-to-owner-database

ROLLBACK:

    DROP VIEW bonding_core_die;
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

VIEW = "bonding_core_die"
EXPECTED = 371593

#: The seven columns a die-to-die edge needs on both ends, plus the time it happened.
KEYS_PRESENT = """b.base_id IS NOT NULL AND b.bx IS NOT NULL AND b.by IS NOT NULL
      AND b.dt_lot IS NOT NULL AND b.dt_slot IS NOT NULL
      AND b.dt_x IS NOT NULL AND b.dt_y IS NOT NULL"""

DROP_SQL = f"DROP VIEW IF EXISTS {VIEW}"

CREATE_SQL = f"""
CREATE VIEW {VIEW} AS
SELECT b.base_id, b.bx, b.by,
       b.dt_lot, b.dt_slot, b.dt_x, b.dt_y,
       b.dt_lot || '|' || b.dt_slot AS dt_seat,
       b.core_lot, b.core_slot, b.cx, b.cy,
       b.event_time
FROM bonding_log b
WHERE {KEYS_PRESENT}"""


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
            dies = c.execute(text(
                f"SELECT count(*) FROM (SELECT DISTINCT base_id, bx, by FROM {VIEW}) t")).scalar()
            pairs = c.execute(text(
                f"SELECT count(*) FROM (SELECT DISTINCT base_id, bx, by, dt_lot, dt_slot, "
                f"dt_x, dt_y FROM {VIEW}) t")).scalar()
            no_time = c.execute(text(
                f"SELECT count(*) FROM {VIEW} WHERE event_time IS NULL")).scalar()
            with_core = c.execute(text(
                f"SELECT count(*) FROM {VIEW} WHERE cx IS NOT NULL AND cy IS NOT NULL")).scalar()
            seats = c.execute(text(
                f"SELECT count(*) FROM (SELECT DISTINCT dt_lot, dt_slot FROM {VIEW}) t")).scalar()

            print("   bonding_log rows             %8d" % source_rows)
            print("   view rows (one per die)      %8d   %s"
                  % (kept, "OK" if kept == EXPECTED else "<- expected %d" % EXPECTED))
            print("   dropped for a missing key    %8d" % (source_rows - kept))
            print("   distinct (base_id,bx,by)     %8d   %s"
                  % (dies, "OK - a row IS a die" if dies == kept else "<- rows are NOT one per die"))
            print("   distinct (base die, dt die)  %8d   %s"
                  % (pairs, "OK - no pair collides" if pairs == kept else "<- pairs collide"))
            print("   rows with no event_time      %8d   %s"
                  % (no_time, "OK" if no_time == 0 else "<- the wrong time column"))
            print("   distinct (dt_lot, dt_slot)   %8d   (the DTLotSlot seats)" % seats)
            print("   rows carrying cx,cy          %8d   (%.1f%% - how far the core segment closes)"
                  % (with_core, 100.0 * with_core / kept if kept else 0))

            ok = kept == EXPECTED and dies == kept and pairs == kept and no_time == 0
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
