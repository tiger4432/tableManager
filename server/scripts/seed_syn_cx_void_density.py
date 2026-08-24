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

INSERT = """
INSERT INTO void_obs (row_id, business_key_val, void_uid, run_uid, base_wafer_id,
                      base_x, base_y, stack_gate, inchip_x, inchip_y,
                      radius_x, radius_y, unit, work_id)
VALUES (:row_id, :void_uid, :void_uid, :run_uid, :base_wafer_id,
        :base_x, :base_y, :stack_gate, :inchip_x, :inchip_y,
        :radius_x, :radius_y, 'um', :work_id)"""


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
    args = ap.parse_args(argv)
    rng = random.Random(SEED)

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '300s'"))
        try:
            before = _counts(c)
            print("BEFORE  %s cells %d voids %d | %s rows %d | view %d"
                  % (WAFER, before["cells"], before["voids"], GATE_WAFER,
                     before["gate_wafer_rows"], before["view"]))

            c.execute(text("DELETE FROM void_obs WHERE work_id = :m"), {"m": MARK})
            free = _cells(c)
            need = TARGET_CELLS - before["cells"]
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
            for i in range(0, len(rows), 500):
                c.execute(text(INSERT), rows[i:i + 500])
            print("inserted %d void rows across %d cells" % (len(rows), len(chosen)))

            after = _counts(c)
            print("\nAFTER (uncommitted)")
            print("   %s cells %d -> %d   voids %d -> %d"
                  % (WAFER, before["cells"], after["cells"], before["voids"], after["voids"]))
            print("   %s rows %d -> %d" % (GATE_WAFER, before["gate_wafer_rows"],
                                           after["gate_wafer_rows"]))
            print("   view %d -> %d   void_obs %d -> %d"
                  % (before["view"], after["view"], before["void_obs"], after["void_obs"]))

            checks = {
                "cell count reaches %d" % TARGET_CELLS: after["cells"] == TARGET_CELLS,
                "%s untouched" % GATE_WAFER:
                    after["gate_wafer_rows"] == before["gate_wafer_rows"],
                "join still total (view == void_obs)": after["view"] == after["void_obs"],
                "view grew by exactly the insert":
                    after["view"] - before["view"] == len(rows),
            }
            for name, ok in checks.items():
                print("   %-38s %s" % (name, "OK" if ok else "FAIL"))
            passed = all(checks.values())
            print("\nGATE: %s" % ("PASS" if passed else "FAIL"))

            if passed and args.apply and args.allow_owner:
                c.commit()
                print("COMMITTED.  Rollback: DELETE FROM void_obs WHERE work_id = '%s';" % MARK)
            else:
                c.rollback()
                print("ROLLED BACK." if not passed else "DRY RUN - rolled back.")
                return 0 if passed else 1
        except Exception:
            c.rollback()
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
