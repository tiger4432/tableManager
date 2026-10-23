# -*- coding: utf-8 -*-
"""Owner 10-23 «회사 양식 엑셀 · 클립보드에 html» (lead 10-23): the HTML Excel puts on the clipboard is the report's
template - each cell whose text is one mark is filled, every other byte stays.

  filled      the mark cells hold the report's tables (rpt-* classes, a scroll box), images, texts, title, meta;
              a mark split by Excel's <font> is still one mark; the mso style block and the cols stay as pasted
  dropped     Excel's housekeeping links and its pictures (local file paths) leave the file - said once at save
  nothing     the file fetches nothing: every src/href left is data:
  refused     a script · an on… attribute · an outside src · a style's outside url · a mark the report does not fill
              · a mark beside other text in its cell · a mark outside a cell · a layout text slot with no mark
"""
import copy
import re

import pytest

from chain import report_html, report_template, rule_shape
from database import crud

#: What Excel 365 puts on the clipboard for a small sheet (written from its shape: unquoted attributes, the mso style
#: comment, the file-list and theme links, a picture as VML imagedata and as an <img> both on a local path, a mark
#: whose half is bold, a merged cell, empty cells).
EXCEL = """<html xmlns:v="urn:schemas-microsoft-com:vml"
xmlns:o="urn:schemas-microsoft-com:office:office"
xmlns:x="urn:schemas-microsoft-com:office:excel"
xmlns="http://www.w3.org/TR/REC-html40">

<head>
<meta http-equiv=Content-Type content="text/html; charset=utf-8">
<meta name=ProgId content=Excel.Sheet>
<meta name=Generator content="Microsoft Excel 15">
<link id=Main-File rel=Main-File
href="file:///C:/Users/me/AppData/Local/Temp/msohtmlclip1/01/clip.htm">
<link rel=File-List
href="file:///C:/Users/me/AppData/Local/Temp/msohtmlclip1/01/clip_filelist.xml">
<link rel=themeData
href="file:///C:/Users/me/AppData/Local/Temp/msohtmlclip1/01/clip_themedata.thmx">
<style>
<!--table
\t{mso-displayed-decimal-separator:"\\.";
\tmso-displayed-thousand-separator:"\\,";}
.xl65
\t{mso-style-parent:style0;
\tfont-weight:700;
\tborder:.5pt solid windowtext;}
.xl66
\t{mso-style-parent:style0;
\tbackground:#DDEBF7;
\tmso-pattern:black none;}
-->
</style>
</head>

<body link="#0563C1" vlink="#954F72">

<table border=0 cellpadding=0 cellspacing=0 width=512 style='border-collapse:
 collapse;width:384pt'>
<!--StartFragment-->
 <col width=64 span=8 style='width:48pt'>
 <tr height=20 style='height:15.0pt'>
  <td height=20 class=xl65 colspan=4 width=256 style='height:15.0pt;width:192pt'>{{title}}</td>
  <td class=xl66 colspan=4 width=256 style='width:192pt'>{{meta}}</td>
 </tr>
 <tr height=20 style='height:15.0pt'>
  <td height=20 class=xl66 colspan=8 style='height:15.0pt'>{{<font class="font6">summary</font>}}</td>
 </tr>
 <tr height=20 style='height:15.0pt'>
  <td height=20 colspan=8 style='height:15.0pt'>{{table:yield_by}}</td>
 </tr>
 <tr height=20 style='height:15.0pt'>
  <td height=20 style='height:15.0pt'></td>
  <td colspan=7>{{&nbsp;table:trend&nbsp;}}</td>
 </tr>
 <tr height=20 style='height:15.0pt'>
  <td height=20 colspan=8 style='height:15.0pt'><!--[if gte vml 1]><v:shape id="Picture_x0020_1"
   o:spid="_x0000_s1025" type="#_x0000_t75" style='position:absolute;width:48pt;height:30pt'><v:imagedata
   src="file:///C:/Users/me/AppData/Local/Temp/msohtmlclip1/01/clip_image001.png" o:title=""/>
  </v:shape><![endif]--><![if !vml]><span style='mso-ignore:vglayout'><img width=64 height=40
  src="file:///C:/Users/me/AppData/Local/Temp/msohtmlclip1/01/clip_image001.png" v:shapes="Picture_x0020_1"></span><![endif]>{{images}}</td>
 </tr>
 <tr height=20 style='height:15.0pt'>
  <td height=20 class=xl66 style='height:15.0pt'>&nbsp;</td>
  <td class=xl66></td>
 </tr>
<!--EndFragment-->
</table>

</body>

</html>
"""
SPEC = {"layout": [{"kind": "text", "slot": "summary"}, {"kind": "table", "fill": "yield_by"}], "template": EXCEL}
TABLE = {"groups": [("E1", ["W1", "W2"])],
         "rows": [("particle", [{"text": "3.0% (3/100)"}, {"text": "5.0% (10/200)"}])]}
