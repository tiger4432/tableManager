"""B3 - module-level loggers must reach the process log file.

THE HOLE THIS CLOSES
--------------------
`get_process_logger` attached its console and file handlers to a logger named
after the process, and stripped the root logger of handlers on the way. Loggers
that happened to be *children* of that name inherited a handler
(`Watcher.DirectoryWatcher` under `Watcher`); every other module logger did not.

`crud.py` logs to `logging.getLogger("Server")`. In a worker process that logger
has no handlers, `root` has no handlers, so its records fell to
`logging.lastResort`: bare stderr, WARNING and above, absent from the worker's
own log file.

That is not cosmetic. The undeclared-column warning in `crud.py` exists to
surface silent data loss during a 100,000-row ingestion, and the only process
that runs those ingestions is the watcher - where it landed nowhere anyone would
look.

WHY THESE RUN IN A SUBPROCESS
-----------------------------
`get_process_logger` reconfigures the root logger of whatever process calls it.
Calling it inside pytest would rip the handlers out from under pytest's own
capture for every later test in the session. Each probe therefore runs in its own
interpreter, with ASSY_DATA_ROOT pointed at tmp_path, so it cannot append to the
user's live server/*.log either.
"""
import os
import sys
import json
import subprocess

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


PROBE = r"""
import os, sys, json, logging
sys.path.insert(0, os.environ["PROBE_SERVER_DIR"])
import paths
from utils.logger import get_process_logger

name = os.environ["PROBE_LOG_NAME"]
proc_logger = get_process_logger("Watcher", name)

# 1. The process logger itself.
proc_logger.info("OWN_LINE_MARKER")
# 2. crud.py's logger, verbatim: a module logger that is NOT a child of
#    "Watcher" and never gets configured in a worker process.
logging.getLogger("Server").warning("CRUD_UNDECLARED_COLUMN_MARKER")
# 3. A __name__-style module logger (bonding_plan.py, map_overlay.py).
logging.getLogger("some.module.deep").info("MODULE_LINE_MARKER")
# 4. A child of the process name - this one always worked, and is the control.
logging.getLogger("Watcher.DirectoryWatcher").info("CHILD_LINE_MARKER")

for h in logging.getLogger().handlers:
    try:
        h.flush()
    except Exception:
        pass

print("@@" + json.dumps({
    "log_path": paths.log_path(name),
    "root_handlers": len(logging.getLogger().handlers),
    "named_handlers": len(logging.getLogger("Watcher").handlers),
    "lastResort_level": logging.lastResort.level if logging.lastResort else None,
}))
"""


def _run_probe(tmp_path, source=PROBE, extra_env=None):
    root = tmp_path / "iso_root"
    name = "_b3probe.log"
    env = os.environ.copy()
    env.update({
        "PROBE_SERVER_DIR": SERVER_DIR,
        "PROBE_LOG_NAME": name,
        "ASSY_DATA_ROOT": str(root),
        "DATABASE_URL": "sqlite:///:memory:",
        "PYTHONIOENCODING": "utf-8",
    })
    env.update(extra_env or {})
    proc = subprocess.run([sys.executable, "-c", source], cwd=SERVER_DIR,
                          env=env, capture_output=True, text=True, errors="replace")
    assert proc.returncode == 0, f"probe failed:\n{proc.stdout}\n{proc.stderr}"
    line = [l for l in proc.stdout.splitlines() if l.startswith("@@")]
    assert line, f"probe produced no result:\n{proc.stdout}\n{proc.stderr}"
    meta = json.loads(line[-1][2:])
    log_file = root / name
    assert log_file.exists(), "the probe wrote no log file at all"
    return meta, log_file.read_text(encoding="utf-8"), proc


def test_crud_warning_reaches_the_worker_log_file(tmp_path):
    """The B3 regression, in one assertion.

    A watcher process, `crud.py`'s exact logger call, and the watcher's own log
    file. Before the fix this line existed only on stderr.
    """
    meta, text, proc = _run_probe(tmp_path)
    assert "CRUD_UNDECLARED_COLUMN_MARKER" in text, (
        "crud.py's warning did not reach the process log file - B3 is back. "
        f"stderr was:\n{proc.stderr}")
    # And it is attributable: the format keeps the originating logger name, so a
    # Server line inside watcher.log is still identifiable as one.
    assert "[Server]" in text


