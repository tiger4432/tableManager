# -*- coding: utf-8 -*-
"""DRAFT (application lane, lead 2f487efb5) - a file that arrives LATER in an existing raws/ subfolder.

For the implementer to move into server/tests/. The real WorkspaceWatcher: watchdog observer on raws/
(recursive=False), the periodic sweep loop, the heavy lane, processing into in-memory SQLite. Only the
clocks are shorter (tree max wait = 2 x sweep, as 600 s / 300 s in operation).

Today: every cell is green but `test_a_late_file_goes_in_while_another_collectors_file_holds_the_sweep`,
which is red - the late files stay, with no log line, until the other collector's file returns.
"""
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
SWEEP, SLICE, POLL, MAX_WAIT = 3.0, 0.5, 0.2, 6.0
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
           "rows": rows, "start": start, "held": held, "settings": tmp_path / "ingestion_settings.json"}
    for release in held:
        release.set()
    watcher.stop()
    Base.metadata.drop_all(bind=engine)


def _in(box, rel, prefix):
    path = os.path.join(box["raws"], *rel.split("/"))
    _write(path, _csv(prefix))
    return path


def _went_in(box, prefixes, seconds=WAIT):
    return _until(lambda: all(f"{p}-1" in box["rows"]() for p in prefixes), seconds)


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


def test_a_growing_file_in_the_folder(box):
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


def test_files_not_archived(box):
    box["settings"].write_text('{"archive_processed_files": false}', encoding="utf-8")
    box["start"]()
    _in(box, "A/f1.csv", "F1")
    assert _went_in(box, ["F1"], 30)
    _in(box, "A/f2.csv", "L0"); _in(box, "A/f3.csv", "L1")
    assert _went_in(box, ["L0", "L1"])              # the files stay by this setting; their rows go in


def test_a_late_file_goes_in_while_another_collectors_file_holds_the_sweep(box, monkeypatch):
    """RED today. A direct raws/ file of another collector, there before start, is dispatched inline by
    the startup sweep under `_sweep_lock`, and its read does not return. A file added to an EXISTING
    subfolder has no event (recursive=False) - only the sweep re-triggers that folder - so it stays,
    with no log line, until that read returns."""
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
    handle = _keep_folder(box)                       # A exists before start: the startup sweep's tree takes keep
    try:
        box["start"]()
        assert _went_in(box, ["K"], 30)
        assert box["watcher"]._sweep_lock.locked()   # canary: the sweep is inside hang.csv
        _in(box, "A/f2.csv", "L0"); _in(box, "A/f3.csv", "L1")
        assert _went_in(box, ["L0", "L1"])           # <- red today: left until hang.csv returns
        # and when a file IS left, one line names the folder, how many, why and the next try (lead 2f487efb5)
    finally:
        handle.close()
