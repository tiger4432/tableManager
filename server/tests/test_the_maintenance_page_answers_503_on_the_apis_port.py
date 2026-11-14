"""The maintenance page (owner 11-14 안 1), as a real process: on the API's port every path - /health too - answers 503
with Retry-After and the one page, the operator's note escaped under «Back soon»; on a held port it refuses at once
with one line naming the next action and serves nothing."""
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAM = os.path.join(SERVER_DIR, "runtime", "maintenance_page.py")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _env(port):
    # 127.0.0.1: the test opens nothing a LAN can reach (the product's default binds both families)
    return dict(os.environ, ASSY_API_HOST="127.0.0.1", ASSY_API_PORT=str(port), PYTHONIOENCODING="utf-8")


def _ask(opener, url):
    try:
        with opener.open(url, timeout=5) as reply:
            return reply.status, dict(reply.headers), reply.read().decode("utf-8")
    except urllib.error.HTTPError as reply:
        return reply.code, dict(reply.headers), reply.read().decode("utf-8")


def test_every_path_answers_503_with_the_page_and_retry_after(tmp_path):
    port = _free_port()
    log = tmp_path / "page.log"
    process = subprocess.Popen([sys.executable, PROGRAM, "until", "15:00", "<b>"], env=_env(port),
                               stdout=open(log, "wb"), stderr=subprocess.STDOUT)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # the box's system proxy is not ours
    try:
        deadline = time.monotonic() + 30
        while True:
            assert process.poll() is None, log.read_text(encoding="utf-8", errors="replace")
            try:
                root = _ask(opener, "http://127.0.0.1:%d/" % port)
                break
            except OSError:
                assert time.monotonic() < deadline, "the page never came up"
                time.sleep(0.2)
        health = _ask(opener, "http://127.0.0.1:%d/health" % port)
        deep = _ask(opener, "http://127.0.0.1:%d/tables/x/data?y=1" % port)
    finally:
        process.kill()
        process.wait(10)
    for status, headers, body in (root, health, deep):
        assert status == 503
        assert headers.get("Retry-After") == "300"
        assert "<h1>Updating</h1>" in body and "Back soon" in body
        assert "until 15:00 &lt;b&gt;" in body, "the operator's note, escaped"
    said = log.read_text(encoding="utf-8", errors="replace")
    assert "Notice page on port %d - close this window before starting the launcher" % port in said


def test_a_held_port_is_refused_at_once_with_the_next_action(tmp_path):
    port = _free_port()
    holder = socket.socket()
    holder.bind(("127.0.0.1", port))
    holder.listen()
    try:
        started = time.monotonic()
        done = subprocess.run([sys.executable, PROGRAM], env=_env(port), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30)
        took = time.monotonic() - started
    finally:
        holder.close()
    assert done.returncode == 1, done.stdout + done.stderr
    assert done.stdout.startswith("Port %d is in use (" % port), done.stdout
    assert done.stdout.rstrip().endswith("- stop the launcher first, then run maintenance.bat again"), done.stdout
    assert took < 15, "it refuses, it does not wait (%.1f s)" % took
