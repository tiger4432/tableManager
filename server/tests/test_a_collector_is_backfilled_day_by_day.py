# -*- coding: utf-8 -*-
"""A collector that declares `# window:` can be backfilled from a start day to now, one
24-hour window at a time (소유자 2026-09-26 「목표 기간까지 1 일 단위로 자동 소급」 · 「24h 씩,
마지막은 지금에서 자름」 · 총괄 ffd5d42b7 ㄴ 「실패한 날에서 멈춤, 그 날부터 재시작」).

🔴 A DAY IS DONE WHEN ITS FILE HAS PASSED THE INGESTION QUEUE, asked of its read's record
(`checkpoint.read_as_written`) by the name and stat the collector wrote - the read moves the
file to archives/ (owner 11-04, the real watcher's test below) - so the days never pile into the queue at
once, and a day whose collect or file FAILED is named in the result's failed days and the run goes on (owner 11-04,
REVERSING 총괄 ffd5d42b7 «stop on the failed day»).
"""
import csv
import io
import os
import re
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

    def step(self, name, page, pages, rows):
        """RunControl's step seat (79afc64e5) - the time inside a page; nothing to record here."""

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
    """The watcher, as the checklist answers for it: the n-th file read gets verdicts[n]
    (DONE = read · FAILED · None = not yet). Returns the windows the files carried, in order."""
    seen, calls = [], []

    def door(db, table, filepath, _file_stat):
        with open(filepath, encoding="utf-8") as f:
            row = next(csv.DictReader(io.StringIO(f.read())))
        if not seen or seen[-1] != (row["s"], row["e"]) or calls[-1] is not None:
            seen.append((row["s"], row["e"]))
        verdict = verdicts[len(seen) - 1] if len(seen) - 1 < len(verdicts) else checkpoint.STATUS_DONE
        calls.append(verdict)
        return None if verdict is None else "SUCCESS" if verdict == checkpoint.STATUS_DONE else verdict
    monkeypatch.setattr(checkpoint, "read_as_written", door)
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
    assert stats == {"days": 3, "days_done": 3, "failed_days": "0", "done_until": seen[-1][1]}
    assert not control.stopped


def test_a_failed_day_is_named_and_the_run_goes_on(workspace, monkeypatch):
    """REVERSES 총괄 ffd5d42b7 «a failed day stops the run» - owner 11-04 «그날에서 멈추지 말고 계속 돌리고 안 돈 날짜
    알려줘»: the middle day's file fails, the third day still runs, and the result names the failed day and why."""
    seen = ingests(monkeypatch, [checkpoint.STATUS_DONE, checkpoint.STATUS_FAILED])
    lines = []
    start = _two_days_ago()
    windows = cm.backfill_windows(cm.backfill_start(start))
    second = windows[1][0].strftime("%Y-%m-%d %H:%M")

    stats = retroactive._run_collector_backfill(DB, {"collector": KEY, "start": start}, lines.append, Control())

    assert len(seen) == 3, "the day after the failed one ran"
    assert stats["days_done"] == 2 and stats["done_until"] == seen[-1][1]
    assert re.fullmatch(r"1: %s \(file failed to ingest: probe_\d{8}_\d{6}\.csv\)" % second,
                        stats["failed_days"]), stats
    assert "failed days " + stats["failed_days"] in retroactive.run_result_sentence(stats)
    assert any(line.endswith("failed days " + stats["failed_days"]) for line in lines), lines


def test_starting_again_from_the_failed_day_finishes_the_rest(workspace, monkeypatch):
    start = _two_days_ago()
    second = cm.backfill_windows(cm.backfill_start(start))[1][0].strftime("%Y-%m-%d %H:%M")
    seen = ingests(monkeypatch, [])

    stats = _run(second, Control())

    assert stats == {"days": 2, "days_done": 2, "failed_days": "0", "done_until": seen[-1][1]}
    assert seen[0][0] == second + ":00"


def test_a_stop_lands_between_days(workspace, monkeypatch):
    seen = ingests(monkeypatch, [])
    control = Control(stop_after_days=1)
    start = _two_days_ago()

    stats = _run(start, control)

    assert stats == {"days": 3, "days_done": 1, "failed_days": "0", "done_until": cm.backfill_text(
        cm.backfill_start(start) + cm.BACKFILL_SLICE)}
    assert control.stopped and len(seen) == 1


