"""[D4] A source map with NO `wafer_map_metadata` row is the NORMAL case, not a defect.

WHAT THE PRODUCT OWNER REPORTED
"map meta 없는 거를 현재 유효 다이 세팅으로 맞춰보는 게 안 된다는 건데." The maps they want
to align have no spec row, and that absence is the REASON they opened the alignment editor -
they are running alignment BECAUSE they do not know the source map's spec. Answering
"맵 규격 미등록 (wafer_map_metadata)" demands the answer before the question.

WHERE THE LINE WAS DRAWN WRONG
`score_candidates` treated "no row" as a question of IDENTITY (dead end) and "row without
phys" as a question of EVIDENCE (reaches the borrow). To the operator they are one fact -
the spec is unknown - and the first is if anything the purer case of it. [D3] already ruled
that case: borrow the wafer spec from the declared floor, for the COMPUTATION only, marked
as an assumption. This file pins that an absent row gets the same ruling.

THE TWO INVARIANTS THAT MUST NOT MOVE
1. The result is an ASSUMPTION and never a declaration. It answers `geometry_declaration`
   as `assumed`, it carries `PHYS_ASSUMED_KEY` provenance, and nothing on this path writes
   to `wafer_map_metadata` (`test_nothing_on_this_path_writes_a_meta_row` runs the real DB
   path and counts rows before and after). ⚠️ `this path` means SCORING, and since
   2026-08-06 that qualifier matters: a CONFIRMATION does write a metadata row and is a
   different act (MAP_ALIGNMENT_SPEC 9.7 / `test_frame_confirmation_meta.py`). What stays
   forbidden is an UNMARKED borrow reaching a stored row.
2. An undeclared floor REFUSES - there is no eyeball-it fallback - and the refusal names
   THE FLOOR. The old behaviour turned every source map into `meta_missing`, which sends
   the operator to fix N source maps when the one thing needing a declaration is the single
   map they picked as the floor.

THE MEASUREMENT THAT LIMITS ALL OF THIS is
`test_a_cropped_floor_still_refuses_because_a_cell_span_is_only_a_lower_bound`. It is not a
labelling check - it runs the real transform stack and reports which floors this path can
actually serve.
"""
import json

import pytest

import map_alignment as ma
import map_meta_registrar
import map_overlay
from database import crud, models

SRC = "unreg_test_log"
MAPT = "unreg_test_map"

