import sys
import os
import time
import signal

# server/ on sys.path so `paths` and `process_supervisor` resolve, matching the
# import convention every other entry point uses.
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT_DIR, "server"))

from process_supervisor import (  # noqa: E402
    ChildSpec, Supervisor, preflight_port_check, psutil_status,
    DUAL_STACK_HOST, describe_bind_host,
)
from launcher_args import parse_launcher_args  # noqa: E402
import paths  # noqa: E402  (single ASSY_DATA_ROOT override point)
from utils.logger import get_process_logger  # noqa: E402

# [B3] The supervisor's restart decisions used to be print() to stdout only, so
# running the launcher detached - or with the console scrolled past - lost the
# permanent-failure and shared-cause banners entirely. They are the record of why
# a child stopped coming back, so they go to a file. Console output is unchanged:
# get_process_logger keeps a stdout handler alongside the file one.
_launcher_logger = get_process_logger("Launcher", "launcher.log")

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


def log_launcher(msg, level="INFO"):
    _launcher_logger.log(_LEVELS.get(level, 20), msg)


# ⚰️ [R-2026-08-14-H] `GRAPH_BIND_HOST = "127.0.0.1"`과 그 근거 문단이 여기 있었다.
# 문단은 「그래프 포트는 이름으로 다이얼하는 호출자가 없으니 듀얼스택이 불필요하다」를
# 설명하고 있었는데, 그 유일한 호출자였던 `main.py`의 `/api/graph/sync` 홉이 이번
# 판정으로 거절로 바뀌었다. 즉 호출자가 0이 됐고 바인드할 프로세스도 사라졌다.
# 근거가 살아 있는 판단은 코드가 사라져도 되살아나므로, 부활이 필요하면 git 이력에
# 있다(이 커밋의 부모).


def refuse_if_ports_are_taken(api_host, api_port):
    """Refuse to start when an older stack still owns the port. Returns True if clear.

    THE FAILURE THIS REPLACES
    -------------------------
    A launcher started while another one is still running used to spawn all five
    children anyway. The two that bind a port (:8080 web, :8090 graph sync) died
    on OSError about three seconds in, every time; the supervisor could not tell a
    bind conflict from an environment outage, so it filed them as a shared cause
    and retried on a 60 s timer with no limit. Meanwhile /health answered 503 -
    from the OLD server - so the operator read a sick new server instead of a
    duplicate start. Measured cost: a minute of silence, or forever.

    None of that is worth one second of anybody's attention. The port is either
    free or it is not, the owner's PID is readable without administrator rights,
    and the answer belongs on the console the operator is already looking at.
    """
    try:
        # ⚰️ [R-2026-08-14-H] 그래프 포트(:8090) 프로브가 여기 함께 있었다. 이제
        # 이 런처가 띄우는 자식 중 그 포트를 바인드하는 것이 없으므로, 계속 물어보면
        # «아무도 필요로 하지 않는 포트» 때문에 스택 전체가 기동을 거부할 수 있다 —
        # 가드가 자기가 막으려던 것(못 뜨는 스택)이 되는 자리다.
        conflicts = preflight_port_check([int(api_port)], host=api_host)
    except Exception as e:
        # A guard must never become the reason the system will not start. If the
        # ports cannot even be parsed or probed, say so and let the children try.
        log_launcher(f"Port preflight could not run ({e}); starting anyway.",
                     level="WARNING")
        return True
    if not conflicts:
        return True

    banner = ["", "=" * 68,
              " 기동을 중단합니다: 필요한 포트를 이미 다른 프로세스가 쓰고 있습니다.",
              " REFUSING TO START - required ports are already in use.", ""]
    for _port, detail in conflicts:
        banner.append(f"   {detail}")
    banner += [
        "",
        " 이 서버 스택이 이미 실행 중일 가능성이 가장 높습니다.",
        " 이미 떠 있는 스택이라면 그대로 사용하십시오. 새로 띄울 필요가 없습니다.",
        " 정말로 재시작하려면 위 PID 를 먼저 종료하십시오:",
        "     taskkill /PID <pid> /T /F",
        "",
        " (아무것도 기동하지 않았습니다. 기존 프로세스는 그대로 살아 있습니다.)",
        " Nothing was started. The processes that own these ports are untouched.",
        "=" * 68, ""]
    for line in banner:
        log_launcher(line, level="ERROR")
    return False