def test_a_stop_while_a_file_waits_ends_without_counting_that_day(workspace, monkeypatch):
    ingests(monkeypatch, [None])
    control = Control()
    control.stopped = True                        # asked before the first file was read

    start = _two_days_ago()

    stats = _run(start, control)

    assert stats == {"days": 3, "days_done": 0, "failed_days": "0", "done_until": start}


class Watcher(Control):
    """The control whose every look while a day waits is one sweep of the REAL watcher over raws/ - it reads the
    file, archives it under another path and writes its record and checklist row there (owner 11-04 «백필로 돌리면
    10분 지나도 안 끝나서 그냥 끔»: the wait asked by the raws path the collector wrote and never saw the read).
    After `patience` looks it asks the run to stop, so a wait that never sees the read ends short of its days."""

    def __init__(self, handler, raws, patience=20):
        super().__init__()
        self.handler, self.raws, self.looks, self.patience = handler, raws, 0, patience

    def stop_requested(self):
        self.looks += 1
        for name in sorted(os.listdir(self.raws)):
            if name.endswith(".csv"):
                self.handler._handle_event(os.path.join(self.raws, name))
        self.handler.heavy_lane.run_all()
        self.stopped = self.stopped or self.looks > self.patience
        return self.stopped


def _real_backfill(workspace, monkeypatch, first_day=None):
    """The backfill against the real watcher (`Watcher`) on a sqlite memory db -> (stats or the refusal, the read
    records [(filepath, status, file_mtime)], the control). `first_day(attempt)`, when given, runs inside the first
    day's write on each attempt the watcher makes at it - it may raise."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import directory_watcher
    from conftest import retire_dynamic_model
    from database import crud, models
    from database.database import Base
    from test_heavy_lane import FakeLane

    info = {"business_key": "s", "column_types": {"s": "string", "e": "string"}, "display_columns": ["s", "e"]}
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models({TABLE: dict(info)})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, dict(info))
    Base.metadata.create_all(bind=engine)
    models.ensure_ingestion_checkpoint_table(engine)
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: {TABLE: info})
    monkeypatch.setattr(directory_watcher, "SessionLocal", factory)
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(workspace / "ingestion_settings.json"))
    if first_day is not None:
        real, files, attempts = directory_watcher.IngestionHandler._send_to_upsert, [], []

        def send(self, *a, **k):
            name = k.get("filename")
            files.append(name) if name not in files else None
            if name == files[0]:
                attempts.append(name)
                first_day(len(attempts))
            return real(self, *a, **k)
        monkeypatch.setattr(directory_watcher.IngestionHandler, "_send_to_upsert", send)
    folder = os.path.join(str(workspace), "ingestion_workspace", TABLE)
    for sub in ("raws", "archives", "err"):
        os.makedirs(os.path.join(folder, sub), exist_ok=True)
    handler = directory_watcher.IngestionHandler(folder, None, os.path.join(folder, "archives"),
                                                 default_table_name=TABLE, heavy_lane=FakeLane())
    control = Watcher(handler, os.path.join(folder, "raws"))
    db = factory()
    try:
        try:
            got = retroactive._run_collector_backfill(db, {"collector": KEY, "start": _two_days_ago()},
                                                      lambda m: None, control)
        except retroactive.RetroactiveRefused as e:
            got = e
        read = db.query(models.FileIngestionLog.filepath, models.FileIngestionLog.status,
                        models.FileIngestionLog.file_mtime).order_by(models.FileIngestionLog.id).all()
    finally:
        db.close()
        engine.dispose()
        retire_dynamic_model(TABLE)
    return got, read, control


def test_every_day_is_read_by_the_real_watcher_and_the_run_goes_on(workspace, monkeypatch):
    stats, read, control = _real_backfill(workspace, monkeypatch)

    assert read and {s for _p, s, _m in read} == {"SUCCESS"}, read           # canary: the watcher read the first day
    assert all(os.sep + "archives" + os.sep in p for p, _s, _m in read), read  # ... under a path never written
    assert stats["days_done"] == 3 and not control.stopped, (stats, control.looks, read)
    assert len(read) == 3, read


def test_a_day_whose_file_stayed_locked_into_err_is_a_failed_day(workspace, monkeypatch):
    """Locked through every attempt: the watcher moves the file to err/ and records a FAILED with no stamp; nothing
    reads it again by itself, so it ends that day as any failed file does (owner 11-04 «2 ㄴ») - named, and the run
    goes on. Before, the wait never saw it and waited until stopped."""
    # the day's own wait, as shipped: a file name carries its second, and a day waits >= 1 s, so no two days share one
    monkeypatch.setattr(retroactive, "BACKFILL_POLL_SECONDS", 1)

    def locked(attempt):
        if attempt <= 3:                                     # the watcher's three attempts at the first day
            raise PermissionError("locked by another process")
    stats, read, control = _real_backfill(workspace, monkeypatch, locked)

    first = cm.backfill_windows(cm.backfill_start(_two_days_ago()))[0][0].strftime("%Y-%m-%d %H:%M")
    assert (os.sep + "err" + os.sep in read[0][0], read[0][1], read[0][2]) == (True, "FAILED", None), read  # the shape
    assert not control.stopped and stats["days_done"] == 2, (stats, control.looks, read)
    assert re.fullmatch(r"1: %s \(file failed to ingest: probe_\d{8}_\d{6}\.csv\)" % first, stats["failed_days"])


def test_a_day_whose_file_waited_out_a_lock_is_waited_for_and_goes_in(workspace, monkeypatch):
    """Waited out another session's lock: a FAILED with no stamp too, but the file stays where it lies and the next
    sweep reads it - the run waits and goes on."""
    import directory_watcher

    def once(attempt):
        if attempt == 1:
            raise directory_watcher.LockWaitedOut("another session holds the table")
    stats, read, control = _real_backfill(workspace, monkeypatch, once)

    assert [s for _p, s, _m in read][:2] == ["FAILED", "SUCCESS"] and read[0][2] is None, read   # the shape
    assert os.sep + "raws" + os.sep in read[0][0], read
    assert stats["days_done"] == 3 and not control.stopped, (stats, control.looks, read)


@pytest.mark.pg
def test_the_stamp_a_read_wrote_is_the_stamp_asked_on_postgresql(pg_session, tmp_path):
    """The record's stamp goes through a PostgreSQL timestamptz and back (microseconds, the session's zone) - the
    file's own stat must still be the same value; another size is not."""
    from database import models

    path = str(tmp_path / "probe_20261104_101500.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("s,e\n1,2\n")
    mtime, size = checkpoint.read_file_stat(path)
    assert mtime.microsecond, "canary: a stamp with no microseconds proves nothing about them"
    pg_session.add(models.FileIngestionLog(
        filename=os.path.basename(path), filepath=str(tmp_path / "archives" / "probe_20261104_101500_1.csv"),
        table_name=TABLE, status="SUCCESS", retry_count=0, file_mtime=mtime, file_size=size))
    pg_session.commit()

    assert checkpoint.read_as_written(pg_session, TABLE, path, (mtime, size)) == "SUCCESS"
    assert checkpoint.read_as_written(pg_session, TABLE, path, (mtime, size + 1)) is None
    assert checkpoint.read_as_written(pg_session, "another_table", path, (mtime, size)) is None


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


def test_a_script_that_raises_is_named_and_the_run_goes_on(workspace, monkeypatch):
    """총괄 69aad666e B: a collect that raised ended the run with no day - any failure names it. Since owner 11-04 the
    run goes on past it (REVERSES 총괄 ffd5d42b7)."""
    import run_auto_update
    ingests(monkeypatch, [])
    real, calls = run_auto_update.GenericScriptRunnerCollector.execute, []

    def execute(self):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("the source is down")
        return real(self)
    monkeypatch.setattr(run_auto_update.GenericScriptRunnerCollector, "execute", execute)
    start = _two_days_ago()
    second = cm.backfill_windows(cm.backfill_start(start))[1][0].strftime("%Y-%m-%d %H:%M")

    stats = _run(start, Control())

    assert len(calls) == 3 and stats["days_done"] == 2, stats
    assert stats["failed_days"].startswith("1: %s (collecting failed: RuntimeError: the source is down (" % second)
    assert "test_a_collector_is_backfilled_day_by_day.py" in stats["failed_days"], stats   # where it broke


def test_a_schedule_the_scheduler_cannot_read_is_refused_before_anything_runs(workspace):
    """총괄 69aad666e B: the judge passed it and the collector's constructor then raised."""
    with open(os.path.join(str(workspace), "ingestion_workspace", TABLE, "auto_update",
                           "bad.py"), "w", encoding="utf-8") as f:
        f.write(SCRIPT.replace("# schedule: 0 * * * *", "# schedule: every hour"))
    with pytest.raises(retroactive.RetroactiveRefused, match="is not a cron expression"):
        retroactive._judge_collector_backfill({"collector": "%s/bad.py" % TABLE,
                                               "start": "2026-09-24"})
