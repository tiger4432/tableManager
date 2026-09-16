"""The dt_log -> dt_map derivation: the gate, the frame, the identity, the retraction.

WHAT THE EVIDENCE IN HERE IS, AND WHAT IT IS NOT
------------------------------------------------
PER-CELL, KEY -> VALUE. Never counts and never set-difference. Both weaker forms have
already scored a wrong answer as right in this repository:

  * a wrong frame produces the IDENTICAL cell count with every die different - four
    misread frames each yielded the same 854 total while disagreeing on 341/108/41/284
    dies;
  * set-difference is not per-cell either - a mirrored rectangle occupies the same
    dies and only the values move, which scored 16 wrong dies as 1.

So `assert_cellwise` compares the full key -> value mapping, and the differential test
shows a plausible misreading that keeps the cell count exactly equal.

THE ORACLE
----------
`map_overlay.make_frame_transform` is not assumed correct because it exists. It is
scored against `oracle_frame_transform` below, which is an independent forward
enumeration: it places every physical die, maps it into each frame, computes that
frame's own bounding box, and reads off the visual coordinate. It never calls
`map_overlay` or `WaferMapCoordinateTransformer`.

That construction is deliberate. Round-trip, injectivity and range tests are all
self-comparisons of one function and its own inverse, and they pass on broken code -
1,024 pairs did exactly that on 2026-07-26. The oracle also pins the ABSOLUTE
placement, which distance-preservation alone cannot: a uniform offset preserves every
pairwise distance, and a uniform offset is the failure mode the bounding-box term
produces when a mirror is involved.

THE FIXTURE ACTIVATES EVERY TERM
--------------------------------
Regression strength comes from a fixture that turns the defect axes ON, not from
counting combinations. This one is deliberately awkward on all of them:

  * grid 9x7        - NOT square, so a rotation that swaps the axes cannot hide
  * chip 12 x 18mm  - NOT isotropic, so `_frame_phys_params`' pitch SWAP is live
  * offset 3, -2 mm - non-zero on both axes, so the offset terms are live
  * start_x 2, start_y 3 - neither is the default 1
  * grid_y_invert   - on
  * margin 4mm      - the wafer circle genuinely CROPS the grid (bbox != 0), which is
                      the term a hand-written round trip drops
  * rot90_back      - rotation AND side both non-identity
"""

import math

import pytest

import dt_map_derivation as derivation
import map_overlay
import virtual_join.config
from chain import ingestion_worker
from chain import join_key_index
from database import crud, models

# ---------------------------------------------------------------------------
# Declarations. `dtderiv_test_` cannot collide with a user's live config - conftest
# initialises dynamic models from the REAL config at import, and a name collision
# there makes create_all skip the table and the suite fail with `no such column`.
# ---------------------------------------------------------------------------

LOG = "dtderiv_test_log"
MAP = "dtderiv_test_map"
JOBATTR = "dtderiv_test_jobattr"
FRAMEATTR = "dtderiv_test_frameattr"

TABLES = {
    LOG: {
        "business_key": "cell_key",
        "composite_key_source": ["job", "dx", "dy"],
        "composite_key_separator": "_",
        "column_types": {
            "cell_key": "string", "job": "string", "eqp": "string", "prod": "string",
            # The STORED lot/slot. Absent 40% of the time and wrong 10% of the time,
            # and seeded WRONG here on purpose. Nothing may read them for key material.
            "lot": "string", "slot": "string",
            "dx": "number", "dy": "number", "bn": "string", "orig": "string",
        },
    },
    MAP: {
        "business_key": "cell_key",
        # The settled identity: the map key is lot+slot, the cell address adds the
        # coordinates, and `job` is carried as the SOURCE without being key material.
        "composite_key_source": ["lot", "slot", "dx", "dy"],
        "composite_key_separator": "_",
        "column_types": {
            "cell_key": "string", "lot": "string", "slot": "string",
            "dx": "number", "dy": "number", "bn": "string", "job": "string",
            "orig": "string",
        },
        "map_key_columns": ["lot", "slot"],
    },
    JOBATTR: {
        "business_key": "job",
        "column_types": {"job": "string", "lot_confirmed": "string",
                         "slot_confirmed": "string"},
    },
    FRAMEATTR: {
        "business_key": "frame_key",
        "composite_key_source": ["eqp", "prod"],
        "composite_key_separator": "|",
        "column_types": {"frame_key": "string", "eqp": "string", "prod": "string",
                         "core_frame": "string", "dt_frame": "string"},
    },
}

# 🔴 [판정 440 ③ㅡ] THE DECLARATION, IN THE PRODUCT'S OWN GRAMMAR - NOT A
# NORMALIZED RULE HANDED STRAIGHT TO THE MODULE. The fixture used to stand in for
# `load_verified_rules` and return the shape that loader produces, which made the fixture
# the SECOND AUTHOR of that shape: a rule the real loader would have refused still arrived
# here fully formed. These are file entries, `expand_declaration` stands them, and the
# derivation reads what the product stood.
#
# ⚠️ ONE DECLARATION STANDS TWO RULES - `<name>` and `<name>:reference` - so the lookup
# has to match the name EXACTLY. Taking the companion would be silent: it carries the same
# `params`, so every assertion here would still pass while the gate resolved the wrong rule.
JOIN_DECLARATIONS = [
    {
        "name": derivation.CONFIRMED_JOIN_RULE, "enabled": True,
        "on": {"table": LOG}, "into": {"table": LOG},
        "key": {"unique": True},
        "derive": {"kind": "join",
                   "join": {"right_table": JOBATTR,
                            "on": [{"left": "job", "right": "job"}],
                            # 🔴 `into` DIFFERS FROM `from` ON PURPOSE, ON ONE OF THE
                            # TWO. Written the easy way - `take: [{from: x}]` - `_takes`
                            # defaults `into` to `from` and the two sides are the SAME
                            # STRING, so an assertion that `expose` is the `from` side
                            # cannot fail and says nothing. One column that renames on
                            # landing is what gives that assertion something to be wrong
                            # about; the other stays plain so both spellings are covered.
                            "take": [{"from": "lot_confirmed",
                                      "into": "lot_from_the_join"},
                                     {"from": "slot_confirmed"}]}},
    },
    {
        "name": derivation.FRAME_JOIN_RULE, "enabled": True,
        "on": {"table": LOG}, "into": {"table": LOG},
        "key": {"unique": True},
        "derive": {"kind": "join",
                   "join": {"right_table": FRAMEATTR,
                            "on": [{"left": "eqp", "right": "eqp"},
                                   {"left": "prod", "right": "prod"}],
                            # Takes BOTH frames, exactly as the live rule does. Only one
                            # may be read.
                            "take": [{"from": "core_frame"}, {"from": "dt_frame"}]}},
    },
]

# The canonical frame the map is registered in. Every term is awkward on purpose -
# see the module docstring.
CANONICAL_META = {
    "grid_cols": 9, "grid_rows": 7,
    "grid_start_x": 2, "grid_start_y": 3, "grid_y_invert": True,
    "rotation": 0, "side": "front",
    "phys_wafer_dia": 140.0, "phys_chip_x": 12.0, "phys_chip_y": 18.0,
    "phys_offset_x": 3.0, "phys_offset_y": -2.0, "phys_edge_margin": 4.0,
}

RECORDED_FRAME = "rot90_back"
# The plausible misreading: the rotation read correctly and the SIDE read wrong. It
# keeps the cell count exactly equal, which is why a count cannot catch it.
MISREAD_FRAME = "rot90_front"


