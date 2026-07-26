# -*- coding: utf-8 -*-
"""Start the directory watcher against the ISOLATED environment - or refuse.

`devenv up` deliberately starts no watcher: the ingestion pipeline's churn is
exactly what makes measurements irreproducible. But an ingestion drill needs
one, and a watcher pointed at production is the single most destructive action
in this whole setup - it would ingest drill files into the user's live data.
Leaving that to a hand-rolled launcher per agent is the gap this closes.

Four properties make the rail structural rather than advisory:

1. **The gate is a pure function.** `check_static_isolation` / `check_live_isolation`
   take resolved facts and return a list of violations. A caller - including a
   test - can ask "would this configuration be refused?" without a process, a
   connection or a filesystem anywhere near the decision.

2. **It runs before anything that logs, connects or opens a file.**
   `import run_watcher` alone builds a log file handler, issues DDL and resolves
   the workspace it will watch, so that import happens only inside
   `_start_watcher()`, only after both gates are clean. Nothing above it in this
   module touches the disk.

3. **The live check asks an actually-opened session**, not the environment
   variables this process just read: `SELECT current_database()` from
   `SessionLocal()` is the database the watcher's own connection pool reaches.
   A URL that says `assy_qa` but resolves elsewhere is caught here.

4. **The failure mode is "does not start".** Every refusal path returns
   EXIT_REFUSED before a single watchdog handler is registered. Being unable to
   *prove* isolation - an unreachable database, an unparseable URL - is itself a
   refusal, never a warning.

Usage (normally via `devenv.py watcher-up`, which runs the gate synchronously
first so a refusal lands in the operator's terminal rather than in a log file):

    python server/scripts/dev_env/iso_watcher.py              # gate, then run
    python server/scripts/dev_env/iso_watcher.py --check-only  # gate, then exit
"""
import os
import sys
import argparse

SERVER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

EXIT_REFUSED = 9

GATE_PASSED_MARKER = "[iso-watcher] ALL TARGET ASSERTIONS PASSED - starting watcher"
REFUSED_MARKER = "[iso-watcher] REFUSED TO START"

# What "production" means, in one place. Kept in sync with
# database.database.DEFAULT_PG_URL by a test rather than by hope.
PRODUCTION_DB_NAMES = frozenset({"assy_manager"})
# The live web server (:8080) and the live graph sync worker (:8090). Posting a
# drill's progress/completion events at either contaminates the running system.
PRODUCTION_API_PORTS = frozenset({"8080", "8090"})
# run_watcher.py's fallback when API_BASE_URL is unset - i.e. production.
WATCHER_DEFAULT_API_BASE = "http://127.0.0.1:8080"


# --------------------------------------------------------------- pure helpers
def _database_name(engine_url):
    """Database name out of an engine URL, without importing sqlalchemy."""
    if not engine_url:
        return None
    tail = str(engine_url).rsplit("/", 1)[-1]
    name = tail.split("?", 1)[0].strip()
    return name or None


def _port_of(url):
    """Port out of an http(s) URL, or None."""
    if not url:
        return None
    netloc = str(url).split("//", 1)[-1].split("/", 1)[0]
    host = netloc.rsplit("@", 1)[-1]
    if ":" in host:
        return host.rsplit(":", 1)[-1] or None
    return None


def _is_within(path, base):
    """True when `path` is `base` or lives underneath it (case-insensitive)."""
    if not path or not base:
        return False
    p = os.path.normcase(os.path.abspath(str(path)))
    b = os.path.normcase(os.path.abspath(str(base)))
    return p == b or p.startswith(b + os.sep)