def test_every_module_logger_reaches_the_file(tmp_path):
    meta, text, _ = _run_probe(tmp_path)
    for marker in ("OWN_LINE_MARKER", "CRUD_UNDECLARED_COLUMN_MARKER",
                   "MODULE_LINE_MARKER", "CHILD_LINE_MARKER"):
        assert marker in text, f"{marker} never reached the log file"


def test_no_line_is_written_twice(tmp_path):
    """Handlers on root AND on the named logger would duplicate every line the
    process logger emits. One handler set, reached by propagation."""
    meta, text, _ = _run_probe(tmp_path)
    assert text.count("OWN_LINE_MARKER") == 1, \
        "the process logger's own line was duplicated"
    assert text.count("CHILD_LINE_MARKER") == 1
    assert meta["named_handlers"] == 0, \
        "handlers are on the named logger again - lines will double up"
    assert meta["root_handlers"] == 2, "expected exactly a console and a file handler"


def test_repeated_configuration_does_not_stack_handlers(tmp_path):
    """main.py, run_watcher.py and the launcher all call this; a second call in
    one process must not add a second pair of handlers."""
    src = PROBE.replace(
        'proc_logger = get_process_logger("Watcher", name)',
        'get_process_logger("Watcher", name)\n'
        'get_process_logger("Watcher", name)\n'
        'proc_logger = get_process_logger("Watcher", name)')
    meta, text, _ = _run_probe(tmp_path, source=src)
    assert meta["root_handlers"] == 2, \
        f"three calls left {meta['root_handlers']} handlers on root"
    assert text.count("OWN_LINE_MARKER") == 1


def test_third_party_info_chatter_is_not_promoted_into_the_log(tmp_path):
    """Handlers on root means every library logs here too. Burying our own lines
    under SQLAlchemy engine chatter is how a log stops being read."""
    src = PROBE.replace(
        'logging.getLogger("some.module.deep").info("MODULE_LINE_MARKER")',
        'logging.getLogger("some.module.deep").info("MODULE_LINE_MARKER")\n'
        'logging.getLogger("sqlalchemy.engine.Engine").info("NOISE_MARKER")\n'
        'logging.getLogger("watchdog.observers").info("NOISE_MARKER")\n'
        'logging.getLogger("urllib3.connectionpool").info("NOISE_MARKER")\n'
        'logging.getLogger("sqlalchemy.engine.Engine").error("REAL_ERROR_MARKER")')
    meta, text, _ = _run_probe(tmp_path, source=src)
    assert "NOISE_MARKER" not in text, "third-party INFO chatter is flooding the log"
    assert "REAL_ERROR_MARKER" in text, \
        "third-party ERRORs were silenced too - that is over-correcting"
    assert "MODULE_LINE_MARKER" in text, "our own INFO must still get through"


def test_the_log_still_follows_the_data_root(tmp_path):
    """The isolation guard this function already carried must survive B3."""
    meta, text, _ = _run_probe(tmp_path)
    expected = os.path.join(str(tmp_path / "iso_root"), "_b3probe.log")
    assert os.path.normcase(meta["log_path"]) == os.path.normcase(expected)
    assert not os.path.exists(os.path.join(SERVER_DIR, "_b3probe.log")), \
        "the probe log leaked into the live server tree"


