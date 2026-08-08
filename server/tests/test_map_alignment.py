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

# Declared for the tests that want a ranked winner.
#
# 🔴 THIS IS THE SAME PAIR THE SCORER NOW FALLS BACK TO (`ma.DEFAULT_THRESHOLDS`), AND THAT IS
#    THE POINT RATHER THAN A COINCIDENCE. `{1, 1}` is the weakest thing an operator could
#    declare: the margin comparison already floors at 1 (`max(1, ...)`) and `discriminating > 0`
#    is a structural check that runs earlier, so a defaulted run and a run declared `{1, 1}`
#    rank the eight identically. What separates them is not the ORDER but the PROVENANCE, which
#    is why the undeclared case is asserted on two axes - the ranking AND the marker
#    (`test_an_undeclared_threshold_ranks_and_says_it_was_defaulted`). A default of 0 would be
#    the old impersonation (I4) and is still refused: it would turn "cannot tell" into a
#    confident winner.
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
    """A source map whose grid spec is auto-registered: the same refusal the live case hit.

    🔴 Since 2026-08-06 reaching that refusal takes `assume_reference_geometry=False`,
    passed EXPLICITLY at every call site below. The assumption now defaults ON, which
    means this map gets its geometry borrowed and scored instead of excluded - the
    intended behaviour, and it would quietly empty every test in this section. These
    tests are about how the scorer reports having scored NOTHING, so they have to reach
    that state on purpose rather than inherit it from a default that has since moved.
    """
    return {"map_id": map_id, "meta": _auto_meta(), "cells": _ref_cells()}


def test_a_run_where_no_cell_reached_the_scorer_is_not_a_tie():
    """THE REGRESSION. The reference resolves, the only source map is excluded, and the answer
    must say that nothing was scored - never that the candidates were level."""
    cands, excluded, ruling, stats = ma.score_candidates(
        [_refused_map()], _ref_cells(), _meta(), thresholds=THRESHOLDS,
        assume_reference_geometry=False)
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


def test_coordinates_that_arrived_and_were_refused_are_not_called_undelivered():
    """MEASURED 2026-08-05, and the reason `no_candidate_scored` was unreachable in production.

    `placed_cells` counts coordinates that SURVIVED the transform. When all eight candidates
    refuse, every `keys` is None, so that count is 0 - and `not live` already implies it, which
    made the branch a constant: every run with nothing live said `no_cells_scored`, "소스 좌표
    미도달". Here the source is intact (0 excluded, 1 usable map, 47 cells handed to the
    scorer) and the REFERENCE is what cannot be reproduced. Sending the operator to inspect
    their coordinates is sending them to the one thing that is fine.

    The refusal PROSE was already right - `compose_refusal` reads the candidates' own reason -
    so the sentence and the reason code contradicted each other, and the screen's label comes
    from the code.
    """
    ref_meta = _meta()
    ref = _ref_cells()
    # a reference whose own grid spec is missing: every candidate's transform refuses, and
    # nothing about the source is wrong
    blind_ref_meta = dict(ref_meta, grid_cols=None, grid_rows=None)
    cands, excluded, ruling, stats = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": ref}], ref, blind_ref_meta,
        thresholds=THRESHOLDS)

    # the fixture really is the refused-by-the-transform state, not an excluded-source state
    assert excluded.total() == 0, "the source was excluded, so this tests the wrong branch"
    assert stats["source_maps_usable"] == 1
    assert stats["scored_cells"] == len(ref), "the coordinates DID reach the scorer"
    assert stats["placed_cells"] == 0
    assert all(c["reason"] for c in cands), "every candidate refused, with a stated reason"

    assert ruling["reason_code"] == ma.RULING_NO_CANDIDATE_SCORED, (
        "coordinates that arrived and were refused are not coordinates that never arrived")
    # and the sentence the operator reads must not blame the source data either
    why = ma.compose_refusal(ma.STATE_NOT_SCORABLE, {"state": ma.REFERENCE_RESOLVED},
                             excluded, ruling, 1, cands)
    assert "미도달" not in why, why


def test_a_source_that_never_reached_the_scorer_still_says_so():
    """The other side of the same fork, so the fix cannot be "always say refused". Here the
    coordinates genuinely never arrive - the map is excluded before the candidate loop - and
    the repair is the source declaration, not the reference."""
    ref_meta = _meta()
    ref = _ref_cells()
    _c, excluded, ruling, stats = ma.score_candidates(
        [{"map_id": "M1", "meta": _meta(cols=23, rows=23), "cells": ref}], ref, ref_meta,
        thresholds=THRESHOLDS, assume_reference_geometry=False)
    assert excluded.total() == 1
    assert stats["scored_cells"] == 0
    assert ruling["reason_code"] == ma.RULING_NO_CELLS_SCORED


def test_the_verdict_carries_the_exclusion_count_and_its_reason():
    """A verdict that contradicts a fact sitting beside it is worse than one that says less.
    The exclusion tally was in the response and the ruling said something else."""
    _e, excluded, ruling, _s = ma.score_candidates(
        [_refused_map("M1"), _refused_map("M2")], _ref_cells(), _meta(),
        thresholds=THRESHOLDS, assume_reference_geometry=False)
    assert ruling["source_map_count"] == 2
    assert ruling["excluded_map_count"] == 2 == excluded.total()
    assert ruling["excluded_reason_code"] == ma.EXCLUDE_GEOMETRY_REFUSED
    assert ruling["placed_cells"] == 0


def test_the_nothing_scored_sentence_names_what_to_declare():
    """The sentence IS the instruction. It has to carry the count that was only in the console
    AND the word for the thing the operator must declare."""
    _c, excluded, ruling, _s = ma.score_candidates(
        [_refused_map()], _ref_cells(), _meta(), thresholds=THRESHOLDS,
        assume_reference_geometry=False)
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
    nothing = ma.score_candidates([_refused_map()], ref, ref_meta, thresholds=THRESHOLDS,
                                  assume_reference_geometry=False)[2]
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
    """🔴 Opt-out passed explicitly since 2026-08-06: with the assumption ON (the default)
    an auto-registered map is BORROWED and scored, not excluded. This test is about the
    exclusion carrying a named reason, so it has to ask for the exclusion."""
    ref_meta = _meta()
    ref = _ref_cells()
    cands, excluded, _r, stats = ma.score_candidates(
        [{"map_id": "GOOD", "meta": ref_meta, "cells": ref},
         {"map_id": "AUTO", "meta": _auto_meta(), "cells": ref}], ref, ref_meta,
        assume_reference_geometry=False)
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


def test_no_winner_names_missing_index_values_before_margin():
    """A proposed `dt_index` column is not evidence that any row has a value.

    The live DT-EQP-02 case had all source values NULL.  The scorer correctly darkened the
    index axis and searched shifts, but its old margin-only sentence prescribed the unsafe
    repair: lowering the margin threshold.  This sentence must win only for that exact causal
    pair; ordinary low-margin verdicts retain their existing ruling text.
    """
    missing_index = {
        "reason_code": "margin_too_small",
        "index_axis": ma.INDEX_AXIS_ABSENT,
        "anchor_reason": ma.ANCHOR_NO_INDEX,
    }
    why = ma.compose_refusal(ma.STATE_NO_WINNER, {"state": ma.REFERENCE_RESOLVED},
                             ma._Excluded(), missing_index, 1)
    # 🔴 컬럼 이름은 문장에 없다 — `compose_refusal`은 어느 컬럼이 순번인지 모르고, 적으면
    #    `core_*` 표에서 없는 이름을 대게 된다(총괄 병합 수정 2026-08-08).
    assert why == ("순번 컬럼에 값이 없어 값 축으로 채점했습니다 - "
                   "순번을 채우면 정확 채점이 가능합니다")

    ordinary_margin = dict(missing_index, index_axis=ma.INDEX_AXIS_RANKING,
                           anchor_reason=None)
    assert ma.compose_refusal(ma.STATE_NO_WINNER, {"state": ma.REFERENCE_RESOLVED},
                              ma._Excluded(), ordinary_margin, 1) == \
        ma._ruling_text(ordinary_margin)


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


# ---------------------------------------------------------------------------
# VALUE COMPARISON, FIXED 2026-08-06 - three defects, all with the SAME symptom
# ---------------------------------------------------------------------------
# `str(rv) == str(sv)` / `reference.kind == 'values'` / a value column that is all NULL each
# produce "value agreement 0" -> `no_overlap` -> a screen that reads as a geometry failure. That
# ambiguity is what cost the operator a day.

@pytest.mark.parametrize("ref_value,src_value,expect,why", [
    (2.0, "2", True, "the live trace showed exactly this: a float source against a string ref"),
    ("2", 2, True, "and the mirror image"),
    ("02", "2", True, "leading zeros are formatting, not a different bin"),
    ("2.0", "2.00", True, None),
    ("B1 ", "b1", True, "whitespace and case are rendering, not meaning"),
    ("B1", "B2", False, "different bins must stay different"),
    ("1E1", "10", False, "scientific notation stays TEXT - '1E1' is a spellable bin code"),
    ("nan", "nan", True, "as TEXT they are equal; as floats NaN != NaN, which is why the "
                         "acceptor is a regex and not float()"),
    (None, "1", False, "absent is not a match"),
    (None, None, False, "and two absents are not a match either - nothing was measured"),
])
def test_the_value_comparison_rule(ref_value, src_value, expect, why):
    assert ma.values_equal(ref_value, src_value) is expect, why


def test_the_numeric_rule_does_not_widen_silently():
    """The rule was allowed to get looser; it was NOT allowed to get looser than stated. float()
    accepts spellings that are real bin codes, and a comparison that widened without saying so
    is the next round's mystery."""
    assert ma._value_key("1E1") == ("t", "1e1"), "exponent form must not become a number"
    assert ma._value_key("inf")[0] == "t"
    assert ma._value_key("nan")[0] == "t"
    assert ma._value_key(" 2 ") == ma._value_key("2.0") == ("n", 2.0)


def test_a_float_source_now_matches_a_string_reference_end_to_end():
    """The unit-level fix is not the point; the point is that it reaches the ranking. Same
    fixture as `test_values_settle_what_occupancy_cannot_see`, with the source's values arriving
    as floats the way they do live."""
    ref_meta = _meta()
    ref = _symmetric_ref()
    planted = "rot180_front"
    ref_vals = [str(i % 7) for i in range(len(ref))]
    src_vals = [float(v) for v in ref_vals]

    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": _plant(ref_meta, ref, planted),
          "values": src_vals}],
        ref, ref_meta, reference_values=ref_vals, thresholds=THRESHOLDS)
    assert ruling["value_axis"] == ma.VALUE_AXIS_RANKING
    assert ruling["value_axis_reason"] is None
    assert max(c["value_agreement"] for c in cands) == len(ref), (
        "every die matched by meaning; under the old str() rule this was zero")


def test_disjoint_value_vocabularies_demote_the_axis_and_name_it():
    """`reference.kind='values'` means both sides HAVE a value column, not that the words mean
    the same things. A valid-die floor's words ('1', 'E1') are not bin codes ('B1', 'B2') - the
    intersection is empty at every coordinate under every frame, so ranking on it produces
    `no_overlap` and sends the operator to check geometry that was never wrong."""
    ref_meta = _meta()
    ref = _ref_cells()
    ref_vals = ["1" if i % 3 else "E1" for i in range(len(ref))]
    src_vals = ["B%d" % (i % 4 + 1) for i in range(len(ref))]

    cands, _e, ruling, stats = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": _plant(ref_meta, ref, "rot90_front"),
          "values": src_vals}],
        ref, ref_meta, reference_values=ref_vals, thresholds=THRESHOLDS)

    assert ruling["metric"] == ma.METRIC_OCCUPANCY, "the ranking must fall back, not refuse"
    assert ruling["value_axis"] == ma.VALUE_AXIS_REPORTED, "measured, but not ranking"
    assert ruling["value_axis_reason"] == ma.VALUE_AXIS_DISJOINT
    assert stats["value_vocab_shared"] == 0
    assert ruling["winner"] == "rot90_front", (
        "and the feature still runs - the product owner's ruling is that it runs first")
    assert all(c["value_agreement"] is not None for c in cands if c["state"] == ma.STATE_SCORED), (
        "the numbers stay on the rows; what changed is that they do not rank")


def test_an_all_null_reference_value_column_demotes_by_its_own_name():
    """The identical symptom by another route: `ref_value_at` is NOT empty (it has a key per
    coordinate), the values behind those keys are all None, every comparison misses, and the
    ruling is `no_overlap`. The old gate `bool(ref_value_at)` passed it straight through."""
    ref_meta = _meta()
    ref = _ref_cells()
    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": _plant(ref_meta, ref, "rot90_front"),
          "values": _unique_values(ref)}],
        ref, ref_meta, reference_values=[None] * len(ref), thresholds=THRESHOLDS)
    assert ruling["metric"] == ma.METRIC_OCCUPANCY
    assert ruling["value_axis_reason"] == ma.VALUE_AXIS_REF_ALL_NULL
    assert ruling["reason_code"] != ma.RULING_NO_OVERLAP, (
        "this is the whole point: it must no longer look like a geometry failure")
    assert all(c["value_agreement"] is None for c in cands), (
        "null, not zero - nothing was compared")


def test_a_demoted_value_axis_does_not_get_called_weighted():
    """Weights multiply value hits. If the value axis is not ranking, weighting it changes no
    ranking and only renames the metric - and then the screen says 'winner chosen under weights'
    about a verdict weights never touched."""
    ref_meta = _meta()
    ref = _ref_cells()
    _c, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": _plant(ref_meta, ref, "rot90_front"),
          "values": ["B1"] * len(ref)}],
        ref, ref_meta, reference_values=["1"] * len(ref), thresholds=THRESHOLDS,
        value_weights={"B1": 5.0})
    assert ruling["metric"] == ma.METRIC_OCCUPANCY
    assert ruling["metric"] != ma.METRIC_VALUES_WEIGHTED
    assert ruling["value_axis_reason"] == ma.VALUE_AXIS_DISJOINT


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
# PER-VALUE WEIGHTS - what breaks a symmetry the raw count cannot
# ---------------------------------------------------------------------------
# Measured 2026-08-05: a partial DT map against the valid-die disk scored agreement 467 on ALL
# EIGHT candidates with discriminating 0. Every cell of a partial map lands on a valid die under
# every frame, so no cell's answer varies. Weighting OCCUPANCY cannot touch that - scaling a
# mask that is identical across eight candidates scales eight candidates identically. Only the
# VALUE MATCH varies, so that is where a weight has to land.
#
# The fixture below is built so the RAW value counts TIE at the top on two DIFFERENT cell sets:
# one contains the distinctive value, the other does not. That is the smallest shape where a
# weight can change the ranking and an unweighted run genuinely cannot.

_W_HEAVY, _W_PLAIN = "rot90_front", "rot180_front"


def _block_permutation(ref_meta, block, frame):
    """Where candidate `frame` lands each block cell, after the shift the scorer solves.

    Goes through the REAL transform stack rather than composing rotation math here - a fixture
    with its own rotation would agree with a scorer that had the same bug.
    """
    tf = map_overlay.make_frame_transform(source_meta_for_frame(ref_meta, frame), ref_meta)
    placed = {p: tf(*p) for p in block}
    dx = min(p[0] for p in block) - min(v[0] for v in placed.values())
    dy = min(p[1] for p in block) - min(v[1] for v in placed.values())
    out = {p: (v[0] + dx, v[1] + dy) for p, v in placed.items()}
    assert sorted(out.values()) == sorted(block), frame
    return out


