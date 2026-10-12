"""The pool seat (`runtime.process_pool.in_pool`, lead b47388fde): a route's body answers from a process of its own with
the same status, headers and bytes as when it runs here; a pool process killed mid-body fails that request only; a
reload's recycle gives the next body a fresh process; a request waits a bounded time; code that calls the walk's
function itself gets a dict, as before (QA on 407448592)."""
import ast
import datetime
import os
import sys
import threading
import time

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
    with TestClient(app, raise_server_exceptions=False) as each:
        yield each
    with process_pool._cond:
        process_pool._generation[0] += 1
        process_pool._drain_locked()


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


def test_the_server_starts_the_pool_ahead_after_the_testing_return():
    """The startup event's order, read from main.py: `process_pool.warm()` comes after the TESTING early return."""
    tree = ast.parse(open(os.path.join(SERVER_DIR, "main.py"), encoding="utf-8").read())
    (startup,) = [node for node in ast.walk(tree)
                  if isinstance(node, ast.AsyncFunctionDef) and node.name == "startup_event"]
    testing_return = next(i for i, stmt in enumerate(startup.body)
                          if isinstance(stmt, ast.If) and "TESTING" in ast.unparse(stmt.test)
                          and any(isinstance(s, ast.Return) for s in stmt.body))
    warm_at = [i for i, stmt in enumerate(startup.body) if "process_pool.warm()" in ast.unparse(stmt)]
    assert warm_at and warm_at[0] > testing_return


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


def test_a_walk_that_does_not_finish_in_time_is_stopped(client, monkeypatch, tmp_path):
    process_pool.warm()
    _until_idle(2)
    _set(monkeypatch, walk_processes=2, walk_seconds_max=3)
    pid_file, out = str(tmp_path / "pid"), {}
    thread = _hang_in_a_thread(client, pid_file, out)
    stuck = _until_written(pid_file)
    thread.join(30)
    assert out["response"].status_code == 503
    assert out["response"].json()["detail"]["reason"] == "walk_timed_out"
    time.sleep(0.5)
    assert stuck not in {worker[0].pid for worker in process_pool._idle}
    assert client.get("/body", params={"kind": "pid"}).json()["pid"] != stuck


def test_a_killed_pool_process_fails_only_its_request(client, tmp_path):
    pid_file, hung = str(tmp_path / "pid"), {}
    thread = _hang_in_a_thread(client, pid_file, hung)
    other = client.get("/body", params={"kind": "pid"})
    killed = _until_written(pid_file)
    assert killed != os.getpid()
    os.kill(killed, 9)
    thread.join(30)
    assert hung["response"].status_code == 500
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


def test_the_pool_started_ahead_hands_the_first_body_a_ready_process(client):
    process_pool.warm()
    _until_idle(2)
    ready = {worker[0].pid for worker in process_pool._idle}
    assert client.get("/body", params={"kind": "pid"}).json()["pid"] in ready


def test_a_reload_starts_the_pool_ahead_again_and_keeps_no_older_process(client):
    process_pool.warm()
    _until_idle(2)
    before = {worker[0].pid for worker in process_pool._idle}
    process_pool.recycle()
    _until_idle(2)
    assert all(worker[2] == process_pool._generation[0] for worker in process_pool._idle)
    assert not before & {worker[0].pid for worker in process_pool._idle}


def test_a_body_running_through_a_reload_leaves_its_process_behind(client, tmp_path):
    pid_file, out = str(tmp_path / "pid"), {}
    thread = _hang_in_a_thread(client, pid_file, out)
    running = _until_written(pid_file)
    process_pool.recycle()
    open(pid_file + ".go", "w").close()
    thread.join(30)
    assert running not in {worker[0].pid for worker in process_pool._idle}
    assert client.get("/body", params={"kind": "pid"}).json()["pid"] != running
