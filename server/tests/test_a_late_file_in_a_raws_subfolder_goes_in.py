# -*- coding: utf-8 -*-
"""A file that arrives LATER in an existing raws/ subfolder goes in (총괄 2f487efb5; cells: application
draft d34058e75). It has no event - the observer on raws/ is not recursive - so the subfolder recheck
finds it, on a thread of its own and outside the sweep's lock.

The real WorkspaceWatcher: observer, periodic sweep loop, subfolder recheck, heavy lane, processing into
in-memory SQLite. Only the clocks are shorter (tree max wait = 2 x sweep, as 600 s / 300 s in operation).
"""
import json
import logging
import os
import sys
import threading
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

here = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(here, ".."))
for p in (server_dir, os.path.join(server_dir, "parsers")):
    if p not in sys.path:
        sys.path.insert(0, p)

import directory_watcher  # noqa: E402
from directory_watcher import WorkspaceWatcher  # noqa: E402
from database.database import Base  # noqa: E402
from database import crud, models  # noqa: E402

TABLE, OTHER = "flat_test_parts", "flat_test_other"
INFO = {"business_key": "part_no",
        "column_types": {"part_no": "string", "category": "string", "stock_qty": "number"},
        "display_columns": ["part_no", "category", "stock_qty"]}
SWEEP, SLICE, POLL, MAX_WAIT, RECHECK = 3.0, 0.5, 0.2, 6.0, 1.0
WAIT = SWEEP * 4 + 3                       # four sweeps


def _csv(prefix):
    return "part_no,category,stock_qty\n" + "".join(f"{prefix}-{i},Cap,{i}\n" for i in (1, 2))


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _until(pred, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.1)
    return pred()


