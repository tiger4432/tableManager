"""[D7] A confirmation reaches `wafer_map_metadata` — the terminus of the purpose chain.

WHAT THIS FILE IS ABOUT, AND THE ONE THING THAT MAKES IT NECESSARY
-----------------------------------------------------------------
The confirmed winner on the seeded unit is `rot0_front` — rotation 0, side front,
y-invert false — which is EXACTLY the evidence-free triple. So writing the orientation
with no marker produces a BYTE-IDENTICAL row, and the confirmation becomes invisible,
indistinguishable from a map nobody ever touched. That is measured, not hypothetical
(`map_overlay` [D7]), and it is the reason the `confirmed` token exists at all.

🔴 THE DEFECT AXIS THIS FILE MUST ACTIVATE, because getting it wrong writes a row that
   looks perfectly coherent and disagrees with the ruling that produced it: THE GRID.
   The alignment did not run under a grid derived from the map's own cells — it ran under
   the grid it BORROWED from the reference, and the whole ruling that made partial maps
   work is that a partial map's own cell span is a lower bound and must not be used
   (`assume_grid_from` [D5]). So every fixture here gives the source map a cell bbox that
   is a STRICT SUB-BOX of the floor's grid. An implementation that synthesizes the grid
   from the map's own cells writes 5x5 where the answer is 13x13, and these tests say so.
   A fixture whose bbox happens to fill the floor cannot see that defect at all, and this
   repo has paid for that class of fixture several times.

Table names use the `fcmeta_test_*` prefix so they can never collide with a real table in
the user's gitignored config (server-pm memory: the `bonding_log` trap).
"""
import json
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import frame_confirmation as fc                      # noqa: E402
import map_alignment                                 # noqa: E402
import map_meta_registrar                            # noqa: E402
import map_overlay                                   # noqa: E402
from database import crud, models, schemas           # noqa: E402
from database.database import Base                   # noqa: E402
from map_meta_registrar import META_TABLE            # noqa: E402
from product_tables import PRODUCT_TABLES            # noqa: E402

MAP_TABLE = "fcmeta_test_map"
FLOOR_TABLE = "fcmeta_test_floor"

#: The floor. Its phys is DECLARED (six readable keys, no `auto_registered` marker), which
#: is what makes it borrowable at all, and its grid is 13x13 starting at (0, 0).
FLOOR_META = {"grid_cols": 13, "grid_rows": 13, "grid_start_x": 0, "grid_start_y": 0,
              "grid_y_invert": False, "rotation": 0, "side": "front",
              "phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
              "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}
FLOOR_ID = "PRD-A_DT13"
BASIS = {"table": FLOOR_TABLE, "map_id": FLOOR_ID}

#: The unit. `target_fields` are deliberately NOT `core_frame`/`dt_frame` — the same defect
#: axis `test_frame_confirmation.OTHER_RULE` exists for.
RULE = {"name": "fcmeta_job_attribution", "derived_table": "fcmeta_test_attribution",
        "decision_key": ["job"], "target_fields": ["lot_confirmed", "slot_confirmed"]}

TEST_TABLE_CONFIG = {
    MAP_TABLE: {
        "business_key": "chip_key",
        "composite_key_source": ["job", "x", "y"],
        "composite_key_separator": "_",
        "map_key_columns": ["job"],
        "column_types": {"chip_key": "string", "job": "string",
                         "x": "number", "y": "number", "val": "string"},
        "display_columns": ["chip_key", "job", "x", "y", "val"],
    },
    FLOOR_TABLE: {
        "business_key": "cell_key",
        "composite_key_source": ["product", "type", "x", "y"],
        "composite_key_separator": "_",
        "map_key_columns": ["product", "type"],
        "column_types": {"cell_key": "string", "product": "string", "type": "string",
                         "x": "number", "y": "number", "val": "string"},
        "display_columns": ["cell_key", "product", "type", "x", "y", "val"],
    },
    META_TABLE: PRODUCT_TABLES[META_TABLE],
}


@pytest.fixture()
def env(monkeypatch):
    """Isolated sqlite DB + config singleton, with the floor's meta row already there."""
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    models.init_dynamic_models(TEST_TABLE_CONFIG)
    saved = dict(crud.TABLE_CONFIG)
    crud.TABLE_CONFIG.clear()
    crud.TABLE_CONFIG.update(TEST_TABLE_CONFIG)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    monkeypatch.setattr(map_overlay, "load_overlay_config", lambda path=None: {})

    db = Session()
    _write_meta(db, FLOOR_TABLE, FLOOR_ID, FLOOR_META, source_name="user")
    try:
        yield db
    finally:
        db.close()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        engine.dispose()


def _write_meta(db, target_table, map_id, meta, source_name="custom_script"):
    crud.apply_batch_updates(db, META_TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(
            business_key_val=map_meta_registrar.meta_business_key(target_table, map_id),
            updates={"target_table": target_table, "map_id": map_id,
                     "grid_metadata": json.dumps(meta)},
            source_name=source_name, updated_by="seed")], silent=True))


