import json
from types import SimpleNamespace

from mappers import core_usage_mapper as mapper


EQUATION = {
    "core_x_base": "X", "core_x_sign": 1, "core_x_offset": 4,
    "core_y_base": "Y", "core_y_sign": 1, "core_y_offset": 4,
}


def _row(job, wafer, x, y, lot="L1", slot="S1"):
    return SimpleNamespace(dt_job=job, core_wafer=wafer, core_x=x, core_y=y,
                           core_lot=lot, core_slot=slot)


def test_usage_map_is_keyed_by_enriched_wafer_and_replaces_only_that_map():
    rows = [_row("J1", "W1", 1, 2), _row("J2", "W1", 1, 2), _row("J1", "W1", 2, 2)]
    batches = mapper._usage_batches(rows, {"J1": EQUATION, "J2": EQUATION}, "dt_job")
    assert len(batches) == 1
    assert batches[0]["scope"] == {"core_wafer": "W1"}
    first = batches[0]["updates"][0]["updates"]
    assert (first["core_x"], first["core_y"], first["used_count"]) == (5, 6, 2)
    assert first["used_dt_jobs"] == '["J1", "J2"]'


def test_lot_slot_only_rows_wait_for_wafer_enrichment():
    assert mapper._usage_batches([_row("J1", None, 1, 2)], {"J1": EQUATION}, "dt_job") == []


def test_wafer_separator_variants_share_one_usage_map():
    rows = [_row("J1", "wf.01", 1, 2), _row("J2", "WF-01", 2, 2)]
    batches = mapper._usage_batches(rows, {"J1": EQUATION, "J2": EQUATION}, "dt_job")
    assert len(batches) == 1
    assert batches[0]["scope"] == {"core_wafer": "WF-01"}


def test_usage_metadata_is_always_the_standard_front_zero_origin(monkeypatch):
    monkeypatch.setattr(mapper.map_meta_registrar, "meta_business_key",
                        lambda table, map_id: f"{table}_{map_id}")
    frame = {
        "grid_cols": 13, "grid_rows": 9,
        "grid_start_x": 7, "grid_start_y": 5,
        "grid_y_invert": True, "rotation": 180, "side": "back",
        "valid_die_ref": {"table": "valid_die_ref", "map_id": "CORE_DT"},
    }
    updates = mapper._usage_metadata_updates({"W1": {"J2", "J1"}},
                                              {"J1": mapper._standard_frame(frame)},
                                              "core_usage_map")
    assert len(updates) == 1
    metadata = json.loads(updates[0]["updates"]["grid_metadata"])
    assert metadata["side"] == "front"
    assert metadata["rotation"] == 0
    assert metadata["grid_start_x"] == metadata["grid_start_y"] == 1
    assert metadata["valid_die_ref"]["map_id"] == "CORE_DT"


def test_live_mapper_and_tracked_sample_are_byte_identical():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "mappers"
    assert (root / "core_usage_mapper.py").read_bytes() == \
           (root / "core_usage_mapper.py.sample").read_bytes()