@pytest.fixture
def box(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    cfg = {TABLE: dict(INFO), OTHER: dict(INFO)}
    models.init_dynamic_models(cfg)
    crud.TABLE_CONFIG.update(cfg)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    models.ensure_ingestion_checkpoint_table(engine)
    for name, value in (("load_global_table_config", lambda: cfg), ("SessionLocal", Session),
                        ("INGESTION_SETTINGS_PATH", str(tmp_path / "ingestion_settings.json")),
                        ("PERIODIC_SWEEP_INTERVAL_SECONDS", SWEEP), ("HEARTBEAT_SLICE_SECONDS", SLICE),
                        ("FLATTEN_STABILITY_INTERVAL_SECONDS", POLL), ("FLATTEN_STABILITY_MAX_WAIT_SECONDS", MAX_WAIT)):
        monkeypatch.setattr(directory_watcher, name, value)
    base = tmp_path / "ingestion"
    for table in (TABLE, OTHER):
        for sub in ("raws", "archives", "err"):
            (base / table / sub).mkdir(parents=True)
    settings = tmp_path / "ingestion_settings.json"
    settings.write_text(json.dumps({"subfolder_recheck_seconds": RECHECK}), encoding="utf-8")
    watcher = WorkspaceWatcher(str(base))
    for table in (TABLE, OTHER):
        assert watcher._register_workspace(str(base / table / "raws"), cfg)
    held = []

    def rows():
        db = Session()
        try:
            return {r.part_no for r in db.query(models.DYNAMIC_TABLES[TABLE]).all()}
        finally:
            db.close()

    def start():
        watcher.start(blocking=False)

    yield {"raws": str(base / TABLE / "raws"), "other_raws": str(base / OTHER / "raws"), "watcher": watcher,
           "rows": rows, "start": start, "held": held, "settings": settings}
    for release in held:
        release.set()
    if watcher.observer.is_alive():                 # the cells that only look never start it
        watcher.stop()
    Base.metadata.drop_all(bind=engine)


def _in(box, rel, prefix):
    path = os.path.join(box["raws"], *rel.split("/"))
    _write(path, _csv(prefix))
    return path


def _went_in(box, prefixes, seconds=WAIT):
    return _until(lambda: all(f"{p}-1" in box["rows"]() for p in prefixes), seconds)


def _left(caplog, reason_words):
    """The folder-left lines (`say_what_a_folder_left`) whose reason carries `reason_words`."""
    return [r.getMessage() for r in caplog.records
            if "file(s) left - " in r.getMessage() and reason_words in r.getMessage()]


SAID = " for this folder and reason (said at the 1st, 10th, 100th ...)"


def _keep_folder(box, rel="A/keep.csv"):
    """An open handle on a file in the folder: its archive move fails, so the folder is not removed."""
    path = _in(box, rel, "K")
    handle = open(path, "a")
    box["held"].append(threading.Event())          # placeholder so teardown order stays simple
    return handle


def test_folder_emptied_and_removed_then_made_again(box):
    box["start"]()
    first = _in(box, "A/f1.csv", "F1")
    assert _until(lambda: not os.path.exists(first) and "F1-1" in box["rows"](), 30)
    _in(box, "A/f2.csv", "L0"); _in(box, "A/f3.csv", "L1")
    assert _went_in(box, ["L0", "L1"])


def test_folder_kept_by_a_file_that_stays(box):
    box["start"]()
    handle = _keep_folder(box)
    try:
        _in(box, "A/f1.csv", "F1")
        assert _went_in(box, ["F1", "K"], 30)
        _in(box, "A/f2.csv", "L0"); _in(box, "A/f3.csv", "L1")
        assert _went_in(box, ["L0", "L1"])
    finally:
        handle.close()


def test_a_growing_file_in_the_folder(box, caplog):
    caplog.set_level(logging.INFO)
    box["start"]()
    grow = os.path.join(box["raws"], "A", "grow.log")
    os.makedirs(os.path.dirname(grow), exist_ok=True)
    stop = threading.Event()

    def grower():
        with open(grow, "a") as f:
            while not stop.is_set():
                f.write("x\n"); f.flush(); time.sleep(0.05)
    t = threading.Thread(target=grower, daemon=True); t.start()
    try:
        _in(box, "A/f1.csv", "F1")
        assert _went_in(box, ["F1"], 30)
        _in(box, "A/f2.csv", "L0"); _in(box, "A/f3.csv", "L1")
        assert _went_in(box, ["L0", "L1"])
        # reason «still being written»: the pass gives up waiting after MAX_WAIT; the words 31802478c asserts stay
        assert _until(lambda: _left(caplog, "Tree ingestion deferred"), MAX_WAIT * 3)
        line = _left(caplog, "Tree ingestion deferred")[0]
        assert line.startswith("[%s] 📂 'A': " % TABLE) and "1 file(s) still being written after 6.0s" in line \
            and "(still writing: grow.log; " in line and "finished file(s) dispatched)" in line \
            and line.endswith(" - next look in 1 s - #1" + SAID), line
    finally:
        stop.set(); t.join(5)


def test_same_name_as_the_first(box):
    box["start"]()
    first = _in(box, "A/f1.csv", "F1")
    assert _until(lambda: not os.path.exists(first) and "F1-1" in box["rows"](), 30)
    _in(box, "A/f1.csv", "S0")
    assert _went_in(box, ["S0"])


def test_two_levels_down(box):
    box["start"]()
    _in(box, "A/B/f1.csv", "F1")
    assert _went_in(box, ["F1"], 30)
    _in(box, "A/B/f2.csv", "L0"); _in(box, "A/B/f3.csv", "L1")
    assert _went_in(box, ["L0", "L1"])


def test_late_files_while_the_first_is_being_ingested(box):
    box["start"]()
    _in(box, "A/f1.csv", "F1")
    assert _went_in(box, ["F1"], 30)
    _in(box, "A/f2.csv", "L0"); _in(box, "A/f3.csv", "L1")
    assert _went_in(box, ["L0", "L1"])


def test_every_file_on_the_heavy_lane(box, monkeypatch):
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 1)
    box["start"]()
    _in(box, "A/f1.csv", "F1")
    assert _went_in(box, ["F1"], 30)
    _in(box, "A/f2.csv", "L0"); _in(box, "A/f3.csv", "L1")
    assert _went_in(box, ["L0", "L1"])


