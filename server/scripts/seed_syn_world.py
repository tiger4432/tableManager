"""The upstream the ledger already names: core wafers, DT transfers, lots, process history.

WHAT THIS IS, AND WHY IT IS NOT A NEW WORLD
--------------------------------------------
`seed_syn_process_ledger` already wrote a COMPLETE, walkable transfer chain for the SYN
world. MEASURED on `assy_manager` 2026-08-14, before this script existed:

    Wafer{"wafer":"SYN-CW-001-01"} --transferred--> to dt_slot{SYN-DT-001,01}   qty 164
    Wafer{"wafer":"SYN-CW-001-01"} --transferred--> to package_gate{SYN-BW-001-08} qty 6

2,575 distinct `SYN-CW-<lot>-<slot>` subjects, 29 atoms each, and the consume hops
RECONCILE with the source table exactly: 25 hops x qty 6 = 150 chips out of
`SYN-DT-001/01`, and `bonding_log` holds exactly 150 chips with that (dt_lot, dt_slot).

And `core_wafer_map` held ZERO rows for any of them.

So the walk already reaches a core wafer; there was no row at the far end. This script
does not invent a world - it MATERIALISES the one the ledger already names. No new side
join is created anywhere (ruling R-2026-08-14-D): every link below is a column on a row,
reached by the bridge `siblings_axes.json` already declares.

🔴 WHAT IS DELIBERATELY NOT TOUCHED, AND WHY THAT IS THE WHOLE SAFETY ARGUMENT
------------------------------------------------------------------------------
Four answer keys are live on this box and every one of them is computed AT PROVE TIME
from `bonding_log` / `void_obs` / `inspection_run`. Two of them are fragile in ways that
are easy to miss:

  * `seed_syn_lot_excursion --prove` measures its baseline as the LIVE MEDIAN over every
    lot on the grid, and lot 101 clears the 2.0 threshold by only ~13%. Adding lots moves
    the median and can un-plant a planted lot.
  * the same prove asserts BOTH "no unplanted lot crosses the first threshold" AND "the
    planted lots are the latest three by inspection time". A new bond lot, a new void, or
    a new inspection run can break either.

Therefore this script writes NO bond row, NO void, NO inspection run, and changes NO
existing bonding column except two that are provably unread by any answer key
(`dt_x`/`dt_y`, see below) and four that are NULL on every row (`core_lot`, `core_slot`,
`cx`, `cy`). The populations, the denominators and the timestamps all four keys divide by
are bit-identical before and after. `--prove` re-runs them and prints the comparison.

🔴 THE DT ADDRESS WAS COLLAPSED, AND THAT IS A DEFECT, NOT A STYLE CHOICE
--------------------------------------------------------------------------
`seed_syn_void_base_join.bonding_rows` derives all three DT fields from `index` alone::

    "dt_slot": "%02d" % (1 + (index % 25)),
    "dt_x": index % WAFER_SPEC["grid_cols"],      # 15
    "dt_y": index // WAFER_SPEC["grid_cols"],

`index` runs 0..140 over ONE base wafer's cells and the same sequence runs on every base
wafer, so the DT address does not vary with the consuming wafer. MEASURED consequence:
`SYN-DT-001/01` has SIX distinct (dt_x, dt_y) - (0,0) (0,5) (5,3) (5,8) (10,1) (10,6) -
and each is claimed by all 25 base wafers. Across the whole table: 19,819 distinct DT
cells for 368,371 chips, and 141 x 103 lots + 5,296 = 19,819 exactly.

A DT tape cell holds ONE die. Twenty-five is not a modelling simplification, it is
impossible, and it is already lying on screen: `GET /api/ledger/lot_map` renders a
3,525-chip lot's DT axis as SIX dots. It also makes the core link underivable - joining
through (dt_lot, dt_slot, dt_x, dt_y) would hand 25 chips the same core die.

So this script RE-MINTS `dt_x`/`dt_y` as a bijection. There is exactly room: a DT slot
receives 150 chips (25 base wafers x 6) and the DT grid is 15 x 10 = 150 cells, which is
strong evidence the original intended a bijection.

⚠️ Nothing reads `dt_x`/`dt_y` as a factor or a key - VERIFIED: `siblings_axes.json`
declares `bond_eqp`/`bond_lot`/`dt_lot`/`b_bn`/`stack_height`, the void join is
`base_id`/`bx`/`by`, and `bonding_log`'s identity is (bond_lot, bond_slot, bond_x,
bond_y). The re-mint is an UPDATE, never a re-key.

🔴 THE RE-MINT IS DONE HERE AND NOT IN `seed_syn_void_base_join`, ON PURPOSE. That
generator stays byte-identical, so re-running it with the same seed restores the original
values exactly - which turns "undo the re-mint" from a stored backup into a PREDICATE,
the same standard as every DELETE in the rollback block below.

🔴 core_slot != bond_slot, AND THE FIXTURE WAS NOT BENT TO HIDE THAT
---------------------------------------------------------------------
One bonded wafer's 141 dies genuinely arrive from 25 different core wafers, so
`core_slot` is the DT slot and differs from `bond_slot` on almost every row.

When this fixture was designed, `ledger_lots._map_envelope` applied the requested BOND
slot as the frame slot of EVERY axis, so a core coordinate was looked up against a bond
slot's frame. Setting `core_slot == bond_slot` here would have made that defect
permanently invisible - the fixture would have passed and the wrong-frame path would
never have been reachable - so the fixture was built to expose it instead and the repair
was taken as its own lane.

⚠️ THAT REPAIR HAS LANDED (lead PM, 2026-08-14) and this paragraph is history, not a
live hazard. Each axis now resolves its own slot column, `by=` axes with no slot family
report `slot_column: null` rather than borrowing the first family's, and the response
carries `slot_column` so a caller can see WHICH family the row set was narrowed by.
MEASURED here after the repair: `lot_map(row='SYN-DT-001', by='dt_lot', slot='01')`
returns `scanned=150` - exactly one DT slot's intake. Under the old code the same call
narrowed by `bond_slot` and would have returned 141. The DT axis reads `ready` on a
15x10 frame and the CORE axis `ready` on a 19x19 frame, which is the screen that could
not be drawn at all before this round.

Do not "simplify" `core_slot` to equal `bond_slot`. It would still be wrong, and it
would now also be a fixture that agrees with a bug that no longer exists.

WHAT LANDS WHERE
-----------------
🔴 BOTH TRANSFER HOPS ARE MANY-TO-MANY (product owner, 2026-08-14)
--------------------------------------------------------------------
    「본딩 → DT 여러 장 → DT 1장 → 코어 여러 장」

MEASURED before this correction landed, only ONE of the two hops had any fan-out:

    bonding base wafer -> DT slots       25 on every one of 2,575 wafers (min = max)
    DT slot -> core wafers                1 on every one of 2,865 containers

So a tape fed by several core wafers DID NOT OCCUR in this fixture, and a screen that
cannot draw one would have passed forever. `CORE_FANOUT` now declares the degree per
tape, it INCLUDES 1 (a tape really can come from one wafer, and that is the negative
case), and the shares are unequal so an even-split assumption is wrong rather than lucky.

⚠️ THE FIRST HOP STILL HAS NO VARIATION AND THIS SCRIPT CANNOT GIVE IT ANY. 25 is not a
spectrum - without a 1, a consumer that hardcodes "many" is indistinguishable from one
that reads the count. Fixing it means rewriting `bonding_log.dt_slot`, which is what the
64,375 existing `dt_slot -> package_gate` atoms were derived from; rewriting it would
make them false. Reported, not silently left.

    tier 1 - 24 bond lots (001..021 + the three excursion lots 101,102,103)
        bonding_log   UPDATE core_lot/core_slot/cx/cy + re-mint dt_x/dt_y   84,600 rows
        wafer_process 5 fab steps per core wafer                             3,000 rows
        wafer_map_metadata  a registered frame per DT wafer and core wafer   1,200 rows
        lot_event     3 splits + 2 merges, two rows each                        10 rows
        ledger        600 register + 3,000 processed_with + 654 co-load     4,254 atoms
    tier 2/3 - 6 of those lots (001,002,003 + 101,102,103 - the excursion lots are
               REQUIRED here, lead PM: the most valuable question this fixture can
               answer is which core die a void excursion came from)
        dt_log        one row per transferred die                           21,150 rows
        core_wafer_map every die on every core wafer, transferred or not    53,550 rows
                      (6 lots x 25 wafers x 357 occupied cells; the ~40% NOT transferred
                       are the denominator for "how much of this wafer was used")

AS-OF CONVENTION (lead PM approved): `bonding_log.core_lot/core_slot` are the values AS
OF DT TIME - the same convention `dt_lot`/`dt_slot` on that row already follow, so the
whole row speaks one convention. `core_wafer_map.core_lot` is the CURRENT lot. Three core
lots carry a split AFTER DT so the two disagree there and agree everywhere else; the
difference is exactly the `lot_event` walk.

Usage::

    # dry run: build everything, write nothing, print what would land
    conda run -n assy_manager python server/scripts/seed_syn_world.py

    # write (this box's dev database is `assy_manager` and it is the owner's)
    ... seed_syn_world.py --apply --i-accept-writing-to-owner-database

    # both directions, every axis
    ... seed_syn_world.py --prove

ROLLBACK - a predicate, not a list
-----------------------------------
    DELETE FROM core_wafer_map      WHERE core_lot LIKE 'SYN-CL-%';
    DELETE FROM dt_log              WHERE dt_job  LIKE 'SYN-DTJ-%';
    DELETE FROM dt_map              WHERE dt_job  LIKE 'SYN-DTJ-%';
    DELETE FROM lot_event           WHERE lot LIKE 'SYN-CL-%';
    DELETE FROM wafer_process       WHERE lot LIKE 'SYN-CL-%';
    DELETE FROM wafer_map_metadata  WHERE map_id LIKE 'SYN-CL-%' OR map_id LIKE 'SYN-DT-%';
    DELETE FROM ledger_events       WHERE source_translator_ver LIKE 'syn_world/%';
    DELETE FROM ledger_translator_cursor WHERE source = 'syn_world';
    DELETE FROM cell_sources        WHERE updated_by = 'seed_syn_world';
    DELETE FROM cell_overwrites     WHERE updated_by = 'seed_syn_world';
    -- ⚠️ the cell layers key on `row_id`; `business_key_val` is NOT a column on them, so
    -- a delete written against that name fails with UndefinedColumn rather than 0 rows.
    UPDATE bonding_log SET core_lot=NULL, core_slot=NULL, cx=NULL, cy=NULL
      WHERE bond_lot LIKE 'SYN-VOID-%';
    -- and dt_x/dt_y, which is the one UPDATE a DELETE cannot express:
    --   conda run -n assy_manager python server/scripts/seed_syn_void_base_join.py \
    --       --apply --i-accept-writing-to-owner-database
    -- that generator is pure and seeded, so it restores the original formula's values.
"""
from __future__ import annotations

