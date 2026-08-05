"""The alignment scorer: 8 candidates in one pass, counts only, and refusals that name a cause.

WHY THE PLANTED-WINNER TEST IS THE LOAD-BEARING ONE
`test_the_planted_frame_wins` builds a reference, re-expresses it in a KNOWN frame, and requires
the scorer to name that frame back. Everything else here is a property test; that one is the only
assertion that would notice the scorer ranking on the wrong axis. It runs through the real
`make_frame_transform` / `_frame_phys_params` stack on purpose - a scorer that composed its own
rotation math would pass every other test in this file.
"""
import pytest

import map_alignment as ma
import map_overlay
from dt_map_derivation import parse_frame, source_meta_for_frame


PHYS = {"phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}

# Declared for the tests that want a ranked winner. Deliberately NOT a module default in the
# scorer: a threshold invented in code is a plausible default impersonating a declaration
# (I4), and here that impersonation turns "we cannot tell" into a confident answer.
THRESHOLDS = {"min_margin_dies": 1, "min_discriminating_dies": 1}


def _meta(rotation=0, side="front", cols=13, rows=13, start_x=1, start_y=1):
    return {"grid_cols": cols, "grid_rows": rows, "rotation": rotation, "side": side,
            "grid_y_invert": False, "grid_start_x": start_x, "grid_start_y": start_y, **PHYS}


def _auto_meta(**kw):
    m = _meta(**kw)
    m.update({"phys_chip_x": 1, "phys_chip_y": 1, "phys_offset_x": 0, "phys_offset_y": 0,
              "phys_edge_margin": 3, "phys_wafer_dia": 300, "auto_registered": True})
    return m


# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------

def test_the_eight_candidates_are_exactly_what_the_existing_acceptor_accepts():
    """The frame vocabulary has ONE spelling. Listing 8 literals here would be the second."""
    assert len(ma.CANDIDATE_FRAMES) == 8
    assert len(set(ma.CANDIDATE_FRAMES)) == 8
    for f in ma.CANDIDATE_FRAMES:
        assert parse_frame(f) is not None, f
    assert {parse_frame(f) for f in ma.CANDIDATE_FRAMES} == {
        (r, s) for r in (0, 90, 180, 270) for s in ("front", "back")}


def test_frame_text_is_the_inverse_of_parse_frame():
    for f in ma.CANDIDATE_FRAMES:
        rot, side = parse_frame(f)
        assert ma.frame_text(rot, side) == f


def test_grid_y_invert_is_not_a_candidate_axis():
    """Spec section 2: on the production path the 16 tuples collapse to 8, so inverting y is an
    alias rather than a ninth/sixteenth candidate. A scorer that enumerated it would double the
    list and report ties that are not ties."""
    assert len(ma.CANDIDATE_FRAMES) == 8
    assert not any("inv" in f for f in ma.CANDIDATE_FRAMES)


# ---------------------------------------------------------------------------
# the scorer, end to end through the real transform stack
# ---------------------------------------------------------------------------

def _ref_cells():
    """An occupied subset with NO symmetry in the dihedral group - the only kind that can break
    a tie at all (spec section 1: the circle is invariant under all 8 frames, so only the
    occupied subset carries information).

    🔴 Getting this wrong is easy and silent. The first version of this fixture clipped
    {(3,3), (3,4), (4,3)}, which is symmetric under transpose - and transpose IS one of the
    eight frames. The scorer then correctly reported a two-way tie on every planted frame, and
    the test read as a scorer bug when it was a fixture bug.
    `test_the_fixture_has_no_symmetry` scores the fixture so that cannot recur.
    """
    cells = {(x, y) for x in range(3, 10) for y in range(3, 10) if x + y <= 15}
    cells -= {(3, 3), (3, 4), (5, 3)}          # asymmetric under transpose AND under reflection
    cells.add((9, 9))
    return sorted(cells)


def _dihedral_images(cells):
    """The 8 images of a cell set under the dihedral group, normalised to the origin."""
    def norm(s):
        mx, my = min(p[0] for p in s), min(p[1] for p in s)
        return frozenset((x - mx, y - my) for (x, y) in s)
    out = []
    cur = set(cells)
    for _ in range(4):
        cur = {(-y, x) for (x, y) in cur}
        out.append(norm(cur))
        out.append(norm({(-x, y) for (x, y) in cur}))
    return out


def test_the_fixture_has_no_symmetry():
    """If the reference set maps onto itself under any non-identity frame, no scorer can name a
    winner and a planted-winner test would be asserting something false. Score the fixture."""
    base = _ref_cells()
    images = _dihedral_images(base)
    assert len(set(images)) == 8, (
        "the fixture is invariant under %d of the 8 frames - it cannot distinguish them"
        % (8 - len(set(images)) + 1))


@pytest.mark.parametrize("planted", ["rot90_front", "rot180_front", "rot270_front",
                                     "rot0_back"])
def test_the_planted_frame_wins(planted):
    """Express the reference in a known frame, then require the scorer to name that frame.

    The source cells are produced by the SAME primitive the scorer uses in the opposite
    direction, so this is a round trip through `_frame_phys_params`, not a re-derivation of it.
    """
    ref_meta = _meta()
    ref = _ref_cells()

    # Put the reference into `planted`'s frame - that is what the equipment would have recorded.
    fwd = map_overlay.make_frame_transform(ref_meta, source_meta_for_frame(ref_meta, planted))
    recorded = [fwd(x, y) for (x, y) in ref]

    # Thresholds are PASSED IN. There is no default in the scorer, so a test that wants a
    # ranked winner has to declare what "far enough ahead" means - which is the same demand
    # the route makes of server config.
    cands, excluded, ruling, stats = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": recorded}], ref, ref_meta,
        thresholds=THRESHOLDS)

    assert ruling["winner"] == planted, (
        "planted %s, scorer said %s; agreements=%s"
        % (planted, ruling["winner"], {c["frame"]: c["agreement"] for c in cands}))
    assert ruling["margin"] >= 1
    assert excluded.total() == 0
    top = next(c for c in cands if c["frame"] == planted)
    assert top["agreement"] == len(ref)
    assert top["discriminating"] > 0, "a win with no discriminating cell is not a win"


