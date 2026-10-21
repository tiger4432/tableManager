"""Let already-ingested files be read again — without touching the files.

WHY THIS EXISTS
---------------
An EXTERNAL source is read-only by design: the watcher never moves or renames what it finds there, and neither
should you. Whether a file is read again is the checklist's answer (소유자 10-21): a file log row of the same
(path, table) carrying the file's (mtime, size) checks it. This lets those keys go - `reread.uncheck`, the same one a
table's changed reading calls - so the next sweep reads the files again. The files are not read, moved, renamed or
hashed; only the rows' stamps are emptied (their history stays).

    python scripts/replay_ingestion.py --path "D:/feeds/WF-001/JOB1_20260818_140000/voids.json"
    python scripts/replay_ingestion.py --path "..." --path "..." --table void_obs --apply
    python scripts/replay_ingestion.py --path "..." --now [--table <table>] [--apply]

`--now` reads the file now as the watcher would have - even one no row names and one the source's pattern did not
take (총괄 aaf19d0ca): the screen's «Read now», the same function (`reread.read_now`).

Dry run by default: it prints the rows that check the files and changes nothing. Re-ingestion UPDATES rows that
carry the same business key rather than duplicating them, so a replay of unchanged content lands the same values
again. One file from the screen is the file screen's Retry.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
for path in (SERVER, os.path.join(SERVER, "parsers")):
    if path not in sys.path:
        sys.path.insert(0, path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", required=True, action="append", help="a file to let through again (repeatable)")
    parser.add_argument("--table", help="narrow to one table (a file may feed two)")
    parser.add_argument("--apply", action="store_true", help="actually let them go; without this nothing changes")
    parser.add_argument("--now", action="store_true", help="hand each file to the watcher to read now")
    args = parser.parse_args(argv)
    if args.now:
        return read_now(args)

    from sqlalchemy import literal

    from database.database import SessionLocal
    from database.models import FileIngestionLog as Log, path_key
    from ingestion import reread

    paths = [os.path.abspath(path) for path in args.path]
    db = SessionLocal()
    try:
        query = db.query(Log).filter(Log.file_mtime.isnot(None),
                                     path_key(Log.filepath).in_([path_key(literal(path)) for path in paths]))
        if args.table:
            query = query.filter(Log.table_name == args.table)
        rows = query.order_by(Log.id).all()
        for path in paths:
            print(f"file      : {path} ({'on the disk' if os.path.exists(path) else 'not on the disk'})")
        if not rows:
            print("No row checks these files - the next sweep already reads them.")
            print("If one still does not come in, the cause is not the checklist (see the source's folder, "
                  "options.filename and enabled).")
            return 0
        print(f"=== rows that check them: {len(rows)} ===")
        for row in rows:
            print(f"  table {row.table_name:20s} status={row.status:14s} read {row.updated_at or row.created_at}  "
                  f"{row.filepath}")
        if not args.apply:
            print("(dry run - add --apply to let them go)")
            return 0
        unchecked = reread.uncheck(db, table=args.table, paths=paths)
        print(f"Unchecked {unchecked} row(s). The next sweep (external sources: within 300 s) reads these files again; "
              f"a row the retry door holds is left to it.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def read_now(args) -> int:
    from database.database import SessionLocal
    from ingestion import reread

    db = SessionLocal()
    try:
        for path in args.path:
            try:
                said = reread.read_now(db, path, table=args.table, apply=args.apply)
            except reread.RereadRefused as refused:
                print(f"refused   : {refused}")
                continue
            for owner in said["owners"]:
                why = "; ".join(owner["why_not"]) or "the watcher takes it"
                print(f"owner     : {owner['table']} ({owner['source']}) - {why}")
            print(f"file      : {said['path']} -> "
                  + (f"handed to the watcher for {said['owner']['table']} (log #{said['log_id']})" if args.apply
                     else f"{len(said['owners'])} tables read it - add --table" if said["owner"] is None
                     else f"{said['owner']['table']} would read it (dry run - add --apply)"))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
