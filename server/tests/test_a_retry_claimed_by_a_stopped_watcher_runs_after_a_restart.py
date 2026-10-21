# -*- coding: utf-8 -*-
"""18a3bc5b7 ㄱ (소유자 10-21 「파일 리플레이는 펜딩에서 안 도는데」, 총괄): a Retry the watcher claimed (PENDING) and stopped
before its first checkpoint stood PENDING for good - `reclaim_stranded_claims` skips a claim with no checkpoint, and
the screen's Retry takes FAILED only. A real watcher process on a scratch data root, a sqlite file and a stub API:
run 1 reads e0.csv; the row is left PENDING with no checkpoint in progress (what a watcher killed right after its
claim leaves); run 2 (the restart) hands it back and reads it, and says so in one line."""
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


def _states(c):
    return c.execute("SELECT status FROM file_ingestion_logs ORDER BY id").fetchall()


def test_a_retry_claimed_by_a_stopped_watcher_runs_after_a_restart(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    ext = tmp_path / "ext"
    ext.mkdir()
    (ext / "e0.csv").write_text("lot,val\nE0,v\n", encoding="utf-8")
    with open(data / "config" / "table_config.json", "w", encoding="utf-8") as f:
        json.dump({"tx": TABLE}, f)
    with open(data / "config" / "ingestion_settings.json", "w", encoding="utf-8") as f:
        json.dump({"external_sources": [{"path": str(ext), "table_name": "tx", "options": {"glob": "*.csv"}}],
                   "retry_reclaim_after_seconds": 1}, f)
    db = tmp_path / "box.db"
    api = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % api.server_address[1]
    try:
        _run(tmp_path, db, url, lambda c: _states(c) == [("SUCCESS",)])
        with sqlite3.connect(str(db)) as c:
            assert _states(c) == [("SUCCESS",)]
            c.execute("UPDATE file_ingestion_logs SET status = 'PENDING', updated_at = '2026-01-01 00:00:00'")
            assert c.execute("SELECT count(*) FROM file_ingestion_checkpoints WHERE status = 'IN_PROGRESS'"
                             ).fetchone() == (0,)

        said = _run(tmp_path, db, url, lambda c: _states(c) != [("PENDING",)] and _states(c) != [("PENDING_RETRY",)],
                    seconds=60)
        with sqlite3.connect(str(db)) as c:
            assert _states(c) == [("SUCCESS",)], said[-3000:]
        assert "[Retry] 1 retry claim(s) left by the last run handed again" in said
        assert "Retry succeeded for log ID #1." in said
    finally:
        api.shutdown()
