r"""Seed core-step and dt-step defect observations WITH in-chip positions.

WHY
---
`core_defect_map` and `dt_map` carry a die-grid coordinate and nothing finer, so a composite
-- the picture of where inside the chip defects land -- can only be drawn after bonding, from
`void_obs` and `delam_obs`. That leaves the screen's sharpest question unanswerable: is a hot
spot inside the chip ALREADY there at the core or dt step, or does it only appear after
bonding? The first blames an upstream process, the second blames bonding, and today the two
look identical because the upstream data has no in-chip coordinate at all.

THE FIXTURE IS A DISCRIMINATOR, NOT NOISE
------------------------------------------
Scattering in-chip positions uniformly would produce a flat composite, and a flat composite
cannot be told apart from a broken view. So each step gets its OWN hot spot in a different
corner of the die:

    core step   concentrated in the chip's upper-left cell
    dt step     concentrated in the chip's lower-right cell
    void (already live, measured by the lead)  one 5x5 cell at 2.19x

Three composites side by side must therefore look DIFFERENT. If they look alike, the view is
broken -- and that is a conclusion this fixture makes reachable, which uniform noise would not.

SHAPE
-----
The subject columns are the ledger's `die@1` key (mat_type, mat_id, x, y) and the step is a
VALUE, so a third step later costs one row's worth of vocabulary rather than a table. `mat_id`
is spelled with `map_overlay.compose_map_id`, the same function the map composes frame ids
with, so a die here and a cell on the map name the same material rather than two spellings of
it.

USAGE - dry run by default:

    python scripts/seed_syn_step_defects.py
    python scripts/seed_syn_step_defects.py --apply --i-accept-writing-to-owner-database

ROLLBACK - one namespace, two lines:

    DELETE FROM step_defect_obs     WHERE mat_id LIKE 'SYN-AUG-%';
    DELETE FROM step_inspection_run WHERE mat_id LIKE 'SYN-AUG-%';
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
import map_overlay                                                   # noqa: E402
import seed_syn_aug_material as aug                                  # noqa: E402

STEPS = (
    # step, lot format, lot column, slot column, hot-spot cell in a 5x5 chip grid
    ("core", aug.CORE_LOT_FMT, "core_lot", "core_slot", (0, 0)),
    ("dt", aug.DT_LOT_FMT, "dt_lot", "dt_slot", (4, 4)),
)
INCHIP_SPAN = 12000.0          # same span `void_obs` uses, so the bins line up
GRID = 5                       # the composite's cell count per axis
HOT_SHARE = 0.55               # of a step's defects, this fraction lands in its hot cell
INSPECT_SHARE = 0.60
DEFECT_RATE = 0.28
EXTENT = (6.0, 18.0)           # FULL widths, um
SEED = 20260824
BASE_DAY = "2026-07-12"

#: This script's namespace, as (table, predicate). The door deletes BY ID, so the predicate
#: is resolved first - an outbox event names the rows it is about, and an unexpanded
#: predicate would produce an event nobody can resolve (S-78, ruling 181).
OWNED = (
    ("step_defect_obs", "mat_id LIKE 'SYN-AUG-%'"),
    ("step_inspection_run", "mat_id LIKE 'SYN-AUG-%'"),
)


def _clear_owned(connection, url, log=print):
    """Remove this script's namespace through the door. Returns rows removed."""
    removed = 0
    for table, where in OWNED:
        ids = [r[0] for r in connection.execute(
            text("SELECT row_id FROM %s WHERE %s" % (table, where))).fetchall()]
        if not ids:
            continue
        log("   clearing %-22s %6d rows" % (table, len(ids)))
        product_door.delete_rows(table, ids, base_url=url,
                                 user_name=SOURCE_NAME, log=lambda *_: None)
        removed += len(ids)
    return removed


import product_door

#: The layer name these rows land under, so the set is attributable and removable.
SOURCE_NAME = "seed_syn_step_defects"


def _stamp(days, minutes):
    from datetime import datetime, timedelta
    return (datetime.fromisoformat(BASE_DAY + "T03:00:00+09:00")
            + timedelta(days=days, minutes=minutes)).isoformat()


def _inchip(rng, hot):
    """A position inside the die: mostly in this step's hot cell, the rest spread out."""
    cell = INCHIP_SPAN / GRID
    if rng.random() < HOT_SHARE:
        cx, cy = hot
    else:
        cx, cy = rng.randrange(GRID), rng.randrange(GRID)
    return (round(cx * cell + rng.uniform(0, cell), 2),
            round(cy * cell + rng.uniform(0, cell), 2))