import argparse
import datetime as _dt
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

# The void seeder owns the base geometry primitives. Importing it rather than respelling
# `occupied_cells` keeps "which cells exist" answered in ONE place - a second spelling of
# a coordinate rule is how two screens come to disagree about where a die is.
import seed_syn_void_base_join as vbj  # noqa: E402

# --------------------------------------------------------------------------
# Namespace. Every row and atom is reachable by one of these; that is what makes
# the rollback above a predicate.
# --------------------------------------------------------------------------
SOURCE = "syn_world"
UPDATED_BY = "seed_syn_world"
SOURCE_NAME = "custom_script"
TRANSLATOR_BASE = f"{SOURCE}/1/rules:world1"

CORE_LOT_PREFIX = "SYN-CL-"
#: 🔴 NOT MINTED HERE. `seed_syn_process_ledger` already emitted 2,575 `transferred`
#: atoms whose subject is `SYN-CW-<lot>-<slot>`; this script writes the ROWS for those
#: exact names. Changing this literal orphans the walk.
CORE_WAFER_FMT = "SYN-CW-%03d-%02d"
DT_LOT_FMT = "SYN-DT-%03d"          # already on every bonding row; NOT rewritten
DT_JOB_PREFIX = "SYN-DTJ-"
BOND_LOT_FMT = "SYN-VOID-%03d"

WHO_DT_LOG = "syn_dt_handler"
WHO_FAB_MES = "syn_fab_mes"

DERIV_FIRST_SIGHT = "first_sight"
DERIV_FAB_STEP = "fab_step"
DERIV_CO_LOAD = "co_load"
DECLARED_DERIVATIONS = frozenset({DERIV_FIRST_SIGHT, DERIV_FAB_STEP, DERIV_CO_LOAD})

FORBIDDEN_DATABASES = ("assy_manager",)
CHUNK = 1000

#: The 24 bond lots whose core axis comes alive. The other 79 stay untouched ON PURPOSE:
#: a lot whose core link is KNOWN and a lot whose core link was NEVER RECORDED are
#: different answers, and wiring all 103 removes the second one from the fixture. Same
#: denominator discipline `finding_kinds` applies to 미검사 vs 0.
TIER1_LOTS = list(range(1, 22)) + [101, 102, 103]
#: Die-level depth. The excursion lots are REQUIRED members (lead PM 2026-08-14).
DEEP_LOTS = [1, 2, 3, 101, 102, 103]
#: Core lots that split AFTER DT, so `bonding_log.core_lot` (as-of DT) and
#: `core_wafer_map.core_lot` (current) disagree and only the lot_event walk closes it.
SPLIT_LOTS = [2, 3, 102]
#: Slots that move in a split. Deterministic and a minority, so the parent keeps rows.
def moved(slot: int) -> bool:
    return slot % 3 == 0


#: The core wafer's own geometry. Bigger than the reconstituted base wafer because a core
#: wafer must supply 150 dies to its DT slot AND keep some behind - the leftovers are the
#: denominator that makes "how much of this wafer was used" answerable.
#: MEASURED sizing, not a guess. The binding constraint is the WAFER CIRCLE, not the
#: grid: at 15 mm dies the occupied count is 263 whatever the grid (19x19, 21x21, 23x23,
#: 25x25 all give 263), so growing the grid buys nothing and the die pitch is the only
#: dial. Worst-case demand on one wafer under `CORE_FANOUT` is 267 dies - primary of a
#: fan-out-1 tape (150) plus the rank-2, rank-3 and rank-4 shares of three other tapes
#: (57 + 45 + 15) - so 263 was 4 short and `lot_tapes` refused, correctly. 13 mm on a
#: 23x23 grid gives 357, a margin of 90.
CORE_SPEC = {
    "grid_cols": 23, "grid_rows": 23, "grid_start_x": 0, "grid_start_y": 0,
    "grid_y_invert": False,
    "phys_wafer_dia": 300, "phys_chip_x": 13, "phys_chip_y": 13,
    "phys_offset_x": 5, "phys_offset_y": -3, "phys_edge_margin": 3,
}
#: The DT tape grid. 15 x 10 = 150, exactly a full slot's intake.
DT_COLS, DT_ROWS = 15, 10
DT_CELLS = DT_COLS * DT_ROWS

