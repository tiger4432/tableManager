r"""Rewrite `uq_ledger_atom` so it indexes DIGESTS of the big columns instead of the columns.

🔴 WHAT IS NOT CHANGING: which atoms count as the same atom. Every column of the old key is
still in the new one; three of them arrive as `md5(...)` instead of in full. The jsonb payload
alone costs 1,695 bytes per atom, which is why this index is 75% of the ledger's index bytes.

🔴 `source_raw_ref` STAYS IN THE KEY, and that was measured before it was designed. 774 atoms
differ by NOTHING ELSE: on the index's own columns there are 0 duplicate groups, without
`source_raw_ref` there are 774, and without `occurred_at` as well there are 8,933. Dropping the
column would have failed the index build outright.

⚠️ AND THE COLLISION STORY IS NOT "structurally impossible" -- measured, not assumed:

    CREATE INDEX   a collision among today's rows fails the build LOUDLY. A build that
                   succeeds is therefore proof this data has none.
    INSERT         `store.insert_atoms` uses `ON CONFLICT DO NOTHING` with NO target
                   (store.py:165), so it swallows a conflict on ANY unique index. A future
                   atom whose three digests all collide with an existing row's, under the same
                   occurred_at, predicate, subject_type and translator_ver, would be dropped in
                   silence rather than refused.

    The probability is negligible and the alternative (the full payload in the key) costs 639MB,
    but "negligible" is the honest word, not "impossible".

⚠️ SIZE IS MEASURED OVER THE PARTITIONS. `pg_relation_size('ledger_events')` answers 0 bytes --
it is a partitioned parent and the storage is on its children. Measuring the parent would report
a shrink from nothing to nothing and call it a success.

USAGE -- dry run by default; the gate runs before the commit either way:

    python scripts/shrink_uq_ledger_atom.py
    python scripts/shrink_uq_ledger_atom.py --apply --i-accept-writing-to-owner-database

ROLLBACK:

    DROP INDEX uq_ledger_atom;
    CREATE UNIQUE INDEX uq_ledger_atom ON ledger_events
      (occurred_at, predicate, subject_type, subject_keys,
       COALESCE(object_payload, '{}'::jsonb), source_translator_ver, source_raw_ref);
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import text                                          # noqa: E402
from database import database as db                                  # noqa: E402

INDEX = "uq_ledger_atom"
TABLE = "ledger_events"

OLD_KEY = ("occurred_at, predicate, subject_type, subject_keys, "
           "COALESCE(object_payload,'{}'::jsonb), source_translator_ver, source_raw_ref")
NEW_SQL = f"""
CREATE UNIQUE INDEX {INDEX} ON {TABLE}
  (occurred_at, predicate, subject_type,
   md5(subject_keys::text),
   md5(COALESCE(object_payload, '{{}}'::jsonb)::text),
   source_translator_ver,
   md5(source_raw_ref))"""

#: The index's own bytes live on its PARTITION indexes, which carry generated names -- so they
#: are found through `pg_inherits` on the index, not by name matching.
SIZE_SQL = f"""
SELECT coalesce(sum(pg_relation_size(c.oid)), 0)
  FROM pg_inherits h
  JOIN pg_class c ON c.oid = h.inhrelid
  JOIN pg_class p ON p.oid = h.inhparent
 WHERE p.relname = '{INDEX}'"""


def _index_bytes(c):
    return int(c.execute(text(SIZE_SQL)).scalar() or 0)


def _duplicate_groups(c, key):
    return c.execute(text(
        f"SELECT count(*) FROM (SELECT 1 FROM {TABLE} GROUP BY {key} "
        "HAVING count(*) > 1) t")).scalar()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '1800s'"))
        try:
            rows_before = c.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar()
            dup_before = _duplicate_groups(c, OLD_KEY)
            size_before = _index_bytes(c)
            print("   rows                         %10d" % rows_before)
            print("   duplicate groups on the OLD key %7d   %s"
                  % (dup_before, "OK" if dup_before == 0 else "<- the index is not unique?!"))
            print("   this index, over partitions  %10.1f MB" % (size_before / 1048576.0))
            if dup_before != 0:
                c.rollback()
                print("REFUSED - uniqueness does not hold before the change.")
                return 1

            c.execute(text(f"DROP INDEX {INDEX}"))
            c.execute(text(NEW_SQL))

            rows_after = c.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar()
            dup_after = _duplicate_groups(c, OLD_KEY)
            size_after = _index_bytes(c)
            # 🔴 EXPLAIN THE QUERIES THAT MATTER, NOT A QUERY. The walk reads by
            # (subject_type, subject_keys) -- `idx_ledger_subject_entity`, which this change
            # does not touch; the plan that CAN move is the uniqueness probe on the new key.
            # A containment probe answers Seq Scan and says nothing about either, which is
            # what the first draft of this check did.
            plans = {}
            plans["walk (subject_type, subject_keys)"] = chr(10).join(
                r[0] for r in c.execute(text(
                    f"EXPLAIN SELECT 1 FROM {TABLE} WHERE subject_type = 'wafer' "
                    "AND subject_keys = '{\"wafer\":\"SYN-BW-101-16\"}'::jsonb")))
            plans["uniqueness probe on the new key"] = chr(10).join(
                r[0] for r in c.execute(text(
                    f"EXPLAIN SELECT 1 FROM {TABLE} "
                    "WHERE occurred_at = now() AND predicate = 'inspected' "
                    "AND subject_type = 'wafer' "
                    "AND md5(subject_keys::text) = md5('x') "
                    "AND md5(COALESCE(object_payload, '{}'::jsonb)::text) = md5('y') "
                    "AND source_translator_ver = 'z' AND md5(source_raw_ref) = md5('w')")))
            uses_index = all("Seq Scan" not in text_ for text_ in plans.values())

            print()
            print("   rows                         %10d   %s"
                  % (rows_after, "OK" if rows_after == rows_before else "<- ROWS MOVED"))
            print("   duplicate groups on the OLD key %7d   %s"
                  % (dup_after, "OK - same atoms are still the same"
                     if dup_after == dup_before else "<- the definition changed"))
            print("   this index, over partitions  %10.1f MB   (%.0f%% of before)"
                  % (size_after / 1048576.0,
                     100.0 * size_after / size_before if size_before else 0))
            for label, plan in plans.items():
                first = next((l.strip() for l in plan.splitlines() if "Scan" in l),
                             plan.splitlines()[0].strip())
                print("   %-32s %s" % (label, first[:60]))

            ok = (rows_after == rows_before and dup_after == dup_before
                  and size_after > 0 and size_after < size_before
                  and uses_index)
            print("\n   GATE: %s" % ("PASS" if ok else "FAIL"))
            if ok and args.apply and args.allow_owner:
                c.commit()
                print("COMMITTED.  Rollback SQL is in this file's header.")
            else:
                c.rollback()
                print("ROLLED BACK." if not ok else "DRY RUN - rolled back.")
                return 0 if ok else 1
        except Exception:
            c.rollback()
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