def test_all_eight_are_scored_in_one_call():
    """The hard requirement: candidate switching must be a client repaint, so every candidate is
    scored in the SAME pass. A payload carrying fewer than 8 forces a fetch per candidate."""
    ref_meta = _meta()
    ref = _ref_cells()
    cands, _e, _r, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": ref}], ref, ref_meta)
    assert [c["frame"] for c in cands] == list(ma.CANDIDATE_FRAMES)
    assert all(c["state"] == ma.STATE_SCORED for c in cands)
    assert all(c["shift"] is not None for c in cands)


def test_every_metric_is_an_integer_count_and_never_a_ratio():
    """Spec section 3: a coverage percentage inverted the ranking when measured. The guard is
    structural - no float metric may appear on a candidate at all."""
    ref_meta = _meta()
    ref = _ref_cells()
    cands, _e, _r, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": ref}], ref, ref_meta)
    for c in cands:
        for key in ("agreement", "discriminating", "placed", "margin"):
            assert isinstance(c[key], int), (c["frame"], key, type(c[key]))
        assert not any(isinstance(v, float) for v in c.values()), c
        assert not any("pct" in k or "percent" in k or "ratio" in k for k in c)


def test_a_tie_is_reported_as_a_tie_and_not_broken():
    """A fully symmetric occupied set cannot distinguish frames. Naming a winner there is the
    forced first place the spec forbids."""
    ref_meta = _meta()
    ref = sorted({(x, y) for x in range(4, 9) for y in range(4, 9)})   # square: symmetric
    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": ref}], ref, ref_meta)
    assert ruling["winner"] is None
    assert ruling["reason_code"] in ("tie", "no_discrimination")
    assert max(c["agreement"] for c in cands) > 0, (
        "the point is that agreement is HIGH and still nobody wins")


def test_high_agreement_with_zero_discrimination_never_wins():
    """Spec section 1, stated as an assertion: agreement earned only on cells where every
    candidate answers the same way excludes nothing."""
    ruling = ma._rule_on([
        {"frame": "rot0_front", "state": ma.STATE_SCORED, "agreement": 900,
         "discriminating": 0, "margin": 900},
        {"frame": "rot90_front", "state": ma.STATE_SCORED, "agreement": 0,
         "discriminating": 0, "margin": -900},
    ])
    assert ruling["winner"] is None
    assert ruling["reason_code"] == "no_discrimination"


# ---------------------------------------------------------------------------
# the premise: a full meta per candidate, not one bbox with 8 transforms on top
# ---------------------------------------------------------------------------

def test_each_candidate_gets_its_own_full_meta_through_the_transform_stack(monkeypatch):
    """Spec section 2's premise. If the scorer built one transform and post-composed rotations,
    `make_frame_transform` would be called once, and `CORE_YINV` would be off by (2,-1)."""
    seen = []
    real = map_overlay.make_frame_transform

    def spy(src, tgt):
        seen.append((map_overlay._rotation_of(src), map_overlay._side_of(src)))
        return real(src, tgt)

    monkeypatch.setattr(map_overlay, "make_frame_transform", spy)
    ref_meta = _meta()
    ref = _ref_cells()
    ma.score_candidates([{"map_id": "M1", "meta": ref_meta, "cells": ref}], ref, ref_meta)
    assert set(seen) == {(r, s) for r in (0, 90, 180, 270) for s in ("front", "back")}, (
        "every candidate must go through the transform builder with its OWN rotation/side")


def test_scoring_does_not_invent_a_bounding_box_basis(monkeypatch):
    """`frame_axes` is the key of `_FRAME_TF_CACHE` and does NOT carry the bbox basis, so a
    module that varied the basis would hand the next caller the previous caller's box. This
    scorer must only ever key on metas it was given."""
    ref_meta = _meta()
    ref = _ref_cells()
    map_overlay._FRAME_TF_CACHE.clear()
    ma.score_candidates([{"map_id": "M1", "meta": ref_meta, "cells": ref}], ref, ref_meta)
    expected = {map_overlay.frame_axes(source_meta_for_frame(ref_meta, f))
                for f in ma.CANDIDATE_FRAMES} | {map_overlay.frame_axes(ref_meta)}
    assert set(map_overlay._FRAME_TF_CACHE) <= expected, (
        "a cache key appeared that is not one of the metas we passed in")