# --------------------------------------------------------------------------
# 🔴 FAN-OUT. Product owner, 2026-08-14: 「본딩 → DT 여러 장 → DT 1장 → 코어 여러 장」
# --------------------------------------------------------------------------
#: BOTH hops are many-to-many, and MEASURED before this was built, only one of them was:
#:
#:   bonding base wafer -> DT slots        25, on every one of 2,575 wafers (min=max=25)
#:   DT slot -> core wafers                 1, on every one of 2,865 containers
#:
#: So the DT->core hop had NO fan-out at all: `SYN-CW-<L>-<S>` fed `dt_slot(<L>,<S>)` and
#: nothing else. A screen that cannot draw a tape fed by several core wafers would have
#: passed against this fixture forever, because the case never occurs in it - the same
#: argument that made 「DT 2회 경유」 worth planting (125 of 400 chains, measured).
#:
#: 🔴 AND THE FIRST HOP HAS NO VARIATION EITHER. 25 everywhere is not a spectrum; a
#: consumer that hardcodes "many" and one that reads the real count are indistinguishable
#: without a 1. This script CANNOT fix that hop - `bonding_log.dt_slot` is what the
#: existing `dt_slot -> package_gate` atoms (64,375 of them, qty 6 each) were derived
#: from, and rewriting it would falsify them. It is reported instead, and the DEGREE IT
#: CAN CONTROL carries the 1: see `CORE_FANOUT`.
#:
#: The degree is DECLARED rather than random so an answer key can assert the exact
#: number, and it deliberately includes 1 - a tape really can come from a single core
#: wafer, and 「팬아웃이 없는 경우도 정상 답」 (owner). The shares are UNEQUAL so a
#: consumer that assumes an even split is wrong rather than lucky.
CORE_FANOUT = (1, 1, 2, 3, 2, 4, 1, 2, 3, 2)
#: Share weights per contributor rank. Deliberately not equal.
FANOUT_SHARES = {1: (1.0,), 2: (0.62, 0.38), 3: (0.5, 0.3, 0.2),
                 4: (0.4, 0.3, 0.2, 0.1)}


#: 🔴 TAPES THAT MUST STAY FAN-OUT 1, AND WHY THAT IS MODELLING RATHER THAN A DODGE.
#: `seed_syn_process_ledger` wrote 290 `dt_slot -> dt_slot` RESTAGE hops: those tapes were
#: fed by ANOTHER TAPE, not from a wafer grid. Giving one of them an extra `wafer_grid ->
#: dt_slot` load says two incompatible things about the same tape, and MEASURED, it also
#: broke a stated answer key: 48 of the 290 restage targets got a co-load atom on the
#: first attempt and `seed_syn_process_ledger --prove`'s "chains passing TWO dt slots"
#: fell from 125 to 25 - the walk reached a core wafer directly and never followed the
#: restage. Restage targets are therefore pinned to 1 contributor, which is both the
#: physically correct story and what keeps that key at 125.
_RESTAGE_TARGETS = None


def restage_targets(db):
    """`{(lot:int, slot:int)}` for every tape the ledger says was fed by another tape."""
    global _RESTAGE_TARGETS
    if _RESTAGE_TARGETS is None:
        from sqlalchemy import text

        out = set()
        for lot_s, slot_s in db.execute(text("""
                SELECT DISTINCT object_payload->'to'->'keys'->>'dt_lot',
                                object_payload->'to'->'keys'->>'dt_slot'
                FROM ledger_events WHERE predicate='transferred'
                  AND object_payload->'from'->>'type'='dt_slot'
                  AND object_payload->'to'->>'type'='dt_slot'""")).fetchall():
            if lot_s and lot_s.startswith("SYN-DT-") and slot_s:
                out.add((int(lot_s[len("SYN-DT-"):]), int(slot_s)))
        _RESTAGE_TARGETS = out
    return _RESTAGE_TARGETS


def core_fanout(lot: int, slot: int) -> int:
    """How many core wafers feed DT slot (lot, slot). Declared, deterministic, includes 1."""
    if _RESTAGE_TARGETS and (lot, slot) in _RESTAGE_TARGETS:
        return 1
    return CORE_FANOUT[(lot * 7 + slot * 3) % len(CORE_FANOUT)]


#: Which core lot a tape borrows from when it reaches outside its own. Deep lots borrow
#: from deep lots so the die-level walk stays complete on both sides of the loan.
def neighbour_lot(lot: int) -> int:
    pool = DEEP_LOTS if lot in DEEP_LOTS else [n for n in TIER1_LOTS if n not in DEEP_LOTS]
    return pool[(pool.index(lot) + 1) % len(pool)]


def contributors(lot: int, slot: int):
    """The core wafers feeding this tape as `(lot, slot)`, most-significant first.

    🔴 `(lot, slot)` IS ALWAYS FIRST AND ALWAYS PRESENT. The existing ledger already
    asserts `SYN-CW-<lot>-<slot>` loaded into `dt_slot(<lot>,<slot>)`; dropping it would
    make 2,575 already-written atoms false. Fan-out is added by ADMITTING more
    contributors, never by replacing the one the chain already names.

    🔴 FIXED COPRIME STRIDES, NOT A SHUFFLE. A shuffled pick makes PARTICIPATION uneven -
    measured, it oversubscribed SYN-CW-003-05 past its die count and the die-cursor guard
    refused. 7, 13 and 19 are coprime with 25, so each wafer is the rank-2 contributor of
    exactly one tape, the rank-3 of exactly one and the rank-4 of exactly one.

    🔴 THE LAST CONTRIBUTOR OF A k>=3 TAPE COMES FROM ANOTHER CORE LOT. Without this the
    fan-out is real per tape and INVISIBLE per lot: MEASURED on the first attempt, a bond
    lot still reached exactly 25 core wafers because every contributor was one of its own
    lot's 25. A screen asking 「이 랏이 닿는 코어 프레임 목록」 would have got 25 either
    way and the many-to-many case would never have been exercised at the level a person
    actually looks at.
    """
    k = core_fanout(lot, slot)
    strides = (7, 13, 19)
    out = [(lot, slot)]
    for i in range(k - 1):
        peer = ((slot - 1 + strides[i]) % 25) + 1
        cross = (i == k - 2 and k >= 3)
        out.append((neighbour_lot(lot) if cross else lot, peer))
    return out


