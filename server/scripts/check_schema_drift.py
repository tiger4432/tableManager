"""Report every place the code expects a schema the database does not have.

WHY THIS EXISTS
    Adding a column to a mapped model is a schema change, and `create_all` will not
    apply it to a table that already exists. On a database where the migration has
    not run, SQLAlchemy still names that column in every SELECT and every INSERT it
    generates for the table - so the table goes down entirely, including code paths
    that predate the column and never read it. That failure is invisible on any box
    where the migration HAS run, which is every box we develop and test on. The only
    place it shows up is production, on a screen, in front of an operator.

    Two outages on 2026-08-05 had exactly this shape. Nothing could have reported
    them beforehand. This can.

WHAT IT DOES
    Walks every table SQLAlchemy has mapped - system tables and the dynamic tables
    built from table_config.json alike, since both live in `Base.metadata` - and
    compares declared tables and columns against the database catalog. For each
    drift it prints what breaks and what to do about it.

WHAT IT DOES NOT DO
    It never writes. No DDL, no DML, no transaction that could leave anything
    changed: the only statements issued are catalog reads. Remedies are PRINTED for
    a human to run, deliberately - the whole point is a check that is safe to run
    against production at any moment, including while something is already broken.

    It compares NAMES, not types. A column that exists with the wrong type is real
    drift and this will call it healthy. Name drift is what takes a table down.

USAGE
    conda run -n assy_manager python server/scripts/check_schema_drift.py
    conda run -n assy_manager python server/scripts/check_schema_drift.py --url <sqlalchemy-url>

    Exit code 0 when the database carries everything the code expects, 1 when it
    does not, 2 when the check could not run. Suitable for a deploy gate: run it
    after migrating and before letting traffic in.
"""
import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sqlalchemy import create_engine, inspect, text  # noqa: E402


# Where a column that is missing from an existing table gets added. A column absent
# from this map is not necessarily unmigrated - it means nobody recorded the path,
# which is worth knowing on its own, so the report says exactly that rather than
# guessing.
MIGRATION_OWNER = {
    ("cell_sources", "confirmation_uid"): "server/migrations/add_frame_confirmation.py",
    ("database_outbox", "processed_chain"): "applied at web-server boot (main.py startup_event)",
    ("database_outbox", "broadcast_at"): "applied at web-server boot (main.py startup_event)",
    ("interaction_effort_logs", "nav_preserved_count"): "server/scripts/setup_db_performance.py",
}

SEVERITY_ORDER = {"TABLE-DOWN": 0, "MISSING-TABLE": 1, "INFO": 2}


def _declared():
    """Every table the running code has mapped, with its declared column names."""
    os.environ.setdefault("TESTING", "True")   # keeps import side effects off the wire
    from database.database import Base
    import database.models  # noqa: F401  (registers the mappings onto Base)
    return {name: {c.name: c for c in table.columns}
            for name, table in Base.metadata.tables.items()}


def _actual(engine):
    """Catalog state. `inspect` reads information_schema on PostgreSQL and the
    equivalent pragma on SQLite, so one code path covers production and a simulated
    database built for testing."""
    insp = inspect(engine)
    return {t: {c["name"] for c in insp.get_columns(t)} for t in insp.get_table_names()}


def _add_column_ddl(table, col, dialect):
    """The statement a human should run. Printed, never executed."""
    try:
        type_sql = col.type.compile(dialect)
    except Exception:
        type_sql = "<declare the type by hand - it did not compile for this dialect>"
    stmt = f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{col.name}" {type_sql}'
    if not col.nullable:
        return (stmt + " /* declared NOT NULL - a table with rows in it needs a "
                       "DEFAULT or a backfill, so do not paste this unedited */")
    return stmt


def check(engine):
    declared, actual = _declared(), _actual(engine)
    dialect = engine.dialect
    findings = []

    for table, columns in sorted(declared.items()):
        if table not in actual:
            findings.append({
                "severity": "MISSING-TABLE", "table": table, "column": None,
                "breaks": "every query against this table fails",
                "remedy": ("boot the web server once - Base.metadata.create_all builds a "
                           "missing table whole. If it stays missing after a boot, the "
                           "mapping is registered somewhere create_all does not reach."),
            })
            continue

        missing = [c for name, c in columns.items() if name not in actual[table]]
        for col in missing:
            owner = MIGRATION_OWNER.get((table, col.name))
            findings.append({
                "severity": "TABLE-DOWN", "table": table, "column": col.name,
                "breaks": (f"EVERY full-entity SELECT and EVERY ORM INSERT on {table} "
                           f"fails, not only code that reads {col.name}"),
                "remedy": (f"run {owner}" if owner else
                           "no migration is recorded for this column - add one, then "
                           "record it in MIGRATION_OWNER in this script")
                          + "\n        or: " + _add_column_ddl(table, col, dialect),
            })

        extra = sorted(actual[table] - set(columns))
        if extra:
            findings.append({
                "severity": "INFO", "table": table, "column": ", ".join(extra),
                "breaks": "nothing - the database carries columns the code does not map",
                "remedy": "harmless. Worth a look if one of these was meant to be dropped.",
            })

    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["table"], f["column"] or ""))
    return findings


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", help="SQLAlchemy URL. Defaults to the app's configured database.")
    ap.add_argument("--quiet", action="store_true", help="print findings only")
    args = ap.parse_args()

    if args.url:
        engine = create_engine(args.url)
        where = args.url
    else:
        from database.database import engine, SQLALCHEMY_DATABASE_URL, DB_URL_SOURCE
        where = f"{SQLALCHEMY_DATABASE_URL} (from {DB_URL_SOURCE})"

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
        print(f"  [{f['severity']}] {target}")
        print(f"      breaks: {f['breaks']}")
        print(f"      do:     {f['remedy']}")
        print()

    print(f"[drift] {len(blocking)} blocking, {len(findings) - len(blocking)} informational.")
    if blocking:
        print("[drift] a TABLE-DOWN finding means that table is unusable right now, for "
              "every screen that touches it, until the column exists.")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