# ---------------------------------------------------------------------------
# nothing scored vs nothing discriminating - the distinction that was missing
# ---------------------------------------------------------------------------
# 🔴 THE MEASURED FAILURE (product owner, 2026-08-05). One source map, chip spec undeclared,
#    so `geometry_refusal` excluded it and NO cell reached the scorer. The eight candidates
#    each placed an empty array, each scored zero agreement, and `_rule_on` read those eight
#    zeros as an eight-way TIE. The screen said 동점 while `1 of 1 excluded` sat beside it in
#    the same response, and the operator went to swap the reference when the repair was to
#    declare the geometry.
#
#    Zero candidates scoring zero is not eight candidates scoring equally. These tests assert
#    the four facts apart, because each names a different repair.

def _refused_map(map_id="M1"):
    """A source map whose grid spec is auto-registered: the same refusal the live case hit."""
    return {"map_id": map_id, "meta": _auto_meta(), "cells": _ref_cells()}


def test_a_run_where_no_cell_reached_the_scorer_is_not_a_tie():
    """THE REGRESSION. The reference resolves, the only source map is excluded, and the answer
    must say that nothing was scored - never that the candidates were level."""
    cands, excluded, ruling, stats = ma.score_candidates(
        [_refused_map()], _ref_cells(), _meta(), thresholds=THRESHOLDS)
    assert ruling["reason_code"] == ma.RULING_NO_CELLS_SCORED
    assert ruling["reason_code"] != ma.RULING_TIE
    assert "tied" not in ruling, "a run that scored nothing has nobody to tie with"
    assert ruling["winner"] is None and ruling["margin"] is None
    # and no candidate claims to have been scored
    assert {c["state"] for c in cands} == {ma.STATE_NOT_SCORABLE}
    assert all(c["placed"] == 0 and c["shift"] is None and c["margin"] is None for c in cands)
    assert excluded.total() == 1 and stats["placed_cells"] == 0


def test_eight_candidates_agreeing_on_nothing_is_not_a_tie_either():
    """The same misreading as the zero-cell case, one step along: here cells WERE placed, and
    not one of them landed on the reference. Eight zeros again - and eight zeros again used to
    be read as an eight-way tie, which claims the evidence was real and level. The operator's
    repair is a third one: the floor, the coordinate columns, or the shift window is wrong.
    """
    ref_meta, ref = _meta(), _ref_cells()
    far = [(x + 100, y + 100) for (x, y) in ref]      # outside any shift the scorer will try
    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": far}], ref, ref_meta,
        thresholds=THRESHOLDS)
    assert all(c["placed"] > 0 for c in cands), "the point is that cells DID reach the scorer"
    assert all(c["agreement"] == 0 for c in cands)
    assert ruling["reason_code"] == ma.RULING_NO_OVERLAP
    assert ruling["reason_code"] not in (ma.RULING_TIE, ma.RULING_NO_CELLS_SCORED)
    assert ruling["placed_cells"] > 0, "and the verdict says so, beside the reason"


def test_the_verdict_carries_the_exclusion_count_and_its_reason():
    """A verdict that contradicts a fact sitting beside it is worse than one that says less.
    The exclusion tally was in the response and the ruling said something else."""
    _e, excluded, ruling, _s = ma.score_candidates(
        [_refused_map("M1"), _refused_map("M2")], _ref_cells(), _meta(), thresholds=THRESHOLDS)
    assert ruling["source_map_count"] == 2
    assert ruling["excluded_map_count"] == 2 == excluded.total()
    assert ruling["excluded_reason_code"] == ma.EXCLUDE_GEOMETRY_REFUSED
    assert ruling["placed_cells"] == 0


def test_the_nothing_scored_sentence_names_what_to_declare():
    """The sentence IS the instruction. It has to carry the count that was only in the console
    AND the word for the thing the operator must declare."""
    _c, excluded, ruling, _s = ma.score_candidates(
        [_refused_map()], _ref_cells(), _meta(), thresholds=THRESHOLDS)
    why = ma.compose_refusal(ma.STATE_NOT_SCORABLE, {"state": ma.REFERENCE_RESOLVED},
                             excluded, ruling, 1)
    assert "동점" not in why, why
    assert "1개 중 1개 제외" in why, why
    # the repair, named: the excluded reason label already says WHICH declaration is missing
    assert ma._EXCLUDE_TEXT[ma.EXCLUDE_GEOMETRY_REFUSED] in why, why
    assert "\n" not in why


