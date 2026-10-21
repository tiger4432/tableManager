# -*- coding: utf-8 -*-
"""An external source switched off or changed in ingestion_settings.json takes hold with no restart, for that source
only (총괄 10-21, 소유자 「외부 저장소 별로 끄기」 · 「받는 파일을 log.txt 로 바꿨는데 voids.json 이 계속 돎」 · 「다른 작동은
유지하고 해당 타깃만 멈춰야 해」).

A real watcher on a scratch data root and a sqlite file, a stub API. Source A (table ta) takes voids.json, source B
(table tb) takes *.csv, and ta's raws/ is watched too:
  A's filename saved as log.txt     -> a new voids.json under A is not read, a new log.txt is; B and raws/ go on
  A saved enabled: false            -> nothing new under A is read; B and raws/ go on
  A saved enabled: true             -> A's file left meanwhile is read
"""
import http.server
import json
import os
import sqlite3
import subprocess
import sys
import threading
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
PLUGIN = '''
import csv
from pipeline_base import BasePipelineParser
class P(BasePipelineParser):
    @classmethod
    def match(cls, path):
        return True
    def parse(self, path):
        with open(path, newline="") as f:
            return [dict(r) for r in csv.DictReader(f)]
'''
TABLE = {"business_key": "lot", "column_types": {"lot": "string", "val": "string"}, "display_columns": ["lot", "val"]}


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


def _write(path, lot):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("lot,val\n%s,v\n" % lot)


def test_a_source_saved_off_or_changed_stops_alone_with_no_restart(tmp_path):
    data, share_a, share_b = tmp_path / "data", tmp_path / "share_a", tmp_path / "share_b"
    (data / "config").mkdir(parents=True)
    with open(data / "config" / "table_config.json", "w", encoding="utf-8") as f:
        json.dump({"ta": TABLE, "tb": TABLE}, f)
    for table in ("ta", "tb"):
        scripts = data / "ingestion_workspace" / table / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "p.py").write_text(PLUGIN, encoding="utf-8")
    raws = data / "ingestion_workspace" / "ta" / "raws"
    raws.mkdir(parents=True)
    source_a = {"path": str(share_a), "table_name": "ta", "options": {"filename": "voids.json"}}
    source_b = {"path": str(share_b), "table_name": "tb", "options": {"glob": "*.csv"}}
    settings = data / "config" / "ingestion_settings.json"

    def save(a):
        with open(settings, "w", encoding="utf-8") as f:
            json.dump({"external_sources": [a, source_b]}, f)

    save(source_a)
    _write(share_a / "w0" / "voids.json", "A0")
    _write(share_b / "b0.csv", "B0")
    db = tmp_path / "box.db"
    api = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + db.as_posix(),
               API_BASE_URL="http://127.0.0.1:%d" % api.server_address[1], NO_PROXY="127.0.0.1,localhost",
               PYTHONIOENCODING="utf-8", PYTHONPATH=SERVER_DIR, DECOUPLED="True")
    env.pop("TESTING", None)
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER, encoding="utf-8")
    log_path = tmp_path / "watcher.log"
    log = open(log_path, "wb")
    watcher = subprocess.Popen([sys.executable, str(driver)], cwd=SERVER_DIR, env=env, stdout=log,
                               stderr=subprocess.STDOUT)

    def read():
        """{(table, path below its share or raws): status}."""
        try:
            with sqlite3.connect(str(db)) as c:
                rows = c.execute("SELECT table_name, filepath, status FROM file_ingestion_logs").fetchall()
        except sqlite3.Error:
            return {}
        out = {}
        for table, path, status in rows:
            for root in (share_a, share_b):
                if os.path.normcase(path).startswith(os.path.normcase(str(root))):
                    out[(table, os.path.relpath(path, root).replace("\\", "/"))] = status
            if os.path.normcase(path).startswith(os.path.normcase(str(raws.parent))):
                out[(table, os.path.basename(path))] = status        # raws/, or archives/ once read
        return out

    def until(holds, seconds=60):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            assert watcher.poll() is None, log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
            if holds(read()):
                break
            time.sleep(0.5)
        return read()

    try:
        got = until(lambda r: ("ta", "w0/voids.json") in r and ("tb", "b0.csv") in r)
        assert got.get(("ta", "w0/voids.json")) == "SUCCESS" and got.get(("tb", "b0.csv")) == "SUCCESS", got

        # A takes log.txt now - saved, no restart
        save(dict(source_a, options={"filename": "log.txt"}))
        time.sleep(6)                                              # the poller's ticks hear the save
        _write(share_a / "w1" / "voids.json", "A1")
        _write(share_a / "w1" / "log.txt", "A1L")
        _write(share_b / "b1.csv", "B1")
        _write(raws / "r1.csv", "R1")
        got = until(lambda r: {("ta", "w1/log.txt"), ("tb", "b1.csv"), ("ta", "r1.csv")} <= set(r))
        time.sleep(5)
        got = read()
        assert ("ta", "w1/voids.json") not in got, got
        assert got.get(("ta", "w1/log.txt")) == got.get(("tb", "b1.csv")) == got.get(("ta", "r1.csv")) == "SUCCESS", got

        # A switched off: nothing new under A; B and raws/ go on
        save(dict(source_a, options={"filename": "log.txt"}, enabled=False))
        time.sleep(6)
        _write(share_a / "w2" / "log.txt", "A2")
        _write(share_b / "b2.csv", "B2")
        _write(raws / "r2.csv", "R2")
        got = until(lambda r: {("tb", "b2.csv"), ("ta", "r2.csv")} <= set(r))
        time.sleep(5)
        got = read()
        assert ("ta", "w2/log.txt") not in got, got
        assert got.get(("tb", "b2.csv")) == got.get(("ta", "r2.csv")) == "SUCCESS", got

        # A switched on again: what was left meanwhile is read
        save(dict(source_a, options={"filename": "log.txt"}))
        got = until(lambda r: ("ta", "w2/log.txt") in r)
        assert got.get(("ta", "w2/log.txt")) == "SUCCESS", got
        assert ("ta", "w1/voids.json") not in got, got
    finally:
        watcher.kill()
        watcher.wait(30)
        log.close()
        api.shutdown()
