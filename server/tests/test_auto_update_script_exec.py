# -*- coding: utf-8 -*-
"""
Script-execution contract for GenericScriptRunnerCollector.

Background - the runner used to execute collector scripts via
`exec(code, globals, locals)` with TWO DISTINCT namespaces. Python then runs the
file with class-body scoping: module-level `def`/`import` bind into locals, but
function bodies resolve names via LOAD_GLOBAL and never see them. So

  * a helper function called from inside another function, and
  * a module-level import used inside a function

both died with NameError. That exception was swallowed as a single WARNING and
the runner fell through to the stdout fallback - but such scripts assign `out`
instead of printing, so stdout was empty, the runner logged
"Skipping file generation" and returned SUCCESS. Net result: zero rows, zero
errors, a run that looked fine.

WARNING for anyone extending these fixtures: calling a helper at MODULE level
(`out = build_rows()`) compiles to LOAD_NAME, which does consult locals, so it
does NOT reproduce the bug. That is why every fixture below calls its helper
from inside another function - that is the actual defect axis.
"""
import os
import sys
import json
import logging
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from run_auto_update import GenericScriptRunnerCollector, MultiDiscoveryScheduler  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TABLE = "autoupd_exec_tbl"
SCRIPT = "collector.py"


def _make_collector(tmp_path, body, table=TABLE, script=SCRIPT):
    """Plant a collector script in a tmp server dir and return the collector."""
    au_dir = os.path.join(str(tmp_path), "ingestion_workspace", table, "auto_update")
    os.makedirs(au_dir, exist_ok=True)
    script_path = os.path.join(au_dir, script)
    with open(script_path, "w", encoding="utf-8") as f:
        f.write("# schedule: * * * * *\n" + body)
    return GenericScriptRunnerCollector(
        table_name=table,
        script_path=script_path,
        cron_expression="* * * * *",
        filename_prefix="exec_probe",
        server_dir=str(tmp_path),
    )


def _written(collector):
    """Contents of whatever the collector actually dropped into raws/."""
    out = []
    for fn in sorted(os.listdir(collector.target_dir)):
        with open(os.path.join(collector.target_dir, fn), encoding="utf-8") as f:
            out.append(f.read())
    return out


# Helper called from INSIDE another function - this is the defect axis.
HELPER_FN_SCRIPT = '''
def build_rows():
    return [{"a": 1, "b": 2}]

def collect():
    return build_rows()

out = collect()
'''

# Module-level import used INSIDE a function - same defect, second form.
MODULE_IMPORT_SCRIPT = '''
import json

def collect():
    return json.loads('[{"a": 1, "b": 2}]')

out = collect()
'''

PRINT_ONLY_SCRIPT = '''
def rows():
    return [("1", "2")]

print("a,b")
for r in rows():
    print(",".join(r))
'''

# Raises under exec(), then exits 0 with no output when re-run as a subprocess.
# Makes the "execution failed AND the fallback came back empty" path deterministic.
TRANSIENT_FAILURE_SCRIPT = '''
import os
LOCK = os.path.join(os.path.dirname(__file__), "ran_once.lock")
if not os.path.exists(LOCK):
    with open(LOCK, "w") as f:
        f.write("x")
    raise RuntimeError("collector source system is down")
'''

# The shape real collectors use: catch the fetch error, report it, set out = None.
# Mirrors ingestion_workspace/bonding_map/auto_update/fetch_data.py:28-32.
# Counts its own executions so a stdout re-run (a second external API call) is visible.
OUT_NONE_SCRIPT = '''
import os, sys
COUNTER = os.path.join(os.path.dirname(__file__), "runs.count")
with open(COUNTER, "a") as f:
    f.write("x")
try:
    raise ConnectionError("upstream API unreachable")
except Exception as e:
    print(f"Error fetching web data inside script: {e}", file=sys.stderr)
    out = None
'''


def _run_count(collector):
    """How many times the script body actually executed (see OUT_NONE_SCRIPT)."""
    path = os.path.join(os.path.dirname(collector.script_path), "runs.count")
    if not os.path.exists(path):
        return 0
    with open(path) as f:
        return len(f.read())


# ---------------------------------------------------------------------------
# 1. Single namespace - helpers and module imports must actually work
#    (every test here fails against the split-namespace implementation)
# ---------------------------------------------------------------------------

