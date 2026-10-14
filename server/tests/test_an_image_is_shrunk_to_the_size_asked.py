# -*- coding: utf-8 -*-
"""총괄 1084b4bfd (소유자 «썸네일은 주어진 칸에 딱 맞게 비율은 보존»): GET /api/image?px= sends the picture with its longer
side at px, the ratio kept, from any source (folder · db · url) through the one `resolve`; kept by size, a changed original
is another key; no px - the original as before. Without Pillow the original goes and one line says why."""
import io
import json
import logging
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import image_sources  # noqa: E402
from PIL import Image  # noqa: E402


def _picture(size, fmt="PNG"):
    out = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(out, fmt)
    return out.getvalue()


WIDE = _picture((400, 200))
TALL = _picture((300, 600), "JPEG")


def _size(data):
    return Image.open(io.BytesIO(data)).size


@pytest.fixture(autouse=True)
def _no_thumbs_kept(monkeypatch):
    monkeypatch.setattr(image_sources, "_THUMBS", type(image_sources._THUMBS)())


@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import main

    app = FastAPI()
    app.add_api_route("/api/image", main.get_image, methods=["GET"])
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def sources(tmp_path, monkeypatch):
    root = tmp_path / "pics"
    root.mkdir()
    (root / "wide.png").write_bytes(WIDE)
    (root / "tall.jpg").write_bytes(TALL)
    (root / "broken.png").write_bytes(b"\x89PNG\r\n\x1a\nnot really")
    db = tmp_path / "images.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE images (key TEXT, data BLOB)")
        connection.execute("INSERT INTO images VALUES (?, ?)", ("w.png", WIDE))
    path = tmp_path / "image_sources.json"
    path.write_text(json.dumps({
        "pics": {"kind": "folder", "root": str(root)},
        "store": {"kind": "db", "connection": {"dialect": "sqlite", "database": str(db)},
                  "query": "SELECT data FROM images WHERE key = :key"},
        "vendor": {"kind": "url", "base": "https://img.example.com/p/"}}), encoding="utf-8")
    monkeypatch.setattr(image_sources, "CONFIG_PATH", str(path))

    import requests

    class _Answer:
        status_code, headers = 200, {"content-type": "image/png"}

        def iter_content(self, size):
            yield WIDE

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: _Answer())
    return root


@pytest.mark.parametrize("ref", ["pics:wide.png", "store:w.png", "vendor:wide.png"])
def test_each_source_answers_a_thumbnail_at_the_size_asked(client, sources, ref):
    for px in (16, 64, 300):
        answer = client.get("/api/image", params={"ref": ref, "px": px})
        assert answer.status_code == 200 and answer.headers["content-type"] == "image/png"
        assert _size(answer.content) == (px, px // 2), "the longer side at px, the ratio kept"
        assert answer.headers["cache-control"] == image_sources.CACHE_CONTROL
    plain = client.get("/api/image", params={"ref": ref})
    assert plain.content == WIDE, "no px - the original, as before"


def test_a_jpeg_stays_a_jpeg_and_a_small_original_is_not_made_larger(client, sources):
    answer = client.get("/api/image", params={"ref": "pics:tall.jpg", "px": 64})
    assert answer.headers["content-type"] == "image/jpeg" and _size(answer.content) == (32, 64)
    big = client.get("/api/image", params={"ref": "pics:tall.jpg", "px": 1024})
    assert big.content == TALL, "an original no larger than px goes as it is - not encoded again"


@pytest.mark.parametrize("px", [image_sources.PX_MIN - 1, image_sources.PX_MAX + 1, 0])
def test_a_size_outside_the_bounds_is_refused(client, sources, px):
    assert client.get("/api/image", params={"ref": "pics:wide.png", "px": px}).status_code == 422


def test_a_thumbnail_is_kept_by_size_and_a_changed_original_is_another_key(client, sources, monkeypatch):
    opened = []
    real = Image.open
    monkeypatch.setattr(Image, "open", lambda *a, **k: opened.append(1) or real(*a, **k))
    for _ in range(3):
        client.get("/api/image", params={"ref": "pics:wide.png", "px": 64})
    client.get("/api/image", params={"ref": "pics:wide.png", "px": 32})
    assert len(opened) == 2, "one shrink a size"
    picture = sources / "wide.png"
    picture.write_bytes(_picture((100, 400)))
    os.utime(picture, (os.stat(picture).st_mtime + 5,) * 2)
    assert _size(client.get("/api/image", params={"ref": "pics:wide.png", "px": 64}).content) == (16, 64)


def test_the_kept_thumbnails_stay_under_their_cap(client, sources, monkeypatch):
    one = len(image_sources.shrink(("bytes", WIDE, "image/png"), 64)[1])
    monkeypatch.setattr(image_sources, "THUMB_CACHE_BYTES", one * 2)
    for px in (40, 50, 60, 64):
        image_sources.shrink(("bytes", WIDE, "image/png"), px)
    assert sum(len(each[1]) for each in image_sources._THUMBS.values()) <= one * 2
    assert [key[-1] for key in image_sources._THUMBS] == [60, 64], "the oldest let go first"


def test_what_does_not_shrink_goes_as_it_is(client, sources):
    answer = client.get("/api/image", params={"ref": "pics:broken.png", "px": 64})
    assert answer.status_code == 200 and answer.content == b"\x89PNG\r\n\x1a\nnot really"


def test_without_pillow_the_original_goes_and_one_line_says_why(client, sources, monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "PIL", None)
    monkeypatch.setattr(image_sources, "_SAID_NO_PILLOW", [])
    with caplog.at_level(logging.WARNING, logger="Server"):
        for _ in range(2):
            assert client.get("/api/image", params={"ref": "pics:wide.png", "px": 64}).content == WIDE
    said = [m for m in caplog.messages if "Pillow is not installed" in m]
    assert len(said) == 1, said
