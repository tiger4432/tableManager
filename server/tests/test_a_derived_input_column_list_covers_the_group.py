# -*- coding: utf-8 -*-
"""S-196 ②. The derived `map.input_columns` contains the columns the unit groups by.

🔴 THE VALIDATOR REQUIRES IT: 「group_by columns must be mapper input columns」. The derivation
is 「the prepared frame MINUS what `read` already reads」, and a group column is usually exactly
one of the columns `read` reads — so it was subtracted away, and a bundle rebuilt from the
derivation was refused by its own validator.

⚠️ AND A ROW UNIT GETS NOTHING (판정 306). `unit.kind == "row"` is a declaration that there IS
no group; filling columns for it would invent one.

⛔ THE EVIDENCE FOR THIS WAS WRONG THE FIRST TIME. I measured `config/sample/ledger_config.json.sample`
and reported a row unit inventing columns; the test reads `DEFAULT_ONTOLOGY_ROOT/ledger_config.json`,
where `dt_job` is `{"kind": "group_by", "columns": ["dt_job"]}`. A ruling stood on that for
half an hour. The subject of a measurement is the document the code under test OPENS.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from ledger.config_authoring import (_with_group_columns,                # noqa: E402
                                     unit_group_columns)


def test_a_row_unit_declares_no_group():
    """⚠️ 「없는 그룹」 MUST NOT BE INVENTED — this is the half of 판정 306 that stands as a
    principle even though it was not the failing case."""
    assert unit_group_columns({"unit": {"kind": "row"}}) == []
    assert unit_group_columns({"unit": {"kind": "row", "columns": ["x"]}}) == [], (
        "a row unit's columns are not a group even if the file carries some")
    assert unit_group_columns({}) == [] and unit_group_columns({"unit": None}) == []


def test_a_group_unit_names_its_columns():
    assert unit_group_columns(
        {"unit": {"kind": "group_by", "columns": ["dt_job"]}}) == ["dt_job"]


def test_the_derived_list_contains_the_group_columns():
    """🔴 THE GATE. `dt_job` groups by `dt_job`, and `read` already reads it — so the base
    derivation subtracts it and the rebuilt bundle was refused."""
    derived = _with_group_columns(
        ["dt_eqp", "event_time"], {"unit": {"kind": "group_by", "columns": ["dt_job"]}})
    assert "dt_job" in derived
    assert set(derived) >= {"dt_eqp", "event_time"}, "the base list is not lost"


def test_the_base_order_is_kept_and_nothing_is_duplicated():
    """⚠️ APPENDED, NOT UNIONED-AND-SORTED. The base order is the prepared frame's, and a
    re-derivation that reordered it would show every operator a diff that means nothing."""
    base = ["c", "a", "b"]
    out = _with_group_columns(base, {"unit": {"kind": "group_by", "columns": ["a", "z"]}})
    assert out == ["c", "a", "b", "z"], out


def test_a_row_unit_leaves_the_derived_list_untouched():
    base = ["c", "a"]
    assert _with_group_columns(base, {"unit": {"kind": "row"}}) == base


def test_one_place_reads_the_unit():
    """🔴 TWO READERS OF ONE DECLARATION is how they come to disagree — and here they would
    disagree about whether a column is required to exist."""
    import inspect

    from ledger import config_authoring

    source = inspect.getsource(config_authoring)
    # ⛔ NO `or True` HERE. An assertion that cannot fail is the defect this repository keeps
    # paying for, and I wrote one into the first draft of this very test.
    assert source.count("def unit_group_columns(") == 1
    # The derivation reaches the unit ONLY through that function: no second `unit.get(
    # "columns")` anywhere outside it.
    outside = source.replace(inspect.getsource(config_authoring.unit_group_columns), "")
    assert 'unit.get("columns")' not in outside, (
        "a second reader of the unit's columns is back")
    assert outside.count("_with_group_columns(") >= 2, (
        "the derived value and its ground must both carry the group columns")