@pytest.fixture()
def env(db_session, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    # The product's ONE reader of the rules file (S-180 ⓑ). Handing it the document
    # rather than the parsed rules keeps `expand_declaration` - the judge the loader uses
    # (S-244) - in the path, so a declaration this suite accepts is one the loader accepts.
    monkeypatch.setattr(ingestion_worker, "read_rules_document",
                        lambda path=None: {"document": {}, "rules": list(JOIN_DECLARATIONS),
                                           "path": None, "exists": True, "error": None})
    # 🔴 A DOUBLE FOR THE CATALOG, NOT FOR THE GATE. `unique_index_covering` reads
    # `pg_index` and answers None on any other dialect ("모르면 거부"), so on this suite's
    # SQLite the real call refuses every join. The double answers the question the catalog
    # would answer on PostgreSQL; what it must NOT do is remove the question, which is why
    # `test_a_join_key_no_unique_index_covers_is_a_named_refusal` lets it answer None.
    monkeypatch.setattr(join_key_index, "unique_index_covering",
                        lambda db, table, columns, folds=None: "uq_test_%s" % table)
    map_overlay._FRAME_TF_CACHE.clear()
    return db_session


# ---------------------------------------------------------------------------
# THE ORACLE - an independent forward enumeration. Imports nothing under test.
# ---------------------------------------------------------------------------

def _physical_dies(meta):
    """Every physical die inside the wafer circle, as 0-based (xp, yp).

    Written straight from the geometry: a die's millimetre position is its offset from
    the grid centre times the chip pitch, plus the wafer offset, and it exists when
    that position is inside the circle shrunk by the edge margin.
    """
    cols, rows = meta["grid_cols"], meta["grid_rows"]
    cc, cr = (cols - 1) / 2.0, (rows - 1) / 2.0
    limit = meta["phys_wafer_dia"] / 2.0 - meta["phys_edge_margin"]
    out = []
    for yp in range(rows):
        for xp in range(cols):
            x_mm = (xp - cc) * meta["phys_chip_x"] + meta["phys_offset_x"]
            y_mm = (cr - yp) * meta["phys_chip_y"] + meta["phys_offset_y"]
            if math.hypot(x_mm, y_mm) <= limit:
                out.append((xp, yp))
    return out


def _phys_to_frame_cell(xp, yp, rot, side, cols, rows):
    """Physical die -> that die's cell index in the frame (rot, side).

    Transcribed from the frame convention, then inverted by hand: the frame applies
    the face flip first and the rotation second, so undoing it rotates back first.
    """
    vis_cols = rows if rot in (90, 270) else cols
    vis_rows = cols if rot in (90, 270) else rows
    if rot == 0:
        c_m, r_m = xp, yp
    elif rot == 90:
        c_m, r_m = (vis_cols - 1) - yp, xp
    elif rot == 180:
        c_m, r_m = (vis_cols - 1) - xp, (vis_rows - 1) - yp
    else:
        c_m, r_m = yp, (vis_rows - 1) - xp
    c, r = c_m, r_m
    if side == "back":
        if rot in (90, 270):
            r = (vis_rows - 1) - r_m
        else:
            c = (vis_cols - 1) - c_m
    return c, r


def oracle_visual_map(meta, frame_text):
    """{physical die -> visual (x, y)} for one frame, computed from scratch.

    The bounding box is derived here too - over the frame's OWN cell set - because the
    stored coordinate is bounding-box relative, and dropping that term is the failure
    that put 12 live map pairs quietly out by twice the box origin.
    """
    rot, side = derivation.parse_frame(frame_text)
    cols, rows = meta["grid_cols"], meta["grid_rows"]
    cells = {die: _phys_to_frame_cell(die[0], die[1], rot, side, cols, rows)
             for die in _physical_dies(meta)}
    min_c = min(c for c, _r in cells.values())
    min_r = min(r for _c, r in cells.values())
    max_r = max(r for _c, r in cells.values())
    out = {}
    for die, (c, r) in cells.items():
        xv = c - min_c + meta["grid_start_x"]
        yv = (max_r - r + meta["grid_start_y"]) if meta.get("grid_y_invert") \
            else (r - min_r + meta["grid_start_y"])
        out[die] = (xv, yv)
    return out


def oracle_frame_transform(meta, source_frame, target_frame):
    """{source visual -> target visual}, matched BY DIE IDENTITY.

    Matching on the die rather than on the coordinate is what makes this an oracle
    rather than a second copy: the answer is "where did this physical die go", which
    is a fact about the wafer, not about either implementation.
    """
    src = oracle_visual_map(meta, source_frame)
    dst = oracle_visual_map(meta, target_frame)
    return {src[die]: dst[die] for die in src}


# ---------------------------------------------------------------------------
# The oracle is checked before it is used as an authority
# ---------------------------------------------------------------------------

def test_fixture_actually_activates_every_defect_axis():
    """A fixture that does not turn the defect axes on cannot catch anything.

    2026-07-26: a swap-defect fixture was chosen with chip_x == chip_y, which killed
    the very axis it was written for, and the test passed on broken code. So the
    fixture asserts about ITSELF here, before anything else runs.
    """
    m = CANONICAL_META
    assert m["grid_cols"] != m["grid_rows"], "square grid hides an axis swap"
    assert m["phys_chip_x"] != m["phys_chip_y"], "isotropic chip hides the pitch swap"
    assert m["phys_offset_x"] and m["phys_offset_y"], "zero offsets hide the offset terms"
    assert (m["grid_start_x"], m["grid_start_y"]) != (1, 1), "default starts hide start"
    assert m["grid_y_invert"] is True

    dies = _physical_dies(m)
    assert 0 < len(dies) < m["grid_cols"] * m["grid_rows"], \
        "the wafer circle must genuinely CROP the grid, or the bounding-box term is dead"

    rot, side = derivation.parse_frame(RECORDED_FRAME)
    assert rot != 0 and side != m["side"], "the recorded frame must differ on both axes"


def test_oracle_is_a_bijection_and_is_not_the_identity():
    """An oracle that quietly collapsed two dies onto one would excuse the same bug."""
    mapping = oracle_frame_transform(CANONICAL_META, RECORDED_FRAME, "rot0_front")
    assert len(set(mapping.values())) == len(mapping)
    assert any(k != v for k, v in mapping.items())


def test_oracle_preserves_die_count_across_all_eight_frames():
    """A frame change moves dies; it never creates or destroys one."""
    expected = len(_physical_dies(CANONICAL_META))
    for rot in (0, 90, 180, 270):
        for side in ("front", "back"):
            assert len(oracle_visual_map(CANONICAL_META, "rot%d_%s" % (rot, side))) \
                == expected


# ---------------------------------------------------------------------------
# SCORING the existing transform family against that oracle
# ---------------------------------------------------------------------------

def _implementation_transform(source_frame, target_meta=None):
    target_meta = target_meta or CANONICAL_META
    src_meta = derivation.source_meta_for_frame(target_meta, source_frame)
    return map_overlay.make_frame_transform(src_meta, target_meta)


def _score(source_frame, target_frame="rot0_front"):
    """(agreements, disagreements as {source visual: (implementation, oracle)})."""
    target_meta = dict(CANONICAL_META)
    rot, side = derivation.parse_frame(target_frame)
    target_meta["rotation"], target_meta["side"] = rot, side
    expected = oracle_frame_transform(CANONICAL_META, source_frame, target_frame)
    tf = _implementation_transform(source_frame, target_meta)
    agree, disagree = 0, {}
    for src_xy, want in expected.items():
        got = tuple(tf(*src_xy))
        if got == want:
            agree += 1
        else:
            disagree[src_xy] = (got, want)
    return agree, disagree


def test_transform_family_scores_against_the_oracle_per_cell():
    """The scoring the round was required to produce, per cell and not as a count.

    `make_frame_transform` has no independent verification of its own - its callers are
    `bonding_plan` and `transfer_plan`, which consume its answer rather than check it.
    This is the check.
    """
    agree, disagree = _score(RECORDED_FRAME)
    assert not disagree, (
        "implementation disagrees with the independent oracle on %d of %d dies; "
        "first few (source -> implementation vs oracle): %s"
        % (len(disagree), agree + len(disagree),
           sorted(disagree.items())[:6]))
    assert agree == len(_physical_dies(CANONICAL_META))


def test_transform_family_scores_across_all_eight_recorded_frames():
    """One frame agreeing could be luck; the pitch swap only shows on 90/270."""
    failures = {}
    for rot in (0, 90, 180, 270):
        for side in ("front", "back"):
            frame = "rot%d_%s" % (rot, side)
            _agree, disagree = _score(frame)
            if disagree:
                failures[frame] = len(disagree)
    assert not failures, "frames disagreeing with the oracle: %r" % failures


def test_oracle_would_catch_a_uniform_offset():
    """Proof that the oracle is load-bearing, not decorative.

    A uniform offset preserves every pairwise distance and every round trip, so the
    tests this repository used to rely on would pass through it untouched. The oracle
    must not.
    """
    expected = oracle_frame_transform(CANONICAL_META, RECORDED_FRAME, "rot0_front")
    shifted = {k: (v[0] + 1, v[1]) for k, v in expected.items()}
    assert shifted != expected
    disagreeing = sum(1 for k in expected if shifted[k] != expected[k])
    assert disagreeing == len(expected)


# ---------------------------------------------------------------------------
# Seeding and the per-cell evidence
# ---------------------------------------------------------------------------

JOB = "EQP1_20260804T0000_T07"
CONFIRMED_LOT = "CL-2601-001"
CONFIRMED_SLOT = "07"
# Deliberately WRONG stored values, in the notation that would fold to the confirmed
# ones if anybody applied folding. Nothing may read them.
STORED_LOT = "CL_2601_009"
STORED_SLOT = "99"


def _seed_log(db, frame_meta=None):
    """One source row per die, each carrying a value unique to its die.

    Unique values are what make the evidence per-cell. With a constant value a mirrored
    or offset placement is invisible - every cell still holds the same thing.
    """
    meta = frame_meta or CANONICAL_META
    model = models.DYNAMIC_TABLES[LOG]
    recorded = oracle_visual_map(meta, RECORDED_FRAME)
    rows = []
    for die, (xv, yv) in sorted(recorded.items()):
        rows.append(model(
            row_id="%s_%d_%d" % (JOB, xv, yv),
            business_key_val="%s_%d_%d" % (JOB, xv, yv),
            cell_key="%s_%d_%d" % (JOB, xv, yv),
            job=JOB, eqp="EQP1", prod="PRD-A",
            lot=STORED_LOT, slot=STORED_SLOT,
            dx=xv, dy=yv,
            bn="B%d-%d" % die,          # the die's own identity, carried as the value
            orig="W%d%d" % die,
        ))
    db.add_all(rows)
    db.commit()
    return recorded


def _seed_attribution(db, lot=CONFIRMED_LOT, slot=CONFIRMED_SLOT,
                      dt_frame=RECORDED_FRAME, core_frame="rot180_front"):
    jm = models.DYNAMIC_TABLES[JOBATTR]
    fm = models.DYNAMIC_TABLES[FRAMEATTR]
    db.add(jm(row_id=JOB, business_key_val=JOB, job=JOB,
              lot_confirmed=lot, slot_confirmed=slot))
    db.add(fm(row_id="EQP1|PRD-A", business_key_val="EQP1|PRD-A",
              frame_key="EQP1|PRD-A", eqp="EQP1", prod="PRD-A",
              # core_frame is present and DIFFERENT. If anything ever substitutes it,
              # the placement changes and the differential test says so.
              core_frame=core_frame, dt_frame=dt_frame))
    db.commit()


def _rows(db):
    return db.query(models.DYNAMIC_TABLES[LOG]).all()


def _derive(db, **kw):
    return derivation.derive_cells(
        db, _rows(db), source_table=LOG, target_table=MAP, source_column="job",
        value_columns=("bn",), origin_columns=("orig",),
        meta_loader=kw.pop("meta_loader", lambda _mid: dict(CANONICAL_META)), **kw)


def _cellwise(result):
    """{(lot, slot, x, y) -> value}. The evidence form: key -> value, per cell."""
    out = {}
    for item in result["updates"]:
        u = item["updates"]
        out[(u["lot"], u["slot"], u["dx"], u["dy"])] = u["bn"]
    return out


def test_derivation_places_every_die_where_the_oracle_says(env):
    """THE PER-CELL EVIDENCE: the intended die-to-value mapping, in full.

    Every key is checked against an independently computed answer and every value is
    the die's own identity, so a placement error cannot hide behind a matching count.
    """
    db = env
    _seed_log(db)
    _seed_attribution(db)

    result = _derive(db)
    got = _cellwise(result)

    expected = {}
    canonical = oracle_visual_map(CANONICAL_META, "rot0_front")
    for die, (xv, yv) in canonical.items():
        expected[(CONFIRMED_LOT, CONFIRMED_SLOT, xv, yv)] = "B%d-%d" % die

    assert got == expected, (
        "%d cell(s) differ; wrong-or-missing: %r"
        % (len(set(expected.items()) ^ set(got.items())),
           sorted(k for k in set(expected) | set(got)
                  if expected.get(k) != got.get(k))[:8]))
    assert result["held"]["total"] == 0


def test_differential_every_misread_frame_keeps_the_cell_count_identical(env):
    """THE DIFFERENTIAL, part 1: A COUNT CANNOT SEPARATE A RIGHT FRAME FROM A WRONG ONE.

    All seven misreadings of the recorded frame are derived here. Every one of them
    yields EXACTLY the same number of cells as the truth while disagreeing about which
    die holds which value. That is the phenomenon measured this week when four misread
    frames each produced the same 854 total while disagreeing on 341/108/41/284 dies -
    reproduced here rather than taken on trust.
    """
    db = env
    _seed_log(db)
    _seed_attribution(db)
    truth = _cellwise(_derive(db))
    frame_row = db.query(models.DYNAMIC_TABLES[FRAMEATTR]).one()

    moved = {}
    for rot in (0, 90, 180, 270):
        for side in ("front", "back"):
            frame = "rot%d_%s" % (rot, side)
            if frame == RECORDED_FRAME:
                continue
            # Correcting the row in place is what an operator editing the attribution
            # table actually does, and it is the trigger the revisit rule exists for.
            frame_row.dt_frame = frame
            db.commit()
            misread = _cellwise(_derive(db))
            assert len(misread) == len(truth), (
                "misreading %s changed the cell count (%d vs %d) - if a count could "
                "catch this, the whole per-cell discipline would be unnecessary"
                % (frame, len(misread), len(truth)))
            moved[frame] = sum(1 for k in truth if truth.get(k) != misread.get(k))

    assert len(moved) == 7
    assert all(v > 0 for v in moved.values()), \
        "a misreading that moves no die would make this test vacuous: %r" % moved
    assert min(moved.values()) >= len(truth) // 2, (
        "dies moved per misreading, out of %d: %r" % (len(truth), moved))