EMBEDDED = {"particle": [{"wafer": "W1", "src": "data:image/png;base64,AAAA"}]}


def _page(template=EXCEL):
    return report_html.page("E1 report", "R-1 · eval_summary", dict(SPEC, template=template),
                             {"yield_by": TABLE, "trend": TABLE}, EMBEDDED, {"summary": "Particle rose on W2."})


def test_the_template_stands_and_says_the_pictures_it_drops():
    assert report_template.refusal(SPEC) is None
    assert report_template.note(SPEC) == ("derive.report.template: image(s) dropped: 1 - Excel puts pictures on the "
                                          "clipboard as local file paths")


def test_each_mark_cell_is_filled_and_every_other_byte_stays():
    page = _page()
    assert "{{" not in page
    assert '<td height=20 class=xl66 colspan=8 style=\'height:15.0pt\'><div class="text">Particle rose on W2.</div></td>' \
        in page, "a mark split by <font> is one mark - the whole cell inside is the text"
    assert '<td class=xl66 colspan=4 width=256 style=\'width:192pt\'>R-1 · eval_summary</td>' in page
    assert re.search(r"<td height=20 colspan=8 style='height:15\.0pt'><div class=\"scroll\" style=\"overflow-x:auto;"
                     r"max-width:100%\"><table><thead><tr><th class=\"rpt-group\">", page)
    assert '<td class="rpt-cell">5.0% (10/200)</td>' in page and '<td class="rpt-item">particle</td>' in page
    style = EXCEL[EXCEL.index("<style>"):EXCEL.index("</style>")]
    assert style in page and "<col width=64 span=8 style='width:48pt'>" in page, "the template's own bytes stay"
    assert "<td class=xl66></td>" in page and "&nbsp;</td>" in page, "empty cells stay empty"


def test_the_file_fetches_nothing():
    page = _page()
    assert "file:///" not in page and "clip_filelist" not in page
    assert re.findall(r'(?:src|href)\s*=\s*["\']?([^"\'\s>]+)', page) == ["data:image/png;base64,AAAA"]


@pytest.mark.parametrize("change, said", [
    (("{{meta}}", "{{meta}}<script>alert(1)</script>"), "a <script> runs or fetches outside the file"),
    (("<td height=20 class=xl65", "<td onclick=x() height=20 class=xl65"), "<td onclick=…> runs a script"),
    (("{{title}}</td>", "{{title}}</td><td><img src=\"https://cdn.example/logo.png\"></td>"),
     "<img src=\"https://cdn.example/logo.png\"> is fetched from outside the file"),
    ((".xl65", ".xl65 {background:url(http://x/y.png)}\n.xl67"), "a style's url(http://x/y.png) is fetched"),
    (("{{meta}}", "{{author}}"), "{{author}} is not a mark this report fills"),
    (("{{meta}}", "Made: {{meta}}"), "{{meta}} stands alone in its cell - the cell also says 'Made:'"),
    (("<table border=0", "<p>{{meta}}</p><table border=0"), "{{meta}} is outside a table cell"),
    (("{{<font class=\"font6\">summary</font>}}", ""), "has no {{summary}} - the layout's text slot summary"),
])
def test_what_would_fetch_run_or_go_nowhere_is_refused_by_name(change, said):
    spec = dict(SPEC, template=EXCEL.replace(*change, 1))
    assert said in (report_template.refusal(spec) or ""), report_template.refusal(spec)


def test_the_save_names_the_dropped_pictures_and_refuses_by_the_template(monkeypatch):
    for name in ("w", "s"):
        monkeypatch.setitem(crud.TABLE_CONFIG, name, {"column_types": {"k": "string", "i": "string", "f": "number",
                                                                       "st": "string", "fl": "string", "why": "string"}})
    report = {"wafer": {"table": "w", "key": "k"}, "summary": {"table": "s", "wafer": "k", "item": "i", "rate": "f",
                                                                "rate_scale": 1},
              "results": {"file": "fl"}}
    report.update(copy.deepcopy(SPEC))
    declaration = {"name": "rep", "on": {"table": "w"}, "into": {"table": "w"},
                   "derive": {"kind": "report", "report": report}}
    rules, refusal, notes = rule_shape.expand_declaration(declaration)
    assert refusal is None and len(rules) == 1
    assert any("image(s) dropped: 1" in note for note in notes), notes
    declaration["derive"]["report"]["template"] = EXCEL.replace("{{meta}}", "{{author}}")
    rules, refusal, _notes = rule_shape.expand_declaration(declaration)
    assert rules == [] and "{{author}} is not a mark this report fills" in refusal
