# -*- coding: utf-8 -*-
"""A collector that declares `# window:` can be backfilled from a start day to now, one
24-hour window at a time (소유자 2026-09-26 「목표 기간까지 1 일 단위로 자동 소급」 · 「24h 씩,
마지막은 지금에서 자름」 · 총괄 ffd5d42b7 ㄴ 「실패한 날에서 멈춤, 그 날부터 재시작」).

🔴 A DAY IS DONE WHEN ITS FILE HAS PASSED THE INGESTION QUEUE, asked of the file checkpoint
ledger by the path and stat the collector wrote - so the days never pile into the queue at
once, and a day whose file FAILED stops the run and names the day.
"""
import csv
import io
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import collector_markers as cm                                             # noqa: E402
import paths                                                               # noqa: E402
from admin import retroactive                                              # noqa: E402
from ingestion import checkpoint                                           # noqa: E402

TABLE = "backfill_probe_tbl"
KEY = "%s/probe.py" % TABLE
SCRIPT = ("# schedule: 0 * * * *\n# window: 1d\n"
          'out = [{"s": "{{WINDOW_START}}", "e": "{{WINDOW_END}}"}]\n')
KST = cm.WINDOW_ZONE


def at(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=KST)


class Control:
    """The run's control as the ending reads it: progress, a sticky stop, the stats."""

    def __init__(self, stop_after_days=None):
        self.progressed, self.stopped, self.stats = [], False, None
        self.stop_after_days = stop_after_days

    def progress(self, processed=None, total=None):
        self.progressed.append((processed, total))

    def stop_requested(self):
        if self.stop_after_days is not None and any(
                p and p >= self.stop_after_days for p, _t in self.progressed):
            self.stopped = True
        return self.stopped


@pytest.fixture(name="workspace")
def fixture_workspace(tmp_path, monkeypatch):
    folder = os.path.join(str(tmp_path), "ingestion_workspace", TABLE, "auto_update")
    os.makedirs(folder)
    with open(os.path.join(folder, "probe.py"), "w", encoding="utf-8") as f:
        f.write(SCRIPT)
    monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(retroactive, "BACKFILL_POLL_SECONDS", 0)
    return tmp_path


def ingests(monkeypatch, verdicts):
    """The watcher, as the ledger answers for it: the n-th file read gets verdicts[n]
    (DONE · FAILED · None = not yet). Returns the windows the files carried, in order."""
    seen, calls = [], []

    def door(db, table, filepath, file_stat):
        with open(filepath, encoding="utf-8") as f:
            row = next(csv.DictReader(io.StringIO(f.read())))
        if not seen or seen[-1] != (row["s"], row["e"]) or calls[-1] is not None:
            seen.append((row["s"], row["e"]))
        verdict = verdicts[len(seen) - 1] if len(seen) - 1 < len(verdicts) else checkpoint.STATUS_DONE
        calls.append(verdict)
        return None if verdict is None else SimpleNamespace(status=verdict)
    monkeypatch.setattr(checkpoint, "find_terminal_by_path_stat", door)
    return seen


DB = SimpleNamespace(rollback=lambda: None)


def _run(start, control):
    return retroactive._run_collector_backfill(DB, {"collector": KEY, "start": start},
                                               lambda m: None, control)


def _two_days_ago():
    return (datetime.now(KST) - timedelta(days=2)).strftime("%Y-%m-%d")


def test_the_windows_are_24_hours_end_to_end_and_the_last_is_cut_at_now():
    windows = cm.backfill_windows(at("2026-09-24 00:00"), now=at("2026-09-26 09:30"))
    assert [(s.strftime("%d %H:%M"), e.strftime("%d %H:%M")) for s, e in windows] == [
        ("24 00:00", "25 00:00"), ("25 00:00", "26 00:00"), ("26 00:00", "26 09:30")]


@pytest.mark.parametrize("text,expected", [("2026-09-24", "2026-09-24 00:00"),
                                           ("2026-09-24 13:30", "2026-09-24 13:30")])
