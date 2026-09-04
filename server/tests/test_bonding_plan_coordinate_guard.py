# -*- coding: utf-8 -*-
"""A NaN coordinate must be skipped, not converted.

`if px is None or py is None` reads as "skip the missing ones", and for a
`double precision` column that is wrong: a NaN is not None, so it walks through the guard
and `int(nan)` raises `cannot convert float NaN to integer` - the error class the owner
hit in production on 2026-09-04, in another place. The failure here is a 500 on a count
screen, from one bad row among thousands.

⚠️ These cases assert on COUNTS, not on exceptions alone. The silent half of this class is
that a wrong guard changes the answer: a point that should be skipped must not be counted,
and every finite point must still be.
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import bonding_plan                                              # noqa: E402


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), None])
def test_a_coordinate_that_is_not_a_number_is_not_a_point(bad):
    assert bonding_plan._finite_point(bad, 3.0) is False
    assert bonding_plan._finite_point(3.0, bad) is False


@pytest.mark.parametrize("good", [0, 0.0, -1, 7.5, 10 ** 9])
def test_every_ordinary_coordinate_still_counts(good):
    """🔴 ZERO AND NEGATIVE ARE COORDINATES. A guard that swallowed them would silently
    shrink every count that includes the origin, and nothing would raise."""
    assert bonding_plan._finite_point(good, good) is True


def test_int_on_what_survives_the_guard_can_never_raise():
    """The property the call sites rely on: everything the guard admits is convertible.
    Written as the conversion itself, because that is what the code does two lines on."""
    for px, py in [(1, 2), (0, 0), (-5.0, 7.9), (float("nan"), 1), (1, float("inf")),
                   (None, 1)]:
        if bonding_plan._finite_point(px, py):
            int(px), int(py)                      # must not raise
        else:
            with pytest.raises((ValueError, OverflowError, TypeError)):
                int(px), int(py)


def test_the_count_skips_the_bad_row_rather_than_dropping_the_batch():
    """The failure mode this replaces is not "one point missing" but "the whole screen
    500s". Counted here, because a test that only asserted "no exception" would pass on a
    guard that threw everything away."""
    points = [(1, 1), (float("nan"), 2), (3, 3), (4, float("inf")), (None, 5), (6, 6)]
    kept = [(int(px), int(py)) for (px, py) in points
            if bonding_plan._finite_point(px, py)]
    assert kept == [(1, 1), (3, 3), (6, 6)]
