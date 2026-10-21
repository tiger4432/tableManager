# -*- coding: utf-8 -*-
"""총괄 10-21 (C 간섭 전수 ③ W5): the watcher sent a notification per chunk, each waiting on an API that took none -
5 s a try against one that does not answer - while it held the table's lock. Now one judgement
(`internal_event_client.api_took` · `api_may_send`) opens a window on a refusal in which no sender of the process tries:
a file waits on a dead API once, not once per notification. A real watcher process; three-chunk files.

  silent API (accepts, never answers)  file 1 waits one timeout · file 2, inside the window, none ·
                                       file 3, after the window, one timeout and no more
  closed port                          the same, a refusal's ~2 s for a timeout
What is not sent is left undelivered for the chain's sweep, as a refusal's is.
"""
import http.server
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

from tests.test_a_file_read_is_checked_by_its_path_and_table import DRIVER, PLUGIN, SERVER_DIR, TABLE

ROWS = 2500                   # three chunks of the watcher's 1000
TIMEOUT = 5                   # run_watcher.post_event's


class _Silent(http.server.BaseHTTPRequestHandler):
    """Takes the request and never answers it."""
    def _hang(self):
        time.sleep(60)

    do_GET = do_POST = do_PUT = _hang

    def log_message(self, *args):
        pass


def _closed_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("api", ["silent", "closed"])
def test_a_file_waits_on_a_dead_api_once(tmp_path, api):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    with open(data / "config" / "table_config.json", "w", encoding="utf-8") as f:
        json.dump({"ta": TABLE}, f)
    scripts = data / "ingestion_workspace" / "ta" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "p.py").write_text(PLUGIN, encoding="utf-8")
    raws = data / "ingestion_workspace" / "ta" / "raws"
    raws.mkdir(parents=True)
    with open(data / "config" / "ingestion_settings.json", "w", encoding="utf-8") as f:
        json.dump({"archive_processed_files": False}, f)
    server = None
    if api == "silent":
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Silent)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
    else:
        port = _closed_port()
    db = tmp_path / "box.db"
    env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + db.as_posix(),
               API_BASE_URL="http://127.0.0.1:%d" % port, NO_PROXY="127.0.0.1,localhost", PYTHONIOENCODING="utf-8",
               PYTHONPATH=SERVER_DIR, DECOUPLED="True")
    env.pop("TESTING", None)
    driver, log_path = tmp_path / "driver.py", tmp_path / "watcher.log"
    driver.write_text(DRIVER, encoding="utf-8")
    log = open(log_path, "ab")
    watcher = subprocess.Popen([sys.executable, str(driver)], cwd=SERVER_DIR, env=env, stdout=log,
                               stderr=subprocess.STDOUT)

    def took(name, seconds=120):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            assert watcher.poll() is None, log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
            try:
                with sqlite3.connect(str(db)) as c:
                    row = c.execute("SELECT status, took_seconds FROM file_ingestion_logs WHERE filename = ? "
                                    "AND status IN ('SUCCESS', 'FAILED')", (name,)).fetchone()
            except sqlite3.Error:
                row = None
            if row:
                assert row[0] == "SUCCESS", row
                return row[1]
            time.sleep(0.2)
        raise AssertionError("%s was not read: %s" % (name, log_path.read_text(encoding="utf-8",
                                                                              errors="replace")[-3000:]))

    def drop(name):
        rows = "".join("L%s%05d,v\n" % (name[0], i) for i in range(ROWS))
        (raws / name).write_text("lot,val\n" + rows, encoding="utf-8")

    try:
        time.sleep(6)                                       # the watcher up, and any window its start opened past
        drop("a.csv")
        first = took("a.csv")
        drop("b.csv")
        second = took("b.csv")
        time.sleep(TIMEOUT + 1)                             # past the window
        drop("c.csv")
        third = took("c.csv")
        failures = log_path.read_text(encoding="utf-8", errors="replace").count("API notification")
        said = (first, second, third, failures)
        print("%s API: file seconds %.1f / %.1f / %.1f, failed sends %d" % ((api,) + said))
        assert first < TIMEOUT + 4, said                    # one wait, not one per chunk
        assert second < 3, said                             # inside the window: none
        assert third < TIMEOUT + 4, said                    # after the window: one timeout and no more
        if api == "silent":
            assert third >= TIMEOUT - 1, said               # it did try again after the window
        with sqlite3.connect(str(db)) as c:                 # what was not sent waits for the sweep
            assert c.execute("SELECT count(*) FROM database_outbox").fetchone()[0] > 0
    finally:
        watcher.kill()
        watcher.wait(30)
        log.close()
        if server is not None:
            server.shutdown()
