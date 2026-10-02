"""Give each outbox event the ledger's own mark, so the ledger's queue survives a restart.

Read-only report (default)::

    conda run -n assy_manager python server/migrations/add_outbox_ledger_state.py

Apply - with the app STOPPED (run_app.bat closed), BEFORE the code that reads the column starts;
every outbox insert names it::

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

🔴 IT NEVER WAITS IN SILENCE (응용 c4f0323cc, 총괄 a3d19dc51). Measured in a scratch schema: a
session idle in transaction after READING the outbox holds the column step; one idle after
WRITING to it holds both steps, and an index build cut off there is left INVALID. Each step
therefore waits at most LOCK_TIMEOUT, and a step that runs out names the sessions holding the
outbox and stops. Run again after they end - the column is IF-guarded and an invalid index from
a cut-off run is dropped and built again.
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
#: How long one step waits for the outbox's locks before it names who holds them and stops.
LOCK_TIMEOUT = "30s"


class Waited(RuntimeError):
    """A step ran out of LOCK_TIMEOUT - the message names the step and the sessions."""


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


def _index_valid(connection):
    """True, False (left INVALID by a cut-off build) or None (absent)."""
    return _scalar(connection,
                   "SELECT (SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(%s))",
                   (INDEX,))


def _sessions(connection):
    """Other sessions of this database idle in a transaction or holding a lock on the outbox:
    (pid, state, seconds in transaction, application_name)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT a.pid, a.state, round(extract(epoch FROM now() - a.xact_start)), "
            "       coalesce(nullif(a.application_name, ''), '-') "
            "  FROM pg_stat_activity a "
            " WHERE a.datname = current_database() AND a.pid <> pg_backend_pid() "
            "   AND (a.state = 'idle in transaction' OR EXISTS ("
            "        SELECT 1 FROM pg_locks l WHERE l.pid = a.pid AND l.relation = to_regclass(%s))) "
            " ORDER BY 1", (TABLE,))
        return cursor.fetchall()


def _said(sessions):
    return "; ".join("pid %s %s %ss %s" % row for row in sessions) or "(none now)"


def _step(connection, label, statements):
    """Run one step under LOCK_TIMEOUT; out of time -> Waited naming the sessions."""
    from psycopg2 import errors

    waiting = _sessions(connection)
    if waiting:
        print(f"{label}: sessions that can hold it - {_said(waiting)}")
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        return cursor.rowcount
    except errors.LockNotAvailable:
        connection.rollback()
        raise Waited(f"STOPPED at {label}: waited {LOCK_TIMEOUT} for the outbox - {_said(_sessions(connection))}. "
                     f"Next: end those sessions (stop the app: close run_app.bat) and run --apply again")


def report(connection):
    print(f"server_version={_scalar(connection, 'SHOW server_version')}")
    present = _column_exists(connection)
    print(f"column={COLUMN} exists={present}")
    print(f"index={INDEX} valid={_index_valid(connection)}")
    if not present:
        return
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT coalesce(split_part({COLUMN}, ':', 1), '<null = yet to follow>'), "
                       f"count(*) FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC")
        for state, count in cursor.fetchall():
            print(f"  {state}: {count:,}")


def apply(connection):
    with connection.cursor() as cursor:
        cursor.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
    if not _column_exists(connection):
        unprocessed = _step(connection, "add column", [
            f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {COLUMN} TEXT DEFAULT 'done'",
            f"ALTER TABLE {TABLE} ALTER COLUMN {COLUMN} DROP DEFAULT",
            f"UPDATE {TABLE} SET {COLUMN} = NULL WHERE processed_chain = false"])
        connection.commit()
        print(f"added {COLUMN} - existing events 'done', {unprocessed} unprocessed back to NULL")
    else:
        print(f"{COLUMN} already present")
    # CONCURRENTLY refuses a transaction block, and the wrapper's `.autocommit` does not reach
    # psycopg2 (add_ledger_atom_rows.py) - the driver's is set, after the open one is closed.
    connection.commit()
    driver = getattr(connection, "driver_connection", connection)
    driver.autocommit = True
    try:
        if _index_valid(driver) is False:
            _step(driver, "drop the invalid index", [f"DROP INDEX IF EXISTS {INDEX}"])
            print(f"{INDEX} was left invalid by a cut-off build - dropped")
        _step(driver, "build the index", [
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX} ON {TABLE} (id) "
            f"WHERE processed_chain = true AND {COLUMN} IS NULL"])
    finally:
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
            try:
                apply(connection)
            except Waited as stopped:
                print(stopped)
                return 3
        report(connection)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
