"""`bin_fingerprint_shift` — the translation, and the four ways it must refuse to name one.

WHY THIS FILE EXISTS
Two paths returned a CONFIDENT, WRONG translation instead of refusing (QA-1 F1/F2), and
both are reachable with realistic inputs. The docstring already stated the contract those
paths broke - *"on any refusal `(dx, dy)` is `(0, 0)` and that zero is not a measurement"* -
so these tests pin the contract, not a new opinion.

🔴 Every refusal test here also asserts that the SAME fixture yields a real translation
   once the refusing condition is lifted. A refusal test that cannot show the input was
   otherwise answerable proves only that the function is broken.
"""
import numpy as np
import pytest

import map_alignment as ma


def _ref_grid(w=8, h=8, labels=("B1", "B2", "B3", "B4")):
    """A reference bin map whose labels vary die to die - a fingerprint, not a flat field.

    🔴 Pseudo-RANDOM, not `(a*x + b*y) % n`. A modular label rule is PERIODIC, and a
       periodic bin map genuinely does not name a translation - every fixture built that
       way lands in `BINFP_NOT_UNIQUE` and can only test the refusal. Seeded, so the map
       is the same on every run.
    """
    import random
    rnd = random.Random(20260806)
    return {(x, y): labels[rnd.randrange(len(labels))]
            for x in range(w) for y in range(h)}


def _source_from(ref, dx, dy, cells):
    """Cells lifted out of `ref` and shifted by `(dx, dy)`, so the truth is `(dx, dy)`."""
    phys = [(x - dx, y - dy) for (x, y) in cells]
    labels = [ref[(x, y)] for (x, y) in cells]
    return phys, labels


# ---------------------------------------------------------------------------
# The happy path, first - so the refusals below have a baseline to be measured against.
# ---------------------------------------------------------------------------

def test_it_finds_the_planted_translation():
    ref = _ref_grid()
    cells = [(x, y) for x in range(4) for y in range(4)]
    phys, labels = _source_from(ref, 2, 1, cells)
    dx, dy, matched, seats, reason = ma.bin_fingerprint_shift(phys, labels, ref)
    assert (dx, dy) == (2, 1)
    assert reason is None
    assert matched == len(cells)


# ---------------------------------------------------------------------------
# F1 — the support floor.
# ---------------------------------------------------------------------------

def test_a_translation_held_up_by_too_few_dies_is_refused():
    """One coincidence is not a fix.

    Measured before the floor existed (QA-1 F1): a 40-die source that can match the
    reference in exactly one place returned `(9, 9, 1, 1, None)` - and `reason is None`
    is documented as "the translation was determined". The failure that reaches this is
    the reference resolving to the wrong wafer revision: one die coincides, the map lands
    a wafer-radius off, and nothing anywhere says so.
    """
    ref = {(0, 0): "B1", (9, 9): "RARE"}
    phys = [(0, 0)] + [(i, 0) for i in range(1, 40)]
    labels = ["RARE"] + ["NOPE"] * 39
    dx, dy, matched, seats, reason = ma.bin_fingerprint_shift(phys, labels, ref)
    assert reason == ma.BINFP_LOW_SUPPORT
    assert (dx, dy) == (0, 0)          # the contract: a refusal does not carry a pair
    assert matched == 1                # but the measurement is still reported

    # the fixture is answerable: the same input with the floor lowered names the shift
    lowered = ma.bin_fingerprint_shift(phys, labels, ref, min_support=1)
    assert lowered[:2] == (9, 9)
    assert lowered[4] is None


def test_the_floor_is_a_caller_supplied_number():
    """The default is a module constant so the wiring round can raise it from config;
    until then a caller can. `min_support=1` must NOT be silently floored upward."""
    ref = _ref_grid()
    cells = [(x, y) for x in range(4) for y in range(4)]
    phys, labels = _source_from(ref, 1, 1, cells)
    assert ma.bin_fingerprint_shift(phys, labels, ref, min_support=16)[4] is None
    assert ma.bin_fingerprint_shift(phys, labels, ref, min_support=17)[4] == ma.BINFP_LOW_SUPPORT
    assert ma._BINFP_MIN_SUPPORT >= 2


# ---------------------------------------------------------------------------
# F2 — the seat cap is a refusal, not a truncated answer.
# ---------------------------------------------------------------------------

def test_the_seat_cap_refuses_instead_of_answering_from_the_survivors():
    """Measured before the fix (QA-1 F2), same input, cap varied:

        uncapped   : (22, 22, 3, 4, None)                  <- the truth
        seat_cap=3 : (-3, -3, 2, 3, 'seat_cap_reached')    <- wrong, non-zero, plausible

    `sorted(seats)[:cap]` truncates by ascending `(x, y)`, i.e. by an arbitrary corner of
    the wafer, so the best fit among the SURVIVORS is not the map's best fit.
    """
    ref = _ref_grid(w=8, h=8)
    cells = [(x, y) for x in range(5) for y in range(5)]
    phys, labels = _source_from(ref, 3, 2, cells)

    uncapped = ma.bin_fingerprint_shift(phys, labels, ref, min_support=1)
    assert uncapped[:2] == (3, 2) and uncapped[4] is None
    seats_needed = uncapped[3]
    assert seats_needed > 1            # the cap below actually bites

    capped = ma.bin_fingerprint_shift(phys, labels, ref,
                                      seat_cap=seats_needed - 1, min_support=1)
    assert capped[4] == ma.BINFP_SEAT_CAP
    assert capped[:2] == (0, 0)        # the contract
    assert capped[3] == seats_needed   # ...and it says how far past the cap it was


