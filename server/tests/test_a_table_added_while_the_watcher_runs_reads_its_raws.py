# -*- coding: utf-8 -*-
"""A table added to table_config.json while the watcher runs gets its raws/ made and watched - a CSV put there is
read, no Reload button and no restart (lead 10-24: a table save writes no SYSTEM_RELOAD, e6a0bdbbd).

A real watcher process (`run_watcher.main`) on a scratch data root and a sqlite file: ta read first (the watcher
is up), then tb written into the table config, then a CSV into tb's raws/ the moment it exists.
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCHEMA = '''
import json, sys
sys.path.insert(0, "parsers")
from database.database import Base, engine
from database import models
models.init_dynamic_models(json.load(open(sys.argv[1], encoding="utf-8")))
Base.metadata.create_all(bind=engine)
'''
DRIVER = '''
import sys
sys.path.insert(0, "parsers")
import run_watcher
run_watcher.main()
'''
TABLE = {"business_key": "lot", "column_types": {"lot": "string", "val": "string"}, "display_columns": ["lot", "val"]}
SECONDS = 30


def _csv(folder, lot):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, lot + ".csv"), "w", encoding="utf-8") as f:
        f.write("lot,val\n%s,file\n" % lot)


def _config(data, names):
    with open(os.path.join(data, "config", "table_config.json"), "w", encoding="utf-8") as f:
        json.dump({name: TABLE for name in names}, f)


def _until(db, pred, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            with sqlite3.connect(str(db)) as c:
                if pred(c):
                    return True
        except sqlite3.Error:
            pass
        time.sleep(0.5)
    return False


def _read(table):
    return lambda c: c.execute("SELECT count(*) FROM file_ingestion_logs WHERE table_name = ? AND status = 'SUCCESS'",
                               (table,)).fetchone()[0] > 0


def test_a_table_added_while_the_watcher_runs_reads_its_raws(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    db = tmp_path / "box.db"
    env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + db.as_posix(),
               API_BASE_URL="http://127.0.0.1:9", PYTHONIOENCODING="utf-8", PYTHONPATH=SERVER_DIR, DECOUPLED="True")
    env.pop("TESTING", None)
    env.pop("ASSY_ADMIN_TOKEN", None)
    both = tmp_path / "both.json"
    both.write_text(json.dumps({"ta": TABLE, "tb": TABLE}), encoding="utf-8")
    (tmp_path / "schema.py").write_text(SCHEMA, encoding="utf-8")
    (tmp_path / "driver.py").write_text(DRIVER, encoding="utf-8")
    # the API makes tb's physical table on its save; here before the watcher starts (the watcher does not on sqlite)
    subprocess.run([sys.executable, str(tmp_path / "schema.py"), str(both)], cwd=SERVER_DIR, env=env, check=True)
    _config(str(data), ["ta"])
    workspace = data / "ingestion_workspace"
    log_path = tmp_path / "watcher.log"
    with open(log_path, "wb") as log:
        watcher = subprocess.Popen([sys.executable, str(tmp_path / "driver.py")], cwd=SERVER_DIR, env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            assert _until(db, lambda c: (workspace / "ta" / "raws").is_dir(), 60), "the watcher never made ta's raws/"
            _csv(str(workspace / "ta" / "raws"), "A1")
            assert _until(db, _read("ta"), 60), "the watcher never read ta's file"

            assert not (workspace / "tb").exists()
            began = time.monotonic()
            _config(str(data), ["ta", "tb"])
            made = _until(db, lambda c: (workspace / "tb" / "raws").is_dir(), SECONDS)
            if made:
                _csv(str(workspace / "tb" / "raws"), "B1")
            read = made and _until(db, _read("tb"), SECONDS)
            took = time.monotonic() - began
        finally:
            watcher.kill()
            watcher.wait(30)
    said = log_path.read_text(encoding="utf-8", errors="replace")
    assert made, "tb's raws/ was never made - the table was added, nobody looked:\n" + said[-3000:]
    assert read, "tb's file was never read:\n" + said[-3000:]
    print("[gate] table added -> its CSV read: %.1f s" % took)
    with sqlite3.connect(str(db)) as c:
        assert c.execute('SELECT lot, val FROM "tb"').fetchall() == [("B1", "file")]
