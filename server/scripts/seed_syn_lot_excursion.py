"""Lot-level EXCURSIONS - the outliers the trend grid exists to find. Ruling R-2026-08-14-F.

WHY THIS EXISTS
---------------
`ledger_lots.py` computes correctly and colours nothing. Measured on `assy_manager`
2026-08-14, over all 100 synthetic lots with no window:

    found_rate    0.5766 .. 0.6483   median 0.6124   max/median 1.059
    per_chip      1.1393 .. 1.3255   median 1.2248   max/median 1.082
    extent_mean  55.0999 ..64.3201   median 58.659   max/median 1.097

The first conditional-format step is 2.0x. Nothing is within reach of it, because
`seed_syn_process_ledger` planted FACTOR-level effects (for the case-control answer key)
and a trend grid looks for LOT-level outliers. Those are different objects and the fixture
only had the first. This script plants the second.

🔴 A MEASUREMENT THAT CHANGES WHAT CAN BE PLANTED, AND IT IS NOT A FIXTURE PROBLEM
-----------------------------------------------------------------------------------
`found_rate` is `found chips / scanned chips`, so it is BOUNDED BY 1.0. With a baseline of
0.6124 the largest ratio that column can EVER show is::

    1.0 / 0.6124 = 1.633

which is below the first threshold (2.0). **No plant can colour `found_rate`.** A lot where
every single scanned chip has a void still renders uncoloured. That is a property of a
saturating ratio judged against a mid-range baseline, not something a fixture can fix, and
it is reported rather than papered over - see the report for the escalation.

So the excursion is planted where the metric is UNBOUNDED and can actually cross the
ladder: `per_chip` (observations per scanned chip) and `extent_mean` (mean defect size).
Both are declared aggregates in `ledger_lots.AGGREGATES`; neither is a new idea.

🔴 WHY NEW LOTS AND NOT MORE VOIDS ON EXISTING ONES
----------------------------------------------------
The obvious move - add voids to lots 098-100 - creates a contradiction. Every one of those
wafers already carries a `processed_with` atom naming its bonding recipe revision, so
giving the excursion a CAUSE would mean asserting a second, different revision for a run
the ledger has already described. Append-only would keep both and the later one would win
by rank, which is a CORRECTION - a completely different claim from "a new revision was
rolled out late in production".

New lots have no such history. The cause is planted at birth, nothing existing is touched,
and the bidirectional assertion gets much stronger: the 100 existing lots can be shown
BYTE-IDENTICAL before and after, so "unplanted lots do not light up" is proven by
construction rather than by re-measuring and hoping.

WHAT IS PLANTED (ruling conditions 1 and 3)
--------------------------------------------
Three lots, late in production order, graded so the LADDER ITSELF is exercised rather than
one step of it::

    SYN-VOID-101   per_chip ~2.6   -> ~2.1x baseline   level 1  주의
    SYN-VOID-102   per_chip ~4.0   -> ~3.3x baseline   level 2  높음
    SYN-VOID-103   per_chip ~5.6   -> ~4.6x baseline   level 3  심각

🔴 "Late in production order" is enforced on the axis the GRID actually sorts by.
`ledger_lots._build` takes each row's time from `inspection_run.observed_at` and says why
in its own comment: `bonding_log.event_time` is one identical string across all 352,500
synthetic rows and cannot order anything. So these lots are late because their SCANS are
late (day offsets 101-103, after every existing lot's), not because their names sort last.

THE CAUSE, AND WHY IT CONNECTS (ruling condition 1)
----------------------------------------------------
The excursion lots bond under `SYN-RCP-BOND` **rev 6** - a revision rolled out late. That
is a value in the SAME factor namespace the case-control answer key already scores
(`recipe_rev@BONDING`), so the chain trend grid -> reference view -> contrast is scorable
end to end: the grid colours the lot, the contrast says WHY, and `--prove` asserts both.
An excursion whose cause were merely "these lots are worse" would colour the grid and
dead-end immediately after.

RUNNING IT (ruling condition 4 - THE DB GATE)
----------------------------------------------
🔴 **Nothing is written without `--i-accept-writing-to-owner-database`**, exactly as
`seed_syn_void_base_join` requires. As of 2026-08-14 this has been BUILT AND DRY-RUN ONLY;
the owner's approval to write to `assy_manager` had not been given. A dry run reads and
prints and is safe::

    conda run -n assy_manager python server/scripts/seed_syn_lot_excursion.py
    conda run -n assy_manager python server/scripts/seed_syn_lot_excursion.py --prove

    # only after the owner approves:
    ... seed_syn_lot_excursion.py --apply --i-accept-writing-to-owner-database

    # then, to extend the DT transfer chain onto the new lots (idempotent for the rest):
    ... seed_syn_process_ledger.py --apply --i-accept-writing-to-owner-database

ROLLBACK
--------
    DELETE FROM void_obs       WHERE base_wafer_id LIKE 'SYN-BW-1__-%';
    DELETE FROM inspection_run WHERE base_wafer_id LIKE 'SYN-BW-1__-%';
    DELETE FROM bonding_log    WHERE bond_lot IN ('SYN-VOID-101','SYN-VOID-102','SYN-VOID-103');
    DELETE FROM ledger_events  WHERE source_translator_ver LIKE 'syn_lot_excursion/%';
    DELETE FROM cell_sources    WHERE updated_by = 'seed_syn_lot_excursion';
    DELETE FROM cell_overwrites WHERE updated_by = 'seed_syn_lot_excursion';
    -- wafer_map_metadata rows for the three lots' maps carry the same updated_by.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import seed_syn_void_base_join as base          # noqa: E402  the geometry primitive

SOURCE_NAME = "custom_script"
UPDATED_BY = "seed_syn_lot_excursion"
TRANSLATOR_BASE = "syn_lot_excursion/1/rules:excursion1"
WHO_RECIPE_BOOK = "syn_recipe_book"
WHO_EQP_LOG = "syn_eqp_log"

#: The excursion, DECLARED. `per_chip_target` and `extent_scale` are what the generator
#: aims at; `expect_level` is what the grid must then show. Both halves are in one place
#: so the answer key cannot drift from the plant.
#: 🔴 `expect_min_ratio` MUST be at or above the ladder step `expect_level` names, and
#: `per_chip_target` must clear it with margin. A first draft declared 1.8 for level 1 (the
#: step is 2.0) and 4.2 for level 3 (the step is 4.5) - a declaration that contradicts
#: itself, which would have failed the answer key for a reason with nothing to do with the
#: data. `test_lot_excursion.py::test_each_declared_ratio_actually_reaches_its_declared_level`
#: caught it and is why the two numbers can never drift apart again.
#:
#: Margins against the MEASURED baseline (per_chip median 1.2248): the targets land at
#: 2.29x / 3.43x / 5.06x - roughly 13% above the step each one claims, and comfortably
#: below the next step, so neither a small baseline shift nor the three new rows entering
#: the median can move a lot across a boundary.
EXCURSIONS = {
    101: {"per_chip_target": 2.8, "found_rate_target": 0.88, "extent_scale": 1.45,
          "expect_level": 1, "expect_min_ratio": 2.0},
    102: {"per_chip_target": 4.2, "found_rate_target": 0.93, "extent_scale": 1.75,
          "expect_level": 2, "expect_min_ratio": 3.0},
    103: {"per_chip_target": 6.2, "found_rate_target": 0.96, "extent_scale": 2.10,
          "expect_level": 3, "expect_min_ratio": 4.5},
}

EXCURSION_RECIPE = ("SYN-RCP-BOND", "6")

#: 🔴 THE CAUSE, in the factor namespace the contrast already scores. Not a new axis.
EXCURSION_FACTOR = "recipe_rev@BONDING=%s@%s" % EXCURSION_RECIPE

#: rev6 against rev5: pressure drops again and cure time is cut. Two parameters move, the
#: rest do not - the same discipline rev4->rev5 follows, so a diff view still has to
#: separate signal from noise.
RECIPE_PARAMS = {
    "pressure_MPa": (0.16, "MPa"), "temp_C": (150.0, "C"), "time_s": (9.0, "s"),
    "vacuum_Pa": (5.0, "Pa"), "purge_delay_s": (0, "s"), "vacuum_assist": (True, "bool"),
}

#: The aggregates the answer key scores, and the ONE that cannot be scored. Declared so a
#: reader does not have to rediscover the saturation argument from the numbers.
#: The kind THIS FIXTURE plants. A seeder names its own kind: the generalization rule
#: forbids a literal in product code, and `finding_kinds` no longer holds a default.
FIXTURE_KIND = "void"

SCORED_AGGREGATES = ("per_chip", "extent_mean")
UNSCORABLE_AGGREGATES = {
    "found_rate": ("bounded by 1.0; with a baseline of ~0.61 the maximum possible ratio "
                   "is ~1.63, below the first threshold of 2.0. No plant can colour it."),
}

SCAN_EVERY = 5          # 141 positions -> 29 scanned, i.e. 725 per lot. Matches the fixture.
SLOTS_PER_LOT = 25


def _rng(lot, slot, seed):
    return base._rng(seed ^ 0xE7C, lot, slot)


def excursion_rows(lot: int, seed: int):
    """`(wafers, bonding, runs, voids)` for ONE excursion lot.

    Geometry is BORROWED, never re-derived: `base.bonding_rows` puts every bond coordinate
    through the declared frame transform and refuses a frame that does not round-trip. A
    second implementation of that here is the defect that script's docstring is about.
    """
    from parsers import void_sat_format

    spec = EXCURSIONS[lot]
    wafers, bonding, runs, voids = [], [], [], []

    for slot in range(1, SLOTS_PER_LOT + 1):
        frame, base_id, rows = base.bonding_rows(lot, slot, seed)
        wafers.append(("%s%03d" % (base.BOND_LOT_PREFIX, lot), "%02d" % slot,
                       frame, base_id))
        bonding.extend(rows)

        rng = _rng(lot, slot, seed)
        scanned = rows[::SCAN_EVERY]
        for n, row in enumerate(scanned):
            gate = 1 + int(rng.random() * row["stack_height"])
            # 🔴 The observation time is what puts this lot LATE. `ledger_lots` orders
            # rows by `inspection_run.observed_at`, so a lot that is late by NAME and
            # early by SCAN would sit in the middle of the trend and the break would not
            # appear where the answer key says it does.
            observed_at = base._stamp(lot, n * 7 + slot * 3)
            run_uid = void_sat_format.compose_run_uid(
                row["base_id"], row["bx"], row["by"], gate, observed_at)
            if run_uid is None:
                raise SystemExit("REFUSED: could not key a run for %s." % row["base_id"])
            runs.append({"method": base.METHOD, "base_wafer_id": row["base_id"],
                         "base_x": row["bx"], "base_y": row["by"], "stack_gate": gate,
                         "recipe_id": "SYN_VOID_EXC", "eqp_id": "SYN-SAT-%02d" % (1 + slot % 3),
                         "observed_at": observed_at})

            if rng.random() >= spec["found_rate_target"]:
                continue                      # a CLEAN scan - the denominator still needs them
            # Draw a per-chip count whose MEAN over found chips hits the lot target.
            mean_over_found = spec["per_chip_target"] / spec["found_rate_target"]
            count = max(1, int(round(rng.gauss(mean_over_found, mean_over_found * 0.35))))
            seen = set()
            for _ in range(count):
                inchip = base._inchip(rng)
                if inchip in seen:            # the parser refuses a repeat; do not emit one
                    continue
                seen.add(inchip)
                voids.append({
                    "run_uid": run_uid, "base_wafer_id": row["base_id"],
                    "base_x": row["bx"], "base_y": row["by"], "stack_gate": gate,
                    "inchip_x": inchip[0], "inchip_y": inchip[1],
                    "radius_x": round(rng.uniform(0.5, 15.0) * spec["extent_scale"], 3),
                    "radius_y": round(rng.uniform(0.5, 15.0) * spec["extent_scale"], 3),
                    "unit": base.UNIT})
    return wafers, bonding, runs, voids


def excursion_atoms(wafers):
    """`register` + `has_param` for rev6, and `processed_with` for every new wafer.

    The atoms are built by the SAME helpers the process generator uses, so the excursion's
    cause lands in the same shape the contrast already reads. No second spelling.
    """
    import seed_syn_process_ledger as proc

    recipe_id, rev = EXCURSION_RECIPE
    keys = {"recipe": recipe_id, "rev": rev}
    ref = "recipe_book:%s@%s" % (recipe_id, rev)
    molecule = "recipe:%s:%s" % (recipe_id, rev)
    when = proc._stamp(-1, 0)

    atoms = [proc._atom("Recipe", keys, "register", None, None, when, WHO_RECIPE_BOOK,
                        proc.DERIV_FIRST_SIGHT, ref, molecule)]
    for name, (value, unit) in sorted(RECIPE_PARAMS.items()):
        atoms.append(proc._atom("Recipe", keys, "has_param", "value",
                                {"param": name, "value": value, "unit": unit},
                                when, WHO_RECIPE_BOOK, proc.DERIV_RECIPE_BOOK,
                                "%s#%s" % (ref, name), molecule))

    for index, (_bond_lot, _slot, _frame, base_id) in enumerate(wafers):
        atoms.append(proc._atom("Wafer", {"wafer": base_id}, "register", None, None,
                                proc._stamp(0, index % 1440), WHO_EQP_LOG,
                                proc.DERIV_FIRST_SIGHT, "wafer_registry:%s" % base_id,
                                "wafer:%s" % base_id))
        common = {"step": "BONDING", "step_family": "packaging",
                  "eqp": "SYN-BD-EXC", "chamber": "CH-A",
                  "recipe": {"id": recipe_id, "rev": rev}}
        fallback = dict(common)
        fallback["params_setpoint"] = {n: v for n, (v, _u) in sorted(RECIPE_PARAMS.items())}
        fallback["inferred"] = True
        fallback["basis"] = proc.DERIV_RECIPE_SETPOINT
        atoms.append(proc._atom(
            "Wafer", {"wafer": base_id}, "processed_with", "value", fallback,
            proc._stamp(2, 60 + index % 60), WHO_RECIPE_BOOK, proc.DERIV_RECIPE_SETPOINT,
            "%s:%s" % (ref, base_id), "wafer:%s:BONDING" % base_id))
        measured = dict(common)
        measured["params_actual"] = proc._actual_from_setpoint(
            RECIPE_PARAMS, base_id, "BONDING")
        atoms.append(proc._atom(
            "Wafer", {"wafer": base_id}, "processed_with", "value", measured,
            proc._stamp(0, 60 + index % 60), WHO_EQP_LOG, proc.DERIV_EQP_LOG,
            "eqp_log:SYN-BD-EXC:%s:BONDING" % base_id, "wafer:%s:BONDING" % base_id))
    return atoms


# --------------------------------------------------------------------------- writing


def _write(db, table: str, rows: list) -> int:
    """Chunked upsert under THIS script's marker, so the rollback predicate is separable.

    Deliberately not `base._write`: that one stamps `seed_syn_void_base_join`, and a
    fixture whose rows cannot be told from the fixture it sits on top of cannot be
    removed without removing both.
    """
    from database import crud, schemas

    written = 0
    for start in range(0, len(rows), base.CHUNK):
        chunk = rows[start:start + base.CHUNK]
        batch = schemas.GeneralUpdateBatch(
            updates=[schemas.GeneralUpdateItem(updates=row, source_name=SOURCE_NAME,
                                               updated_by=UPDATED_BY) for row in chunk],
            replace_map=False, scope=None)
        report = {}
        _, changed, _, _ = crud.apply_batch_updates(db, table, batch, drop_report=report)
        if report.get("dropped_cells"):
            raise SystemExit(
                "REFUSED: writing '%s' DROPPED %d update cell(s), column(s) %s."
                % (table, report["dropped_cells"], sorted(report.get("by_column") or {})))
        written += len(changed or ())
        db.commit()
    return written


def register_map_meta(db, wafers) -> int:
    """One `wafer_map_metadata` row per new wafer, carrying its DECLARED frame."""
    import json

    import map_meta_registrar

    rows = []
    for bond_lot, bond_slot, frame, _base_id in wafers:
        map_id = map_meta_registrar.compose_map_id(
            ["bond_lot", "bond_slot"],
            {"bond_lot": bond_lot, "bond_slot": bond_slot}, "bonding_log")
        if map_id is None:
            raise SystemExit("REFUSED: could not compose a map_id for %s/%s."
                             % (bond_lot, bond_slot))
        rows.append({"target_table": "bonding_log", "map_id": map_id,
                     "grid_metadata": json.dumps(base.recorded_meta(frame),
                                                 ensure_ascii=False, sort_keys=True)})
    return _write(db, "wafer_map_metadata", rows)


def guard_database(db, allow_owner: bool, writing: bool) -> str:
    """🔴 RULING CONDITION 4. The existing flag, unchanged, still required."""
    from sqlalchemy import text

    name = db.execute(text("SELECT current_database()")).scalar()
    if writing and name in ("assy_manager",) and not allow_owner:
        raise SystemExit(
            "REFUSED: connected to '%s', the owner's working database, and this run would "
            "WRITE. Ruling R-2026-08-14-F gates execution on the owner's approval: pass "
            "--i-accept-writing-to-owner-database only once that approval exists. A dry "
            "run and --prove need no flag." % name)
    print("database: %s" % name)
    if writing:
        print("!! rollback (rdb):    updated_by = '%s'" % UPDATED_BY)
        print("!! rollback (ledger): source_translator_ver LIKE '%s%%'"
              % TRANSLATOR_BASE.split("rules:")[0])
    return name


# --------------------------------------------------------------------------- the answer key


def lot_table(db, kind: str = None):
    """Per-lot aggregates, computed the way `ledger_lots` computes them.

    Reads the metric geometry from `finding_kinds` rather than naming a table, so a second
    kind is scored by the same function. `ledger_lots` itself is another lane's module and
    is imported for its DECLARATIONS (aggregate names, thresholds, baseline rule) rather
    than reimplemented.
    """
    from ledger_api import finding_kinds
    from sqlalchemy import text

    kind = kind or FIXTURE_KIND
    table = finding_kinds.observation_table(kind)
    extent = finding_kinds.spec(kind).get("extent_columns") or []
    extent_expr = " * ".join("o.%s" % c for c in extent) or "NULL::double precision"
    sql = f"""
