"""ONE synthetic bond lot whose bonding -> DT hop is k = 1, so all three axes draw.

WHAT THIS CLOSES, IN ONE SENTENCE
---------------------------------
`GET /api/ledger/lot_map` serves three projections - bond, DT, core - and on this box
NO LOT could ever make more than the first one `ready`. This lot can.

MEASURED on `assy_manager` 2026-08-14, before this script existed::

    GET /api/ledger/lot_map?row=SYN-VOID-001&slot=01
      bond   ready
      dt     no_frame  frame_ambiguous_across_slots  available_slots 01..25
      core   no_frame  frame_ambiguous_across_slots  available_slots 01..25

One bonded wafer's 141 dies scatter across 25 DT slots (`seed_syn_void_base_join`
assigns `dt_slot = 1 + index % 25`), so narrowing to ONE bond slot still leaves 25 DT
frames and 25 core frames on the surviving rows. `_map_envelope` counts the frame keys
rather than sampling one - deliberately, that is what `MAP_REASON_FRAME_AMBIGUOUS`
exists for - so the DT and core panels correctly refuse to draw. The screen has never
been seen whole.

`seed_syn_world.py` (~line 115) states plainly why it cannot repair that in place: the
64,375 existing `dt_slot -> package_gate` atoms were DERIVED from the current
`bonding_log.dt_slot`, and rewriting the column would make them false. So this script
does not touch one existing row. It mints a NEW lot in which the first hop is k = 1.

THE TOPOLOGY, WHICH IS THE WHOLE POINT
--------------------------------------
For bond slot S, every one of that wafer's 141 dies goes to::

    dt_lot   = 'SYN-K1DT-201'   dt_slot   = S
    core_lot = 'SYN-K1CL-201'   core_slot = S

so on a `slot=S` request all three frame keys resolve to exactly one value each and
`_frame` finds a registered grid for all three. `dt_x`/`dt_y` are a BIJECTION inside the
DT frame (row-major, 141 dies into a 15x10 = 150-cell tape) and `cx`/`cy` a bijection
inside the core frame (141 of the core wafer's 263 occupied cells) - asserted on the
plan before anything is written, because a tape cell holds one die and a fixture that
forgets it re-introduces the exact defect `seed_syn_world` was written to remove.

k = 1 IS A MODEL, NOT A SIMPLIFICATION. `seed_syn_world`'s own note says the first hop
having no variation - 25 everywhere, min = max - is itself a defect in the fixture: a
consumer that hardcodes "many" and one that reads the real count are indistinguishable
without a 1. This lot IS that 1. The 103 existing lots keep their 25, so the corpus now
carries both degrees and a screen can be asked to tell them apart.

BASE (x, y) IS DERIVED, NEVER INVENTED
--------------------------------------
Same rule and the same primitive as `seed_syn_void_base_join`: each wafer DECLARES its
recorded frame in `wafer_map_metadata`, and `bx`/`by` come out of
`map_overlay.make_frame_transform` applied to the bond coordinate on the same row.
`vbj.base_derivation` refuses a frame that does not round-trip, so nothing is written
that cannot be reproduced from the stored declaration. No coordinate rule is respelled
here.

THE NAMESPACE, AND WHY THE PREFIX IS NOT NEGOTIABLE
---------------------------------------------------
Base wafers are `SYN-BW-K1-201-<slot>`. The `SYN-BW-` prefix is KEPT ON PURPOSE:
`PROJECT_STATUS.md` documents the fixture-separation predicates as
``void_obs WHERE base_wafer_id LIKE 'SYN-BW-%'`` and
``wafer_map_metadata WHERE map_id LIKE 'SYN-...'``. A prettier prefix would make these
rows invisible to the documented predicate, and a synthetic row that no separation
predicate can see READS AS REAL DATA. Separation beats convenience.

⚠️ CONSEQUENCE, RECORDED RATHER THAN PREVENTED
`seed_syn_process_ledger.measured_void_rate` matches `SYN-BW-%`. These 25 new wafers
therefore fall inside its population, so a future RE-RUN of that answer-key generator
will pick them up and may shift its top-10% causal cut by a couple of boundary wafers.
That is not a reason to rename them - it is a reason to say so here. Nothing already
written changes; only a re-run would recompute. Two smaller mitigations are in place:
the inspection stamps sit at day offset 0 (2026-08-13), EARLIER than every existing SYN
lot's runs (offsets 1..103), so `seed_syn_lot_excursion --prove`'s "the planted lots are
the latest three by inspection time" cannot be disturbed; and the void generator is
`vbj.scan_rows` unchanged, so this lot's void rate is drawn from the same distribution
as the 103 ordinary lots rather than being an outlier.

WHAT IT WRITES - and what it deliberately does not
--------------------------------------------------
    bonding_log         25 slots x 141 dies                        3,525 rows
    wafer_map_metadata  25 bond + 25 DT + 25 core frames              75 rows
    inspection_run      scans (every 5th die) + 2 negatives/wafer    ~750 rows
    void_obs            the voids those scans found                  ~700 rows

NO ledger atom, NO `dt_log`, NO `core_wafer_map`, NO existing row touched. This lot is
the SCREEN's fixture; wiring it into the transfer chain would mean emitting `transferred`
atoms that reconcile with `seed_syn_process_ledger`'s residual fold, which is a separate
decision and not needed to make the three-axis map draw.

Usage::

    conda run -n assy_manager python server/scripts/seed_syn_k1_lot.py
    conda run -n assy_manager python server/scripts/seed_syn_k1_lot.py \
        --apply --i-accept-writing-to-owner-database
    conda run -n assy_manager python server/scripts/seed_syn_k1_lot.py --verify-rollback

ROLLBACK - a predicate, and it has been RUN (as SELECT count) rather than assumed
---------------------------------------------------------------------------------
    DELETE FROM void_obs       WHERE base_wafer_id LIKE 'SYN-BW-K1-201-%';
    DELETE FROM inspection_run WHERE base_wafer_id LIKE 'SYN-BW-K1-201-%';
    DELETE FROM bonding_log    WHERE bond_lot = 'SYN-K1-201';
    DELETE FROM wafer_map_metadata WHERE target_table = 'bonding_log'
       AND (map_id LIKE 'SYN-K1-201\\_%' ESCAPE '\\'
         OR map_id LIKE 'SYN-K1DT-201\\_%' ESCAPE '\\'
         OR map_id LIKE 'SYN-K1CL-201\\_%' ESCAPE '\\');
    DELETE FROM cell_sources    WHERE updated_by = 'seed_syn_k1_lot';
    DELETE FROM cell_overwrites WHERE updated_by = 'seed_syn_k1_lot';

🔴 `updated_by` IS THIS MODULE'S OWN, AND THAT IS NOT A DETAIL. A helper imported from
another seeder closes over ITS OWN module-level constants: calling `vbj._write` would
have stamped every cell with `updated_by = 'seed_syn_void_base_join'` and the predicate
above would have matched ZERO rows while the data sat there looking fine. That exact
mistake was made in this project on 2026-08-14 (6,964 atoms landed under another
module's translator name). So `_write` / `_batch` are re-declared here rather than
imported, and `--verify-rollback` COUNTS the marker instead of trusting it. Every
coordinate primitive - which is where a second spelling actually costs something - is
still imported from `seed_syn_void_base_join`.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The void seeder owns the base geometry primitives - `occupied_cells`,
# `base_derivation`, `recorded_meta`, `frame_for_wafer`, `scan_rows`, `screened`. A second
# spelling of a coordinate rule is how two screens come to disagree about where a die is,
# so they are imported. What is NOT imported is anything that writes provenance; see the
# docstring's last paragraph.
import seed_syn_void_base_join as vbj  # noqa: E402

# --------------------------------------------------------------------------
# Namespace
# --------------------------------------------------------------------------
LOT_NO = 201
BOND_LOT = "SYN-K1-201"
DT_LOT = "SYN-K1DT-201"
CORE_LOT = "SYN-K1CL-201"
#: 🔴 `SYN-BW-` is load-bearing. See the docstring.
BASE_ID_FMT = "SYN-BW-K1-201-%02d"
SLOTS = 25

#: MINE, not vbj's. The rollback predicate is written against this literal.
SOURCE_NAME, UPDATED_BY = "custom_script", "seed_syn_k1_lot"
EVENT_TIME = "2026-08-13T00:00:00+09:00"

FORBIDDEN_DATABASES = ("assy_manager",)
CHUNK = 1000
SEED = 20260814

#: The DT tape grid. 15 x 10 = 150 cells; one wafer delivers 141, so the tape is not full
#: and "how much of this tape was loaded" stays a real question.
DT_COLS, DT_ROWS = 15, 10
DT_CELLS = DT_COLS * DT_ROWS

#: The core wafer's own geometry - DELIBERATELY a third distinct grid. Bond is 15x15,
#: DT is 15x10, core is 19x19; three axes drawn on three identical grids would let a
#: client that ignores `frame.grid` look correct on all of them.
#: MEASURED sizing (`seed_syn_world` pinned it): at 15 mm dies inside a 300 mm circle the
#: occupied count is 263 for every grid from 19x19 up, so 19x19 is the smallest grid that
#: holds the whole circle, and 263 >= 141 with room to spare - the ~122 dies that never
#: leave are the denominator for "how much of this wafer was used".
CORE_SPEC = {
    "grid_cols": 19, "grid_rows": 19, "grid_start_x": 0, "grid_start_y": 0,
    "grid_y_invert": False,
    "phys_wafer_dia": 300, "phys_chip_x": 15, "phys_chip_y": 15,
    "phys_offset_x": 4, "phys_offset_y": -2, "phys_edge_margin": 3,
}

#: `vbj.scan_rows` uses its `lot` argument as a DAY OFFSET from 2026-08-13. Passing 201
#: would stamp these runs in March 2027 and steal "the latest three by inspection time"
#: from `seed_syn_lot_excursion`'s planted lots. 0 puts them BEFORE every existing SYN
#: run (offsets 1..103), which is the one place they cannot disturb an answer key.
SCAN_DAY_OFFSET = 0


# --------------------------------------------------------------------------
# Geometry - all borrowed
# --------------------------------------------------------------------------


def core_meta() -> dict:
    meta = dict(CORE_SPEC)
    meta["rotation"], meta["side"] = 0, "front"
    return meta


_CORE_CELLS = None


def core_cells():
    """The core wafer's occupied cells, via the SAME primitive the base wafer uses."""
    global _CORE_CELLS
    if _CORE_CELLS is None:
        _CORE_CELLS = vbj.occupied_cells(core_meta())
    return _CORE_CELLS


