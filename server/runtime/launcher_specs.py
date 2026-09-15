"""The launcher's child roster, as a VALUE a test can import (S-255).

🔴 WHY THIS IS NOT INSIDE `run_decoupled_app.py`. That file's module body opens the live
`launcher.log` and re-homes the root logger on import (its own tests say so and read it as
text for that reason), and it sits at the repository root, on no runtime process's
`sys.path`. So two oracles read the roster as TEXT - a fixed 420-character window after
each `ChildSpec(`, a regex on the first mention of `run_chain_worker.py` - and a comment
placed inside a spec turned both red on 2026-09-15 (`86016d10`, moved out again in
`f7f89ab9`) while the launcher was correct. A text proxy for a value is the prohibited
shape. The value lives here, `main()` calls it, and the oracles import it.

Nothing in this module starts, binds, opens or writes anything: `child_specs` builds the
list and returns it.
"""
try:
    import paths
except ImportError:  # imported without server/ on sys.path
    from . import paths  # type: ignore

from runtime.process_supervisor import ChildSpec


def child_specs(python_exe, server_dir, server_cmd, api_host, api_port):
    """The children every launcher start supervises, in start order.

    `heartbeat=` names the progress beat each child publishes (see
    server/utils/heartbeat.py). /health joins this list to those beats: the
    supervisor is authoritative about whether a process exists, the beat is
    authoritative about whether it is getting anything done.

    `ports=` names the TCP ports a child must be able to bind, which is what
    lets the supervisor answer "somebody else owns it" instead of "the
    environment is down". Only two children bind anything, and in the 74-death
    sample those two accounted for 100% of the deaths.

    `log_file=` is where the child's stdout/stderr is tee'd - the console still
    shows it, and now so does a file. uvicorn's start-up lines and its bind
    error live there and nowhere else.

    🔴 [판정 406] THE CHAIN LOOP RUNS IN ITS OWN PROCESS. The API child is told to
    stand down (`ASSY_CHAIN_WORKER=0`) because the launcher already starts the chain's
    own process below - without that, a launcher-run deployment had TWO chain loops and
    one of them lived inside uvicorn, whose event-loop thread the loop body blocks on
    every slow tick. S-252 was one instance of that shape; this removes the shape.

    The desktop shell is NOT here: `main()` appends it only when the launcher is not
    in server-only mode, and its path is `run_decoupled_app.desktop_shell_path`.
    """
    return [
        ChildSpec("Backend FastAPI Server", server_cmd, server_dir,
                  env={"DECOUPLED": "True", "ASSY_CHAIN_WORKER": "0"},
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
