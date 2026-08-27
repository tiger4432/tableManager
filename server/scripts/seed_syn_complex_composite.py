"""Deterministic complex composite-CHIP R&D fixture (SYN-CX-* only).

The fixture is dry-run by default and writes only append-only ledger atoms through the
real gate/store path with ``--apply``.  It models the shape the R&D console must handle:

* several Core types and source lots with split, rework/resort, and multi-parent merge;
* 20+ ordered Core step/recipe events spanning PHOTO/ETCH/CMP/CLN, with long common
  spans, sparse recipe/sequence differences, and later reconvergence;
* separate canonical physical measurements with explicit missingness states;
* component identity moving through one to three DT collections before bonding;
* heterogeneous DT content and 10..15 independently sourced layers per final CHIP;
* defect/reference populations plus an explicit answer key for absence semantics.

No production row is updated.  Rollback is namespace-scoped to ``source_who`` and
``source_translator_ver`` and must be explicitly requested with ``--rollback``.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

from ledger.envelope import Atom, entity_ref  # noqa: E402


SOURCE = "syn_complex_composite"
TRANSLATOR = "syn_complex_composite/1/rules:complex-world1"
# Keep the deterministic browser fixture inside the console's 90-day window at the
# 2026-08-14 acceptance date.  Transfer and observation builders add up to 35 days;
# using the acceptance date itself as the base silently put every useful event in the
# future, so `/composition` correctly returned `empty` after a real server restart.
BASE_TIME = datetime(2026, 6, 1, 8, 0, tzinfo=timezone(timedelta(hours=9)))
ACCEPTANCE_NOW = datetime(2026, 8, 14, 23, 59, tzinfo=timezone(timedelta(hours=9)))
DERIV_LINEAGE = "syn_complex_lineage"
DERIV_PROCESS = "syn_complex_process"
DERIV_MEASUREMENT = "syn_complex_measurement"
DERIV_TRANSFER = "syn_complex_transfer"
DERIV_OBSERVATION = "syn_complex_observation"
DERIV_EXPERIMENT = "syn_complex_experiment_plan"
DERIVATIONS = frozenset({DERIV_LINEAGE, DERIV_PROCESS, DERIV_TRANSFER,
                         DERIV_OBSERVATION, DERIV_MEASUREMENT,
                         DERIV_EXPERIMENT})
SUBJECT_TYPES = frozenset({"Lot", "Wafer"})

CORE_TYPES = ("LOGIC", "HBM", "SENSOR", "POWER")
BRANCHES = ("A", "B", "C")
DT_LOTS = tuple(f"SYN-CX-DT-{i:02d}" for i in range(1, 11))
FINAL_CHIPS = tuple(f"SYN-CX-CHIP-{i:03d}" for i in range(1, 13))
BASE_WAFERS = tuple(f"SYN-CX-BW-{i:03d}" for i in range(1, 7))
DEFECT_CHIPS = frozenset(FINAL_CHIPS[:6])
REFERENCE_CHIPS = frozenset(FINAL_CHIPS[6:])
CAUSE_LEG = "HBM-B_LOW-P"
REFERENCE_LEG = "LOGIC-A_REF"
DT_OUTPUT_CASES = ("complete", "output_lot_missing", "output_slot_missing",
                   "recoverable_indirect", "unresolvable", "unknown",
                   "contradiction_candidate", "not_performed")
UI_PRESETS = {
    "defect_sample": sorted(DEFECT_CHIPS),
    "clean_reference": sorted(REFERENCE_CHIPS),
    "hero_defect": "SYN-CX-CHIP-006",
    "hero_reference": "SYN-CX-CHIP-012",
    "finding_kinds": ["void", "delam", "non_wet"],
}

# Spatial contract. Geometry is declared here and then persisted verbatim in the product
# SSOT (`wafer_map_metadata`); renderers must not infer a circle or dimensions from cells.
MAP_UPDATED_BY = "seed_syn_complex_composite"
MAP_SOURCE_NAME = "custom_script"
MAP_PRODUCT = "SYN-CX-MAP"
VALID_DIE_TYPE = "G12"
VALID_DIE_MAP_ID = f"{MAP_PRODUCT}_{VALID_DIE_TYPE}"
GRID_COLS = GRID_ROWS = 12
GRID_START_X = GRID_START_Y = 1
def _bond_spatial_spec(chip):
    population = "defect" if chip in DEFECT_CHIPS else "reference"
    if chip == UI_PRESETS["hero_defect"]:
        bond_lot = "SYN-CX-BOND-DEFECT"
    elif chip == UI_PRESETS["hero_reference"]:
        bond_lot = "SYN-CX-BOND-REFERENCE"
    else:
        chip_no = int(chip.rsplit("-", 1)[1])
        bond_lot = f"SYN-CX-BOND-{population.upper()}-{chip_no:03d}"
    return {"population": population, "chip": chip,
            "bonding_leg": CAUSE_LEG if population == "defect" else REFERENCE_LEG,
            "bond_lot": bond_lot, "bond_slot": "01"}


# One physical Bond map per Wafer experiment unit.  Every Bond map deliberately draws
# from both DT/Core families so any of the 12 aggregation units can open the full three-
# stage spatial trace; the two hero names remain stable for old browser presets.
BOND_SPATIAL_MAPS = tuple(_bond_spatial_spec(chip) for chip in FINAL_CHIPS)
DT_SPATIAL_MAPS = (("SYN-CX-DT-01", "01"), ("SYN-CX-DT-02", "02"))
CORE_SPATIAL_MAPS = (("SYN-CX-LOGIC-MRG", "11"),
                     ("SYN-CX-HBM-MRG", "22"))
CORE_SPATIAL_WAFERS = {
    CORE_SPATIAL_MAPS[0]: "SYN-CX-CW-LOGIC-A-01",
    CORE_SPATIAL_MAPS[1]: "SYN-CX-CW-HBM-B-02",
}


def is_designed_cause(component):
    """Test/oracle predicate derived from evidence; never persisted as an answer tag."""
    return (component.get("bonding_leg") == CAUSE_LEG
            and component.get("core_type") == "HBM"
            and component.get("core_branch") == "B")

COMMON_PREFIX = (
    "INGOT_RELEASE", "WAFER_SORT",
    "CLN_PRE_PHOTO_01", "PHOTO_COAT_01", "PHOTO_EXPOSE_01",
    "PHOTO_DEVELOP_01", "ETCH_PATTERN_01", "CLN_POST_ETCH_01",
    "CMP_BULK_01", "CLN_POST_CMP_01",
    "PHOTO_COAT_02", "PHOTO_EXPOSE_02", "PHOTO_DEVELOP_02",
    "ETCH_PATTERN_02", "CLN_POST_ETCH_02", "CMP_BULK_02",
    "CLN_POST_CMP_02", "THINNING", "ALIGN", "PRE_BOND_MI",
)
COMMON_SUFFIX = ("FINAL_CLEAN", "METROLOGY_RELEASE", "PACK_OUT")
BRANCH_MIDDLE = {
    "A": ("PLASMA_ACTIVATION", "BOND_PREP", "INLINE_SCAN"),
    "B": ("PLASMA_ACTIVATION", "REWORK_CLEAN", "BOND_PREP", "INLINE_SCAN"),
    "C": ("PLASMA_ACTIVATION", "RESORT", "BOND_PREP"),
}

# Process comparison is intentionally categorical.  Most recipes are common and fold;
# only these HBM/B steps receive a revision/name excursion.  Every numeric R&D signal
# lives in separate ``measured`` atoms below.
VOID_CORRELATED_RECIPE_STEPS = frozenset({
    "PHOTO_EXPOSE_02", "ETCH_PATTERN_02", "CMP_BULK_02", "CLN_POST_CMP_02",
})

# Separate post-process metrology.  These are physical output observations, not a
# repetition of process equipment telemetry.  A sparse set of
# HBM/B excursions gives Measurement comparison something to contrast while the common
# values still dominate and can be folded.  State-only rows deliberately carry no
# numeric sentinel (not even JSON null).
MEASUREMENT_SPECS = (
    {"metric": "photo_overlay_error", "unit": "um", "method": "overlay_metrology",
     "step": "PHOTO_EXPOSE_02", "step_family": "PHOTO", "eqp": "SYN-CX-MET-OVL-1",
     "normal": 0.18, "excursion": 0.42},
    {"metric": "etched_cd", "unit": "nm", "method": "cd_sem",
     "step": "ETCH_PATTERN_02", "step_family": "ETCH", "eqp": "SYN-CX-MET-CDSEM-1",
     "normal": 45.0, "excursion": 48.8},
    {"metric": "post_cmp_film_thickness", "unit": "nm", "method": "ellipsometry",
     "step": "CMP_BULK_02", "step_family": "CMP", "eqp": "SYN-CX-MET-ELLIP-1",
     "normal": 1180.0, "excursion": 1125.0},
    {"metric": "post_clean_surface_roughness", "unit": "nm", "method": "afm",
     "step": "CLN_POST_CMP_02", "step_family": "CLN", "eqp": "SYN-CX-MET-AFM-1",
     "normal": 0.72, "excursion": 1.28},
)
MEASUREMENT_STATE_CASES = {
    ("LOGIC", "A", 2, "photo_overlay_error"): "missing",
    ("HBM", "C", 1, "post_clean_surface_roughness"): "not_performed",
    ("SENSOR", "B", 2, "etched_cd"): "unknown",
}


def process_recipe(core_type, branch, step):
    """Return the common recipe or the sparse HBM/B categorical excursion."""
    excursion = core_type == "HBM" and branch == "B" \
        and step in VOID_CORRELATED_RECIPE_STEPS
    suffix = "-HBM-B-EXCURSION" if excursion else ""
    return {"id": f"SYN-CX-RCP-{step}{suffix}",
            "rev": "2" if excursion else "1"}


def core_lot(core_type, stage):
    return f"SYN-CX-{core_type}-{stage}"


def core_wafer(core_type, branch, index):
    return f"SYN-CX-CW-{core_type}-{branch}-{index:02d}"


def final_wafer(chip):
    chip_no = int(str(chip).rsplit("-", 1)[1])
    return BASE_WAFERS[(chip_no - 1) % len(BASE_WAFERS)]


def bonding_leg(chip):
    return CAUSE_LEG if chip in DEFECT_CHIPS else REFERENCE_LEG


def aggregation_unit(chip):
    return {"wafer": final_wafer(chip), "bonding_leg": bonding_leg(chip)}


def experiment_identity(chip):
    unit = aggregation_unit(chip)
    return {"type": "Wafer", "keys": {"wafer": unit["wafer"]},
            "context": {"role": "planned_bonding_experiment_unit",
                        "bonding_leg": unit["bonding_leg"]}}


def place(kind, keys, position):
    return {"type": kind, "keys": dict(keys), "position": dict(position)}


def valid_die_cells():
    """The declared G12 floor: 12x12 with two cells clipped at each corner."""
    cells = []
    for x in range(GRID_START_X, GRID_START_X + GRID_COLS):
        for y in range(GRID_START_Y, GRID_START_Y + GRID_ROWS):
            local_x, local_y = x - GRID_START_X, y - GRID_START_Y
            corner_distance = min(local_x + local_y,
                                  local_x + (GRID_ROWS - 1 - local_y),
                                  (GRID_COLS - 1 - local_x) + local_y,
                                  (GRID_COLS - 1 - local_x) +
                                  (GRID_ROWS - 1 - local_y))
            if corner_distance >= 2:
                cells.append((x, y))
    return cells


def leg_area_cells(leg):
    """Two disjoint 64-cell physical regions on one declared Base-WF floor."""
    if leg not in {CAUSE_LEG, REFERENCE_LEG}:
        raise ValueError(f"unknown bonding leg: {leg}")
    left = leg == CAUSE_LEG
    half = sorted((x, y) for x, y in valid_die_cells()
                  if (x <= 6 if left else x >= 7))
    # Each half has 66 valid cells. The two most edge-adjacent cells are outside the
    # declared bonding-use region; this is an explicit fixture declaration, not inference.
    return half[1:-1]


def process_area_cells(leg=None):
    """Declared per-LEG used area, or the disjoint union for the Base wafer."""
    if leg is not None:
        return leg_area_cells(leg)
    return sorted(leg_area_cells(CAUSE_LEG) + leg_area_cells(REFERENCE_LEG))


def defect_area_cells():
    return sorted((x, y) for x, y in leg_area_cells(CAUSE_LEG)
                  if x >= 4 and 8 <= y <= 10)


def spatial_supply_for_cell(x, y, *, defect=False):
    """Choose one of two declared DT/Core supply families for a Bond cell."""
    use_hbm = defect or (int(x) + int(y)) % 2 == 0
    return ((DT_SPATIAL_MAPS[1], CORE_SPATIAL_MAPS[1]) if use_hbm else
            (DT_SPATIAL_MAPS[0], CORE_SPATIAL_MAPS[0]))


def _grid_meta(*, with_floor=True):
    meta = {
        "phys_wafer_dia": 16.0, "phys_chip_x": 1.0, "phys_chip_y": 1.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 1.0,
        "grid_cols": GRID_COLS, "grid_rows": GRID_ROWS,
        "grid_start_x": GRID_START_X, "grid_start_y": GRID_START_Y,
        "grid_y_invert": False,
        "rotation": 0, "side": "front", "auto_registered": False,
        "fixture_declaration": "SYN-CX-G12-v1",
    }
    if with_floor:
        meta["valid_die_ref"] = {"table": "valid_die_ref",
                                 "map_id": VALID_DIE_MAP_ID}
    return meta


def map_metadata_rows():
    rows = [{"target_table": "valid_die_ref", "map_id": VALID_DIE_MAP_ID,
             "grid_metadata": json.dumps(_grid_meta(with_floor=False),
                                         ensure_ascii=False, sort_keys=True)}]
    # Current /lot_map deliberately resolves all three projection frames under its
    # source relation (`bonding_log`). Direct map consumers resolve DT/Core under their
    # physical tables. Register both declared namespaces; neither is guessed at read time.
    route_ids = [(m["bond_lot"], m["bond_slot"]) for m in BOND_SPATIAL_MAPS]
    route_ids += list(DT_SPATIAL_MAPS) + list(CORE_SPATIAL_MAPS)
    for lot, slot in route_ids:
        rows.append({"target_table": "bonding_log", "map_id": f"{lot}_{slot}",
                     "grid_metadata": json.dumps(_grid_meta(), ensure_ascii=False,
                                                 sort_keys=True)})
    for table, maps in (("dt_map", DT_SPATIAL_MAPS),
                        ("core_wafer_map", CORE_SPATIAL_MAPS)):
        for lot, slot in maps:
            rows.append({"target_table": table, "map_id": f"{lot}_{slot}",
                         "grid_metadata": json.dumps(_grid_meta(), ensure_ascii=False,
                                                     sort_keys=True)})
    for wafer in BASE_WAFERS:
        rows.append({"target_table": "bonding_map", "map_id": wafer,
                     "grid_metadata": json.dumps(_grid_meta(), ensure_ascii=False,
                                                 sort_keys=True)})
    return rows


def spatial_source_rows():
    """Return product-table rows for Bond/DT/Core projection and scan/finding overlays."""
    from ledger_api import finding_kinds
    from parsers import void_sat_format

    void_method = finding_kinds.methods("void")[0]
    scan_methods = sorted({method for kind in finding_kinds.kinds()
                           for method in finding_kinds.methods(kind)})
    bond_rows, bonding_map_rows, core_rows, runs, voids = [], [], [], [], []
    dt_rows_by_key = {}
    defects = set(defect_area_cells())
    root_layers = sorted({
        atom.object_payload["component"]["bond_layer"]
        for atom in transfer_atoms()
        if atom.object_payload["component"]["final_chip_id"] == UI_PRESETS["hero_defect"]
        and is_designed_cause(atom.object_payload["component"])})
    for map_spec in BOND_SPATIAL_MAPS:
        is_defect = map_spec["population"] == "defect"
        leg = map_spec["bonding_leg"]
        used = leg_area_cells(leg)
        wafer = final_wafer(map_spec["chip"])
        observed_at_text = (BASE_TIME + timedelta(days=40)).isoformat()
        for index, (x, y) in enumerate(used):
            is_cause_cell = is_defect and (x, y) in defects
            (dt_lot, dt_slot), (core_lot_id, core_slot) = spatial_supply_for_cell(
                x, y, defect=is_cause_cell)
            gate = root_layers[index % len(root_layers)] if is_cause_cell else 1
            bond_rows.append({
                "bond_lot": map_spec["bond_lot"], "bond_slot": map_spec["bond_slot"],
                "bond_x": x, "bond_y": y, "base_id": wafer, "bx": x, "by": y,
                "b_bn": "0" if is_cause_cell else "1", "stack_height": 15,
                "dt_lot": dt_lot, "dt_slot": dt_slot, "dt_x": x, "dt_y": y,
                "core_lot": core_lot_id, "core_slot": core_slot, "cx": x, "cy": y,
                "bond_eqp": ("SYN-CX-BONDER-LOWP" if leg == CAUSE_LEG
                             else "SYN-CX-BONDER-REF"),
                "event_time": observed_at_text,
            })
            core_map = (core_lot_id, core_slot)
            dt_key = (dt_lot, dt_slot, x, y)
            dt_row = {
                "dt_lot": dt_lot, "dt_slot": dt_slot, "dt_x": x, "dt_y": y,
                "c_bn": "0" if is_cause_cell else "1",
                "dt_job": f"SYN-CX-SPATIAL-{dt_lot}-{dt_slot}",
                "core_wafer": CORE_SPATIAL_WAFERS[core_map],
                "core_lot": core_lot_id, "core_slot": core_slot,
                "core_x": x, "core_y": y,
            }
            previous = dt_rows_by_key.setdefault(dt_key, dt_row)
            if previous != dt_row:
                raise RuntimeError(f"conflicting synthetic DT cell {dt_key}")
            run = {"method": void_method, "base_wafer_id": wafer,
                   "base_x": x, "base_y": y, "stack_gate": gate,
                   "recipe_id": "SYN-CX-MAP-INSPECT", "eqp_id": "SYN-CX-SAT-01",
                   "observed_at": observed_at_text}
            run_uid = void_sat_format.compose_business_key("inspection_run", run)
            if not run_uid:
                raise RuntimeError(f"inspection_run key unavailable for {wafer}@{x},{y}")
            run["run_uid"] = run_uid
            if is_cause_cell:
                voids.append({
                    "run_uid": run_uid, "base_wafer_id": wafer,
                    "base_x": x, "base_y": y, "stack_gate": gate,
                    "inchip_x": 5000.0 + x, "inchip_y": 5000.0 + y,
                    "radius_x": 8.0, "radius_y": 6.0, "unit": "um"})
    # Every final wafer has an explicit denominator for every registry-declared scan
    # method. Clean references are therefore scanned_clean, never inferred from the
    # absence of an observation. The hero void run keys intentionally match void_obs.
    for chip in FINAL_CHIPS:
        wafer = final_wafer(chip)
        leg = bonding_leg(chip)
        used = leg_area_cells(leg)
        for method in scan_methods:
            for index, (x, y) in enumerate(used):
                is_defect_cause = (chip in DEFECT_CHIPS
                                   and method == void_method and (x, y) in defects)
                gate = root_layers[index % len(root_layers)] if is_defect_cause else 1
                run = {"method": method, "base_wafer_id": wafer,
                       "base_x": x, "base_y": y, "stack_gate": gate,
                       "recipe_id": f"SYN-CX-{method.upper()}-INSPECT",
                       "eqp_id": f"SYN-CX-{method.upper()}-01",
                       "observed_at": (BASE_TIME + timedelta(days=40)).isoformat()}
                run_uid = void_sat_format.compose_business_key("inspection_run", run)
                if not run_uid:
                    raise RuntimeError(
                        f"inspection_run key unavailable for {method}:{wafer}@{x},{y}")
                run["run_uid"] = run_uid
                runs.append(run)
    for wafer in BASE_WAFERS:
        for leg in (CAUSE_LEG, REFERENCE_LEG):
            for x, y in leg_area_cells(leg):
                bonding_map_rows.append({"base": wafer, "x": x, "y": y, "leg": leg})
    valid_rows = [{"product": MAP_PRODUCT, "type": VALID_DIE_TYPE,
                   "x": x, "y": y, "val": "1"} for x, y in valid_die_cells()]
    for core_map in CORE_SPATIAL_MAPS:
        lot, slot = core_map
        wafer = CORE_SPATIAL_WAFERS[core_map]
        cause_map = core_map == CORE_SPATIAL_MAPS[1]
        for x, y in process_area_cells():
            core_rows.append({
                "core_lot": lot, "core_slot": slot, "core_x": x, "core_y": y,
                "c_bn": "0" if cause_map and (x, y) in defects else "1",
                "wafer_id": wafer, "event_time": observed_at_text,
            })
    return {"wafer_map_metadata": map_metadata_rows(),
            "valid_die_ref": valid_rows, "bonding_log": bond_rows,
            "bonding_map": bonding_map_rows,
            "dt_map": [dt_rows_by_key[key] for key in sorted(dt_rows_by_key)],
            "core_wafer_map": core_rows, "inspection_run": runs, "void_obs": voids}


def supply_material_layers(bond_rows=None):
    """Project stable supply identities for sorting-map colouring.

    ``bonding_log`` already records both physical source frames.  Material IDs are a
    deterministic presentation key over those declared identities, not an extra fact
    column and not a guessed join.  A Bond cell is supplied by one DT cell; a DT cell
    is supplied by one Core cell.
    """
    rows = bond_rows if bond_rows is not None else spatial_source_rows()["bonding_log"]
    bond, dt = defaultdict(list), defaultdict(dict)
    for row in rows:
        bond_map_id = f"{row['bond_lot']}_{row['bond_slot']}"
        dt_map_id = f"{row['dt_lot']}_{row['dt_slot']}"
        bond[bond_map_id].append({
            "x": row["bond_x"], "y": row["bond_y"],
            "material_id": (f"DT:{row['dt_lot']}:{row['dt_slot']}:"
                            f"{row['dt_x']}:{row['dt_y']}"),
        })
        dt_cell = {
            "x": row["dt_x"], "y": row["dt_y"],
            "material_id": (f"CORE:{row['core_lot']}:{row['core_slot']}:"
                            f"{row['cx']}:{row['cy']}"),
        }
        dt_key = (dt_cell["x"], dt_cell["y"])
        previous = dt[dt_map_id].setdefault(dt_key, dt_cell)
        if previous != dt_cell:
            raise RuntimeError(f"conflicting supply identity for {dt_map_id}@{dt_key}")
    sort_cells = lambda cells: sorted(cells, key=lambda cell: (cell["y"], cell["x"],
                                                               cell["material_id"]))
    return {"bond": {map_id: sort_cells(cells) for map_id, cells in sorted(bond.items())},
            "dt": {map_id: sort_cells(cells.values())
                   for map_id, cells in sorted(dt.items())}}


def spatial_answer_key():
    valid, used, defects = valid_die_cells(), process_area_cells(), defect_area_cells()
    supply = supply_material_layers()
    core_defects = {
        f"{lot}_{slot}": ([{"x": x, "y": y, "value": "0"}
                            for x, y in defects]
                           if (lot, slot) == CORE_SPATIAL_MAPS[1] else [])
        for lot, slot in CORE_SPATIAL_MAPS}
    return {
        "coordinate_unit": "cells_from_origin",
        "grid": _grid_meta(), "valid_die_map_id": VALID_DIE_MAP_ID,
        "axes": {
            "bond": [f"{m['bond_lot']}_{m['bond_slot']}" for m in BOND_SPATIAL_MAPS],
            "dt": [f"{lot}_{slot}" for lot, slot in DT_SPATIAL_MAPS],
            "core": [f"{lot}_{slot}" for lot, slot in CORE_SPATIAL_MAPS]},
        "overlay_order": ["valid_die", "process_area", "used_in_bonding", "defect"],
        "layers": {"supply_material": supply, "defect": core_defects},
        "map_payloads": {
            map_id: {"layers": {"defect": cells}}
            for map_id, cells in core_defects.items()},
        "supply_material_contract": {
            "shape": "layers.supply_material.<bond|dt>.<map_id>[{x,y,material_id}]",
            "bond_material_id": "DT:<dt_lot>:<dt_slot>:<dt_x>:<dt_y>",
            "dt_material_id": "CORE:<core_lot>:<core_slot>:<cx>:<cy>",
            "source": "declared bonding_log source-frame columns",
            "semantics": "색상은 개별 transfer event가 아니라 동일 공급 재료 ID 그룹"},
        "core_defect_contract": {
            "shape_per_map": "layers.defect[{x,y,value}]",
            "source": "core_wafer_map.c_bn at declared core_x/core_y",
            "defect_value": "0", "normal_value": "1",
            "answer_tags_persisted": False},
        "aggregation_units": [dict(aggregation_unit(chip), final_chip_id=chip)
                           for chip in FINAL_CHIPS],
        "leg_regions": {
            leg: [{"x": x, "y": y} for x, y in leg_area_cells(leg)]
            for leg in (CAUSE_LEG, REFERENCE_LEG)},
        "bond_map_analysis_bridge": {
            f"{spec['bond_lot']}_{spec['bond_slot']}": {
                **aggregation_unit(spec["chip"]), "final_chip_id": spec["chip"],
                "cells": [{"x": x, "y": y}
                          for x, y in leg_area_cells(spec["bonding_leg"])]}
            for spec in BOND_SPATIAL_MAPS},
        "counts": {"valid_die": len(valid), "process_area_per_bond_map": 64,
                   "defect_on_hero": len(defects), "defect_on_reference": 0},
        "root_cause_spatial_mark": {
            "bond_map": f"{BOND_SPATIAL_MAPS[0]['bond_lot']}_01",
            "dt_map": f"{DT_SPATIAL_MAPS[1][0]}_{DT_SPATIAL_MAPS[1][1]}",
            "core_map": f"{CORE_SPATIAL_MAPS[1][0]}_{CORE_SPATIAL_MAPS[1][1]}",
            "cells": [{"x": x, "y": y} for x, y in defects],
            "expected_signal": "HBM branch-B / rework / plasma 505W / multi-DT regroup"},
        "clean_contrast": {"bond_map": f"{BOND_SPATIAL_MAPS[1]['bond_lot']}_01",
                           "same_base_wafer": True, "same_region_cardinality": True,
                           "defect_cells": []},
    }


def _atom(subject_type, subject_keys, predicate, object_kind, payload, when,
          raw_ref, derivation, molecule):
    return Atom(subject_type=subject_type, subject_keys=subject_keys,
                predicate=predicate, object_kind=object_kind,
                object_payload=payload, occurred_at=when, source_who=SOURCE,
                source_translator_ver=f"{TRANSLATOR}#{derivation}",
                source_raw_ref=raw_ref, derivation=derivation,
                molecule_ref=molecule)


def _register(entity_type, keys, minute):
    name = "|".join(f"{key}={keys[key]}" for key in sorted(keys))
    return _atom(entity_type, keys, "register", None, None,
                 BASE_TIME + timedelta(minutes=minute),
                 f"{SOURCE}:register:{entity_type}:{name}", DERIV_LINEAGE,
                 f"register:{entity_type}:{name}")


def lineage_atoms():
    """Lot split/merge claims and membership, expressed in the active vocabulary."""
    atoms = []
    minute = 0
    for core_type in CORE_TYPES:
        root = core_lot(core_type, "ROOT")
        a, b = core_lot(core_type, "A"), core_lot(core_type, "B")
        c = core_lot(core_type, "C")
        b_rw = core_lot(core_type, "B-RWK")
        c_rs = core_lot(core_type, "C-RST")
        merged = core_lot(core_type, "MRG")
        lots = (root, a, b, c, b_rw, c_rs, merged)
        for lot in lots:
            atoms.append(_register("Lot", {"lot": lot}, minute)); minute += 1

        # ROOT splits three ways. B and C take explicit rework/resort hops. MRG has
        # three parents: no representative branch is allowed to erase the others.
        parents = ((a, root, "split-A"), (b, root, "split-B"),
                   (c, root, "split-C"), (b_rw, b, "rework"),
                   (c_rs, c, "resort"), (merged, a, "merge-A"),
                   (merged, b_rw, "merge-B"), (merged, c_rs, "merge-C"))
        for child, parent, operation in parents:
            atoms.append(_atom(
                "Lot", {"lot": child}, "derived_from", "entity_ref",
                entity_ref("Lot", {"lot": parent}), BASE_TIME + timedelta(minutes=minute),
                f"{SOURCE}:lot-event:{operation}:{child}:{parent}", DERIV_LINEAGE,
                f"lineage:{child}:{parent}"))
            minute += 1

        final_branch_lot = {"A": a, "B": b_rw, "C": c_rs}
        for branch in BRANCHES:
            lot = final_branch_lot[branch]
            for index in range(1, 4):
                wafer = core_wafer(core_type, branch, index)
                atoms.append(_register("Wafer", {"wafer": wafer}, minute)); minute += 1
                atoms.append(_atom(
                    "Lot", {"lot": lot}, "has_wafer", "entity_ref",
                    entity_ref("Wafer", {"wafer": wafer}, slot=f"{index:02d}"),
                    BASE_TIME + timedelta(minutes=minute),
                    f"{SOURCE}:membership:{lot}:{wafer}", DERIV_LINEAGE,
                    f"membership:{lot}:{wafer}"))
                minute += 1
                # After regrouping the same physical wafer has a new slot in MRG.
                atoms.append(_atom(
                    "Lot", {"lot": merged}, "has_wafer", "entity_ref",
                    entity_ref("Wafer", {"wafer": wafer}, slot=f"{BRANCHES.index(branch)+1}{index}"),
                    BASE_TIME + timedelta(minutes=minute),
                    f"{SOURCE}:membership:{merged}:{wafer}", DERIV_LINEAGE,
                    f"membership:{merged}:{wafer}"))
                minute += 1
    return atoms


def process_atoms():
    """Core-wafer processes: 20+ ordered step/recipe claims with sparse divergence."""
    atoms = []
    for type_no, core_type in enumerate(CORE_TYPES):
        for branch_no, branch in enumerate(BRANCHES):
            for index in range(1, 4):
                wafer = core_wafer(core_type, branch, index)
                steps = COMMON_PREFIX + BRANCH_MIDDLE[branch] + COMMON_SUFFIX
                for sequence, step in enumerate(steps):
                    # One expected measurement is absent on A-02. The absence is in the
                    # answer key, not encoded as a fake value atom.
                    if branch == "A" and index == 2 and step == "INLINE_SCAN":
                        continue
                    payload = {"step": step,
                               "recipe": process_recipe(core_type, branch, step)}
                    atoms.append(_atom(
                        "Wafer", {"wafer": wafer}, "processed_with", "value", payload,
                        BASE_TIME + timedelta(days=1 + type_no, hours=branch_no,
                                              minutes=index * 20 + sequence),
                        f"{SOURCE}:process:{wafer}:{sequence}:{step}", DERIV_PROCESS,
                        f"process:{wafer}:{sequence}"))
    return atoms


def measurement_atoms():
    """Post-process Core-wafer metrology with explicit non-numeric absence states."""
    atoms = []
    for type_no, core_type in enumerate(CORE_TYPES):
        for branch_no, branch in enumerate(BRANCHES):
            for index in range(1, 4):
                wafer = core_wafer(core_type, branch, index)
                for metric_no, spec in enumerate(MEASUREMENT_SPECS):
                    state = MEASUREMENT_STATE_CASES.get(
                        (core_type, branch, index, spec["metric"]), "recorded")
                    payload = {
                        "metric": spec["metric"], "unit": spec["unit"],
                        "method": spec["method"], "state": state,
                        "step": spec["step"], "step_family": spec["step_family"],
                        "eqp": spec["eqp"],
                        "recipe": process_recipe(core_type, branch, spec["step"]),
                        "stat": "wafer_mean",
                    }
                    if state == "recorded":
                        payload.update({
                            "value": (spec["excursion"]
                                      if core_type == "HBM" and branch == "B"
                                      else spec["normal"]),
                            "run_uid": f"SYN-CX-MET:{wafer}:{spec['metric']}",
                        })
                    atoms.append(_atom(
                        "Wafer", {"wafer": wafer}, "measured", "value", payload,
                        BASE_TIME + timedelta(days=8 + type_no, hours=branch_no,
                                              minutes=index * 10 + metric_no),
                        f"{SOURCE}:measurement:{wafer}:{spec['metric']}",
                        DERIV_MEASUREMENT,
                        f"measurement:{wafer}:{spec['metric']}"))
    return atoms


def bonding_leg_process_atoms():
    """Final-bond claims on Wafer, scoped by the planned experiment-unit value."""
    atoms = []
    for chip_no, chip in enumerate(FINAL_CHIPS):
        leg = bonding_leg(chip)
        payload = {
            "step": "FINAL_BOND",
            "recipe": {"id": f"SYN-CX-RCP-{leg}", "rev": "1"},
            "bonding_leg": leg,
        }
        atoms.append(_atom(
            "Wafer", {"wafer": final_wafer(chip)}, "processed_with", "value", payload,
            BASE_TIME + timedelta(days=6, minutes=chip_no),
            f"{SOURCE}:bond-process:{chip}:{leg}", DERIV_PROCESS,
            f"bond-process:{chip}:{leg}"))
    return atoms


def _component_resolution(chip_no, layer):
    return ("resolved", "resolved", "candidate", "contested", "resolved",
            "unresolvable")[(chip_no + layer) % 6]


def layers_for_chip(chip_no):
    return 10 + (chip_no % 6)


def transfer_atoms():
    atoms = []
    for chip_no, chip in enumerate(FINAL_CHIPS):
        layer_count = layers_for_chip(chip_no)
        for layer in range(1, layer_count + 1):
            core_type = CORE_TYPES[(layer + chip_no) % len(CORE_TYPES)]
            # Defect population is enriched for branch B but still heterogeneous.
            if chip in DEFECT_CHIPS and layer % 3:
                branch = "B"
            else:
                branch = BRANCHES[(layer + chip_no) % len(BRANCHES)]
            # The designed cause is a COMBINATION, not a branch label: HBM/B after
            # rework, with the BOND_PREP plasma excursion. Reference chips deliberately
            # keep branch-B confounders on other types but never this exact combination.
            if chip in REFERENCE_CHIPS and core_type == "HBM" and branch == "B":
                branch = "A"
            wafer_index = 1 + ((layer * 2 + chip_no) % 3)
            wafer = core_wafer(core_type, branch, wafer_index)
            component = f"{chip}:L{layer:02d}"
            core_position = {"x": 10 + layer, "y": 20 + chip_no,
                             "die_id": f"D{layer:02d}-{chip_no:02d}"}
            current = place("wafer_grid", {"wafer": wafer}, core_position)
            hops = 1 + ((layer + chip_no) % 3)  # one, two, or three DTs
            output_case = DT_OUTPUT_CASES[(chip_no + layer) % len(DT_OUTPUT_CASES)]
            if output_case == "not_performed":
                hops = 0
            designed_cause = chip in DEFECT_CHIPS and core_type == "HBM" and branch == "B"
            if designed_cause:
                hops = max(hops, 2)  # the cause is carried through a DT regroup.
            state = _component_resolution(chip_no, layer)
            meta = {
                "final_chip_id": chip, "component_id": component,
                "base_wafer_id": final_wafer(chip),
                "bonding_leg": bonding_leg(chip),
                "core_type": core_type, "role": f"stack_layer_{layer:02d}",
                "bond_layer": layer, "bond_position": {"chip_x": 0, "chip_y": 0},
                "core_lot": core_lot(core_type, "MRG"),
                "core_slot": None if state == "unresolvable" else f"{wafer_index:02d}",
                "state": state,
                "final_wafer_id": final_wafer(chip),
                "dt_output_case": output_case,
                "core_branch": branch,
            }
            for sequence in range(hops):
                dt_index = ((chip_no * 3 + layer + sequence * 4) % len(DT_LOTS))
                output_job = f"SYN-CX-DTJ-{chip_no + 1:03d}-{layer:02d}-{sequence:02d}"
                output_lot = f"SYN-CX-DTO-{dt_index + 1:02d}"
                output_slot = f"{1 + ((layer * 3 + sequence) % 24):02d}"
                if sequence == 0 and output_case in {"output_lot_missing",
                                                     "recoverable_indirect",
                                                     "unresolvable", "unknown"}:
                    output_lot = None
                if sequence == 0 and output_case in {"output_slot_missing",
                                                     "unresolvable", "unknown"}:
                    output_slot = None
                target = place(
                    "dt_slot", {"dt_lot": DT_LOTS[dt_index],
                                "dt_slot": f"{1 + ((layer + sequence) % 24):02d}"},
                    {"x": 30 + layer + sequence, "y": 5 + chip_no,
                     "tape_index": sequence})
                # Output identity is evidence ABOUT the physical DT container, not part
                # of that container's identity. Keeping it outside `keys` prevents null
                # lot/slot values or different jobs from minting fake DT entities.
                target["output"] = {"job": output_job, "lot": output_lot,
                                    "slot": output_slot}
                payload = {"from": current, "to": target, "qty": 1,
                           "sequence": sequence, "component": meta,
                           "operation": "load" if sequence == 0 else
                                        ("regroup" if sequence == hops - 1 else "split")}
                if sequence > 0 and output_case == "recoverable_indirect":
                    payload["output_identity_evidence"] = {
                        "job": (current.get("output") or {}).get("job"),
                        "output_lot": f"SYN-CX-DTO-REC-{chip_no + 1:03d}",
                        "output_slot": f"{layer:02d}", "resolution": "indirect"}
                if sequence > 0 and output_case == "contradiction_candidate":
                    payload["output_identity_evidence"] = {
                        "job": (current.get("output") or {}).get("job"),
                        "claims": [
                            {"output_lot": (current.get("output") or {}).get("lot"),
                             "output_slot": (current.get("output") or {}).get("slot")},
                            {"output_lot": "SYN-CX-DTO-CONFLICT",
                             "output_slot": "99"}],
                        "resolution": "candidate_conflict"}
                atoms.append(_atom(
                    "Wafer", {"wafer": wafer}, "transferred", "value", payload,
                    BASE_TIME + timedelta(days=7 + chip_no, minutes=layer * 10 + sequence),
                    f"{SOURCE}:transfer:{component}:{sequence}", DERIV_TRANSFER,
                    f"transfer:{component}"))
                current = target
            bond = place("bond_layer", {"final_chip_id": chip,
                                         "bond_wafer": final_wafer(chip),
                                         "base_wafer_id": final_wafer(chip),
                                         "bonding_leg": bonding_leg(chip),
                                         "layer": layer},
                         {"chip_x": 0, "chip_y": 0, "layer": layer})
            sequence = hops
            atoms.append(_atom(
                "Wafer", {"wafer": wafer}, "transferred", "value",
                {"from": current, "to": bond, "qty": 1, "sequence": sequence,
                 "component": meta, "operation": "pick_and_bond"},
                BASE_TIME + timedelta(days=7 + chip_no, minutes=layer * 10 + sequence),
                f"{SOURCE}:transfer:{component}:{sequence}", DERIV_TRANSFER,
                f"transfer:{component}"))
    return atoms


def observation_atoms():
    """Defect findings only; reference scans stay an explicit contract gap, never fake 0."""
    atoms = []
    for chip_no, chip in enumerate(sorted(DEFECT_CHIPS)):
        wafer = final_wafer(chip)
        leg = bonding_leg(chip)
        for finding_no, finding_kind in enumerate(("void", "delam", "non_wet")):
            payload = {
                "finding_kind": finding_kind, "method": "SYN_CX_INSPECTION",
                "run_uid": f"SYN-CX-RUN-{chip_no:02d}-{finding_no}",
                "final_chip_id": chip, "bonding_leg": leg,
                "position": {"x": chip_no + finding_no, "y": finding_no},
            }
            atoms.append(_atom(
                "Wafer", {"wafer": wafer},
                "observed", "value", payload,
                BASE_TIME + timedelta(days=30 + chip_no, minutes=finding_no),
                f"{SOURCE}:observation:{chip}:{finding_kind}", DERIV_OBSERVATION,
                f"observation:{chip}:{finding_kind}"))
    # WF-internal spatial findings point at the same declared HBM-B map cells as the
    # physical c_bn defects. No answer tag is persisted; expected grouping stays in
    # spatial_answer_key/tests only.
    core_map = CORE_SPATIAL_MAPS[1]
    wafer = CORE_SPATIAL_WAFERS[core_map]
    for x, y in defect_area_cells():
        payload = {
            "finding_kind": "void", "method": "SYN_CX_CORE_WF_MAP",
            "run_uid": f"SYN-CX-CORE-WF-{x:02d}-{y:02d}",
            "map_id": f"{core_map[0]}_{core_map[1]}",
            "position": {"x": x, "y": y}, "value": "0",
        }
        atoms.append(_atom(
            "Wafer", {"wafer": wafer}, "observed", "value", payload,
            BASE_TIME + timedelta(days=40, minutes=x * GRID_ROWS + y),
            f"{SOURCE}:core-map-observation:{wafer}:{x}:{y}", DERIV_OBSERVATION,
            f"core-map-observation:{wafer}:{x}:{y}"))
    return atoms


def experiment_plan_atoms():
    """One non-entity plan Claim per distinct bonding_map experiment region."""
    atoms = [_register("Wafer", {"wafer": wafer}, 900 + wafer_no)
             for wafer_no, wafer in enumerate(BASE_WAFERS)]
    for unit_no, chip in enumerate(FINAL_CHIPS):
        wafer, leg = final_wafer(chip), bonding_leg(chip)
        payload = {
            "experiment_type": "bonding_leg",
            "unit_id": leg,
            "map_ref": {"table": "bonding_map", "base": wafer, "leg": leg},
            "planned_by": "human_doe",
        }
        atoms.append(_atom(
            "Wafer", {"wafer": wafer}, "assigned_to_experiment", "value", payload,
            BASE_TIME + timedelta(minutes=910 + unit_no),
            f"bonding_map:{wafer}:{leg}", DERIV_EXPERIMENT,
            f"bonding-map-plan:{wafer}:{leg}"))
    return atoms


def build_atoms():
    return (lineage_atoms() + process_atoms() + measurement_atoms()
            + experiment_plan_atoms() + bonding_leg_process_atoms()
            + transfer_atoms() + observation_atoms())


def answer_key(atoms=None):
    atoms = atoms or build_atoms()
    transfers = [a for a in atoms if a.predicate == "transferred"]
    measurements = [a for a in atoms if a.predicate == "measured"]
    by_component = defaultdict(list)
    dt_types = defaultdict(set)
    for atom in transfers:
        meta = atom.object_payload["component"]
        by_component[meta["component_id"]].append(atom)
        for end in (atom.object_payload["from"], atom.object_payload["to"]):
            if end["type"] == "dt_slot":
                dt_types[(end["keys"]["dt_lot"], end["keys"]["dt_slot"])].add(
                    meta["core_type"])
    cases = {
        core_wafer("LOGIC", "A", 2): "missing_record",
        core_wafer("HBM", "C", 1): "not_performed",
        core_wafer("SENSOR", "B", 2): "unknown",
    }
    output_cases = {}
    affected = defaultdict(list)
    for component, events in by_component.items():
        meta = events[0].object_payload["component"]
        output_cases[component] = {
            "state": meta["dt_output_case"],
            "expected_resolution": (
                "resolved_indirectly" if meta["dt_output_case"] == "recoverable_indirect"
                else "candidate" if meta["dt_output_case"] == "contradiction_candidate"
                else "unresolvable" if meta["dt_output_case"] in
                     {"unresolvable", "unknown"}
                else meta["dt_output_case"]),
        }
        if is_designed_cause(meta):
            affected[meta["final_chip_id"]].append({
                "component_id": component, "layer": meta["bond_layer"],
                "core_type": meta["core_type"], "core_branch": meta["core_branch"],
                "core_wafer": events[0].subject_keys["wafer"]})
    return {
        "namespace": "SYN-CX-*", "source": SOURCE,
        "populations": {"defect": sorted(DEFECT_CHIPS),
                        "reference": sorted(REFERENCE_CHIPS)},
        "chips": {chip: {"layers": layers_for_chip(i), **aggregation_unit(chip),
                         "population": "defect" if chip in DEFECT_CHIPS else "reference"}
                  for i, chip in enumerate(FINAL_CHIPS)},
        "resolution_states": sorted({a.object_payload["component"]["state"]
                                      for a in transfers}),
        "absence_cases": cases,
        "dt_output_cases": output_cases,
        "wafer_to_final_chips": {
            wafer: [chip for chip in FINAL_CHIPS if final_wafer(chip) == wafer]
            for wafer in BASE_WAFERS},
        "experiment_unit_to_final_chip": {
            json.dumps(["bonding_experiment_unit", final_wafer(chip), bonding_leg(chip)],
                       separators=(",", ":")): chip for chip in FINAL_CHIPS},
        "ui_presets": UI_PRESETS,
        "expected_root_causes": [{
            "cause_id": "HBM_B_REWORK_RECIPE_AND_METROLOGY_EXCURSION_VIA_DT_REGROUP",
            "process_evidence": {"steps": ["REWORK_CLEAN", "BOND_PREP"],
                                 "recipe_excursions": {
                                     step: {
                                         "defect": process_recipe("HBM", "B", step),
                                         "reference": process_recipe("HBM", "A", step)}
                                     for step in sorted(VOID_CORRELATED_RECIPE_STEPS)}},
            "transfer_evidence": {"operation": "regroup", "minimum_dt_hops": 2,
                                  "bond_layers_by_chip": {
                                      chip: [row["layer"] for row in rows]
                                      for chip, rows in sorted(affected.items())}},
            "affected": dict(sorted(affected.items())),
            "clean_contrast": {
                "chips": sorted(REFERENCE_CHIPS),
                "exact_combination_present": False,
                "confounder": "branch B exists on non-HBM Core; HBM/B recipe plus measured outputs is the combination"},
            "confidence": "designed_high",
            "missing_fields_reducing_uncertainty": [
                "DT output lot/slot for missing_record cases",
                "direct spatial-to-process projection for marked cells"],
        }],
        "component_count": len(by_component),
        "multi_dt_components": sum(len(events) >= 3 for events in by_component.values()),
        "heterogeneous_dt_slots": sum(len(types) > 1 for types in dt_types.values()),
        "core_process": {
            "step_prefixes": ["PHOTO", "ETCH", "CMP", "CLN"],
            "minimum_steps": min(len(COMMON_PREFIX + BRANCH_MIDDLE[branch] +
                                     COMMON_SUFFIX) for branch in BRANCHES),
            "recipe_excursions": sorted(VOID_CORRELATED_RECIPE_STEPS),
            "payload_fields": ["step", "recipe"],
        },
        "measurement": {
            "metrics": [spec["metric"] for spec in MEASUREMENT_SPECS],
            "recorded": sum(a.object_payload["state"] == "recorded"
                            for a in measurements),
            "state_counts": {
                state: sum(a.object_payload["state"] == state for a in measurements)
                for state in ("recorded", "missing", "not_performed", "unknown")},
            "state_cases": {
                f"{core_wafer(core_type, branch, index)}:{metric}": state
                for (core_type, branch, index, metric), state in
                sorted(MEASUREMENT_STATE_CASES.items())},
            "excursion_population": "HBM/B",
            "answer_tags_persisted": False,
        },
        "spatial": spatial_answer_key(),
    }


def validate(atoms):
    key = answer_key(atoms)
    by_component = defaultdict(list)
    for atom in atoms:
        if atom.predicate == "transferred":
            by_component[atom.object_payload["component"]["component_id"]].append(atom)
    for component, events in by_component.items():
        events.sort(key=lambda a: a.object_payload["sequence"])
        assert [a.object_payload["sequence"] for a in events] == list(range(len(events))), component
        for left, right in zip(events, events[1:]):
            assert left.object_payload["to"] == right.object_payload["from"], component
    assert key["heterogeneous_dt_slots"] > 0
    assert key["multi_dt_components"] > 0
    assert set(key["resolution_states"]) == {
        "resolved", "candidate", "contested", "unresolvable"}
    measurements = [atom for atom in atoms if atom.predicate == "measured"]
    assert len(measurements) == len(CORE_TYPES) * len(BRANCHES) * 3 * \
           len(MEASUREMENT_SPECS)
    for atom in measurements:
        payload = atom.object_payload
        if payload["state"] == "recorded":
            assert isinstance(payload["value"], (int, float))
            assert payload["run_uid"]
        else:
            assert "value" not in payload and "run_uid" not in payload
    return key


def screen(atoms):
    from ledger import gate

    groups = defaultdict(list)
    for atom in atoms:
        groups[atom.molecule_ref].append(atom)
    accepted = []
    for molecule, members in groups.items():
        with gate.building_molecule(SOURCE):
            kept, _ = gate.screen_molecule(
                SOURCE, members, DERIVATIONS, SUBJECT_TYPES, molecule_ref=molecule)
        accepted.extend(kept)
    return accepted, len(groups)


def _write_spatial_rows():
    """Write SYN spatial source rows through the generic priority-preserving funnel."""
    from database.database import SessionLocal
    from database import crud, schemas, models

    models.init_dynamic_models(crud.TABLE_CONFIG)
    db = SessionLocal()
    report = {}
    try:
        for table, rows in spatial_source_rows().items():
            changed = 0
            dropped = {}
            for start in range(0, len(rows), 1000):
                chunk = rows[start:start + 1000]
                existing_keys = set()
                if table == "inspection_run":
                    model = models.DYNAMIC_TABLES[table]
                    keys = [row["run_uid"] for row in chunk]
                    existing_keys = {
                        row.business_key_val
                        for row in db.query(model).filter(
                            model.business_key_val.in_(keys)).all()}
                items = []
                for row in chunk:
                    updates = dict(row)
                    business_key = None
                    if table == "inspection_run":
                        business_key = updates["run_uid"]
                        # This fixture owns immutable SYN-only run keys. PostgreSQL turns
                        # the offset string into timestamptz, while generic CRUD compares
                        # the next source string against a datetime and would emit a fake
                        # EDIT. An existing key is therefore already this fixture's claim;
                        # fixture-definition changes require the namespace rollback.
                        if business_key in existing_keys:
                            continue
                    items.append(schemas.GeneralUpdateItem(
                        business_key_val=business_key, updates=updates,
                        source_name=MAP_SOURCE_NAME, updated_by=MAP_UPDATED_BY))
                if not items:
                    continue
                batch = schemas.GeneralUpdateBatch(updates=items)
                _results, cells, _logs, _deleted = crud.apply_batch_updates(
                    db, table, batch, drop_report=dropped)
                changed += len(cells or ())
                db.commit()
            if dropped.get("dropped_cells"):
                raise RuntimeError(
                    f"{table}: {dropped['dropped_cells']} undeclared spatial cells dropped: "
                    f"{sorted((dropped.get('by_column') or {}).keys())}")
            report[table] = {"rows_attempted": len(rows), "cells_changed": changed}
    finally:
        db.close()
    return report


def apply(atoms):
    from database.database import engine
    from ledger.store import LedgerStore

    accepted, molecules = screen(atoms)
    store = LedgerStore(engine, who=SOURCE)
    store.ensure_schema()
    ledger_result = store.write_batch(
        SOURCE, TRANSLATOR, accepted,
        cursor_value={"fixture": "complete", "namespace": "SYN-CX-*"},
        molecules=molecules, refused=0, incomplete=0, reasons={})
    return {"ledger": ledger_result, "spatial": _write_spatial_rows()}


def rollback():
    """Remove only this fixture's atoms/cursor. Intended for a disposable dev DB."""
    from database.database import engine
    from sqlalchemy import text

    with engine.begin() as connection:
        database = connection.execute(text("SELECT current_database()")).scalar()
        if database not in {"assy_manager", "assy_qa"}:
            raise SystemExit(f"REFUSED rollback on database {database!r}")
        deleted = connection.execute(text(
            "DELETE FROM ledger_events WHERE source_who = :source "
            "AND source_translator_ver LIKE :translator"),
            {"source": SOURCE, "translator": TRANSLATOR + "%"}).rowcount
        connection.execute(text(
            "DELETE FROM ledger_translator_cursor WHERE source = :source"),
            {"source": SOURCE})
        spatial_deleted = {}
        statements = {
            "void_obs": "DELETE FROM void_obs WHERE base_wafer_id LIKE 'SYN-CX-BW-%'",
            "inspection_run": (
                "DELETE FROM inspection_run WHERE base_wafer_id LIKE 'SYN-CX-BW-%'"),
            "bonding_log": "DELETE FROM bonding_log WHERE bond_lot LIKE 'SYN-CX-BOND-%'",
            "bonding_map": "DELETE FROM bonding_map WHERE base LIKE 'SYN-CX-BW-%'",
            "dt_map": (
                "DELETE FROM dt_map WHERE dt_lot IN ('SYN-CX-DT-01','SYN-CX-DT-02') "
                "AND dt_slot IN ('01','02') AND dt_job LIKE 'SYN-CX-SPATIAL-%'"),
            "core_wafer_map": (
                "DELETE FROM core_wafer_map WHERE core_lot IN "
                "('SYN-CX-LOGIC-MRG','SYN-CX-HBM-MRG') AND core_slot IN ('11','22')"),
            "valid_die_ref": "DELETE FROM valid_die_ref WHERE product = :product",
            "wafer_map_metadata": (
                "DELETE FROM wafer_map_metadata WHERE map_id LIKE 'SYN-CX-%' "
                "AND target_table IN "
                "('bonding_log','bonding_map','dt_map','core_wafer_map','valid_die_ref')"),
        }
        params = {"d": final_wafer(UI_PRESETS["hero_defect"]),
                  "r": final_wafer(UI_PRESETS["hero_reference"]),
                  "product": MAP_PRODUCT}
        for table, statement in statements.items():
            spatial_deleted[table] = connection.execute(text(statement), params).rowcount
        # Generic writes preserve every source layer. Remove only this fixture's layer
        # records after its SYN rows are gone; no other updated_by is touched.
        connection.execute(text("DELETE FROM cell_sources WHERE updated_by = :updated_by"),
                           {"updated_by": MAP_UPDATED_BY})
    return {"deleted_atoms": deleted, "deleted_spatial_rows": spatial_deleted,
            "source": SOURCE}


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--rollback", action="store_true")
    parser.add_argument("--answer-key", action="store_true")
    args = parser.parse_args()
    if args.rollback:
        print(json.dumps(rollback(), ensure_ascii=False, indent=2))
        return
    atoms = build_atoms()
    key = validate(atoms)
    if args.answer_key:
        shown = {"atoms": len(atoms), **key}
    else:
        shown = {
            "atoms": len(atoms), "molecules": len({a.molecule_ref for a in atoms}),
            "chips": len(key["chips"]), "components": key["component_count"],
            "multi_dt_components": key["multi_dt_components"],
            "heterogeneous_dt_slots": key["heterogeneous_dt_slots"],
            "resolution_states": key["resolution_states"],
            "dt_output_case_states": sorted({row["state"]
                                             for row in key["dt_output_cases"].values()}),
            "root_cause_affected_chips": sorted(
                key["expected_root_causes"][0]["affected"]),
            "measurement": {
                "metrics": key["measurement"]["metrics"],
                "state_counts": key["measurement"]["state_counts"]},
            "spatial": {"axes": key["spatial"]["axes"],
                        "counts": key["spatial"]["counts"]},
            "ui_presets": key["ui_presets"],
        }
    print(json.dumps(shown, ensure_ascii=False, indent=2))
    if args.apply:
        print(json.dumps(apply(atoms), ensure_ascii=False, indent=2, default=str))
    else:
        print("DRY RUN: pass --apply to append the SYN-CX-* fixture")


if __name__ == "__main__":
    main()