def report_schema_drift():
    """Print whether this database carries the schema this build expects.

    Reports; never refuses. The reasoning for that split lives at the call site.

    Everything here is a catalog read - `check_schema_drift` issues no DDL and no
    DML - so it is safe against a production database at any moment, including a
    moment when something is already broken.

    Like the port guard above, a check must never become the reason the system
    will not start: every failure path below degrades to a line and a return.

    THIS RUNS BEFORE THE PROCESSES THAT REPAIR HALF OF WHAT IT FINDS, and that is
    not an accident to be tidied away. Two of the children started below -
    run_watcher.py, run_chain_worker.py - each call
    `models.sync_dynamic_tables_schema(engine)` on their own boot, as does the web
    server through `bootstrap_database_schema`. So a column that table_config
    declares on a dynamic table is missing when this line reads the catalog and
    present a few seconds later, with nothing asked of anybody.

    Moving the check after `start_all` would trade that away for nothing: the whole
    value of a pre-flight is that the operator is still standing at the console and
    nothing is up yet to be disrupted. What was actually wrong was the banner, which
    on 2026-08-13 told the product owner that every screen touching `dt_map` failed
    until they wrote a migration - for two columns the very same startup added. The
    fix is in `schema_drift._sync_repairs`, which classifies that one drift kind and
    leaves every other one at full severity.
    """
    try:
        # The runtime module, not the CLI in server/scripts - `server/` is already
        # on this process's sys.path (top of this file) and server/scripts must
        # never be (server/tests/test_prod_import_env.py).
        import schema_drift
        import paths as _paths
        from database.database import (SQLALCHEMY_DATABASE_URL, DB_URL_SOURCE,
                                       engine as _engine)
        target = (f"{_paths.mask_db_password(SQLALCHEMY_DATABASE_URL)} "
                  f"(from {DB_URL_SOURCE})")
    except Exception as e:
        log_launcher(f"Schema drift check unavailable ({type(e).__name__}: {e}); "
                     f"starting anyway.", level="WARNING")
        return None
    try:
        return schema_drift.run_at_startup(
            _engine,
            lambda level, text: log_launcher(text, level=level.upper()),
            target=target)
    except Exception as e:
        log_launcher(f"Schema drift check failed ({type(e).__name__}: {e}); "
                     f"starting anyway.", level="WARNING")
        return None


def refuse_if_arguments_are_unknown(argv):
    """Parse the command line. Returns the parsed args, or exits before anything runs.

    THE FAILURE THIS REPLACES
    -------------------------
    Every flag used to be `"--flag" in sys.argv`, so an argument the launcher
    did not recognise was not an error - it was nothing. Measured on this file
    before the fix, with subprocess.Popen neutered: `--server_only` planned SIX
    children (the full stack, desktop window included) while `--server-only`
    planned five. A one-character typo silently started the thing the operator
    was explicitly trying not to start, and with a stack already running the two
    port binders then failed to bind and went into the correlated-backoff loop.

    This runs FIRST - before the port probe, because there is no point asking
    about ports for a command that is not going to run, and long before the
    "Starting AssyManager" banner, because a banner followed by a refusal is the
    contradiction that makes an operator stop and reread.
    """
    args = parse_launcher_args(argv)
    if args.should_start:
        return args
    if args.is_refusal:
        # On the record, not just on a console someone scrolled past - same
        # channel the port refusal uses.
        for line in args.lines:
            log_launcher(line, level="ERROR")
    else:
        # --help is an answer, not an incident. Plain stdout, no log file.
        for line in args.lines:
            print(line)
    sys.exit(args.exit_code)


