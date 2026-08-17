# -*- coding: utf-8 -*-
"""Seed synthetic ``dt_log`` rows from the current root-lot valid-die floors.

The owner database currently declares ``dt_log`` as the raw transfer source and does not
declare a ``core_wafer_map`` table. Therefore a core-WF's synthetic map is represented by
the source tuples ``(core_wafer_id, c_wx, c_wy, c_bn)`` written to ``dt_log``. The root-lot
``valid_die_ref`` floor supplies the die domain and geometry; it is never overwritten.

For every root lot, its 25 core wafers are partitioned as ``3,2,3,2,...`` into ten DT
jobs. Thus every DT job contains at least two distinct core wafers and every core wafer
is used exactly once. Most jobs contain the complete valid-die floor, while every third
job intentionally contains a deterministic half-floor slice so full and partial DT maps
are present together. DT/core frame tokens rotate independently across the four front-side
rotation spellings. ``dt_inventory`` receives one identity row per job; exactly half of the
rows intentionally omit both frame JSON values and all equation fields, preserving the
job identity while simulating an unresolved inventory chain.

This is bounded and idempotent. It replaces only the owned synthetic ``dt_log`` scope,
then writes its ``wafer_map_metadata`` records and ``dt_inventory``. ``dt_map`` remains
a derived table and is intentionally not hand-written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


DT_TABLE = "dt_log"
INVENTORY_TABLE = "dt_inventory"
META_TABLE = "wafer_map_metadata"
VALID_TABLE = "valid_die_ref"
VALID_TYPE = "WF"
JOB_PREFIX = "SYN-DT-ROOT-"
SOURCE_NAME = "custom_script"
UPDATED_BY = "seed_dt_log_from_root_refs"
FRAME_TOKENS = (
    "rot0_front", "rot90_front", "rot180_front", "rot270_front",
)
PARTIAL_JOB_PERIOD = 3
CORE_BINS = ("B1", "B2", "B3", "B4")
MAX_SOURCE_ROWS = 10_000
EXPECTED_ROOTS = {"NAB115", "NAB122", "NAB123", "NAB163", "NAB539"}
WAFER_RE = re.compile(r"^(?P<root>.+)-W\d+$")


def _stable_seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def _root_from_wafer(value: str):
    match = WAFER_RE.match(str(value or "").strip())
    return match.group("root") if match else None


def _frame_meta(base_meta: dict, token: str) -> dict:
    from dt_map_derivation import source_meta_for_frame

    meta = source_meta_for_frame(base_meta, token)
    if meta is None:
        raise SystemExit(f"REFUSED: unsupported frame token {token!r}.")
    return meta


def _express(cells, base_meta: dict, token: str):
    """Reference-frame cells -> coordinates as recorded by the selected frame."""
    import map_overlay

    source_meta = _frame_meta(base_meta, token)
    transform = map_overlay.make_frame_transform(base_meta, source_meta)
    return [transform(x, y) for x, y in cells]


def _batch(items, business_keys=None, *, replace_map=False, scope=None):
    from database import schemas

    keys = list(business_keys or ())
    return schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(
            updates=updates,
            source_name=SOURCE_NAME,
            updated_by=UPDATED_BY,
            business_key_val=(keys[i] if i < len(keys) else None),
        )
        for i, updates in enumerate(items)
    ], replace_map=replace_map, scope=scope)


def _write(db, table: str, items, business_keys=None, chunk: int = 1000,
           *, replace_map=False, scope=None) -> int:
    from database import crud

    changed = 0
    keys = list(business_keys or ())
    for start in range(0, len(items), chunk):
        part_keys = keys[start:start + chunk] if keys else None
        _, cells, _, _ = crud.apply_batch_updates(
            db, table, _batch(items[start:start + chunk], part_keys,
                              replace_map=replace_map, scope=scope)
        )
        changed += len(cells or ())
    return changed


def _source_roots(db):
    """Bounded root/core-WF extraction from lot_event wafer identities."""
    from database import models

    model = models.DYNAMIC_TABLES.get("lot_event")
    if model is None:
        raise SystemExit("REFUSED: lot_event is not declared.")
    rows = (db.query(model.waferids)
            .order_by(model.updated_at, model.row_id)
            .limit(MAX_SOURCE_ROWS + 1).all())
    if len(rows) > MAX_SOURCE_ROWS:
        raise SystemExit(f"REFUSED: lot_event exceeds {MAX_SOURCE_ROWS}-row setup scope.")

    by_root = {}
    for (raw,) in rows:
        for wafer in str(raw or "").split(":"):
            wafer = wafer.strip()
            if not wafer:
                continue
            root = _root_from_wafer(wafer)
            if root is None:
                raise SystemExit(f"REFUSED: unreadable core wafer id {wafer!r}.")
            by_root.setdefault(root, set()).add(wafer)
    if set(by_root) != EXPECTED_ROOTS:
        raise SystemExit(
            "REFUSED: root set changed; measured=%s expected=%s"
            % (sorted(by_root), sorted(EXPECTED_ROOTS))
        )
    if any(len(wafers) != 25 for wafers in by_root.values()):
        raise SystemExit("REFUSED: every reviewed root must contain exactly 25 core WFs.")
    return {root: sorted(wafers) for root, wafers in sorted(by_root.items())}


def _load_reference_maps(db, roots):
    from database import models

    cell_model = models.DYNAMIC_TABLES.get(VALID_TABLE)
    meta_model = models.DYNAMIC_TABLES.get(META_TABLE)
    if cell_model is None or meta_model is None:
        raise SystemExit("REFUSED: valid_die_ref or wafer_map_metadata is not declared.")

    metas = (db.query(meta_model.map_id, meta_model.grid_metadata)
             .filter(meta_model.target_table == VALID_TABLE,
                     meta_model.map_id.in_([f"{root}_WF" for root in roots])).all())
    meta_by_root = {}
    for map_id, raw in metas:
        try:
            meta = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            meta = None
        root = str(map_id).removesuffix("_WF") if map_id else ""
        if root in roots and isinstance(meta, dict):
            meta_by_root[root] = meta

    rows = (db.query(cell_model.product, cell_model.x, cell_model.y)
            .filter(cell_model.product.in_(list(roots)),
                    cell_model.type == VALID_TYPE).all())
    cells_by_root = {root: set() for root in roots}
    for root, x, y in rows:
        if x is not None and y is not None:
            cells_by_root[str(root)].add((int(float(x)), int(float(y))))
    for root in roots:
        if root not in meta_by_root or not cells_by_root[root]:
            raise SystemExit(f"REFUSED: root floor {root}_WF is missing or empty.")
    return meta_by_root, cells_by_root


def _groups(wafers):
    """Partition 25 wafers into ten groups: 3,2 repeated five times."""
    out, cursor = [], 0
    for size in (3, 2) * 5:
        out.append(wafers[cursor:cursor + size])
        cursor += size
    assert cursor == len(wafers) and all(len(group) >= 2 for group in out)
    return out


def _core_map(wafer_id, cells):
    """Deterministic arbitrary bin map for one core WF (not persisted separately)."""
    rng = random.Random(_stable_seed("core-map:" + wafer_id))
    ordered = sorted(cells)
    return {cell: rng.choice(CORE_BINS) for cell in ordered}


def _valid_die_pointer(root: str) -> dict:
    """Declare the root floor consumed by a DT/core frame."""
    return {"table": VALID_TABLE, "map_id": f"{root}_WF"}


def _partition_floor_cells(floor_cells, core_count):
    """Round-robin partition that preserves every floor cell exactly once."""
    if core_count < 1:
        raise ValueError("core_count must be positive")
    return [list(floor_cells[i::core_count]) for i in range(core_count)]


def _snake_floor_cells(floor_cells):
    """Order cells from the upper-right in alternating left/right row sweeps."""
    by_row = {}
    for x, y in floor_cells:
        by_row.setdefault(y, []).append((x, y))
    ordered = []
    for row_index, y in enumerate(sorted(by_row)):
        row = sorted(by_row[y], key=lambda cell: cell[0],
                     reverse=(row_index % 2 == 0))
        ordered.extend(row)
    return ordered


def _coverage_cells(floor_cells, global_job):
    """Return a contiguous full/partial prefix of the DT snake path."""
    ordered = _snake_floor_cells(floor_cells)
    if global_job % PARTIAL_JOB_PERIOD == 0:
        return ordered[:(len(ordered) + 1) // 2], "partial"
    return ordered, "full"


def build_plans(roots, wafers_by_root, metas, cells_by_root):
    """Build pure plans; no DB mutation occurs here."""
    from dt_frame_transform import core_equations, dt_equations

    plans = []
    global_job = 0
    base_time = datetime(2026, 2, 1, 8, 0, tzinfo=timezone.utc)
    for root, wafers in wafers_by_root.items():
        base_meta = metas[root]
        floor_cells = _snake_floor_cells(cells_by_root[root])
        jobs = _groups(wafers)
        for local_slot, core_wafers in enumerate(jobs, start=1):
            global_job += 1
            job_id = f"{JOB_PREFIX}{root}-J{local_slot:02d}"
            dt_token = FRAME_TOKENS[global_job % len(FRAME_TOKENS)]
            core_token = FRAME_TOKENS[(global_job * 3 + 1) % len(FRAME_TOKENS)]
            dt_meta = _frame_meta(base_meta, dt_token)
            core_meta = _frame_meta(base_meta, core_token)
            dt_meta["synthetic_frame_token"] = dt_token
            core_meta["synthetic_frame_token"] = core_token
            dt_meta["source_root_lot"] = root
            core_meta["source_root_lot"] = root
            # The generated coordinates intentionally follow the root floor, including
            # its one-cell notch.  Persist the reference declaration so map consumers
            # do not fall back to a circle-only mask and classify valid edge cells as
            # outside the map.
            dt_meta["valid_die_ref"] = _valid_die_pointer(root)
            core_meta["valid_die_ref"] = _valid_die_pointer(root)

            selected_cells, coverage_mode = _coverage_cells(floor_cells, global_job)
            dt_meta["synthetic_coverage"] = coverage_mode
            core_meta["synthetic_coverage"] = coverage_mode

            # Each core WF gets its own full arbitrary bin map.  The DT floor slice is
            # the shared physical die selection: both coordinate pairs are projections
            # of the same reference cell, while the core-specific map supplies c_bn.
            # Keeping B/C paired is essential; independently sampling C coordinates
            # makes a valid core die appear unrelated to the DT die on screen.
            maps_by_core = {}
            for wafer_id in core_wafers:
                core_map = _core_map(wafer_id, floor_cells)
                maps_by_core[wafer_id] = core_map

            rows = []
            # Keep dt_index continuous along the snake path.  Core wafers take turns
            # owning cells, which preserves the composite B-key uniqueness while the
            # visible DT progression remains upper-right -> alternating row sweeps.
            dt_segment = _express(selected_cells, base_meta, dt_token)
            core_raw = _express(selected_cells, base_meta, core_token)
            for index, ((bx, by), (cx, cy), reference_cell) in enumerate(
                    zip(dt_segment, core_raw, selected_cells), start=1):
                wafer_id = core_wafers[(index - 1) % len(core_wafers)]
                core_slot = int(wafer_id.rsplit("-W", 1)[1])
                rows.append({
                        "dt_event_id": f"SYN-DTE-{root}-{local_slot:02d}-{index:04d}",
                        "dt_job_id": job_id,
                        "event_time": base_time + timedelta(minutes=global_job, seconds=index),
                        "dt_index": index,
                        "dt_lot": f"DT-{root}",
                        "dt_slot": local_slot,
                        "b_wx": bx,
                        "b_wy": by,
                        "core_lot": root,
                        "core_slot": core_slot,
                        "core_wafer_id": wafer_id,
                        "c_wx": cx,
                        "c_wy": cy,
                        "c_bn": maps_by_core[wafer_id][reference_cell],
                })

            equations = {
                **dt_equations(dt_meta, base_meta, floor_cells),
                **core_equations(core_meta, base_meta, floor_cells),
            }
            complete = global_job % 2 == 0
            inventory = {
                "dt_job_id": job_id,
                "dt_eqp": f"SYN-DT-EQP-{(global_job % 3) + 1}",
                "dt_lot": f"DT-{root}",
                "dt_slot": f"{local_slot:02d}",
            }
            if complete:
                inventory.update({
                    "dt_frame": json.dumps(dt_meta, ensure_ascii=False, sort_keys=True),
                    "core_frame": json.dumps(core_meta, ensure_ascii=False, sort_keys=True),
                    **equations,
                })
            else:
                inventory.update({
                    "dt_frame": None, "core_frame": None,
                    **{field: None for field in (
                        "dt_x_base", "dt_x_sign", "dt_x_offset", "dt_y_base",
                        "dt_y_sign", "dt_y_offset", "core_x_base", "core_x_sign",
                        "core_x_offset", "core_y_base", "core_y_sign", "core_y_offset",
                    )},
                })
            plans.append({
                "root_lot": root,
                "job_id": job_id,
                "dt_token": dt_token,
                "core_token": core_token,
                "core_wafers": tuple(core_wafers),
                "rows": rows,
                "coverage_mode": coverage_mode,
                "coverage_cells": len(selected_cells),
                "floor_cells": len(floor_cells),
                "metadata": dt_meta,
                "inventory": inventory,
                "complete_inventory": complete,
            })
    return plans


def _verify_prefixes(db):
    from database import models

    expected = {f"{JOB_PREFIX}{root}-J{slot:02d}"
                for root in EXPECTED_ROOTS for slot in range(1, 11)}
    for table, column in ((DT_TABLE, "dt_job_id"), (INVENTORY_TABLE, "dt_job_id")):
        model = models.DYNAMIC_TABLES.get(table)
        if model is None:
            raise SystemExit(f"REFUSED: {table} is not declared.")
        rows = db.query(getattr(model, column)).filter(
            getattr(model, column).like(JOB_PREFIX + "%")).distinct().all()
        stray = sorted({str(row[0]) for row in rows} - expected)
        if stray:
            raise SystemExit(f"REFUSED: unowned synthetic job ids exist in {table}: {stray[:5]}")

    meta_model = models.DYNAMIC_TABLES.get(META_TABLE)
    if meta_model is None:
        raise SystemExit(f"REFUSED: {META_TABLE} is not declared.")
    stray_meta = (db.query(meta_model.map_id)
                  .filter(meta_model.target_table == DT_TABLE,
                          meta_model.map_id.like(JOB_PREFIX + "%"))
                  .distinct().all())
    if stray_meta:
        known = {f"{JOB_PREFIX}{root}-J{slot:02d}"
                 for root in EXPECTED_ROOTS for slot in range(1, 11)}
        stray = sorted({str(row[0]) for row in stray_meta} - known)
        if stray:
            raise SystemExit(f"REFUSED: unowned synthetic metadata ids exist: {stray[:5]}")


def _dt_replacement_payload(db, rows):
    """Claim the full DT scope without churning unchanged datetime sources."""
    from database import models

    model = models.DYNAMIC_TABLES[DT_TABLE]
    existing = {
        (str(row.dt_job_id), float(row.b_wx), float(row.b_wy)): row
        for row in db.query(model).filter(model.dt_job_id.like(JOB_PREFIX + "%")).all()
    }
    payload = []
    for updates in rows:
        key = (str(updates["dt_job_id"]), float(updates["b_wx"]), float(updates["b_wy"]))
        current = existing.get(key)
        if current is not None and str(current.dt_event_id) == str(updates["dt_event_id"]):
            # event_time is already equal at the resolved-row level.  The shared
            # source layer serializes it as JSON text, so sending the datetime object
            # again would look changed even though the instant is identical.
            payload.append({k: v for k, v in updates.items() if k != "event_time"})
        else:
            # ``event_time`` is a Python datetime in the ORM row, but the shared
            # outbox payload is JSONB.  New coordinates after a frame/origin fix
            # legitimately take this branch, so normalize the instant before the
            # batch reaches the outbox serializer.
            normalized = dict(updates)
            event_time = normalized.get("event_time")
            if isinstance(event_time, datetime):
                normalized["event_time"] = event_time.isoformat()
            payload.append(normalized)
    return payload


def seed(db, plans, apply_changes):
    from database import models

    _verify_prefixes(db)
    report = {"jobs": len(plans), "blank_inventory": 0, "complete_inventory": 0,
              "dt_rows": sum(len(p["rows"]) for p in plans),
              "dt_cells_changed": 0, "meta_cells_changed": 0,
              "inventory_cells_changed": 0}
    for plan in plans:
        if plan["complete_inventory"]:
            report["complete_inventory"] += 1
        else:
            report["blank_inventory"] += 1
        if not apply_changes:
            continue
        # A frame change can move the composite B coordinate, so each DT job is
        # replaced within its declared map scope.  The complete payload claims all
        # rows; crud's map-key diff retracts old coordinates and suppresses no-op
        # cells on replay.
        report["dt_cells_changed"] += _write(
            db, DT_TABLE, _dt_replacement_payload(db, plan["rows"]),
            replace_map=True, scope={"dt_job_id": plan["job_id"]}
        )
        report["meta_cells_changed"] += _write(db, META_TABLE, [{
            "target_table": DT_TABLE,
            "map_id": plan["job_id"],
            "grid_metadata": json.dumps(plan["metadata"], ensure_ascii=False, sort_keys=True),
        }])
        report["inventory_cells_changed"] += _write(
            db, INVENTORY_TABLE, [plan["inventory"]], [plan["job_id"]]
        )
    return report


def main():
    parser = argparse.ArgumentParser(description="Seed synthetic multi-core dt_log jobs.")
    parser.add_argument("--apply", action="store_true", help="write; default is dry-run")
    parser.add_argument("--show", action="store_true", help="print job/frame summary")
    parser.add_argument("--i-accept-writing-to-owner-database", action="store_true",
                        dest="accepted")
    args = parser.parse_args()
    if args.apply and not args.accepted:
        raise SystemExit("REFUSED: --apply needs --i-accept-writing-to-owner-database.")

    from database.database import SessionLocal
    from database import crud, models

    models.init_dynamic_models(crud.TABLE_CONFIG)
    db = SessionLocal()
    try:
        wafers = _source_roots(db)
        metas, cells = _load_reference_maps(db, sorted(wafers))
        plans = build_plans(sorted(wafers), wafers, metas, cells)
        report = seed(db, plans, args.apply)
    finally:
        db.close()

    print("synthetic dt jobs       : %d" % report["jobs"])
    print("dt_log rows planned     : %d" % report["dt_rows"])
    print("inventory complete/blank: %d/%d (exactly 50%% blank)"
          % (report["complete_inventory"], report["blank_inventory"]))
    if args.show:
        for plan in plans:
            print("%-24s core=%d dt=%-13s core=%-13s rows=%d inventory=%s"
                  % (plan["job_id"], len(plan["core_wafers"]), plan["dt_token"],
                     plan["core_token"], len(plan["rows"]),
                     "complete" if plan["complete_inventory"] else "blank"))
    if args.apply:
        print("dt_log changed           : %d" % report["dt_cells_changed"])
        print("metadata changed         : %d" % report["meta_cells_changed"])
        print("dt_inventory changed     : %d" % report["inventory_cells_changed"])
        print("WROTE synthetic dt_log + metadata + 50%% incomplete inventory.")
    else:
        print("DRY RUN, nothing written.")


if __name__ == "__main__":
    main()
