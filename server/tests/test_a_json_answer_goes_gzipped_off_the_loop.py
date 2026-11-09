"""Lead 11-09 ㄴ: a JSON answer goes gzipped when its asker takes gzip - made where its bytes are made, off the loop:
the route's worker thread (`runtime.offloop_json`) or the pool process (`process_pool._answer`), one judgement
(`offloop_json.gzipped`), the asker's Accept-Encoding set by the HTTP door (`main.db_context_middleware`).

                      takes gzip                               does not
  JSON >= 1 KB here    gzip, the same bytes once unpacked       as before
  JSON >= 1 KB pool    gzip made in the pool process            as before
  JSON < 1 KB          as it is                                 as before
  text (tsv)           as it is                                 as before
  picture · zip file   as they are, their length kept           as before
"""
import gzip
import json
import os
import sys

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.responses import Response

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from database.database import get_db                                   # noqa: E402
from runtime import offloop_json, process_pool                           # noqa: E402
from runtime.offloop_json import OffLoopJSONRoute                       # noqa: E402

BIG = {"rows": [{"value": "S122B-8AB779-%04d" % i, "is_overwrite": False, "sources": []} for i in range(200)]}
PICTURE = b"\x89PNG" + b"\0" * 5000

router = APIRouter(route_class=OffLoopJSONRoute)


@router.get("/answer")
@process_pool.in_pool
def answer(kind: str, db: Session = Depends(get_db)):
    if kind == "big":
        return BIG
    if kind == "page":                              # the grid's own Response (main._table_data_response)
        return Response(json.dumps(BIG).encode(), media_type="application/json")
    if kind == "rows":
        return PlainTextResponse("a\tb\n" * 600, media_type="text/tab-separated-values")
    if kind == "pid":
        return {"pid": os.getpid()}
    return {"ok": 1}


@router.get("/picture")
def picture():
    return Response(PICTURE, media_type="image/png")


@router.get("/bundle")
def bundle(file: str):
    return FileResponse(file, media_type="application/zip", filename="bundle.zip")


def _app():
    import main

    app = FastAPI()
    app.router.route_class = OffLoopJSONRoute
    app.include_router(router)
    app.middleware("http")(main.db_context_middleware)                   # the door that hears Accept-Encoding
    return app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(process_pool, "_settings", lambda: {"walk_processes": 2, "walk_seconds_max": 60})
    monkeypatch.setattr(process_pool, "_warmed", [False])
    with TestClient(_app(), raise_server_exceptions=False) as each:
        yield each
    with process_pool._cond:
        process_pool._generation[0] += 1
        process_pool._drain_locked()


def _here(monkeypatch):
    monkeypatch.setattr(process_pool, "_settings", lambda: {"walk_processes": 0})


def _get(client, path, takes, **params):
    return client.get(path, params=params, headers={"Accept-Encoding": "gzip" if takes else "identity"})


@pytest.mark.parametrize("where", ["here", "pool"])
@pytest.mark.parametrize("kind", ["big", "page"])
def test_a_json_answer_goes_gzipped_and_unpacks_to_the_bytes_sent_plain(client, monkeypatch, where, kind):
    carried = []
    sent = process_pool._reply
    monkeypatch.setattr(process_pool, "_reply", lambda answer: carried.append(len(answer["body"])) or sent(answer))
    if where == "here":
        _here(monkeypatch)
    else:
        assert _get(client, "/answer", True, kind="pid").json()["pid"] != os.getpid()   # canary: the pool is on
        carried.clear()
    packed, plain = _get(client, "/answer", True, kind=kind), _get(client, "/answer", False, kind=kind)
    assert (packed.status_code, plain.status_code) == (200, 200)
    assert packed.headers["content-encoding"] == "gzip" and "accept-encoding" in packed.headers["vary"].lower()
    assert "content-encoding" not in plain.headers
    assert packed.content == plain.content and json.loads(plain.content) == BIG
    assert int(packed.headers["content-length"]) < len(plain.content) // 5
    assert int(plain.headers["content-length"]) == len(plain.content)
    if where == "pool":                         # gzipped in the pool process: the pipe carried the small bytes
        assert carried == [int(packed.headers["content-length"]), len(plain.content)]
    else:
        assert carried == []


@pytest.mark.parametrize("where", ["here", "pool"])
@pytest.mark.parametrize("kind", ["small", "rows"])
def test_a_small_answer_or_text_goes_as_it_is(client, monkeypatch, where, kind):
    if where == "here":
        _here(monkeypatch)
    packed, plain = _get(client, "/answer", True, kind=kind), _get(client, "/answer", False, kind=kind)
    assert packed.status_code == 200 and "content-encoding" not in packed.headers
    assert (packed.content, packed.headers["content-length"]) == (plain.content, plain.headers["content-length"])
    assert len(plain.content) == {"small": 8, "rows": 2400}[kind]


def test_a_picture_goes_as_it_is(client):
    got = _get(client, "/picture", True)
    assert "content-encoding" not in got.headers
    assert (got.content, int(got.headers["content-length"])) == (PICTURE, len(PICTURE))


def test_a_zip_file_goes_as_it_is_with_its_length(client, tmp_path):
    path = tmp_path / "bundle.zip"
    path.write_bytes(b"PK\x03\x04" + b"\0" * 300000)
    got = _get(client, "/bundle", True, file=str(path))
    assert "content-encoding" not in got.headers
    assert int(got.headers["content-length"]) == 300004 == len(got.content)


def test_the_judgement_reads_the_asker_the_size_and_the_kind():
    body = json.dumps(BIG).encode()
    assert gzip.decompress(offloop_json.gzipped(body, "gzip, deflate, br")) == body
    assert offloop_json.gzipped(body, "") is None                                   # no request
    assert offloop_json.gzipped(body, "identity") is None
    assert offloop_json.gzipped(body[:offloop_json.GZIP_MIN_BYTES - 1], "gzip") is None
    assert offloop_json.gzipped(body[:offloop_json.GZIP_MIN_BYTES], "gzip") is not None
    assert offloop_json.gzipped(body, "gzip", "image/png") is None
    assert offloop_json.gzipped(body, "gzip", "application/json; charset=utf-8") is not None
