"""One snapshot of a running installation, restored by the restore.bat it carries - no installer, no Docker
(owner 11-05 «ㄱ»): the code at its commit, the conda environment (conda-pack), PostgreSQL's binaries of the server's
version, the database less what can be rebuilt (pg_dump -Fc), the live declarations, the workspace's scripts, and a
manifest of what, when, how large, and what was left out and why.

    python server/scripts/snapshot.py --out <new dir> [--no-secrets] [--env assy_manager] [--pg-bin <dir>]

Left out (each said in the manifest):
  the ledger space - each world's ledger, cursor and row_ref (`ledger.schema.world_names`), their partitions, its atom
      view, a world's own schema: translated again from the tables after a restore (`rebuild` in the manifest)
  <ledger>_pre_rebuild*  a copy an earlier rebuild left - no declaration reads it
  raws · archives · err  listed (path, bytes, mtime), not copied (`dev_env.devenv.SKIP_CONTENT_DIRS`)
Secrets: kept by default; --no-secrets empties database.json's url and llm_config.json's api_key and names them. The
sign-in client secret lives in the environment (`admin.sso.CLIENT_SECRET_ENV`), never in a file - not carried.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
sys.path.insert(0, os.path.join(SERVER_DIR, "scripts", "dev_env"))

import paths  # noqa: E402
from devenv import SKIP_CONTENT_DIRS, _copy_tree  # noqa: E402

RESTORE_FILES = ("restore.py", "restore.bat")
SECRETS = {"database.json": ("url",), "llm_config.json": ("api_key",)}


def _run(args, **kw):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode:
        raise SystemExit("%s failed (%d): %s" % (os.path.basename(str(args[0])), r.returncode, (r.stderr or r.stdout)[-800:]))
    return r.stdout


def _timed(steps, name, work):
    started = time.monotonic()
    out = work()
    steps[name] = round(time.monotonic() - started, 1)
    print("[snapshot] %-12s %6.1f s" % (name, steps[name]), flush=True)
    return out


def left_out(names_of=None):
    """(pg_dump --exclude-table patterns, --exclude-schema names, why) - the ledger space of every world."""
    from ledger import schema

    names_of = names_of or schema.world_names
    tables, schemas = [], []
    for world in [None] + list(schema.worlds()):
        names = names_of(world)
        if names.schema:
            schemas.append(names.schema)
            continue
        for name in (names.ledger, names.cursor, names.row_ref):
            tables += [name, name + "_*"]
        tables.append(schema.atom_rows_view_name(names))
        tables += [names.ledger + "_pre_rebuild", names.ledger + "_pre_rebuild_*"]
    return tables, schemas


def _ledger_sources():
    """The ledger's declared source ids - each one translated again after a restore."""
    from error_said import told
    from ledger.setup import load_setup

    try:
        return list(load_setup().source_ids)
    except Exception as exc:                                            # noqa: BLE001 - said in the list instead
        return ["<the ledger declaration did not load: %s - list its sources by GET /api/ledger/declaration>"
                % told(exc)]


def _pg(url):
    from sqlalchemy.engine import make_url

    url = make_url(url)
    env = dict(os.environ, PGHOST=url.host or "localhost", PGPORT=str(url.port or 5432), PGUSER=url.username or "",
               PGPASSWORD=url.password or "", PGDATABASE=url.database)
    return url, env


def _facts(url):
    """What a restore compares itself with: the server's version and locale, tables, layers and a person's layers."""
    from sqlalchemy import create_engine, text

    from database import crud

    engine = create_engine(url)
    try:
        with engine.connect() as c:
            c.execute(text("SET statement_timeout = 0"))
            version, = c.execute(text("SHOW server_version_num")).first()
            encoding, collate, ctype = c.execute(text(
                "SELECT pg_encoding_to_char(encoding), datcollate, datctype FROM pg_database "
                "WHERE datname = current_database()")).first()
            layers, people = c.execute(text(
                "SELECT count(*), count(*) FILTER (WHERE split_part(source_name, ' (', 1) = :user) FROM cell_sources"),
                {"user": crud.USER_SOURCE}).first()
            return {"server_version_num": int(version), "encoding": encoding, "collate": collate, "ctype": ctype,
                    "cell_sources": layers, "person_layers": people}
    finally:
        engine.dispose()


