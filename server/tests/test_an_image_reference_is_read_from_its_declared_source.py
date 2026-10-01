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
            ("k1.png", PNG, "pics:a.png"), ("k2", b"two", "again:k2")])
    return {"dialect": "sqlite", "database": str(path)}


def _db_sources(connection, root):
    return {"pics": {"kind": "folder", "root": str(root)},
            "bytes": {"kind": "db", "connection": connection,
                      "query": "SELECT data FROM images WHERE key = :key"},
            "refs": {"kind": "db", "connection": connection,
                     "query": "SELECT ref FROM images WHERE key = :key"},
            "again": {"kind": "db", "connection": connection,
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
    answer = client.get("/api/image", params={"ref": "bytes:x' OR '1'='1"})
    assert answer.status_code == 404
    with sqlite3.connect(images_db["database"]) as db:
        assert db.execute("SELECT count(*) FROM images").fetchone()[0] == 2


def test_db_text_is_read_once_more_as_a_reference_and_only_once(client, declare, pics, images_db):
    declare(_db_sources(images_db, pics))
    assert client.get("/api/image", params={"ref": "refs:k1.png"}).content == PNG
    answer = client.get("/api/image", params={"ref": "refs:k2"})      # k2 -> again:k2 -> again:k2
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

def test_a_url_source_hands_the_address_on(client, declare):
    declare({"vendor": {"kind": "url", "base": "https://img.example.com/p/"}})
    answer = client.get("/api/image", params={"ref": "vendor:a.png"})
    assert answer.status_code in (302, 307)
    assert answer.headers["location"] == "https://img.example.com/p/a.png"
    raw = client.get("/api/image", params={"ref": "https://other.example.com/x.png"})
    assert raw.headers["location"] == "https://other.example.com/x.png"


def test_a_url_source_may_be_fetched_by_the_server_when_declared(client, declare, monkeypatch):
    import requests

    class Answer:
        status_code, content, headers = 200, PNG, {"content-type": "image/png"}
    asked = []
    monkeypatch.setattr(requests, "get", lambda url, timeout: asked.append(url) or Answer())
    declare({"plain": {"kind": "url", "base": "http://intranet/img/", "proxy": True}})
    answer = client.get("/api/image", params={"ref": "plain:a.png"})
    assert answer.status_code == 200 and answer.content == PNG
    assert asked == ["http://intranet/img/a.png"]


# ------------------------------------------------------------------------------ refusals

def test_an_undeclared_source_is_refused_by_name(client, declare):
    declare({})
    answer = client.get("/api/image", params={"ref": "nowhere:a.png"})
    assert answer.status_code == 404 and "nowhere" in answer.json()["detail"]
    assert client.get("/api/image", params={"ref": "no-colon"}).status_code == 400
