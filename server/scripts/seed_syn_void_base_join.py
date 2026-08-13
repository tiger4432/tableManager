"""Synthetic base-coordinate bonding wafers, the SAT scans on them, and the join.

WHAT THIS CLOSES
----------------
`void_obs` addresses a package by ``(base_wafer_id, base_x, base_y, stack_gate)``.
`bonding_log` had nothing to meet it with: `base_id`/`bx`/`by` existed as physical
columns in both dev databases and were filled 0 / 5,296. This script fills them for
its OWN synthetic wafers and puts voids on the same base coordinates, so
"which die is under this void" becomes a query that returns rows.

🔴 BASE (x, y) IS DERIVED, NOT INVENTED (product owner 2026-08-13)
------------------------------------------------------------------
base (x, y) is bond (x, y) put through the frame transform declared by that map's
`wafer_map_metadata` row. It is NOT a second, independent coordinate system, and a
fixture that minted one would be internally incoherent - every join built on it
would prove nothing. So this script never writes a base coordinate it did not
COMPUTE from the bond coordinate sitting in the same row.

The computation is the project's existing primitive and not a second spelling of it::

    recorded_meta = dt_map_derivation.source_meta_for_frame(base_meta, frame)
    to_base       = map_overlay.make_frame_transform(recorded_meta, base_meta)
    bx, by        = to_base(bond_x, bond_y)

A second implementation of a coordinate transform is how two screens come to
disagree about where a die is; `map_overlay` and `map_alignment` are read-only here.

🔴 THE FRAME IS LOAD-BEARING, AND THAT IS THE POINT
---------------------------------------------------
If the declared frame is wrong the transform still succeeds and still produces a
coordinate that joins - to the WRONG die. Nothing raises. That is the same failure
class `bonding_log`'s own config comment warns about for dt_lot, one layer up. So:

  * the frame each wafer used is DECLARED, and it is declared in the one place that
    already means "which frame are these stored coordinates in" - the map's
    `wafer_map_metadata` row (`rotation` + `side`). Nothing here invents a second
    home for that fact.
  * the derivation is checked to ROUND-TRIP (bond -> base -> bond) for every cell
    before a row is written. A transform that does not invert is one nobody can audit,
    and `--apply` REFUSES rather than writing coordinates it cannot reproduce.
  * `--prove` runs the same bond coordinate through a DIFFERENT frame and shows the
    join answer change. A frame test that is not run is an assumption.

WHY NEW WAFERS RATHER THAN A BACKFILL OF THE 5,296
--------------------------------------------------
The existing `bonding_log` maps carry `auto_registered: true` metadata (measured on
assy_qa: 125 of them, `phys_chip_x`/`phys_chip_y` = 1, `phys_wafer_dia` = 300).
`map_overlay.geometry_computable` REFUSES that token by name - "값은 있지만 선언이
아니다" - so the transform cannot run on those maps at all. Backfilling them is
therefore blocked on somebody DECLARING their geometry, which is a decision about
real wafers, not a fixture's to make. These synthetic wafers declare theirs.

THE ONE MODELLING CHOICE, NAMED
-------------------------------
`stack_height` is the LAYER NUMBER - the same axis as SAT's `gate`. Product owner,
2026-08-13 ("stack height 층번호"). So a void at `stack_gate` belongs to the die at
that layer and nowhere else: ``stack_gate = stack_height``.

🔴 THIS WAS WRITTEN THE OTHER WAY FIRST, AND THE REASONING IS WORTH KEEPING because
it is a trap that reads as diligence. The first version inferred "height, a count"
from the business key: (bond_lot, bond_slot, bond_x, bond_y) omits `stack_height`, so
one base position holds exactly one row - "which it could not if the column were a
layer index". That inference is backwards. The key IS defective, measured and pinned
by `c1aa1b9` (twelve dies in, one row out), so it is evidence about an unrepaired
declaration and NOT about what the column means. Reading a schema's current shape as
a statement about the domain is how a fixture inherits the defect it exists to expose.

The cost of the correct reading is visible rather than hidden, which is the point:
on this fixture ``<=`` joins 8,607 voids and ``=`` joins 891 of 9,110. The other
~8,200 sit at layers that have no row to belong to. ``<=`` made that disappear by
attaching voids from twelve different layers to the same single die - a join that
returns plausible rows and wrong answers. The 891 is not a worse result; it is the
measured price of `c1aa1b9`'s open defect, and the first time anyone has seen it as
a number.

`LAYER_PREDICATE` below is the single place this reading lives, so if the stack ever
becomes representable (layer in `composite_key_source`) the fixture follows in one
line.

Usage::

    # dry run - builds everything, writes nothing, still checks the round trip
    python server/scripts/seed_syn_void_base_join.py

    # write into a NAMED database. assy_manager is refused outright.
    set DATABASE_URL=postgresql://postgres:admin@localhost:5432/assy_qa
    python server/scripts/seed_syn_void_base_join.py --apply --lots 4 --slots 25

    # the deliverable: run the join and the two cases that must return nothing
    python server/scripts/seed_syn_void_base_join.py --prove
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import random
import sys
import time

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# --------------------------------------------------------------------------
# Namespace. Everything this script writes is reachable by these prefixes, so a
# reader can always tell fixture rows from the rest of the database.
# --------------------------------------------------------------------------
BOND_LOT_PREFIX = "SYN-VOID-"
BASE_ID_PREFIX = "SYN-BW-"
SOURCE_NAME, UPDATED_BY = "custom_script", "seed_syn_void_base_join"
EVENT_TIME = "2026-08-13T00:00:00+09:00"

#: 🔴 REFUSED OUTRIGHT. The owner's working stack runs against this database and
#: fixture values quoted as facts have cost this project before.
FORBIDDEN_DATABASES = ("assy_manager",)

#: The frame base (x, y) is expressed in. Every wafer's base coordinate is stated
#: against this one frame, or "base_x = 4" would mean a different die per wafer.
BASE_FRAME = "rot0_front"

#: The eight recorded frames, cycled across wafers so the fixture exercises all of
#: them. `rot0_front` is included deliberately AND is not the only one: it is the
#: case where base == bond, and a fixture built only from it would pass whether or
#: not the transform ran at all.
RECORDED_FRAMES = ("rot0_front", "rot90_front", "rot180_front", "rot270_front",
                   "rot0_back", "rot90_back", "rot180_back", "rot270_back")

#: One declared wafer spec for every synthetic base wafer. Chosen so the wafer
#: circle actually CLIPS the grid (measured: 141 of 225 cells occupied) - a fixture
#: whose bounding box is the whole grid cannot catch a bbox-relative coordinate bug,
#: which is the defect axis `make_frame_transform` exists to get right. The offset is
#: non-zero for the same reason: a centred circle is symmetric under rotation and
#: would let a broken transform look correct.
WAFER_SPEC = {
    "grid_cols": 15, "grid_rows": 15, "grid_start_x": 0, "grid_start_y": 0,
    "grid_y_invert": False,
    "phys_wafer_dia": 300, "phys_chip_x": 20, "phys_chip_y": 20,
    "phys_offset_x": 7, "phys_offset_y": -4, "phys_edge_margin": 3,
}

#: Die pitch in micrometres, from the spec above. In-chip void coordinates are
#: relative to the die and must fall inside it.
DIE_UM_X = WAFER_SPEC["phys_chip_x"] * 1000
DIE_UM_Y = WAFER_SPEC["phys_chip_y"] * 1000

#: `void_sat_format.UNITS` vocabulary. Declared per row, never defaulted.
UNIT = "um"
METHOD = "sat"

STACK_MIN, STACK_MAX = 8, 12       # matches the observed range on the real 5,296 rows
CHUNK = 1000                       # write chunk; the platform's production chunk size

#: 🔴 THE LAYER READING, in one place. See the module docstring.
LAYER_PREDICATE = "v.stack_gate = b.stack_height"

#: The deliverable. "Which die is under this void."
JOIN_SQL = """
SELECT v.void_uid, v.base_wafer_id, v.base_x, v.base_y, v.stack_gate,
       v.inchip_x, v.inchip_y, v.radius_x, v.radius_y, v.unit,
       b.bond_cell_key, b.bond_lot, b.bond_slot, b.bond_x, b.bond_y,
       b.stack_height, b.b_bn, b.dt_lot, b.dt_slot, b.dt_x, b.dt_y