def dt_meta() -> dict:
    return {"grid_cols": DT_COLS, "grid_rows": DT_ROWS,
            "grid_start_x": 0, "grid_start_y": 0, "grid_y_invert": False,
            "phys_chip_x": 15, "phys_chip_y": 15, "phys_edge_margin": 2,
            "phys_offset_x": 0, "phys_offset_y": 0, "rotation": 0, "side": "front"}


def dt_cell(j: int):
    """DT tape address for the j-th die of a wafer. Row-major, bijective by construction."""
    if not 0 <= j < DT_CELLS:
        raise SystemExit(
            "REFUSED: DT cell index %d is outside the %dx%d tape. A tape cell holds ONE "
            "die; more dies were assigned to this slot than it can hold."
            % (j, DT_COLS, DT_ROWS))
    return j % DT_COLS, j // DT_COLS


def core_pick(slot: int, n: int):
    """`n` distinct cells of core wafer `slot`, as a deterministic permutation.

    🔴 NOT THE FIRST `n` IN SORTED ORDER, on purpose - the same argument
    `seed_syn_world.pick_order` makes. If DT cell j always came from the j-th core cell in
    reading order, a consumer could recover the core position by arithmetic and would
    never read the stored correspondence, so the join this fixture exists to exercise
    would sit unused while the fixture passed.
    """
    cells = core_cells()
    if n > len(cells):
        raise SystemExit(
            "REFUSED: core wafer %02d has %d occupied cells but %d dies were asked of it. "
            "A wafer cannot supply more dies than it has." % (slot, len(cells), n))
    order = list(range(len(cells)))
    random.Random((SEED * 7919) + LOT_NO * 1009 + slot).shuffle(order)
    return [cells[i] for i in order[:n]]


