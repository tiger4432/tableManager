"""The audit panel's indexes on a database that predates them - read, and with --apply built.

`create_all` never adds an index to a table that already exists, so a database older than these declarations
(production included) has `idx_audit_recent_groups` only if someone ran its SQL file - and without it the panel's
first walk sorts the whole of `audit_logs` (`add_audit_recent_groups_index.sql`: 212 s cold), each statement is
cancelled at `recent_statement_seconds` and the walk starts again: «Updating» for a long time (owner 11-11). Its pair
`add_audit_history_keyset_indexes.sql` (a row's and a cell's history pages) is checked and built the same way -
DEPLOY_SETUP runs the two together.

    python migrations/add_audit_recent_groups_index.py            read only: each index present / missing / invalid
    python migrations/add_audit_recent_groups_index.py --apply    builds the missing ones (CREATE INDEX CONCURRENTLY -
                                                                  writes go on meanwhile), drops and builds again an
                                                                  invalid one, then reads them again

An invalid index is a cancelled CONCURRENTLY build: no query uses it, so dropping it costs no read (ops has no SQL
tool to drop it by hand - lead 11-11).

The statements are the SQL files' own: this script reads and runs them, so the two never say different things.
After the cell-source overhaul the panel reads `audit_batches` - this is the bridge until then.
"""
import argparse
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

import db_safety  # noqa: E402
from migrations.add_business_key_unique_index import index_exists  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
#: The SQL files whose statements this runs, in DEPLOY_SETUP's order.
SQL_FILES = ("add_audit_history_keyset_indexes.sql", "add_audit_recent_groups_index.sql")
#: The name `pg_stat_activity` shows for the read pass.
READONLY_APPLICATION_NAME = "assy_audit_index_check"
PRESENT, MISSING, INVALID = "present", "missing", "invalid"
_NAMED = re.compile(r"CREATE\s+INDEX\s+CONCURRENTLY\s+IF\s+NOT\s+EXISTS\s+(\w+)", re.I)


def statements():
    """[(index name, statement)] of the SQL files - comment lines out, one statement per «;»."""
    out = []
    for name in SQL_FILES:
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            body = "\n".join(line for line in f.read().splitlines() if not line.lstrip().startswith("--"))
        for one in (s.strip() for s in body.split(";")):
            if one:
                named = _NAMED.match(one)
                if not named:
                    raise ValueError("%s: a statement this script does not run: %s" % (name, one.splitlines()[0]))
                out.append((named.group(1), one))
    return out


def state(conn, name) -> str:
    exists, valid = index_exists(conn, name)
    return PRESENT if exists and valid else INVALID if exists else MISSING


def say(found, title):
    print("=== %s ===" % title)
    for name, now in found.items():
        print("  %-28s %s" % (name, now))
        if now == INVALID:
            print("    !! %s is INVALID - it serves nothing. --apply drops it and builds it again" % name)


def run(apply: bool, url: str = None) -> dict:
    """{index: state after the run}. On SQLite nothing to do - the declarations make them (`create_all`)."""
    if url is None:
        from database.database import SQLALCHEMY_DATABASE_URL as url
    if not url.startswith("postgresql"):
        print("Not PostgreSQL - nothing to do (a new database gets these indexes from create_all).")
        return {}
    wanted = statements()
    engine = db_safety.open_readonly_engine(url, application_name=READONLY_APPLICATION_NAME)
    try:
        conn = db_safety.open_readonly_connection(engine)
        try:
            found = {name: state(conn, name) for name, _ in wanted}
        finally:
            db_safety.close_readonly_connection(conn)
    finally:
        engine.dispose()
    say(found, "audit panel indexes %s" % ("APPLY" if apply else "CHECK (read-only)"))
    if not apply:
        if any(s != PRESENT for s in found.values()):
            print("Run again with --apply (CREATE INDEX CONCURRENTLY - may take minutes, writes go on).")
        return found
    from sqlalchemy import create_engine

    writer = create_engine(url)
    try:
        with writer.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for name, ddl in wanted:
                if found[name] == INVALID:
                    print("  %s: invalid" % name)
                    print("  %s: dropping ..." % name, flush=True)
                    conn.execute(text('DROP INDEX CONCURRENTLY IF EXISTS "%s"' % name))
                if found[name] != PRESENT:
                    print("  %s: building ..." % name, flush=True)
                    conn.execute(text(ddl))
                found[name] = state(conn, name)
    finally:
        writer.dispose()
    say(found, "after")
    return found


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true", help="build the missing indexes. Without it the run is read-only.")
    found = run(apply=p.parse_args(argv).apply)
    return 1 if INVALID in found.values() else 0


if __name__ == "__main__":
    sys.exit(main())