def test_nothing_scored_and_nothing_discriminating_are_different_reasons_and_sentences():
    """Three facts, three repairs: declare the geometry / plug in a better reference / relax
    the floor. One shared word would send two thirds of the operators to the wrong place."""
    ref_meta, ref = _meta(), _ref_cells()
    nothing = ma.score_candidates([_refused_map()], ref, ref_meta, thresholds=THRESHOLDS)[2]
    blind = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta,
          "cells": _plant(ref_meta, _symmetric_ref(), "rot90_front")}],
        _symmetric_ref(), ref_meta, thresholds=THRESHOLDS)[2]
    tight = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": _plant(ref_meta, ref, "rot90_front")}],
        ref, ref_meta, thresholds={"min_margin_dies": 10_000,
                                   "min_discriminating_dies": 1})[2]
    codes = [nothing["reason_code"], blind["reason_code"], tight["reason_code"]]
    assert codes == [ma.RULING_NO_CELLS_SCORED, ma.RULING_NO_DISCRIMINATION,
                     "margin_too_small"]
    assert len({ma._ruling_text(r) for r in (nothing, blind, tight)}) == 3


def test_the_scored_and_separable_case_still_reaches_the_thresholds():
    """The floor must stay reachable: a run with real, separating evidence is ranked, so the
    new structural checks did not swallow the ordinary path."""
    ref_meta, ref = _meta(), _ref_cells()
    ruling = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": _plant(ref_meta, ref, "rot90_front")}],
        ref, ref_meta, thresholds=THRESHOLDS)[2]
    assert ruling["winner"] == "rot90_front"
    assert ruling["discriminating"] > 0 and ruling["margin"] >= 1


def test_a_margin_is_never_measured_against_a_candidate_that_was_not_scored(monkeypatch):
    """The same class one level down: a refused candidate's `agreement: 0` is a placeholder,
    not a score. Ranking against it lets a lone survivor report its ENTIRE agreement as a gap,
    and a fabricated gap of 800 dies clears any declared floor.

    🔴 THE SCORER'S OWN RUNNER-UP CODE HAS TO RUN. Asserting this by handing `_rule_on` a
       list built here would leave the loop that picks the runner-up unexecuted, and a test
       that never runs the changed line proves nothing. So seven of the eight transforms are
       made to refuse and the real `score_candidates` does the picking.
    """
    real = map_overlay.make_frame_transform
    survivor = "rot0_front"

    def only_one_frame(src, tgt):
        if (map_overlay._rotation_of(src), map_overlay._side_of(src)) != parse_frame(survivor):
            raise ValueError("refused by the fixture")
        return real(src, tgt)

    monkeypatch.setattr(map_overlay, "make_frame_transform", only_one_frame)
    ref_meta, ref = _meta(), _ref_cells()
    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": ref}], ref, ref_meta,
        thresholds={"min_margin_dies": 1, "min_discriminating_dies": 1})

    top = next(c for c in cands if c["frame"] == survivor)
    assert top["state"] == ma.STATE_SCORED and top["agreement"] > 0
    assert sum(1 for c in cands if c["state"] == ma.STATE_SCORED) == 1
    assert top["margin"] is None, (
        "the only scored candidate has no runner-up, so its margin is unmeasured - reporting "
        "%s means it was ranked against a candidate that never scored" % top["margin"])
    assert ruling["winner"] is None
    assert ruling["reason_code"] in (ma.RULING_NO_DISCRIMINATION, "margin_too_small")


# ---------------------------------------------------------------------------
# refusals - first-class states with a cause, never zeros
# ---------------------------------------------------------------------------

def test_absent_reference_is_its_own_state_with_a_sentence_and_no_candidate_list():
    """Measured: this is the COMMON case, not the edge. A client must not be able to render it
    as 'scored zero' - so there is no candidate list to render."""
    ref = {"state": ma.REFERENCE_ABSENT, "reason": None}
    why = ma.compose_refusal(ma.STATE_NOT_SCORABLE, ref, ma._Excluded(), {}, 40)
    assert why and isinstance(why, str)
    assert "기준" in why


def test_every_not_scorable_cause_gets_a_different_sentence():
    """Four different repairs must not share one sentence - the sentence IS the instruction."""
    e_geom = ma._Excluded()
    e_geom.add(ma.EXCLUDE_GEOMETRY_REFUSED, "M1", "물리 규격이 자동 등록된 합성값입니다")
    sentences = {
        "absent": ma.compose_refusal(ma.STATE_NOT_SCORABLE,
                                     {"state": ma.REFERENCE_ABSENT}, ma._Excluded(), {}, 40),
        "refused": ma.compose_refusal(ma.STATE_NOT_SCORABLE,
                                      {"state": ma.REFERENCE_REFUSED, "reason": "없는 맵"},
                                      ma._Excluded(), {}, 40),
        "all_excluded": ma.compose_refusal(ma.STATE_NOT_SCORABLE,
                                           {"state": ma.REFERENCE_RESOLVED}, e_geom, {}, 40),
        "no_maps": ma.compose_refusal(ma.STATE_NOT_SCORABLE,
                                      {"state": ma.REFERENCE_RESOLVED}, ma._Excluded(), {}, 0),
    }
    assert len(set(sentences.values())) == 4, sentences