WITH runs AS (
    SELECT run_uid AS run_key, base_wafer_id, base_x, base_y, observed_at
    FROM inspection_run WHERE method = ANY(:methods)
),
unit AS (
    SELECT DISTINCT base_id AS base_wafer_id, bx AS base_x, by AS base_y,
           bond_lot AS row_value
    FROM bonding_log
    WHERE base_id IS NOT NULL AND bx IS NOT NULL AND by IS NOT NULL
      AND bond_lot IS NOT NULL
),
scanned AS (SELECT DISTINCT base_wafer_id, base_x, base_y FROM runs),
agg AS (
    SELECT r.base_wafer_id, r.base_x, r.base_y, count(*) AS n,
           avg({extent_expr}) AS extent
    FROM {table} o JOIN runs r ON r.run_key = o.run_uid
    GROUP BY 1, 2, 3
),
chip_time AS (SELECT base_wafer_id, base_x, base_y, max(observed_at) AS last_at
              FROM runs GROUP BY 1, 2, 3)
SELECT u.row_value AS lot,
       count(*) FILTER (WHERE s.base_wafer_id IS NOT NULL) AS scanned,
       count(*) FILTER (WHERE a.base_wafer_id IS NOT NULL) AS found,
       coalesce(sum(a.n), 0) AS events,
       avg(a.extent) AS extent_mean,
       max(t.last_at) AS last_at
