# -*- coding: utf-8 -*-
"""A picture pasted or dropped on a grid image cell (owner 11-05 ㄱ): POST /tables/{t}/images keeps it under the folder
source that declares `receive` and answers its reference; the scheduler's line sweeps what no image cell's current
value has held for `receive.keep_days` days (the day first seen unreferenced is kept in the root's state file).

    route   receivers 0 / 1 / 2 · max_mb exact and +1 byte · Content-Length past the limit (the body not read) ·
            six picture heads and two that are not · not an image column · an unknown table · twice, two names
    sweep   held · first day unreferenced · keep_days - 1 · keep_days · held again · names it did not make ·
            a link out of the root · keep_days absent · no receiver · held by another table · made after the listing ·
            the removed picture's sentence
"""
import datetime
import json
import os

import pytest

import image_sources
from database import crud, models

TABLES = {"im_a": {"business_key": "k", "composite_key_source": ["k"],
                   "column_types": {"k": "string", "pic": "image", "note": "string"}},
          "im_b": {"business_key": "k", "composite_key_source": ["k"], "column_types": {"k": "string", "shot": "image"}}}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
HEADS = {"png": PNG, "jpg": b"\xff\xd8\xff\xe0" + b"\x00" * 40, "gif": b"GIF89a" + b"\x00" * 40,
         "bmp": b"BM" + b"\x00" * 40, "webp": b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 40,
         "tif": b"II*\x00" + b"\x00" * 40}
DAY = datetime.date(2026, 11, 5)


def _sources(root, keep_days=3, max_mb=0.01, receivers=1):
    out = {"_comment": "x", "photos": {"kind": "folder", "root": str(root / "photos")}}
    for n in range(receivers):
        receive = {"max_mb": max_mb}
        if keep_days is not None:
            receive["keep_days"] = keep_days
        out["up%d" % n] = {"kind": "folder", "root": str(root / ("up%d" % n)), "receive": receive}
    return out


@pytest.fixture(name="tables")
def fixture_tables(db_session, monkeypatch):
    for name, config in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, config)
    models.init_dynamic_models(crud.TABLE_CONFIG)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind(), tables=[models.DYNAMIC_TABLES[t].__table__ for t in TABLES])
    return db_session


def _hold(db, table, column, ref, key="r1"):
    model = models.DYNAMIC_TABLES[table]
    row = db.query(model).filter(model.k == key).first()
    if row is None:
        db.add(model(row_id=key + table, k=key, business_key_val=key, **{column: ref}))
    else:
        setattr(row, column, ref)
    db.commit()


def _post(client, data, table="im_a", column="pic", **headers):
    return client.post("/tables/%s/images?column=%s" % (table, column), files={"file": ("x.bin", data)},
                       headers=headers)


# ── route ──

def test_no_receiver_two_receivers_and_one(client, tables, tmp_path, monkeypatch):
    none, two = _post_with(client, monkeypatch, tmp_path, 0), _post_with(client, monkeypatch, tmp_path, 2)
    assert none.status_code == 409 and "no image source receives pictures" in none.json()["detail"]
    assert two.status_code == 409 and "up0, up1 both receive pictures" in two.json()["detail"]
    assert not (tmp_path / "up0").exists() and not (tmp_path / "up1").exists()
    monkeypatch.setattr(image_sources, "load_sources", lambda: _sources(tmp_path))
    answer = _post(client, PNG)
    assert answer.status_code == 200, answer.text
    ref = answer.json()["ref"]
    relative = ref.split(":", 1)[1]
    assert ref.startswith("up0:im_a/%s/" % datetime.date.today().isoformat()) and image_sources.RECEIVED_NAME.match(relative)
    assert answer.json()["bytes"] == len(PNG) and answer.json()["media_type"] == "image/png"
    path = tmp_path / "up0" / relative
    assert path.read_bytes() == PNG
    assert image_sources.resolve(ref, _sources(tmp_path)) == ("file", os.path.realpath(path))
    again = _post(client, PNG).json()["ref"]
    assert again != ref, "a second paste is another file"


def _post_with(client, monkeypatch, tmp_path, receivers):
    monkeypatch.setattr(image_sources, "load_sources", lambda: _sources(tmp_path, receivers=receivers))
    return _post(client, PNG)


def test_the_size_limit_is_max_mb_to_the_byte(client, tables, tmp_path, monkeypatch):
    monkeypatch.setattr(image_sources, "load_sources", lambda: _sources(tmp_path))
    limit = image_sources.receive_settings("up0", _sources(tmp_path)["up0"])[0]
    assert _post(client, PNG + b"\x00" * (limit - len(PNG))).status_code == 200
    over = _post(client, PNG + b"\x00" * (limit - len(PNG) + 1))
    assert over.status_code == 413 and "at most 0.01 MB" in over.json()["detail"]
    assert len(list((tmp_path / "up0").rglob("*.png"))) == 1