FROM void_obs v
JOIN bonding_log b
  ON  b.base_id = v.base_wafer_id
 AND  b.bx      = v.base_x
 AND  b.by      = v.base_y
WHERE {layer}
"""

# --------------------------------------------------------------------------
# Geometry - one primitive, borrowed
# --------------------------------------------------------------------------


def base_meta() -> dict:
    """The canonical base frame's map meta. Geometry is DECLARED, never auto."""
    meta = dict(WAFER_SPEC)
    meta["rotation"], meta["side"] = 0, "front"
    return meta


def recorded_meta(frame: str) -> dict:
    """The map meta for coordinates RECORDED in `frame`, same wafer spec."""
    from dt_map_derivation import source_meta_for_frame

    meta = source_meta_for_frame(base_meta(), frame)
    if meta is None:
        raise SystemExit("REFUSED: '%s' is not a frame this system parses." % frame)
    return meta


def frame_for_wafer(lot: int, slot: int) -> str:
    """Deterministic frame assignment. Coprime stride so slots do not all share one."""
    return RECORDED_FRAMES[(lot * 3 + slot) % len(RECORDED_FRAMES)]


def occupied_cells(meta: dict):
    """Stored coordinates the wafer circle keeps, in `meta`'s own frame.

    Reuses the transformer `make_frame_transform` itself builds, so "which cells
    exist" and "where do they go" cannot answer from two different bounding boxes.
    """
    import map_overlay

    grid = map_overlay._grid_of(meta)
    tf = map_overlay._frame_transformer(meta, grid)
    return sorted(tf.cell_to_visual(c, r)
                  for c in range(grid["cols"]) for r in range(grid["rows"])
                  if tf.is_inside_wafer(c, r))


