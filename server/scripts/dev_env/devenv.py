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

`up` starts no directory watcher and no auto-update scheduler - their 2-minute
collector cron is exactly the churn that makes measurements irreproducible. The
collector scripts themselves are copied in, so "the scheduler is off" is a fact
about the running processes, not about a missing file.

An ingestion drill does need a watcher, so that is a SEPARATE verb
(`watcher-up`) and `up` stays churn-free. The watcher runs behind an isolation
gate that refuses to start unless the running process itself proves it is
isolated - see scripts/dev_env/iso_watcher.py.

Commands:
    bootstrap    copy config/ + ingestion_workspace/ into dev_env/ (skips raws/archives)
    snapshot     build or refresh the assy_qa snapshot database
    up           bootstrap if needed, then start the isolated processes
    down         stop them (including the watcher, if one is running)
    status       what is running, what it points at
    env          print the environment variables (for running one-off scripts)
    watcher-up   start a directory watcher against the ISOLATED env only
    watcher-down stop it
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
# The watcher is a separate verb, so it gets a separate ledger: `up --force`
# must not be able to forget a running watcher.
WATCHER_PID_FILE = os.path.join(DEV_ROOT, "watcher_pid.json")
LOG_DIR = os.path.join(DEV_ROOT, "logs")
ISO_WATCHER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iso_watcher.py")

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
    # ⚰️ [R-2026-08-14-H] ("graph", run_graph_sync.py) 가 여기 있었다. 격리 스택은
    # 운영 스택의 축소판이어야 하므로 같이 뺀다 — 격리 환경에만 죽은 갈래가 남으면
    # QA가 운영에 없는 동작을 재현하게 된다.
    # DELIBERATELY ABSENT: run_watcher.py, run_auto_update.py.
]


def _read_pids(path=PID_FILE):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_pids(path, pids):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pids, f, indent=2)


def _stop_recorded(path, label):
    """Stop everything recorded in a pid file. Returns how many were alive."""
    pids = _read_pids(path)
    stopped = 0
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
            stopped += 1
        except Exception as e:
            log(f"failed to stop {name} (pid {pid}): {e}")
    if pids and os.path.exists(path):
        os.remove(path)
    elif not pids:
        log(f"no {label} recorded as running")
    return stopped


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

    _write_pids(PID_FILE, pids)

    print()
    log(f"API      http://127.0.0.1:{API_PORT}")
    log(f"database {QA_DB_URL}")
    log(f"data     {DEV_ROOT}")
    log("watcher + auto-update scheduler: NOT started (no churn)")
    log("need a watcher for an ingestion drill? 'watcher-up' (gated)")
    return 0


def cmd_down(args):
    n = _stop_recorded(WATCHER_PID_FILE, "watcher")
    n += _stop_recorded(PID_FILE, "process")
    return 0


# --------------------------------------------------------------- watcher-up
def cmd_watcher_up(args):
    """Start a directory watcher that CANNOT be pointed at production.

    The gate is not implemented here on purpose: a check made by this process
    proves nothing about the process that will do the ingesting. It lives inside
    iso_watcher.py and runs there, in the watcher's own interpreter, against its
    own resolved paths and its own opened database session.

    We do run it once in --check-only mode first, so a refusal lands in the
    operator's terminal instead of disappearing into a log file. The real
    process re-runs the whole gate itself - that is the load-bearing one.
    """
    if not os.path.isdir(DEV_ROOT):
        log(f"{DEV_ROOT} missing - run 'bootstrap' first "
            "(a watcher needs an isolated workspace to watch)")
        return 1
    os.makedirs(LOG_DIR, exist_ok=True)

    running = {n: p for n, p in _read_pids(WATCHER_PID_FILE).items() if _alive(p)}
    if running and not args.force:
        log(f"watcher already running: {running}. "
            "Use 'watcher-down' first, or 'watcher-up --force'.")
        return 1

    env = isolated_env()
    log("running the isolation gate...")
    rc = subprocess.call([sys.executable, ISO_WATCHER, "--check-only"],
                         cwd=SERVER_DIR, env=env)
    if rc != 0:
        log(f"isolation gate REFUSED (exit {rc}) - watcher NOT started")
        return rc

    logfile = os.path.join(LOG_DIR, "watcher_stdout.log")
    f = open(logfile, "ab")
    proc = subprocess.Popen([sys.executable, ISO_WATCHER],
                            cwd=SERVER_DIR, env=env, stdout=f, stderr=f)
    _write_pids(WATCHER_PID_FILE, {"watcher": proc.pid})
    log(f"started watcher pid={proc.pid}  -> {logfile}")

    # The child re-runs the gate; if it refuses, it exits before watching
    # anything. Confirm it actually survived rather than reporting a pid that
    # is already gone.
    time.sleep(3.0)
    if not _alive(proc.pid):
        log(f"watcher exited immediately (gate refused in the real process?) "
            f"- see {logfile}")
        if os.path.exists(WATCHER_PID_FILE):
            os.remove(WATCHER_PID_FILE)
        return 1

    log(f"watching  {os.path.join(DEV_ROOT, 'ingestion_workspace')}")
    log(f"log file  {os.path.join(DEV_ROOT, 'watcher.log')}")
    return 0


def cmd_watcher_down(args):
    _stop_recorded(WATCHER_PID_FILE, "watcher")
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
        print(f"processes  {name:<7} pid={pid} {'RUNNING' if _alive(pid) else 'dead'}")
    watcher = _read_pids(WATCHER_PID_FILE)
    if not watcher:
        print("processes  watcher not started (use 'watcher-up')")
    for name, pid in watcher.items():
        print(f"processes  {name:<7} pid={pid} {'RUNNING' if _alive(pid) else 'dead'} (gated)")
    print("never started: auto-update scheduler")
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

    w = sub.add_parser("watcher-up"); w.add_argument("--force", action="store_true")
    w.set_defaults(func=cmd_watcher_up)
    sub.add_parser("watcher-down").set_defaults(func=cmd_watcher_down)

    e = sub.add_parser("env"); e.add_argument("--cmd-style", action="store_true")
    e.set_defaults(func=cmd_env)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