def _secrets_out(config_dir):
    emptied = []
    for name, cells in SECRETS.items():
        path = os.path.join(config_dir, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            held = json.load(f)
        for cell in cells:
            if held.get(cell):
                held[cell] = ""
                emptied.append("%s:%s" % (name, cell))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(held, f, ensure_ascii=False, indent=2)
    return emptied


def _listed(root):
    """Every file under `root`'s raws · archives · err, listed - not copied."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root).replace("\\", "/")
        if not set(rel.split("/")) & SKIP_CONTENT_DIRS:
            continue
        for name in filenames:
            st = os.stat(os.path.join(dirpath, name))
            out.append({"path": rel + "/" + name, "bytes": st.st_size,
                        "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()})
    return out


def _zip_dir(src, dst, parts):
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for part in parts:
            for dirpath, _dirs, filenames in os.walk(os.path.join(src, part)):
                for name in filenames:
                    full = os.path.join(dirpath, name)
                    z.write(full, os.path.relpath(full, src))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="a new directory")
    ap.add_argument("--no-secrets", action="store_true")
    ap.add_argument("--env", default="assy_manager", help="the conda environment to pack")
    ap.add_argument("--pg-bin", default=None, help="PostgreSQL's bin directory (default: the server's major version "
                                                     "under C:/Program Files/PostgreSQL)")
    args = ap.parse_args(argv)
    if os.path.exists(args.out):
        raise SystemExit("%s exists - a snapshot goes into a new directory" % args.out)
    os.makedirs(args.out)
    out, steps = os.path.abspath(args.out), {}
    url = paths.resolve_database_url(paths.DEFAULT_PG_URL)[0]
    facts = _timed(steps, "facts", lambda: _facts(url))
    major = facts["server_version_num"] // 10000
    pg_bin = args.pg_bin or r"C:\Program Files\PostgreSQL\%d\bin" % major
    client = _run([os.path.join(pg_bin, "pg_dump"), "--version"])
    if " %d." % major not in client:
        raise SystemExit("pg_dump in %s is %s - the server is %d" % (pg_bin, client.strip(), major))

    sha = _run(["git", "-C", paths.REPO_ROOT, "rev-parse", "HEAD"]).strip()
    dirty = bool(_run(["git", "-C", paths.REPO_ROOT, "status", "--porcelain", "--untracked-files=no"]).strip())
    _timed(steps, "code", lambda: _run(["git", "-C", paths.REPO_ROOT, "archive", "--format=zip",
                                        "-o", os.path.join(out, "code.zip"), "HEAD"]))
    conda = os.environ.get("CONDA_EXE") or shutil.which("conda") or "conda"
    _timed(steps, "env", lambda: _run([conda, "run", "-n", "base", "conda-pack", "-n", args.env,
                                       "-o", os.path.join(out, "env.tar.gz"), "--ignore-missing-files",
                                       "--ignore-editable-packages", "--exclude", "*.pyc"]))  # the repo itself: code.zip carries it
    _timed(steps, "pg binaries", lambda: _zip_dir(os.path.dirname(pg_bin), os.path.join(out, "pg.zip"),
                                                    ("bin", "lib", "share")))
    tables, schemas = left_out()
    _, pg_env = _pg(url)
    dump = [os.path.join(pg_bin, "pg_dump"), "-Fc", "-Z", "6", "-f", os.path.join(out, "db.dump")]
    dump += [arg for t in tables for arg in ("--exclude-table", t)]
    dump += [arg for s in schemas for arg in ("--exclude-schema", s)]
    _timed(steps, "db dump", lambda: _run(dump, env=pg_env))

    data = os.path.join(out, "data")
    _timed(steps, "files", lambda: (
        _copy_tree(paths.CONFIG_DIR, os.path.join(data, "config")),
        _copy_tree(paths.WORKSPACE_DIR, os.path.join(data, "ingestion_workspace"), SKIP_CONTENT_DIRS)))
    mappers = next((d for d in (os.path.join(paths.DATA_ROOT, "mappers"), os.path.join(paths.SERVER_DIR, "mappers"))
                    if os.path.isdir(d)), None)
    if mappers:
        _copy_tree(mappers, os.path.join(out, "mappers"))
    emptied = _secrets_out(os.path.join(data, "config")) if args.no_secrets else []
    for name in RESTORE_FILES:
        shutil.copy2(os.path.join(SERVER_DIR, "scripts", name), os.path.join(out, name))

    sizes = {name: os.path.getsize(os.path.join(out, name)) for name in ("code.zip", "env.tar.gz", "pg.zip", "db.dump")}
    manifest = {
        "made": datetime.now(timezone.utc).isoformat(), "commit": sha, "dirty": dirty, "env": args.env,
        "database": facts, "seconds": steps, "bytes": sizes,
        "left_out": {"tables": tables, "schemas": schemas,
                     "why": "the ledger space is translated again from the tables; <ledger>_pre_rebuild* is a copy an "
                            "earlier rebuild left that no declaration reads"},
        "not_copied": {"dirs": sorted(SKIP_CONTENT_DIRS), "files": _listed(paths.WORKSPACE_DIR)},
        "secrets": {"kept": not args.no_secrets, "emptied": emptied,
                    "not_carried": ["environment ASSY_OIDC_CLIENT_SECRET (sign-in)"]},
        "mappers_from": mappers,
        "rebuild": ["the ledger worker makes the ledger's tables and view at its start (ledger.schema.ensure_schema) - "
                    "empty; it follows new changes only"] + [
            "Admin > Retroactive > «Translate the rows not yet in the ledger» source=%s  "
            "(or in server/: python -m ledger.backfill --source %s --apply)" % (source, source)
            for source in _ledger_sources()],
    }
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("[snapshot] %s - %.2f GB in all" % (out, sum(sizes.values()) / 1e9), flush=True)
    return manifest


if __name__ == "__main__":
    main()