def test_a_transform_that_refuses_every_candidate_says_so_rather_than_blaming_the_data():
    """Found by exercising the real endpoint: reference and sources both present, but their grid
    specs differ, so all 8 candidates refuse. Answering 'there are no coordinates to score' sends
    the operator to inspect data that is fine."""
    cands = [{"frame": "rot0_front", "reason": "physical grid dims differ: 13x13 vs 23x23"}]
    why = ma.compose_refusal(ma.STATE_NOT_SCORABLE, {"state": ma.REFERENCE_RESOLVED},
                             ma._Excluded(), {}, 40, cands)
    assert "13x13" in why and "23x23" in why
    assert "좌표가 없습니다" not in why


def test_auto_registered_source_maps_are_excluded_with_a_named_reason_not_silently():
    ref_meta = _meta()
    ref = _ref_cells()
    cands, excluded, _r, stats = ma.score_candidates(
        [{"map_id": "GOOD", "meta": ref_meta, "cells": ref},
         {"map_id": "AUTO", "meta": _auto_meta(), "cells": ref}], ref, ref_meta)
    rows = excluded.as_list()
    assert excluded.total() == 1
    assert rows[0]["reason_code"] == ma.EXCLUDE_GEOMETRY_REFUSED
    assert rows[0]["count"] == 1
    assert rows[0]["reason"], "an excluded count with no reason names no repair"
    assert stats["source_maps_usable"] == 1


def test_exclusions_are_aggregated_by_reason_not_emitted_per_row():
    e = ma._Excluded()
    for i in range(37):
        e.add(ma.EXCLUDE_META_MISSING, "M%d" % i)
    rows = e.as_list()
    assert len(rows) == 1 and rows[0]["count"] == 37
    assert e.total() == 37


def test_scored_state_has_no_refusal_sentence():
    assert ma.compose_refusal(ma.STATE_SCORED, {"state": ma.REFERENCE_RESOLVED},
                              ma._Excluded(), {"winner": "rot0_front"}, 1) is None


def test_the_state_vocabulary_is_closed():
    assert {ma.STATE_SCORED, ma.STATE_NO_WINNER, ma.STATE_NOT_SCORABLE,
            ma.STATE_COMPUTING} == {"scored", "no_winner", "not_scorable", "computing"}
    assert {ma.REFERENCE_RESOLVED, ma.REFERENCE_ABSENT,
            ma.REFERENCE_REFUSED} == {"resolved", "absent", "refused"}


def test_the_scorer_writes_nothing_and_needs_no_session():
    """Layer 5/6/7 are pure by contract - only layer 8 writes. Passing no db proves it."""
    ref_meta = _meta()
    ref = _ref_cells()
    ma.score_candidates([{"map_id": "M1", "meta": ref_meta, "cells": ref}], ref, ref_meta)


def test_empty_source_and_empty_reference_do_not_raise():
    cands, excluded, ruling, _s = ma.score_candidates([], [], _meta())
    assert ruling["winner"] is None
    assert len(cands) == 8
    assert all(c["agreement"] == 0 for c in cands)


# ---------------------------------------------------------------------------
# the stored DECLARATION - a read fact, and not a confirmation
# ---------------------------------------------------------------------------

def test_a_defaulted_frame_does_not_earn_the_current_badge():
    """THE point of this block. `rotation:0, side:"front"` is what the registrar and the
    ingestion scripts write without anyone looking, so a badge driven by the raw value would put
    `현재` on maps nobody ever measured - a plausible default impersonating a declaration (I4).
    """
    auto = _auto_meta()
    info = ma.declared_frame_of(auto)
    assert info["frame"] == "rot0_front", "still reports what the transform will use"
    assert info["source"] == map_overlay.GEOMETRY_AUTO_REGISTERED

    silent = _meta(rotation=0, side="front")          # unmarked, but 0/front
    assert ma.declared_frame_of(silent)["source"] == map_overlay.ORIENTATION_INDETERMINATE

    real = _meta(rotation=90, side="back")
    info = ma.declared_frame_of(real)
    assert info["frame"] == "rot90_back"
    assert info["source"] == map_overlay.GEOMETRY_DECLARED
    assert info["axes"] == {"rotation": map_overlay.GEOMETRY_DECLARED,
                            "side": map_overlay.GEOMETRY_DECLARED}


def test_a_half_declared_frame_still_reports_the_declared_axis():
    """Measured on the only live unit: 40 of 40 maps write `rot90_front`, where rotation 90 IS a
    declaration (no default path emits it) and `side: "front"` is not. The combined answer is
    honestly 'not a declaration', but collapsing to that alone would throw away a real rotation
    declaration that on its own narrows 8 candidates to 2. The verdict uses the combined token;
    the screen gets the axes."""
    half = _meta(rotation=90, side="front")
    info = ma.declared_frame_of(half)
    assert info["source"] != map_overlay.GEOMETRY_DECLARED, "the pair is not attested"
    assert info["axes"]["rotation"] == map_overlay.GEOMETRY_DECLARED, (
        "the rotation declaration must survive the combination")
    assert info["axes"]["side"] == map_overlay.ORIENTATION_INDETERMINATE


