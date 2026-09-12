# -*- coding: utf-8 -*-
"""S-196 ②. The derived `map.input_columns` holds everything the validator demands of it.

🔴 ONE ENUMERATION, TWO CALLERS. The validator refuses an `input_columns` that misses a
column, and the authoring form DERIVES that same list — so they have to be answering one
question. They were not: the derivation is 「the prepared frame MINUS what `read` already
reads」, which subtracts away exactly the columns a group or a binding needs, and a bundle
rebuilt from it was refused by its own validator.

⛔ AND THE FIRST REPAIR WAS A HAND-WRITTEN LIST. I added the group columns only; `dt_job`
then passed and `bonded_from` fell over on its BINDING columns — `base_id`, `by` and five
more that no group mentions. A list extended by hand misses whatever the next declaration
uses, which is why the enumeration lives in one function that both sides call.

⛔ AND THE EVIDENCE WAS WRONG BEFORE THAT. I measured `config/sample/ledger_config.json.sample`
and reported a row unit inventing columns; the test opens
`DEFAULT_ONTOLOGY_ROOT/ledger_config.json`, where `dt_job` is a `group_by` unit. A ruling
stood on that. The subject of a measurement is the document the code under test OPENS.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from ledger.config_authoring import _with_required_columns                # noqa: E402
from ledger.setup_bundle import required_mapper_input_columns             # noqa: E402

GROUP = {"unit": {"kind": "group_by", "columns": ["dt_job"]}}
ROW = {"unit": {"kind": "row"}}
BOUND = {"mappings": {"s": {"bind": {"subject": {"kind": "column", "column": "base_id"}}}}}
NO_BINDINGS = {"mappings": {}}


# ---------------------------------------------------------------------------
# the enumeration
# ---------------------------------------------------------------------------

def test_a_group_unit_demands_its_group_columns():
    demanded = required_mapper_input_columns(GROUP, NO_BINDINGS, "p")
    assert [c for c, _ in demanded] == ["dt_job"]
    assert demanded[0][1] == "p.unit.columns", "the refusal must name where the demand is"


def test_a_row_unit_demands_nothing_of_its_own():
    """⚠️ 「없는 그룹」 MUST NOT BE INVENTED — `kind: "row"` is a declaration that there is no
    group, not an omission."""
    assert required_mapper_input_columns(ROW, NO_BINDINGS, "p") == ()
    assert required_mapper_input_columns(
        {"unit": {"kind": "row", "columns": ["x"]}}, NO_BINDINGS, "p") == ()


def test_bindings_are_demanded_too_and_that_was_the_second_cause():
    """🔴 THE CASE MY HAND-WRITTEN FIX MISSED. `bonded_from` needs binding columns no group
    mentions, so an enumeration covering only groups left it refused."""
    demanded = required_mapper_input_columns(ROW, BOUND, "p")
    assert [c for c, _ in demanded] == ["base_id"]
    assert "subject" in demanded[0][1], "it names the binding that wants it"


def test_both_kinds_ride_together_without_duplicates():
    both = {"mappings": {"s": {"bind": {"subject": {"kind": "column",
                                                    "column": "dt_job"}}}}}
    demanded = required_mapper_input_columns(GROUP, both, "p")
    assert [c for c, _ in demanded] == ["dt_job"], "a column demanded twice is listed once"


# ---------------------------------------------------------------------------
# the derivation asks it
# ---------------------------------------------------------------------------

def test_the_derived_list_gains_every_demanded_column():
    out = _with_required_columns(["dt_eqp", "event_time"], GROUP, BOUND, "p")
    assert set(out) >= {"dt_job", "base_id"}
    assert set(out) >= {"dt_eqp", "event_time"}, "the base list is not lost"


def test_the_base_order_is_kept_and_nothing_is_duplicated():
    """⚠️ APPENDED, NOT UNIONED-AND-SORTED. The base order is the prepared frame's, and a
    re-derivation that reordered it would show an operator a diff that means nothing."""
    out = _with_required_columns(["c", "a", "b"], GROUP, NO_BINDINGS, "p")
    assert out == ["c", "a", "b", "dt_job"], out


def test_a_half_built_profile_does_not_raise():
    """⚠️ THE AUTHORING FORM RUNS ON A BUNDLE BEING BUILT, where the validator only ever runs
    on a structurally sound one (`validate_bundle_errors` returns before cross-validation if
    anything is wrong). A derivation that raised on a half-written profile would blank the
    screen the operator is using to finish it."""
    assert _with_required_columns(["a"], GROUP, None, "p") == ["a"]
    assert _with_required_columns(["a"], GROUP, "not a mapping", "p") == ["a"]
    # 🔴 THESE THREE RAISED. Wiring the derivation to the validator's enumerator handed it a
    # STRICT traversal — `profile["mappings"]`, `mapping["bind"]` — which is safe only
    # because the validator never runs on a malformed bundle. The authoring form does
    # nothing else. Measured, then unified onto the tolerant traversal, which the same
    # measurement showed answers identically on all 15 live sources.
    for half_built in ({}, {"mappings": {"s": {}}}, {"mappings": {"s": {"bind": None}}}):
        assert _with_required_columns(["a"], GROUP, half_built, "p") == ["a", "dt_job"], (
            half_built)


# ---------------------------------------------------------------------------
# 🔴 one function, and it is the validator's
# ---------------------------------------------------------------------------

def test_the_derivation_calls_the_validators_enumeration():
    """⛔ SCORED ON THE SOURCE, because the failure mode is a SECOND enumeration that happens
    to agree today — which is exactly what this round found: two `profile_binding_columns`,
    measured identical on all 15 live sources, one of which was about to grow a third."""
    import inspect

    from ledger import config_authoring

    body = inspect.getsource(config_authoring._with_required_columns)
    assert "required_mapper_input_columns" in body
    for rebuilt in ("unit.get(", "mappings", "bind"):
        assert rebuilt not in body, ("the derivation enumerates for itself again: %s"
                                     % rebuilt)


def test_the_validator_calls_it_too():
    import inspect

    from ledger import setup_bundle

    source = inspect.getsource(setup_bundle)
    assert source.count("def required_mapper_input_columns(") == 1
    # ⚠️ THE CALL IS IN `_cross_validate`, not in `_cross_profile_source` — I asserted the
    # wrong function first and the gate caught it. Naming the seat matters: an assertion on
    # a function that never had the call would pass the day the call was deleted.
    cross = inspect.getsource(setup_bundle._cross_validate)
    assert "required_mapper_input_columns(" in cross
    # The only remaining uses of the raw enumerator are INSIDE the shared function and its
    # own definition — the validator no longer counts binding columns for itself.
    outside = source.replace(
        inspect.getsource(setup_bundle.required_mapper_input_columns), "").replace(
        inspect.getsource(setup_bundle._profile_binding_columns), "")
    assert "_profile_binding_columns(" not in outside, (
        "the validator counts binding columns for itself again")
