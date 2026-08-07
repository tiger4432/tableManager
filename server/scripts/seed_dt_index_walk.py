"""Seed SYNTHETIC dt_index walks into ``dt_map`` so the index axis can be exercised.

=============================================================================
EVERYTHING THIS SCRIPT WRITES IS SYNTHETIC AND AUTHORED HERE.
None of it is a measurement of production data and none of it may be quoted as
one. The mark travels with the data: every row this script writes carries a
``dt_job`` beginning with ``SYN-IDX-``, and no other row on this box does.
This repo has a recorded incident of a fixture number being read later as a
production measurement, which is why the mark is in the KEY and not a comment.
=============================================================================

Why this exists
---------------
`map_alignment`'s index axis was built and shipped with no input: ``dt_index``
exists on no table, in no CSV, and in no file of this repo (measured 2026-08-05).
So the axis had never been run against data that obeys its premise, and the one
thing nobody could see was whether it names the right frame. This plants data
that obeys the premise under a KNOWN frame, so the answer is known before the
scorer is asked.

THE RULE THIS PLANTS (stated by the product owner, and it is the design)
-----------------------------------------------------------------------
One pick order, read on two different coordinate systems:

  * The machine picks dies off the CORE wafer grouped by BIN - every bin-1 die
    in serpentine order, then every bin-2 die, and so on.
  * The k-th pick is placed in the k-th DT slot, and the DT slots run a DENSE
    serpentine over the DT destination.
  * ``dt_index`` = k. One column, two readings.

That makes the two walks structurally different, which is the whole point:

  * ``dt_x``/``dt_y`` by ``dt_index``  -> a dense unbroken serpentine.
  * ``core_x``/``core_y`` by ``dt_index`` -> maximal serpentine RUNS whose
    boundaries are the bin boundaries, and SPARSE, because each bin's pass
    skips the other bins' dies.

🔴 THE INDEX AXIS IS A DT-WALK RULE. "Index 1 is the top-left" is true of the DT
   map and FALSE of the core wafer: the first pick is the top-left of the BIN-1
   SET, and bin 1's extent is not the wafer's extent. Measured on this fixture,
   the same column scores the true frame 88/88 on the DT walk and 4/88 on the
   core walk. The core-side origin is a different mechanism entirely (correlate
   the picked pattern's gaps against the defect map); it is not in this file and
   this seed does not pretend to serve it.

What is simplified, said out loud
---------------------------------
The DT destination and the core wafer are given the SAME footprint here (the
``PRD-A/DT13`` floor, 88 dies). A real DT tape is a different shape. The
simplification is forced rather than lazy: ``make_frame_transform`` refuses when
grid dimensions differ, so a demo that compares against this floor has to share
its grid. Nothing in the walk logic depends on the two footprints matching.

Safety
------
Additive only. No DDL, no DROP, no DELETE. Writes go through
``crud.apply_batch_updates`` with ``source_name='custom_script'`` - the lowest
rank in the layering order - so an operator edit made later always wins.

``dt_map`` declares itself "[TRACE FIXTURE -- DERIVED, do not write by hand]"
because a hand-written row disagrees with the next chain replay. These rows do
not: the replay derives ``dt_map`` from ``dt_log`` rows, keyed by ``dt_job``, and
NO ``dt_log`` row carries a ``SYN-IDX-`` job. The script VERIFIES that before
writing (``verify_no_replay_collision``) rather than asserting it, and refuses if
it is ever untrue.

Idempotent: every row is addressed by its composite business key, so a second
run changes nothing and says so.

Usage
-----
    python server/scripts/seed_dt_index_walk.py             # dry run, default
    python server/scripts/seed_dt_index_walk.py --apply     # write
    python server/scripts/seed_dt_index_walk.py --show      # print the walks
"""

import argparse
import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import seed_valid_die_ref_floor as floor          # noqa: E402  (the die field + grid)

