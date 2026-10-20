# -*- coding: utf-8 -*-
"""A re-read preview that walks a big folder stops only itself (소유자 10-20 「파일 소급 미리보기 하니까 다 멈추네」).

`retry-failed?table=…&preview=true` walks the disk (`reread.select_files`). It ran on the event loop, so while it
walked every request of the API waited. A real server process with a walk that sleeps: `/health` answers inside a
second while the preview is still walking, and the preview's answer is the walk's."""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLOW = 4.0

DRIVER = '''
import sys, time
import uvicorn
import main
from admin import auth
from database import crud
from ingestion import reread

def slow_select_files(db, table, folder, limit=None):
    time.sleep(float(sys.argv[2]))
    return {"picked": [(None, "a.csv", folder + "/a.csv")], "not_taken": {}, "not_taken_files": [], "walked": 1}

reread.select_files = slow_select_files
crud.TABLE_CONFIG["probe_table"] = {}
main.app.dependency_overrides[auth.require_admin_token] = lambda: None
uvicorn.run(main.app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
'''


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ask(opener, url, data=None, timeout=30):
    """-> (status, body). An answer that is not 2xx is still an answer."""
    try:
        with opener.open(urllib.request.Request(url, data=data, method="POST" if data is not None else "GET"),
                         timeout=timeout) as reply:
            return reply.status, reply.read()
    except urllib.error.HTTPError as reply:
        return reply.code, reply.read()


def test_health_answers_while_a_preview_walks_the_disk(tmp_path):
    port = _free_port()
    driver = tmp_path / "slow_reread_server.py"
    driver.write_text(DRIVER, encoding="utf-8")
    env = dict(os.environ, TESTING="True", DECOUPLED="True", ASSY_DATA_ROOT=str(tmp_path),
               DATABASE_URL="sqlite:///%s" % (tmp_path / "box.db").as_posix(), PYTHONPATH=SERVER_DIR,
               PYTHONIOENCODING="utf-8")
    log = open(tmp_path / "server.log", "wb")
    server = subprocess.Popen([sys.executable, str(driver), str(port), str(SLOW)], cwd=SERVER_DIR, env=env,
                              stdout=log, stderr=subprocess.STDOUT)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # the box's system proxy is not ours
    base = "http://127.0.0.1:%d" % port
    try:
        deadline = time.monotonic() + 90
        while True:
            assert server.poll() is None, (tmp_path / "server.log").read_text(errors="replace")
            try:
                _ask(opener, base + "/health", timeout=5)
                break
            except OSError:
                assert time.monotonic() < deadline, "the server never came up"
                time.sleep(0.5)
        preview = {}

        def ask_preview():
            started = time.monotonic()
            preview["answer"] = _ask(opener, base + "/admin/file-ingestion/retry-failed?folder=%s&table=probe_table"
                                     "&preview=true" % urllib.request.quote(str(tmp_path)), data=b"")
            preview["ended"] = time.monotonic()
            preview["took"] = preview["ended"] - started

        walking = threading.Thread(target=ask_preview)
        walking.start()
        time.sleep(1.0)                                           # the walk is asleep now
        started = time.monotonic()
        _ask(opener, base + "/health", timeout=SLOW * 3)
        health_took = time.monotonic() - started
        walking.join(SLOW * 3)
    finally:
        server.kill()
        server.wait(30)
        log.close()
    assert preview["ended"] > started, "the preview had ended before /health was asked - nothing was measured"
    assert health_took < 1.0, "/health waited %.1f s behind the preview's walk" % health_took
    status, body = preview["answer"]
    assert status == 200, body
    said = json.loads(body)
    assert preview["took"] >= SLOW
    assert (said["status"], said["count"], said["by_state"], said["table"], said["walked"]) == \
        ("preview", 1, {"NEW": 1}, "probe_table", 1)