def cell_owners_pairs(lot: int, slot: int, n: int):
    """For each of the tape's `n` cells, which contributor slot supplied it.

    Interleaved rather than blocked, so a contributor's dies are SCATTERED across the
    tape. A blocked layout would let a consumer recover the owner from `dt_x < 60` and
    never read the stored provenance - the same reason `pick_order` is not the identity.
    """
    k = core_fanout(lot, slot)
    who = contributors(lot, slot)
    shares = FANOUT_SHARES[k]
    counts = [int(round(n * w)) for w in shares]
    counts[0] += n - sum(counts)          # the first contributor absorbs the rounding
    bag = []
    for pair, count in zip(who, counts):
        bag.extend([pair] * count)
    random.Random((SEED * 17) + lot * 31 + slot).shuffle(bag)
    if len(bag) != n:
        raise SystemExit("REFUSED: fan-out shares for k=%d do not partition %d cells "
                         "(got %d)." % (k, n, len(bag)))
    return bag

FAB_STEPS = ("DEPO", "CMP", "PHOTO", "ETCH", "CLEAN")
#: 🔴 DISJOINT FROM `seed_syn_process_ledger.STEPS` ({DIFFUSION, BONDING, MOLDING, DT}) ON
#: PURPOSE. A `processed_with` atom naming the same (subject, step) would compete with
#: that script's claims inside `claim_rank_key` and could silently win the resolution its
#: answer key depends on. Different subjects AND different steps means no contest.
FAB_KNOBS = {
    "DEPO": {"temp_c": 420, "thickness_nm": 180},
    "CMP": {"pressure": 3.5, "slurry": "SL-2", "pad": "IC1000"},
    "PHOTO": {"dose_mj": 28, "focus": 0.02},
    "ETCH": {"depth_um": 1.2, "gas": "CF4", "time_s": 90},
    "CLEAN": {"chem": "SC1", "time_s": 300},
}

SEED = 20260814
#: Every stamp this script writes sits BEFORE the excursion lots' inspection runs, so
#: `seed_syn_lot_excursion --prove`'s "the planted lots are the latest by inspection time"
#: cannot be disturbed. It reads `inspection_run`, which this script never writes, but a
#: fixture whose stamps wander into that window is one edit away from breaking it.
T0 = _dt.datetime(2026, 8, 10, 0, 0, 0, tzinfo=_dt.timezone(_dt.timedelta(hours=9)))
EVENT_TIME = T0.isoformat()


def _stamp(minutes: int) -> str:
    return (T0 + _dt.timedelta(minutes=minutes)).isoformat()


