"""Unit contracts for the config-driven primary-core automatic mapper."""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import map_alignment


mapper = importlib.import_module("mappers.core_alignment_mapper")


def _row(index, wafer, lot="L1", slot="S1"):
    return SimpleNamespace(dt_index=index, core_wafer=wafer, core_lot=lot, core_slot=slot)


SELECTOR = {
    "group_columns": ["core_lot", "core_slot", "core_wafer"],
    "order_columns": ["dt_index", "core_lot", "core_slot", "core_wafer"],
}


def test_primary_core_is_the_lowest_dt_index_with_stable_tie_breaker():
    selected = mapper._primary_group([_row(9, "W2"), _row(3, "W2"), _row(1, "W1")], SELECTOR)
    assert selected["identity"] == {"core_lot": "L1", "core_slot": "S1", "core_wafer": "W1"}
    assert [row.dt_index for row in selected["rows"]] == [1]


def test_primary_core_rejects_incomplete_identity_instead_of_guessing():
    assert mapper._primary_group([_row(1, "")], SELECTOR) is None


def test_reference_table_and_map_id_are_entirely_config_driven():
    rule = {"reference": {"table": "physical_defect_map", "map_id_template": "{core_wafer}",
                          "fields": ["core_wafer"]}}
    assert mapper._reference_spec(rule, {"core_wafer": "WAFER-77"}) == "physical_defect_map:WAFER-77"


def test_gate_only_accepts_configured_metric_and_complete_winner():
    view = {"state": "scored", "ruling": {"winner": "rot0_tl", "metric": "values",
                                               "geometry_assumed": True, "thresholds_defaulted": []},
            "stats": {"truncated": False}, "sources": {"truncated": False},
            "reference": {"truncated": False, "table": "core_wafer_map", "map_id": "L_S"}}
    assert mapper._automatic_gate(view, {"accepted_metrics": ["values"],
                                         "allow_assumed_geometry": True})
    assert not mapper._automatic_gate(view, {"accepted_metrics": ["occupancy"],
                                             "allow_assumed_geometry": True})
    assert not mapper._automatic_gate(view, {"accepted_metrics": ["values"]})


def test_shift_search_derives_equations_without_a_later_mask_bbox():
    """The equation must use the same geometry authority that scored it.

    A shift-search result is relative to grid origins.  Feeding a valid-die
    mask only into the later equation step changes the affine offset for some
    rotations (observed on SYN-CORE-WAFER-01/P3).
    """
    meta, cells = {"grid_start_x": -3}, [(-3, -3), (0, 0)]
    assert mapper._equation_basis(
        {"placement": map_alignment.PLACEMENT_SEARCH}, meta, cells) == (None, None)


def test_anchor_placement_keeps_the_valid_die_geometry_for_equations():
    meta, cells = {"grid_start_x": -3}, [(-3, -3), (0, 0)]
    assert mapper._equation_basis(
        {"placement": map_alignment.PLACEMENT_ANCHOR}, meta, cells) == (meta, cells)


def test_live_mapper_and_tracked_sample_are_byte_identical():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "mappers"
    assert (root / "core_alignment_mapper.py").read_bytes() == \
           (root / "core_alignment_mapper.py.sample").read_bytes()
