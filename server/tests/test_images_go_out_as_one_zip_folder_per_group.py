# -*- coding: utf-8 -*-
"""Owner 11-12 ㄴ (lead): POST /api/images/zip streams the images named, one folder per group, each read by
GET /api/image's reader, stored as they are; a refused ref is said in _not_included.txt; too many is refused before
any read. The route opens no database session and writes nothing to disk but the response."""
import io
import json
import os
import sys
import tempfile
import zipfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import image_sources  # noqa: E402
import image_zip  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 300
JPG = b"\xff\xd8\xff" + b"j" * 500


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import main

    a, b = tmp_path / "pics" / "a", tmp_path / "pics" / "b"
    a.mkdir(parents=True)
    b.mkdir()
    (a / "x.png").write_bytes(PNG)
    (b / "x.png").write_bytes(PNG[::-1])
    (a / "y.jpg").write_bytes(JPG)
    path = tmp_path / "image_sources.json"
    path.write_text(json.dumps({"pics": {"kind": "folder", "root": str(tmp_path / "pics")}}), encoding="utf-8")
    monkeypatch.setattr(image_sources, "CONFIG_PATH", str(path))
    app = FastAPI()
    app.add_api_route("/api/images/zip", main.images_zip, methods=["POST"])
    return TestClient(app)


BODY = {"filename": "lot: A?", "folders": [
    {"path": ["lot A", "w/1"], "refs": [{"ref": "pics:a/x.png"}, {"ref": "pics:b/x.png"}, {"ref": "pics:a/y.jpg",
                                                                                          "name": "CON"}]},
    {"path": ["", "lot B"], "refs": [{"ref": "pics:a/x.png"}, {"ref": "pics:a/missing.png"}]}]}


def _zip(answer):
    assert answer.status_code == 200, answer.text
    return zipfile.ZipFile(io.BytesIO(answer.content))


def test_two_folders_nested_a_collision_and_a_refused_ref(client):
    answer = client.post("/api/images/zip", json=BODY)
    z = _zip(answer)
    assert answer.headers["content-disposition"] == "attachment; filename*=UTF-8''lot_%20A_.zip"
    assert sorted(z.namelist()) == sorted([
        "lot A/w_1/x.png", "lot A/w_1/x (2).png", "lot A/w_1/_CON.jpg",
        "(Empty)/lot B/x.png", image_zip.NOT_INCLUDED])
    assert z.read("lot A/w_1/x.png") == PNG and z.read("lot A/w_1/x (2).png") == PNG[::-1]
    assert z.read("lot A/w_1/_CON.jpg") == JPG
    assert {i.compress_type for i in z.infolist()} == {zipfile.ZIP_STORED}
    said = z.read(image_zip.NOT_INCLUDED).decode("utf-8").splitlines()
    assert said[0] == "folder\tref\twhy" and len(said) == 2
    assert said[1].startswith("(Empty)/lot B\tpics:a/missing.png\t") and len(said[1].split("\t")[2]) > 0


def test_too_many_is_refused_before_any_read(client, monkeypatch):
    monkeypatch.setattr(image_zip, "MAX_IMAGES", 5)
    _zip(client.post("/api/images/zip", json=BODY))                                  # 5 images at a cap of 5 - streamed
    six = dict(BODY, folders=BODY["folders"] + [{"path": ["c"], "refs": [{"ref": "pics:a/x.png"}]}])
    read = []
    monkeypatch.setattr(image_sources, "resolve", lambda ref, *a, **k: read.append(ref))
    answer = client.post("/api/images/zip", json=six)
    assert answer.status_code == 413 and read == []
    assert answer.json()["detail"] == "6 images asked; one zip holds at most 5 - pick fewer groups or rows"


def test_the_route_opens_no_session_and_writes_nothing_to_disk(client, monkeypatch, tmp_path):
    import inspect

    from sqlalchemy import event

    import main
    from database.database import engine

    assert "db" not in inspect.signature(main.images_zip).parameters
    checkouts = []

    def seen(*a):
        checkouts.append(1)

    event.listen(engine, "checkout", seen)

    def refused(*a, **k):
        raise AssertionError("a temporary file was asked for")

    for name in ("TemporaryFile", "NamedTemporaryFile", "SpooledTemporaryFile", "mkstemp", "mkdtemp"):
        monkeypatch.setattr(tempfile, name, refused)
    before = sorted(os.listdir(tmp_path)), sorted(os.listdir(os.getcwd()))
    try:
        _zip(client.post("/api/images/zip", json=BODY))
    finally:
        event.remove(engine, "checkout", seen)
    assert checkouts == []
    assert (sorted(os.listdir(tmp_path)), sorted(os.listdir(os.getcwd()))) == before