# A second, deliberately SYMMETRIC fixture. Its only job is the set-difference point;
# it trades the pitch/offset axes away to get a die set that a 180-degree misreading
# maps onto itself, which is the shape that makes set-difference lie.
SYMMETRIC_META = dict(CANONICAL_META, phys_offset_x=0.0, phys_offset_y=0.0)


def test_differential_set_difference_scores_a_wholly_wrong_map_as_zero():
    """THE DIFFERENTIAL, part 2: SET-DIFFERENCE IS NOT A PER-CELL CHECK EITHER.

    A mirrored map occupies the SAME dies and only the values move. Set-difference over
    the occupied cells therefore reports zero wrong - the failure that scored 16 wrong
    dies as 1 this week. The per-cell comparison reports the truth.

    Computed on the oracle rather than through the derivation, because the claim is
    about the shape of the evidence, not about the code path.
    """
    truth = oracle_frame_transform(SYMMETRIC_META, "rot0_front", "rot0_front")
    misread = oracle_frame_transform(SYMMETRIC_META, "rot180_front", "rot0_front")

    recorded = list(truth.keys())
    truth_cells = {p: truth[p] for p in recorded}
    misread_cells = {p: misread[p] for p in recorded}

    assert set(truth_cells.values()) == set(misread_cells.values()), \
        "the fixture must be symmetric enough that the misreading occupies the SAME cells"

    set_difference_score = len(set(truth_cells.values()) ^ set(misread_cells.values()))
    per_cell_score = sum(1 for p in recorded if truth_cells[p] != misread_cells[p])

    assert set_difference_score == 0, "set-difference sees nothing wrong"
    assert per_cell_score >= len(recorded) - 1, (
        "per-cell sees %d of %d dies wrong" % (per_cell_score, len(recorded)))


# ---------------------------------------------------------------------------
# The three-part gate. Each refusal is injected and proved to go red.
# ---------------------------------------------------------------------------

def test_no_row_is_created_when_attribution_is_missing(env):
    db = env
    _seed_log(db)
    _seed_attribution(db)
    db.query(models.DYNAMIC_TABLES[JOBATTR]).delete()
    db.commit()

    result = _derive(db)
    assert result["updates"] == []
    # A NAMED refusal, not merely an empty result.
    assert result["held"]["by_reason"] == {
        derivation.HOLD_ATTRIBUTION_MISSING: result["held"]["total"]}


def test_blank_confirmed_slot_holds_the_row_back_as_attribution_missing(env):
    """Present-but-blank is the same as absent. A blank in a key is not a key."""
    db = env
    _seed_log(db)
    _seed_attribution(db, slot="   ")
    result = _derive(db)
    assert result["updates"] == []
    assert derivation.HOLD_ATTRIBUTION_MISSING in result["held"]["by_reason"]


def test_no_row_is_created_when_the_frame_is_missing(env):
    db = env
    _seed_log(db)
    _seed_attribution(db, dt_frame=None)
    result = _derive(db)
    assert result["updates"] == []
    assert result["held"]["by_reason"] == {
        derivation.HOLD_FRAME_MISSING: result["held"]["total"]}


def test_core_frame_is_never_substituted_for_a_missing_dt_frame(env):
    """The user ruling, as a test. `core_frame` is present, readable and WRONG here.

    Filling an absent value from the neighbouring axis is the substitution that
    produced a perfectly-aligned screen with every value wrong.
    """
    db = env
    _seed_log(db)
    _seed_attribution(db, dt_frame=None, core_frame="rot90_back")
    result = _derive(db)
    assert result["updates"] == [], \
        "a readable core_frame must not rescue an absent dt_frame"
    assert derivation.HOLD_FRAME_MISSING in result["held"]["by_reason"]


def test_disagreeing_frame_evidence_refuses_rather_than_picking(env):
    """Two sources, two answers, no vote."""
    frame, reason = derivation.resolve_frame_candidates(["rot90_back", "rot0_front"])
    assert frame is None
    assert reason == derivation.HOLD_FRAME_DISAGREEMENT
    frame, reason = derivation.resolve_frame_candidates(["rot90_back", " rot90_back "])
    assert (frame, reason) == ("rot90_back", None)


def test_unreadable_frame_is_named_separately_from_a_missing_one(env):
    """Different repairs: one is 'confirm it', the other is 'it is spelled wrong'."""
    db = env
    _seed_log(db)
    _seed_attribution(db, dt_frame="rotate-90-backside")
    result = _derive(db)
    assert result["updates"] == []
    assert derivation.HOLD_FRAME_UNREADABLE in result["held"]["by_reason"]


def test_missing_target_meta_holds_back_instead_of_inventing_a_canonical_frame(env):
    db = env
    _seed_log(db)
    _seed_attribution(db)
    result = _derive(db, meta_loader=lambda _mid: None)
    assert result["updates"] == []
    assert derivation.HOLD_TARGET_META_MISSING in result["held"]["by_reason"]


