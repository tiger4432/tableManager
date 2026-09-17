# -*- coding: utf-8 -*-
"""참조뷰는 파생 표의 «어느 컬럼이든» 바인드할 수 있다 (S-136, 소유자 09-10 21:11).

🔴 THE SET WAS NARROWER THAN THE ROW. S-129 opened binding to `decision_key ∪ aggregation
names`, and the values were already read from the derived row - so `target_fields` and every
other declared column sat right there, readable, and could not be asked with. The owner's
words: 「쿼리에 아무 컬럼 붙이는 거 — 후자 해줘」.

⛔ ONE SPELLING FOR THE ALLOWED SET. The validator checks a view's `:names` against it and
the execution reads values from it. Built separately, a view could validate on load and then
be asked with a name nothing supplies - a declaration that passes and a query that fails in
front of an operator.

⚠️ ABSENT AND EMPTY ARE DIFFERENT FACTS. A column the derived row does not HAVE is refused
by name; a column it has whose value is empty binds as NULL - except the decision key, where
blank stays 「missing」 because `slot=''` builds a legal query that matches nothing.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import enrichment                                             # noqa: E402

CATALOGUE = {
    "s136_derived": {
        "column_types": {"lot": "string", "equipment": "string",
                         "bonding_time_min": "string", "wafer_id": "string"},
    },
}
RULE = {"name": "r", "derived_table": "s136_derived", "decision_key": ["lot"],
        "target_fields": ["wafer_id"],
        "aggregations": {"bonding_time_min": {"fn": "min", "column": "t"}}}


def test_every_declared_column_of_the_derived_row_is_bindable():
    names = enrichment.config.view_bind_names(RULE, CATALOGUE)

    assert names == {"lot", "equipment", "bonding_time_min", "wafer_id"}
    assert "equipment" in names, "a plain column, neither key nor aggregate"
    assert "wafer_id" in names, "a target field is a column of the row like any other"


def test_the_widening_is_worthless_unless_the_catalogue_is_handed_over():
    """🔴 S-163: the allowed set widened, the VALUE SUPPLY did not - on two seats.

    `view_bind_names` falls back to the pre-S-136 set when it cannot see the derived
    table, and that fallback is correct ("unknown table" is not "no columns"). But a
    CALLER that forgets to pass the catalogue gets that narrow set silently - so the
    operator binds a perfectly legal column, this says the name is not bindable, and the
    refusal surfaces one layer down as `missing required bind param(s)`. Measured in
    production by the owner.

    ⚠️ THE TWO HALVES ARE ASSERTED TOGETHER ON PURPOSE. Each is defensible alone; the
    defect is only visible as the DIFFERENCE between them.
    """
    row = {"lot": "L1", "equipment": "EQ1", "wafer_id": "W1"}

    with_catalogue = enrichment.config.view_bind_values(RULE, row,
                                                        known_tables=CATALOGUE)
    without = enrichment.config.view_bind_values(RULE, row)

    assert with_catalogue["equipment"] == "EQ1", (
        "a plain column of the derived row must be supplied, not just allowed")
    assert "equipment" not in without, (
        "this is the silent narrowing S-163 fixed - kept here so a caller that drops the "
        "catalogue is a RED TEST rather than a production refusal")


def test_the_validator_and_the_execution_read_one_function():
    """⛔ TWO SETS WOULD LET A VIEW VALIDATE AND THEN FAIL WHEN ASKED."""
    import inspect

    body = inspect.getsource(enrichment.config._normalize_reference_views)
    assert "derived_binds" in body, body[:900]

    assert inspect.getsource(enrichment.config.view_bind_names).count(
        "derived_columns(") == 1


def test_a_name_the_derived_row_does_not_carry_is_still_refused_by_name():
    assert "no_such_column" not in enrichment.config.view_bind_names(RULE, CATALOGUE)


def test_a_column_that_is_present_but_empty_binds_as_null_rather_than_going_missing():
    """🔴 「있고 비어 있다」는 그 행이 «아는» 사실이다. Dropping it would turn a row that says
    「this is empty」 into a view that cannot be asked at all."""
    values = enrichment.config.view_bind_values(
        RULE, {"lot": "L", "equipment": "", "bonding_time_min": None, "wafer_id": "W"},
        CATALOGUE)

    assert "equipment" in values and values["equipment"] == ""
    assert "bonding_time_min" in values and values["bonding_time_min"] is None

    view = {"query": "SELECT 1 WHERE e = :equipment AND m = :bonding_time_min",
            "required_binds": ["equipment", "bonding_time_min"],
            "blank_is_missing": []}

    assert enrichment.config.missing_binds(view, values) == []


def test_a_blank_decision_key_is_still_missing_because_it_matches_nothing():
    """⚠️ THE HALF THAT MUST NOT MOVE, and it is measured rather than preferred: `slot=''`
    builds a legal query that matches nothing, and a zero-row read cannot be told from
    「no such evidence exists」. Only the KEY columns keep that treatment."""
    view = {"query": "SELECT 1 WHERE lot = :lot", "required_binds": ["lot"],
            "blank_is_missing": ["lot"]}

    assert enrichment.config.missing_binds(view, {"lot": ""}) == ["lot"]
    assert enrichment.config.missing_binds(view, {"lot": "L"}) == []


def test_a_column_the_row_does_not_have_at_all_is_named_as_missing():
    view = {"query": "SELECT 1 WHERE e = :equipment", "required_binds": ["equipment"],
            "blank_is_missing": []}

    assert enrichment.config.missing_binds(view, {"lot": "L"}) == ["equipment"]


def test_a_view_that_never_went_through_the_normalizer_behaves_exactly_as_before():
    """⚠️ NO `blank_is_missing` KEY MEANS 「every bind is treated as a key」, which is what
    this function did before S-136. An old view must not change meaning."""
    view = {"query": "SELECT 1 WHERE lot = :lot", "required_binds": ["lot"]}

    assert enrichment.config.missing_binds(view, {"lot": ""}) == ["lot"]


def test_the_normalizer_stamps_only_the_key_columns_a_view_actually_binds():
    views = enrichment.config._normalize_reference_views(
        "r", [{"label": "x", "query": "SELECT 1 WHERE lot = :lot AND e = :equipment"}],
        ["lot"], ["wafer_id"], derived_binds={"lot", "equipment", "wafer_id"})

    assert views, "the view must survive validation with a non-key bind"
    assert views[0]["blank_is_missing"] == ["lot"]
    assert set(views[0]["required_binds"]) == {"lot", "equipment"}
