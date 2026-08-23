# -*- coding: utf-8 -*-
"""Give every SYN frame a valid-die reference, so the map mask path can actually fire.

Why this exists
---------------
The three-axis map (`GET /api/ledger/lot_map`) draws defect chips on a REGISTERED frame and
is supposed to draw them on a REAL DIE FIELD under it. It never did: no frame in the SYN
world declared `grid_metadata.valid_die_ref`, so there was nothing for the reference to
resolve to and every panel took the 「유효 다이 마스크 미적용」 branch.

A reference needs THREE things and none of them alone is a reference:

  1. rows in the floor table (`map_overlay.VALID_DIE_TABLE`) under a `(product, type)` key —
     THE PRESENCE OF THE ROW IS THE MASK, there is no "is this die valid" column;
  2. a `wafer_map_metadata` row for the floor itself, so the floor is a registered map like
     any other and can be opened in the editor;
  3. `valid_die_ref` in the CONSUMING frame's own `grid_metadata`, which is the declared
     pointer (`product_tables.PRODUCT_TABLES['valid_die_ref']` says so in as many words).

This script writes all three, for the frames of the SYN world only.

🔴 THE FOOTPRINT IS THE FRAME'S OWN DECLARED DIE FIELD, NOT A SHAPE THIS FILE INVENTS.
It is `map_overlay.circle_die_mask(meta)` — the same primitive the overlay uses as the
circle basis, fed the frame's own registered physical spec (`phys_wafer_dia`,
`phys_chip_x/y`, `phys_edge_margin`, offsets). Two consequences, both deliberate:

  * It is the physically correct answer for that spec rather than a drawing. The owner's
    ban is on a SCREEN drawing a circle nobody registered; these are stored rows derived
    from the registration itself.
  * Its bounding box is IDENTICAL to the box the circle basis already yields, so
    `map_overlay.origin_box` returns the same box before and after this runs and no
    coordinate anywhere moves. A hand-drawn footprint with a wafer flat would have cut the
    box in y and silently shifted `grid_start_y` for every consumer of these frames.

🔴 NOTHING IS TYPED HERE THAT A DECLARATION ALREADY OWNS.
The consuming relation comes from `siblings_axes.json` (the attribution source this console
reads), the floor table from `map_overlay.VALID_DIE_TABLE`, the metadata table from
`map_overlay.META_TABLE`, the declaration key from `map_overlay.VALID_DIE_REF_KEY`, and the
floor's key columns from that table's own `map_key_columns`. A deployment that spells any of
them differently swaps declarations and this script follows.

Safety
------
* ADDITIVE. No DDL, no DROP, no DELETE. Rows already under a floor key that fall outside the
  footprint are REPORTED and left alone.
* SYN ONLY, and the marker is checked rather than assumed: a frame is touched only if its
  `map_id` starts with `SYN-`. The five real `BS-2601-*` lots and every other real frame are
  skipped by that test, and the count of skipped frames is printed so the skip is visible.
* New floor rows carry the `SYN-` marker in their own key (`SYN-VD_...`), so synthetic mask
  data can never be mistaken for a real product's valid-die map.
* Writes go through `crud.apply_batch_updates` with `source_name='custom_script'`, the LOWEST
  rank in the layering order, so any operator edit made later wins.
* Idempotent: every row is addressed by its composite business key.

Usage
-----
    python server/scripts/seed_syn_valid_die_floors.py
    python server/scripts/seed_syn_valid_die_floors.py --apply --i-accept-writing-to-owner-database
"""

import argparse
import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

#: The separation marker. Frames without it are REAL and are not touched; floors created
#: here carry it in their own product key.
SYN_MARKER = "SYN-"
#: The product half of every floor key this script creates. The type half is derived from the
#: geometry it masks, so two frames with different grids never share one floor.
FLOOR_PRODUCT = "SYN-VD"

VAL_INTERIOR = "1"
VAL_EDGE = "E1"

SOURCE_NAME = "custom_script"
UPDATED_BY = "seed_syn_valid_die_floors"


