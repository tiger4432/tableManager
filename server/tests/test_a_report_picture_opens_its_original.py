# -*- coding: utf-8 -*-
"""Owner 10-29 «리포트에서 이미지 보고서에 뜨는건 작아도 크게 보기 같은거 · 이미지 경로로 라우트» · «보고서에 큰 원본은
좀 아니고» (lead ㄱ, by ref): the page keeps its small embedded pictures; each one links to GET
/reports/<file>/image/<n>, which opens the n-th ref of the list the report wrote beside itself - only that list's.

  the route asked                             answers
  a number on the list                        200, the original's bytes (not the embedded thumbnail)
  a number off the list (len, -1)             404 «has N picture(s) - no picture n»
  the list tampered: not JSON / not refs      500, the sentence says which
  the list tampered: a ref no source holds    resolve's refusal - a full path to a non-image or an undeclared source 404,
                                              out of a source's root 400
  the original gone since                     resolve's 404
  no list (a report from before, or none)     404 «links no picture»; the page itself opens as before, with no link
  a name that leaves the folder               404 «no report»

  by the signed link (owner 10-29 ㄱ) - /shared/report/<file>/image/<n>?k=, the same function after the page's key check
  the report's key                            200, the original
  a wrong key, none, another report's key     403 - the key never expires: there is no «expired»
  the report's key, a number off the list     404, the same sentence
  the page's links                            carry the page's own ?k= (a script); a page with no link has no script

  server_settings.json's public_url (lead 10-29 ①) - the file a mail carried opens its pictures too
  written (a «/» at its end or not, http or https)   the file links <public_url>/reports/<file>/image/<n>, the
                                                      relative link beside it (data-rel) for the server's own pages
  blank or not written                               relative, as before, nothing said
  not an http(s) address                             relative, one line says so - once, not per report
  (what the script makes of each link on each page: in the browser - the round's report)
"""
import io
import json
import os

import pytest

from chain import report_html, report_reads

PX = 64


def _png(size, colour):
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (size, size), colour).save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
def box(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import image_sources
    import main
    import paths

    monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path / "data"))
    pics = tmp_path / "pics"
    pics.mkdir()
    originals = {name: _png(400, colour) for name, colour in (("a.png", "red"), ("b.png", "blue"), ("c.png", "green"))}
    for name, data in originals.items():
        (pics / name).write_bytes(data)
    (tmp_path / "secret.txt").write_text("not an image", encoding="utf-8")
    sources = tmp_path / "image_sources.json"
    sources.write_text(json.dumps({"pics": {"kind": "folder", "root": str(pics)}}), encoding="utf-8")
    monkeypatch.setattr(image_sources, "CONFIG_PATH", str(sources))
    app = FastAPI()
    app.add_api_route("/reports/{name}", main.get_report, methods=["GET"])
    app.add_api_route("/reports/{name}/image/{n}", main.get_report_image, methods=["GET"])
    app.add_api_route("/shared/report/{name}", main.get_shared_report, methods=["GET"])
    app.add_api_route("/shared/report/{name}/image/{n}", main.get_shared_report_image, methods=["GET"])
    return {"client": TestClient(app), "originals": originals, "pics": pics, "tmp": tmp_path, "key": main._report_link_key}


def _written(name="W1"):
    """A report page as the loop writes one (`report_loop`): pictures read by `_picture`, numbered, the list kept."""
    row = dict(report_reads._picture("pics:a.png", PX), text="")
    table = {"groups": [("E1", ["W1"])], "heads": [["E1", "W1"]], "own": [True], "rows": [],
             "pictures": [("wafer map", [row])]}
    layers = [dict(report_reads._picture("pics:b.png", PX), layer="L1"),
              dict(report_reads._picture("pics:c.png", PX), layer="L2")]
    embedded = {"void": [{"wafer": "W1", "layers": layers, **layers[0]},
                         dict(report_reads._picture("pics:a.png", PX), wafer="W2"),
                         {"wafer": "W3", "refused": "no file"}]}
    file = report_html.file_name(name)
    refs = report_html.link_pictures(file, {"yield_by": table}, embedded)
    page = report_html.page("W1 report", "R", {"layout": [{"kind": "table", "fill": "yield_by"}, {"kind": "image"}]},
                            {"yield_by": table}, embedded, {})
    path, _sha = report_html.keep(name, page, refs)
    return path, page, refs


def test_each_picture_links_to_its_original_and_the_list_is_kept_beside_the_page(box):
    path, page, refs = _written()
    assert refs == ["pics:a.png", "pics:b.png", "pics:c.png", "pics:a.png"], "picture row, both layers, the gallery"
    assert [json.load(open(path + report_html.IMAGES_SUFFIX, encoding="utf-8"))] == [refs]
    links = [page.count('href="W1.html/image/%d" target="_blank"' % n) for n in range(len(refs))]
    assert links == [1, 1, 1, 1] and page.count('class="%s"' % report_html.ORIGINAL) == len(refs)
    assert page.count("<img ") == len(refs) and "data:image/png;base64," in page, "the pictures stay embedded"
    assert "W3" in page and "no file" in page, "a refused picture: its words, no link"