def test_a_half_declared_frame_follows_its_weakest_axis():
    """rotation declared, side defaulted -> the pair is not a declaration. A combined value
    follows its weakest contributor (spec section 0.2 layer 9)."""
    half = _meta(rotation=270, side="front")
    info = ma.declared_frame_of(half)
    assert info["frame"] == "rot270_front"
    assert info["source"] == map_overlay.ORIENTATION_INDETERMINATE


def test_declared_frame_of_none_is_absent_not_a_frame():
    assert ma.declared_frame_of(None)["frame"] is None
    assert ma.declared_frame_of(None)["source"] == map_overlay.GEOMETRY_ABSENT


# ---------------------------------------------------------------------------
# THE VALUE METRIC - and why occupancy alone was not enough
# ---------------------------------------------------------------------------
# Occupancy is not merely "flat" on a symmetric footprint; it carries NO orientation
# information at all. The circle is invariant under all eight frames (spec section 1), so
# every candidate covers the same dies and whatever spread appears between them is sampling
# noise. A ranked winner produced from that is worse than a refusal, and the route WAS
# producing one: `rot90_front`, margin 7 dies, on a unit whose eight occupancy scores differ
# only by noise.
#
# `test_values_settle_what_occupancy_cannot_see` is the load-bearing test here. Its fixture is
# occupancy-blind BY CONSTRUCTION and `test_the_value_fixture_is_occupancy_blind` asserts that
# it is, so a green result cannot come from occupancy leaking back in.

def _symmetric_ref():
    """A footprint invariant under all eight frames - centred on the 13x13 grid.

    Deliberately the OPPOSITE of `_ref_cells`: there the asymmetry is what lets occupancy
    decide, here its absence is what makes occupancy useless. Both fixtures are needed
    because the two metrics fail in different places.
    """
    return sorted((x, y) for x in range(3, 10) for y in range(3, 10))


def _unique_values(cells):
    """One distinct value per die. A cell that lands on the wrong die therefore disagrees,
    which is what makes the value axis able to separate frames the footprint cannot."""
    return ["v%d_%d" % (x, y) for (x, y) in cells]


def _plant(ref_meta, ref, planted):
    """Re-express `ref` in `planted`'s frame, carrying each die's value with it."""
    fwd = map_overlay.make_frame_transform(ref_meta, source_meta_for_frame(ref_meta, planted))
    return [fwd(x, y) for (x, y) in ref]


def test_the_value_fixture_is_occupancy_blind():
    """Guard on the FIXTURE, not on the code. If the footprint ever stops being symmetric,
    the test below would start passing on occupancy and would no longer be testing values."""
    ref_meta = _meta()
    ref = _symmetric_ref()
    images = _dihedral_images(ref)
    assert len(set(images)) == 1, "the footprint must be invariant under all eight frames"

    cands, _e, _r, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": _plant(ref_meta, ref, "rot90_front")}],
        ref, ref_meta, thresholds=THRESHOLDS)
    occ = {c["agreement"] for c in cands}
    assert len(occ) == 1, "occupancy separates this fixture, so it is the wrong fixture: %s" % occ


@pytest.mark.parametrize("planted", ["rot90_front", "rot180_front", "rot270_front",
                                     "rot0_back"])
def test_values_settle_what_occupancy_cannot_see(planted):
    """The measured case, reproduced: all eight candidates occupy the SAME dies and only the
    values move. `core_defect_map LOT-A/05` is the real instance - occupancy reported an
    eight-way tie there while values separated the truth `rot270_back` (1028 of 1028
    discriminating) from the declared candidate (640) by 374 dies."""
    ref_meta = _meta()
    ref = _symmetric_ref()
    recorded = _plant(ref_meta, ref, planted)

    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": recorded,
          "values": _unique_values(ref)}],
        ref, ref_meta, reference_values=_unique_values(ref), thresholds=THRESHOLDS)

    assert ruling["metric"] == ma.METRIC_VALUES
    assert ruling["winner"] == planted, (
        "planted %s, scorer said %s; values=%s"
        % (planted, ruling["winner"], {c["frame"]: c["value_agreement"] for c in cands}))
    top = next(c for c in cands if c["frame"] == planted)
    assert top["value_agreement"] == len(ref)
    assert top["value_discriminating"] > 0


def test_a_constant_valued_reference_agrees_everywhere_and_discriminates_nothing():
    """The value axis needs its OWN discriminating subset, for the same reason occupancy does.
    If every candidate gets the same answer on a cell, that cell excludes no candidate - and a
    reference whose dies all carry one value is exactly that case for every cell at once.
    Counting agreement without the mask turns "all eight are equally right" into a winner.

    Defect injection found this gap: dropping `& value_varies` left the suite green."""
    ref_meta = _meta()
    ref = _symmetric_ref()
    flat = ["1"] * len(ref)
    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta,
          "cells": _plant(ref_meta, ref, "rot90_front"), "values": flat}],
        ref, ref_meta, reference_values=flat, thresholds=THRESHOLDS)
    assert ruling["metric"] == ma.METRIC_VALUES
    assert all(c["value_agreement"] == len(ref) for c in cands), \
        "every candidate should match a constant value everywhere"
    assert all(c["value_discriminating"] == 0 for c in cands), \
        "no cell separates the candidates, so none of them discriminates"
    assert ruling["winner"] is None
    assert ruling["reason_code"] in ("tie", "no_discrimination")