def _lot_event_time(minutes: int) -> str:
    """`lot_event.event_time` is a STRING that must sort lexicographically (its own
    declaration says so) and the translator parses it with the configured format."""
    return (T0 + _dt.timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# Geometry
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
        cells = vbj.occupied_cells(core_meta())
        if len(cells) < DT_CELLS:
            raise SystemExit(
                "REFUSED: the core wafer spec occupies %d cells but a DT slot takes up "
                "to %d. A core wafer cannot supply more dies than it has, and a fixture "
                "that pretends otherwise makes 'how much of this wafer was used' answer "
                "above 100%%." % (len(cells), DT_CELLS))
        _CORE_CELLS = cells
    return _CORE_CELLS


def pick_order(lot: int, slot: int):
    """Which core cell feeds DT cell j, as a deterministic permutation.

    🔴 NOT THE IDENTITY, ON PURPOSE. If DT cell j always came from core cell j, every
    consumer could recover the core position by arithmetic and would never exercise the
    stored correspondence - the fixture would pass while the join it exists to test was
    never used. The permutation is seeded, so it is reproducible without being guessable.
    """
    cells = core_cells()
    order = list(range(len(cells)))
    random.Random((SEED * 7919) + (lot * 1009) + slot).shuffle(order)
    return [cells[i] for i in order]


def dt_cell(j: int):
    """DT tape address for the j-th die into a slot. Bijective by construction."""
    if not 0 <= j < DT_CELLS:
        raise SystemExit(
            "REFUSED: DT cell index %d is outside the %dx%d tape grid. More dies were "
            "assigned to one slot than it holds, which is the exact defect this script "
            "exists to repair - it must not be re-introduced by the repair."
            % (j, DT_COLS, DT_ROWS))
    return j % DT_COLS, j // DT_COLS


_ALL_TAPES = None


def all_tapes():
    """EVERY tape of every seeded lot, resolved in ONE pass:
    `{(lot, slot): [(owner_lot, owner_slot, core_x, core_y)]}`.

    🔴 THE DIE CURSOR IS PER WAFER AND SPANS EVERY LOT, NOT ONE TAPE AND NOT ONE LOT.
    With fan-out a core wafer supplies its own tape, some of its lot-mates' tapes, and -
    since `contributors` reaches across lots - tapes in a NEIGHBOURING lot. A cursor
    scoped to one tape hands the wafer's cell #0 to two tapes; a cursor scoped to one lot
    hands it to two lots. Either way the fixture contains a die that was bonded twice,
    which is the exact class of defect the DT re-mint exists to remove, re-introduced one
    layer up. Resolving everything in one deterministic pass is what makes the cursor
    global, and `assert_bijection` is what proves it worked.
    """
    global _ALL_TAPES
    if _ALL_TAPES is not None:
        return _ALL_TAPES
    picks, cursor = {}, {}
    tapes = {}
    for lot in sorted(TIER1_LOTS):
        for slot in range(1, 26):
            n = DT_CELLS if slot <= 16 else 125
            plan = []
            for owner in cell_owners_pairs(lot, slot, n):
                if owner not in picks:
                    picks[owner] = pick_order(*owner)
                    cursor[owner] = 0
                if cursor[owner] >= len(picks[owner]):
                    raise SystemExit(
                        "REFUSED: core wafer %s ran out of dies (%d occupied cells) "
                        "while feeding tape (%03d, %02d). A wafer cannot supply more "
                        "dies than it has; lower the fan-out degree or widen CORE_SPEC."
                        % (CORE_WAFER_FMT % owner, len(picks[owner]), lot, slot))
                plan.append(owner + picks[owner][cursor[owner]])
                cursor[owner] += 1
            tapes[(lot, slot)] = plan
    _ALL_TAPES = tapes
    return tapes


def tape_plan(lot: int, slot: int):
    return all_tapes()[(lot, slot)]


def transferred_shares(lot: int, slot: int):
    """((owner_lot, owner_slot), dies supplied) for one tape - what a load hop must say."""
    counts = {}
    for owner_lot, owner_slot, _x, _y in tape_plan(lot, slot):
        counts[(owner_lot, owner_slot)] = counts.get((owner_lot, owner_slot), 0) + 1
    return sorted(counts.items())


def core_lot_at_dt(lot: int) -> str:
    """The lot the wafer was in when DT ran. Splits happen after DT, so: the parent."""
    return CORE_LOT_PREFIX + "%03d" % lot


def core_lot_now(lot: int, slot: int) -> str:
    """The lot the wafer is in TODAY. Differs from the above only on moved slots."""
    if lot in SPLIT_LOTS and moved(slot):
        return CORE_LOT_PREFIX + "%03d-A1" % lot
    return CORE_LOT_PREFIX + "%03d" % lot


# --------------------------------------------------------------------------
# Row builders - pure, so the dry run checks exactly what --apply would write
# --------------------------------------------------------------------------


def bonding_updates(db, lot: int, audit=None):
    """Re-mint (dt_x, dt_y) as a bijection and resolve (core_lot, core_slot, cx, cy).

    `audit` collects `(dt_address, core_address)` per chip for `assert_bijection`; the
    addresses cannot be recovered from the update dicts because `dt_lot`/`dt_slot` are
    deliberately not written.

    The rank comes from the database rather than from a reconstruction of the original
    generator's `index`, so the bijection holds by construction even if that generator
    ever changes: `row_number()` over the partition IS the assignment.
    """
    from sqlalchemy import text

    if audit is None:
        audit = []
    rows = db.execute(text("""
        SELECT bond_lot, bond_slot, bond_x, bond_y, dt_lot, dt_slot,
               row_number() OVER (PARTITION BY dt_lot, dt_slot
                                  ORDER BY bond_slot, bond_x, bond_y) - 1 AS j
        FROM bonding_log WHERE bond_lot = :lot
    """), {"lot": BOND_LOT_FMT % lot}).fetchall()

    tapes = {}
    out = []
    for bond_lot, bond_slot, bond_x, bond_y, dt_lot, dt_slot, j in rows:
        j = int(j)
        dt_x, dt_y = dt_cell(j)
        slot_no = int(dt_slot)
        if slot_no not in tapes:
            tapes[slot_no] = tape_plan(lot, slot_no)
        owner_lot, owner_slot, core_x, core_y = tapes[slot_no][j]
        out.append({
            "bond_lot": bond_lot, "bond_slot": bond_slot,
            "bond_x": bond_x, "bond_y": bond_y,
            "dt_x": dt_x, "dt_y": dt_y,
            # 🔴 the CONTRIBUTOR's lot and slot, not the tape's. With fan-out these
            # differ, and a fixture that let them stay equal would hide every consumer
            # that confuses "which tape" with "which core wafer".
            "core_lot": core_lot_at_dt(owner_lot), "core_slot": "%02d" % owner_slot,
            "cx": core_x, "cy": core_y,
        })
        # The two addresses the bijection assertions need. `dt_lot`/`dt_slot` are NOT in
        # the update dict - they are unchanged, and writing an unchanged value would cost
        # 169,200 cell rows to say nothing.
        audit.append(((dt_lot, dt_slot, dt_x, dt_y),
                      (core_lot_at_dt(owner_lot), "%02d" % owner_slot, core_x, core_y)))
    return out


def dt_log_rows(lot: int):
    """One row per die that actually moved onto a tape. The UTTERANCE of the transfer."""
    rows = []
    for slot in range(1, 26):
        dt_lot, dt_slot = DT_LOT_FMT % lot, "%02d" % slot
        job = "%s%03d-%02d" % (DT_JOB_PREFIX, lot, slot)
        for j, (owner_lot, owner_slot, core_x, core_y) in enumerate(tape_plan(lot, slot)):
            dt_x, dt_y = dt_cell(j)
            rows.append({
                "dt_job": job, "dt_eqp": "SYN-DTE-%02d" % (1 + (lot % 3)),
                "product": "SYN-PRD-A",
                "dt_lot": dt_lot, "dt_slot": dt_slot,
                "dt_x": dt_x, "dt_y": dt_y, "dt_index": j + 1,
                # 🔴 the lot AS OF DT TIME - what the handler could have known - and the
                # CONTRIBUTOR's lot, slot and wafer, which is the whole point of these
                # columns existing: one DT wafer mixes dies from several core wafers, in
                # general from several core LOTS, so the map's own key cannot recover
                # where a die came from.
                "core_lot": core_lot_at_dt(owner_lot), "core_slot": "%02d" % owner_slot,
                "core_wafer": CORE_WAFER_FMT % (owner_lot, owner_slot),
                "core_x": core_x, "core_y": core_y,
                "c_bn": "1", "event_time": _stamp(slot * 7),
            })
    return rows


def core_wafer_map_rows(lot: int):
    """Every die on the core wafer - transferred or not. The leftovers ARE the denominator."""
    # A wafer's dies can leave on SEVERAL tapes (it may be a minor contributor to a
    # neighbouring slot's tape), so "taken" is collected across every tape of the lot
    # rather than from this wafer's own slot alone.
    # 🔴 SCANNED OVER EVERY TAPE OF EVERY LOT, not this lot's. A wafer's dies can leave on
    # a NEIGHBOURING LOT's tape (see `contributors`), so a lot-scoped scan would mark
    # those dies as never transferred and the "how much of this wafer was used"
    # denominator would be wrong in the safe-looking direction.
    taken_by_wafer = {}
    for (_tl, _ts), plan in all_tapes().items():
        for owner_lot, owner_slot, core_x, core_y in plan:
            taken_by_wafer.setdefault((owner_lot, owner_slot), set()).add((core_x, core_y))
    rows = []
    for slot in range(1, 26):
        wafer = CORE_WAFER_FMT % (lot, slot)
        taken = taken_by_wafer.get((lot, slot), set())
        for (x, y) in core_cells():
            rows.append({
                # 🔴 the CURRENT lot, which is where it differs from dt_log above
                "core_lot": core_lot_now(lot, slot), "core_slot": "%02d" % slot,
                "core_x": x, "core_y": y,
                "c_bn": "1" if (x, y) in taken else "9",
                "wafer_id": wafer, "event_time": _stamp(slot * 7),
            })
    return rows


def wafer_process_rows(lot: int):
    rows = []
    for slot in range(1, 26):
        wafer = CORE_WAFER_FMT % (lot, slot)
        rng = random.Random((SEED * 31) + lot * 101 + slot)
        for i, step in enumerate(FAB_STEPS):
            start = T0 - _dt.timedelta(days=3) + _dt.timedelta(minutes=90 * i + slot)
            end = start + _dt.timedelta(minutes=45)
            rows.append({
                "proc_id": "SYN-WP-%03d-%02d-%s" % (lot, slot, step),
                "wafer_id": wafer,
                "lot": core_lot_now(lot, slot), "slot": "%02d" % slot,
                "lot_id": core_lot_now(lot, slot), "slot_no": "%02d" % slot,
                "step": step, "eqp_id": "SYN-FE-%02d" % (1 + (i * 3 + slot) % 8),
                "start_time": start.strftime("%Y-%m-%d %H:%M"),
                "end_time": end.strftime("%Y-%m-%d %H:%M"),
                "result": "FAIL" if rng.random() < 0.08 else "PASS",
                "eventtime": T0.strftime("%Y-%m-%d %H:%M"),
                "recipe_id": "SYN-R-%s-01" % step,
                "knobs": json.dumps(FAB_KNOBS[step]),
            })
    return rows


def frame_map_id(lot_col, slot_col, lot, slot):
    """The frame identity, composed the way the READER composes it — one spelling.

    `ledger_lots._map_identity` calls the same function with the same binding. Writing the
    id by string formatting here is what produced `_07` against a reader asking for `_7`.
    """
    import map_overlay
    return map_overlay.compose_map_id([lot_col, slot_col],
                                      {lot_col: lot, slot_col: slot},
                                      {"table": "bonding_log"})


def frame_rows():
    """A registered grid for every DT wafer and every core wafer.

    🔴 KEYED THE WAY `ledger_lots._frame` LOOKS THEM UP: `target_table` is the ATTRIBUTION
    RELATION (`bonding_log`, the table the declared bridge lands on). Registering them
    under `dt_log` or `core_wafer_map` would be the intuitive choice and would never be
    found.

    🔴 THE SENTENCE ABOVE USED TO CLAIM THE map_id WAS KEYED THAT WAY TOO, AND IT WAS NOT.
    It said f"{frame_lot}_{frame_slot}" and then wrote "%02d", so every DT and core frame
    landed as `SYN-DT-101_07` while the reader — composing from `bonding_log`'s own
    `dt_slot`, a `double precision` — looked up `SYN-DT-101_7.0`. MEASURED 2026-08-23:
    zero of the 1,200 were reachable, and the claim in this docstring is what made the
    defect invisible for months. Both sides now compose through `map_overlay.compose_map_id`
    with `bonding_log` as the binding, so the declared column type ("number") decides the
    spelling in ONE place and a second spelling cannot be introduced by editing one side.
    """
    dt_meta = {"grid_cols": DT_COLS, "grid_rows": DT_ROWS,
               "grid_start_x": 0, "grid_start_y": 0, "grid_y_invert": False,
               "phys_chip_x": 15, "phys_chip_y": 15, "phys_edge_margin": 2,
               "phys_offset_x": 0, "phys_offset_y": 0, "rotation": 0, "side": "front"}
    cm = core_meta()
    rows = []
    for lot in TIER1_LOTS:
        for slot in range(1, 26):
            rows.append({"target_table": "bonding_log",
                         "map_id": frame_map_id("dt_lot", "dt_slot",
                                                DT_LOT_FMT % lot, slot),
                         "grid_metadata": json.dumps(dt_meta)})
            rows.append({"target_table": "bonding_log",
                         "map_id": frame_map_id("core_lot", "core_slot",
                                                core_lot_at_dt(lot), slot),
                         "grid_metadata": json.dumps(cm)})
    return rows


def lot_event_rows():
    """Three splits and two merges, TWO ROWS EACH - the shape the translator requires.

    Read off `lot_event`'s own declaration and `ledger.lot_event_translator`: a split
    writes a parent row (child_lot set, parent_lot blank) and a child row (parent_lot set,
    child_lot blank), matched on (event_type, event_time, parent, child). `slot_numbers`
    and `wafer_ids` are colon-delimited and correspond POSITIONALLY with equal length -
    a mismatch does not fail loudly, it silently reattributes wafers to the wrong slots.
    """
    rows = []
    minute = 600
    for lot in SPLIT_LOTS:
        parent, child = core_lot_at_dt(lot), CORE_LOT_PREFIX + "%03d-A1" % lot
        when = _lot_event_time(minute)
        minute += 137
        moved_slots = [s for s in range(1, 26) if moved(s)]
        stay_slots = [s for s in range(1, 26) if not moved(s)]
        # A split's two rows are BOTH post-event snapshots, so no wafer is on both sides.
        rows.append({"lot": parent, "event_type": "split", "parent_lot": "",
                     "child_lot": child,
                     "slot_numbers": ":".join("%02d" % s for s in stay_slots),
                     "wafer_ids": ":".join(CORE_WAFER_FMT % (lot, s) for s in stay_slots),
                     "equipment": "SYN-STK-01", "event_time": when})
        rows.append({"lot": child, "event_type": "split", "parent_lot": parent,
                     "child_lot": "",
                     "slot_numbers": ":".join("%02d" % s for s in moved_slots),
                     "wafer_ids": ":".join(CORE_WAFER_FMT % (lot, s) for s in moved_slots),
                     "equipment": "SYN-STK-01", "event_time": when})
    # A merge's SOURCE row is a PRE-move snapshot and the destination's is POST-move, so
    # the moved wafers ARE on both sides. That asymmetry is what the translator reads.
    for src_lot, dst_lot in ((20, 21), (18, 19)):
        src, dst = core_lot_at_dt(src_lot), core_lot_at_dt(dst_lot)
        when = _lot_event_time(minute)
        minute += 149
        move = [1, 2, 3, 4]
        rows.append({"lot": src, "event_type": "merge", "parent_lot": "",
                     "child_lot": dst,
                     "slot_numbers": ":".join("%02d" % s for s in move),
                     "wafer_ids": ":".join(CORE_WAFER_FMT % (src_lot, s) for s in move),
                     "equipment": "SYN-STK-02", "event_time": when})
        rows.append({"lot": dst, "event_type": "merge", "parent_lot": src,
                     "child_lot": "",
                     "slot_numbers": ":".join("%02d" % s for s in move + [5, 6]),
                     "wafer_ids": ":".join(
                         [CORE_WAFER_FMT % (src_lot, s) for s in move]
                         + [CORE_WAFER_FMT % (dst_lot, s) for s in (5, 6)]),
                     "equipment": "SYN-STK-02", "event_time": when})
    for r in rows:
        a, b = r["slot_numbers"].split(":"), r["wafer_ids"].split(":")
        if len(a) != len(b):
            raise SystemExit(
                "REFUSED: lot_event row for %s has %d slots and %d wafer ids. They "
                "correspond POSITIONALLY; a length mismatch does not fail loudly, it "
                "reattributes wafers to the wrong slots." % (r["lot"], len(a), len(b)))
    return rows


# --------------------------------------------------------------------------
# Atoms
# --------------------------------------------------------------------------


def _atom(subject_keys, predicate, payload, occurred_at, who, derivation, raw_ref,
          molecule_ref, object_kind="value", subject_type="Wafer"):
    from ledger.envelope import Atom

    if derivation not in DECLARED_DERIVATIONS:
        raise SystemExit("REFUSED: undeclared derivation '%s'." % derivation)
    return Atom(subject_type=subject_type, subject_keys=subject_keys,
                predicate=predicate, object_kind=object_kind, object_payload=payload,
                occurred_at=occurred_at, source_who=who,
                source_translator_ver=f"{TRANSLATOR_BASE}#{derivation}",
                source_raw_ref=raw_ref, derivation=derivation,
                molecule_ref=molecule_ref)


def world_atoms():
    """`register` for the core wafers the transfer chain already names, and one
    `processed_with` per fab step.

    🔴 NO `transferred` ATOM IS EMITTED. The chain already exists (2,575 subjects,
    measured), and `object_payload` is inside the dedupe key - re-emitting the same hop
    with a coordinate added would not enrich the existing atom, it would DOUBLE it.
    """
    atoms = []
    for lot in TIER1_LOTS:
        for slot in range(1, 26):
            wafer = CORE_WAFER_FMT % (lot, slot)
            keys = {"wafer": wafer}
            mol = f"cw|{wafer}"
            # 🔴 `register` TAKES NO OBJECT and the gate enforces it (vocabulary.py:26 -
            # `object_kind IS NULL` is what the DDL's CHECK makes legal for this one
            # predicate). It asserts existence and nothing else; the wafer's lot lives in
            # `core_wafer_map` and reaches the ledger through `lot_event`'s `has_wafer`,
            # which is the predicate that actually means membership.
            atoms.append(_atom(
                keys, "register", None,
                T0 - _dt.timedelta(days=4), WHO_FAB_MES, DERIV_FIRST_SIGHT,
                f"core_wafer_map:{core_lot_now(lot, slot)}|{slot:02d}", mol,
                object_kind=None))
            for i, step in enumerate(FAB_STEPS):
                atoms.append(_atom(
                    keys, "processed_with",
                    {"step": step, "step_family": "fab",
                     "eqp": "SYN-FE-%02d" % (1 + (i * 3 + slot) % 8),
                     "recipe": {"recipe_id": "SYN-R-%s-01" % step, "rev": "1"},
                     "params_actual": FAB_KNOBS[step]},
                    T0 - _dt.timedelta(days=3) + _dt.timedelta(minutes=90 * i + slot),
                    WHO_FAB_MES, DERIV_FAB_STEP,
                    f"wafer_process:SYN-WP-{lot:03d}-{slot:02d}-{step}", mol))
    atoms.extend(co_load_atoms())
    return atoms


def co_load_atoms():
    """The EXTRA load hops fan-out creates, and only those.

    🔴 THE FIRST CONTRIBUTOR IS NOT RE-EMITTED. `seed_syn_process_ledger` already wrote
    `SYN-CW-<L>-<S> --transferred--> dt_slot(<L>,<S>)` for all 2,575 wafers, and
    `object_payload` is inside the dedupe key - a second atom for the same hop with a
    different qty would not correct the first, it would sit beside it and the residual
    fold would count the dies twice. So only contributors 2..k are uttered here, which is
    exactly the claim that was missing: MEASURED before this ran, every one of the 2,865
    dt_slot containers had EXACTLY ONE core wafer loading it.

    ⚠️ Direction check on the residual fold (`seed_syn_process_ledger --prove`): these
    atoms add INFLOW to a container and never outflow, so a residual that was >= 0 stays
    >= 0. The prove asserts no NEGATIVE residual, so this can only move it away from the
    failure.
    """
    atoms = []
    for lot in TIER1_LOTS:
        for slot in range(1, 26):
            shares = transferred_shares(lot, slot)
            if len(shares) == 1:
                continue                      # fan-out 1: nothing extra to say
            dt_lot, dt_slot = DT_LOT_FMT % lot, "%02d" % slot
            for owner, qty in shares:
                if owner == (lot, slot):
                    continue                  # already uttered, see the docstring
                wafer = CORE_WAFER_FMT % owner
                atoms.append(_atom(
                    {"wafer": wafer}, "transferred",
                    {"from": {"type": "wafer_grid", "keys": {"wafer": wafer},
                              "position": None},
                     "to": {"type": "dt_slot",
                            "keys": {"dt_lot": dt_lot, "dt_slot": dt_slot},
                            "position": None},
                     "qty": qty},
                    T0 - _dt.timedelta(days=2) + _dt.timedelta(minutes=slot * 7),
                    WHO_DT_LOG, DERIV_CO_LOAD,
                    f"dt_log:{DT_JOB_PREFIX}{lot:03d}-{slot:02d}",
                    f"cw|{wafer}"))
    return atoms


def screen(atoms):
    from ledger import gate

    # One molecule per core wafer: its `register` and its five fab steps travel together,
    # so a refusal anywhere unwinds that wafer whole rather than landing a partial history.
    by_molecule = {}
    for atom in atoms:
        by_molecule.setdefault(atom.molecule_ref, []).append(atom)
    kept = []
    for molecule_ref, members in by_molecule.items():
        try:
            with gate.building_molecule(molecule_ref):
                accepted, _ = gate.screen_molecule(
                    SOURCE, members,
                    declared_derivations=DECLARED_DERIVATIONS,
                    declared_subject_types=frozenset({"Wafer"}),
                    molecule_ref=molecule_ref, source_rows=len(members))
                kept.extend(accepted)
        except Exception as exc:  # noqa: BLE001 - the gate's own refusal type varies
            raise SystemExit("REFUSED by the ledger gate: %r (molecule %s). This is a "
                             "bug in this script, not in the gate."
                             % (exc, molecule_ref))
    return kept


def write_atoms(atoms, batch_size: int = 2000) -> dict:
    from database.database import engine
    from ledger.store import LedgerStore

    store = LedgerStore(engine, who=SOURCE)
    store.ensure_schema()
    totals = {"attempted": 0, "inserted": 0, "deduped": 0}
    for start in range(0, len(atoms), batch_size):
        chunk = atoms[start:start + batch_size]
        result = store.write_batch(
            SOURCE, TRANSLATOR_BASE, chunk,
            cursor_value={"written_through": start + len(chunk)},
            molecules=len({a.molecule_ref for a in chunk}),
            refused=0, incomplete=0, reasons={})
        for key in totals:
            totals[key] += result.get(key, 0)
    return totals


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def _batch(rows):
    from database import schemas

    return schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(updates=row, source_name=SOURCE_NAME,
                                           updated_by=UPDATED_BY) for row in rows],
        replace_map=False, scope=None)