class TestSingleNamespace:
    def test_helper_called_from_another_function_is_collected(self, tmp_path):
        collector = _make_collector(tmp_path, HELPER_FN_SCRIPT)
        collector.execute()
        assert _written(collector) == ["a,b\n1,2\n"]

    def test_module_level_import_used_inside_function(self, tmp_path):
        collector = _make_collector(tmp_path, MODULE_IMPORT_SCRIPT)
        collector.execute()
        assert _written(collector) == ["a,b\n1,2\n"]

    def test_helper_script_logs_no_name_resolution_failure(self, tmp_path, caplog):
        """
        A healthy script must not report a name-resolution failure at ANY level.
        The split-namespace build logged "name 'build_rows' is not defined" as a
        WARNING, so asserting only on ERROR would miss it - check the text too.
        """
        collector = _make_collector(tmp_path, HELPER_FN_SCRIPT)
        with caplog.at_level(logging.INFO):
            collector.execute()
        assert [r.message for r in caplog.records if r.levelno >= logging.ERROR] == []
        assert "is not defined" not in caplog.text

    def test_class_definition_with_methods(self, tmp_path):
        """A method reaching a module-level function is the same defect axis."""
        body = '''
def scale(v):
    return v * 10

class Collector:
    def run(self):
        return [{"a": scale(1)}]

out = Collector().run()
'''
        collector = _make_collector(tmp_path, body)
        collector.execute()
        assert _written(collector) == ["a\n10\n"]


# ---------------------------------------------------------------------------
# 2. Stdout fallback - print-based collectors (no 'out') must keep working
# ---------------------------------------------------------------------------

class TestStdoutFallback:
    def test_print_only_collector_still_works(self, tmp_path):
        collector = _make_collector(tmp_path, PRINT_ONLY_SCRIPT)
        collector.execute()
        assert _written(collector) == ["a,b\n1,2\n"]

    def test_absent_out_is_not_reported_as_an_error(self, tmp_path, caplog):
        """An absent 'out' is normal and must not be logged as a failure."""
        collector = _make_collector(tmp_path, PRINT_ONLY_SCRIPT)
        with caplog.at_level(logging.INFO):
            collector.execute()
        assert [r.message for r in caplog.records if r.levelno >= logging.ERROR] == []
        assert "stdout collector" in caplog.text

    def test_silent_script_with_no_out_and_no_stdout_is_not_a_failure(self, tmp_path):
        """A normal cycle that simply had nothing to collect: quiet, no raise."""
        collector = _make_collector(tmp_path, "pass\n")
        collector.execute()
        assert _written(collector) == []


# ---------------------------------------------------------------------------
# 3. Failures must be loud - no silent success
# ---------------------------------------------------------------------------

class TestFailuresAreLoud:
    def test_exec_failure_and_empty_fallback_raises(self, tmp_path):
        """
        Script raised AND the stdout fallback captured nothing -> the run FAILS.
        (The old build logged "Skipping file generation" and returned SUCCESS.)
        """
        collector = _make_collector(tmp_path, TRANSIENT_FAILURE_SCRIPT)
        with pytest.raises(RuntimeError) as exc:
            collector.execute()
        # Root cause must ride along so admin's last_error is diagnostic.
        assert "collector source system is down" in str(exc.value)
        assert _written(collector) == []

    def test_exec_failure_is_logged_at_error_with_traceback(self, tmp_path, caplog):
        """An execution failure must be ERROR + traceback, not a WARNING."""
        collector = _make_collector(tmp_path, TRANSIENT_FAILURE_SCRIPT)
        with caplog.at_level(logging.INFO):
            with pytest.raises(RuntimeError):
                collector.execute()
        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors, "in-memory execution failure was not logged at ERROR"
        joined = "\n".join(r.message for r in errors)
        assert "Traceback" in joined and "collector source system is down" in joined

    def test_hard_broken_script_still_raises(self, tmp_path):
        """Both executions fail - regression guard on the pre-existing behaviour."""
        collector = _make_collector(tmp_path, 'raise ValueError("boom")\n')
        with pytest.raises(RuntimeError):
            collector.execute()
        assert _written(collector) == []

    def test_failure_surfaces_as_FAIL_status(self, tmp_path):
        """Scheduler integration: the failure reaches admin via status/last_error."""
        collector = _make_collector(tmp_path, TRANSIENT_FAILURE_SCRIPT)
        scheduler = MultiDiscoveryScheduler(check_interval=1, server_dir=str(tmp_path))
        scheduler.collectors = [collector]

        scheduler.execute_collector(collector)

        assert collector.last_status == "FAIL"
        assert "collector source system is down" in (collector.last_error or "")

        with open(scheduler.status_file_path, encoding="utf-8") as f:
            status = json.load(f)
        assert status["collectors"][0]["last_status"] == "FAIL"

    @pytest.mark.parametrize("body", ["out = []\n", 'out = ""\n'])
    def test_empty_out_is_not_a_failure(self, tmp_path, body):
        """
        Collecting zero rows is normal and stays SUCCESS - this is the sanctioned
        way to say "nothing this cycle" now that `out = None` fails.
        """
        collector = _make_collector(tmp_path, body)
        collector.execute()
        assert _written(collector) == []