def main():
    root_dir = _ROOT_DIR
    server_dir = os.path.join(root_dir, "server")

    # Nothing below this line is reached by a command line the launcher does not
    # fully understand.
    args = refuse_if_arguments_are_unknown(sys.argv[1:])

    # Use the current python executable (guarantees the active conda environment is used)
    python_exe = sys.executable

    # Production default. Overridable so the whole launcher - supervision policy
    # included - can be exercised against the isolated dev stack on :8081 instead
    # of being verified by a reimplementation of itself.
    api_port = os.environ.get("ASSY_API_PORT", "8080")

    # uvicorn defaults to 127.0.0.1, which made the launcher reachable only from the
    # server box - while SERVER_STARTUP_GUIDE documented --host 0.0.0.0 and the team
    # actually reaches this over the LAN. The two disagreed, and the launcher was the
    # side that was wrong: it could not produce the deployment everyone was using.
    # Override with ASSY_API_HOST when a narrower bind is wanted (e.g. 127.0.0.1 on a
    # dev box). Exposure is gated by the admin token and the static-path containment
    # check, not by the bind address - see docs/guide/DEPLOY_SETUP.md.
    #
    # [2026-08-04] The DEFAULT is now the dual-stack wildcard, not "0.0.0.0".
    # Diagnosed on the live stack: netstat showed `0.0.0.0:8080` and no `[::]:8080`,
    # and on Windows `localhost` resolves to ::1 BEFORE 127.0.0.1. Reaching the app
    # as `localhost` therefore loaded the page (HTTP falls back to IPv4) while the
    # WebSocket sat in CONNECTING - and because the client's reconnect ladder is
    # driven by onclose, a connection that never opens and never closes never
    # retries. Reaching the same server by its LAN address worked at the same
    # moment; the only variable was name resolution.
    #
    # Only the DEFAULT changed. Every explicit ASSY_API_HOST string keeps the exact
    # meaning it had yesterday - "127.0.0.1" is still a narrow IPv4-only bind, and
    # so is an explicit "0.0.0.0" - because narrowing the bind is the entire point
    # of the variable and an operator who typed an address meant that address.
    api_host = os.environ.get("ASSY_API_HOST", DUAL_STACK_HOST)
    # ⚰️ [R-2026-08-14-H] `graph_port` 읽기가 여기 있었다 (GRAPH_SYNC_PORT, 기본 8090).
    # 이 런처는 더 이상 그 포트를 쓰는 자식을 띄우지 않는다.
    server_cmd = [python_exe, "-m", "uvicorn", "main:app",
                  "--host", api_host, "--port", api_port]
    if args.reload:
        server_cmd.append("--reload")

    # Server-only mode. `--no-client` and `--server-only` are synonyms and both
    # keep working exactly as they did - see server/launcher_args.py.
    server_only = args.server_only

    # Nothing is spawned until the ports are known to be free. Five children
    # racing an older stack is not a startup - and the banner below is not
    # printed until we know there is going to be one, because "Starting
    # AssyManager" followed by a refusal is exactly the kind of contradiction an
    # operator has to stop and reread.
    ports_clear = refuse_if_ports_are_taken(api_host, api_port)
    if ports_clear:
        # The second pre-flight question, asked in the same slot as the first and
        # for the same reason: BEFORE the restart rather than after it.
        #
        # "A migration must run" is a deployment fact that nothing in this repo
        # carried. A commit that adds a column to a model looks exactly like one
        # that does not, so the operator restarted, the stack came up, and the
        # first report was a screen erroring, repeatedly on 2026-08-05. This is
        # the moment that fact exists and can still be acted on cheaply: the
        # operator is at the console, and nothing is up yet to be disrupted.
        #
        # It does NOT touch the exit code, and that is deliberate. The port guard
        # refuses because a second stack on a held port cannot work at all. Drift
        # is not that: the product runs, minus the tables that drifted. Refusing
        # here would hand an unattended restart the power to keep the whole
        # product down over one column - and a restart is exactly when nobody is
        # watching. The verdict is loud; the decision stays with the human.
        report_schema_drift()
    if args.preflight_only:
        # Ask the question without answering it by starting anything. Also what
        # the end-to-end test drives, so the refusal path can be exercised
        # against throwaway ports with no risk of spawning a second stack.
        if ports_clear:
            log_launcher(f"Preflight OK: port {api_port} is free.")
        sys.exit(0 if ports_clear else 1)
    if not ports_clear:
        sys.exit(1)

    print("=" * 60)
    print(" Starting AssyManager Enterprise in Decoupled Process Mode...")
    print(f" Python Executable: {python_exe}")
    print("=" * 60)

    # What is REALLY bound, not the string that was passed in. uvicorn's own
    # "Uvicorn running on ..." line echoes config.host verbatim, so for the
    # dual-stack default it prints `http://:8080` - which names neither address
    # that is actually listening and is worse than silence for an operator trying
    # to work out why one URL works and another does not. This line is derived
    # from the same bind_targets() the pre-flight guard probed, so the operator
    # and the guard cannot be looking at different addresses.
    #
    # `--reload` is the one case where the line would otherwise LIE. That flag
    # sends uvicorn down Config.bind_socket() instead of loop.create_server(), and
    # bind_socket builds a single AF_INET socket - so the dual-stack host yields an
    # IPv4-only listener. Measured, same throwaway-port harness as the table in
    # process_supervisor.DUAL_STACK_HOST. It is a dev-only flag and production does
    # not use it, so the behaviour is reported rather than worked around: an
    # operator debugging "why does localhost hang under --reload" needs this
    # sentence, and a line that claimed both stacks would cost them the afternoon.
    reload_narrows = args.reload and api_host == DUAL_STACK_HOST
    if reload_narrows:
        log_launcher(f"API 리슨 주소: 0.0.0.0 : 포트 {api_port}"
                     "  (--reload 는 IPv4 단독 - localhost(::1) 접속은 안 됩니다)",
                     level="WARNING")
    else:
        log_launcher(f"API 리슨 주소: {describe_bind_host(api_host)} : 포트 {api_port}"
                     + ("  (기본값 - IPv4/IPv6 양쪽)"
                        if api_host == DUAL_STACK_HOST
                        else "  (ASSY_API_HOST 지정 - 이 주소로만 접속됩니다)"))
    # ⚰️ [R-2026-08-14-H] 「그래프 싱크 리슨 주소」 배너가 여기 있었다. 아무도
    # 바인드하지 않는 포트를 계속 announce하면 운영자는 그 프로세스가 있다고 믿는다.

    # `heartbeat=` names the progress beat each child publishes (see
    # server/utils/heartbeat.py). /health joins this list to those beats: the
    # supervisor is authoritative about whether a process exists, the beat is
    # authoritative about whether it is getting anything done.
    #
    # `ports=` names the TCP ports a child must be able to bind, which is what
    # lets the supervisor answer "somebody else owns it" instead of "the
    # environment is down". Only two children bind anything, and in the 74-death
    # sample those two accounted for 100% of the deaths.
    #
    # `log_file=` is where the child's stdout/stderr is tee'd - the console still
    # shows it, and now so does a file. uvicorn's start-up lines and its bind
    # error live there and nowhere else.
    specs = [
        ChildSpec("Backend FastAPI Server", server_cmd, server_dir,
                  env={"DECOUPLED": "True"},
                  ports=(int(api_port),), port_host=api_host,
                  log_file=paths.log_path("server_stdout.log")),
        # The workers assume the web server is accepting /internal/events/*.
        ChildSpec("File Ingestion Watcher", [python_exe, "run_watcher.py"], server_dir,
                  heartbeat="watcher", start_delay=2.0,
                  log_file=paths.log_path("watcher_stdout.log")),
        # ⚰️ [R-2026-08-14-H] "Graph DB Sync Worker" (`run_graph_sync.py`, :8090)가
        # 여기 있었다. 스택은 5프로세스에서 4프로세스가 된다.
        # 이 자식이 하던 일은 outbox를 증분 소비해 행을 `graph_nodes`/`graph_edges`의
        # 사본으로 머티리얼라이즈하는 것이었다. 소유자 판정으로 그 사본이 폐기됐다 —
        # 원장(`ledger_events`)이 개체 층이고, 실측상 이 워커에는 `ledger` 참조가
        # 0건이었다. 두 갈래가 같은 소스 표를 각자 읽으며 서로를 몰랐다는 뜻이다.
        # 진입(라우트)은 `server/main.py`의 `_graph_branch_retired`가 막고,
        # 저장소는 `server/migrations/drop_graph_storage.py`가 폐기한다.
        ChildSpec("Chained Ingestion Worker", [python_exe, "run_chain_worker.py"], server_dir,
                  heartbeat="chain",
                  log_file=paths.log_path("chain_worker_stdout.log")),
        ChildSpec("Auto Update Scheduler", [python_exe, "run_auto_update.py"], server_dir,
                  heartbeat="scheduler",
                  log_file=paths.log_path("auto_update_stdout.log")),
    ]
    if not server_only:
        # The desktop window closing means "stop everything", not "restart me".
        specs.append(ChildSpec("Desktop Client UI",
                               [python_exe, os.path.join(root_dir, "client", "desktop_wrapper.py")],
                               root_dir, restartable=False,
                               log_file=paths.log_path("desktop_client_stdout.log")))

    supervisor = Supervisor(specs, log=log_launcher)

    # Graceful shutdown handler
    def shutdown_all(signum=None, frame=None):
        if signum:
            log_launcher(f"Signal {signum} received. Cleaning up all background processes...", level="WARNING")
        elif server_only:
            log_launcher("Stopping all backend server processes...")
        else:
            log_launcher("Desktop Client window closed. Cleaning up all background processes...")

        # stop_all() sets the stopping flag before terminating anything, so the
        # monitor loop cannot race us and restart a child we are shutting down.
        supervisor.stop_all(timeout=3.0)
        print("=" * 60)
        print(" AssyManager has stopped cleanly.")
        print("=" * 60)
        sys.exit(0)

    # Register signal handler for Ctrl+C (SIGINT) and SIGTERM
    signal.signal(signal.SIGINT, shutdown_all)
    signal.signal(signal.SIGTERM, shutdown_all)
    # Windows delivers Ctrl+Break as SIGBREAK, not SIGINT. Without this the
    # graceful path is simply unreachable for that key, and the launcher dies
    # leaving its children orphaned.
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, shutdown_all)

    # Announced at boot, not discovered at shutdown: without psutil the launcher
    # still stops its five children but leaves their own subprocesses (the
    # auto-update collector scripts) running as orphans.
    psutil_ok, psutil_detail = psutil_status()
    log_launcher(psutil_detail, level="INFO" if psutil_ok else "WARNING")

    supervisor.start_all()
    log_launcher(f"Supervising {len(specs)} process(es). "
                 f"Status: {supervisor.status_file}")
    if server_only:
        log_launcher("Running in Server-only mode. Press Ctrl+C to stop.")

    try:
        # Replaces the old `while True: time.sleep(1)`, which detected nothing.
        supervisor.run()
        log_launcher("Desktop client closed.")
        shutdown_all()
    except KeyboardInterrupt:
        shutdown_all()

if __name__ == "__main__":
    main()
