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

    def raster(cells_, top_is_min_y=True):
        present = {}
        for (x, y) in (cells_ or ()):
            present.setdefault(int(y), set()).add(int(x))
        out, i = {}, 1
        for y in sorted(present, reverse=not top_is_min_y):
            for x in sorted(present[y]):          # never reverses - THIS is the mutation
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

def _confirm_and_rescore(ref_start, src_start, planted, n=180):
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
    assert w2 is not None and r2["winner"] == planted, (
        "the confirmed coordinate system must still score to the same frame")
    assert w2["shift"] == {"dx": 0, "dy": 0}, (
        "a confirmed origin that still needs a shift has not recorded the alignment: %s"
        % w2["shift"])
    assert w2["agreement"] == w1["agreement"]


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


def test_the_derived_start_is_the_same_under_all_eight_frames():
    """THE EIGHT-WAY IDENTITY. The origin is a quantity in the map's OWN visual space, which is
    before the rotation - so it cannot depend on which candidate frame is being tested.

    One assertion catches three distinct mistakes at once: a missing inverse, a wrong sign, and
    a rotation applied the wrong way round. Any of them makes the eight disagree; only a correct
    inverse makes them identical. Measured: `start +/- (dx,dy)` - the expression anyone fixing
    this by eye reaches for first - agrees with the truth on exactly TWO frames of eight, so a
    test that checked `rot0_front` alone would pass on a broken conversion.

    🔴 THE INDEX COLUMN IS NOT OPTIONAL HERE. Without it the translation is solved by the +-3
    search, and this fixture's displacement is (5,-4) - outside the window, so the search
    returns a clamped value and the eight derived origins legitimately differ. The first
    version of this test omitted the indices and read that as a failure of the conversion.
    The anchor is what makes the displacement recoverable at all.
    """
    ref_meta = _meta(cols=41, rows=41, start_x=1, start_y=1)
    floor = _valid_die_floor(ref_meta)
    cells, ks = _partial_job(ref_meta, floor, 180)
    src_meta = dict(ref_meta, grid_start_x=1, grid_start_y=1)
    DISPLACEMENT = (5, -4)

    derived = {}
    for frame in ma.CANDIDATE_FRAMES:
        recorded = [(x + DISPLACEMENT[0], y + DISPLACEMENT[1])
                    for (x, y) in _plant(ref_meta, cells, frame)]
        c, _e, r, _s = ma.score_candidates(
            [{"map_id": "M1", "meta": src_meta, "cells": recorded, "indices": ks}],
            floor, ref_meta, thresholds=THRESHOLDS, index_thresholds=THRESHOLDS)
        assert r["winner"] == frame, "guard: the planted frame must win before its shift is used"
        w = next(x for x in c if x["frame"] == frame)
        derived[frame] = ma.start_for_placement(
            source_meta_for_frame(src_meta, frame), ref_meta, w["shift"])

    assert len(set(derived.values())) == 1, (
        "the origin is a pre-rotation quantity and cannot depend on the frame: %s" % derived)
    assert derived["rot0_front"] == (1 + DISPLACEMENT[0], 1 + DISPLACEMENT[1]), (
        "and it is the declared origin moved by the displacement, in the map's own space")


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


def _reproduce_agreement_at(shift, cells, meta, frame, reference):
    """Independently place `cells` under `frame` and count how many land on `reference` when
    moved by `shift`. Used to bind the SHIPPED offset to the SHIPPED agreement.

    Deliberately does not call the scorer: an assertion that asked the scorer to confirm its
    own number would pass under any offset it chose to ship."""
    import numpy as np
    tf = map_overlay.make_frame_transform(source_meta_for_frame(meta, frame), meta)
    placed = [tf(x, y) for (x, y) in cells]
    moved = ma._encode([(x + shift["dx"], y + shift["dy"]) for (x, y) in placed])
    ref = np.unique(ma._encode(sorted(reference)))
    idx = np.searchsorted(ref, moved)
    idx[idx >= ref.size] = 0
    return int(np.count_nonzero(ref[idx] == moved))


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
        assert c["shift"] is not None
        assert _reproduce_agreement_at(c["shift"], recorded, floor_meta, c["frame"],
                                       floor) == c["agreement"], (
            "candidate %s ships offset %s and agreement %d, and those two do not describe the "
            "same placement" % (c["frame"], c["shift"], c["agreement"]))

    # And the ruling's copy POINTS AT the winning row rather than re-deriving it.
    win = next(c for c in cands if c["frame"] == ruling["winner"])
    assert ruling["shift"] == win["shift"]
    assert ruling["shift"] != {"dx": 0, "dy": 0}, (
        "guard: on this fixture the anchor moves the map, so a consumer that drops the offset "
        "draws somewhere else - which is the whole defect")


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

    assert _reproduce_agreement_at(stale, recorded, floor_meta, win["frame"],
                                   floor) != win["agreement"], (
        "shipping the search's offset while scoring by the anchor must not reproduce the "
        "shipped agreement; if it does, the assertion above cannot catch this bug")


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
