"""Restore a snapshot made by snapshot.py into an empty directory - run by the restore.bat beside it, with the
snapshot's own conda environment, after the environment is unpacked (owner 11-05 «ㄱ»).

    restore.bat <into dir> [pg port, default 5432] [api port, default 8080] [--no-start]

  code.zip -> <into>/code · pg.zip -> <into>/pg · initdb <into>/pgdata (the source's encoding and locale) · PostgreSQL
  on the pg port · db.dump -> pg_restore -j · data -> <into>/data (ASSY_DATA_ROOT) · mappers -> code/server/mappers ·
  data/config/database.json -> this PostgreSQL · the manifest's «rebuild» printed · the app started on the api port.
Writes nothing outside <into>. Only the standard library: the product is not importable until it is unpacked.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

DB = "assy_manager"


def _run(args, **kw):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode:
        raise SystemExit("%s failed (%d): %s" % (os.path.basename(str(args[0])), r.returncode,
                                                 (r.stderr or r.stdout)[-800:]))
    return r.stdout


def _step(name, work):
    started = time.monotonic()
    out = work()
    print("[restore] %-14s %6.1f s" % (name, time.monotonic() - started), flush=True)
    return out


def _copy(src, dst):
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)


def counts(psql, port):
    """(tables, cell_sources rows, a person's layers) of the restored database - what the manifest compares with."""
    q = ("SELECT (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
         "WHERE c.relkind IN ('r','p') AND n.nspname = 'public'), count(*), "
         "count(*) FILTER (WHERE split_part(source_name, ' (', 1) = 'user') FROM cell_sources")
    out = _run([psql, "-h", "localhost", "-p", str(port), "-U", "postgres", "-d", DB, "-At", "-c", q])
    return [int(x) for x in out.strip().split("|")]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--into", required=True)
    ap.add_argument("--pg-port", type=int, default=5432)
    ap.add_argument("--api-port", type=int, default=8080)
    ap.add_argument("--jobs", type=int, default=max(2, (os.cpu_count() or 4) // 2))
    ap.add_argument("--no-start", action="store_true", help="restore only - start nothing")
    args = ap.parse_args(argv)
    snap, into = os.path.abspath(args.snapshot), os.path.abspath(args.into)
    with open(os.path.join(snap, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    db = manifest["database"]
    pg = os.path.join(into, "pg")
    binary = lambda name: os.path.join(pg, "bin", name)                                   # noqa: E731

    _step("code", lambda: zipfile.ZipFile(os.path.join(snap, "code.zip")).extractall(os.path.join(into, "code")))
    _step("pg binaries", lambda: zipfile.ZipFile(os.path.join(snap, "pg.zip")).extractall(pg))
    pgdata = os.path.join(into, "pgdata")
    _step("initdb", lambda: _run([binary("initdb"), "-D", pgdata, "-U", "postgres", "-A", "trust",
                                  "-E", db["encoding"], "--lc-collate", db["collate"], "--lc-ctype", db["ctype"]]))
    # not _run: the postgres pg_ctl leaves running inherits a captured pipe and holds it open - the run never returns
    _step("pg start", lambda: subprocess.run([binary("pg_ctl"), "-D", pgdata, "-o", "-p %d" % args.pg_port,
                                              "-l", os.path.join(into, "pg.log"), "-w", "start"],
                                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL, check=True))
    conn = ["-h", "localhost", "-p", str(args.pg_port), "-U", "postgres"]
    _step("createdb", lambda: _run([binary("createdb")] + conn + ["-T", "template0", DB]))
    restored = subprocess.run([binary("pg_restore")] + conn + ["-d", DB, "-j", str(args.jobs), "--no-owner",
                                                               os.path.join(snap, "db.dump")],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("[restore] pg_restore exit %d%s" % (restored.returncode, (" - " + restored.stderr.strip()[-600:])
                                               if restored.returncode else ""), flush=True)

    data = os.path.join(into, "data")
    _step("files", lambda: (_copy(os.path.join(snap, "data"), data),
                            _copy(os.path.join(snap, "mappers"), os.path.join(into, "code", "server", "mappers"))))
    with open(os.path.join(data, "config", "database.json"), "w", encoding="utf-8") as f:
        json.dump({"url": "postgresql://postgres@localhost:%d/%s" % (args.pg_port, DB)}, f, indent=2)

    tables, layers, people = counts(binary("psql"), args.pg_port)
    said = {"tables": tables, "cell_sources": layers, "person_layers": people}
    print("[restore] restored %s - the snapshot had cell_sources %s, person_layers %s" % (
        said, db["cell_sources"], db["person_layers"]), flush=True)
    print("[restore] left out: %s" % manifest["left_out"]["why"])
    print("[restore] to rebuild:")
    for line in manifest["rebuild"]:
        print("    " + line)
    if args.no_start:
        return said
    env = dict(os.environ, ASSY_DATA_ROOT=data, ASSY_API_PORT=str(args.api_port),
               API_BASE_URL="http://127.0.0.1:%d" % args.api_port, ASSY_API_BASE="http://127.0.0.1:%d" % args.api_port,
               PYTHONIOENCODING="utf-8")
    env.pop("DATABASE_URL", None)
    code = os.path.join(into, "code")
    app = subprocess.Popen([sys.executable, "run_decoupled_app.py", "--no-client"], cwd=code, env=env,
                           stdout=open(os.path.join(into, "app.log"), "ab"), stderr=subprocess.STDOUT,
                           creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    with open(os.path.join(into, "app.pid"), "w") as f:
        f.write(str(app.pid))
    for _ in range(120):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/health" % args.api_port, timeout=2) as r:
                said["health"] = r.status
                break
        except OSError:                                                 # refused · timed out · URLError: not up yet
            time.sleep(2)
    print("[restore] app pid %d · /health %s" % (app.pid, said.get("health", "not answering after 240 s")))
    return said


if __name__ == "__main__":
    main()