#: 🔴 THE SCORER READS CELLS FROM THE RULE'S `source_table`, NOT FROM `map_table`.
#: `map_table` supplies only the map-key column names and the meta namespace
#: (`alignment_view` -> `src_table = rule["source_table"]`). Seeding `dt_map` and
#: expecting the aligner to see it produces `sources.map_count = 0` and a
#: `not_scorable` screen with nothing wrong in it - measured here 2026-08-05
#: before this line was written. So the cells go to `dt_log`.
CELL_TABLE = "dt_log"
#: Kept as a secondary write so the map is also browsable under `dt_map`, which is
#: the table an operator picks on screen. Not what the scorer reads.
BROWSE_TABLE = "dt_map"
META_TABLE = "wafer_map_metadata"
#: The meta namespace follows `map_table`, i.e. what the operator picks on screen.
META_TARGET = "dt_map"

#: The alignment screen lists DECISION UNITS, and it reads them from the rule's
#: derived table - not from the map table. A seeded map with no unit row is a map
#: nobody can navigate to: the cells exist, the screen has no row to click, and the
#: seed looks broken when it is merely unreachable. So the unit is part of the seed.
#: `dt_job_lot_slot_attribution` is the rule whose decision_key (`dt_job`) IS
#: `dt_map`'s map key, which is what makes one row per job the right shape here.
UNIT_TABLE = "dt_job_attribution"
UNIT_RULE = "dt_job_lot_slot_attribution"

#: The mark, and it is in the KEY. Grep this prefix to find every synthetic row.
JOB_PREFIX = "SYN-IDX-"

REFERENCE = {"table": "valid_die_ref", "product": floor.PRODUCT, "type": floor.TYPE}

SOURCE_NAME = "custom_script"
UPDATED_BY = "seed_dt_index_walk"
CHUNK = 1000


def grid_meta():
    """The floor's own grid. Copied, never guessed - a source map whose spec differs
    from the reference cannot be compared to it at all."""
    return dict(floor.GRID_META)


