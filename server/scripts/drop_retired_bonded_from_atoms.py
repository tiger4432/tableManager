r"""Delete the atoms of ONE retired mapping, and reset ONE cursor row. Both are approved.

🔴 THE PREDICATE IS THE WHOLE STRING, `#mapping` INCLUDED. `source_translator_ver` is
`<bundle-hash>#<mapping>` and NINE mappings share this bundle's hash:

    LIKE 'ledger-v2:aebdbfcd%'                     626,658 rows   <- everything but the new source
    = '...#bonded-die-from-dt-seat'                371,593 rows   <- the retired mapping alone

So the delete matches with `=`, never `LIKE`, and the script measures BOTH numbers and refuses
unless the exact match is the smaller one -- an assertion that cannot pass if someone later
loosens the predicate.

WHY THESE ATOMS MAY GO, under the owner's rule "does the fact survive elsewhere":
`bonded_from` used to mean "this BW die sits in that DT seat" because the relation pointed at
the DT side. The split gave that fact its own source, `bw_dt_seat`, which wrote it as
`transfer@1` -- 371,593 atoms, the same number. The fact is not lost; only the wrong predicate
name for it is. The Lead PM verified independently that this is the ONLY (predicate, object,
translator_ver) combination in the ledger with no mapping in the current declaration.

THE CURSOR ROW: `bonded_from`'s cursor holds `ledger-v2:41533a37…`, which is neither the current
declaration's version nor the retired atoms' -- a leftover from two revisions ago, pointing at a
relation the source no longer reads. The framework refuses to run over it and asks for inspect,
backup and separate approval; the inspection is printed here, the row's contents are printed
before deletion in place of a backup file, and the approval is the Lead PM's ruling of
2026-08-26 17:5x. ONE row, named explicitly -- no other source is touched.

USAGE -- dry run by default; the gate runs inside the transaction, before the commit:

    python scripts/drop_retired_bonded_from_atoms.py
    python scripts/drop_retired_bonded_from_atoms.py --apply --i-accept-writing-to-owner-database

ROLLBACK: re-running `python -m ledger.backfill --source bw_dt_seat` rewrites the fact under its
right predicate; the retired name is not meant to come back.
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

BUNDLE = "ledger-v2:aebdbfcd659d3ff5a8917918c015e17ce3d23b598e18374a3fd65d881815245c"
RETIRED = BUNDLE + "#bonded-die-from-dt-seat"
EXPECTED_ATOMS = 371593
SURVIVES_AS = "transfer"
CURSOR_SOURCE = "bonded_from"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '900s'"))
        try:
            exact = c.execute(text(
                "SELECT count(*) FROM ledger_events WHERE source_translator_ver = :v"),
                {"v": RETIRED}).scalar()
            prefixed = c.execute(text(
                "SELECT count(*) FROM ledger_events WHERE source_translator_ver LIKE :p"),
                {"p": BUNDLE + "%"}).scalar()
            survives = c.execute(text(
                "SELECT count(*) FROM ledger_events WHERE predicate = :p "
                "AND object_payload->'keys'->>'mat_type' = 'DTLotSlot'"),
                {"p": SURVIVES_AS}).scalar()
            print("   exact match  (=  ...#bonded-die-from-dt-seat) %9d" % exact)
            print("   prefix match (LIKE bundle hash)               %9d   <- what LIKE would take"
                  % prefixed)
            print("   the same fact, kept as %-8s               %9d" % (SURVIVES_AS, survives))

            row = c.execute(text(
                "SELECT translator_ver, cursor_value, molecules_done, atoms_written, updated_at "
                "FROM ledger_translator_cursor WHERE source = :s"), {"s": CURSOR_SOURCE}).first()
            print("\n   cursor row to remove (printed in place of a backup):")
            if row is None:
                print("      (none)")
            else:
                print("      translator_ver %s" % row[0])
                print("      cursor_value   %s" % (str(row[1])[:120]))
                print("      molecules %s · atoms %s · updated %s" % (row[2], row[3], row[4]))

            safe = (exact == EXPECTED_ATOMS and exact < prefixed
                    and survives == EXPECTED_ATOMS)
            print("\n   PRE-GATE: %s" % ("PASS" if safe else "FAIL"))
            if not safe:
                c.rollback()
                print("REFUSED - not deleting.")
                return 1
            if not (args.apply and args.allow_owner):
                c.rollback()
                print("DRY RUN - nothing deleted.")
                return 0

            deleted = c.execute(text(
                "DELETE FROM ledger_events WHERE source_translator_ver = :v"),
                {"v": RETIRED}).rowcount
            cursors = c.execute(text(
                "DELETE FROM ledger_translator_cursor WHERE source = :s"),
                {"s": CURSOR_SOURCE}).rowcount
            left = c.execute(text(
                "SELECT count(*) FROM ledger_events WHERE source_translator_ver = :v"),
                {"v": RETIRED}).scalar()
            others = c.execute(text(
                "SELECT count(*) FROM ledger_events WHERE source_translator_ver LIKE :p"),
                {"p": BUNDLE + "%"}).scalar()
            still = c.execute(text(
                "SELECT count(*) FROM ledger_events WHERE predicate = :p "
                "AND object_payload->'keys'->>'mat_type' = 'DTLotSlot'"),
                {"p": SURVIVES_AS}).scalar()
            cursor_rows = c.execute(text(
                "SELECT count(*) FROM ledger_translator_cursor")).scalar()

            print("\n   deleted atoms                %9d   %s"
                  % (deleted, "OK" if deleted == EXPECTED_ATOMS else "<- unexpected"))
            print("   deleted cursor rows          %9d   %s"
                  % (cursors, "OK" if cursors == 1 else "<- must be exactly one"))
            print("   retired version left         %9d   %s"
                  % (left, "OK" if left == 0 else "<- not empty"))
            print("   siblings on the same bundle  %9d   (were %d; %d expected to remain)"
                  % (others, prefixed, prefixed - EXPECTED_ATOMS))
            print("   the fact still kept as %-8s %9d   %s"
                  % (SURVIVES_AS, still, "OK" if still == EXPECTED_ATOMS else "<- LOST"))
            print("   cursor rows remaining        %9d" % cursor_rows)

            ok = (deleted == EXPECTED_ATOMS and cursors == 1 and left == 0
                  and others == prefixed - EXPECTED_ATOMS and still == EXPECTED_ATOMS)
            print("\n   GATE: %s" % ("PASS" if ok else "FAIL"))
            if not ok:
                c.rollback()
                print("ROLLED BACK.")
                return 1
            c.commit()
            print("COMMITTED.")
        except Exception:
            c.rollback()
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
