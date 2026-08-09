"""Create two safe, reproducible DT alignment samples from the PRD valid-die map.

The generated jobs differ only in their first ``dt_index`` corner:

* ``SYN-TL-R<rotation>-<seed>`` records the PRD field from its top-left die;
* ``SYN-TR-R<rotation>-<seed>`` records it from its top-right die.

By default each start corner is generated for rotations 0, 90, 180, and 270.
Both corner variants use the same `front` side for a given rotation. A top-right
start is a sequence rule only: it makes `dt_index=1` the top-right valid die and
does not mirror the recorded coordinate map.

Each job chooses a reproducible random index upper bound and emits a sparse
subset of ``dt_index=1..N`` (including 1 and N). A short plan hash in the job id
identifies the exact corner/rotation/index plan. This is important: automatic alignment
must receive actual index values, not merely a declared ``dt_index`` column.
The script reads the live PRD valid-die cells and their metadata; it refuses
rather than guessing a reference shape or grid.

Usage:
    python server/scripts/seed_syn_dt_alignment_samples.py
    python server/scripts/seed_syn_dt_alignment_samples.py --apply
    python server/scripts/seed_syn_dt_alignment_samples.py --seed 20260809 --show

Writes are additive/upsert-only through ``crud.apply_batch_updates``.  The
default is dry-run, and a fixed seed means a second ``--apply`` is idempotent.
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
import uuid

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


REFERENCE_TABLE = "valid_die_ref"
REFERENCE_PRODUCT = "PRD-A"
REFERENCE_TYPE = "DT13"
META_TABLE = "wafer_map_metadata"
TARGET_TABLE = "dt_log"
SOURCE_NAME = "custom_script"
UPDATED_BY = "seed_syn_dt_alignment_samples"
CHUNK_SIZE = 1000
DT_LOG_COLUMNS = (
    "dt_job", "dt_eqp", "product", "dt_lot", "dt_slot", "dt_x", "dt_y", "dt_index",
    "core_lot", "core_slot", "core_wafer", "core_x", "core_y", "c_bn", "event_time",
)


def reference_map_id(product=REFERENCE_PRODUCT, ref_type=REFERENCE_TYPE):
    return "%s_%s" % (product, ref_type)


def _top_to_bottom_rows(cells, meta):
    """Return each horizontal row in the declared physical top-to-bottom order."""
    by_y = {}
    for x, y in cells:
        by_y.setdefault(y, []).append(x)
    y_values = sorted(by_y, reverse=bool(meta.get("grid_y_invert")))
    return [(y, sorted(by_y[y])) for y in y_values]


def ranked_reference_cells(cells, meta, starts_at_top_right):
    """One continuous serpentine rank in the PRD reference frame.

    The initial physical row follows the requested corner.  Subsequent rows
    alternate direction; this makes ``dt_index=1`` observably top-left or
    top-right while retaining one index for every valid die.
    """
    ordered = []
    for row_index, (y, xs) in enumerate(_top_to_bottom_rows(cells, meta)):
        right_to_left = bool(starts_at_top_right) ^ bool(row_index % 2)
        ordered.extend((x, y) for x in (reversed(xs) if right_to_left else xs))
    return ordered


def choose_index_limit(total_cells, *, seed, label, rotation):
    """Return a reproducible random inclusive upper bound for one sample job."""
    if total_cells < 1:
        raise ValueError("cannot choose an index limit without valid dies")
    planner = random.Random("%s:%s:%s:index-limit" % (seed, label, rotation))
    return planner.randint(1, total_cells)


def choose_index_positions(index_limit, *, seed, label, rotation):
    """Keep both endpoints and deterministically skip some middle indices."""
    positions = list(range(1, index_limit + 1))
    if index_limit <= 2:
        return positions
    planner = random.Random("%s:%s:%s:index-skip" % (seed, label, rotation))
    kept = [1]
    kept.extend(index for index in positions[1:-1] if planner.random() >= 0.25)
    kept.append(index_limit)
    if len(kept) == index_limit:  # Make the requested skip visible for every eligible job.
        kept.remove(planner.choice(kept[1:-1]))
    return kept


def plan_hash(cells, meta, *, starts_at_top_right, rotation, index_limit, index_positions, seed):
    """Stable short identity for the reference prefix a job will ingest."""
    ordered = ranked_reference_cells(cells, meta, starts_at_top_right)
    if not 1 <= index_limit <= len(ordered):
        raise ValueError("index_limit must be within the valid-die count")
    if not index_positions or index_positions[0] != 1 or index_positions[-1] != index_limit:
        raise ValueError("index_positions must include index 1 and the upper bound")
    identity = {
        "reference": "%s:%s" % (REFERENCE_PRODUCT, REFERENCE_TYPE),
        "seed": seed,
        "rotation": rotation,
        "starts_at_top_right": bool(starts_at_top_right),
        "index_limit": index_limit,
        "index_positions": index_positions,
        "reference_cells": [ordered[index - 1] for index in index_positions],
    }
    encoded = json.dumps(identity, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:8].upper()


def sample_job_id(cells, meta, *, label, starts_at_top_right, rotation, index_limit,
                  index_positions, seed):
    digest = plan_hash(cells, meta, starts_at_top_right=starts_at_top_right,
                       rotation=rotation, index_limit=index_limit,
                       index_positions=index_positions, seed=seed)
    return "SYN-%s-R%d-N%03d-H%s-%d" % (label, rotation, index_limit, digest, uuid.uuid4())


def _recorded_coordinates(reference_cells, ref_meta, frame):
    """Express PRD reference cells as the equipment records the requested frame."""
    import map_overlay
    from dt_map_derivation import source_meta_for_frame

    source_meta = source_meta_for_frame(ref_meta, frame)
    if source_meta is None:
        raise ValueError("unsupported DT frame: %s" % frame)
    transform = map_overlay.make_frame_transform(ref_meta, source_meta)
    return [transform(x, y) for x, y in reference_cells]


def build_job_rows(job_id, cells, ref_meta, *, starts_at_top_right, rotation, seed,
                   index_limit=None, index_positions=None):
    """Pure sample planner; no database access and no duplicate DT destinations."""
    reference_order = ranked_reference_cells(cells, ref_meta, starts_at_top_right)
    index_limit = len(reference_order) if index_limit is None else index_limit
    if not 1 <= index_limit <= len(reference_order):
        raise ValueError("index_limit must be within the valid-die count")
    reference_order = reference_order[:index_limit]
    index_positions = list(range(1, index_limit + 1)) if index_positions is None else index_positions
    if (not index_positions or index_positions[0] != 1 or index_positions[-1] != index_limit
            or len(set(index_positions)) != len(index_positions)
            or any(not 1 <= index <= index_limit for index in index_positions)):
        raise ValueError("index_positions must be unique and include both endpoints")
    # Start corner controls ranking only. It must not change the DT coordinate frame.
    frame = "rot%d_front" % rotation
    recorded = _recorded_coordinates(reference_order, ref_meta, frame)
    if len(set(recorded)) != len(recorded):
        raise ValueError("frame transform produced duplicate DT cells")

    rng = random.Random(seed)
    rows = []
    for index in index_positions:
        core_x, core_y = reference_order[index - 1]
        dt_x, dt_y = recorded[index - 1]
        rows.append({
            "dt_job": job_id,
            "dt_eqp": "SYN-EQP-%s" % ("TR" if starts_at_top_right else "TL"),
            "product": REFERENCE_PRODUCT,
            "dt_lot": "SYN-DT-%04d" % rng.randrange(10000),
            "dt_slot": "S%02d" % rng.randrange(1, 26),
            "dt_x": dt_x,
            "dt_y": dt_y,
            "dt_index": index,
            "core_lot": "SYN-CORE-%04d" % rng.randrange(10000),
            "core_slot": "C%02d" % rng.randrange(1, 26),
            "core_wafer": "SYN-WAFER-%04d" % rng.randrange(10000),
            "core_x": core_x,
            "core_y": core_y,
            "c_bn": "B%d" % rng.randrange(1, 5),
            "event_time": "2026-08-09T00:00:00Z",
        })
    return rows, frame


def load_prd_reference(db, product=REFERENCE_PRODUCT, ref_type=REFERENCE_TYPE):
    """Load the live PRD cells and metadata together; neither half is optional."""
    from database import models

    ref_model = models.DYNAMIC_TABLES.get(REFERENCE_TABLE)
    meta_model = models.DYNAMIC_TABLES.get(META_TABLE)
    if ref_model is None or meta_model is None:
        raise SystemExit("REFUSED: valid_die_ref or wafer_map_metadata is undeclared.")
    cells = sorted({(int(float(x)), int(float(y))) for x, y in db.query(ref_model.x, ref_model.y)
                    .filter(ref_model.product == product, ref_model.type == ref_type).all()
                    if x is not None and y is not None})
    if not cells:
        raise SystemExit("REFUSED: %s:%s/%s has no valid dies." % (REFERENCE_TABLE, product, ref_type))
    row = db.query(meta_model.grid_metadata).filter(
        meta_model.target_table == REFERENCE_TABLE,
        meta_model.map_id == reference_map_id(product, ref_type),
    ).one_or_none()
    try:
        meta = json.loads(row[0]) if row and row[0] else None
    except (TypeError, ValueError):
        meta = None
    required = {
        "grid_cols", "grid_rows", "grid_start_x", "grid_start_y", "grid_y_invert",
        "phys_wafer_dia", "phys_chip_x", "phys_chip_y", "phys_offset_x",
        "phys_offset_y", "phys_edge_margin",
    }
    if not isinstance(meta, dict) or not required.issubset(meta):
        raise SystemExit("REFUSED: PRD valid-die metadata is missing or incomplete.")
    return cells, meta


def _batch(rows):
    from database import schemas
    return schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(
            updates=row, source_name=SOURCE_NAME, updated_by=UPDATED_BY,
        ) for row in rows]
    )


def write_rows(db, rows, apply_changes):
    if not apply_changes:
        return 0
    from database import crud

    changed = 0
    for start in range(0, len(rows), CHUNK_SIZE):
        _, changed_cells, _, _ = crud.apply_batch_updates(
            db, TARGET_TABLE, _batch(rows[start:start + CHUNK_SIZE]))
        changed += len(changed_cells or ())
    return changed


def write_csv_files(directory, plans):
    """Write one portable CSV per job and return their paths.

    CSV generation is independent of database writes, so it can be used for a
    directory-watcher ingest test without first modifying ``dt_log``.
    """
    output_dir = Path(directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for _label, job_id, _frame, rows in plans:
        path = output_dir / (job_id + ".csv")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=DT_LOG_COLUMNS, extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
        paths.append(path)
    return paths


def main():
    parser = argparse.ArgumentParser(description="Seed PRD-based SYN DT alignment samples.")
    parser.add_argument("--apply", action="store_true", help="write dt_log rows; default is dry-run")
    parser.add_argument("--seed", type=int, default=20260809,
                        help="reproducible job suffix and random non-coordinate fields")
    parser.add_argument("--rotations", default="0,90,180,270",
                        help="comma-separated rotations to generate (default: 0,90,180,270)")
    parser.add_argument("--csv-dir", metavar="PATH",
                        help="also write one UTF-8 dt_log CSV per SYN job into PATH")
    parser.add_argument("--show", action="store_true", help="show the first six rows of each job")
    args = parser.parse_args()

    from database.database import SessionLocal
    from database import crud, models

    models.init_dynamic_models(crud.TABLE_CONFIG)
    db = SessionLocal()
    try:
        try:
            rotations = [int(value.strip()) for value in args.rotations.split(",") if value.strip()]
        except ValueError:
            raise SystemExit("REFUSED: --rotations must contain only 0,90,180,270.")
        if not rotations or any(value not in (0, 90, 180, 270) for value in rotations):
            raise SystemExit("REFUSED: --rotations must contain only 0,90,180,270.")
        if len(set(rotations)) != len(rotations):
            raise SystemExit("REFUSED: --rotations must not repeat a rotation.")

        cells, meta = load_prd_reference(db)
        plans = []
        for rotation in rotations:
            for label, top_right in (("TL", False), ("TR", True)):
                index_limit = choose_index_limit(len(cells), seed=args.seed, label=label,
                                                 rotation=rotation)
                index_positions = choose_index_positions(index_limit, seed=args.seed,
                                                         label=label, rotation=rotation)
                job_id = sample_job_id(cells, meta, label=label,
                                       starts_at_top_right=top_right, rotation=rotation,
                                       index_limit=index_limit, index_positions=index_positions,
                                       seed=args.seed)
                rows, frame = build_job_rows(
                    job_id, cells, meta, starts_at_top_right=top_right, rotation=rotation,
                    seed=args.seed + rotation + (1 if top_right else 0), index_limit=index_limit,
                    index_positions=index_positions,
                )
                plans.append((label, job_id, frame, rows))
        for label, job_id, frame, rows in plans:
            print("%s  %s  %d dies  expected frame %s  first dt=(%s,%s)" % (
                label, job_id, len(rows), frame, rows[0]["dt_x"], rows[0]["dt_y"]))
            if args.show:
                for row in rows[:6]:
                    print("  index=%d dt=(%s,%s) core=(%s,%s) bin=%s" % (
                        row["dt_index"], row["dt_x"], row["dt_y"], row["core_x"],
                        row["core_y"], row["c_bn"]))
        csv_paths = write_csv_files(args.csv_dir, plans) if args.csv_dir else []
        changed = sum(write_rows(db, rows, args.apply) for _label, _job, _frame, rows in plans)
    finally:
        db.close()
    print("changed cells: %d" % changed)
    for path in csv_paths:
        print("csv: %s" % path)
    if not args.apply:
        print("DRY RUN: no dt_log rows were written. Re-run with --apply to trigger the chain.")


if __name__ == "__main__":
    main()
