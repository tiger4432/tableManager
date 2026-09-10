"""The void->die seam: base (x, y) is DERIVED from bond (x, y), and the fixture proves it.

Scope note, in the same spirit as `test_void_schema`: the join itself needs a real
PostgreSQL database and the suite runs on sqlite, so the JOIN is proved by
`seed_syn_void_base_join.py --prove` against `assy_qa`, not here. What IS here is
everything that can be wrong without a database - and, more importantly, the three
things an end-to-end run would NOT catch:

  * a transform that does not invert (a base coordinate nobody can re-derive is a
    base coordinate nobody can audit, and it still joins);
  * a fixture built from the IDENTITY frame only, which passes whether or not the
    transform ran at all;
  * `base_id`/`bx`/`by` drifting into `composite_key_source`, which would re-key
    every existing `bonding_log` row and un-key every feed that omits them.

The last one is a CONFIG pin, not a code test, and it is here because config is
where that mistake gets made.
"""
import io
import json
import os
import sys

import pytest

_SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _SERVER)
sys.path.insert(0, os.path.join(_SERVER, "scripts"))

import map_overlay                                                  # noqa: E402
import seed_syn_void_base_join as seed                              # noqa: E402
from database import crud                                           # noqa: E402
from parsers import void_sat_format as vsf                          # noqa: E402

# 🔴 THE SHIPPED CATALOGUE, NOT THIS BOX'S (S-126, 판정 251). This read
# `server/config/table_config.json`, which is GITIGNORED - so these cases asked what one
# machine happens to declare, and they went red the day the owner renamed their own
# columns. A test whose subject is the live declaration is measuring the box, which the
# standing gate calls a defect however green it usually is.
#
# ⚠️ AND NOT `crud.TABLE_CONFIG` EITHER, for the reason this comment already carried: that
# singleton is replaced and not restored by other modules in this suite
# (`test_runtime_table_create` monkeypatches the loader), so an assertion against it passes
# or fails by test ORDER.
_CONFIG_PATH = os.path.join(_SERVER, "config", "sample", "table_config.json.sample")
BONDING = json.load(io.open(_CONFIG_PATH, encoding="utf-8"))["bonding_log"]

DERIVED_COLUMNS = ("base_id", "bx", "by")
_KEYED_TABLES = ("void_obs", "inspection_run")


@pytest.fixture(autouse=True)
def _void_tables_declared():
    """Put the two void declarations into the singleton, then put back what was there.

    ⚠️ NOT OPTIONAL, and it failed the first time without it. `seed.scan_rows` keys a
    run through `void_sat_format.compose_run_uid` -> `crud.assemble_composite_business
    _key`, which reads `crud.TABLE_CONFIG`. Other modules in this suite REPLACE that
    singleton and do not restore it (`test_runtime_table_create` monkeypatches the
    loader), so these tests passed alone and failed in the suite - the generator
    correctly REFUSED to key a run for a table it could not see declared. Restoring
    keeps this module from becoming the next one's contamination.
    """
    declared = json.load(io.open(_CONFIG_PATH, encoding="utf-8"))
    previous = {t: crud.TABLE_CONFIG.get(t) for t in _KEYED_TABLES}
    crud.TABLE_CONFIG.update({t: declared[t] for t in _KEYED_TABLES})
    yield
    for table, value in previous.items():
        if value is None:
            crud.TABLE_CONFIG.pop(table, None)
        else:
            crud.TABLE_CONFIG[table] = value


# ---------------------------------------------------------------------------
# The config decision
# ---------------------------------------------------------------------------

def test_base_columns_are_declared():
    """🔴 REVIVED AGAINST THE SHIPPED CATALOGUE (S-127, 판정 254). S-126 retired it because
    it read THIS BOX's gitignored declaration; moved to the shipped one the statement was
    FALSE - the sample declared none of the three - and that was a FINDING, not a test to
    force green. `crud` drops an undeclared column with a 200, so on a fresh install those
    three writes went nowhere and said nothing.

    ⛔ AND THE REPOSITORY HAD ALREADY RULED, in a file nobody had read into the question:
    `migrations/add_bonding_base_join_index.sql` builds an index on
    `bonding_log (base_id, bx, by, row_id)` and its own header says 「Declare them in
    table_config.json (`column_types`, NOT `composite_key_source`) before this file is
    worth anything」. Three view scripts read the same three columns. Four tracked
    artifacts stand on this declaration.

    ⚠️ THE TYPES ARE NOT CHOSEN HERE. `void_obs` (the join partner) and `bonding_core_die`
    already declare the same triple as string/number/number; a third opinion about one
    column's type is how a join comes to return zero rows.
    """
    types = BONDING["column_types"]

    for column in DERIVED_COLUMNS:
        assert column in types, column
    assert types["base_id"] == "string"
    assert types["bx"] == "number" and types["by"] == "number"


