# -*- coding: utf-8 -*-
"""Fix a table's plugin and its failed files stay FAILED until Retry reads them (소유자 10-24 «에러파일 자동으로 읽는건
안끄냐», `reread.hand_on_a_changed_reading`; it replaced lead 10-20 ab951f09b «a fixed plugin reads them again»).

A real watcher process (`run_watcher.main`) and a real API process on a scratch data root and a sqlite file;
reread_max_files is 2 - the Retry line's pace, not a cap (총괄 10-21).
Run 1:
  ta (2 files) · tb (1) · tc (3) · td (1) · te (1) - every plugin raises, every file FAILED
  ta's display_columns changed             -> nothing said, nothing read
  tb's plugin fixed                         -> its line says failed files are not read again; tb stays FAILED
  Retry on tb's folder (the file page)      -> tb read (from err/, where a failed file goes), ta untouched
  tc's plugin fixed, Retry on tc's folder   -> all 3 read, past reread_max_files
Run 2 (a restart): td's and te's plugins fixed while the watcher is down, te's kept reading taken away
  td -> its line at the start, still FAILED · te -> seen the first time: kept, no line
"""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOT_AGAIN = "failed files are not read again by themselves (Retry on the file page)"

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
API = '''
import sys
import uvicorn
import main
from admin import auth
main.app.dependency_overrides[auth.require_admin_token] = lambda: None
uvicorn.run(main.app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
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
    for table, status, n in c.execute("SELECT table_name, status, count(*) FROM file_checklist GROUP BY 1, 2"):
        out.setdefault(table, {})[status] = n
    return out


def _env(tmp, db):
    env = dict(os.environ, ASSY_DATA_ROOT=str(tmp / "data"), DATABASE_URL="sqlite:///" + db.as_posix(),
               API_BASE_URL="http://127.0.0.1:9", PYTHONIOENCODING="utf-8", PYTHONPATH=SERVER_DIR, DECOUPLED="True")
    env.pop("TESTING", None)
    env.pop("ASSY_ADMIN_TOKEN", None)
    return env


class _Watcher:
    def __init__(self, tmp, db):
        driver = tmp / "driver.py"
        driver.write_text(DRIVER, encoding="utf-8")
        self.db, self.log_path = db, tmp / ("watcher_%d.log" % time.monotonic_ns())
        self.log = open(self.log_path, "wb")
        self.process = subprocess.Popen([sys.executable, str(driver)], cwd=SERVER_DIR, env=_env(tmp, db),
                                        stdout=self.log, stderr=subprocess.STDOUT)

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


class _Api:
    """The file page's Retry: POST /admin/file-ingestion/retry-failed?folder=<the table's folder>."""
    def __init__(self, tmp, db):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        script = tmp / "api.py"
        script.write_text(API, encoding="utf-8")
        self.log = open(tmp / "api.log", "wb")
        self.process = subprocess.Popen([sys.executable, str(script), str(self.port)], cwd=SERVER_DIR,
                                        env=_env(tmp, db), stdout=self.log, stderr=subprocess.STDOUT)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # the box's proxy is not ours

    def retry(self, folder, seconds=90):
        url = "http://127.0.0.1:%d/admin/file-ingestion/retry-failed?%s" % (
            self.port, urllib.parse.urlencode({"folder": folder}))
        deadline = time.monotonic() + seconds
        while True:
            assert self.process.poll() is None, "the API process is gone - another may hold its port"
            try:
                with self.opener.open(urllib.request.Request(url, data=b"", method="POST"), timeout=60) as reply:
                    said = json.loads(reply.read())
                assert self.process.poll() is None, "the API process is gone - another answered on its port"
                return said
            except OSError:
                if time.monotonic() > deadline or self.process.poll() is not None:
                    raise
                time.sleep(1)

    def stop(self):
        self.process.kill()
        self.process.wait(30)
        self.log.close()


def _all_failed(states):
    return all(states.get(t, {}).get("FAILED") == n for t, n in FILES.items())


def test_a_fixed_plugin_leaves_its_failed_files_to_retry(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    tables = {t: dict(TABLE) for t in FILES}
    _table_config(data, tables)
    with open(os.path.join(data, "config", "ingestion_settings.json"), "w", encoding="utf-8") as f:
        json.dump({"reread_max_files": 2}, f)
    raws, folder = {}, {}
    for table, n in FILES.items():
        _plugin(data, table, RAISING)
        folder[table] = os.path.join(data, "ingestion_workspace", table)
        raws[table] = os.path.join(folder[table], "raws")
        os.makedirs(raws[table], exist_ok=True)
        for i in range(n):
            with open(os.path.join(raws[table], "%s%d.csv" % (table, i)), "w", encoding="utf-8") as f:
                f.write("lot,val\n%s%d,raw\n" % (table, i))
    db = tmp_path / "box.db"
    stamps_path = os.path.join(data, "config", "watcher_reading_stamps.json")

    watcher = _Watcher(tmp_path, db)
    api = None
    try:
        states = watcher.until(_all_failed)
        assert _all_failed(states), states
        assert watcher.until(lambda s: os.path.exists(stamps_path), 20) is not None and os.path.exists(stamps_path)
        api = _Api(tmp_path, db)

        tables["ta"] = dict(TABLE, display_columns=["val", "lot"])
        _table_config(data, tables)
        time.sleep(10)                                         # three of the poller's ticks
        assert "[Watcher] ta: its reading changed" not in watcher.text(), "a display cell said a changed reading"
        assert watcher.until(lambda s: False, 1)["ta"] == {"FAILED": 2}

        _plugin(data, "tb", FIXED)
        line = "[Watcher] tb: its reading changed (scripts\\p.py) - 0 read file(s) unchecked, " + NOT_AGAIN
        assert watcher.until(lambda s: line in watcher.text(), 60) is not None and line in watcher.text()
        time.sleep(5)
        assert watcher.until(lambda s: False, 1)["tb"] == {"FAILED": 1}, "a fixed plugin read its failed file"
        assert api.retry(folder["tb"])["count"] == 1
        states = watcher.until(lambda s: s["tb"] == {"SUCCESS": 1})
        assert states["tb"] == {"SUCCESS": 1} and states["ta"] == {"FAILED": 2}, states

        _plugin(data, "tc", FIXED)
        assert watcher.until(lambda s: "[Watcher] tc: its reading changed" in watcher.text(), 60) is not None
        assert api.retry(folder["tc"])["count"] == 3
        states = watcher.until(lambda s: s["tc"] == {"SUCCESS": 3})
        assert states["tc"] == {"SUCCESS": 3}, states
    finally:
        watcher.stop()
        if api is not None:
            api.stop()

    _plugin(data, "td", FIXED)
    _plugin(data, "te", FIXED)
    with open(stamps_path, encoding="utf-8") as f:
        kept = json.load(f)
    kept.pop("te")
    with open(stamps_path, "w", encoding="utf-8") as f:
        json.dump(kept, f)

    watcher = _Watcher(tmp_path, db)
    try:
        line = "[Watcher] td: its reading changed (scripts\\p.py) - 0 read file(s) unchecked, " + NOT_AGAIN
        assert watcher.until(lambda s: line in watcher.text(), 60) is not None and line in watcher.text()
        time.sleep(8)
        states = watcher.until(lambda s: False, 1)
        assert (states["td"], states["te"]) == ({"FAILED": 1}, {"FAILED": 1}), states
        assert "[Watcher] te: its reading changed" not in watcher.text(), "a table seen the first time was said"
        with open(stamps_path, encoding="utf-8") as f:
            assert "te" in json.load(f)
    finally:
        watcher.stop()
