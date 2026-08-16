"""Add first-class source-event identity to the canonical ledger, safely.

Read-only report (default)::

    conda run -n assy_manager python server/migrations/add_ledger_source_events.py

Apply the additive migration::

    conda run -n assy_manager python server/migrations/add_ledger_source_events.py --apply

The historical molecule marker was deliberately never stored, so old atoms cannot be
regrouped without inventing evidence.  This migration therefore gives each old atom its
own event (`source_event_state = legacy_atom`).  New writes group atoms by the opaque
source-event UUID produced in `ledger.envelope`.

Safety:
* no DELETE, DROP, or rewrite of claim payloads;
* nullable columns are metadata-only additions;
* backfill commits bounded batches, one physical partition at a time;
* serving indexes are built CONCURRENTLY, outside a transaction;
* NOT NULL is installed only after a validated check proves the backfill complete.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import engine  # noqa: E402
from ledger import schema  # noqa: E402


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
    for column in ("source_event_id", "source_event_state"):
        present = schema.column_exists(connection, schema.LEDGER_TABLE, column)
        print(f"column={column} exists={present}")
    if schema.column_exists(connection, schema.LEDGER_TABLE, "source_event_id"):
        missing = _scalar(
            connection,
            f"SELECT count(*) FROM {schema.LEDGER_TABLE} WHERE source_event_id IS NULL")
        states = []
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT coalesce(source_event_state, '<null>'), count(*) "
                f"FROM {schema.LEDGER_TABLE} GROUP BY 1 ORDER BY 1")
            states = cursor.fetchall()
        print(f"missing_source_event_id={missing}")
        for state, count in states:
            print(f"state={state} atoms={count}")
    for index in (schema.SOURCE_EVENT_INDEX, schema.OBJECT_ENTITY_INDEX):
        print(f"index={index} exists={_scalar(connection, 'SELECT to_regclass(%s) IS NOT NULL', (index,))}")


def _add_columns(connection):
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '20s'")
        for column, statement in schema.LEDGER_ADDITIONS:
            if not schema.column_exists(cursor, schema.LEDGER_TABLE, column):
                print(f"adding column {column}")
                cursor.execute(statement)
    connection.commit()


def _backfill_partition(connection, partition, batch_size):
    changed = 0
    while True:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '20s'")
            cursor.execute(f"""
                WITH todo AS (
                    SELECT ctid FROM {partition}
                    WHERE source_event_id IS NULL
                    ORDER BY occurred_at, id
                    LIMIT %s
                )
                UPDATE {partition} atom
                   SET source_event_id = atom.id,
                       source_event_state = 'legacy_atom'
                  FROM todo
                 WHERE atom.ctid = todo.ctid
            """, (int(batch_size),))
            batch = max(0, cursor.rowcount or 0)
        connection.commit()
        changed += batch
        if batch:
            print(f"backfill partition={partition} batch={batch} total={changed}")
        if batch < batch_size:
            return changed


def _build_indexes(connection):
    """Build partition indexes concurrently, then attach them to parent indexes.

    PostgreSQL refuses `CREATE INDEX CONCURRENTLY` on a partitioned parent.  A plain
    parent build would scan and lock every partition, defeating the migration's scale
    contract.  The supported online pattern is: metadata-only index on ONLY parent,
    concurrent physical index per child, then ATTACH PARTITION.
    """
    connection.commit()
    # SQLAlchemy's `raw_connection()` returns a ConnectionFairy.  Assigning
    # `.autocommit` on that wrapper does not reliably reach psycopg2 (the first live
    # run proved it by PostgreSQL's ActiveSqlTransaction refusal), so unwrap the exact
    # driver connection for this one operation.
    driver = getattr(connection, "driver_connection", connection)
    previous = driver.autocommit
    driver.autocommit = True
    try:
        with driver.cursor() as cursor:
            for name, columns, predicate in schema.SOURCE_EVENT_INDEX_SPECS:
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS {name} ON ONLY "
                    f"{schema.LEDGER_TABLE} {columns} {predicate}")
        partition_names = [name for name, _bound in schema.partitions(driver)]
        for parent_name, columns, predicate in schema.SOURCE_EVENT_INDEX_SPECS:
            for partition in partition_names:
                suffix = partition.removeprefix(schema.LEDGER_TABLE + "_")
                child_name = f"{parent_name}_{suffix}"
                with driver.cursor() as cursor:
                    print(f"create index concurrently {child_name}")
                    cursor.execute(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {child_name} "
                        f"ON {partition} {columns} {predicate}")
    finally:
        driver.autocommit = previous

    # ATTACH is metadata-only but transactional.  A failed/retried migration asks the
    # catalogue first so it never mistakes "already attached" for a new defect.
    for parent_name, _columns, _predicate in schema.SOURCE_EVENT_INDEX_SPECS:
        for partition, _bound in schema.partitions(connection):
            suffix = partition.removeprefix(schema.LEDGER_TABLE + "_")
            child_name = f"{parent_name}_{suffix}"
            attached = _scalar(connection, """
                SELECT EXISTS (
                    SELECT 1 FROM pg_inherits
                    WHERE inhparent = to_regclass(%s)
                      AND inhrelid = to_regclass(%s))
            """, (parent_name, child_name))
            if attached:
                continue
            with connection.cursor() as cursor:
                cursor.execute(
                    f"ALTER INDEX {parent_name} ATTACH PARTITION {child_name}")
            connection.commit()


def _install_constraints(connection):
    checks = {
        "ck_ledger_source_event_present":
            "source_event_id IS NOT NULL AND source_event_state IS NOT NULL",
        "ck_ledger_source_event_state":
            "source_event_state IN ('source_molecule', 'source_record', 'legacy_atom')",
    }
    with connection.cursor() as cursor:
        for name, expression in checks.items():
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conrelid = to_regclass(%s) AND conname = %s)
            """, (schema.LEDGER_TABLE, name))
            if not cursor.fetchone()[0]:
                cursor.execute(
                    f"ALTER TABLE {schema.LEDGER_TABLE} ADD CONSTRAINT {name} "
                    f"CHECK ({expression}) NOT VALID")
            cursor.execute(
                f"ALTER TABLE {schema.LEDGER_TABLE} VALIDATE CONSTRAINT {name}")
        cursor.execute(
            f"ALTER TABLE {schema.LEDGER_TABLE} ALTER COLUMN source_event_id SET NOT NULL")
        cursor.execute(
            f"ALTER TABLE {schema.LEDGER_TABLE} ALTER COLUMN source_event_state SET NOT NULL")
    connection.commit()


def apply(connection, batch_size):
    if not _scalar(connection, "SELECT to_regclass(%s) IS NOT NULL",
                   (schema.LEDGER_TABLE,)):
        raise RuntimeError("ledger_events is absent; run add_ledger_events.py first")
    _add_columns(connection)
    total = 0
    for partition, _bound in schema.partitions(connection):
        total += _backfill_partition(connection, partition, batch_size)
    remaining = _scalar(
        connection,
        f"SELECT count(*) FROM {schema.LEDGER_TABLE} WHERE source_event_id IS NULL")
    if remaining:
        raise RuntimeError(f"source-event backfill incomplete: {remaining} atoms remain")
    _build_indexes(connection)
    _install_constraints(connection)
    print(f"backfilled={total} remaining=0 constraints=validated")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true",
                        help="perform the additive migration; default is report only")
    parser.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args(argv)
    if not 100 <= args.batch_size <= 100_000:
        parser.error("--batch-size must be between 100 and 100000")
    connection = engine.raw_connection()
    try:
        if args.apply:
            apply(connection, args.batch_size)
        report(connection)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