# ---------------------------------------------------------------------------
# The refusals that were already correct - pinned so a later edit cannot quietly
# turn one of them into a pair.
# ---------------------------------------------------------------------------

def test_a_degenerate_bin_map_names_no_translation():
    """One label everywhere: many translations fit equally, so none is THE translation.
    Picking the origin-nearest here would let the RULE place the map."""
    ref = {(x, y): "B1" for x in range(6) for y in range(6)}
    phys = [(0, 0), (1, 0)]
    labels = ["B1", "B1"]
    dx, dy, matched, seats, reason = ma.bin_fingerprint_shift(phys, labels, ref,
                                                              min_support=1)
    assert reason == ma.BINFP_NOT_UNIQUE
    assert (dx, dy) == (0, 0)


@pytest.mark.parametrize("labels", [None, [], [None, None], ["", ""]])
def test_a_source_with_no_bin_values_refuses_by_name(labels):
    ref = _ref_grid()
    assert ma.bin_fingerprint_shift([(0, 0), (1, 0)], labels, ref)[4] == ma.BINFP_NO_SOURCE_BINS


@pytest.mark.parametrize("ref", [None, {}])
def test_no_reference_bin_map_refuses_by_name(ref):
    out = ma.bin_fingerprint_shift([(0, 0)], ["B1"], ref)
    assert out[4] == ma.BINFP_NO_REFERENCE_BINS
    assert out[:2] == (0, 0)


def test_a_label_the_reference_never_carries_has_no_seat():
    ref = _ref_grid()
    out = ma.bin_fingerprint_shift([(0, 0)], ["NOT-IN-THE-REFERENCE"], ref)
    assert out[4] == ma.BINFP_NO_SEAT
    assert out[:2] == (0, 0)


def test_every_refusal_carries_a_zero_pair():
    """The contract, stated once over the whole vocabulary: no refusal may return a pair.

    🔴 The membership assertion is deliberate. Pinning the COUNT of reasons would let a
       later edit add a sixth refusal that returns a non-zero pair and stay green.
    """
    assert {ma.BINFP_NO_SOURCE_BINS, ma.BINFP_NO_REFERENCE_BINS, ma.BINFP_NO_SEAT,
            ma.BINFP_NOT_UNIQUE, ma.BINFP_SEAT_CAP, ma.BINFP_LOW_SUPPORT} == {
        "no_source_bin_values", "no_reference_bin_map", ma.RESIDUAL_NO_QUALIFYING_SEAT,
        ma.RESIDUAL_NOT_UNIQUE, "bin_seat_cap_refused", "match_support_below_floor"}


def test_the_seat_cap_reason_is_not_the_residual_search_s_spelling():
    """One string may not carry two contracts (lead PM ruling 2026-08-06).

    A caller that branches on the reason string would otherwise read the wrong contract
    half the time, and nothing could catch it: both functions are correct on their own
    terms, so there is no failing assertion to write. The two names ARE allowed to be
    equal in value only if the two functions promise the same thing about `(dx, dy)`, and
    that promise is a per-function docstring, not a property of the token.
    """
    assert ma.BINFP_SEAT_CAP != ma.RESIDUAL_SEAT_CAP
    # the two that ARE aliases stay aliases - they name the same outcome on both sides
    assert ma.BINFP_NO_SEAT == ma.RESIDUAL_NO_QUALIFYING_SEAT
    assert ma.BINFP_NOT_UNIQUE == ma.RESIDUAL_NOT_UNIQUE


# ---------------------------------------------------------------------------
# F7 — `c_bn` is a DB column and may arrive as an array.
# ---------------------------------------------------------------------------

def test_bin_labels_may_be_an_ndarray():
    """`len(bin_labels or ())` asked an ndarray for its truth value and raised
    ("truth value of an array with more than one element is ambiguous"). `idx_k` already
    arrives as one on this route, so `c_bn` plausibly will too."""
    ref = _ref_grid()
    cells = [(x, y) for x in range(4) for y in range(4)]
    phys, labels = _source_from(ref, 1, 2, cells)
    out = ma.bin_fingerprint_shift(phys, np.array(labels, dtype=object), ref)
    assert out[:2] == (1, 2)
    assert out[4] is None


def test_the_anchor_is_the_rarest_label_not_the_first_row():
    """The anchor rule costs seats, so it has to be measured or a later edit will drop it.

    The reference carries one die of `RARE` and many of `COMMON`; anchoring on array
    order would scan the COMMON seats instead. `seats_considered` is what tells them
    apart, and it is returned.
    """
    ref = {(x, y): "COMMON" for x in range(6) for y in range(6)}
    ref[(4, 4)] = "RARE"
    cells = [(0, 0), (1, 0), (2, 0), (2, 2)]
    phys = [(x, y) for (x, y) in cells]
    labels = ["COMMON", "COMMON", "COMMON", "RARE"]
    out = ma.bin_fingerprint_shift(phys, labels, ref, min_support=1)
    assert out[3] == 1                      # one seat: the single RARE die
    assert out[:2] == (2, 2)