def base_derivation(frame: str):
    """``(to_base, to_recorded, cells)`` for one recorded frame. Refuses if it cannot invert.

    The round-trip check runs HERE, before any row exists, because a coordinate
    nobody can reproduce from its source is a coordinate nobody can audit.
    """
    import map_overlay

    rec, base = recorded_meta(frame), base_meta()
    to_base = map_overlay.make_frame_transform(rec, base)
    to_recorded = map_overlay.make_frame_transform(base, rec)
    cells = occupied_cells(rec)

    mapped = [to_base(x, y) for x, y in cells]
    if len(set(mapped)) != len(cells):
        raise SystemExit(
            "REFUSED: frame '%s' does not map its %d occupied cells one-to-one "
            "(%d distinct base coordinates). Two dies would share a base position "
            "and every void there would be ambiguous." % (frame, len(cells), len(set(mapped))))
    broken = [(c, b) for c, b in zip(cells, mapped) if to_recorded(*b) != c]
    if broken:
        raise SystemExit(
            "REFUSED: frame '%s' does not round-trip. %d of %d cells do not come "
            "back; first: bond %s -> base %s -> bond %s. Nothing was written."
            % (frame, len(broken), len(cells), broken[0][0], broken[0][1],
               to_recorded(*broken[0][1])))
    return to_base, to_recorded, cells


# --------------------------------------------------------------------------
# Row builders - pure, so the dry run checks exactly what --apply would write
# --------------------------------------------------------------------------


def _rng(seed: int, lot: int, slot: int) -> random.Random:
    """Reproducible per-wafer stream. Arithmetic, never `hash()` (salted for str)."""
    return random.Random((seed * 1_000_003) + (lot * 1009) + slot)


def bonding_rows(lot: int, slot: int, seed: int):
    """One synthetic base wafer's bonded dies, base coordinates DERIVED per row."""
    frame = frame_for_wafer(lot, slot)
    to_base, _to_recorded, cells = base_derivation(frame)
    bond_lot = "%s%03d" % (BOND_LOT_PREFIX, lot)
    bond_slot = "%02d" % slot
    base_id = "%s%03d-%02d" % (BASE_ID_PREFIX, lot, slot)
    rng = _rng(seed, lot, slot)

    # A small deterministic bin cluster so the wafer is not uniformly good. '0' is
    # the minority bin on the real rows (243 of 5,296), so the fixture matches.
    cx, cy = rng.choice(cells)
    rows = []
    for index, (bond_x, bond_y) in enumerate(cells):
        bx, by = to_base(bond_x, bond_y)
        defect = abs(bond_x - cx) + abs(bond_y - cy) <= 2 or rng.random() < 0.02
        rows.append({
            "bond_lot": bond_lot, "bond_slot": bond_slot,
            "bond_x": bond_x, "bond_y": bond_y,
            "base_id": base_id, "bx": bx, "by": by,
            "b_bn": "0" if defect else "1",
            "stack_height": STACK_MIN + ((bond_x * 5 + bond_y * 3) % (STACK_MAX - STACK_MIN + 1)),
            "dt_lot": "SYN-DT-%03d" % lot, "dt_slot": "%02d" % (1 + (index % 25)),
            "dt_x": index % WAFER_SPEC["grid_cols"],
            "dt_y": index // WAFER_SPEC["grid_cols"],
            "bond_eqp": "SYN-BD-%02d" % (1 + (lot % 4)),
            "event_time": EVENT_TIME,
        })
    return frame, base_id, rows


