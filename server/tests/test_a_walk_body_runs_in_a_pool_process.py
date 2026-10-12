"""The pool seat (`runtime.process_pool.in_pool`, lead b47388fde): a route's body answers from a process of its own with
the same status, headers and bytes as when it runs here; a pool process killed mid-body fails that request only; a
reload's recycle gives the next body a fresh process; a request waits a bounded time; code that calls the walk's
function itself gets a dict, as before (QA on 407448592)."""
import asyncio
import datetime
import json
import os
import subprocess
import sys
import threading
import time

import psutil
import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SERVER_DIR)

from database.database import SessionLocal, get_db                      # noqa: E402
from runtime import process_pool, request_timing                         # noqa: E402
from runtime.offloop_json import OffLoopJSONRoute                       # noqa: E402

router = APIRouter(route_class=OffLoopJSONRoute)


@router.get("/body")
@process_pool.in_pool
def answer(kind: str, pid_file: str | None = None, db: Session = Depends(get_db)):
    if kind == "json":
        return {"when": datetime.date(2026, 10, 12), "set": ["a"], "text": "웨이퍼"}
    if kind == "rows":
        return PlainTextResponse("a\tb\n1\t2\n", media_type="text/tab-separated-values")
    if kind == "refuse":
        raise HTTPException(status_code=422, detail={"reason": "no", "choices": ["Count"]},
                            headers={"X-Why": "no"})
    if kind == "boom":
        raise ZeroDivisionError("boom")
    if kind == "query":
        db.execute(text("SELECT 1"))
    if kind == "hang":
        with open(pid_file, "w") as handle:
            handle.write(str(os.getpid()))
        for _ in range(600):
            if os.path.exists(pid_file + ".go"):
                break
            time.sleep(0.1)
    return {"pid": os.getpid()}


app = FastAPI()
app.router.route_class = OffLoopJSONRoute
app.include_router(router)


@app.middleware("http")
async def timed(request: Request, call_next):
    began = request_timing.begin()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        request_timing.end(began, request.method, request.url.path, response)


def _set(monkeypatch, **settings):
    monkeypatch.setattr(process_pool, "_settings", lambda: dict(settings))


@pytest.fixture
def client(monkeypatch):
    _set(monkeypatch, walk_processes=2, walk_seconds_max=60)
    monkeypatch.setattr(process_pool, "_warmed", [False])
    with TestClient(app, raise_server_exceptions=False) as each:
        yield each
    with process_pool._cond:
        taken = process_pool._taken[0]
        process_pool._generation[0] += 1
        process_pool._drain_locked()
    assert taken == 0, "a request left its slot taken"


@pytest.fixture
def warming(monkeypatch):
    """`warm` starts nothing in testing mode (lead 9a3c510c5) - these cells measure it, so they leave that mode."""
    monkeypatch.setenv("TESTING", "False")


def _seen(response):
    headers = {k: v for k, v in response.headers.items() if k != "server-timing"}
    return response.status_code, headers, response.content


def _until_written(path):
    for _ in range(300):
        if os.path.exists(path) and open(path).read():
            return int(open(path).read())
        time.sleep(0.1)
    raise AssertionError("the body did not start")


def _hang_in_a_thread(client, pid_file, out):
    thread = threading.Thread(target=lambda: out.setdefault(
        "response", client.get("/body", params={"kind": "hang", "pid_file": pid_file})))
    thread.start()
    return thread


@pytest.mark.parametrize("kind", ["json", "rows", "refuse", "boom"])
def test_a_pool_answer_is_the_answer_given_here(client, monkeypatch, kind):
    pooled = _seen(client.get("/body", params={"kind": kind}))
    _set(monkeypatch, walk_processes=0)
    here = _seen(client.get("/body", params={"kind": kind}))
    assert pooled == here
    assert pooled[0] == {"json": 200, "rows": 200, "refuse": 422, "boom": 500}[kind]


def test_the_body_ran_in_another_process(client):
    assert client.get("/body", params={"kind": "pid"}).json()["pid"] != os.getpid()


