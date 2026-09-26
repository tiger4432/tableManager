# -*- coding: utf-8 -*-
"""A collector script says `# window: 1d` and writes {{WINDOW_START}} · {{WINDOW_END}}; each
run fills them with the window it covers (소유자 2026-09-26: markers as proposed, the usual
window is the last 24 hours, KST).

🔴 TWO PATHS RUN A SCRIPT, AND BOTH MUST SEE THE FILLED TEXT. The runner execs the script's
text in process, and when the script sets no `out` it runs the FILE again as a child for its
stdout. Filling only the first would hand the child the raw markers. The original file is
never written - the child runs a filled copy beside it that discovery does not register.
"""
import csv
import hashlib
import io
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import run_auto_update as rau                                              # noqa: E402

TABLE = "window_probe_tbl"
HEADER = "# schedule: * * * * *\n# window: 1d\n# window_format: %Y-%m-%d %H:%M:%S\n"
EXEC_BODY = 'out = [{"start": "{{WINDOW_START}}", "end": "{{WINDOW_END}}"}]\n'
STDOUT_BODY = 'print("start,end")\nprint("{{WINDOW_START}},{{WINDOW_END}}")\n'
#: 2026-09-26 00:30 UTC is 09:30 KST - the window's two ends, as the script will read them
NOW = datetime(2026, 9, 26, 0, 30, tzinfo=timezone.utc)
FILLED = {"start": "2026-09-25 09:30:00", "end": "2026-09-26 09:30:00"}


def _plant(tmp_path, body, header=HEADER, name="probe.py"):
    au_dir = os.path.join(str(tmp_path), "ingestion_workspace", TABLE, "auto_update")
    os.makedirs(au_dir, exist_ok=True)
    path = os.path.join(au_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + body)
    return path


def _collector(tmp_path, path):
    head = rau.parse_script_comments(path)
    return rau.GenericScriptRunnerCollector(
        table_name=TABLE, script_path=path, cron_expression="* * * * *",
        filename_prefix="window_probe", server_dir=str(tmp_path),
        window=head["window"], window_format=head["window_format"])


def _rows(collector):
    files = sorted(os.listdir(collector.target_dir))
    assert len(files) == 1, files
    with open(os.path.join(collector.target_dir, files[0]), encoding="utf-8") as f:
        return list(csv.DictReader(io.StringIO(f.read())))


def _md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def test_the_header_is_read_with_the_colons_of_its_format(tmp_path):
    head = rau.parse_script_comments(_plant(tmp_path, EXEC_BODY))
    assert head["window"] == "1d"
    assert head["window_format"] == "%Y-%m-%d %H:%M:%S"


def test_the_usual_window_is_the_last_day_ending_now_in_kst():
    start, end = rau.usual_window(rau.window_length("1d"), now=NOW)
    assert (start.strftime(rau.DEFAULT_WINDOW_FORMAT),
            end.strftime(rau.DEFAULT_WINDOW_FORMAT)) == (FILLED["start"], FILLED["end"])
    assert end - start == timedelta(hours=24)
    # ⚠️ this box's own clock is KST, so the strings alone cannot tell KST from 「the box's
    #    zone」 - the zone the window carries is what says which one was asked
    assert end.tzinfo == rau.WINDOW_ZONE


@pytest.mark.parametrize("declared,length", [("1d", timedelta(days=1)),
                                              ("12h", timedelta(hours=12))])
def test_a_window_is_days_or_hours(declared, length):
    assert rau.window_length(declared) == length


@pytest.mark.parametrize("declared", ["1w", "0d", "", "day"])
def test_any_other_window_is_refused_by_name(declared):
    with pytest.raises(ValueError, match="is not a length"):
        rau.window_length(declared)


@pytest.mark.parametrize("body", [EXEC_BODY, STDOUT_BODY], ids=["exec path", "stdout path"])
def test_both_run_paths_see_the_filled_window_and_the_original_stays(tmp_path, body):
    path = _plant(tmp_path, body)
    before = _md5(path)
    collector = _collector(tmp_path, path)
    collector.run_window = rau.usual_window(rau.window_length("1d"), now=NOW)

    collector.execute()

    assert _rows(collector) == [FILLED]
    assert _md5(path) == before, "the original script is never written"
    assert sorted(os.listdir(os.path.dirname(path))) == ["probe.py"], "no copy is left behind"


def test_a_filled_copy_left_beside_the_script_is_not_a_collector(tmp_path):
    path = _plant(tmp_path, STDOUT_BODY)
    with open(rau.filled_copy_path(path), "w", encoding="utf-8") as f:
        f.write(HEADER + STDOUT_BODY)   # a real copy carries the whole script, header too
    scheduler = rau.MultiDiscoveryScheduler(server_dir=str(tmp_path))

    scheduler.discover_and_load_collectors()

    assert [c.script_path for c in scheduler.collectors] == [path]


def test_a_scheduled_run_fills_the_last_24_hours(tmp_path):
    path = _plant(tmp_path, EXEC_BODY)
    scheduler = rau.MultiDiscoveryScheduler(server_dir=str(tmp_path))
    scheduler.discover_and_load_collectors()
    [collector] = scheduler.collectors

    scheduler.execute_collector(collector)

    assert collector.last_status == "SUCCESS", collector.last_error
    [row] = _rows(collector)
    start, end = (datetime.strptime(row[k], rau.DEFAULT_WINDOW_FORMAT) for k in ("start", "end"))
    assert end - start == timedelta(hours=24)
    now_kst = datetime.now(rau.WINDOW_ZONE).replace(tzinfo=None)
    assert timedelta(0) <= now_kst - end < timedelta(minutes=1)


def test_a_script_that_declares_no_window_runs_as_it_did(tmp_path):
    path = _plant(tmp_path, EXEC_BODY, header="# schedule: * * * * *\n")
    scheduler = rau.MultiDiscoveryScheduler(server_dir=str(tmp_path))
    scheduler.discover_and_load_collectors()
    [collector] = scheduler.collectors

    scheduler.execute_collector(collector)

    assert _rows(collector) == [{"start": "{{WINDOW_START}}", "end": "{{WINDOW_END}}"}]
