"""The finding-kind registry, and the one rule the console is not allowed to break.

These are the guards for `server/finding_kinds.py`. The ANSWER KEY - "the planted factor
comes out and the decoys do not" - is not here: it needs the 2,500-wafer fixture and it
lives in `server/scripts/seed_syn_process_ledger.py --prove`, which runs against a real
database. What is here is everything that can be decided without one.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger_api import finding_kinds  # noqa: E402


#: 🔴 THE KINDS ARE DECLARED HERE NOW, BY THE TEST. `finding_kinds` used to ship a
#: code-held catalogue and these rules were measured against it; the catalogue is gone
#: (2026-08-27) and the registry starts empty, so a rule stated over `kinds()` would pass
#: over an EMPTY loop and assert nothing. Two kinds, with DIFFERENT scan methods, because
#: that difference is what one of these rules is about.
TWO_KINDS = {
    "alpha": {"label": "A", "observed_by": ["scan_a"], "observation_table": "void_obs",
              "extent_columns": ["radius_x", "radius_y"], "unit_column": "unit"},
    "beta": {"label": "B", "observed_by": ["scan_b"], "observation_table": "delam_obs",
             "extent_columns": ["extent_x"], "unit_column": "unit",
             "classes": ["one", "two"]},
}


@pytest.fixture(autouse=True)
def _clean_registry():
    finding_kinds.set_registry(None)
    yield
    finding_kinds.set_registry(None)


def test_an_undeclared_kind_is_refused_by_name_and_never_silently_defaulted():
    """A misspelled kind in a URL must not render the default kind's numbers.

    🔴 This is the failure that would be invisible: every figure on the screen would be
    correct, and every one of them would be about a different defect than the heading
    says. Refusing is the only outcome a reader can notice.
    """
    with pytest.raises(finding_kinds.FindingKindError) as exc:
        finding_kinds.spec("viod")
    assert "viod" in str(exc.value) and "declared" in str(exc.value)


def test_switching_kind_actually_switches_the_denominator():
    """No two kinds may share a scan method, or the generalization is untested.

    If both kinds were counted against `sat` runs, `finding=<kind>` could be a parameter
    that changes the numerator and nothing else - and a console with a hidden
    `WHERE finding_kind='void'` in its DENOMINATOR would pass every test anyone wrote.
    """
    finding_kinds.set_registry(TWO_KINDS)
    seen = {}
    for kind in finding_kinds.kinds():
        for method in finding_kinds.methods(kind):
            assert method not in seen, (
                f"kinds {seen[method]!r} and {kind!r} share method {method!r}; switching "
                f"between them would not move the denominator")
            seen[method] = kind


def test_a_kind_with_no_scan_has_no_denominator_and_says_so():
    """Empty `observed_by` means "no systematic scan looks for this" - a DECISION.

    The brief's answer for such a kind is to render "분모 없음 - 대조 불가" as content.
    That is only possible if the registry can express it, so empty is legal and ABSENT
    is not: a kind somebody forgot to give methods to must fail loudly rather than
    silently become the incidental-observation case.
    """
    finding_kinds.set_registry({
        "om_note": {"label": "OM", "observed_by": [], "observation_table": "void_obs",
                    "extent_columns": ["radius_x"]},
    })
    assert finding_kinds.has_denominator("om_note") is False

    finding_kinds.set_registry(None)
    finding_kinds._cache = None
    bad = {"om_note": {"label": "OM", "observation_table": "void_obs",
                       "extent_columns": ["radius_x"]}}
    with pytest.raises(finding_kinds.FindingKindError) as exc:
        finding_kinds.load.__wrapped__ if False else _load_with(bad)
    assert "observed_by" in str(exc.value)


def _load_with(registry):
    """Drive `load`'s validation over a hand-built registry.

    It used to swap the code-held catalogue in and out. That catalogue is gone, so the
    registry arrives the way every registry arrives now - through the config file - and
    the validation being measured is the same validation production runs.
    """
    import json
    import tempfile

    directory = tempfile.mkdtemp()
    path = os.path.join(directory, finding_kinds.CONFIG_FILENAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(registry, handle)
    saved = finding_kinds._config_path
    try:
        finding_kinds._config_path = lambda: path
        finding_kinds._cache = None
        return finding_kinds.load(force_reload=True)
    finally:
        finding_kinds._config_path = saved
        finding_kinds._cache = None


def test_the_observation_table_name_can_never_become_a_statement():
    """The table name is interpolated into SQL, so it is validated as an identifier."""
    with pytest.raises(finding_kinds.FindingKindError):
        _load_with({"x": {"label": "x", "observed_by": ["m"],
                          "observation_table": "void_obs; DROP TABLE bonding_log",
                          "extent_columns": ["a"]}})
        finding_kinds.observation_table("x")


def test_active_declaration_is_boolean_not_truthy_text():
    with pytest.raises(finding_kinds.FindingKindError) as exc:
        _load_with({"x": {"label": "X", "active": "false", "observed_by": ["xray"],
                          "observation_table": "x_obs", "extent_columns": ["span"]}})
    assert "active" in str(exc.value)


def test_clean_is_scanned_minus_found_and_never_absence_of_a_finding():
    """🔴 THE NON-NEGOTIABLE. A never-scanned package may not drift into the clean side.

    Measured on `assy_manager` 2026-08-14: for kind `void` the three populations are
    46,899 found / 28,101 clean-scanned / 280,001 never-scanned. Spelling the control set
    as "no finding row" would move all 280,001 into `clean` - the console's central claim
    ("these were LOOKED AT and were fine") would then be false for 91% of the rows
    supporting it, and nothing on screen would admit it.

    So the shape is asserted, not just documented: `kind_clean` is a set DIFFERENCE of
    two populations that both require a run, and `kind_unscanned` is what is left of the
    package universe.
    """
    finding_kinds.set_registry(TWO_KINDS)
    sql = finding_kinds.population_ctes("alpha")
    clean = sql.split("kind_clean AS (")[1].split("),")[0]
    assert "EXCEPT" in clean, "kind_clean must be a set difference"
    assert "kind_scanned" in clean and "kind_found" in clean
    assert "NOT EXISTS" not in clean, (
        "kind_clean must never be defined as the absence of a finding row - that is the "
        "drift this test exists for")
    unscanned = sql.split("kind_unscanned AS (")[1]
    assert "EXCEPT" in unscanned and "kind_scanned" in unscanned


def test_no_kind_name_is_baked_into_the_generated_sql():
    """The CTEs are the same text for every kind except the observation table."""
    finding_kinds.set_registry(TWO_KINDS)
    assert len(finding_kinds.kinds()) > 1, "this rule needs at least two kinds to mean anything"
    for kind in finding_kinds.kinds():
        sql = finding_kinds.population_ctes(kind)
        for other in finding_kinds.kinds():
            if other == kind:
                continue
            assert finding_kinds.observation_table(other) not in sql
        assert ":methods" in sql, "the denominator must be BOUND, never inlined"
