r"""Re-spell the SYN DT/core frame identities to the spelling their reader composes.

WHY THIS EXISTS
---------------
MEASURED on `assy_manager` 2026-08-23: one DT slot had THREE spellings and NOBODY produced
the registered one.

    registered in wafer_map_metadata   SYN-DT-101_07     ("%02d", written by seed_syn_world)
    built by the read path             SYN-DT-101_7.0    (f-string over a float column)
    composed canonically               SYN-DT-101_7      (declared type "number")

So `GET /api/ledger/lot_map` served `no_registered_frame` for every DT and core projection
while 1,200 frames sat registered and unreachable, and the client had no lattice to draw a
border on. The bond axis resolved only because `bond_slot` is TEXT and undeclared, so all
three spellings coincided there BY ACCIDENT.

Ruled (lead PM 2026-08-23, owner approved): the declaration governs. `ledger_lots` now
composes through `map_overlay.compose_map_id`, `seed_syn_world.frame_rows` composes through
the same function, and this script moves the rows already on the box to that spelling.

WHAT MOVES, AND WHAT DOES NOT
-----------------------------
Only slots 01..09 change: "%02d" and the canonical fold AGREE from slot 10 up, so 768 of
the 1,200 are already correct and are not touched. The row COUNT does not change - this is
an UPDATE of the identity columns, never a delete and re-insert.

    SYN-DT-*/SYN-CL-* frames under bonding_log      1,200   (count invariant)
      of which re-spelled (slots 01..09)              432
      of which already canonical (slots 10..25)       768
    every other bonding_log frame (the bond axis)   2,810   NOT TOUCHED

ROLLBACK - one statement, printed again at the end of every run; see ROLLBACK below.

USAGE - a dry run by default, and the owner's database needs saying out loud:

    python scripts/respell_syn_frame_map_ids.py
    python scripts/respell_syn_frame_map_ids.py --apply --i-accept-writing-to-owner-database
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
import seed_syn_world as world                                       # noqa: E402

TOTAL_PREDICATE = ("target_table = 'bonding_log' "
                   "AND (map_id LIKE 'SYN-DT-%' OR map_id LIKE 'SYN-CL-%')")

#: The undo, as ONE statement. Every identity column carries the id, so all three move
#: together or the row's identity diverges from itself.
ROLLBACK = (
    "UPDATE wafer_map_metadata SET "
    r"map_id = regexp_replace(map_id, '_([1-9])$', '_0\1'), "
    r"map_pk = regexp_replace(map_pk, '_([1-9])$', '_0\1'), "
    r"business_key_val = regexp_replace(business_key_val, '_([1-9])$', '_0\1') "
    "WHERE target_table = 'bonding_log' "
    "AND (map_id LIKE 'SYN-DT-%' OR map_id LIKE 'SYN-CL-%') "
    r"AND map_id ~ '_[1-9]$';")


def plan():
    """(old, new) for every frame this fixture registers, taken FROM THE FIXTURE.

    The old spelling is the literal this script replaces and the new one comes from the
    shared composer, so neither is re-derived by pattern-matching the stored id - a regex
    over `map_id` would be a FOURTH spelling of the same rule.
    """
    pairs = []
    for lot in world.TIER1_LOTS:
        for slot in range(1, 26):
            for lot_col, slot_col, lot_id in (
                    ("dt_lot", "dt_slot", world.DT_LOT_FMT % lot),
                    ("core_lot", "core_slot", world.core_lot_at_dt(lot))):
                old = "%s_%02d" % (lot_id, slot)
                new = world.frame_map_id(lot_col, slot_col, lot_id, slot)
                if old != new:
                    pairs.append((old, new))
    return pairs


def count(connection):
    return connection.execute(
        text("SELECT count(*) FROM wafer_map_metadata WHERE " + TOTAL_PREDICATE)).scalar()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write; default is a dry run")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)

    pairs = plan()
    print("planned re-spellings: %d" % len(pairs))
    for old, new in pairs[:3]:
        print("   %s  ->  %s" % (old, new))
    print("   ...")

    olds = [o for o, _ in pairs]
    news = [n for _, n in pairs]

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '60s'"))
        before = count(c)
        print("\nSYN DT/CL frames under bonding_log BEFORE: %d" % before)

        present = c.execute(text("SELECT count(*) FROM wafer_map_metadata "
                                 "WHERE target_table='bonding_log' AND map_id = ANY(:ids)"),
                            {"ids": olds}).scalar()
        collide = c.execute(text("SELECT count(*) FROM wafer_map_metadata "
                                 "WHERE target_table='bonding_log' AND map_id = ANY(:ids)"),
                            {"ids": news}).scalar()
        synced = c.execute(text("SELECT count(*) FROM wafer_map_metadata "
                                "WHERE target_table='bonding_log' AND map_id = ANY(:ids) "
                                "AND (is_graph_synced OR graph_synced_at IS NOT NULL)"),
                           {"ids": olds}).scalar()
        print("  old spellings present  : %d (expected %d)" % (present, len(pairs)))
        print("  new spellings present  : %d (expected 0 - a hit is a collision)" % collide)
        print("  graph-synced among them: %d (expected 0 - a hit means a graph node "
              "keys off this id)" % synced)

        if collide or synced or present != len(pairs):
            print("\nSTOP - a precondition does not hold. Nothing written.")
            return 1

        if not args.apply:
            print("\nDRY RUN - nothing written. Add --apply "
                  "--i-accept-writing-to-owner-database")
            print("\nrollback:\n" + ROLLBACK)
            return 0
        if not args.allow_owner:
            print("\n--apply needs --i-accept-writing-to-owner-database")
            return 1

    with db.engine.begin() as c:
        c.execute(text("SET statement_timeout = '60s'"))
        moved = 0
        for old, new in pairs:
            r = c.execute(text("UPDATE wafer_map_metadata SET map_id = :new, "
                               "map_pk = replace(map_pk, :old, :new), "
                               "business_key_val = replace(business_key_val, :old, :new) "
                               "WHERE target_table = 'bonding_log' AND map_id = :old"),
                          {"old": old, "new": new})
            moved += r.rowcount

    with db.engine.connect() as c:
        after = count(c)
        print("\nrows updated: %d" % moved)
        print("SYN DT/CL frames under bonding_log AFTER: %d" % after)
        if after != before:
            print("\nCOUNT CHANGED %d -> %d. Roll back:\n%s" % (before, after, ROLLBACK))
            return 1
        print("count invariant held.")
        print("\nrollback:\n" + ROLLBACK)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