def unoccupied_base_cell():
    """A base coordinate inside the grid that the wafer circle EXCLUDES.

    This is the negative case with teeth: a void here is well-formed, keyed, and
    addresses a place where no die is bonded. It must return zero rows, not a
    neighbour.
    """
    grid = WAFER_SPEC
    have = set(occupied_cells(base_meta()))
    for x in range(grid["grid_cols"]):
        for y in range(grid["grid_rows"]):
            if (x + grid["grid_start_x"], y + grid["grid_start_y"]) not in have:
                return (x + grid["grid_start_x"], y + grid["grid_start_y"])
    raise SystemExit("REFUSED: this wafer spec occupies every cell, so the fixture "
                     "cannot express 'a void where no die is bonded'.")


def _stamp(day_offset: int, minutes: int) -> str:
    """An inspection time with an EXPLICIT offset. R5: never a naive stamp."""
    base = _dt.datetime(2026, 8, 13, 0, 0, 0) + _dt.timedelta(days=day_offset,
                                                              minutes=minutes)
    return base.strftime("%Y-%m-%dT%H:%M:%S") + "+09:00"


def _inchip(rng) -> tuple:
    """A void centroid inside the die, in micrometres, quantised to 0.25 um."""
    return (round(rng.uniform(50, DIE_UM_X - 50) * 4) / 4,
            round(rng.uniform(50, DIE_UM_Y - 50) * 4) / 4)


def scan_rows(lot: int, slot: int, seed: int, bond: list, scan_every: int,
              with_negatives: bool = True):
    """`(runs, voids, negatives)` for one wafer.

    A CLEAN run - one that found nothing - is generated on purpose. It is the whole
    reason `inspection_run` exists (`no void rows` vs `never scanned`), and a fixture
    with only dirty scans never exercises the denominator.
    """
    from parsers import void_sat_format

    rng = _rng(seed ^ 0x5A7, lot, slot)
    runs, voids, negatives = [], [], []
    scanned = bond[::max(1, scan_every)]

    for n, row in enumerate(scanned):
        gate = 1 + int(rng.random() * row["stack_height"])
        observed_at = _stamp(lot, n * 7 + slot * 3)
        run_uid = void_sat_format.compose_run_uid(
            row["base_id"], row["bx"], row["by"], gate, observed_at)
        if run_uid is None:
            raise SystemExit("REFUSED: could not key a run for %s (%s, %s) gate %s."
                             % (row["base_id"], row["bx"], row["by"], gate))
        runs.append({"method": METHOD, "base_wafer_id": row["base_id"],
                     "base_x": row["bx"], "base_y": row["by"], "stack_gate": gate,
                     "recipe_id": "SYN_VOID_R%d" % (1 + lot % 3),
                     "eqp_id": "SYN-SAT-%02d" % (1 + slot % 3),
                     "observed_at": observed_at})
        # ~40% of scans are clean. The denominator has to be able to say so.
        seen = set()
        for _ in range(0 if rng.random() < 0.4 else rng.randint(1, 3)):
            inchip = _inchip(rng)
            if inchip in seen:          # the parser refuses a repeat; do not emit one
                continue
            seen.add(inchip)
            voids.append({"run_uid": run_uid, "base_wafer_id": row["base_id"],
                          "base_x": row["bx"], "base_y": row["by"],
                          "stack_gate": gate,
                          "inchip_x": inchip[0], "inchip_y": inchip[1],
                          "radius_x": round(rng.uniform(0.5, 15.0), 3),
                          "radius_y": round(rng.uniform(0.5, 15.0), 3),
                          "unit": UNIT})

    if with_negatives and bond:
        # (a) a void at a base position where the circle leaves no die at all.
        nx, ny = unoccupied_base_cell()
        # (b) a void whose gate is ABOVE the stack that exists at that position.
        deep = bond[len(bond) // 2]
        for label, base_id, bxy, gate in (
                ("no_die_at_base_position", bond[0]["base_id"], (nx, ny), 3),
                ("gate_above_stack", deep["base_id"], (deep["bx"], deep["by"]),
                 int(deep["stack_height"]) + 1)):
            observed_at = _stamp(lot, 900 + slot)
            run_uid = void_sat_format.compose_run_uid(base_id, bxy[0], bxy[1],
                                                      gate, observed_at)
            runs.append({"method": METHOD, "base_wafer_id": base_id,
                         "base_x": bxy[0], "base_y": bxy[1], "stack_gate": gate,
                         "recipe_id": "SYN_VOID_NEG", "eqp_id": "SYN-SAT-NEG",
                         "observed_at": observed_at})
            void = {"run_uid": run_uid, "base_wafer_id": base_id,
                    "base_x": bxy[0], "base_y": bxy[1], "stack_gate": gate,
                    "inchip_x": 1234.5, "inchip_y": 5678.25,
                    "radius_x": 3.5, "radius_y": 2.25, "unit": UNIT}
            voids.append(void)
            # The key comes from the platform's composer, never from string
            # concatenation here - a second spelling of a key is how a row lands
            # under an identity nothing else can look up (`compose_business_key`).
            negatives.append({"case": label,
                              "void_uid": void_sat_format.compose_business_key(
                                  "void_obs", void),
                              "base_wafer_id": base_id, "base_x": bxy[0],
                              "base_y": bxy[1], "stack_gate": gate})
    return runs, voids, negatives


def screened(table: str, rows: list, source: str):
    """Run the fixture through the SAME gate ingestion uses. Refuse on any rejection.

    A fixture that its own ingestion path would refuse is not a fixture; it is a
    file waiting to fail in `err/`.
    """
    from parsers import void_sat_format

    kept, report = void_sat_format.screen(table, rows, source=source)
    if report["refused_rows"]:
        raise SystemExit(
            "REFUSED: the fixture generator produced %d row(s) that the void ingest "
            "gate rejects (%s). Example(s): %s. This is a bug in this script, not in "
            "the gate." % (report["refused_rows"], report["by_reason"],
                           "; ".join(report["details"][:3])))
    return kept


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def _batch(rows, *, replace_map=False, scope=None):
    from database import schemas

    return schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(updates=row, source_name=SOURCE_NAME,
                                           updated_by=UPDATED_BY) for row in rows],
        replace_map=replace_map, scope=scope)


