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
import virtual_join_config
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

# The shape `virtual_join_config.load_verified_rules` actually returns: a LIST of
# normalized rules each carrying its own `name`, NOT a {name: rule} dict. Getting this
# wrong is silent - `rules, rejections = load_...()` unpacks a two-element list into
# two rule dicts and every lookup then misses - so the fixture mirrors the real shape.
VJOIN_RULES = [
    {
        "name": derivation.CONFIRMED_JOIN_RULE,
        "left_table": LOG, "right_table": JOBATTR,
        "join_key": [{"left": "job", "right": "job"}],
        "left_columns": ["job"], "right_columns": ["job"],
        "expose": ["lot_confirmed", "slot_confirmed"],
        "join_cardinality": "one", "unique_index": "uq_test_jobattr_job",
    },
    {
        "name": derivation.FRAME_JOIN_RULE,
        "left_table": LOG, "right_table": FRAMEATTR,
        "join_key": [{"left": "eqp", "right": "eqp"}, {"left": "prod", "right": "prod"}],
        "left_columns": ["eqp", "prod"], "right_columns": ["eqp", "prod"],
        # Exposes BOTH frames, exactly as the live rule does. Only one may be read.
        "expose": ["core_frame", "dt_frame"],
        "join_cardinality": "one", "unique_index": "uq_test_frameattr_eqp_prod",
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
    monkeypatch.setattr(virtual_join_config, "load_verified_rules",
                        lambda *a, **k: [dict(r) for r in VJOIN_RULES])
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


def test_an_unverified_join_rule_is_a_named_refusal(env, monkeypatch):
    """`load_verified_rules` drops a rule whose join key has no UNIQUE index, and this
    module consumes only that loader.

    A rule that can fan out must not run this gate: `load_attribution` keys results by
    the join key, so a second attribution row for one key would silently overwrite the
    first and one arbitrary lot would win the identity.
    """
    monkeypatch.setattr(virtual_join_config, "load_verified_rules", lambda *a, **k: [])
    with pytest.raises(derivation.DerivationRefused) as exc:
        derivation.join_rule(env, derivation.CONFIRMED_JOIN_RULE)
    assert exc.value.code == derivation.REFUSE_JOIN_RULE_MISSING


def test_the_gate_reads_the_verified_loader_and_not_the_shape_only_one(env, monkeypatch):
    """Pins WHICH loader. `load_virtual_join_rules` checks the declaration's shape and
    nothing else; `virtual_join_config` names `load_verified_rules` the only entry point
    for code that executes a join, and quotes the difference as 130 million rows."""
    called = []
    monkeypatch.setattr(virtual_join_config, "load_virtual_join_rules",
                        lambda *a, **k: called.append("shape") or [])
    derivation.join_rule(env, derivation.CONFIRMED_JOIN_RULE)
    assert called == [], "the gate must not consume the shape-only loader"


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

def test_live_virtual_join_rules_resolve_the_gate_if_they_are_present():
    """A fixture can only prove the code. This asks the REAL declaration file whether
    the gate it feeds is actually resolvable - `server/config/` is gitignored, so it is
    skipped rather than failed where the file does not exist."""
    by_name = {r["name"]: r
               for r in (virtual_join_config.load_virtual_join_rules() or [])}
    if derivation.CONFIRMED_JOIN_RULE not in by_name:
        pytest.skip("live virtual_join_rules.json not present in this checkout")
    confirmed = by_name[derivation.CONFIRMED_JOIN_RULE]
    frame = by_name[derivation.FRAME_JOIN_RULE]
    assert derivation.join_pairs(confirmed), "the confirmed join declares no join key"
    assert derivation.FRAME_COLUMN in (frame.get("expose") or []), \
        "the frame join must expose the column the gate reads"
    assert derivation.FORBIDDEN_FRAME_SUBSTITUTE in (frame.get("expose") or []), \
        "core_frame is expected to be present and to be ignored - if it is gone, the " \
        "substitution test is no longer testing anything"


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


def test_all_three_declared_rules_ship_disabled():
    """Enabling them is a separate, explicit decision that belongs with the evidence."""
    import json
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sample = os.path.join(here, "config", "chain_rules.json.sample")
    with open(sample, encoding="utf-8") as f:
        rules = json.load(f)["rules"]
    dt_rules = [r for r in rules if r.get("target_table") == "dt_map"]
    assert len(dt_rules) == 3, "expected three trigger rules, found %d" % len(dt_rules)
    assert {r["trigger_table"] for r in dt_rules} == {
        "dt_log", "dt_job_attribution", "eqp_frame_attribution"}
    assert all(r["enabled"] is False for r in dt_rules)
    assert len({r["mapper_function"] for r in dt_rules}) == 1, \
        "the three rules must share one mapper, or the decision lives in three places"