def test_both_metrics_are_reported_and_neither_replaces_the_other():
    """Occupancy stays the honest answer where the reference carries no values, so it is not
    removed when values exist. Both are on every candidate."""
    ref_meta = _meta()
    ref = _ref_cells()
    cands, _e, _r, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": ref, "values": _unique_values(ref)}],
        ref, ref_meta, reference_values=_unique_values(ref), thresholds=THRESHOLDS)
    for c in cands:
        for k in ("agreement", "discriminating", "value_agreement", "value_discriminating"):
            assert k in c, k
        assert c["agreement"] is not None


def test_a_reference_without_values_reports_null_not_zero():
    """Zero would say "we compared the values and none matched". Null says "there were no
    values to compare" - the opposite claim, and the one that is true."""
    ref_meta = _meta()
    ref = _ref_cells()
    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": ref}], ref, ref_meta,
        thresholds=THRESHOLDS)
    assert ruling["metric"] == ma.METRIC_OCCUPANCY
    for c in cands:
        assert c["value_agreement"] is None
        assert c["value_discriminating"] is None
        assert c["value_margin"] is None


def test_a_source_without_values_leaves_the_value_axis_null():
    """The weakest side decides. A reference carrying values cannot make a value comparison
    possible when the source brought none."""
    ref_meta = _meta()
    ref = _ref_cells()
    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": ref}], ref, ref_meta,
        reference_values=_unique_values(ref), thresholds=THRESHOLDS)
    assert ruling["metric"] == ma.METRIC_OCCUPANCY
    assert all(c["value_agreement"] is None for c in cands)


def test_values_stay_aligned_with_their_cells_when_a_coordinate_is_dropped():
    """A value list that is filtered independently of its coordinates shifts every value
    after the dropped row onto its neighbour. That is invisible in every count - the totals
    are identical - and it is exactly the class of defect this module exists to prevent."""
    rows = [(1, 1), ("bad", 2), (3, 3)]
    cells, vals = ma._to_cells(rows, ["a", "b", "c"])
    assert cells == [(1, 1), (3, 3)]
    assert vals == ["a", "c"], "the dropped coordinate took the wrong value with it"


def test_values_are_truncated_with_their_cells_not_separately():
    ref_meta = _meta()
    ref = _ref_cells()
    cands, _e, _r, stats = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": ref, "values": _unique_values(ref)}],
        ref, ref_meta, reference_values=_unique_values(ref), cell_cap=5,
        thresholds=THRESHOLDS)
    assert stats["truncated"] is True
    assert stats["scored_cells"] == 5
    top = max(cands, key=lambda c: c["value_agreement"] or 0)
    assert top["value_agreement"] <= 5


# ---------------------------------------------------------------------------
# THRESHOLDS - declared, never defaulted
# ---------------------------------------------------------------------------

def test_an_undeclared_threshold_refuses_to_rank():
    """`Number(null) === 0` has bitten this project three times. Folding an absent threshold
    to zero turns "we cannot tell" into "always rank", which is the failure this whole round
    is closing."""
    ref_meta = _meta()
    ref = _ref_cells()
    args = ([{"map_id": "M1", "meta": ref_meta,
              "cells": _plant(ref_meta, ref, "rot90_front")}], ref, ref_meta)
    assert ma.score_candidates(*args, thresholds=THRESHOLDS)[2]["winner"] == "rot90_front"
    for absent in (None, {}, {"min_margin_dies": 1}, {"min_discriminating_dies": 1}):
        ruling = ma.score_candidates(*args, thresholds=absent)[2]
        assert ruling["winner"] is None, absent
        assert ruling["reason_code"] == "no_thresholds", absent


def test_an_undeclared_threshold_is_omitted_from_the_payload_not_nulled():
    assert ma.load_alignment_thresholds({}) == {}
    assert ma.load_alignment_thresholds({"alignment": {}}) == {}
    assert ma.load_alignment_thresholds(
        {"alignment": {"min_margin_dies": 7}}) == {"min_margin_dies": 7}
    # an unreadable declaration is not a declaration - it must not become 0 either
    assert ma.load_alignment_thresholds(
        {"alignment": {"min_margin_dies": "twenty", "min_discriminating_dies": 3}}
    ) == {"min_discriminating_dies": 3}


def test_a_margin_below_the_declared_floor_does_not_win():
    """The measured case that forced this: eight occupancy scores spread by 7 dies on a
    circular footprint, which the route was ranking as a confident winner."""
    ref_meta = _meta()
    ref = _ref_cells()
    args = ([{"map_id": "M1", "meta": ref_meta,
              "cells": _plant(ref_meta, ref, "rot90_front")}], ref, ref_meta)
    tight = {"min_margin_dies": 10_000, "min_discriminating_dies": 1}
    ruling = ma.score_candidates(*args, thresholds=tight)[2]
    assert ruling["winner"] is None
    assert ruling["reason_code"] == "margin_too_small"
    # the numbers that produced the refusal travel with it - the operator can see both
    assert ruling["min_margin_dies"] == 10_000
    assert ruling["margin"] is not None


