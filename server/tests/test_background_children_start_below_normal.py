# -*- coding: utf-8 -*-
"""Owner 11-10 «c100을 고쳐야지» → «1 ㄴ» (lead): at «STALL 397s … C100 api:17» the background work had queued the
reads - every child ran at the same priority. The roster says which children start below normal (one ChildSpec
cell); the supervisor gives the flag on all three ways it starts a child; a below-normal child's own children follow
it; one line per child at start."""
import os
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from runtime import process_supervisor as ps  # noqa: E402
from runtime.launcher_specs import child_specs  # noqa: E402

windows = pytest.mark.skipif(os.name != "nt", reason="the priority class is Windows'")

#: Every child the launcher starts, and its priority - no blank cell (lead 11-10 table).
ROSTER = {
    "Backend FastAPI Server": ps.PRIORITY_NORMAL,
    "File Ingestion Watcher": ps.PRIORITY_BELOW_NORMAL,
    "Chained Ingestion Worker": ps.PRIORITY_BELOW_NORMAL,
    "Ledger Worker": ps.PRIORITY_BELOW_NORMAL,
    "Auto Update Scheduler": ps.PRIORITY_BELOW_NORMAL,
}


def test_the_roster_says_each_childs_priority_and_none_is_blank():
    specs = child_specs(sys.executable, "server", ["uvicorn"], "127.0.0.1", "8080")
    assert {spec.name: spec.priority for spec in specs} == ROSTER


def test_a_priority_the_supervisor_cannot_give_is_refused_at_the_roster():
    with pytest.raises(ValueError, match="priority 'idle' is not one of normal, below normal"):
        ps.ChildSpec("x", ["x"], ".", priority="idle")


def _sleeper(tmp_path, grandchild=False):
    """A command that sleeps - or starts a sleeping child and writes its pid, then sleeps."""
    body = ("import subprocess, sys, time\n"
            "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "open(sys.argv[1], 'w').write(str(c.pid))\n"
            "time.sleep(30)\n") if grandchild else "import time; time.sleep(30)\n"
    script = tmp_path / ("g.py" if grandchild else "s.py")
    script.write_text(body)
    return [sys.executable, str(script)] + ([str(tmp_path / "pid.txt")] if grandchild else [])


def _python_under(proc):
    """The python process a spawn started - itself, or (the own-window way) the one under cmd."""
    import psutil
    root = psutil.Process(proc.pid)
    for _ in range(100):
        found = [p for p in [root, *root.children(recursive=True)] if "python" in p.name().lower()]
        if found:
            return found[0]
        time.sleep(0.1)
    raise AssertionError("no python under the spawn")


@windows
@pytest.mark.parametrize("way", ["no log file", "log file", "own window"])
@pytest.mark.parametrize("priority", [ps.PRIORITY_NORMAL, ps.PRIORITY_BELOW_NORMAL])
def test_each_way_the_supervisor_starts_a_child_gives_its_priority(tmp_path, way, priority):
    import psutil
    want = psutil.BELOW_NORMAL_PRIORITY_CLASS if priority == ps.PRIORITY_BELOW_NORMAL else psutil.NORMAL_PRIORITY_CLASS
    spec = ps.ChildSpec("probe", _sleeper(tmp_path), str(tmp_path), priority=priority,
                        log_file=str(tmp_path / "out.log") if way == "log file" else None)
    sup = ps.Supervisor([spec], status_file=str(tmp_path / "status.json"), log=lambda *a, **k: None)
    sup.own_window = way == "own window"
    proc = sup._default_spawn(spec)
    try:
        assert _python_under(proc).nice() == want
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


@windows
def test_a_below_normal_childs_own_children_start_below_normal(tmp_path):
    """The chain's slots and the scheduler's retroactive runs are started by a below-normal worker with no priority
    flag of their own - Windows gives them the parent's class."""
    import psutil
    spec = ps.ChildSpec("probe", _sleeper(tmp_path, grandchild=True), str(tmp_path),
                        priority=ps.PRIORITY_BELOW_NORMAL)
    sup = ps.Supervisor([spec], status_file=str(tmp_path / "status.json"), log=lambda *a, **k: None)
    proc = sup._default_spawn(spec)
    try:
        for _ in range(100):
            if (tmp_path / "pid.txt").exists() and (tmp_path / "pid.txt").read_text():
                break
            time.sleep(0.1)
        assert psutil.Process(int((tmp_path / "pid.txt").read_text())).nice() == psutil.BELOW_NORMAL_PRIORITY_CLASS
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def test_each_child_says_its_priority_when_it_starts(tmp_path):
    said = []

    class Proc:
        pid = 1

        def poll(self):
            return None
    specs = [ps.ChildSpec("A", ["a"], ".", priority=ps.PRIORITY_BELOW_NORMAL), ps.ChildSpec("B", ["b"], ".")]
    sup = ps.Supervisor(specs, status_file=str(tmp_path / "status.json"),
                        log=lambda msg, level="INFO": said.append(msg), spawn=lambda spec: Proc())
    for child in sup.children:
        sup._start(child)
    tail = "" if os.name == "nt" else " (not set: not Windows)"
    assert [line for line in said if line.startswith("Priority of ")] == [
        "Priority of A: below normal" + tail, "Priority of B: normal" + tail]