def _write(db, table: str, rows: list) -> int:
    """Chunked upsert. Any silently dropped update key fails the run, loudly.

    `drop_report` is the out-parameter `apply_batch_updates` grew for exactly this:
    an undeclared column is discarded with a 200, and a fixture that lost `bx` in
    silence would look like a working join that returns nothing.
    """
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
                "column_types. Declare them before re-running; a dropped key lands "
                "as a 200 with nothing written."
                % (table, report["dropped_cells"], sorted(report.get("by_column") or {}),
                   report.get("by_reason")))
        written += len(changed or ())
    return written


def _guard_database(db, allow_owner_database=False):
    """Refuse a database this fixture must never touch. Names the one it reached.

    `allow_owner_database` is the product owner's per-run decision (2026-08-14),
    NOT a relaxation of the rule. The guard stays because the next run is not this
    run: the default still refuses, and anyone who wants the owner's database has
    to say so on the command line where it shows up in shell history and in a
    report. The license is separability -- every row written carries
    `updated_by = UPDATED_BY`, so one predicate excludes the whole fixture from any
    measurement and one DELETE removes it.
    """
    from sqlalchemy import text

    name = db.execute(text("SELECT current_database()")).scalar()
    if name in FORBIDDEN_DATABASES:
        if not allow_owner_database:
            raise SystemExit(
                "REFUSED: connected to '%s', which is the owner's working database. "
                "Synthetic rows never go there. Point DATABASE_URL at a fixture "
                "database and re-run, or pass --i-accept-writing-to-owner-database "
                "if the owner has decided otherwise for this run." % name)
        print("!! OWNER DATABASE '%s' -- writing synthetic rows by explicit "
              "decision." % name)
        print("!! every row carries updated_by = '%s'" % UPDATED_BY)
        print("!! rollback: DELETE FROM <table> WHERE updated_by = '%s'" % UPDATED_BY)
    return name


def _register_map_meta(db, wafers) -> int:
    """One `wafer_map_metadata` row per synthetic wafer, carrying its DECLARED frame.

    This is where "which frame are these stored coordinates in" already lives, so
    the fixture states its frame there rather than inventing a second home for it.
    """
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
                     "grid_metadata": json.dumps(recorded_meta(frame),
                                                 ensure_ascii=False, sort_keys=True)})
    return _write(db, "wafer_map_metadata", rows)