def test_hold_back_reasons_are_split_and_both_are_always_reported(env):
    """One number cannot tell an operator which repair to make.

    Half the rows lack attribution and half lack a frame; the summary must carry both,
    and must print a zero rather than omitting it - an omitted reason reads exactly
    like a reason that was never checked.
    """
    db = env
    _seed_log(db)
    model = models.DYNAMIC_TABLES[LOG]
    all_rows = db.query(model).all()
    half = len(all_rows) // 2
    for row in all_rows[:half]:
        row.job = JOB + "-NOATTR"          # no attribution row exists for this job
    db.commit()
    _seed_attribution(db)
    # And remove the frame for everyone, so both reasons are live at once.
    fm = models.DYNAMIC_TABLES[FRAMEATTR]
    db.query(fm).delete()
    db.commit()
    db.add(fm(row_id="EQP1|PRD-A", business_key_val="EQP1|PRD-A",
              frame_key="EQP1|PRD-A", eqp="EQP1", prod="PRD-A",
              core_frame="rot0_front", dt_frame=None))
    db.commit()

    result = _derive(db)
    by = result["held"]["by_reason"]
    assert by.get(derivation.HOLD_ATTRIBUTION_MISSING) == half
    assert by.get(derivation.HOLD_FRAME_MISSING) == len(all_rows) - half

    line = derivation.format_holdback_summary(result["held"], result["derived"])
    assert derivation.HOLD_ATTRIBUTION_MISSING in line
    assert derivation.HOLD_FRAME_MISSING in line

    # ...and a zero is printed rather than dropped.
    empty = derivation.format_holdback_summary({"total": 0, "by_reason": {}}, 5)
    assert "%s=0" % derivation.HOLD_ATTRIBUTION_MISSING in empty
    assert "%s=0" % derivation.HOLD_FRAME_MISSING in empty


# ---------------------------------------------------------------------------
# The identity: never the stored lot/slot, canonicalised, never folded
# ---------------------------------------------------------------------------

def test_identity_comes_from_the_confirmed_columns_and_never_from_the_stored_ones(env):
    """The seeded stored lot/slot are WRONG. A fallback would be silent corruption:
    the cell count is identical either way and only the map they land in changes.

    BOTH halves are needed and the second is the one that matters. Asserting only that
    a confirmed value wins WHEN IT EXISTS leaves the dangerous case untested - a
    `confirmed or stored` fallback passes that assertion untouched, because the
    fallback never fires while the confirmed value is present. Measured: that exact
    mutation survived the first version of this test.
    """
    db = env
    _seed_log(db)
    _seed_attribution(db)
    result = _derive(db)
    lots = {i["updates"]["lot"] for i in result["updates"]}
    slots = {i["updates"]["slot"] for i in result["updates"]}
    assert lots == {CONFIRMED_LOT}
    assert slots == {CONFIRMED_SLOT}
    assert STORED_LOT not in lots and STORED_SLOT not in slots

    # ...and now remove the confirmation while the WRONG stored values stay in place.
    # This is the 10%: present, readable, and pointing at another lot's map.
    db.query(models.DYNAMIC_TABLES[JOBATTR]).delete()
    db.commit()
    absent = _derive(db)
    assert absent["updates"] == [], (
        "with no confirmation the derivation must produce nothing; it produced %d "
        "cell(s), the first as %r" % (len(absent["updates"]),
                                      absent["updates"][:1]))
    assert absent["held"]["by_reason"] == {
        derivation.HOLD_ATTRIBUTION_MISSING: absent["held"]["total"]}


def test_the_meta_is_looked_up_under_the_identity_the_registrar_composes(env):
    """WHICH map_id the derivation asks for, pinned.

    `wafer_map_metadata` rows are registered under identities composed by
    `map_meta_registrar.compose_map_id`. Composing the lookup key any other way does not
    fail loudly - it finds no meta, and every row holds back under `target_meta_missing`
    while the map sits there in the table. Nothing observes the identity unless a test
    captures it, because the loader is otherwise free to ignore its argument.
    """
    import map_meta_registrar

    db = env
    _seed_log(db)
    _seed_attribution(db)

    asked = []

    def loader(map_id):
        asked.append(map_id)
        return dict(CANONICAL_META)

    result = _derive(db, meta_loader=loader)
    assert result["derived"] > 0
    expected = map_meta_registrar.compose_map_id(
        ["lot", "slot"], {"lot": CONFIRMED_LOT, "slot": CONFIRMED_SLOT}, MAP)
    assert set(asked) == {expected}
    assert expected == "%s_%s" % (CONFIRMED_LOT, CONFIRMED_SLOT)


def test_a_partial_identity_is_refused_by_the_composition_too(env):
    """The blank gate is not the only thing standing here, and that is deliberate.

    `compose_map_id` returns None for a missing or empty part, so an identity with a
    hole is refused a second time on the way out. The two gates charge the SAME
    hold-back reason, which is why removing either one is invisible in behaviour - the
    redundancy is the point, and this test pins the second one directly.
    """
    import map_meta_registrar
    assert map_meta_registrar.compose_map_id(
        ["lot", "slot"], {"lot": CONFIRMED_LOT, "slot": ""}, MAP) is None
    assert map_meta_registrar.compose_map_id(
        ["lot", "slot"], {"lot": CONFIRMED_LOT}, MAP) is None


def test_stored_key_columns_are_structurally_excluded_from_the_payload(env):
    """Not merely unused - unavailable. The projection allowlist excludes them, so a
    fallback would have to be added to `_forbidden_fallback_columns` first."""
    db = env
    _seed_log(db)
    _seed_attribution(db)
    result = _derive(db)
    for item in result["updates"]:
        assert item["updates"]["lot"] == CONFIRMED_LOT
        assert item["updates"]["slot"] == CONFIRMED_SLOT
    forbidden = derivation._forbidden_fallback_columns(
        MAP, derivation.resolve_identity_sources(
            MAP, derivation.join_rule(db, derivation.CONFIRMED_JOIN_RULE)))
    assert forbidden == {"lot", "slot"}


def test_key_material_is_canonicalised_but_not_folded(env):
    """Spelling IS identity, so `CL-2601-001` and `CL_2601_001` are two different maps.

    Canonicalisation only: whitespace and numeric repr, never notation folding. Map
    metadata rows are registered under RAW identities, so folding here would be a data
    migration wearing a config flip's clothes.
    """
    db = env
    _seed_log(db)
    _seed_attribution(db, lot="  " + CONFIRMED_LOT + "  ", slot=" 07 ")
    result = _derive(db)
    lots = {i["updates"]["lot"] for i in result["updates"]}
    slots = {i["updates"]["slot"] for i in result["updates"]}
    assert lots == {CONFIRMED_LOT}, "surrounding whitespace must be trimmed"
    # `slot` is DECLARED string, so '07' stays '07'. Folding it to '7' would point the
    # map key at an identity no metadata row is registered under.
    assert slots == {"07"}

    underscored = CONFIRMED_LOT.replace("-", "_")
    assert map_overlay.canonical_bind_value(MAP, "lot", underscored) == underscored
    assert underscored != CONFIRMED_LOT, "the two notations must stay distinct"


def test_the_source_travels_with_the_value_but_is_not_key_material(env):
    """`job` is on every cell and in none of the keys. That is what makes the same
    physical die the same row - and what makes retraction possible at all."""
    db = env
    _seed_log(db)
    _seed_attribution(db)
    result = _derive(db)
    assert derivation.identity_columns(MAP) == ["lot", "slot"]
    assert "job" not in derivation.identity_columns(MAP)
    assert "job" not in derivation.coordinate_columns(MAP)
    assert all(i["updates"]["job"] == JOB for i in result["updates"])
    # No business_key_val: crud composes the composite key itself, and letting it do so
    # is what stops this module from disagreeing with the key crud recomposes.
    assert all("business_key_val" not in i for i in result["updates"])


def test_two_jobs_on_one_die_are_one_row_not_two(env):
    """The load-bearing consequence of keeping `dt_job` out of the identity.

    With the job in the key these would be two rows that can never merge, and the map
    would need a 'which job wins' rule that does not exist.
    """
    db = env
    _seed_log(db)
    _seed_attribution(db)
    first = _cellwise(_derive(db))

    model = models.DYNAMIC_TABLES[LOG]
    for row in db.query(model).all():
        row.job = JOB + "-RERUN"
    db.commit()
    jm = models.DYNAMIC_TABLES[JOBATTR]
    db.add(jm(row_id=JOB + "-RERUN", business_key_val=JOB + "-RERUN",
              job=JOB + "-RERUN", lot_confirmed=CONFIRMED_LOT,
              slot_confirmed=CONFIRMED_SLOT))
    db.commit()

    second = _cellwise(_derive(db))
    assert set(second.keys()) == set(first.keys()), \
        "a second job on the same dies must address the SAME cells"


# ---------------------------------------------------------------------------
# Declaration-driven, not hardcoded
# ---------------------------------------------------------------------------

