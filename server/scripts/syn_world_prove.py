"""The answer key for `seed_syn_world`, in BOTH directions, on every axis.

An assertion that only checks "the thing I planted is there" cannot fail for the reason
that matters. Every check below has a NEGATIVE twin: the 79 bond lots this fixture did
not touch must still read `unreachable`, the core dies nobody bonded must still be
unbonded, and the 21 core lots with no split must still agree with their walk. A fixture
that lights every lamp proves only that lamps light.

🔴 THE FOURTH SECTION IS THE ONE THAT MATTERS MOST. `seed_syn_world` claims it changed
nothing any existing answer key divides by. That is a claim about `bonding_log`'s
populations, `void_obs`, `inspection_run` and the excursion baseline - all measurable -
so it is measured here rather than asserted in a docstring.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import seed_syn_world as W  # noqa: E402

#: Measured on `assy_manager` immediately BEFORE this fixture was applied
#: (`seed_syn_lot_excursion --prove`, 2026-08-14). These are the numbers the "nothing
#: moved" claim is checked against. They are the record of an event that has already
#: happened, so they cannot go stale - unlike a census of something that grows.
BEFORE = {
    "bonding_log_rows": 368371,
    "void_obs_rows": 101220,
    "inspection_run_rows": 110575,
    "lots_on_grid": 103,
    "baseline_per_chip": 1.226206896551724,
    "baseline_extent_mean": 58.705757445498534,
    "ratio_101_per_chip": 2.298,
    "ratio_102_per_chip": 3.381,
    "ratio_103_per_chip": 4.966,
}
TOL = 1e-6

_FAILURES = []
_CHECKS = [0]


def check(ok, label, detail=""):
    _CHECKS[0] += 1
    print("  %s %s%s" % ("PASS" if ok else "FAIL", label,
                         ("  -- " + detail) if detail else ""))
    if not ok:
        _FAILURES.append(label)
    return ok


def one(db, sql, **params):
    from sqlalchemy import text

    return db.execute(text(sql), params).scalar()


def rows(db, sql, **params):
    from sqlalchemy import text

    return db.execute(text(sql), params).fetchall()


def prove(db):
    # 🔴 FIRST, BEFORE ANY CHECK CALLS `W.core_fanout`. That function consults the restage
    # pin set and returns the UNPINNED declared degree while the set is empty, so a check
    # written above this line compares the built fixture against a model that never
    # existed. Measured when this call sat further down: 48 tapes "disagreed" - exactly
    # the Tier-1 restage targets - and the fixture was right, the assertion was wrong.
    # This is the same load-before-use mistake the generator already had to fix once.
    W.restage_targets(db)

    tier1 = [W.BOND_LOT_FMT % n for n in W.TIER1_LOTS]
    deep = [W.BOND_LOT_FMT % n for n in W.DEEP_LOTS]

    print("\n=== 1. THE CORE AXIS: PLANTED LOTS REACH IT, UNPLANTED LOTS DO NOT ===")
    linked = one(db, "SELECT count(*) FROM bonding_log WHERE core_lot IS NOT NULL "
                     "AND core_slot IS NOT NULL AND cx IS NOT NULL AND cy IS NOT NULL")
    check(linked == 84600, "84,600 chips carry a complete core link", "got %d" % linked)
    inside = one(db, "SELECT count(*) FROM bonding_log WHERE bond_lot = ANY(:l) "
                     "AND core_lot IS NULL", l=tier1)
    check(inside == 0, "no chip in the 24 seeded lots is missing its core link",
          "%d missing" % inside)
    outside = one(db, "SELECT count(*) FROM bonding_log WHERE bond_lot LIKE 'SYN-VOID-%' "
                      "AND NOT (bond_lot = ANY(:l)) AND core_lot IS NOT NULL", l=tier1)
    check(outside == 0, "NEGATIVE: not one of the 79 unseeded lots gained a core link",
          "%d leaked" % outside)
    unseeded = one(db, "SELECT count(DISTINCT bond_lot) FROM bonding_log "
                       "WHERE bond_lot LIKE 'SYN-VOID-%' AND NOT (bond_lot = ANY(:l))",
                   l=tier1)
    check(unseeded == 79, "the 79-lot contrast population is intact",
          "%d lots" % unseeded)

    print("\n=== 2. THE DT ADDRESS IS A BIJECTION AGAIN ===")
    clash = one(db, """SELECT count(*) FROM (
        SELECT dt_lot, dt_slot, dt_x, dt_y FROM bonding_log WHERE bond_lot = ANY(:l)
        GROUP BY 1,2,3,4 HAVING count(*) > 1) t""", l=tier1)
    check(clash == 0, "no DT tape cell feeds two bonded chips in the seeded lots",
          "%d cells shared" % clash)
    cells = one(db, "SELECT count(*) FROM (SELECT DISTINCT dt_lot, dt_slot, dt_x, dt_y "
                    "FROM bonding_log WHERE bond_lot = ANY(:l)) t", l=tier1)
    chips = one(db, "SELECT count(*) FROM bonding_log WHERE bond_lot = ANY(:l)", l=tier1)
    check(cells == chips, "distinct DT cells == chips (%d)" % chips, "cells %d" % cells)
    still = one(db, """SELECT max(c) FROM (
        SELECT count(*) c FROM bonding_log
        WHERE bond_lot LIKE 'SYN-VOID-%' AND NOT (bond_lot = ANY(:l))
        GROUP BY dt_lot, dt_slot, dt_x, dt_y) t""", l=tier1)
    check(still == 25, "NEGATIVE: the unseeded lots STILL show the collapse (25 chips "
                       "per DT cell) - so the repair is what fixed it, not something "
                       "else that happened meanwhile", "max %s" % still)
    dies = one(db, """SELECT count(*) FROM (
        SELECT core_lot, core_slot, cx, cy FROM bonding_log WHERE bond_lot = ANY(:l)
        GROUP BY 1,2,3,4 HAVING count(*) > 1) t""", l=tier1)
    check(dies == 0, "no core die is bonded twice", "%d dies reused" % dies)

    print("\n=== 3. THE FRAME IS REGISTERED WHERE `ledger_lots._frame` LOOKS ===")
    dt_frames = one(db, "SELECT count(*) FROM wafer_map_metadata "
                        "WHERE target_table='bonding_log' AND map_id LIKE 'SYN-DT-%'")
    core_frames = one(db, "SELECT count(*) FROM wafer_map_metadata "
                          "WHERE target_table='bonding_log' AND map_id LIKE 'SYN-CL-%'")
    check(dt_frames == 600, "600 DT frames registered", "got %d" % dt_frames)
    check(core_frames == 600, "600 core frames registered", "got %d" % core_frames)
    hit = one(db, """SELECT count(*) FROM bonding_log b
        JOIN wafer_map_metadata m ON m.target_table='bonding_log'
         AND m.map_id = b.core_lot || '_' || b.core_slot
        WHERE b.bond_lot = ANY(:l)""", l=tier1)
    check(hit == 84600, "every seeded chip's (core_lot, core_slot) resolves to a "
                        "registered frame", "%d of 84600" % hit)
    orphan = one(db, """SELECT count(*) FROM wafer_map_metadata m
        WHERE m.target_table='bonding_log' AND m.map_id LIKE 'SYN-CL-%'
          AND NOT EXISTS (SELECT 1 FROM bonding_log b
                          WHERE b.core_lot || '_' || b.core_slot = m.map_id)""")
    check(orphan == 0, "NEGATIVE: no core frame is registered for a wafer no chip came "
                       "from", "%d orphan frames" % orphan)

    print("\n=== 4. THE DT WALK CLOSES (it returned 0 rows before) ===")
    joined = one(db, """SELECT count(*) FROM bonding_log b
        JOIN dt_log d ON d.dt_lot = b.dt_lot AND d.dt_slot = b.dt_slot
                     AND d.dt_x = b.dt_x AND d.dt_y = b.dt_y
        WHERE b.bond_lot = ANY(:l)""", l=deep)
    expect = one(db, "SELECT count(*) FROM bonding_log WHERE bond_lot = ANY(:l)", l=deep)
    check(joined == expect, "every chip of the 6 deep lots joins its dt_log row",
          "%d of %d" % (joined, expect))
    agree = one(db, """SELECT count(*) FROM bonding_log b
        JOIN dt_log d ON d.dt_lot = b.dt_lot AND d.dt_slot = b.dt_slot
                     AND d.dt_x = b.dt_x AND d.dt_y = b.dt_y
        WHERE b.bond_lot = ANY(:l)
          AND (d.core_lot IS DISTINCT FROM b.core_lot
               OR d.core_x IS DISTINCT FROM b.cx OR d.core_y IS DISTINCT FROM b.cy)""",
              l=deep)
    check(agree == 0, "the materialised core link AGREES with the dt_log utterance on "
                      "every one of those chips", "%d disagree" % agree)
    shallow = one(db, """SELECT count(*) FROM bonding_log b
        JOIN dt_log d ON d.dt_lot = b.dt_lot AND d.dt_slot = b.dt_slot
        WHERE b.bond_lot = ANY(:t) AND NOT (b.bond_lot = ANY(:d))""", t=tier1, d=deep)
    check(shallow == 0, "NEGATIVE: the 18 shallow lots have a core COLUMN but no dt_log "
                        "row - column-present and walk-present are different answers",
          "%d rows" % shallow)

    print("\n=== 5. THE AS-OF GAP IS REAL ON 3 LOTS AND ABSENT ON THE REST ===")
    # 🔴 THE GAP BELONGS TO THE CONTRIBUTOR, NOT TO THE BOND LOT. An earlier version of
    # this section asserted "bond lot 001 has no gap because 001 does not split", and
    # cross-lot fan-out made that false in the right way: lot 001's tapes borrow from lot
    # 002, which DOES split, so 001 inherits a real gap through the loan. Predicting per
    # bond lot would now be wrong; predicting per contributor is what the model says.
    split_lots = {W.core_lot_at_dt(n) for n in W.SPLIT_LOTS}
    deep_lots = {W.core_lot_at_dt(n) for n in W.DEEP_LOTS}
    for n in W.DEEP_LOTS:
        bl = W.BOND_LOT_FMT % n
        got = {(a, b) for a, b in rows(db, """
            SELECT DISTINCT b.core_lot, b.core_slot FROM bonding_log b
            WHERE b.bond_lot = :bl AND NOT EXISTS (
              SELECT 1 FROM core_wafer_map c
              WHERE c.core_lot = b.core_lot AND c.core_slot = b.core_slot)""", bl=bl)}
        present = {(a, b) for a, b in rows(db,
            "SELECT DISTINCT core_lot, core_slot FROM bonding_log WHERE bond_lot = :bl",
            bl=bl)}
        want = {(cl, cs) for cl, cs in present
                if cl not in deep_lots                       # no core map at all
                or (cl in split_lots and W.moved(int(cs)))}  # moved out by the split
        check(got == want,
              "%s: the wafers with no core-map row are EXACTLY the ones the model "
              "predicts (%d of %d contributors)" % (bl, len(want), len(present)),
              "unexpected=%s missing=%s" % (sorted(got - want)[:3], sorted(want - got)[:3]))
    borrowed = one(db, """SELECT count(DISTINCT (b.bond_lot, b.core_lot))
        FROM bonding_log b WHERE b.core_lot IS NOT NULL
          AND b.core_lot <> 'SYN-CL-' || substring(b.bond_lot from 10)""")
    check(borrowed > 0, "cross-lot loans exist: %d (bond lot, core lot) pairs where the "
                        "core lot is NOT the bond lot's own" % borrowed)
    ev = one(db, "SELECT count(*) FROM lot_event WHERE lot LIKE 'SYN-CL-%'")
    check(ev == 10, "10 lot_event rows (3 splits + 2 merges, two rows each)",
          "got %d" % ev)
    lens = rows(db, "SELECT lot, event_type, slot_numbers, wafer_ids FROM lot_event "
                    "WHERE lot LIKE 'SYN-CL-%'")
    bad = [r[0] for r in lens
           if len(r[2].split(":")) != len(r[3].split(":"))]
    check(not bad, "slot_numbers and wafer_ids correspond positionally on every row",
          "mismatched: %s" % bad)

    print("\n=== 6. THE PROCESS AXIS ===")
    wp = one(db, "SELECT count(*) FROM wafer_process WHERE lot LIKE 'SYN-CL-%'")
    check(wp == 3000, "3,000 wafer_process rows", "got %d" % wp)
    old = one(db, "SELECT count(*) FROM wafer_process WHERE lot = 'LOT-A'")
    check(old == 22, "NEGATIVE: the 22 pre-existing LOT-A rows are untouched",
          "got %d" % old)
    steps = one(db, """SELECT count(*) FROM wafer_process
        WHERE lot LIKE 'SYN-CL-%' AND step IN ('DIFFUSION','BONDING','MOLDING','DT')""")
    check(steps == 0, "NEGATIVE: no fab step collides with seed_syn_process_ledger's "
                      "step vocabulary, so no processed_with claim competes with its "
                      "answer key", "%d collisions" % steps)

    print("\n=== 6-bis. FAN-OUT: BOTH HOPS, AND THE 1-CASE IS PRESENT ===")
    # 🔴 The declared degree is asserted against the MEASURED one, per tape. A fixture
    # that declares fan-out and builds 1 looks identical to a correct one from the
    # outside, which is the whole reason this section exists.
    wrong = 0
    ones = mult = 0
    for n in W.TIER1_LOTS:
        for slot in range(1, 26):
            want = W.core_fanout(n, slot)
            got = one(db, """SELECT count(DISTINCT core_slot) FROM bonding_log
                WHERE dt_lot = :dl AND dt_slot = :ds AND core_slot IS NOT NULL""",
                      dl=W.DT_LOT_FMT % n, ds="%02d" % slot)
            if got != want:
                wrong += 1
            if want == 1:
                ones += 1
            else:
                mult += 1
    check(wrong == 0, "every DT tape's core-wafer count equals its DECLARED fan-out",
          "%d tapes disagree" % wrong)
    check(ones > 0 and mult > 0,
          "BOTH cases are planted: %d tapes with fan-out 1, %d with more" % (ones, mult))
    lo, hi = rows(db, """SELECT min(n), max(n) FROM (
        SELECT dt_lot, dt_slot, count(DISTINCT core_slot) n FROM bonding_log
        WHERE core_slot IS NOT NULL GROUP BY 1,2) t""")[0]
    check(lo == 1 and hi > 1, "measured DT->core fan-out spans 1..%d (it was 1..1 "
                              "before this round)" % hi, "min %s max %s" % (lo, hi))
    # The owner's assertion, spelled as he wrote it: a bond lot reaches N DT frames and
    # M core frames, and N/M are what the data says rather than what the screen guesses.
    for n in (1, 101):
        bl = W.BOND_LOT_FMT % n
        dt_frames = one(db, "SELECT count(DISTINCT (dt_lot, dt_slot)) FROM bonding_log "
                            "WHERE bond_lot = :bl", bl=bl)
        core_frames = one(db, "SELECT count(DISTINCT (core_lot, core_slot)) FROM "
                              "bonding_log WHERE bond_lot = :bl", bl=bl)
        check(dt_frames == 25 and core_frames > 25,
              "%s reaches %d DT frames and %d CORE frames - the core side is WIDER, "
              "which is what many-to-many means" % (bl, dt_frames, core_frames))
    # And one base wafer, which is the unit a screen actually draws.
    b_dt, b_core = rows(db, """SELECT count(DISTINCT (dt_lot,dt_slot)),
                                      count(DISTINCT (core_lot,core_slot))
        FROM bonding_log WHERE base_id = 'SYN-BW-001-08'""")[0]
    check(b_dt == 25 and b_core > 25,
          "one base wafer SYN-BW-001-08 is fed by %d DT tapes and %d core wafers"
          % (b_dt, b_core))

    print("\n=== 7. THE LEDGER ===")
    # DERIVED from the generator, never typed in. A hardcoded expectation goes stale the
    # first time the fan-out declaration changes and then asserts the old world.
    W.restage_targets(db)
    want_coload = sum(len(W.transferred_shares(n, s)) - 1
                      for n in W.TIER1_LOTS for s in range(1, 26))
    want_atoms = 600 + 3000 + want_coload
    atoms = one(db, "SELECT count(*) FROM ledger_events "
                    "WHERE source_translator_ver LIKE 'syn_world/%'")
    check(atoms == want_atoms,
          "%d atoms landed (600 register + 3,000 processed_with + %d co-load)"
          % (want_atoms, want_coload), "got %d" % atoms)
    reg = one(db, "SELECT count(*) FROM ledger_events WHERE predicate='register' "
                  "AND source_translator_ver LIKE 'syn_world/%'")
    check(reg == 600, "600 core wafers registered", "got %d" % reg)
    orphan_reg = one(db, """SELECT count(*) FROM ledger_events r
        WHERE r.predicate='register' AND r.source_translator_ver LIKE 'syn_world/%'
          AND NOT EXISTS (SELECT 1 FROM ledger_events t
                          WHERE t.predicate='transferred'
                            AND t.subject_keys = r.subject_keys)""")
    check(orphan_reg == 0, "every registered core wafer is one the EXISTING transfer "
                           "chain already names - no new entity was invented",
          "%d unreachable registrations" % orphan_reg)
    xfer = one(db, "SELECT count(*) FROM ledger_events WHERE predicate='transferred' "
                   "AND source_translator_ver LIKE 'syn_world/%#co_load'")
    check(xfer == want_coload,
          "%d co-load `transferred` atoms - ONLY the extra contributors fan-out created"
          % want_coload, "%d emitted" % xfer)
    # 🔴 THE REGRESSION THIS PIN EXISTS TO PREVENT. On the first attempt 48 of the 290
    # restage targets got a co-load atom, the walk reached a core wafer without following
    # the restage, and `seed_syn_process_ledger --prove`'s "chains passing TWO dt slots"
    # fell from 125 to 25. Restage targets must carry NO co-load atom.
    leaked = one(db, """WITH restage AS (
          SELECT DISTINCT object_payload->'to'->'keys'->>'dt_lot' l,
                          object_payload->'to'->'keys'->>'dt_slot' s
          FROM ledger_events WHERE predicate='transferred'
            AND object_payload->'from'->>'type'='dt_slot'
            AND object_payload->'to'->>'type'='dt_slot'),
        coload AS (
          SELECT DISTINCT object_payload->'to'->'keys'->>'dt_lot' l,
                          object_payload->'to'->'keys'->>'dt_slot' s
          FROM ledger_events WHERE predicate='transferred'
            AND source_translator_ver LIKE 'syn_world/%')
        SELECT count(*) FROM restage r JOIN coload c USING (l, s)""")
    check(leaked == 0, "NEGATIVE: no restage target carries a co-load atom - a tape fed "
                       "by another tape was not also fed from a wafer grid",
          "%d leaked" % leaked)
    primary = one(db, """SELECT count(*) FROM ledger_events
        WHERE predicate='transferred' AND source_translator_ver LIKE 'syn_world/%'
          AND object_payload->'from'->>'type' = 'wafer_grid'
          AND subject_keys->>'wafer' = 'SYN-CW-001-01'
          AND object_payload->'to'->'keys'->>'dt_slot' = '01'""")
    check(primary == 0, "NEGATIVE: the PRIMARY load hop was not re-emitted - payload is "
                        "in the dedupe key, so a second copy would double-count the "
                        "dies in the residual fold", "%d duplicates" % primary)
    ledger_fan = one(db, """SELECT max(n) FROM (
        SELECT object_payload->'to'->'keys'->>'dt_lot' l,
               object_payload->'to'->'keys'->>'dt_slot' s,
               count(DISTINCT subject_keys->>'wafer') n
        FROM ledger_events WHERE predicate='transferred'
          AND object_payload->'to'->>'type'='dt_slot' GROUP BY 1,2) t""")
    check(ledger_fan > 1, "the LEDGER now tells the same fan-out story as the tables "
                          "(max core wafers per tape = %s; it was 1 before)"
          % ledger_fan)

    print("\n=== 8. NOTHING THE FOUR ANSWER KEYS DIVIDE BY MOVED ===")
    for table, want in (("bonding_log", BEFORE["bonding_log_rows"]),
                        ("void_obs", BEFORE["void_obs_rows"]),
                        ("inspection_run", BEFORE["inspection_run_rows"])):
        got = one(db, "SELECT count(*) FROM %s" % table)
        check(got == want, "%s row count unchanged (%d)" % (table, want), "got %d" % got)
    lots = one(db, "SELECT count(DISTINCT bond_lot) FROM bonding_log "
                   "WHERE bond_lot LIKE 'SYN-VOID-%'")
    check(lots == BEFORE["lots_on_grid"], "lots on the grid unchanged (%d)"
          % BEFORE["lots_on_grid"], "got %d" % lots)
    moved_cols = one(db, """SELECT count(*) FROM bonding_log
        WHERE bond_lot = ANY(:l) AND (b_bn IS NULL OR stack_height IS NULL
              OR base_id IS NULL OR bx IS NULL OR by IS NULL)""", l=tier1)
    check(moved_cols == 0, "the void-join columns (base_id, bx, by) and the factor "
                           "columns (b_bn, stack_height) are all still populated",
          "%d damaged" % moved_cols)

    print("\n" + "=" * 74)
    print("VERDICT: %s   (%d checks, %d failed)"
          % ("PASS" if not _FAILURES else "FAIL", _CHECKS[0], len(_FAILURES)))
    if _FAILURES:
        for f in _FAILURES:
            print("   FAILED: %s" % f)
    print("=" * 74)
    print("\nNow re-run the four existing answer keys and compare against BEFORE:")
    print("  seed_syn_lot_excursion.py --prove     baseline(per_chip) was %.15f"
          % BEFORE["baseline_per_chip"])
    print("  seed_syn_void_base_join.py --prove")
    print("  seed_syn_process_ledger.py --prove")
    print("  seed_syn_process_ledger.py --prove --finding delam")
    return 1 if _FAILURES else 0
