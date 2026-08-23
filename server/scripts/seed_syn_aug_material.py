r"""Seed a SEPARATE material set so the board has enough to judge, without touching the old.

WHY A NEW SET AND NOT MORE ROWS ON THE OLD ONE
-----------------------------------------------
The board draws thirteen findings on one screen, so its trend flattens, its ranking ties and
its candidate map is empty. MEASURED 2026-08-24 on `SYN-BW-001-07`: 141 bonded cells, 30
positions ever inspected, 14 carrying a void. The ceiling is the INSPECTION, not the process
row -- adding bonding rows adds denominator and moves the ratio the wrong way.

Filling the existing lots is what the owner's ruling rejected, and the reason is in
`seed_syn_world`'s own docstring: `seed_syn_lot_excursion --prove` scores every lot against
the LIVE MEDIAN, and the planted lots clear the first threshold by as little as 4.8%. Raising
the old lots' rates un-plants them and breaks a screen this round never touches. So this
writes a new namespace and leaves every existing row alone.

THE THREE CONSTRAINTS THIS FIXTURE IS SHAPED BY, ALL MEASURED FIRST
--------------------------------------------------------------------
  1. THE MEDIAN IS ROBUST, so the lot count is not the limit. Twenty added lots move the
     baseline by at most 0.9% and sixty never un-plant one, at any level tried.

  2. THE DATE IS THE REAL LIMIT. The same prove also asserts the planted lots are the LATEST
     THREE by inspection time, and they sit in late November 2026 -- ahead of today. Anything
     dated after 2026-11-22 04:31 breaks that assertion no matter what the median does.
     These rows are dated in the recent past, which ALSO puts them inside the trend's default
     window where the November rows do not reach. One choice satisfies both.

  3. NEW LOTS MUST NOT CROSS THE FIRST THRESHOLD, or the prove's other assertion fails
     ("no unplanted lot lights up"). Baselines are per_chip 1.2207 and extent_mean 58.64, so
     these lots aim at roughly one void per found chip and a modest extent. The ranking still
     splits, because it only needs the NEW lots to differ FROM EACH OTHER.

GEOMETRY IS BORROWED, NEVER RESPELLED. `seed_syn_void_base_join.occupied_cells` owns "which
cells exist"; a second spelling of a coordinate rule is how two screens come to disagree about
where a die is.

USAGE - dry run by default, and the owner's database has to be said out loud:

    python scripts/seed_syn_aug_material.py
    python scripts/seed_syn_aug_material.py --apply --i-accept-writing-to-owner-database

The dry run INSERTS INSIDE A TRANSACTION AND ROLLS BACK, then scores the result with the
excursion prove's own `lot_table`, so the numbers it prints are the numbers `--apply` lands --
not an estimate of them.

ROLLBACK - one predicate per table, all on the namespace this script owns:

    DELETE FROM void_obs        WHERE base_wafer_id LIKE 'SYN-AUG-%';
    DELETE FROM inspection_run  WHERE base_wafer_id LIKE 'SYN-AUG-%';
    DELETE FROM bonding_log     WHERE bond_lot      LIKE 'SYN-AUG-%';
    DELETE FROM core_defect_map WHERE lot           LIKE 'SYN-AUG-%';
    DELETE FROM bonding_map     WHERE base          LIKE 'SYN-AUG-%';
    DELETE FROM wafer_map_metadata WHERE map_id     LIKE 'SYN-AUG-%';
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
import seed_syn_void_base_join as vbj                                # noqa: E402

PREFIX = "SYN-AUG-"
BOND_LOT_FMT = PREFIX + "%03d"
WAFER_FMT = PREFIX + "BW-%03d-%02d"
CORE_LOT_FMT = PREFIX + "CL-%03d"
DT_LOT_FMT = PREFIX + "DT-%03d"

LOTS = (1, 2, 3, 4, 5, 6)
SLOTS = (1, 2, 3, 4, 5)

#: Inspected share of a wafer's cells. The round's criterion is 40%+; 60% leaves headroom
#: so the number survives the cells that carry no void.
INSPECT_SHARE = 0.60

#: Per-lot void rate among INSPECTED positions. Deliberately unequal: the ranking is only
#: worth looking at if the lots differ from each other, and the owner's third criterion is
#: exactly that the marked and control sides come apart.
VOID_RATE = {1: 0.12, 2: 0.18, 3: 0.24, 4: 0.30, 5: 0.36, 6: 0.42}

#: Baselines MEASURED 2026-08-24; the first threshold is x2.0, so these stay well under.
PER_CHIP_TARGET = 1.15          # voids per found chip (baseline 1.2207, ceiling 2.44)
RADIUS = (7.4, 7.9)             # radius_x * radius_y ~ 58 (baseline 58.64, ceiling 117.3)

#: Inside the trend's default window AND months before the planted lots (2026-11-22).
BASE_DAY = "2026-07-05"
STACK_GATE = 7.0
RECIPES = ("SYN_VOID_R1", "SYN_VOID_R2", "SYN_VOID_R3")
EQPS = ("SYN-SAT-01", "SYN-SAT-02", "SYN-SAT-03")
BOND_EQPS = ("SYN-BD-01", "SYN-BD-02", "SYN-BD-03")
SEED = 20260824


def _wafer_meta():
    """The frame the existing SYN wafers are drawn on, read from the void seeder."""
    return vbj.WAFER_SPEC


def cells():
    return vbj.occupied_cells(_wafer_meta())


def _stamp(day_offset, minute):
    from datetime import datetime, timedelta, timezone
    base = datetime.fromisoformat(BASE_DAY + "T02:00:00+09:00")
    return (base + timedelta(days=day_offset, minutes=minute)).isoformat()


def build():
    """Every row this script would write, as (table, [dict, ...]). Pure."""
    rng = random.Random(SEED)
    grid = cells()
    bonding, runs, voids, defects = [], [], [], []
    day = 0
    for lot in LOTS:
        bond_lot = BOND_LOT_FMT % lot
        core_lot = CORE_LOT_FMT % lot
        dt_lot = DT_LOT_FMT % lot
        rate = VOID_RATE[lot]
        for slot in SLOTS:
            wafer = WAFER_FMT % (lot, slot)
            slot_s = "%02d" % slot
            inspected = rng.sample(grid, int(len(grid) * INSPECT_SHARE))
            for index, (x, y) in enumerate(grid):
                bonding.append({
                    "business_key_val": "%s_%s_%d_%d" % (bond_lot, slot_s, x, y),
                    "bond_cell_key": "%s_%s_%d_%d" % (bond_lot, slot_s, x, y),
                    "base_id": wafer, "bx": float(x), "by": float(y),
                    "bond_lot": bond_lot, "bond_slot": slot_s,
                    "bond_x": float(x), "bond_y": float(y),
                    "b_bn": "1", "stack_height": 10.0,
                    "dt_lot": dt_lot, "dt_slot": float(slot),
                    "dt_x": float(index % 15), "dt_y": float(index // 15),
                    "core_lot": core_lot, "core_slot": float(slot),
                    "cx": float(x), "cy": float(y),
                    "bond_eqp": BOND_EQPS[(lot + slot) % len(BOND_EQPS)],
                    "event_time": _stamp(day, 0),
                })
            for n, (x, y) in enumerate(sorted(inspected)):
                at = _stamp(day, n)
                run_uid = "sat|%s|%d|%d|%d|%s" % (wafer, x, y, int(STACK_GATE), at)
                runs.append({
                    "business_key_val": run_uid, "run_uid": run_uid, "method": "sat",
                    "base_wafer_id": wafer, "base_x": float(x), "base_y": float(y),
                    "stack_gate": STACK_GATE,
                    "recipe_id": RECIPES[(lot + n) % len(RECIPES)],
                    "eqp_id": EQPS[(slot + n) % len(EQPS)],
                    "observed_at": at,
                })
                if rng.random() >= rate:
                    continue
                count = 2 if rng.random() < (PER_CHIP_TARGET - 1.0) else 1
                for k in range(count):
                    ix = round(rng.uniform(1000, 12000), 2) + k
                    iy = round(rng.uniform(1000, 12000), 2)
                    voids.append({
                        "business_key_val": "%s|%s|%s" % (run_uid, ix, iy),
                        "void_uid": "%s|%s|%s" % (run_uid, ix, iy), "run_uid": run_uid,
                        "base_wafer_id": wafer, "base_x": float(x), "base_y": float(y),
                        "stack_gate": STACK_GATE, "inchip_x": ix, "inchip_y": iy,
                        "radius_x": round(rng.uniform(*RADIUS), 3),
                        "radius_y": round(rng.uniform(*RADIUS), 3), "unit": "um",
                    })
                    defects.append({
                        "business_key_val": "%s_%s_%d_%d" % (core_lot, slot_s, x, y),
                        "chip_key": "%s_%s_%d_%d" % (core_lot, slot_s, x, y),
                        "lot": core_lot, "slot": slot_s,
                        "x": float(x), "y": float(y), "val": "F",
                    })
            day += 1
    # 🔴 THE FRAME, OR THE MAP SAYS `no_frame` AND DRAWS NOTHING. Registered under the
    # ATTRIBUTION relation and composed through `map_overlay.compose_map_id`, the way the
    # reader composes it -- the spelling defect repaired on 2026-08-24 was exactly a writer
    # that formatted this id itself.
    import json as _json
    import map_overlay as _mo
    frames, legs = [], []
    dt_meta = {"grid_cols": 15, "grid_rows": 15, "grid_start_x": 0, "grid_start_y": 0,
               "grid_y_invert": False, "phys_chip_x": 15, "phys_chip_y": 15,
               "phys_edge_margin": 2, "rotation": 0, "side": "front"}
    for lot in LOTS:
        for slot in SLOTS:
            for lot_col, slot_col, lot_id in (
                    ("bond_lot", "bond_slot", BOND_LOT_FMT % lot),
                    ("dt_lot", "dt_slot", DT_LOT_FMT % lot),
                    ("core_lot", "core_slot", CORE_LOT_FMT % lot)):
                slot_v = "%02d" % slot if slot_col == "bond_slot" else float(slot)
                map_id = _mo.compose_map_id(
                    [lot_col, slot_col], {lot_col: lot_id, slot_col: slot_v},
                    {"table": "bonding_log"})
                frames.append({
                    "business_key_val": "bonding_log_" + map_id,
                    "map_pk": "bonding_log_" + map_id,
                    "target_table": "bonding_log", "map_id": map_id,
                    "grid_metadata": _json.dumps(dt_meta)})
            # 🔴 THE LEG, or the trend has no subject to put a point on. The trend's grain
            # reads `bonding_map.leg`; without these rows the new wafers are invisible to it
            # however many findings they carry.
            wafer = WAFER_FMT % (lot, slot)
            for half, leg in ((0, "HBM-B_LOW-P"), (1, "LOGIC-A_REF")):
                for (x, y) in cells()[half::2]:
                    legs.append({
                        "business_key_val": "%s_%d_%d" % (wafer, x, y),
                        "pkg_id": "%s_%d_%d" % (wafer, x, y),
                        "base": wafer, "x": float(x), "y": float(y), "leg": leg})

    # a defect row is one per (lot, slot, x, y); voids can repeat a position
    seen, unique = set(), []
    for d in defects:
        if d["chip_key"] in seen:
            continue
        seen.add(d["chip_key"])
        unique.append(d)
    return [("bonding_log", bonding), ("inspection_run", runs),
            ("void_obs", voids), ("core_defect_map", unique),
            ("wafer_map_metadata", frames), ("bonding_map", legs)]


OWNED = (
    "DELETE FROM void_obs           WHERE base_wafer_id LIKE 'SYN-AUG-%'",
    "DELETE FROM inspection_run     WHERE base_wafer_id LIKE 'SYN-AUG-%'",
    "DELETE FROM bonding_log        WHERE bond_lot      LIKE 'SYN-AUG-%'",
    "DELETE FROM core_defect_map    WHERE lot           LIKE 'SYN-AUG-%'",
    "DELETE FROM bonding_map        WHERE base          LIKE 'SYN-AUG-%'",
    "DELETE FROM wafer_map_metadata WHERE map_id        LIKE 'SYN-AUG-%'",
)


def _insert(connection, table, rows):
    """`row_id` is minted here because the column is NOT NULL with no default and the
    application mints it the same way (`crud`: `str(uuid6.uuid7())`). Time-ordered ids keep
    the physical order of these rows matching their event order, as every other writer's do.
    """
    if not rows:
        return 0
    for r in rows:
        r.setdefault("row_id", str(uuid6.uuid7()))
    cols = list(rows[0])
    sql = text("INSERT INTO %s (%s) VALUES (%s)" % (
        table, ", ".join(cols), ", ".join(":" + c for c in cols)))
    for i in range(0, len(rows), 500):
        connection.execute(sql, rows[i:i + 500])
    return len(rows)


def _score(connection, tag):
    import seed_syn_lot_excursion as EX
    table = EX.lot_table(connection, "void")
    planted = {"%s%03d" % (EX.base.BOND_LOT_PREFIX, l) for l in EX.EXCURSIONS}
    out = {"lots": len(table), "baselines": {}, "planted": {}, "new_lots": {}}
    for agg in EX.SCORED_AGGREGATES:
        vals = sorted(v[agg] for v in table.values() if v[agg] is not None)
        base = vals[len(vals) // 2] if len(vals) % 2 else (
            vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2.0
        out["baselines"][agg] = base
        for lot in sorted(planted & set(table)):
            if table[lot][agg] is not None:
                out["planted"].setdefault(lot, {})[agg] = table[lot][agg] / base
        for lot in sorted(l for l in table if l.startswith(PREFIX)):
            if table[lot][agg] is not None:
                out["new_lots"].setdefault(lot, {})[agg] = table[lot][agg] / base
    print("--- %s: %d lots" % (tag, out["lots"]))
    for agg, base in out["baselines"].items():
        print("    baseline %-12s %.4f" % (agg, base))
    for lot, r in sorted(out["planted"].items()):
        print("    planted %s  " % lot + "  ".join(
            "%s x%.3f" % (a, v) for a, v in sorted(r.items())))
    for lot, r in sorted(out["new_lots"].items()):
        flag = "  <-- OVER 2.0" if any(v >= 2.0 for v in r.values()) else ""
        print("    new     %s  " % lot + "  ".join(
            "%s x%.3f" % (a, v) for a, v in sorted(r.items())) + flag)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write; default is a dry run")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)

    plan = build()
    print("planned rows:")
    for table, rows in plan:
        print("   %-18s %6d" % (table, len(rows)))

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '600s'"))
        before = _score(c, "BEFORE")
        try:
            # 🔴 THIS SCRIPT OWNS THE `SYN-AUG-` NAMESPACE AND NOTHING ELSE, so it clears
            # that namespace before writing it. Without this a second run doubles every row
            # it already landed. The predicates are the SAME ones the rollback block names —
            # one namespace, one blast radius, stated once.
            for stmt in OWNED:
                c.execute(text(stmt))
            for table, rows in plan:
                _insert(c, table, rows)
            after = _score(c, "AFTER (simulated)" if not args.apply else "AFTER")
            broke = [l for l, r in after["new_lots"].items() if any(v >= 2.0 for v in r.values())]
            planted_lost = [l for l, r in after["planted"].items()
                            if any(v < 2.0 for v in r.values())]
            if broke or planted_lost:
                print("\nSTOP - new lots over the threshold: %s ; planted lots dropped: %s"
                      % (broke or "none", planted_lost or "none"))
                c.rollback()
                return 1
            if args.apply and args.allow_owner:
                c.commit()
                print("\nCOMMITTED.")
            else:
                c.rollback()
                print("\nDRY RUN - rolled back. Add --apply "
                      "--i-accept-writing-to-owner-database")
        except Exception:
            c.rollback()
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