def test_a_number_on_the_list_opens_the_original_not_the_thumbnail(box):
    _written()
    got = box["client"].get("/reports/W1.html/image/2")
    assert got.status_code == 200 and got.content == box["originals"]["c.png"]
    import base64

    from PIL import Image

    thumb = base64.b64decode(report_reads._picture("pics:c.png", PX)["src"].split(",", 1)[1])
    assert [Image.open(io.BytesIO(data)).size for data in (got.content, thumb)] == [(400, 400), (PX, PX)]


def test_a_link_in_the_page_followed_from_the_page_s_address_opens_its_original(box):
    _path, page, refs = _written()
    href = page.split('href="', 1)[1].split('"', 1)[0]
    got = box["client"].get("/reports/" + href)                     # the page is at /reports/W1.html
    assert got.status_code == 200 and got.content == box["originals"][refs[0].split(":", 1)[1]]


@pytest.mark.parametrize("n", [4, 99, -1])
def test_a_number_off_the_list_is_refused_with_how_many_there_are(box, n):
    _written()
    got = box["client"].get("/reports/W1.html/image/%d" % n)
    assert got.status_code == 404 and got.json()["detail"] == "report 'W1.html' has 4 picture(s) - no picture %d" % n


@pytest.mark.parametrize("body, said", [
    ("{not json", "report 'W1.html''s picture list does not read: "),
    (json.dumps([1, 2]), "report 'W1.html''s picture list is not a list of image refs"),
    (json.dumps({"0": "pics:a.png"}), "report 'W1.html''s picture list is not a list of image refs"),
])
def test_a_list_that_does_not_read_as_refs_is_refused_by_what_it_is(box, body, said):
    path, _page, _refs = _written()
    with open(path + report_html.IMAGES_SUFFIX, "w", encoding="utf-8") as handle:
        handle.write(body)
    got = box["client"].get("/reports/W1.html/image/0")
    assert got.status_code == 500 and got.json()["detail"].startswith(said)


def test_a_ref_put_on_the_list_by_hand_still_passes_the_image_sources_judgement(box):
    path, _page, _refs = _written()
    secret = str(box["tmp"] / "secret.txt")
    with open(path + report_html.IMAGES_SUFFIX, "w", encoding="utf-8") as handle:
        json.dump([secret, "nowhere:a.png", "pics:../secret.txt"], handle)
    said = [box["client"].get("/reports/W1.html/image/%d" % n) for n in range(3)]
    assert [s.status_code for s in said] == [404, 404, 400], [s.text for s in said]
    assert "is under no folder source" in said[0].json()["detail"]
    assert "image source 'nowhere' is not declared" in said[1].json()["detail"]
    assert said[2].json()["detail"] == "'../secret.txt' is outside the root of image source 'pics'"
    assert all(b"not an image" not in s.content for s in said)


def test_an_original_gone_since_the_report_is_said(box):
    _written()
    os.remove(box["pics"] / "c.png")
    got = box["client"].get("/reports/W1.html/image/2")
    assert got.status_code == 404 and "c.png" in got.json()["detail"]


def test_a_report_without_a_list_opens_as_before_and_links_nothing(box):
    path, _page, _refs = _written()
    old = report_html.page("W1 report", "R", {"layout": [{"kind": "image"}]}, {},
                           {"void": [{"wafer": "W1", "src": "data:image/png;base64,AAAA"}]}, {})
    os.remove(path + report_html.IMAGES_SUFFIX)
    with open(path, "w", encoding="utf-8") as handle:                # a report written before 10-29
        handle.write(old)
    page = box["client"].get("/reports/W1.html")
    assert page.status_code == 200 and "data:image/png;base64,AAAA" in page.text and "/image/" not in page.text
    got = box["client"].get("/reports/W1.html/image/0")
    assert got.status_code == 404 and got.json()["detail"] == (
        "report 'W1.html' links no picture - it has none, or it was written before pictures linked to their "
        "originals (write it again)")


def test_written_again_with_no_picture_the_old_list_goes(box):
    path, _page, _refs = _written()
    report_html.keep("W1", report_html.page("W1 report", "R", {"layout": [{"kind": "image"}]}, {}, {}, {}), [])
    assert not os.path.exists(path + report_html.IMAGES_SUFFIX)
    assert box["client"].get("/reports/W1.html/image/0").status_code == 404


@pytest.mark.parametrize("name", ["..%2Fx.html", "W1.html.images.json", "nope.html"])
def test_a_name_that_is_no_report_is_refused(box, name):
    _written()
    got = box["client"].get("/reports/%s/image/0" % name)
    assert got.status_code == 404


