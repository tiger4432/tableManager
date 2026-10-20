# -*- coding: utf-8 -*-
"""Fix a table's plugin or its declaration and its failed files are read again (lead 10-20 ab951f09b, owner 「ㅇㅇ」).

A real watcher process (`run_watcher.main`) on a scratch data root and a sqlite file; reread_max_files is 2.
Run 1:
  ta (2 files) · tb (1) · tc (3) · td (1) · te (1) - every plugin raises, every file FAILED
  ta's display_columns changed             -> nothing handed
  tb's plugin fixed                         -> tb read again, ta untouched
  ta's plugin fixed                         -> ta's 2 read again, one line
  tc's plugin fixed                         -> 3 over the cap of 2: one line, nothing handed
Run 2 (a restart): td's and te's plugins fixed while the watcher is down, te's kept reading taken away
  td -> read again at the start · te -> seen the first time: kept, not handed
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DRIVER = '''
import json, sys
sys.path.insert(0, "parsers")
import paths
from database.database import Base, engine
from database import models
models.init_dynamic_models(json.load(open(paths.config_path("table_config.json"), encoding="utf-8")))
Base.metadata.create_all(bind=engine)
import run_watcher
run_watcher.main()
'''

RAISING = '''
from pipeline_base import BasePipelineParser
class P(BasePipelineParser):
    @classmethod
    def match(cls, path):
        return True
    def parse(self, path):
        raise RuntimeError("the plugin is broken")
'''
FIXED = '''
import csv
from pipeline_base import BasePipelineParser
class P(BasePipelineParser):
    @classmethod
    def match(cls, path):
        return path.endswith(".csv")
    def parse(self, path):
        with open(path, newline="") as f:
            return [dict(r, val="fixed") for r in csv.DictReader(f)]
'''
TABLE = {"business_key": "lot", "column_types": {"lot": "string", "val": "string"}, "display_columns": ["lot", "val"]}
FILES = {"ta": 2, "tb": 1, "tc": 3, "td": 1, "te": 1}


def _plugin(data, table, source):
    scripts = os.path.join(data, "ingestion_workspace", table, "scripts")
    os.makedirs(scripts, exist_ok=True)
    with open(os.path.join(scripts, "p.py"), "w", encoding="utf-8") as f:
        f.write(source)


def _table_config(data, tables):
    with open(os.path.join(data, "config", "table_config.json"), "w", encoding="utf-8") as f:
        json.dump(tables, f)


def _states(c):
    out = {}
    for table, status, n in c.execute("SELECT table_name, status, count(*) FROM file_ingestion_logs GROUP BY 1, 2"):
        out.setdefault(table, {})[status] = n
    return out


class _Watcher:
    def __init__(self, tmp, db):
        env = dict(os.environ, ASSY_DATA_ROOT=str(tmp / "data"), DATABASE_URL="sqlite:///" + db.as_posix(),
                   API_BASE_URL="http://127.0.0.1:9", PYTHONIOENCODING="utf-8", PYTHONPATH=SERVER_DIR,
                   DECOUPLED="True")
        env.pop("TESTING", None)
        driver = tmp / "driver.py"
        driver.write_text(DRIVER, encoding="utf-8")
        self.db, self.log_path = db, tmp / ("watcher_%d.log" % time.monotonic_ns())
        self.log = open(self.log_path, "wb")
        self.process = subprocess.Popen([sys.executable, str(driver)], cwd=SERVER_DIR, env=env, stdout=self.log,
                                        stderr=subprocess.STDOUT)

    def until(self, holds, seconds=120):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and self.process.poll() is None:
            time.sleep(1)
            try:
                with sqlite3.connect(str(self.db)) as c:
                    states = _states(c)
            except sqlite3.Error:
                continue
            if holds(states):
                return states
        with sqlite3.connect(str(self.db)) as c:
            return _states(c)

    def text(self):
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def stop(self):
        self.process.kill()
        self.process.wait(30)
        self.log.close()


def _all_failed(states):
    return all(states.get(t, {}).get("FAILED") == n for t, n in FILES.items())


def test_a_fixed_plugin_reads_its_tables_failed_files_again(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    tables = {t: dict(TABLE) for t in FILES}
    _table_config(data, tables)
    with open(os.path.join(data, "config", "ingestion_settings.json"), "w", encoding="utf-8") as f:
        json.dump({"reread_max_files": 2}, f)
    for table, n in FILES.items():
        _plugin(data, table, RAISING)
        raws = os.path.join(data, "ingestion_workspace", table, "raws")
        os.makedirs(raws, exist_ok=True)
        for i in range(n):
            with open(os.path.join(raws, "%s%d.csv" % (table, i)), "w", encoding="utf-8") as f:
                f.write("lot,val\n%s%d,raw\n" % (table, i))
    db = tmp_path / "box.db"
    stamps_path = os.path.join(data, "config", "watcher_reading_stamps.json")

    watcher = _Watcher(tmp_path, db)
    try:
        states = watcher.until(_all_failed)
        assert _all_failed(states), states
        assert watcher.until(lambda s: os.path.exists(stamps_path), 20) is not None and os.path.exists(stamps_path)

        tables["ta"] = dict(TABLE, display_columns=["val", "lot"])
        _table_config(data, tables)
        time.sleep(10)                                         # three of the poller's ticks
        # by its line: handed files would fail again under the broken plugin and look the same
        assert "[Watcher] ta: its reading changed" not in watcher.text(), "a display cell handed the files"
        assert watcher.until(lambda s: False, 1)["ta"] == {"FAILED": 2}

        _plugin(data, "tb", FIXED)
        states = watcher.until(lambda s: s["tb"] == {"SUCCESS": 1})
        assert states["tb"] == {"SUCCESS": 1} and states["ta"] == {"FAILED": 2}, states

        _plugin(data, "ta", FIXED)
        states = watcher.until(lambda s: s["ta"] == {"SUCCESS": 2})
        assert states["ta"] == {"SUCCESS": 2}, states
        assert "[Watcher] ta: its reading changed (scripts\\p.py) - 2 failed file(s) handed again" in watcher.text()

        _plugin(data, "tc", FIXED)
        time.sleep(10)
        assert watcher.until(lambda s: False, 1)["tc"] == {"FAILED": 3}
        assert ("[Watcher] tc: its reading changed (scripts\\p.py) - 3 failed files wait - Retry failed by folder"
                in watcher.text())
    finally:
        watcher.stop()

    _plugin(data, "td", FIXED)
    _plugin(data, "te", FIXED)
    with open(stamps_path, encoding="utf-8") as f:
        kept = json.load(f)
    kept.pop("te")
    with open(stamps_path, "w", encoding="utf-8") as f:
        json.dump(kept, f)

    watcher = _Watcher(tmp_path, db)
    try:
        states = watcher.until(lambda s: s["td"] == {"SUCCESS": 1})
        assert states["td"] == {"SUCCESS": 1}, states
        time.sleep(8)
        assert watcher.until(lambda s: False, 1)["te"] == {"FAILED": 1}, "a table seen the first time was handed"
        with open(stamps_path, encoding="utf-8") as f:
            assert "te" in json.load(f)
    finally:
        watcher.stop()


def test_a_settings_file_that_reads_as_nothing_passes_the_tick(tmp_path, monkeypatch):
    """Lead 10-20: ingestion_settings.json there but read as nothing (mid-write) - the external part is not compared,
    nothing handed, the stamps not written over; the file absent is no external source, compared as before."""
    sys.path.insert(0, os.path.join(SERVER_DIR, "parsers"))
    import directory_watcher
    import run_watcher
    from ingestion import reread, settings

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    entry = dict(TABLE)
    source = {"path": str(tmp_path / "share"), "table_name": "ta", "options": {"glob": "*.csv"}}
    kept = {"ta": reread.reading_of("ta", entry, [source], str(scripts))}

    class Handler:
        scripts_path = str(scripts)

        def _resolve_table_name(self, table_config):
            return "ta"

    monkeypatch.setattr(run_watcher, "workspace_watcher", type("W", (), {"handlers_by_raw_path": {"r": Handler()}}))
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: {"ta": entry})
    handed, written = [], []
    monkeypatch.setattr(reread, "hand_on_a_changed_reading", lambda *a: handed.append(a[1]))
    monkeypatch.setattr(reread, "keep_reading_stamps", lambda stamps: written.append(stamps))
    path = tmp_path / "ingestion_settings.json"
    monkeypatch.setattr(settings, "INGESTION_SETTINGS_PATH", str(path))

    path.write_text("", encoding="utf-8")                          # there, read as nothing
    assert run_watcher.hear_changed_readings(None, kept) == kept and not handed and not written

    path.unlink()                                                  # absent: no external source - a change
    assert run_watcher.hear_changed_readings(None, kept) != kept and handed == ["ta"] and len(written) == 1