def test_files_not_archived(box, caplog):
    caplog.set_level(logging.INFO)
    box["settings"].write_text(json.dumps({"subfolder_recheck_seconds": RECHECK, "archive_processed_files": False}),
                               encoding="utf-8")
    box["start"]()
    _in(box, "A/f1.csv", "F1")
    assert _went_in(box, ["F1"], 30)
    # reason «kept by archive off»: the owner must not read a file still there as «not recognized» (총괄 2f487efb5)
    assert _until(lambda: _left(caplog, "kept in place"), 30)
    assert _left(caplog, "kept in place") == [
        "[%s] 📂 'A': 1 file(s) left - kept in place (archive_processed_files=false): dispatched 1 file(s)"
        " - next pass when it changes, else in 3 s - #1" % TABLE + SAID]
    _in(box, "A/f2.csv", "L0"); _in(box, "A/f3.csv", "L1")
    assert _went_in(box, ["L0", "L1"])              # the files stay by this setting; their rows go in


def test_a_late_file_goes_in_while_another_collectors_file_holds_the_sweep(box, monkeypatch, caplog):
    """A direct raws/ file of another collector, there before start, is dispatched inline by the startup
    sweep under `_sweep_lock`, and its read does not return. When the sweep re-read subfolders the late
    files stayed, with no log line, until that read returned (d34058e75: red)."""
    release = threading.Event()
    box["held"].append(release)
    _write(os.path.join(box["other_raws"], "hang.csv"), _csv("H"))
    other = box["watcher"].handlers_by_raw_path[os.path.abspath(box["other_raws"])]
    real = other._resolve_rows

    def hangs(file_path, **kw):
        if os.path.basename(file_path) == "hang.csv":
            release.wait(120)
        return real(file_path, **kw)
    monkeypatch.setattr(other, "_resolve_rows", hangs)
    caplog.set_level(logging.INFO)
    handle = _keep_folder(box)                       # A exists before start: the recheck's tree takes keep
    try:
        box["start"]()
        assert _went_in(box, ["K"], 30)
        assert box["watcher"]._sweep_lock.locked()   # canary: the sweep is inside hang.csv
        # the file that IS left - keep.csv, its move refused by the open handle - is said: folder, how many,
        # why and the next try (총괄 2f487efb5). Its pass is over: what comes now is late.
        assert _until(lambda: _left(caplog, "Tree ingestion incomplete"), 30)
        _in(box, "A/f2.csv", "L0"); _in(box, "A/f3.csv", "L1")
        assert _went_in(box, ["L0", "L1"])           # the sweep's lock no longer holds them (d34058e75: red)
        assert box["watcher"]._sweep_lock.locked()
        assert _left(caplog, "Tree ingestion incomplete") == [
            "[%s] 📂 'A': 1 file(s) left - Tree ingestion incomplete: dispatched 1 file(s), 0 refused — directory"
            " preserved - next pass when it changes, else in 3 s - #1" % TABLE + SAID]
    finally:
        handle.close()