def test_identity_and_coordinates_follow_the_declaration_when_it_changes(env):
    """The dev database and production disagree about this table's shape.

    Re-declaring the map key as the job - which is exactly the dev fixture's shape -
    must move the identity without a code change. A module that read `lot` because
    someone typed `lot` would be correct in only one of the two environments.
    """
    db = env
    _seed_log(db)
    _seed_attribution(db)

    crud.TABLE_CONFIG[MAP] = dict(
        TABLES[MAP], map_key_columns=["job"],
        composite_key_source=["job", "dx", "dy"])
    try:
        assert derivation.identity_columns(MAP) == ["job"]
        assert derivation.coordinate_columns(MAP) == ["dx", "dy"]
        with pytest.raises(derivation.DerivationRefused) as exc:
            derivation.resolve_identity_sources(
                MAP, derivation.join_rule(db, derivation.CONFIRMED_JOIN_RULE))
        assert exc.value.code == derivation.REFUSE_IDENTITY_UNDECLARED
    finally:
        crud.TABLE_CONFIG[MAP] = TABLES[MAP]


def test_an_undeclared_map_key_is_a_named_refusal(env):
    """Rows that belong to no map accumulate until nobody can tell a bug from normal,
    so the derivation refuses to make any."""
    crud.TABLE_CONFIG[MAP] = dict(TABLES[MAP], map_key_columns=[])
    try:
        with pytest.raises(derivation.DerivationRefused) as exc:
            derivation.identity_columns(MAP)
        assert exc.value.code == derivation.REFUSE_IDENTITY_UNDECLARED
    finally:
        crud.TABLE_CONFIG[MAP] = TABLES[MAP]


def test_a_join_key_no_unique_index_covers_is_a_named_refusal(env, monkeypatch):
    """The fan-out refusal, asked of the CATALOG and not of the declaration.

    A rule that can fan out must not run this gate: `load_attribution` keys results by
    the join key, so a second attribution row for one key would silently overwrite the
    first and one arbitrary lot would win the identity. 판정 440 ③ㅡ moved where the
    declaration is read; it did not soften this, so the question is still put to
    `unique_index_covering` - the same function the read-time seat's `verify_uniqueness`
    wraps - and a None answer is still a refusal that names the rule.
    """
    monkeypatch.setattr(join_key_index, "unique_index_covering",
                        lambda db, table, columns, folds=None: None)
    with pytest.raises(derivation.DerivationRefused) as exc:
        derivation.join_rule(env, derivation.CONFIRMED_JOIN_RULE)
    assert exc.value.code == derivation.REFUSE_JOIN_RULE_MISSING
    assert derivation.CONFIRMED_JOIN_RULE in str(exc.value), "the refusal must name the rule"
    assert "CREATE UNIQUE INDEX" in str(exc.value),         "and it must carry the next action, not just the verdict"


def test_the_gate_does_not_read_the_package_being_removed(env, monkeypatch):
    """⚰️ THIS TEST USED TO PIN THE OPPOSITE. It asserted the gate consumed
    `load_verified_rules` and not the shape-only loader, which was right while the
    read-time join existed. 판정 440 retires it, so what has to be pinned now is that
    nothing here reaches back into `virtual_join` - a seat that still did would stand
    today and break at step 4, which is the half-move this round refused to land.
    """
    called = []
    for door in ("load_verified_rules", "load_virtual_join_rules"):
        monkeypatch.setattr(virtual_join.config, door,
                            lambda *a, _d=door, **k: called.append(_d) or [])
    rule = derivation.join_rule(env, derivation.CONFIRMED_JOIN_RULE)
    assert called == [], "the gate reached back into the package being removed: %r" % called
    assert rule["right_table"] == JOBATTR


def test_the_gate_takes_the_rule_and_not_its_reference_companion(env):
    """🔴 ONE DECLARATION STANDS TWO CHAIN RULES. `expand_declaration` yields
    `<name>` and `<name>:reference`, and they carry IDENTICAL `params` - so a lookup that
    took the companion would satisfy every other assertion in this file while resolving
    the gate from the wrong rule. The name has to match exactly.
    """
    from chain import rule_shape
    stood, refusal, _notes = rule_shape.expand_declaration(JOIN_DECLARATIONS[0], TABLES)
    assert refusal is None
    names = [r.get("name") for r in stood]
    assert len(names) == 2 and names[0] == derivation.CONFIRMED_JOIN_RULE, names
    assert names[1] != names[0], "the companion must be distinguishable by name"

    assert derivation.join_rule(env, derivation.CONFIRMED_JOIN_RULE)["name"] ==         derivation.CONFIRMED_JOIN_RULE


def test_the_gate_matches_the_name_exactly_and_not_as_a_prefix(env, monkeypatch):
    """⚰️ THE ORDER WAS DOING THE WORK, NOT THE COMPARISON. Loosening the lookup to
    `startswith` left the suite GREEN - the exactly-named rule simply comes first, so the
    wrong comparison never got to be wrong. Ordering is not a guarantee: `<name>` and
    `<name>:reference` come out of one declaration, and any future companion or a rule an
    operator names with the same stem would resolve this gate from the wrong declaration,
    silently, because the companion carries identical `params`.

    So this asks the question ordering cannot answer: with ONLY a longer-named rule
    declared, asking for the short name must refuse.
    """
    longer = dict(JOIN_DECLARATIONS[0],
                  name=derivation.CONFIRMED_JOIN_RULE + "_v2")
    monkeypatch.setattr(ingestion_worker, "read_rules_document",
                        lambda path=None: {"document": {}, "rules": [longer], "path": None,
                                           "exists": True, "error": None})
    assert derivation.join_rule(env, longer["name"])["name"] == longer["name"],         "the longer name itself must still resolve - this is about the SHORT one"
    with pytest.raises(derivation.DerivationRefused) as exc:
        derivation.join_rule(env, derivation.CONFIRMED_JOIN_RULE)
    assert exc.value.code == derivation.REFUSE_JOIN_RULE_MISSING


def test_a_switched_off_join_says_SWITCHED_OFF_and_not_absent(env, monkeypatch):
    """⚰️ I ASSERTED THE OPPOSITE ONE COMMIT AGO AND IT WAS WRONG (판정 450 ①). The test
    here said 「없다」 and 「꺼져 있다」 reach this gate as one fact and called the loss the
    loader's - but `expand_declaration` returns THREE things and `join_rule` was throwing
    the third away. A disabled declaration stands no rule, raises no refusal, and says so
    in `notes`; the judge's own docstring says exactly that.

    🔴 SO THIS IS THE 「없어서 0 / 못 읽어서 0」 CLASS WITH A THIRD MEMBER - 「꺼서 0」 -
    and an operator who switched a declaration off has to be told that, because it is the
    only one of the three they can undo in a second.
    """
    off = [dict(JOIN_DECLARATIONS[0], enabled=False), JOIN_DECLARATIONS[1]]
    monkeypatch.setattr(ingestion_worker, "read_rules_document",
                        lambda path=None: {"document": {}, "rules": off, "path": None,
                                           "exists": True, "error": None})
    with pytest.raises(derivation.DerivationRefused) as exc:
        derivation.join_rule(env, derivation.CONFIRMED_JOIN_RULE)
    said = str(exc.value)
    assert exc.value.code == derivation.REFUSE_JOIN_RULE_MISSING
    assert derivation.CONFIRMED_JOIN_RULE in said, "it still has to NAME the rule"
    assert "enabled=false" in said,         "a switched-off declaration is reported as never written: %r" % said
    assert "absent" not in said,         "it is not absent - it is there and off, and those are different repairs: %r" % said
    # The other declaration is untouched, so this is a per-rule answer and not a collapse.
    assert derivation.join_rule(env, derivation.FRAME_JOIN_RULE)["right_table"] == FRAMEATTR


def test_another_rules_refusal_is_not_claimed_by_a_name_it_merely_contains(env, monkeypatch):
    """🔴 [판정 450 ②] THE NAME FIELD, NOT THE NAME INSIDE THE SENTENCE. A loader
    refusal reads "<name>: <detail>", so testing `name in refusal` let a short name claim a
    longer one's refusal and send the operator to somebody else's declaration to fix a
    problem that is not theirs.

    ⚠️ AND IT IS THE SAME QUESTION THE LOOKUP BELOW ASKS. Spelling 「is this my rule」 two
    ways one line apart is door-splitting inside a single function - the exact shape the
    round was removing - and the prefix mutant that survived on the lookup side came from
    the same blind spot.
    """
    stale = dict(JOIN_DECLARATIONS[0],
                 name=derivation.CONFIRMED_JOIN_RULE + "_extra", into={"read": True})
    monkeypatch.setattr(ingestion_worker, "read_rules_document",
                        lambda path=None: {"document": {}, "rules": [stale], "path": None,
                                           "exists": True, "error": None})
    with pytest.raises(derivation.DerivationRefused) as exc:
        derivation.join_rule(env, derivation.CONFIRMED_JOIN_RULE)
    said = str(exc.value)
    assert stale["name"] not in said,         "this gate reported another declaration's refusal as its own: %r" % said
    assert "absent" in said, "with nothing of its own declared, absent is the honest answer"