def test_too_few_discriminating_dies_is_a_different_refusal_from_too_small_a_margin():
    """One asks whether there is evidence at all, the other whether the winner is ahead.
    Reading either as standing in for the other sends the operator to the wrong repair."""
    ref_meta = _meta()
    ref = _ref_cells()
    args = ([{"map_id": "M1", "meta": ref_meta,
              "cells": _plant(ref_meta, ref, "rot90_front")}], ref, ref_meta)
    ruling = ma.score_candidates(
        *args, thresholds={"min_margin_dies": 1, "min_discriminating_dies": 10_000})[2]
    assert ruling["reason_code"] == "too_few_discriminating"
    assert ruling["min_discriminating_dies"] == 10_000


def test_every_threshold_refusal_has_its_own_sentence():
    seen = {}
    for code in ("no_thresholds", "too_few_discriminating", "margin_too_small",
                 "no_discrimination", "no_margin", "tie", "no_candidate_scored"):
        text = ma._RULING_TEXT[code]
        assert text not in seen, "%s and %s share a sentence" % (code, seen.get(text))
        seen[text] = code


def _half_symmetric_ref():
    """Invariant under the transpose and NOTHING else, so exactly two of the eight frames land
    on the same dies while the other six do not.

    This is the only shape that produces a TIE in the strict sense: the evidence is real (it
    separates six candidates) and it still cannot choose between the top two. Every other
    "tie" this suite used to build was a symmetric footprint, where the eight scores are equal
    because the reference carries no orientation at all - a different fact with a different
    repair, and now a different reason code.
    """
    return sorted(({(x, y) for x in range(4, 9) for y in range(4, 9)}
                   - {(4, 5), (5, 4)}) | {(9, 9)})


def test_a_structural_refusal_is_named_before_the_thresholds_are_blamed():
    """"These eight are indistinguishable" is true whatever the thresholds say. Reporting it
    as `no_thresholds` sends the operator to edit config, where nothing will change.

    🔴 THIS FIXTURE IS SYMMETRIC UNDER ALL EIGHT, AND THAT IS `no_discrimination`, NOT `tie`.
       The assertion used to read `tie`, which contradicted this module's own documented rule
       (see the REFERENCE_KIND_* block: eight candidates occupying the same dies is the
       reference failing to distinguish them, not a tie). The tie branch ran first and swallowed
       the most common production shape - a circular or symmetric footprint - and told the
       operator the evidence was real when it carried no orientation at all.
    """
    ref_meta = _meta()
    ref = _symmetric_ref()          # invariant under all eight: the reference cannot choose
    ruling = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": _plant(ref_meta, ref, "rot90_front")}],
        ref, ref_meta, thresholds=None)[2]
    assert ruling["reason_code"] == ma.RULING_NO_DISCRIMINATION
    assert ruling["discriminating"] == 0


def test_a_tie_is_reported_only_when_the_evidence_separates_something():
    """The product owner's distinction, as an assertion: a tie means the evidence is REAL and
    still does not choose. So `tie` requires discrimination above zero - candidates level at
    zero discrimination are the reference's failure, not a tie between candidates.
    """
    ref_meta = _meta()
    ref = _half_symmetric_ref()
    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": _plant(ref_meta, ref, "rot0_front")}],
        ref, ref_meta, thresholds=THRESHOLDS)
    assert ruling["reason_code"] == ma.RULING_TIE
    assert len(ruling["tied"]) == 2, ruling["tied"]
    assert ruling["discriminating"] > 0, (
        "a tie with nothing discriminating is not a tie - it is an unusable reference")
    # and the fixture really does separate the other six, so the tie is between two REAL scores
    assert len({c["agreement"] for c in cands}) > 1


def test_the_ruling_says_which_metric_it_ranked_on():
    ref_meta = _meta()
    ref = _ref_cells()
    occ = ma.score_candidates([{"map_id": "M1", "meta": ref_meta, "cells": ref}],
                              ref, ref_meta, thresholds=THRESHOLDS)[2]
    val = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": ref, "values": _unique_values(ref)}],
        ref, ref_meta, reference_values=_unique_values(ref), thresholds=THRESHOLDS)[2]
    assert occ["metric"] == ma.METRIC_OCCUPANCY
    assert val["metric"] == ma.METRIC_VALUES


def test_no_metric_is_a_ratio():
    """Fit percentages were measured REVERSING the ranking (spec section 3): a candidate one
    cell off at 94% ranked below three wrongly-oriented candidates at 95-98%."""
    ref_meta = _meta()
    ref = _ref_cells()
    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": ref, "values": _unique_values(ref)}],
        ref, ref_meta, reference_values=_unique_values(ref), thresholds=THRESHOLDS)
    for c in cands:
        for k, v in c.items():
            assert "percent" not in k and "pct" not in k and "ratio" not in k
            if isinstance(v, float):
                assert float(v) == int(v), "%s is fractional" % k
    assert all(not isinstance(v, float) or float(v) == int(v) for v in ruling.values()
               if isinstance(v, (int, float)))
