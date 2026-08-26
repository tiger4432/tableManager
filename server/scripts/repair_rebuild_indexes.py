r"""Free the index names the rename took with it, empty the half-loaded ledger, and rebuild the
schema so the new table carries every index the old one had.

🔴 WHAT WENT WRONG, NAMED: renaming `ledger_events` moved the TABLE, not its indexes. Index
names are unique per schema, so `uq_ledger_atom` and six others stayed occupied by indexes on
the renamed table. `ensure_schema` creates with `CREATE ... IF NOT EXISTS <fixed name>`, which
does not mean "if this index is missing" -- it means "if this NAME is free". The names were not
free, so seven creations were skipped in silence and the load ran with one index instead of
eight. The proof is in the name Postgres was forced to pick for the primary key:
`ledger_events_pkey1`.

🔴 THE HALF-LOAD IS DISCARDED, NOT DEDUPED. 533,259 atoms went in without `uq_ledger_atom`
watching, so the second net against a double write was absent. Picking duplicates out by hand
would leave a ledger that is no longer "the output of the declaration", which is the definition
this rebuild exists to make true. Truncate and reload.

⚠️ `ensure_schema` commits on its own, so this cannot all be one transaction. The destructive
half (rename + truncate) is one gated transaction; the additive half (ensure_schema) runs after
and is idempotent. The parity check runs last and compares index DEFINITIONS, not names --
names are exactly what a rename can carry away.

USAGE -- dry run reports the plan and the current parity; it changes nothing:

    python scripts/repair_rebuild_indexes.py
    python scripts/repair_rebuild_indexes.py --apply --i-accept-writing-to-owner-database

ROLLBACK: the renamed indexes can be renamed back; nothing is dropped. The truncated rows are
the half-load, which is being replaced by the reload either way.
"""
import argparse
import os
import re
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

INDEX_SQL = """
SELECT c.relname, pg_get_indexdef(c.oid)
  FROM pg_index i
  JOIN pg_class c ON c.oid = i.indexrelid
  JOIN pg_class t ON t.oid = i.indrelid
  JOIN pg_namespace n ON n.oid = t.relnamespace
 WHERE t.relname = :t AND n.nspname = 'public'
 ORDER BY c.relname"""


def shape(name, definition, table):
    """An index's definition with its own name and its table's name removed.

    Comparing definitions rather than names is the whole point: the incident happened because a
    name moved while the thing it named stayed put.
    """
    # `pg_get_indexdef` writes "ON ONLY public.<t>" for an index on a partitioned parent, so
    # both spellings are normalised -- matching only one of them made the primary key look
    # like a missing index.
    out = definition.replace(f" ON ONLY public.{table} ", " ON <table> ")
    out = out.replace(f" ON public.{table} ", " ON <table> ")
    out = out.replace(f"INDEX {name} ", "INDEX <name> ")
    return re.sub(r"\s+", " ", out).strip()


