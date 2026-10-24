# -*- coding: utf-8 -*-
"""A re-read whose files fail one after another stops for its (table, source) (owner 10-24 «외부 저장소 다시 읽을 때 연속
파일 3 번 에러 나면 멈추면 안 됨?» · «잘못된 파서로 계속 에러만 띄우면서 돌잖아» · «근데 근본 불량 파일들도 있네», 총괄).

Real processes - the API (uvicorn) and the watcher (run_watcher.main) - on one sqlite file and a scratch data root;
ta reads share_a (10 files), tb share_b (2), each with its plugin; reread_max_files 2:
  ta's plugin broken             its read files unchecked, the sweep reads 3, fails them, stops - the rest unchecked
  Read all again on share_a      the press lets the stop go; the retry door fails 3 and stops - 7 still waiting
  Read all again on share_b      read while ta's 7 wait - more of them than one turn picks
  ta's plugin fails f6-f9        the reading change lets go; read files come first - no stop, every file read
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
import directory_watcher
directory_watcher.PERIODIC_SWEEP_INTERVAL_SECONDS = 2
import run_watcher
run_watcher.main()
'''
API = '''
import sys
import uvicorn
sys.path.insert(1, "parsers")
import main
uvicorn.run(main.app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
'''
GOOD = '''
import csv
from pipeline_base import BasePipelineParser
class P(BasePipelineParser):
    @classmethod
    def match(cls, path):
        return path.endswith(".csv")
    def parse(self, path):
        with open(path, newline="") as f:
            return [dict(r) for r in csv.DictReader(f)]
'''
BROKEN = GOOD.replace("            return [dict(r) for r in csv.DictReader(f)]",
                      "            raise KeyError('lot is not a column this parser knows')")
SOME_BAD = GOOD.replace("        with open(path", "        if path[-6:] in ('f6.csv', 'f7.csv', 'f8.csv', 'f9.csv'):\n"
                                              "            raise KeyError('a bad file')\n        with open(path")
TABLE = {"business_key": "lot", "column_types": {"lot": "string", "val": "string"}, "display_columns": ["lot", "val"]}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _plugin(data, table, source):
    scripts = data / "ingestion_workspace" / table / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "p.py").write_text(source, encoding="utf-8")


def _records(db, table):
    with sqlite3.connect(str(db)) as c:
        return [r[0] for r in c.execute("SELECT status FROM file_ingestion_logs WHERE table_name = ? ORDER BY id",
                                        (table,))]


def _checklist(db, table):
    with sqlite3.connect(str(db)) as c:
        return {"waiting": c.execute("SELECT count(*) FROM file_checklist WHERE table_name = ? AND status = "
                                     "'PENDING_RETRY'", (table,)).fetchone()[0],
                "unchecked": c.execute("SELECT count(*) FROM file_checklist WHERE table_name = ? AND file_mtime IS "
                                       "NULL AND status != 'PENDING_RETRY'", (table,)).fetchone()[0]}


def _until(holds, seconds, *processes):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        assert all(p.poll() is None for p in processes), "a process ended"
        try:
            if holds():
                return True
        except sqlite3.Error:
            pass
        time.sleep(0.5)
    return False


def test_a_reread_that_fails_file_after_file_stops_for_its_source(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    shares = {name: tmp_path / name for name in ("share_a", "share_b")}
    for share in shares.values():
        share.mkdir()

    def files(name, n):
        for i in range(n):
            (shares[name] / ("f%d.csv" % i)).write_text("lot,val\n%s%d,x\n" % (name[-1], i), encoding="utf-8")
    files("share_a", 10)
    (data / "config" / "table_config.json").write_text(json.dumps({"ta": TABLE, "tb": TABLE}), encoding="utf-8")
    (data / "config" / "ingestion_settings.json").write_text(json.dumps({
        "reread_max_files": 2, "external_sources": [
            {"path": str(shares["share_a"]), "table_name": "ta", "options": {"glob": "*.csv"}},
            {"path": str(shares["share_b"]), "table_name": "tb", "options": {"glob": "*.csv"}}]}), encoding="utf-8")
    _plugin(data, "ta", GOOD)
    _plugin(data, "tb", GOOD)
    db = tmp_path / "box.db"
    port = _free_port()
    base = "http://127.0.0.1:%d" % port
    env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + db.as_posix(), DECOUPLED="True",
               API_BASE_URL=base, PYTHONIOENCODING="utf-8", PYTHONPATH=SERVER_DIR)
    for name in ("TESTING", "ASSY_ADMIN_TOKEN"):
        env.pop(name, None)
    for name, body in (("schema.py", SCHEMA), ("watcher.py", WATCHER), ("api.py", API)):
        (tmp_path / name).write_text(body, encoding="utf-8")
    subprocess.run([sys.executable, str(tmp_path / "schema.py")], cwd=SERVER_DIR, env=env, check=True,
                   capture_output=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def ask(path, method="GET"):
        with opener.open(urllib.request.Request(base + path, method=method, data=b"" if method == "POST" else None),
                         timeout=60) as reply:
            return json.loads(reply.read())

    def read_all_again(share):
        return ask("/admin/file-ingestion/retry-failed?" + urllib.parse.urlencode(
            {"folder": str(share), "statuses": "SUCCESS,FAILED"}), "POST")

    def said():
        return (tmp_path / "watcher.log").read_text(encoding="utf-8", errors="replace")

    def stops():
        return [line for line in said().splitlines() if "Stopped: " in line and "left as they are" in line]

    logs = {name: open(tmp_path / ("%s.log" % name), "wb") for name in ("api", "watcher")}
    api = subprocess.Popen([sys.executable, str(tmp_path / "api.py"), str(port)], cwd=SERVER_DIR, env=env,
                           stdout=logs["api"], stderr=subprocess.STDOUT)
    watcher = subprocess.Popen([sys.executable, str(tmp_path / "watcher.py")], cwd=SERVER_DIR, env=env,
                               stdout=logs["watcher"], stderr=subprocess.STDOUT)
    try:
        assert _until(lambda: len(_records(db, "ta")) == 10, 120, api, watcher), "the first reads: %s" % (
            _records(db, "ta"),)
        files("share_b", 2)                    # after ta's: tb's checklist rows come after every one of ta's
        assert _until(lambda: len(_records(db, "tb")) == 2, 60, api, watcher), "tb's first reads"
        assert set(_records(db, "ta")) == {"SUCCESS"}, "CANARY: the good plugin reads every file"

        # 1 the unchecked sweep's way: ta's plugin broken - its read files unchecked, the sweep fails 3 and stops
        _plugin(data, "ta", BROKEN)
        assert _until(lambda: len(stops()) == 1, 90, api, watcher), "the sweep never stopped: %s" % _records(db, "ta")
        time.sleep(8)                                          # sweeps after the stop: nothing more of ta read
        failed = _records(db, "ta")[10:]
        assert 3 <= len(failed) <= 5 and set(failed) == {"FAILED"}, failed
        assert _checklist(db, "ta")["unchecked"] == 10 - len(failed), _checklist(db, "ta")
        # (the child's stdout spells «·» in the console's code page - the words around it are compared)
        assert all(words in stops()[0] for words in (
            "[Watcher] ta ", str(shares["share_a"]) + ": Stopped: 3 failed in a row - ValueError: Plugin p.py::P could not read 'f2.csv': "
            "'lot is not a column this parser knows' - waiting 0 ", "unchecked 7 left as they are")), stops()
        tables = ask("/admin/file-ingestion/tables")["data"]
        [line] = [s for t in tables if t["table_name"] == "ta" for s in t["sources"] if s.get("stopped")]
        assert line["source"] == str(shares["share_a"]) and line["stopped"] == (
            "Stopped: 3 failed in a row - ValueError: Plugin p.py::P could not read 'f2.csv': 'lot is not a column this parser knows'"), line

        # 2 the retry door's way: Read all again lets the stop go; 3 fail, it stops - the rest wait
        before = len(_records(db, "ta"))
        assert read_all_again(shares["share_a"])["status"] == "success"
        assert _until(lambda: len(stops()) == 2, 90, api, watcher), "the retry door never stopped"
        time.sleep(8)
        assert _records(db, "ta")[before:] == ["FAILED"] * 3, _records(db, "ta")[before:]
        assert _checklist(db, "ta")["waiting"] == 7, _checklist(db, "ta")
        assert "waiting 7 " in stops()[1] and "unchecked 0 left as they are" in stops()[1], stops()

        # 3 ta's 7 waiting - older than tb's rows, more than one turn's 2 - do not hold tb's
        assert read_all_again(shares["share_b"])["status"] == "success"
        assert _until(lambda: len(_records(db, "tb")) == 4, 60, api, watcher), \
            "tb's re-read never ran behind ta's waiting: %s" % _records(db, "tb")
        assert _checklist(db, "ta")["waiting"] == 7, "ta's still wait"

        # 4 bad files among good ones (owner «근본 불량 파일들도 있네»): the plugin fails f6-f9 - the change lets go,
        #   the files read first keep it going to the end: every file read, the four bad ones failed
        _plugin(data, "ta", SOME_BAD)

        def ta_done():
            with sqlite3.connect(str(db)) as c:
                states = dict(c.execute("SELECT filepath, status FROM file_checklist WHERE table_name = 'ta'"))
            return (_checklist(db, "ta") == {"waiting": 0, "unchecked": 0}
                    and sorted(os.path.basename(p) for p, s in states.items() if s == "FAILED")
                    == ["f6.csv", "f7.csv", "f8.csv", "f9.csv"] and len(states) == 10)
        assert _until(ta_done, 120, api, watcher), "the re-read did not go to the end: %s %s" % (
            _checklist(db, "ta"), _records(db, "ta")[-12:])
        assert len(stops()) == 2, stops()
        assert "the re-read stop let go (a person asked a re-read)" in said()
        assert "the re-read stop let go (its reading changed)" in said()
    finally:
        for process in (api, watcher):
            process.kill()
            process.wait(30)
        for log in logs.values():
            log.close()
