"""[Header predicate] Regression suite against the REAL bonding-map header shapes.

The archived smart-paste files live under server/ingestion_workspace/ (gitignored user
territory, read-only), so the fixtures below REBUILD their exact geometry instead of
reading them: title = one cell colspan=W rowspan=2; then a 4-row band of GROUP
(rowspan 4, colspan 2) -> KEY (rowspan 2, colspan 2) -> VALUE (rowspan 2, colspan 2);
then the X-axis tick row; then the grid. Verified cell-for-cell against
server/ingestion_workspace/bonding_map/archives/*.html - 19 files, 4 header shapes.

What these pin: a cell is a header because of WHERE it is - strictly above the X-axis
tick row - and never because of what its text looks like. The predicate that shipped
before answered "is this a header?" with "does float() reject it?", which broke in
both directions on the real corpus:

  - `BDIE / LOT / 12312` lost the numeric lot from the header set, the LEFT-ancestor
    chain shifted one cell right, and the map key silently became the literal "CDIE"
    while CDIE_LOT and CDIE_WF vanished. bonding_map declares map_key_columns=["base"]
    and `base` IS BDIE_LOT, so the corrupted value is the map key itself.
  - a BIN letter inside the grid was promoted to a header and leaked back out as a
    phantom meta key ("F_AAA").

A lot id, a slot number and a wafer id are all legitimately numeric, and the
2026-08-04 ruling that `slot` is always int puts more of them in headers.
"""
import pytest

from parsers.html_topology_parser import HTMLMatrixTableParser

BLANK = "　"  # Excel's clipboard writes an ideographic space into empty cells


def _bonding_map_html(title, groups, grid_rows=11, bins=None):
    """Rebuild the real Excel-clipboard bonding-map shape.

    groups: [(group_label, lot_value, wf_value), ...] - N groups produce 6*N columns
    bins:   {(x, y): text} - grid cells; everything else is Excel's blank
    """
    bins = bins or {}
    cols = 6 * len(groups)
    grid_w = cols - 1
    out = ['<table border="0" cellpadding="0" cellspacing="0"><tbody>']
    out.append('<tr><td colspan="%d" rowspan="2" class="xl65">%s</td></tr>' % (cols, title))
    out.append("<tr></tr>")

    band_a = []
    for label, lot, _wf in groups:
        band_a.append('<td colspan="2" rowspan="4" class="xl65">%s</td>' % label)
        band_a.append('<td colspan="2" rowspan="2" class="xl65">LOT</td>')
        band_a.append('<td colspan="2" rowspan="2" class="xl65">%s</td>' % lot)
    out.append("<tr>" + "".join(band_a) + "</tr>")
    out.append("<tr></tr>")

    band_b = []
    for _label, _lot, wf in groups:
        band_b.append('<td colspan="2" rowspan="2" class="xl65">WF</td>')
        band_b.append('<td colspan="2" rowspan="2" class="xl65">%s</td>' % wf)
    out.append("<tr>" + "".join(band_b) + "</tr>")
    out.append("<tr></tr>")

    ticks = ['<td class="xl65">%s</td>' % BLANK]
    ticks += ['<td class="xl65">%d</td>' % x for x in range(1, grid_w + 1)]
    out.append("<tr>" + "".join(ticks) + "</tr>")

    for y in range(1, grid_rows + 1):
        cells = ['<td class="xl65">%d</td>' % y]
        for x in range(1, grid_w + 1):
            cells.append('<td class="xl65">%s</td>' % bins.get((x, y), BLANK))
        out.append("<tr>" + "".join(cells) + "</tr>")

    out.append("</tbody></table>")
    return "\n".join(out)


def _meta_of(records):
    """The header block as it is stamped onto every cell record."""
    assert records, "parser returned no records - the grid itself was lost"
    meta = {k: v for k, v in records[0].items() if k not in ("X", "Y", "VALUE")}
    for r in records[1:]:
        assert {k: v for k, v in r.items() if k not in ("X", "Y", "VALUE")} == meta
    return meta