def test_the_absent_refusal_carries_the_next_action(env, monkeypatch):
    """🔴 [상설] 「거절의 «사유»와 «다음 행동»」. The retirement refusal landed
    the same night says 「→ 다음: …」 and this one stopped at 「absent」 - two ways of
    speaking in one house, and the half without an action leaves the operator guessing.
    """
    monkeypatch.setattr(ingestion_worker, "read_rules_document",
                        lambda path=None: {"document": {}, "rules": [], "path": None,
                                           "exists": True, "error": None})
    with pytest.raises(derivation.DerivationRefused) as exc:
        derivation.join_rule(env, derivation.CONFIRMED_JOIN_RULE)
    said = str(exc.value)
    assert "Next:" in said, "the refusal names no next action: %r" % said
    for cell in ("join", "on", "take"):
        assert cell in said, "the action does not say what to write (%r missing)" % cell


def test_a_declaration_refused_by_name_is_carried_into_the_gates_sentence(env, monkeypatch):
    """🔴 「없다」 AND 「있는데 쓸 수 없다」 ARE DIFFERENT REPAIRS, and only the second one
    the operator can act on. The realistic case tonight is a declaration still written as
    `into: {read: true}`: 판정 440 ① retires it BY NAME, `expand_declaration` stands
    nothing for it, and without carrying that refusal through, this gate would report the
    rule as never declared - sending the operator to write a declaration that is already
    there.
    """
    stale = dict(JOIN_DECLARATIONS[0])
    stale["into"] = {"read": True}
    monkeypatch.setattr(ingestion_worker, "read_rules_document",
                        lambda path=None: {"document": {}, "rules": [stale], "path": None,
                                           "exists": True, "error": None})
    with pytest.raises(derivation.DerivationRefused) as exc:
        derivation.join_rule(env, derivation.CONFIRMED_JOIN_RULE)
    assert exc.value.code == derivation.REFUSE_JOIN_RULE_MISSING
    said = str(exc.value)
    assert derivation.CONFIRMED_JOIN_RULE in said
    assert "into.read" in said or "read" in said,         "the loader's own refusal must ride along, not be replaced by 「absent」: %r" % said


def test_a_rule_of_another_kind_under_that_name_is_refused_rather_than_used(env, monkeypatch):
    """⚠️ A NAME IS NOT A KIND. Chain rules share one namespace, so nothing stops a
    mapper rule from carrying the name this gate resolves; reading `params` off it would
    hand `join_pairs` an empty list and derive every row with no attribution at all.
    """
    impostor = {"name": derivation.CONFIRMED_JOIN_RULE, "enabled": True,
                "on": {"table": LOG}, "into": {"table": LOG},
                "derive": {"mapper": {"mapper": "dt_map_mapper"}}}
    monkeypatch.setattr(ingestion_worker, "read_rules_document",
                        lambda path=None: {"document": {}, "rules": [impostor],
                                           "path": None, "exists": True, "error": None})
    with pytest.raises(derivation.DerivationRefused) as exc:
        derivation.join_rule(env, derivation.CONFIRMED_JOIN_RULE)
    assert exc.value.code == derivation.REFUSE_JOIN_RULE_MISSING
    assert "not a join" in str(exc.value)


def test_the_four_cells_the_gate_reads_come_out_of_the_unified_declaration(env):
    """판정 440 ③ㅡ's whole content: the SOURCE of these cells changes, their
    spelling does not. `expose` resolves to `take`'s `from` side - the right column -
    because that is what `load_attribution` SELECTs on the right table.
    """
    confirmed = derivation.join_rule(env, derivation.CONFIRMED_JOIN_RULE)
    assert derivation.join_pairs(confirmed) == [("job", "job")]
    assert confirmed["expose"] == ["lot_confirmed", "slot_confirmed"]
    assert confirmed["right_table"] == JOBATTR
    assert confirmed["_name"] == derivation.CONFIRMED_JOIN_RULE

    frame = derivation.join_rule(env, derivation.FRAME_JOIN_RULE)
    assert derivation.join_pairs(frame) == [("eqp", "eqp"), ("prod", "prod")]
    assert frame["expose"] == ["core_frame", "dt_frame"]

    # And the identity resolution that consumes `expose` still lands on the RIGHT
    # column, which is the half that would have gone wrong had this read `into`.
    assert derivation.resolve_identity_sources(MAP, confirmed) == {
        "lot": "lot_confirmed", "slot": "slot_confirmed"}


def test_frame_parsing_refuses_everything_it_does_not_recognise():
    assert derivation.parse_frame("rot90_back") == (90, "back")
    assert derivation.parse_frame("ROT270_FRONT") == (270, "front")
    for bad in (None, "", "rot45_front", "rot90_side", "90_back", "rot90", "back_rot90"):
        assert derivation.parse_frame(bad) is None, bad


# ---------------------------------------------------------------------------
# Fan-out sizing
# ---------------------------------------------------------------------------

def test_frame_trigger_scope_reports_the_fan_out_before_anything_expands(env):
    """The frame trigger is keyed by equipment and product, not by job, so one
    corrected row reaches every job on that equipment. The size is a number the
    operator sees BEFORE it happens, not a surprise in a log afterwards."""
    db = env
    _seed_log(db)
    scope = derivation.frame_trigger_scope(db, LOG, {"eqp": "EQP1", "prod": "PRD-A"})
    assert scope["rows"] == len(_rows(db))
    assert scope["cap"] == derivation.SCOPE_ROW_CAP
    assert scope["over_cap"] is False

    narrow = derivation.frame_trigger_scope(db, LOG, {"eqp": "EQP1", "prod": "PRD-Z"})
    assert narrow["rows"] == 0


def test_scope_over_the_cap_is_flagged(env, monkeypatch):
    db = env
    _seed_log(db)
    monkeypatch.setattr(derivation, "SCOPE_ROW_CAP", 1)
    scope = derivation.frame_trigger_scope(db, LOG, {"eqp": "EQP1", "prod": "PRD-A"})
    assert scope["over_cap"] is True


# ---------------------------------------------------------------------------
# Retraction - the question that kept the chain rule disabled
# ---------------------------------------------------------------------------

def _seed_map_rows(db, keys, job=JOB):
    model = models.DYNAMIC_TABLES[MAP]
    for key in keys:
        db.add(model(row_id=key, business_key_val=key, cell_key=key, job=job,
                     lot=CONFIRMED_LOT, slot=CONFIRMED_SLOT, dx=0, dy=0, bn="x"))
    db.commit()


def test_retraction_selects_positively_what_the_source_owns(env):
    """`replace_map` cannot do this. `crud.derive_replace_map_scope` validates every
    scope key to be inside the map-key contract, so a purge can only be scoped to a
    WHOLE map - and one map can be fed by more than one job, so purging by map would
    delete a second job's cells to correct the first. Ownership is the way."""
    db = env
    _seed_map_rows(db, ["k1", "k2", "k3", "k4"])
    _seed_map_rows(db, ["other1", "other2"], job="OTHER-JOB")

    plan = derivation.plan_retraction(db, MAP, "job", JOB, derived_keys={"k1", "k2"},
                                      min_population=100)
    assert plan["population"] == 4
    assert set(plan["delete_row_ids"]) == {"k3", "k4"}
    assert "other1" not in plan["delete_row_ids"]


def test_retraction_is_dry_run_until_applied(env):
    db = env
    _seed_map_rows(db, ["k1", "k2", "k3"])
    plan = derivation.plan_retraction(db, MAP, "job", JOB, derived_keys={"k1"},
                                      min_population=100)
    assert db.query(models.DYNAMIC_TABLES[MAP]).count() == 3, "planning wrote something"
    assert derivation.apply_retraction(db, plan) == 2
    assert db.query(models.DYNAMIC_TABLES[MAP]).count() == 1


def test_retraction_never_deletes_a_human_correction(env):
    """A derivation may not delete a human correction for the same reason it may not
    overwrite one."""
    db = env
    _seed_map_rows(db, ["k1", "k2", "k3"])
    db.add(models.CellOverwrite(table_name=MAP, row_id="k2", column_name="bn",
                                is_overwrite=True, updated_by="operator"))
    db.commit()

    plan = derivation.plan_retraction(db, MAP, "job", JOB, derived_keys=set(),
                                      min_population=100)
    assert plan["protected"] == 1
    assert "k2" not in plan["delete_row_ids"]
    assert set(plan["delete_row_ids"]) == {"k1", "k3"}


def test_retraction_budget_guard_declines_a_wholesale_loss(env):
    """A wrong frame or a wrong attribution looks exactly like 'almost everything is
    stale'. The guard declines and NAMES the decline; it does not report zero."""
    db = env
    _seed_map_rows(db, ["k%d" % i for i in range(30)])
    plan = derivation.plan_retraction(db, MAP, "job", JOB, derived_keys=set(),
                                      max_fraction=0.5, min_population=20)
    assert plan["declined"] is not None
    assert plan["delete_row_ids"] == []
    assert derivation.apply_retraction(db, plan) == 0
    assert "DECLINED" in derivation.format_retraction_summary(plan)


def test_apply_retraction_deletes_exactly_the_plan_and_re_derives_nothing(env):
    """A dry run that could differ from what runs is a decoration."""
    db = env
    _seed_map_rows(db, ["k1", "k2", "k3"])
    plan = derivation.plan_retraction(db, MAP, "job", JOB, derived_keys={"k1", "k2"},
                                      min_population=100)
    _seed_map_rows(db, ["k4"])          # arrives AFTER planning
    derivation.apply_retraction(db, plan)
    remaining = {r.row_id for r in db.query(models.DYNAMIC_TABLES[MAP]).all()}
    assert remaining == {"k1", "k2", "k4"}, "apply must not act on what the plan never saw"


