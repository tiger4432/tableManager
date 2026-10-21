# -*- coding: utf-8 -*-
"""An external source's `max_depth` (소유자 10-21 「와처 max depth 지정하게 해, 적은 경로부터」): the written path is 0,
a folder below it 1. `recursive` widened into it - false is 0, true or unwritten is to the end.

  the fold            recursive false = max_depth 0 · recursive true = unwritten       -> the same spec
  refused             -1 · 1.5 · true · "1" · recursive and max_depth disagreeing      -> named
  the seat            max_depth 1, files at 0/1/2/3                                    -> taken 0 and 1
  reading             max_depth written or changed                                     -> no new reading
  a real watcher      max_depth 1: two read, the depth-3 folder never listed, the line says why; an event at depth
                      2 -> not read, at depth 1 -> read; max_depth taken out -> the rest read
"""
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

from directory_watcher import IngestionHandler, validate_external_source_specs
from ingestion import reread
from tests.test_a_failed_external_file_retries_on_its_own_handler import env  # noqa: F401
from tests.test_a_file_read_is_checked_by_its_path_and_table import PLUGIN, SERVER_DIR, TABLE, _Stub, _write
from tests.test_external_source_watcher import TABLES


def _specs(tmp_path, **raw):
    (tmp_path / "external").mkdir(exist_ok=True)
    return validate_external_source_specs({"external_sources": [dict(
        {"path": str(tmp_path / "external"), "table_name": "void_obs", "parser": "voids_json",
         "options": {"glob": "*.json"}}, **raw)]}, TABLES, str(tmp_path / "ingestion_workspace"))


def test_recursive_folds_into_max_depth(tmp_path):
    assert _specs(tmp_path, recursive=False) == _specs(tmp_path, max_depth=0)
    assert _specs(tmp_path, recursive=True) == _specs(tmp_path) == _specs(tmp_path, max_depth=None)
    assert _specs(tmp_path)[0][0]["max_depth"] is None
    assert _specs(tmp_path, recursive=True, max_depth=2)[0][0]["max_depth"] == 2


@pytest.mark.parametrize("raw,said", [
    ({"max_depth": -1}, "max_depth must be a whole number 0 or more (0: the path's own files), got -1."),
    ({"max_depth": 1.5}, "max_depth must be a whole number 0 or more (0: the path's own files), got 1.5."),
    ({"max_depth": True}, "max_depth must be a whole number 0 or more (0: the path's own files), got True."),
    ({"max_depth": "1"}, "max_depth must be a whole number 0 or more (0: the path's own files), got '1'."),
    ({"recursive": False, "max_depth": 2}, ": recursive False and max_depth 2 disagree - write max_depth only."),
    ({"recursive": True, "max_depth": 0}, ": recursive True and max_depth 0 disagree - write max_depth only."),
])
def test_a_max_depth_is_refused_by_name(tmp_path, raw, said):
    specs, errors = _specs(tmp_path, **raw)
    assert specs == [] and errors == ["external_sources[0]" + ("." if said.startswith("max_depth") else "") + said]


def test_the_seat_takes_files_to_the_depth_only(tmp_path):
    specs, _errors = _specs(tmp_path, max_depth=1)
    workspace = tmp_path / "ingestion_workspace" / "void_obs"
    (workspace / "archives").mkdir(parents=True)
    handler = IngestionHandler(str(workspace), None, str(workspace / "archives"), default_table_name="void_obs")
    handler.register_external_source(specs[0])
    files = [_write(tmp_path / "external" / rel, "{}") for rel in ("v.json", "a/v.json", "a/b/v.json", "a/b/c/v.json")]
    assert [handler.external_source_context(path) is not None for path in files] == [True, True, False, False]


def test_a_max_depth_is_no_new_reading(tmp_path):
    source = {"path": str(tmp_path), "table_name": "ta", "options": {"glob": "*.csv"}}
    on = reread.reading_of("ta", {}, [source], str(tmp_path))
    assert reread.reading_of("ta", {}, [dict(source, max_depth=1)], str(tmp_path)) == on
    assert reread.reading_of("ta", {}, [dict(source, max_depth=3)], str(tmp_path)) == on


# ── a real watcher ────────────────────────────────────────────────────────────────────────────────────────────────────