#: 🔴 TABLES THIS SCRIPT MUST CLEAR BEFORE WRITING, AND THE PLATFORM DEFECT THAT FORCES IT
#:
#: REPRODUCED 2026-08-14 on a SINGLE row, with the discriminating case beside it:
#:
#:   core_wafer_map  (declares composite_key_source)   re-write of an existing row -> OK
#:   wafer_process   (business_key only, NO composite) re-write of an existing row -> FAIL
#:                                                     UniqueViolation uq_bk_wafer_process
#:   wafer_process   same table, a key that does NOT exist yet          -> OK (inserts)
#:
#: So `crud.apply_batch_updates` cannot UPDATE an existing row of a table declared with a
#: `business_key` and no `composite_key_source`: identity prefetch does not find it, the
#: writer takes the INSERT path, and the unique index on `business_key_val` refuses it
#: after three recovery attempts. The FIRST write of a row succeeds and every later one
#: is a hard failure - which means any operator re-ingesting such a table hits this, not
#: just this fixture.
#:
#: ⚠️ THIS DELETE IS A WORKAROUND, NOT A DESIGN. It is scoped to rows this script owns
#: (`lot LIKE 'SYN-CL-%'`) so it can never touch the 22 pre-existing `LOT-A` rows, and it
#: removes their cell layers too - otherwise the layers outlive the rows and become the
#: kind of orphan population `cell_sources` already carries 267,886 of for this same
#: table. Delete this block the day the writer can update these tables.
PRE_DELETE = {"wafer_process": "lot LIKE 'SYN-CL-%'"}