def test_apply_retraction_takes_the_ledgers_with_the_row(env):
    """A row deleted without its `cell_sources` / `cell_overwrites` leaves records keyed
    to a row_id that no longer exists, and nothing will ever join back to them.
    `crud._apply_batch_updates_once` deletes exactly these two tables before it deletes
    the row on BOTH of its removal paths; a second way to remove a map row must not be a
    second opinion about what removing one means."""
    db = env
    _seed_map_rows(db, ["k1", "k2"])
    for rid in ("k1", "k2"):
        db.add(models.CellSource(table_name=MAP, row_id=rid, column_name="bn",
                                 source_name="chain_ingestion", value={"value": "x"},
                                 updated_by="chain_worker"))
    # A human overwrite on the row that SURVIVES - it must still be there afterwards.
    db.add(models.CellOverwrite(table_name=MAP, row_id="k1", column_name="bn",
                                is_overwrite=True, updated_by="operator"))
    db.commit()

    def ledger(rid):
        return (db.query(models.CellSource)
                .filter(models.CellSource.table_name == MAP,
                        models.CellSource.row_id == rid).count(),
                db.query(models.CellOverwrite)
                .filter(models.CellOverwrite.table_name == MAP,
                        models.CellOverwrite.row_id == rid).count())

    assert ledger("k2") == (1, 0), "fixture did not arm the axis this test is about"

    plan = derivation.plan_retraction(db, MAP, "job", JOB, derived_keys={"k1"},
                                      min_population=100)
    assert plan["delete_row_ids"] == ["k2"]
    assert derivation.apply_retraction(db, plan) == 1
    assert ledger("k2") == (0, 0), "the retracted row left ledger orphans behind"
    assert ledger("k1") == (1, 1), "the surviving row lost its ledger"


def test_derived_keys_refuses_an_item_that_came_back_unkeyed(env):
    """`plan_retraction` treats "owned and not in derived_keys" as stale, so a key
    missing from the set is a row being marked for deletion. An incomplete set does not
    under-delete - it OVER-deletes what was just written."""
    from database import schemas
    good = schemas.GeneralUpdateItem(business_key_val="k1", updates={"bn": "x"})
    blank = schemas.GeneralUpdateItem(business_key_val=None, updates={"bn": "y"})

    assert derivation.derived_keys_of([good], MAP, "job") == {"k1"}
    with pytest.raises(derivation.DerivationRefused) as exc:
        derivation.derived_keys_of([good, blank], MAP, "job")
    assert exc.value.code == derivation.REFUSE_RETRACTION_UNKEYED
    assert "1 of 2" in str(exc.value)


@pytest.mark.parametrize("request_obj,needle", [
    (None, "non-empty object"),
    ({}, "non-empty object"),
    ({"source_value": "J"}, "no 'source_column'"),
    ({"source_column": "  ", "source_value": "J"}, "no 'source_column'"),
    ({"source_column": "job"}, "blank 'source_value'"),
    ({"source_column": "job", "source_value": ""}, "blank 'source_value'"),
    ({"source_column": "job", "source_value": "   "}, "blank 'source_value'"),
])
def test_a_malformed_retract_envelope_is_refused_by_name(request_obj, needle):
    """A blank source_value would select every row whose source is blank - the
    widening the envelope exists to avoid."""
    with pytest.raises(ValueError) as exc:
        derivation.normalize_retraction_request(request_obj, "some_rule")
    assert needle in str(exc.value)
    assert "some_rule" in str(exc.value)


def test_a_well_formed_retract_envelope_normalizes():
    assert derivation.normalize_retraction_request(
        {"source_column": " job ", "source_value": "J1"}, "r") == ("job", "J1")


def test_retraction_refuses_when_the_target_does_not_carry_the_source(env):
    """Without the source on the cell, stale rows could only be guessed at by set
    difference - and set-difference is exactly what scored 16 wrong dies as 1."""
    with pytest.raises(derivation.DerivationRefused) as exc:
        derivation.plan_retraction(db=None, target_table=MAP,
                                   source_column="not_a_column", source_value=JOB,
                                   derived_keys=set())
    assert exc.value.code == derivation.REFUSE_SOURCE_COLUMN_MISSING


# ---------------------------------------------------------------------------
# The live declarations resolve. Fixtures prove the code; this proves the config.
# ---------------------------------------------------------------------------

def test_the_live_chain_declaration_resolves_the_gate_if_it_declares_it():
    """A fixture can only prove the code. This asks the REAL declaration file whether the
    gate it feeds is actually resolvable.

    ⚰️ IT USED TO ASK `virtual_join_rules.json`, AND AFTER 판정 440 ③ㅡ THAT FILE NO
    LONGER FEEDS THIS GATE. Left pointing there it would have kept passing - the file is
    gitignored, so it skips - while asserting a property of a declaration nothing reads:
    a green line about the wrong document. It asks the chain declaration now, through the
    product's own reader and the judge the loader uses.

    `server/config/` is gitignored, so absence is a skip and not a failure.
    """
    from chain import ingestion_worker as worker, rule_shape as shape
    from database import crud

    stood = []
    for raw in worker.read_rules_document()["rules"] or ():
        rules, refusal, _notes = shape.expand_declaration(raw, crud.TABLE_CONFIG)
        if not refusal:
            stood.extend(rules or ())
    by_name = {r.get("name"): r for r in stood}
    if derivation.CONFIRMED_JOIN_RULE not in by_name:
        pytest.skip("the live chain declaration does not declare %s in this checkout"
                    % derivation.CONFIRMED_JOIN_RULE)
    from chain import join_into

    confirmed = join_into.join_spec(by_name[derivation.CONFIRMED_JOIN_RULE])
    frame = join_into.join_spec(by_name[derivation.FRAME_JOIN_RULE])
    takes = [source for source, _into in join_into._takes(frame)]
    assert confirmed.get("on"), "the confirmed join declares no join key"
    assert derivation.FRAME_COLUMN in takes,         "the frame join must take the column the gate reads"
    assert derivation.FORBIDDEN_FRAME_SUBSTITUTE in takes,         "core_frame is expected to be present and to be ignored - if it is gone, the "         "substitution test is no longer testing anything"


# ---------------------------------------------------------------------------
# The mapper: three trigger rules, one mapper, and the fan-out cap
# ---------------------------------------------------------------------------

def _mapper():
    """`server/mappers/` is gitignored - only the `.sample` is tracked, so on a fresh
    checkout the module this exercises does not exist. Skipping is honest; asserting it
    away would hide board item O7, which is that the live mapper lives on one machine
    and in no repository."""
    import importlib
    try:
        return importlib.import_module("mappers.dt_map_mapper")
    except ImportError:
        pytest.skip("mappers/dt_map_mapper.py absent (gitignored; only .sample tracked)")


def _seed_meta(db):
    """Register the map's canonical frame the way the system really stores it.

    The mapper does NOT take a `meta_loader`; it goes through
    `map_overlay.load_map_meta`, which reads `wafer_map_metadata` by
    (target_table, map_id). Skipping this seeding is how the first run of these tests
    produced `target_meta_missing` for all 58 rows - which is the gate working, and is
    also proof that the mapper path really does consult the registered frame rather
    than assuming one.
    """
    import json
    import map_meta_registrar
    model = models.DYNAMIC_TABLES.get(map_overlay.META_TABLE)
    map_id = map_meta_registrar.compose_map_id(
        ["lot", "slot"], {"lot": CONFIRMED_LOT, "slot": CONFIRMED_SLOT}, MAP)
    db.add(model(row_id="meta_%s" % map_id, business_key_val="%s|%s" % (MAP, map_id),
                 target_table=MAP, map_id=map_id,
                 grid_metadata=json.dumps(CANONICAL_META)))
    db.commit()
    return map_id


def _rule(name, trigger):
    """A rule declaration in the shape the chain worker passes through verbatim.

    The column names are DECLARED here rather than baked into the mapper, which is what
    lets one mapper serve a fixture whose columns are `job`/`bn` and a live table whose
    columns are `dt_job`/`c_bn`.
    """
    return {"name": name, "trigger_table": trigger, "target_table": MAP,
            "derivation_source_table": LOG,
            "derivation_source_column": "job",
            "derivation_value_columns": ["bn"],
            "derivation_origin_columns": ["orig"],
            "mapper_module": "mappers.dt_map_mapper",
            "mapper_function": "build_dt_map_batch_df",
            "is_batch": True, "enabled": False}


def test_the_mapper_is_kept_byte_identical_with_its_sample():
    """Nothing syncs the two and nothing else checks that they agree.

    `production_mapper.py` and its own sample are already different files. Identical
    bytes are the only cheap way to make divergence visible, so it is asserted rather
    than merely intended.
    """
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    live = os.path.join(here, "mappers", "dt_map_mapper.py")
    sample = os.path.join(here, "mappers", "dt_map_mapper.py.sample")
    if not os.path.exists(live):
        pytest.skip("mappers/dt_map_mapper.py absent (gitignored)")
    with open(live, "rb") as f:
        live_bytes = f.read()
    with open(sample, "rb") as f:
        sample_bytes = f.read()
    assert live_bytes.replace(b"\r\n", b"\n") == sample_bytes.replace(b"\r\n", b"\n"), \
        "dt_map_mapper.py and its .sample have diverged - the tracked copy is the only " \
        "one that exists outside this machine"


