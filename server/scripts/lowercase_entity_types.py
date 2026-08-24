r"""Lowercase every entity TYPE NAME in the ledger -- the data side of the rename.

WHY THIS IS NOT A LEDGER VIOLATION
----------------------------------
The ledger never rewrites a claim, because a claim is somebody's statement about the world
and editing it makes the record lie about what was said and when. `subject_type` is not
that. It is the TYPE LABEL of the thing the claim is about -- `Wafer` and `wafer` name the
same wafer -- and every source row that produced these atoms is still present. By the
standing test ("if this atom were deleted, would the fact survive somewhere else?") the
spelling is a projection, not a record. NOT ONE PREDICATE, VALUE OR TIMESTAMP IS TOUCHED.

WHY THE DATA AND NOT JUST THE DECLARATION
-----------------------------------------
Of 340,548 uppercase atoms, 219,576 (64%) came from v1 translators that are RETIRED. They
cannot be re-derived. Changing only the declaration would leave new atoms spelled `wafer`
and those 219,576 spelled `Wafer` forever -- two worlds that never meet, WITH NO ERROR
RAISED. The walk would simply return less and call it an answer.

WHAT IS IN SCOPE, AND WHAT IS DELIBERATELY NOT
----------------------------------------------
    (1) subject_type                                       340,548   yes
    (2) object_payload->>'type' WHERE object_kind =
        'entity_ref'                                         2,189   yes
    (3) the nested from/to `type` under object_kind =
        'value'                                             72,964   NO -- OTHER VOCABULARY

(3) holds `dt_slot`, `package_gate`, `wafer_grid`, `dt_job`, `bond_layer`: those are FRAME
names -- the words behind the screen's "기반" pills -- not entity types, and they are
already lowercase. They are excluded knowingly. This is why the statements below address
the jsonb PATH ('type') with `jsonb_set` rather than substituting text: a `payload::text`
replace is the obvious implementation and it would walk straight through (3).

THE UNIQUE INDEX IS THE REAL HAZARD
-----------------------------------
    uq_ledger_atom UNIQUE (occurred_at, predicate, subject_type, subject_keys,
                           COALESCE(object_payload,'{}'), source_translator_ver,
                           source_raw_ref)

BOTH rewritten columns sit inside it, so two rows differing ONLY by case would collide and
abort the transaction partway through. `--check` computes every row's POST-migration tuple
and counts duplicates BEFORE anything is written, so that is answered as a number rather
than as a rollback halfway.

USAGE -- dry run by default, and small first:

    python scripts/lowercase_entity_types.py --check
    python scripts/lowercase_entity_types.py --scope dtjob
    python scripts/lowercase_entity_types.py --scope dtjob --apply --i-accept-writing-to-owner-database
    python scripts/lowercase_entity_types.py --scope all   --apply --i-accept-writing-to-owner-database

ROLLBACK -- written down BEFORE the first write, as ordered:

    UPDATE ledger_events SET subject_type = 'Wafer'    WHERE subject_type = 'wafer';
    UPDATE ledger_events SET subject_type = 'Lot'      WHERE subject_type = 'lot';
    UPDATE ledger_events SET subject_type = 'DTJob'    WHERE subject_type = 'dtjob';
    UPDATE ledger_events SET subject_type = 'Recipe'   WHERE subject_type = 'recipe';
    UPDATE ledger_events SET subject_type = 'WaferLeg' WHERE subject_type = 'waferleg';
    UPDATE ledger_events SET object_payload = jsonb_set(object_payload, '{type}', '"Wafer"')
      WHERE object_kind = 'entity_ref' AND object_payload->>'type' = 'wafer';
    UPDATE ledger_events SET object_payload = jsonb_set(object_payload, '{type}', '"Lot"')
      WHERE object_kind = 'entity_ref' AND object_payload->>'type' = 'lot';

`die` was ALREADY lowercase -- 1,405 subject atoms and 119,067 object refs -- so it is
absent from the map on purpose. Reversing `die` would invent an uppercase that never
existed.

ASYMMETRY, STATED PLAINLY: the reverse map above is the ONLY way back for the 219,576
retired-translator atoms, since they cannot be re-derived from source. That is exactly why
`--scope dtjob` (792 rows, re-derivable) runs first and is verified by a walk.
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

#: type -> its lowercase form. `die` is absent because it is already lowercase.
FORWARD = {"Wafer": "wafer", "Lot": "lot", "DTJob": "dtjob",
           "Recipe": "recipe", "WaferLeg": "waferleg"}
SCOPES = {"dtjob": ("DTJob",), "all": tuple(FORWARD)}

SUBJECT_SQL = """
UPDATE ledger_events SET subject_type = lower(subject_type)
WHERE subject_type = ANY(:types) AND subject_type <> lower(subject_type)"""

#: `jsonb_set` names the PATH. A text substitution would also hit the frame vocabulary
#: nested under `object_kind = 'value'`, which is not an entity type. See the docstring.
OBJECT_SQL = """
UPDATE ledger_events
SET object_payload = jsonb_set(object_payload, '{type}',
                               to_jsonb(lower(object_payload->>'type')))