# (name, title, groups, expected header block) - the four shapes observed in the
# archive. File counts as of 2026-08-04: V1 x 15, V2 x 2, V3 x 1, V4 x 1.
REAL_HEADER_VARIANTS = [
    # V1 - two groups, alphabetic lot. The common shape.
    ("v1_two_groups", "AAA",
     [("BDIE", "A", "B"), ("CDIE", "C", "D")],
     {"TITLE": "AAA", "BDIE_LOT": "A", "BDIE_WF": "B",
      "CDIE_LOT": "C", "CDIE_WF": "D"}),
    # V2 - three groups. AQ_* appears and disappears between files, so the header
    # shape is variable and a fixed column list would drop the next variant.
    ("v2_three_groups", "asdf",
     [("BDIE", "HFZ123.13", "B"), ("CDIE", "C", "D"), ("AQ", "C", "D")],
     {"TITLE": "asdf", "BDIE_LOT": "HFZ123.13", "BDIE_WF": "B",
      "CDIE_LOT": "C", "CDIE_WF": "D", "AQ_LOT": "C", "AQ_WF": "D"}),
    # V3 - three groups where the operator typed CDIE twice. The composite keys
    # genuinely collide and the last one wins; that is the file's own doing, not the
    # parser's, and it must stay a 5-key result rather than becoming 7.
    ("v3_repeated_group_label", "AAA",
     [("BDIE", "HFZ123.12", "B"), ("CDIE", "C", "D"), ("CDIE", "C", "D")],
     {"TITLE": "AAA", "BDIE_LOT": "HFZ123.12", "BDIE_WF": "B",
      "CDIE_LOT": "C", "CDIE_WF": "D"}),
    # V4 - THE DEFECT. A purely numeric lot id. Pre-fix this produced
    # {'TITLE': 'AAA', 'BDIE_WF': 'B', 'BDIE_LOT': 'CDIE'} - wrong map key, and
    # CDIE_LOT / CDIE_WF gone entirely.
    ("v4_numeric_lot_id", "AAA",
     [("BDIE", "12312", "B"), ("CDIE", "C", "D")],
     {"TITLE": "AAA", "BDIE_LOT": "12312", "BDIE_WF": "B",
      "CDIE_LOT": "C", "CDIE_WF": "D"}),
]

_VARIANTS_BY_NAME = {v[0]: v for v in REAL_HEADER_VARIANTS}


@pytest.mark.parametrize("name,title,groups,expected", REAL_HEADER_VARIANTS,
                         ids=[v[0] for v in REAL_HEADER_VARIANTS])
def test_real_header_variants_extract_the_whole_header_block(name, title, groups, expected):
    html = _bonding_map_html(title, groups)
    records = HTMLMatrixTableParser().parse_matrix_to_records(html)

    grid_w = 6 * len(groups) - 1
    assert len(records) == grid_w * 11
    assert _meta_of(records) == expected


def test_v4_fixture_actually_activates_the_defect_axis():
    """Guard the guard: V4 only proves anything if its lot id is float-parseable.

    Without this, someone 'fixing' the fixture to a friendlier value would leave a
    green test that exercises nothing. V1's lot must NOT be float-parseable, so the
    pair brackets the old predicate's decision boundary.
    """
    v4_lot = _VARIANTS_BY_NAME["v4_numeric_lot_id"][2][0][1]
    v1_lot = _VARIANTS_BY_NAME["v1_two_groups"][2][0][1]
    float(v4_lot)  # raises if the numeric lot stopped being numeric
    with pytest.raises(ValueError):
        float(v1_lot)


def test_every_header_value_may_be_numeric():
    """Group label, key label and value all numeric at once.

    Nothing in this header is distinguishable from a coordinate tick by its text, so
    only a positional answer to "is this a header?" survives it.
    """
    html = _bonding_map_html("2026", [("11", "12312", "13"), ("21", "22", "23")])
    records = HTMLMatrixTableParser().parse_matrix_to_records(html)

    assert len(records) == 11 * 11
    assert _meta_of(records) == {
        "TITLE": "2026",
        "11_LOT": "12312", "11_WF": "13",
        "21_LOT": "22", "21_WF": "23",
    }


def test_numeric_title_does_not_collapse_the_header_block():
    """A title that parses as an int must not be mistaken for a Y-axis tick.

    The title cell starts at column 0, so a purely numeric title would otherwise be
    read as the topmost Y tick, drag the X-axis row above the header band, and take
    the entire grid down with it.
    """
    html = _bonding_map_html("2026", [("BDIE", "A", "B"), ("CDIE", "C", "D")])
    records = HTMLMatrixTableParser().parse_matrix_to_records(html)

    assert len(records) == 11 * 11
    meta = _meta_of(records)
    assert meta["TITLE"] == "2026"
    assert meta["BDIE_LOT"] == "A"


