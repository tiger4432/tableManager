# -*- coding: utf-8 -*-
"""Owner 10-23 (lead 4c51fb05e · 8a72d6618 · c4ce6ba0b · 56ce5b347): the summary table of the AI report, for the
company and in Korean. Seed: a wafer known by (wafer, version) - W1 holds two versions, two bonding zones with other
conditions, numbers and info - and a control evaluation E0 (C1).

  two columns    a version is a column; a key of two columns heads in two tiers, the wafer merged over its versions
  info rows      from the info table under the head - a name with no row stands not, rows narrows, a column of
                 several wafers says the one value or «mixed (n)», a pair two rows say is left out
  picture rows   a picture a column, embedded by the one function images() uses; a missing file says why; a column
                 of a condition value «—»; the model is told «n of m columns»
  formats        the first rule that holds colours the cell - a fixed bar, or this evaluation against the others
  item_sep       a.b.c · a.b.d · a.e · f -> a row head of three cells, a shared leading part merged
  sample block   the rows under {{table:yield_by}} lend their class and style; the three rows become one cell
  labels         every fixed word of the file passes the declaration's labels; the template's charset is dropped
  reckon         a character past ASCII is a token of its own
"""
import json
import re

import pytest

from conftest import retire_dynamic_model
from database import crud, models

TABLES = {
    "rk_wafer": {"composite_key_source": ["wafer_id", "version"],
                 "column_types": {"wafer_id": "string", "version": "string", "eval_id": "string",
                                  "measured_at": "string", "bond": "string"}},
    "rk_summary": {"composite_key_source": ["wafer_id", "version", "item"],
                   "column_types": {"wafer_id": "string", "version": "string", "item": "string",
                                    "fail": "number", "total": "number", "rs_state": "string",
                                    "rs_file": "string", "rs_reason": "string"}},
    "rk_info": {"composite_key_source": ["wafer_id", "version", "name", "n"],
                "column_types": {"wafer_id": "string", "version": "string", "name": "string", "n": "string",
                                 "value": "string"}},
    "rk_yield": {"composite_key_source": ["wafer_id", "version"],
                 "column_types": {"wafer_id": "string", "version": "string", "yield": "number"}},
    "rk_map": {"composite_key_source": ["wafer_id", "version", "n"],
               "column_types": {"wafer_id": "string", "version": "string", "n": "string", "path": "string"}},
}
WAFERS = [("W1", "v1", "E1", "2026-10-01T00", "저온"), ("W1", "v2", "E1", "2026-10-01T01", "고온"),
          ("W2", "v1", "E1", "2026-10-02", "저온"), ("W3", "v1", "E1", "2026-10-03", "고온"),
          ("C1", "v1", "E0", "2026-09-20", "저온")]
BIG = "결함.입자.대"
#: wafer, version, item, F, N - W1's two versions differ
SUMMARY = [("W1", "v1", BIG, 2, 100), ("W1", "v2", BIG, 10, 100), ("W2", "v1", BIG, 1, 100), ("W3", "v1", BIG, 0, 100),
           ("C1", "v1", BIG, 2, 100), ("W1", "v1", "결함.입자.소", 1, 100), ("W1", "v1", "결함.긁힘", 1, 100),
           ("W1", "v1", "기타", 1, 100)]
INFO = [("W1", "v1", "자재", "A-lot"), ("W1", "v2", "자재", "B-lot"), ("W2", "v1", "자재", "A-lot"),
        ("W3", "v1", "자재", "A-lot"), ("W1", "v1", "평가자", "김"), ("W2", "v1", "평가자", "이"),
        ("W2", "v1", "평가자", "박")]
#: a wide table, a row a wafer (lead 10-23: the yield table [wafer, leg] · yield) - W3 has none
YIELDS = [("W1", "v1", 52.0), ("W1", "v2", 60.0), ("W2", "v1", 88.0)]
MAPS = [("W1", "v1", "맵/a.png"), ("W1", "v2", "맵/b.png"), ("W2", "v1", "맵/c.png"), ("W3", "v1", "맵/없음.png")]
LABELS = {"report": "리포트", "item": "항목", "left_out": "제외 - 같은 웨이퍼 · 이름 두 행", "not_read": "%s 안 읽음",
          "nothing_written": "%s 글 없음", "no_image": "이미지 없음", "pareto_item": "항목", "pareto_fail": "불량 칩",
          "pareto_cumulative": "누적", "control": "대조", "mixed": "섞임 (%d)"}