def _tie_on_two_different_sets():
    """Source/reference values engineered so `_W_HEAVY` and `_W_PLAIN` tie on the raw count.

    One cell `a` carries "E1" and matches ONLY under `_W_HEAVY`; one cell `b` carries "X" and
    matches ONLY under `_W_PLAIN`. Each planted value costs its frame exactly two mismatches
    elsewhere, so the two candidates land on the same raw total with different matched sets and
    the other six land below. The footprint is `_symmetric_ref`, so occupancy is blind by
    construction and cannot leak in as the thing that decided.
    """
    ref_meta = _meta()
    block = _symmetric_ref()
    perm = {f: _block_permutation(ref_meta, block, f) for f in ma.CANDIDATE_FRAMES}

    def _unique_under(frame, p):
        """`frame` is the ONLY candidate that lands p where it does - otherwise a second frame
        would collect the planted match too and the tie would not be between these two."""
        return sum(1 for f in ma.CANDIDATE_FRAMES if perm[f][p] == perm[frame][p]) == 1

    a = next(p for p in block if _unique_under(_W_HEAVY, p))
    b = next(p for p in block if p != a and _unique_under(_W_PLAIN, p)
             and len({p, a, perm[_W_HEAVY][a], perm[_W_PLAIN][p]}) == 4)

    src = dict.fromkeys(block, "1")
    src[a], src[b] = "E1", "X"
    ref = dict.fromkeys(block, "1")
    ref[perm[_W_HEAVY][a]], ref[perm[_W_PLAIN][b]] = "E1", "X"
    sources = [{"map_id": "M1", "meta": ref_meta, "cells": list(block),
                "values": [src[p] for p in block]}]
    return ref_meta, list(block), sources, [ref[q] for q in block]


def test_a_value_weight_ranks_what_the_raw_count_cannot():
    """FAILS BEFORE THE WEIGHTS EXIST. Two candidates hold the same raw value count on two
    different sets of cells, so the scorer correctly refuses with `tie`. Declaring the
    distinctive value heavier makes the two sets stop weighing the same - and that is the
    discrimination, because it is the only thing on this fixture that varies by frame.
    """
    ref_meta, ref, sources, ref_values = _tie_on_two_different_sets()

    cands, _e, plain, _s = ma.score_candidates(
        sources, ref, ref_meta, reference_values=ref_values, thresholds=THRESHOLDS)
    assert len({c["agreement"] for c in cands}) == 1, \
        "occupancy separates this fixture, so a weighted win would prove nothing"
    assert plain["metric"] == ma.METRIC_VALUES
    assert plain["winner"] is None and plain["reason_code"] == ma.RULING_TIE
    assert sorted(plain["tied"]) == sorted([_W_HEAVY, _W_PLAIN]), plain["tied"]

    w_cands, _e, weighted, _s = ma.score_candidates(
        sources, ref, ref_meta, reference_values=ref_values, thresholds=THRESHOLDS,
        value_weights={"E1": 5})
    assert weighted["winner"] == _W_HEAVY, (
        "weighted scores: %s" % {c["frame"]: c["value_agreement"] for c in w_cands})
    # 🔴 the ruling itself has to say the ranking came from a weighted axis. A winner picked
    #    under weights that is written down as `values` is indistinguishable from one picked
    #    without them.
    assert weighted["metric"] == ma.METRIC_VALUES_WEIGHTED

    # 🔴 NUMERATOR AND DISCRIMINATION MOVE TOGETHER. The one E1 cell is matched by `_W_HEAVY`
    #    and it varies across candidates, so weight 5 replaces its 1 in BOTH numbers. Leaving
    #    `value_discriminating` a raw count would keep `min_discriminating_dies` counting
    #    something else than the threshold it is compared against.
    before = next(c for c in cands if c["frame"] == _W_HEAVY)
    after = next(c for c in w_cands if c["frame"] == _W_HEAVY)
    assert after["value_agreement"] == before["value_agreement"] + 4
    assert after["value_discriminating"] == before["value_discriminating"] + 4, \
        "the discriminating count was left unweighted while agreement was weighted"


def test_an_undeclared_weight_scores_exactly_as_it_did():
    """The property that lets an operator switch weights on for ONE rule without touching the
    others: a run that declares none is unchanged - same numbers, same TYPES, same metric name.
    Counts stay `int`; a weighting path that ran with a default of 1.0 everywhere would produce
    whole-valued floats that every equality assertion would still accept.
    """
    ref_meta, ref, sources, ref_values = _tie_on_two_different_sets()
    base_c, _e, base_r, _s = ma.score_candidates(
        sources, ref, ref_meta, reference_values=ref_values, thresholds=THRESHOLDS)
    for absent in (None, {}):
        cands, _e2, ruling, _s2 = ma.score_candidates(
            sources, ref, ref_meta, reference_values=ref_values, thresholds=THRESHOLDS,
            value_weights=absent)
        assert cands == base_c, absent
        assert ruling == base_r, absent
        assert ruling["metric"] == ma.METRIC_VALUES, absent
    for c in base_c:
        for k in ("value_agreement", "value_discriminating", "value_margin"):
            assert type(c[k]) is int, "%s is %s, not a count" % (k, type(c[k]).__name__)


def test_a_declared_zero_is_a_declaration_and_an_absent_key_is_not():
    """`{"1": 0}` says "do not count this value". Reading it as "undeclared" hands it weight 1,
    the opposite instruction - and BOTH readings pick the same winner here, so only the exact
    number catches the conflation. Absence and zero have been confused twice this week.
    """
    ref_meta, ref, sources, ref_values = _tie_on_two_different_sets()
    cands, _e, ruling, _s = ma.score_candidates(
        sources, ref, ref_meta, reference_values=ref_values, thresholds=THRESHOLDS,
        value_weights={"1": 0, "E1": 5})
    top = next(c for c in cands if c["frame"] == _W_HEAVY)
    assert ruling["winner"] == _W_HEAVY
    # the single E1 match, and nothing else. Folding 0 to "undeclared" would read 5 + 46 = 51.
    assert top["value_agreement"] == 5.0, top["value_agreement"]

    assert ma.load_alignment_value_weights({}) == {}
    assert ma.load_alignment_value_weights({"alignment": {}}) == {}
    assert ma.load_alignment_value_weights(
        {"alignment": {"value_weights": {"1": 0}}}) == {"1": 0.0}
    # an unreadable declaration is not a declaration, and a negative one would let a match
    # count as evidence AGAINST the frame it matched
    assert ma.load_alignment_value_weights(
        {"alignment": {"value_weights": {"E1": "five", "E2": -1, "E3": 2}}}) == {"E3": 2.0}


def test_weights_cannot_rescue_a_reference_that_answers_the_same_everywhere():
    """THE HONEST LIMIT, as an assertion. When every cell lands on a matching value under all
    eight frames, no cell's answer varies - and any weight scales eight identical masks
    identically. The refusal must therefore name the REFERENCE as what cannot choose and point
    at the repair, rather than reporting "no discrimination" as a bare fact.
    """
    ref_meta = _meta()
    ref = _symmetric_ref()
    flat = ["1"] * len(ref)
    args = ([{"map_id": "M1", "meta": ref_meta,
              "cells": _plant(ref_meta, ref, "rot90_front"), "values": flat}], ref, ref_meta)
    heavy = ma.score_candidates(*args, reference_values=flat, thresholds=THRESHOLDS,
                                value_weights={"1": 1000})
    assert heavy[2]["winner"] is None
    assert heavy[2]["reason_code"] == ma.RULING_NO_DISCRIMINATION
    assert len({c["value_agreement"] for c in heavy[0]}) == 1, \
        "a uniform weight moved eight identical masks apart, which is impossible"
    for text in (ma._RULING_TEXT[ma.RULING_NO_DISCRIMINATION], ma._ruling_text(heavy[2])):
        assert "기준" in text and "필요" in text, \
            "the refusal has to name the reference and point at the repair: %s" % text


# ---------------------------------------------------------------------------
# THRESHOLDS - declared, never defaulted
# ---------------------------------------------------------------------------

def test_an_undeclared_threshold_ranks_and_says_it_was_defaulted():
    """PRODUCT OWNER RULING 2026-08-06: build the core behaviour, prove it runs, then add the
    refusals. An undeclared threshold used to mean NO RANKING AT ALL, and that single refusal
    is why the operator went a full day without ever seeing a ranked candidate list.

    🔴 TWO ASSERTIONS, NOT ONE, AND THE SECOND IS THE LOAD-BEARING ONE. A version that ranks
       and forgets to mark the ranking passes any test that only checks a winner appeared -
       and a defaulted winner that looks declared is exactly the thing that gets CONFIRMED into
       stored coordinates, after which nothing downstream looks wrong. So the marker is
       asserted on its own: which keys were defaulted, and the sentence that says so.

    🔴 AND THE MARKER IS ASSERTED ABSENT ON THE DECLARED RUN. Marking every ruling would be the
       same defect wearing the other hat - if `thresholds_defaulted` is never empty, it stops
       distinguishing anything and the screen learns to ignore it.
    """
    ref_meta = _meta()
    ref = _ref_cells()
    args = ([{"map_id": "M1", "meta": ref_meta,
              "cells": _plant(ref_meta, ref, "rot90_front")}], ref, ref_meta)

    declared = ma.score_candidates(*args, thresholds=THRESHOLDS)[2]
    assert declared["winner"] == "rot90_front"
    # unchanged behaviour: a declared run carries no marker and no sentence
    assert declared["thresholds_defaulted"] == []
    assert declared["provisional_text"] is None

    for absent, keys in ((None, ["min_margin_dies", "min_discriminating_dies"]),
                         ({}, ["min_margin_dies", "min_discriminating_dies"]),
                         ({"min_margin_dies": 1}, ["min_discriminating_dies"]),
                         ({"min_discriminating_dies": 1}, ["min_margin_dies"])):
        ruling = ma.score_candidates(*args, thresholds=absent)[2]
        # ① it ranks - the same frame the declared run named
        assert ruling["winner"] == "rot90_front", absent
        assert ruling["reason_code"] is None, absent
        # ② and it says the ranking is provisional, naming which keys were invented
        assert ruling["thresholds_defaulted"] == keys, absent
        assert ruling["provisional_text"] == ma.TEXT_PROVISIONAL_RANKING, absent
        # the numbers the ruling actually stood on travel with it, defaulted or not
        assert ruling["min_margin_dies"] == 1, absent
        assert ruling["min_discriminating_dies"] == 1, absent


def test_the_default_threshold_is_not_zero():
    """The guard that stays. Folding an undeclared threshold to 0 is `Number(null) === 0`,
    which has bitten this project three times, and it turns "we cannot tell these apart" into
    "confident winner". 1 is not a compromise: it is the floor the margin comparison already
    enforces (`max(1, ...)`), so it changes what may be CLAIMED, never what wins."""
    assert set(ma.DEFAULT_THRESHOLDS) == set(ma.THRESHOLD_KEYS)
    assert all(v >= 1 for v in ma.DEFAULT_THRESHOLDS.values())


def test_a_defaulted_ranking_still_loses_to_a_structural_refusal():
    """Defaulting the thresholds must not reach past the facts that are true whatever the
    thresholds say. A symmetric footprint cannot tell the eight apart, and answering that with
    a provisional WINNER would be precisely the confident-wrong-winner this round guards."""
    ref_meta = _meta()
    ruling = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta,
          "cells": _plant(ref_meta, _symmetric_ref(), "rot90_front")}],
        _symmetric_ref(), ref_meta, thresholds=None)[2]
    assert ruling["winner"] is None
    assert ruling["reason_code"] == ma.RULING_NO_DISCRIMINATION
    # the marker is still carried - the run WAS defaulted, and a reader of the refusal has to
    # be able to tell that raising a declared threshold was never the missing piece
    assert ruling["thresholds_defaulted"] == list(ma.THRESHOLD_KEYS)


def test_the_marker_survives_on_every_branch_the_ruling_can_take():
    """`geometry_assumed`'s rule, applied here: carried ALWAYS, not only when true. An absent
    key and an empty list look the same to the receiver, and that sameness is what folds
    "ranked on a declaration" and "ranked on a default" into one word."""
    ref_meta = _meta()
    ref = _ref_cells()
    planted = _plant(ref_meta, ref, "rot90_front")
    runs = [
        # nothing scored at all
        ma.score_candidates([], ref, ref_meta, thresholds=None)[2],
        # scored, and a winner
        ma.score_candidates([{"map_id": "M1", "meta": ref_meta, "cells": planted}],
                            ref, ref_meta, thresholds=None)[2],
        # scored, declared, no marker
        ma.score_candidates([{"map_id": "M1", "meta": ref_meta, "cells": planted}],
                            ref, ref_meta, thresholds=THRESHOLDS)[2],
    ]
    for r in runs:
        assert "thresholds_defaulted" in r, r.get("reason_code")
        assert isinstance(r["thresholds_defaulted"], list)
        assert "provisional_text" in r, r.get("reason_code")


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
    for code in ("too_few_discriminating", "margin_too_small",
                 "no_discrimination", "tie", "no_candidate_scored"):
        text = ma._RULING_TEXT[code]
        assert text not in seen, "%s and %s share a sentence" % (code, seen.get(text))
        seen[text] = code


def test_the_sentence_table_holds_no_code_the_scorer_cannot_emit():
    """A reason code with a sentence and no branch is a lie inside the vocabulary - this
    module says so itself (see `ASSUMPTION_AVAILABLE`). `no_margin` never had a branch, and
    `no_thresholds` lost its one when an undeclared threshold became a default plus a marker.

    Read from the SOURCE rather than from a list here: a list would be a second spelling of
    the branch set and would go stale the next time a branch is added. BOTH DIRECTIONS are
    checked - a branch with no sentence is the mirror defect and degrades silently to the
    catch-all 「순위 근거 부족」, which names nothing at all."""
    import inspect
    import re
    src = inspect.getsource(ma._rule_on)
    # the codes `_rule_on` can actually put on a ruling: string literals plus the constants
    literals = set(re.findall(r'reason_code=["\']([a-z_]+)["\']', src))
    named = {getattr(ma, n) for n in re.findall(r'reason_code=\(?(RULING_[A-Z_]+)', src)}
    named |= {getattr(ma, n)
              for n in re.findall(r'else (RULING_[A-Z_]+)\)', src)}
    emitted = literals | named
    assert emitted, "the branch scan found nothing - the regex went stale, not the code"

    for code in emitted:
        assert code in ma._RULING_TEXT, "%r is emitted but has no sentence" % code
    for code in ma._RULING_TEXT:
        assert code in emitted, "%r has a sentence but no branch in _rule_on" % code
    assert "no_thresholds" not in ma._RULING_TEXT
    assert "no_margin" not in ma._RULING_TEXT


def test_the_index_refusal_does_not_name_a_remedy_that_cannot_exist():
    """This sentence has now been WRONG TWICE, in two different directions, and this test was
    complicit in the second one.

    First it said 「번호가 매겨진 기준 맵 필요」 - read as "obtain a reference map that carries
    numbers", and the product owner went to build one. There is no place in the schema to put
    numbers ON a reference.

    Then it said the reference was the wrong valid-die map, and THIS TEST PINNED THAT (it
    required the words 「기준」 and 「다름」). That was true only of the old implementation, which
    numbered the REFERENCE's cells and compared the source's stored index against that table.
    Since 2026-08-06 the walk runs over the SOURCE's own dies in canonical coordinates and never
    reads the reference at all - so swapping the reference cannot move this number by one, and a
    sentence sending the operator to do that is the same failure a second time.

    What zero actually means now: under none of the eight frames did the source's own walk order
    reproduce its stored numbers. The thing to look at is the index column."""
    text = ma._RULING_TEXT_BY_METRIC[(ma.RULING_NO_OVERLAP, ma.METRIC_INDEX)]
    assert "번호가 매겨진 기준 맵 필요" not in text
    # it must NOT send the operator to the reference - that axis no longer reads one
    assert "기준" not in text, (
        "the index axis does not consult the reference; naming it sends the operator to change "
        "something that cannot change this number: %r" % text)
    assert "순번 컬럼" in text, "the repair that exists is to look at the index column"
    assert text != ma._RULING_TEXT[ma.RULING_NO_OVERLAP]
    assert "다른 기준 맵 필요" not in text


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
    as a threshold problem sends the operator to edit config, where nothing will change.

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


