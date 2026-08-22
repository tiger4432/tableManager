# -*- coding: utf-8 -*-
"""Seed synthetic die-transfer rows into ``dt_log`` -- the first data of its kind.

WHY THIS EXISTS.  Across the 34,939 rows ``dt_log`` held on 2026-08-22, six columns were
entirely NULL: ``core_wafer_id``, ``c_wx``, ``c_wy``, ``dt_job_id``, ``b_wx``, ``b_wy``.
No seeder has ever written them, so the owner's ``transfer_event`` source refused its test
run with ``entity identity value is missing after preparation`` at ``rows[0].b_wx``.  Those
six are exactly what that source's declaration binds:

    subject (die@1)   mat_id=core_wafer_id   x=c_wx   y=c_wy      # the core wafer it left
    target  (die@1)   mat_id=dt_job_id       x=b_wx   y=b_wy      # the DT wafer it landed on

This is not repair -- there is nothing to restore.  It ADDS rows and never deletes any.

GEOMETRY IS READ, NEVER GENERATED.  Both die sets come out of ``valid_die_ref`` as they are:

    CORE side   product='5N'    type='BASE'   425 dies   x 1..25    y 1..21
    DT   side   product='CORE'  type='DT'     261 dies   x -3..15   y -3..15

FILL ORDER uses ``map_alignment.serpentine_index`` -- the walk this repository already owns.
That module's docstring forbids a second implementation of the walk, and the owner's
「맵 정렬기 참조해 (우상부터 지그재그)」 points at exactly it.  The arguments that produce
「우상부터」 (start at the TOP-RIGHT, zigzag) are:

    serpentine_index(dt_cells, top_is_min_y=True, left_to_right=False)

  * ``top_is_min_y=True`` -- ``wafer_map_metadata`` for map ``CORE_DT`` declares
    ``grid_y_invert: false``.  With ``invert_y=False``, ``CoordinateTransformer.cell_to_visual``
    maps the SMALLEST stored y to the top visual row, so y=-3 is the top row, not y=15.
    This is read from the map's own metadata, not assumed from the parameter name.
  * ``left_to_right=False`` -- the walk reverses a row when
    ``(r % 2 == 1) == left_to_right``.  On the first row (r=0) that is ``False == False``
    -> True -> descending x -> the row is entered from its RIGHT edge.

  Measured against the real 261 cells, that pair yields slots
  ``(7,-3) (6,-3) (5,-3) (2,-2) (3,-2) ...``: the top row right-to-left, then the next row
  left-to-right.  The other three argument pairs start at top-left, bottom-left or
  bottom-right and are wrong for this order.

SHAPE OF THE FIXTURE ("many cores -> one DT").  All ten core wafers' yielded dies are
pooled and shuffled once, then dealt to the ten DT wafers in turn.  A DT wafer therefore
draws from several core wafers by construction, and the run refuses if any DT wafer ends
up fed by fewer than two.

DETERMINISM.  Two runs must be identical.  The per-wafer die counts and the per-wafer core
yields are declared constants below (not draws), so the row total is arithmetic and needs
no execution to state.  Only WHICH dies are yielded and WHERE each lands is random, and
that randomness comes from one fixed seed.

IDEMPOTENCY.  ``dt_log`` declares ``business_key: dt_cell_key`` and carries a UNIQUE index
on ``business_key_val``.  Every row here is written with its ``dt_cell_key`` as the batch
business key, so a second run resolves onto the SAME rows and updates them in place.
Running twice cannot double the rows, because the keys are a pure function of the fixed
seed and the read geometry.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

DT_TABLE = "dt_log"
VALID_TABLE = "valid_die_ref"

#: The core wafer floor and the DT wafer floor, as declared in ``valid_die_ref``.
CORE_REF = ("5N", "BASE")
DT_REF = ("CORE", "DT")
#: Measured 2026-08-22 (read-only).  The yields below are percentages OF ``CORE_DIE_COUNT``
#: and the largest DT wafer is a FULL MAP of ``DT_SLOT_COUNT``, so a change in either
#: floor changes what this fixture means.  Refuse rather than silently reinterpret.
CORE_DIE_COUNT = 425
DT_SLOT_COUNT = 261

#: ``dt_job`` / ``dt_job_id`` for the ten DT wafers, and the synthetic product marker.
#: 🔴 ORDERING NOTE, deliberate.  The `dt_job` source reads this same table ordered by
#: ``(dt_job, dt_cell_key)`` and its cursor stood at ``{'dt_job': 'TWO',
#: 'dt_cell_key': 'TWO_3_10'}`` -- the maximum key in the table.  ``'SYN-XFER-D01' < 'TWO'``,
#: so these rows land BEHIND that cursor and `dt_job` will not translate them; its molecule
#: count is left undisturbed.  ``transfer_event`` has no cursor row at all, so it reads from
#: the beginning and DOES see them -- which is the source this fixture exists for.
#: To make `dt_job` pick them up too, give this prefix a value sorting after ``'TWO'``
#: (e.g. ``"XFER-SYN-D"``); that is the only edit needed.
JOB_PREFIX = "SYN-XFER-D"
CORE_WAFER_PREFIX = "SYN-XFER-CORE-W"
PRODUCT = "SYN-XFER"

SOURCE_NAME = "custom_script"
UPDATED_BY = "seed_syn_die_transfer"

SEED = 20260822

#: Dies on each of the ten DT wafers.  Owner: 「DT는 꽉 채우지 않아도 됨 20개 ~ FULL MAP
#: 사이로 채워」 -- spread across the declared range, the last one a full map.  Declared
#: rather than drawn so the row total is arithmetic: these sum to 1,405.
DT_DIE_COUNTS = (20, 47, 74, 100, 127, 154, 181, 207, 234, 261)

#: Yield of each of the ten core wafers.  Owner: 「코어 수율은 50~90퍼 사이」.
#: Usable dies per wafer are ``CORE_DIE_COUNT * pct // 100`` -> 212 229 250 267 289 306
#: 327 344 365 382, pooling to 2,971 available against 1,405 demanded.
CORE_YIELD_PCT = (50, 54, 59, 63, 68, 72, 77, 81, 86, 90)

#: One ``event_time`` per DT wafer, an hour apart.  ``dt_log.event_time`` is a TEXT column
#: and the existing SYN-* rows spell it ISO-8601 with a ``Z`` (e.g. ``2026-08-09T00:00:00Z``),
#: so that spelling is matched here.  ``transfer_event`` binds ``occurred_at`` to it.
EVENT_TIME_BASE = datetime(2026, 8, 22, 0, 0, tzinfo=timezone.utc)

CHUNK = 1000


def _job_id(slot: int) -> str:
    return f"{JOB_PREFIX}{slot:02d}"


def _core_wafer_id(slot: int) -> str:
    return f"{CORE_WAFER_PREFIX}{slot:02d}"


def _cell_key(job: str, x: int, y: int) -> str:
    """``dt_cell_key`` exactly as the existing 34,939 rows spell it.

    Verified read-only against 20,000 live rows: every one satisfies
    ``dt_cell_key == f"{dt_job}_{int(dt_x)}_{int(dt_y)}"`` (0 mismatches), and
    ``business_key_val == dt_cell_key`` across the whole table (0 mismatches).
    The coordinates are integers with no ``.0``, which is why ``int()`` is applied.
    """
    return f"{job}_{int(x)}_{int(y)}"


def _read_floor(db, product: str, type_: str, expected: int):
    """Read one declared die set out of ``valid_die_ref``.  Coordinates are never invented."""
    from database import models

    model = models.DYNAMIC_TABLES.get(VALID_TABLE)
    if model is None:
        raise SystemExit(f"REFUSED: {VALID_TABLE} is not declared.")
    rows = db.query(model.x, model.y).filter(
        model.product == product, model.type == type_).all()
    cells = sorted({(int(float(x)), int(float(y)))
                    for x, y in rows if x is not None and y is not None})
    if len(cells) != expected:
        raise SystemExit(
            f"REFUSED: {product}/{type_} holds {len(cells)} dies, expected {expected}. "
            "The declared yields and DT die counts are stated against that floor, so a "
            "changed floor changes what this fixture means -- re-decide, do not re-run."
        )
    return cells


def _dt_slots(dt_cells):
    """DT slots in 「우상부터 지그재그」 order -- top-right first, zigzag.

    Uses the repository's own walk.  See the module docstring for why
    ``top_is_min_y=True, left_to_right=False`` is that order for the ``CORE_DT`` map.
    """
    import map_alignment

    walk = map_alignment.serpentine_index(
        dt_cells, top_is_min_y=True, left_to_right=False)
    ordered = [walk[i] for i in range(1, len(walk) + 1)]
    if len(ordered) != len(dt_cells):
        raise SystemExit("REFUSED: serpentine walk did not number every DT die.")
    return ordered


def build_plans(core_cells, dt_cells):
    """Pure planning -- no database is touched here."""
    rng = random.Random(SEED)

    # One yielded subset per core wafer.  Every core wafer shares the same 425-die
    # floor geometry; the yield decides WHICH of those dies can be transferred.
    pool = []
    yields = []
    for slot, pct in enumerate(CORE_YIELD_PCT, start=1):
        usable = CORE_DIE_COUNT * pct // 100
        wafer_id = _core_wafer_id(slot)
        drawn = rng.sample(core_cells, usable)
        yields.append({"core_wafer_id": wafer_id, "yield_pct": pct, "dies": usable})
        pool.extend((wafer_id, cx, cy) for cx, cy in drawn)

    demand = sum(DT_DIE_COUNTS)
    if demand > len(pool):
        raise SystemExit(
            f"REFUSED: DT wafers demand {demand} dies but the pooled core yield is "
            f"{len(pool)}.  A die transfers once, so the pool cannot be re-drawn."
        )

    # Pool ALL ten core wafers together and shuffle once, so each DT wafer is fed by
    # several core wafers -- the 「코어 여러장 -> DT 1장」 shape this fixture is for.
    rng.shuffle(pool)

    slots = _dt_slots(dt_cells)
    plans = []
    taken = 0
    for slot, count in enumerate(DT_DIE_COUNTS, start=1):
        if count > len(slots):
            raise SystemExit(
                f"REFUSED: DT wafer {slot} wants {count} dies but the DT map has "
                f"only {len(slots)} slots."
            )
        job = _job_id(slot)
        event_time = (EVENT_TIME_BASE + timedelta(hours=slot - 1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        drawn = pool[taken:taken + count]
        taken += count

        rows = []
        for (wafer_id, cx, cy), (bx, by) in zip(drawn, slots[:count]):
            rows.append({
                # DT side -- where the die landed.  `dt_x`/`dt_y` carry the same
                # coordinate as `b_wx`/`b_wy`: they are the pair the existing rows fill,
                # and `dt_cell_key` is built out of them.
                "dt_job": job,
                "dt_job_id": job,
                "b_wx": bx,
                "b_wy": by,
                "dt_x": bx,
                "dt_y": by,
                "dt_cell_key": _cell_key(job, bx, by),
                # Core side -- where the die came from.
                "core_wafer_id": wafer_id,
                "c_wx": cx,
                "c_wy": cy,
                # Shared.
                "event_time": event_time,
                "product": PRODUCT,
            })

        contributors = {row["core_wafer_id"] for row in rows}
        if len(contributors) < 2:
            raise SystemExit(
                f"REFUSED: DT wafer {job} drew from {len(contributors)} core wafer(s). "
                "This fixture exists to carry 「many cores -> one DT」."
            )
        plans.append({
            "job": job,
            "dies": count,
            "event_time": event_time,
            "core_wafers": len(contributors),
            "rows": rows,
        })

    keys = [row["dt_cell_key"] for plan in plans for row in plan["rows"]]
    if len(set(keys)) != len(keys):
        raise SystemExit("REFUSED: dt_cell_key is not unique across the planned rows.")
    return plans, yields, len(pool)


def _verify_unowned(db, plans):
    """Refuse if anything already wears this fixture's job names but is not ours."""
    from database import models

    model = models.DYNAMIC_TABLES.get(DT_TABLE)
    if model is None:
        raise SystemExit(f"REFUSED: {DT_TABLE} is not declared.")
    expected = {plan["job"] for plan in plans}
    for column in (model.dt_job, model.dt_job_id):
        found = {str(row[0]) for row in
                 db.query(column).filter(column.like(JOB_PREFIX + "%")).distinct().all()
                 if row[0] is not None}
        stray = sorted(found - expected)
        if stray:
            raise SystemExit(
                f"REFUSED: unowned rows already use this prefix: {stray[:5]}")