def test_a_body_whose_length_is_past_the_limit_is_refused_before_it_is_read(client, tables, tmp_path, monkeypatch):
    from starlette.requests import Request

    monkeypatch.setattr(image_sources, "load_sources", lambda: _sources(tmp_path, max_mb=0.01))

    async def _read_nothing(self, *a, **k):
        raise AssertionError("the body was read")
    monkeypatch.setattr(Request, "form", _read_nothing)
    answer = _post(client, PNG + b"\x00" * 200_000)
    assert answer.status_code == 413, answer.text


@pytest.mark.parametrize("suffix", sorted(HEADS))
def test_each_picture_head_is_kept_under_its_suffix(client, tables, tmp_path, monkeypatch, suffix):
    monkeypatch.setattr(image_sources, "load_sources", lambda: _sources(tmp_path))
    answer = _post(client, HEADS[suffix])
    assert answer.status_code == 200 and answer.json()["ref"].endswith("." + suffix), answer.text


@pytest.mark.parametrize("data", [b"hello, not a picture", b"%PDF-1.7\n" + b"\x00" * 40])
def test_a_file_that_is_not_a_picture_is_refused(client, tables, tmp_path, monkeypatch, data):
    monkeypatch.setattr(image_sources, "load_sources", lambda: _sources(tmp_path))
    answer = _post(client, data)
    assert answer.status_code == 415 and "not a png, jpeg, gif, bmp, webp or tiff" in answer.json()["detail"]
    assert not (tmp_path / "up0").exists()


def test_not_an_image_column_and_an_unknown_table(client, tables, tmp_path, monkeypatch):
    monkeypatch.setattr(image_sources, "load_sources", lambda: _sources(tmp_path))
    for column in ("note", "nope"):
        answer = _post(client, PNG, column=column)
        assert answer.status_code == 400 and "is not an image column" in answer.json()["detail"]
    assert _post(client, PNG, table="nope_table").status_code == 404
    assert not (tmp_path / "up0").exists()


# ── sweep ──

def _kept(tmp_path, sources, table="im_a", day=DAY):
    return image_sources.keep(table, PNG, sources, today=day)["ref"]


def _marks(tmp_path):
    return json.loads((tmp_path / "up0" / image_sources.UNREFERENCED_FILE).read_text(encoding="utf-8"))


def _exists(tmp_path, ref):
    return (tmp_path / "up0" / ref.split(":", 1)[1]).exists()


def test_held_unreferenced_counted_from_the_first_day_and_gone_at_keep_days(tables, tmp_path):
    db, sources = tables, _sources(tmp_path, keep_days=3)
    held, loose = _kept(tmp_path, sources), _kept(tmp_path, sources)
    _hold(db, "im_a", "pic", held)
    assert image_sources.sweep(db, DAY, sources)["deleted"] == 0
    assert list(_marks(tmp_path)) == [loose.split(":", 1)[1]] and _marks(tmp_path)[loose.split(":", 1)[1]] == DAY.isoformat()
    assert image_sources.sweep(db, DAY + datetime.timedelta(days=2), sources)["deleted"] == 0 and _exists(tmp_path, loose)
    said = image_sources.sweep(db, DAY + datetime.timedelta(days=3), sources)
    assert (said["deleted"], said["freed_bytes"]) == (1, len(PNG)) and not _exists(tmp_path, loose)
    assert _exists(tmp_path, held) and _marks(tmp_path) == {}


def test_one_held_again_is_taken_off_and_counted_afresh(tables, tmp_path):
    db, sources = tables, _sources(tmp_path, keep_days=3)
    ref = _kept(tmp_path, sources)
    path = tmp_path / "up0" / ref.split(":", 1)[1]
    old = datetime.datetime(2026, 9, 1).timestamp()
    os.utime(path, (old, old))                                  # an old file: a count by its age would take it
    image_sources.sweep(db, DAY, sources)
    _hold(db, "im_a", "pic", ref)
    image_sources.sweep(db, DAY + datetime.timedelta(days=1), sources)
    assert _marks(tmp_path) == {}
    _hold(db, "im_a", "pic", "photos:other.png")
    image_sources.sweep(db, DAY + datetime.timedelta(days=5), sources)
    assert path.exists() and _marks(tmp_path) == {ref.split(":", 1)[1]: (DAY + datetime.timedelta(days=5)).isoformat()}


