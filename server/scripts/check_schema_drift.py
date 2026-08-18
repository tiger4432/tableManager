"""Command line over `server/schema_drift.py`. Read-only; safe against production.

USAGE
    conda run -n assy_manager python server/scripts/check_schema_drift.py
    conda run -n assy_manager python server/scripts/check_schema_drift.py --url <sqlalchemy-url>

    Exit code 0 when the database carries everything the code expects, 1 when it
    does not, 2 when the check could not run. Suitable for a deploy gate: run it
    after migrating and before letting traffic in.

    The same check now runs by itself at launcher pre-flight and at web-server
    startup, so this is the deliberate, detailed form - not the only line of
    defence it used to be.
"""
import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sqlalchemy import create_engine, text  # noqa: E402

# Re-exported so anything already importing them from this script keeps working.
from schema_drift import (  # noqa: E402,F401
    MIGRATION_OWNER, SEVERITY_ORDER, TYPE_KINDS, banner_lines, check,
    finding_label, run_at_startup,
)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", help="SQLAlchemy URL. Defaults to the app's configured database.")
    ap.add_argument("--quiet", action="store_true", help="print findings only")
    args = ap.parse_args()

    # Masked, both branches. The URL carries the database password and this line
    # gets pasted into tickets. `paths.mask_db_password` is the app's own helper,
    # already used for the web server's boot line.
    import paths
    if args.url:
        engine = create_engine(args.url)
        where = paths.mask_db_password(args.url)
    else:
        from database.database import engine, SQLALCHEMY_DATABASE_URL, DB_URL_SOURCE
        where = (f"{paths.mask_db_password(SQLALCHEMY_DATABASE_URL)} "
                 f"(from {DB_URL_SOURCE})")

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        print(f"[drift] cannot reach the database: {e}")
        return 2

    if not args.quiet:
        print(f"[drift] target: {where}")
        print("[drift] read-only: catalog reads only, no statement here changes anything.")
        print()

    findings = check(engine)
    if not findings:
        print("[drift] none. The database carries every table and column the code maps.")
        return 0

    blocking = [f for f in findings if f["severity"] != "INFO"]
    for f in findings:
        target = f"{f['table']}.{f['column']}" if f["column"] else f["table"]
        print(f"  [{finding_label(f)}] {target}")
        print(f"      breaks: {f['breaks']}")
        print(f"      do:     {f['remedy']}")
        print()

    print(f"[drift] {len(blocking)} blocking, {len(findings) - len(blocking)} informational.")
    # Type findings are INFO and deliberately do NOT move the exit code - the
    # remedy is a human decision (see schema_drift._sync_repairs) and a gate that
    # went red on one would stay red until somebody made it. But a breaking one
    # means that table answers nothing right now, so it gets its own line rather
    # than being one of N informational.
    breaking_types = [f for f in findings if f.get("kind") == "type-breaking"]
    if breaking_types:
        print(f"[drift] {len(breaking_types)} of the informational findings are "
              f"BREAKING type mismatches: numeric is declared over a column that is "
              f"not numeric, so EVERY query of "
              f"{', '.join(sorted({f['table'] for f in breaking_types}))} raises "
              f"'Unknown PG numeric type'. Not counted as blocking on purpose - no "
              f"automatic repair exists - but nothing on those tables works.")
    if any(f["severity"] == "TABLE-DOWN" for f in findings):
        print("[drift] a TABLE-DOWN finding means that table is unusable right now, for "
              "every screen that touches it, until the column exists.")
    healing = [f for f in findings if f["severity"] == "SELF-HEALING"]
    if healing:
        # Counted as blocking, deliberately, and this is the reasoning so nobody
        # "fixes" the inconsistency with the startup banner by accident.
        #
        # The banner answers "what must the operator do", and for these the answer
        # is nothing - so it does not raise the red block. This exit code answers a
        # different question: "does the database match the code RIGHT NOW". For a
        # self-healing column that answer is genuinely no, and this exit code feeds
        # deploy gates. Narrowing a gate is not something a banner-wording round
        # gets to do as a side effect, so the code stays 1 and the text explains it.
        print(f"[drift] {len(healing)} of those are SELF-HEALING: a boot adds them and "
              f"no migration exists to run. Exit 1 still, because the database does "
              f"not match the code yet - re-run this after the stack is up.")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
