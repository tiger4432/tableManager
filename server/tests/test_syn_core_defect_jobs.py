import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import seed_syn_core_defect_jobs as seed


META = {"grid_y_invert": False, "grid_cols": 9, "grid_rows": 9,
        "grid_start_x": -4, "grid_start_y": -4,
        "rotation": 0, "side": "front", "phys_wafer_dia": 300,
        "phys_chip_x": 7, "phys_chip_y": 7, "phys_offset_x": 0,
        "phys_offset_y": 0, "phys_edge_margin": 3}
CORE = [(x, y) for x in range(-4, 5) for y in range(-4, 5)]
DT = [(x, y) for x in range(-4, 5) for y in range(-4, 5)]


def test_clustered_core_seed_splits_one_wafer_without_duplicate_core_dies():
    bins, _centers, plans = seed.build_plans(CORE, META, DT, META, seed=8, job_count=3)
    rows = [row for plan in plans for row in plan["rows"]]
    missing = seed.missing_die_cells(CORE, META, seed=8)
    assert missing
    expected_physical = round(len(CORE) * seed.CORE_YIELD)
    assert len(rows) == expected_physical
    assert len({cell for plan in plans for cell in plan["core_cells"]}) == expected_physical
    assert not ({cell for plan in plans for cell in plan["core_cells"]} & missing)
    assert any(value != "B0" for value in bins.values())
    assert [plan["core_start_side"] for plan in plans] == ["TL", "TR", "TL"]
    assert seed.core_column_start(CORE, META, False) == (-4, -4)
    assert seed.core_column_start(CORE, META, True) == (4, -4)
    assert [plan["core_frame"] for plan in plans] != [
        "rot%d_front" % ((-int(plan["dt_frame"][3:plan["dt_frame"].index("_")])) % 360)
        for plan in plans]
    view_rows = seed.core_view_rows(plans)
    assert len(view_rows) == expected_physical
    assert {row["dt_job"] for row in view_rows} == {plan["job_id"] for plan in plans}
    assert all({"core_x", "core_y", "dt_index", "c_bn"} <= set(row) for row in view_rows)
    for plan in plans:
        indices = sorted(row["dt_index"] for row in view_rows if row["dt_job"] == plan["job_id"])
        assert indices == list(range(1, len(plan["rows"]) + 1))
