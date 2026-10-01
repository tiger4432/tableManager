"""The flattened ledger read for the main grid: `ledger_atom_rows` - one row per (atom, source
row), keys and payload as plain text - and the two ref-table indexes it joins on (총괄 0fb9e9390).

    conda run -n assy_manager python server/migrations/add_ledger_atom_rows.py --report
    conda run -n assy_manager python server/migrations/add_ledger_atom_rows.py

Additive and idempotent. The ref table is not partitioned, so its indexes are built
CONCURRENTLY and writes continue. The ledger table gets nothing. The grid opens the view once
`table_config.json` carries its entry - copy `ledger_atom_rows` from the shipped sample.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import engine                                        # noqa: E402
from ledger import schema                                                   # noqa: E402


def report(connection):
    with connection.cursor() as cursor:
        for name in (schema.ROW_REF_RAW_INDEX, schema.ROW_REF_ROW_INDEX, schema.ATOM_ROWS_VIEW):
            cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (name,))
            exists = bool(cursor.fetchone()[0])
            size = None
            if exists and name != schema.ATOM_ROWS_VIEW:
                cursor.execute("SELECT pg_size_pretty(pg_relation_size(to_regclass(%s)))", (name,))
                size = cursor.fetchone()[0]
            print(f"  {name:28s} exists={exists} size={size or '-'}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", action="store_true",
                        help="print presence and index sizes and change nothing")
    args = parser.parse_args(argv)
    connection = engine.raw_connection()
    try:
        if args.report:
            report(connection)
            return 0
        # CONCURRENTLY refuses a transaction block; the wrapper's `.autocommit` does not reach
        # psycopg2 (`add_ledger_source_events.py` measured it), so the driver's is set.
        driver = getattr(connection, "driver_connection", connection)
        driver.autocommit = True
        with driver.cursor() as cursor:
            schema.ensure_row_ref_table(cursor)
            for statement in schema.row_ref_indexes(schema.world_names(), concurrently=True):
                cursor.execute(statement)
            cursor.execute(schema.atom_rows_view_sql(schema.world_names()))
        report(driver)
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
