"""Physical schema for the canonical ledger - **additive only, idempotent, partitioned**.

    conda run -n assy_manager python server/migrations/add_ledger_events.py
    conda run -n assy_manager python server/migrations/add_ledger_events.py --report

[SAFETY CONTRACT]
- There is no DROP, no ALTER of anything that already exists, and no statement that
  touches a row of any existing table. This script only ever ADDS two new tables that
  nothing else in the system reads.
- 🔴 It creates NEW tables, so it does not share the hazard `add_frame_confirmation.py`
  documents (a column added to a large existing table). Nothing waits on it and nothing
  breaks if it has not run: no process imports `server/ledger` at boot.
- `ledger_events` is RANGE partitioned on `occurred_at` from the first statement.
  PostgreSQL has no `ALTER TABLE ... PARTITION BY`, so retro-fitting partitioning to a
  populated ledger is a full rewrite - which is why the brief calls for it on day one.

[WHERE THE DDL LIVES]
The statements are in `server/ledger/schema.py`, not here. That is deliberate: the
translator has to be able to build the same table into a scratch schema for its tests,
and a second copy of the DDL in a migration script is how a test ends up proving a
lookalike works. This file is the operator's entry point and the audit trail; that file
is the single spelling.

[WHAT IT DOES NOT CREATE]
Partitions. The translator creates the month it is about to write into
(`schema.ensure_partition`), because the months that exist depend on the data, not on the
deployment date. `--months` is offered for an operator who wants to pre-create a window.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone                                     # noqa: E402

from database.database import engine                                        # noqa: E402
from ledger import schema                                                   # noqa: E402


def report(connection):
    with connection.cursor() as cursor:
        for table in (schema.LEDGER_TABLE, schema.CURSOR_TABLE):
            cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (table,))
            print(f"  {table:28s} exists={cursor.fetchone()[0]}")
        # Qualified by the schema `to_regclass` actually resolved to. `pg_indexes`
        # matches on bare `tablename`, so an unqualified query lists the indexes of
        # EVERY schema that happens to hold a table of this name - and a reader sees
        # each index twice and concludes there are duplicates. There is such a second
        # copy on this box (a scratch schema), which is how the defect was found.
        cursor.execute("""
            SELECT i.indexname FROM pg_indexes i
            JOIN pg_class c ON c.relname = i.tablename
            JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = i.schemaname
            WHERE c.oid = to_regclass(%s) ORDER BY 1
        """, (schema.LEDGER_TABLE,))
        for (name,) in cursor.fetchall():
            print(f"  index  {name}")
    for name, bound in schema.partitions(connection):
        print(f"  partition {name}  {bound}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", action="store_true",
                        help="print what exists and change nothing")
    parser.add_argument("--months", type=int, default=0,
                        help="pre-create this many monthly partitions from today")
    args = parser.parse_args(argv)

    connection = engine.raw_connection()
    try:
        if args.report:
            report(connection)
            return 0

        schema.ensure_schema(connection)
        print(f"[ledger] {schema.LEDGER_TABLE} + {schema.CURSOR_TABLE} are present "
              f"(partitioned by RANGE (occurred_at))")

        if args.months:
            now = datetime.now(timezone.utc)
            last = now
            for _ in range(max(0, args.months - 1)):
                last = schema.month_bounds(last.replace(day=28))[1]
            for name in schema.ensure_partitions_for_range(connection, now, last):
                print(f"[ledger] partition {name}")

        report(connection)
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
