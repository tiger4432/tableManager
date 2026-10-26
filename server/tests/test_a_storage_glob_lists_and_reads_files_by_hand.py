# -*- coding: utf-8 -*-
"""A storage's glob list and its Read these (소유자 10-26 «아직 안 읽은 파일 옛날 거 경로 지정해서 읽게 하려면?» · «읽은 거
무관하게 glob 리스트 인제션 페이지에 해 주면 좋겠는데»).

A real watcher process and a real API process on a scratch data root and a sqlite file. An external source switched
on before two new files and after five old ones (12f46f32f: the old ones are read by hand only):
  list      GET /admin/file-ingestion/glob - old/x*.csv: the three, BEFORE_SWITCH_ON, never read; read or not,
            new/n1.csv: SUCCESS and when (총괄 10-26 «이미 읽었나(언제)»)
  read      POST read-now with the glob - the three handed, read by the watcher; /read-now/left counts them down and
            says each one's state and read time; a file that fails says its error's first line («넘긴 뒤 결과»)
  again     a read file picked by the glob is read again (a second log row)
  refused   a glob that leaves the root (.. · an absolute path) 400; a storage the table has not 404
"""
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
import json
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
PLUGIN = '''
import csv
from pipeline_base import BasePipelineParser
class P(BasePipelineParser):
    @classmethod
    def match(cls, path):
        return path.endswith(".csv")
    def parse(self, path):
        if path.endswith("z1.csv"):
            raise ValueError("z1 is broken\\nthe traceback goes on")
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
'''
TABLE = {"business_key": "lot", "column_types": {"lot": "string", "val": "string"}, "display_columns": ["lot", "val"]}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ask(opener, url, body=None):
    request = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                     method="GET" if body is None else "POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with opener.open(request, timeout=60) as reply:
            return reply.status, json.loads(reply.read())
    except urllib.error.HTTPError as reply:
        return reply.code, json.loads(reply.read() or b"{}")