def test_a_numeric_header_row_is_not_mistaken_for_the_ruler():
    """The hardest case for a positional predicate: a header row that LOOKS like a ruler.

    One group with a numeric key AND a numeric value gives the band row the exact
    arity and text of a short ruler row - a non-numeric cell at column 0 followed by
    integers. Nothing lexical separates them.

    What does: a ruler is built from UNMERGED 1x1 cells, one cell per coordinate,
    while Excel's smart paste writes every header cell with colspan=2. Measured across
    all 19 archived files - every corner and every tick is 1x1, every header cell is
    merged.
    """
    html = "\n".join([
        '<table><tbody>',
        '<tr><td colspan="6" rowspan="2" class="xl65">AAA</td></tr>',
        '<tr></tr>',
        '<tr>'
        '<td colspan="2" rowspan="2" class="xl65">BDIE</td>'
        '<td colspan="2" rowspan="2" class="xl65">5</td>'
        '<td colspan="2" rowspan="2" class="xl65">12312</td>'
        '</tr>',
        '<tr></tr>',
        '<tr>' + '<td class="xl65">%s</td>' % BLANK
        + "".join('<td class="xl65">%d</td>' % x for x in range(1, 6)) + '</tr>',
    ] + [
        '<tr><td class="xl65">%d</td>' % y
        + "".join('<td class="xl65">%s</td>' % BLANK for _ in range(5)) + '</tr>'
        for y in range(1, 12)
    ] + ['</tbody></table>'])

    records = HTMLMatrixTableParser().parse_matrix_to_records(html)

    # The ruler is the row of 1..5, not the BDIE / 5 / 12312 row.
    assert len(records) == 5 * 11
    assert sorted({r["X"] for r in records}) == [1, 2, 3, 4, 5]
    assert _meta_of(records) == {"TITLE": "AAA", "BDIE_5": "12312"}


def test_grid_bins_never_leak_into_the_header_block():
    """Alphabetic BIN values are data. They must not become meta keys.

    On the real 18-column files this leaked as a phantom 'F_AAA' key built from grid
    letters. Adjacent alphabetic bins on one row are what let the LEFT-ancestor chain
    reach length 2 and qualify as a GROUP/KEY pair.
    """
    bins = {(2, 2): "F", (3, 2): "AAA", (4, 2): "A",
            (5, 3): "F", (6, 3): "AAA", (7, 3): "A"}
    html = _bonding_map_html("AAA", [("BDIE", "A", "B"), ("CDIE", "C", "D")], bins=bins)
    records = HTMLMatrixTableParser().parse_matrix_to_records(html)

    assert _meta_of(records) == {"TITLE": "AAA", "BDIE_LOT": "A", "BDIE_WF": "B",
                                 "CDIE_LOT": "C", "CDIE_WF": "D"}
    # and the bins still landed as VALUEs where they belong
    by_xy = {(r["X"], r["Y"]): r["VALUE"] for r in records}
    assert by_xy[(3, 2)] == "AAA"
    assert by_xy[(4, 2)] == "A"


def test_numeric_bins_are_still_values_not_headers():
    """The inverse of the leak: numeric bins stay VALUEs and add no meta keys."""
    bins = {(2, 2): "16", (3, 2): "12", (4, 4): "16"}
    html = _bonding_map_html("AAA", [("BDIE", "A", "B"), ("CDIE", "C", "D")], bins=bins)
    records = HTMLMatrixTableParser().parse_matrix_to_records(html)

    assert set(_meta_of(records)) == {"TITLE", "BDIE_LOT", "BDIE_WF",
                                      "CDIE_LOT", "CDIE_WF"}
    by_xy = {(r["X"], r["Y"]): r["VALUE"] for r in records}
    assert by_xy[(2, 2)] == "16"
    assert by_xy[(4, 4)] == "16"
    assert by_xy[(5, 5)] == ""