def consuming_relation():
    """Which relation's frames the console draws — READ FROM THE CONSOLE'S OWN DECLARATION.

    `siblings_axes.json` names the attribution source whose rows carry the map coordinates;
    `ledger_lots._frame` looks its frames up under exactly that name. Taking it from there
    means a deployment that attributes to another relation gets its frames stamped with no
    edit here.
    """
    from ledger_api import ledger_siblings
    from ledger_api import finding_kinds
    config = ledger_siblings.load_axes_config()
    geometry, attribution = config.for_kind(finding_kinds.DEFAULT_KIND)
    for source in attribution:
        if getattr(source, "about", None) == "process":
            return source.relation
    return attribution[0].relation


def floor_key(cols, rows):
    """`(product, type)` for the floor that masks a `cols x rows` frame.

    One floor per GEOMETRY, because a valid-die map is a property of the die field and
    `map_overlay.make_frame_transform` refuses outright when grid dimensions differ.
    """
    return FLOOR_PRODUCT, "G%dX%d" % (cols, rows)


def die_value(cell, dies):
    """Edge dies are the ones missing an orthogonal neighbour inside the field."""
    x, y = cell
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if (x + dx, y + dy) not in dies:
            return VAL_EDGE
    return VAL_INTERIOR


def completed_meta(meta):
    """The frame's declaration with a MISSING wafer diameter completed, mask-neutrally.

    🔴 MEASURED, AND IT IS WHY THE DT AXIS COULD NOT GET A FLOOR: the 600 `SYN-DT-*` frames
    declare `phys_chip_x/y`, offsets and an edge margin but NO `phys_wafer_dia`, so
    `map_overlay._phys_signature` is None and `circle_die_mask` correctly refuses to
    reproduce a die field it was never given the diameter of.

    The completion is not a guess: it is the rule `map_meta_registrar.synthesize_grid_meta`
    already applies when it auto-registers a frame — a diameter whose effective radius
    CIRCUMSCRIBES the grid's half-diagonal, so the mask is neutral (every cell valid) rather
    than a shape this file drew. Written in the frame's own millimetre units because this
    frame declares a real chip pitch, unlike the auto-registered 1x1 case.

    The caller ASSERTS neutrality afterwards by counting the resulting mask, so a diameter
    that failed to circumscribe would be caught rather than shipped.
    """
    import math
    if not isinstance(meta, dict) or meta.get("phys_wafer_dia"):
        return meta, False
    try:
        cols = int(meta.get("grid_cols") or 0)
        rows = int(meta.get("grid_rows") or 0)
        chip_x = float(meta.get("phys_chip_x") or 0)
        chip_y = float(meta.get("phys_chip_y") or 0)
        margin = float(meta.get("phys_edge_margin") or 0)
    except (TypeError, ValueError):
        return meta, False
    if cols <= 0 or rows <= 0 or chip_x <= 0 or chip_y <= 0:
        return meta, False
    half_diag = math.hypot(cols * chip_x, rows * chip_y) / 2.0
    out = dict(meta)
    out["phys_wafer_dia"] = math.ceil(2 * (half_diag + margin + chip_x + chip_y))
    return out, True


def footprint(meta):
    """The frame's declared die field, or None when the spec cannot reproduce one."""
    import map_overlay
    mask = map_overlay.circle_die_mask(meta)
    return None if mask is None else sorted(mask)


def floor_meta(meta, cols, rows):
    """The floor's OWN registration — the consuming frame's geometry with the orientation
    neutralised.

    The floor is the die field itself, so it is stored in the unrotated front-side frame and
    every consumer projects into its own orientation. Carrying the consumer's rotation here
    would make one floor per orientation of the same physical wafer.
    """
    out = dict(meta)
    out["grid_cols"] = cols
    out["grid_rows"] = rows
    out["rotation"] = 0
    out["side"] = "front"
    out["grid_start_x"] = 0
    out["grid_start_y"] = 0
    out["grid_y_invert"] = False
    # A floor that declared its own reference would be a two-hop chain, which
    # `map_overlay.valid_die_chain_error` refuses — and rightly, it resolves to a set nobody
    # declared. Strip it rather than let one be inherited by copying.
    out.pop("valid_die_ref", None)
    return out