def clear_owned_rows(db, table: str) -> int:
    from sqlalchemy import text

    predicate = PRE_DELETE.get(table)
    if not predicate:
        return 0
    # ⚠️ The cell layers key on `row_id`, NOT `business_key_val` - that column does not
    # exist on `cell_sources` / `cell_overwrites`. Deleting by the business key silently
    # fails with UndefinedColumn; deleting by nothing would leave the layers orphaned.
    ids = [r[0] for r in db.execute(text(
        f"SELECT row_id FROM {table} WHERE {predicate}")).fetchall()]
    for start in range(0, len(ids), CHUNK):
        chunk = ids[start:start + CHUNK]
        for layer in ("cell_sources", "cell_overwrites"):
            db.execute(text(f"DELETE FROM {layer} WHERE table_name = :t "
                            f"AND row_id = ANY(:k)"), {"t": table, "k": chunk})
        db.execute(text(f"DELETE FROM {table} WHERE row_id = ANY(:k)"), {"k": chunk})
    db.commit()
    return len(ids)


def write_rows(db, table: str, rows: list) -> int:
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
                "column_types. Declare them before re-running; a dropped key lands as "
                "a 200 with nothing written."
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
                "Synthetic rows never go there. Point DATABASE_URL at a fixture "
                "database and re-run, or pass --i-accept-writing-to-owner-database "
                "if the owner has decided otherwise for this run." % name)
        print("!! OWNER DATABASE '%s' -- writing synthetic rows by explicit decision."
              % name)
        print("!! every row carries updated_by = '%s'" % UPDATED_BY)
        print("!! every atom carries source_translator_ver LIKE '%s%%'" % SOURCE)
    return name


