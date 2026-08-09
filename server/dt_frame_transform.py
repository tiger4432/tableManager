"""Derive portable X/Y/sign/offset equations from confirmed DT frame metadata."""
from __future__ import annotations

import copy

import map_overlay


STANDARD_FRAME = {
    "rotation": 0,
    "side": "front",
    "grid_y_invert": False,
    "grid_start_x": 1,
    "grid_start_y": 1,
}


def standard_meta(frame_meta: dict) -> dict:
    """Same physical grid, fixed standard coordinate axes."""
    if not isinstance(frame_meta, dict):
        raise ValueError("dt_frame must be an object")
    out = copy.deepcopy(frame_meta)
    out.update(STANDARD_FRAME)
    return out


def _axis_equation(transform, origin_x: int, origin_y: int, output_index: int):
    """Read an affine signed-axis equation from the canonical transform itself."""
    p0 = transform(origin_x, origin_y)
    px = transform(origin_x + 1, origin_y)
    py = transform(origin_x, origin_y + 1)
    dx, dy = px[output_index] - p0[output_index], py[output_index] - p0[output_index]
    if (dx, dy) in ((1, 0), (-1, 0)):
        base, sign = "X", dx
        offset = p0[output_index] - sign * origin_x
    elif (dx, dy) in ((0, 1), (0, -1)):
        base, sign = "Y", dy
        offset = p0[output_index] - sign * origin_y
    else:
        raise ValueError("frame transform is not a signed X/Y affine coordinate map")
    return {"base": base, "sign": int(sign), "offset": int(offset)}


def dt_equations(frame_meta: dict, basis_meta: dict | None = None,
                 basis_cells=None) -> dict:
    """Return the four DT fields that express raw DT x/y → standard x/y."""
    target_meta = standard_meta(frame_meta)
    # A frame confirmed with valid_die_ref has an origin solved against that
    # reference's valid-die box.  Re-use those boxes here: deriving the affine
    # formula with circle boxes shifts 90/180-degree frames despite a correct
    # confirmed rotation.  An unresolved reference deliberately retains the
    # historical circle-box transform rather than guessing a mask.
    source_box = target_box = None
    if isinstance(basis_meta, dict) and basis_cells:
        mask = map_overlay.die_mask_from_reference(basis_meta, basis_cells)
        if mask:
            source_box = map_overlay.origin_box(frame_meta, mask)
            target_box = map_overlay.origin_box(target_meta, mask)
    transform = map_overlay.make_frame_transform(
        frame_meta, target_meta, source_box=source_box, target_box=target_box)
    origin_x = int(frame_meta.get("grid_start_x", 1))
    origin_y = int(frame_meta.get("grid_start_y", 1))
    x = _axis_equation(transform, origin_x, origin_y, 0)
    y = _axis_equation(transform, origin_x, origin_y, 1)
    return {
        "dt_x_base": x["base"], "dt_x_sign": x["sign"], "dt_x_offset": x["offset"],
        "dt_y_base": y["base"], "dt_y_sign": y["sign"], "dt_y_offset": y["offset"],
    }


def core_equations(frame_meta: dict, basis_meta: dict | None = None,
                   basis_cells=None) -> dict:
    """Return core fields that express raw core x/y in the standard frame."""
    equations = dt_equations(frame_meta, basis_meta, basis_cells)
    return {
        "core_x_base": equations["dt_x_base"],
        "core_x_sign": equations["dt_x_sign"],
        "core_x_offset": equations["dt_x_offset"],
        "core_y_base": equations["dt_y_base"],
        "core_y_sign": equations["dt_y_sign"],
        "core_y_offset": equations["dt_y_offset"],
    }


def apply_dt_equations(x, y, equations: dict) -> tuple[int, int]:
    """Apply the persisted portable formula; shared by the standard-map mapper."""
    if x is None or y is None:
        raise ValueError("DT raw coordinates are required")
    raw = {"X": int(x), "Y": int(y)}
    try:
        return (
            raw[equations["dt_x_base"]] * int(equations["dt_x_sign"]) + int(equations["dt_x_offset"]),
            raw[equations["dt_y_base"]] * int(equations["dt_y_sign"]) + int(equations["dt_y_offset"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("DT transformation equation is incomplete") from exc