def _meta(db, target_table, map_id):
    return map_overlay.load_map_meta(db, target_table, map_id)


def _contrib(map_id, frame="rot90_front", **kw):
    d = {"role": "source", "source_table": MAP_TABLE, "map_id": map_id,
         "source_name": "user", "applied_frame": frame, "shift_dx": 0, "shift_dy": 0}
    d.update(kw)
    return d


def _confirm(db, job, map_id, frame="rot90_front", by="operator", contributors=None,
             reference=BASIS, **kw):
    return fc.record_confirmation(
        db, RULE, {"job": job}, contributors or [_contrib(map_id, frame)],
        confirmed_by=by, frame=frame, map_table=MAP_TABLE,
        columns={"x": "x", "y": "y", "val": "val"},
        ruling={"winner": frame, "margin": 87}, reference=reference, **kw)


# ---------------------------------------------------------------------------
# The row gets created, and the grid on it is the scoring's grid
# ---------------------------------------------------------------------------

def test_a_confirmation_creates_the_metadata_row_for_a_map_that_had_none(env):
    """The chain used to stop at `frame_confirmation`. It reaches the terminus now."""
    assert _meta(env, MAP_TABLE, "J1") is None

    _confirm(env, "J1", "J1", "rot90_front")

    stored = _meta(env, MAP_TABLE, "J1")
    assert stored is not None, "the confirmation recorded no coordinate system at all"
    assert (stored["rotation"], stored["side"]) == (90, "front")
    assert [stored[k] for k in map_overlay.PHYS_KEYS] == \
           [FLOOR_META[k] for k in map_overlay.PHYS_KEYS]


def test_the_grid_written_is_the_one_the_scoring_ran_under_not_the_maps_own_cells(env):
    """🔴 THE DEFECT AXIS. The floor's grid is 13x13@(0,0); a grid synthesized from this
    map's own cells would be 5x5@(2,1). A row carrying the second one is coherent, wrong,
    and disagrees with the ruling that produced it.

    The assertion is written against BOTH numbers on purpose: `== floor` alone would also
    pass a fixture where the two happen to coincide, which is the fixture that proves
    nothing.
    """
    own_cells_grid = map_meta_registrar.synthesize_grid_meta(2, 1, 6, 5)
    assert map_overlay.grid_dims(own_cells_grid) == (5, 5), "fixture lost its defect axis"

    _confirm(env, "J1", "J1")

    stored = _meta(env, MAP_TABLE, "J1")
    assert map_overlay.grid_dims(stored) == map_overlay.grid_dims(FLOOR_META) == (13, 13)
    assert (stored["grid_start_x"], stored["grid_start_y"]) == (0, 0)
    assert map_overlay.grid_dims(stored) != map_overlay.grid_dims(own_cells_grid)


def test_the_maps_own_cell_bbox_cannot_reach_the_written_row(env):
    """The write reuses the scoring's own composer instead of reading cells again, and this
    is the reason that is sound rather than convenient: the bbox is overwritten twice on the
    way out (grid by `assume_grid_from`, phys by `assume_phys_from`) and everything else
    `synthesize_grid_meta` writes is a constant. Prose would be an assertion about the code;
    this is a measurement of it."""
    rows = {}
    for bbox in ((2, 1, 6, 5), (0, 0, 12, 12), (-4, 7, 9, 40)):
        cells = [(bbox[0], bbox[1]), (bbox[2], bbox[3])]
        got = map_alignment.assumed_meta_for_unregistered(cells, FLOOR_META, BASIS)
        assert got is not None
        rows[bbox] = {k: v for k, v in got.items()
                      if k != map_overlay.GRID_ASSUMED_KEY}
    first = next(iter(rows.values()))
    for bbox, row in rows.items():
        assert row == first, f"bbox {bbox} changed the composed frame: {row}"


