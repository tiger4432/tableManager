# -*- coding: utf-8 -*-
"""An external source reads its files as raws/ does (lead 10-20, owner 「기본 파서도 있는데 왜 파서 없다고 막아」 · 「ㅇㅇ 해」).

A real watcher process (`run_watcher.main`) on a scratch data root and a sqlite file. Run 1: table ta reads a root with
its plugin. Run 2 (a restart) adds tables to the same root and to others:
  tb  no plugin                      -> the standard parser reads the files
  tc  no plugin, std_parse false     -> refused at registration, saying both
  td  a plugin that takes no file    -> the standard parser
  te  a glob nothing under its root matches -> one WARNING
  tf  a plugin that raises reading   -> the file FAILED with the read's sentence, not «Failed to load plugin script»
  tg, th  each a plugin importing its own helper.py (same name, other value) -> each table its own value
"""
import json
import os
import sqlite3
import subprocess
import sys
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

CSV_PLUGIN = '''
import csv
from pipeline_base import BasePipelineParser
class P(BasePipelineParser):
    @classmethod
    def match(cls, path):
        return path.endswith(".csv")
    def parse(self, path):
        with open(path, newline="") as f:
            return [dict(r, val=%s) for r in csv.DictReader(f)]
'''
DECLINING = '''
from pipeline_base import BasePipelineParser
class P(BasePipelineParser):
    @classmethod
    def match(cls, path):
        return False
    def parse(self, path):
        raise AssertionError("never asked")
'''
RAISING = '''
from pipeline_base import BasePipelineParser
class P(BasePipelineParser):
    @classmethod
    def match(cls, path):
        return True
    def parse(self, path):
        raise RuntimeError("the probe cannot read this")
'''
HELPED = "import helper\n" + CSV_PLUGIN % "helper.VALUE"
TABLE = {"business_key": "lot", "column_types": {"lot": "string", "val": "string"}, "display_columns": ["lot", "val"]}


def _plugin(data, table, source, helper=None):
    scripts = os.path.join(data, "ingestion_workspace", table, "scripts")
    os.makedirs(scripts, exist_ok=True)
    with open(os.path.join(scripts, "p.py"), "w", encoding="utf-8") as f:
        f.write(source)
    if helper is not None:
        with open(os.path.join(scripts, "helper.py"), "w", encoding="utf-8") as f:
            f.write("VALUE = %r\n" % helper)


def _csvs(folder, n, stem):
    os.makedirs(folder, exist_ok=True)
    for i in range(n):
        with open(os.path.join(folder, "%s%d.csv" % (stem, i)), "w", encoding="utf-8") as f:
            f.write("lot,val\n%s%d,file\n" % (stem, i))


def _settings(data, tables, bindings):
    with open(os.path.join(data, "config", "table_config.json"), "w", encoding="utf-8") as f:
        json.dump(tables, f)
    with open(os.path.join(data, "config", "ingestion_settings.json"), "w", encoding="utf-8") as f:
        json.dump({"external_sources": [{"path": root, "table_name": table, "options": {"glob": glob}}
                                        for table, root, glob in bindings]}, f)


def _run(tmp, db, until, seconds=150):
    """The watcher until `until(sqlite)` holds (or the time is up) -> its log text."""
    env = dict(os.environ, ASSY_DATA_ROOT=str(tmp / "data"), DATABASE_URL="sqlite:///" + db.as_posix(),
               API_BASE_URL="http://127.0.0.1:9", PYTHONIOENCODING="utf-8", PYTHONPATH=SERVER_DIR, DECOUPLED="True")
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
                time.sleep(1)
                try:
                    with sqlite3.connect(str(db)) as c:
                        if until(c):
                            break
                except sqlite3.Error:
                    continue
            time.sleep(3)                      # a sweep after the last file, for the warning's «once»
        finally:
            watcher.kill()
            watcher.wait(30)
    return log_path.read_text(encoding="utf-8", errors="replace")


def _logs(c, table):
    return sorted(tuple(r) for r in c.execute(
        "SELECT status, coalesce(error_message, '') FROM file_ingestion_logs WHERE table_name = ?", (table,)))


def _vals(c, table):
    return sorted(tuple(r) for r in c.execute('SELECT lot, val FROM "%s"' % table))


def test_an_external_source_reads_as_raws_does(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    share, other, failing, helpers = (str(tmp_path / n) for n in ("share", "other", "failing", "helpers"))
    _csvs(share, 2, "S")
    _csvs(failing, 1, "F")
    _csvs(helpers, 1, "H")
    os.makedirs(other)
    with open(os.path.join(other, "notes.txt"), "w", encoding="utf-8") as f:
        f.write("not a csv")
    db = tmp_path / "box.db"

    # run 1: ta reads the share with its plugin
    _plugin(str(data), "ta", CSV_PLUGIN % '"plugin"')
    _settings(str(data), {"ta": TABLE}, [("ta", share, "*.csv")])
    _run(tmp_path, db, lambda c: len(_logs(c, "ta")) >= 2)
    with sqlite3.connect(str(db)) as c:
        assert _vals(c, "ta") == [("S0", "plugin"), ("S1", "plugin")]

    # run 2: the restart with the new tables
    tables = {name: TABLE for name in ("ta", "tb", "td", "te", "tf", "tg", "th")}
    tables["tc"] = dict(TABLE, std_parse=False)
    _plugin(str(data), "td", DECLINING)
    _plugin(str(data), "tf", RAISING)
    _plugin(str(data), "tg", HELPED, helper="g")
    _plugin(str(data), "th", HELPED, helper="h")
    _settings(str(data), tables, [("ta", share, "*.csv"), ("tb", share, "*.csv"), ("tc", share, "*.csv"),
                                  ("td", share, "*.csv"), ("te", other, "*.csv"), ("tf", failing, "*.csv"),
                                  ("tg", helpers, "*.csv"), ("th", helpers, "*.csv")])
    said = _run(tmp_path, db, lambda c: (len(_logs(c, "tb")) >= 2 and len(_logs(c, "td")) >= 2
                                         and _logs(c, "tf") and _logs(c, "tg") and _logs(c, "th")))

    with sqlite3.connect(str(db)) as c:
        assert _vals(c, "tb") == [("S0", "file"), ("S1", "file")], "no plugin: the standard parser"
        assert _vals(c, "td") == [("S0", "file"), ("S1", "file")], "the plugin took none: the standard parser"
        assert _vals(c, "ta") == [("S0", "plugin"), ("S1", "plugin")], "ta is not read again"
        assert _logs(c, "tc") == [] and _logs(c, "te") == []
        [(status, error)] = _logs(c, "tf")
        assert status == "FAILED" and "p.py::P could not read 'F0.csv': the probe cannot read this" in error
        assert (_vals(c, "tg"), _vals(c, "th")) == ([("H0", "g")], [("H0", "h")]), "each table its own helper"
    refused = [line for line in said.splitlines() if "External source config rejected" in line]
    assert len(refused) == 1 and "'tc'" in refused[0] and "std_parse is false" in refused[0], refused
    unmatched = [line for line in said.splitlines() if "none matched" in line]
    assert len(unmatched) == 1 and "1 file(s) under the root, none matched ['*.csv']" in unmatched[0], unmatched
    assert "te@" in unmatched[0]
    assert "Failed to load plugin script" not in said
