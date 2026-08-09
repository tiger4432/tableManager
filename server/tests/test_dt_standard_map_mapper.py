import json

from database import models
from mappers import dt_standard_map_mapper


FRAME = {
    "grid_cols": 10, "grid_rows": 8,
    "grid_start_x": 1, "grid_start_y": 1,
    "grid_y_invert": False, "rotation": 0, "side": "front",
    "phys_wafer_dia": 300, "phys_chip_x": 1, "phys_chip_y": 1,
    "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3,
    "valid_die_ref": {"table": "valid_die_ref", "map_id": "PRD-A_DT13"},
}


class _JobColumn:
    def __eq__(self, value):
        return value


class _DtLog:
    dt_job = _JobColumn()


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, job_id):
        assert job_id == "SYN-META-001"
        return self

    def all(self):
        return self.rows


class _Db:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        assert model is _DtLog
        return _Query(self.rows)


class _Row:
    def __init__(self, x, y, index, bin_value):
        self.dt_x, self.dt_y = x, y
        self.dt_index, self.c_bn = index, bin_value


def _payload():
    return {"data": {
        "dt_job": {"value": "SYN-META-001"},
        "dt_frame": {"value": json.dumps(FRAME)},
        "dt_x_base": {"value": "X"}, "dt_x_sign": {"value": 1}, "dt_x_offset": {"value": 0},
        "dt_y_base": {"value": "Y"}, "dt_y_sign": {"value": 1}, "dt_y_offset": {"value": 0},
    }}


def test_registers_standard_metadata_and_replaces_exactly_one_job(monkeypatch):
    monkeypatch.setitem(models.DYNAMIC_TABLES, "dt_log", _DtLog)
    monkeypatch.setattr(dt_standard_map_mapper.map_meta_registrar, "meta_business_key",
                        lambda table, map_id: f"{table}_{map_id}")
    monkeypatch.setattr(dt_standard_map_mapper.map_overlay, "load_map_meta",
                        lambda _db, table, map_id: {
                            "valid_die_ref": {"table": "valid_die_ref", "map_id": "PRD-SOURCE"}
                        } if (table, map_id) == ("dt_log", "SYN-META-001") else None)

    result = dt_standard_map_mapper.build_standard_dt_map_batches(
        _Db([_Row(1, 1, 1, "B4"), _Row(2, 3, 2, "B1")]), [_payload()],
    )

    meta = result["map_metadata_updates"]
    assert len(meta) == 1
    assert meta[0]["updates"]["target_table"] == "dt_map"
    assert meta[0]["updates"]["map_id"] == "SYN-META-001"
    standard = json.loads(meta[0]["updates"]["grid_metadata"])
    assert standard["grid_start_x"] == standard["grid_start_y"] == 1
    assert standard["rotation"] == 0 and standard["side"] == "front"
    assert standard["valid_die_ref"] == {"table": "valid_die_ref", "map_id": "PRD-SOURCE"}

    batch = result["batches"]
    assert len(batch) == 1
    assert batch[0]["replace_map"] is True
    assert batch[0]["scope"] == {"dt_job": "SYN-META-001"}
    assert [item["updates"] for item in batch[0]["updates"]] == [
        {"dt_job": "SYN-META-001", "dt_x": 1, "dt_y": 1, "dt_index": 1, "c_bn": "B4"},
        {"dt_job": "SYN-META-001", "dt_x": 2, "dt_y": 3, "dt_index": 2, "c_bn": "B1"},
    ]
