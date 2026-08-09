from dt_frame_transform import apply_dt_equations, core_equations, dt_equations


REFERENCE = {
    "grid_cols": 13, "grid_rows": 13,
    "grid_start_x": -6, "grid_start_y": -6,
    "grid_y_invert": False, "rotation": 0, "side": "front",
    "phys_wafer_dia": 300, "phys_chip_x": 7, "phys_chip_y": 7,
    "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3,
}


def _frame(rotation, start_x=-6, start_y=-6):
    return {**REFERENCE, "rotation": rotation,
            "grid_start_x": start_x, "grid_start_y": start_y}


def _asymmetric_valid_die_cells():
    # A non-full mask is essential: it exercises the same origin-box branch
    # that automatic confirmation uses once it stamps valid_die_ref.
    return [(x, y) for x in range(-6, 7) for y in range(-6, 7) if x * x + y * y <= 35]


def test_mask_aware_equations_do_not_translate_confirmed_rot90_or_rot180_frames():
    cells = _asymmetric_valid_die_cells()
    cases = [
        # These are the two origins auto confirmation can legitimately write to
        # redraw a masked source map.  Circle-only formula extraction used +9
        # and moved the standard map two rows down; the shared mask boxes yield
        # the generator's original reference coordinate instead.
        (_frame(90, start_x=-4), (6, 1)),
        (_frame(180, start_y=-4), (-1, 6)),
    ]
    for frame, raw in cases:
        equations = dt_equations(frame, REFERENCE, cells)
        assert equations["dt_y_offset"] == 7
        assert apply_dt_equations(*raw, equations)[1] == 1


def test_core_equations_are_the_same_transform_with_core_column_names():
    equations = core_equations(_frame(90, start_x=-4), REFERENCE, _asymmetric_valid_die_cells())
    assert equations == {
        "core_x_base": "Y", "core_x_sign": 1, "core_x_offset": 7,
        "core_y_base": "X", "core_y_sign": -1, "core_y_offset": 7,
    }
