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

    cands, excluded, ruling, stats = ma.score_candidates(
        [{"map_id": "M1", "meta": ref_meta, "cells": recorded}], ref, ref_meta)

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