class TestOutAssignedNone:
    """
    `out = None` is a DECLARED failure, distinct from `out` never being defined.
    `script_ns.get("out")` cannot tell them apart, so the runner used to treat a
    failed collector as a stdout collector: it re-ran the whole script as a
    subprocess (a second external API call), got empty stdout, logged
    "Skipping file generation" and finished SUCCESS with last_error = None.
    """

    def test_out_none_is_a_failure(self, tmp_path):
        collector = _make_collector(tmp_path, OUT_NONE_SCRIPT)
        with pytest.raises(RuntimeError) as exc:
            collector.execute()
        assert "out = None" in str(exc.value)
        assert _written(collector) == []

    def test_out_none_does_not_re_run_the_script(self, tmp_path):
        """No stdout fallback: the external call must not be repeated."""
        collector = _make_collector(tmp_path, OUT_NONE_SCRIPT)
        with pytest.raises(RuntimeError):
            collector.execute()
        assert _run_count(collector) == 1, "script re-ran; the fallback repeated the API call"

    def test_out_none_surfaces_as_FAIL_status(self, tmp_path):
        collector = _make_collector(tmp_path, OUT_NONE_SCRIPT)
        scheduler = MultiDiscoveryScheduler(check_interval=1, server_dir=str(tmp_path))
        scheduler.collectors = [collector]

        scheduler.execute_collector(collector)

        assert collector.last_status == "FAIL"
        assert "out = None" in (collector.last_error or "")

    def test_out_none_is_logged_at_error(self, tmp_path, caplog):
        collector = _make_collector(tmp_path, OUT_NONE_SCRIPT)
        with caplog.at_level(logging.INFO):
            with pytest.raises(RuntimeError):
                collector.execute()
        assert [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert "Skipping file generation" not in caplog.text

    def test_out_none_after_sys_exit_zero_also_fails(self, tmp_path):
        collector = _make_collector(tmp_path, "out = None\nimport sys\nsys.exit(0)\n")
        with pytest.raises(RuntimeError):
            collector.execute()


class TestOutFormattingFailure:
    """
    A valid 'out' whose CSV formatting blows up is a FAIL with no stdout fallback.
    This is a deliberate behaviour change: pre-fix the formatting error fell
    through to the subprocess, so a hybrid collector that both print()s its rows
    and sets `out = df` still produced a CSV. It no longer does - a loud failure
    is preferred over a silent divergence between the two outputs.
    """

    def test_unformattable_out_fails_and_does_not_fall_back(self, tmp_path):
        body = '''
class Bad:
    def to_csv(self, index=False):
        raise ValueError("mixed dtype column")

print("a,b")
print("1,2")
out = Bad()
'''
        collector = _make_collector(tmp_path, body)
        with pytest.raises(ValueError, match="mixed dtype column"):
            collector.execute()
        # The stdout copy is deliberately NOT used as a consolation prize.
        assert _written(collector) == []


# ---------------------------------------------------------------------------
# 4. sys.exit() containment - a user script must not kill the scheduler daemon
# ---------------------------------------------------------------------------

class TestSystemExitContainment:
    def test_sys_exit_zero_keeps_out_and_does_not_propagate(self, tmp_path):
        body = '''
def collect():
    return [{"a": 1, "b": 2}]

out = collect()
import sys
sys.exit(0)
'''
        collector = _make_collector(tmp_path, body)
        collector.execute()  # a leaking SystemExit kills the test right here
        assert _written(collector) == ["a,b\n1,2\n"]

    def test_sys_exit_zero_does_not_kill_the_scheduler_tick(self, tmp_path):
        """
        SystemExit is a BaseException, not an Exception, so it passes through the
        `except Exception` in both execute_collector() and
        check_and_run_schedules() and terminates the scheduler's run() loop -
        i.e. the whole daemon.
        """
        collector = _make_collector(tmp_path, 'out = [{"a": 1}]\nimport sys\nsys.exit(0)\n')
        scheduler = MultiDiscoveryScheduler(check_interval=1, server_dir=str(tmp_path))
        scheduler.collectors = [collector]

        now = datetime.now()
        collector.next_run = now - timedelta(seconds=1)
        scheduler.check_and_run_schedules(now=now)  # daemon death ends the test here

        assert collector.last_status == "SUCCESS"
        assert _written(collector) == ["a\n1\n"]

    def test_nonzero_sys_exit_is_an_error(self, tmp_path):
        collector = _make_collector(tmp_path, "import sys\nsys.exit(3)\n")
        with pytest.raises(RuntimeError):
            collector.execute()
