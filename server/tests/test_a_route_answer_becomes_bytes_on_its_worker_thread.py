"""총괄 3d1f25056 (소유자 「알아서해」 ②): a sync route's answer becomes bytes on its worker thread, not the event loop -
`runtime.offloop_json`, the route class of the app and every router.

  every route      each sync route of the app with no response model and no response class of its own is wrapped
  same answer      the seat and fastapi's own path give the same status, body and headers - dates, sets, Decimal, a
                   pydantic model, None, a decorator's 201 and 204 (no body), a header a dependency set; NaN refused by
                   both
  no stop          while a big sync answer is made, an async route answers - its longest wait a fraction of what the
                   old path makes it wait
"""
import datetime
import decimal
import os
import sys
import threading
import time

import pytest
from fastapi import Depends, FastAPI, Response
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from runtime import offloop_json                                      # noqa: E402


class _Point(BaseModel):
    x: int
    at: datetime.datetime


def _set_a_header(response: Response):
    response.headers["X-Total-Rows"] = "7"


def _app(seat):
    app = FastAPI()
    if seat:
        app.router.route_class = offloop_json.OffLoopJSONRoute
    when = datetime.datetime(2026, 10, 12, 21, 5, 0, tzinfo=datetime.timezone.utc)

    @app.get("/mixed")
    def mixed():
        return {"when": when, "day": when.date(), "tags": {"b"}, "price": decimal.Decimal("1.50"),
                "whole": decimal.Decimal("3"), "point": _Point(x=1, at=when), "none": None, "pair": (1, "a"),
                "name": "웨이퍼 «A»", 1: "an int key"}

    @app.get("/none")
    def nothing():
        return None

    @app.get("/nan")
    def nan():
        return {"v": float("nan")}

    @app.post("/made", status_code=201)
    def made():
        return {"ok": True}

    @app.delete("/gone", status_code=204)
    def gone():
        return None

    @app.get("/headed", dependencies=[Depends(_set_a_header)])
    def headed():
        return [1, 2]

    @app.get("/response")
    def a_response():
        return Response(content=b"plain", media_type="text/plain")

    return app


def test_every_sync_route_of_the_app_is_wrapped():
    import main
    routes = [r for r in main.app.routes if isinstance(r, APIRoute)]
    plain = [r for r in routes if not _is_async(r) and r.response_model is None]
    assert routes and plain, "the app has no routes - this measured nothing"
    assert {type(r) for r in routes} == {offloop_json.OffLoopJSONRoute}, {type(r).__name__ for r in routes}
    unwrapped = [r.path for r in plain if r.response_class is not offloop_json._EncodedJSONResponse]
    assert unwrapped == [], unwrapped


def _is_async(route):
    import inspect
    endpoint = getattr(route.endpoint, "__wrapped__", route.endpoint)
    return inspect.iscoroutinefunction(endpoint)


@pytest.mark.parametrize("method,path", [("get", "/mixed"), ("get", "/none"), ("get", "/nan"), ("post", "/made"),
                                         ("delete", "/gone"), ("get", "/headed"), ("get", "/response")])
def test_the_seat_answers_as_fastapi_did(method, path):
    before = getattr(TestClient(_app(False), raise_server_exceptions=False), method)(path)
    after = getattr(TestClient(_app(True), raise_server_exceptions=False), method)(path)
    assert (after.status_code, after.content) == (before.status_code, before.content), (path, before.content[:200],
                                                                                        after.content[:200])
    for header in ("content-type", "content-length", "x-total-rows"):
        assert after.headers.get(header) == before.headers.get(header), (path, header)
    if path == "/nan":
        assert after.status_code == 500                           # refused, as before
    if path == "/gone":
        assert after.content == b""


#: About 17 MB as JSON. Built once, before any endpoint, so what is timed is turning it into bytes.
_BIG = {"rows": [{"id": i, "name": "row %d" % i, "at": "2026-10-12", "v": [i, i + 1]} for i in range(250000)]}


def _longest_ping_wait(seat):
    """The longest an async route waits while a big sync answer is turned into bytes and sent. ⚠️ ONE CLIENT IN A
    `with`: outside one, TestClient opens an event loop per request and the pings never share the big answer's loop."""
    app = FastAPI()
    if seat:
        app.router.route_class = offloop_json.OffLoopJSONRoute

    @app.get("/big")
    def big():
        return _BIG

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    with TestClient(app) as client:
        client.get("/ping")
        done, waits = threading.Event(), []

        def pinger():
            while not done.is_set():
                started = time.perf_counter()
                client.get("/ping")
                waits.append(time.perf_counter() - started)
                time.sleep(0.01)
        thread = threading.Thread(target=pinger, daemon=True)
        thread.start()
        time.sleep(0.2)
        assert client.get("/big").status_code == 200
        done.set()
        thread.join(10)
    return max(waits)


def test_an_async_route_answers_while_a_big_answer_is_made():
    old, new = _longest_ping_wait(False), _longest_ping_wait(True)
    assert old > 0.5, "the old path did not stop the loop here (%.3f s) - this measures nothing" % old
    assert new < 0.3 * old, "the seat still stops the loop: %.3f s against %.3f s" % (new, old)