SPEC = {
    "wafer": {"table": "rk_wafer", "key": ["wafer_id", "version"], "time": "measured_at", "evaluation": "eval_id",
              "conditions": ["bond"]},
    "summary": {"table": "rk_summary", "wafer": ["wafer_id", "version"], "item": "item", "fail": "fail",
                "total": "total"},
    "info": {"table": "rk_info", "wafer": ["wafer_id", "version"], "item": "name", "value": "value"},
    "picture_rows": [{"label": "합성맵", "table": "rk_map", "wafer": ["wafer_id", "version"], "image": "path"}],
    "rows": [BIG], "digits": 1, "item_sep": ".",
    "control": {"recent": {"days": 60}},
    "formats": {BIG: [{"vs": "control", "times": 2, "fill": "#ffcccc"}, {"when": ">=", "value": 1, "fill": "#ffffcc"}]},
    "labels": LABELS,
    "layout": [{"kind": "text", "slot": "summary"}, {"kind": "table", "fill": "yield_by"}],
    "results": {"state": "rs_state", "file": "rs_file", "reason": "rs_reason"},
}


@pytest.fixture
def report(db_session, tmp_path, monkeypatch):
    import image_sources
    from chain import report_reads

    models.init_dynamic_models(TABLES)
    for name, entry in TABLES.items():
        crud.TABLE_CONFIG[name] = entry
        models.DYNAMIC_TABLES[name].__table__.create(bind=db_session.get_bind())
    m = models.DYNAMIC_TABLES
    for n, (w, v, ev, at, bond) in enumerate(WAFERS):
        db_session.add(m["rk_wafer"](row_id="w%d" % n, wafer_id=w, version=v, eval_id=ev, measured_at=at, bond=bond))
    for n, (w, v, item, fail, total) in enumerate(SUMMARY):
        db_session.add(m["rk_summary"](row_id="s%d" % n, wafer_id=w, version=v, item=item, fail=fail, total=total))
    for n, (w, v, name, value) in enumerate(INFO):
        db_session.add(m["rk_info"](row_id="i%d" % n, wafer_id=w, version=v, name=name, n=str(n), value=value))
    for n, (w, v, share) in enumerate(YIELDS):
        db_session.add(m["rk_yield"](row_id="y%d" % n, wafer_id=w, version=v, **{"yield": share}))
    root = tmp_path / "그림"
    (root / "맵").mkdir(parents=True)
    for n, (w, v, path) in enumerate(MAPS):
        if "없음" not in path:
            (root / path).write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([n]))
        db_session.add(m["rk_map"](row_id="m%d" % n, wafer_id=w, version=v, n="1", path="pics:" + path))
    db_session.commit()
    monkeypatch.setattr(image_sources, "load_sources", lambda path=None: {
        "pics": {"kind": "folder", "root": str(root)}})
    # what the picture is shrunk to says the width - a picture put in by any other way says something else
    monkeypatch.setattr(image_sources, "shrink", lambda answer, px: ("bytes", b"shrunk %d " % px + open(
        answer[1], "rb").read()[-1:], "image/png"))
    try:
        yield report_reads.Report(db_session, json.loads(json.dumps(SPEC)), "E1")
    finally:
        db_session.rollback()
        for name in TABLES:
            models.DYNAMIC_TABLES[name].__table__.drop(bind=db_session.get_bind())
            retire_dynamic_model(name)


def _texts(rows):
    return [(name, [cell.get("text") for cell in cells]) for name, cells in rows]


