"""Give the ledger a place to say WHERE an atom's time came from.

Read-only report (default)::

    conda run -n assy_manager python server/migrations/add_ledger_occurred_at_basis.py

Apply::

    conda run -n assy_manager python server/migrations/add_ledger_occurred_at_basis.py --apply

Until now every source had to name a world-time column. A table that carries no time could
only be declared by pointing at something that is not a time, or by pinning a constant into
the profile - both produce atoms that READ as world time and cannot be told apart
afterwards. `occurred_at_basis` is the place an atom admits the difference itself.

Safety:
* one nullable TEXT column - metadata-only in PostgreSQL 11+, no row rewrite;
* NO backfill. NULL is the correct value for every existing atom: absence means world
  time, which is what they all are. Writing a value into them would be inventing evidence;
* additive only - no DELETE, DROP, or payload rewrite;
* the CHECK is added NOT VALID first, so the exclusive lock does not wait on a full scan,
  and validated separately.

The parent of a partitioned table takes ACCESS EXCLUSIVE for the ADD COLUMN and queues
behind every open reader of `ledger_events`, so run it when the table is quiet.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import engine  # noqa: E402
from ledger import schema  # noqa: E402

COLUMN = "occurred_at_basis"
CONSTRAINT = "ck_ledger_occurred_at_basis"
DECLARED_BASES = ("ingested",)


def _scalar(connection, sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]


def report(connection):
    exists = _scalar(connection, "SELECT to_regclass(%s) IS NOT NULL",
                     (schema.LEDGER_TABLE,))
    print(f"relation={schema.LEDGER_TABLE} exists={exists}")
    if not exists:
        return
    present = schema.column_exists(connection, schema.LEDGER_TABLE, COLUMN)
    print(f"column={COLUMN} exists={present}")
    constrained = _scalar(
        connection,
        "SELECT count(*) FROM pg_constraint WHERE conname = %s", (CONSTRAINT,))
    print(f"constraint={CONSTRAINT} installed={bool(constrained)}")
    if not present:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT coalesce({COLUMN}, '<null = world time>'), count(*) "
            f"FROM {schema.LEDGER_TABLE} GROUP BY 1 ORDER BY 2 DESC")
        for basis, count in cursor.fetchall():
            print(f"  {basis}: {count:,}")


def apply(connection):
    if not schema.column_exists(connection, schema.LEDGER_TABLE, COLUMN):
        with connection.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE {schema.LEDGER_TABLE} ADD COLUMN {COLUMN} TEXT")
        print(f"added {COLUMN}")
    else:
        print(f"{COLUMN} already present")
    installed = _scalar(
        connection,
        "SELECT count(*) FROM pg_constraint WHERE conname = %s", (CONSTRAINT,))
    if not installed:
        allowed = ", ".join(f"'{value}'" for value in DECLARED_BASES)
        with connection.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE {schema.LEDGER_TABLE} ADD CONSTRAINT {CONSTRAINT} "
                f"CHECK ({COLUMN} IS NULL OR {COLUMN} IN ({allowed})) NOT VALID")
            cursor.execute(
                f"ALTER TABLE {schema.LEDGER_TABLE} VALIDATE CONSTRAINT {CONSTRAINT}")
        print(f"installed and validated {CONSTRAINT}")
    else:
        print(f"{CONSTRAINT} already installed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="perform the migration (default is a read-only report)")
    args = parser.parse_args()
    connection = engine.raw_connection()
    try:
        if args.apply:
            apply(connection)
            connection.commit()
        report(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