def _write(db, rows):
    from database import crud, schemas

    changed = 0
    for start in range(0, len(rows), CHUNK):
        part = rows[start:start + CHUNK]
        batch = schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(
                updates=row,
                source_name=SOURCE_NAME,
                updated_by=UPDATED_BY,
                # The business key IS `dt_cell_key`.  Supplying it is what makes a
                # second run resolve onto the same rows instead of inserting new ones.
                business_key_val=row["dt_cell_key"],
            )
            for row in part
        ])
        _, cells, _, _ = crud.apply_batch_updates(db, DT_TABLE, batch)
        changed += len(cells or ())
    return changed


def main():
    parser = argparse.ArgumentParser(
        description="Seed synthetic die-transfer rows into dt_log (adds, never deletes).")
    parser.add_argument("--apply", action="store_true",
                        help="write; default is a dry run that touches nothing")
    parser.add_argument("--show", action="store_true",
                        help="print per-DT-wafer and per-core-wafer detail")
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
        core_cells = _read_floor(db, *CORE_REF, expected=CORE_DIE_COUNT)
        dt_cells = _read_floor(db, *DT_REF, expected=DT_SLOT_COUNT)
        plans, yields, pool_size = build_plans(core_cells, dt_cells)
        _verify_unowned(db, plans)
        total = sum(len(plan["rows"]) for plan in plans)
        changed = 0
        if args.apply:
            for plan in plans:
                changed += _write(db, plan["rows"])
    finally:
        db.close()

    print("core wafers            : %d  (pooled yield %d dies)" % (len(yields), pool_size))
    print("DT wafers              : %d" % len(plans))
    print("dt_log rows planned    : %d" % total)
    first = plans[0]["rows"][:5]
    print("first 5 slots of %-10s: %s"
          % (plans[0]["job"], [(r["b_wx"], r["b_wy"]) for r in first]))
    if args.show:
        for plan in plans:
            print("  %-14s dies=%3d  fed by %2d core wafers  event_time=%s"
                  % (plan["job"], plan["dies"], plan["core_wafers"], plan["event_time"]))
        for item in yields:
            print("  %-20s yield=%2d%%  usable=%3d/%d"
                  % (item["core_wafer_id"], item["yield_pct"], item["dies"],
                     CORE_DIE_COUNT))
    if args.apply:
        print("cells changed          : %d" % changed)
        print("WROTE synthetic die-transfer rows. Existing rows were not deleted.")
    else:
        print("DRY RUN, nothing written.")


if __name__ == "__main__":
    main()
