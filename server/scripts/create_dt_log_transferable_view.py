r"""Create `dt_log_transferable` -- the dt_log rows that can actually name a core die.

WHY A VIEW AND NOT A DECLARATION CLAUSE
---------------------------------------
The transfer binding takes the core die's identity from `core_wafer`, and 6,731 of dt_log's
34,939 rows have none. The order was that those rows must produce NO edge and must not be
filled by a guess. But a declaration cannot say "only rows with core_wafer": `read` accepts
unit, identity, group_by, order_by and occurred_at, and nothing else.

MEASURED 2026-08-24, and it is a third outcome nobody had written down: the translator does
not count those rows as refused and does not skip them -- `source_preparation` RAISES on the
missing identity and the batch ends. Zero atoms landed. The refusal itself is correct; it is
the machinery declining to invent an identity. What was missing was a place to filter.

ONE CONDITION, NOT TWO
----------------------
`core_wafer IS NOT NULL` yields exactly 28,208. The other exclusion the order named -- 522
rows with no `event_time`, which are exactly the `product = 'SYNTHETIC'` rows -- is a SUBSET
of those 6,731 (all 522 also lack core_wafer). Writing both conditions would count the
overlap twice and imply two independent gaps where there is one.

⚠️ WHAT THIS COSTS: the 6,731 excluded rows are not visible downstream at all -- the view
removes them, so "nothing was translated from them" stops being observable in the ledger and
lives only here and in the report. That is why the number is printed on every run.

USAGE -- dry run by default; the gate runs before the commit either way:

    python scripts/create_dt_log_transferable_view.py
    python scripts/create_dt_log_transferable_view.py --apply --i-accept-writing-to-owner-database

ROLLBACK:

    DROP VIEW dt_log_transferable;
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

VIEW = "dt_log_transferable"
EXPECTED = 28208

#: `SELECT *` on purpose: the binding reads dt_job/dt_x/dt_y/core_wafer/core_x/core_y and the
#: driver reads row_id and event_time, and naming a subset here would mean editing DDL every
#: time the declaration reaches for one more column it already has.
CREATE_SQL = f"""
CREATE OR REPLACE VIEW {VIEW} AS
SELECT * FROM dt_log WHERE NULLIF(core_wafer::text, '') IS NOT NULL"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)

    with db.engine.connect() as c:
        c.execute(text("SET statement_timeout = '300s'"))
        try:
            source_rows = c.execute(text("SELECT count(*) FROM dt_log")).scalar()
            c.execute(text(CREATE_SQL))
            kept = c.execute(text(f"SELECT count(*) FROM {VIEW}")).scalar()
            excluded = source_rows - kept
            no_time = c.execute(text(
                f"SELECT count(*) FROM {VIEW} WHERE event_time IS NULL")).scalar()

            print("   dt_log rows                  %8d" % source_rows)
            print("   view keeps                   %8d   %s"
                  % (kept, "OK" if kept == EXPECTED else "<- expected %d" % EXPECTED))
            print("   view EXCLUDES (recorded)     %8d   (no core_wafer -- makes no edge)"
                  % excluded)
            print("   of the kept, missing time    %8d   %s"
                  % (no_time, "OK - the 522 were inside the excluded set"
                     if no_time == 0 else "<- a second gap exists after all"))

            ok = kept == EXPECTED and no_time == 0
            print("\n   GATE: %s" % ("PASS" if ok else "FAIL"))
            if ok and args.apply and args.allow_owner:
                c.commit()
                print("COMMITTED.  Rollback: DROP VIEW %s;" % VIEW)
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