# --------------------------------------------------------------------------
# Row builders - pure, so the dry run checks exactly what --apply would write
# --------------------------------------------------------------------------


def bonding_rows(slot: int):
    """One wafer's bonded dies. `(frame, base_id, rows)`.

    Base (x, y) is DERIVED from bond (x, y) through the frame this wafer declares - never
    invented. `vbj.base_derivation` refuses a frame that does not map one-to-one or does
    not round-trip, so the refusal happens before a row exists.
    """
    frame = vbj.frame_for_wafer(LOT_NO, slot)
    to_base, _to_recorded, cells = vbj.base_derivation(frame)
    base_id = BASE_ID_FMT % slot
    bond_slot = "%02d" % slot
    core_slot = "%02d" % slot
    dt_slot = "%02d" % slot
    picks = core_pick(slot, len(cells))
    rng = random.Random((SEED * 1_000_003) + LOT_NO * 1009 + slot)

    # A deterministic defect cluster so the wafer is not uniformly good and the map has
    # something to show. '0' is the minority bin on the real rows, so the fixture matches.
    ccx, ccy = rng.choice(cells)
    rows = []
    for j, (bond_x, bond_y) in enumerate(cells):
        bx, by = to_base(bond_x, bond_y)
        dt_x, dt_y = dt_cell(j)
        core_x, core_y = picks[j]
        defect = abs(bond_x - ccx) + abs(bond_y - ccy) <= 2 or rng.random() < 0.02
        rows.append({
            "bond_lot": BOND_LOT, "bond_slot": bond_slot,
            "bond_x": bond_x, "bond_y": bond_y,
            "base_id": base_id, "bx": bx, "by": by,
            "b_bn": "0" if defect else "1",
            "stack_height": vbj.STACK_MIN + ((bond_x * 5 + bond_y * 3)
                                             % (vbj.STACK_MAX - vbj.STACK_MIN + 1)),
            # 🔴 k = 1. The whole wafer lands on ONE tape and comes from ONE core wafer.
            "dt_lot": DT_LOT, "dt_slot": dt_slot, "dt_x": dt_x, "dt_y": dt_y,
            "core_lot": CORE_LOT, "core_slot": core_slot, "cx": core_x, "cy": core_y,
            "bond_eqp": "SYN-BD-K1",
            "event_time": EVENT_TIME,
        })
    return frame, base_id, rows


