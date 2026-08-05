"""Seed a valid-die reference floor into ``valid_die_ref`` (plus its metadata row).

Why this exists
---------------
Map Editor 2's alignment view scores eight candidate frames against a **common
floor**: the die set several defect sources get laid onto. Without a floor that
resolves, ``/api/maps/alignment/view`` answers ``not_scorable`` for every unit and
the screen cannot demonstrate what it was built for.

A floor needs BOTH halves and neither alone is a floor:

* cells in ``valid_die_ref`` under a ``(product, type)`` key, and
* a ``wafer_map_metadata`` row with ``target_table='valid_die_ref'`` carrying the
  grid and the physical wafer spec.

What makes this floor usable
----------------------------
* **The key splits.** ``valid_die_ref.map_key_columns`` is ``(product, type)``, so a
  single-token name can never be a floor key: ``map_overlay.map_key_parts`` would bind
  the whole string to ``product`` and find nothing under ``type``.
* **The footprint is asymmetric on purpose.** A circular die field is invariant under
  all eight frames, so it discriminates nothing and the honest answer is an eight-way
  tie (MAP_ALIGNMENT_SPEC section 1). This floor takes a flat off the bottom and drops
  the upper-left quadrant, and ``verify_discrimination`` below REFUSES to write if any
  of the seven non-identity frames maps the footprint back onto itself. The check is
  run against the same integer shift window the scorer uses, because a shape the
  scorer can slide back onto itself is not discriminating in the place that matters.
* **It carries values.** ``map_overlay.resolve_binding`` derives ``val`` for this table,
  which is what makes the route answer ``reference.kind: "values"`` rather than
  ``occupancy``. Interior dies and the edge ring are distinguished, and the ring
  inherits the footprint's asymmetry.
* **Its geometry matches a real source unit.** The grid and the phys signature are
  copied from the maps this floor has to be compared against;
  ``map_overlay.make_frame_transform`` refuses outright when the grid dims differ, so
  matching is forced rather than convenient.

Safety
------
Additive only. No DDL, no DROP, no DELETE, no row is ever removed: rows already
stored under this key that fall outside the footprint are REPORTED, never purged
(``replace_map`` would delete them, so this script does not use it). Writes go
through ``crud.apply_batch_updates`` with ``source_name='custom_script'``, which is the
lowest rank in the layering order, so an operator edit made later always wins.

Idempotent: every row is addressed by its composite business key, so a second run
changes nothing and says so.

Usage
-----
    python server/scripts/seed_valid_die_ref_floor.py             # dry run, default
    python server/scripts/seed_valid_die_ref_floor.py --apply     # write
    python server/scripts/seed_valid_die_ref_floor.py --show      # print the footprint
"""

import argparse
import json
import math
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


# ---------------------------------------------------------------------------
# The floor declaration. One place, no values derived twice.
# ---------------------------------------------------------------------------
# The grid and phys signature below are the ones the DT tape maps of the matched
# unit declare in `wafer_map_metadata`. Copy them, never guess them: a floor whose
# spec differs cannot be compared to the maps at all.
PRODUCT = "PRD-A"
TYPE = "DT13"
MAP_ID = "%s_%s" % (PRODUCT, TYPE)
TARGET_TABLE = "valid_die_ref"
META_TABLE = "wafer_map_metadata"

GRID_COLS = 13
GRID_ROWS = 13
GRID_META = {
    "grid_cols": GRID_COLS,
    "grid_rows": GRID_ROWS,
    "grid_start_x": 0,
    "grid_start_y": 0,
    "grid_y_invert": False,
    "rotation": 0,
    "side": "front",
    "phys_wafer_dia": 300.0,
    "phys_chip_x": 7.0,
    "phys_chip_y": 7.0,
    "phys_offset_x": 0.0,
    "phys_offset_y": 0.0,
    "phys_edge_margin": 3.0,
}

# The die field before anything is taken out of it: the circular printable area of
# this wafer spec, in cell units, centred on the odd grid's middle cell.
FIELD_RADIUS = 6.3
FIELD_CENTRE = ((GRID_COLS - 1) / 2.0, (GRID_ROWS - 1) / 2.0)

# The two deliberate asymmetries. Named, so the reason they exist survives the shape.
FLAT_ROWS = 2          # wafer flat: whole rows removed off the bottom edge
QUADRANT_MAX_X = 4     # scrapped upper-left quadrant: x <= this ...
QUADRANT_MAX_Y = 6     # ... and y <= this

# Value vocabulary. `1` is the good-die token this deployment already uses
# (dt_log.c_bn, core_wafer_map.c_bn, the four floors that already resolve); `E1` is
# the edge token declared in map_overlay_config's legend guidance. Two values, so the
# value channel carries something, and the ring is asymmetric because the field is.
VAL_INTERIOR = "1"
VAL_EDGE = "E1"