def test_the_pool_s_database_time_joins_the_request_s(client):
    timing = client.get("/body", params={"kind": "query"}).headers["server-timing"]
    assert 'desc="1 queries"' in timing


@pytest.mark.parametrize("settings,expected", [
    ({}, 2), ({"walk_processes": 0}, 0), ({"walk_processes": 3}, 3), ({"walk_processes": "0"}, 0),
    ({"walk_processes": False}, 0), ({"walk_processes": True}, 0), ({"walk_processes": 0.0}, 0),
    ({"walk_processes": -1}, 0)], ids=["absent", "0", "3", "text 0", "false", "true", "0.0", "-1"])
def test_only_a_whole_number_from_0_is_read_and_anything_else_turns_it_off(settings, expected):
    assert process_pool.size(settings) == expected


def test_the_body_runs_here_when_the_pool_is_off_or_the_session_is_not_the_server_s(client, monkeypatch):
    other = sessionmaker(bind=create_engine("sqlite://"))()
    try:
        assert process_pool.in_pool(answer.__pool_body__)(kind="pid", db=other)["pid"] == os.getpid()
        assert process_pool.in_pool(answer.__pool_body__)(kind="pid", db=None)["pid"] == os.getpid()
    finally:
        other.close()
    _set(monkeypatch, walk_processes=0)
    assert client.get("/body", params={"kind": "pid"}).json()["pid"] == os.getpid()


def test_turning_the_pool_off_ends_the_idle_processes(client, monkeypatch):
    client.get("/body", params={"kind": "pid"})
    assert process_pool._idle
    _set(monkeypatch, walk_processes=0)
    client.get("/body", params={"kind": "pid"})
    assert process_pool._idle == []


def test_a_direct_call_of_the_walk_function_answers_a_dict(monkeypatch):
    """🔴 QA on 407448592: the pool sat on the NAME, so `mappers/contrast_walk.py` (a chain slot, a server-engine
    session) got a Response - and its group rolled back three times into quarantine."""
    from ledger import trace_router

    _set(monkeypatch, walk_processes=2, walk_seconds_max=60)
    monkeypatch.setattr(trace_router, "_evidence_graph", lambda *args, **kwargs: {"ok": 1})
    db = SessionLocal()
    try:
        got = trace_router.evidence_subgraph(
            node_id="seed", response_format="json", db=db, hops=1, direction="both", since=None, until=None,
            node_limit=400, edge_limit=1200, positive=None, negative=None, follow=None, backbone_hops=0,
            collect=None, include_superseded=False)
    finally:
        db.close()
    assert got == {"ok": 1}


def test_the_walk_route_is_the_one_that_runs_in_the_pool():
    from ledger import trace_router

    (route,) = [r for r in trace_router.router.routes if getattr(r, "path", "") == "/api/ledger/subgraph"]
    assert route.endpoint.__pool_body__ is trace_router.evidence_subgraph
    assert not hasattr(trace_router.evidence_subgraph, "__pool_body__")


def test_a_reload_recycles_the_pool(monkeypatch):
    from runtime import system_reload

    called = []
    monkeypatch.setattr(process_pool, "recycle", lambda: called.append(1))
    system_reload.reload_local_process_cache()
    assert called == [1]


def test_the_server_s_start_starts_the_pool_ahead(monkeypatch):
    """The startup event, run: it calls `warm` (which in testing mode starts nothing)."""
    import main
    from database import config_watcher

    called = []
    monkeypatch.setattr(process_pool, "warm", lambda: called.append(1))
    monkeypatch.setattr(config_watcher, "start_config_watcher", lambda engine=None: None)
    asyncio.run(main.startup_event())
    assert called == [1]


def test_testing_mode_starts_no_pool_process(monkeypatch):
    monkeypatch.setenv("TESTING", "True")
    process_pool.warm()
    time.sleep(0.5)
    assert process_pool._idle == [] and process_pool._taken[0] == 0