# ----------------------------------------------------------------- the gate
def check_static_isolation(*, server_dir, data_root, config_dir, workspace_dir,
                           is_isolated, workspace_exists, engine_url,
                           api_base_url, assy_api_base=None):
    """Pure. Returns a list of violations; an empty list means safe to start.

    No I/O, no imports, no globals - so a test can hand it production-shaped
    facts and assert the refusal without anything being pointed at production.
    """
    violations = []

    if not is_isolated:
        violations.append(
            "ASSY_DATA_ROOT does not relocate the data root: paths.IS_ISOLATED is "
            f"False, so config/ and ingestion_workspace/ resolve to the LIVE tree "
            f"({data_root}). The watcher would ingest into the user's real workspace.")
    if _is_within(data_root, server_dir):
        violations.append(
            f"data root resolves inside the live server tree: {data_root}")
    if _is_within(config_dir, server_dir):
        violations.append(
            f"config dir resolves inside the live server tree: {config_dir}")
    if _is_within(workspace_dir, server_dir):
        violations.append(
            f"ingestion workspace resolves inside the live server tree: {workspace_dir}")
    if not workspace_exists:
        violations.append(
            f"isolated ingestion workspace does not exist: {workspace_dir} "
            "(run 'devenv.py bootstrap' first)")

    db = _database_name(engine_url)
    if db is None:
        violations.append(
            f"cannot determine the database from the engine URL: {engine_url!r}")
    elif db in PRODUCTION_DB_NAMES:
        violations.append(
            f"the engine is bound to the PRODUCTION database '{db}' ({engine_url})")

    if not api_base_url:
        violations.append(
            "API_BASE_URL is unset, so run_watcher falls back to "
            f"{WATCHER_DEFAULT_API_BASE} - every progress and completion event "
            "would be posted into the PRODUCTION web server.")
    for label, url in (("API_BASE_URL", api_base_url),
                       ("ASSY_API_BASE", assy_api_base)):
        port = _port_of(url)
        if port in PRODUCTION_API_PORTS:
            violations.append(
                f"{label}={url} targets the production port {port}.")

    return violations


def check_live_isolation(*, live_database, engine_url):
    """Pure. The answer from an opened session, judged against the URL.

    Separate from the static gate because it can only run after a connection
    exists - and it is the load-bearing check: it is the database this process
    actually reaches, not the one its environment claims.
    """
    violations = []
    if not live_database:
        violations.append(
            "the opened session did not report a database name, so isolation "
            "cannot be proven from inside this process.")
        return violations
    if live_database in PRODUCTION_DB_NAMES:
        violations.append(
            f"the OPEN CONNECTION reports current_database()='{live_database}' "
            "- this process reaches PRODUCTION.")
    declared = _database_name(engine_url)
    if declared and declared != live_database:
        violations.append(
            f"the engine URL declares database '{declared}' but the open "
            f"connection is on '{live_database}' - the URL cannot be trusted.")
    return violations


# ------------------------------------------------------------ fact gathering
def collect_static_facts():
    """Resolve what this process WILL use. No connection is opened here.

    `database.database` only calls create_engine (lazy - it does not connect),
    so reading engine.url is safe and is strictly better than reading
    os.environ["DATABASE_URL"]: it is the URL the watcher's own pool will use.
    """
    import paths
    from database import database as db_mod

    return {
        "server_dir": paths.SERVER_DIR,
        "data_root": paths.DATA_ROOT,
        "config_dir": paths.CONFIG_DIR,
        "workspace_dir": paths.WORKSPACE_DIR,
        "is_isolated": paths.IS_ISOLATED,
        "workspace_exists": os.path.isdir(paths.WORKSPACE_DIR),
        # str(URL) masks the password as ***; the database name survives.
        "engine_url": str(db_mod.engine.url),
        "api_base_url": os.environ.get("API_BASE_URL"),
        "assy_api_base": os.environ.get("ASSY_API_BASE"),
    }