def build():
    rng = random.Random(SEED)
    grid = aug.cells()
    runs, obs = [], []
    day = 0
    for step, lot_fmt, lot_col, slot_col, hot in STEPS:
        for lot in aug.LOTS:
            lot_id = lot_fmt % lot
            for slot in aug.SLOTS:
                slot_v = float(slot)
                mat_id = map_overlay.compose_map_id(
                    [lot_col, slot_col], {lot_col: lot_id, slot_col: slot_v},
                    {"table": "bonding_log"})
                looked = rng.sample(grid, int(len(grid) * INSPECT_SHARE))
                for n, (x, y) in enumerate(sorted(looked)):
                    at = _stamp(day, n)
                    run_uid = "%s|%s|%d|%d|%s" % (step, mat_id, x, y, at)
                    runs.append({
                        "row_id": str(uuid6.uuid7()),
                        "business_key_val": run_uid, "run_uid": run_uid, "step": step,
                        "mat_type": "Wafer", "mat_id": mat_id,
                        "x": float(x), "y": float(y),
                        "recipe_id": "SYN_%s_R1" % step.upper(),
                        "eqp_id": "SYN-%s-0%d" % (step.upper(), (slot % 3) + 1),
                        "observed_at": at})
                    if rng.random() >= DEFECT_RATE:
                        continue
                    ix, iy = _inchip(rng, hot)
                    obs_uid = "%s|%s|%s" % (run_uid, ix, iy)
                    obs.append({
                        "row_id": str(uuid6.uuid7()),
                        "business_key_val": obs_uid, "obs_uid": obs_uid,
                        "run_uid": run_uid, "step": step,
                        "mat_type": "Wafer", "mat_id": mat_id,
                        "x": float(x), "y": float(y),
                        "inchip_x": ix, "inchip_y": iy,
                        "extent_x": round(rng.uniform(*EXTENT), 3),
                        "extent_y": round(rng.uniform(*EXTENT), 3),
                        "unit": "um", "val": "F"})
                day += 1
    return [("step_inspection_run", runs), ("step_defect_obs", obs)]


def _put(table, rows, url, log=print):
    """Write one table's rows through the product door.

    No `row_id` is minted here: the engine mints it and ruling 150 refuses a supplied id
    that is not a uuid7. Every row already carries `business_key_val`.
    """
    if not rows:
        return 0
    items = []
    for row in rows:
        values = dict(row)
        items.append(product_door.row_item(
            values.pop("business_key_val"), values, source_name=SOURCE_NAME))
    result = product_door.put_rows(table, items, base_url=url, log=lambda *_: None)
    log("   wrote    %-22s %6d rows in %d request(s)"
        % (table, result["rows"], result["requests"]))
    return result["rows"]


def _composite(connection, step):
    """The 5x5 in-chip picture this step produces, as counts. The discriminator itself."""
    rows = connection.execute(text(f"""
        SELECT floor(inchip_x / {INCHIP_SPAN / GRID})::int AS cx,
               floor(inchip_y / {INCHIP_SPAN / GRID})::int AS cy, count(*)
        FROM step_defect_obs WHERE step = :s AND mat_id LIKE 'SYN-AUG-%'
        GROUP BY 1, 2"""), {"s": step}).fetchall()
    cell = {(r[0], r[1]): r[2] for r in rows}
    total = sum(cell.values()) or 1
    peak = max(cell.items(), key=lambda kv: kv[1]) if cell else ((None, None), 0)
    mean = total / float(GRID * GRID)
    print("   %-5s total %5d   peak cell %s = %d  (%.2fx the mean)"
          % (step, total, peak[0], peak[1], peak[1] / mean if mean else 0))
    for cy in range(GRID):
        print("        " + " ".join("%4d" % cell.get((cx, cy), 0) for cx in range(GRID)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    ap.add_argument("--url", default=product_door.DEFAULT_BASE_URL,
                    help="server base url the rows are written through")
    args = ap.parse_args(argv)

    plan = build()
    print("planned rows:")
    for table, rows in plan:
        print("   %-22s %6d" % (table, len(rows)))

    # ⚠️ THE DRY RUN NO LONGER REHEARSES, and that is a real loss stated rather than hidden.
    # It used to insert inside a transaction, print the composite computed from the
    # SIMULATED rows, and roll back. Writes through the door commit on the server, so a
    # rehearsal is not available: this stops before the door and prints the plan only.
    if not (args.apply and args.allow_owner):
        print("\nDRY RUN - nothing written. The composite is computed from rows in the"
              " database,\nso it can only be shown after a real write; add --apply"
              " --i-accept-writing-to-owner-database.")
        return 0

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '300s'"))
        print("")
        _clear_owned(c, args.url)

    for table, rows in plan:
        _put(table, rows, args.url)

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '300s'"))
        print("\ncomposite per step (this is the discriminator):")
        for step, *_ in STEPS:
            _composite(c, step)
    print("\nCOMMITTED through the product door.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
