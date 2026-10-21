# -*- coding: utf-8 -*-
"""«Read now» (총괄 aaf19d0ca, 소유자 「이거 강제로 못 돌리냐고 · 그냥 와처 인식한 걸로 하면 되잖아」): a path handed to the
Retry door under the source that owns its folder - read as the watcher would have, the source's layer name, even a
file the watcher did not pick. A real watcher; `scripts/replay_ingestion.py --now` calls the same `reread.read_now`.

  notes.txt     the source's glob is *.csv                 -> preview «name not matched» · read now under the source
  deep/d.csv    the source's max_depth is 1, it is 2 down   -> preview «below max_depth» · read now
  raws/r.csv    read at the start                           -> preview «already read» · read again on its own row
  elsewhere     under no raws folder and no source root     -> refused, the sentence says what to write
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

from tests.test_a_file_read_is_checked_by_its_path_and_table import DRIVER, PLUGIN, SERVER_DIR, TABLE, _Stub, _write


def test_a_path_is_read_now_under_the_source_that_owns_its_folder(tmp_path):
    data, share = tmp_path / "data", tmp_path / "share"
    (data / "config").mkdir(parents=True)
    with open(data / "config" / "table_config.json", "w", encoding="utf-8") as f:
        json.dump({"ta": TABLE, "tb": TABLE}, f)
    for table in ("ta", "tb"):
        scripts = data / "ingestion_workspace" / table / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "p.py").write_text(PLUGIN, encoding="utf-8")
        (data / "ingestion_workspace" / table / "raws").mkdir(parents=True)
    with open(data / "config" / "ingestion_settings.json", "w", encoding="utf-8") as f:
        json.dump({"archive_processed_files": False, "external_sources": [
            {"path": str(share), "table_name": "ta", "options": {"glob": "*.csv"}, "max_depth": 1}]}, f)
    notes = _write(share / "a" / "notes.txt", "lot,val\nNOTES,v\n")
    deep = _write(share / "a" / "deep" / "d.csv", "lot,val\nDEEP,v\n")
    raws = _write(data / "ingestion_workspace" / "tb" / "raws" / "r.csv", "lot,val\nRAWS,v\n")
    elsewhere = _write(tmp_path / "elsewhere" / "e.csv", "lot,val\nE,v\n")

    db = tmp_path / "box.db"
    api = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + db.as_posix(),
               API_BASE_URL="http://127.0.0.1:%d" % api.server_address[1], NO_PROXY="127.0.0.1,localhost",
               PYTHONIOENCODING="utf-8", PYTHONPATH=SERVER_DIR, DECOUPLED="True")
    env.pop("TESTING", None)
    driver, log_path = tmp_path / "driver.py", tmp_path / "watcher.log"
    driver.write_text(DRIVER, encoding="utf-8")

    def rows():
        try:
            with sqlite3.connect(str(db)) as c:
                return c.execute("SELECT id, filename, table_name, status FROM file_ingestion_logs ORDER BY id").fetchall()
        except sqlite3.Error:
            return []

    def now(*paths, apply=True):
        args = [sys.executable, os.path.join("scripts", "replay_ingestion.py"), "--now"] + (["--apply"] if apply else [])
        for path in paths:
            args += ["--path", path]
        done = subprocess.run(args, cwd=SERVER_DIR, env=env, capture_output=True, text=True, encoding="utf-8")
        assert done.returncode == 0, done.stdout + done.stderr
        return done.stdout

    log = open(log_path, "ab")
    watcher = subprocess.Popen([sys.executable, str(driver)], cwd=SERVER_DIR, env=env, stdout=log,
                               stderr=subprocess.STDOUT)

    def until(holds, seconds=60):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            assert watcher.poll() is None, log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
            if holds():
                return True
            time.sleep(0.5)
        return False

    try:
        assert until(lambda: [r[1:] for r in rows()] == [("r.csv", "tb", "SUCCESS")]), rows()
        time.sleep(3)
        assert len(rows()) == 1, rows()                                 # the watcher picked neither share file

        said = now(notes, deep, raws, elsewhere, apply=False)
        assert "owner     : ta (%s) - name not matched" % share in said, said      # the sweep line's words
        assert "owner     : ta (%s) - below max_depth" % share in said, said
        assert "owner     : tb (raws) - already read" in said, said
        assert re.search(r"refused   : No table reads .*e\.csv: it is under no raws folder and no external source "
                         r"root - add an external source for its folder in ingestion_settings\.json", said), said
        assert len(rows()) == 1                                         # a preview writes nothing

        now(notes, deep, raws, elsewhere)
        assert until(lambda: sorted(r[1:] for r in rows()) == [("d.csv", "ta", "SUCCESS"), ("notes.txt", "ta", "SUCCESS"),
                                                               ("r.csv", "tb", "SUCCESS")]), rows()
        with sqlite3.connect(str(db)) as c:
            layers = {name for (name,) in c.execute("SELECT DISTINCT source_name FROM cell_sources")}
            assert c.execute("SELECT lot FROM ta ORDER BY lot").fetchall() == [("DEEP",), ("NOTES",)]
        for path in (notes, deep):                                      # the source's layer, as the watcher names it
            assert "external:workspace:" + os.path.realpath(path) in layers, layers
        text = log_path.read_text(encoding="utf-8", errors="replace")
        assert len(re.findall(r"Retry succeeded for log ID #1\.", text)) == 1      # raws/r.csv: its own row again
    finally:
        watcher.kill()
        watcher.wait(30)
        log.close()
        api.shutdown()


def test_a_row_whose_source_is_gone_is_refused_not_read_as_raws(tmp_path):
    import pytest

    from directory_watcher import IngestionHandler, SourceGone, validate_external_source_specs
    from tests.test_external_source_watcher import TABLES

    workspace, share, gone = tmp_path / "ws" / "void_obs", tmp_path / "share", tmp_path / "gone"
    (workspace / "archives").mkdir(parents=True)
    share.mkdir()
    specs, _errors = validate_external_source_specs({"external_sources": [{
        "path": str(share), "table_name": "void_obs", "parser": "voids_json", "options": {"glob": "*.json"}}]},
        TABLES, str(tmp_path / "ws"))
    handler = IngestionHandler(str(workspace), None, str(workspace / "archives"), default_table_name="void_obs")
    handler.register_external_source(specs[0])
    path = _write(share / "w" / "v.json", "{}")
    with pytest.raises(SourceGone) as refused:
        handler._parse_meta_for(path, source=str(gone))
    assert str(refused.value) == ("the source %s is not in ingestion_settings.json - owned now by: %s"
                                  % (gone, specs[0]["root"]))
    assert handler._parse_meta_for(path, source=str(share))["external_source"]["source_root"] == specs[0]["root"]