def _batch(items):
    from database import schemas
    return schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(updates=u, source_name=SOURCE_NAME,
                                           updated_by=UPDATED_BY) for u in items])


def _write(db, table, items, chunk=1000):
    from database import crud
    changed = 0
    for start in range(0, len(items), chunk):
        _, cells, _, _ = crud.apply_batch_updates(db, table, _batch(items[start:start + chunk]))
        changed += len(cells or ())
    return changed


def plan(db, relation):
    """Every SYN frame of `relation`, grouped by the geometry its floor must match."""
    import map_overlay
    from database import models
    meta_model = models.DYNAMIC_TABLES.get(map_overlay.META_TABLE)
    if meta_model is None:
        raise SystemExit("REFUSED: %r is not a declared table on this box."
                         % map_overlay.META_TABLE)
    rows = (db.query(meta_model.map_id, meta_model.grid_metadata)
            .filter(meta_model.target_table == relation).all())
    frames, skipped_real, unreadable, already = [], 0, 0, 0
    geometries = {}
    for map_id, raw in rows:
        if not map_id or not str(map_id).startswith(SYN_MARKER):
            skipped_real += 1
            continue
        try:
            meta = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:                                    # noqa: BLE001 - text is data
            meta = None
        if not isinstance(meta, dict):
            unreadable += 1
            continue
        cols = int(meta.get("grid_cols") or 0)
        grid_rows = int(meta.get("grid_rows") or 0)
        if cols <= 0 or grid_rows <= 0:
            unreadable += 1
            continue
        product, kind = floor_key(cols, grid_rows)
        meta, completed = completed_meta(meta)
        if geometries.get((product, kind)) is None:
            geometries[(product, kind)] = (meta, cols, grid_rows)
        ref, _err = map_overlay.parse_valid_die_ref(meta)
        if ref and ref.get("map_id") == "%s_%s" % (product, kind) and not completed:
            already += 1
            continue
        frames.append((str(map_id), meta, product, kind))
    return {"frames": frames, "geometries": geometries, "skipped_real": skipped_real,
            "unreadable": unreadable, "already_stamped": already,
            "frames_total": len(rows)}


