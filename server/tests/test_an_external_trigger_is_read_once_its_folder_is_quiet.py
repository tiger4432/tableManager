# -*- coding: utf-8 -*-
"""An external source's trigger file is read once its folder went quiet (owner 10-23 「폴더 전송 중에 읽어버린다」,
총괄 b15d6b66e): voids.json arrives first and the images under its folder over seconds; the owner's script lists the
images when voids.json is read, so a read at once lists part of them - and the sweep never reads it again.

The real watchdog observer and handler on a scratch folder, sqlite, a plugin standing in for the owner's script (one row
per image under the trigger's folder):
  the cell        `options.stability_interval_seconds` - every image, read once the folder looked the same that far apart
  unwritten       read at once, as before - part of them
  max wait        still changing after it: read with what was there, one line names the folder and the re-read door
  two folders     one still changing does not hold back the other
  refused         a cell that is no number of seconds above 0, by name
"""
import json
import logging
import os
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import directory_watcher
from database import crud, models
from database.database import Base

TABLE = "qt_images"
TABLES = {TABLE: {"composite_key_source": ["folder", "image"],
                  "column_types": {"folder": "string", "image": "string"}}}
PLUGIN = '''
import os
import pandas as pd
from pipeline_base import BasePipelineParser


class ImageList(BasePipelineParser):
    @classmethod
    def match(cls, file_path):
        return os.path.basename(file_path).lower() == "voids.json"

    def _read_file_to_dataframe(self, file_path):
        folder = os.path.dirname(file_path)
        images = sorted(f for f in os.listdir(os.path.join(folder, "images")) if f.endswith(".png"))
        return pd.DataFrame([{"folder": os.path.basename(folder), "image": f} for f in images])
'''
IMAGES, GAP = 10, 0.5


@pytest.fixture(name="box")
def fixture_box(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + (tmp_path / "box.db").as_posix(), connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    monkeypatch.setattr(crud, "TABLE_CONFIG", dict(crud.TABLE_CONFIG, **TABLES))
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    models.ensure_ingestion_checkpoint_table(engine)
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: TABLES)
    monkeypatch.setattr(directory_watcher, "SessionLocal", Session)
    workspace = tmp_path / "ws"
    (workspace / TABLE / "raws").mkdir(parents=True)
    (workspace / TABLE / "scripts").mkdir()
    (workspace / TABLE / "scripts" / "image_list.py").write_text(PLUGIN, encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    settings = tmp_path / "ingestion_settings.json"
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(settings))
    started = []

    def watch(options):
        settings.write_text(json.dumps({"external_sources": [{
            "path": str(external), "table_name": TABLE, "recursive": True,
            "options": dict({"filename": "voids.json"}, **options)}]}), encoding="utf-8")
        watcher = directory_watcher.WorkspaceWatcher(str(workspace))
        watcher.discover_and_watch()
        watcher.start(blocking=False)
        started.append(watcher)
        time.sleep(1)
        return watcher

    def rows(folder=None):
        db = Session()
        try:
            query = db.query(models.DYNAMIC_TABLES[TABLE])
            return (query.filter_by(folder=folder) if folder else query).count()
        finally:
            db.close()

    yield {"watch": watch, "rows": rows, "external": external}
    for watcher in started:
        watcher.stop()
    Base.metadata.drop_all(bind=engine)


def _copy(external, wafer, run, images=IMAGES, gap=GAP):
    """A folder copied in: voids.json first, then its images `gap` seconds apart."""
    folder = external / wafer / run
    (folder / "images").mkdir(parents=True)
    (folder / "voids.json").write_text('{"voids": []}', encoding="utf-8")
    for i in range(images):
        time.sleep(gap)
        (folder / "images" / ("img_%03d.png" % i)).write_bytes(b"\x89PNG" + os.urandom(32))


def _until(check, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.2)
    return check()


def test_with_the_cell_every_image_is_read(box):
    box["watch"]({"stability_interval_seconds": 1})
    _copy(box["external"], "WF-001", "JOB1_20261023_010000")
    assert _until(lambda: box["rows"]() == IMAGES, 15), box["rows"]()
    time.sleep(2)
    assert box["rows"]() == IMAGES


def test_without_the_cell_it_is_read_at_once_as_before(box):
    box["watch"]({})
    _copy(box["external"], "WF-001", "JOB1_20261023_010000")
    time.sleep(3)
    assert 0 < box["rows"]() < IMAGES, box["rows"]()


def test_past_the_max_wait_it_is_read_with_what_was_there_and_said(box, monkeypatch, caplog):
    monkeypatch.setattr(directory_watcher, "FLATTEN_STABILITY_MAX_WAIT_SECONDS", 2)
    box["watch"]({"stability_interval_seconds": 1})
    with caplog.at_level(logging.WARNING):
        _copy(box["external"], "WF-001", "JOB1_20261023_010000", images=12, gap=0.5)
        assert _until(lambda: box["rows"]() > 0, 10)
    assert box["rows"]() < 12
    said = [r.getMessage() for r in caplog.records if "still changing after 2s" in r.getMessage()]
    assert len(said) == 1 and "'JOB1_20261023_010000'" in said[0] and "retry-failed statuses=SUCCESS" in said[0], said


def test_a_folder_still_changing_does_not_hold_back_another(box):
    import threading

    box["watch"]({"stability_interval_seconds": 1})
    slow = threading.Thread(target=_copy, args=(box["external"], "WF-001", "SLOW_20261023_010000", 16, 0.5))
    slow.start()                                                   # eight seconds of images
    time.sleep(1)
    began = time.monotonic()
    _copy(box["external"], "WF-002", "FAST_20261023_010000", images=3, gap=0.1)
    assert _until(lambda: box["rows"]("FAST_20261023_010000") == 3, 10)
    fast_in = time.monotonic() - began
    slow_rows = box["rows"]("SLOW_20261023_010000")
    slow.join()
    assert fast_in < 5 and slow_rows == 0, (fast_in, slow_rows)      # in while the slow one was still copying
    assert _until(lambda: box["rows"]("SLOW_20261023_010000") == 16, 15)


@pytest.mark.parametrize("value", [0, -1, "1", True, None])
def test_a_cell_that_is_no_seconds_above_zero_is_refused_by_name(tmp_path, value):
    (tmp_path / "external").mkdir()
    (tmp_path / "ws" / TABLE / "scripts").mkdir(parents=True)
    (tmp_path / "ws" / TABLE / "scripts" / "image_list.py").write_text(PLUGIN, encoding="utf-8")
    options = {"filename": "voids.json", "stability_interval_seconds": value}
    if value is None:
        options.pop("stability_interval_seconds")
    valid, errors = directory_watcher.validate_external_source_specs(
        {"external_sources": [{"path": str(tmp_path / "external"), "table_name": TABLE, "options": options}]},
        TABLES, str(tmp_path / "ws"))
    if value is None:
        assert errors == [] and len(valid) == 1
    else:
        assert valid == [] and any("options.stability_interval_seconds must be a number of seconds above 0" in e
                                   for e in errors), errors
