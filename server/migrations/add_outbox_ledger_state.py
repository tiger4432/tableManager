"""Give each outbox event the ledger's own mark, so the ledger's queue survives a restart.

Read-only report (default)::

    conda run -n assy_manager python server/migrations/add_outbox_ledger_state.py

Apply (BEFORE the code that reads the column starts - every outbox insert names it)::

    conda run -n assy_manager python server/migrations/add_outbox_ledger_state.py --apply

총괄 bb9b1c19c (가), 소유자 10-02 「누락 절대 없고」. The ledger followed the outbox through a
memory queue the chain group filled; a restart between the group's commit and the drain lost
those events (measured: 2,000 rows committed, restart, 0 atoms). `ledger_state` is the ledger's
cell on the event row itself: NULL = yet to follow, 'done', or 'failed: <why>'.

Safety:
* ADD COLUMN with a constant DEFAULT is metadata-only on PostgreSQL 11+ (the report prints
  the server version) - every existing event reads 'done' with no rewrite; the DEFAULT is then
  dropped so a new event starts NULL;
* the events the chain has NOT processed yet are set back to NULL - the ledger follows them
  after the chain, as it would have;
* the partial index is built CONCURRENTLY, so writes go on.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import engine  # noqa: E402

TABLE = "database_outbox"
COLUMN = "ledger_state"
INDEX = "idx_outbox_ledger_pending"


def _scalar(connection, sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]


def _column_exists(connection):
    return bool(_scalar(
        connection,
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s AND table_schema = current_schema()",
        (TABLE, COLUMN)))


def report(connection):
    print(f"server_version={_scalar(connection, 'SHOW server_version')}")
    present = _column_exists(connection)
    print(f"column={COLUMN} exists={present}")
    print(f"index={INDEX} exists={_scalar(connection, 'SELECT to_regclass(%s) IS NOT NULL', (INDEX,))}")
    if not present:
        return
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT coalesce(split_part({COLUMN}, ':', 1), '<null = yet to follow>'), "
                       f"count(*) FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC")
        for state, count in cursor.fetchall():
            print(f"  {state}: {count:,}")


def apply(connection):
    if not _column_exists(connection):
        with connection.cursor() as cursor:
            cursor.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} TEXT DEFAULT 'done'")
            cursor.execute(f"ALTER TABLE {TABLE} ALTER COLUMN {COLUMN} DROP DEFAULT")
            cursor.execute(f"UPDATE {TABLE} SET {COLUMN} = NULL WHERE processed_chain = false")
            print(f"added {COLUMN} - existing events 'done', {cursor.rowcount} unprocessed back to NULL")
        connection.commit()
    else:
        print(f"{COLUMN} already present")
    # CONCURRENTLY refuses a transaction block, and the wrapper's `.autocommit` does not reach
    # psycopg2 (add_ledger_atom_rows.py) - the driver's is set, after the open one is closed.
    connection.commit()
    driver = getattr(connection, "driver_connection", connection)
    driver.autocommit = True
    with driver.cursor() as cursor:
        cursor.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX} ON {TABLE} (id) "
                       f"WHERE processed_chain = true AND {COLUMN} IS NULL")
    driver.autocommit = False
    print(f"{INDEX} ensured")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="perform the migration (default is a read-only report)")
    args = parser.parse_args(argv)
    connection = engine.raw_connection()
    try:
        if args.apply:
            apply(connection)
        report(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