# The scorer solves an integer shift per candidate inside this window
# (`map_alignment.SHIFT_WINDOW`). The asymmetry check has to allow the same slack or
# it certifies a shape the scorer can slide back onto itself.
SHIFT_WINDOW = 3

SOURCE_NAME = "custom_script"
UPDATED_BY = "seed_valid_die_ref_floor"


# ---------------------------------------------------------------------------
# Geometry. Pure: no DB, no module state, arguments in and values out.
# ---------------------------------------------------------------------------

def field_dies():
    """The floor's die set, as sorted ``(x, y)`` pairs in the grid's own frame."""
    cx, cy = FIELD_CENTRE
    out = []
    for y in range(GRID_ROWS):
        for x in range(GRID_COLS):
            if math.hypot(x - cx, y - cy) > FIELD_RADIUS:
                continue
            if y >= GRID_ROWS - FLAT_ROWS:
                continue
            if x <= QUADRANT_MAX_X and y <= QUADRANT_MAX_Y:
                continue
            out.append((x, y))
    return sorted(out)


def die_value(cell, dies):
    """Edge dies are the ones missing an orthogonal neighbour inside the field."""
    present = dies if isinstance(dies, set) else set(dies)
    x, y = cell
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if (x + dx, y + dy) not in present:
            return VAL_EDGE
    return VAL_INTERIOR


def frame_image(cells, rotation, side):
    """``cells`` seen through one candidate frame, in this floor's own coordinates.

    Goes through the SAME transform the scorer uses
    (``map_alignment.score_candidates`` -> ``map_overlay.make_frame_transform``), fed the
    same way: a whole meta per candidate, never one box with eight rotations laid on it
    (MAP_ALIGNMENT_SPEC section 2). Rewriting the round trip by hand here was tried and
    it silently reversed the 90/270 direction, which would have mislabelled two of the
    seven refusal scores while leaving their worst case unchanged: exactly the kind of
    wrong that looks right.

    Needs no database session; both modules are import-clean.
    """
    import map_overlay
    from dt_map_derivation import source_meta_for_frame

    source_meta = source_meta_for_frame(GRID_META, "rot%d_%s" % (rotation, side))
    if source_meta is None:
        raise SystemExit("REFUSED: 'rot%d_%s' is not a candidate frame." % (rotation, side))
    transform = map_overlay.make_frame_transform(source_meta, GRID_META)
    return {transform(x, y) for (x, y) in cells}


def discrimination(cells, shift_window=SHIFT_WINDOW):
    """Per non-identity frame: how many dies it CANNOT put back on the floor.

    Zero for any frame means that frame is indistinguishable from doing nothing, and a
    floor with a zero here sends six of eight candidates blind.
    """
    field = set(cells)
    out = {}
    for side in ("front", "back"):
        for rotation in (0, 90, 180, 270):
            if rotation == 0 and side == "front":
                continue
            image = frame_image(field, rotation, side)
            best = 0
            for dx in range(-shift_window, shift_window + 1):
                for dy in range(-shift_window, shift_window + 1):
                    shifted = {(x + dx, y + dy) for (x, y) in image}
                    best = max(best, len(shifted & field))
            out["rot%d_%s" % (rotation, side)] = len(field) - best
    return out


def verify_discrimination(cells):
    """Refuse to seed a floor that answers the same for two different frames."""
    scores = discrimination(cells)
    blind = sorted(f for f, n in scores.items() if n <= 0)
    if blind:
        raise SystemExit(
            "REFUSED: the footprint is invariant under %s, so those candidates cannot "
            "be told apart from doing nothing. Change the shape, not this check."
            % ", ".join(blind))
    return scores


def render(cells):
    field = set(cells)
    return "\n".join("".join("#" if (x, y) in field else "."
                             for x in range(GRID_COLS)) for y in range(GRID_ROWS))


# ---------------------------------------------------------------------------
# Write. One transaction per table, both through the layering-aware upsert.
# ---------------------------------------------------------------------------

def _batch(items):
    from database import schemas
    return schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(updates=u, source_name=SOURCE_NAME,
                                           updated_by=UPDATED_BY) for u in items])