def test_a_name_it_did_not_make_and_a_link_out_of_the_root_are_not_touched(tables, tmp_path):
    db, sources = tables, _sources(tmp_path, keep_days=1)
    _kept(tmp_path, sources)
    by_hand = tmp_path / "up0" / "a.png"
    by_hand.write_bytes(PNG)
    wrong_suffix = tmp_path / "up0" / "im_a" / DAY.isoformat() / ("0" * 32 + ".txt")
    wrong_suffix.write_bytes(PNG)
    outside = tmp_path / "outside" / DAY.isoformat()
    outside.mkdir(parents=True)
    far = outside / ("f" * 32 + ".png")
    far.write_bytes(PNG)
    day_folder = tmp_path / "outside2"                          # a date folder under the root that leads out of it
    day_folder.mkdir()
    farther = day_folder / ("e" * 32 + ".png")
    farther.write_bytes(PNG)
    for target, link in ((tmp_path / "outside", tmp_path / "up0" / "im_b"),
                         (day_folder, tmp_path / "up0" / "im_a" / "2026-11-06")):
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(str(target), str(link))
    image_sources.sweep(db, DAY, sources)
    said = image_sources.sweep(db, DAY + datetime.timedelta(days=1), sources)
    assert said["listed"] == 1 and said["deleted"] == 1
    assert by_hand.exists() and wrong_suffix.exists() and far.exists() and farther.exists()
    assert set(_marks(tmp_path)) == set()


def test_keep_days_absent_deletes_nothing_and_says_so(tables, tmp_path, caplog):
    db, sources = tables, _sources(tmp_path, keep_days=None)
    ref = _kept(tmp_path, sources)
    with caplog.at_level("INFO"):
        said = image_sources.sweep(db, DAY + datetime.timedelta(days=400), sources)
    assert said["deleted"] == 0 and _exists(tmp_path, ref) and list(_marks(tmp_path)) == [ref.split(":", 1)[1]]
    assert "[Images] keep_days not declared - kept 1 unreferenced received file(s)" in caplog.text


def test_no_receiver_sweeps_nothing(tables, tmp_path, caplog):
    with caplog.at_level("INFO"):
        assert image_sources.sweep(tables, DAY, _sources(tmp_path, receivers=0)) == {}
    assert "[Images]" not in caplog.text


def test_one_held_by_another_tables_image_column_stays(tables, tmp_path):
    db, sources = tables, _sources(tmp_path, keep_days=1)
    ref = _kept(tmp_path, sources)
    _hold(db, "im_b", "shot", ref)
    image_sources.sweep(db, DAY, sources)
    assert image_sources.sweep(db, DAY + datetime.timedelta(days=9), sources)["deleted"] == 0 and _exists(tmp_path, ref)


def test_a_file_made_after_the_listing_is_not_this_passes(tables, tmp_path, monkeypatch):
    db, sources = tables, _sources(tmp_path, keep_days=1)
    _kept(tmp_path, sources)
    image_sources.sweep(db, DAY, sources)
    late = []
    asked = image_sources.referenced

    def _upload_meanwhile(*a, **k):
        late.append(_kept(tmp_path, sources))
        return asked(*a, **k)
    monkeypatch.setattr(image_sources, "referenced", _upload_meanwhile)
    assert image_sources.sweep(db, DAY + datetime.timedelta(days=1), sources)["deleted"] == 1
    assert _exists(tmp_path, late[0]) and late[0].split(":", 1)[1] not in _marks(tmp_path)


def test_a_removed_picture_says_so_and_others_keep_todays_sentence(tmp_path):
    sources = _sources(tmp_path, keep_days=3)
    with pytest.raises(image_sources.ImageRefused) as removed:
        image_sources.resolve("up0:im_a/2026-11-01/%s.png" % ("a" * 32), sources)
    assert removed.value.status == 404 and str(removed.value) == (
        "picture removed - it was unreferenced for 3 days (image_sources.json up0.receive.keep_days)")
    for ref in ("up0:by_hand.png", "photos:im_a/2026-11-01/%s.png" % ("a" * 32)):
        with pytest.raises(image_sources.ImageRefused) as missing:
            image_sources.resolve(ref, sources)
        assert str(missing.value).startswith("no file ")


@pytest.mark.pg
def test_the_held_question_on_postgresql_across_the_batch_edge(pg_session, monkeypatch):
    """Production is PostgreSQL: the same `referenced` (one LIKE read a column, both dialects) at 1,000 and 1,001
    names, one held under another source name."""
    db = pg_session
    for name, config in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, config)
    models.init_dynamic_models(crud.TABLE_CONFIG)
    from database.database import Base
    Base.metadata.create_all(bind=db.get_bind(), tables=[models.DYNAMIC_TABLES[t].__table__ for t in TABLES])
    names = ["im_a/2026-11-05/%032x.png" % n for n in range(1001)]
    _hold(db, "im_a", "pic", "up0:" + names[0], key="r0")
    _hold(db, "im_a", "pic", "up0:" + names[999], key="r999")
    _hold(db, "im_b", "shot", "renamed:" + names[1000], key="r1000")
    _hold(db, "im_b", "shot", "photos:p/1.png", key="r1")
    assert image_sources.referenced(db, names[:1000]) == ({names[0], names[999]}, [])
    assert image_sources.referenced(db, names) == ({names[0], names[999], names[1000]}, [])
    assert image_sources.referenced(db, names[1:999]) == (set(), [])


