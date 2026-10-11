"""Stop the retroactive runs that hold the queue - one double-click (`stop_retroactive.bat`), no token, no curl.

    python scripts/stop_retroactive.py            the runs in flight, then stop them after one «y»
    python scripts/stop_retroactive.py <run_id>   only that run
    python scripts/stop_retroactive.py --yes      no question

Per run: a run process of THIS host (`retroactive/<host>/<pid>` - a CLI's `run_here` or the scheduler's
child) is ended first, its heartbeat with it, so the screen's own cancel (`request_cancel`) finds nobody
and releases the row `failed`. A row still in flight after that is marked `failed` by hand - the
UPDATE RUN.md names as the last resort - with the reason on the row.
"""
import os
import socket
import subprocess
import sys

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

HAND_RELEASE = "released by hand (stop_retroactive)"


def _end_process(runner):
    """End the run's process when it is a run process on this host. -> one line of what was done, or None."""
    from admin import retroactive
    from utils import heartbeat

    parts = str(runner or "").split("/")
    if len(parts) != 3 or parts[0] != retroactive.RUN_HERE_HEARTBEAT \
            or parts[1] != socket.gethostname() or not parts[2].isdigit():
        return None
    name, pid = parts[0], parts[2]
    done = subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True, text=True)
    if str((heartbeat.read_all().get(name) or {}).get("pid")) == pid:
        heartbeat.forget(name)
    return "process %s: %s" % (pid, (done.stdout or done.stderr or "").strip() or done.returncode)


def main(argv, ask=input, say=print) -> int:
    from admin import retroactive
    from database import models
    from database.database import SessionLocal

    yes = "--yes" in argv
    wanted = [arg for arg in argv if not arg.startswith("--")]
    run = models.RetroactiveRun
    db = SessionLocal()
    try:
        query = db.query(run).filter(run.state.in_((retroactive.RUN_QUEUED,) + retroactive.IN_FLIGHT_STATES))
        if wanted:
            query = query.filter(run.run_id.in_(wanted))
        rows = query.order_by(run.queued_at).all()
        if not rows:
            say("No retroactive run is queued or running.")
            return 0
        for row in rows:
            say("%s  %s  %s  runner=%s  last progress=%s" % (
                row.run_id, row.op, row.state, row.runner, row.last_progress_at))
        if not yes and ask("Stop these %d run(s)? [y/N] " % len(rows)).strip().lower() != "y":
            say("Nothing stopped.")
            return 1
        for run_id, state, runner in [(row.run_id, row.state, row.runner) for row in rows]:
            if state != retroactive.RUN_QUEUED:
                ended = _end_process(runner)
                if ended:
                    say("  " + ended)
            if retroactive.request_cancel(db, run_id)["state"] in retroactive.IN_FLIGHT_STATES:
                retroactive._mark_run(run_id, state=retroactive.RUN_FAILED, finished=True, error=HAND_RELEASE)
            db.expire_all()
            say("  %s -> %s" % (run_id, db.query(run.state).filter(run.run_id == run_id).scalar()))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    os.chdir(SERVER_DIR)
    sys.exit(main(sys.argv[1:]))