# ---------------------------------------------------------------------------
# The jobs. Declared in one place so the expected answer is readable next to the
# thing that produces it.
# ---------------------------------------------------------------------------
#   dt_frame   : the frame the DT coordinates were RECORDED in  (the right answer)
#   core_frame : the frame the CORE coordinates were recorded in
#   bins       : how many bins the pick order is grouped into
#   coverage   : fraction of the floor this job picked (1.0 = the whole map)
#   ref_shift  : number of dies by which the numbering's reference differs from
#                the floor the scorer will use (0 = identical)
JOBS = [
    # The good case. Identity frame, whole map, one bin: a dense serpentine and
    # nothing else. This is the unit that must reach 88/88.
    {"name": "FULL-R0", "dt_frame": "rot0_front", "core_frame": "rot0_front",
     "bins": 1, "coverage": 1.0, "ref_shift": 0,
     "why": "whole map, identity frame - the DT walk's clean case"},
    # A non-identity frame. A fixture that only plants identity proves nothing
    # about the other seven candidates.
    {"name": "FULL-R90", "dt_frame": "rot90_front", "core_frame": "rot180_back",
     "bins": 3, "coverage": 1.0, "ref_shift": 0,
     "why": "whole map, ROTATED - the DT answer must not be the identity"},
    # The population this feature exists to serve: most indices absent, and gaps
    # inside rows (rule 3 of the serpentine: a hole consumes no index).
    # 🔴 [2026-08-07] THIS BLOCK USED TO SAY dt_frame IS FRONT ON EVERY JOB ON PURPOSE,
    #    because `alignment.sides` was declared ["front"]. That declaration has been
    #    WITHDRAWN and the reason it existed was a misreading:
    #
    #    IN THE ALIGNER, `back` MEANS **MIRROR**, NOT A PHYSICAL WAFER BACK SIDE.
    #    It is the `x -> -x` half of the candidate space, and the equipment fact it
    #    expresses is "this tool numbers from the TOP-RIGHT" - the serpentine's start
    #    corner (`serpentine_index` fixes the walk as first row left-to-right, so a
    #    top-right walk is its mirror). Such equipment exists (product owner,
    #    2026-08-07), so narrowing to front removed REAL answers from the search, and a
    #    unit whose tool numbers from the right came out as "no winner" - or, on the
    #    group-minimisation axis, as a confident WRONG frame.
    #
    #    ⚠️ THE MAP EDITOR IS A DIFFERENT DOMAIN. A genuine physical back side exists
    #    there. The two use the same word for different facts, and this simplification
    #    is scoped to the aligner deliberately (product owner: 구현 단순화 위함).
    #
    #    MIRROR-R0 below is the demonstration that the mirror half is reachable. The
    #    minimisation axis ties 2-way on the mirror pair by construction - a flip is
    #    x -> -x and a group boundary is a y event, so no y-based count can see it - and
    #    the bin fingerprint is what separates them (measured: truth 88/88, mirror 67/88).
    {"name": "PART-R270", "dt_frame": "rot270_front", "core_frame": "rot90_front",
     "bins": 4, "coverage": 0.38, "ref_shift": 0,
     "why": "PARTIAL map with interior gaps - the normal case, not the happy one"},
    # The numbering was assigned against a die set that is CLOSE to, but not the
    # same as, the floor the operator will score against. The honest answer is a
    # high ratio, not a failure, and the screen has to be able to tell them apart.
    {"name": "NEAR-R180", "dt_frame": "rot180_front", "core_frame": "rot0_back",
     "bins": 2, "coverage": 1.0, "ref_shift": 3,
     "why": "reference is CLOSE but not identical - expect high, not perfect"},
    # The equipment that numbers from the TOP-RIGHT. Its true dt_frame is a MIRROR one,
    # so it is the unit that goes missing the moment `alignment.sides` narrows to front -
    # which is exactly what happened until 2026-08-07. Nothing else in this list can fail
    # that way, because everything else is front.
    {"name": "MIRROR-R0", "dt_frame": "rot0_back", "core_frame": "rot0_front",
     "bins": 1, "coverage": 1.0, "ref_shift": 0,
     "why": "top-right numbering - the mirror half of the search space, reachable at all"},
    # ══ The CORE axis, added 2026-08-06 ═════════════════════════════════════════════
    # 🔴 THE FOUR JOBS ABOVE WERE DESIGNED FRONT-COMPLETE FOR THE **DT** AXIS AND ARE
    #    NOT FRONT-COMPLETE FOR THE **CORE** AXIS. `core_frame` is a BACK frame on two of
    #    them (FULL-R90 -> rot180_back, NEAR-R180 -> rot0_back). `alignment.sides` is
    #    declared ["front"] on this box (`server/config/map_overlay_config.json`), so on
    #    those two the true core frame is not in the search space at all - and because
    #    `index_group_count`'s minimum is held by the truth AND ITS FRONT/BACK MIRROR,
    #    removing the truth leaves the mirror alone at the minimum. The scorer then
    #    returns a UNIQUE, CONFIDENT, WRONG core frame instead of "no winner". That is a
    #    gap in the fixture, not a defect in the scorer, and these two jobs close it.
    #
    #    Between them the four jobs' `core_frame` values now cover ALL FOUR FRONT
    #    rotations - rot0_front (FULL-R0), rot90_front (PART-R270), rot180_front and
    #    rot270_front (here) - which is the whole declared search space. Before this,
    #    truth across every run was only ever {rot0_front, rot0_back, rot90_front,
    #    rot180_back}: 4 of the 8 candidates, and a systematic bias against the 270 pair
    #    would have left the headline count fully green (QA-1 F6).
    {"name": "CORE-R180", "dt_frame": "rot0_front", "core_frame": "rot180_front",
     "bins": 3, "coverage": 1.0, "ref_shift": 0,
     "why": "CORE axis: truth is rot180_front - a front core frame the DT jobs never plant"},
    {"name": "CORE-R270", "dt_frame": "rot90_front", "core_frame": "rot270_front",
     "bins": 2, "coverage": 0.55, "ref_shift": 0,
     "why": "CORE axis: truth is rot270_front, PARTIAL - the 270 pair was never the answer"},
]


def job_id(name):
    return JOB_PREFIX + name