# --------------------------------------------------------------------------
# The proof
# --------------------------------------------------------------------------


def prove(db, limit: int = 5) -> dict:
    """Run the join, the two zero-row cases, and the frame-sensitivity case."""
    from sqlalchemy import text

    out = {}
    sql = JOIN_SQL.format(layer=LAYER_PREDICATE)

    rows = db.execute(text(
        sql + " AND v.base_wafer_id LIKE :p ORDER BY v.void_uid LIMIT :n"),
        {"p": BASE_ID_PREFIX + "%", "n": limit}).mappings().all()
    out["matched_sample"] = [dict(r) for r in rows]
    out["matched_total"] = db.execute(text(
        "SELECT count(*) FROM (" + sql + " AND v.base_wafer_id LIKE :p) s"),
        {"p": BASE_ID_PREFIX + "%"}).scalar()

    # Case 1 - a void whose base position has no bonded die. Counted from the JOIN
    # itself, not from `rowcount`: a SELECT's rowcount is driver-defined and would
    # make "zero rows" a claim about psycopg2 rather than about the data.
    out["no_die_rows"] = db.execute(text(
        "SELECT count(*) FROM (" + sql +
        " AND v.base_wafer_id LIKE :p AND NOT EXISTS ("
        " SELECT 1 FROM bonding_log b2 WHERE b2.base_id = v.base_wafer_id"
        " AND b2.bx = v.base_x AND b2.by = v.base_y)) s"),
        {"p": BASE_ID_PREFIX + "%"}).scalar()
    out["no_die_voids"] = db.execute(text(
        "SELECT count(*) FROM void_obs v WHERE v.base_wafer_id LIKE :p"
        " AND NOT EXISTS (SELECT 1 FROM bonding_log b WHERE b.base_id = v.base_wafer_id"
        " AND b.bx = v.base_x AND b.by = v.base_y)"),
        {"p": BASE_ID_PREFIX + "%"}).scalar()

    # Case 2 - the gate is above the stack that exists there.
    out["gate_above_stack_voids"] = db.execute(text(
        "SELECT count(*) FROM void_obs v JOIN bonding_log b"
        " ON b.base_id = v.base_wafer_id AND b.bx = v.base_x AND b.by = v.base_y"
        " WHERE v.base_wafer_id LIKE :p AND v.stack_gate > b.stack_height"),
        {"p": BASE_ID_PREFIX + "%"}).scalar()
    out["gate_above_stack_matched"] = db.execute(text(
        "SELECT count(*) FROM (" + sql +
        " AND v.base_wafer_id LIKE :p AND v.stack_gate > b.stack_height) s"),
        {"p": BASE_ID_PREFIX + "%"}).scalar()
    return out


def audit_from_stored_meta(db) -> dict:
    """Re-derive every stored base coordinate from bond (x, y) + the map's OWN meta.

    🔴 THIS IS THE CHECK THAT MAKES THE FIXTURE AUDITABLE. `prove_frame_matters`
    below uses this script's in-memory frame assignment, which proves only that the
    script agrees with itself. This one reads the frame back out of
    `wafer_map_metadata` - the same row anybody else would read six months from now -
    and asks whether `bx`/`by` can be reproduced from it. If it cannot, the stored
    base coordinates are unverifiable no matter how they were produced.
    """
    import json

    import map_meta_registrar
    import map_overlay
    from sqlalchemy import text

    wafers = db.execute(text(
        "SELECT DISTINCT bond_lot, bond_slot FROM bonding_log WHERE bond_lot LIKE :p"
        " ORDER BY bond_lot, bond_slot"), {"p": BOND_LOT_PREFIX + "%"}).all()

    checked = mismatched = no_meta = 0
    examples = []
    for bond_lot, bond_slot in wafers:
        map_id = map_meta_registrar.compose_map_id(
            ["bond_lot", "bond_slot"],
            {"bond_lot": bond_lot, "bond_slot": bond_slot}, "bonding_log")
        raw = db.execute(text(
            "SELECT grid_metadata FROM wafer_map_metadata"
            " WHERE target_table = 'bonding_log' AND map_id = :m"),
            {"m": map_id}).scalar()
        if not raw:
            no_meta += 1
            continue
        to_base = map_overlay.make_frame_transform(json.loads(raw), base_meta())
        for bond_x, bond_y, bx, by in db.execute(text(
                "SELECT bond_x, bond_y, bx, by FROM bonding_log"
                " WHERE bond_lot = :l AND bond_slot = :s"),
                {"l": bond_lot, "s": bond_slot}).all():
            checked += 1
            want = to_base(int(bond_x), int(bond_y))
            if (int(bx), int(by)) != want:
                mismatched += 1
                if len(examples) < 5:
                    examples.append({"map": map_id, "bond": (bond_x, bond_y),
                                     "stored": (bx, by), "re_derived": want})
    return {"maps": len(wafers), "maps_without_meta": no_meta, "cells_checked": checked,
            "mismatched": mismatched, "examples": examples}