WHERE object_kind = 'entity_ref'
  AND object_payload->>'type' = ANY(:types)
  AND object_payload->>'type' <> lower(object_payload->>'type')"""

COLLISION_SQL = """
SELECT count(*) FROM (
    SELECT occurred_at, predicate, lower(subject_type) AS st, subject_keys,
           CASE WHEN object_kind = 'entity_ref' AND object_payload ? 'type'
                THEN jsonb_set(object_payload, '{type}',
                               to_jsonb(lower(object_payload->>'type')))
                ELSE COALESCE(object_payload, '{}'::jsonb) END AS op,
           source_translator_ver, source_raw_ref
    FROM ledger_events
    GROUP BY 1, 2, 3, 4, 5, 6, 7 HAVING count(*) > 1) dup"""

SUBJECT_CENSUS = "SELECT subject_type, count(*) FROM ledger_events GROUP BY 1"
OBJECT_CENSUS = """
SELECT object_payload->>'type', count(*) FROM ledger_events
WHERE object_kind = 'entity_ref' AND object_payload ? 'type' GROUP BY 1"""


def census(connection):
    return (dict(connection.execute(text(SUBJECT_CENSUS)).fetchall()),
            dict(connection.execute(text(OBJECT_CENSUS)).fetchall()))


def _table(title, before, after):
    print("\n   %s" % title)
    for key in sorted(set(before) | set(after), key=str):
        b, a = before.get(key, 0), after.get(key, 0)
        print("      %-12s %8d -> %8d%s" % (key, b, a, "" if b == a else "   <-"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=sorted(SCOPES), default="dtjob")
    ap.add_argument("--check", action="store_true",
                    help="answer only the unique-index collision question, write nothing")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)
    types = list(SCOPES[args.scope])

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '600s'"))
        try:
            print("collision pre-check (post-migration tuples that would break "
                  "uq_ledger_atom):")
            dup = c.execute(text(COLLISION_SQL)).scalar()
            print("   duplicate tuples: %d   %s"
                  % (dup, "OK" if dup == 0 else "STOP - the transaction would abort"))
            if args.check:
                return 0 if dup == 0 else 1
            if dup:
                print("\nREFUSING to write while a collision exists.")
                return 1

            before_s, before_o = census(c)
            print("\nscope %s -> %s" % (args.scope, ", ".join(types)))
            n1 = c.execute(text(SUBJECT_SQL), {"types": types}).rowcount
            n2 = c.execute(text(OBJECT_SQL), {"types": types}).rowcount
            print("   (1) subject_type rows rewritten   %8d" % n1)
            print("   (2) entity_ref  rows rewritten    %8d" % n2)
            after_s, after_o = census(c)
            _table("subject_type", before_s, after_s)
            _table("entity_ref object type", before_o, after_o)

            if args.apply and args.allow_owner:
                c.commit()
                print("\nCOMMITTED.")
            else:
                c.rollback()
                print("\nDRY RUN - rolled back.")
        except Exception:
            c.rollback()
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