# ---------------------------------------------------------------------------
# y-invert: not a candidate axis, therefore not confirmed and not written
# ---------------------------------------------------------------------------

def test_y_invert_is_not_written_and_reads_as_nobody_claimed_it(env):
    """`candidate_frames` is 4 rotations x 2 sides; y-invert cancels into an alias, so
    nothing varies it and nothing scores it. The confirmed frame is expressed RELATIVE to
    whatever y-invert the map already carries."""
    _confirm(env, "J1", "J1")
    stored = _meta(env, MAP_TABLE, "J1")
    axes = map_overlay.orientation_declaration(stored)

    assert axes["grid_y_invert"]["source"] == map_overlay.ORIENTATION_INDETERMINATE
    assert axes["grid_y_invert"]["source"] != map_overlay.GEOMETRY_CONFIRMED
    assert map_overlay.FRAME_CONFIRMED_KEY in stored
    assert axes["rotation"]["source"] == axes["side"]["source"] == \
           map_overlay.GEOMETRY_CONFIRMED


def test_an_existing_y_invert_survives_the_confirmation_untouched(env):
    """Overwriting it would not merely assert an unsolved fact; it would change the meaning
    of the rotation and side that WERE confirmed."""
    own = dict(FLOOR_META, grid_y_invert=True, rotation=270, side="back")
    own.pop("phys_chip_x")                       # not declared -> phys is borrowable
    _write_meta(env, MAP_TABLE, "J1", own)

    _confirm(env, "J1", "J1", "rot90_front")

    stored = _meta(env, MAP_TABLE, "J1")
    assert stored["grid_y_invert"] is True, "the confirmation overwrote an unsolved axis"
    assert (stored["rotation"], stored["side"]) == (90, "front")


# ---------------------------------------------------------------------------
# The confirmation must not be invisible — the measured reason the token exists
# ---------------------------------------------------------------------------

def test_the_evidence_free_winner_still_leaves_an_observable_record(env):
    """`rot0_front` IS the evidence-free triple. Written with no marker, the row a
    confirmation produces is byte-identical to a row nobody ever touched."""
    _confirm(env, "J1", "J1", "rot0_front")
    stored = _meta(env, MAP_TABLE, "J1")

    untouched = {k: v for k, v in stored.items()
                 if k not in (map_overlay.FRAME_CONFIRMED_KEY,
                              map_overlay.PHYS_CONFIRMED_KEY)}
    assert map_overlay.orientation_declaration(untouched)["rotation"]["source"] == \
        map_overlay.ORIENTATION_INDETERMINATE, \
        "fixture lost its point: this frame must be indistinguishable WITHOUT the marker"
    assert map_overlay.orientation_declaration(stored)["rotation"]["source"] == \
        map_overlay.GEOMETRY_CONFIRMED


def test_the_marker_carries_the_identity_of_the_confirmation_not_just_its_source(env):
    """`confirmation_uid` is what makes the derivation re-checkable and what makes the row
    unreadable as having happened without a confirmation."""
    h = _confirm(env, "J1", "J1", by="park")
    stored = _meta(env, MAP_TABLE, "J1")

    for key in (map_overlay.FRAME_CONFIRMED_KEY, map_overlay.PHYS_CONFIRMED_KEY):
        mark = stored[key]
        assert mark["confirmation_uid"] == h.confirmation_uid
        assert mark["confirmed_by"] == "park"
        assert mark["confirmed_at"]
        assert (mark["table"], mark["map_id"]) == (FLOOR_TABLE, FLOOR_ID)


def test_no_axis_of_a_confirmation_written_row_reads_as_a_declaration(env):
    """Nobody measured this map. Every axis must say so — `declared` anywhere on this row
    is the impersonation the whole vocabulary exists to stop (I4)."""
    _confirm(env, "J1", "J1")
    stored = _meta(env, MAP_TABLE, "J1")

    sources = {a: d["source"] for a, d in
               map_overlay.orientation_declaration(stored).items()}
    assert map_overlay.GEOMETRY_DECLARED not in sources.values(), sources
    assert map_overlay.geometry_declaration(stored) == map_overlay.GEOMETRY_CONFIRMED


# ---------------------------------------------------------------------------
# The token's rank: stronger than assumed, weaker than declared
# ---------------------------------------------------------------------------

