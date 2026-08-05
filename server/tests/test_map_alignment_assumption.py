"""[Spec MAP_ALIGNMENT_SPEC section 9(a)] Scoring a map whose wafer spec nobody ever measured.

THE CIRCULARITY THIS CLOSES
A source map could not be scored without a declared physical spec, and the operator runs the
alignment precisely BECAUSE they do not know that map's spec. Requiring it first asks for the
answer before the question. The resolution: when the source has no declared spec and the
operator picks a reference floor that HAS one, score under the assumption that the two share
the wafer's geometry - "these are the same wafer" is the premise of aligning them at all.

THE THREE THINGS THAT MUST STAY TRUE, and each has a test that fails if it stops:
  1. The borrowed value is used for the COMPUTATION and never written to the source's meta.
     `test_the_borrowed_spec_never_becomes_a_declaration` and its neighbours.
  2. The result says so - in the payload AND in the confirmation record. A verdict reached
     under an assumption is a different fact from one reached on declared geometry, and the
     whole point of recording a confirmation is that when the assumption is later shown
     false, someone can ask WHICH DECISIONS RESTED ON IT and get an answer.
  3. What is assumable is decided by measurement, not by argument. The measurements are in
     `test_borrowing_the_orientation_axes_would_move_every_cell` and
     `test_grid_dims_derived_from_cells_are_a_lower_bound_not_a_value`, which run the real
     transform stack rather than asserting a claim about it.

THE LOAD-BEARING TEST is `test_a_planted_frame_is_recovered_under_the_assumption`. Everything
else checks labelling; that one is the only assertion that would notice an unlock which lets
the population through and then scores it wrong.
"""
import json

import pytest

import frame_confirmation as fc
import map_alignment as ma
import map_overlay
from database import crud, models
from dt_map_derivation import source_meta_for_frame

SRC = "asum_test_log"
MAPT = "asum_test_map"
REFT = "asum_test_ref"