def test_this_seed_still_cannot_fill_the_shipped_key_and_that_is_not_a_bug_here():
    """🔴 THE SECOND TRUE SENTENCE (판정 254). Declaring the three was necessary and is not
    sufficient, and the reason is not an oversight to be tidied away.

    Measured 2026-09-10: this seed writes 15 columns to `bonding_log` and the shipped
    catalogue declares 6 of them after this round. More decisively, it fills NONE of the
    five columns of the shipped composite key - so `crud.unfilled_key_columns` refuses
    every row of it on a fresh install.

    ⛔ AND FILLING THEM WOULD BE WORSE THAN LEAVING THEM. The shipped key is
    `base_lot/base_slot/bonding_index/b_wx/b_wy`, and `b_wx`/`b_wy` are DT coordinates -
    `docs/architecture/DT_CORE_FRAME_CHAINS.md` states it - while this seed's coordinates
    are BASE ones. A synthetic value invented to satisfy the key would be a key that
    identifies nothing, which is the failure `test_base_columns_are_not_key_material`
    below already refuses from the other direction.

    ⚰️ So the seed is not touched: it addresses a different unit than this table's
    identity does. Where that unit should live is S-127-b, ruled after S-120 because
    `bonding_log`'s own identity (자리 vs 웨이퍼) is that item's subject.
    """
    written = {"b_bn", "base_id", "bond_eqp", "bond_lot", "bond_slot", "bond_x", "bond_y",
               "bx", "by", "dt_x", "dt_y", "event_time", "dt_lot", "dt_slot",
               "stack_height"}

    assert written - set(BONDING["column_types"]),         "if this is empty the two vocabularies have converged - re-read S-127-b"
    assert not set(BONDING["composite_key_source"]) & written,         "the seed fills none of the key columns; a seed row cannot be keyed"


def test_base_columns_are_not_key_material():
    """🔴 THE PIN. Promoting any of these to key material re-keys all 5,296 rows.

    It would also un-key every feed that omits them - `crud.unfilled_key_columns`
    refuses a row with a blank key column, and no ingestion path fills these yet.
    The identity stays what it has always been.
    """
    # ⚠️ THE EXPECTATION WAS STALE AGAINST BOTH FILES. It named
    # `bond_lot/bond_slot/bond_x/bond_y`; the shipped catalogue - and this box - spell the
    # identity `base_lot/base_slot/bonding_index/b_wx/b_wy`. Reading the box hid the drift
    # until the owner renamed something and the case went red for the wrong reason.
    assert BONDING["composite_key_source"] == [
        "base_lot", "base_slot", "bonding_index", "b_wx", "b_wy"]
    for column in DERIVED_COLUMNS:
        assert column not in BONDING["composite_key_source"]


# ---------------------------------------------------------------------------
# The derivation
# ---------------------------------------------------------------------------

def test_the_fixture_geometry_is_declared_not_auto_registered():
    """The transform REFUSES `auto_registered` geometry, which is why the existing
    125 bonding maps cannot be backfilled. The fixture's own spec must not be that."""
    assert map_overlay.geometry_declaration(seed.base_meta()) == \
        map_overlay.GEOMETRY_DECLARED
    assert map_overlay.geometry_computable(seed.base_meta()) is None


def test_the_wafer_circle_actually_clips_the_grid():
    """A bbox equal to the whole grid cannot catch a bbox-relative coordinate bug.

    Stored cell coordinates are bounding-box relative (`map_overlay
    .make_frame_transform`'s own docstring, QA B1), so a fixture that occupies
    every cell leaves that term at zero and a broken transform looks correct.
    """
    occupied = seed.occupied_cells(seed.base_meta())
    total = seed.WAFER_SPEC["grid_cols"] * seed.WAFER_SPEC["grid_rows"]
    assert 0 < len(occupied) < total