def test_confirmed_geometry_is_a_basis_but_is_never_a_declaration(env):
    _confirm(env, "J1", "J1")
    stored = _meta(env, MAP_TABLE, "J1")

    assert map_overlay.geometry_computable(stored) is None      # a basis, like declared
    assert map_overlay.geometry_refusal(stored) is not None     # but not a declaration
    assert map_overlay.geometry_declaration(stored) != map_overlay.GEOMETRY_DECLARED


def test_a_borrow_marker_still_wins_over_a_confirmed_one_in_the_same_dict(env):
    """Weakest contributor (spec 0.2 (9)). A copy still carrying the borrow marker has not
    been confirmed away from the assumption."""
    both = dict(FLOOR_META)
    both[map_overlay.PHYS_CONFIRMED_KEY] = {"confirmation_uid": "fc_x"}
    both[map_overlay.PHYS_ASSUMED_KEY] = dict(BASIS)
    assert map_overlay.geometry_declaration(both) == map_overlay.GEOMETRY_ASSUMED


def test_a_confirmed_map_does_not_borrow_its_own_geometry_again(env):
    """Re-borrowing changes not one byte of the values and overwrites the marker with
    `assumed` — the next screen would then be indistinguishable from the one before the
    confirmation, which is the exact failure this token exists to prevent."""
    _confirm(env, "J1", "J1")
    stored = _meta(env, MAP_TABLE, "J1")

    assert map_alignment.phys_needs_basis(stored) is False
    assert map_alignment.grid_needs_basis(stored, FLOOR_META) is False
    assert map_alignment.geometry_basis_of(stored, None, FLOOR_META) == \
        map_overlay.GEOMETRY_CONFIRMED


# ---------------------------------------------------------------------------
# What a confirmation may NOT touch
# ---------------------------------------------------------------------------

def test_a_declared_phys_is_never_overwritten_by_a_confirmation(env):
    """A measured value is not replaced by a derived one. The frame is still recorded —
    that is what was confirmed."""
    own = dict(FLOOR_META, phys_chip_x=11.0, phys_chip_y=13.0, rotation=0, side="front")
    _write_meta(env, MAP_TABLE, "J1", own)
    assert map_overlay.geometry_declaration(own) == map_overlay.GEOMETRY_DECLARED

    _confirm(env, "J1", "J1", "rot180_back")

    stored = _meta(env, MAP_TABLE, "J1")
    assert (stored["phys_chip_x"], stored["phys_chip_y"]) == (11.0, 13.0)
    assert map_overlay.PHYS_CONFIRMED_KEY not in stored
    assert (stored["rotation"], stored["side"]) == (180, "back")
    assert map_overlay.FRAME_CONFIRMED_KEY in stored


def test_an_excluded_contributor_gets_no_confirmed_coordinate_system(env):
    """An excluded source was aligned to nothing, so it has no confirmed frame to record."""
    _confirm(env, "J1", "J1", contributors=[
        _contrib("kept"), _contrib("dropped", excluded_reason="no_cells")])

    assert _meta(env, MAP_TABLE, "kept") is not None
    assert _meta(env, MAP_TABLE, "dropped") is None


def test_with_no_basis_the_frame_is_still_recorded_but_nothing_is_derived(env):
    """`reference.state = "absent"` is the most common normal state, not a failure. With no
    floor there is nothing to derive a phys FROM — but the operator still named a frame, and
    that is what a confirmation is. A row that never existed stays absent: a metadata row
    with no grid cannot be read at all, and the grid comes from the basis."""
    own = dict(FLOOR_META, rotation=0, side="front")
    own.pop("phys_chip_x")
    _write_meta(env, MAP_TABLE, "has_row", own)

    _confirm(env, "J1", "has_row", "rot90_front", reference={},
             contributors=[_contrib("has_row", "rot90_front"),
                           _contrib("no_row", "rot90_front")])

    stored = _meta(env, MAP_TABLE, "has_row")
    assert (stored["rotation"], stored["side"]) == (90, "front")
    assert map_overlay.FRAME_CONFIRMED_KEY in stored
    assert map_overlay.PHYS_CONFIRMED_KEY not in stored, "derived a phys from no basis"
    assert _meta(env, MAP_TABLE, "no_row") is None


