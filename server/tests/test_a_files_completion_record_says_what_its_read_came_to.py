# -*- coding: utf-8 -*-
"""A file's completion record says what its read came to (총괄 e390600d6): rows read · new · changed · unchanged ·
refused, the reader, the source, and for a failure its one-line reason and the frame it broke in. A real watcher on a
scratch root, a sqlite file and a stub API, started on a file_ingestion_logs WITHOUT those columns: the boot schema
sync adds them, the records carry them, and the file list route reads them.
  tp  standard reader: 3 rows + 1 with a blank key, then the file again with one value changed
  tf  a plugin that raises -> FAILED, reason and «p.py:<line>»"""
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
RAISING = '''from pipeline_base import BasePipelineParser
class P(BasePipelineParser):
    @classmethod
    def match(cls, path):
        return True
    def parse(self, path):
        raise RuntimeError("the probe cannot read this")
'''
OLD_SHAPE = ('CREATE TABLE file_ingestion_logs (id INTEGER PRIMARY KEY, filename VARCHAR, filepath VARCHAR, '
             'table_name VARCHAR, status VARCHAR(20), error_message VARCHAR, retry_count INTEGER, '
             'created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)')
TABLE = {"business_key": "lot", "column_types": {"lot": "string", "val": "string"}, "display_columns": ["lot", "val"]}
RESULT = ("rows_read", "rows_new", "rows_changed", "rows_unchanged", "rows_refused", "reader", "source", "reason",
          "failed_at", "took_seconds")


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


def _run(tmp, db, api, until, seconds=120):
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
                        if until(c):
                            break
                except sqlite3.Error:
                    continue
        finally:
            watcher.kill()
            watcher.wait(30)
    return log_path.read_text(encoding="utf-8", errors="replace")


def _records(c):
    cols = [r[1] for r in c.execute("PRAGMA table_info(file_ingestion_logs)")]
    if "rows_read" not in cols:
        return []
    return c.execute("SELECT table_name, status, %s FROM file_ingestion_logs ORDER BY id" % ", ".join(RESULT)).fetchall()


def test_a_files_completion_record_says_what_its_read_came_to(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    share, failing = tmp_path / "share", tmp_path / "failing"
    share.mkdir()
    failing.mkdir()
    (share / "good.csv").write_text("lot,val\nL1,a\nL2,b\nL3,c\n,d\n", encoding="utf-8")
    (failing / "f.csv").write_text("lot,val\nF1,x\n", encoding="utf-8")
    scripts = data / "ingestion_workspace" / "tf" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "p.py").write_text(RAISING, encoding="utf-8")
    raise_line = RAISING.splitlines().index('        raise RuntimeError("the probe cannot read this")') + 1
    with open(data / "config" / "table_config.json", "w", encoding="utf-8") as f:
        json.dump({"tp": TABLE, "tf": TABLE}, f)
    with open(data / "config" / "ingestion_settings.json", "w", encoding="utf-8") as f:
        json.dump({"external_sources": [{"path": str(share), "table_name": "tp", "options": {"glob": "*.csv"}},
                                        {"path": str(failing), "table_name": "tf", "options": {"glob": "*.csv"}}]}, f)
    db = tmp_path / "box.db"
    with sqlite3.connect(str(db)) as c:
        c.execute(OLD_SHAPE)                                   # a database from before the columns
    api = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % api.server_address[1]
    try:
        said = _run(tmp_path, db, url, lambda c: len(_records(c)) >= 2)
        with sqlite3.connect(str(db)) as c:
            records = _records(c)
        assert records, said[-3000:]
        by_table = {r[0]: r for r in records}
        assert by_table["tp"][1:11] == ("SUCCESS", 3, 3, 0, 0, 1, "standard", str(share), None, None), by_table["tp"]
        assert 0 <= by_table["tp"][11] < 30 and 0 <= by_table["tf"][11] < 30, (by_table["tp"], by_table["tf"])
        status, *result = by_table["tf"][1:]
        assert (status, result[:5]) == ("FAILED", [None] * 5), by_table["tf"]
        assert result[5:9] == ["p.py::P", str(failing),
                              "ValueError: Plugin p.py::P could not read 'f.csv': the probe cannot read this",
                              "p.py:%d in parse" % raise_line], by_table["tf"]

        # the file again, one value changed: a new record of new · changed · unchanged
        time.sleep(1.1)
        (share / "good.csv").write_text("lot,val\nL1,a\nL2,B\nL3,c\n,d\n", encoding="utf-8")
        _run(tmp_path, db, url, lambda c: len([r for r in _records(c) if r[0] == "tp"]) >= 2)
        with sqlite3.connect(str(db)) as c:
            again = [r for r in _records(c) if r[0] == "tp"][-1]
        assert again[1:7] == ("SUCCESS", 3, 0, 1, 2, 1), again
    finally:
        api.shutdown()

    # the file list route reads the columns
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    sys.path.insert(0, SERVER_DIR)
    import main

    session = sessionmaker(bind=create_engine("sqlite:///" + db.as_posix()))()
    try:
        listed = main.get_file_ingestion_logs(status="ALL", page=1, limit=10, db=session)["data"]
    finally:
        session.close()
    assert {row["table_name"]: row["reader"] for row in listed} == {"tp": "standard", "tf": "p.py::P"}, listed
    assert all(set(RESULT) <= set(row) for row in listed)