def test_a_version_is_a_column_and_the_key_heads_in_two_tiers(report):
    from chain import report_html

    table = report.yield_by()["html"]
    assert table["groups"] == [("E1", ["W1/v1", "W1/v2", "W2/v1", "W3/v1"])]
    assert _texts(table["rows"]) == [(BIG, ["2.0% (2/100)", "10.0% (10/100)", "1.0% (1/100)", "0.0% (0/100)"])]
    page = report_html._summary_table(table, SPEC)
    assert ('<th class="rpt-head" colspan="2">W1</th><th class="rpt-head">W2</th><th class="rpt-head">W3</th>'
            in page), "the wafer merged over its versions"
    assert '<th class="rpt-head">v1</th><th class="rpt-head">v2</th><th class="rpt-head">v1</th>' in page
    by = report_html._summary_table(report.yield_by(by="bond")["html"], SPEC)
    assert '<th class="rpt-head">고온</th><th class="rpt-head">저온</th>' in by, "a condition value's column: one tier"


def test_info_rows_stand_under_the_head_from_the_info_table(report, db_session):
    from chain import report_reads

    table = report.yield_by()["html"]
    assert _texts(table["info"]) == [("자재", ["A-lot", "B-lot", "A-lot", "A-lot"]), ("평가자", ["김", "", "", ""])]
    assert table["left_out"] == ["W2/v1 평가자"], "two rows of one wafer and name are left out, named"
    assert "info 자재 | A-lot | B-lot | A-lot | A-lot" in report.yield_by()["context"]
    by = report.yield_by(by="bond")["html"]
    assert _texts(by["info"])[0] == ("자재", ["섞임 (2)", "A-lot"]), "고온 holds B-lot and A-lot; 저온 A-lot alone"
    spec = json.loads(json.dumps(SPEC))
    spec["info"]["rows"] = ["없는정보", "자재"]
    narrowed = report_reads.Report(db_session, spec, "E1").yield_by()["html"]
    assert [name for name, _c in narrowed["info"]] == ["자재"], "a name with no row for these wafers stands not"


def test_info_is_a_list_of_tables_and_a_wide_one_is_its_value_column(report, db_session):
    """Lead 10-23: the yield is the owner's own table [wafer, leg] · yield, made by a chain rule - one info row named
    by its column, under the long info table's rows; one table written alone reads as before."""
    from chain import report_reads, report_shape

    spec = json.loads(json.dumps(SPEC))
    spec["info"] = [SPEC["info"], {"table": "rk_yield", "wafer": ["wafer_id", "version"], "value": "yield"}]
    assert report_shape.refusal(spec) is None
    table = report_reads.Report(db_session, spec, "E1").yield_by()["html"]
    assert _texts(table["info"]) == [("자재", ["A-lot", "B-lot", "A-lot", "A-lot"]), ("평가자", ["김", "", "", ""]),
                                     ("yield", ["52.0", "60.0", "88.0", ""])], "W3 has no yield row: a blank"
    assert table["left_out"] == ["W2/v1 평가자"]
    assert _texts(report.yield_by()["html"]["info"]) == _texts(table["info"])[:2], "one table alone: as it was"


def test_a_picture_row_holds_a_picture_a_column_by_the_one_function(report, db_session):
    from chain import report_reads

    answer = report.yield_by()
    [(label, cells)] = answer["html"]["pictures"]
    assert label == "합성맵"
    assert [cell["src"] for cell in cells[:3]] == [report_reads._picture("pics:" + path, 160)["src"]
                                                   for _w, _v, path in MAPS[:3]], "px 160 by default"
    assert "shrunk 160" in __import__("base64").b64decode(cells[0]["src"].split(",")[1]).decode("latin-1")
    assert "없음.png" in cells[3]["refused"], "a missing file says why in its cell"
    assert "합성맵: 3 of 4 columns" in answer["context"] and "base64" not in answer["context"]
    assert _texts(report.yield_by(by="bond")["html"]["pictures"]) == [("합성맵", ["—", "—"])]
    db_session.add(models.DYNAMIC_TABLES["rk_map"](row_id="m9", wafer_id="W2", version="v1", n="2",
                                                   path="pics:맵/a.png"))
    db_session.commit()
    table = report_reads.Report(db_session, json.loads(json.dumps(SPEC)), "E1").yield_by()["html"]
    assert "W2/v1 합성맵" in table["left_out"] and table["pictures"][0][1][2] == {"text": ""}


