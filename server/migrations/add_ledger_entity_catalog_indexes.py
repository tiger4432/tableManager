"""Indexes for the global Ledger Graph entity catalogue and entity subgraph.

    conda run -n assy_manager python server/migrations/add_ledger_entity_catalog_indexes.py
    conda run -n assy_manager python server/migrations/add_ledger_entity_catalog_indexes.py --report

Additive and idempotent. ``idx_ledger_register_search`` is partial to register
atoms and serves contains-search over structured identities. The full
``idx_ledger_subject_entity`` B-tree serves exact (type, keys) frontier probes.

Both indexes are declared on the partitioned parent so future month partitions
inherit them. PostgreSQL cannot create an index concurrently on a partitioned
parent, so the operator should run this migration in a maintenance window on a
large ledger. The route refuses indexed text search when the first index is
absent; it never falls back to a JSON text full scan.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import engine                                        # noqa: E402
from ledger import schema                                                   # noqa: E402


def report(connection):
    with connection.cursor() as cursor:
        for name in (schema.REGISTER_SEARCH_INDEX, schema.SUBJECT_ENTITY_INDEX):
            cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (name,))
            exists = bool(cursor.fetchone()[0])
            size = None
            if exists:
                cursor.execute("""
                    SELECT pg_size_pretty(COALESCE(
                        (SELECT sum(pg_relation_size(inhrelid))
                         FROM pg_inherits WHERE inhparent = to_regclass(%s)),
                        pg_relation_size(to_regclass(%s))))
                """, (name, name))
                size = cursor.fetchone()[0]
            print(f"  {name:36s} exists={exists} size={size or '-'}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", action="store_true",
                        help="print index presence and change nothing")
    args = parser.parse_args(argv)
    connection = engine.raw_connection()
    try:
        if args.report:
            report(connection)
            return 0
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            cursor.execute(schema.REGISTER_SEARCH_INDEX_SQL)
            cursor.execute(schema.SUBJECT_ENTITY_INDEX_SQL)
        connection.commit()
        report(connection)
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
