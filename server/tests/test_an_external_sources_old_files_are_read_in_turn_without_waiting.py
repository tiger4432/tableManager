# -*- coding: utf-8 -*-
"""External sources' old files (총괄 5b5b76fc1, 소유자 「아직도 외부 저장소 안 읽어」 · 「ㄱ」). A real watcher process on a scratch
data root, a sqlite file and a stub API:
  big    40 files of three days ago   -> read without the one-second copy wait
  small  3 files of two days ago      -> taken in turn with big, so read among the first dispatches
  bm     w1/bmap.csv and w2/bmap.csv, the same bytes -> both read (each wafer's own file)
and a line «External sweep in progress: <source> looked x · dispatched y · z s» while the sweep runs.
Run 2 (a restart, sweeps every 2 s): small's s0.csv written again (same bytes, a new mtime) at its own path is read
again; the rest - the bmap copies too - are already read by the checklist: not dispatched, not hashed (소유자 10-21)."""
import ctypes
import http.server
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytestmark = pytest.mark.skipif(os.name != "nt", reason="sets a file's creation time (Windows)")

DRIVER = '''
import json, sys
sys.path.insert(0, "parsers")
import paths
from database.database import Base, engine
from database import models
models.init_dynamic_models(json.load(open(paths.config_path("table_config.json"), encoding="utf-8")))
Base.metadata.create_all(bind=engine)
import directory_watcher
directory_watcher.PERIODIC_SWEEP_INTERVAL_SECONDS = 2
directory_watcher.SWEEP_PROGRESS_SECONDS = 1
import run_watcher
run_watcher.main()
'''

WAFER_PLUGIN = '''
import csv, os
from pipeline_base import BasePipelineParser
class P(BasePipelineParser):
    @classmethod
    def match(cls, path):
        return path.endswith("bmap.csv")
    def parse(self, path):
        with open(path, newline="") as f:
            return [dict(r, lot=os.path.basename(os.path.dirname(path))) for r in csv.DictReader(f)]
'''
TABLE = {"business_key": "lot", "column_types": {"lot": "string", "val": "string"}, "display_columns": ["lot", "val"]}
DAY = 86400


def _age(path, seconds):
    """mtime and creation time `seconds` ago - a file that has sat on the share."""
    when = time.time() - seconds
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateFileW.restype = ctypes.c_void_p
    handle = kernel32.CreateFileW(str(path), 0x100, 0, None, 3, 0x80, None)      # FILE_WRITE_ATTRIBUTES, OPEN_EXISTING
    assert handle not in (None, ctypes.c_void_p(-1).value), path
    try:
        stamp = ctypes.c_ulonglong(int((when + 11644473600) * 10 ** 7))
        assert kernel32.SetFileTime(ctypes.c_void_p(handle), ctypes.byref(stamp), None, None)
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
    os.utime(path, (when, when))