def frame_rows(wafers):
    """A registered frame for every bond wafer, every DT tape and every core wafer.

    🔴 KEYED THE WAY `ledger_lots._frame` LOOKS THEM UP, which is not the intuitive way:
    `target_table` is the ATTRIBUTION RELATION - `bonding_log`, the table the declared
    bridge lands on - for ALL THREE families, and `map_id` is f"{lot}_{slot}". Registering
    the DT frames under `dt_log` or the core frames under `core_wafer_map` would read as
    obviously correct and would never be found. Verified against the existing SYN-DT-* /
    SYN-CL-* rows, which sit under `target_table='bonding_log'`, 600 of each.
    """
    import map_meta_registrar

    rows = []
    for bond_slot, frame, _base_id in wafers:
        # The bond frame's map_id goes through the platform's composer rather than an
        # f-string, because registration and lookup must compose the SAME identity; then
        # it is CHECKED against the spelling `_frame` will build, so a divergence fails
        # here instead of showing up as `no_registered_frame` on a screen.
        map_id = map_meta_registrar.compose_map_id(
            ["bond_lot", "bond_slot"],
            {"bond_lot": BOND_LOT, "bond_slot": bond_slot}, "bonding_log")
        expected = "%s_%s" % (BOND_LOT, bond_slot)
        if map_id != expected:
            raise SystemExit(
                "REFUSED: the composer makes map_id %r but `ledger_lots._frame` looks up "
                "%r (f\"{lot}_{slot}\" off the stored column values). The frame would be "
                "registered where nothing reads it." % (map_id, expected))
        rows.append({"target_table": "bonding_log", "map_id": map_id,
                     "grid_metadata": json.dumps(vbj.recorded_meta(frame),
                                                 ensure_ascii=False, sort_keys=True)})
        rows.append({"target_table": "bonding_log",
                     "map_id": "%s_%s" % (DT_LOT, bond_slot),
                     "grid_metadata": json.dumps(dt_meta(), ensure_ascii=False,
                                                 sort_keys=True)})
        rows.append({"target_table": "bonding_log",
                     "map_id": "%s_%s" % (CORE_LOT, bond_slot),
                     "grid_metadata": json.dumps(core_meta(), ensure_ascii=False,
                                                 sort_keys=True)})
    return rows


