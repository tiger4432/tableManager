"""`index_group_count` — the CORE-walk axis, and the walk order both axes share.

WHY THIS FILE EXISTS
The function shipped with its evidence in a session scratchpad and nothing committed.
An adversarial review then planted four mutations and **two of them survived every
measurement offered for it** (QA-1 F4): dropping `groups = boundaries + 1`, and removing
the sort by index. Both survived for the same reason - the only fixture in play sat where
the code under test could not matter (`cell_owner` was `[0] * n` everywhere, so `+1` was a
constant offset across all candidates; and the seed's rows already arrive in `dt_index`
order, so the sort was never exercised).

So the tests below are written against those two mutants specifically, and each one that
depends on a fixture PROPERTY asserts that property rather than assuming it - a fixture
that is green either way proves nothing, and this repo has been burned by exactly that.
"""
import numpy as np
import pytest

import map_alignment as ma


def _has(n, false_at=()):
    a = np.ones(n, bool)
    for i in false_at:
        a[i] = False
    return a


def _falls_in_array_order(phys, idx_k):
    """An INDEPENDENT count of y-falls read in ARRAY order, ignoring the index.

    This is the oracle for "the sort is doing something": if this disagrees with the
    shipped function on a fixture, then that fixture actually exercises the sort. It is
    deliberately not a copy of the implementation - it never looks at `idx_k`.
    """
    return 1 + sum(1 for a, b in zip(phys, phys[1:]) if int(b[1]) < int(a[1]))


# ---------------------------------------------------------------------------
# The count itself.  (Mutant M1: drop `groups = boundaries + 1`.)
# ---------------------------------------------------------------------------

def test_a_walk_that_never_falls_is_one_group():
    """The `+1`. A monotone walk has ZERO boundaries and is still ONE group.

    🔴 This is the assertion mutant M1 escaped: with `+1` removed the answer is 0, and 0
       reads as a better score than any real map can achieve on a MINIMISED axis.
    """
    phys = [(0, 0), (1, 0), (2, 0), (2, 1), (1, 1), (0, 1)]
    groups, steps = ma.index_group_count(phys, None, [1, 2, 3, 4, 5, 6], _has(6))
    assert (groups, steps) == (1, 5)


def test_each_map_brings_its_own_group():
    """`groups` is summed PER MAP, so two untroubled maps are two groups, not one.

    The one fixture this function had measured used `cell_owner = [0] * n` everywhere -
    a single map - which is what made the `+1` a constant offset and M1 invisible.
    """
    phys = [(0, 0), (1, 0), (0, 0), (1, 0)]
    owner = ["A", "A", "B", "B"]
    groups, steps = ma.index_group_count(phys, owner, [1, 2, 1, 2], _has(4))
    assert (groups, steps) == (2, 2)


def test_a_fall_in_y_opens_a_group_and_equal_y_does_not():
    """Three runs, counted exactly - not "more than one"."""
    #        run 1            run 2 (y falls)   run 3 (y falls)
    phys = [(0, 5), (1, 5), (0, 2), (1, 2), (0, 0), (1, 0)]
    groups, steps = ma.index_group_count(phys, None, [1, 2, 3, 4, 5, 6], _has(6))
    assert (groups, steps) == (3, 5)
    # and the equal-y steps inside each run were measured and NOT counted
    flat = [(0, 3), (1, 3), (2, 3), (3, 3)]
    assert ma.index_group_count(flat, None, [1, 2, 3, 4], _has(4)) == (1, 3)


def test_a_rise_in_y_is_not_a_boundary():
    phys = [(0, 0), (0, 1), (0, 2), (0, 3)]
    assert ma.index_group_count(phys, None, [1, 2, 3, 4], _has(4)) == (1, 3)


# ---------------------------------------------------------------------------
# Absence is not zero.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("idx_has", [None, np.zeros(4, bool)])
def test_absence_is_none_not_zero(idx_has):
    """A zero here would read as "one group", i.e. a PERFECT score, for a walk nobody
    numbered - and this axis is minimised, so that zero would win."""
    phys = [(0, 0), (1, 0), (2, 0), (3, 0)]
    groups, steps = ma.index_group_count(phys, None, [1, 2, 3, 4], idx_has)
    assert groups is None
    assert steps == 0


