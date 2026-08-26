r"""Move the whole ledger aside under a new name, so the rebuild writes into an empty table
while the old atoms stay readable for the comparison.

🔴 NOT A DROP. The Lead PM's ruling: the old rows are what the reload is compared against, so
they are renamed, never deleted. Deleting them would leave "the counts changed" with nothing to
check it against.

🔴 THE PARENT ALONE IS NOT ENOUGH. `ledger_events` is a PARTITIONED table (relkind 'p') with
eight monthly children. Renaming only the parent leaves the children holding their own names, so
the moment the reload calls `ensure_partition` and tries to create `ledger_events_2026_09`
again, the name is still taken -- by a partition of the renamed table. All nine move together.

🔴 THE CURSOR MOVES TOO, OR THE RELOAD WRITES NOTHING. `ledger_translator_cursor` holds where
each translator stopped -- 17 rows. Leave it and the reload resumes at the end of work it can no
longer see and produces an empty ledger, silently. `--reset-cursor` is refused at the operator
boundary (`destructive_approval_required`), so the honest way to give the reload a clean slate
is the same one used for the atoms: move it aside, do not delete it. `ensure_schema` recreates
an empty one.

⚠️ SIDE EFFECT, NAMED: those 17 rows include script sources (`syn_journey`, `syn_lot_excursion`)
that are not part of the reload. If one of them runs later it will re-scan from the beginning;
`uq_ledger_atom` stops it writing the same atom twice, so the cost is time, not duplicates.

WHAT RECREATES THE EMPTY TABLE: nothing here. `ledger/backfill.py` calls `store.ensure_schema()`
on every run and the store ensures each month as it writes, so the reload builds its own table
and partitions. This script only moves the old one out of the way.

USAGE -- dry run by default; the gate runs inside the transaction, before the commit:

    python scripts/rename_ledger_for_rebuild.py
    python scripts/rename_ledger_for_rebuild.py --apply --i-accept-writing-to-owner-database

ROLLBACK (nothing was destroyed):

    ALTER TABLE ledger_events_pre_rebuild RENAME TO ledger_events;
    ALTER TABLE ledger_translator_cursor_pre_rebuild RENAME TO ledger_translator_cursor;
    -- and the eight children back to ledger_events_<month>
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

LIVE = "ledger_events"
ASIDE = "ledger_events_pre_rebuild"
CURSOR = "ledger_translator_cursor"
CURSOR_ASIDE = "ledger_translator_cursor_pre_rebuild"

CHILDREN_SQL = """
SELECT c.relname
  FROM pg_inherits i
  JOIN pg_class c ON c.oid = i.inhrelid
  JOIN pg_class p ON p.oid = i.inhparent
 WHERE p.relname = :parent
 ORDER BY c.relname"""

KIND_SQL = """
SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relname = :name AND n.nspname = 'public'"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '600s'"))
        try:
            kind = c.execute(text(KIND_SQL), {"name": LIVE}).scalar()
            if kind is None:
                print("   %s does not exist -- already moved aside?" % LIVE)
                return 1
            children = [r[0] for r in c.execute(text(CHILDREN_SQL), {"parent": LIVE})]
            before_rows = c.execute(text(f"SELECT count(*) FROM {LIVE}")).scalar()
            print("   %-28s relkind=%s  children=%d  rows=%d"
                  % (LIVE, kind, len(children), before_rows))
            for name in children:
                print("      %s" % name)

            cursor_rows = c.execute(text(f"SELECT count(*) FROM {CURSOR}")).scalar()
            print("   %-28s rows=%d  (moves too, or the reload resumes at the end)"
                  % (CURSOR, cursor_rows))

            if c.execute(text(KIND_SQL), {"name": CURSOR_ASIDE}).scalar() is not None:
                print("\n   REFUSED: %s already exists." % CURSOR_ASIDE)
                c.rollback()
                return 1
            if c.execute(text(KIND_SQL), {"name": ASIDE}).scalar() is not None:
                print("\n   REFUSED: %s already exists. A previous run moved a ledger aside;"
                      " renaming onto it would bury it." % ASIDE)
                c.rollback()
                return 1

            c.execute(text(f'ALTER TABLE {LIVE} RENAME TO {ASIDE}'))
            renamed = []
            for name in children:
                # ledger_events_2026_09 -> ledger_events_pre_rebuild_2026_09
                suffix = name[len(LIVE):]
                new = ASIDE + suffix
                c.execute(text(f'ALTER TABLE {name} RENAME TO {new}'))
                renamed.append(new)

            c.execute(text(f'ALTER TABLE {CURSOR} RENAME TO {CURSOR_ASIDE}'))

            after_kind = c.execute(text(KIND_SQL), {"name": ASIDE}).scalar()
            after_children = [r[0] for r in c.execute(text(CHILDREN_SQL), {"parent": ASIDE})]
            after_rows = c.execute(text(f"SELECT count(*) FROM {ASIDE}")).scalar()
            live_gone = c.execute(text(KIND_SQL), {"name": LIVE}).scalar() is None
            cursor_gone = c.execute(text(KIND_SQL), {"name": CURSOR}).scalar() is None
            cursor_kept = c.execute(text(f"SELECT count(*) FROM {CURSOR_ASIDE}")).scalar()

            print("\n   %-28s relkind=%s  children=%d  rows=%d"
                  % (ASIDE, after_kind, len(after_children), after_rows))
            print("   the name %-18s is free: %s" % (LIVE, live_gone))
            print("   every child moved with it   : %s"
                  % (sorted(after_children) == sorted(renamed)))
            print("   not one row moved           : %s (%d -> %d)"
                  % (after_rows == before_rows, before_rows, after_rows))
            print("   the cursor is free too      : %s (%d rows kept at %s)"
                  % (cursor_gone, cursor_kept, CURSOR_ASIDE))

            ok = (after_kind == "p" and live_gone and cursor_gone
                  and cursor_kept == cursor_rows and after_rows == before_rows
                  and sorted(after_children) == sorted(renamed)
                  and len(after_children) == len(children))
            print("\n   GATE: %s" % ("PASS" if ok else "FAIL"))
            if ok and args.apply and args.allow_owner:
                c.commit()
                print("COMMITTED.  %d atoms are readable at %s." % (after_rows, ASIDE))
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