# ---------------------------------------------------------------------------
# [Grid origin] Junk above the grid - the OTHER end of the document.
#
# The header predicate above is positional, which means it is only as good as the
# position it is measured from. That origin is derived TWICE, and the two derivations
# have blind spots at opposite ends:
#
#   top-anchored (row shape, scanning down) is fooled by anything ruler-shaped ABOVE
#     the real ruler - and the top of a spreadsheet is exactly where operator junk
#     lives (a SLOT row, a DATE stamp, a two-entry legend);
#   bottom-anchored (the Y ruler's topmost label, minus one - the derivation that
#     shipped before 2026-08-04) is fooled by an integer in column 0 above the grid.
#
# None of these shapes occurs in today's corpus - one producer, one geometry. They are
# prospective, and that is the point: this parser exists to eat Excel pastes whose
# template shapes vary. On disagreement the parse is REFUSED, because a wrong grid
# origin is not a degraded parse - X and Y are part of the business key, so a
# plausible-looking wrong origin files every cell under coordinates that do not exist.
# ---------------------------------------------------------------------------

def _bonding_map_with_junk_row(junk_cells):
    """The real two-group geometry with an extra 1x1 row directly above the ruler.

    Alphabetic lot, so the V4 defect is out of play and every delta is attributable to
    the origin derivation alone.
    """
    html = _bonding_map_html("AAA", [("BDIE", "A", "B"), ("CDIE", "C", "D")])
    lines = html.split("\n")
    ruler_at = next(i for i, ln in enumerate(lines) if '>1</td><td class="xl65">2<' in ln)
    junk = "<tr>" + "".join('<td class="xl65">%s</td>' % c for c in junk_cells) + "</tr>"
    return "\n".join(lines[:ruler_at] + [junk] + lines[ruler_at:])


# (name, junk row cells, expect_refusal, expected top anchor, expected bottom anchor).
# The junk row is inserted at index 6, pushing the real ruler to 7. The last two
# columns are what makes each shape discriminating - a shape where both anchors agree
# on the same wrong row would prove nothing.
JUNK_SHAPES = [
    # M1 - the worst shape. Ruler-shaped and full width, so it yielded the RIGHT record
    # count, the RIGHT values and a SILENTLY WRONG X (2,3,6,7,10,...). Fools the TOP.
    ("m1_slot_row", ["SLOT", 2, 3, 6, 7, 10, 11, 14, 15, 18, 19, 22], True, 6, 7),
    # M2 - a ragged date stamp. Fooled the top anchor into 33 records instead of 121.
    ("m2_ragged_date", ["DATE", 2026, 6, 20], True, 6, 7),
    # M2-A - a two-entry legend with a blank corner. Top anchor gave 22 records.
    ("m2a_blank_corner_legend", [BLANK, 1, 2], True, 6, 7),
    # M3 - the same date stamp padded to full width. The blanks disqualify it as a
    # ruler, so BOTH anchors agree and the file must still parse - but its 1x1 cells
    # sat in the header band and produced the phantom key DATE_2026: "6".
    ("m3_padded_date", ["DATE", 2026, 6, 20] + [BLANK] * 8, False, 7, 7),
    # M4 - the mirror of M1, and the reason the top anchor has to stay. A stray 1x1
    # INTEGER in column 0 above the grid (a legend row, a count) is invisible to the
    # merged-cell restriction and drags the BOTTOM anchor up into the header band -
    # exactly the blind spot the pre-2026-08-04 derivation had. Fools the BOTTOM.
    ("m4_numeric_corner_legend", [5, "F", 16], True, 7, 5),
]


@pytest.mark.parametrize("name,junk,expect_refusal,_top,_bottom", JUNK_SHAPES,
                         ids=[s[0] for s in JUNK_SHAPES])
def test_junk_above_the_grid_is_refused_or_parsed_but_never_guessed(
        name, junk, expect_refusal, _top, _bottom, caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="HTMLTopologyParser"):
        records = HTMLMatrixTableParser().parse_matrix_to_records(
            _bonding_map_with_junk_row(junk))
    refusals = [r.getMessage() for r in caplog.records if "REFUSED" in r.getMessage()]

    if expect_refusal:
        assert records == [], (
            "a shape the two derivations disagree about must be REFUSED, not silently "
            "adopted as the grid origin"
        )
        # Zero records is NOT sufficient. An accidentally-empty parse and a refusal are
        # the same silence otherwise - which is the entire finding this round is about.
        assert len(refusals) == 1, (
            f"{name}: 0 records with no stated reason is indistinguishable from a "
            f"successful parse of an empty grid"
        )
    else:
        assert refusals == [], f"{name}: a parseable shape must not be refused"
        # Correct parse, and the junk row contributes NO header key.
        assert len(records) == 11 * 11
        assert sorted({r["X"] for r in records}) == list(range(1, 12))
        assert _meta_of(records) == {"TITLE": "AAA", "BDIE_LOT": "A", "BDIE_WF": "B",
                                     "CDIE_LOT": "C", "CDIE_WF": "D"}