# ── C's six cells (lead 11-05) ──

def test_a_renamed_receiving_source_or_a_full_path_still_holds_its_picture(tables, tmp_path):
    db, sources = tables, _sources(tmp_path, keep_days=1)
    by_name, by_path = _kept(tmp_path, sources), _kept(tmp_path, sources)
    _hold(db, "im_a", "pic", by_name, key="r1")
    _hold(db, "im_b", "shot", str(tmp_path / "up0" / by_path.split(":", 1)[1]).replace("/", "\\"), key="r2")
    renamed = {"pics": dict(sources["up0"]), "photos": sources["photos"]}
    said = image_sources.sweep(db, DAY + datetime.timedelta(days=9), renamed)
    assert (said["unreferenced"], said["deleted"]) == (0, 0) and _exists(tmp_path, by_name) and _exists(tmp_path, by_path)


def test_an_image_column_this_process_cannot_read_stops_the_deleting(tables, tmp_path, monkeypatch, caplog):
    db, sources = tables, _sources(tmp_path, keep_days=1)
    ref = _kept(tmp_path, sources)
    monkeypatch.setitem(crud.TABLE_CONFIG, "im_ghost", {"business_key": "k", "column_types": {"k": "string", "g": "image"}})
    image_sources.sweep(db, DAY, sources)
    with caplog.at_level("WARNING"):
        said = image_sources.sweep(db, DAY + datetime.timedelta(days=9), sources)
    assert said == {"unread": ["im_ghost.g"]} and _exists(tmp_path, ref)
    assert "image column(s) im_ghost.g could not be read" in caplog.text


def test_with_keep_days_absent_a_missing_received_file_says_what_todays_sentence_says(tmp_path):
    with pytest.raises(image_sources.ImageRefused) as missing:
        image_sources.resolve("up0:im_a/2026-11-01/%s.png" % ("a" * 32), _sources(tmp_path, keep_days=None))
    assert str(missing.value).startswith("no file ") and "removed" not in str(missing.value)


@pytest.mark.parametrize("keep_days", ["7d", 0, -1, 1.5, True])
def test_a_keep_days_it_does_not_take_is_said_and_nothing_deleted(tables, tmp_path, caplog, keep_days):
    db = tables
    ref = _kept(tmp_path, _sources(tmp_path, keep_days=1))
    with caplog.at_level("WARNING"):
        said = image_sources.sweep(db, DAY + datetime.timedelta(days=9), _sources(tmp_path, keep_days=keep_days))
    assert "receive.keep_days is %r - write whole days, 1 or more" % keep_days in said["refused"]
    assert "[Images] not swept - image_sources.json up0.receive.keep_days" in caplog.text and _exists(tmp_path, ref)


def test_a_state_file_of_another_shape_is_counted_afresh(tables, tmp_path, caplog):
    db, sources = tables, _sources(tmp_path, keep_days=1)
    ref = _kept(tmp_path, sources)
    (tmp_path / "up0" / image_sources.UNREFERENCED_FILE).write_text("[]", encoding="utf-8")
    with caplog.at_level("WARNING"):
        said = image_sources.sweep(db, DAY, sources)
    assert said["deleted"] == 0 and _exists(tmp_path, ref) and _marks(tmp_path) == {ref.split(":", 1)[1]: DAY.isoformat()}
    assert "is not a {path: day} object - counting afresh" in caplog.text


@pytest.mark.parametrize("max_mb, said", [(None, "is not declared"), (0, "is 0"), ("10", "is '10'")])
def test_a_max_mb_it_does_not_take_refuses_the_paste_by_name(client, tables, tmp_path, monkeypatch, max_mb, said):
    sources = _sources(tmp_path)
    if max_mb is None:
        del sources["up0"]["receive"]["max_mb"]
    else:
        sources["up0"]["receive"]["max_mb"] = max_mb
    monkeypatch.setattr(image_sources, "load_sources", lambda: sources)
    answer = _post(client, PNG)
    assert answer.status_code == 409 and ("image_sources.json up0.receive.max_mb " + said) in answer.json()["detail"]
    assert not (tmp_path / "up0").exists()


def test_keep_days_zero_refuses_the_paste(client, tables, tmp_path, monkeypatch):
    monkeypatch.setattr(image_sources, "load_sources", lambda: _sources(tmp_path, keep_days=0))
    answer = _post(client, PNG)
    assert answer.status_code == 409 and "receive.keep_days is 0 - write whole days, 1 or more" in answer.json()["detail"]
