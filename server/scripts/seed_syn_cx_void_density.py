r"""Give SYN-CX-BW-001 a void map dense enough to exercise the screen.

🔴 THIS IS A FIXTURE FOR THE SCREEN, NOT A REPRODUCTION OF PROCESS REALITY.
Neither density here is a fact about manufacturing. SYN-CX-BW-001 sits at a 3.5% hit rate
and SYN-BW-103-11 at 485% (multiple voids per cell) because each was GENERATED that way.
The reason for this round is not "9 cells is too few to be realistic" -- it is that A NINE
CELL MAP CANNOT EXERCISE A MAP: hot spots, cell shading, marking a region and walking its
subgraph all need a populated grid to show anything at all. Read the two rates as fixture
settings. They are not a process difference, and reading them as one was a mistake the lead
and I each nearly made.

WHY NO NEW INSPECTIONS ARE CREATED
----------------------------------
The obvious implementation adds inspection_run rows alongside the voids, because
`void_obs_observed` is an INNER join and a void with no run would vanish from it. Measured
first, and the assumption was wrong in a useful direction: SYN-CX-BW-001 already carries 256
inspections over 128 distinct cells -- more than the mockup wafer's 41 over 38. The looks are
not missing; the hits are. So voids hang off the runs that already exist and this script
creates NO inspection rows. The denominator ("scanned") is left exactly as it was, which also
keeps the map's control axis honest.

SHAPE -- copied from a real row on this wafer, not invented:
    void_uid = 'sat|<wafer>|<x>|<y>|<gate>|<iso ts>|<inchip_x>|<inchip_y>'
    run_uid  = the existing inspection's, verbatim
Per-cell counts follow the mockup wafer's own distribution (3-11 voids per cell, mostly 6-7).

USAGE -- dry run by default; the gate runs BEFORE the commit either way:

    python scripts/seed_syn_cx_void_density.py
    python scripts/seed_syn_cx_void_density.py --apply --i-accept-writing-to-owner-database

ROLLBACK -- one predicate, and it cannot reach anybody else's rows:

    DELETE FROM void_obs WHERE work_id = 'SYN-DENSITY-20260824';
"""
import argparse
import os
import random
import sys

import uuid6

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import text                                          # noqa: E402
from database import database as db                                  # noqa: E402

WAFER = "SYN-CX-BW-001"
#: 🔴 The gate wafer. Today's baselines (point 208, void 199, delam 9) are all measured on it,
#: so a single row landing here would silently invalidate three lanes' reference numbers.
GATE_WAFER = "SYN-BW-103-11"
MARK = "SYN-DENSITY-20260824"
TARGET_CELLS = 28
#: the mockup wafer's own per-cell distribution, measured
PER_CELL = (3, 4, 4, 4, 5, 6, 6, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 8, 8, 8, 9, 9, 10, 10,
            11, 11, 11)
INCHIP_SPAN = 12000.0
RADIUS = (4.0, 12.0)
SEED = 20260824

#: 🔴 THE INSERT STATEMENT IS GONE (S-78, ruling 181). Rows go through the product door so
#: they carry an envelope; a statement issued here left the fold blind to them and left no
#: `write⁻¹`. `business_key_val` was `void_uid` in that statement and still is - the door
#: resolves or creates on it.
CLEAR_WHERE = "work_id = :mark"


import product_door

#: The layer name these rows land under, so the set is attributable and removable.
SOURCE_NAME = "seed_syn_cx_void_density"

def _clear_own(connection, url, log=print):
    """Remove this script's own rows through the door, and report how many.

    Used twice: before writing, and as the COMPENSATION when the gate refuses what was
    written. Exact both times because `work_id = MARK` is this script's namespace.
    """
    ids = [r[0] for r in connection.execute(
        text("SELECT row_id FROM void_obs WHERE " + CLEAR_WHERE), {"mark": MARK}).fetchall()]
    if ids:
        product_door.delete_rows("void_obs", ids, base_url=url,
                                 user_name=SOURCE_NAME, log=lambda *_: None)
    return len(ids)


def _cells(connection):
    """Inspected cells with no void yet, plus the run and gate to hang new ones on."""
    return connection.execute(text("""
        SELECT r.base_x, r.base_y, min(r.run_uid), min(r.stack_gate)
        FROM inspection_run r
        WHERE r.base_wafer_id = :w
          AND NOT EXISTS (SELECT 1 FROM void_obs v
                          WHERE v.base_wafer_id = r.base_wafer_id
                            AND v.base_x = r.base_x AND v.base_y = r.base_y)
        GROUP BY 1, 2 ORDER BY 1, 2"""), {"w": WAFER}).fetchall()