def test_only_the_indexed_cells_are_walked():
    """A partial index is a partial walk, not a broken one.

    The unindexed cell sits between two indexed ones IN THE ARRAY and would open a
    spurious group if it were read; the walk must step straight over it.
    """
    phys = [(0, 0), (5, 9), (1, 0), (2, 0)]
    groups, steps = ma.index_group_count(phys, None, [1, 0, 2, 3], _has(4, false_at=[1]))
    assert (groups, steps) == (1, 2)


# ---------------------------------------------------------------------------
# The walk order is a property of the MAP.  (Mutant M4: remove the sort.)
# ---------------------------------------------------------------------------

def test_the_score_does_not_depend_on_row_order():
    """Same map, rows shuffled → same answer.

    🔴 The `assert` on the oracle is the load-bearing line, not the equality below it.
       Mutant M4 (remove the sort) survived every earlier measurement because the fixture
       arrived pre-sorted, so the sort could be deleted with nothing changing. This
       fixture asserts up front that ARRAY order and INDEX order genuinely disagree here;
       without that, the equality would pass on an unsorted implementation too and this
       test would be decoration.
    """
    ordered = [(0, 4), (1, 4), (2, 4), (0, 1), (1, 1), (2, 1)]
    idx_ordered = [1, 2, 3, 4, 5, 6]
    #                       k=4      k=1     k=5     k=2     k=6     k=3
    scrambled = [(0, 1), (0, 4), (1, 1), (1, 4), (2, 1), (2, 4)]
    idx_scrambled = [4, 1, 5, 2, 6, 3]

    truth = ma.index_group_count(ordered, None, idx_ordered, _has(6))
    assert truth == (2, 5)
    # the fixture really does exercise the sort: read in array order it answers 3, not 2
    array_order_answer = _falls_in_array_order(scrambled, idx_scrambled)
    assert array_order_answer == 3
    assert array_order_answer != truth[0]
    assert ma.index_group_count(scrambled, None, idx_scrambled, _has(6)) == truth


def test_duplicate_indices_do_not_depend_on_row_order():
    """Two cells on the same `dt_index` must not let the DB's row order pick the score.

    Measured before the fix (QA-1 F3): the same map in two row orders answered `groups`
    2 and 1. A re-probe or a merge landing two cells on one index is all it takes, and a
    query with no `ORDER BY` then names two different core frames on two runs.
    """
    #                     k=1     k=2     k=2     k=3
    order_a = [(0, 0), (1, 5), (2, 0), (3, 5)]
    idx_a = [1, 2, 2, 3]
    order_b = [(0, 0), (2, 0), (1, 5), (3, 5)]     # the same four cells, rows swapped
    idx_b = [1, 2, 2, 3]

    # the fixture is capable of showing the defect: the two duplicate-index cells sit on
    # DIFFERENT rows, so array order would decide which of them comes first
    assert order_a[1][1] != order_a[2][1]
    assert _falls_in_array_order(order_a, idx_a) != _falls_in_array_order(order_b, idx_b)

    assert (ma.index_group_count(order_a, None, idx_a, _has(4))
            == ma.index_group_count(order_b, None, idx_b, _has(4)))


def test_direction_violations_walks_the_same_order():
    """The two axes are read as one joint ordering, so they must not order the walk
    differently - otherwise the pair describes two different walks of one map."""
    ref = [(x, y) for y in range(3) for x in range(3)]
    judge = ma.direction_judge(ref)
    order_a = [(0, 0), (1, 2), (2, 0), (0, 2)]
    idx_a = [1, 2, 2, 3]
    order_b = [(0, 0), (2, 0), (1, 2), (0, 2)]
    idx_b = [1, 2, 2, 3]
    assert (ma.direction_violations(order_a, None, idx_a, _has(4), judge)
            == ma.direction_violations(order_b, None, idx_b, _has(4), judge))


def test_the_shared_walk_helper_orders_by_index_then_position():
    """The ordering rule stated once, so a future edit has to face it."""
    phys = [(9, 9), (0, 1), (5, 1)]
    walk = ma._walk_by_index(phys, None, [7, 7, 7], _has(3))
    assert list(walk) == [0]
    assert [t[:3] for t in walk[0]] == [(7, 1, 0), (7, 1, 5), (7, 9, 9)]