def seed(db, relation, apply_changes):
    import map_overlay
    from database import models
    p = plan(db, relation)
    cell_model = models.DYNAMIC_TABLES.get(map_overlay.VALID_DIE_TABLE)
    if cell_model is None:
        raise SystemExit("REFUSED: %r is not a declared table on this box."
                         % map_overlay.VALID_DIE_TABLE)

    report = dict(p)
    report.pop("geometries")
    report["floors"] = []
    report["floor_cells_written"] = 0
    report["floor_meta_written"] = 0
    report["frames_stamped"] = 0

    #: 🔴 A FRAME IS STAMPED ONLY IF ITS FLOOR RESOLVED. Pointing a frame at a floor that
    #: cannot be built is WORSE than leaving it unstamped: the client refuses the whole panel
    #: with `origin_box_unknown` instead of drawing the registered grid and saying the mask
    #: is absent. An unreachable reference turns a partial answer into no answer.
    resolvable = set()
    for (product, kind), (meta, cols, rows) in sorted(p["geometries"].items()):
        dies = footprint(meta)
        if not dies:
            report["floors"].append({"key": "%s_%s" % (product, kind), "cells": 0,
                                     "refused": "물리 규격이 없어 다이 필드를 재현할 수 없다"})
            continue
        # The completion above claims to be MASK-NEUTRAL. Count it rather than believe it.
        if meta.get("phys_wafer_dia") and len(dies) < cols * rows:
            neutral = "partial(%d/%d)" % (len(dies), cols * rows)
        else:
            neutral = "full(%d)" % len(dies)
        resolvable.add((product, kind))
        die_set = set(dies)
        existing = {(int(float(r[0])), int(float(r[1])))
                    for r in db.query(cell_model.x, cell_model.y)
                    .filter(cell_model.product == product, cell_model.type == kind).all()
                    if r[0] is not None and r[1] is not None}
        entry = {"key": "%s_%s" % (product, kind), "grid": "%dx%d" % (cols, rows),
                 "cells": len(dies), "coverage": neutral,
                 "already_present": len(die_set & existing),
                 "outside_footprint_left_alone": len(existing - die_set)}
        report["floors"].append(entry)
        if not apply_changes:
            continue
        items = [{"product": product, "type": kind, "x": x, "y": y,
                  "val": die_value((x, y), die_set)} for (x, y) in dies]
        report["floor_cells_written"] += _write(db, map_overlay.VALID_DIE_TABLE, items)
        report["floor_meta_written"] += _write(db, map_overlay.META_TABLE, [{
            "target_table": map_overlay.VALID_DIE_TABLE,
            "map_id": "%s_%s" % (product, kind),
            "grid_metadata": json.dumps(floor_meta(meta, cols, rows), ensure_ascii=False)}])

    stampable = [f for f in p["frames"] if (f[2], f[3]) in resolvable]
    report["frames_unstampable"] = len(p["frames"]) - len(stampable)
    report["frames_to_stamp"] = len(stampable)
    if apply_changes and stampable:
        stamps = []
        for map_id, meta, product, kind in stampable:
            nxt = dict(meta)
            # Written through the declared KEY constant, and as the object form so the
            # pinned read table is spelled out rather than inherited by convention.
            nxt[map_overlay.VALID_DIE_REF_KEY] = {
                "table": map_overlay.VALID_DIE_TABLE,
                "map_id": "%s_%s" % (product, kind)}
            stamps.append({"target_table": relation, "map_id": map_id,
                           "grid_metadata": json.dumps(nxt, ensure_ascii=False)})
        report["frames_stamped"] = _write(db, map_overlay.META_TABLE, stamps)
    return report


def main():
    ap = argparse.ArgumentParser(
        description="Register a valid-die reference for every SYN frame. Additive only.")
    ap.add_argument("--apply", action="store_true", help="write; otherwise report only")
    ap.add_argument("--i-accept-writing-to-owner-database", action="store_true",
                    dest="accepted",
                    help="RECORD that this run writes to the owner's working database "
                         "(ruling R-2026-08-14-I: the flag exists so the write is legible "
                         "afterwards, not so anyone waits for permission)")
    args = ap.parse_args()
    if args.apply and not args.accepted:
        raise SystemExit("REFUSED: --apply needs --i-accept-writing-to-owner-database, "
                         "which is the RECORD that this write happened.")

    import map_overlay
    from database.database import SessionLocal
    from database import crud, models
    models.init_dynamic_models(crud.TABLE_CONFIG)
    relation = consuming_relation()
    print("consuming relation : %s   (declared by siblings_axes.json)" % relation)
    print("floor table        : %s   (map_overlay.VALID_DIE_TABLE)" % map_overlay.VALID_DIE_TABLE)
    print("declaration key    : grid_metadata.%s" % map_overlay.VALID_DIE_REF_KEY)

    db = SessionLocal()
    try:
        report = seed(db, relation, args.apply)
    finally:
        db.close()

    print("frames in relation   : %d" % report["frames_total"])
    print("real frames skipped  : %d (no %r marker — never touched)"
          % (report["skipped_real"], SYN_MARKER))
    print("unreadable metadata  : %d" % report["unreadable"])
    print("already stamped      : %d" % report["already_stamped"])
    print("to stamp             : %d" % report["frames_to_stamp"])
    print("cannot stamp (no floor): %d" % report["frames_unstampable"])
    for f in report["floors"]:
        print("floor %-18s %s" % (f["key"], json.dumps(f, ensure_ascii=False)))
    if args.apply:
        print("floor cells changed  : %d" % report["floor_cells_written"])
        print("floor meta changed   : %d" % report["floor_meta_written"])
        print("frames stamped       : %d" % report["frames_stamped"])
    else:
        print("DRY RUN, nothing written.")


if __name__ == "__main__":
    main()