@pytest.mark.parametrize("sync", ["synced", "sync fails"])
def test_a_table_config_reload_recycles_the_pool(monkeypatch, sync):
    """lead 9a3c510c5 중1: a pool process reads the table config when it starts - the reload gives new ones; and when
    the schema sync after the new config fails, the pool does not stay on the old one (lead eb9c328e4)."""
    from database import config_watcher, crud, models

    def fails(engine):
        raise RuntimeError("the schema sync failed")

    called = []
    monkeypatch.setattr(process_pool, "recycle", lambda: called.append(1))
    monkeypatch.setattr(crud, "TABLE_CONFIG", {})
    monkeypatch.setattr(crud, "load_table_config", lambda: {"t": {}})
    monkeypatch.setattr(models, "init_dynamic_models", lambda config, engine=None: None)
    monkeypatch.setattr(models, "create_missing_dynamic_tables", lambda engine: [])
    monkeypatch.setattr(models, "sync_dynamic_tables_schema", (lambda engine: None) if sync == "synced" else fails)
    monkeypatch.setattr(config_watcher, "_report_unsearchable_declarations", lambda config: None)
    config_watcher.ConfigChangeHandler(engine=object())._reload("table_config.json")
    assert called == [1]


#: A script shaped as a daemon (run_watcher.py, run_chain_worker.py, run_auto_update.py: the reload, no warm) or as the
#: server (warm, then the reload). Its top level marks each run of itself - a walk process runs it as `__mp_main__`.
SHAPE = """
import json, os, sys, time
sys.path.insert(0, os.getcwd())
open(os.path.join(os.environ["POOL_SHAPE_MARKS"], "%s.%d" % (__name__, os.getpid())), "w").close()
if __name__ == "__main__":
    import psutil
    from database import config_watcher, crud, models
    from runtime import process_pool
    process_pool._settings = lambda: {"walk_processes": 1, "walk_seconds_max": 60}
    crud.load_table_config = lambda: {"t": {}}
    models.init_dynamic_models = lambda config, engine=None: None
    config_watcher._report_unsearchable_declarations = lambda config: None
    if sys.argv[1] == "server":
        process_pool.warm()
        for _ in range(600):
            if process_pool._idle:
                break
            time.sleep(0.1)
    config_watcher.ConfigChangeHandler(engine=None)._reload("table_config.json")
    for tick in range(600):
        if sys.argv[1] == "daemon" and tick == 80:
            break
        if sys.argv[1] == "server" and process_pool._idle and process_pool._idle[0][2] == process_pool._generation[0]:
            break
        time.sleep(0.1)
    alive = [p.pid for p in psutil.Process().children() if p.status() != psutil.STATUS_ZOMBIE]
    print(json.dumps({"children": len(alive), "generation": process_pool._generation[0]}))
"""


def test_a_table_config_reload_in_a_daemon_starts_no_walk_process(tmp_path):
    """🔴 lead eb9c328e4: the watcher, chain worker and auto-update daemons run the same reload - a walk process started
    there runs the daemon's top level again. Only a process that warmed the pool (the server) recycles it."""
    script = tmp_path / "shape.py"
    script.write_text(SHAPE, encoding="utf-8")
    seen = {}
    for shape in ("server", "daemon"):
        marks = tmp_path / shape
        marks.mkdir()
        run = subprocess.run([sys.executable, str(script), shape], cwd=SERVER_DIR, capture_output=True, text=True,
                             env=dict(os.environ, TESTING="False", POOL_SHAPE_MARKS=str(marks)), timeout=180)
        assert run.returncode == 0, run.stderr[-3000:]
        (line,) = [line for line in run.stdout.splitlines() if line.startswith('{"children"')]
        seen[shape] = dict(json.loads(line), mp_main=sum(1 for name in os.listdir(marks)
                                                         if name.startswith("__mp_main__.")))
    assert seen["server"]["generation"] == 1 and seen["server"]["mp_main"] >= 2, ("canary: the server recycles", seen)
    assert seen["daemon"] == {"children": 0, "generation": 0, "mp_main": 0}, seen