def test_by_the_report_s_signed_link_a_picture_opens_its_original(box):
    _written()
    key = box["key"]("W1.html")
    assert box["client"].get("/shared/report/W1.html?k=%s" % key).status_code == 200, "CANARY: the page opens by it"
    got = box["client"].get("/shared/report/W1.html/image/2?k=%s" % key)
    assert got.status_code == 200 and got.content == box["originals"]["c.png"]


@pytest.mark.parametrize("k", ["", "0" * 32, "W2"])
def test_a_wrong_key_none_or_another_report_s_opens_no_picture(box, k):
    _written()
    k = box["key"]("W2.html") if k == "W2" else k
    got = box["client"].get("/shared/report/W1.html/image/0?k=%s" % k)
    assert got.status_code == 403 and got.json()["detail"] == \
        "this link is not a report's signed link - copy it from GET /reports"


def test_by_the_signed_link_a_number_off_the_list_is_refused_as_it_is_signed_in(box):
    _written()
    got = box["client"].get("/shared/report/W1.html/image/4?k=%s" % box["key"]("W1.html"))
    assert got.status_code == 404 and got.json()["detail"] == "report 'W1.html' has 4 picture(s) - no picture 4"


def test_the_page_s_links_carry_its_own_key_only_when_it_has_links(box):
    _path, page, _refs = _written()
    assert page.count(report_html.LINK_SCRIPT) == 1 and "k=" not in page.replace(report_html.LINK_SCRIPT, ""), \
        "the key is the address's, not the file's"
    bare = report_html.page("W1 report", "R", {"layout": [{"kind": "image"}]}, {},
                            {"void": [{"wafer": "W1", "src": "data:image/png;base64,AAAA"}]}, {})
    assert report_html.LINK_SCRIPT not in bare


@pytest.fixture
def settings(box, monkeypatch):
    """server_settings.json in the scratch root -> write(cells or None for no file); read again as a change is."""
    from database import config_watcher
    from runtime import request_timing

    path = box["tmp"] / "server_settings.json"
    monkeypatch.setattr(request_timing, "SETTINGS_PATH", str(path))

    def write(cells):
        if cells is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(json.dumps(cells), encoding="utf-8")
        config_watcher.forget_held()
    yield write
    config_watcher.forget_held()


def _links(page):
    return [(a.split('href="', 1)[1].split('"', 1)[0], a.split('data-rel="', 1)[1].split('"', 1)[0]
             if 'data-rel="' in a else None) for a in page.split('<a class="%s" ' % report_html.ORIGINAL)[1:]]


@pytest.mark.parametrize("written, base", [
    ("https://assy.example.com", "https://assy.example.com"),
    ("https://assy.example.com/", "https://assy.example.com"),
    (" http://assy.example.com/ ", "http://assy.example.com"),
    ("https://gate.example.com/assy/", "https://gate.example.com/assy"),
])
def test_with_public_url_the_file_links_its_pictures_there(box, settings, written, base):
    settings({"slow_request_ms": 500, "public_url": written})
    _path, page, refs = _written()
    assert _links(page) == [("%s/reports/W1.html/image/%d" % (base, n), "W1.html/image/%d" % n)
                            for n in range(len(refs))]
    assert page.count(report_html.LINK_SCRIPT) == 1 and "k=" not in page.replace(report_html.LINK_SCRIPT, "")
    href = _links(page)[2][0]
    got = box["client"].get(href[len(base):])                      # the address's path is the route's
    assert got.status_code == 200 and got.content == box["originals"]["c.png"]
    from runtime import request_timing

    assert request_timing.slow_request_ms() == 500, "the same file's other cell reads as before"


@pytest.mark.parametrize("cells", [None, {}, {"public_url": ""}, {"public_url": "   "}, {"public_url": None}])
def test_blank_or_not_written_links_relative_as_before_and_says_nothing(box, settings, caplog, cells):
    settings(cells)
    _path, page, refs = _written()
    assert _links(page) == [("W1.html/image/%d" % n, None) for n in range(len(refs))]
    assert "[Report]" not in caplog.text


@pytest.mark.parametrize("written", ["assy.example.com", "ftp://assy.example.com", "https://", "https://h/?a=1",
                                     "https://h/#x", 8080])
def test_not_an_address_is_said_once_and_links_relative(box, settings, caplog, written):
    settings({"public_url": written})
    for _ in range(2):
        _path, page, refs = _written()
        assert _links(page) == [("W1.html/image/%d" % n, None) for n in range(len(refs))]
    said = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[Report]")]
    assert said == ["[Report] server_settings.json public_url is not an http(s) address (%r) - report files link "
                    "their pictures relative to themselves" % (written,)], said