def assert_bijections(plan_rows):
    """A tape cell holds one die, and so does a core cell. Asserted on the PLAN.

    Both addresses are checked GLOBALLY rather than per wafer: with k = 1 the two happen
    to coincide, and an assertion that is only accidentally right stops being right the
    day somebody widens the fan-out.
    """
    dt_seen, core_seen = {}, {}
    for r in plan_rows:
        dt = (r["dt_lot"], r["dt_slot"], r["dt_x"], r["dt_y"])
        core = (r["core_lot"], r["core_slot"], r["cx"], r["cy"])
        dt_seen[dt] = dt_seen.get(dt, 0) + 1
        core_seen[core] = core_seen.get(core, 0) + 1
    for label, seen, what in (("DT cell", dt_seen, "a tape cell holds one die"),
                              ("core die", core_seen, "a die is bonded once")):
        clash = {k: v for k, v in seen.items() if v > 1}
        if clash:
            first = sorted(clash)[0]
            raise SystemExit("REFUSED: %d %s(s) used more than once; first %s x%d - %s."
                             % (len(clash), label, first, clash[first], what))
    if len(dt_seen) != len(plan_rows) or len(core_seen) != len(plan_rows):
        raise SystemExit("REFUSED: %d rows but %d DT cells and %d core dies - the counts "
                         "must be equal for both to be bijections."
                         % (len(plan_rows), len(dt_seen), len(core_seen)))
    return len(dt_seen), len(core_seen)


def assert_single_frame_per_slot(plan_rows):
    """The reason this lot exists: ONE frame key per family per slot.

    This is the condition `_map_envelope` actually tests (`len(lots_seen) == 1 and
    len(slots_seen) == 1` per axis, on the rows surviving the `bond_slot` filter). Asserting
    it here means a topology regression fails in this script rather than as a
    `frame_ambiguous_across_slots` on somebody's screen.
    """
    by_slot = {}
    for r in plan_rows:
        by_slot.setdefault(r["bond_slot"], []).append(r)
    for bond_slot, rows in sorted(by_slot.items()):
        for lot_col, slot_col in (("bond_lot", "bond_slot"), ("dt_lot", "dt_slot"),
                                  ("core_lot", "core_slot")):
            lots = {r[lot_col] for r in rows}
            slots = {r[slot_col] for r in rows}
            if len(lots) != 1 or len(slots) != 1:
                raise SystemExit(
                    "REFUSED: bond slot %s spans %d %s x %d %s. `lot_map` would answer "
                    "`frame_ambiguous_across_slots` for that axis, which is the exact "
                    "state this lot exists to escape."
                    % (bond_slot, len(lots), lot_col, len(slots), slot_col))
    return len(by_slot)


# --------------------------------------------------------------------------
# Writing - re-declared here, NOT imported. See the docstring's last paragraph.
# --------------------------------------------------------------------------


def _batch(rows):
    from database import schemas

    return schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(updates=row, source_name=SOURCE_NAME,
                                           updated_by=UPDATED_BY) for row in rows],
        replace_map=False, scope=None)