def test_the_launcher_banner_is_durable(tmp_path):
    """The permanent-failure and shared-cause banners used to be print() to
    stdout, so running the launcher detached lost them entirely. They are the
    record of why a child stopped coming back."""
    src = r"""
import os, sys, json, logging
root = os.environ["PROBE_REPO_ROOT"]
sys.path.insert(0, os.path.join(root, "server"))
sys.path.insert(0, root)
import paths
import importlib.util
spec = importlib.util.spec_from_file_location(
    "launcher_probe", os.path.join(root, "run_decoupled_app.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.log_launcher("CHILD PERMANENTLY FAILED: probe", level="ERROR")
for h in logging.getLogger().handlers:
    try:
        h.flush()
    except Exception:
        pass
print("@@" + json.dumps({"log_path": paths.log_path("launcher.log")}))
"""
    repo_root = os.path.abspath(os.path.join(SERVER_DIR, ".."))
    root = tmp_path / "iso_root"
    env = os.environ.copy()
    env.update({"PROBE_REPO_ROOT": repo_root, "ASSY_DATA_ROOT": str(root),
                "DATABASE_URL": "sqlite:///:memory:", "PYTHONIOENCODING": "utf-8"})
    proc = subprocess.run([sys.executable, "-c", src], cwd=repo_root, env=env,
                          capture_output=True, text=True, errors="replace")
    assert proc.returncode == 0, f"probe failed:\n{proc.stdout}\n{proc.stderr}"

    log_file = root / "launcher.log"
    assert log_file.exists(), "the launcher wrote no log file"
    text = log_file.read_text(encoding="utf-8")
    assert "CHILD PERMANENTLY FAILED: probe" in text, \
        "the launcher's banner is still stdout-only"
    # Console output must not have been traded away for it.
    assert "CHILD PERMANENTLY FAILED: probe" in proc.stdout


# ---------------------------------------------------------------------------
# Which file wins when one process configures logging twice
# ---------------------------------------------------------------------------

SECOND_CALLER = r"""
import os, sys, json, logging
sys.path.insert(0, os.environ["PROBE_SERVER_DIR"])
import paths
from utils.logger import get_process_logger, active_log_filename

first = os.environ["PROBE_LOG_NAME"]
second = "_second_caller.log"

# The process entry point, then something it imports - exactly main.py's shape:
# `get_process_logger("Server", "server.log")` at import, then a startup event that
# imports the chain worker, whose module level asks for chain_worker.log.
get_process_logger("Server", first)
get_process_logger("Chain", second)

logging.getLogger("Server").info("AFTER_SECOND_CALL_MARKER")
for h in logging.getLogger().handlers:
    try:
        h.flush()
    except Exception:
        pass

print("@@" + json.dumps({
    "log_path": paths.log_path(first),
    "second_path": paths.log_path(second),
    "second_exists": os.path.exists(paths.log_path(second)),
    "active": active_log_filename(),
    "root_handlers": len(logging.getLogger().handlers),
}))
"""


def test_the_first_caller_in_a_process_keeps_the_log_file(tmp_path):
    """🔴 THE 2026-09-04 DEFECT, IN ONE ASSERTION.

    It used to be last-wins. `main.py` bound the root to `server.log` at import, its
    startup event imported `chain_ingestion_worker`, and that module's own call
    re-pointed the root at `chain_worker.log` - so four seconds after boot the API's log
    file went silent and every subsequent `[Server]` line landed in the chain worker's
    file. Somebody reading `server.log` for a mapper's output saw an empty tail and read
    it as "the mapper did not run".

    First-wins makes the file follow the PROCESS: its entry point is whatever configured
    logging first. No setting decides it - the import order already says which process
    this is.
    """
    meta, text, _ = _run_probe(tmp_path, source=SECOND_CALLER)
    assert "AFTER_SECOND_CALL_MARKER" in text, \
        "a line written after the second call did not reach the first caller's file"
    assert meta["active"] == "_b3probe.log", "the first caller's file is not the active one"
    assert not meta["second_exists"], \
        "the second caller opened its own file; lines are split across two logs"
    assert meta["root_handlers"] == 2, "the second call added another handler pair"


def test_the_process_publishes_which_file_it_actually_writes(tmp_path):
    """A component that names its log file in its own output has to name the real one.
    `chain_ingestion_worker.MAPPER_LOG_TAG` reads this; without it the tag printed
    `mapper@chain_worker.log` on lines sitting in `server.log`."""
    meta, _, _ = _run_probe(tmp_path, source=SECOND_CALLER)
    assert meta["active"] == "_b3probe.log", \
        "active_log_filename() reports a file this process is not writing to"
