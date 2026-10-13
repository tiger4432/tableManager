"""The run's process and its slices (총괄 fd550df13 ㄱ · 0cd396d3d) - `_run_slices` over stand-in slice processes that
speak the slice's protocol (its range on stdin, `{"rows"}` / `{"result"}` lines on stdout, relayed lines on stderr).

  sum      the run's count is the slices' sum, its page line says their state; each slice's end is said
  relay    a slice's lines land in this process's log under the logger that wrote them, after «[slice k/N pid P]»
  death    a slice that ends without its answer lets the others go (stdin closed - a held one answers «stopped») and
           the run fails naming what each left
  spawn    a slice that cannot start leaves no slice before it holding on
"""
import json
import logging
import subprocess
import sys
import time

import pytest

from admin import retroactive

CHILD = r'''
import json, sys
how = sys.argv[1]
key_range = json.loads(sys.stdin.readline())
def say(d):
    sys.stdout.write(json.dumps(d) + "\n")
    sys.stdout.flush()
say({"rows": 3})
sys.stderr.write("INFO\tRetroactive_slice\tread %s\n" % json.dumps(key_range))
sys.stderr.flush()
if how == "die":
    sys.stderr.write("ERROR\tRetroactive_slice\tboom\nTraceback line\n")
    sys.stderr.flush()
    sys.exit(1)
if how == "held":
    for _ in sys.stdin:
        pass
    say({"result": {"rows_in_scope": 3, "stopped": True, "refused": {}}})
    sys.exit(0)
say({"rows": 6})
say({"result": {"rows_in_scope": 6, "inserted": 6, "refused": {"no key": 1}, "source": "s"}})
'''
BOUNDS = [(None, "a"), ("a", "b"), ("b", None)]


def _children(monkeypatch, hows, started=None):
    def spawn(run_id, index, count):
        if hows[index - 1] == "unstartable":
            raise OSError("no such interpreter")
        proc = subprocess.Popen([sys.executable, "-c", CHILD, hows[index - 1]], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                bufsize=1)
        if started is not None:
            started.append(proc)
        return proc
    monkeypatch.setattr(retroactive, "_spawn_slice", spawn)


def _control(lines):
    return retroactive.RunControl(None, op="ledger_rescope", log=lines.append)


def test_the_run_writes_its_count_at_most_a_beat_apart_and_when_a_slice_ends(monkeypatch):
    """A slice page is not a run-row write and a line of the run's: with the beat longer than the run, the count is
    written once a slice ends - three here - and never between."""
    _children(monkeypatch, ["done", "done", "done"])
    monkeypatch.setattr(retroactive, "BEAT_SECONDS", 3600)
    counted = []
    control = _control([])
    monkeypatch.setattr(control, "progress", lambda processed, total, note=None: counted.append(processed))
    retroactive._run_slices(control, BOUNDS, 18)
    assert len(counted) == 3 and counted[-1] == 18, counted


def test_the_count_is_the_slices_sum_and_each_end_is_said(monkeypatch, caplog):
    _children(monkeypatch, ["done", "done", "done"])
    monkeypatch.setattr(retroactive, "BEAT_SECONDS", 0)                  # every answer counted
    lines = []
    control = _control(lines)
    with caplog.at_level(logging.INFO):
        answers = retroactive._run_slices(control, BOUNDS, 18)
    assert [answer["rows_in_scope"] for answer in answers] == [6, 6, 6]
    assert retroactive._summed(answers)["refused"] == {"no key": 3}
    assert control._said == 18
    pages = [line for line in lines if line.startswith("[ledger_rescope] page ")]
    assert pages and all(" / 18 · " in line and " · slices 3: " in line for line in pages), pages
    assert any("slices 3: 3 working" in line for line in pages), pages
    assert sorted(line for line in lines if " done: " in line) == [
        "[ledger_rescope] slice %d/3 done: 6 rows" % k for k in (1, 2, 3)]
    relayed = [r for r in caplog.records if r.name == "Retroactive_slice" and "read " in r.getMessage()]
    assert sorted((json.loads(r.getMessage().split("read ", 1)[1]) for r in relayed), key=str) == sorted(
        [list(b) for b in BOUNDS], key=str)
    assert all(r.getMessage().startswith("[slice ") and " pid " in r.getMessage() for r in relayed)


def test_a_slice_that_dies_lets_the_others_go_and_the_run_fails_naming_each(monkeypatch, caplog):
    _children(monkeypatch, ["done", "die", "held"])
    lines = []
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError) as raised:
        retroactive._run_slices(_control(lines), BOUNDS, 18)
    said = str(raised.value)
    assert said.startswith("slice 2/3 ended without its answer"), said
    assert "1/3 6 rows done · 2/3 3 rows failed · 3/3 3 rows stopped" in said, said
    assert any(line.startswith("[ledger_rescope] slice 2/3 failed: 3 rows - exit code 1 without its answer")
               for line in lines), lines
    errors = [r.getMessage() for r in caplog.records if r.name == "Retroactive_slice" and r.levelno == logging.ERROR]
    assert any(m.startswith("[slice 2/3 pid ") and m.endswith(" boom") for m in errors), errors
    assert any(m.endswith(" Traceback line") for m in errors), errors


def test_a_slice_that_cannot_start_leaves_none_before_it_holding_on(monkeypatch):
    started = []
    _children(monkeypatch, ["held", "unstartable", "done"], started)
    with pytest.raises(OSError):
        retroactive._run_slices(_control([]), BOUNDS, 18)
    deadline = time.monotonic() + 10
    while started[0].poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert [proc.poll() for proc in started] == [0]


@pytest.mark.parametrize("cells, read, said", [
    ({}, 4, False),                                         # absent: half the cores, 4 at most
    ({"ledger_translate_slices": 2}, 2, False),
    ({"ledger_translate_slices": 16}, 16, False),           # up to the cores
    ({"ledger_translate_slices": 17}, 4, True),
    ({"ledger_translate_slices": 0}, 4, True),
    ({"ledger_translate_slices": -2}, 4, True),
    ({"ledger_translate_slices": "8"}, 4, True),
    ({"ledger_translate_slices": True}, 4, True),
])
def test_the_slices_setting_is_a_whole_number_from_one_to_the_cores(monkeypatch, caplog, cells, read, said):
    """lead 9752e91f7: 64 was 64 processes and 0 · -2 · '8' read as the default unsaid - now one line says it."""
    monkeypatch.setattr(retroactive.os, "cpu_count", lambda: 16)
    monkeypatch.setattr(retroactive, "_REFUSED_SETTINGS", set())
    with caplog.at_level(logging.WARNING):
        assert retroactive.translate_slices(cells) == (read, 16)
        retroactive.translate_slices(cells)
    lines = [r.getMessage() for r in caplog.records if "ledger_translate_slices" in r.getMessage()]
    assert len(lines) == (1 if said else 0), lines                   # once, however often it is read
