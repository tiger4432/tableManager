"""`ledger_translator_cursor.refusal_reasons` - the breakdown of a number that already
exists. **Additive, idempotent, reversible.**

    conda run -n assy_manager python server/migrations/add_ledger_refusal_reasons.py
    conda run -n assy_manager python server/migrations/add_ledger_refusal_reasons.py --report
    conda run -n assy_manager python server/migrations/add_ledger_refusal_reasons.py --reverse

[WHY A COLUMN ON A ROW THAT EXISTS, AND NOT A TABLE]
Ruling R-2026-08-13-F. Named refusal reasons could not be read out of this database at
all: `gate._refusals` is process-local to the backfill, the web server deliberately never
imports `server/ledger`, and the heartbeat note the gate writes is dropped by `/health`.
The cursor row already carries `molecules_refused` - the aggregate this column breaks
down - and it is already written once per batch inside the atom transaction. A separate
reasons table would have been a new relation with its own writer, retention and
lifecycle, for a status strip.

[SAFETY CONTRACT]
- ONE `ALTER TABLE ... ADD COLUMN`, nullable, no DEFAULT and no rewrite: PostgreSQL 11+
  records a nullable column with no default in the catalogue alone, so this does not
  touch a heap page and does not depend on the table's size. It holds ACCESS EXCLUSIVE
  for the duration of the catalogue update only.
- It is GATED on `pg_attribute`, so re-running issues no DDL and takes no lock.
- No row of any table is read or written. Existing cursor rows keep every value they
  have and gain a NULL.

🔴 NULL IS NOT `{}` AND THE DIFFERENCE IS THE POINT.
A row that predates this column can never have its `molecules_refused` broken down - the
names were only ever in the memory of a process that has exited. Both development
databases held exactly such a row (`molecules_refused = 1`, no breakdown) when this ran.
NULL says "this aggregate predates the breakdown"; `{}` says "the current writer has
owned this row and refused nothing". `GET /api/ledger/coverage` reports the difference as
`refusals_unaccounted` rather than rendering an empty breakdown beside a non-zero count,
which would read as a bookkeeping fault that is not there.

[ORDERING - THE HAZARD THIS PROJECT HAS ALREADY PAID FOR]
`add_frame_confirmation.py` documents it: a column added to an existing table is a 500 in
every process that reads it before the migration runs. Both directions are defended here
rather than by hoping for an order:
  * the WRITER (`ledger.schema.ensure_schema`, called at the start of every backfill)
    applies the same additive statement, so a translator can never meet a table it cannot
    write into;
  * the READER (`ledger_trace.coverage`) asks the catalogue which cursor columns exist
    and selects only those, so a web server running ahead of this migration answers
    without the field instead of failing.
This script remains the operator's entry point and the audit trail.

[WHERE THE DDL LIVES]
`server/ledger/schema.py`, with the rest of the ledger's DDL, for the reason
`add_ledger_events.py` states: a second copy in a migration is how a test ends up proving
a lookalike works. The only statement spelled here is the REVERSE, because `schema.py` is
additive-only by contract and a DROP has no business in it.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import engine                                        # noqa: E402
from ledger import schema                                                   # noqa: E402

COLUMN = schema.REFUSAL_REASONS_COLUMN

#: The reverse. `IF EXISTS` so it is idempotent in its own direction, and it is a real
#: reverse rather than a comment: the column carries telemetry, so dropping it loses a
#: breakdown and no atom, no cursor position and no aggregate.
DROP_COLUMN = f"ALTER TABLE {schema.CURSOR_TABLE} DROP COLUMN IF EXISTS {COLUMN}"


def report(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (schema.CURSOR_TABLE,))
        exists = cursor.fetchone()[0]
        print(f"  {schema.CURSOR_TABLE:28s} exists={exists}")
        if not exists:
            return
        print(f"  column {COLUMN:21s} exists="
              f"{schema.column_exists(cursor, schema.CURSOR_TABLE, COLUMN)}")
        # The counts an operator has to see BEFORE and AFTER: this migration must change
        # the second number and nothing else. Quoting the aggregate beside the breakdown
        # is also how the NULL-vs-{} distinction above becomes visible on a real row.
        cursor.execute(f"SELECT count(*) FROM {schema.CURSOR_TABLE}")
        print(f"  cursor rows: {cursor.fetchone()[0]}")
        columns = "source, molecules_done, molecules_refused, incomplete_molecules"
        if schema.column_exists(cursor, schema.CURSOR_TABLE, COLUMN):
            columns += f", {COLUMN}"
        cursor.execute(f"SELECT {columns} FROM {schema.CURSOR_TABLE} ORDER BY source")
        for row in cursor.fetchall():
            print(f"    {row}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", action="store_true",
                        help="print what exists and change nothing")
    parser.add_argument("--reverse", action="store_true",
                        help=f"drop {COLUMN} again (loses the breakdown, nothing else)")
    args = parser.parse_args(argv)

    connection = engine.raw_connection()
    try:
        print("[before]")
        report(connection)

        if args.report:
            return 0

        if args.reverse:
            if schema.column_exists(connection, schema.CURSOR_TABLE, COLUMN):
                with connection.cursor() as cursor:
                    cursor.execute(DROP_COLUMN)
                connection.commit()
                print(f"[ledger] dropped {schema.CURSOR_TABLE}.{COLUMN}")
            else:
                print(f"[ledger] {COLUMN} is already absent - nothing to do")
        else:
            # `ensure_schema` is the single spelling: it creates the two tables if they
            # are missing and applies `CURSOR_ADDITIONS` if they are not. Both are gated
            # on the catalogue, so this is a no-op on an up-to-date database.
            schema.ensure_schema(connection)
            print(f"[ledger] {schema.CURSOR_TABLE}.{COLUMN} is present")

        print("[after]")
        report(connection)
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
