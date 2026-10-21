# -*- coding: utf-8 -*-
"""«Read all again» (소유자 10-21 「다시 로드는 파일 인제션 창 이용하면 되잖아」, 총괄): every file a table read - in place,
archived - handed to the watcher through the one Retry door, the cap a pace and not a refusal.

A real API process and a real watcher process on a scratch data root and one sqlite file:
  ta  raws r0 · r1 · r2 (archived once read) and an external source ext with e0 · e1 (read in place)
  tb  raws b0 - the control
ta's rows are deleted, r2's archived file is taken off the disk; reread_max_files is 2. The page's ask
(retry-failed?read_by=ta&statuses=SUCCESS,FAILED,SKIPPED - no folder: the whole table) previews 4 files and 1 missing,
hands 4 although the cap is 2, and the watcher reads them all, two a turn: ta's rows come back but r2's, and tb is
not read again."""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = '''
import json, sys
sys.path.insert(0, "parsers")
import paths
from database.database import Base, engine
from database import models
models.init_dynamic_models(json.load(open(paths.config_path("table_config.json"), encoding="utf-8")))
Base.metadata.create_all(bind=engine)
'''
WATCHER = '''
import sys
sys.path.insert(0, "parsers")
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
TABLE = {"business_key": "lot", "column_types": {"lot": "string", "val": "string"}, "display_columns": ["lot", "val"]}
ALL = "SUCCESS,FAILED,SKIPPED"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ask(opener, url):
    try:
        with opener.open(urllib.request.Request(url, data=b"", method="POST"), timeout=60) as reply:
            return reply.status, json.loads(reply.read())
    except urllib.error.HTTPError as reply:
        return reply.code, reply.read().decode("utf-8", "replace")


def _until(db, cond, seconds, procs):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        assert all(p.poll() is None for p in procs), "a process ended"
        try:
            with sqlite3.connect(str(db)) as c:
                if cond(c):
                    return True
        except sqlite3.Error:
            pass
        time.sleep(0.5)
    return False


def _logs(c, table):
    return c.execute("SELECT filename, status FROM file_ingestion_logs WHERE table_name = ? ORDER BY id",
                     (table,)).fetchall()


def test_read_all_again_reads_a_table_s_files_in_place_and_archived_and_no_other(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    for table, names in (("ta", ("r0", "r1", "r2")), ("tb", ("b0",))):
        raws = data / "ingestion_workspace" / table / "raws"
        raws.mkdir(parents=True)
        for name in names:
            (raws / (name + ".csv")).write_text("lot,val\n%s,v\n" % name.upper(), encoding="utf-8")
    ext = tmp_path / "ext"
    ext.mkdir()
    for name in ("e0", "e1"):
        (ext / (name + ".csv")).write_text("lot,val\n%s,v\n" % name.upper(), encoding="utf-8")
    with open(data / "config" / "table_config.json", "w", encoding="utf-8") as f:
        json.dump({"ta": TABLE, "tb": TABLE}, f)
    with open(data / "config" / "ingestion_settings.json", "w", encoding="utf-8") as f:
        json.dump({"external_sources": [{"path": str(ext), "table_name": "ta", "options": {"glob": "*.csv"}}],
                   "reread_max_files": 2}, f)
    db = tmp_path / "box.db"
    port = _free_port()
    env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + db.as_posix(), DECOUPLED="True",
               API_BASE_URL="http://127.0.0.1:%d" % port, NO_PROXY="127.0.0.1,localhost", PYTHONIOENCODING="utf-8",
               PYTHONPATH=SERVER_DIR)
    env.pop("TESTING", None)
    for name, text in (("schema.py", SCHEMA), ("watcher.py", WATCHER), ("api.py", API)):
        (tmp_path / name).write_text(text, encoding="utf-8")
    subprocess.run([sys.executable, str(tmp_path / "schema.py")], cwd=SERVER_DIR, env=env, check=True)
    procs = []
    logs = [open(tmp_path / name, "wb") for name in ("api.log", "watcher.log")]
    try:
        procs.append(subprocess.Popen([sys.executable, str(tmp_path / "api.py"), str(port)], cwd=SERVER_DIR,
                                      env=dict(env, TESTING="True"), stdout=logs[0], stderr=subprocess.STDOUT))
        procs.append(subprocess.Popen([sys.executable, str(tmp_path / "watcher.py")], cwd=SERVER_DIR, env=env,
                                      stdout=logs[1], stderr=subprocess.STDOUT))
        assert _until(db, lambda c: [s for _f, s in _logs(c, "ta") + _logs(c, "tb")] == ["SUCCESS"] * 6, 180, procs), \
            (tmp_path / "watcher.log").read_text(encoding="utf-8", errors="replace")[-3000:]
        archives = data / "ingestion_workspace" / "ta" / "archives"
        r2 = [p for p in archives.rglob("*") if p.is_file() and p.name.startswith("r2")]
        assert len(r2) == 1, list(archives.rglob("*"))
        r2[0].unlink()
        with sqlite3.connect(str(db)) as c:
            assert c.execute("SELECT count(*) FROM ta").fetchone() == (5,)
            c.execute("DELETE FROM ta")
            c.execute("DELETE FROM cell_sources WHERE table_name = 'ta'")
            tb_before = c.execute("SELECT id, status, updated_at FROM file_ingestion_logs WHERE table_name = 'tb'"
                                  ).fetchall()

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base = "http://127.0.0.1:%d/admin/file-ingestion/retry-failed?" % port
        ask = urllib.parse.urlencode({"read_by": "ta", "statuses": ALL})
        assert _until(db, lambda c: True, 1, procs)
        deadline = time.monotonic() + 90
        while True:
            try:
                status, preview = _ask(opener, base + ask + "&preview=true")
                break
            except OSError:
                assert time.monotonic() < deadline, "the API never came up"
                time.sleep(0.5)
        assert status == 200, preview
        assert (preview["count"], preview["missing"], preview["limit"]) == (4, 1, 2), preview
        status, done = _ask(opener, base + ask)
        assert status == 200, done                                  # over the cap: handed all the same - a pace
        assert done["message"] == "4 file(s) handed to the watcher", done

        assert _until(db, lambda c: c.execute("SELECT count(*) FROM ta").fetchone() == (4,)
                      and not [s for _f, s in _logs(c, "ta") if s in ("PENDING_RETRY", "PENDING")], 180, procs), \
            (tmp_path / "watcher.log").read_text(encoding="utf-8", errors="replace")[-3000:]
        with sqlite3.connect(str(db)) as c:
            assert sorted(r[0] for r in c.execute("SELECT lot FROM ta")) == ["E0", "E1", "R0", "R1"]
            assert c.execute("SELECT id, status, updated_at FROM file_ingestion_logs WHERE table_name = 'tb'"
                             ).fetchall() == tb_before
    finally:
        for p in procs:
            p.kill()
            p.wait(30)
        for f in logs:
            f.close()
