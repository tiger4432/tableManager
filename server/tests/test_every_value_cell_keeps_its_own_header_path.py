# -*- coding: utf-8 -*-
"""총괄 eed8b37de — every value cell keeps its own header path, or the table is refused by name.

① `extract_semantic_tuples` answers a dict keyed by the header path, so two value cells on one
   path left only the later one - silently (the lead measured 12 cells -> 8). The table is
   refused, naming the path, how many cells share it, where, and what to mark as a header.
② A column-header group reaches a cell only if it stands over that cell's columns: two 2-wide
   groups A · B over four columns both passed the width test (int(4 * 0.7) = 2), so B headed
   A's cells and 집계A was lost.
③ is not built (stacked tables are split before parsing - guide §3.1-bis); here only its count.
"""
import os
import sys

import pytest

server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (server_dir, os.path.join(server_dir, "parsers")):
    if path not in sys.path:
        sys.path.insert(0, path)

from html_topology_parser import HTMLTableGraphParser  # noqa: E402

#: The lot column is merged over two rows and the wafer column - the one that tells the rows
#: apart - is not a header, so each lot's two rows land on one path per value column.
SHARED = """<table>
<tr><td>LOT</td><td>WAFER</td><td>THK</td><td>RES</td></tr>
<tr><td rowspan=2>L001</td><td>W01</td><td>10.1</td><td>3.2</td></tr>
<tr><td>W02</td><td>10.3</td><td>3.3</td></tr>
<tr><td rowspan=2>L002</td><td>W01</td><td>11.1</td><td>4.2</td></tr>
<tr><td>W02</td><td>11.3</td><td>4.3</td></tr>
</table>"""
TWO_GROUPS = """<table>
<tr><td colspan=2>A</td><td colspan=2>B</td></tr>
<tr><td colspan=2>sumA</td><td colspan=2>sumB</td></tr>
<tr><td>A1</td><td>A2</td><td>B1</td><td>B2</td></tr>
<tr><td>a1</td><td>a2</td><td>b1</td><td>b2</td></tr>
</table>"""
OWNER = """<table>
<tr><td colspan=2>A</td></tr>
<tr><td colspan=2>집계</td></tr>
<tr><td>A1</td><td>A2</td></tr>
<tr><td>집계1</td><td>집계2</td></tr>
</table>"""
STACKED = """<table>
<tr><td>LOT</td><td>WAFER</td><td>THK</td><td>RES</td></tr>
<tr><td>L001</td><td>W01</td><td>10.1</td><td>3.2</td></tr>
<tr><td>L001</td><td>W02</td><td>10.3</td><td>3.3</td></tr>
<tr><td>LOT</td><td>WAFER</td><td>BOW</td><td>WARP</td></tr>
<tr><td>L001</td><td>W01</td><td>21</td><td>40</td></tr>
<tr><td>L001</td><td>W02</td><td>22</td><td>41</td></tr>
</table>"""


def _tuples(html, is_header_fn):
    parser = HTMLTableGraphParser(is_header_fn=is_header_fn)
    nodes, edges = parser.parse_to_graph(html)
    values = [n for n in nodes if not n.is_header and n.value]
    return parser.extract_semantic_tuples(nodes, edges), values


def test_two_value_cells_on_one_header_path_are_refused_by_name():
    with pytest.raises(ValueError) as refused:
        _tuples(SHARED, lambda tag, r, c: r == 0 or c == 0)
    said = str(refused.value)
    assert "('L001', 'WAFER')" in said, said          # the path
    assert "2 value cells" in said, said              # how many share it
    assert "row 1 col 1" in said, said                # where, one example
    assert "6 header path(s)" in said, said           # 2 lots x 3 value columns
    assert "header" in said.split("Next:")[1], said   # what to do


def test_marking_the_row_splitting_column_as_a_header_keeps_every_value():
    got, values = _tuples(SHARED, lambda tag, r, c: r == 0 or c <= 1)
    assert len(got) == len(values) == 8
    assert got[("L001", "W02", "THK")] == "10.3"
    assert got[("L002", "W01", "RES")] == "4.2"


def test_sibling_groups_head_only_their_own_columns():
    got, values = _tuples(TWO_GROUPS, lambda tag, r, c: r in (0, 2))
    assert got == {("A",): "sumA", ("B",): "sumB",
                   ("A", "A1"): "a1", ("A", "A2"): "a2",
                   ("B", "B1"): "b1", ("B", "B2"): "b2"}
    assert len(got) == len(values)


def test_the_owners_shape_reads_as_it_did():
    got, values = _tuples(OWNER, lambda tag, r, c: r in (0, 2))
    assert got == {("A",): "집계", ("A", "A1"): "집계1", ("A", "A2"): "집계2"}
    assert len(got) == len(values)


def test_stacked_tables_keep_one_answer_per_value_cell():
    """③ is not built - the lower table's paths still carry the upper header (guide §3.1-bis
    splits the table first). What this pins is only that nothing is lost."""
    got, values = _tuples(STACKED, lambda tag, r, c: r in (0, 3) or c <= 1)
    assert len(got) == len(values) == 8
