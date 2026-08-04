"""A mistyped launcher flag must refuse, not silently start the full stack.

THE INCIDENT
------------
The operator meant to start server-only and mistyped the flag. The launcher
parsed every option by membership in ``sys.argv``, so an argument it did not
recognise was not an error - it was nothing. The full stack started, desktop
window included; a stack was already running; the two port binders could not
bind :8080/:8090 and went into the correlated-backoff loop. From the console it
read as "the socket is completely dead" plus "why is the desktop client
running".

Measured on the pre-fix launcher, with ``subprocess.Popen`` neutered so nothing
could actually start::

    --server_only  -> PLANNED CHILDREN: Backend | Watcher | Graph | Chain |
                                        Scheduler | Desktop Client UI
    --server-only  -> PLANNED CHILDREN: Backend | Watcher | Graph | Chain |
                                        Scheduler

HOW THIS FILE PROVES "NOTHING STARTED"
--------------------------------------
Not by reading the refusal message - a message proves only that a message was
printed. A ``sitecustomize.py`` on ``PYTHONPATH`` replaces ``subprocess.Popen``
in the launcher process with a tripwire that records the attempt to a file and
then kills the process, so a spawn ATTEMPT is observable and a spawn never
happens. ``test_a_valid_command_line_does_trip_the_tripwire`` is the positive
control: without it, "the marker file is absent" would also pass if the
tripwire were broken.

The production stack is live. Nothing here starts, stops or restarts any
process: the tripwire runs before ``CreateProcess``, and every port used is a
throwaway one.
"""
import os
import socket
import subprocess
import sys

import pytest

