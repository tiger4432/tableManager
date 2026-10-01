# -*- coding: utf-8 -*-
"""총괄 785b2ef54 · 20e1c09df — an image reference is one grammar (an http(s) address, or
`<source>:<path or key>`), read from a source declared in `image_sources.json` through one
read-only route, `GET /api/image?ref=`."""
import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import image_sources  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\nfixture"


@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import main

    app = FastAPI()
    app.add_api_route("/api/image", main.get_image, methods=["GET"])
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def declare(tmp_path, monkeypatch):
    path = tmp_path / "image_sources.json"
    monkeypatch.setattr(image_sources, "CONFIG_PATH", str(path))

    def write(sources):
        path.write_text(json.dumps(sources), encoding="utf-8")
    return write


@pytest.fixture
def pics(tmp_path, declare):
    root = tmp_path / "pics"
    (root / "sub").mkdir(parents=True)
    (root / "a.png").write_bytes(PNG)
    (root / "sub" / "b.png").write_bytes(PNG + b"b")
    (tmp_path / "outside.png").write_bytes(b"secret")
    declare({"pics": {"kind": "folder", "root": str(root)}})
    return root


@pytest.fixture
def images_db(tmp_path):
    path = tmp_path / "images.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE images (key TEXT, data BLOB, ref TEXT)")
        db.executemany("INSERT INTO images VALUES (?, ?, ?)", [
            ("k1.png", PNG, "pics:a.png"), ("k2", b"two", "chain:k3"), ("k3", None, "pics:a.png")])
    return {"dialect": "sqlite", "database": str(path)}


def _db_sources(connection, root):
    return {"pics": {"kind": "folder", "root": str(root)},
            "bytes": {"kind": "db", "connection": connection,
                      "query": "SELECT data FROM images WHERE key = :key"},
            "refs": {"kind": "db", "connection": connection,
                     "query": "SELECT ref FROM images WHERE key = :key"},
            "chain": {"kind": "db", "connection": connection,
                      "query": "SELECT ref FROM images WHERE key = :key"}}


# ------------------------------------------------------------------------------- folder

def test_a_folder_reference_is_served_from_inside_its_root(client, pics):
    assert client.get("/api/image", params={"ref": "pics:a.png"}).content == PNG
    assert client.get("/api/image", params={"ref": "pics:sub/b.png"}).content == PNG + b"b"


@pytest.mark.parametrize("escape", ["../outside.png", "..\\outside.png", "sub/../../outside.png",
                                    "ABSOLUTE"])
def test_a_path_that_climbs_out_of_the_root_is_refused(client, pics, escape):
    if escape == "ABSOLUTE":
        escape = str(pics.parent / "outside.png")
    answer = client.get("/api/image", params={"ref": "pics:" + escape})
    assert answer.status_code == 400 and b"secret" not in answer.content
    assert "outside the root" in answer.json()["detail"]


def test_a_missing_file_is_a_404_that_names_it(client, pics):
    answer = client.get("/api/image", params={"ref": "pics:nope.png"})
    assert answer.status_code == 404 and "nope.png" in answer.json()["detail"]


# ----------------------------------------------------------------------------------- db

def test_db_bytes_come_back_as_they_are(client, declare, pics, images_db):
    declare(_db_sources(images_db, pics))
    answer = client.get("/api/image", params={"ref": "bytes:k1.png"})
    assert answer.status_code == 200 and answer.content == PNG
    assert answer.headers["content-type"] == "image/png"


def test_a_db_key_is_bound_not_spliced(client, declare, pics, images_db):
    declare(_db_sources(images_db, pics))

    def rows():
        with sqlite3.connect(images_db["database"]) as db:
            return db.execute("SELECT count(*) FROM images").fetchone()[0]
    before = rows()
    answer = client.get("/api/image", params={"ref": "bytes:x' OR '1'='1"})
    assert answer.status_code == 404
    assert rows() == before


def test_db_text_is_read_once_more_as_a_reference_and_only_once(client, declare, pics, images_db):
    declare(_db_sources(images_db, pics))
    assert client.get("/api/image", params={"ref": "refs:k1.png"}).content == PNG
    # a chain, not a loop: refs:k2 -> chain:k3 -> pics:a.png. Read on, it would find a file
    answer = client.get("/api/image", params={"ref": "refs:k2"})
    assert answer.status_code == 500 and "another reference twice" in answer.json()["detail"]