def probe_live_database():
    """Open a session and ask it where it is. Raises if it cannot be proven."""
    from database.database import SessionLocal, engine
    from sqlalchemy import text

    session = SessionLocal()
    try:
        if engine.url.get_backend_name() == "postgresql":
            row = session.execute(text(
                "SELECT current_database(), current_user, "
                "inet_server_port(), pg_backend_pid()")).first()
            return {
                "database": row[0],
                "describe": (f"current_database='{row[0]}' user='{row[1]}' "
                             f"port={row[2]} backend_pid={row[3]}"),
            }
        # No current_database() outside postgres. Production is postgres, so the
        # static gate carries the weight there; prove the connection opens at
        # all and report the URL's own token, so the declared-vs-live comparison
        # is a no-op rather than a false alarm on a sqlite file path.
        session.execute(text("SELECT 1"))
        name = _database_name(str(engine.url))
        return {"database": name,
                "describe": (f"backend={engine.url.get_backend_name()} "
                             f"database='{name}' (no current_database() outside postgres)")}
    finally:
        session.close()


# ---------------------------------------------------------------- reporting
def _emit_facts(facts):
    print(f"[iso-watcher] env ASSY_DATA_ROOT   = {os.environ.get('ASSY_DATA_ROOT')!r}")
    print(f"[iso-watcher] env API_BASE_URL     = {facts['api_base_url']!r}")
    print(f"[iso-watcher] paths.SERVER_DIR     = {facts['server_dir']}")
    print(f"[iso-watcher] paths.DATA_ROOT      = {facts['data_root']}")
    print(f"[iso-watcher] paths.CONFIG_DIR     = {facts['config_dir']}")
    print(f"[iso-watcher] paths.WORKSPACE_DIR  = {facts['workspace_dir']}")
    print(f"[iso-watcher] paths.IS_ISOLATED    = {facts['is_isolated']}")
    print(f"[iso-watcher] engine.url           = {facts['engine_url']}")
    sys.stdout.flush()


def _refuse(violations):
    print()
    print(f"{REFUSED_MARKER} - {len(violations)} isolation assertion(s) failed:")
    for i, msg in enumerate(violations, 1):
        print(f"  {i}. {msg}")
    print("[iso-watcher] No watchdog handler was registered and no ingestion "
          "code was imported. Nothing was started.")
    sys.stdout.flush()
    return EXIT_REFUSED


# ------------------------------------------------------------------- runner
def _start_watcher(facts):
    """Import and run the watcher. Reached only with a clean gate."""
    # First import of anything that opens a log file, issues DDL or resolves the
    # workspace to watch. Deliberately here and nowhere above.
    import run_watcher

    # Re-gate on the value the imported module actually resolved: run_watcher
    # reads API_BASE_URL at import time, and :8080 there would post every
    # progress and completion event into the production web server.
    post = dict(facts)
    post["api_base_url"] = run_watcher.API_BASE_URL
    violations = check_static_isolation(**post)
    if violations:
        return _refuse(violations)

    print(f"[iso-watcher] run_watcher.API_BASE_URL = {run_watcher.API_BASE_URL}")
    sys.stdout.flush()
    run_watcher.main()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Start the directory watcher against the isolated environment only.")
    ap.add_argument("--check-only", action="store_true",
                    help="run the gate, print the verdict, exit. Never starts the watcher.")
    args = ap.parse_args(argv)

    facts = collect_static_facts()
    _emit_facts(facts)

    violations = check_static_isolation(**facts)
    if violations:
        return _refuse(violations)

    # Only now is it safe to open a connection. A configuration that names
    # production is rejected above, without ever contacting it.
    try:
        live = probe_live_database()
    except Exception as e:  # unreachable DB, bad credentials, anything
        return _refuse([
            "could not open a session to prove which database this process "
            f"reaches: {e.__class__.__name__}: {e}"])

    print(f"[iso-watcher] LIVE CONNECTION       -> {live['describe']}")
    violations = check_live_isolation(live_database=live["database"],
                                      engine_url=facts["engine_url"])
    if violations:
        return _refuse(violations)

    print(GATE_PASSED_MARKER)
    sys.stdout.flush()
    if args.check_only:
        return 0
    return _start_watcher(facts)


if __name__ == "__main__":
    sys.exit(main())