def _write(db, table: str, rows: list) -> int:
    """Chunked upsert. A silently dropped update cell fails the run, loudly."""
    from database import crud

    written = 0
    for start in range(0, len(rows), CHUNK):
        report = {}
        _, changed, _, _ = crud.apply_batch_updates(
            db, table, _batch(rows[start:start + CHUNK]), drop_report=report)
        if report.get("dropped_cells"):
            raise SystemExit(
                "REFUSED: writing '%s' DROPPED %d update cell(s), column(s) %s, "
                "reason(s) %s - the columns are not declared in table_config.json "
                "column_types. A dropped key lands as a 200 with nothing written."
                % (table, report["dropped_cells"], sorted(report.get("by_column") or {}),
                   report.get("by_reason")))
        written += len(changed or ())
    return written


def guard_database(db, allow_owner_database=False):
    from sqlalchemy import text

    name = db.execute(text("SELECT current_database()")).scalar()
    if name in FORBIDDEN_DATABASES:
        if not allow_owner_database:
            raise SystemExit(
                "REFUSED: connected to '%s', which is the owner's working database. "
                "Point DATABASE_URL at a fixture database, or pass "
                "--i-accept-writing-to-owner-database if the owner has decided "
                "otherwise for this run." % name)
        print("!! OWNER DATABASE '%s' -- writing synthetic rows by explicit decision."
              % name)
        print("!! every cell carries updated_by = '%s' (this module's OWN, not the "
              "borrowed seeder's)" % UPDATED_BY)
    return name


#: The rollback block from the docstring, as executable predicates. `--verify-rollback`
#: runs them as SELECT count(*) so the block is a MEASUREMENT rather than a promise: a
#: predicate that has never been run is a predicate that matches zero rows exactly as
#: convincingly as one that works.
ROLLBACK_PREDICATES = [
    ("void_obs", "base_wafer_id LIKE 'SYN-BW-K1-201-%'"),
    ("inspection_run", "base_wafer_id LIKE 'SYN-BW-K1-201-%'"),
    ("bonding_log", "bond_lot = 'SYN-K1-201'"),
    ("wafer_map_metadata",
     r"target_table = 'bonding_log' AND (map_id LIKE 'SYN-K1-201\_%' ESCAPE '\'"
     r" OR map_id LIKE 'SYN-K1DT-201\_%' ESCAPE '\'"
     r" OR map_id LIKE 'SYN-K1CL-201\_%' ESCAPE '\')"),
    ("cell_sources", "updated_by = 'seed_syn_k1_lot'"),
    ("cell_overwrites", "updated_by = 'seed_syn_k1_lot'"),
]


def verify_rollback(db):
    """Count what each rollback predicate matches, and REFUSE a zero on the marker.

    🔴 THE MARKER CHECK IS THE POINT. `vbj._write` stamps `updated_by =
    'seed_syn_void_base_join'` because that helper closes over ITS module's constants; a
    seeder that reused it would write perfectly good rows under somebody else's name and
    the `cell_sources` predicates below would match nothing while looking fine. Counting
    is what turns "I used my own writer" from a claim into a fact.
    """
    from sqlalchemy import text

    out = []
    for table, predicate in ROLLBACK_PREDICATES:
        n = db.execute(text(f"SELECT count(*) FROM {table} WHERE {predicate}")).scalar()
        out.append((table, predicate, int(n)))
    marker = {t: n for t, _p, n in out}
    if not marker.get("cell_sources"):
        raise SystemExit(
            "REFUSED: `cell_sources WHERE updated_by = '%s'` matched 0 rows. Either "
            "nothing was written yet, or the cells landed under ANOTHER module's "
            "`updated_by` - which is the imported-helper trap this script re-declares "
            "`_write` to avoid. The rollback block is not verified." % UPDATED_BY)
    return out


# --------------------------------------------------------------------------