def test_the_source_trigger_derives_the_rows_that_just_landed(env):
    db = env
    mapper = _mapper()
    _seed_log(db)
    _seed_attribution(db)
    _seed_meta(db)
    payloads = [{c: getattr(r, c) for c in TABLES[LOG]["column_types"]}
                for r in _rows(db)]
    out = mapper.build_dt_map_batch_df(db, payloads,
                                       rule=_rule("dt_log_to_dt_map", LOG))
    assert len(out["updates"]) == len(payloads)


def test_the_attribution_trigger_revisits_rows_that_were_already_held_back(env):
    """THE POINT OF THE SECOND RULE. These rows landed before their confirmation and
    were skipped at source-trigger time. Without a revisit they are never looked at
    again, and that is how the absent 40% would be lost permanently."""
    db = env
    mapper = _mapper()
    _seed_log(db)

    skipped = _derive(db)
    assert skipped["updates"] == [], "the rows must start out held back"

    _seed_attribution(db)
    _seed_meta(db)
    # The trigger payload is an ATTRIBUTION row, not a source row.
    out = mapper.build_dt_map_batch_df(
        db, [{"job": JOB, "lot_confirmed": CONFIRMED_LOT,
              "slot_confirmed": CONFIRMED_SLOT}],
        rule=_rule("dt_job_attribution_to_dt_map", JOBATTR))
    assert len(out["updates"]) == len(_rows(db)), \
        "the revisit must reach every source row of that job"


def test_the_frame_trigger_revisits_every_job_on_that_equipment_and_product(env):
    db = env
    mapper = _mapper()
    _seed_log(db)
    _seed_attribution(db)
    _seed_meta(db)
    out = mapper.build_dt_map_batch_df(
        db, [{"eqp": "EQP1", "prod": "PRD-A", "dt_frame": RECORDED_FRAME}],
        rule=_rule("eqp_frame_attribution_to_dt_map", FRAMEATTR))
    assert len(out["updates"]) == len(_rows(db))


def test_the_frame_trigger_refuses_a_fan_out_over_the_cap(env, monkeypatch):
    """One corrected frame row reaches every job on that equipment - measured at 2,892
    source rows across 40 jobs on the dev fixture, a third of the table. A single config
    edit must not re-derive that silently."""
    db = env
    mapper = _mapper()
    _seed_log(db)
    _seed_attribution(db)
    monkeypatch.setattr(derivation, "SCOPE_ROW_CAP", 1)
    out = mapper.build_dt_map_batch_df(
        db, [{"eqp": "EQP1", "prod": "PRD-A", "dt_frame": RECORDED_FRAME}],
        rule=_rule("eqp_frame_attribution_to_dt_map", FRAMEATTR))
    assert out["updates"] == []


def test_an_incomplete_trigger_key_selects_nothing_rather_than_everything(env):
    """A missing scope component must never widen to the whole table."""
    db = env
    mapper = _mapper()
    _seed_log(db)
    _seed_attribution(db)
    out = mapper.build_dt_map_batch_df(
        db, [{"eqp": "EQP1", "prod": ""}],
        rule=_rule("eqp_frame_attribution_to_dt_map", FRAMEATTR))
    assert out["updates"] == []


def test_the_dt_log_derivation_rule_ships_disabled():
    """Enabling it is a separate, explicit decision that belongs with the evidence.

    ⚰️ THIS COUNTED THREE AND NAMED THEIR TRIGGERS (S-100 ⓐ-2, 판정 16:20). All three of
    its claims are false against today's shipped sample, and the drift is bigger than the
    one rule S-100 ⓐ removed - measured 2026-09-10:

        was  3 rules -> triggers {dt_log, dt_job_attribution, eqp_frame_attribution},
             all disabled
        now  2 rules -> triggers {dt_log, dt_inventory}; `dt_job_attribution` and
             `eqp_frame_attribution` do not appear in the sample AT ALL, and
             `dt_inventory_to_standard_dt_map` ships ENABLED

    🔴 SO 「every declared rule ships disabled」 IS NOT THE REPLACEMENT PREDICATE - it is
    false of the sample, both dt_map-wide (one of the two is enabled) and file-wide (five
    of the ten shipped rules are enabled, `dt_log_to_dt_job_rollup` among them). Asserting
    it would be forcing green on a statement the file contradicts.

    What is left is the claim this test was actually written for and which still holds:
    the dt_log -> dt_map derivation does not run on a fresh install unless somebody turns
    it on. Whether `dt_inventory_to_standard_dt_map` SHOULD ship enabled is a ruling, not
    an assertion, and it is named in the report rather than pinned here.
    """
    import json
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sample = os.path.join(here, "config", "sample", "chain_rules.json.sample")
    with open(sample, encoding="utf-8") as f:
        rules = json.load(f)["rules"]

    by_name = {r.get("name"): r for r in rules}
    rule = by_name.get("dt_log_to_dt_map")

    assert rule is not None, sorted(by_name)
    assert rule["trigger_table"] == "dt_log"
    assert rule["target_table"] == "dt_map"
    assert rule["enabled"] is False, "the derivation must not run on a fresh install"


def test_the_retired_triggers_are_gone_rather_than_shipped_disabled():
    """⚠️ ABSENT, NOT OFF - and those are different facts. A rule shipped `enabled: false`
    is one an operator can turn on; a rule that is not in the file is one the product no
    longer has. The two the old assertion named left the sample entirely, so a reader
    looking for them should find this instead of finding nothing."""
    import json
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sample = os.path.join(here, "config", "sample", "chain_rules.json.sample")
    with open(sample, encoding="utf-8") as f:
        rules = json.load(f)["rules"]

    triggers = {r.get("trigger_table") for r in rules}

    assert "dt_job_attribution" not in triggers
    assert "eqp_frame_attribution" not in triggers


def _shipped_rules():
    import json
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "config", "sample", "chain_rules.json.sample"),
              encoding="utf-8") as f:
        return json.load(f)["rules"]


def test_every_rule_that_ships_enabled_says_why(  ):
    """🔴 THE ENABLED SET IS A DECLARATION OF WHAT A FRESH INSTALL STARTS BY ITSELF
    (S-132, 판정 17:15). Read one at a time each looks defensible; read as a table it is a
    claim about the product's out-of-box behaviour, and every member of it owes a reason.

    ⛔ THE REASON MUST COME FROM THE RULE'S OWN PURPOSE, not from its name. The three that
    ship enabled each carry one that is checkable: a test reads what one produces, an owner
    ruling put one on the chain, and the shipped ledger declaration reads a third's target.
    """
    enabled = [r for r in _shipped_rules() if r.get("enabled") is not False]

    assert enabled, "if this is empty the predicate below is vacuous"
    missing = sorted(r.get("name") for r in enabled if not r.get("__why_enabled"))
    assert not missing, f"enabled without a stated reason: {missing}"


def test_the_dt_chain_ships_wholly_off_rather_than_broken_in_the_middle():
    """🔴 MEASURED 2026-09-10, AND IT IS WHY TWO RULES WERE TURNED OFF. The DT derivation
    shipped with its ENDS on and its MIDDLE off:

        dt_log_to_dt_alignment_metadata  ENABLED  -> wafer_map_metadata
        dt_metadata_to_dt_inventory      disabled <- the only rule that consumes it
        dt_inventory_to_standard_dt_map  ENABLED  <- waits on dt_inventory

    So a fresh install wrote `wafer_map_metadata` that nothing in the chain read, and kept
    a rule armed for a table the chain never produced. Neither end carried a reason for
    being on, and turning them off makes the set coherent - which is what
    「enabling them is a separate, explicit decision」 meant in the first place.
    """
    by_name = {r.get("name"): r for r in _shipped_rules()}
    chain = ("dt_log_to_dt_map", "dt_log_to_dt_alignment_metadata",
             "dt_metadata_to_dt_inventory", "dt_inventory_to_standard_dt_map",
             "dt_inventory_to_core_usage_map", "dt_log_to_core_usage_map",
             "dt_log_to_primary_core_frame")

    for name in chain:
        assert name in by_name, name
        assert by_name[name]["enabled"] is False, f"{name} ships enabled with no reason"


def test_a_rule_is_not_left_armed_for_a_table_no_enabled_rule_produces():
    """⚠️ THE GENERAL FORM OF THE ABOVE. An enabled rule whose trigger table is produced
    ONLY by disabled rules can never fire from the chain - it reads as running and does
    nothing, which is the least visible kind of broken."""
    rules = _shipped_rules()
    enabled = [r for r in rules if r.get("enabled") is not False]
    produced_by_enabled = {r.get("target_table") for r in enabled}
    produced_by_any = {r.get("target_table") for r in rules}

    stranded = sorted(
        r.get("name") for r in enabled
        if r.get("trigger_table") in produced_by_any
        and r.get("trigger_table") not in produced_by_enabled)

    assert not stranded, f"enabled but unreachable through the chain: {stranded}"
