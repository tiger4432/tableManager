import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import seed_syn_dt_alignment_samples as samples


META = {
    "grid_cols": 13, "grid_rows": 13, "grid_start_x": 0, "grid_start_y": 0,
    "grid_y_invert": False, "rotation": 0, "side": "front",
    "phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
    "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0,
}
CELLS = [(5, 0), (6, 0), (7, 0), (4, 1), (5, 1), (6, 1), (7, 1), (8, 1)]


def test_top_left_and_top_right_reference_walks_begin_at_requested_corner():
    assert samples.ranked_reference_cells(CELLS, META, False)[0] == (5, 0)
    assert samples.ranked_reference_cells(CELLS, META, True)[0] == (7, 0)


def test_both_plans_have_continuous_index_and_unique_dt_destinations():
    left, left_frame = samples.build_job_rows("SYN-TL-1", CELLS, META,
                                              starts_at_top_right=False, rotation=0, seed=1)
    right, right_frame = samples.build_job_rows("SYN-TR-1", CELLS, META,
                                                starts_at_top_right=True, rotation=0, seed=2)

    assert left_frame == "rot0_front"
    assert right_frame == "rot0_front"
    assert {
        (row["core_x"], row["core_y"]): (row["dt_x"], row["dt_y"])
        for row in left
    } == {
        (row["core_x"], row["core_y"]): (row["dt_x"], row["dt_y"])
        for row in right
    }
    for rows, job in ((left, "SYN-TL-1"), (right, "SYN-TR-1")):
        assert [row["dt_index"] for row in rows] == list(range(1, len(CELLS) + 1))
        assert len({(row["dt_x"], row["dt_y"]) for row in rows}) == len(CELLS)
        assert {row["dt_job"] for row in rows} == {job}


def test_frames_cover_all_rotations_without_corner_mirroring():
    frames = {
        samples.build_job_rows("SYN", CELLS, META, starts_at_top_right=right,
                               rotation=rotation, seed=rotation)[1]
        for rotation in (0, 90, 180, 270)
        for right in (False, True)
    }
    assert frames == {"rot0_front", "rot90_front", "rot180_front", "rot270_front"}


def test_random_index_limit_is_reproducible_and_job_id_carries_plan_hash():
    limit = samples.choose_index_limit(len(CELLS), seed=20260809, label="TR", rotation=90)
    assert limit == samples.choose_index_limit(len(CELLS), seed=20260809, label="TR", rotation=90)
    assert 1 <= limit <= len(CELLS)

    positions = samples.choose_index_positions(limit, seed=20260809, label="TR", rotation=90)
    assert positions == samples.choose_index_positions(limit, seed=20260809, label="TR", rotation=90)
    assert positions[0] == 1 and positions[-1] == limit
    if limit > 2:
        assert len(positions) < limit

    job_id = samples.sample_job_id(CELLS, META, label="TR", starts_at_top_right=True,
                                   rotation=90, index_limit=limit, index_positions=positions,
                                   seed=20260809)
    rows, _frame = samples.build_job_rows(job_id, CELLS, META, starts_at_top_right=True,
                                          rotation=90, seed=2, index_limit=limit,
                                          index_positions=positions)
    assert "-N%03d-H" % limit in job_id
    assert len(rows) == len(positions)
    assert [row["dt_index"] for row in rows] == positions


def test_csv_writer_emits_one_dt_log_file_per_job(tmp_path):
    rows, frame = samples.build_job_rows("SYN-TL-R0-1", CELLS, META,
                                         starts_at_top_right=False, rotation=0, seed=1)
    paths = samples.write_csv_files(tmp_path, [("TL", "SYN-TL-R0-1", frame, rows)])

    assert [path.name for path in paths] == ["SYN-TL-R0-1.csv"]
    content = paths[0].read_text(encoding="utf-8").splitlines()
    assert content[0].split(",") == list(samples.DT_LOG_COLUMNS)
    assert len(content) == len(rows) + 1