def test_a_folder_whose_worker_is_still_at_it_is_said_once_per_episode(box, monkeypatch, caplog):
    """Reason «tree worker running»: since when and the file it is on (총괄 10-07 ③), counted per look;
    the count ends when a look finds nobody ingesting the folder."""
    caplog.set_level(logging.INFO)
    watcher = box["watcher"]
    handler = watcher.handlers_by_raw_path[os.path.abspath(box["raws"])]
    monkeypatch.setattr(handler, "request_tree_ingest", lambda path: None)
    _in(box, "A/f1.csv", "F1"); _in(box, "A/f2.csv", "F2")
    key = os.path.normcase(os.path.abspath(os.path.join(box["raws"], "A")))

    def running(seconds_ago):
        with handler._processing_lock:
            handler._ingesting_dirs[key] = time.time() - seconds_ago
    running(125)
    for _ in range(10):
        watcher.recheck_subfolders()
    said = _left(caplog, "tree ingestion has been running")
    assert said == ["[%s] 📂 'A': 2 file(s) left - tree ingestion has been running for 2 min (now: no file)"
                    " - next look in 1 s - #%d" % (TABLE, n) + SAID for n in (1, 10)], said
    with handler._processing_lock:
        handler._ingesting_dirs.pop(key)
    watcher.recheck_subfolders()                     # nobody at it: the episode ends
    running(0)
    watcher.recheck_subfolders()
    assert _left(caplog, "tree ingestion has been running")[2:] == [
        "[%s] 📂 'A': 2 file(s) left - tree ingestion has been running for 0 min (now: no file)"
        " - next look in 1 s - #1" % TABLE + SAID]


def test_an_unchanged_folder_of_20000_kept_files_gets_no_worker_until_a_sweep_interval(box, monkeypatch):
    """총괄 2f487efb5 ①: archive off, the files stay - the look walks the folder (no DB) and asks for a
    worker only when it changed, or a sweep interval after the last one. The worker here only counts."""
    box["settings"].write_text(json.dumps({"subfolder_recheck_seconds": 30, "archive_processed_files": False}),
                               encoding="utf-8")
    monkeypatch.setattr(directory_watcher, "PERIODIC_SWEEP_INTERVAL_SECONDS", 3600)
    watcher = box["watcher"]
    handler = watcher.handlers_by_raw_path[os.path.abspath(box["raws"])]
    asked = []
    monkeypatch.setattr(handler, "request_tree_ingest", lambda path: asked.append(path) or object())
    folder = os.path.join(box["raws"], "A")
    for i in range(20000):
        sub = os.path.join(folder, "d%02d" % (i % 20))
        if i < 20:
            os.makedirs(sub)
        with open(os.path.join(sub, "f%05d.csv" % i), "w") as f:
            f.write("x\n")
    assert sum(len(names) for _d, _s, names in os.walk(folder)) == 20000
    assert watcher.recheck_subfolders() == 1 and len(asked) == 1           # first sight
    for _ in range(3):
        assert watcher.recheck_subfolders() == 0                           # unchanged: no worker
    assert len(asked) == 1
    _in(box, "A/d00/late.csv", "L0")
    assert watcher.recheck_subfolders() == 1 and len(asked) == 2           # changed
    assert watcher.recheck_subfolders() == 0 and len(asked) == 2
    monkeypatch.setattr(directory_watcher, "PERIODIC_SWEEP_INTERVAL_SECONDS", 0)
    assert watcher.recheck_subfolders() == 1 and len(asked) == 3           # a sweep interval since: retried


def test_nested_ingestion_off_is_said_at_the_1st_and_10th_of_25_looks(box, caplog):
    caplog.set_level(logging.INFO)
    box["settings"].write_text(json.dumps({"subfolder_recheck_seconds": 30, "flatten_nested_dirs": False}),
                               encoding="utf-8")
    _in(box, "A/f1.csv", "F1")
    for _ in range(25):
        box["watcher"].recheck_subfolders()
    assert _left(caplog, "nested-directory ingestion is off") == [
        "[%s] 📂 'A': 1 file(s) left - nested-directory ingestion is off (flatten_nested_dirs=false) - left"
        " untouched, its files are NOT ingested - no pass while flatten_nested_dirs=false - #%d" % (TABLE, n) + SAID
        for n in (1, 10)]
    assert os.path.exists(os.path.join(box["raws"], "A", "f1.csv"))
