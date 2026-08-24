r"""Create `void_obs_observed` -- void observations carrying their real inspection time.

WHY A VIEW AND NOT A COLUMN
---------------------------
`void_obs` has no time column at all. Its physical columns are position, size, unit and the
run it belongs to; the moment the wafer was actually inspected lives one join away, in
`inspection_run.observed_at`. Declaring `created_at` instead would pass the validator and
put the SEEDER'S clock on the trend axis -- an honest label on the wrong number.

The other correct option was a verified join declared in the ledger config. Measured and
rejected: `backfill.py` REFUSES any source declaring a join descriptor, at both the execute
(:326) and preview (:509) entries, and the comment on the second says why -- inventing a
reader for the preview would report a pass for a declaration the run cannot execute. Those
are deliberate guards against a false green, and opening them for one fixture source would
widen the blast radius to every source.

THE JOIN IS TOTAL, AND THAT IS THIS VIEW'S PREMISE
--------------------------------------------------
A view over a partial join drops rows in silence, so it was measured first:

    void_obs rows                          103,729
    rows surviving the join                103,729   total
    joined rows with a NULL observed_at          0
    run_uid duplicated in inspection_run         0   one-to-one, so no row multiplies

⚠️ THE COST, WRITTEN DOWN SO IT IS NOT REDISCOVERED LATER: this join now lives in DDL rather
than in configuration, which steps half a pace back from "a different schema costs zero
lines of code". If a production deployment joins these differently, the VIEW is rewritten --
not a declaration swapped. Accepted deliberately because the cost is local and reversible,
where the join option's cost was a guard opened for every source. Revisit when production
vocabulary lands and there is more than one join to serve.

USAGE - dry run by default:

    python scripts/create_void_obs_observed_view.py
    python scripts/create_void_obs_observed_view.py --apply --i-accept-writing-to-owner-database

ROLLBACK - one line, and it touches nothing else:

    DROP VIEW void_obs_observed;
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

VIEW = "void_obs_observed"

#: Read-only by construction: no INSTEAD OF trigger, so Postgres refuses writes through it.
#: Position, size and unit stay the void's own; only the time comes from the run.
CREATE_SQL = f"""
CREATE OR REPLACE VIEW {VIEW} AS
SELECT v.void_uid,
       v.run_uid,
       v.base_wafer_id,
       v.base_x,
       v.base_y,
       v.stack_gate,
       v.inchip_x,
       v.inchip_y,
       v.radius_x,
       v.radius_y,
       v.unit,
       r.observed_at,
       r.recipe_id,
       r.eqp_id
FROM void_obs v
JOIN inspection_run r ON r.run_uid = v.run_uid"""

CHECKS = {
    "void_obs rows": "SELECT count(*) FROM void_obs",
    "view rows": f"SELECT count(*) FROM {VIEW}",
    "view rows with NULL observed_at": f"SELECT count(*) FROM {VIEW} WHERE observed_at IS NULL",
    "SYN-CX-BW-001 rows in view":
        f"SELECT count(*) FROM {VIEW} WHERE base_wafer_id = 'SYN-CX-BW-001'",
}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '300s'"))
        try:
            c.execute(text(CREATE_SQL))
            results = {name: c.execute(text(sql)).scalar()
                       for name, sql in CHECKS.items()}
            for name, value in results.items():
                print("   %-34s %8d" % (name, value))

            same = results["void_obs rows"] == results["view rows"]
            print("\n   row count preserved: %s" % ("YES" if same else "NO - REFUSING"))
            if not same or results["view rows with NULL observed_at"]:
                c.rollback()
                print("REFUSED: the view would not be a faithful projection.")
                return 1

            if args.apply and args.allow_owner:
                c.commit()
                print("\nCOMMITTED.  Rollback:  DROP VIEW %s;" % VIEW)
            else:
                c.rollback()
                print("\nDRY RUN - rolled back.")
        except Exception:
            c.rollback()
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