def test_a_confirmation_without_a_readable_frame_writes_no_coordinate_system(env):
    """`frames` (target fields) names an enrichment answer, not a map's coordinate system.
    With no frame there is no subject, and a row is not invented for one."""
    fc.record_confirmation(env, RULE, {"job": "J1"}, [_contrib("J1", None)],
                           confirmed_by="operator", map_table=MAP_TABLE,
                           frames={"lot_confirmed": "rot90_front"}, reference=BASIS)
    assert _meta(env, MAP_TABLE, "J1") is None


# ---------------------------------------------------------------------------
# The write has to actually land, and it has to land with the header
# ---------------------------------------------------------------------------

def test_the_write_lands_over_a_lower_ranked_source(env):
    """Written below `user`, the layering keeps the older cell and the route answers 200
    having changed nothing — the exact shape of the defect `e6fcc92` just closed."""
    seeded = dict(FLOOR_META, rotation=0, side="front")
    seeded.pop("phys_chip_x")
    _write_meta(env, MAP_TABLE, "J1", seeded, source_name="custom_script")

    _confirm(env, "J1", "J1", "rot270_front")

    stored = _meta(env, MAP_TABLE, "J1")
    assert (stored["rotation"], stored["side"]) == (270, "front"), \
        "the confirmation was outranked and recorded nothing"


def test_the_header_and_the_metadata_row_are_one_transaction(env, monkeypatch):
    """Not by discipline — by construction. `apply_batch_updates` commits unconditionally
    and rides this session, so a failed metadata write leaves the header uncommitted."""
    def boom(*a, **kw):
        raise RuntimeError("metadata write failed")
    monkeypatch.setattr(crud, "apply_batch_updates", boom)

    with pytest.raises(RuntimeError):
        _confirm(env, "J1", "J1")
    env.rollback()

    assert env.query(models.FrameConfirmation).filter_by(unit_key="J1").first() is None
    assert _meta(env, MAP_TABLE, "J1") is None


def test_deferring_the_commit_while_writing_metadata_is_refused(env):
    """The metadata write commits on its own, so `commit=False` plus a frame is a request
    for two transactions claiming to be one. Refused instead of silently split."""
    with pytest.raises(ValueError, match=META_TABLE):
        _confirm(env, "J1", "J1", commit=False)


def test_one_map_keeps_exactly_one_metadata_row_under_the_registrar_s_key(env):
    """Two spellings of an identity is how one writer creates the row another cannot find.

    🔴 THE COUNT IS THE ASSERTION, and it took a measurement to find that out. Asserting
       only the stored spelling is NOT enough: `crud` recomputes `business_key_val` from
       `composite_key_source`, so the stored key comes out canonical whatever the caller
       passed, and a divergent write-side key passed that check while quietly FORKING the
       map into two rows on the second confirmation (measured 2026-08-06 by mutating
       `meta_business_key` out of this writer — the spelling assert stayed green, the count
       assert went red).
    """
    _confirm(env, "J1", "J1", "rot90_front")
    _confirm(env, "J1", "J1", "rot180_back")

    model = models.DYNAMIC_TABLES[META_TABLE]
    rows = (env.query(model)
            .filter(model.target_table == MAP_TABLE, model.map_id == "J1").all())
    assert len(rows) == 1, "a re-confirmation forked the map's metadata into two rows"
    assert rows[0].business_key_val == map_meta_registrar.meta_business_key(MAP_TABLE, "J1")


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------

def test_re_confirming_the_same_frame_is_not_a_fresh_declaration_by_a_new_author(env):
    """The second pass must not promote anything to `declared`, must not lose the marker,
    and must not change a single value."""
    _confirm(env, "J1", "J1", "rot90_front", by="park")
    first = _meta(env, MAP_TABLE, "J1")

    h2 = _confirm(env, "J1", "J1", "rot90_front", by="lee")
    second = _meta(env, MAP_TABLE, "J1")

    marks = (map_overlay.FRAME_CONFIRMED_KEY, map_overlay.PHYS_CONFIRMED_KEY)
    assert {k: v for k, v in second.items() if k not in marks} == \
           {k: v for k, v in first.items() if k not in marks}
    assert map_overlay.geometry_declaration(second) == map_overlay.GEOMETRY_CONFIRMED
    assert second[map_overlay.FRAME_CONFIRMED_KEY]["confirmation_uid"] == h2.confirmation_uid
    assert second[map_overlay.FRAME_CONFIRMED_KEY]["confirmed_by"] == "lee"