@pytest.mark.parametrize("frame", seed.RECORDED_FRAMES)
def test_every_frame_round_trips_and_is_one_to_one(frame):
    """bond -> base -> bond, for every occupied cell of every frame."""
    to_base, to_recorded, cells = seed.base_derivation(frame)
    mapped = [to_base(x, y) for x, y in cells]
    assert len(set(mapped)) == len(cells)
    assert all(to_recorded(*b) == c for b, c in zip(mapped, cells))


@pytest.mark.parametrize("frame", [f for f in seed.RECORDED_FRAMES
                                   if f != seed.BASE_FRAME])
def test_a_non_identity_frame_moves_the_coordinate(frame):
    """The frame has to be LOAD-BEARING or the fixture proves nothing.

    If base == bond everywhere, a join on `bx`/`by` and a join on `bond_x`/`bond_y`
    return the same answer and the test that distinguishes them does not exist.
    """
    to_base, _inv, cells = seed.base_derivation(frame)
    moved = sum(1 for x, y in cells if to_base(x, y) != (x, y))
    assert moved > len(cells) // 2


def test_a_transform_that_does_not_invert_is_REFUSED(monkeypatch):
    """⚠️ The alarm, rung. A guard nobody has fired is a guard nobody can trust.

    Two separate mutations, because the two checks fail differently: collapsing the
    map breaks one-to-one, and a mismatched inverse breaks the round trip. Either
    one on its own would leave the other check unproven.
    """
    real = map_overlay.make_frame_transform

    def collapse(src, dst, *a, **k):
        return lambda x, y: (0, 0)

    monkeypatch.setattr(map_overlay, "make_frame_transform", collapse)
    with pytest.raises(SystemExit, match="one-to-one"):
        seed.base_derivation("rot90_front")

    def wrong_inverse(src, dst, *a, **k):
        fn = real(src, dst)
        # Forward is genuine; the inverse is a DIFFERENT frame's, so every cell
        # round-trips to the wrong place while both directions stay bijective.
        if dst.get("rotation") == 0 and dst.get("side") == "front":
            return fn
        return real(src, dict(dst, rotation=(dst.get("rotation", 0) + 90) % 360))

    monkeypatch.setattr(map_overlay, "make_frame_transform", wrong_inverse)
    with pytest.raises(SystemExit, match="round-trip"):
        seed.base_derivation("rot90_front")


# ---------------------------------------------------------------------------
# The rows
# ---------------------------------------------------------------------------

def test_generated_rows_carry_a_derived_base_never_an_invented_one():
    frame, base_id, rows = seed.bonding_rows(1, 1, 20260813)
    to_base, _inv, _cells = seed.base_derivation(frame)
    assert rows
    for row in rows:
        assert row["base_id"] == base_id
        assert (row["bx"], row["by"]) == to_base(row["bond_x"], row["bond_y"])


def test_the_two_negative_cases_really_cannot_join():
    """The rows that must return zero, checked against the fixture they sit in."""
    frame, base_id, bond = seed.bonding_rows(1, 1, 20260813)
    _runs, _voids, negatives = seed.scan_rows(1, 1, 20260813, bond, scan_every=5)
    cases = {n["case"]: n for n in negatives}

    no_die = cases["no_die_at_base_position"]
    occupied = {(r["bx"], r["by"]) for r in bond if r["base_id"] == no_die["base_wafer_id"]}
    assert (no_die["base_x"], no_die["base_y"]) not in occupied

    above = cases["gate_above_stack"]
    here = [r for r in bond if (r["bx"], r["by"]) == (above["base_x"], above["base_y"])]
    assert len(here) == 1
    assert above["stack_gate"] > here[0]["stack_height"]


def test_the_fixture_survives_the_ingest_gate_it_would_arrive_through():
    """A fixture its own ingestion path refuses is a file waiting to fail in `err/`.

    `screen` is the gate `void_sat_format` puts every real SAT row through, so
    running the generated rows through it pins the fixture to the same four
    refusals (unkeyed row, duplicate location, undeclared unit, non-integral gate).
    """
    try:
        vsf.reset_counters()
        _frame, _base_id, bond = seed.bonding_rows(2, 3, 20260813)
        runs, voids, _neg = seed.scan_rows(2, 3, 20260813, bond, scan_every=5)
        assert runs and voids
        for table, rows in (("inspection_run", runs), ("void_obs", voids)):
            kept, report = vsf.screen(table, rows, source="test")
            assert report["refused_rows"] == 0, report["details"][:3]
            assert len(kept) == len(rows)
    finally:
        vsf.reset_counters()