def build():
    wafers, bond_all, run_all, void_all, negatives = [], [], [], [], []
    for slot in range(1, SLOTS + 1):
        frame, base_id, rows = bonding_rows(slot)
        runs, voids, negs = vbj.scan_rows(SCAN_DAY_OFFSET, slot, SEED, rows, 5)
        wafers.append(("%02d" % slot, frame, base_id))
        bond_all.extend(rows)
        run_all.extend(runs)
        void_all.extend(voids)
        negatives.extend(negs)
    # The SAME gate ingestion uses. A fixture its own ingest path would refuse is a file
    # waiting to fail in `err/`.
    run_all = vbj.screened("inspection_run", run_all, source=UPDATED_BY)
    void_all = vbj.screened("void_obs", void_all, source=UPDATED_BY)
    return {"wafers": wafers, "bonding_log": bond_all,
            "wafer_map_metadata": frame_rows(wafers),
            "inspection_run": run_all, "void_obs": void_all,
            "__negatives": negatives}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write; default is a dry run")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    ap.add_argument("--verify-rollback", action="store_true",
                    help="count what each rollback predicate matches, write nothing")
    args = ap.parse_args(argv)

    from database import crud, models
    from database.database import SessionLocal

    # REQUIRED, and its absence does not look like a config problem - without it the first
    # write raises "Table model for '<t>' is not initialized", which reads as a deployment
    # fault when it is only this process never having built its dynamic models.
    models.init_dynamic_models(crud.TABLE_CONFIG)

    db = SessionLocal()
    try:
        if args.verify_rollback:
            print("database: %s" % guard_database(db, allow_owner_database=True))
            print("\n--- ROLLBACK PREDICATES, COUNTED ---")
            for table, predicate, n in verify_rollback(db):
                print("  %-19s %7d rows   WHERE %s" % (table, n, predicate))
            return 0

        started = time.time()
        plan = build()
        dt_cells, core_dies = assert_bijections(plan["bonding_log"])
        slots = assert_single_frame_per_slot(plan["bonding_log"])
        print("built in %.1fs" % (time.time() - started))
        print("lot %s: %d slots x %d dies = %d bonded positions"
              % (BOND_LOT, slots, len(plan["bonding_log"]) // max(1, slots),
                 len(plan["bonding_log"])))
        print("  k = 1 on BOTH hops: bond slot S -> %s/S -> %s/S (one frame key per "
              "family per slot, asserted)" % (DT_LOT, CORE_LOT))
        print("  distinct DT cells %d / distinct core dies %d - both equal the row "
              "count, so both are bijections" % (dt_cells, core_dies))
        print("  core wafer: %d occupied cells of a %dx%d grid; %d leave, %d stay"
              % (len(core_cells()), CORE_SPEC["grid_cols"], CORE_SPEC["grid_rows"],
                 len(plan["bonding_log"]) // max(1, slots),
                 len(core_cells()) - len(plan["bonding_log"]) // max(1, slots)))
        print("  frames used (declared in wafer_map_metadata): %s"
              % ", ".join(sorted({w[1] for w in plan["wafers"]})))
        for table in ("bonding_log", "wafer_map_metadata", "inspection_run", "void_obs"):
            print("  %-19s %7d rows" % (table, len(plan[table])))
        print("  negatives (must NOT join): %d" % len(plan["__negatives"]))

        if not args.apply:
            print("\nDRY RUN - nothing written. Add --apply "
                  "--i-accept-writing-to-owner-database to write.")
            return 0

        print("database: %s" % guard_database(db, allow_owner_database=args.allow_owner))
        for table in ("wafer_map_metadata", "bonding_log", "inspection_run", "void_obs"):
            t0 = time.time()
            n = _write(db, table, plan[table])
            db.commit()
            print("  wrote %-19s %7d changed row(s) in %.1fs"
                  % (table, n, time.time() - t0))
        print("\n--- ROLLBACK PREDICATES, COUNTED (not assumed) ---")
        for table, predicate, n in verify_rollback(db):
            print("  %-19s %7d rows   WHERE %s" % (table, n, predicate))
        print("\nDONE. Confirm with:")
        print("  GET http://127.0.0.1:8080/api/ledger/lot_map?row=%s&slot=01" % BOND_LOT)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