def _counts(connection):
    cells = connection.execute(text("""SELECT count(DISTINCT (base_x, base_y)), count(*)
        FROM void_obs WHERE base_wafer_id = :w"""), {"w": WAFER}).fetchone()
    gate = connection.execute(text("SELECT count(*) FROM void_obs WHERE base_wafer_id = :w"),
                              {"w": GATE_WAFER}).scalar()
    view = connection.execute(text("SELECT count(*) FROM void_obs_observed")).scalar()
    rows = connection.execute(text("SELECT count(*) FROM void_obs")).scalar()
    return {"cells": cells[0], "voids": cells[1], "gate_wafer_rows": gate,
            "view": view, "void_obs": rows}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    ap.add_argument("--url", default=product_door.DEFAULT_BASE_URL,
                    help="server base url the rows are written through")
    args = ap.parse_args(argv)
    rng = random.Random(SEED)

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '300s'"))
        try:
            before = _counts(c)
            print("BEFORE  %s cells %d voids %d | %s rows %d | view %d"
                  % (WAFER, before["cells"], before["voids"], GATE_WAFER,
                     before["gate_wafer_rows"], before["view"]))

            # 🔴 THE DRY RUN MUST NOT REACH THE DOOR. Writes through it commit on the
            # server, so what used to be an inspectable rehearsal inside a transaction
            # would now be the real thing - the first version of this conversion did
            # exactly that and only a smoke test caught it. The dry run stops here with
            # the BEFORE numbers; the gate that used to decide the commit now runs after
            # the write and compensates (ruling 181).
            if not (args.apply and args.allow_owner):
                print("\nDRY RUN - nothing written. Writes go through the product door and"
                      " commit, so this run cannot rehearse them; add --apply"
                      " --i-accept-writing-to-owner-database.")
                return 0

            # 🔴 CLEAR OWN ROWS FIRST, THEN TAKE THE BASELINE. Sizing the insert from the
            # PRE-clear count made the script destroy its own fixture: run it a second time
            # and `before["cells"]` was already 28, so it deleted the 19 it had added, asked
            # for 28-28 = 0 more, and failed its own gate at 9. A seeder that cannot be run
            # twice is not a reproduction path, which is the one thing committing it claimed.
            _clear_own(c, args.url)
            baseline = _counts(c)
            free = _cells(c)
            need = TARGET_CELLS - baseline["cells"]
            if need > len(free):
                raise SystemExit("only %d free inspected cells, need %d" % (len(free), need))
            chosen = rng.sample(free, need) if need > 0 else []
            print("free inspected cells %d, taking %d" % (len(free), need))

            rows = []
            for index, (bx, by, run_uid, gate) in enumerate(sorted(chosen)):
                stamp = str(run_uid).split("|")[-1]
                for _ in range(PER_CELL[index % len(PER_CELL)]):
                    ix = round(rng.uniform(0, INCHIP_SPAN), 2)
                    iy = round(rng.uniform(0, INCHIP_SPAN), 2)
                    rows.append({
                        "row_id": str(uuid6.uuid7()),
                        "void_uid": "sat|%s|%g|%g|%g|%s|%g|%g"
                                    % (WAFER, bx, by, gate or 0, stamp, ix, iy),
                        "run_uid": run_uid, "base_wafer_id": WAFER,
                        "base_x": bx, "base_y": by, "stack_gate": gate,
                        "inchip_x": ix, "inchip_y": iy,
                        "radius_x": round(rng.uniform(*RADIUS), 2),
                        "radius_y": round(rng.uniform(*RADIUS), 2),
                        "work_id": MARK})
            items = []
            for row in rows:
                values = dict(row)
                values.pop("row_id", None)      # the engine mints it (ruling 150)
                items.append(product_door.row_item(
                    values["void_uid"], values, source_name=SOURCE_NAME))
            product_door.put_rows("void_obs", items, base_url=args.url,
                                  log=lambda *_: None)
            print("wrote %d void rows across %d cells through the door"
                  % (len(rows), len(chosen)))

            after = _counts(c)
            print("\nAFTER (uncommitted)")
            print("   %s cells %d (own rows cleared -> %d) -> %d   voids %d -> %d"
                  % (WAFER, before["cells"], baseline["cells"], after["cells"],
                     before["voids"], after["voids"]))
            print("   %s rows %d -> %d" % (GATE_WAFER, before["gate_wafer_rows"],
                                           after["gate_wafer_rows"]))
            print("   view %d -> %d   void_obs %d -> %d"
                  % (before["view"], after["view"], before["void_obs"], after["void_obs"]))

            checks = {
                "cell count reaches %d" % TARGET_CELLS: after["cells"] == TARGET_CELLS,
                "%s untouched" % GATE_WAFER:
                    after["gate_wafer_rows"] == before["gate_wafer_rows"],
                "join still total (view == void_obs)": after["view"] == after["void_obs"],
                # measured from the POST-clear baseline, so re-running compares like with like
                "view grew by exactly the insert":
                    after["view"] - baseline["view"] == len(rows),
            }
            for name, ok in checks.items():
                print("   %-38s %s" % (name, "OK" if ok else "FAIL"))
            passed = all(checks.values())
            print("\nGATE: %s" % ("PASS" if passed else "FAIL"))

            # 🔴 COMPENSATION, NOT ROLLBACK (ruling 181). The rows are committed through
            # the door and their atoms exist; what undoes them is another write through it.
            if passed:
                print("COMMITTED through the door.  Undo: this script's own clear, or"
                      " DELETE the work_id namespace by id through /rows/batch_delete.")
            else:
                print("GATE FAILED - compensating: withdrawing this run's rows.")
                _clear_own(c, args.url)
                print("compensated. The ledger keeps both events - written, then withdrawn.")
                print("ROLLED BACK." if not passed else "DRY RUN - rolled back.")
                return 0 if passed else 1
        except Exception:
            c.rollback()
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