def test_the_first_rule_that_holds_colours_the_cell(report):
    from chain import report_html

    alone = report_html._summary_table(report.yield_by()["html"], SPEC)
    cells = re.findall(r'<td class="rpt-cell"(?: style="([^"]*)")?>([^<]*)</td>', alone)
    assert cells == [("background:#ffffcc", "2.0% (2/100)"), ("background:#ffffcc", "10.0% (10/100)"),
                     ("background:#ffffcc", "1.0% (1/100)"), ("", "0.0% (0/100)")], "no control: the fixed bar"
    report.compare(evaluations=["E0"])
    against = report_html._summary_table(report.yield_by()["html"], SPEC)
    cells = re.findall(r'<td class="rpt-cell"(?: style="([^"]*)")?>([^<]*)</td>', against)
    assert [style for style, _t in cells] == ["background:#ffffcc", "background:#ffcccc", "background:#ffffcc", "",
                                              "background:#ffffcc"], \
        "10% is twice the control's 2% - the first rule; the control's own cell holds by the fixed bar"


def test_item_names_split_into_a_row_head_a_shared_part_merged():
    from chain import report_html

    depth, [heads] = report_html.row_heads([["a.b.c", "f", "a.b.d", "a.e"]], ".")
    assert depth == 3
    assert heads == [("a.b.c", [("a", 3, None), ("b", 2, None), ("c", 1, 1)]), ("a.b.d", [("d", 1, 1)]),
                     ("a.e", [("e", 1, 2)]), ("f", [("f", 1, 3)])], "a.b gathered where its first name came"
    assert report_html.row_heads([["a.b", "c"]], "") == (1, [[("a.b", [("a.b", 1, 1)]), ("c", [("c", 1, 1)])]])


TEMPLATE = """<html xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta http-equiv=Content-Type content="text/html; charset=ks_c_5601-1987">
<style><!--.xl70 {font-weight:700;} .xl76 {color:navy;}--></style>
</head>
<body>
<table border=0 cellpadding=0 cellspacing=0 width=384 style='border-collapse:collapse'>
<tr height=20><td class=xl70 colspan=2>{{table:yield_by}}</td><td class=xl71 colspan=4>값</td></tr>
<tr height=20><td class=xl72 colspan=2>{{info}}</td><td class=xl73 colspan=4>A</td></tr>
<tr height=20><td class=xl74 colspan=2>{{picture}}</td><td class=xl75 colspan=4></td></tr>
<tr height=20><td class=xl76 colspan=2 style='border:.5pt solid windowtext'>{{item}}</td><td class=xl77 colspan=4 style='background:#EEEEEE'>1.0%</td></tr>
<tr height=20><td colspan=6>{{summary}}</td></tr>
</table>
</body>
</html>
"""


def test_the_sample_rows_lend_their_formats_and_become_one_cell(report):
    from chain import report_html, report_template

    spec = dict(SPEC, template=TEMPLATE)
    assert report_template.refusal(spec) is None
    page = report_html.page("E1 리포트", "R-1", spec, {"yield_by": report.yield_by()["html"]}, {}, {"summary": "요약"})
    assert "{{" not in page and "xl72 colspan=2>" not in page, "the sample rows are gone"
    assert '<tr height=20><td colspan="6"><div class="scroll"' in page, "one cell spanning the sample's first row"
    assert '<th class="rpt-group xl70" colspan="3"></th><th class="rpt-group xl71" colspan="4">E1</th>' in page, \
        "the head's name cell spans the row head's three cells (결함 · 입자 · 대)"
    assert '<td class="rpt-info xl72" colspan="3">자재</td><td class="rpt-info xl73">A-lot</td>' in page
    assert '<td class="rpt-picture xl74" colspan="3">합성맵</td><td class="rpt-picture xl75"><img src="data:' in page
    assert ('<td class="rpt-item xl76" style="border:.5pt solid windowtext">결함</td>'
            '<td class="rpt-item xl76" style="border:.5pt solid windowtext">입자</td>'
            '<td class="rpt-item xl76" style="border:.5pt solid windowtext">대</td>') in page
    assert '<td class="rpt-cell xl77" style="background:#EEEEEE;background:#ffffcc">2.0% (2/100)</td>' in page, \
        "a format's colour over the sample's"
    assert page.count("charset") == 1 and '<head><meta charset="utf-8">' in page.replace("\n", "")[:200]


