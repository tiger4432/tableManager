# -*- coding: utf-8 -*-
"""Files already there when a table's reading changes wait for a press; new files are read; the watcher pauses (소유자
10-21 운영 마비 「외장 저장소를 다시 다 읽음」 · 「막 도는 거 막아」 · 「고친 것만 선택적 읽기」, 총괄 290e22ac0).

A real watcher and a real API process on a scratch data root and a sqlite file. Table tw reads a share and its raws/:
  start, nothing kept on the box           -> the readings kept, nothing waits
  the share bound to tw (a restart)        -> its 5 old files WAITING, none read
  a display cell changed                   -> no reading change, nothing more waits
  Read under LOT1 (the retry door)         -> its 3 read, LOT2's 2 still WAITING
  new.csv · bad.csv                        -> read by themselves (bad.csv FAILED)
  Pause; new2.csv, Read under LOT2         -> none read; Resume -> all read
  the plugin changed and raws/old.csv dropped while down, a restart
                                           -> bad.csv stays FAILED (one line), raws/old.csv WAITING, nothing read
  a restart                                -> nothing read, the waiting stay
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
import csv, os
from pipeline_base import BasePipelineParser
class P(BasePipelineParser):
    @classmethod
    def match(cls, path):
        return path.endswith(".csv")
    def parse(self, path):
        if "bad" in os.path.basename(path) and %r:
            raise RuntimeError("the plugin cannot read it")
        with open(path, newline="") as f:
            return [dict(r) for r in csv.DictReader(f)]
'''
TABLE = {"business_key": "lot", "column_types": {"lot": "string", "val": "string"}, "display_columns": ["lot", "val"]}
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # the box's system proxy is not ours


def _write(path, lot, age=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("lot,val\n%s,v\n" % lot)
    if age is not None:
        when = time.time() - age
        os.utime(path, (when, when))


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Box:
    def __init__(self, tmp):
        self.tmp, self.data, self.db = tmp, tmp / "data", tmp / "box.db"
        self.share, self.scripts = tmp / "share", self.data / "ingestion_workspace" / "tw" / "scripts"
        self.raws = self.data / "ingestion_workspace" / "tw" / "raws"
        self.port = _free_port()
        self.env = dict(os.environ, ASSY_DATA_ROOT=str(self.data), DATABASE_URL="sqlite:///" + self.db.as_posix(),
                        API_BASE_URL="http://127.0.0.1:%d" % self.port, NO_PROXY="127.0.0.1,localhost",
                        PYTHONIOENCODING="utf-8", PYTHONPATH=SERVER_DIR, DECOUPLED="True")
        self.env.pop("TESTING", None)
        self.logs, self.watcher, self.api = [], None, None

    def config(self, tables, sources):
        (self.data / "config").mkdir(parents=True, exist_ok=True)
        with open(self.data / "config" / "table_config.json", "w", encoding="utf-8") as f:
            json.dump(tables, f)
        with open(self.data / "config" / "ingestion_settings.json", "w", encoding="utf-8") as f:
            json.dump({"reread_max_files": 50, "external_sources": sources}, f)

    def plugin(self, fails_bad):
        self.scripts.mkdir(parents=True, exist_ok=True)
        (self.scripts / "p.py").write_text(PLUGIN % fails_bad, encoding="utf-8")

    def _start(self, name, body, *args):
        path = self.tmp / ("%s.py" % name)
        path.write_text(body, encoding="utf-8")
        log_path = self.tmp / ("%s_%d.log" % (name, time.monotonic_ns()))
        log = open(log_path, "wb")
        self.logs.append((log_path, log))
        return subprocess.Popen([sys.executable, str(path)] + list(args), cwd=SERVER_DIR, env=self.env, stdout=log,
                                stderr=subprocess.STDOUT)

    def schema(self):
        self._start("schema", SCHEMA).wait(120)

    def start_api(self):
        self.api = self._start("api", API, str(self.port))
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            assert self.api.poll() is None, self.text()
            try:
                OPENER.open("http://127.0.0.1:%d/health" % self.port, timeout=5).read()
                return
            except urllib.error.HTTPError:
                return
            except OSError:
                time.sleep(0.5)
        raise AssertionError("the API never came up")

    def start_watcher(self):
        self.watcher = self._start("watcher", WATCHER)

    def stop_watcher(self):
        self.watcher.kill()
        self.watcher.wait(30)

    def post(self, path, **params):
        url = "http://127.0.0.1:%d%s?%s" % (self.port, path, urllib.parse.urlencode(params))
        request = urllib.request.Request(url, data=b"{}", method="POST", headers={"Content-Type": "application/json"})
        with OPENER.open(request, timeout=60) as reply:
            return json.loads(reply.read())

    def rows(self):
        """{file name: [its states, oldest first]} of tw."""
        out = {}
        try:
            with sqlite3.connect(str(self.db)) as c:
                for name, state in c.execute("SELECT filename, status FROM file_ingestion_logs WHERE table_name = 'tw'"
                                             " ORDER BY id"):
                    out.setdefault(name, []).append(state)
        except sqlite3.Error:
            pass
        return out

    def until(self, holds, seconds=90):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            assert self.watcher.poll() is None, self.text()
            rows = self.rows()
            if holds(rows):
                return rows
            time.sleep(0.5)
        return self.rows()

    def text(self):
        return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p, _log in self.logs)

    def close(self):
        for process in (self.watcher, self.api):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(30)
        for _path, log in self.logs:
            log.close()


def _now(rows):
    """{file name: its newest state}."""
    return {name: states[-1] for name, states in rows.items()}


def _read(rows):
    return sorted(name for name, states in rows.items() if "SUCCESS" in states or "FAILED" in states)


def test_files_there_when_a_reading_changes_wait_and_new_ones_are_read(tmp_path):
    box = _Box(tmp_path)
    source = {"path": str(box.share), "table_name": "tw", "options": {"glob": "**/*.csv"}}
    old = {"a1.csv": "LOT1", "a2.csv": "LOT1", "a3.csv": "LOT1", "b1.csv": "LOT2", "b2.csv": "LOT2"}
    for name, lot in old.items():
        _write(box.share / lot / name, lot, age=86400)
    box.config({"tw": TABLE}, [])
    box.plugin(True)
    box.raws.mkdir(parents=True)
    owed_path = box.data / "config" / "watcher_waiting_owed.json"
    stamps_path = box.data / "config" / "watcher_reading_stamps.json"
    try:
        box.schema()
        box.start_api()

        # start: nothing kept on this box - the first reading is only kept
        box.start_watcher()
        deadline = time.monotonic() + 60
        while not stamps_path.exists() and time.monotonic() < deadline:
            time.sleep(0.5)
        assert stamps_path.exists(), box.text()[-3000:]
        assert box.rows() == {} and not owed_path.exists()
        box.stop_watcher()

        # the share bound (a restart): its old files wait, none read
        box.config({"tw": TABLE}, [source])
        box.start_watcher()
        rows = box.until(lambda r: len(r) == 5)
        time.sleep(5)
        rows = box.rows()
        assert _now(rows) == dict.fromkeys(old, "WAITING"), rows
        assert json.loads(owed_path.read_text(encoding="utf-8")) == {}, "the full sweep left the table owing"

        # a display cell is no reading: nothing more waits
        box.config({"tw": dict(TABLE, display_columns=["val", "lot"])}, [source])
        time.sleep(8)                                              # the poller's ticks
        assert json.loads(owed_path.read_text(encoding="utf-8")) == {} and len(box.rows()) == 5

        # Read under LOT1 - the retry door, its 3 only
        said = box.post("/admin/file-ingestion/retry-failed", read_by="tw", folder=str(box.share / "LOT1"),
                        statuses="WAITING")
        assert said["count"] == 3, said
        rows = box.until(lambda r: _now(r).get("a3.csv") == "SUCCESS" and _now(r).get("a1.csv") == "SUCCESS"
                         and _now(r).get("a2.csv") == "SUCCESS")
        assert _now(rows) == {"a1.csv": "SUCCESS", "a2.csv": "SUCCESS", "a3.csv": "SUCCESS",
                              "b1.csv": "WAITING", "b2.csv": "WAITING"}, rows

        # new files: read by themselves
        _write(box.share / "LOT3" / "new.csv", "LOT3")
        _write(box.share / "LOT3" / "bad.csv", "LOT3")
        rows = box.until(lambda r: "new.csv" in _read(r) and "bad.csv" in _read(r))
        assert _now(rows)["new.csv"] == "SUCCESS" and _now(rows)["bad.csv"] == "FAILED", rows

        # Pause: a new file and a Read are not read; Resume reads them
        assert box.post("/admin/watcher/pause", reason="probe")["paused"]["reason"] == "probe"
        _write(box.share / "LOT3" / "new2.csv", "LOT3")
        said = box.post("/admin/file-ingestion/retry-failed", read_by="tw", folder=str(box.share / "LOT2"),
                        statuses="WAITING")
        assert said["count"] == 2, said
        time.sleep(10)
        rows = box.rows()
        assert "new2.csv" not in rows and _now(rows)["b1.csv"] == "PENDING_RETRY", rows
        assert box.post("/admin/watcher/resume")["paused"] is None
        rows = box.until(lambda r: _now(r).get("new2.csv") == "SUCCESS" and _now(r).get("b1.csv") == "SUCCESS"
                         and _now(r).get("b2.csv") == "SUCCESS")
        assert _now(rows)["new2.csv"] == "SUCCESS" and _now(rows)["b2.csv"] == "SUCCESS", rows
        box.stop_watcher()

        # the plugin changed and a file dropped in raws/ while down: a restart reads none of it
        box.plugin(False)                                          # it would read bad.csv now
        _write(box.raws / "old.csv", "RAW", age=86400)
        before = box.rows()
        box.start_watcher()
        rows = box.until(lambda r: "old.csv" in r)
        time.sleep(8)
        rows = box.rows()
        assert _now(rows)["old.csv"] == "WAITING" and rows["bad.csv"] == before["bad.csv"] == ["FAILED"], rows
        assert "[Watcher] tw: its reading changed (scripts\\p.py) - 1 failed file(s) wait" in box.text()
        box.stop_watcher()

        # a restart: nothing read, the waiting stay
        before = box.rows()
        box.start_watcher()
        time.sleep(15)
        assert box.rows() == before
    finally:
        box.close()
