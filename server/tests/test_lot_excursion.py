"""The lot-excursion answer key (ruling R-2026-08-14-F), scored without a database.

`prove` reads the world through ONE function (`lot_table`), so replacing that function
lets both directions of the ruling's condition 2 be tested here rather than only against
`assy_manager` - which matters today, because condition 4 says the database run waits on
the owner's approval and an answer key nobody can execute is not an answer key.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..",
                                                "scripts")))

import ledger_lots  # noqa: E402
import seed_syn_lot_excursion as exc  # noqa: E402

BASELINE_PER_CHIP = 1.2248        # MEASURED on assy_manager 2026-08-14, 100 lots
BASELINE_EXTENT = 58.659


def _table(planted_ratio=None, rogue_lot_ratio=None, include_planted=True):
    """A synthetic lot table: 100 normal lots, then the excursion lots.

    Normal lots are spread across the measured band so the MEDIAN lands where the real
    one does - a fixture whose normal lots were all identical would make the baseline
    exact and hide any drift in how it is chosen.
    """
    table = {}
    for i in range(100):
        wobble = 1.0 + ((i % 11) - 5) * 0.012
        table["SYN-VOID-%03d" % (i + 1)] = {
            "scanned": 725,
            "found_rate": 0.6124 * wobble,
            "per_chip": BASELINE_PER_CHIP * wobble,
            "extent_mean": BASELINE_EXTENT * wobble,
            "last_at": 1000 + i,
        }
    if include_planted:
        for lot_number, spec in exc.EXCURSIONS.items():
            ratio = planted_ratio or spec["expect_min_ratio"] * 1.05
            table["SYN-VOID-%03d" % lot_number] = {
                "scanned": 725,
                "found_rate": spec["found_rate_target"],
                "per_chip": BASELINE_PER_CHIP * ratio,
                "extent_mean": BASELINE_EXTENT * ratio,
                "last_at": 2000 + lot_number,        # LATEST, per condition 3
            }
    if rogue_lot_ratio:
        table["SYN-VOID-007"]["per_chip"] = BASELINE_PER_CHIP * rogue_lot_ratio
    return table


@pytest.fixture
def patched(monkeypatch):
    def install(table):
        monkeypatch.setattr(exc, "lot_table", lambda db, kind=None: table)
    return install


def test_the_declaration_is_two_or_three_lots_and_they_are_late(patched):
    """Ruling condition 3, read off the declaration rather than off the generator."""
    assert 2 <= len(exc.EXCURSIONS) <= 3, "the ruling says 2-3 lots"
    assert all(str(n).isdigit() and n > 100 for n in exc.EXCURSIONS), (
        "excursion lots must sit after the existing 100, so they are late in production "
        "order")


def test_each_declared_ratio_actually_reaches_its_declared_level():
    """🔴 The declaration must not contradict itself.

    `expect_min_ratio` and `expect_level` are two statements about one plant. If the
    declared ratio fell short of the declared level, `prove` would demand a level the
    generator was never aimed at - and the answer key would fail for a reason that has
    nothing to do with the data.
    """
    ladder = sorted(ledger_lots.DEFAULT_THRESHOLDS, key=lambda t: t["at"])
    for lot, spec in exc.EXCURSIONS.items():
        reached = 0
        for threshold in ladder:
            if spec["expect_min_ratio"] >= threshold["at"]:
                reached = threshold["level"]
        assert reached >= spec["expect_level"], (
            f"lot {lot} declares level {spec['expect_level']} but its declared minimum "
            f"ratio {spec['expect_min_ratio']} only reaches level {reached}")


def test_the_planted_lots_light_up(patched):
    """Direction one."""
    patched(_table())
    report = exc.prove(None)
    assert not report["failures"], report["failures"]
    assert len(report["planted"]) == len(exc.EXCURSIONS)
    for lot, entry in report["planted"].items():
        assert entry["level"] >= 1, (lot, entry)


def test_the_unplanted_lots_do_not(patched):
    """🔴 Direction two - and it is the one that catches a grid that colours everything.

    A rogue normal lot at 2.5x is exactly what a broken threshold, a broken baseline, or
    a mis-scoped denominator would produce, and the first direction alone cannot see it.
    """
    patched(_table(rogue_lot_ratio=2.5))
    report = exc.prove(None)
    assert report["unplanted_over_threshold"], (
        "an unplanted lot at 2.5x the baseline was not reported - this assertion is the "
        "only thing standing between 'the grid works' and 'the grid colours everything'")
    assert any("unplanted" in f for f in report["failures"])


def test_absence_is_reported_as_pending_and_never_as_a_pass(patched):
    """Condition 4 lives here too: before the owner approves the run, nothing is planted.

    The answer key must say so rather than pass vacuously - a green on an empty fixture
    would be read as 'the grid is proven' by whoever runs it next.
    """
    patched(_table(include_planted=False))
    report = exc.prove(None)
    assert report["planted_present"] == []
    assert any("has not been applied" in f for f in report["failures"])


def test_the_trend_break_lands_at_the_end_of_the_series(patched):
    """Condition 3's other half: the excursion must also be the LATEST by scan time.

    `ledger_lots` orders rows by `inspection_run.observed_at`, so a lot that is last by
    NAME and middling by scan time would put the break in the wrong place.
    """
    table = _table()
    for lot_number in exc.EXCURSIONS:                 # make them EARLY instead
        table["SYN-VOID-%03d" % lot_number]["last_at"] = 1
    patched(table)
    report = exc.prove(None)
    assert any("not the latest" in f for f in report["failures"]), report["failures"]


def test_found_rate_is_declared_unscorable_and_the_arithmetic_still_holds():
    """🔴 The saturating column, pinned so a threshold change re-opens the question.

    `found_rate` is found/scanned, so it cannot exceed 1.0. Against the measured baseline
    the ceiling is ~1.63 and the first ladder step is 2.0 - meaning a lot where EVERY
    scanned chip has a finding still renders uncoloured. If somebody lowers the first
    threshold below the ceiling this test fails, which is the moment to delete the
    exclusion rather than keep explaining it.
    """
    assert "found_rate" in exc.UNSCORABLE_AGGREGATES
    assert "found_rate" not in exc.SCORED_AGGREGATES
    first_step = min(t["at"] for t in ledger_lots.DEFAULT_THRESHOLDS)
    ceiling = 1.0 / 0.6124
    assert ceiling < first_step, (
        f"found_rate's ceiling is now {ceiling:.3f} and the first threshold is "
        f"{first_step} - the column is reachable, so it should be SCORED, not excluded")


def test_the_cause_is_in_the_namespace_the_contrast_already_scores():
    """Ruling condition 1: the colour has to lead somewhere.

    The excursion's cause must be a value of a factor the existing case-control contrast
    already emits, or the chain grid -> reference view -> contrast breaks at the second
    arrow.
    """
    assert exc.EXCURSION_FACTOR.startswith("recipe_rev@BONDING="), exc.EXCURSION_FACTOR
    assert exc.EXCURSION_RECIPE[0] == "SYN-RCP-BOND"
    # a NEW revision, not a reuse of one the existing wafers already claim
    import seed_syn_process_ledger as proc
    assert exc.EXCURSION_RECIPE not in proc.RECIPES, (
        "the excursion must introduce a new revision; reusing an existing one would put "
        "two different recipe claims on wafers the ledger has already described")