def test_refusal_names_both_derivations_and_is_cp949_encodable(caplog):
    """A refusal that does not say WHY is the same silence in a different costume."""
    import logging
    with caplog.at_level(logging.WARNING, logger="HTMLTopologyParser"):
        HTMLMatrixTableParser().parse_matrix_to_records(
            _bonding_map_with_junk_row(["SLOT", 2, 3, 6, 7, 10, 11, 14, 15, 18, 19, 22])
        )

    lines = [r.getMessage() for r in caplog.records if "REFUSED" in r.getMessage()]
    assert len(lines) == 1, "one named refusal per call, no more and no less"
    msg = lines[0]
    assert "row 6" in msg and "row 7" in msg, "both candidate origins must be named"
    assert "business key" in msg, "must say why 0 records beats a wrong origin"
    msg.encode("cp949")


def _anchors(html):
    """Re-derive both grid-origin anchors from the outside, as an oracle.

    Deliberately a second implementation rather than a call into the parser: a fixture
    checked with the code under test proves nothing about the fixture.
    """
    from bs4 import BeautifulSoup
    gp = HTMLMatrixTableParser().graph_parser
    grid, row_count, col_count = gp._reconstruct_2d_grid(
        BeautifulSoup(html, "html.parser").find("table"))
    nodes, _ = gp._build_adjacency_graph(grid, row_count, col_count)

    def is_int(t):
        try:
            int(t)
            return True
        except (TypeError, ValueError):
            return False

    def unmerged(n):
        return n.row_span == 1 and n.col_span == 1

    top = None
    for r in range(row_count):
        corner = grid.get((r, 0))
        if corner is None or not unmerged(corner) or is_int(corner.value):
            continue
        ticks, seen, ok = [], {corner.id}, True
        for c in range(1, col_count):
            n = grid.get((r, c))
            if n is None or n.id in seen:
                continue
            seen.add(n.id)
            if not unmerged(n) or not is_int(n.value):
                ok = False
                break
            ticks.append(n)
        if ok and len(ticks) >= 2:
            top = r
            break

    y_rows = [n.row_range[0] for n in nodes
              if n.col_range[0] == 0 and unmerged(n) and is_int(n.value)]
    bottom = (min(y_rows) - 1) if y_rows else None
    return top, bottom


def test_the_junk_fixtures_actually_reach_the_cross_check():
    """Guard the guard: M1/M2/M2-A only prove anything if the two anchors DISAGREE.

    A fixture built so that both derivations happen to land on the same row would leave
    the refusal untested and the suite still green. Assert each anchor's value directly,
    against an independently written oracle.

    The set is also asserted to be BALANCED: at least one shape must fool the top anchor
    and at least one must fool the bottom. Otherwise the surviving anchor could be
    dropped and this suite would not notice - which is exactly what a reviewer should be
    able to check without rerunning the injections.
    """
    fooled_top, fooled_bottom = 0, 0
    for name, junk, expect_refusal, exp_top, exp_bottom in JUNK_SHAPES:
        top, bottom = _anchors(_bonding_map_with_junk_row(junk))
        assert (top, bottom) == (exp_top, exp_bottom), f"{name}: anchors moved"
        assert (top != bottom) == expect_refusal, f"{name}: refusal must follow disagreement"
        if top != 7:
            fooled_top += 1
        if bottom != 7:
            fooled_bottom += 1

    assert fooled_top >= 1, "no shape exercises the top anchor's blind spot"
    assert fooled_bottom >= 1, (
        "no shape exercises the bottom anchor's blind spot - the top anchor could be "
        "deleted and this suite would stay green"
    )


def test_the_control_shape_has_both_anchors_agreeing():
    """And the converse - without junk the two derivations agree, so nothing is
    refused. Otherwise the refusal path could be passing for the wrong reason."""
    top, bottom = _anchors(_bonding_map_html("AAA", [("BDIE", "A", "B"), ("CDIE", "C", "D")]))
    assert top == bottom == 6
