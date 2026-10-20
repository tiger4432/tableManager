# -*- coding: utf-8 -*-
"""A file's completion record names the transaction its rows were written under (lead 10-20) - one per file, a read
resumed after a restart included. A real watcher on a scratch root, a sqlite file and a stub API.
  ts  a 3-row file, read once                          -> the record's tx = the tx of every audit row of ts
  tb  a 20,000-row file, the watcher killed after its first chunks, started again -> it resumes from the checkpoint,
      and every audit row of tb, before and after, is one tx = the record's = the checkpoint's"""
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
TABLE = {"business_key": "lot", "column_types": {"lot": "string", "val": "string"}, "display_columns": ["lot", "val"]}
BIG = 20000


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


def _start(tmp, db, api):
    env = dict(os.environ, ASSY_DATA_ROOT=str(tmp / "data"), DATABASE_URL="sqlite:///" + db.as_posix(),
               API_BASE_URL=api, NO_PROXY="127.0.0.1,localhost", PYTHONIOENCODING="utf-8", PYTHONPATH=SERVER_DIR,
               DECOUPLED="True")
    env.pop("TESTING", None)
    driver = tmp / "driver.py"
    driver.write_text(DRIVER, encoding="utf-8")
    log = open(tmp / ("watcher_%d.log" % time.monotonic_ns()), "wb")
    return subprocess.Popen([sys.executable, str(driver)], cwd=SERVER_DIR, env=env, stdout=log,
                            stderr=subprocess.STDOUT), log


def _until(db, holds, seconds=180, step=0.2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with sqlite3.connect(str(db), timeout=5) as c:
                answer = holds(c)
                if answer:
                    return answer
        except sqlite3.Error:
            pass
        time.sleep(step)
    return None


def _stop(process, log):
    process.kill()
    process.wait(30)
    log.close()


def _record(c, table):
    return c.execute("SELECT status, transaction_id FROM file_ingestion_logs WHERE table_name = ? "
                     "ORDER BY id DESC LIMIT 1", (table,)).fetchone()


def _audit_txs(c, table):
    return sorted(r[0] for r in c.execute("SELECT DISTINCT transaction_id FROM audit_logs WHERE table_name = ?",
                                          (table,)))


def test_a_files_rows_are_one_transaction_on_its_record(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    with open(data / "config" / "table_config.json", "w", encoding="utf-8") as f:
        json.dump({"ts": TABLE, "tb": TABLE}, f)
    for table, n in (("ts", 3), ("tb", BIG)):
        raws = data / "ingestion_workspace" / table / "raws"
        raws.mkdir(parents=True)
        with open(raws / ("%s.csv" % table), "w", encoding="utf-8") as f:
            f.write("lot,val\n" + "".join("%s%d,v%d\n" % (table, i, i) for i in range(n)))
    db = tmp_path / "box.db"
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    api = "http://127.0.0.1:%d" % server.server_address[1]
    try:
        watcher, log = _start(tmp_path, db, api)
        try:
            small = _until(db, lambda c: _record(c, "ts") if (_record(c, "ts") or ("",))[0] == "SUCCESS" else None)
            assert small is not None and small[1], small
            # killed between chunks: the checkpoint has some rows of tb and not all
            part = _until(db, lambda c: c.execute(
                "SELECT processed_rows, transaction_id FROM file_ingestion_checkpoints WHERE table_name = 'tb' "
                "AND status = 'IN_PROGRESS' AND processed_rows >= 2000").fetchone(), step=0.05)
        finally:
            _stop(watcher, log)
        assert part is not None and part[0] < BIG, part
        with sqlite3.connect(str(db)) as c:
            assert _audit_txs(c, "ts") == [small[1]]
            assert _audit_txs(c, "tb") == [part[1]], "the first run wrote under one transaction"

        watcher, log = _start(tmp_path, db, api)
        try:
            done = _until(db, lambda c: _record(c, "tb") if (_record(c, "tb") or ("",))[0] == "SUCCESS" else None,
                          seconds=300)
        finally:
            _stop(watcher, log)
        assert done is not None, "the resumed read did not finish"
        with sqlite3.connect(str(db)) as c:
            assert c.execute("SELECT count(*) FROM tb").fetchone()[0] == BIG
            note = c.execute("SELECT note, transaction_id FROM file_ingestion_checkpoints WHERE table_name = 'tb'"
                             ).fetchone()
            assert _audit_txs(c, "tb") == [done[1]] == [part[1]] == [note[1]], (_audit_txs(c, "tb"), done, part, note)
    finally:
        server.shutdown()
