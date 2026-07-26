"""Production-integrity manifest.

Captures a fingerprint of the LIVE environment so that "the agent did not write to
production" can be proven by comparison instead of asserted.

Two halves:
  * DB    - per-table row count + max(updated_at) + max(created_at) for the tables
            an agent is likely to touch. Read-only (SELECT only).
  * FILES - sha256 + mtime + size for every file under server/config/** and
            server/ingestion_workspace/**. mtime is recorded on purpose: it
            separates "rewritten with identical bytes" from "never opened".

Usage:
    python server/scripts/dev_env/manifest.py capture <out.json> [--db-url URL]
    python server/scripts/dev_env/manifest.py diff <before.json> <after.json>
"""
import os
import sys
import json
import hashlib
import argparse
from datetime import datetime, date
from decimal import Decimal

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# Directories whose contents are rewritten by the LIVE pipeline itself (scheduler
# drops CSVs, watcher archives them). They are still captured, but reported in a
# separate bucket because churn there is not evidence of agent activity.
CHURN_DIR_NAMES = {"raws", "archives", "err"}


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    return str(o)


def capture_files(root, label):
    """sha256 + mtime + size for every file under `root`."""
    out = {}
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace("\\", "/")
            try:
                st = os.stat(full)
                h = hashlib.sha256()
                with open(full, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(chunk)
                out[f"{label}/{rel}"] = {
                    "sha256": h.hexdigest(),
                    "mtime": st.st_mtime,
                    "size": st.st_size,
                    "churn": any(p in CHURN_DIR_NAMES for p in rel.split("/")),
                }
            except OSError as e:
                out[f"{label}/{rel}"] = {"error": str(e)}
    return out


def capture_db(db_url):
    from sqlalchemy import create_engine, text
    engine = create_engine(db_url)
    result = {}
    with engine.connect() as conn:
        tables = [r[0] for r in conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' ORDER BY table_name"
        ))]
        for t in tables:
            cols = {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t"
            ), {"t": t})}
            sel = ["COUNT(*) AS n"]
            if "updated_at" in cols:
                sel.append("MAX(updated_at) AS max_updated")
            if "created_at" in cols:
                sel.append("MAX(created_at) AS max_created")
            row = conn.execute(text(f'SELECT {", ".join(sel)} FROM "{t}"')).mappings().first()
            result[t] = {k: row[k] for k in row.keys()}
    engine.dispose()
    return result


def cmd_capture(args):
    db_url = args.db_url or os.getenv("DATABASE_URL") or \
        "postgresql://postgres:admin@localhost:5432/assy_manager"
    snap = {
        "captured_at": datetime.now().isoformat(),
        "db_url": db_url,
        "db": capture_db(db_url) if not args.no_db else {},
        "files": {},
    }
    if not args.no_files:
        snap["files"].update(capture_files(os.path.join(SERVER_DIR, "config"), "config"))
        snap["files"].update(capture_files(os.path.join(SERVER_DIR, "ingestion_workspace"), "workspace"))
        snap["files"].update(capture_files(os.path.join(SERVER_DIR, "mappers"), "mappers"))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=1, default=_json_default)
    n_churn = sum(1 for v in snap["files"].values() if v.get("churn"))
    print(f"captured -> {args.out}")
    print(f"  db tables: {len(snap['db'])}")
    print(f"  files:     {len(snap['files'])} ({n_churn} in raws/archives/err churn dirs)")
    return 0


def cmd_diff(args):
    with open(args.before, encoding="utf-8") as f:
        b = json.load(f)
    with open(args.after, encoding="utf-8") as f:
        a = json.load(f)

    print(f"BEFORE {b['captured_at']}   AFTER {a['captured_at']}")
    print(f"db_url {b['db_url']}")

    print("\n== DB ==")
    db_changed = []
    for t in sorted(set(b["db"]) | set(a["db"])):
        bv, av = b["db"].get(t), a["db"].get(t)
        if bv != av:
            db_changed.append((t, bv, av))
    if not db_changed:
        print("  IDENTICAL (no row-count / max-timestamp change on any table)")
    for t, bv, av in db_changed:
        bn = (bv or {}).get("n"), (av or {}).get("n")
        print(f"  {t}: n {bn[0]} -> {bn[1]}   "
              f"max_updated {(bv or {}).get('max_updated')} -> {(av or {}).get('max_updated')}")

    print("\n== FILES ==")
    buckets = {"stable": [], "churn": []}
    for k in sorted(set(b["files"]) | set(a["files"])):
        bv, av = b["files"].get(k), a["files"].get(k)
        if bv == av:
            continue
        churn = (bv or av or {}).get("churn")
        if bv is None:
            what = "ADDED"
        elif av is None:
            what = "REMOVED"
        elif bv.get("sha256") != av.get("sha256"):
            what = "CONTENT-CHANGED"
        else:
            what = "TOUCHED (same bytes, mtime moved)"
        buckets["churn" if churn else "stable"].append((k, what, bv, av))

    print(f"  stable files changed: {len(buckets['stable'])}"
          f"   |  churn-dir files changed: {len(buckets['churn'])}")
    for k, what, bv, av in buckets["stable"]:
        print(f"  [STABLE] {what}: {k}")
        if what.startswith("TOUCHED"):
            print(f"           mtime {bv['mtime']} -> {av['mtime']}")
    if args.verbose:
        for k, what, bv, av in buckets["churn"]:
            print(f"  [churn ] {what}: {k}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("capture")
    c.add_argument("out")
    c.add_argument("--db-url")
    c.add_argument("--no-db", action="store_true")
    c.add_argument("--no-files", action="store_true")
    c.set_defaults(func=cmd_capture)

    d = sub.add_parser("diff")
    d.add_argument("before")
    d.add_argument("after")
    d.add_argument("-v", "--verbose", action="store_true")
    d.set_defaults(func=cmd_diff)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