@pytest.mark.parametrize("query", ["SELECT data FROM images",
                                   "SELECT data FROM images WHERE key = :key AND ref = :ref"])
def test_a_query_must_bind_the_key_and_nothing_else(client, declare, images_db, query):
    declare({"bad": {"kind": "db", "connection": images_db, "query": query}})
    answer = client.get("/api/image", params={"ref": "bad:k1.png"})
    assert answer.status_code == 500 and ":key" in answer.json()["detail"]


def test_a_password_comes_from_the_named_variable_and_its_absence_is_named(client, declare,
                                                                         images_db, monkeypatch):
    monkeypatch.delenv("ASSY_TEST_IMAGE_DB_PASSWORD", raising=False)
    declare({"locked": {"kind": "db", "query": "SELECT data FROM images WHERE key = :key",
                        "connection": dict(images_db, password_env="ASSY_TEST_IMAGE_DB_PASSWORD")}})
    answer = client.get("/api/image", params={"ref": "locked:k1.png"})
    assert answer.status_code == 500 and "ASSY_TEST_IMAGE_DB_PASSWORD" in answer.json()["detail"]


# ---------------------------------------------------------------------------------- url

class _Answer:
    """What `requests.get(..., stream=True)` hands back, and how much of it was read."""

    def __init__(self, status=200, media="image/png", chunks=(PNG,), headers=None):
        self.status_code = status
        self.headers = dict(headers or {}, **({"content-type": media} if media else {}))
        self._chunks, self.read = list(chunks), 0

    def iter_content(self, size):
        for chunk in self._chunks:
            self.read += 1
            yield chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fetched(monkeypatch):
    """Every fetch the server makes, and what each one answers."""
    import requests

    asked, answer = [], {"next": _Answer()}

    def get(url, **kwargs):
        asked.append((url, kwargs))
        if isinstance(answer["next"], Exception):
            raise answer["next"]
        return answer["next"]
    monkeypatch.setattr(requests, "get", get)
    return asked, answer


@pytest.mark.parametrize("proxy", ["absent", False, True])
def test_a_url_source_is_fetched_by_the_server_whatever_its_retired_proxy_cell(
        client, declare, fetched, proxy):
    """[총괄 f087403fe, 소유자 「그래야함」] Every image goes through the server; `proxy` is not read
    and a declaration that still carries it is not refused."""
    source = {"kind": "url", "base": "https://img.example.com/p/"}
    if proxy != "absent":
        source["proxy"] = proxy
    declare({"vendor": source})
    answer = client.get("/api/image", params={"ref": "vendor:a.png"})
    assert answer.status_code == 200 and answer.content == PNG
    assert [url for url, _k in fetched[0]] == ["https://img.example.com/p/a.png"]


def test_an_address_cell_is_fetched_by_the_server_too(client, declare, fetched):
    declare({})
    answer = client.get("/api/image", params={"ref": "https://other.example.com/x.png"})
    assert answer.status_code == 200 and answer.content == PNG
    assert fetched[0] == [("https://other.example.com/x.png",
                           {"timeout": 10, "allow_redirects": False, "stream": True})]


@pytest.mark.parametrize("ref", ["plain:a.png", "http://intranet/img/a.png"])
def test_a_fetch_does_not_follow_a_redirect(client, declare, fetched, ref):
    fetched[1]["next"] = _Answer(status=302, media=None, headers={"location": "http://inside/x"})
    declare({"plain": {"kind": "url", "base": "http://intranet/img/"}})
    answer = client.get("/api/image", params={"ref": ref})
    assert answer.status_code == 502 and "not followed" in answer.json()["detail"]
    assert all(k["allow_redirects"] is False for _url, k in fetched[0])


@pytest.mark.parametrize("media", ["text/html", "application/json", None])
def test_a_fetched_answer_that_is_not_an_image_is_refused(client, declare, fetched, media):
    fetched[1]["next"] = _Answer(media=media, chunks=(b"<html>inside</html>",))
    declare({})
    answer = client.get("/api/image", params={"ref": "https://intranet/page"})
    assert answer.status_code == 502 and "not an image" in answer.json()["detail"]
    assert b"inside" not in answer.content


