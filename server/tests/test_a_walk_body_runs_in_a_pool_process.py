"""The pool seat (`runtime.process_pool.in_pool`, lead b47388fde): a route's body answers from a process
of its own with the same status, headers and bytes as when it runs here; a pool process killed mid-body
fails that request only; a reload's recycle gives the next body a fresh process."""
import datetime
import os
import sys
import threading
import time

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.database import get_db                                    # noqa: E402
from runtime import process_pool                                        # noqa: E402
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


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(process_pool, "size", lambda settings=None: 2)
    with TestClient(app, raise_server_exceptions=False) as each:
        yield each
    process_pool.recycle()


def _seen(response):
    headers = {k: v for k, v in response.headers.items() if k != "server-timing"}
    return response.status_code, headers, response.content


@pytest.mark.parametrize("kind", ["json", "rows", "refuse", "boom"])
def test_a_pool_answer_is_the_answer_given_here(client, monkeypatch, kind):
    pooled = _seen(client.get("/body", params={"kind": kind}))
    monkeypatch.setattr(process_pool, "size", lambda settings=None: 0)
    here = _seen(client.get("/body", params={"kind": kind}))
    assert pooled == here
    assert pooled[0] == {"json": 200, "rows": 200, "refuse": 422, "boom": 500}[kind]


def test_the_pool_started_ahead_hands_the_first_body_a_ready_process(client):
    process_pool.recycle()
    process_pool.warm()
    for _ in range(600):
        if len(process_pool._idle) == 2:
            break
        time.sleep(0.1)
    ready = {worker[0].pid for worker in process_pool._idle}
    assert len(ready) == 2
    assert client.get("/body", params={"kind": "pid"}).json()["pid"] in ready


def test_the_body_ran_in_another_process(client):
    assert client.get("/body", params={"kind": "pid"}).json()["pid"] != os.getpid()


def test_a_killed_pool_process_fails_only_its_request(client, tmp_path):
    pid_file = str(tmp_path / "pid")
    hung = {}
    thread = threading.Thread(target=lambda: hung.setdefault(
        "response", client.get("/body", params={"kind": "hang", "pid_file": pid_file})))
    thread.start()
    other = client.get("/body", params={"kind": "pid"})
    for _ in range(300):
        if os.path.exists(pid_file) and open(pid_file).read():
            break
        time.sleep(0.1)
    killed = int(open(pid_file).read())
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


def _until_written(path):
    for _ in range(300):
        if os.path.exists(path) and open(path).read():
            return int(open(path).read())
        time.sleep(0.1)
    raise AssertionError("the body did not start")


def test_a_reload_gives_the_next_body_a_fresh_process(client):
    before = client.get("/body", params={"kind": "pid"}).json()["pid"]
    assert client.get("/body", params={"kind": "pid"}).json()["pid"] == before
    process_pool.recycle()
    assert client.get("/body", params={"kind": "pid"}).json()["pid"] != before


def test_a_body_running_through_a_reload_leaves_its_process_behind(client, tmp_path):
    pid_file = str(tmp_path / "pid")
    thread = threading.Thread(target=lambda: client.get(
        "/body", params={"kind": "hang", "pid_file": pid_file}))
    thread.start()
    running = _until_written(pid_file)
    process_pool.recycle()
    open(pid_file + ".go", "w").close()
    thread.join(30)
    assert client.get("/body", params={"kind": "pid"}).json()["pid"] != running