import launcher_args as la
from launcher_args import (
    EXIT_BAD_ARGUMENT, FLAGS, KNOWN_FLAGS, help_lines, parse_launcher_args,
    suggest_flag,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LAUNCHER = os.path.join(ROOT, "run_decoupled_app.py")


def free_port():
    """A port number nothing is listening on."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ===========================================================================
# (1) The parser as a function. No subprocess, no side effects.
# ===========================================================================

# Every spelling that worked before this module existed, and what it meant.
# `--no-client` and `--server-only` are synonyms; order never mattered; flags
# combine. This table is the no-regression contract: an operator has muscle
# memory for these, and changing what a working spelling does would be a worse
# defect than the one being fixed.
EXISTING_BEHAVIOUR = [
    ([], False, False, False),
    (["--server-only"], True, False, False),
    (["--no-client"], True, False, False),
    (["--reload"], False, True, False),
    (["--preflight-only"], False, False, True),
    (["--server-only", "--preflight-only"], True, False, True),
    (["--preflight-only", "--server-only"], True, False, True),
    (["--no-client", "--reload"], True, True, False),
    (["--reload", "--no-client"], True, True, False),
    (["--server-only", "--no-client"], True, False, False),
    (["--server-only", "--reload", "--preflight-only"], True, True, True),
]


@pytest.mark.parametrize("argv,server_only,reload_,preflight", EXISTING_BEHAVIOUR)
def test_every_existing_spelling_still_means_what_it_meant(argv, server_only,
                                                           reload_, preflight):
    args = parse_launcher_args(argv)
    assert args.should_start, f"{argv} was refused; it used to work"
    assert args.exit_code is None
    assert args.server_only is server_only, f"{argv}: server_only regressed"
    assert args.reload is reload_, f"{argv}: reload regressed"
    assert args.preflight_only is preflight, f"{argv}: preflight_only regressed"


def test_no_arguments_means_the_full_stack():
    """The control for the table above. If everything defaulted to server-only
    the incident would be 'invisible' rather than fixed."""
    assert parse_launcher_args([]).server_only is False


@pytest.mark.parametrize("typo,expected", [
    ("--server_only", "--server-only"),      # the one that caused the incident
    ("--serveronly", "--server-only"),
    ("--server-onlyy", "--server-only"),
    ("--no_client", "--no-client"),
    ("--noclient", "--no-client"),
    ("--preflight-onlyy", "--preflight-only"),
    ("--preflight_only", "--preflight-only"),
    ("--relaod", "--reload"),
])
def test_a_near_miss_spelling_suggests_the_right_flag(typo, expected):
    """The failure mode is a near-miss, not an invention. A refusal that only
    says "unknown argument" sends the operator back to the source to find the
    spelling; naming the intended flag ends it in one line."""
    assert suggest_flag(typo) == expected
    args = parse_launcher_args([typo])
    assert args.exit_code == EXIT_BAD_ARGUMENT
    text = "\n".join(args.lines)
    assert typo in text, "the refusal does not name the argument it rejected"
    assert expected in text, "the refusal does not offer the closest valid flag"


@pytest.mark.parametrize("invented", ["--verbose", "--dry-run", "-x", "foo.txt"])
def test_an_invented_argument_is_refused_without_a_wrong_guess(invented):
    """None is a real answer. Offering `--reload` to somebody who typed
    `--verbose` spends the one line they are going to read on a wrong guess."""
    assert suggest_flag(invented) is None
    args = parse_launcher_args([invented])
    assert args.exit_code == EXIT_BAD_ARGUMENT
    assert args.should_start is False
    assert invented in "\n".join(args.lines)


def test_a_refusal_names_every_argument_it_did_not_understand():
    args = parse_launcher_args(["--server_only", "--relaod"])
    text = "\n".join(args.lines)
    for bad, good in (("--server_only", "--server-only"), ("--relaod", "--reload")):
        assert bad in text
        assert good in text


def test_one_bad_argument_poisons_an_otherwise_valid_command_line():
    """`--server-only --serveronly` must not run. Half-understanding a command
    line is how the operator gets something they did not ask for."""
    args = parse_launcher_args(["--server-only", "--serveronly"])
    assert args.should_start is False
    assert args.exit_code == EXIT_BAD_ARGUMENT


def test_a_refusal_outranks_help():
    """An operator who mistyped needs to be told the command did not run.
    Answering with a help page hides the one fact that matters."""
    args = parse_launcher_args(["--help", "--bogus-flag"])
    assert args.exit_code == EXIT_BAD_ARGUMENT
    assert args.is_refusal is True


def test_a_near_miss_is_never_silently_accepted():
    """A launcher that guesses will one day guess wrong on the flag that decides
    whether a desktop window opens."""
    args = parse_launcher_args(["--server_only"])
    assert args.server_only is False
    assert args.should_start is False


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_exits_zero_and_lists_every_flag(flag):
    args = parse_launcher_args([flag])
    assert args.exit_code == 0
    assert args.is_refusal is False
    text = "\n".join(args.lines)
    for name in KNOWN_FLAGS:
        assert name in text, f"--help does not mention {name}"


def test_help_gives_each_flag_its_own_line():
    lines = help_lines()
    for name, _description in FLAGS:
        owning = [ln for ln in lines if ln.strip().startswith(name + " ")
                  or ln.strip() == name]
        assert len(owning) == 1, f"{name} does not have exactly one line of its own"


def test_the_flag_table_is_the_only_source_of_truth():
    """Parsed, suggested and documented all read FLAGS, so they cannot drift.
    A flag added to the parser but not to --help is the exact gap that made the
    correct spelling undiscoverable in the first place."""
    for name in KNOWN_FLAGS:
        assert parse_launcher_args([name]).exit_code != EXIT_BAD_ARGUMENT, \
            f"{name} is advertised by --help but the parser refuses it"


# ---------------------------------------------------------------- cp949
def _cp949_or_fail(lines):
    for line in lines:
        try:
            line.encode("cp949")
        except UnicodeEncodeError as e:
            pytest.fail(
                f"character {e.object[e.start:e.end]!r} "
                f"(U+{ord(e.object[e.start]):04X}) cannot be printed on the "
                f"production console, so this line is DROPPED there: {line[:120]!r}")


def test_the_refusal_and_the_help_survive_the_production_console():
    """The production console is cp949 (`run_app.bat` sets no PYTHONIOENCODING)
    and one character outside it makes the logging handler raise and DROP the
    line. Dropping THIS line leaves an operator staring at a silent console
    during exactly the moment the message exists to end."""
    _cp949_or_fail(help_lines())
    _cp949_or_fail(parse_launcher_args(["--server_only"]).lines)
    _cp949_or_fail(parse_launcher_args(["--verbose"]).lines)
    _cp949_or_fail(la.refusal_lines([("--x", None), ("--y", "--reload")]))


# ===========================================================================
# (2) End to end through the real launcher - with a tripwire on Popen.
# ===========================================================================

# Replaces subprocess.Popen in the launcher process. Records the attempt (and
# which children the supervisor had planned - the supervisor is the `self` of
# the frame that calls Popen) and then kills the process before CreateProcess.
# So a spawn attempt is observable, and a spawn never occurs.
_TRIPWIRE = '''\
import os
import subprocess
import sys

_MARKER = os.environ["ASSY_SPAWN_MARKER"]


class _Tripwire(subprocess.Popen):
    def __init__(self, args, *a, **kw):
        lines = ["SPAWN ATTEMPT: " + repr(args)]
        try:
            sup = sys._getframe(1).f_locals.get("self")
            names = [c.spec.name for c in getattr(sup, "children", [])]
            lines.append("PLANNED CHILDREN: " + " | ".join(names))
        except Exception as e:
            lines.append("PLANNED CHILDREN: unreadable (%s)" % e)
        with open(_MARKER, "a", encoding="utf-8") as fh:
            fh.write("\\n".join(lines) + "\\n")
            fh.flush()
            os.fsync(fh.fileno())
        os._exit(97)


subprocess.Popen = _Tripwire
'''

SPAWN_TRIPPED_EXIT = 97


def _run_launcher(tmp_path, argv, api_port=None):
    """Run the real launcher with the tripwire armed and (by default) free ports.

    Free ports on purpose: the port guard must NOT be the thing that stops a bad
    command line, or the test would pass for the wrong reason. Pass ``api_port``
    to hold one deliberately.

    -> (returncode, console_text, spawn_records, launcher_log_text)
    """
    spy_dir = tmp_path / "spy"
    spy_dir.mkdir()
    (spy_dir / "sitecustomize.py").write_text(_TRIPWIRE, encoding="utf-8")
    marker = tmp_path / "spawn_attempts.txt"

    env = dict(os.environ)
    env["ASSY_DATA_ROOT"] = str(tmp_path)
    env["ASSY_API_PORT"] = str(api_port if api_port is not None else free_port())
    env["ASSY_API_HOST"] = "127.0.0.1"
    env["GRAPH_SYNC_PORT"] = str(free_port())
    env["PYTHONIOENCODING"] = "utf-8"
    env["ASSY_SPAWN_MARKER"] = str(marker)
    env["PYTHONPATH"] = str(spy_dir) + os.pathsep + env.get("PYTHONPATH", "")

    res = subprocess.run([sys.executable, LAUNCHER] + argv,
                         cwd=ROOT, env=env, capture_output=True, timeout=180)
    console = (res.stdout + res.stderr).decode("utf-8", "replace")
    records = (marker.read_text(encoding="utf-8") if marker.exists() else "")
    log = tmp_path / "launcher.log"
    return (res.returncode, console, records,
            log.read_text(encoding="utf-8", errors="replace") if log.exists() else "")


def test_a_valid_command_line_does_trip_the_tripwire(tmp_path):
    """POSITIVE CONTROL, and it must come first.

    Without it, every "no spawn was attempted" assertion below would also pass
    if the tripwire silently failed to install - which is the difference between
    evidence and a green light. The process still never starts: the tripwire
    fires inside Popen.__init__, before CreateProcess.
    """
    code, console, records, _log = _run_launcher(tmp_path, ["--server-only"])
    assert code == SPAWN_TRIPPED_EXIT, \
        f"the tripwire did not fire on a valid command line:\n{console}"
    assert "SPAWN ATTEMPT" in records
    assert "uvicorn" in records, "the recorded spawn is not the backend server"
    assert "Desktop Client UI" not in records, \
        "--server-only planned the desktop client"


def test_no_flags_plans_the_desktop_client(tmp_path):
    """The other half of the incident, measured rather than asserted about: the
    difference between `--server-only` and a full start is one child, and that
    child is the window the operator saw open."""
    code, console, records, _log = _run_launcher(tmp_path, [])
    assert code == SPAWN_TRIPPED_EXIT, console
    assert "Desktop Client UI" in records, \
        "a no-flag start no longer plans the desktop client"


def test_reload_still_reaches_the_uvicorn_command_line(tmp_path):
    """`--reload` is proved where it lands - in the argv of the child that would
    have been spawned - not by reading a boolean back out of the parser."""
    code, console, records, _log = _run_launcher(tmp_path, ["--server-only", "--reload"])
    assert code == SPAWN_TRIPPED_EXIT, console
    assert "'--reload'" in records, f"--reload did not reach uvicorn:\n{records}"


@pytest.mark.parametrize("typo,expected", [
    ("--server_only", "--server-only"),
    ("--serveronly", "--server-only"),
    ("--preflight-onlyy", "--preflight-only"),
])
def test_an_unknown_argument_refuses_and_spawns_nothing(tmp_path, typo, expected):
    """The whole fix, end to end: non-zero exit, the argument named, the closest
    valid flag offered, and - observed, not assumed - no spawn attempted."""
    code, console, records, log = _run_launcher(tmp_path, [typo])

    assert records == "", \
        f"a refused command line still tried to spawn a child:\n{records}"
    assert code not in (0, SPAWN_TRIPPED_EXIT), \
        f"a refused command line did not exit non-zero (code {code}):\n{console}"
    assert code == EXIT_BAD_ARGUMENT
    assert typo in console, "the refusal does not name the argument"
    assert expected in console, "the refusal does not suggest the right flag"
    assert "기동을 중단합니다" in console
    assert "REFUSING TO START" in console
    # The banner must not appear first. "Starting AssyManager" followed by a
    # refusal is the contradiction that makes an operator stop and reread.
    assert "Starting AssyManager" not in console
    # On the record, not only on a console someone scrolled past.
    assert typo in log, "the refusal never reached launcher.log"


def test_the_refusal_is_not_the_port_guard_in_disguise(tmp_path):
    """Both ports are free in _run_launcher, so the only thing that can refuse a
    mistyped flag is the argument parser. Without this, a port guard that
    happened to fire would make the test above pass for the wrong reason."""
    code, console, _records, _log = _run_launcher(tmp_path, [])
    assert code == SPAWN_TRIPPED_EXIT, \
        f"the ports were not free, so the refusal test proves nothing:\n{console}"
    assert "REFUSING TO START" not in console


def test_a_bad_argument_is_refused_even_when_the_ports_are_busy(tmp_path):
    """The ordering guarantee, made observable.

    Both failures are live at once - a mistyped flag AND an occupied port -
    which is exactly the situation the incident happened in. The operator must
    be told about the thing they can fix by retyping, not sent to hunt a PID for
    a command that was never going to run. A throwaway port is held here; :8080
    belongs to the running production stack and is never touched.
    """
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        held = srv.getsockname()[1]
        code, console, records, _log = _run_launcher(
            tmp_path, ["--server_only"], api_port=held)
    finally:
        srv.close()

    assert records == "", "a refused command line still tried to spawn a child"
    assert code == EXIT_BAD_ARGUMENT, \
        f"the port guard answered a question about arguments (code {code}):\n{console}"
    assert "--server_only" in console and "--server-only" in console
    assert "필요한 포트를" not in console, \
        "the port refusal ran for a command line that was never going to run"


def test_help_through_the_real_launcher_exits_zero_and_starts_nothing(tmp_path):
    code, console, records, _log = _run_launcher(tmp_path, ["--help"])
    assert code == 0, f"--help did not exit zero:\n{console}"
    assert records == "", "--help spawned something"
    for name in KNOWN_FLAGS:
        assert name in console, f"--help does not list {name}"
    assert "Starting AssyManager" not in console


# ===========================================================================
# (3) Ordering, at the source level.
# ===========================================================================

def test_the_argument_gate_runs_before_the_port_probe_and_before_any_spawn():
    """Ordering is half the fix. There is no point asking about ports for a
    command that will not run, and a banner printed ahead of a refusal is the
    contradiction this launcher already learned to avoid once."""
    src = open(LAUNCHER, encoding="utf-8").read()
    # CALL sites, not definitions. `refuse_if_ports_are_taken(api_host` also
    # matches the `def` line near the top of the file, which sorts before
    # everything and would make this test pass no matter where the call moved.
    parse = src.index("refuse_if_arguments_are_unknown(sys.argv[1:])")
    ports = src.index("ports_clear = refuse_if_ports_are_taken(")
    banner = src.index('" Starting AssyManager')
    spawn = src.index("supervisor.start_all()")
    assert parse < ports, "the port probe runs before the command line is understood"
    assert ports < banner, "the start banner is printed before the port guard"
    assert banner < spawn


def test_the_launcher_no_longer_parses_flags_by_membership():
    """The defect itself, pinned. `"--flag" in sys.argv` is what made an
    unrecognised argument a no-op instead of an error."""
    src = open(LAUNCHER, encoding="utf-8").read()
    for flag in ("--no-client", "--server-only", "--reload", "--preflight-only"):
        assert f'"{flag}" in sys.argv' not in src, \
            f"{flag} is parsed by membership again; unknown arguments are silent"