def test_an_image_type_with_parameters_is_still_an_image(client, declare, fetched):
    fetched[1]["next"] = _Answer(media="Image/PNG; charset=binary")
    declare({})
    answer = client.get("/api/image", params={"ref": "https://img.example.com/a.png"})
    assert answer.status_code == 200 and answer.headers["content-type"] == "image/png"


def test_a_fetch_stops_reading_past_the_size_limit(client, declare, fetched, monkeypatch):
    monkeypatch.setattr(image_sources, "MAX_BYTES", 10)
    big = _Answer(chunks=[b"1234"] * 100)
    fetched[1]["next"] = big
    declare({})
    answer = client.get("/api/image", params={"ref": "https://img.example.com/big.png"})
    assert answer.status_code == 502 and "larger than 10 bytes" in answer.json()["detail"]
    assert big.read == 3, "the fetch kept reading past the limit"


def test_a_fetch_that_fails_says_which(client, declare, fetched):
    import requests

    fetched[1]["next"] = requests.ConnectionError("no route to host")
    declare({})
    answer = client.get("/api/image", params={"ref": "https://nowhere.example.com/a.png"})
    assert answer.status_code == 502 and "nowhere.example.com" in answer.json()["detail"]


# ------------------------------------------------------------------------------ refusals

@pytest.mark.parametrize("value", ["@evil.com/a.png", ".evil.com/a.png", ":99999/a.png"])
def test_a_value_cannot_move_the_host(client, declare, fetched, value):
    """[총괄 e96551d02] Joined to a base without a trailing «/», a value could name a new host."""
    declare({"vendor": {"kind": "url", "base": "https://img.example.com"}})
    answer = client.get("/api/image", params={"ref": "vendor:" + value})
    assert answer.status_code == 400 and "leaves the host" in answer.json()["detail"]
    assert fetched[0] == [], "the server fetched from a host nobody declared"


def test_the_same_value_under_a_base_ending_in_a_slash_stays_home(client, declare, fetched):
    declare({"vendor": {"kind": "url", "base": "https://img.example.com/"}})
    assert client.get("/api/image", params={"ref": "vendor:@evil.com/a.png"}).status_code == 200
    assert [url for url, _k in fetched[0]] == ["https://img.example.com/@evil.com/a.png"]


def test_a_db_source_that_cannot_be_read_says_which(client, declare, tmp_path):
    declare({"gone": {"kind": "db", "query": "SELECT data FROM images WHERE key = :key",
                      "connection": {"dialect": "sqlite",
                                     "database": str(tmp_path / "no" / "such" / "dir.db")}}})
    answer = client.get("/api/image", params={"ref": "gone:k1.png"})
    assert answer.status_code == 502 and "'gone' could not be read" in answer.json()["detail"]


def test_an_undeclared_source_is_refused_by_name(client, declare):
    declare({})
    answer = client.get("/api/image", params={"ref": "nowhere:a.png"})
    assert answer.status_code == 404 and "nowhere" in answer.json()["detail"]
    assert client.get("/api/image", params={"ref": "no-colon"}).status_code == 400


# --------------------------------------------------------------------------------- cache

def test_every_answer_may_be_kept_by_the_browser_and_no_refusal_is(client, declare, pics,
                                                                  images_db, fetched):
    """[총괄 191912ce2] The main grid's preview revisits the same cells; a refusal must be asked
    again at once, so that a fixed declaration is read the next time."""
    declare(dict(_db_sources(images_db, pics),
                 vendor={"kind": "url", "base": "https://img.example.com/"}))
    for ref in ("pics:a.png", "bytes:k1.png", "vendor:a.png", "https://img.example.com/a.png"):
        answer = client.get("/api/image", params={"ref": ref})
        assert answer.status_code == 200, ref
        assert answer.headers.get("cache-control") == image_sources.CACHE_CONTROL, ref
    assert image_sources.CACHE_CONTROL.startswith("private, max-age=")
    for ref in ("pics:nope.png", "pics:../outside.png", "nowhere:a.png", "refs:k2"):
        answer = client.get("/api/image", params={"ref": ref})
        assert answer.status_code >= 400 and "cache-control" not in answer.headers, ref
