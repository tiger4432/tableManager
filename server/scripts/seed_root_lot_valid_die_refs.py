# -*- coding: utf-8 -*-
"""Seed one synthetic valid-die floor per current ``lot_event`` root lot.

This is deliberately a data setup script, not a production inference rule. ``lot_event``
contains lineage and wafer membership but no die geometry, so this script does not claim to
recover geometry from it. The owner requested five non-square, circular-wafer assumptions in
the 15..25-cell range, each with one bottom-centre notch cell removed.

Both required halves are written:

* cells in ``valid_die_ref`` under ``(product=root_lot, type='WF')``; and
* the matching ``wafer_map_metadata`` registration.

The script is additive and idempotent. Existing cells outside the requested footprint are
reported and left untouched. All writes use ``crud.apply_batch_updates`` with the lowest-rank
``custom_script`` source, so later operator edits keep priority.

Usage::

    python server/scripts/seed_root_lot_valid_die_refs.py --show
    python server/scripts/seed_root_lot_valid_die_refs.py \
        --apply --i-accept-writing-to-owner-database
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


TARGET_TABLE = "valid_die_ref"
META_TABLE = "wafer_map_metadata"
MAP_TYPE = "WF"
SOURCE_NAME = "custom_script"
UPDATED_BY = "seed_root_lot_valid_die_refs"

# Measured from the current owner DB's lot_event table on 2026-08-16. Every pair is
# deliberately non-square and every axis stays inside the owner's requested 15..25 range.
DIMENSIONS_BY_ROOT = {
    "NAB115": (15, 17),
    "NAB122": (19, 17),
    "NAB123": (19, 21),
    "NAB163": (23, 21),
    "NAB539": (23, 25),
}

PHYS_WAFER_DIA = 300.0
PHYS_EDGE_MARGIN = 3.0
VAL_INTERIOR = "1"
VAL_EDGE = "E1"
MAX_SOURCE_ROWS = 10_000
_WAFER_ROOT = re.compile(r"^(?P<root>.+)-W\d+$")


def grid_meta(cols: int, rows: int) -> dict:
    """A circular physical wafer whose unequal die pitches fill a non-square grid."""
    usable_diameter = PHYS_WAFER_DIA - (2.0 * PHYS_EDGE_MARGIN)
    return {
        "grid_cols": cols,
        "grid_rows": rows,
        "grid_start_x": 0,
        "grid_start_y": 0,
        "grid_y_invert": False,
        "rotation": 0,
        "side": "front",
        "phys_wafer_dia": PHYS_WAFER_DIA,
        "phys_chip_x": usable_diameter / cols,
        "phys_chip_y": usable_diameter / rows,
        "phys_offset_x": 0.0,
        "phys_offset_y": 0.0,
        "phys_edge_margin": PHYS_EDGE_MARGIN,
        "synthetic_assumption": "root_lot_non_square_circle_with_1cell_bottom_notch",
    }


def footprint(cols: int, rows: int):
    """Circular die field minus one bottom-centre cell, plus proof of the ㄷ boundary."""
    import map_overlay

    cells = set(map_overlay.circle_die_mask(grid_meta(cols, rows)) or ())
    if not cells:
        raise SystemExit(f"REFUSED: circle mask is empty for {cols}x{rows}.")

    centre_x = cols // 2
    centre_column = [y for x, y in cells if x == centre_x]
    if not centre_column:
        raise SystemExit(f"REFUSED: {cols}x{rows} circle has no centre column.")
    notch = (centre_x, max(centre_column))

    # The missing cell must be open to the exterior below, while valid cells on its left,
    # right, and across the row above make a one-cell-deep ㄷ-shaped boundary.
    x, y = notch
    boundary = {(x - 1, y), (x + 1, y),
                (x - 1, y - 1), (x, y - 1), (x + 1, y - 1)}
    if not boundary.issubset(cells) or (x, y + 1) in cells:
        raise SystemExit(
            f"REFUSED: {cols}x{rows} cannot form the requested one-cell bottom notch."
        )
    cells.remove(notch)
    return sorted(cells), notch


def die_value(cell, cells) -> str:
    """Mark the outer circle and the notch boundary as edge, everything else interior."""
    present = cells if isinstance(cells, set) else set(cells)
    x, y = cell
    if any((x + dx, y + dy) not in present
           for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
        return VAL_EDGE
    return VAL_INTERIOR


def map_id(root_lot: str) -> str:
    return f"{root_lot}_{MAP_TYPE}"


def render(cols: int, rows: int, cells, notch) -> str:
    present = set(cells)
    lines = []
    for y in range(rows):
        line = []
        for x in range(cols):
            if (x, y) == notch:
                line.append("N")
            elif (x, y) in present:
                line.append("#")
            else:
                line.append(".")
        lines.append("".join(line))
    return "\n".join(lines)


def roots_from_lot_event(db):
    """Read a bounded source slice and derive roots from persistent wafer identities."""
    from database import models

    model = models.DYNAMIC_TABLES.get("lot_event")
    if model is None:
        raise SystemExit("REFUSED: 'lot_event' is not declared on this box.")
    rows = (db.query(model.waferids)
            .order_by(model.updated_at, model.row_id)
            .limit(MAX_SOURCE_ROWS + 1).all())
    if len(rows) > MAX_SOURCE_ROWS:
        raise SystemExit(
            f"REFUSED: lot_event exceeds the bounded {MAX_SOURCE_ROWS}-row setup scope."
        )

    roots = set()
    bad = []
    for (raw,) in rows:
        row_roots = set()
        for wafer_id in str(raw or "").split(":"):
            wafer_id = wafer_id.strip()
            if not wafer_id:
                continue
            match = _WAFER_ROOT.match(wafer_id)
            if not match:
                bad.append(wafer_id)
                continue
            row_roots.add(match.group("root"))
        if len(row_roots) > 1:
            raise SystemExit(
                "REFUSED: one lot_event row mixes wafer roots: " + ", ".join(sorted(row_roots))
            )
        roots.update(row_roots)
    if bad:
        raise SystemExit("REFUSED: unreadable wafer ids: " + ", ".join(sorted(set(bad))[:10]))

    measured = set(roots)
    declared = set(DIMENSIONS_BY_ROOT)
    if measured != declared:
        raise SystemExit(
            "REFUSED: current roots differ from the reviewed setup; measured=%s declared=%s"
            % (sorted(measured), sorted(declared))
        )
    return sorted(measured), len(rows)


def _batch(items):
    from database import schemas

    return schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(
            updates=item, source_name=SOURCE_NAME, updated_by=UPDATED_BY
        )
        for item in items
    ])


def _write(db, table: str, items, chunk: int = 1000) -> int:
    from database import crud

    changed = 0
    for start in range(0, len(items), chunk):
        _, changed_cells, _, _ = crud.apply_batch_updates(
            db, table, _batch(items[start:start + chunk])
        )
        changed += len(changed_cells or ())
    return changed


def seed(db, apply_changes: bool):
    from database import models

    roots, source_rows = roots_from_lot_event(db)
    cell_model = models.DYNAMIC_TABLES.get(TARGET_TABLE)
    meta_model = models.DYNAMIC_TABLES.get(META_TABLE)
    if cell_model is None or meta_model is None:
        raise SystemExit(
            f"REFUSED: {TARGET_TABLE!r} or {META_TABLE!r} is not declared on this box."
        )

    report = {"source_rows": source_rows, "roots": [], "cells_changed": 0,
              "metadata_changed": 0}
    for root in roots:
        cols, rows = DIMENSIONS_BY_ROOT[root]
        cells, notch = footprint(cols, rows)
        present = set(cells)
        existing = {
            (int(float(x)), int(float(y)))
            for x, y in (db.query(cell_model.x, cell_model.y)
                         .filter(cell_model.product == root,
                                 cell_model.type == MAP_TYPE).all())
            if x is not None and y is not None
        }
        meta_before = (db.query(meta_model.row_id)
                       .filter(meta_model.target_table == TARGET_TABLE,
                               meta_model.map_id == map_id(root)).count())
        entry = {
            "root_lot": root,
            "map_id": map_id(root),
            "grid": f"{cols}x{rows}",
            "cells": len(cells),
            "notch": notch,
            "already_present": len(existing & present),
            "outside_footprint_left_alone": len(existing - present),
            "metadata_before": meta_before,
        }
        report["roots"].append(entry)
        if not apply_changes:
            continue

        items = [
            {"product": root, "type": MAP_TYPE, "x": x, "y": y,
             "val": die_value((x, y), present)}
            for x, y in cells
        ]
        report["cells_changed"] += _write(db, TARGET_TABLE, items)
        report["metadata_changed"] += _write(db, META_TABLE, [{
            "target_table": TARGET_TABLE,
            "map_id": map_id(root),
            "grid_metadata": json.dumps(grid_meta(cols, rows), ensure_ascii=False),
        }])
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Seed non-square circular valid-die maps for current lot_event roots."
    )
    parser.add_argument("--apply", action="store_true", help="write; default is dry run")
    parser.add_argument("--show", action="store_true", help="print every footprint")
    parser.add_argument(
        "--i-accept-writing-to-owner-database", action="store_true", dest="accepted",
        help="record that this run writes to the owner's working database",
    )
    args = parser.parse_args()
    if args.apply and not args.accepted:
        raise SystemExit(
            "REFUSED: --apply needs --i-accept-writing-to-owner-database."
        )

    from database.database import SessionLocal
    from database import crud, models

    models.init_dynamic_models(crud.TABLE_CONFIG)
    db = SessionLocal()
    try:
        report = seed(db, args.apply)
    finally:
        db.close()

    print("lot_event source rows : %d" % report["source_rows"])
    print("root_lot groups       : %d" % len(report["roots"]))
    for entry in report["roots"]:
        print("%-8s map=%-10s grid=%-5s cells=%-3d notch=%s existing=%d outside=%d meta=%d"
              % (entry["root_lot"], entry["map_id"], entry["grid"], entry["cells"],
                 entry["notch"], entry["already_present"],
                 entry["outside_footprint_left_alone"], entry["metadata_before"]))
        if args.show:
            cols, rows = DIMENSIONS_BY_ROOT[entry["root_lot"]]
            cells, notch = footprint(cols, rows)
            print(render(cols, rows, cells, notch))
    if args.apply:
        print("valid_die_ref cells changed : %d" % report["cells_changed"])
        print("metadata cells changed      : %d" % report["metadata_changed"])
        print("WROTE root-lot valid-die floors and their metadata registrations.")
    else:
        print("DRY RUN, nothing written.")


if __name__ == "__main__":
    main()
