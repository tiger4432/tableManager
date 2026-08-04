"""The four causes behind "the server takes a minute to come up, or never does".

The mechanism, confirmed before this file was written: a second launcher is
started while the first is still running, the new backend cannot bind :8080,
uvicorn raises OSError about three seconds in, and the supervisor - whose only
notion of a shared cause is "is the database reachable" - files that as an
environment outage and retries on a 60 s timer with no limit. Meanwhile /health
answers 503 from the OLD server, so the operator reads a sick new server.

Every test here makes the thing actually happen rather than asserting about it:
a real socket is held, a real child fails to bind, a real launcher process is
run. Throwaway ports only - :8080 and :8090 belong to the running production
stack and are never touched.
"""
import json
import os
import socket
import subprocess
import sys

import pytest

import process_supervisor as ps
from process_supervisor import (
    ChildSpec, Supervisor, STATE_FAILED, STATE_RETRYING_CORRELATED,
    VERDICT_BROKEN_CHILD, VERDICT_PORT_CONFLICT,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture
def held_port():
    """A real listening socket owned by this test process. Yields its port."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        yield srv.getsockname()[1]
    finally:
        srv.close()


def free_port():
    """A port number nothing is listening on."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ===========================================================================
# (1) The pre-flight guard: refuse, and name the PID.
# ===========================================================================

def test_preflight_names_the_pid_that_owns_the_port(held_port):
    """The one message that replaces a minute of silence must be specific.

    "Port 8080 is in use" sends an operator hunting. "Port 8080 is held by PID
    8444 (python.exe)" ends the question in one second, which is the entire
    point of the fix.
    """
    conflicts = ps.preflight_port_check([held_port], host="127.0.0.1")
    assert len(conflicts) == 1, "a port this process is listening on read as free"
    port, detail = conflicts[0]
    assert port == held_port
    assert str(held_port) in detail
    assert str(os.getpid()) in detail, \
        "the owning PID is the whole diagnostic value and it is missing"


def test_preflight_says_nothing_about_a_free_port():
    """The control. Without it "always refuses" would pass the test above."""
    assert ps.preflight_port_check([free_port()], host="127.0.0.1") == []


def test_the_bind_probe_and_the_connect_probe_are_both_load_bearing(held_port):
    """On Windows a bind to 0.0.0.0:N succeeds while another process holds
    127.0.0.1:N. Either probe alone therefore has a blind spot; the OR is what
    makes the answer right for a child that binds loopback (the graph worker)
    and for one that binds every interface (the web server)."""
    taken, how = ps.port_is_taken(held_port, host="127.0.0.1")
    assert taken is True and how
    # The wide-bind view of the same held loopback port: whichever probe catches
    # it, the verdict must still be "taken".
    taken_wide, _ = ps.port_is_taken(held_port, host="0.0.0.0")
    assert taken_wide is True, \
        "a loopback-held port read as free from the 0.0.0.0 view - a launcher " \
        "would start a second graph worker on top of the running one"


def test_the_launcher_refuses_to_start_and_starts_nothing(tmp_path, held_port):
    """End to end, through the real launcher, against a throwaway port.

    --preflight-only is what makes this safe to run: whatever the guard decides,
    no child is spawned, so a regression in the guard cannot start a second
    stack on top of the live one. ASSY_DATA_ROOT keeps launcher.log out of the
    production tree.
    """
    env = dict(os.environ)
    env["ASSY_DATA_ROOT"] = str(tmp_path)
    env["ASSY_API_PORT"] = str(held_port)
    env["ASSY_API_HOST"] = "127.0.0.1"
    env["GRAPH_SYNC_PORT"] = str(free_port())
    env["PYTHONIOENCODING"] = "utf-8"

    res = subprocess.run(
        [sys.executable, os.path.join(ROOT, "run_decoupled_app.py"),
         "--server-only", "--preflight-only"],
        cwd=ROOT, env=env, capture_output=True, timeout=120)
    out = (res.stdout + res.stderr).decode("utf-8", "replace")

    assert res.returncode == 1, f"the launcher did not refuse:\n{out}"
    assert str(held_port) in out
    assert str(os.getpid()) in out, "the refusal did not name the owning PID"
    assert "REFUSING TO START" in out
    assert "기동을 중단합니다" in out
    assert "taskkill" in out, "the refusal must carry the remedy, not just the verdict"
    # And it is on the record, not only on a console someone scrolled past.
    launcher_log = tmp_path / "launcher.log"
    assert launcher_log.exists()
    assert str(held_port) in launcher_log.read_text(encoding="utf-8", errors="replace")


def test_the_launcher_starts_normally_when_the_ports_are_free(tmp_path):
    """The control for the test above: the guard must not refuse a clean box."""
    env = dict(os.environ)
    env["ASSY_DATA_ROOT"] = str(tmp_path)
    env["ASSY_API_PORT"] = str(free_port())
    env["ASSY_API_HOST"] = "127.0.0.1"
    env["GRAPH_SYNC_PORT"] = str(free_port())
    env["PYTHONIOENCODING"] = "utf-8"

    res = subprocess.run(
        [sys.executable, os.path.join(ROOT, "run_decoupled_app.py"),
         "--server-only", "--preflight-only"],
        cwd=ROOT, env=env, capture_output=True, timeout=120)
    out = (res.stdout + res.stderr).decode("utf-8", "replace")
    assert res.returncode == 0, f"the guard refused a free box:\n{out}"
    assert "Preflight OK" in out


def test_the_guard_runs_before_any_child_is_spawned():
    """Ordering is the whole fix. A guard that runs after start_all() has already
    lost: five children are fighting the old stack by then."""
    src = open(os.path.join(ROOT, "run_decoupled_app.py"), encoding="utf-8").read()
    guard = src.index("refuse_if_ports_are_taken(api_host")
    start = src.index("supervisor.start_all()")
    assert guard < start, "the port guard runs after the children are spawned"


def test_the_launcher_declares_the_ports_its_children_bind():
    """The supervisor can only reach the port-conflict verdict for a child whose
    spec names its ports. A future child that binds something and forgets to say
    so silently inherits the 60 s-forever policy again."""
    src = open(os.path.join(ROOT, "run_decoupled_app.py"), encoding="utf-8").read()
    assert "ports=(int(api_port),)" in src
    assert "ports=(int(graph_port),)" in src


# ===========================================================================
# (2) A port conflict is not an environment outage.
# ===========================================================================

class _FakeProc:
    def __init__(self, pid):
        self.pid = pid
        self._code = None

    def poll(self):
        return self._code

    def die(self, code=1):
        self._code = code

    def terminate(self):
        self._code = -15

    def wait(self, timeout=None):
        return self._code

    def kill(self):
        self._code = -9


class _Harness:
    """Two port-binding children on a fake clock, exactly like the incident."""

    def __init__(self, tmp_path, specs, **kw):
        self.now = 1000.0
        self.spawned = []
        self.next_pid = 500
        self.logs = []
        self.sup = Supervisor(
            specs,
            status_file=os.path.join(str(tmp_path), "supervisor_status.json"),
            log=lambda msg, level="INFO": self.logs.append((level, msg)),
            spawn=self._spawn,
            clock=lambda: self.now,
            sleep=lambda s: None,
            **kw)

    def _spawn(self, spec):
        self.next_pid += 1
        p = _FakeProc(self.next_pid)
        self.spawned.append((spec.name, p))
        return p

    def spawn_count(self, name):
        return len([n for n, _ in self.spawned if n == name])

    def burn_the_budget(self, names=()):
        """Kill the named children over and over until the verdict is reached."""
        for _ in range(12):
            for c in self.sup.children:
                if names and c.spec.name not in names:
                    continue
                if c.proc is not None and c.proc.poll() is None:
                    c.proc.die(code=1)
            self.sup.poll_once()
            self.now += 61.0
            self.sup.poll_once()

    def errors(self):
        return [m for lvl, m in self.logs if lvl == "ERROR"]


def _two_port_binders():
    return [ChildSpec("web", ["python", "s.py"], ".", ports=(18080,)),
            ChildSpec("graph", ["python", "g.py"], ".", ports=(18090,))]


def test_a_port_conflict_is_terminal_and_names_the_owner(tmp_path):
    """The incident. Both port binders die together, so the peer rule would have
    called it a shared-cause outage and retried on 60 s FOREVER - which is what
    production actually did, 74 times."""
    h = _Harness(tmp_path, _two_port_binders(),
                 port_probe=lambda spec: (
                     True, f"TCP port {spec.ports[0]} is already held by "
                           f"PID 8444 (python.exe) [bind failed (OSError)]"),
                 environment_probe=lambda: (False, None))
    h.sup.start_all()
    h.burn_the_budget()

    for name in ("web", "graph"):
        c = h.sup._find(name)
        assert c.state == STATE_FAILED, \
            f"{name} is {c.state} - a port conflict is being retried forever again"
        assert c.terminal_verdict == VERDICT_PORT_CONFLICT
        assert "8444" in (c.failure_reason or ""), \
            "the verdict must name the PID that owns the port"
        assert "not an environment outage" in (c.failure_reason or "")

    # Terminal means terminal: no further spawns, ever.
    before = {n: h.spawn_count(n) for n in ("web", "graph")}
    for _ in range(20):
        h.now += 3600.0
        h.sup.poll_once()
    assert {n: h.spawn_count(n) for n in ("web", "graph")} == before

    errs = "\n".join(h.errors())
    assert "PORT CONFLICT" in errs
    assert "second launcher" in errs
    assert "taskkill" in errs, "the banner must carry the remedy"

    st = json.load(open(h.sup.status_file, encoding="utf-8"))
    assert sorted(st["failed_children"]) == ["graph", "web"]
    assert st["correlated_children"] == []
    assert st["children"]["web"]["terminal_verdict"] == VERDICT_PORT_CONFLICT


def test_a_database_outage_still_gets_the_correlated_retry(tmp_path):
    """The case the correlated policy exists for, on the SAME fixture: two port
    binders dying together, the only difference being that their ports are free
    and the database is down. This must still retry indefinitely."""
    h = _Harness(tmp_path, _two_port_binders(),
                 port_probe=lambda spec: (False, None),
                 environment_probe=lambda: (
                     True, "the database at db:5432 is not accepting connections"))
    h.sup.start_all()
    h.burn_the_budget()
    for c in h.sup.children:
        if c.proc is not None:
            c.proc.die(code=1)
    h.sup.poll_once()

    for name in ("web", "graph"):
        c = h.sup._find(name)
        assert c.state == STATE_RETRYING_CORRELATED, \
            f"{name} is {c.state} - the database-outage case was broken by the fix"
        assert c.terminal_verdict is None
        assert h.spawn_count(name) > h.sup.max_consecutive_failures + 1, \
            "the child stopped being respawned during a database outage"
    st = json.load(open(h.sup.status_file, encoding="utf-8"))
    assert st["failed_children"] == []
    assert sorted(st["correlated_children"]) == ["graph", "web"]


def test_a_lone_port_binder_with_a_down_database_still_retries(tmp_path):
    """The measured real outage: with PostgreSQL unreachable exactly ONE child
    dies (the web server, whose import runs create_all). It binds a port, so it
    now meets the new probe first - and must still be spared."""
    h = _Harness(tmp_path,
                 [ChildSpec("web", ["python", "s.py"], ".", ports=(18080,)),
                  ChildSpec("worker", ["python", "w.py"], ".")],
                 port_probe=lambda spec: (False, None),
                 environment_probe=lambda: (True, "the database at db:5432 is down"))
    h.sup.start_all()
    h.burn_the_budget(names=("web",))
    h.sup._find("web").proc.die(code=1)
    h.sup.poll_once()

    c = h.sup._find("web")
    assert c.state == STATE_RETRYING_CORRELATED
    assert "database" in (c.correlated_evidence or "")


def test_a_broken_child_that_binds_a_port_is_still_permanently_failed(tmp_path):
    """The other control: free port, healthy database, failing alone. The old
    verdict must survive, or "port conflict" would just be a new way to never
    give up."""
    h = _Harness(tmp_path,
                 [ChildSpec("web", ["python", "s.py"], ".", ports=(18080,))],
                 port_probe=lambda spec: (False, None),
                 environment_probe=lambda: (False, None))
    h.sup.start_all()
    h.burn_the_budget()
    c = h.sup._find("web")
    assert c.state == STATE_FAILED
    assert c.terminal_verdict == VERDICT_BROKEN_CHILD
    assert "PORT CONFLICT" not in "\n".join(h.errors())


def test_the_port_probe_only_runs_at_the_giving_up_point(tmp_path):
    """It enumerates the machine's TCP table. Running it on every ordinary
    restart would put that cost inside the normal path."""
    calls = []
    h = _Harness(tmp_path,
                 [ChildSpec("web", ["python", "s.py"], ".", ports=(18080,))],
                 port_probe=lambda spec: (calls.append(spec.name), (False, None))[1],
                 environment_probe=lambda: (False, None))
    h.sup.start_all()
    for _ in range(3):          # well inside the budget
        h.sup._find("web").proc.die(code=1)
        h.sup.poll_once()
        h.now += 61.0
        h.sup.poll_once()
    assert calls == [], "the port probe ran during ordinary backoff restarts"
    h.burn_the_budget()
    assert calls, "the probe never ran, even at the giving-up point"


def test_the_probe_is_not_consulted_for_a_child_that_binds_nothing(tmp_path):
    """Three of the five children bind nothing. Asking about their ports would be
    asking a question with no answer."""
    calls = []
    h = _Harness(tmp_path,
                 [ChildSpec("worker", ["python", "w.py"], ".")],
                 port_probe=lambda spec: (calls.append(spec.name), (True, "x"))[1],
                 environment_probe=lambda: (False, None))
    h.sup.start_all()
    h.burn_the_budget()
    assert calls == []
    assert h.sup._find("worker").state == STATE_FAILED
    assert h.sup._find("worker").terminal_verdict == VERDICT_BROKEN_CHILD


def test_a_port_probe_that_raises_decides_nothing(tmp_path):
    """Monitoring must never become a new failure mode."""
    def boom(spec):
        raise OSError("probe exploded")

    h = _Harness(tmp_path,
                 [ChildSpec("web", ["python", "s.py"], ".", ports=(18080,))],
                 port_probe=boom, environment_probe=lambda: (False, None))
    h.sup.start_all()
    h.burn_the_budget()
    c = h.sup._find("web")
    assert c.state == STATE_FAILED
    assert c.terminal_verdict == VERDICT_BROKEN_CHILD


def test_the_real_probe_sees_a_real_socket(held_port):
    """Not a mocked return value: a socket this process is actually listening on,
    read back through the production probe."""
    spec = ChildSpec("web", ["python", "s.py"], ".", ports=(held_port,),
                     port_host="127.0.0.1")
    conflict, detail = ps.port_conflict(spec)
    assert conflict is True
    assert str(os.getpid()) in detail

    free = ChildSpec("web", ["python", "s.py"], ".", ports=(free_port(),),
                     port_host="127.0.0.1")
    assert ps.port_conflict(free) == (False, None)


# ===========================================================================
# (3) The child's own output has to exist in a file.
# ===========================================================================

def test_a_childs_bind_error_lands_in_a_file(tmp_path, held_port):
    """THE acceptance test.

    uvicorn writes `Started server process`, `Uvicorn running on`, `Application
    startup complete` and its OSError to stdout/stderr. The launcher captured
    none of it, so the single most decisive line of this incident existed in no
    file on disk and the cause had to be reconstructed from 74 deaths' worth of
    statistics. Here a real child really fails to bind a really occupied port,
    through the real spawn path, and the error has to be greppable afterwards.
    """
    binder = tmp_path / "binder.py"
    binder.write_text(
        "import socket\n"
        "s = socket.socket()\n"
        f"s.bind(('127.0.0.1', {held_port}))\n",
        encoding="utf-8")
    log_file = str(tmp_path / "binder_stdout.log")

    sup = Supervisor(
        [ChildSpec("binder", [sys.executable, str(binder)], str(tmp_path),
                   ports=(held_port,), port_host="127.0.0.1",
                   log_file=log_file)],
        status_file=str(tmp_path / "status.json"))
    sup.start_all()
    child = sup.children[0]
    try:
        child.proc.wait(timeout=60)
    finally:
        sup.stop_all(timeout=3.0)
    if child.log_pump is not None:
        child.log_pump.join(timeout=30)

    assert os.path.exists(log_file), "the child's output file was never created"
    text = open(log_file, "rb").read().decode("utf-8", "replace")
    assert "Traceback" in text, f"the child's stderr was not captured:\n{text}"
    assert "OSError" in text
    assert ("10048" in text or "Address already in use" in text), \
        f"the bind error itself is missing from the file:\n{text}"
    # And the header that answers "which run was this" - the question two
    # launcher banners with no shutdown between them made unanswerable.
    assert "binder started" in text
    assert "pid=" in text


def test_the_capture_is_declared_for_every_child():
    """A child added later without a log_file is invisible again for exactly the
    reason this fix exists."""
    src = open(os.path.join(ROOT, "run_decoupled_app.py"), encoding="utf-8").read()
    for name in ("Backend FastAPI Server", "File Ingestion Watcher",
                 "Graph DB Sync Worker", "Chained Ingestion Worker",
                 "Auto Update Scheduler"):
        i = src.index(f'ChildSpec("{name}"')
        window = src[i:i + 420]
        assert "log_file=" in window, \
            f"the child '{name}' has no output capture"


def test_a_child_with_no_log_file_still_starts(tmp_path):
    """The capture must be optional, not a new way for a spawn to fail."""
    script = tmp_path / "ok.py"
    script.write_text("print('hello')\n", encoding="utf-8")
    sup = Supervisor([ChildSpec("plain", [sys.executable, str(script)], str(tmp_path))],
                     status_file=str(tmp_path / "status.json"))
    sup.start_all()
    try:
        assert sup.children[0].proc is not None
        assert sup.children[0].log_pump is None
    finally:
        sup.stop_all(timeout=3.0)


# ===========================================================================
# (4) /health answering 503 is this application, not a proxy.
# ===========================================================================

class _Resp:
    def __init__(self, status_code, body=None, headers=None, raises=False):
        from requests.structures import CaseInsensitiveDict
        self.status_code = status_code
        self.headers = CaseInsensitiveDict(headers or {})
        self.ok = 200 <= status_code < 300
        self._body = body
        self._raises = raises

    def json(self):
        if self._raises or self._body is None:
            raise ValueError("not json")
        return self._body


def _probe(monkeypatch, response):
    import internal_event_client

    class _Sess:
        @staticmethod
        def get(url, **kw):
            return response

    monkeypatch.setattr(internal_event_client, "internal_event_session", lambda: _Sess())
    monkeypatch.setattr("urllib.request.getproxies", lambda: {})
    return internal_event_client.check_api_reachable("http://127.0.0.1:8080")


OUR_503 = {
    "status": "unhealthy",
    "checked_at": "2026-08-04T10:00:00+09:00",
    "problems": ["child 'Backend FastAPI Server' permanently failed: port taken"],
    "checks": {"database": {"status": "ok"}, "supervisor": {"status": "failed_children"}},
}


def test_our_own_503_is_not_reported_as_a_proxy(monkeypatch):
    """/health returns 503 BY DESIGN whenever any check fails. Calling that
    proof that "something in front of it answered" is what made both workers
    print a proxy essay on 2026-07-31 while the real cause was a duplicate
    launcher - and it misdirected this very diagnosis once."""
    level, msg = _probe(monkeypatch, _Resp(503, body=OUR_503,
                                           headers={"Server": "uvicorn"}))
    assert level == "warning", "an unhealthy web server is not an ERROR-level proxy incident"
    assert "THIS application" in msg
    assert "unhealthy" in msg
    assert "permanently failed" in msg, "the actual problem must be quoted, not hidden"
    assert "NO_PROXY" not in msg and "프록시" not in msg, \
        "the proxy essay is still being printed for our own 503"


def test_a_503_from_something_else_still_gets_the_proxy_essay(monkeypatch):
    """Narrowed, not deleted. This site really does have a corporate proxy that
    does not honour <local> for 127.0.0.1, and that instinct has been right
    before."""
    level, msg = _probe(monkeypatch, _Resp(503, raises=True,
                                           headers={"Server": "squid/5.7"}))
    assert level == "error"
    assert "squid/5.7" in msg
    assert "NO_PROXY" in msg and "프록시" in msg


def test_a_403_from_a_proxy_is_unchanged(monkeypatch):
    """The original incident's signature must still be caught."""
    level, msg = _probe(monkeypatch, _Resp(403, headers={"Server": "squid/5.7"}))
    assert level == "error"
    assert "NO admin gate" in msg


def test_a_body_shaped_like_ours_but_missing_checks_is_not_trusted(monkeypatch):
    """The fingerprint is `status` AND `checks` together. A proxy that happens to
    return `{"status": "error"}` must not be able to impersonate us."""
    level, msg = _probe(monkeypatch, _Resp(502, body={"status": "error"},
                                           headers={"Server": "nginx"}))
    assert level == "error"
    assert "NO_PROXY" in msg


def test_a_200_is_still_direct(monkeypatch):
    level, msg = _probe(monkeypatch, _Resp(200))
    assert level == "info" and "200" in msg


def _cp949_or_fail(lines):
    for line in lines:
        try:
            line.encode("cp949")
        except UnicodeEncodeError as e:
            pytest.fail(
                f"character {e.object[e.start:e.end]!r} "
                f"(U+{ord(e.object[e.start]):04X}) cannot be printed on the "
                f"production console, so this line is DROPPED there: {line[:120]!r}")


def test_the_refusal_survives_the_production_console(tmp_path):
    """The production console is cp949 (run_app.bat sets no PYTHONIOENCODING) and
    one character outside it makes the logging handler raise and DROP the line.
    Dropping THIS line means an operator staring at a silent console during
    exactly the incident this message exists to end.

    The launcher's half is read with `ast` rather than imported, because
    importing run_decoupled_app.py opens the LIVE server/launcher.log and resets
    the root logger for the rest of the suite. Only the string literals inside
    the refusal function are examined - the lines it actually prints - not
    docstrings elsewhere in the file that are never encoded by anything.
    """
    import ast
    tree = ast.parse(open(os.path.join(ROOT, "run_decoupled_app.py"),
                          encoding="utf-8").read())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "refuse_if_ports_are_taken")
    doc = ast.get_docstring(fn)
    literals = [n.value for n in ast.walk(fn)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and n.value != doc]
    assert any("기동을 중단합니다" in s for s in literals), \
        "the Korean refusal line is no longer a literal in this function"
    _cp949_or_fail(literals)

    # The supervisor's own port-conflict banner, same rule.
    h = _Harness(tmp_path,
                 [ChildSpec("web", ["python", "s.py"], ".", ports=(18080,))],
                 port_probe=lambda spec_: (
                     True, "TCP port 18080 is already held by PID 8444 (python.exe)"),
                 environment_probe=lambda: (False, None))
    h.sup.start_all()
    h.burn_the_budget()
    _cp949_or_fail([m for _, m in h.logs])
    _cp949_or_fail([h.sup._find("web").failure_reason])
