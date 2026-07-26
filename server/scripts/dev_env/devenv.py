"""assyManager isolated development environment - one entry point.

    conda run -n assy_manager python server/scripts/dev_env/devenv.py up

Gives you a server on :8081 backed by the `assy_qa` snapshot database and a
private copy of config/ + ingestion_workspace/ under dev_env/. Write to it
freely. It structurally cannot reach production:

    production                     isolated
    ------------------------------ --------------------------------------
    DB   assy_manager              assy_qa                (DATABASE_URL)
    data server/config             dev_env/config         (ASSY_DATA_ROOT)
         server/ingestion_workspace dev_env/ingestion_workspace
    API  127.0.0.1:8080            127.0.0.1:8081         (--port)
    graph 127.0.0.1:8090           127.0.0.1:8091         (GRAPH_SYNC_PORT)

The directory watcher and the auto-update scheduler are NOT started and this
script has no flag to start them - their 2-minute collector cron is exactly the
churn that makes measurements irreproducible. The collector scripts themselves
are copied in, so "the scheduler is off" is a fact about the running processes,
not about a missing file.

Commands:
    bootstrap   copy config/ + ingestion_workspace/ into dev_env/ (skips raws/archives)
    snapshot    build or refresh the assy_qa snapshot database
    up          bootstrap if needed, then start the isolated processes
    down        stop them
    status      what is running, what it points at
    env         print the environment variables (for running one-off scripts)
"""
import os
import sys
import json
import time
import shutil
import signal
import argparse
import subprocess

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
SERVER_DIR = os.path.join(REPO_ROOT, "server")
DEV_ROOT = os.path.join(REPO_ROOT, "dev_env")
PID_FILE = os.path.join(DEV_ROOT, "pids.json")
LOG_DIR = os.path.join(DEV_ROOT, "logs")

API_PORT = int(os.getenv("ASSY_DEV_API_PORT", "8081"))
GRAPH_PORT = int(os.getenv("ASSY_DEV_GRAPH_PORT", "8091"))
QA_DB_URL = os.getenv("ASSY_QA_DATABASE_URL",
                      "postgresql://postgres:admin@localhost:5432/assy_qa")

# Directories copied as empty shells. raws/ and archives/ hold the live
# pipeline's files (9,000+ of them); the isolated env wants the structure, not
# the backlog.
SKIP_CONTENT_DIRS = {"raws", "archives", "err"}


def log(msg):
    print(f"[devenv] {msg}", flush=True)


def isolated_env():
    """The complete set of overrides that redirect a process away from production."""
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": QA_DB_URL,
        "ASSY_DATA_ROOT": DEV_ROOT,
        "DECOUPLED": "True",
        # Worker -> web server callbacks (/internal/events/*).
        "API_BASE_URL": f"http://127.0.0.1:{API_PORT}",
        # auto_update collector scripts default to http://localhost:8080, i.e.
        # PRODUCTION. Anything run with this env hits the isolated server instead.
        "ASSY_API_BASE": f"http://127.0.0.1:{API_PORT}",
        "GRAPH_SYNC_PORT": str(GRAPH_PORT),
        "PYTHONIOENCODING": "utf-8",
    })
    return env


# --------------------------------------------------------------------- bootstrap
def _copy_tree(src, dst, skip_content_dirs=frozenset()):
    copied = shelled = 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        rel = os.path.relpath(dirpath, src)
        target = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target, exist_ok=True)

        parts = set(rel.replace("\\", "/").split("/"))
        if parts & skip_content_dirs:
            shelled += 1
            continue
        for name in filenames:
            shutil.copy2(os.path.join(dirpath, name), os.path.join(target, name))
            copied += 1
    return copied, shelled