def prove_frame_matters(db, limit: int = 3) -> list:
    """Same bond coordinate, a DIFFERENT frame: does the join answer change?

    Not an assertion about the fixture - a QUERY. For a real bonded die this takes
    its bond coordinate, re-derives base under every other frame, and asks the
    database which die each answer lands on.
    """
    from sqlalchemy import text

    rows = db.execute(text(
        "SELECT bond_lot, bond_slot, bond_x, bond_y, base_id, bx, by, stack_height,"
        " dt_lot, dt_slot FROM bonding_log WHERE bond_lot LIKE :p"
        " ORDER BY bond_lot, bond_slot, bond_x, bond_y LIMIT :n"),
        {"p": BOND_LOT_PREFIX + "%", "n": limit}).mappings().all()

    out = []
    for row in rows:
        lot = int(str(row["bond_lot"])[len(BOND_LOT_PREFIX):])
        declared = frame_for_wafer(lot, int(row["bond_slot"]))
        entry = {"bond": (row["bond_lot"], row["bond_slot"],
                          row["bond_x"], row["bond_y"]),
                 "declared_frame": declared,
                 "declared_base": (row["bx"], row["by"]),
                 "declared_lands_on": row["dt_lot"] + "/" + row["dt_slot"],
                 "under_other_frames": []}
        for frame in RECORDED_FRAMES:
            to_base, _inv, _cells = base_derivation(frame)
            bx, by = to_base(int(row["bond_x"]), int(row["bond_y"]))
            hit = db.execute(text(
                "SELECT bond_cell_key, dt_lot, dt_slot FROM bonding_log"
                " WHERE base_id = :b AND bx = :x AND by = :y"),
                {"b": row["base_id"], "x": bx, "y": by}).mappings().first()
            entry["under_other_frames"].append({
                "frame": frame, "base": (bx, by),
                "same_base_as_declared": (bx, by) == (row["bx"], row["by"]),
                "lands_on": (hit["dt_lot"] + "/" + hit["dt_slot"]) if hit else None,
            })
        out.append(entry)
    return out