# ---------------------------------------------------------------------------
# SERPENTINE INDEX - the primitive, and the one absolute anchor in this data
# ---------------------------------------------------------------------------
# Occupancy and value agreement both measure a RELATION BETWEEN TWO UNKNOWNS, so neither pins
# an absolute orientation - that is why a partial map scored 467 agreement with 0 discriminating
# on all eight candidates. A serpentine index is a statement about canonical orientation itself,
# which is why it can decide what those two cannot.
#
# MEASURED 2026-08-05, and it bounds what these tests may claim: this box has NO index column
# anywhere - not in `table_config.json`, not in the live `dt_log`/`dt_map`, not in the raw
# transfer-log CSVs, and no file in the repo mentions one. Every fixture below is therefore
# SYNTHETIC and authored by the server agent. None of these numbers is a production
# measurement and none may be quoted as one.

def test_the_serpentine_alternates_and_starts_at_the_top_left():
    """Rules (1) and (2) as an assertion. A scan that never reversed would number the second
    row left-to-right too, and every index after the first row would be wrong."""
    cells = [(x, y) for y in range(3) for x in range(3)]
    m = ma.serpentine_index(cells)
    assert m[1] == (0, 0), "index 1 is the top-left of the valid-die region"
    assert m[3] == (2, 0), "first row runs left to right"
    assert m[4] == (2, 1), "the scan steps down and REVERSES"
    assert m[6] == (0, 1)
    assert m[7] == (0, 2), "and reverses again"
    assert len(m) == 9 and len(set(m.values())) == 9


def test_a_gap_inside_a_row_consumes_no_index():
    """Rule (3), and it is the one that BITES: measured 2026-08-05, the `TEST/TEST` floor in
    this DB has 2 rows with an interior hole. Letting a hole take a number shifts every index
    after it, so the whole tail of the map compares against the wrong cells."""
    cells = [(0, 0), (1, 0), (3, 0), (0, 1)]      # x=2 is absent from row 0
    m = ma.serpentine_index(cells)
    assert m[3] == (3, 0), "the hole at x=2 must not eat index 3"
    assert m[4] == (0, 1)
    assert len(m) == 4


def test_top_is_derived_from_the_reference_and_not_a_constant():
    """`cell_to_visual` renders the SMALLEST y at the top when `grid_y_invert` is false and the
    LARGEST when it is true. Baking either in makes the two readings 40 rows apart on a real
    floor (`CORE/1X`: index 1 at (14,0) vs (16,40), measured 2026-08-05)."""
    cells = [(0, 0), (1, 0), (0, 5), (1, 5)]
    assert ma.serpentine_index(cells, top_is_min_y=True)[1] == (0, 0)
    assert ma.serpentine_index(cells, top_is_min_y=False)[1] == (0, 5)


def test_an_empty_row_does_not_flip_the_direction():
    """Rule (2)'s explicit half. No floor in this DB exercises it - all five have zero empty
    rows inside their span (measured 2026-08-05) - but undeclared is not the same as
    unreachable, and a footprint with a hollow row would otherwise flip silently."""
    cells = [(0, 0), (1, 0), (0, 2), (1, 2)]      # y=1 entirely absent
    m = ma.serpentine_index(cells)
    assert m[3] == (1, 2), "row y=2 is the SECOND visited row, so it runs right to left"
    assert m[4] == (0, 2)


# ---------------------------------------------------------------------------
# THE INDEX AXIS, REBUILT 2026-08-06 - numbered over the SOURCE's own die set
# ---------------------------------------------------------------------------
# The old implementation walked the REFERENCE's cells to build a 1..N answer table and scored the
# source's stored index against it. Production data is not numbered that way (product owner:
# 「dt index는 1~266 또는 0~255 등이지」 · 「당연히 소스별로 index 매기는거잖아」). On their unit -
# reference 512 cells, source 266 - a 1..266 sequence compared against a 1..512 table disagrees at
# the first cell and at every cell after it. That is what `metric=index` / `reason=no_overlap`
# was: not a data problem, a wrong question.
#
# Everything below is SYNTHETIC and authored by the server agent; this box still has no index
# column anywhere. None of these numbers is a production measurement.

def _valid_die_floor(m):
    """Every die inside the wafer, in `m`'s own visual coordinates - i.e. what a reference IS in
    production: the whole valid-die map, not a job's subset. Reaches into map_overlay's private
    transformer on purpose: building the disc a second way here would be a second implementation
    of the very bounding-box rule the scorer depends on."""
    grid = map_overlay._grid_of(m)
    tf = map_overlay._frame_transformer(m, grid)
    return sorted({tf.cell_to_visual(c, r)
                   for r in range(tf.visual_rows) for c in range(tf.visual_cols)
                   if tf.is_inside_wafer(c, r)})


def _partial_job(floor_meta, floor, count, base=1):
    """A job that touched the first `count` dies of the wafer's walk, numbered over ITS OWN die
    set from `base`. Returns `(cells in the floor's frame, stored indices)`.

    This is the production shape and the case that has never worked: a strict subset of the
    floor, carrying a dense 1..count (or 0..count-1) of its own."""
    grid = map_overlay._grid_of(floor_meta)
    tf = map_overlay._frame_transformer(floor_meta, grid)
    walk = ma.serpentine_index([tf.visual_to_physical(x, y) for (x, y) in floor],
                               top_is_min_y=True)
    picked = [walk[k] for k in sorted(walk)[:count]]
    own = ma.serpentine_index(picked, top_is_min_y=True)
    k_of = {xy: k for k, xy in own.items()}
    return ([tf.physical_to_visual(*p) for p in picked],
            [k_of[p] - 1 + base for p in picked])


@pytest.mark.parametrize("planted", list(ma.CANDIDATE_FRAMES))
def test_the_index_axis_separates_the_frames_on_a_partial_map(planted):
    """THE LOAD-BEARING ONE. A partial map is the case the axis was built for and the only case
    it has never handled: occupancy saturates there (every subset of the valid dies sits on valid
    dies under every frame), so the index is the only axis with anything to say.

    Measured on this fixture: the planted frame scores 266/266 and no other candidate exceeds a
    couple of dozen."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _partial_job(floor_meta, floor, 266)
    assert len(cells) == 266 < len(floor), "the job must be a STRICT subset of the floor"

    cands, _e, ruling, stats = ma.score_candidates(
        [{"map_id": "M1", "meta": floor_meta, "cells": _plant(floor_meta, cells, planted),
          "indices": ks}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)

    assert ruling["metric"] == ma.METRIC_INDEX
    assert ruling["index_axis"] == ma.INDEX_AXIS_RANKING
    assert ruling["winner"] == planted, [
        (c["frame"], c["index_agreement"]) for c in cands]
    by = {c["frame"]: c["index_agreement"] for c in cands}
    assert by[planted] == 266, by
    runner_up = max(v for f, v in by.items() if f != planted)
    assert runner_up < 266 / 4, (
        "the correct frame must not merely win, it must be in a different class: %s" % by)


def test_occupancy_is_saturated_on_that_same_partial_map():
    """The FIXTURE guard for the test above, and the product owner's own symptom:
    「화면 보면 어긋나 있는데 오버랩 266이래」. If occupancy could separate these eight, the index
    test would be passing on something other than the index."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, _ks = _partial_job(floor_meta, floor, 266)
    cands, _e, _r, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": floor_meta,
          "cells": _plant(floor_meta, cells, "rot90_front")}],
        floor, floor_meta, thresholds=THRESHOLDS)
    assert {c["agreement"] for c in cands} == {266}, "occupancy must be an 8-way tie here"
    assert {c["discriminating"] for c in cands} == {0}, "and nothing may discriminate"