def _csv(path, lot, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("lot,val\n%s,file\n" % lot)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def _wait(what, until, seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        said = until()
        if said:
            return said
        time.sleep(1)
    raise AssertionError("waited %d s for %s" % (seconds, what))


def test_a_storage_glob_lists_and_reads_files_by_hand(tmp_path):
    data, share = tmp_path / "data", str(tmp_path / "share")
    (data / "config").mkdir(parents=True)
    scripts = data / "ingestion_workspace" / "gt" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "p.py").write_text(PLUGIN, encoding="utf-8")
    (data / "config" / "table_config.json").write_text(json.dumps({"gt": TABLE}), encoding="utf-8")
    (data / "config" / "ingestion_settings.json").write_text(json.dumps(
        {"external_sources": [{"path": share, "table_name": "gt", "options": {"glob": "**/*.csv"}}]}), encoding="utf-8")
    switched_on = time.time() - 60
    old = ["x1", "x2", "x3", "y1", "y2", "z1"]
    for lot in old:
        _csv(os.path.join(share, "old", lot + ".csv"), lot, mtime=switched_on - 3600)
    for lot in ("n1", "n2"):
        _csv(os.path.join(share, "new", lot + ".csv"), lot)
    source_id = "gt@" + os.path.normcase(os.path.abspath(share))
    (data / "config" / "watcher_switched_on.json").write_text(json.dumps({source_id: switched_on}), encoding="utf-8")

    db = tmp_path / "box.db"
    env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + db.as_posix(), DECOUPLED="True",
               API_BASE_URL="http://127.0.0.1:9", PYTHONIOENCODING="utf-8", PYTHONPATH=SERVER_DIR)
    env.pop("TESTING", None)
    env.pop("ASSY_ADMIN_TOKEN", None)
    for name, text in (("schema.py", SCHEMA), ("watcher.py", WATCHER), ("api.py", API)):
        (tmp_path / name).write_text(text, encoding="utf-8")
    subprocess.run([sys.executable, str(tmp_path / "schema.py")], cwd=SERVER_DIR, env=env, check=True)
    port = _free_port()
    base = "http://127.0.0.1:%d/admin/file-ingestion" % port
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # the box's system proxy is not ours
    logs = {name: open(tmp_path / (name + ".log"), "wb") for name in ("watcher", "api")}
    watcher = subprocess.Popen([sys.executable, str(tmp_path / "watcher.py")], cwd=SERVER_DIR, env=env,
                               stdout=logs["watcher"], stderr=subprocess.STDOUT)
    api = subprocess.Popen([sys.executable, str(tmp_path / "api.py"), str(port)], cwd=SERVER_DIR, env=env,
                           stdout=logs["api"], stderr=subprocess.STDOUT)

    def lots():
        with sqlite3.connect(str(db)) as c:
            return sorted(r[0] for r in c.execute("SELECT lot FROM gt"))

    def reads_of(name):
        with sqlite3.connect(str(db)) as c:
            return c.execute("SELECT count(*) FROM file_ingestion_logs WHERE filename = ? AND status = 'SUCCESS'",
                             (name,)).fetchone()[0]

    def glob(pattern, source=share):
        query = urllib.parse.urlencode({"table": "gt", "source": source, "pattern": pattern})
        return _ask(opener, base + "/glob?" + query)

    try:
        _wait("the new files read by themselves", lambda: lots() == ["n1", "n2"])
        _wait("the API", lambda: glob("old/*.csv")[0] == 200, seconds=90)
        status, listed = glob("old/x*.csv")
        assert status == 200, listed
        assert (listed["matched"], listed["truncated"], listed["by_status"]) == (3, False, {"BEFORE_SWITCH_ON": 3})
        assert [(f["rel"], f["read_at"]) for f in listed["files"]] == [
            ("old/x1.csv", None), ("old/x2.csv", None), ("old/x3.csv", None)]
        n1 = glob("**/n1.csv")[1]
        assert n1["by_status"] == {"SUCCESS": 1}, "read or not - a read file is listed too"
        assert n1["files"][0]["read_at"], n1

        query = urllib.parse.urlencode({"table": "gt", "source": share, "pattern": "old/x*.csv"})
        status, handed = _ask(opener, base + "/read-now?" + query, body={})
        assert status == 200 and handed["handed"] == 3, handed
        _wait("the three read by the watcher", lambda: lots() == ["n1", "n2", "x1", "x2", "x3"])
        status, left = _ask(opener, base + "/read-now/left", body={"ids": handed["ids"]})
        assert (status, left["handed"], left["left"], left["read"]) == (200, 3, 0, 3), left
        assert sorted((os.path.basename(f["path"]), f["status"], bool(f["read_at"]), f["error"])
                      for f in left["files"]) == [(n, "SUCCESS", True, None) for n in ("x1.csv", "x2.csv", "x3.csv")]
        assert glob("old/*.csv")[1]["by_status"] == {"BEFORE_SWITCH_ON": 3, "SUCCESS": 3}, "y1 · y2 · z1 by hand"

        query = urllib.parse.urlencode({"table": "gt", "source": share, "pattern": "old/z1.csv"})
        status, broken = _ask(opener, base + "/read-now?" + query, body={})
        assert status == 200 and broken["handed"] == 1, broken
        left = _wait("z1 failed", lambda: (lambda said: said if said["failed"] == 1 else None)(
            _ask(opener, base + "/read-now/left", body={"ids": broken["ids"]})[1]))
        (failed,) = left["files"]
        assert failed["status"] == "FAILED" and failed["read_at"], failed
        assert "z1 is broken" in failed["error"] and "traceback goes on" not in failed["error"], failed

        query = urllib.parse.urlencode({"table": "gt", "source": share, "pattern": "new/n1.csv"})
        status, again = _ask(opener, base + "/read-now?" + query, body={})
        assert status == 200 and again["handed"] == 1, again
        _wait("n1 read again", lambda: reads_of("n1.csv") == 2)

        assert glob("../share/*.csv")[0] == 400
        assert glob("C:/data/*.csv")[0] == 400
        status, unknown = glob("*.csv", source=str(tmp_path / "elsewhere"))
        assert status == 404 and "has no storage" in unknown["detail"], unknown
    finally:
        for process in (watcher, api):
            process.kill()
            process.wait(30)
        for log in logs.values():
            log.close()