# --------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Seed synthetic base-coordinate bonding wafers and the voids on them.")
    parser.add_argument("--apply", action="store_true", help="write the rows")
    parser.add_argument("--prove", action="store_true",
                        help="run the join and the cases that must return nothing")
    parser.add_argument("--lots", type=int, default=2)
    parser.add_argument("--slots", type=int, default=5, help="slots per lot (1..25)")
    parser.add_argument("--first-lot", type=int, default=1)
    parser.add_argument("--scan-every", type=int, default=5,
                        help="inspect every Nth bonded position")
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--no-negatives", action="store_true",
                        help="omit the two rows that must NOT join")
    parser.add_argument("--i-accept-writing-to-owner-database", action="store_true",
                        dest="allow_owner_database",
                        help="write into a FORBIDDEN_DATABASES name. Owner decision "
                             "only; every row stays removable by updated_by.")
    args = parser.parse_args()

    started = time.time()
    wafers, bond_all, run_all, void_all, negatives = [], [], [], [], []
    for lot in range(args.first_lot, args.first_lot + args.lots):
        for slot in range(1, args.slots + 1):
            frame, base_id, rows = bonding_rows(lot, slot, args.seed)
            runs, voids, negs = scan_rows(lot, slot, args.seed, rows,
                                          args.scan_every,
                                          with_negatives=not args.no_negatives)
            wafers.append(("%s%03d" % (BOND_LOT_PREFIX, lot), "%02d" % slot,
                           frame, base_id))
            bond_all.extend(rows)
            run_all.extend(runs)
            void_all.extend(voids)
            negatives.extend(negs)
    build_s = time.time() - started

    run_all = screened("inspection_run", run_all, source=UPDATED_BY)
    void_all = screened("void_obs", void_all, source=UPDATED_BY)

    frames_used = sorted({w[2] for w in wafers})
    print("wafers=%d  bonding rows=%d  runs=%d  voids=%d  negatives=%d"
          % (len(wafers), len(bond_all), len(run_all), len(void_all), len(negatives)))
    print("frames used (declared in wafer_map_metadata): %s" % ", ".join(frames_used))
    print("base frame: %s | cells per wafer: %d of %d (wafer circle clips the grid)"
          % (BASE_FRAME, len(bond_all) // max(1, len(wafers)),
             WAFER_SPEC["grid_cols"] * WAFER_SPEC["grid_rows"]))
    print("bond -> base -> bond round trip: verified for every cell of every frame")
    print("build time: %.2fs (%.0f bonding rows/s)"
          % (build_s, len(bond_all) / max(build_s, 1e-9)))
    for neg in negatives[:4]:
        print("  negative[%s]: base=%s (%s, %s) gate=%s"
              % (neg["case"], neg["base_wafer_id"], neg["base_x"], neg["base_y"],
                 neg["stack_gate"]))

    if not (args.apply or args.prove):
        print("DRY RUN: nothing written. Re-run with --apply.")
        return

    from database import crud, models
    from database.database import SessionLocal

    models.init_dynamic_models(crud.TABLE_CONFIG)
    db = SessionLocal()
    try:
        print("database: %s" % _guard_database(
            db, allow_owner_database=args.allow_owner_database))
        if args.apply:
            t0 = time.time()
            meta_n = _register_map_meta(db, wafers)
            bond_n = _write(db, "bonding_log", bond_all)
            run_n = _write(db, "inspection_run", run_all)
            void_n = _write(db, "void_obs", void_all)
            took = time.time() - t0
            print("WROTE wafer_map_metadata cells=%d, bonding_log cells=%d, "
                  "inspection_run cells=%d, void_obs cells=%d in %.1fs "
                  "(%.0f bonding rows/s)"
                  % (meta_n, bond_n, run_n, void_n, took,
                     len(bond_all) / max(took, 1e-9)))
        if args.prove:
            result = prove(db)
            print("\n--- THE JOIN: which die is under this void ---")
            print("matched void->die rows: %d" % result["matched_total"])
            for row in result["matched_sample"]:
                print("  void %s @ in-chip (%s, %s) %s  ->  die %s  dt=%s/%s (%s,%s)"
                      " stack_height=%s bin=%s"
                      % (row["void_uid"], row["inchip_x"], row["inchip_y"], row["unit"],
                         row["bond_cell_key"], row["dt_lot"], row["dt_slot"],
                         row["dt_x"], row["dt_y"], row["stack_height"], row["b_bn"]))
            print("\n--- MUST RETURN NOTHING ---")
            print("voids whose base position has no bonded die: %d  ->  join rows: %d"
                  % (result["no_die_voids"], max(0, result["no_die_rows"])))
            print("voids whose gate is above the stack there: %d  ->  join rows: %d"
                  % (result["gate_above_stack_voids"], result["gate_above_stack_matched"]))

            audit = audit_from_stored_meta(db)
            print("\n--- AUDIT: base re-derived from bond + the map's STORED meta ---")
            print("maps=%d (without meta: %d)  cells checked=%d  MISMATCHED=%d"
                  % (audit["maps"], audit["maps_without_meta"],
                     audit["cells_checked"], audit["mismatched"]))
            for ex in audit["examples"]:
                print("  %s bond %s stored %s re-derived %s"
                      % (ex["map"], ex["bond"], ex["stored"], ex["re_derived"]))

            print("\n--- THE FRAME IS LOAD-BEARING ---")
            for entry in prove_frame_matters(db):
                print("bond %s -> declared frame %s -> base %s (die %s)"
                      % (str(entry["bond"]), entry["declared_frame"],
                         str(entry["declared_base"]), entry["declared_lands_on"]))
                for alt in entry["under_other_frames"]:
                    if alt["same_base_as_declared"]:
                        continue
                    print("    under %-13s base %-9s -> %s"
                          % (alt["frame"], str(alt["base"]),
                             alt["lands_on"] or "NO DIE (zero rows)"))
    finally:
        db.close()


if __name__ == "__main__":
    main()