def _write(path, text, age=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    if age is not None:
        _age(path, age)


class _Stub(http.server.BaseHTTPRequestHandler):
    def _ok(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    do_GET = do_POST = do_PUT = _ok

    def log_message(self, *args):
        pass


def _run(tmp, db, api, until, seconds=180):
    env = dict(os.environ, ASSY_DATA_ROOT=str(tmp / "data"), DATABASE_URL="sqlite:///" + db.as_posix(),
               API_BASE_URL=api, NO_PROXY="127.0.0.1,localhost", PYTHONIOENCODING="utf-8", PYTHONPATH=SERVER_DIR,
               DECOUPLED="True")
    env.pop("TESTING", None)
    driver = tmp / "driver.py"
    driver.write_text(DRIVER, encoding="utf-8")
    log_path = tmp / ("watcher_%d.log" % time.monotonic_ns())
    with open(log_path, "wb") as log:
        watcher = subprocess.Popen([sys.executable, str(driver)], cwd=SERVER_DIR, env=env, stdout=log,
                                   stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline and watcher.poll() is None:
                time.sleep(0.5)
                try:
                    with sqlite3.connect(str(db)) as c:
                        if until(c, log_path.read_text(encoding="utf-8", errors="replace")):
                            break
                except sqlite3.Error:
                    continue
        finally:
            watcher.kill()
            watcher.wait(30)
    return log_path.read_text(encoding="utf-8", errors="replace")


def _logs(c, table=None):
    sql = "SELECT id, table_name, status, filepath, created_at FROM file_ingestion_logs"
    return c.execute(sql + (" WHERE table_name = ?" if table else "") + " ORDER BY id", (table,) if table else ()).fetchall()


def test_old_files_are_read_in_turn_without_waiting(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    big, small, bm = (tmp_path / n for n in ("big", "small", "bm"))
    for i in range(40):
        _write(big / ("b%02d.csv" % i), "lot,val\nB%02d,old\n" % i, age=3 * DAY + i)
    for i in range(3):
        _write(small / ("s%d.csv" % i), "lot,val\nS%d,few\n" % i, age=2 * DAY)
    for wafer in ("w1", "w2"):
        _write(bm / wafer / "bmap.csv", "val\nsame bytes\n", age=2 * DAY)
    scripts = data / "ingestion_workspace" / "bm" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "p.py").write_text(WAFER_PLUGIN, encoding="utf-8")
    with open(data / "config" / "table_config.json", "w", encoding="utf-8") as f:
        json.dump({"big": TABLE, "small": TABLE, "bm": TABLE}, f)
    with open(data / "config" / "ingestion_settings.json", "w", encoding="utf-8") as f:
        json.dump({"external_sources": [{"path": str(big), "table_name": "big", "options": {"glob": "*.csv"}},
                                        {"path": str(small), "table_name": "small", "options": {"glob": "*.csv"}},
                                        {"path": str(bm), "table_name": "bm", "options": {"glob": "**/bmap.csv"}}]}, f)
    db = tmp_path / "box.db"
    api = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % api.server_address[1]
    try:
        said = _run(tmp_path, db, url, lambda c, _log: len(_logs(c)) >= 45)
        with sqlite3.connect(str(db)) as c:
            logs = _logs(c)
            assert [r[2] for r in logs] == ["SUCCESS"] * 45, [r[1:4] for r in logs]
            order = [r[1] for r in logs]
            assert max(i for i, t in enumerate(order) if t == "small") < 9, order        # in turn, not behind big
            assert sorted(c.execute("SELECT lot, val FROM bm").fetchall()) == [("w1", "same bytes"), ("w2", "same bytes")]
            first, last = (time.mktime(time.strptime(r[4][:19], "%Y-%m-%d %H:%M:%S"))
                           for r in (logs[0], logs[-1]))
        print("files per second: %.2f (45 files in %.0f s)" % (45 / max(last - first, 1), last - first))
        assert last - first < 0.5 * 45, "a file waited for a copy that cannot be running"
        progress = re.findall(r"External sweep in progress: (big@\S+) looked (\d+) · dispatched (\d+) · \d+ s", said)
        assert progress, said[-3000:]

        # run 2: a restart; s0.csv written again with the same bytes at its own path
        _write(small / "s0.csv", "lot,val\nS0,few\n")
        swept = []

        def eight_seconds_of_sweeps_after_the_first(_c, log):     # the periodic sweep (2 s) says no line when idle
            if "External sweep:" in log and not swept:
                swept.append(time.monotonic())
            return bool(swept) and time.monotonic() - swept[0] > 8

        said = _run(tmp_path, db, url, eight_seconds_of_sweeps_after_the_first, seconds=90)
        assert swept, said[-3000:]
        with sqlite3.connect(str(db)) as c:          # s0.csv saved again: read again (소유자 10-21 체크리스트), the rest not
            assert len(_logs(c)) == 46 and _logs(c)[45][1] == "small", [r[1:4] for r in _logs(c)[45:]]
        assert re.search(r"New file detected: \S+s0\.csv", said), "s0.csv was not looked at again"
        ended, *later = re.findall(r"External sweep: (\d+) candidate binding\(s\) - (\d+) already read, (\d+) dispatched",
                                   said)
        print("after the restart: %s candidates, %s already read, %s dispatched" % ended)
        assert ended == ("45", "44", "1"), ended                         # s0.csv only - it was written again
        assert later and set(later) == {("45", "45", "0")}, later        # then every sweep: all already read
        assert not re.findall(r"New file detected: \S+bmap\.csv", said)
    finally:
        api.shutdown()