def test_a_walk_process_that_does_not_start_in_time_is_a_503(client, monkeypatch):
    _set(monkeypatch, walk_processes=2, walk_seconds_max=0.05)
    got = client.get("/body", params={"kind": "pid"})
    assert got.status_code == 503 and got.json()["detail"]["reason"] == "walk_process_not_ready"


def test_a_request_waits_for_a_busy_pool_a_bounded_time(client, monkeypatch, tmp_path):
    _set(monkeypatch, walk_processes=1, walk_seconds_max=60)
    pid_file, out = str(tmp_path / "pid"), {}
    thread = _hang_in_a_thread(client, pid_file, out)
    _until_written(pid_file)
    _set(monkeypatch, walk_processes=1, walk_seconds_max=2)
    waited = client.get("/body", params={"kind": "pid"})
    open(pid_file + ".go", "w").close()
    thread.join(30)
    assert waited.status_code == 503 and waited.json()["detail"]["reason"] == "walk_pool_busy"


def test_a_walk_that_does_not_finish_in_time_is_stopped(client, warming, monkeypatch, tmp_path):
    process_pool.warm()
    _until_idle(2)
    _set(monkeypatch, walk_processes=2, walk_seconds_max=3)
    pid_file, out = str(tmp_path / "pid"), {}
    thread = _hang_in_a_thread(client, pid_file, out)
    stuck = _until_written(pid_file)
    thread.join(30)
    assert out["response"].status_code == 503
    assert out["response"].json()["detail"]["reason"] == "walk_timed_out"
    for _ in range(50):
        if not psutil.pid_exists(stuck):
            break
        time.sleep(0.1)
    assert not psutil.pid_exists(stuck), "the walk process that ran out of time was not ended"
    assert stuck not in {worker[0].pid for worker in process_pool._idle}
    assert client.get("/body", params={"kind": "pid"}).json()["pid"] != stuck


def test_a_killed_pool_process_fails_only_its_request(client, tmp_path, monkeypatch):
    said, error = [], process_pool.logger.error
    monkeypatch.setattr(process_pool.logger, "error",
                        lambda message, *args, **kwargs: (said.append(message % args), error(message, *args, **kwargs)))
    pid_file, hung = str(tmp_path / "pid"), {}
    thread = _hang_in_a_thread(client, pid_file, hung)
    other = client.get("/body", params={"kind": "pid"})
    killed = _until_written(pid_file)
    assert killed != os.getpid()
    os.kill(killed, 9)
    thread.join(30)
    assert hung["response"].status_code == 500
    assert any("the pool process running this request ended - pid %d" % killed in line for line in said), \
        ("the Server log says which walk process ended under which request (lead 10-13)", said)
    assert other.status_code == 200
    after = client.get("/body", params={"kind": "pid"})
    assert after.status_code == 200 and after.json()["pid"] != killed


def test_a_pool_process_that_died_while_idle_is_not_handed_the_next_body(client):
    idle = client.get("/body", params={"kind": "pid"}).json()["pid"]
    assert idle != os.getpid()
    os.kill(idle, 9)
    time.sleep(0.5)
    after = client.get("/body", params={"kind": "pid"})
    assert after.status_code == 200 and after.json()["pid"] != idle


def _until_idle(count):
    for _ in range(600):
        if len(process_pool._idle) == count:
            return
        time.sleep(0.1)
    raise AssertionError("the pool did not start %d ahead" % count)


def test_the_pool_started_ahead_hands_the_first_body_a_ready_process(client, warming):
    process_pool.warm()
    _until_idle(2)
    ready = {worker[0].pid for worker in process_pool._idle}
    assert client.get("/body", params={"kind": "pid"}).json()["pid"] in ready


def _walk_children(before=frozenset()):
    """Walk processes alive under this one, as psutil sees them - not the pool's own books (lead eb9c328e4)."""
    alive = []
    for child in psutil.Process().children():
        try:
            if (child.pid not in before and child.status() != psutil.STATUS_ZOMBIE
                    and "spawn_main" in " ".join(child.cmdline())):
                alive.append(child.pid)
        except psutil.Error:
            pass
    return alive