def test_a_start_is_read_in_kst_and_a_date_is_its_midnight(text, expected):
    start = cm.backfill_start(text)
    assert start.strftime("%Y-%m-%d %H:%M") == expected and start.tzinfo == KST


@pytest.mark.parametrize("params,said", [
    ({"collector": "nope/none.py", "start": "2026-09-24"}, "no collector 'nope/none.py'"),
    ({"collector": KEY, "start": "yesterday"}, "start 'yesterday' is not a date"),
    ({"collector": KEY, "start": "2999-01-01"}, "start '2999-01-01' is not in the past"),
])
def test_the_judge_refuses_by_name(workspace, params, said):
    with pytest.raises(retroactive.RetroactiveRefused, match=said):
        retroactive._judge_collector_backfill(params)


def test_a_collector_with_no_window_is_refused(workspace):
    with open(os.path.join(str(workspace), "ingestion_workspace", TABLE, "auto_update",
                           "plain.py"), "w", encoding="utf-8") as f:
        f.write('# schedule: 0 * * * *\nout = [{"a": "1"}]\n')
    with pytest.raises(retroactive.RetroactiveRefused, match="declares no '# window:'"):
        retroactive._judge_collector_backfill({"collector": "%s/plain.py" % TABLE,
                                               "start": "2026-09-24"})


def test_every_day_runs_in_order_and_waits_for_its_file(workspace, monkeypatch):
    seen = ingests(monkeypatch, [])
    control = Control()
    start = _two_days_ago()
    expected = [(s.strftime("%Y-%m-%d %H:%M:%S"), e.strftime("%Y-%m-%d %H:%M:%S"))
                for s, e in cm.backfill_windows(cm.backfill_start(start))]

    stats = _run(start, control)

    assert seen == expected and len(expected) == 3
    assert stats == {"days": 3, "days_done": 3}
    assert not control.stopped


def test_a_failed_day_stops_the_run_and_names_the_day(workspace, monkeypatch):
    seen = ingests(monkeypatch, [checkpoint.STATUS_DONE, checkpoint.STATUS_FAILED])
    start = _two_days_ago()
    second = cm.backfill_windows(cm.backfill_start(start))[1][0].strftime("%Y-%m-%d %H:%M")

    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        _run(start, Control())

    assert "the file collected for %s (KST) failed to ingest" % second in str(refused.value)
    assert "start again from %s" % second in str(refused.value)
    assert len(seen) == 2, "the day after the failed one never ran"


def test_starting_again_from_the_failed_day_finishes_the_rest(workspace, monkeypatch):
    start = _two_days_ago()
    second = cm.backfill_windows(cm.backfill_start(start))[1][0].strftime("%Y-%m-%d %H:%M")
    seen = ingests(monkeypatch, [])

    stats = _run(second, Control())

    assert stats == {"days": 2, "days_done": 2}
    assert seen[0][0] == second + ":00"


def test_a_stop_lands_between_days(workspace, monkeypatch):
    seen = ingests(monkeypatch, [])
    control = Control(stop_after_days=1)

    stats = _run(_two_days_ago(), control)

    assert stats == {"days": 3, "days_done": 1}
    assert control.stopped and len(seen) == 1


def test_a_stop_while_a_file_waits_ends_without_counting_that_day(workspace, monkeypatch):
    ingests(monkeypatch, [None])
    control = Control()
    control.stopped = True                        # asked before the first file was read

    stats = _run(_two_days_ago(), control)

    assert stats == {"days": 3, "days_done": 0}


def test_the_result_line_reads_in_words_not_keys():
    """The run's result is drawn by `run_result_sentence` on the Retroactive list and the
    Overview (design c0feacccf: it printed `days 3 · days_done 3`)."""
    assert retroactive.run_result_sentence({"days": 3, "days_done": 2}) == (
        "days in the window 3 · days collected 2")


def test_the_count_is_the_number_of_days(workspace):
    got = retroactive._count_collector_backfill(None, {"collector": KEY, "start": _two_days_ago()},
                                                retroactive.DEFAULT_SCAN_LIMIT)
    assert (got["affected"], got["affected_label"], got["count_kind"]) == (
        3, "days to collect", retroactive.COUNT_EXACT)
