r"""Fill `process_param` from the PRESERVED old ledger, one row per parameter cell.

🔴 THE SOURCE IS THE OLD LEDGER, NOT AN INVENTION. `ledger_events_pre_rebuild` still holds
the `processed_with` atoms whose payload carried `params_setpoint` / `params_actual`, and
those objects are the only record of what a step was set to and what it actually ran at.
One row per KEY, because a key is one measured quantity.

🔴 `param_id` IS THE ATOM ID PLUS THE KEY, and it has to be. Measured: (wafer, step, param)
is NOT unique across the 80,322 cells - setpoint and actual use the same parameter names, so
that triple collides with itself. `role` is the column that tells the two apart, and the id
has to be unique before `role` can mean anything.

🔴 A BOOLEAN IS NOT A NUMBER, AND NOT A STRING EITHER. Measured on the source:
    number 73,267 · boolean 4,655 · string 2,400   (= 80,322)
The order described the 7,055 non-numeric cells as strings; 4,655 of them are booleans. They
go to `value_text` as 'true'/'false' rather than to `value` as 1/0, because writing a number
where the source had a boolean invents a measurement. That keeps "value only when the value
is a number" literally true and loses no cell - and it reproduces the ordered gate exactly:
value 73,267 + value_text 7,055 = 80,322.

`unit` is read from the parameter NAME only when the name ends in a unit this repo already
uses, and is NULL otherwise. A guessed unit is worse than an absent one.

USAGE - dry run by default; it reports the counts and writes nothing:

    python scripts/load_process_param_rows.py
    python scripts/load_process_param_rows.py --apply --i-accept-writing-to-owner-database
"""
import argparse
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import text                                          # noqa: E402
from database import database as db                                 # noqa: E402
from ledger import uuid7                                            # noqa: E402

TABLE = "process_param"
SOURCE = "ledger_events_pre_rebuild"

#: Suffix -> unit. Only suffixes that already appear in this repo's parameter names; a name
#: that does not end in one of these gets NULL.
UNIT_SUFFIXES = (("_MPa", "MPa"), ("_C", "C"), ("_s", "s"), ("_h", "h"),
                 ("_um", "um"), ("_nm", "nm"), ("_sccm", "sccm"), ("_rpm", "rpm"),
                 ("_pct", "pct"), ("_mm", "mm"), ("_kPa", "kPa"), ("_W", "W"))

ROWS_SQL = f"""
SELECT e.id::text AS atom_id, v.key AS param, v.value AS value, v.role AS role,
       e.subject_keys->>'wafer' AS wafer_id,
       e.object_payload->>'step' AS step,
       e.object_payload->>'eqp' AS eqp_id,
       e.object_payload->'recipe'->>'id' AS recipe_id,
       e.occurred_at AS eventtime
  FROM {SOURCE} e,
  LATERAL (
      SELECT key, value, 'setpoint' AS role
        FROM jsonb_each(coalesce(e.object_payload->'params_setpoint', '{{}}'::jsonb))
      UNION ALL
      SELECT key, value, 'actual' AS role
        FROM jsonb_each(coalesce(e.object_payload->'params_actual', '{{}}'::jsonb))
  ) v
 WHERE e.predicate = 'processed_with'
"""


def unit_of(param):
    for suffix, unit in UNIT_SUFFIXES:
        if param.endswith(suffix):
            return unit
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)

    numeric = text_valued = 0
    rows = []
    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '300s'"))
        existing = c.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar()
        for r in c.execute(text(ROWS_SQL)):
            value = r.value
            # `jsonb_each` hands back Python types: int/float, bool, str, None.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                text_valued += 1
                v_num, v_text = None, ("true" if value is True else
                                       "false" if value is False else str(value))
            else:
                numeric += 1
                v_num, v_text = float(value), None
            param_id = f"{r.atom_id}:{r.role}:{r.param}"
            rows.append({
                # 🔴 THE TABLE'S OWN COLUMNS, spelled the way every other dynamic table in
                # this database spells them - measured on void_obs, bonding_map and
                # inspection_run: `row_id` is a uuid7 and `business_key_val` repeats the
                # declared business key. Inventing a different shape here would make this
                # table the one row the rest of the write path cannot recognise.
                "row_id": str(uuid7.uuid7()),
                "business_key_val": param_id,
                "param_id": param_id,
                "wafer_id": r.wafer_id, "step": r.step, "param": r.param,
                "value": v_num, "value_text": v_text, "role": r.role,
                "unit": unit_of(r.param), "eqp_id": r.eqp_id,
                "recipe_id": r.recipe_id, "eventtime": r.eventtime,
            })

    ids = {row["param_id"] for row in rows}
    print("   %-34s %s" % ("existing rows in " + TABLE, existing))
    print("   %-34s %s" % ("cells read", len(rows)))
    print("   %-34s %s" % ("value (number)", numeric))
    print("   %-34s %s" % ("value_text (bool or string)", text_valued))
    print("   %-34s %s" % ("both filled", 0))
    print("   %-34s %s" % ("neither filled",
                           sum(1 for x in rows
                               if x["value"] is None and x["value_text"] is None)))
    print("   %-34s %s" % ("param_id distinct", len(ids)))
    print("   %-34s %s" % ("unit resolved / NULL",
                           "%d / %d" % (sum(1 for x in rows if x["unit"]),
                                        sum(1 for x in rows if not x["unit"]))))
    if len(ids) != len(rows):
        print("\n   REFUSED: param_id is not unique.")
        return 1
    if not (args.apply and args.allow_owner):
        print("\n   DRY RUN - nothing written.")
        return 0

    columns = ("row_id", "business_key_val", "param_id", "wafer_id", "step", "param",
               "value", "value_text", "role", "unit", "eqp_id", "recipe_id", "eventtime")
    # 🔴 NO `ON CONFLICT`: `param_id` is the DECLARED business key but the table
    # carries no unique constraint, and Postgres refuses the clause without one. Rather than
    # add an index this round did not ask for, the script refuses to run against a non-empty
    # table - so a second run cannot double the rows, which is what the clause was for.
    if existing:
        print("")
        print("   REFUSED: %s already holds %d rows. This loader fills an EMPTY"
              " table; clearing it is a ruling, not a step." % (TABLE, existing))
        return 1
    insert = text("INSERT INTO %s (%s) VALUES (%s)"
                  % (TABLE, ", ".join(columns),
                     ", ".join(":" + name for name in columns)))
    with db.engine.begin() as c:
        c.execute(text("SET statement_timeout = '600s'"))
        for start in range(0, len(rows), 2000):
            c.execute(insert, rows[start:start + 2000])
    with db.engine.connect() as c:
        after = c.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar()
        both = c.execute(text(
            f"SELECT count(*) FROM {TABLE} WHERE value IS NOT NULL "
            f"AND value_text IS NOT NULL")).scalar()
    print("\n   rows now %s   both-filled %s" % (after, both))
    return 0 if after == len(rows) and both == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