def test_the_walk_order_is_what_is_being_asserted():
    """THE MUTANT. This axis is an ORDERING claim, so an assertion that survives a reordered walk
    is asserting nothing. Break rule (2) - make every row run left-to-right instead of
    alternating - and require the partial-map test's winner to collapse.

    A serpentine and a boustrophedon-free raster agree on the first row and diverge on every row
    after it, so a scorer that had quietly stopped depending on the order would still pass."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _partial_job(floor_meta, floor, 266)
    planted = "rot90_front"
    payload = [{"map_id": "M1", "meta": floor_meta,
                "cells": _plant(floor_meta, cells, planted), "indices": ks}]

    h_cands, _he, healthy, _hs = ma.score_candidates(
        payload, floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    assert healthy["winner"] == planted, "guard: the mutant must start from a green run"
    h_hit = {c["frame"]: c["index_agreement"] for c in h_cands}
    h_margin = h_hit[planted] - max(v for f, v in h_hit.items() if f != planted)

    original = ma.serpentine_index

    # `left_to_right` is accepted and DELIBERATELY IGNORED. The mutation being injected is
    # "every row runs the same way", and a raster that honoured the start corner would still
    # alternate nothing - so the parameter changes which corner it starts from and not whether
    # it alternates, which is the axis this test is not about. Accepting it keeps the mutant
    # callable from `serpentine_index`'s current signature; ignoring it keeps the mutation the
    # one the docstring names. (Added 2026-08-07 with the start-corner axis.)
    def raster(cells_, top_is_min_y=True, left_to_right=True):
        present = {}
        for (x, y) in (cells_ or ()):
            present.setdefault(int(y), set()).add(int(x))
        out, i = {}, 1
        for y in sorted(present, reverse=not top_is_min_y):
            for x in sorted(present[y], reverse=not left_to_right):  # never ALTERNATES - the mutation
                out[i] = (x, y)
                i += 1
        return out

    ma.serpentine_index = raster
    try:
        mutated = ma.score_candidates(payload, floor, floor_meta, thresholds=THRESHOLDS,
                                      index_thresholds=THRESHOLDS)
    finally:
        ma.serpentine_index = original

    cands, _e, ruling, _s = mutated
    hit = {c["frame"]: c["index_agreement"] for c in cands}
    assert hit[planted] < 266, (
        "the walk order does not reach the score - a raster scan produced the same agreement as "
        "a serpentine, so this axis is not asserting an ordering at all: %s" % hit)
    # And the SEPARATION is what the axis sells, so that is what the mutant must destroy. A
    # raster keeps the rank of every cell in an even-numbered row (both scans run those rows
    # left to right), so about half the dies still agree under EVERY frame - which is exactly
    # how a wrong frame closes the gap.
    m_margin = hit[planted] - max(v for f, v in hit.items() if f != planted)
    assert m_margin * 10 < h_margin, (
        "breaking the walk left the frames just as separable (healthy margin %d, mutated %d), "
        "so the separation is not coming from the ordering: %s" % (h_margin, m_margin, hit))


@pytest.mark.parametrize("base", [0, 1, 1000])
def test_the_index_origin_is_normalised_by_the_observed_minimum(base):
    """`0..255` and `1..266` are both real (product owner 2026-08-06). The absolute value carries
    nothing; the ORDERING is the entire signal. A scorer that trusted the literal number would
    score one of these bases at zero."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _partial_job(floor_meta, floor, 120, base=base)
    assert min(ks) == base
    cands, _e, ruling, stats = ma.score_candidates(
        [{"map_id": "M1", "meta": floor_meta,
          "cells": _plant(floor_meta, cells, "rot180_front"), "indices": ks}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    assert ruling["winner"] == "rot180_front"
    assert max(c["index_agreement"] for c in cands) == 120
    assert stats["index_bases"] == {"0": base}, "the base that was seen must be reported"


def test_the_index_axis_does_not_consult_the_reference():
    """The constraint the previous round imposed - 「the numbering must have been assigned against
    the same valid-die map you load as the reference」 - was a consequence of the wrong
    implementation, not a property of the data. Score the same source against two DIFFERENT
    references and require the index numbers to be identical.

    Reference B is a strict sub-region of the floor, so it is emphatically not the map the
    numbering was assigned against. Under the old code every index agreement would move."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _partial_job(floor_meta, floor, 200)
    recorded = _plant(floor_meta, cells, "rot270_front")
    payload = lambda: [{"map_id": "M1", "meta": floor_meta, "cells": list(recorded),
                        "indices": list(ks)}]

    a = ma.score_candidates(payload(), floor, floor_meta, thresholds=THRESHOLDS,
                            index_thresholds=THRESHOLDS)[0]
    trimmed = [xy for xy in floor if xy[1] % 2 == 0]
    b = ma.score_candidates(payload(), trimmed, floor_meta, thresholds=THRESHOLDS,
                            index_thresholds=THRESHOLDS)[0]
    assert len(trimmed) < len(floor)
    assert [c["index_agreement"] for c in a] == [c["index_agreement"] for c in b], (
        "the walk runs over the source's own dies; changing the reference must not move it")


def test_each_source_map_is_numbered_over_its_own_die_set():
    """「소스별로 index 매기는거잖아」. Two jobs in one unit each restart at 1. Pooling them into a
    single walk makes one long sequence and BOTH maps score wrong - and the failure is silent,
    because the pooled walk is still a perfectly well-formed 1..N."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _partial_job(floor_meta, floor, 180)
    half = len(cells) // 2
    # split into two jobs, the second RENUMBERED from 1 - which is what the equipment does
    a_cells, a_ks = cells[:half], ks[:half]
    b_cells = cells[half:]
    b_ks = list(range(1, len(b_cells) + 1))
    planted = "rot0_back"
    cands, _e, _r, stats = ma.score_candidates(
        [{"map_id": "A", "meta": floor_meta, "cells": _plant(floor_meta, a_cells, planted),
          "indices": a_ks},
         {"map_id": "B", "meta": floor_meta, "cells": _plant(floor_meta, b_cells, planted),
          "indices": b_ks}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    best = max(c["index_agreement"] for c in cands)
    assert best == len(cells), (
        "both maps must score under their OWN numbering: %s of %d"
        % (best, len(cells)))
    assert stats["index_bases"] == {"0": 1, "1": 1}


def _job_from(floor_meta, floor, start, count, base=1):
    """A job that touched dies `[start, start+count)` of the WAFER's walk.

    `_partial_job` is this with `start=0`, and that zero is why nothing in this file could
    see the defect below: at `start=0` the job's die #1 IS the wafer's top-left valid die,
    so the anchor's premise is true by construction and the residual is zero no matter what
    the code does. The defect axis is `start`, and only a non-zero `start` activates it.
    """
    grid = map_overlay._grid_of(floor_meta)
    tf = map_overlay._frame_transformer(floor_meta, grid)
    walk = ma.serpentine_index([tf.visual_to_physical(x, y) for (x, y) in floor],
                               top_is_min_y=True)
    picked = [walk[k] for k in sorted(walk)[start:start + count]]
    own = ma.serpentine_index(picked, top_is_min_y=True)
    k_of = {xy: k for k, xy in own.items()}
    return ([tf.physical_to_visual(*p) for p in picked],
            [k_of[p] - 1 + base for p in picked])


def _reference_top_left(floor_meta, floor):
    """The reference's first walked valid die, in the reference's OWN stored coordinates.
    Rebuilt the way `score_candidates` builds it (canonical walk, then back through the
    pairing) rather than guessed, so this helper cannot drift from the thing it checks."""
    lc = map_overlay.frame_linear_part(floor_meta, ma._CANONICAL_AXES)
    pairs = sorted(floor)
    canon = [map_overlay.apply_linear(lc, x, y) for (x, y) in pairs]
    back = {}
    for p, v in zip(canon, pairs):
        back.setdefault(p, v)
    return back[ma.serpentine_index(canon, top_is_min_y=True)[1]]


@pytest.mark.parametrize("start,residual,anchor_shift", [
    (42, (13, 2), (-22, -29)), (100, (-9, 5), (-19, -7)), (400, (-9, 14), (-10, -7))])
def test_the_residual_is_observed_but_NOT_applied(start, residual, anchor_shift):
    """🔴 **REVERT PIN, 2026-08-06.** The assertions below used to require that the residual
    MOVED the map. It shipped, and on live data it moved a map whose anchor seat was already
    correct - the operator bisected to `ec8c0e7` (before `17d8d00`/`fac206c`/`4947a65`) and
    reported the screen correct there. The code narrows the bisect to one producer: before
    `4947a65` the anchor path used `dx, dy = anchor_dxy[frame]`, which is identically (0,0),
    so `_residual_shift` is the ONLY thing on that path that can emit a non-zero shift, and
    therefore the only thing that can have produced the operator's `(5,26)`.

    So the shipped shift is the anchor's seat again. What survives is the OBSERVATION: the
    search still runs and still reports what it would have chosen, because an operator seeing
    "a different seat would have fit" is useful and a machine silently taking it is what just
    happened.

    ⚠️ **The `residual` values in the parameters are still the measured ones and still
       correct** - they are what the search finds. The change is that finding is no longer
       doing. When a future round re-earns the movement, this test is where it argues.
    """
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _job_from(floor_meta, floor, start, 266)
    planted = "rot90_front"
    recorded = _plant(floor_meta, cells, planted)
    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": floor_meta, "cells": recorded, "indices": ks}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    win = next(c for c in cands if c["frame"] == planted)
    assert ruling["placement"] == ma.PLACEMENT_ANCHOR
    # ═══ 🔴 THE REDDENING ASSERTION (2026-08-06) — 「shift 0,0 고정」이 여기서 죽는다 ══════
    # The operator's whole report was that this field never moves. It could not: while the
    # placement pre-applied the anchor (`p = reference_top_left + L·(cell − anchor_cell)`),
    # `_anchor_shift`'s `reference_top_left − placed[i_min]` had nothing left to subtract
    # and was **(0,0) by construction** - a value that is structurally correct and
    # semantically empty. The placement is transform-only again, so the anchor's
    # translation is a real quantity and lands here.
    #
    # ⚠️ THE MUTATION THIS CATCHES, BY NAME: re-bake the anchor into the placement (restore
    #    the `L`-differential branch in `[2]`) and every one of these goes to (0,0). Injected
    #    2026-08-06 and confirmed red on all three parameters before this line shipped.
    #
    # 🔴 `anchor_shift` is `anchor_ref − anchor_src` read off the DATABASE COORDINATES of
    #    both anchors (product owner: 「앵커는 그냥 db좌표 그대로」). It is therefore the same
    #    value for all eight candidates - what separates them is the placement's linear
    #    part, not this translation - and it moves only when one of the two maps' STORED
    #    coordinates move. It does NOT move when a declared origin moves, which is the
    #    separate property `test_no_per_map_origin_reaches_anything_the_scorer_reports`
    #    measures on the outputs that rank.
    assert (win["shift"]["dx"], win["shift"]["dy"]) == anchor_shift, (
        "the shipped shift must be the anchor's own translation: %s" % (win["shift"],))
    assert anchor_shift != (0, 0), (
        "the parameter itself must activate the defect axis - a zero here would make the "
        "assertion above pass on the very code it exists to reject")
    assert win["residual"]["applied"] is False
    assert tuple(win["residual"]["would_move"]) == residual, (
        "the search must still REPORT what it would have chosen - that is the evidence the "
        "round which re-earns this will need: %s" % (win["residual"],))


@pytest.mark.skip(reason="RETIRED by the revert above (2026-08-06). Kept, not deleted, so the "
                         "round that re-earns the residual has its argument and its measured "
                         "numbers rather than re-deriving them from scratch.")
@pytest.mark.parametrize("start,residual", [(42, (13, 2)), (100, (-9, 5)), (400, (-9, 14))])
def test_RETIRED_a_job_that_did_not_start_at_the_wafers_top_left_is_still_placed_on_the_floor(
        start, residual):
    """THE MEASURED PRODUCTION SYMPTOM: 「index로는 잘 되는데 shift를 무조건 0,0으로 계산함」.

    `_anchor_shift` cannot return anything but (0,0) in the anchor path, and that is
    arithmetic rather than a bug in the data: `[2]` places every cell as
    `reference_top_left + L·(cell − anchor_cell)`, so `placed[i_min]` IS `reference_top_left`
    and `reference_top_left − placed[i_min]` has nothing to subtract. Measured at two
    different reference top-lefts ((17,1) and (40,16)), all eight frames, every run.

    That zero is harmless exactly when the anchor's premise holds. When the job started
    somewhere other than the wafer's top-left valid die - the ordinary partial DT map - the
    whole map is seated wrong and the structurally-zero shift means NOTHING corrects it.
    Measured on this fixture before the repair: 140/266, 149/266, 141/266 dies on the floor
    for the planted frame, against 266/266 once the residual is applied.

    🔴 The index axis reports 266/266 in every one of those runs, because the walk is
       translation-invariant. That is why the operator's report says the index is fine - the
       one axis that could have caught the displacement is the one axis blind to it.
    """
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _job_from(floor_meta, floor, start, 266)
    planted = "rot90_front"
    recorded = _plant(floor_meta, cells, planted)

    # THE FIXTURE MUST ACTIVATE THE DEFECT AXIS. If the job's min-index die happens to land on
    # the wafer's top-left valid die, the anchor is right by accident and this proves nothing.
    walk1 = ma.serpentine_index(
        [map_overlay._frame_transformer(floor_meta, map_overlay._grid_of(floor_meta))
         .visual_to_physical(x, y) for (x, y) in floor], top_is_min_y=True)[1]
    tfm = map_overlay._frame_transformer(floor_meta, map_overlay._grid_of(floor_meta))
    assert cells[0] != tfm.physical_to_visual(*walk1), (
        "the job's first die sits on the wafer's first die, so the anchor is right by "
        "accident and this fixture is worthless")

    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": floor_meta, "cells": recorded, "indices": ks}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    win = next(c for c in cands if c["frame"] == planted)

    assert ruling["placement"] == ma.PLACEMENT_ANCHOR
    assert win["index_agreement"] == 266, (
        "the index axis must be perfect here - it is what makes the displacement invisible")
    assert (win["shift"]["dx"], win["shift"]["dy"]) == residual, (
        "the shift must carry the translation the anchor did not account for, not 0,0: %s"
        % (win["shift"],))
    assert win["agreement"] == 266, (
        "the map is seated off the valid dies and nothing corrected it: %d of 266"
        % win["agreement"])
    # 🔴 AND THE REPAIR MUST NOT SATURATE OCCUPANCY. The first attempt at this ranked seats by
    #    occupancy and moved every candidate to a full-fit seat - all eight reached 266 and the
    #    occupancy axis died, which is exactly the saturation [3-0] withdrew the shift search
    #    over. Measured: every frame has the SAME number of full-fit seats (105/46/5), so
    #    occupancy cannot choose; only "the dies form an unbroken run of the floor's walk" can,
    #    and it admits 1 seat for the planted frame, 1 for rot270_front (a reversed run is still
    #    a run) and 0 for the other six.
    agreements = sorted(c["agreement"] for c in cands)
    assert agreements.count(266) <= 2, (
        "the residual moved candidates that had no evidence to move: %s"
        % [(c["frame"], c["agreement"]) for c in cands])


#: Origins to sweep on each side. Includes the default so the sweep contains its own control.
_ORIGINS = [(1, 1), (0, 0), (7, -4), (-6, 9), (3, -2)]


@pytest.mark.parametrize("job_start", [0, 400])
def test_no_per_map_origin_reaches_anything_the_scorer_reports(job_start):
    """「유효 다이영역은 자신의 x,y 시작을 0으로 다 맞춰두고 그 위에서 소스맵 shift 계산해야함」.

    The checkable form of that ruling: once the reference is a frame in its own right, moving
    ANY map's declared origin must not move a single number the scorer reports. This sweeps the
    two origins INDEPENDENTLY - the asymmetric case is the one that matters, because if the
    reference is rebased and the source is not, the anchor absorbs the difference and produces a
    shift that is arithmetically consistent and geometrically wrong.

    🔴 THE CONDITION IS PART OF THE ASSERTION, not an excuse dropped from it. This holds on the
       ANCHOR path, where placement is `reference_top_left + L·(cell − anchor_cell)`: the
       source's origin cancels inside the difference and the reference's origin is simply the
       space both sides are expressed in, so neither survives into a verdict. It does NOT hold
       on the `shift_search` fallback, which goes through `make_frame_transform` /
       `make_physical_transform` and reads phys and the bounding box by construction. So the
       sweep asserts `placement == anchor` first - if that ever flips, this test is measuring
       the other path and must fail rather than quietly pass.

    Measured: 25 origin pairs x 2 job shapes, 0 reported outputs moved.
    """
    ref_probe = _meta(cols=41, rows=41)
    planted = "rot90_front"

    def score(ref_start, src_start):
        ref_meta = _meta(cols=41, rows=41, start_x=ref_start[0], start_y=ref_start[1])
        floor = _valid_die_floor(ref_meta)
        cells, ks = _job_from(ref_meta, floor, job_start, 266)
        src_meta = dict(source_meta_for_frame(ref_meta, planted))
        fwd = map_overlay.make_frame_transform(ref_meta, src_meta)
        ox = src_start[0] - src_meta["grid_start_x"]
        oy = src_start[1] - src_meta["grid_start_y"]
        recorded = [(fwd(x, y)[0] + ox, fwd(x, y)[1] + oy) for (x, y) in cells]
        src_meta["grid_start_x"], src_meta["grid_start_y"] = src_start
        cands, _e, ruling, _s = ma.score_candidates(
            [{"map_id": "M1", "meta": src_meta, "cells": recorded, "indices": ks}],
            floor, ref_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
        assert ruling["placement"] == ma.PLACEMENT_ANCHOR, (
            "this assertion is scoped to the anchor path and the run took the other one (%s)"
            % ruling["anchor_reason"])
        # 🔴 2026-08-06: `shift` LEFT THIS TUPLE, and the reason is a definition change
        #    rather than a weakening. The product owner ruled the shift to be
        #    `anchor_ref − anchor_src` on RAW DATABASE COORDINATES; this fixture moves the
        #    source's stored cells by `(ox, oy)` when it moves the declared origin (see
        #    above), so a faithful raw difference MUST move with it. What must not move is
        #    anything that RANKS - the winner and the three scored axes - and that is what
        #    is asserted. Measured 2026-08-06: 0 of 25 origin pairs moved the geometry on
        #    both job shapes; 20 of 25 moved the shift, by exactly the origin delta.
        return (ruling["winner"],
                tuple((c["frame"], c["agreement"], c["index_agreement"],
                       c["index_violations"]) for c in cands))

    base = score((1, 1), (1, 1))
    moved = [(r, s) for r in _ORIGINS for s in _ORIGINS if score(r, s) != base]
    assert moved == [], (
        "a declared origin reached the verdict; the reference is not a frame in its own "
        "right yet. Origin pairs that moved a reported number: %s" % moved[:4])
    assert len(_ORIGINS) ** 2 == 25


def test_the_anchor_aims_at_the_first_valid_die_not_the_bounding_box_corner():
    """On a round wafer the valid-die area's bounding-box corner is NOT a valid die, so the two
    readings of "the area's top-left" are different coordinates. The min-index die is the first
    die the equipment touched - a die - so the anchor must read the walk's position 1.

    Measured on the 41x41 / 300mm floor: first valid die (17,1), bounding-box minimum (1,1).
    Normalizing the area to its own origin would make the bounding-box minimum (0,0); it would
    NOT make the anchor's target (0,0), and a normalization that moved the target to the corner
    would seat every job on a die that does not exist."""
    ref_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(ref_meta)
    cells, ks = _job_from(ref_meta, floor, 0, 266)
    cands, _e, _r, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta,
          "cells": _plant(ref_meta, cells, "rot90_front"), "indices": ks}],
        floor, ref_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    seat = next(c for c in cands if c["frame"] == "rot90_front")["placement"]["anchor_ref"]
    bbox_min = [min(p[0] for p in floor), min(p[1] for p in floor)]
    assert tuple(seat) in {tuple(p) for p in floor}, (
        "the anchor seated the map on %s, which is not a valid die" % (seat,))
    assert seat != bbox_min, (
        "the fixture cannot tell the two readings apart - pick a floor whose corner is empty")


def test_the_shipped_seat_is_where_the_scorer_put_the_map():
    """The screen draws `anchor_ref + linear·(cell − anchor_src)`. If the residual moves the
    scorer's placement but not `anchor_ref`, the server scores one position and the client
    draws another - and both pictures look plausible, so only the counts disagree."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _job_from(floor_meta, floor, 400, 266)
    planted = "rot90_front"

    cands, _e, _r, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": floor_meta, "cells": _plant(floor_meta, cells, planted),
          "indices": ks}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    win = next(c for c in cands if c["frame"] == planted)
    pl = win["placement"]
    floor_set = set(floor)
    drawn = [(pl["anchor_ref"][0]
              + pl["linear"][0][0] * (x - pl["anchor_src"][0])
              + pl["linear"][0][1] * (y - pl["anchor_src"][1]),
              pl["anchor_ref"][1]
              + pl["linear"][1][0] * (x - pl["anchor_src"][0])
              + pl["linear"][1][1] * (y - pl["anchor_src"][1]))
             for (x, y) in _plant(floor_meta, cells, planted)]
    assert sum(1 for p in drawn if p in floor_set) == win["agreement"], (
        "what ships must reproduce what was scored")
    # 🔴 REVERT PIN (2026-08-06): with the residual inert, `anchor_ref` IS the anchor seat.
    #    The client draws from this field since `f894a0c`, so if a future round re-enables
    #    the residual it must move this field too or the two pictures split again.
    assert tuple(pl["anchor_ref"]) == tuple(_reference_top_left(floor_meta, floor)), (
        "anchor_ref must be the reference's top-left valid die once nothing moves the seat")


def test_the_anchor_places_the_map_and_says_so():
    """「소스 조각 좌상단이 기준맵 좌상단 되게 하는게 어려움?」 - the minimum-index die is the
    first die the tool touched and the tool starts at the valid area's top-left, so the
    translation is READ rather than solved. Displace the stored coordinates by a foreign origin
    and require the anchor to recover it; the shift search cannot, because its objective is
    saturated (see `test_occupancy_is_saturated_on_that_same_partial_map`)."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _partial_job(floor_meta, floor, 266)
    planted = "rot90_front"
    recorded = [(x + 5, y - 4) for (x, y) in _plant(floor_meta, cells, planted)]

    cands, _e, ruling, stats = ma.score_candidates(
        [{"map_id": "M1", "meta": floor_meta, "cells": recorded, "indices": ks}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    assert ruling["placement"] == ma.PLACEMENT_ANCHOR
    assert ruling["anchor_reason"] is None
    by = {c["frame"]: c["agreement"] for c in cands}
    assert by[planted] == 266, by
    assert len(set(by.values())) > 1, (
        "the whole point: under the anchor, occupancy is no longer an 8-way tie: %s" % by)


# ---------------------------------------------------------------------------
# THE ORIGIN, AND THE PROPERTY THAT WOULD HAVE CAUGHT ALL FOUR SITES AT ONCE
# ---------------------------------------------------------------------------
# 🔴 EVERY OTHER FIXTURE IN THIS REPO PUTS BOTH ORIGINS AT THE SAME PLACE, AND THAT IS WHY
#    NONE OF THEM COULD SEE THIS. `_meta()` defaults to (1,1) for both sides;
#    `scripts/seed_valid_die_ref_floor.py`, `trace_fixture/world.py` and `trace_fixture/
#    frames.py` all use (0,0). When the two origins agree the alignment's translation is
#    ZERO, and a term that is zero everywhere can be dropped from four separate expressions
#    without a single test noticing. Measured 2026-08-06: it had been dropped from four.
#
# So this section varies the two origins INDEPENDENTLY. A fixture that does not is structurally
# blind here, no matter how many frames or cells it exercises.

@pytest.mark.parametrize("ref_frame", [
    {}, {"rotation": 90}, {"rotation": 180}, {"rotation": 270},
    {"side": "back"}, {"grid_y_invert": True}, {"rotation": 270, "side": "back"},
])
@pytest.mark.parametrize("planted", ["rot0_front", "rot90_front", "rot270_back"])
def test_the_floors_own_frame_does_not_displace_the_placement(ref_frame, planted):
    """THE AXIS THE 48-COMBINATION TEST DOES NOT VARY, added because a defect walked through it.

    Product owner 2026-08-06: 「특정 유효다이맵으로 하면 밀림」 - it depends on WHICH reference
    map, so the missing term is derived from the reference. Controlled comparison, one source
    map held constant against floors differing in ONE field each:

        floor rot0/front  -> 200/200      floor rot90     -> 118/200
        floor y_invert    -> 200/200      floor side=back -> 136/200

    The field is the floor's `rotation`/`side`. The anchor was aiming at the top-left of the
    floor's RENDERING instead of the wafer's canonical top-left die, and those coincide only at
    rot0/front - the same mistake, in the same file, that the index walk had already been moved
    to physical coordinates to escape. `grid_y_invert` was already correct, which is why varying
    only that axis would have kept the suite green too.

    🔴 The origin property test varies the two ORIGINS and cannot see this: a wrong placement
       round-trips to residual (0,0) quite happily. Only the agreement count catches it."""
    ref_meta = _meta(cols=41, rows=41, start_x=0, start_y=0)
    ref_meta.update(ref_frame)
    floor = _valid_die_floor(ref_meta)
    cells, ks = _partial_job(ref_meta, floor, 200)
    recorded = _plant(ref_meta, cells, planted)

    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": dict(ref_meta), "cells": recorded, "indices": ks}],
        floor, ref_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    assert ruling["winner"] == planted, (
        "floor frame %s changed which frame wins: %s" % (ref_frame, ruling["winner"]))
    win = next(c for c in cands if c["frame"] == planted)
    assert win["agreement"] == 200, (
        "the placement is displaced by the floor's own frame %s: %d of 200 cells landed on "
        "valid dies" % (ref_frame, win["agreement"]))
    assert ruling["placement"] == ma.PLACEMENT_ANCHOR


#: Cell count for the round-trip fixture. Named because the agreement assertion below compares
#: against it - a literal in both places is two spellings of one number, and they drift.
_ROUNDTRIP_CELLS = 180


def _confirm_and_rescore(ref_start, src_start, planted, n=_ROUNDTRIP_CELLS):
    """Score -> confirm -> score again with what the confirmation wrote.

    Returns `(first_ruling, first_winner_row, confirmed_meta, second_ruling, second_winner_row)`.
    Nothing about the transform is reimplemented here: both halves go through
    `score_candidates` and the confirmation goes through `confirmed_meta_for`, which is the
    function `frame_confirmation._write_confirmed_meta` calls.
    """
    ref_meta = _meta(cols=41, rows=41, start_x=ref_start[0], start_y=ref_start[1])
    floor = _valid_die_floor(ref_meta)
    cells, ks = _partial_job(ref_meta, floor, n)
    src_meta = dict(ref_meta, grid_start_x=src_start[0], grid_start_y=src_start[1])
    d = (src_start[0] - ref_start[0], src_start[1] - ref_start[1])
    recorded = [(x + d[0], y + d[1]) for (x, y) in _plant(ref_meta, cells, planted)]

    def score(meta):
        c, _e, r, _s = ma.score_candidates(
            [{"map_id": "M1", "meta": meta, "cells": recorded, "indices": ks}],
            floor, ref_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
        return r, next((x for x in c if x["frame"] == r["winner"]), None)

    r1, w1 = score(src_meta)
    confirmed = ma.confirmed_meta_for(
        src_meta, ref_meta, {"table": "vd", "map_id": "F"}, r1["winner"], {},
        (w1 or {}).get("shift"))
    r2, w2 = score(confirmed)
    return r1, w1, confirmed, r2, w2


@pytest.mark.parametrize("ref_start,src_start", [
    ((1, 1), (0, 0)), ((0, 0), (1, 1)), ((3, 7), (0, 0)), ((-2, 5), (4, -3)),
    ((0, 0), (0, 0)), ((1, 1), (1, 1)),
])
@pytest.mark.parametrize("planted", list(ma.CANDIDATE_FRAMES))
def test_a_confirmed_origin_reproduces_the_alignment_it_was_derived_from(
        ref_start, src_start, planted):
    """THE ROUND TRIP, and the property the whole origin fix exists to satisfy.

    Confirm the alignment, then score the same cells again using ONLY what the confirmation
    wrote. If the stored origin really is the origin that reproduces the alignment, the second
    scoring needs NO residual translation at all.

    🔴 A MISSING TERM AND A DOUBLED TERM BOTH BREAK THIS, which is why it replaces the four
       separate assertions it would have taken to catch the four sites individually:
       measured before the fix, the residual was the shift (term missing) or twice the shift
       (term applied once in the wrong direction and never in the right one).
    """
    r1, w1, confirmed, r2, w2 = _confirm_and_rescore(ref_start, src_start, planted)
    assert r1["winner"] == planted, "guard: the first scoring must find the planted frame"
    # 🔴 RESIDUAL ZERO IS NOT ENOUGH, and this line is here because its absence let a real
    #    defect through. The round trip reproduces whatever the first scoring did - including a
    #    WRONG placement - so a misplaced map round-trips to residual (0,0) perfectly. Measured
    #    2026-08-06: a floor declaring rot90 scored 118 of 200 cells onto valid dies and this
    #    test stayed green. The placement is only right if every cell lands.
    assert w1["agreement"] == _ROUNDTRIP_CELLS, (
        "a planted map is a true subset of the floor, so every cell must land on a valid die; "
        "%s of %s did not" % (w1["agreement"], _ROUNDTRIP_CELLS))
    assert w2 is not None and r2["winner"] == planted, (
        "the confirmed coordinate system must still score to the same frame")
    # 🔴 2026-08-06: THE REPRODUCTION IS ASSERTED ON THE SEAT, NOT ON A ZERO.
    #    This line used to read `w2["shift"] == {0, 0}`, which was the right check while
    #    `shift` MEANT "the residual correction the confirmation has now absorbed". The
    #    product owner redefined it as `anchor_ref − anchor_src` on raw DB coordinates, and
    #    a confirmation writes an ORIGIN - it does not move either map's stored cells - so
    #    that difference is unchanged by construction and can never return to zero. A test
    #    demanding zero would now be demanding that the confirmation corrupt the data.
    #    What the round trip actually promises is that the second scoring lands the map on
    #    the same dies, and THAT is asserted directly on the seat the client draws from.
    #    Measured 2026-08-06 across all 8 frames x 6 origin pairs: 48 of 48 reproduce the
    #    seat, the agreement and the shift; 0 of 48 move.
    assert w2["placement"]["anchor_ref"] == w1["placement"]["anchor_ref"], (
        "the confirmed origin seated the map somewhere else: %s -> %s"
        % (w1["placement"]["anchor_ref"], w2["placement"]["anchor_ref"]))
    assert w2["shift"] == w1["shift"], (
        "the confirmation must not move the anchor difference: %s -> %s"
        % (w1["shift"], w2["shift"]))
    assert w2["agreement"] == w1["agreement"]


def test_a_zero_shift_says_WHICH_zero_it_is():
    """「shift 0,0」 was not a symptom anyone could act on, and this pins why it now is.

    `_residual_shift` reaches `(0,0)` down four different paths and they call for four
    different repairs: the anchor seat qualified uniquely (nothing to fix); no seat
    qualified (the gates rejected everything); more than one qualified (the data could not
    choose); there were no walk ranks to ask with. The caller used to unpack three values
    and drop the third, which was the ONLY thing separating the first two, and the
    diagnostic line printed only when the residual MOVED - so giving up was silent.

    🔴 **A GATE THAT REJECTS EVERYTHING AND A GATE THAT NEVER RAN LOOK THE SAME FROM
       OUTSIDE.** That is why the counts are asserted per gate rather than as their
       conjunction. Measured on this fixture before the naming: candidates reached
       `(0,0)` with 5 seats scoring full occupancy and 0 surviving gate 2, and nothing on
       the wire or in `align.log` said so.

    ⚠️ This asserts the OBSERVABILITY, not the choice. The three qualifications are
       unchanged by this round; whether they are the right qualifications is a separate
       question with its own measurement.
    """
    floor_meta = _meta(cols=45, rows=30, start_x=3, start_y=5)
    floor = _valid_die_floor(floor_meta)
    # A job that begins well down the wafer - the case the residual search exists for.
    grid = map_overlay._grid_of(floor_meta)
    tf = map_overlay._frame_transformer(floor_meta, grid)
    w = ma.serpentine_index([tf.visual_to_physical(x, y) for (x, y) in floor],
                            top_is_min_y=True)
    job = [w[k] for k in sorted(w)[42:242]]
    planted = "rot90_front"
    stf = map_overlay._frame_transformer(
        ma.source_meta_for_frame(dict(floor_meta), planted), grid)
    cells = [stf.physical_to_visual(*p) for p in job]

    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": dict(floor_meta), "cells": cells,
          "indices": list(range(1, len(job) + 1))}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    assert ruling["placement"] == ma.PLACEMENT_ANCHOR, "guard: the anchor path must be live"

    scored = [c for c in cands if c["state"] == "scored"]
    assert scored, "guard: something must have been scored"
    for c in scored:
        r = c["residual"]
        assert isinstance(r, dict) and r.get("state"), (
            "%s shipped no residual state, so `shift: %s` is unreadable again"
            % (c["frame"], c["shift"]))
        # the gates are reported one at a time, and they nest
        assert r["gate2_unbroken_run"] <= r["gate1_on_valid_dies"] <= r["seats_scanned"]

    # 🔴 REVERTED 2026-08-06: **the zero being named is the RESIDUAL's, not the shipped
    #    shift's.** With the placement transform-only again, the shipped shift carries the
    #    anchor's real translation and is non-zero on this fixture - which is the repair,
    #    not a regression. The four-way ambiguity this vocabulary exists for was always
    #    `_residual_shift`'s own `(0,0)`; it was only ever readable on `shift` because the
    #    anchor's value was structurally zero and the two coincided.
    zeros = [c for c in scored
             if tuple(c["residual"].get("would_move") or (0, 0)) == (0, 0)]
    assert zeros, "guard: this fixture must produce at least one zero residual to name"
    named = {c["residual"]["state"] for c in zeros}
    # ⚠️ `ANCHOR_SEAT_CORRECTED` belongs in this set SINCE THE REVERT: the search still finds
    #    a seat and still says so, but the seat is not applied, so that state now coexists
    #    with a zero shift. Before the revert it could not.
    assert named <= {ma.RESIDUAL_ANCHOR_HELD, ma.RESIDUAL_NO_QUALIFYING_SEAT,
                     ma.RESIDUAL_NOT_UNIQUE, ma.RESIDUAL_NO_WALK_RANKS,
                     ma.RESIDUAL_SEAT_CAP, ma.ANCHOR_SEAT_CORRECTED}, named
    assert all(c["residual"]["applied"] is False for c in scored), (
        "the revert: observed, never applied")
    # 🔴 THE LOAD-BEARING ONE. A zero that means "gave up" must not be spelled the same as
    #    a zero that means "the anchor was right". Both occur on this fixture.
    gave_up = [c for c in zeros if c["residual"]["state"] == ma.RESIDUAL_NO_QUALIFYING_SEAT]
    assert gave_up, (
        "this fixture is supposed to contain a candidate whose seats all failed the gates; "
        "if it no longer does, the fixture stopped exercising the silent path: %s"
        % {c["frame"]: c["residual"]["state"] for c in zeros})
    # and that giving-up is distinguishable from the anchor holding
    held = [c for c in scored if c["residual"]["state"] == ma.RESIDUAL_ANCHOR_HELD]
    moved = [c for c in scored if c["residual"]["state"] == ma.ANCHOR_SEAT_CORRECTED]
    assert held or moved, (
        "no candidate held or moved; the vocabulary would be untested on its positive side")
    # the one that gave up must show WHERE it died: seats reached gate1 and none survived gate2
    worst = max(gave_up, key=lambda c: c["residual"]["gate1_on_valid_dies"])
    assert worst["residual"]["gate1_on_valid_dies"] > 0, (
        "a candidate that gave up with zero seats even reaching gate 1 cannot tell an "
        "operator whether gate 2 is too strict or the placement is simply wrong")
    assert worst["residual"]["gate2_unbroken_run"] == 0
    assert worst["residual"]["best_tied"] >= 1, (
        "occupancy saturates here, so the report must carry HOW MANY seats tie at the best "
        "score - naming one 'best seat' names an arbitrary member of a tie")


def test_a_confirmed_origin_survives_the_next_read():
    """SITE 4, asserted directly. `grid_needs_basis` used to compare the whole grid dict, so a
    map whose dimensions matched the floor and whose origin did not re-entered the borrow on
    every read and had its origin overwritten with the floor's.

    A system that writes a determined fact and overwrites it on the next pass has determined
    nothing, so this is asserted on the gate itself and not only through the round trip."""
    floor = _meta(cols=41, rows=41, start_x=1, start_y=1)
    same_dims_other_origin = _meta(cols=41, rows=41, start_x=0, start_y=0)
    assert ma.grid_needs_basis(same_dims_other_origin, floor) is False
    assert map_overlay.assume_grid_from(
        same_dims_other_origin, floor, {"table": "vd", "map_id": "F"}) is None


#: The editor's origin box is NOT square and NOT centred once the two chip pitches differ,
#: which is what makes `box.minC` and `box.minR` different numbers. A fixture with
#: `chip_x == chip_y` kills that axis, and this repository has already shipped a swap defect
#: under exactly that fixture (memory 2026-07-26). The wafer is also smaller than the grid so
#: `box.minC`/`box.minR` are both non-zero - a box that starts at 0 makes a dropped box term
#: invisible.
PHYS_XY = {"phys_wafer_dia": 200.0, "phys_chip_x": 5.0, "phys_chip_y": 8.0,
           "phys_offset_x": 0.5, "phys_offset_y": -0.3, "phys_edge_margin": 3.0}


def _editor_cell(meta, box, x, y):
    """`client2/src/map_editor.js:2012-2029` READ LITERALLY, inverted for (col, row).

    🔴 This is an ORACLE, so it must not call anything the code under test calls. It does not
       use `visual_to_cell`, `make_frame_transform`, or any server helper that could carry the
       same mistake - it is the three lines from the other side of the seam and nothing else.
    ⚠️ The `invertY` branch reads `box.maxR` where the plain branch reads `box.minR`. The y
       half is NOT the x half mirrored, so it is written out rather than derived.
    """
    c = x - meta["grid_start_x"] + box[0]                       # box = (minC, maxC, minR, maxR)
    r = (box[3] - (y - meta["grid_start_y"]) if meta.get("grid_y_invert")
         else y - meta["grid_start_y"] + box[2])
    return c, r


def _oracle_origin_box(meta, die_mask=None):
    """The origin box `map_editor.js:1896-2010` produces, WALKED THE OTHER WAY ROUND.

    Production (`map_overlay.origin_box`) walks the grid forward and asks each cell whether its
    die is in the mask (`cell_to_physical`, which is what the editor's loop does). This oracle
    walks the MASK and asks where each die lands (`physical_to_cell`), then clips to the grid.
    Same box, opposite direction, so a transposed axis or a dropped `back` flip in one of the
    two shows up as a disagreement instead of cancelling.

    🔴 THE STRONGER CHECK IS NOT IN PYTHON AT ALL. Both of these are still readings of the
       editor rather than the editor. `server/tests/oracle/editor_origin_box_oracle.mjs` slices
       `getWaferBoundingBox` out of the shipped `map_editor.js` and runs it; measured 2026-08-06
       over 32 combinations (8 frames x invertY x two origins, mask 578 of 677 dies) the server
       agreed with the editor on the CIRCLE box in 32 of 32 and on the MASK box in 32 of 32,
       while the two boxes themselves differed in 32 of 32 - so neither count came from the
       branches quietly agreeing. Re-run it before trusting this transcription again.
    """
    tf = map_overlay._frame_transformer(meta, map_overlay._grid_of(meta))
    if not die_mask:
        return tf.get_wafer_bounding_box()
    seats = [tf.physical_to_cell(px, py) for (px, py) in die_mask]
    seats = [(c, r) for (c, r) in seats
             if 0 <= c < tf.visual_cols and 0 <= r < tf.visual_rows]
    if not seats:                       # the editor's `maskCount === 0` branch
        return tf.get_wafer_bounding_box()
    return (min(c for c, _ in seats), max(c for c, _ in seats),
            min(r for _, r in seats), max(r for _, r in seats))


def _editor_die(meta, x, y, die_mask=None):
    """The die the legacy editor draws stored (x, y) on, under `meta`.

    `die_mask` is the valid-die set this map's `valid_die_ref` resolves to, or None when it
    declares none - i.e. the two branches of `maskDeclaresTheFrame` (`map_editor.js:1942`),
    which is the ONE thing that decides which box the arithmetic above stands on.
    """
    tf = map_overlay._frame_transformer(meta, map_overlay._grid_of(meta))
    return tf.cell_to_physical(*_editor_cell(meta, _oracle_origin_box(meta, die_mask), x, y))


def _partial_floor(floor_meta, floor):
    """A valid-die reference that is a STRICT, ASYMMETRIC subset of its own wafer circle.

    🔴 THE FULL DISC CANNOT SEE THIS ROUND'S DEFECT AND `_valid_die_floor` IS A FULL DISC.
       Measured 2026-08-06: with the whole circle as the reference, the mask box equals the
       circle box on all eight frames, so the branch under test is a no-op and a test built on
       it is green whichever box the server picks. Two bands are bitten out on DIFFERENT axes
       so the two boxes disagree on both, and asymmetrically enough that rotating the frame
       moves the disagreement rather than carrying it along.
    """
    tf = map_overlay._frame_transformer(floor_meta, map_overlay._grid_of(floor_meta))
    out = []
    for (x, y) in floor:
        px, py = tf.visual_to_physical(x, y)
        if px <= 8 or py <= 5:
            continue
        out.append((x, y))
    return sorted(out)


@pytest.mark.parametrize("planted", list(ma.CANDIDATE_FRAMES))
@pytest.mark.parametrize("src_inv", [False, True])
@pytest.mark.parametrize("floor_kind", ["disc", "partial"])
def test_the_written_start_is_where_the_editor_redraws_it(planted, src_inv, floor_kind):
    """THE OPERATOR'S CRITERION, AND THE ONLY ONE. 「서버에서 만점이라고 한 거 저장하고
    편집기 띄워 보면 틀어져 있는데」 · 「x, y 다 틀어지는데」.

    A run the scorer calls perfect must open in the legacy editor with every cell on the die
    the scorer put it on. `grid_start_x/y` is the entire handoff, so this asserts the handoff
    and not the algebra behind it.

    🔴 **NOT A ROUND TRIP.** The test this replaces asserted that the written start and the
       anchor pair agree - but it rebuilt the translation out of the written start itself
       (`tx = start - floor_start`), so it reduced to `t == t` and passed for ANY start. It was
       green while every cell drew displaced. Round trips prove nothing on this path:
       `getDbCoords` and its inverse are exact inverses under any box, including a wrong one.
       The oracle here comes from the OTHER side of the seam (`_editor_die`), so a mistake
       shared by both server derivations cannot hide in it.

    🔴 **THE FIXTURE ACTIVATES EVERY AXIS THE DEFECT NEEDS**, and the parametrisation covers
       rotation 90/270 and `back` rather than sampling one frame that happens to work:
       `chip_x != chip_y` · wafer smaller than the grid so `box.minC`/`box.minR` are non-zero
       and unequal · `grid_y_invert` on the source so the `box.maxR` branch runs · the floor's
       origin non-zero on both axes · the source's own origin different from the floor's on
       both axes. Measured before the repair: **240 of 240 cells on the wrong die, displaced a
       uniform (4, 3)** - both axes, the invisible kind.

    🔴 **THE BOX BRANCH IS INSIDE THIS ASSERTION NOW** (2026-08-06). It used not to be, and
       the note that stood here said so: the editor's origin box becomes the valid-die MASK box
       when the map's `valid_die_ref` resolves, and confirmation then began writing
       `valid_die_ref` onto every source map - which turned that branch on for exactly the maps
       this test is about. `floor_kind` is that axis:
         · `disc`    - the reference is the whole wafer circle. The mask box and the circle box
                       are then THE SAME BOX on all eight frames, so this leg pins the circle
                       reading and proves the repair changed nothing where nothing should change.
         · `partial` - the reference is a strict subset (`_partial_floor`), the two boxes differ,
                       and the origin has to follow the mask. Measured before the repair: the
                       written origin moved on **12 of 16** frame/invertY combinations and
                       **1,440 of 1,920** cells opened on the wrong die. `_the_defect_is_reachable`
                       below re-measures that on every run rather than restating it.
    ⚠️ Still out of reach here: a reference that itself declares a `valid_die_ref` (a two-step
       chain), and the `elif shift` branch of `confirmed_meta_for`, whose derivation reads only
       the linear part and so cannot carry a box correction at all. Both reported, neither fixed.
    """
    floor_meta = dict(_meta(cols=45, rows=30, start_x=3, start_y=5), **PHYS_XY)
    floor = _valid_die_floor(floor_meta)
    if floor_kind == "partial":
        floor = _partial_floor(floor_meta, floor)
    cells, ks = _partial_job(floor_meta, floor, 120)
    # The mask the EDITOR will hold once this confirmation writes `valid_die_ref`: the
    # reference's dies, in the frame-independent physical space `isValidDieAt` keys on.
    ftf = map_overlay._frame_transformer(floor_meta, map_overlay._grid_of(floor_meta))
    die_mask = frozenset(ftf.visual_to_physical(x, y) for (x, y) in floor)

    # The physical truth nobody has declared: the job ran in `planted`, with its own y-invert
    # and its own origin. `+5,-4` on stored coordinates IS an origin difference (the origin is a
    # pure translation of stored coordinates), and it is the term the retired derivations lost.
    src_true = dict(floor_meta)
    src_true.update(dict(zip(("rotation", "side"), parse_frame(planted))),
                    grid_y_invert=src_inv,
                    grid_start_x=floor_meta["grid_start_x"] + 5,
                    grid_start_y=floor_meta["grid_start_y"] - 4)
    fwd = map_overlay.make_frame_transform(floor_meta, src_true)
    recorded = [fwd(x, y) for (x, y) in cells]

    # What the database actually holds for this map: no frame, the floor's origin.
    stored = dict(floor_meta, grid_y_invert=src_inv)

    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": dict(stored), "cells": recorded, "indices": ks}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    win = next(c for c in cands if c["frame"] == ruling["winner"])
    assert win["agreement"] == len(recorded), (
        "the fixture must be a run the server calls PERFECT before the handoff is judged; "
        "got %d/%d on %s" % (win["agreement"], len(recorded), ruling["winner"]))
    assert ruling.get("anchor") == win["placement"], (
        "the anchor pair reaches confirm by riding `ruling`, which the screen transcribes "
        "whole; if it stops being attached the write silently falls back to the shift branch")

    written = ma.confirmed_meta_for(
        dict(stored), floor_meta, {"table": "valid_die_ref", "map_id": "F"},
        ruling["winner"], {"confirmation_uid": "U", "confirmed_by": "t"},
        ruling.get("shift"), placement=ruling.get("anchor"), basis_cells=floor)
    assert written is not None
    assert map_overlay.parse_valid_die_ref(written)[0] is not None, (
        "this test's whole premise is that confirmation hands the editor a valid-die "
        "reference; if it stops writing one, the mask branch is unreachable and the `partial` "
        "leg is asserting nothing")

    L, a_src, a_ref = (win["placement"]["linear"], win["placement"]["anchor_src"],
                       win["placement"]["anchor_ref"])

    def _placed(x, y):
        return (a_ref[0] + L[0][0] * (x - a_src[0]) + L[0][1] * (y - a_src[1]),
                a_ref[1] + L[1][0] * (x - a_src[0]) + L[1][1] * (y - a_src[1]))

    def _displaced(meta, mask):
        # The reference is read on its CIRCLE box on both sides: `anchor_ref` was produced in
        # that coordinate system by the scorer, and a valid-die map declares no reference of
        # its own. Moving it here would move the yardstick, not the measurement.
        return [((x, y), _editor_die(meta, x, y, mask), _editor_die(floor_meta, *_placed(x, y)))
                for (x, y) in recorded
                if _editor_die(meta, x, y, mask) != _editor_die(floor_meta, *_placed(x, y))]

    displaced = _displaced(written, die_mask)
    assert not displaced, (
        "%d of %d cells open in the editor on a different die than the alignment put them on "
        "(dx=%d, dy=%d on the first one). written start=(%s, %s), the source actually ran at "
        "(%s, %s). floor=%s, box=%s vs circle %s."
        % (len(displaced), len(recorded),
           displaced[0][2][0] - displaced[0][1][0], displaced[0][2][1] - displaced[0][1][1],
           written["grid_start_x"], written["grid_start_y"],
           src_true["grid_start_x"], src_true["grid_start_y"], floor_kind,
           _oracle_origin_box(written, die_mask), _oracle_origin_box(written)))

    # ── THE ALARM, RUNG WHERE IT CAN RING ───────────────────────────────────────────
    # A green result above means nothing unless the same fixture can produce a red one, so the
    # PRE-REPAIR computation is run on the same inputs and scored.
    #
    # 🔴 IT CANNOT RING ON EVERY COMBINATION, AND SAYING OTHERWISE WOULD BE THE SAME MISTAKE
    #    THE RETIRED DERIVATIONS MADE. Measured: on 4 of the 16 frame/invertY combinations the
    #    box difference cancels in the origin and the circle-box answer is already right. An
    #    assertion that demanded a red on all 16 would have been asserting something false -
    #    which is exactly how `floor_start - t` came to be believed on the strength of the 4 of
    #    32 where it happened to work. So the alarm is asserted CONDITIONALLY here, and the
    #    census - which combinations move, and that the set is not empty - is a separate
    #    assertion over the whole space (`test_the_mask_box_defect_is_reachable`).
    blind = ma.confirmed_meta_for(
        dict(stored), floor_meta, {"table": "valid_die_ref", "map_id": "F"},
        ruling["winner"], {"confirmation_uid": "U", "confirmed_by": "t"},
        ruling.get("shift"), placement=ruling.get("anchor"), basis_cells=None)
    boxes_differ = _oracle_origin_box(written, die_mask) != _oracle_origin_box(written)
    moved = ((blind["grid_start_x"], blind["grid_start_y"])
             != (written["grid_start_x"], written["grid_start_y"]))
    if floor_kind == "disc":
        assert not boxes_differ, (
            "a full-disc reference must give the same box on both branches; if it stops "
            "doing so this leg is no longer the control it claims to be")
        assert not moved, (
            "the repair moved an origin on the circle branch, which is the half of this "
            "change that must be a no-op")
    else:
        assert boxes_differ, (
            "the `partial` fixture stopped separating the two boxes on %s/inv=%s, so this leg "
            "is exercising nothing: %s" % (planted, src_inv, _oracle_origin_box(written)))
        if moved:
            assert _displaced(blind, die_mask), (
                "the origin moved on %s/inv=%s, so the old one must be visibly wrong under the "
                "box the editor actually uses; if it is not, the two are not the same claim"
                % (planted, src_inv))


#: The combinations on which the valid-die mask box moves the confirmed origin, on the fixture
#: `test_the_mask_box_defect_is_reachable` builds. MEASURED 2026-08-06, not reasoned.
#:
#: 🔴 THE MEMBERS ARE PINNED, NOT THE COUNT. "12 of 16" is a number a fixture change can keep
#:    while swapping WHICH twelve, and the four that do NOT move are the whole reason this
#:    census exists: on those four the circle-box answer is already right, so a test that only
#:    ever sampled one of them would call the defect fixed before it was.
MASK_BOX_MOVES_THE_ORIGIN = frozenset({
    ("rot0_front", False), ("rot0_front", True), ("rot0_back", False),
    ("rot90_front", False), ("rot90_back", True),
    ("rot180_front", True), ("rot180_back", False), ("rot180_back", True),
    ("rot270_front", False), ("rot270_front", True),
    ("rot270_back", False), ("rot270_back", True),
})


def test_the_mask_box_defect_is_reachable():
    """THE CENSUS. Sweeps the whole combination space once and states, in one place, what the
    box branch is worth: which combinations the origin moves on, that the set is not empty, and
    that after the repair NO cell is displaced anywhere in the space.

    🔴 WITHOUT THIS, THE PARAMETRISED TEST ABOVE COULD BE GREEN ON A DEAD AXIS. Each of its
       cases can only see its own combination, so none of them can notice that the fixture
       stopped separating the two boxes everywhere at once. This one can, and it is the
       assertion that would go red if `_partial_floor` were ever softened back towards the disc.
    ⚠️ EVERY NUMBER HERE IS SYNTHETIC and authored by the server agent; the reference shape is
       a fixture, not a production measurement. What is measured is the RELATION between two
       server computations and an editor-derived box, which is what this round is about.
    """
    floor_meta = dict(_meta(cols=45, rows=30, start_x=3, start_y=5), **PHYS_XY)
    floor = _partial_floor(floor_meta, _valid_die_floor(floor_meta))
    cells, ks = _partial_job(floor_meta, floor, 120)
    ftf = map_overlay._frame_transformer(floor_meta, map_overlay._grid_of(floor_meta))
    die_mask = frozenset(ftf.visual_to_physical(x, y) for (x, y) in floor)

    moved, before, after, total = set(), 0, 0, 0
    for planted in ma.CANDIDATE_FRAMES:
        for inv in (False, True):
            src_true = dict(floor_meta)
            src_true.update(dict(zip(("rotation", "side"), parse_frame(planted))),
                            grid_y_invert=inv,
                            grid_start_x=floor_meta["grid_start_x"] + 5,
                            grid_start_y=floor_meta["grid_start_y"] - 4)
            recorded = [map_overlay.make_frame_transform(floor_meta, src_true)(x, y)
                        for (x, y) in cells]
            stored = dict(floor_meta, grid_y_invert=inv)
            cands, _e, ruling, _s = ma.score_candidates(
                [{"map_id": "M1", "meta": dict(stored), "cells": recorded, "indices": ks}],
                floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
            win = next(c for c in cands if c["frame"] == ruling["winner"])
            args = (dict(stored), floor_meta, {"table": "valid_die_ref", "map_id": "F"},
                    ruling["winner"], {"confirmation_uid": "U", "confirmed_by": "t"},
                    ruling.get("shift"))
            new = ma.confirmed_meta_for(*args, placement=ruling.get("anchor"),
                                        basis_cells=floor)
            old = ma.confirmed_meta_for(*args, placement=ruling.get("anchor"),
                                        basis_cells=None)
            if (old["grid_start_x"], old["grid_start_y"]) != (new["grid_start_x"],
                                                              new["grid_start_y"]):
                moved.add((ruling["winner"], inv))

            L, a_src, a_ref = (win["placement"]["linear"], win["placement"]["anchor_src"],
                               win["placement"]["anchor_ref"])
            for (x, y) in recorded:
                placed = (a_ref[0] + L[0][0] * (x - a_src[0]) + L[0][1] * (y - a_src[1]),
                          a_ref[1] + L[1][0] * (x - a_src[0]) + L[1][1] * (y - a_src[1]))
                seat_ref = _editor_die(floor_meta, *placed)
                total += 1
                if _editor_die(old, x, y, die_mask) != seat_ref:
                    before += 1
                if _editor_die(new, x, y, die_mask) != seat_ref:
                    after += 1

    assert moved == MASK_BOX_MOVES_THE_ORIGIN, (
        "the set of combinations the mask box moves the origin on changed. Gained %s, lost %s. "
        "If that is intended, re-measure and update the constant; if it is not, the fixture or "
        "the box branch moved under this test."
        % (sorted(moved - MASK_BOX_MOVES_THE_ORIGIN),
           sorted(MASK_BOX_MOVES_THE_ORIGIN - moved)))
    assert before > 0, (
        "the circle-box origin drew every cell correctly on all 16 combinations, so this "
        "fixture no longer contains the defect and nothing below it means anything")
    assert after == 0, (
        "%d of %d cells still open on the wrong die after the repair (was %d)"
        % (after, total, before))


def test_the_stored_start_is_not_on_the_wire():
    """「화면에 표시하지는 않되 저장은 하기」. A derived number sitting beside the anchor pair
    would make an operator arbitrate between two correct values, which is worse than showing
    neither. It is written to the metadata and the record; it does not ship for display."""
    floor_meta = _meta(cols=41, rows=41, start_x=3, start_y=-2)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _partial_job(floor_meta, floor, 80)
    cands, _e, _r, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": dict(floor_meta),
          "cells": _plant(floor_meta, cells, "rot90_front"), "indices": ks}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    for c in cands:
        assert set((c.get("placement") or {})) <= {"linear", "anchor_src", "anchor_ref"}, (
            "the placement carries what reconstructs it and nothing derived from that")
        assert "grid_start_x" not in c and "start_x" not in c


# ---------------------------------------------------------------------------
# PLACEMENT ON THE SEARCH PATH - the screen could not draw what the scorer scored
# ---------------------------------------------------------------------------
# Live payload 2026-08-08 (`dt_frame_confrimation`, DT-EQP-02_20260512T0000_T09 against
# `valid_die_ref/QA_MAP2`): 72 source cells on the wire, `dt_index` resolved as a column,
# every value NULL -> `index_axis: absent`, `anchor: null`, `placement: shift_search`. All
# eight candidates carried a shift and a value_agreement of 51..72, and all eight carried
# `placement: null`. The product owner: "값축으로 계산했으니 소스맵이 뜨긴해야하는거 아니야?"
# The material existed; the gate was on the anchor rather than on the drawable form.
#
# The reconstruction below is the CLIENT'S formula (`main.js` `placementFor`/`seatingFor`),
# written out here rather than imported, because the assertion is that the server's numbers
# survive the trip through that formula. Presence of a placement proves nothing - one that
# draws the map in the wrong place is worse than none - so every assertion here is a COUNT.

def _seats_from_placement(placement, cells):
    """`placed = anchor_ref + linear*(cell - anchor_src)`, applied the way the screen does."""
    L = placement["linear"]
    ax, ay = placement["anchor_src"]
    rx, ry = placement["anchor_ref"]
    return [(rx + L[0][0] * (x - ax) + L[0][1] * (y - ay),
             ry + L[1][0] * (x - ax) + L[1][1] * (y - ay)) for (x, y) in cells]


# 🔴 THE OFFSET IS NOT DECORATION. At offset (0,0) the search saturates and settles on
#    `(0,0)` for all eight candidates - measured - so a placement that DROPPED the shift
#    entirely would reproduce every count and this test would certify it. The offset fixture
#    is the one where the shift is a real number (measured: dx,dy in {-3,+3}, occupancy 196
#    of 266), and it is the only reason the "plus the shift exactly as scoring applied it"
#    half of the contract is under test at all.
@pytest.mark.parametrize("offset", [(0, 0), (5, -4)])
@pytest.mark.parametrize("planted", list(ma.CANDIDATE_FRAMES))
def test_the_screen_can_draw_when_no_die_carries_an_index(planted, offset):
    """THE REPORTED CASE. No index anywhere, so the anchor never stands and the shift is
    searched - and that is exactly the run where the screen was handed nothing to draw with.

    The real assertion is the last two: the client's own formula, fed the server's three
    numbers, must reproduce the candidate's OWN occupancy and value counts. If the pivot or
    the shift were re-derived rather than taken from where scoring seated the cell, the
    picture would still look plausible and only these counts would disagree."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    floor_set = set(floor)
    cells, _ks = _partial_job(floor_meta, floor, 266)
    src_vals = _unique_values(cells)
    recorded = [(x + offset[0], y + offset[1])
                for (x, y) in _plant(floor_meta, cells, planted)]
    ref_val_at = dict(zip(floor, _unique_values(floor)))

    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": floor_meta, "cells": recorded, "values": src_vals}],
        floor, floor_meta, reference_values=_unique_values(floor),
        thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)

    # ⓐ The fixture must actually be on the branch under test. Without this the test can go
    #    green by taking the anchor path and never touching a line that was written today.
    assert ruling["anchor"] is None and ruling["placement"] == ma.PLACEMENT_SEARCH, ruling
    assert ruling["index_axis"] == ma.INDEX_AXIS_ABSENT, ruling
    # ⓑ And the shift term must be live on the offset fixture, or the "plus the shift" half
    #    of the contract is not being tested here (see the note above the parametrize).
    if offset != (0, 0):
        assert any(c["shift"] != {"dx": 0, "dy": 0} for c in cands), (
            "every candidate settled on a zero shift, so this fixture no longer exercises "
            "the shift term: %s" % [c["shift"] for c in cands])

    for c in cands:
        p = c["placement"]
        assert p is not None, (
            "%s scored %s dies and told the screen nothing to draw with"
            % (c["frame"], c["placed"]))
        assert sorted(p) == ["anchor_ref", "anchor_src", "linear"]
        seats = _seats_from_placement(p, recorded)
        assert len(seats) == c["placed"]
        assert sum(1 for s in seats if s in floor_set) == c["agreement"], (
            "%s: the drawn map does not sit where the scorer scored it" % c["frame"])
        assert sum(1 for s, v in zip(seats, src_vals)
                   if s in floor_set and ma.values_equal(ref_val_at.get(s), v)) \
            == c["value_agreement"], (
            "%s: value agreement %s is not reproducible from the shipped placement"
            % (c["frame"], c["value_agreement"]))


# 🔴 `rot0_front` is NOT in this list and its absence is the point: there the walk's first die
#    IS the minimum-(y, x) die, so the two pivot rules coincide and the fixture guard below
#    fails rather than pass vacuously. The frames kept here are the ones where they disagree.
@pytest.mark.parametrize("planted", ["rot90_front", "rot180_front", "rot270_back"])
def test_the_index_path_still_pivots_on_the_minimum_index_die(planted):
    """THE THING THAT MUST NOT MOVE. Two rules now answer "which cell is the pivot", and only
    one of them may run when an index exists - the minimum-index die, because on that path the
    pivot DECIDES the translation (`anchor_ref - anchor_src`) instead of merely naming a point
    the reconstruction hangs off.

    🔴 The fixture asserts the two rules DISAGREE here. If minimum-index and minimum-(y,x)
       happened to be the same cell, this test would pass against a version that had wired the
       search pivot into the index path, which is the one regression it exists to catch."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    floor_set = set(floor)
    cells, ks = _partial_job(floor_meta, floor, 266)
    recorded = _plant(floor_meta, cells, planted)

    i_min = min(range(len(ks)), key=lambda i: ks[i])
    by_index = tuple(recorded[i_min])
    by_yx = min(recorded, key=lambda c: (c[1], c[0]))
    assert by_index != by_yx, (
        "%s: the two pivot rules agree on this fixture, so it cannot tell them apart"
        % planted)

    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": floor_meta, "cells": recorded, "indices": ks}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)

    assert ruling["anchor"] is not None, ruling
    for c in cands:
        p = c["placement"]
        assert p is not None
        assert tuple(p["anchor_src"]) == by_index, (
            "%s: the index path pivoted on %s, not on the minimum-index die %s"
            % (c["frame"], p["anchor_src"], list(by_index)))
        seats = _seats_from_placement(p, recorded)
        assert sum(1 for s in seats if s in floor_set) == c["agreement"]


def test_the_search_pivot_refuses_two_maps():
    """One placement is one triple, and two source maps have their own metas - hence their own
    linear part and their own affine offset. A triple that describes one of them draws the other
    in the wrong place, silently, so the rule refuses rather than picks. `anchor_cell_of` carries
    the same restriction; this is the point where BOTH would have to be relaxed together."""
    one = {"_use": [(3, 4), (5, 6)]}
    two = {"_use": [(7, 8)]}
    assert ma.search_pivot_of([one]) == (0, 0, (3, 4))
    assert ma.search_pivot_of([one, two]) is None
    assert ma.search_pivot_of([one, {"_use": []}]) == (0, 0, (3, 4)), (
        "a map with no usable cells is skipped by the scoring loop and must not count here")
    assert ma.search_pivot_of([]) is None
    # Minimum (y, x): the top row wins first, and x breaks the tie within it - so (2, 1)
    # beats both (9, 1) on its row and (0, 2) on the row below, despite the smaller x.
    assert ma.search_pivot_of([{"_use": [(9, 1), (0, 2), (2, 1)]}]) == (0, 2, (2, 1))


# 🔴 RETIRED 2026-08-06 with its reason on the record, the way [D5] was.
#    `test_the_derived_start_is_the_same_under_all_eight_frames` asserted that the
#    derived origin is identical under all eight frames - true of a placement that
#    solved a shift against the map's own origin, and meaningless once placement became
#    anchor-plus-differences and stopped reading that origin at all. The rule was not
#    wrong; it described a mechanism that no longer exists, so it is retired rather than
#    patched, and `test_the_stored_start_reconstructs_the_placement` states what is true
#    now. Kept as a comment so the argument can be re-derived if the mechanism returns.

@pytest.mark.parametrize("src_inv", [False, True])
@pytest.mark.parametrize("dst_inv", [False, True])
def test_the_linear_part_matches_the_transform(src_inv, dst_inv):
    """THE ORACLE FOR HAND-WRITTEN ALGEBRA. `frame_linear_part` composes the linear map from
    declared axes alone; `make_frame_transform` derives it through the whole phys/box stack.
    They must agree on every axis combination.

    🔴 `grid_y_invert = True` IS THE CASE THAT MATTERS AND EVERY OTHER FIXTURE HERE HAS IT
       FALSE. It inverts WHICH FRAMES ARE MIRRORS - with src invert on, `rot0_front` becomes a
       reflection and `rot0_back` becomes rotation-only. A suite that only ever ran it false is
       the same control that hid this: it cannot tell a correct composition from one that drops
       the reflection entirely."""
    CELLS = [(5, 7), (6, 7), (9, 7), (9, 8), (2, 11), (20, 3), (33, 26)]
    src = _meta(cols=41, rows=41, start_x=0, start_y=0)
    src["grid_y_invert"] = src_inv
    tgt = _meta(cols=41, rows=41, start_x=0, start_y=0)
    tgt["grid_y_invert"] = dst_inv

    for frame in ma.CANDIDATE_FRAMES:
        sm = source_meta_for_frame(src, frame)
        L = map_overlay.frame_linear_part(sm, tgt)
        tf = map_overlay.make_frame_transform(sm, tgt)
        a = tf(*CELLS[0])
        for (x, y) in CELLS:
            want = tf(x, y)
            got = (a[0] + L[0][0] * (x - CELLS[0][0]) + L[0][1] * (y - CELLS[0][1]),
                   a[1] + L[1][0] * (x - CELLS[0][0]) + L[1][1] * (y - CELLS[0][1]))
            assert want == got, (
                "%s srcInv=%s dstInv=%s cell=%s: the declared-axis composition and the "
                "transform disagree" % (frame, src_inv, dst_inv, (x, y)))


def test_y_invert_inverts_which_frames_are_mirrors():
    """The finding itself, pinned. A client that suppresses `invertY` does not lose a flag - it
    gets the mirror SET backwards, which is why `front` reads correct and `back` displaced on a
    symmetric map, and why the error grows with distance from the mirror axis while cells on the
    anchor's own row look fine."""
    def mirrors(inv):
        out = set()
        src = _meta(cols=41, rows=41, start_x=0, start_y=0)
        src["grid_y_invert"] = inv
        tgt = _meta(cols=41, rows=41, start_x=0, start_y=0)
        for frame in ma.CANDIDATE_FRAMES:
            L = map_overlay.frame_linear_part(source_meta_for_frame(src, frame), tgt)
            if L[0][0] * L[1][1] - L[0][1] * L[1][0] == -1:
                out.add(frame)
        return out

    a, b = mirrors(False), mirrors(True)
    assert a and b and a.isdisjoint(b), (
        "y-invert must swap the mirror set entirely, not merely alter it: %s vs %s" % (a, b))
    assert "rot0_front" in b and "rot0_back" in a


def test_adjacency_cannot_tell_the_eight_frames_apart():
    """A FACT ABOUT THE PROBLEM, pinned so no future diagnostic re-learns it the hard way.

    The eight candidates are isometries of the stored-coordinate lattice - four rotations times
    two mirrors - and an isometry preserves distance by definition. So EVERY statistic derived
    from distances between cells is identical across all eight: neighbour distance, adjacency
    counts, clustering, perimeter.

    Measured by the client lane 2026-08-06 across all eight: mean neighbour distance identical
    to three decimals, one value; orientation signatures 8 of 8 distinct on the same data. Their
    first oracle scored adjacency and only a negative control caught that it was scoring nothing.

    An assertion here costs nothing and makes the trap loud on the server side too."""
    ref_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(ref_meta)
    cells, _ks = _partial_job(ref_meta, floor, 200)

    def mean_neighbour_distance(pts):
        s = set(pts)
        # distance to the nearest other cell, averaged - the cheapest adjacency statistic
        # and representative of the whole family
        import math
        tot = 0.0
        for (x, y) in pts:
            best = min((math.hypot(x - a, y - b) for (a, b) in s if (a, b) != (x, y)),
                       default=0.0)
            tot += best
        return round(tot / max(1, len(pts)), 3)

    seen = {mean_neighbour_distance(_plant(ref_meta, cells, f))
            for f in ma.CANDIDATE_FRAMES}
    assert len(seen) == 1, (
        "if adjacency ever separates the eight, the isometry argument is wrong and every "
        "diagnostic resting on it needs revisiting: %s" % seen)

    # and the axis that IS built for this separates them completely, on the same data
    walks = {f: tuple(ma.serpentine_index(_plant(ref_meta, cells, f)).items())
             for f in ma.CANDIDATE_FRAMES}
    assert len(set(walks.values())) == 8, "the walk order is a non-isometric quantity"


# ---------------------------------------------------------------------------
# DIRECTION - the walk's steps, not just its order
# ---------------------------------------------------------------------------
# Order agreement only sees ORDER. With few cells several frames produce the same order, and the
# ruling is an honest `tie` with no winner. The DIRECTION of each step separates them, and the
# floor is what says which direction is legal.

def _floor_row_probe():
    """A floor plus a mid-wafer row: (meta, floor, y, sorted xs in that row)."""
    m = _meta(cols=41, rows=41, start_x=0, start_y=0)
    floor = _valid_die_floor(m)
    rows = {}
    for (x, y) in floor:
        rows.setdefault(y, set()).add(x)
    y = sorted(rows)[len(rows) // 2]
    return m, floor, y, sorted(rows[y])


def _score_pair(meta, floor, cells, ks):
    c, _e, r, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": dict(meta), "cells": list(cells), "indices": list(ks)}],
        floor, meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    top = max(x["index_agreement"] for x in c)
    on_order = [x["frame"] for x in c if x["index_agreement"] == top]
    least = min(x["index_violations"] for x in c if x["index_agreement"] == top)
    after = [x["frame"] for x in c if x["index_agreement"] == top
             and x["index_violations"] == least]
    return c, r, on_order, after


def test_direction_narrows_a_tie_that_order_alone_cannot():
    """THE TWO-CELL CASE, BOTH WAYS. Measured before this axis existed: a horizontal pair left
    FOUR frames tied at 2/2 with `reason=tie` and no winner, because order is all that order
    agreement can see. Direction halves it."""
    m, floor, y, xs = _floor_row_probe()
    x0 = xs[len(xs) // 2]

    _c, r, on_order, after = _score_pair(m, floor, [(x0, y), (x0 + 1, y)], [1, 2])
    assert on_order == sorted(["rot0_front", "rot180_back", "rot270_front", "rot270_back"]) \
        or set(on_order) == {"rot0_front", "rot180_back", "rot270_front", "rot270_back"}, on_order
    assert set(after) == {"rot0_front", "rot180_back"}, (
        "direction must eliminate the two frames whose step is not rightward: %s" % after)

    # 🔴 AND IT HONESTLY STOPS THERE. `rot0_front` and `rot180_back` are the two frames that
    #    map a rightward step to a rightward step - a real symmetry of a single horizontal
    #    step, not a scorer defect. Forcing a winner out of it would be the confident wrong
    #    answer this module refuses everywhere else.
    assert r["reason_code"] == ma.RULING_TIE and r["winner"] is None


def test_direction_decides_when_the_step_leaves_the_serpentine():
    """The separation is demonstrably NEW: the wrap happens at the END of the floor's row,
    which is the only place a downward step is licensed.

    🔴 THE FIXTURE MUST OBEY THE ANCHOR'S PREMISE. An earlier version put index 1 in the middle
    of a middle row, and it passed only because the direction judge used to read the source's
    UN-anchored coordinates. Once the judge reads the placement - which is where the anchor says
    those dies actually sit - a map whose index 1 is not the floor's first valid die is not a
    map the anchor can place, and the fixture was asserting against a state production cannot
    reach. So this walks the floor's real first row and wraps into the second."""
    m, floor, _y, _xs = _floor_row_probe()
    rows = {}
    for (x, yy) in floor:
        rows.setdefault(yy, set()).add(x)
    y0, y1 = sorted(rows)[0], sorted(rows)[1]
    row0 = sorted(rows[y0])
    row1 = sorted(rows[y1], reverse=True)      # serpentine reverses on the second row
    cells = [(x, y0) for x in row0] + [(row1[0], y1)]
    c, r, on_order, after = _score_pair(m, floor, cells, list(range(1, len(cells) + 1)))
    assert len(on_order) > 1, "guard: order alone must still tie, or nothing is being shown"
    assert after == ["rot0_front"]
    assert r["winner"] == "rot0_front"
    assert r["decided_by"] == "direction", (
        "the ruling must say WHICH axis decided - a die-margin winner and a direction winner "
        "are different claims")
    win = next(x for x in c if x["frame"] == "rot0_front")
    assert win["index_violations"] == 0, "the true frame walks the floor's own serpentine"
    assert win["index_steps"] == len(cells) - 1, "every consecutive pair is a step"


def test_the_floor_is_the_judge_of_a_wrap_not_the_source():
    """The source's own extent would say the row ended after one cell. Measured: index 1 sits at
    x=20 of a floor row spanning x=0..40, so TWENTY dies remain to its right and a downward step
    there is unlicensed. Judging against the source would license it and the rotated frames
    would stay indistinguishable."""
    m, floor, y, xs = _floor_row_probe()
    x0 = xs[len(xs) // 2]
    judge = ma.direction_judge([(x, yy) for (x, yy) in
                                [(a, b) for (a, b) in floor]])
    rows, dir_of, _next = judge
    assert len([x for x in rows[y] if x > x0]) > 0, "fixture: the row must continue rightward"

    # a mid-row downward step: the source has two cells and nothing to its right, but the FLOOR
    # says the row was not finished
    _c, _r, _order, after = _score_pair(m, floor, [(x0, y), (x0, y + 1)], [1, 2])
    mid_wrap = next(x for x in _c if x["frame"] == "rot0_front")
    assert mid_wrap["index_violations"] == 1, (
        "a wrap with dies still left in the floor's row is a violation")


def test_a_gap_in_a_row_is_not_a_violation():
    """Direction counts, distance does not. Measured: a same-row pair stepping +4 is still
    rightward. Counting distance would make every partial map a pile of violations, and partial
    maps are the only population this feature exists for."""
    m, floor, y, xs = _floor_row_probe()
    x0 = xs[len(xs) // 2]
    c, _r, _order, _after = _score_pair(m, floor, [(x0, y), (x0 + 4, y)], [1, 2])
    straight = next(x for x in c if x["frame"] == "rot0_front")
    assert straight["index_violations"] == 0, "a gap is not a wrong direction"
    assert straight["index_steps"] == 1


def test_the_violation_count_ships_with_its_denominator():
    """Zero violations out of zero steps is not the same claim as zero out of forty. The count
    is the only number in this file where SMALLER is better, so it travels with what it was
    measured over."""
    m, floor, y, xs = _floor_row_probe()
    c, _r, _o, _a = _score_pair(m, floor, [(xs[0], y), (xs[1], y)], [1, 2])
    for row in c:
        if row["state"] != ma.STATE_SCORED:
            continue
        assert (row["index_violations"] is None) == (row["index_steps"] is None)
        assert row["index_steps"] == 1


def _reproduce_agreement_from_wire(placement, cells, reference):
    """Rebuild the placement from ONLY what crosses the wire and count what lands on the floor.

    🔴 THE ORACLE IS THE SHIPPED VALUES, and that is MORE independent than the old one, not
       less. It touches no scorer internals at all - just `linear`, `anchor_src`, `anchor_ref`
       and the reference cells - so it asserts precisely the contract the client draws from.
       If the scorer and the shipped values ever part, this is what notices, and that parting
       is the failure that was invisible all day.

       The previous version replayed through `make_frame_transform`, which stopped being the
       scorer's method the moment placement became anchor-plus-differences."""
    import numpy as np
    L = placement["linear"]
    ax, ay = placement["anchor_src"]
    rx, ry = placement["anchor_ref"]
    placed = [(rx + L[0][0] * (x - ax) + L[0][1] * (y - ay),
               ry + L[1][0] * (x - ax) + L[1][1] * (y - ay)) for (x, y) in cells]
    got = ma._encode(placed)
    ref = np.unique(ma._encode(sorted(reference)))
    idx = np.searchsorted(ref, got)
    idx[idx >= ref.size] = 0
    return int(np.count_nonzero(ref[idx] == got))


def test_the_shipped_placement_is_the_scored_placement():
    """THE SCREEN DRAWS WHAT WAS SCORED. Product owner 2026-08-06, after the index axis started
    ranking: 「되긴 하는데 화면에 다른 shift가 뜨는 듯, 계산에 사용된 거 말고」.

    Before the anchor this could not be seen: `_solve_shift` breaks ties toward the origin, so
    on a saturated partial map it returned (0,0) and any consumer that forgot the offset agreed
    with the scorer by accident. The anchor makes the offset real, and every place that carries
    a second copy of it became visible at once.

    This binds the two facts that must not part: take the offset as SHIPPED, replay the placement
    independently, and require it to reproduce the agreement as SHIPPED."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _partial_job(floor_meta, floor, 266)
    planted = "rot90_front"
    recorded = [(x + 5, y - 4) for (x, y) in _plant(floor_meta, cells, planted)]

    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": floor_meta, "cells": recorded, "indices": ks}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)

    assert ruling["placement"] == ma.PLACEMENT_ANCHOR
    for c in cands:
        if c["state"] != ma.STATE_SCORED:
            continue
        assert c["placement"] is not None, "the drawing contract must ship for every candidate"
        assert _reproduce_agreement_from_wire(c["placement"], recorded, floor) == c["agreement"], (
            "candidate %s ships placement %s and agreement %d, and those two do not describe "
            "the same placement" % (c["frame"], c["placement"], c["agreement"]))

    # And the ruling's copy POINTS AT the winning row rather than re-deriving it.
    win = next(c for c in cands if c["frame"] == ruling["winner"])
    assert ruling["shift"] == win["shift"]
    # 🔴 THE GUARD MOVED WITH THE MECHANISM. Under anchor-plus-differences the residual shift
    #    is (0,0) BY CONSTRUCTION - the translation lives in `anchor_ref`, not in `shift`. So
    #    the thing to prove is still "this fixture actually moves the map", and the number that
    #    now says so is the anchor pair.
    assert win["placement"]["anchor_ref"] != win["placement"]["anchor_src"], (
        "guard: the anchor must actually displace this fixture, or a consumer that drops the "
        "placement would coincidentally draw correctly and prove nothing")


def test_a_shipped_offset_that_is_not_the_scored_one_is_caught():
    """THE MUTATION, and it is exactly today's bug: score by the anchor, ship the shift search's
    number. If `test_the_shipped_placement_is_the_scored_placement` survived this, it would be
    asserting nothing."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _partial_job(floor_meta, floor, 266)
    planted = "rot90_front"
    recorded = [(x + 5, y - 4) for (x, y) in _plant(floor_meta, cells, planted)]
    payload = [{"map_id": "M1", "meta": floor_meta, "cells": recorded, "indices": ks}]

    cands, _e, ruling, _s = ma.score_candidates(
        payload, floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    win = next(c for c in cands if c["frame"] == ruling["winner"])

    # The search's answer for the same candidate - the value that used to ship.
    import numpy as np
    tf = map_overlay.make_frame_transform(
        source_meta_for_frame(floor_meta, win["frame"]), floor_meta)
    keys = ma._encode([tf(x, y) for (x, y) in recorded])
    sdx, sdy, _hit = ma._solve_shift(keys, np.unique(ma._encode(sorted(floor))),
                                     ma.SHIFT_WINDOW)
    stale = {"dx": sdx, "dy": sdy}
    assert stale != win["shift"], (
        "guard: the mutation must actually change the number, or it proves nothing - the "
        "search and the anchor have to disagree on this fixture")

    bad = dict(win["placement"])
    bad["anchor_ref"] = [win["placement"]["anchor_ref"][0] + stale["dx"],
                         win["placement"]["anchor_ref"][1] + stale["dy"]]
    assert _reproduce_agreement_from_wire(bad, recorded, floor) != win["agreement"], (
        "shipping a placement that is not the scored one must not reproduce the shipped "
        "agreement; if it does, the assertion above cannot catch this bug")


@pytest.mark.parametrize("mutate,reason", [
    (lambda ks: [None] * len(ks), ma.ANCHOR_NO_INDEX),
    # 🔴 the mutation must actually DUPLICATE the minimum. `[1] + ks[1:]` looks like a mutation
    #    and is a no-op, because `_partial_job` already numbers from 1 - the first version of
    #    this parametrisation asserted nothing and passed for the wrong reason.
    (lambda ks: [ks[0], ks[0]] + ks[2:], ma.ANCHOR_MIN_NOT_UNIQUE),
])
def test_an_unusable_anchor_falls_back_and_names_which(mutate, reason):
    """An absent or ambiguous anchor is a legitimate refusal AS LONG AS IT SAYS WHICH - the
    repairs differ (declare an index column / fix duplicate numbers / narrow the unit)."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _partial_job(floor_meta, floor, 80)
    _c, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": floor_meta,
          "cells": _plant(floor_meta, cells, "rot90_front"), "indices": mutate(ks)}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    assert ruling["placement"] == ma.PLACEMENT_SEARCH
    assert ruling["anchor_reason"] == reason


def test_two_source_maps_leave_the_anchor_ambiguous_rather_than_picking_one():
    """Each map restarts at 1, so 'the minimum-index die' names as many dies as there are maps.
    Choosing among them would be a second arbitrary placement - the thing this change removes."""
    floor_meta = _meta(cols=41, rows=41)
    floor = _valid_die_floor(floor_meta)
    cells, ks = _partial_job(floor_meta, floor, 100)
    h = len(cells) // 2
    _c, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "A", "meta": floor_meta,
          "cells": _plant(floor_meta, cells[:h], "rot0_front"), "indices": ks[:h]},
         {"map_id": "B", "meta": floor_meta,
          "cells": _plant(floor_meta, cells[h:], "rot0_front"),
          "indices": list(range(1, len(cells) - h + 1))}],
        floor, floor_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
    assert ruling["anchor_reason"] == ma.ANCHOR_MULTI_MAP
    assert ruling["placement"] == ma.PLACEMENT_SEARCH


def test_the_index_axis_stays_dark_when_no_cell_carries_a_number():
    """REGRESSION, and it went red across 25 existing tests before the guard existed.

    The scorer pads `indices` to the cell count with None, so 'no index column' arrives as a
    FULL list of Nones rather than an empty one. Read as 'indices present', all eight candidates
    score 0 - and because this axis outranks the others, that zero silently displaced the
    occupancy verdict and every planted-frame test lost its winner. Absence folded to zero, in a
    new axis, in the one module that warns about that three times.
    """
    ref_meta = _meta()
    ref = _ref_cells()
    planted = _plant(ref_meta, ref, "rot90_front")
    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": planted}], ref, ref_meta,
        thresholds=THRESHOLDS)
    assert ruling["metric"] == ma.METRIC_OCCUPANCY, "a dark axis must not claim the ranking"
    assert ruling["winner"] == "rot90_front", "the existing verdict must survive untouched"
    for c in cands:
        assert c["index_agreement"] is None, "null, not 0 - nothing was measured"
        assert c["index_total"] is None


# ---------------------------------------------------------------------------
# DECLARED SIDES - narrowing the search is a claim, and never a default
# ---------------------------------------------------------------------------

def test_undeclared_sides_score_both():
    """Same discipline as the thresholds: an absent declaration must not fold to one side.
    Narrowing is a claim about the equipment and has to be made out loud."""
    assert ma.load_alignment_sides({}) is None
    assert ma.load_alignment_sides({"alignment": {}}) is None
    assert ma.load_alignment_sides({"alignment": {"sides": ["front"]}}) == ["front"]
    assert ma.load_alignment_sides({"alignment": {"sides": ["back", "front"]}}) == \
        ["front", "back"], "normalised to vocabulary order, so one claim has one spelling"
    for junk in ("front", [], ["sideways"], 3):
        assert ma.load_alignment_sides({"alignment": {"sides": junk}}) is None, junk


def test_a_narrowed_side_is_reported_as_unconsidered_not_as_a_loser():
    """The whole point. If the operator narrows to front and the truth is a back frame, the
    screen must be able to say the answer was never looked at. Dropping the four rows - or
    marking them `not_scorable` - makes 'we did not look' indistinguishable from 'we looked and
    it lost', which is the shape of a confident wrong answer."""
    ref_meta = _meta()
    ref = _ref_cells()
    planted = _plant(ref_meta, ref, "rot90_front")
    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": planted}], ref, ref_meta,
        thresholds=THRESHOLDS, sides=["front"])

    assert len(cands) == 8, "the search narrows; the REPORT does not"
    backs = [c for c in cands if c["side"] == "back"]
    fronts = [c for c in cands if c["side"] == "front"]
    assert len(backs) == 4 and len(fronts) == 4
    assert all(c["state"] == ma.STATE_NOT_CONSIDERED for c in backs)
    assert all(c["state"] != ma.STATE_NOT_CONSIDERED for c in fronts)
    assert all(c["reason"] == ma.TEXT_SIDE_NOT_CONSIDERED for c in backs), \
        "and each one says WHY it was not looked at"
    assert all(c["shift"] is None and c["agreement"] == 0 for c in backs)

    assert ruling["sides_considered"] == ["front"]
    assert ruling["sides_narrowed"] is True
    assert ruling["winner"] == "rot90_front"


def test_an_unconsidered_candidate_cannot_win():
    """A frame that was never scored must not enter the ranking through the back door."""
    ref_meta = _meta()
    ref = _ref_cells()
    planted = _plant(ref_meta, ref, "rot0_back")
    cands, _e, ruling, _s = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": planted}], ref, ref_meta,
        thresholds=THRESHOLDS, sides=["front"])
    assert ruling["winner"] != "rot0_back", "the true frame was excluded, so it cannot win"
    scored = [c for c in cands if c["state"] == ma.STATE_SCORED]
    assert len(scored) == 4
    top = max(scored, key=lambda c: c["agreement"])
    others = [c["agreement"] for c in scored if c is not top]
    assert top["margin"] == top["agreement"] - max(others), \
        "the runner-up came from the scored four, not from an unconsidered zero"


def test_undeclared_sides_leave_the_candidate_list_exactly_as_it_was():
    """The switch-on-for-one-rule property: declaring nothing must be byte-identical."""
    ref_meta = _meta()
    ref = _ref_cells()
    planted = _plant(ref_meta, ref, "rot90_front")
    args = ([{"map_id": "M1", "meta": ref_meta, "cells": planted}], ref, ref_meta)
    base_c, _e, base_r, _s = ma.score_candidates(*args, thresholds=THRESHOLDS)
    for absent in (None, []):
        cands, _e2, ruling, _s2 = ma.score_candidates(*args, thresholds=THRESHOLDS,
                                                      sides=absent)
        assert cands == base_c, absent
        assert ruling == base_r, absent
    assert base_r["sides_considered"] == ["front", "back"]
    assert base_r["sides_narrowed"] is False
    assert all(c["state"] != ma.STATE_NOT_CONSIDERED for c in base_c)
