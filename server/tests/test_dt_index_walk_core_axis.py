"""The seeded walks, scored on the CORE axis - does the fixture validate what ships?

WHY THIS FILE EXISTS
`seed_dt_index_walk.py` was designed front-complete for the **DT** axis. Its `core_frame`
was not: two of its four jobs record the core coordinates in a BACK frame, and this box
declares `alignment.sides: ["front"]`. Under that declaration the true core frame of those
two is not in the search space at all - and because the group-count minimum is held by the
truth AND ITS FRONT/BACK MIRROR, deleting the truth leaves the mirror alone at the
minimum. The scorer then returns a unique, confident, WRONG core frame instead of no
winner. That was a gap in the fixture rather than a defect in the scorer, and it meant the
core axis could not be validated at all on this box.

Two jobs were added to close it. This file is what makes them load-bearing, and it asserts
the gap as well as the closure - so that a later reader who deletes the new jobs finds out
here rather than in a wrong map.

🔴 Pure planning: `plan_job` builds its rows from the floor's geometry with no DB. Nothing
   here reads the config either - `alignment.sides` is a gitignored operator declaration,
   so this file asserts the FIXTURE's own coverage and lets the seed script's comment
   carry the reason.
"""
import os
import sys

import numpy as np
import pytest

SCRIPTS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import map_alignment as ma                                   # noqa: E402
import map_overlay                                           # noqa: E402
from dt_map_derivation import source_meta_for_frame          # noqa: E402
import seed_valid_die_ref_floor as floor                     # noqa: E402
import seed_dt_index_walk as seed                            # noqa: E402

FRONT_FRAMES = ["rot0_front", "rot90_front", "rot180_front", "rot270_front"]


@pytest.fixture(scope="module")
def bench():
    ref_meta = seed.grid_meta()
    field = floor.field_dies()
    return ref_meta, field, ma.direction_judge(field)


def _score(rows, frame, ref_meta, judge):
    """`(groups, violations)` for one candidate frame - the joint ordering the scorer reads.

    The recorded core coordinates are carried back into the reference frame through the
    SAME primitive the seed used to express them (`make_frame_transform`), in the opposite
    direction. A second implementation of the rotation math here would agree with itself
    and with nothing else.
    """
    src_meta = source_meta_for_frame(ref_meta, frame)
    assert src_meta is not None, frame
    inv = map_overlay.make_frame_transform(src_meta, ref_meta)
    phys = [inv(r["core_x"], r["core_y"]) for r in rows]
    idx_k = [r["dt_index"] for r in rows]
    idx_has = np.ones(len(phys), bool)
    groups, _ = ma.index_group_count(phys, None, idx_k, idx_has)
    violations, _ = ma.direction_violations(phys, None, idx_k, idx_has, judge)
    return groups, violations


def _ranked(rows, ref_meta, judge, space=FRONT_FRAMES):
    return sorted((_score(rows, f, ref_meta, judge), f) for f in space)


def _front_core_jobs():
    return [j for j in seed.JOBS if j["core_frame"].endswith("_front")]


def _back_core_jobs():
    return [j for j in seed.JOBS if j["core_frame"].endswith("_back")]


# ---------------------------------------------------------------------------
# Coverage: the members, not the count.
# ---------------------------------------------------------------------------

def test_the_core_truths_cover_every_front_rotation():
    """Before the CORE jobs were added, truth across every run was only ever
    `{rot0_front, rot0_back, rot90_front, rot180_back}` - 4 of 8 candidates, with the
    270 pair and `rot90_back`/`rot180_front` never the answer anywhere. A systematic bias
    against a frame nobody plants leaves any pass count fully green."""
    assert set(FRONT_FRAMES) <= {j["core_frame"] for j in seed.JOBS}


def test_the_dt_truths_cover_every_front_rotation():
    """The DT axis was already complete; pinned so an added job cannot quietly break it."""
    assert set(FRONT_FRAMES) <= {j["dt_frame"] for j in seed.JOBS}
    assert all(j["dt_frame"].endswith("_front") for j in seed.JOBS)


# ---------------------------------------------------------------------------
# The closure: on every front-core job the truth is the STRICT joint minimum.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("job", _front_core_jobs(), ids=lambda j: j["name"])
def test_the_true_core_frame_is_the_strict_joint_minimum(job, bench):
    ref_meta, field, judge = bench
    rows, facts = seed.plan_job(job, field, ref_meta)
    ranked = _ranked(rows, ref_meta, judge)
    (best_score, best_frame), (runner_up_score, _) = ranked[0], ranked[1]
    assert best_frame == job["core_frame"], ranked
    # strict, not merely first: `sorted` would otherwise decide a tie by frame NAME
    assert runner_up_score > best_score, ranked


@pytest.mark.parametrize("job", _front_core_jobs(), ids=lambda j: j["name"])
def test_the_group_count_of_the_truth_is_the_bin_count(job, bench):
    """The premise the whole axis rests on: inside one bin the picker walks the
    serpentine, so `y` falls only where the walk restarts - at a bin boundary.

    This is the claim the earlier evidence could not falsify (its single map made the
    per-map `+1` a constant offset across every candidate). Here it is an equality
    against a number declared elsewhere in the job.
    """
    ref_meta, field, judge = bench
    rows, facts = seed.plan_job(job, field, ref_meta)
    groups, _ = _score(rows, job["core_frame"], ref_meta, judge)
    assert groups == facts["bins"] == job["bins"]


# ---------------------------------------------------------------------------
# The gap, asserted - because it is the reason the jobs above exist.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("job", _back_core_jobs(), ids=lambda j: j["name"])
def test_a_back_core_job_cannot_validate_the_front_only_search(job, bench):
    """Its truth is not in the front search space, and what wins there is the truth's
    own FRONT/BACK MIRROR - strictly, so nothing reads as a tie or a refusal.

    That is correct behaviour for a narrowed search and it looks exactly like a defect,
    which is why it is written down here instead of being rediscovered.
    """
    ref_meta, field, judge = bench
    rows, _ = seed.plan_job(job, field, ref_meta)
    assert job["core_frame"] not in FRONT_FRAMES
    ranked = _ranked(rows, ref_meta, judge)
    (best_score, best_frame), (runner_up_score, _) = ranked[0], ranked[1]
    assert best_frame == job["core_frame"].replace("_back", "_front")
    assert runner_up_score > best_score, ranked

    # and the truth really is the winner once its own side is searched
    with_back = _ranked(rows, ref_meta, judge,
                        space=FRONT_FRAMES + [f.replace("_front", "_back")
                                              for f in FRONT_FRAMES])
    assert with_back[0][1] == job["core_frame"], with_back
    assert with_back[1][0] > with_back[0][0], with_back