@pytest.mark.parametrize("where", ["<td>{{info}}</td><td>{{table:yield_by}}</td>",
                                   "<td>{{table:trend}}</td></tr><tr><td>{{info}}</td>"])
def test_a_sample_mark_outside_the_sample_rows_is_refused(where):
    from chain import report_template

    spec = {"layout": [], "template": "<table><tr>%s</tr></table>" % where}
    assert "{{info}} is a sample row's first cell" in report_template.refusal(spec)


def test_every_fixed_word_of_the_file_passes_the_labels(report):
    from chain import report_html, report_shape

    page = report_html.page("E1 리포트", "R-1", SPEC, {"yield_by": report.yield_by()["html"],
                                                       "pareto": {"rows": [("기타", "1", "100.0%")]}}, {}, {})
    page += report_html.page("E1", "R-1", dict(SPEC, layout=[{"kind": "image"}, {"kind": "table", "fill": "trend"}]),
                              {}, {}, {})
    for name, english in report_shape.LABELS.items():
        stem = english.split("%")[0].strip()
        assert not stem or stem not in page.replace("rpt-item", ""), "%s says %r in English" % (name, english)
    assert "항목" in page and "글 없음" in page and "이미지 없음" in page and "trend 안 읽음" in page
    report.compare(evaluations=["E0"])
    assert "대조 E0" in report.groups and "대조 E0" in report.yield_by()["context"], "one name: groups and context"
    assert report_shape.notes(dict(SPEC, labels={"teim": "x"}))[0].startswith("derive.report.labels.teim is not")


def test_a_character_past_ascii_is_a_token_of_its_own():
    from chain import report_loop

    korean, english = "웨이퍼 입자 불량이 늘었다" * 2, "the particle failures on the wafers rose " * 2
    assert report_loop.reckon(korean) >= report_loop.reckon(english)
    assert report_loop.reckon("가나") == 2 and report_loop.reckon("abcd") == 1


@pytest.mark.parametrize("cell, value, refused", [
    ("formats", {BIG: [{"when": ">=", "value": 1, "fill": "red"}]}, "fill is a colour #rrggbb"),
    ("formats", {BIG: [{"when": "==", "value": 1}]}, '"when": one of'),
    ("formats", {BIG: [{"vs": "lot", "times": 2}]}, '"vs": "control"'),
    ("info", {"table": "rk_info", "wafer": ["wafer_id", "version"], "item": "name"}, "info names wafer and value"),
    ("info", [{"table": "rk_yield", "wafer": ["wafer_id"], "value": "yield"}], "info[0].wafer names 1 column(s)"),
    ("info", [{"table": "rk_yield", "wafer": ["wafer_id", "version"], "value": "good"}],
     "info[0].value 'good' is not a column of 'rk_yield'"),
    ("info", "rk_info", "info is a table and its columns, or a list of them"),
    ("picture_rows", [{"label": "맵", "table": "rk_map", "wafer": ["wafer_id"], "image": "path"}],
     "picture_rows[0].wafer names 1 column(s)"),
    ("picture_rows", [{"table": "rk_map", "wafer": ["wafer_id", "version"], "image": "path"}], "needs label"),
])
def test_what_the_save_refuses(report, cell, value, refused):
    from chain import report_shape

    assert refused in (report_shape.refusal(dict(SPEC, **{cell: value})) or "")


def test_vs_control_needs_the_summary_counts(report):
    from chain import report_shape

    assert report_shape.refusal(SPEC) is None
    rate_only = dict(SPEC, summary={"table": "rk_summary", "wafer": ["wafer_id", "version"], "item": "item",
                                    "rate": "fail", "rate_scale": 100})
    assert "needs fail and total" in report_shape.refusal(rate_only)
