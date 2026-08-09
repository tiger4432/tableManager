"""Seed one clustered CORE_DT defect map and split it across synthetic DT jobs.

The core wafer is the shared object. Each DT job receives a disjoint slice of
that wafer and a PRD-A_DT13 destination walk. Core recording frames are an
independent hidden truth -- they are never derived from the DT rotation. This
deliberately leaves future core alignment to solve frame and offset from the
defect/bin fingerprint; no derived core map is written here.

Usage:
    python server/scripts/seed_syn_core_defect_jobs.py          # dry run
    python server/scripts/seed_syn_core_defect_jobs.py --apply  # additive upsert
    python server/scripts/seed_syn_core_defect_jobs.py --apply --core-lot SYN-CORE-CLUSTER-B --core-wafer SYN-CORE-WAFER-02
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import sys
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

CORE_REF = ("CORE", "DT")
DT_REF = ("PRD-A", "DT13")
CORE_LOT, CORE_SLOT, CORE_WAFER = "SYN-CORE-CLUSTER", "S01", "SYN-CORE-WAFER-01"
JOB_PREFIX = "SYN-CORE-CLUSTER-"
CORE_YIELD = 0.70
SOURCE_NAME, UPDATED_BY = "custom_script", "seed_syn_core_defect_jobs"
EVENT_TIME = "2026-08-09T00:00:00Z"
DT_LOG_COLUMNS = (
    "dt_job", "dt_eqp", "product", "dt_lot", "dt_slot",
    "dt_x", "dt_y", "dt_index",
    "core_lot", "core_slot", "core_wafer", "core_x", "core_y",
    "c_bn", "event_time",
)


def _map_id(product, type_name):
    return "%s_%s" % (product, type_name)


def _load_reference(db, product, type_name):
    from database import models

    valid = models.DYNAMIC_TABLES["valid_die_ref"]
    meta = models.DYNAMIC_TABLES["wafer_map_metadata"]
    cells = sorted({(int(x), int(y)) for x, y in db.query(valid.x, valid.y).filter(
        valid.product == product, valid.type == type_name).all()})
    row = db.query(meta.grid_metadata).filter(
        meta.target_table == "valid_die_ref", meta.map_id == _map_id(product, type_name)).one_or_none()
    if not cells or not row or not row[0]:
        raise SystemExit("REFUSED: valid_die_ref %s/%s or its metadata is missing." % (product, type_name))
    return cells, json.loads(row[0])


def _serpentine(cells, meta):
    rows = {}
    for x, y in cells:
        rows.setdefault(y, []).append(x)
    ordered = []
    y_order = sorted(rows, reverse=bool(meta.get("grid_y_invert")))
    for row_no, y in enumerate(y_order):
        xs = sorted(rows[y])
        ordered.extend((x, y) for x in (reversed(xs) if row_no % 2 else xs))
    return ordered


def core_column_start(cells, meta, starts_at_right=False):
    """Core's TL/TR anchor: top die in the outermost occupied column.

    This is intentionally not the grid's nominal corner: a round wafer often
    has no die at that coordinate. "Top" follows the map's y-invert setting.
    """
    outer_x = (max if starts_at_right else min)(x for x, _y in cells)
    ys = [y for x, y in cells if x == outer_x]
    return outer_x, (max(ys) if meta.get("grid_y_invert") else min(ys))


def core_column_walk(cells, meta, starts_at_right=False):
    """Column-first core order whose first die is ``core_column_start``."""
    by_x = {}
    for x, y in cells:
        by_x.setdefault(x, []).append(y)
    xs = sorted(by_x, reverse=starts_at_right)
    out = []
    for x in xs:
        out.extend((x, y) for y in sorted(by_x[x], reverse=bool(meta.get("grid_y_invert"))))
    return out


def clustered_bins(cells, seed=20260809):
    """Mostly-good map with several deterministic, spatially clustered defects."""
    rng = random.Random(seed)
    bins = {cell: "B0" for cell in cells}
    centers = rng.sample(list(cells), min(5, len(cells)))
    for cluster_no, (cx, cy) in enumerate(centers, start=1):
        radius = rng.choice((1, 2, 2, 3))
        label = "B%d" % ((cluster_no - 1) % 3 + 1)
        for x, y in cells:
            # Small jaggedness keeps clusters recognisable without circles being
            # the only possible fingerprint shape.
            if abs(x - cx) + abs(y - cy) <= radius + ((x * 17 + y * 11) % 3 == 0):
                bins[(x, y)] = label
    for cell in cells:
        if bins[cell] == "B0" and rng.random() < 0.018:
            bins[cell] = "B%d" % rng.randint(1, 3)
    return bins, centers


def missing_die_cells(cells, meta, seed=20260809):
    """Choose visible, deterministic gaps in the physical core map.

    Bins alone make a map look fully occupied.  A real defect fixture also
    needs missing dies: a few edge bites plus a small interior chip make the
    partial DT slices visibly unlike an ideal valid-die footprint.  The valid
    die reference remains whole; only the physical core wafer loses these
    cells.
    """
    cell_set = set(cells)
    rng = random.Random(seed ^ 0xC0DE)
    xs = sorted({x for x, _y in cell_set})
    ys = sorted({y for _x, y in cell_set})
    edge = sorted((x, y) for x, y in cell_set
                  if x in (xs[0], xs[-1]) or y in (ys[0], ys[-1]))
    # Spread five bites around the perimeter instead of removing one smooth
    # arc. The shape stays recognisable after the wafer is split by DT job.
    holes = {edge[(i * len(edge)) // 5] for i in range(5)} if edge else set()
    interior = [(x, y) for x, y in cell_set
                if x not in (xs[0], xs[-1]) and y not in (ys[0], ys[-1])]
    if interior:
        cx, cy = rng.choice(interior)
        for x, y in interior:
            if abs(x - cx) + abs(y - cy) <= 1:
                holes.add((x, y))
    target_missing = len(cell_set) - round(len(cell_set) * CORE_YIELD)
    # Fill the rest with deterministic distributed dropouts. At 70% yield the
    # visible teeth must be a property of the map, not merely a token defect
    # cluster; the seeded shuffle keeps every run reproducible.
    remaining = list(cell_set - holes)
    rng.shuffle(remaining)
    holes.update(remaining[:max(0, target_missing - len(holes))])
    return holes


def _recorded(cells, reference_meta, frame):
    import map_overlay
    from dt_map_derivation import source_meta_for_frame

    source_meta = source_meta_for_frame(reference_meta, frame)
    if source_meta is None:
        raise ValueError("unsupported frame %s" % frame)
    transform = map_overlay.make_frame_transform(reference_meta, source_meta)
    return [transform(x, y) for x, y in cells]


def build_plans(core_cells, core_meta, dt_cells, dt_meta, seed=20260809, job_count=3):
    if job_count not in (2, 3):
        raise ValueError("job_count must be 2 or 3")
    missing = missing_die_cells(core_cells, core_meta, seed)
    core_cells = sorted(set(core_cells) - missing)
    bins, centers = clustered_bins(core_cells, seed)
    # Partition once, then order EACH already-disjoint slice from its own
    # occupied outer column. Reversing the whole wafer before slicing would
    # overlap jobs and make a synthetic defect appear twice.
    partition_order = core_column_walk(core_cells, core_meta, False)
    ordered_dt = _serpentine(dt_cells, dt_meta)
    # 261 CORE_DT dies split three ways fit the 88 PRD slots. Refuse rather than
    # silently dropping a core slice should the reference map later change.
    chunk_size = (len(partition_order) + job_count - 1) // job_count
    if chunk_size > len(ordered_dt):
        raise ValueError("CORE_DT split exceeds PRD-A_DT13 destination capacity")
    dt_rotations = (0, 90, 180) if job_count == 3 else (90, 270)
    # Independent synthetic truth for the core recorder. No equation or
    # inference is allowed to derive this from the corresponding DT rotation.
    core_frames = ("rot270_front", "rot0_front", "rot90_front") if job_count == 3 else (
        "rot180_front", "rot0_front")
    plans = []
    for part, rotation in enumerate(dt_rotations, start=1):
        starts_at_right = bool(part % 2 == 0)
        portion = partition_order[(part - 1) * chunk_size:part * chunk_size]
        portion = core_column_walk(portion, core_meta, starts_at_right)
        if not portion:
            continue
        digest = hashlib.sha256((str(seed) + repr(portion[:3])).encode()).hexdigest()[:8].upper()
        job_id = "%sP%d-R%d-H%s" % (JOB_PREFIX, part, rotation, digest)
        core_frame = core_frames[part - 1]
        dt_frame = "rot%d_front" % rotation
        raw_core = _recorded(portion, core_meta, core_frame)
        raw_dt = _recorded(ordered_dt[:len(portion)], dt_meta, dt_frame)
        rows = []
        for index, (core, core_xy, dt_xy) in enumerate(zip(portion, raw_core, raw_dt), start=1):
            rows.append({
                "dt_job": job_id, "dt_eqp": "SYN-CORE-EQP", "product": "PRD-A",
                "dt_lot": "SYN-DT-CORE", "dt_slot": "S%02d" % part,
                "dt_x": dt_xy[0], "dt_y": dt_xy[1], "dt_index": index,
                "core_lot": CORE_LOT, "core_slot": CORE_SLOT, "core_wafer": CORE_WAFER,
                "core_x": core_xy[0], "core_y": core_xy[1],
                "c_bn": bins[core],
                "event_time": EVENT_TIME,
            })
        plans.append({"job_id": job_id, "dt_frame": dt_frame, "core_frame": core_frame,
                      "core_start": core_column_start(portion, core_meta, starts_at_right),
                      "core_start_side": "TR" if starts_at_right else "TL",
                      "rows": rows, "core_cells": portion})
    return bins, centers, plans


def _batch(rows, *, replace_map=False, scope=None):
    from database import schemas
    return schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        updates=row, source_name=SOURCE_NAME, updated_by=UPDATED_BY) for row in rows],
        replace_map=replace_map, scope=scope)


def core_view_rows(plans):
    """Project each job's raw core coordinates into the review-only map table.

    The projection intentionally has no wafer_map_metadata row.  The reviewer
    selects the product-specific valid-die reference in the aligner, which lets
    the scorer borrow only that reference geometry without claiming a core
    frame before it has been reviewed.
    """
    return [{
        "dt_job": row["dt_job"], "core_lot": row["core_lot"],
        "core_slot": row["core_slot"], "core_wafer": row["core_wafer"],
        "core_x": row["core_x"], "core_y": row["core_y"],
        "dt_index": row["dt_index"], "c_bn": row["c_bn"],
    } for plan in plans for row in plan["rows"]]


def write_csv_files(directory, plans):
    """Write one UTF-8 ``dt_log`` ingestion CSV per synthetic job.

    This path has no database write side effect.  Supplying a later
    ``--event-time`` makes the eventual file ingestion a deliberate changed
    source event, so the normal outbox/chain route is exercised.
    """
    output_dir = Path(directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for plan in plans:
        path = output_dir / (plan["job_id"] + ".csv")
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=DT_LOG_COLUMNS,
                                    extrasaction="raise")
            writer.writeheader()
            writer.writerows(plan["rows"])
        paths.append(path)
    return paths


def apply_physical_core_seed(db, core_meta, bins):
    """Replace exactly one physical core-wafer map and register its metadata."""
    from database import crud
    import map_overlay
    # ``bins`` contains only the physically present cells. ``replace_map`` below
    # removes every previous synthetic cell in this exact core wafer scope, so
    # omitted keys become visible missing dies rather than stale rows.
    core_rows = [{"core_lot": CORE_LOT, "core_slot": CORE_SLOT, "wafer_id": CORE_WAFER,
                  "core_x": x, "core_y": y, "c_bn": bins[(x, y)],
                  "event_time": EVENT_TIME} for x, y in sorted(bins)]
    _, core_changed, _, _ = crud.apply_batch_updates(
        db, "core_wafer_map", _batch(core_rows, replace_map=True,
                                     scope={"wafer_id": CORE_WAFER}))
    # ``core_wafer_map`` declares wafer_id as its only map key.  Metadata must
    # use the same identity or the core alignment rule cannot resolve it.
    core_map_id = CORE_WAFER
    core_map_meta = map_overlay.apply_valid_die_ref(
        dict(core_meta), {"table": "valid_die_ref", "map_id": _map_id(*CORE_REF)})
    _, meta_changed, _, _ = crud.apply_batch_updates(db, "wafer_map_metadata", _batch([{
        "target_table": "core_wafer_map", "map_id": core_map_id,
        "grid_metadata": json.dumps(core_map_meta, ensure_ascii=False, sort_keys=True),
    }]))
    return len(core_changed or ()), len(meta_changed or ())


def apply_seed(db, core_cells, core_meta, bins, plans):
    from database import crud, models
    current_jobs = {plan["job_id"] for plan in plans}
    # The job id has a fixture-content hash. Changing yield legitimately changes
    # that hash, so replace the old synthetic job scopes before writing the new
    # set. Never touch a job outside this explicit fixture prefix.
    for table_name in ("dt_log", "dt_core_view"):
        model = models.DYNAMIC_TABLES[table_name]
        stale_jobs = [row[0] for row in db.query(model.dt_job).filter(
            model.dt_job.like(JOB_PREFIX + "%")).distinct().all() if row[0] not in current_jobs]
        for job_id in stale_jobs:
            crud.apply_batch_updates(
                db, table_name, _batch([], replace_map=True, scope={"dt_job": job_id}))
    core_changed, meta_changed = apply_physical_core_seed(db, core_meta, bins)
    dt_changed = 0
    for plan in plans:
        _, changed, _, _ = crud.apply_batch_updates(
            db, "dt_log", _batch(plan["rows"], replace_map=True,
                                  scope={"dt_job": plan["job_id"]}))
        dt_changed += len(changed or ())
    view_changed = 0
    view_by_job = {}
    for row in core_view_rows(plans):
        view_by_job.setdefault(row["dt_job"], []).append(row)
    for job_id, rows in view_by_job.items():
        _, changed, _, _ = crud.apply_batch_updates(
            db, "dt_core_view", _batch(rows, replace_map=True, scope={"dt_job": job_id}))
        view_changed += len(changed or ())
    return len(core_changed or ()), len(meta_changed or ()), dt_changed, view_changed


def main():
    global CORE_LOT, CORE_SLOT, CORE_WAFER, JOB_PREFIX, EVENT_TIME
    parser = argparse.ArgumentParser(description="Seed clustered CORE_DT defects split over synthetic DT jobs.")
    parser.add_argument("--apply", action="store_true", help="write additive synthetic rows")
    parser.add_argument("--seed", type=int, default=20260809)
    parser.add_argument("--jobs", type=int, choices=(2, 3), default=3)
    parser.add_argument("--core-lot", default=CORE_LOT,
                        help="fixture core lot; also namespaces its synthetic DT jobs")
    parser.add_argument("--core-slot", default=CORE_SLOT,
                        help="fixture core slot used by the physical reference map")
    parser.add_argument("--core-wafer", default=CORE_WAFER,
                        help="enriched core wafer identity copied into dt_log")
    parser.add_argument("--event-time", default=EVENT_TIME,
                        help="source timestamp; changing it emits a deliberate dt_log replay event")
    parser.add_argument("--csv-dir", metavar="PATH",
                        help="write one UTF-8-SIG dt_log CSV per job into PATH without requiring --apply")
    parser.add_argument("--physical-core-only", action="store_true",
                        help="with --apply, write only core_wafer_map and its metadata (never dt_log)")
    args = parser.parse_args()
    if args.physical_core_only and not args.apply:
        parser.error("--physical-core-only requires --apply")

    # One invocation owns only its lot/slot map scope and job prefix.  This
    # makes an additional synthetic wafer additive instead of replacing the
    # original SYN-CORE-CLUSTER sample on its stale-job cleanup pass.
    CORE_LOT, CORE_SLOT, CORE_WAFER = args.core_lot, args.core_slot, args.core_wafer
    JOB_PREFIX = CORE_LOT + "-"
    EVENT_TIME = args.event_time

    from database.database import SessionLocal
    from database import crud, models
    models.init_dynamic_models(crud.TABLE_CONFIG)
    db = SessionLocal()
    try:
        core_cells, core_meta = _load_reference(db, *CORE_REF)
        dt_cells, dt_meta = _load_reference(db, *DT_REF)
        bins, centers, plans = build_plans(core_cells, core_meta, dt_cells, dt_meta,
                                            seed=args.seed, job_count=args.jobs)
        physical_dies = sum(len(plan["core_cells"]) for plan in plans)
        print("CORE valid-die: CORE_DT (%d); physical core dies=%d; DT valid-die: PRD-A_DT13 (%d)" % (
            len(core_cells), physical_dies, len(dt_cells)))
        print("synthetic core wafer: %s / clustered centers: %s" % (CORE_WAFER, centers))
        for plan in plans:
            defects = sum(row["c_bn"] != "B0" for row in plan["rows"])
            print("%s dies=%d defects=%d dt=%s core_truth=%s core_%s=%s" % (
                plan["job_id"], len(plan["rows"]), defects, plan["dt_frame"], plan["core_frame"],
                plan["core_start_side"], plan["core_start"]))
        csv_paths = write_csv_files(args.csv_dir, plans) if args.csv_dir else []
        if args.apply and args.physical_core_only:
            core_changed, meta_changed = apply_physical_core_seed(db, core_meta, bins)
            print("WROTE core_wafer_map cells=%d, core metadata=%d; dt_log untouched" % (
                core_changed, meta_changed))
        elif args.apply:
            core_changed, meta_changed, dt_changed, view_changed = apply_seed(
                db, core_cells, core_meta, bins, plans)
            print("WROTE core_wafer_map cells=%d, core metadata=%d, dt_log cells=%d, "
                  "dt_core_view cells=%d" % (core_changed, meta_changed, dt_changed, view_changed))
        else:
            print("DRY RUN: no rows written. Re-run with --apply to write directly.")
        for path in csv_paths:
            print("csv: %s" % path)
    finally:
        db.close()


if __name__ == "__main__":
    main()
