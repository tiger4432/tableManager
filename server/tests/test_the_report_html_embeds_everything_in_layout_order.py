# -*- coding: utf-8 -*-
"""Owner 10-22 «html 에 모두 데이터는 임베딩»: the report's one file - the layout's slots in order, the summary
table's groups over their wafers, every picture inside the file, every text escaped, nothing fetched - kept under
<data root>/reports with the sha256 of the bytes written."""
import hashlib
import re

from chain import report_html, report_shape

TABLE = {"groups": [("E1", ["W1", "W2"]), ("baseline", ["W0"])],
         "heads": [["E1", "W1"], ["E1", "W2"], ["baseline", "W0"]], "own": [True, True, False],
         "rows": [("<script>alert(1)</script>", [{"text": "3.0% (3/100)"}, {"text": "5.0% (10/200)"},
                                                 {"text": "50.0% (50/100)"}])],
         "left_out": ["W9"]}
EMBEDDED = {"particle": [{"wafer": "W1", "src": "data:image/png;base64,AAAA"},
                         {"wafer": "W2", "refused": "image source 'pics' is not declared"}]}
LAYOUT = [{"kind": "text", "slot": "summary"}, {"kind": "table", "fill": "yield_by"}, {"kind": "image", "fill": "images"},
          {"kind": "table", "fill": "pareto"}, {"kind": "text", "slot": "conclusion"}]


def _page():
    return report_html.page("E1 report", "R-1 · eval_summary", {"layout": LAYOUT}, {"yield_by": TABLE}, EMBEDDED,
                             {"summary": "Particle rose on W2.", "conclusion": ""})


def test_the_slots_come_in_layout_order_and_say_what_is_missing():
    """Owner 10-23 «배치 그냥 원래대로 세로 나열해» (the left/right sides of d219fc286 retired): every slot one under
    another in layout's order - and the page as wide as the window, a wide table scrolled inside its box."""
    page = _page()
    order = [page.index(mark) for mark in ("Particle rose on W2.", "3.0% (3/100)", "data:image/png;base64,AAAA",
                                           "pareto was not read.", "Nothing was written for conclusion.")]
    assert order == sorted(order) and 'class="side' not in page
    assert "max-width: 1200px" not in page and 'class="scroll" style="overflow-x:auto;max-width:100%"' in page


def test_the_summary_table_heads_each_group_over_its_wafers():
    page = _page()
    assert '<th class="rpt-group" colspan="2">E1</th><th class="rpt-group" colspan="1">baseline</th>' in page
    assert '<th class="rpt-head">W1</th><th class="rpt-head">W2</th><th class="rpt-head">W0</th>' in page
    assert '<td class="rpt-item">&lt;script&gt;' in page and '<td class="rpt-cell">3.0% (3/100)</td>' in page
    assert "Left out - two rows for one wafer and name: W9" in page


def test_every_text_is_escaped_and_nothing_is_fetched():
    page = _page()
    assert "<script>" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    sources = re.findall(r'(?:src|href)="([^"]*)"', page)
    assert sources == ["data:image/png;base64,AAAA"], sources
    assert "image source &#x27;pics&#x27; is not declared" in page, "a refused picture says why"


def test_every_table_fill_is_one_the_file_can_draw():
    assert tuple(report_html.TABLES) == report_shape.TABLE_FILLS


def test_the_file_is_kept_with_the_hash_of_its_bytes(tmp_path, monkeypatch):
    import paths

    monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))
    path, digest = report_html.keep("R-1/../x", _page())
    assert path == str(tmp_path / "reports" / "R-1_.._x.html"), "the request id cannot leave the folder"
    with open(path, "rb") as handle:
        assert digest == "sha256:" + hashlib.sha256(handle.read()).hexdigest()