def _within_the_size(seconds, size=2, children=None):
    """Idle plus working never above `size` while the pool settles - and, given the children alive before, the walk
    processes alive never above it either."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        with process_pool._cond:
            assert len(process_pool._idle) + process_pool._taken[0] <= size
        if children is not None:
            assert len(_walk_children(children)) <= size, "more walk processes alive than the size"
        time.sleep(0.02)


def test_two_starts_ahead_at_once_stay_within_the_size(client, warming, monkeypatch):
    _set(monkeypatch, walk_processes=1, walk_seconds_max=60)
    before = frozenset(_walk_children())
    process_pool.warm()
    process_pool.warm()
    _within_the_size(8, size=1, children=before)
    assert len(process_pool._idle) == 1
    assert process_pool._taken[0] == 0, "warm's starts were not counted, or not given back"


def test_lowering_the_size_ends_the_extra_one_when_a_walk_returns(client, warming, monkeypatch):
    process_pool.warm()
    _until_idle(2)
    _set(monkeypatch, walk_processes=1, walk_seconds_max=60)
    assert client.get("/body", params={"kind": "pid"}).status_code == 200
    assert len(process_pool._idle) + process_pool._taken[0] <= 1


def test_a_reload_starts_the_pool_ahead_again_and_keeps_no_older_process(client, warming):
    process_pool.warm()
    _until_idle(2)
    before = {worker[0].pid for worker in process_pool._idle}
    process_pool.recycle()
    process_pool.recycle()
    _within_the_size(8)
    _until_idle(2)
    assert all(worker[2] == process_pool._generation[0] for worker in process_pool._idle)
    assert not before & {worker[0].pid for worker in process_pool._idle}


def test_a_body_running_through_a_reload_leaves_its_process_behind(client, tmp_path):
    process_pool.warm()                                         # the server's start (testing mode: it starts none)
    pid_file, out = str(tmp_path / "pid"), {}
    thread = _hang_in_a_thread(client, pid_file, out)
    running = _until_written(pid_file)
    process_pool.recycle()
    open(pid_file + ".go", "w").close()
    thread.join(30)
    assert running not in {worker[0].pid for worker in process_pool._idle}
    assert client.get("/body", params={"kind": "pid"}).json()["pid"] != running


def test_a_reload_while_a_walk_runs_fills_the_pool_back_to_its_size(client, warming, tmp_path):
    """lead eb9c328e4: the walk a reload ran through ends after its answer - a new one takes its place."""
    process_pool.warm()
    _until_idle(2)
    pid_file, out = str(tmp_path / "pid"), {}
    thread = _hang_in_a_thread(client, pid_file, out)
    running = _until_written(pid_file)
    process_pool.recycle()
    _until_idle(1)
    open(pid_file + ".go", "w").close()
    thread.join(30)
    assert out["response"].status_code == 200
    _until_idle(2)
    assert all(worker[2] == process_pool._generation[0] for worker in process_pool._idle)
    assert running not in {worker[0].pid for worker in process_pool._idle}


def test_one_deadline_covers_the_wait_for_a_slot_and_the_answer(client, monkeypatch, tmp_path):
    """lead 9a3c510c5 / eb9c328e4: 4 of a request's 6 s go waiting for the one slot - its answer gets the 2 left, not 6."""
    _set(monkeypatch, walk_processes=1, walk_seconds_max=60)
    first_pid, first = str(tmp_path / "first"), {}
    holding = _hang_in_a_thread(client, first_pid, first)
    _until_written(first_pid)
    _set(monkeypatch, walk_processes=1, walk_seconds_max=6)
    second_pid, second = str(tmp_path / "second"), {}
    waiting = _hang_in_a_thread(client, second_pid, second)
    time.sleep(4)
    open(first_pid + ".go", "w").close()
    _until_written(second_pid)
    time.sleep(4)
    open(second_pid + ".go", "w").close()
    holding.join(30)
    waiting.join(30)
    assert first["response"].status_code == 200
    assert second["response"].status_code == 503
    assert second["response"].json()["detail"]["reason"] == "walk_timed_out"

