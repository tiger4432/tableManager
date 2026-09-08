r"""Widen `ck_ledger_objectless_has_no_payload` so a registration may carry its attributes.

🔴 WHAT THE OLD RULE SAID AND WHY IT HAD TO CHANGE. `CHECK (object_kind IS NOT NULL OR
object_payload IS NULL)` -- an atom with no object carries no payload. Since S-52 a
`register` atom carries the SUBJECT's declared attributes in `object_payload.qualifiers`,
which `envelope.registration_fingerprint` reads and the walk turns into a node's columns. So
a declaration that gave an entity one attribute could not be written at all: the translator
produced the atom and the database refused the INSERT, on the parent and on all 17
partitions.

🔴 THE RULE IS STILL A RULE. The new one is `object_kind IS NOT NULL OR object_payload IS
NULL OR (the payload is an object whose ONLY key is qualifiers)`. An objectless atom
carrying a `value` or a `type` is an object wearing no name and is refused exactly as
before.

🔴 IT IS STRICTLY WEAKER, AND THAT IS THE WHOLE SAFETY ARGUMENT. The new predicate is the
old one OR one more disjunct, so every row that satisfied the old one satisfies this. No
existing row can violate it, the validation scan cannot fail, and there is no data to fix
before or after.

MEASURED BEFORE IT WAS DESIGNED (this deployment's PostgreSQL, 18.3, against a scratch
partitioned table -- the ledger itself was not touched):

    ALTER TABLE <parent> ADD CONSTRAINT ... NOT VALID    accepted, and RECURSES: the
                                                         constraint lands on the parent and
                                                         on every partition, all NOT VALID
    ALTER TABLE <parent> VALIDATE CONSTRAINT ...         accepted, and marks the parent AND
                                                         every partition validated

`NOT VALID` is not a shortcut: it enforces the rule on every INSERT and UPDATE from the
moment it lands. What it skips is re-reading rows that are already there. That is why the
split below is what it is:

    ledger/schema.py `ensure_schema`   DROP old + ADD new NOT VALID, in ONE transaction, so
                                      the table never carries neither rule. Catalogue only,
                                      no scan -- an operator starting a backfill has not
                                      asked for a full read of the ledger.
    THIS SCRIPT --apply               the same, and then the VALIDATE scan, which is the
                                      operator's decision because it is the only part with
                                      a cost.

USAGE -- dry run by default:

    python scripts/migrate_ledger_objectless_payload_constraint.py
    python scripts/migrate_ledger_objectless_payload_constraint.py --apply \
        --i-accept-writing-to-owner-database

ROLLBACK (the ledger must hold no registration carrying attributes, or this will fail):

    ALTER TABLE ledger_events DROP CONSTRAINT ck_ledger_objectless_carries_only_qualifiers;
    ALTER TABLE ledger_events ADD CONSTRAINT ck_ledger_objectless_has_no_payload
      CHECK (object_kind IS NOT NULL OR object_payload IS NULL);
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database import database as db                                  # noqa: E402
from ledger import schema                                            # noqa: E402


def state(cursor):
    """What the catalogue says right now, parent and partitions."""
    cursor.execute(
        "SELECT rel.relname, con.convalidated FROM pg_constraint con "
        "JOIN pg_class rel ON rel.oid = con.conrelid "
        "WHERE con.conname = %s ORDER BY 1", (schema.OBJECTLESS_PAYLOAD_CONSTRAINT,))
    widened = cursor.fetchall()
    cursor.execute(
        "SELECT count(*) FROM pg_constraint WHERE conname = %s",
        (schema.RETIRED_OBJECTLESS_CONSTRAINT,))
    retired = int(cursor.fetchone()[0])
    return widened, retired


def report(widened, retired):
    print(f"  {schema.RETIRED_OBJECTLESS_CONSTRAINT}: {retired} relation(s)")
    print(f"  {schema.OBJECTLESS_PAYLOAD_CONSTRAINT}: {len(widened)} relation(s), "
          f"{sum(1 for _, valid in widened if valid)} validated")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--i-accept-writing-to-owner-database", action="store_true",
                        dest="accepted")
    args = parser.parse_args(argv)
    if args.apply and not args.accepted:
        parser.error("--apply also needs --i-accept-writing-to-owner-database")

    connection = db.engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            if not schema.constraint_exists(cursor, schema.LEDGER_TABLE,
                                            schema.RETIRED_OBJECTLESS_CONSTRAINT) \
                    and not schema.constraint_exists(cursor, schema.LEDGER_TABLE,
                                                     schema.OBJECTLESS_PAYLOAD_CONSTRAINT):
                print(f"{schema.LEDGER_TABLE} carries neither rule -- nothing to migrate. "
                      f"Is this the right database?")
                return 1
            print("before:")
            report(*state(cursor))
        if not args.apply:
            print("\ndry run: pass --apply --i-accept-writing-to-owner-database to migrate")
            return 0

        # One transaction: the DROP and the ADD together, so the table never carries
        # neither rule. Both are catalogue-only; neither reads a row.
        with connection.cursor() as cursor:
            changed = schema.ensure_objectless_payload_constraint(cursor)
        connection.commit()
        print(f"\nwidened: {changed}")

        # The scan, in its own transaction. `VALIDATE` takes SHARE UPDATE EXCLUSIVE rather
        # than ACCESS EXCLUSIVE, so readers and writers keep going while it runs.
        with connection.cursor() as cursor:
            cursor.execute(f"ALTER TABLE {schema.LEDGER_TABLE} VALIDATE CONSTRAINT "
                           f"{schema.OBJECTLESS_PAYLOAD_CONSTRAINT}")
        connection.commit()
        with connection.cursor() as cursor:
            print("after:")
            report(*state(cursor))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