DRIVER = '''
import json, os, sys
sys.path.insert(0, "parsers")
_real, _listed = os.scandir, open(sys.argv[1], "a", encoding="utf-8")
def _scandir(path="."):
    _listed.write(os.path.abspath(str(path)) + "\\n")
    _listed.flush()
    return _real(path)
os.scandir = _scandir
import paths
from database.database import Base, engine
from database import models
models.init_dynamic_models(json.load(open(paths.config_path("table_config.json"), encoding="utf-8")))
Base.metadata.create_all(bind=engine)
import run_watcher
run_watcher.main()
'''


def test_a_real_watcher_never_walks_below_max_depth(tmp_path):
    data, share = tmp_path / "data", tmp_path / "share"
    (data / "config").mkdir(parents=True)
    with open(data / "config" / "table_config.json", "w", encoding="utf-8") as f:
        json.dump({"ta": TABLE}, f)
    scripts = data / "ingestion_workspace" / "ta" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "p.py").write_text(PLUGIN, encoding="utf-8")
    source = {"path": str(share), "table_name": "ta", "options": {"glob": "*.csv"}}
    settings = data / "config" / "ingestion_settings.json"
    settings.write_text(json.dumps({"external_sources": [dict(source, max_depth=1)]}), encoding="utf-8")
    for n, rel in enumerate(("d0.csv", "a/d1.csv", "a/b/d2.csv", "a/b/c/d3.csv")):
        _write(share / rel, "lot,val\nL%d,v\n" % n)

    api = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    db = tmp_path / "box.db"
    run_env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + db.as_posix(),
                   API_BASE_URL="http://127.0.0.1:%d" % api.server_address[1], NO_PROXY="127.0.0.1,localhost",
                   PYTHONIOENCODING="utf-8", PYTHONPATH=SERVER_DIR, DECOUPLED="True")
    run_env.pop("TESTING", None)
    driver, listed, log_path = tmp_path / "driver.py", tmp_path / "listed.txt", tmp_path / "watcher.log"
    driver.write_text(DRIVER, encoding="utf-8")
    log = open(log_path, "ab")
    watcher = subprocess.Popen([sys.executable, str(driver), str(listed)], cwd=SERVER_DIR, env=run_env, stdout=log,
                               stderr=subprocess.STDOUT)

    def text():
        return re.sub(r"\x1b\[[0-9;]*m", "", log_path.read_text(encoding="utf-8", errors="replace"))

    def reads():
        try:
            with sqlite3.connect(str(db)) as c:
                return sorted(r[0] for r in c.execute("SELECT filename FROM file_ingestion_logs WHERE status = 'SUCCESS'"))
        except sqlite3.Error:
            return []

    def until(holds, seconds=60):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            assert watcher.poll() is None, text()[-3000:]
            if holds():
                return True
            time.sleep(0.5)
        return False

    try:
        assert until(lambda: "External source ta@" in text()), text()[-3000:]
        assert until(lambda: reads() == ["d0.csv", "d1.csv"]), reads()
        assert re.search(r"External source ta@[^\n]*: 2 file\(s\) looked at - outside the root 0 · name not matched 0 · "
                         r"not a file 0 · stat failed 0 · folders below max_depth 1 · folders not listed 0 · "
                         r"already read 0 · dispatched 2", text()), text()[-3000:]
        opened = {os.path.normcase(p) for p in listed.read_text(encoding="utf-8").splitlines()}
        assert os.path.normcase(str(share / "a")) in opened                              # the recorder records
        assert not [p for p in opened if p.startswith(os.path.normcase(str(share / "a" / "b")))]

        _write(share / "a" / "b" / "e2.csv", "lot,val\nE2,v\n")                         # an event at depth 2
        _write(share / "a" / "e1.csv", "lot,val\nE1,v\n")                               # and at depth 1
        assert until(lambda: "e1.csv" in reads()), reads()
        time.sleep(3)
        assert reads() == ["d0.csv", "d1.csv", "e1.csv"]

        settings.write_text(json.dumps({"external_sources": [source]}), encoding="utf-8")       # taken out
        assert until(lambda: reads() == ["d0.csv", "d1.csv", "d2.csv", "d3.csv", "e1.csv", "e2.csv"]), reads()
    finally:
        watcher.kill()
        watcher.wait(30)
        log.close()
        api.shutdown()
