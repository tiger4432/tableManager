# -*- coding: utf-8 -*-
"""총괄 10-21 (the file screen's watcher state): the watcher's «sources» lap carries what the process already holds -
each source registered and reached, the sentences sources were refused with, the last sweep's words from the dict its
log lines are said from, the read-files fill, the retries waiting. No new record: the heartbeat it beats anyway, read
through /runtime. A real watcher process.

  share     a.csv taken · notes.txt «name not matched» · deep/d.csv «below max_depth» (max_depth 0)
  gone      a source whose root is not there - registered, not reached
  bad       a source for a table nobody declared - refused, its sentence on the lap as in the log
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

from tests.test_a_file_read_is_checked_by_its_path_and_table import DRIVER, PLUGIN, SERVER_DIR, TABLE


def test_the_lap_says_what_the_sweep_line_says(tmp_path):
    data, share = tmp_path / "data", tmp_path / "share"
    (data / "config").mkdir(parents=True)
    with open(data / "config" / "table_config.json", "w", encoding="utf-8") as f:
        json.dump({"ta": TABLE}, f)
    scripts = data / "ingestion_workspace" / "ta" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "p.py").write_text(PLUGIN, encoding="utf-8")
    (share / "deep").mkdir(parents=True)
    (share / "a.csv").write_text("lot,val\nA,v\n", encoding="utf-8")
    (share / "notes.txt").write_text("lot,val\nN,v\n", encoding="utf-8")
    (share / "deep" / "d.csv").write_text("lot,val\nD,v\n", encoding="utf-8")
    with open(data / "config" / "ingestion_settings.json", "w", encoding="utf-8") as f:
        json.dump({"archive_processed_files": False, "external_sources": [
            {"path": str(share), "table_name": "ta", "options": {"glob": "*.csv"}, "max_depth": 0},
            {"path": str(tmp_path / "gone"), "table_name": "ta", "options": {"glob": "*.csv"}},
            {"path": str(share), "table_name": "nobody", "options": {"glob": "*.csv"}}]}, f)
    db = tmp_path / "box.db"
    env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + db.as_posix(),
               API_BASE_URL="http://127.0.0.1:9", NO_PROXY="127.0.0.1,localhost", PYTHONIOENCODING="utf-8",
               PYTHONPATH=SERVER_DIR, DECOUPLED="True")
    env.pop("TESTING", None)
    driver, log_path = tmp_path / "driver.py", tmp_path / "watcher.log"
    driver.write_text(DRIVER, encoding="utf-8")
    beat_path = data / "config" / "worker_heartbeats" / "watcher.json"
    log = open(log_path, "ab")
    watcher = subprocess.Popen([sys.executable, str(driver)], cwd=SERVER_DIR, env=env, stdout=log,
                               stderr=subprocess.STDOUT)

    def lap():
        try:
            with open(beat_path, encoding="utf-8") as f:
                return (json.load(f).get("laps") or {}).get("sources") or {}
        except (OSError, ValueError):
            return {}

    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and (lap().get("sweep") or {}).get("state") != "done":
            assert watcher.poll() is None, log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
            time.sleep(0.5)
        said = lap()
        text = log_path.read_text(encoding="utf-8", errors="replace")
        assert (said.get("sweep") or {}).get("state") == "done", (said, text[-3000:])
        # the sweep's words: the lap's dict is the one the log line was said from
        lines = dict(re.findall(r"External source (\S+): (\d+ file\(s\) looked at - [^\r\n]*)", text))
        assert lines, text[-3000:]
        for source_id, why in said["sweep"]["sources"].items():
            reasons = " · ".join("%s %d" % (name, n) for name, n in why.items()
                                 if name not in ("looked", "first not listed"))
            assert lines[source_id].startswith("%d file(s) looked at - %s" % (why["looked"], reasons)), \
                (source_id, why, lines[source_id])
        shared = [why for why in said["sweep"]["sources"].values() if why["looked"]]
        assert len(shared) == 1 and (shared[0]["name not matched"], shared[0]["folders below max_depth"],
                                     shared[0]["dispatched"]) == (1, 1, 1), said
        # registered and reached · registered and not reached · refused, in the log's sentence
        reached = sorted(source["reachable"] for source in said["sources"].values())
        assert reached == [False, True], said["sources"]
        assert len(said["refused"]) == 1 and said["refused"][0] in text, said["refused"]
        assert said["refused"][0].startswith("External source config rejected: ")
        assert said["started_at"] <= time.time() and "retry_waiting" in said
        with sqlite3.connect(str(db)) as c:
            assert c.execute("SELECT filename FROM file_ingestion_logs").fetchall() == [("a.csv",)]
    finally:
        watcher.kill()
        watcher.wait(30)
        log.close()