def seed(db, dies, apply_changes):
    """Returns a report dict. Writes only when ``apply_changes`` is true."""
    from database import crud, models

    cell_model = models.DYNAMIC_TABLES.get(TARGET_TABLE)
    meta_model = models.DYNAMIC_TABLES.get(META_TABLE)
    if cell_model is None or meta_model is None:
        raise SystemExit("REFUSED: '%s' or '%s' is not a declared table on this box."
                         % (TARGET_TABLE, META_TABLE))

    existing = {(int(float(r[0])), int(float(r[1])))
                for r in db.query(cell_model.x, cell_model.y)
                .filter(cell_model.product == PRODUCT, cell_model.type == TYPE).all()
                if r[0] is not None and r[1] is not None}
    wanted = set(dies)
    report = {
        "rows_before": len(existing),
        "to_add": len(wanted - existing),
        "already_present": len(wanted & existing),
        # Never purged. A stale die is reported so a human decides, because deleting
        # rows nobody asked to delete is how a seed script becomes a data incident.
        "outside_footprint_left_alone": sorted(existing - wanted),
        "meta_before": db.query(meta_model.map_id).filter(
            meta_model.target_table == TARGET_TABLE,
            meta_model.map_id == MAP_ID).count(),
        "cells_changed": 0,
        "meta_changed": 0,
    }
    if not apply_changes:
        return report

    items = [{"product": PRODUCT, "type": TYPE, "x": x, "y": y,
              "val": die_value((x, y), wanted)} for (x, y) in dies]
    # Chunked, because this is the shape every write path in this codebase takes and a
    # seed that only works at fixture scale is a seed nobody can reuse.
    for start in range(0, len(items), 1000):
        # `apply_batch_updates` returns (results, changed_cells, logs, deleted_row_ids);
        # `changed_cells` is a list of (row_id, column) pairs, not a count.
        _, changed_cells, _, _ = crud.apply_batch_updates(
            db, TARGET_TABLE, _batch(items[start:start + 1000]))
        report["cells_changed"] += len(changed_cells or ())

    _, meta_changed, _, _ = crud.apply_batch_updates(db, META_TABLE, _batch([{
        "target_table": TARGET_TABLE, "map_id": MAP_ID,
        "grid_metadata": json.dumps(GRID_META, ensure_ascii=False)}]))
    report["meta_changed"] = len(meta_changed or ())

    report["rows_after"] = (db.query(cell_model.row_id)
                            .filter(cell_model.product == PRODUCT,
                                    cell_model.type == TYPE).count())
    return report


def main():
    ap = argparse.ArgumentParser(
        description="Seed the valid-die reference floor and its wafer_map_metadata row. "
                    "Additive only: no table is altered and no row is ever deleted.")
    ap.add_argument("--apply", action="store_true",
                    help="write; without it the script only reports what it would do")
    ap.add_argument("--show", action="store_true", help="print the footprint")
    args = ap.parse_args()

    dies = field_dies()
    scores = verify_discrimination(dies)

    print("floor        : %s = %r, %s = %r  (map_id %r on %s)"
          % ("product", PRODUCT, "type", TYPE, MAP_ID, TARGET_TABLE))
    print("grid         : %dx%d start (%d,%d)  chip %sx%s  dia %s  margin %s"
          % (GRID_COLS, GRID_ROWS, GRID_META["grid_start_x"], GRID_META["grid_start_y"],
             GRID_META["phys_chip_x"], GRID_META["phys_chip_y"],
             GRID_META["phys_wafer_dia"], GRID_META["phys_edge_margin"]))
    print("dies         : %d  (edge %d, interior %d)"
          % (len(dies),
             sum(1 for c in dies if die_value(c, dies) == VAL_EDGE),
             sum(1 for c in dies if die_value(c, dies) == VAL_INTERIOR)))
    print("discriminates: worst %d dies, per frame %s"
          % (min(scores.values()), json.dumps(scores, sort_keys=True)))
    if args.show:
        print(render(dies))

    from database.database import SessionLocal
    from database import crud, models
    models.init_dynamic_models(crud.TABLE_CONFIG)
    db = SessionLocal()
    try:
        report = seed(db, dies, args.apply)
    finally:
        db.close()

    print("rows under key before : %d" % report["rows_before"])
    print("already present       : %d" % report["already_present"])
    print("would add / added     : %d" % report["to_add"])
    stale = report["outside_footprint_left_alone"]
    print("outside footprint     : %d (left alone, never deleted)%s"
          % (len(stale), (" " + str(stale[:10])) if stale else ""))
    print("metadata row before   : %d" % report["meta_before"])
    if args.apply:
        print("cells changed         : %d" % report["cells_changed"])
        print("metadata cells changed: %d" % report["meta_changed"])
        print("rows under key after  : %d" % report["rows_after"])
        print("WROTE %s and the %s row for target_table=%r map_id=%r"
              % (TARGET_TABLE, META_TABLE, TARGET_TABLE, MAP_ID))
    else:
        print("DRY RUN, nothing written. Re-run with --apply to write.")


if __name__ == "__main__":
    main()
