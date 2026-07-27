import sys
import os
import time
import signal

# server/ on sys.path so `paths` and `process_supervisor` resolve, matching the
# import convention every other entry point uses.
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT_DIR, "server"))

from process_supervisor import ChildSpec, Supervisor, psutil_status  # noqa: E402
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

def main():
    root_dir = _ROOT_DIR
    server_dir = os.path.join(root_dir, "server")

    # Use the current python executable (guarantees the active conda environment is used)
    python_exe = sys.executable

    # Production default. Overridable so the whole launcher - supervision policy
    # included - can be exercised against the isolated dev stack on :8081 instead
    # of being verified by a reimplementation of itself.
    api_port = os.environ.get("ASSY_API_PORT", "8080")

    print("=" * 60)
    print(" Starting AssyManager Enterprise in Decoupled Process Mode...")
    print(f" Python Executable: {python_exe}")
    print("=" * 60)

    # uvicorn defaults to 127.0.0.1, which made the launcher reachable only from the
    # server box - while SERVER_STARTUP_GUIDE documented --host 0.0.0.0 and the team
    # actually reaches this over the LAN. The two disagreed, and the launcher was the
    # side that was wrong: it could not produce the deployment everyone was using.
    # Override with ASSY_API_HOST when a narrower bind is wanted (e.g. 127.0.0.1 on a
    # dev box). Exposure is gated by the admin token and the static-path containment
    # check, not by the bind address - see docs/guide/DEPLOY_SETUP.md.
    api_host = os.environ.get("ASSY_API_HOST", "0.0.0.0")
    server_cmd = [python_exe, "-m", "uvicorn", "main:app",
                  "--host", api_host, "--port", api_port]
    if "--reload" in sys.argv:
        server_cmd.append("--reload")

    # Check command-line arguments for server-only mode
    server_only = "--no-client" in sys.argv or "--server-only" in sys.argv

    # `heartbeat=` names the progress beat each child publishes (see
    # server/utils/heartbeat.py). /health joins this list to those beats: the
    # supervisor is authoritative about whether a process exists, the beat is
    # authoritative about whether it is getting anything done.
    specs = [
        ChildSpec("Backend FastAPI Server", server_cmd, server_dir,
                  env={"DECOUPLED": "True"}),
        # The workers assume the web server is accepting /internal/events/*.
        ChildSpec("File Ingestion Watcher", [python_exe, "run_watcher.py"], server_dir,
                  heartbeat="watcher", start_delay=2.0),
        ChildSpec("Graph DB Sync Worker", [python_exe, "run_graph_sync.py"], server_dir,
                  heartbeat="graph"),
        ChildSpec("Chained Ingestion Worker", [python_exe, "run_chain_worker.py"], server_dir,
                  heartbeat="chain"),
        ChildSpec("Auto Update Scheduler", [python_exe, "run_auto_update.py"], server_dir,
                  heartbeat="scheduler"),
    ]
    if not server_only:
        # The desktop window closing means "stop everything", not "restart me".
        specs.append(ChildSpec("Desktop Client UI",
                               [python_exe, os.path.join(root_dir, "client", "desktop_wrapper.py")],
                               root_dir, restartable=False))

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