# ---------------------------------------------------------------------------
# Planting. Pure: no DB, no module state.
# ---------------------------------------------------------------------------

def _express(cells, ref_meta, frame):
    """`cells` (reference coords) as equipment in `frame` would have RECORDED them.

    Goes through the SAME primitive the scorer uses, in the opposite direction, so
    this is a round trip rather than a second implementation of the rotation math.
    """
    import map_overlay
    from dt_map_derivation import source_meta_for_frame
    src_meta = source_meta_for_frame(ref_meta, frame)
    if src_meta is None:
        raise SystemExit("REFUSED: '%s' is not a candidate frame." % frame)
    fwd = map_overlay.make_frame_transform(ref_meta, src_meta)
    return [fwd(x, y) for (x, y) in cells]


def _bin_of(cell, nbins):
    """Deterministic bin label. Position-derived, so a re-run plants the same map."""
    x, y = cell
    return "B%d" % (((x * 7 + y * 13) % nbins) + 1)


def plan_job(job, field, ref_meta):
    """One job -> the rows it writes. Returns (rows, facts).

    The pick order is built ONCE and read twice, which is the rule itself: `k` is
    both the k-th pick off the core wafer and the k-th slot on the DT tape.
    """
    import map_alignment as ma

    top_is_min_y = not bool(ref_meta.get("grid_y_invert"))

    # The numbering's own reference. `ref_shift` dies are removed from it, so the
    # ranks it produces are the ranks of a slightly DIFFERENT map - which is what
    # "the operator's floor is close but not identical" means in the data.
    numbering_field = list(field)
    if job["ref_shift"]:
        numbering_field = [c for i, c in enumerate(field)
                           if i % max(2, len(field) // job["ref_shift"]) != 0
                           or i >= job["ref_shift"] * (len(field) // job["ref_shift"])]
        numbering_field = numbering_field[:len(field) - job["ref_shift"]]

    core_rank = {pos: k for k, pos in
                 ma.serpentine_index(numbering_field, top_is_min_y=top_is_min_y).items()}
    dt_slots = ma.serpentine_index(numbering_field, top_is_min_y=top_is_min_y)

    # Which dies this job actually picked. Deterministic and spread across rows so a
    # partial map gets holes INSIDE rows, not just missing rows.
    picked = [c for i, c in enumerate(numbering_field)
              if (i * 37) % 100 < int(job["coverage"] * 100)]
    if not picked:
        raise SystemExit("REFUSED: job %r picked no dies." % job["name"])

    # THE RULE: order by (bin, serpentine rank within the bin). That is the pick
    # order, and its index is the DT slot number.
    order = sorted(picked, key=lambda c: (_bin_of(c, job["bins"]), core_rank[c]))

    core_cells = _express(order, ref_meta, job["core_frame"])
    dt_cells = _express([dt_slots[k + 1] for k in range(len(order))],
                        ref_meta, job["dt_frame"])

    rows = []
    for i, cell in enumerate(order):
        rows.append({"dt_job": job_id(job["name"]),
                     "dt_eqp": "SYN-EQP", "product": "SYNTHETIC",
                     "dt_x": dt_cells[i][0], "dt_y": dt_cells[i][1],
                     "dt_index": i + 1,
                     "core_x": core_cells[i][0], "core_y": core_cells[i][1],
                     "c_bn": _bin_of(cell, job["bins"])})
    sizes = {}
    for c in order:
        b = _bin_of(c, job["bins"])
        sizes[b] = sizes.get(b, 0) + 1
    facts = {"dies": len(rows), "of_floor": len(field), "bins": len(sizes),
             "bin_sizes": [sizes[b] for b in sorted(sizes)],
             "dt_frame": job["dt_frame"], "core_frame": job["core_frame"],
             "numbering_ref_dies": len(numbering_field)}
    return rows, facts


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def verify_prefix_is_ours(db):
    """REFUSE if a NON-synthetic job already uses this prefix.

    The mark is only a mark while it is exclusive. If a real job ever begins with
    `SYN-IDX-`, this script would overwrite production-shaped rows and the prefix
    would stop meaning "authored here" - the exact failure the header promises
    against. Checked, not asserted.
    """
    from database import models
    seen = {}
    for t in (CELL_TABLE, BROWSE_TABLE):
        model = models.DYNAMIC_TABLES.get(t)
        if model is None:
            continue
        rows = (db.query(model.dt_job)
                .filter(model.dt_job.like(JOB_PREFIX + "%")).distinct().all())
        seen[t] = sorted(r[0] for r in rows)
    ours = {job_id(j["name"]) for j in JOBS}
    for t, jobs in seen.items():
        stray = [j for j in jobs if j not in ours]
        if stray:
            raise SystemExit(
                "REFUSED: '%s' already carries %r under the '%s' prefix, which this "
                "script did not author. The mark has to stay exclusive to mean "
                "anything." % (t, stray[:5], JOB_PREFIX))
    return seen


def _batch(items, business_keys=None):
    """`items` -> one layering-aware batch.

    `business_keys`: optional per-item key. 🔴 It is a field ON the item, NOT a
    column inside `updates` - putting it in `updates` writes a column nobody reads
    and leaves the upsert unable to find the existing row, so every re-run INSERTs
    and the second run dies on the unique index (measured 2026-08-05). Tables whose
    identity is a single `business_key` with no `composite_key_source` need this;
    `crud` can compose the key only from `composite_key_source`.
    """
    from database import schemas
    keys = list(business_keys or [])
    return schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(
            updates=u, source_name=SOURCE_NAME, updated_by=UPDATED_BY,
            business_key_val=(keys[i] if i < len(keys) else None))
            for i, u in enumerate(items)])


def seed(db, plans, ref_meta, apply_changes):
    from database import crud, models

    for t in (CELL_TABLE, BROWSE_TABLE, META_TABLE, UNIT_TABLE):
        if models.DYNAMIC_TABLES.get(t) is None:
            raise SystemExit("REFUSED: '%s' is not a declared table on this box." % t)
    model = models.DYNAMIC_TABLES[CELL_TABLE]
    if getattr(model, "dt_index", None) is None:
        raise SystemExit(
            "REFUSED: '%s' has no 'dt_index' attribute. Declare it in "
            "table_config.json and confirm the physical column exists "
            "(information_schema) before seeding - a silent ALTER miss would write "
            "every row with the number dropped." % CELL_TABLE)

    verify_prefix_is_ours(db)

    report = {"jobs": [], "cells_changed": 0, "meta_changed": 0,
              "unit_changed": 0}
    for job, rows, facts in plans:
        mid = job_id(job["name"])
        before = db.query(model.row_id).filter(model.dt_job == mid).count()
        entry = dict(facts, map_id=mid, rows_before=before, why=job["why"])
        if apply_changes:
            # The cells the SCORER reads, then the same cells where an operator
            # BROWSES them. Two tables, one payload, because the two questions are
            # answered by two different tables on this route (§CELL_TABLE).
            for t in (CELL_TABLE, BROWSE_TABLE):
                cols = set((crud.TABLE_CONFIG.get(t) or {}).get("column_types") or {})
                # Project onto what each table actually declares. `dt_log` carries
                # dt_eqp/product and `dt_map` does not; sending a column a table does
                # not declare is a write that fails late instead of a row that fits.
                for start in range(0, len(rows), CHUNK):
                    batch = [{k: v for k, v in r.items() if k in cols}
                             for r in rows[start:start + CHUNK]]
                    _, changed, _, _ = crud.apply_batch_updates(db, t, _batch(batch))
                    report["cells_changed"] += len(changed or ())
            _, mchanged, _, _ = crud.apply_batch_updates(db, META_TABLE, _batch([{
                "target_table": META_TARGET, "map_id": mid,
                "grid_metadata": json.dumps(ref_meta, ensure_ascii=False)}]))
            report["meta_changed"] += len(mchanged or ())
            # The unit row. `dt_lot_confirmed`/`dt_slot_confirmed` carry the synthetic
            # mark too, so the mark is visible on the screen's own list and not only
            # in the key - somebody reading the unit list must see what it is.
            # 🔴 `business_key_val` is supplied EXPLICITLY here. `crud` composes it
            #    only from `composite_key_source`, and `dt_job_attribution` declares
            #    none (its identity is the single `business_key`, `dt_job`). Without
            #    it every re-run is an INSERT and the second run dies on
            #    `uq_vjoin_dt_job_attribution_dt_job` - measured here 2026-08-05.
            #    Idempotency is a property of the key, not of the intention.
            _, uchanged, _, _ = crud.apply_batch_updates(db, UNIT_TABLE, _batch([{
                "dt_job": mid,
                "dt_lot_confirmed": "SYNTHETIC", "dt_slot_confirmed": "SYNTHETIC",
                "cell_count": len(rows)}], business_keys=[mid]))
            report["unit_changed"] += len(uchanged or ())
            entry["rows_after"] = (db.query(model.row_id)
                                   .filter(model.dt_job == mid).count())
        report["jobs"].append(entry)
    return report


def main():
    ap = argparse.ArgumentParser(
        description="Seed SYNTHETIC dt_index walks into dt_map. Additive only: no "
                    "table is altered and no row is ever deleted.")
    ap.add_argument("--apply", action="store_true",
                    help="write; without it the script only reports what it would do")
    ap.add_argument("--show", action="store_true", help="print each walk's first steps")
    args = ap.parse_args()

    ref_meta = grid_meta()
    field = floor.field_dies()
    plans = []
    for job in JOBS:
        rows, facts = plan_job(job, field, ref_meta)
        plans.append((job, rows, facts))

    print("SYNTHETIC SEED - every row written here carries dt_job '%s*'." % JOB_PREFIX)
    print("reference    : %s %s/%s (%d dies), grid %dx%d"
          % (REFERENCE["table"], REFERENCE["product"], REFERENCE["type"], len(field),
             ref_meta["grid_cols"], ref_meta["grid_rows"]))
    print("cells -> %s (what the scorer reads) and %s (where you browse them)"
          % (CELL_TABLE, BROWSE_TABLE))
    print("meta  -> %s under target_table=%r ; units -> %s (rule %s)"
          % (META_TABLE, META_TARGET, UNIT_TABLE, UNIT_RULE))
    for job, rows, facts in plans:
        print("  %-22s dies %3d/%-3d bins %d %-14s dt_frame %-13s core_frame %-13s"
              % (job_id(job["name"]), facts["dies"], facts["of_floor"], facts["bins"],
                 str(facts["bin_sizes"]), facts["dt_frame"], facts["core_frame"]))
        print("      %s" % job["why"])
        if args.show:
            for r in rows[:6]:
                print("        k=%-3d dt=(%2d,%2d) core=(%2d,%2d) bin=%s"
                      % (r["dt_index"], r["dt_x"], r["dt_y"],
                         r["core_x"], r["core_y"], r["c_bn"]))

    from database.database import SessionLocal
    from database import crud, models
    models.init_dynamic_models(crud.TABLE_CONFIG)
    db = SessionLocal()
    try:
        report = seed(db, plans, ref_meta, args.apply)
    finally:
        db.close()

    print()
    for e in report["jobs"]:
        print("  %-22s rows before %-4d%s"
              % (e["map_id"], e["rows_before"],
                 ("  after %d" % e["rows_after"]) if "rows_after" in e else ""))
    if args.apply:
        print("cells changed : %d" % report["cells_changed"])
        print("meta changed  : %d" % report["meta_changed"])
        print("unit changed  : %d  (rule %r units in %s)"
              % (report["unit_changed"], UNIT_RULE, UNIT_TABLE))
        print("WROTE %s + %s cells, %s rows and %s units. "
              "All rows are SYNTHETIC (dt_job '%s*')."
              % (CELL_TABLE, BROWSE_TABLE, META_TABLE, UNIT_TABLE, JOB_PREFIX))
    else:
        print("DRY RUN, nothing written. Re-run with --apply to write.")


if __name__ == "__main__":
    main()
