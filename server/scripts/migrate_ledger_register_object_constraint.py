r"""S-77. Drop `ck_ledger_register_has_no_object` -- the storage layer naming a predicate.

🔴 WHAT THE RULE SAID AND WHY IT HAD TO GO. `CHECK ((predicate = 'register') = (object_kind
IS NULL))`: only the predicate literally spelled `register` may be objectless, and it must
be. That is a DOMAIN WORD in the one layer an operator cannot change by editing a
declaration -- 「코드에 도메인 낱말이 «없다»」, which is an architecture rule and not a style
one.

🔴 IT WAS NOT MERELY REDUNDANT, IT WAS NARROWER THAN THE DECLARATION. Which predicates carry
no object is a declared fact (`object.kind: none`), and `roleframe` already refuses an
emission whose object kind disagrees with its vocabulary signature -- in both directions,
naming the config path. So declare a SECOND objectless predicate (`retire@1`) and the atom
compiles, emits, passes every Python check, and is then refused BY THE DATABASE, three
layers away from the line the operator wrote and with a message that names neither.

🔴 WHAT REMAINS, AND WHY THAT ONE IS DIFFERENT.
`ck_ledger_objectless_carries_only_qualifiers` stays: an atom with no object carries
`qualifiers` and nothing else. It names no predicate and owes nothing to any vocabulary, so
it is true whatever a declaration says -- which is the test for whether a rule belongs at
this layer at all.

🔴 A DROP CANNOT FAIL ON EXISTING DATA, and that is the whole safety argument. Removing a
CHECK weakens the table: every row that satisfied it still satisfies what remains. There is
no validation scan, no window in which the table is wrong, and nothing to fix before or
after. (The sibling migration, `migrate_ledger_objectless_payload_constraint.py`, had to
argue its way to the same conclusion because it REPLACED a rule; this one only removes one.)

⚠️ `ensure_schema` DOES THIS TOO, on every backfill, via
`schema.ensure_register_object_constraint_dropped`. This script exists so an operator can do
it deliberately and SEE it -- before and after, parent and partitions -- rather than
discovering it in a log line.

USAGE -- dry run by default:

    python scripts/migrate_ledger_register_object_constraint.py
    python scripts/migrate_ledger_register_object_constraint.py --apply \
        --i-accept-writing-to-owner-database

ROLLBACK (only valid while `register` is the ONLY objectless predicate declared -- if a
second one has emitted an atom, this will fail, and that failure is the point of S-77):

    ALTER TABLE ledger_events ADD CONSTRAINT ck_ledger_register_has_no_object
      CHECK ((predicate = 'register') = (object_kind IS NULL));
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
    """Which relations still carry the retired rule, parent and partitions."""
    cursor.execute(
        "SELECT rel.relname FROM pg_constraint con "
        "JOIN pg_class rel ON rel.oid = con.conrelid "
        "WHERE con.conname = %s ORDER BY 1",
        (schema.RETIRED_REGISTER_OBJECT_CONSTRAINT,))
    carrying = [row[0] for row in cursor.fetchall()]
    cursor.execute(
        "SELECT count(*) FROM pg_constraint WHERE conname = %s",
        (schema.OBJECTLESS_PAYLOAD_CONSTRAINT,))
    return carrying, int(cursor.fetchone()[0])


def report(carrying, structural):
    print(f"  {schema.RETIRED_REGISTER_OBJECT_CONSTRAINT}: {len(carrying)} relation(s)")
    # 🔴 PRINTED BESIDE IT ON PURPOSE. The question an operator has after a DROP is 「what is
    # still enforced」, and a report that answers only 「it is gone」 invites the wrong one.
    print(f"  {schema.OBJECTLESS_PAYLOAD_CONSTRAINT} (kept): {structural} relation(s)")


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
            carrying, structural = state(cursor)
            if not carrying:
                print(f"{schema.LEDGER_TABLE} does not carry "
                      f"{schema.RETIRED_REGISTER_OBJECT_CONSTRAINT} -- nothing to migrate.")
                report(carrying, structural)
                return 0
            print("before:")
            report(carrying, structural)
        if not args.apply:
            print("\ndry run: pass --apply --i-accept-writing-to-owner-database to migrate")
            return 0

        # Catalogue-only, one statement, no row is read. Dropping on the partitioned PARENT
        # removes it from every partition, which is why the count above is reported rather
        # than a single yes/no: a partial state would be visible here.
        with connection.cursor() as cursor:
            dropped = schema.ensure_register_object_constraint_dropped(cursor)
        connection.commit()
        print(f"\ndropped: {dropped}")
        with connection.cursor() as cursor:
            print("after:")
            report(*state(cursor))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