def cmd_bootstrap(args):
    if os.path.exists(DEV_ROOT) and not args.force:
        log(f"{DEV_ROOT} already exists - use --force to re-copy from production")
        return 0
    os.makedirs(DEV_ROOT, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    n1, _ = _copy_tree(os.path.join(SERVER_DIR, "config"),
                       os.path.join(DEV_ROOT, "config"))
    log(f"config/            {n1} file(s)")

    n2, shells = _copy_tree(os.path.join(SERVER_DIR, "ingestion_workspace"),
                            os.path.join(DEV_ROOT, "ingestion_workspace"),
                            SKIP_CONTENT_DIRS)
    log(f"ingestion_workspace/ {n2} file(s), {shells} raws/archives/err dir(s) left empty")

    # The scheduler must not resume production's cron state if someone ever
    # starts one against this root by hand.
    status = os.path.join(DEV_ROOT, "config", "scheduler_status.json")
    if os.path.exists(status):
        with open(status, "w", encoding="utf-8") as f:
            json.dump({"last_updated": None, "collectors": []}, f, indent=2)
        log("config/scheduler_status.json reset (no inherited cron state)")

    with open(os.path.join(DEV_ROOT, "README.txt"), "w", encoding="utf-8") as f:
        f.write(
            "assyManager isolated dev environment.\n\n"
            "Generated by server/scripts/dev_env/devenv.py bootstrap.\n"
            "Everything here is a COPY. Editing these files does not affect the\n"
            "user's live server/config or server/ingestion_workspace.\n\n"
            "Re-create with:  devenv.py bootstrap --force\n"
        )
    log(f"bootstrapped {DEV_ROOT}")
    return 0


# ---------------------------------------------------------------------- snapshot
def cmd_snapshot(args):
    if not os.path.isdir(DEV_ROOT):
        cmd_bootstrap(argparse.Namespace(force=False))
    script = os.path.join(SERVER_DIR, "scripts", "dev_env", "snapshot_db.py")
    cmd = [sys.executable, script, "--target", QA_DB_URL]
    if args.full_copy_max_rows:
        cmd += ["--full-copy-max-rows", str(args.full_copy_max_rows)]
    return subprocess.call(cmd, cwd=SERVER_DIR, env=isolated_env())


# ------------------------------------------------------------------- up / down
PROCESSES = [
    ("api", [sys.executable, "-m", "uvicorn", "main:app",
             "--host", "127.0.0.1", "--port", str(API_PORT)]),
    ("chain", [sys.executable, "run_chain_worker.py"]),
    ("graph", [sys.executable, "run_graph_sync.py"]),
    # DELIBERATELY ABSENT: run_watcher.py, run_auto_update.py.
]


def _read_pids():
    if not os.path.exists(PID_FILE):
        return {}
    try:
        with open(PID_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _alive(pid):
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmd_up(args):
    if not os.path.isdir(DEV_ROOT):
        cmd_bootstrap(argparse.Namespace(force=False))
    os.makedirs(LOG_DIR, exist_ok=True)

    running = {n: p for n, p in _read_pids().items() if _alive(p)}
    if running and not args.force:
        log(f"already running: {running}. Use 'down' first, or 'up --force'.")
        return 1

    env = isolated_env()
    pids = {}
    for name, cmd in PROCESSES:
        logfile = os.path.join(LOG_DIR, f"{name}.log")
        f = open(logfile, "ab")
        proc = subprocess.Popen(cmd, cwd=SERVER_DIR, env=env, stdout=f, stderr=f)
        pids[name] = proc.pid
        log(f"started {name:<6} pid={proc.pid}  -> {logfile}")
        if name == "api":
            time.sleep(2.5)

    with open(PID_FILE, "w", encoding="utf-8") as f:
        json.dump(pids, f, indent=2)

    print()
    log(f"API      http://127.0.0.1:{API_PORT}")
    log(f"database {QA_DB_URL}")
    log(f"data     {DEV_ROOT}")
    log("watcher + auto-update scheduler: NOT started (no churn)")
    return 0


def cmd_down(args):
    pids = _read_pids()
    if not pids:
        log("nothing recorded as running")
        return 0
    for name, pid in pids.items():
        if not _alive(pid):
            log(f"{name} (pid {pid}) already gone")
            continue
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
            log(f"stopped {name} (pid {pid})")
        except Exception as e:
            log(f"failed to stop {name} (pid {pid}): {e}")
    os.remove(PID_FILE)
    return 0


def cmd_status(args):
    print(f"dev root   {DEV_ROOT}  {'(exists)' if os.path.isdir(DEV_ROOT) else '(MISSING - run bootstrap)'}")
    print(f"database   {QA_DB_URL}")
    print(f"API        http://127.0.0.1:{API_PORT}")
    print(f"graph      http://127.0.0.1:{GRAPH_PORT}")
    pids = _read_pids()
    if not pids:
        print("processes  none recorded")
    for name, pid in pids.items():
        print(f"processes  {name:<6} pid={pid} {'RUNNING' if _alive(pid) else 'dead'}")
    print("never started: directory watcher, auto-update scheduler")
    return 0


def cmd_env(args):
    base = os.environ
    for k, v in sorted(isolated_env().items()):
        if base.get(k) != v:
            print(f'set "{k}={v}"' if args.cmd_style else f'{k}={v}')
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("bootstrap"); b.add_argument("--force", action="store_true")
    b.set_defaults(func=cmd_bootstrap)

    s = sub.add_parser("snapshot"); s.add_argument("--full-copy-max-rows", type=int)
    s.set_defaults(func=cmd_snapshot)

    u = sub.add_parser("up"); u.add_argument("--force", action="store_true")
    u.set_defaults(func=cmd_up)

    sub.add_parser("down").set_defaults(func=cmd_down)
    sub.add_parser("status").set_defaults(func=cmd_status)

    e = sub.add_parser("env"); e.add_argument("--cmd-style", action="store_true")
    e.set_defaults(func=cmd_env)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
