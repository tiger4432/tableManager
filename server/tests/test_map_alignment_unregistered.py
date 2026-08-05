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
   path and counts rows before and after).
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

def test_the_frame_is_the_existing_synthesizer_composed_with_the_existing_borrow():
    """A third frame synthesizer would be a third vocabulary for «mask-neutral frame», and
    the day the three disagree the screen is perfect and every value is wrong. So this
    asserts composition, not shape: the result must be byte-identical to calling the two
    primitives in order.

    🔴 The floor is the CROPPED one on purpose. On an uncropped floor the cell span equals
       the floor's grid, so a fix that quietly borrowed the dims would produce the identical
       dict and this assertion would pass on a broken build - measured, not supposed: the
       first version of this test used `_meta()` and survived exactly that mutation."""
    floor = _meta(cols=45, rows=39)
    cells = _cells_of(floor)
    assert _span(cells) != (45, 39), "fixture must be able to see a borrowed dim"
    bbox = (min(x for x, _ in cells), min(y for _, y in cells),
            max(x for x, _ in cells), max(y for _, y in cells))

    expected = map_overlay.assume_phys_from(
        map_meta_registrar.synthesize_grid_meta(*bbox), floor, REF_REF)
    got = ma.assumed_meta_for_unregistered(cells, floor, REF_REF)
    assert json.dumps(got, sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_the_frame_borrows_the_wafer_and_derives_the_grid():
    """The two halves of the ruling, each measured against its source rather than restated:
    phys comes from the floor, grid dims come from the map's OWN cells. Cropped floor for
    the same reason as above - the two answers have to be DIFFERENT numbers here."""
    floor = _meta(cols=45, rows=39)
    cells = _cells_of(floor)
    got = ma.assumed_meta_for_unregistered(cells, floor, REF_REF)

    for k in map_overlay.PHYS_KEYS:
        assert got[k] == float(floor[k]), k
    assert map_overlay.grid_dims(got) == _span(cells)
    assert map_overlay.grid_dims(got) != map_overlay.grid_dims(floor)
    assert (got["grid_start_x"], got["grid_start_y"]) == (min(x for x, _ in cells),
                                                          min(y for _, y in cells))


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

def test_a_cropped_floor_still_refuses_because_a_cell_span_is_only_a_lower_bound():
    """MEASURED, not argued. Stored coordinates are bbox-relative, so their span equals the
    wafer CROP, not the grid - `test_map_alignment_assumption.py` measured that already. So
    the synthesized grid is a LOWER BOUND on the floor's grid and is tight only when the mask
    crops nothing. `make_frame_transform` requires the two grids to be EQUAL, so on a cropped
    floor the borrow happens and the map is still excluded - `grid_dims_differ` instead of
    `meta_missing`.

    This is the limit of the ruling as written, recorded here so it is a known quantity
    rather than a surprise: the absent-row borrow serves floors whose mask crops nothing.
    """
    cropped = _meta(cols=45, rows=39)
    cells = _cells_of(cropped)
    assert _span(cells) == (41, 35) != (45, 39), "fixture must actually crop"

    _c, excluded, _r, stats = _score([_no_row_map(cells)], cells, cropped,
                                     assume_reference_geometry=True)
    assert stats["assumed_map_ids"] == ["NOROW"]        # the borrow DID happen
    assert stats["usable_map_ids"] == []                # and it still could not be scored
    assert list(_reasons(excluded)) == [ma.EXCLUDE_GRID_DIMS_DIFFER]

    # the same fixture with a grid the mask does not crop goes all the way through
    ok = _meta()
    ok_cells = _cells_of(ok)
    assert _span(ok_cells) == (COLS, ROWS)
    _c, excluded, _r, stats = _score([_no_row_map(ok_cells)], ok_cells, ok,
                                     assume_reference_geometry=True)
    assert stats["usable_map_ids"] == ["NOROW"]
    assert excluded.as_list() == []


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
    could tell it was assumed. Counted against the real table, not asserted about the code."""
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