def index_shapes(c, table):
    return {shape(n, d, table): n for n, d in c.execute(text(INDEX_SQL), {"t": table})}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '600s'"))
        old = index_shapes(c, ASIDE)
        new = index_shapes(c, LIVE)
        rows = c.execute(text(f"SELECT count(*) FROM {LIVE}")).scalar()
        print("   %-28s indexes %d" % (ASIDE, len(old)))
        print("   %-28s indexes %d   rows %d  (the half-load)" % (LIVE, len(new), rows))
        missing = [old[s] for s in old if s not in new]
        print("   missing from the new table  : %s" % ", ".join(sorted(missing)))

        # Only names that BLOCK a re-creation need freeing: the old index keeps a name the new
        # table wants. The primary key is already made (as pkey1) so it is left alone.
        to_free = sorted(n for n in missing if not n.endswith("_pre_rebuild"))
        print("   names to free               : %s" % ", ".join(to_free))

        if not (args.apply and args.allow_owner):
            print("\n   DRY RUN - nothing changed.")
            return 0

        try:
            for name in to_free:
                c.execute(text(f'ALTER INDEX {name} RENAME TO {name}_pre_rebuild'))
            # 🔴 THE SAME TRAP ONE LEVEL DOWN. The migration creates a per-partition index
            # named `idx_ledger_source_event_<month>` with IF NOT EXISTS, then ATTACHes it.
            # The old partitions still hold exactly those names, so the create is skipped and
            # the ATTACH grabs the OLD index -- which is already attached to the old parent,
            # and Postgres refuses. Freeing the parent names alone is not enough.
            # ⚠️ The freed name cannot be `<name>_pre_rebuild`: identifiers cap at 63 bytes,
            # and two of these are already near the cap, so the suffix truncates them onto
            # each other. The oid is short and unique, and these indexes are never named
            # again -- they exist only so the old partitions stay queryable.
            child = list(c.execute(text(
                "SELECT c.oid, c.relname FROM pg_class c JOIN pg_index i ON i.indexrelid=c.oid "
                "JOIN pg_class t ON t.oid=i.indrelid "
                "WHERE t.relname LIKE 'ledger_events_pre_rebuild_%' "
                "AND c.relname NOT LIKE 'preidx\_%'")))
            for oid, name in child:
                c.execute(text(f'ALTER INDEX "{name}" RENAME TO preidx_{oid}'))
            print("   partition index names freed : %d" % len(child))
            c.execute(text(f"TRUNCATE TABLE {LIVE}"))
            c.execute(text(f"TRUNCATE TABLE {CURSOR}"))
            still_taken = [r[0] for r in c.execute(text(
                "SELECT relname FROM pg_class WHERE relname = ANY(:names)"),
                {"names": to_free})]
            emptied = c.execute(text(f"SELECT count(*) FROM {LIVE}")).scalar()
            cursors = c.execute(text(f"SELECT count(*) FROM {CURSOR}")).scalar()
            ok = not still_taken and emptied == 0 and cursors == 0
            print("\n   names still occupied        : %s" % (still_taken or "none"))
            print("   %s rows / %s cursor rows" % (emptied, cursors))
            print("   GATE (destructive half): %s" % ("PASS" if ok else "FAIL"))
            if not ok:
                c.rollback()
                print("ROLLED BACK.")
                return 1
            c.commit()
            print("COMMITTED.")
        except Exception:
            c.rollback()
            raise

    # Additive half, in its own transaction -- ensure_schema commits for itself.
    from ledger import schema                                        # noqa: E402
    raw = db.engine.raw_connection()
    try:
        schema.ensure_schema(raw)
    finally:
        raw.close()

    # 🔴 `ensure_schema` builds the source-event pair ONLY for a brand-new empty ledger; on an
    # existing one they belong to `migrations/add_ledger_source_events.py`. The table already
    # existed (the half-load made it), so that path was taken and the two were left undone.
    #
    # 🔴 AND EXISTENCE IS NOT VALIDITY. An index on a partitioned parent stays INVALID until
    # every partition carries a matching one, so a name-count parity check reports PASS over
    # two indexes the planner will never use. Any invalid parent is dropped and rebuilt.
    with db.engine.connect() as c:
        invalid = [r[0] for r in c.execute(text(
            "SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
            "JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace "
            f"WHERE t.relname='{LIVE}' AND n.nspname='public' AND NOT i.indisvalid"))]
        if invalid:
            print("   invalid, dropped to rebuild: %s" % ", ".join(invalid))
            for name in invalid:
                c.execute(text(f"DROP INDEX IF EXISTS {name}"))
            c.commit()

    from migrations import add_ledger_source_events                  # noqa: E402
    raw = db.engine.raw_connection()
    try:
        add_ledger_source_events.apply(raw, 5000)
        raw.commit()
    finally:
        raw.close()

    with db.engine.connect() as c:
        old = index_shapes(c, ASIDE)
        new = index_shapes(c, LIVE)
        gone = sorted(old[s] for s in old if s not in new)
        extra = sorted(new[s] for s in new if s not in old)
        print("\n   %-28s indexes %d" % (ASIDE, len(old)))
        print("   %-28s indexes %d" % (LIVE, len(new)))
        print("   definitions the new table lacks : %s" % (gone or "none"))
        print("   definitions only the new one has: %s" % (extra or "none"))
        invalid = [r[0] for r in c.execute(text(
            "SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
            "JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace "
            f"WHERE t.relname='{LIVE}' AND n.nspname='public' AND NOT i.indisvalid"))]
        print("   indexes that exist but are INVALID: %s" % (invalid or "none"))
        parity = not gone and not invalid
        print("\n   GATE (parity by DEFINITION, and every index VALID): %s"
              % ("PASS" if parity else "FAIL"))
        return 0 if parity else 1


if __name__ == "__main__":
    raise SystemExit(main())
