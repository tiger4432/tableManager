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

⚰️ THE DRY RUN USED TO INSERT INSIDE A TRANSACTION AND ROLL BACK, which made its numbers
the numbers `--apply` landed rather than an estimate. That is gone as of S-78 (ruling 181):
every write goes through the product door and commits on the server, so there is no
transaction here to roll back. The dry run now prints the plan and the BEFORE score only.

WHAT REPLACED THE ROLLBACK IS COMPENSATION. The scoring that used to gate the commit now
runs AFTER the write, and when it refuses, this script clears its namespace again through
the door. That is exact because the namespace was emptied before the run, so it holds this
run's rows and nothing else. The ledger keeps both events -- written, then withdrawn -- and
that is true rather than dirty: those facts existed and then did not.

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


import product_door

#: The layer name these rows land under, so the set is attributable and removable.
SOURCE_NAME = "seed_syn_aug_material"


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


#: The namespace this script owns, as (table, predicate) rather than as DELETE statements.
#:
#: 🔴 THE DOOR DELETES BY ID (`RowDeleteBatch` is `{row_ids, user_name}`), so a predicate is
#: resolved to ids and the ids are sent. That is not a workaround: an outbox event names the
#: rows it is about, and a predicate nobody expanded would produce an event nobody can
#: resolve.
#:
#: 🔴 AND RAW DELETE HERE WAS WORSE THAN "NO ENVELOPE" (ruling 181). This script empties the
#: TABLE and not the ledger, so rows removed by a raw statement left their atoms standing --
#: the S-74 shape. Going through the door is what withdraws them.
OWNED = (
    ("void_obs", "base_wafer_id LIKE 'SYN-AUG-%'"),
    ("inspection_run", "base_wafer_id LIKE 'SYN-AUG-%'"),
    ("bonding_log", "bond_lot LIKE 'SYN-AUG-%'"),
    ("core_defect_map", "lot LIKE 'SYN-AUG-%'"),
    ("bonding_map", "base LIKE 'SYN-AUG-%'"),
    ("wafer_map_metadata", "map_id LIKE 'SYN-AUG-%'"),
)


def _clear_owned(connection, url, log=print):
    """Delete this script's namespace through the door, table by table.

    Returns the number of rows removed. Used twice: once before writing, and again as the
    COMPENSATION when scoring refuses what was written - the namespace holds only this
    run's rows at that point, so clearing it again is exact.
    """
    removed = 0
    for table, where in OWNED:
        ids = [r[0] for r in connection.execute(
            text("SELECT row_id FROM %s WHERE %s" % (table, where))).fetchall()]
        if not ids:
            continue
        log("   clearing %-20s %6d rows" % (table, len(ids)))
        product_door.delete_rows(table, ids, base_url=url,
                                 user_name=SOURCE_NAME, log=lambda *_: None)
        removed += len(ids)
    return removed


def _put(table, rows, url, log=print):
    """Write one table's rows through the product door.

    🔴 NO `row_id` IS MINTED HERE ANY MORE. The engine mints it, and ruling 150 refuses a
    supplied id that is not a uuid7. Every row already carries `business_key_val`, which is
    what the door resolves or creates on.
    """
    if not rows:
        return 0
    items = []
    for row in rows:
        values = dict(row)
        items.append(product_door.row_item(
            values.pop("business_key_val"), values, source_name=SOURCE_NAME))
    result = product_door.put_rows(table, items, base_url=url, log=lambda *_: None)
    log("   wrote    %-20s %6d rows in %d request(s)" % (
        table, result["rows"], result["requests"]))
    return result["rows"]


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
    ap.add_argument("--url", default=product_door.DEFAULT_BASE_URL,
                    help="server base url the rows are written through")
    args = ap.parse_args(argv)

    plan = build()
    print("planned rows:")
    for table, rows in plan:
        print("   %-18s %6d" % (table, len(rows)))

    # 🔴 THE CONNECTION IS A READER NOW. Every write goes through the door, so there is no
    # transaction here to commit or roll back - which is the whole change (S-78, ruling 181).
    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '600s'"))
        _score(c, "BEFORE")

    if not (args.apply and args.allow_owner):
        # ⚠️ THE DRY RUN NO LONGER SIMULATES, AND SAYING SO IS THE HONEST PART.
        # It used to insert inside a transaction, score the real result and roll back, so
        # its numbers WERE the numbers `--apply` landed. Writes through the door commit on
        # the server and cannot be rolled back, so that is gone: what remains is the plan
        # and the BEFORE score. The check that used to gate the commit now runs AFTER the
        # write and compensates - see below.
        print("\nDRY RUN - nothing written. The scoring that used to gate the commit now")
        print("runs after the write and compensates on refusal; add --apply")
        print("--i-accept-writing-to-owner-database to run it.")
        return 0

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '600s'"))
        # 🔴 THIS SCRIPT OWNS THE `SYN-AUG-` NAMESPACE AND NOTHING ELSE, so it clears that
        # namespace before writing it. Without this a second run doubles every row it
        # landed. One namespace, one blast radius, stated once in `OWNED`.
        print("")
        _clear_owned(c, args.url)

    written = 0
    for table, rows in plan:
        written += _put(table, rows, args.url)

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '600s'"))
        after = _score(c, "AFTER")
        broke = [l for l, r in after["new_lots"].items() if any(v >= 2.0 for v in r.values())]
        planted_lost = [l for l, r in after["planted"].items()
                        if any(v < 2.0 for v in r.values())]
        if broke or planted_lost:
            # 🔴 COMPENSATION, NOT ROLLBACK (ruling 181). The rows are committed and their
            # atoms exist; what undoes them is another write through the door. Clearing the
            # namespace is exact here because the namespace was emptied before this run, so
            # it holds this run's rows and nothing else.
            print("\nSTOP - new lots over the threshold: %s ; planted lots dropped: %s"
                  % (broke or "none", planted_lost or "none"))
            print("compensating - withdrawing what this run wrote:")
            _clear_owned(c, args.url)
            # ⚠️ THE LEDGER KEEPS THE TRACE, AND THAT IS TRUE RATHER THAN DIRTY: these facts
            # existed and then did not. An append-only ledger saying so is correct.
            print("compensated. The ledger keeps both events - written, then withdrawn.")
            return 1
        print("\nCOMMITTED through the product door - %d rows." % written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