PHYS = {"phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 8.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}
THRESHOLDS = {"min_margin_dies": 1, "min_discriminating_dies": 1}
REF_REF = {"table": "unreg_test_ref", "map_id": "R1"}

# 13x13 at chip 7x8 inside a 300mm wafer: the mask crops NOTHING, so the cell span equals
# the grid. That equality is what makes the borrow usable at all - see the cropped
# counterpart at the bottom of this file, which is the same fixture with a bigger grid.
COLS, ROWS = 13, 13


def _meta(cols=COLS, rows=ROWS, **kw):
    m = {"grid_cols": cols, "grid_rows": rows, "rotation": 0, "side": "front",
         "grid_y_invert": False, "grid_start_x": 1, "grid_start_y": 1}
    m.update(PHYS)
    m.update(kw)
    assert not (set(kw) - set(m)), "unknown meta key: %s" % sorted(set(kw) - set(m))
    return m


def _auto_meta(**kw):
    """What `synthesize_grid_meta` leaves behind: the six keys are present and well formed,
    and the marker says nobody measured them. Used here as a NOT-declared floor."""
    m = _meta(**kw)
    m.update({"phys_chip_x": 1, "phys_chip_y": 1, "phys_offset_x": 0, "phys_offset_y": 0,
              "phys_edge_margin": 3, "phys_wafer_dia": 300, "auto_registered": True})
    return m


def _tf_of(m):
    from utils.coordinate_transformer import WaferMapCoordinateTransformer
    from utils.physical_wafer_engine import PhysicalWaferEngine
    dia, cx, cy, ox, oy, mg = map_overlay._frame_phys_params(m)
    eng = PhysicalWaferEngine(wafer_diameter_mm=dia, chip_size_x_mm=cx, chip_size_y_mm=cy,
                              edge_exclusion_mm=mg, offset_x_mm=ox, offset_y_mm=oy)
    g = map_overlay._grid_of(m)
    return WaferMapCoordinateTransformer(
        cols=g["cols"], rows=g["rows"], start_x=g["start_x"], start_y=g["start_y"],
        rotation=map_overlay._rotation_of(m), side=map_overlay._side_of(m),
        invert_y=map_overlay._y_invert_of(m), physical_engine=eng), g


def _cells_of(m):
    """Every stored coordinate this meta admits - bbox-relative, as the client writes them."""
    tf, g = _tf_of(m)
    min_c, max_c, min_r, max_r = tf.get_wafer_bounding_box()
    return [(c - min_c + g["start_x"], r - min_r + g["start_y"])
            for r in range(min_r, max_r + 1) for c in range(min_c, max_c + 1)
            if tf.is_inside_wafer(c, r)]


def _asymmetric_subset(m=None):
    """An occupied subset with NO dihedral symmetry. The circle is invariant under all eight
    frames, so a symmetric fixture ties every candidate and the failure reads as a scorer bug
    when it is a fixture bug."""
    return [p for p in _cells_of(m or _meta()) if not (p[0] > 9 and p[1] < 4)]


def _span(cells):
    return (max(x for x, _ in cells) - min(x for x, _ in cells) + 1,
            max(y for _, y in cells) - min(y for _, y in cells) + 1)


def _score(source_maps, ref_cells, ref_meta, **kw):
    kw.setdefault("thresholds", THRESHOLDS)
    kw.setdefault("reference_ref", REF_REF)
    map_overlay._FRAME_TF_CACHE.clear()
    return ma.score_candidates(source_maps, ref_cells, ref_meta, **kw)


def _no_row_map(cells, map_id="NOROW"):
    """The production shape: cells exist, `meta` is None because no spec row was ever
    registered for this map."""
    return {"map_id": map_id, "meta": None, "cells": list(cells)}


def _reasons(excluded):
    return {r["reason_code"]: r["count"] for r in excluded.as_list()}


# ---------------------------------------------------------------------------
# 1. an absent row reaches the borrow rather than a dead end
# ---------------------------------------------------------------------------

def test_a_map_with_no_meta_row_is_offered_the_assumption_not_declared_missing():
    """Without the assumption requested, the map is still EXCLUDED - but it must be counted
    as assumable so the screen can say the offer exists. Reporting `meta_missing` here is
    what drew the dead end: it names a repair (register the map) that is not the repair."""
    ref = _asymmetric_subset()
    _c, excluded, _r, stats = _score([_no_row_map(ref)], ref, _meta(),
                                     assume_reference_geometry=False)

    assert stats["assumable_map_ids"] == ["NOROW"]
    assert stats["assumed_map_ids"] == []
    assert ma.EXCLUDE_META_MISSING not in _reasons(excluded)
    rows = excluded.as_list()
    assert [r["reason_code"] for r in rows] == [ma.EXCLUDE_GEOMETRY_REFUSED]
    # and the detail says WHICH fact, so the offer is legible rather than generic
    assert rows[0]["example_detail"] == ma.TEXT_NO_META_ROW


def test_a_map_with_no_meta_row_is_scored_when_the_assumption_is_requested():
    """The outcome the operator asked for: fit an unregistered map against the currently
    selected valid-die map."""
    ref = _asymmetric_subset()
    _c, excluded, ruling, stats = _score([_no_row_map(ref)], ref, _meta(),
                                         assume_reference_geometry=True)

    assert stats["usable_map_ids"] == ["NOROW"]
    assert stats["assumed_map_ids"] == ["NOROW"]
    assert excluded.as_list() == []
    assert ruling["geometry_assumed"] is True
    assert ruling["assumed_map_count"] == 1


def test_a_planted_frame_is_recovered_for_a_map_that_has_no_meta_row():
    """The only assertion here that would notice an unlock which lets the population through
    and then scores it WRONG. The source cells are the floor's own cells re-expressed in a
    planted frame; the scorer must name that frame back."""
    floor = _meta()
    ref = _asymmetric_subset(floor)
    for planted in ("rot90_front", "rot180_front", "rot270_back"):
        from dt_map_derivation import source_meta_for_frame
        map_overlay._FRAME_TF_CACHE.clear()
        planted_meta = source_meta_for_frame(_meta(), planted)
        back = map_overlay.make_frame_transform(floor, planted_meta)
        cells = [back(x, y) for (x, y) in ref]

        _c, _e, ruling, stats = _score([_no_row_map(cells)], ref, floor,
                                       assume_reference_geometry=True)
        assert stats["usable_map_ids"] == ["NOROW"], planted
        assert ruling.get("winner") == planted, (planted, ruling.get("winner"))


# ---------------------------------------------------------------------------
# 2. it is the EXISTING primitive, and the result stays an assumption
# ---------------------------------------------------------------------------

def test_the_frame_is_the_existing_synthesizer_with_only_the_grid_replaced():
    """A third frame synthesizer would be a third vocabulary for «mask-neutral frame», and
    the day the three disagree the screen is perfect and every value is wrong. So this
    asserts composition, not shape: everything except the four grid keys must be
    byte-identical to what the existing primitive produces.

    🔴 The floor is the CROPPED one on purpose. On an uncropped floor the cell span equals
       the floor's grid, so a build that did NOT borrow would produce the identical dict and
       this assertion would pass on it - measured, not supposed: an earlier version of this
       test used `_meta()` and survived exactly that mutation."""
    floor = _meta(cols=45, rows=39)
    cells = _cells_of(floor)
    assert _span(cells) != (45, 39), "fixture must be able to see the grid substitution"
    bbox = (min(x for x, _ in cells), min(y for _, y in cells),
            max(x for x, _ in cells), max(y for _, y in cells))

    synth = map_meta_registrar.synthesize_grid_meta(*bbox)
    got = ma.assumed_meta_for_unregistered(cells, floor, REF_REF)
    GRID = ("grid_cols", "grid_rows", "grid_start_x", "grid_start_y")
    for k, v in synth.items():
        if k in GRID or k in map_overlay.PHYS_KEYS:
            continue
        assert got[k] == v, k                       # mask-neutral vocabulary, unchanged
    assert got[map_overlay.AUTO_REGISTERED_KEY] is True

    # and the whole thing is still the existing primitives composed. [D6] the hand-written
    # grid substitution became its own primitive (`assume_grid_from`), so the composition now
    # names three - and the borrowed grid carries its own marker, for the same reason the
    # borrowed phys always did: a value taken from somewhere else must say where.
    expected = map_overlay.assume_phys_from(
        map_overlay.assume_grid_from(synth, floor, REF_REF), floor, REF_REF)
    assert json.dumps(got, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert got[map_overlay.GRID_ASSUMED_KEY] == REF_REF


def test_the_frame_borrows_the_wafer_AND_the_grid():
    """[D5] The reversal. Grid dims AND start come from the floor, not from the cells - a
    partial map's span is systematically an under-estimate, so the derived answer is the
    less accurate one, not the safer one. Cropped floor so the two answers are DIFFERENT
    numbers; otherwise the assertion cannot tell them apart."""
    floor = _meta(cols=45, rows=39)
    cells = _cells_of(floor)
    got = ma.assumed_meta_for_unregistered(cells, floor, REF_REF)

    for k in map_overlay.PHYS_KEYS:
        assert got[k] == float(floor[k]), k
    assert map_overlay.grid_dims(got) == map_overlay.grid_dims(floor) == (45, 39)
    assert map_overlay.grid_dims(got) != _span(cells)          # NOT the span
    assert (got["grid_start_x"], got["grid_start_y"]) == (floor["grid_start_x"],
                                                          floor["grid_start_y"])
    assert map_overlay.grid_box(got) == map_overlay.grid_box(floor)


def test_the_result_is_an_assumption_and_says_where_it_came_from():
    """[D3]'s invariant, extended to the absent-row case. `assumed` is not `declared`, and
    the provenance is what lets someone later ask which decisions rested on it."""
    got = ma.assumed_meta_for_unregistered(_asymmetric_subset(), _meta(), REF_REF)
    assert map_overlay.geometry_declaration(got) == map_overlay.GEOMETRY_ASSUMED
    assert map_overlay.geometry_declaration(got) != map_overlay.GEOMETRY_DECLARED
    assert map_overlay.geometry_refusal(got) is not None     # not a declaration
    assert map_overlay.geometry_computable(got) is None      # but it IS a basis
    assert got[map_overlay.PHYS_ASSUMED_KEY] == REF_REF


def test_a_map_scored_this_way_reports_assumed_as_its_basis():
    """`geometry_basis_of` is the one spelling both the payload and the confirmation record
    read. A map with no row that WAS aligned must answer `assumed`, not `absent` - otherwise
    the record loses the fact that a verdict rested on a borrowed wafer."""
    ref = _asymmetric_subset()
    _c, _e, _r, stats = _score([_no_row_map(ref)], ref, _meta(),
                               assume_reference_geometry=True)
    assert stats["usable_map_ids"] == ["NOROW"]
    assert ma.geometry_basis_of(None, None) == map_overlay.GEOMETRY_ASSUMED
    # excluded maps are aligned to nothing, so they keep their own (absent) token
    assert ma.geometry_basis_of(None, "not_aligned") == map_overlay.GEOMETRY_ABSENT


# ---------------------------------------------------------------------------
# 3. an undeclared floor refuses, and the refusal names the floor
# ---------------------------------------------------------------------------

def test_an_undeclared_floor_refuses_rather_than_drawing_something():
    """There is no eyeball-it fallback. Coordinates drawn without a basis look perfect and
    are entirely wrong, and that failure is invisible in a cell count."""
    ref = _asymmetric_subset()
    _c, excluded, _r, stats = _score([_no_row_map(ref)], ref, _auto_meta(),
                                     assume_reference_geometry=True)
    assert stats["usable_map_ids"] == []
    assert stats["assumed_map_ids"] == []
    assert stats["basis_undeclared_map_ids"] == ["NOROW"]


def test_the_undeclared_floor_is_not_counted_as_a_fault_of_the_source_maps():
    """THE asymmetry. Three source maps fail for ONE reason that belongs to a fourth map.
    Padding the per-map exclusion list with it makes the repair look like N jobs and hides
    the single one - fifteen minutes versus a week."""
    ref = _asymmetric_subset()
    maps = [_no_row_map(ref, "A"), _no_row_map(ref, "B"), _no_row_map(ref, "C")]
    _c, excluded, _r, stats = _score(maps, ref, _auto_meta(),
                                     assume_reference_geometry=True)

    assert stats["basis_undeclared_map_ids"] == ["A", "B", "C"]
    assert ma.EXCLUDE_META_MISSING not in _reasons(excluded)
    assert ma.EXCLUDE_BASIS_UNDECLARED not in _reasons(excluded)
    assert excluded.as_list() == []


def test_the_refusal_has_its_own_code_its_own_label_and_one_spelling():
    """Same vocabulary discipline as the codes it joins: a label lives in `_EXCLUDE_TEXT`,
    the sentence is composed by the server, and the worklist inherits the label rather than
    keeping a second copy of it."""
    assert ma._EXCLUDE_TEXT.get(ma.EXCLUDE_BASIS_UNDECLARED)
    assert ma._WORKLIST_REASON_TEXT[ma.EXCLUDE_BASIS_UNDECLARED] == \
        ma._EXCLUDE_TEXT[ma.EXCLUDE_BASIS_UNDECLARED]
    assert ma.EXCLUDE_BASIS_UNDECLARED != ma.EXCLUDE_META_MISSING


def test_the_request_level_statement_names_the_floor_and_is_stated_once():
    block = ma.compose_basis_refusal(["A", "B", "C"],
                                     {"table": "valid_die_ref", "map_id": "P1_T1"},
                                     "기준 맵 규격 미선언")
    assert block["reason_code"] == ma.EXCLUDE_BASIS_UNDECLARED
    assert block["map_count"] == 3
    assert block["basis"] == {"table": "valid_die_ref", "map_id": "P1_T1"}
    # the sentence must send the operator to the FLOOR, not to the source maps
    assert "기준" in block["text"]
    assert ma.compose_basis_refusal([], None, None) is None


# ---------------------------------------------------------------------------
# 4. ordering: coordinates are asked about before the spec
# ---------------------------------------------------------------------------

def test_a_map_with_neither_cells_nor_a_meta_row_is_named_by_its_coordinates():
    """With no row the frame comes from the map's own cells, so no cells means there is
    nothing to measure before the spec even matters. The old order answered `meta_missing`,
    which points at the half that is NOT the operator's to fix."""
    ref = _asymmetric_subset()
    _c, excluded, _r, _s = _score([{"map_id": "EMPTY", "meta": None, "cells": []}],
                                  ref, _meta(), assume_reference_geometry=True)
    assert list(_reasons(excluded)) == [ma.EXCLUDE_NO_CELLS]


# ---------------------------------------------------------------------------
# 5. THE MEASUREMENT - which floors this path can actually serve
# ---------------------------------------------------------------------------

def test_a_cropped_floor_now_goes_all_the_way_through():
    """[D5] The reversal, at the outcome level. Under [D4] this exact fixture was excluded
    `grid_dims_differ`: the synthesized span (41x35) could never equal the floor's declared
    grid (45x39), and `make_frame_transform` requires equality. Borrowing the grid removes
    that mismatch by construction - there is only one grid now."""
    cropped = _meta(cols=45, rows=39)
    cells = _cells_of(cropped)
    assert _span(cells) == (41, 35) != (45, 39), "fixture must actually crop"

    _c, excluded, _r, stats = _score([_no_row_map(cells)], cells, cropped,
                                     assume_reference_geometry=True)
    assert stats["assumed_map_ids"] == ["NOROW"]
    assert stats["usable_map_ids"] == ["NOROW"]
    assert excluded.as_list() == []


# ---------------------------------------------------------------------------
# 5-bis. THE LOAD-BEARING MEASUREMENT - a PARTIAL map lands where it started
# ---------------------------------------------------------------------------

def _partial_of(floor):
    """«DT를 일부만 돌렸다» - a contiguous asymmetric REGION of the wafer, expressed in the
    floor's coordinates. This is the population the product owner named, and it is the only
    fixture that can tell the two halves of the grid apart: a full-coverage map has its own
    min at the floor's start, so deriving start from cells looks correct on it."""
    return [p for p in _cells_of(floor)
            if 12 <= p[0] <= 34 and 8 <= p[1] <= 28 and not (p[0] > 30 and p[1] < 12)]


@pytest.mark.parametrize("planted", ["rot0_front", "rot90_front", "rot180_front",
                                     "rot270_back"])
def test_a_partial_map_is_placed_back_exactly_where_it_came_from(planted):
    """ORACLE, not a label check: take a partial map whose true frame is known, run the real
    transform stack under that frame, and require the coordinates we started from - cell for
    cell, zero tolerance.

    🔴 This is the assertion that distinguishes «borrow the dims» from «borrow the grid».
       MEASURED on this fixture (467 cells): borrowing dims while DERIVING start from the
       cells gets 467/467 cells wrong, because re-basing a partial map to its own minimum
       translates the whole map (11 columns here). The shift solver only reaches +-3, so
       that error does not announce itself - it is the silent-overlay failure, arriving by
       the half of the grid nobody was watching.
    """
    from dt_map_derivation import source_meta_for_frame
    floor = _meta(cols=45, rows=39)
    truth = _partial_of(floor)
    assert len(truth) > 100

    map_overlay._FRAME_TF_CACHE.clear()
    to_planted = map_overlay.make_frame_transform(
        floor, source_meta_for_frame(_meta(cols=45, rows=39), planted))
    stored = [to_planted(x, y) for (x, y) in truth]

    assumed = ma.assumed_meta_for_unregistered(stored, floor, REF_REF)

    map_overlay._FRAME_TF_CACHE.clear()
    back = map_overlay.make_frame_transform(
        source_meta_for_frame(assumed, planted), floor)
    got = [back(x, y) for (x, y) in stored]
    wrong = sum(1 for a, b in zip(got, truth) if a != b)
    assert wrong == 0, "%d/%d cells landed in the wrong place" % (wrong, len(truth))


# ---------------------------------------------------------------------------
# 5-ter. [D16] A DIFFERENT STORED ORIGIN IS NOT A DIFFERENT GRID
# ---------------------------------------------------------------------------
# WHAT THE OPERATOR REPORTED, verbatim: 「셀 범위 2~28이 빌린 격자 −4~26을 벗어나서 점수
# 못 낸다는데, 당연히 shift가 있으니 범위가 다를 수 있는 거 아니야? 불합리한 설계로 보임」.
#
# They are right and the widths prove it: the source spans 2..28 (width 27), the borrowed
# grid spans -4..26 (width 31). THE SOURCE IS SMALLER THAN THE GRID - it fits. What does not
# line up is the origin, and closing that gap is exactly what the shift the aligner solves
# is for.
#
# WHERE THE LINE WAS DRAWN WRONG. The retired guard (`cells_outside_grid`) compared the
# source's RAW STORED bbox against the floor's index box. Those are two different origins -
# the product owner ruled a map's stored origin arbitrary from map to map (「랜덤이야」) - so
# the containment it computed was not a test of anything. And it ran BEFORE the placement:
# it refused a map on the grounds that it did not fit where it had not yet been put.
#
# The guard did not even separate the population it claimed to. MEASURED 2026-08-06: a solid
# 20x20 block - not a wafer at all, unambiguously «a different map» - passes the guard at
# stored origin -4 AND at +7, and scoring is what refuses it (400 vs 400, margin 0, TIE).
# Meanwhile the operator's honest partial map of the SAME wafer was deleted for being at +6.
# The only input the guard discriminated on was the arbitrary origin.

_ORIGIN_FLOOR = dict(cols=31, rows=31, grid_start_x=-4, grid_start_y=-4)


def _origin_shifted_source(floor, off):
    """A partial DT map of THIS wafer, written down under its own arbitrary stored origin.

    Returns `(truth_in_floor_coords, stored, indices)`. The indices are the DT walk order
    over the map's own cells - production carries them in a column, and they are what lets
    the anchor read the translation instead of searching a +-3 window for it."""
    truth = [p for p in _cells_of(floor)
             if p[0] <= 22 and p[1] <= 22 and not (p[0] > 18 and p[1] < -1)]
    stored = [(x + off, y + off) for (x, y) in truth]
    walk = ma.serpentine_index(stored, top_is_min_y=True)
    rank = {xy: k for k, xy in walk.items()}
    return truth, stored, [rank.get(tuple(p)) for p in stored]


def test_a_source_offset_from_the_floors_origin_is_still_scorable():
    """🔴 THE OPERATOR'S SHAPE, to the number. A source spanning 2..28 against a borrowed
    grid spanning -4..26 must be SCORABLE - and on this fixture the answer it yields is not
    marginal, it is exact.

    MEASURED with the guard still in place: 8/8 candidates `not_scorable`, no ruling at all.
    The guard sat OUTSIDE the candidate loop, so it did not pick among the eight - it erased
    the map before the loop began. With it gone: rot0_front 706/706, runner-up 549,
    margin 157, 705 discriminating dies, placement `anchor`."""
    floor = _meta(**_ORIGIN_FLOOR)
    truth, stored, indices = _origin_shifted_source(floor, off=6)

    # The fixture must ACTUALLY carry the reported shape, or this test stops exercising the
    # axis the day the wafer mask changes and nobody notices.
    assert map_overlay.grid_box(floor) == (-4, -4, 26, 26)
    assert (min(x for x, _ in stored), max(x for x, _ in stored)) == (2, 28)
    assert (min(y for _, y in stored), max(y for _, y in stored)) == (2, 28)
    src_w = 28 - 2 + 1
    assert src_w < 26 - (-4) + 1, "the source must be SMALLER than the grid it is refused by"

    src = {"map_id": "NOROW", "meta": None, "cells": stored, "indices": indices}
    cands, excluded, ruling, stats = _score([src], _cells_of(floor), floor,
                                            assume_reference_geometry=True)
    assert stats["usable_map_ids"] == ["NOROW"], list(_reasons(excluded))
    assert list(_reasons(excluded)) == []

    scored = [c for c in cands if c.get("state") == "scored"]
    assert len(scored) == 8, [(c["frame"], c.get("state")) for c in cands]

    # Not merely scorable - RIGHT. The map came from rot0_front, and every one of its dies
    # lands back on the floor.
    best = max(scored, key=lambda c: c["agreement"])
    assert best["frame"] == "rot0_front", [(c["frame"], c["agreement"]) for c in scored]
    assert best["agreement"] == len(truth) == 706
    assert ruling["margin"] and ruling["margin"] > 0
    assert ruling.get("placement") == "anchor"


def test_the_origin_offset_does_not_have_to_be_small():
    """The operator's own words - 「당연히 shift가 있으니 범위가 다를 수 있는 거 아니야」.
    The offset is a property of how the map was written down, not a tolerance, so there is
    no size at which it becomes a defect. Same map, three origins, same answer."""
    floor = _meta(**_ORIGIN_FLOOR)
    got = []
    for off in (6, 40, 100000):
        truth, stored, indices = _origin_shifted_source(floor, off=off)
        src = {"map_id": "NOROW", "meta": None, "cells": stored, "indices": indices}
        cands, excluded, _r, stats = _score([src], _cells_of(floor), floor,
                                           assume_reference_geometry=True)
        assert stats["usable_map_ids"] == ["NOROW"], (off, list(_reasons(excluded)))
        got.append(tuple(sorted((c["frame"], c.get("agreement")) for c in cands)))
    assert got[0] == got[1] == got[2], "the stored origin leaked into the score"


def test_a_map_that_is_not_this_wafer_is_refused_by_the_RULING_not_before_it():
    """🔴 The vocabulary must not go silent. Retiring the guard does not mean a mismatched
    map now passes - it means the refusal moves to the place that can actually see it.

    A solid 20x20 block is not this wafer's footprint. It reaches the scorer (no exclusion),
    and scoring refuses it BY NAME: two frames tie at 400, so there is no sole best and the
    ruling reports `tie` with no winner. That is the same information the guard claimed to
    carry, arrived at by measurement instead of by an origin coincidence."""
    floor = _meta(**_ORIGIN_FLOOR)
    block = [(x, y) for x in range(-4, 16) for y in range(-4, 16)]
    walk = ma.serpentine_index(block, top_is_min_y=True)
    rank = {xy: k for k, xy in walk.items()}
    src = {"map_id": "NOROW", "meta": None, "cells": block,
           "indices": [rank.get(tuple(p)) for p in block]}

    _c, excluded, ruling, stats = _score([src], _cells_of(floor), floor,
                                         assume_reference_geometry=True)
    assert stats["usable_map_ids"] == ["NOROW"], list(_reasons(excluded))
    assert ruling.get("winner") is None, ruling
    assert ruling.get("reason_code") == ma.RULING_TIE, ruling


def test_a_rotated_full_map_reaches_the_scorer():
    """Kept from the retired containment section, because the population is still real.
    Stored coordinates live in the frame's VISUAL extent and a 90/270 frame swaps it: a
    full-coverage map of a 45x39 wafer drawn at rot90 stores y up to 41, past `rows=39`.
    Any future gate that reads a bbox must not refuse these - rotation is what the eight
    candidates are solving, and deciding it before the loop answers the question first."""
    from dt_map_derivation import source_meta_for_frame
    floor = _meta(cols=45, rows=39)
    map_overlay._FRAME_TF_CACHE.clear()
    to90 = map_overlay.make_frame_transform(
        floor, source_meta_for_frame(_meta(cols=45, rows=39), "rot90_front"))
    stored = [to90(x, y) for (x, y) in _cells_of(floor)]
    assert max(y for _, y in stored) > 39, "fixture must exceed `rows` or it sees nothing"

    _c, excluded, _r, stats = _score([_no_row_map(stored)], _cells_of(floor), floor,
                                     assume_reference_geometry=True)
    assert stats["usable_map_ids"] == ["NOROW"], _reasons(excluded)


# ---------------------------------------------------------------------------
# 6. the DB path - the invariant that nothing here is ever written
# ---------------------------------------------------------------------------

TABLES = {
    SRC: {"business_key": "cell_key",
          "column_types": {"cell_key": "string", "eqp": "string", "job": "string",
                           "x": "number", "y": "number", "v": "string"},
          "map_key_columns": ["job"]},
    MAPT: {"business_key": "cell_key",
           "column_types": {"cell_key": "string", "job": "string",
                            "x": "number", "y": "number"},
           "map_key_columns": ["job"]},
    # Product-owned tables, copied VERBATIM from table_config.json.
    map_overlay.VALID_DIE_TABLE: {
        "business_key": "cell_key",
        "composite_key_source": ["product", "type", "x", "y"],
        "composite_key_separator": "_",
        "column_types": {"cell_key": "string", "product": "string", "type": "string",
                         "x": "number", "y": "number", "val": "string"},
        "map_key_columns": ["product", "type"]},
    "unreg_test_unit": {"business_key": "unit_key",
                        "composite_key_source": ["eqp"],
                        "column_types": {"unit_key": "string", "eqp": "string",
                                         "map_metadata": "string"}},
    map_overlay.META_TABLE: {"business_key": "map_pk",
                             "composite_key_source": ["target_table", "map_id"],
                             "column_types": {"map_pk": "string",
                                              "target_table": "string",
                                              "map_id": "string",
                                              "grid_metadata": "string"}},
}

RULE = {"name": "unreg_test_rule", "source_table": SRC,
        "derived_table": "unreg_test_unit", "decision_key": ["eqp"],
        "target_fields": ["map_metadata"]}

CFG = {"table_bindings": {
    SRC: {"columns": {"x": "x", "y": "y", "val": "v", "key_columns": ["job"]}},
}, "alignment": THRESHOLDS}


@pytest.fixture()
def env(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    map_overlay._FRAME_TF_CACHE.clear()
    return db_session


def _seed(db, floor_meta=_meta):
    """One unit, one source map with NO meta row, and a floor that HAS one."""
    s = models.DYNAMIC_TABLES[SRC]
    v = models.DYNAMIC_TABLES[map_overlay.VALID_DIE_TABLE]
    meta_model = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    fm = floor_meta() if callable(floor_meta) else floor_meta
    cells = _asymmetric_subset(fm)
    for i, (x, y) in enumerate(cells):
        db.add(s(row_id="s%d" % i, business_key_val="s%d" % i, cell_key="s%d" % i,
                 eqp="E1", job="J1", x=x, y=y, v="1"))
        db.add(v(row_id="v%d" % i, business_key_val="v%d" % i, cell_key="v%d" % i,
                 product="P1", type="T1", x=x, y=y, val="1"))
    db.add(meta_model(row_id="mv", business_key_val="floor",
                      target_table=map_overlay.VALID_DIE_TABLE, map_id="P1_T1",
                      grid_metadata=json.dumps(fm)))
    db.commit()
    return cells


def _meta_rows(db):
    m = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    return {(r.target_table, r.map_id) for r in db.query(m).all()}


def test_nothing_on_this_path_writes_a_meta_row(env):
    """THE line this change must not cross. If the borrowed spec ever reached
    `wafer_map_metadata` it would afterwards read as a value somebody measured, and nobody
    could tell it was assumed. Counted against the real table, not asserted about the code.

    ⚠️ **THE SCOPE IS THIS PATH, AND SINCE 2026-08-06 THAT WORD IS LOAD-BEARING.** Scoring
    is a READ and still writes nothing — that is what this counts. A confirmation is a
    different act and DOES write a metadata row (MAP_ALIGNMENT_SPEC 9.7): the product owner
    overturned the prohibition because a match against a product-specific reference is
    evidence, and the row carries `phys_confirmed_from`/`frame_confirmed_from` with the
    confirmation's identity so it can never read as something somebody measured. The half
    of the old rule that survives is the half this test guards: an UNMARKED borrow reaches
    no stored row. `test_frame_confirmation_meta.py` is the other side."""
    _seed(env)
    before = _meta_rows(env)

    view = ma.build_alignment_view(
        env, CFG, RULE, {"eqp": "E1"}, MAPT,
        reference_spec="%s:P1_T1" % map_overlay.VALID_DIE_TABLE,
        include_cells=False, x_col="x", y_col="y", assume_reference_geometry=True)

    assert view["ruling"]["geometry_assumed"] is True
    assert view["assumption"]["state"] == ma.ASSUMPTION_APPLIED
    assert map_overlay.load_map_meta(env, MAPT, "J1") is None
    assert _meta_rows(env) == before == {(map_overlay.VALID_DIE_TABLE, "P1_T1")}


def test_the_view_offers_the_assumption_instead_of_reporting_the_map_unregistered(env):
    """End to end, without the assumption requested: the screen must be able to say the
    offer exists. `assumption.state` carrying `available` is what replaces the dead end."""
    _seed(env)
    view = ma.build_alignment_view(
        env, CFG, RULE, {"eqp": "E1"}, MAPT,
        reference_spec="%s:P1_T1" % map_overlay.VALID_DIE_TABLE,
        include_cells=False, x_col="x", y_col="y", assume_reference_geometry=False)

    assert view["assumption"]["state"] == ma.ASSUMPTION_AVAILABLE
    assert view["assumption"]["map_ids"] == ["J1"]
    assert ma.EXCLUDE_META_MISSING not in {e["reason_code"] for e in view["excluded"]}
    assert view["basis_refusal"] is None


def test_with_no_floor_the_view_names_the_floor_once_instead_of_every_source_map(env):
    """The production route to an undeclared basis: the reference does not resolve at all,
    and every meta-less source map used to be counted `meta_missing`. Now the response says
    it once, at the request level, pointing at the floor."""
    _seed(env)
    view = ma.build_alignment_view(
        env, CFG, RULE, {"eqp": "E1"}, MAPT,
        include_cells=False, x_col="x", y_col="y")

    assert view["reference"]["state"] == ma.REFERENCE_ABSENT
    block = view["basis_refusal"]
    assert block is not None
    assert block["reason_code"] == ma.EXCLUDE_BASIS_UNDECLARED
    assert block["map_ids"] == ["J1"]
    assert "기준" in block["text"]
    # and the per-map list is NOT padded with a fact about a different map
    assert ma.EXCLUDE_META_MISSING not in {e["reason_code"] for e in view["excluded"]}
    assert ma.EXCLUDE_BASIS_UNDECLARED not in {e["reason_code"] for e in view["excluded"]}
    # a map blocked by the missing floor is not "usable" either
    assert view["sources"]["usable_map_count"] == 0


def test_the_worklist_counts_a_map_with_no_spec_row_as_assumable(env):
    """[D5] The list must not say «가망 없음» about a unit the detail view will open. Under
    [D4] `assumable_map_count` required a meta row - which excluded exactly the population
    this feature serves, so the list under-claimed against its own detail screen.

    The count stays an UPPER BOUND (the list reads no cells, so it cannot ask containment)
    and the detail view remains authoritative - that is the pre-existing discipline, not a
    new concession."""
    _seed(env)
    d = models.DYNAMIC_TABLES["unreg_test_unit"]
    env.add(d(row_id="u1", business_key_val="E1", unit_key="E1", eqp="E1"))
    env.commit()

    wl = ma.build_alignment_worklist(env, CFG, RULE, MAPT)
    unit = next(u for u in wl["units"] if u["unit_key"] == "E1")
    assert unit["map_count"] == 1
    assert unit["usable_map_count"] == 0          # no spec row: not scorable as declared
    assert unit["assumable_map_count"] == 1       # ...but a floor would open it