# A grid the wafer circle actually CROPS. A grid that fits entirely inside the mask has
# min_c == min_r == 0 whatever the phys values are, so it cannot see the effect these tests
# ask about - the first pass of this measurement used one and reported "no effect" for every
# axis. 45x39 at chip 7x8 crops 4 columns and 4 rows.
PHYS = {"phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 8.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}
COLS, ROWS = 45, 39

THRESHOLDS = {"min_margin_dies": 1, "min_discriminating_dies": 1}

RULE = {"name": "asum_test_rule", "source_table": SRC,
        "derived_table": "asum_test_unit", "decision_key": ["eqp", "product"],
        "target_fields": ["core_frame", "dt_frame"]}

TABLES = {
    SRC: {"business_key": "cell_key",
          "column_types": {"cell_key": "string", "eqp": "string", "product": "string",
                           "job": "string", "x": "number", "y": "number",
                           "v": "string"},
          "map_key_columns": ["job"]},
    MAPT: {"business_key": "cell_key",
           "column_types": {"cell_key": "string", "job": "string",
                            "x": "number", "y": "number"},
           "map_key_columns": ["job"]},
    REFT: {"business_key": "cell_key",
           "column_types": {"cell_key": "string", "ref_id": "string",
                            "rx": "number", "ry": "number", "rv": "string"},
           "map_key_columns": ["ref_id"]},
    map_overlay.META_TABLE: {"business_key": "map_pk",
                             "composite_key_source": ["target_table", "map_id"],
                             "column_types": {"map_pk": "string",
                                              "target_table": "string",
                                              "map_id": "string",
                                              "grid_metadata": "string"}},
}

CFG = {"table_bindings": {
    SRC: {"columns": {"x": "x", "y": "y", "val": "v", "key_columns": ["job"]}},
    REFT: {"columns": {"x": "rx", "y": "ry", "val": "rv", "key_columns": ["ref_id"]}},
}, "alignment": THRESHOLDS}


def _meta(cols=COLS, rows=ROWS, start_x=1, start_y=1, y_invert=False, **kw):
    """🔴 The orientation axes are NAMED PARAMETERS on purpose. Passing them through `**kw`
    writes `start_x` instead of `grid_start_x`, the reader keeps its absent-default of 1, and
    the test then compares a meta against itself and reports "no effect" for the axis it was
    built to measure. That happened here on the first pass. The trailing assert makes a
    misspelled key loud instead of silently inert."""
    m = {"grid_cols": cols, "grid_rows": rows, "rotation": 0, "side": "front",
         "grid_y_invert": y_invert, "grid_start_x": start_x, "grid_start_y": start_y}
    m.update(PHYS)
    m.update(kw)
    assert not (set(kw) - set(m)), "unknown meta key: %s" % sorted(set(kw) - set(m))
    return m


def _auto_meta(**kw):
    """Exactly what `map_meta_registrar.synthesize_grid_meta` leaves behind: the six keys are
    present and well formed, and the marker says nobody measured them."""
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


def _place(src_meta, tgt_meta, cells):
    map_overlay._FRAME_TF_CACHE.clear()
    t = map_overlay.make_frame_transform(src_meta, tgt_meta)
    return [t(x, y) for (x, y) in cells]


def _moved(a, b):
    return sum(1 for p, q in zip(a, b) if p != q)


def _asymmetric_subset():
    """An occupied subset with NO dihedral symmetry. The circle is invariant under all eight
    frames (spec section 1), so a symmetric fixture makes every planted frame tie and the
    failure reads as a scorer bug when it is a fixture bug."""
    return [p for p in _cells_of(_meta()) if not (p[0] > 30 and p[1] < 12)]


# ---------------------------------------------------------------------------
# 1. the borrowed value is for the computation, and it is not a declaration
# ---------------------------------------------------------------------------

def test_the_borrowed_spec_never_becomes_a_declaration():
    """THE line this whole change must not cross. Writing the floor's pitch onto the source
    manufactures a declaration: afterwards it reads as a value somebody measured and nobody
    can tell it was assumed. The existing provenance vocabulary already separates measured
    from defaulted, and this has to land on the assumed side of that line."""
    floor, auto = _meta(), _auto_meta()
    borrowed = map_overlay.assume_phys_from(auto, floor, {"table": REFT, "map_id": "R1"})

    assert borrowed is not None
    assert map_overlay.geometry_declaration(borrowed) == map_overlay.GEOMETRY_ASSUMED
    assert map_overlay.geometry_declaration(borrowed) != map_overlay.GEOMETRY_DECLARED
    # it refuses the "is this a declaration" question and answers the "can I compute" one
    assert map_overlay.geometry_refusal(borrowed) is not None
    assert map_overlay.geometry_computable(borrowed) is None
    # and it says where the values came from, which is what makes the record answerable
    assert borrowed[map_overlay.PHYS_ASSUMED_KEY] == {"table": REFT, "map_id": "R1"}


def test_the_source_meta_is_not_touched_by_the_borrow():
    """A copy, not an edit. If the borrow mutated its input, the same dict is the one
    `declared_frame_of` reads and the one a later writer could persist."""
    auto = _auto_meta()
    before = json.dumps(auto, sort_keys=True)
    map_overlay.assume_phys_from(auto, _meta())
    assert json.dumps(auto, sort_keys=True) == before
    assert map_overlay.PHYS_ASSUMED_KEY not in auto
    assert map_overlay.geometry_declaration(auto) == map_overlay.GEOMETRY_AUTO_REGISTERED


def test_a_measured_spec_is_never_overwritten_by_a_borrowed_one():
    """The assumption fills an EMPTY seat. Letting it overwrite a declaration would be the
    same defect in the other direction - a measured value silently replaced by a guess."""
    floor = _meta(phys_chip_x=11.0, phys_chip_y=13.0)
    declared = _meta()
    assert map_overlay.assume_phys_from(declared, floor) is None


def test_an_assumption_is_never_stacked_on_an_assumption():
    """Borrowing from a floor that is itself not a declaration would chain guesses, and the
    chain would carry one token that says nothing about its depth."""
    auto = _auto_meta()
    assert map_overlay.assume_phys_from(auto, auto) is None
    assert map_overlay.assume_phys_from(auto, _auto_meta()) is None
    borrowed = map_overlay.assume_phys_from(auto, _meta())
    assert map_overlay.assume_phys_from(_auto_meta(), borrowed) is None


def test_the_borrow_changes_the_six_wafer_keys_and_nothing_else():
    """The exhaustive statement of what is assumable, asserted against the copy rather than
    argued in a comment. Found by mutation: borrowing the floor's `grid_start_x/y` on top of
    the wafer spec passed every other test in this file, and start is the axis being solved
    for - borrowing it writes the answer down and then asks whether the answer is right.

    A subset assertion rather than an equality one: a source whose spec happens to match the
    floor's has fewer differing keys, and that is not a defect."""
    floor = _meta(phys_wafer_dia=200.0, phys_chip_x=11.0, phys_chip_y=13.0,
                  phys_offset_x=2.0, phys_offset_y=3.0, phys_edge_margin=5.0,
                  start_x=9, start_y=9, y_invert=True, rotation=270, side="back",
                  cols=COLS, rows=ROWS)
    src = _auto_meta(start_x=4, start_y=7)
    borrowed = map_overlay.assume_phys_from(src, floor)

    allowed = set(map_overlay.PHYS_KEYS) | {map_overlay.PHYS_ASSUMED_KEY}
    changed = {k for k in set(src) | set(borrowed)
               if src.get(k) != borrowed.get(k)}
    assert changed <= allowed, "borrowed an axis that is not the wafer's: %s" % sorted(
        changed - allowed)
    # named one by one as well, so a future widening of PHYS_KEYS cannot quietly take them
    for axis in ("grid_start_x", "grid_start_y", "grid_y_invert", "rotation", "side",
                 "grid_cols", "grid_rows"):
        assert borrowed[axis] == src[axis], axis


def test_the_orientation_axes_keep_their_own_provenance_through_the_borrow():
    """Only the wafer spec is borrowed. The auto-registration marker still governs rotation,
    side, y-invert and start - those axes were not measured either, and the borrow does not
    make them measured."""
    borrowed = map_overlay.assume_phys_from(_auto_meta(), _meta())
    d = map_overlay.orientation_declaration(borrowed)
    assert {a: d[a]["source"] for a in ("rotation", "side", "grid_y_invert")} == {
        a: map_overlay.GEOMETRY_AUTO_REGISTERED
        for a in ("rotation", "side", "grid_y_invert")}


# ---------------------------------------------------------------------------
# 2. what is assumable - decided by measurement, not by argument
# ---------------------------------------------------------------------------

def test_borrowing_the_orientation_axes_would_move_every_cell():
    """MEASURED, not reasoned. Rotation, side, start and y-invert are the unknown being
    solved for; borrowing the floor's values writes the answer down and then asks whether the
    answer is right. The numbers below are what that would cost in placed cells.

    Rotation and side are excluded from the borrow for a second reason too: the candidate
    loop overwrites them per candidate, so borrowing them is invisible in the placement and
    would corrupt only the `declared_frame` badge - the quietest possible way to be wrong."""
    floor = _meta(start_x=1, start_y=1, y_invert=False)

    own_start = _meta(start_x=4, start_y=7)
    cells = _cells_of(own_start)
    kept = _place(source_meta_for_frame(own_start, "rot90_back"), floor, cells)
    lent = _place(source_meta_for_frame(_meta(start_x=1, start_y=1), "rot90_back"),
                  floor, cells)
    assert _moved(kept, lent) == len(cells), "start is not a wafer property"

    cells = _cells_of(_meta())
    kept = _place(source_meta_for_frame(_meta(y_invert=True), "rot90_back"), floor, cells)
    lent = _place(source_meta_for_frame(_meta(y_invert=False), "rot90_back"), floor, cells)
    assert _moved(kept, lent) > len(cells) * 0.9, "y-invert is not a wafer property"


def test_the_shared_wafer_spec_is_not_a_no_op_which_is_why_it_is_labelled():
    """The spec's section 9(a) note says a shared nominal pitch makes the mm round trip an
    identity on the die index. MEASURED: that holds only for the two candidates whose
    composition is the identity. For the other six the shared value moves hundreds of cells
    even after the per-candidate shift is solved - so the assumption has real content, and
    the label on it is not decoration."""
    import numpy as np
    floor = _meta()
    cells = _cells_of(floor)
    moved_by_candidate = {}
    for cand in ma.CANDIDATE_FRAMES:
        base = _place(source_meta_for_frame(_meta(), cand), floor, cells)
        other = _meta(phys_chip_x=11.0, phys_chip_y=13.0)
        got = _place(source_meta_for_frame(other, cand), other, cells)
        _dx, _dy, hit = ma._solve_shift(ma._encode(got),
                                        np.unique(ma._encode(base)), ma.SHIFT_WINDOW)
        moved_by_candidate[cand] = len(cells) - int(hit)

    unaffected = [f for f, n in moved_by_candidate.items() if n == 0]
    assert sorted(unaffected) == ["rot0_front", "rot270_back"], moved_by_candidate
    assert all(moved_by_candidate[f] > 0 for f in ma.CANDIDATE_FRAMES
               if f not in unaffected), moved_by_candidate


def test_grid_dims_derived_from_cells_are_a_lower_bound_not_a_value():
    """The question the ruling asked to check: can grid dims be honestly bounded from the
    source's own cells, and does that count as derived or as assumed?

    MEASURED: stored coordinates are bbox-relative, so their span equals the wafer crop, not
    the grid. The span is DERIVED (it borrows nothing) but it is a LOWER BOUND - it is tight
    only when the mask crops nothing. A bound can refuse a candidate; it can never satisfy
    one. That is why absent dims are named rather than invented."""
    for cols, rows, cx, cy in ((COLS, ROWS, 7, 8), (29, 25, 11, 13), (21, 19, 7, 8)):
        m = _meta(cols=cols, rows=rows, phys_chip_x=float(cx), phys_chip_y=float(cy))
        cs = _cells_of(m)
        span = (max(x for x, _ in cs) - min(x for x, _ in cs) + 1,
                max(y for _, y in cs) - min(y for _, y in cs) + 1)
        assert span[0] <= cols and span[1] <= rows, "a span can never exceed the grid"
    # and it is strictly under on the shape this repository actually runs
    m = _meta()
    cs = _cells_of(m)
    assert max(x for x, _ in cs) - min(x for x, _ in cs) + 1 < COLS


def test_grid_dims_are_not_borrowed_and_their_absence_is_named():
    """Two maps of one wafer can crop differently, so dims are a property of the MAP. When
    they are missing the answer is to say what is needed, not to invent them."""
    no_dims = {k: v for k, v in _auto_meta().items() if k != "grid_cols"}
    assert map_overlay.assume_phys_from(no_dims, _meta()) is None

    ref = _asymmetric_subset()
    _c, excluded, _r, _s = ma.score_candidates(
        [{"map_id": "NODIM", "meta": no_dims, "cells": ref}], ref, _meta(),
        assume_reference_geometry=True)
    rows = excluded.as_list()
    assert [r["reason_code"] for r in rows] == [ma.EXCLUDE_GRID_DIMS_MISSING]
    assert rows[0]["reason"] and "격자" in rows[0]["reason"]


def test_a_map_cropped_differently_from_the_floor_is_excluded_alone_not_the_whole_unit():
    """The dims check used to live inside the candidate loop, where one mismatched map killed
    all eight candidates and the unit lost its answer entirely. The assumption opens a
    population whose dims come from a bbox scan, so this path gets walked far more often -
    a map that does not fit must take itself out, not the unit."""
    ref = _asymmetric_subset()
    floor = _meta()
    good = _place(source_meta_for_frame(floor, "rot0_front"),
                  source_meta_for_frame(floor, "rot90_back"), ref)
    cands, excluded, ruling, stats = ma.score_candidates(
        [{"map_id": "FITS", "meta": _meta(), "cells": good},
         {"map_id": "CROPPED", "meta": _meta(cols=25, rows=19), "cells": ref}],
        ref, floor, thresholds=THRESHOLDS)

    assert [r["reason_code"] for r in excluded.as_list()] == [ma.EXCLUDE_GRID_DIMS_DIFFER]
    assert stats["source_maps_usable"] == 1
    assert ruling["winner"] == "rot90_back", "the fitting map still gets its answer"


# ---------------------------------------------------------------------------
# 3. the unlock actually works - the load-bearing assertion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("planted", ma.CANDIDATE_FRAMES)
def test_a_planted_frame_is_recovered_under_the_assumption(planted):
    """Re-express the floor in a KNOWN frame, strip the source's geometry to exactly what the
    registrar leaves behind, and require the scorer to name that frame back. This runs the
    real `make_frame_transform` / `_frame_phys_params` stack on purpose: an unlock that let
    the population through and scored it on synthetic 1x1 pitch would pass every labelling
    test in this file and fail this one."""
    ref = _asymmetric_subset()
    floor = _meta()
    src_cells = _place(source_meta_for_frame(floor, "rot0_front"),
                       source_meta_for_frame(floor, planted), ref)

    blocked = ma.score_candidates(
        [{"map_id": "M", "meta": _auto_meta(), "cells": src_cells}], ref, floor,
        thresholds=THRESHOLDS)[2]
    assert blocked["winner"] is None, "without the assumption this population is a dead end"

    cands, excluded, ruling, stats = ma.score_candidates(
        [{"map_id": "M", "meta": _auto_meta(), "cells": src_cells}], ref, floor,
        thresholds=THRESHOLDS, assume_reference_geometry=True,
        reference_ref={"table": REFT, "map_id": "R1"})
    assert ruling["winner"] == planted
    assert excluded.total() == 0
    assert stats["assumed_map_ids"] == ["M"]


def test_the_verdict_itself_carries_the_assumption_not_only_a_field_beside_it():
    """A verdict reached under an assumption is a different fact from one reached on declared
    geometry. Carrying it only in a sibling field means every place that copies the ruling -
    the confirmation record, the worklist - drops it."""
    ref = _asymmetric_subset()
    floor = _meta()
    src = _place(source_meta_for_frame(floor, "rot0_front"),
                 source_meta_for_frame(floor, "rot90_back"), ref)

    on_declared = ma.score_candidates(
        [{"map_id": "M", "meta": _meta(), "cells": src}], ref, floor,
        thresholds=THRESHOLDS)[2]
    assert on_declared["geometry_assumed"] is False
    assert on_declared["assumed_map_count"] == 0

    on_assumed = ma.score_candidates(
        [{"map_id": "M", "meta": _auto_meta(), "cells": src}], ref, floor,
        thresholds=THRESHOLDS, assume_reference_geometry=True)[2]
    assert on_assumed["winner"] == on_declared["winner"], "same answer"
    assert on_assumed["geometry_assumed"] is True, "different fact"
    assert on_assumed["assumed_map_count"] == 1


def test_the_assumption_is_a_claim_the_operator_makes_not_a_default():
    """Applying it automatically would put every verdict on ground nobody claimed."""
    ref = _asymmetric_subset()
    _c, excluded, ruling, stats = ma.score_candidates(
        [{"map_id": "M", "meta": _auto_meta(), "cells": ref}], ref, _meta(),
        thresholds=THRESHOLDS)
    assert ruling["geometry_assumed"] is False
    assert stats["assumed_map_ids"] == []
    # but the offer is counted even when it was not taken - otherwise the screen has no
    # way to show one
    assert stats["assumable_map_ids"] == ["M"]
    assert [r["reason_code"] for r in excluded.as_list()] == [ma.EXCLUDE_GEOMETRY_REFUSED]


def test_no_offer_is_made_when_the_floor_itself_has_no_declared_geometry():
    ref = _asymmetric_subset()
    _c, _e, ruling, stats = ma.score_candidates(
        [{"map_id": "M", "meta": _auto_meta(), "cells": ref}], ref, _auto_meta(),
        thresholds=THRESHOLDS, assume_reference_geometry=True)
    assert stats["assumable_map_ids"] == [] and stats["assumed_map_ids"] == []
    assert ruling["geometry_assumed"] is False


# ---------------------------------------------------------------------------
# 4. the payload says so - and an excluded map becomes an offer, not a dead end
# ---------------------------------------------------------------------------

@pytest.fixture()
def env(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    map_overlay._FRAME_TF_CACHE.clear()
    return db_session


def _seed(db, src_meta, planted="rot90_back"):
    s = models.DYNAMIC_TABLES[SRC]
    r = models.DYNAMIC_TABLES[REFT]
    mm = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    ref = _asymmetric_subset()
    floor = _meta()
    src_cells = _place(source_meta_for_frame(floor, "rot0_front"),
                       source_meta_for_frame(floor, planted), ref)
    for i, (x, y) in enumerate(src_cells):
        db.add(s(row_id="s%d" % i, business_key_val="s%d" % i, cell_key="s%d" % i,
                 eqp="E1", product="P1", job="J1", x=x, y=y, v="1"))
    for i, (x, y) in enumerate(ref):
        db.add(r(row_id="r%d" % i, business_key_val="r%d" % i, cell_key="r%d" % i,
                 ref_id="R1", rx=x, ry=y, rv="1"))
    db.add(mm(row_id="m1", business_key_val="%s|J1" % MAPT, target_table=MAPT,
              map_id="J1", grid_metadata=json.dumps(src_meta)))
    db.add(mm(row_id="mr", business_key_val="%s|R1" % REFT, target_table=REFT,
              map_id="R1", grid_metadata=json.dumps(floor)))
    db.commit()


def _view(db, **kw):
    return ma.build_alignment_view(db, CFG, RULE, {"eqp": "E1", "product": "P1"},
                                   MAPT, reference_spec="%s:R1" % REFT,
                                   include_cells=False, **kw)


def test_a_map_excluded_for_missing_geometry_becomes_an_offer_not_a_dead_end(env):
    """The screen used to show nothing for this case. An unmeasured map is now a proposal
    the operator can accept, and the proposal names the floor it would borrow from - the
    sentence is composed server-side, as every other refusal in this module is."""
    _seed(env, _auto_meta())
    v = _view(env)
    a = v["assumption"]
    assert a["state"] == ma.ASSUMPTION_AVAILABLE
    assert a["requested"] is False
    assert a["map_ids"] == ["J1"] and a["map_count"] == 1
    assert a["basis"] == {"table": REFT, "map_id": "R1"}
    assert a["text"] and REFT in a["text"] and "\n" not in a["text"]
    assert v["ruling"]["geometry_assumed"] is False


def test_taking_the_offer_scores_the_unit_and_the_payload_labels_every_layer(env):
    _seed(env, _auto_meta())
    v = _view(env, assume_reference_geometry=True)

    assert v["state"] == ma.STATE_SCORED
    assert v["ruling"]["winner"] == "rot90_back"
    assert v["ruling"]["geometry_assumed"] is True
    assert v["assumption"]["state"] == ma.ASSUMPTION_APPLIED
    assert v["assumption"]["requested"] is True

    m = v["sources"]["maps"][0]
    # what the map says about itself, and what this run actually stood on - two facts
    assert m["geometry"] == map_overlay.GEOMETRY_AUTO_REGISTERED
    assert m["geometry_basis"] == map_overlay.GEOMETRY_ASSUMED
    # the declaration badge is NOT contaminated by the borrow
    assert m["declared_frame_source"] == map_overlay.GEOMETRY_AUTO_REGISTERED


def test_a_declared_map_reports_no_assumption_at_all(env):
    _seed(env, _meta())
    v = _view(env, assume_reference_geometry=True)
    assert v["assumption"]["state"] == ma.ASSUMPTION_UNAVAILABLE
    assert v["assumption"]["basis"] is None and v["assumption"]["text"] is None
    assert v["ruling"]["geometry_assumed"] is False
    assert v["sources"]["maps"][0]["geometry_basis"] == map_overlay.GEOMETRY_DECLARED


def test_the_stored_meta_is_byte_identical_after_a_run_under_the_assumption(env):
    """The one assertion that would notice a borrow leaking into the database. It reads the
    row back rather than the dict the scorer was handed."""
    _seed(env, _auto_meta())
    mm = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    before = env.query(mm).filter_by(map_id="J1").first().grid_metadata

    _view(env, assume_reference_geometry=True)
    env.expire_all()
    after = env.query(mm).filter_by(map_id="J1").first().grid_metadata

    assert after == before
    stored = json.loads(after)
    assert stored["phys_chip_x"] == 1 and stored["phys_chip_y"] == 1
    assert map_overlay.PHYS_ASSUMED_KEY not in stored
    assert map_overlay.geometry_declaration(stored) != map_overlay.GEOMETRY_DECLARED


# ---------------------------------------------------------------------------
# 5. the confirmation record answers "which decisions rested on it"
# ---------------------------------------------------------------------------

def _contrib(map_id, table=MAPT, **kw):
    d = {"role": "defect", "source_table": table, "map_id": map_id,
         "source_name": "user", "applied_frame": "rot90_back", "shift_dx": 0,
         "shift_dy": 0}
    d.update(kw)
    return d


def test_the_confirmation_records_which_sources_stood_on_a_borrowed_spec(env):
    """The reason this is on the record at all: when the assumption is later shown false,
    someone asks which decisions rested on it. Without this the answer is a guess."""
    _seed(env, _auto_meta())
    h = fc.record_confirmation(env, RULE, {"eqp": "E1", "product": "P1"},
                               [_contrib("J1")], confirmed_by="tester",
                               frames={"dt_frame": "rot90_back"})
    env.refresh(h)
    assert h.geometry_assumed is True

    row = (env.query(models.FrameConfirmationSource)
           .filter_by(confirmation_uid=h.confirmation_uid).one())
    assert row.geometry_basis == map_overlay.GEOMETRY_ASSUMED

    payload = fc.as_payload(env, h)
    assert payload["ruling"]["geometry_assumed"] is True
    assert payload["sources"][0]["geometry_basis"] == map_overlay.GEOMETRY_ASSUMED


def test_a_confirmation_on_declared_geometry_is_marked_as_such_not_left_null(env):
    _seed(env, _meta())
    h = fc.record_confirmation(env, RULE, {"eqp": "E1", "product": "P2"},
                               [_contrib("J1")], confirmed_by="tester")
    env.refresh(h)
    assert h.geometry_assumed is False
    row = (env.query(models.FrameConfirmationSource)
           .filter_by(confirmation_uid=h.confirmation_uid).one())
    assert row.geometry_basis == map_overlay.GEOMETRY_DECLARED


def test_an_excluded_source_is_not_recorded_as_having_stood_on_an_assumption(env):
    """An excluded source was aligned onto nothing. Calling its basis `assumed` would attach
    a ground to something that never happened, and would inflate the answer to the question
    this column exists to answer."""
    _seed(env, _auto_meta())
    h = fc.record_confirmation(
        env, RULE, {"eqp": "E1", "product": "P3"},
        [_contrib("J1", excluded_reason=ma.EXCLUDE_GEOMETRY_REFUSED)],
        confirmed_by="tester")
    env.refresh(h)
    row = (env.query(models.FrameConfirmationSource)
           .filter_by(confirmation_uid=h.confirmation_uid).one())
    assert row.geometry_basis == map_overlay.GEOMETRY_AUTO_REGISTERED
    assert h.geometry_assumed is False


def test_the_write_path_derives_the_basis_rather_than_trusting_the_request(env):
    """One spelling. If the client supplied this, an old client would silently drop the very
    fact the record exists to keep - and a wrong client could assert the opposite."""
    _seed(env, _auto_meta())
    h = fc.record_confirmation(
        env, RULE, {"eqp": "E1", "product": "P4"},
        # the request insists the source stood on a declaration. it did not.
        [_contrib("J1", geometry_basis=map_overlay.GEOMETRY_DECLARED)],
        confirmed_by="tester")
    env.refresh(h)
    row = (env.query(models.FrameConfirmationSource)
           .filter_by(confirmation_uid=h.confirmation_uid).one())
    assert row.geometry_basis == map_overlay.GEOMETRY_ASSUMED
    assert h.geometry_assumed is True


def test_the_assumed_token_has_one_spelling_across_the_layers():
    """`frame_confirmation` names the token locally to roll the header up without an import
    cycle. The day the two strings differ, every confirmation is written with the wrong
    flag and nothing raises."""
    assert fc._ASSUMED == map_overlay.GEOMETRY_ASSUMED
    assert ma.geometry_basis_of(_auto_meta(), None) == map_overlay.GEOMETRY_ASSUMED


def test_the_geometry_vocabulary_is_closed():
    assert {map_overlay.GEOMETRY_DECLARED, map_overlay.GEOMETRY_AUTO_REGISTERED,
            map_overlay.GEOMETRY_ABSENT, map_overlay.GEOMETRY_UNPARSABLE,
            map_overlay.GEOMETRY_ASSUMED} == {
        "declared", "auto_registered", "absent", "unparsable", "assumed"}
    assert {ma.ASSUMPTION_APPLIED, ma.ASSUMPTION_AVAILABLE,
            ma.ASSUMPTION_UNAVAILABLE} == {"applied", "available", "unavailable"}