def verify_prefix_is_ours(db):
    """Refuse if any namespace this script claims is already occupied by someone else."""
    from sqlalchemy import text

    checks = [
        ("core_wafer_map", "core_lot LIKE 'SYN-CL-%'"),
        ("dt_log", "dt_job LIKE 'SYN-DTJ-%'"),
        ("lot_event", "lot LIKE 'SYN-CL-%'"),
        ("wafer_process", "lot LIKE 'SYN-CL-%'"),
    ]
    taken = []
    for table, pred in checks:
        n = db.execute(text(f"SELECT count(*) FROM {table} WHERE {pred}")).scalar()
        if n:
            taken.append("%s: %d row(s) match %s" % (table, n, pred))
    if taken:
        print("   NOTE: namespace already populated (re-run is idempotent by key): %s"
              % "; ".join(taken))
    return taken


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def build(db):
    plan = {"bonding_log": [], "dt_log": [], "core_wafer_map": [],
            "wafer_process": [], "wafer_map_metadata": frame_rows(),
            "lot_event": lot_event_rows()}
    audit = []
    for lot in TIER1_LOTS:
        plan["bonding_log"].extend(bonding_updates(db, lot, audit))
        plan["wafer_process"].extend(wafer_process_rows(lot))
    plan["__audit"] = audit
    for lot in DEEP_LOTS:
        plan["dt_log"].extend(dt_log_rows(lot))
        plan["core_wafer_map"].extend(core_wafer_map_rows(lot))
    return plan


def assert_bijection(plan):
    """The defect this script repairs, asserted on the PLAN before anything is written."""
    # 🔴 THE DT ADDRESS IS (dt_lot, dt_slot, dt_x, dt_y). It is NOT
    # (core_lot, core_slot, dt_x, dt_y) - that spelling was correct only while every tape
    # had exactly one contributor, and it started reporting 16,001 false clashes the
    # moment fan-out made `core_slot` the CONTRIBUTOR's slot instead of the tape's. An
    # assertion that silently changes meaning when the model changes is worse than none.
    seen, dies = {}, {}
    for dt_addr, core_addr in plan["__audit"]:
        seen[dt_addr] = seen.get(dt_addr, 0) + 1
        dies[core_addr] = dies.get(core_addr, 0) + 1
    clashes = {k: v for k, v in seen.items() if v > 1}
    if clashes:
        first = sorted(clashes)[0]
        raise SystemExit(
            "REFUSED: %d DT cell(s) would be assigned to more than one bonded chip; "
            "first %s x%d. A tape cell holds one die - this is the exact defect the "
            "re-mint exists to remove." % (len(clashes), first, clashes[first]))
    shared = {k: v for k, v in dies.items() if v > 1}
    if shared:
        first = sorted(shared)[0]
        raise SystemExit(
            "REFUSED: %d core die(s) would be bonded more than once; first %s x%d. With "
            "fan-out a wafer feeds several tapes, so the die cursor must span the whole "
            "lot - see `lot_tapes`." % (len(shared), first, shared[first]))
    return len(seen), len(dies)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write; default is a dry run")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    ap.add_argument("--prove", action="store_true",
                    help="assert every axis in BOTH directions, then re-run the four "
                         "existing answer keys and print the comparison")
    ap.add_argument("--skip-ledger", action="store_true")
    args = ap.parse_args(argv)

    from database import crud, models
    from database.database import SessionLocal

    # 🔴 REQUIRED, and its absence does not look like a config problem. Without this the
    # first write raises "Table model for '<t>' is not initialized ... restart the
    # server/watcher processes", which reads as a deployment fault when it is only this
    # process never having built its dynamic models. `seed_syn_void_base_join` does the
    # same thing at the same point.
    models.init_dynamic_models(crud.TABLE_CONFIG)
    declared = set(crud.TABLE_CONFIG or {})
    needed = {"bonding_log", "dt_log", "dt_map", "core_wafer_map", "wafer_process",
              "lot_event", "wafer_map_metadata"}
    if needed - declared:
        raise SystemExit(
            "REFUSED: %s not declared in table_config.json. Declare them first; an "
            "undeclared table has no dynamic model and every cell written to it is "
            "dropped with a 200." % sorted(needed - declared))

    db = SessionLocal()
    try:
        name = guard_database(db, allow_owner_database=args.allow_owner or not args.apply)
        print("database: %s" % name)
        print("core wafer: %d occupied cells; DT slot takes up to %d"
              % (len(core_cells()), DT_CELLS))

        if args.prove:
            from syn_world_prove import prove
            return prove(db)

        # 🔴 BEFORE `build`. `core_fanout` consults this set, so loading it afterwards
        # would silently plan a fixture that disagrees with the one that gets written.
        pinned = restage_targets(db)
        print("restage targets pinned to fan-out 1: %d tapes (they were fed by another "
              "tape, not from a wafer grid)" % len(pinned))

        started = time.time()
        plan = build(db)
        cells, dies = assert_bijection(plan)
        print("plan built in %.1fs" % (time.time() - started))
        print("  bonding_log      %7d row updates (dt_x/dt_y re-mint + core link)"
              % len(plan["bonding_log"]))
        print("     distinct DT cells %d / distinct core dies %d - both equal the row "
              "count, so both are bijections" % (cells, dies))
        for table in ("dt_log", "core_wafer_map", "wafer_process",
                      "wafer_map_metadata", "lot_event"):
            print("  %-16s %7d rows" % (table, len(plan[table])))
        atoms = [] if args.skip_ledger else screen(world_atoms())
        extra = sum(1 for a in atoms if a.predicate == "transferred")
        print("  ledger_events    %7d atoms = register + processed_with + %d co-load "
              "`transferred`. The 2,575 PRIMARY load hops are NOT re-emitted - they "
              "already exist and payload is in the dedupe key." % (len(atoms), extra))
        degrees = {}
        for lot in TIER1_LOTS:
            for slot in range(1, 26):
                k = core_fanout(lot, slot)
                degrees[k] = degrees.get(k, 0) + 1
        print("  fan-out (core wafers per DT tape): %s"
              % ", ".join("k=%d x%d" % (k, n) for k, n in sorted(degrees.items())))

        if not args.apply:
            print("\nDRY RUN - nothing written. Add --apply "
                  "--i-accept-writing-to-owner-database to write.")
            return 0

        verify_prefix_is_ours(db)
        for table in ("wafer_map_metadata", "core_wafer_map", "dt_log",
                      "wafer_process", "lot_event", "bonding_log"):
            started = time.time()
            cleared = clear_owned_rows(db, table)
            n = write_rows(db, table, plan[table])
            db.commit()
            print("  wrote %-16s %7d changed row(s) in %.1fs%s"
                  % (table, n, time.time() - started,
                     "  (cleared %d owned row(s) first - see PRE_DELETE)" % cleared
                     if cleared else ""))
        if atoms:
            started = time.time()
            totals = write_atoms(atoms)
            print("  wrote ledger_events   %s in %.1fs" % (totals, time.time() - started))
        print("\nDONE. Rollback predicate is in this file's docstring.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