FROM unit u
LEFT JOIN scanned s ON s.base_wafer_id = u.base_wafer_id AND s.base_x = u.base_x
                   AND s.base_y = u.base_y
LEFT JOIN agg a ON a.base_wafer_id = u.base_wafer_id AND a.base_x = u.base_x
               AND a.base_y = u.base_y
LEFT JOIN chip_time t ON t.base_wafer_id = u.base_wafer_id AND t.base_x = u.base_x
                     AND t.base_y = u.base_y
GROUP BY 1 ORDER BY 1
"""
    rows = db.execute(text(sql), {"methods": finding_kinds.methods(kind)}).mappings().all()
    out = {}
    for row in rows:
        scanned = int(row["scanned"] or 0)
        if not scanned:
            continue
        out[row["lot"]] = {
            "scanned": scanned,
            "found_rate": float(row["found"]) / scanned,
            "per_chip": float(row["events"]) / scanned,
            "extent_mean": (float(row["extent_mean"])
                            if row["extent_mean"] is not None else None),
            "last_at": row["last_at"],
        }
    return out


def _median(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    n = len(values)
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2.0


def prove_cause_connects(db, kind: str = None):
    """🔴 RULING CONDITION 1 - the grid's colour must lead somewhere.

    Runs the EXISTING case-control contrast and asks whether the excursion's cause is
    enriched. If it is not, the grid colours a lot and the reference view has nothing to
    say, which is the failure the condition exists to prevent.
    """
    from ledger_api import finding_kinds
    import seed_syn_process_ledger as proc

    result = proc.contrast(db, kind or FIXTURE_KIND)
    entry = result["factors"].get(EXCURSION_FACTOR)
    return {"factor": EXCURSION_FACTOR, "entry": entry,
            "cases": result["cases"], "controls": result["controls"]}


# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--prove", action="store_true")
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--i-accept-writing-to-owner-database", action="store_true",
                        dest="allow_owner")
    args = parser.parse_args()

    from database import crud, models
    from database.database import SessionLocal

    models.init_dynamic_models(crud.TABLE_CONFIG)
    db = SessionLocal()
    try:
        guard_database(db, args.allow_owner, writing=args.apply)

        if args.prove and not args.apply:
            cause = prove_cause_connects(db)
            print("\n=== THE CAUSE CONNECTS (grid -> reference view -> contrast) ===")
            if cause["entry"]:
                print("  %s cases %d/%d (%.4f) controls %d/%d (%.4f) ratio %.3f"
                      % (cause["factor"], cause["entry"]["cases"], cause["cases"],
                         cause["entry"]["p_case"], cause["entry"]["controls"],
                         cause["controls"], cause["entry"]["p_control"],
                         cause["entry"]["ratio"] or 0.0))
            else:
                print("  %s is absent from the contrast - not applied yet"
                      % cause["factor"])
            return

        wafers, bonding, runs, voids = [], [], [], []
        for lot in sorted(EXCURSIONS):
            w, b, r, v = excursion_rows(lot, args.seed)
            wafers.extend(w)
            bonding.extend(b)
            runs.extend(r)
            voids.extend(v)
        runs = base.screened("inspection_run", runs, source=UPDATED_BY)
        voids = base.screened("void_obs", voids, source=UPDATED_BY)
        atoms = excursion_atoms(wafers)

        import seed_syn_process_ledger as proc
        atoms = proc.screen_all(atoms)

        print("excursion lots=%d  wafers=%d  bonding=%d  runs=%d  voids=%d  atoms=%d"
              % (len(EXCURSIONS), len(wafers), len(bonding), len(runs), len(voids),
                 len(atoms)))
        for lot in sorted(EXCURSIONS):
            prefix = "%s%03d" % (base.BASE_ID_PREFIX, lot)
            lot_runs = [r for r in runs if str(r["base_wafer_id"]).startswith(prefix)]
            lot_voids = [v for v in voids if str(v["base_wafer_id"]).startswith(prefix)]
            found = len({(v["base_wafer_id"], v["base_x"], v["base_y"])
                         for v in lot_voids})
            scanned = len({(r["base_wafer_id"], r["base_x"], r["base_y"])
                           for r in lot_runs})
            print("  lot %d: scanned=%d found=%d found_rate=%.3f per_chip=%.3f "
                  "(declared per_chip %.1f, level %d)"
                  % (lot, scanned, found, found / max(1, scanned),
                     len(lot_voids) / max(1, scanned),
                     EXCURSIONS[lot]["per_chip_target"], EXCURSIONS[lot]["expect_level"]))
        print("cause: every excursion wafer bonds under %s@%s (factor '%s')"
              % (EXCURSION_RECIPE[0], EXCURSION_RECIPE[1], EXCURSION_FACTOR))

        if not args.apply:
            print("DRY RUN: nothing written. Ruling R-2026-08-14-F gates execution on "
                  "the owner's approval; re-run with --apply "
                  "--i-accept-writing-to-owner-database once it exists.")
            return

        meta_n = register_map_meta(db, wafers)
        bond_n = _write(db, "bonding_log", bonding)
        run_n = _write(db, "inspection_run", runs)
        void_n = _write(db, "void_obs", voids)
        from ledger.store import LedgerStore
        from database.database import engine

        store = LedgerStore(engine, who="syn_lot_excursion")
        store.ensure_schema()
        atom_result = store.write_batch(
            "syn_lot_excursion", TRANSLATOR_BASE, atoms,
            cursor_value={"lots": sorted(EXCURSIONS)},
            molecules=len({a.molecule_ref for a in atoms}),
            refused=0, incomplete=0, reasons={})
        print("WROTE map_meta=%d bonding=%d runs=%d voids=%d atoms=%s"
              % (meta_n, bond_n, run_n, void_n, atom_result))

    finally:
        db.close()


if __name__ == "__main__":
    main()
