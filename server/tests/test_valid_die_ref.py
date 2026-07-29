"""M4 phase 1 — `valid_die_ref`: a stored map IS the valid-die set.

Circle geometry is being demoted from *validity judge* to *template generator*.
Real dt maps live on tape and carry no 300mm constraint, so a valid-die set that
cannot be drawn as a circle is unrepresentable today. Phase 1 introduces an
ADDITIVE declaration in `wafer_map_metadata.grid_metadata`:

    "valid_die_ref": {"table": "<map table>", "map_id": "<map key>"}  (table optional)
    "valid_die_ref": "<map key>"                                      (table inherited)

and consumes it. Phases 2-3 (preset as generator, retiring the circle from
`inside`, migrating existing metadata rows) are out of scope.

The grammar and the refusal vocabulary are pinned by `contracts/map_seam/`, which
scores this half and the client half against the same vectors.

The four invariants under test:

  INV-M4-1  no `valid_die_ref` -> behaviour identical to the baseline. The field
            must be inert on every existing path.
  INV-M4-2  ref present -> the referenced map is the SOLE basis. The circle does
            not participate in the answer. Every test on this axis asserts the
            resolved set actually DIFFERS from the circle mask — otherwise a
            circle implementation would pass it (server-pm memory: "does this
            test execute the line I wrote?").
  INV-M4-3  ref unresolvable -> refuse with a stated cause. `cells` is absent,
            never a silent circle fallback. A silent fallback makes a wrong
            answer indistinguishable from a right one.
  INV-M4-4  resolution goes through the 7b canonicalisation
            (`map_overlay.canonical_key_value`) — proved with the mutation twin
            pattern of test_key_canonicalization.py, not just a happy path.

Phase 2 adds two more, and both are scored HERE at the caller — the contract
scores the pure halves and says in as many words that it cannot reach the wiring:

  INV-M4-5  the declaration can be WRITTEN and UNWRITTEN
            (`map_overlay.apply_valid_die_ref`). The unset direction is the
            load-bearing one: `valid_die_ref` lives in a JSON payload with no
            other editor, so a writer that can set but not clear pins the map to
            a template forever.
  INV-M4-6  the reference chain is ONE HOP
            (`map_overlay.valid_die_chain_error`). A valid-die map is a map, so
            self-reference (a tautology) and a two-level chain (a set nobody
            declared) are both reachable, and both used to resolve looking
            healthy.

[Isolation] Table names use the `vdr_test_` prefix so they can never collide
with a real table in the user's gitignored config (server-pm memory: the
`bonding_log` trap).
"""
import json
import uuid

import pytest

import map_overlay
from database import crud, models

# `slot` is number-declared on purpose: every lookup in this file then rides the
# 7b canonicalisation, and the INV-M4-4 mutation twin can kill it.
_MAP_COLS = {"cell_key": "string", "lot": "string", "slot": "number",
             "x": "number", "y": "number", "val": "string"}
# Declared explicitly (the lot/slot convention fallback would derive the same
# list) because `map_meta_registrar` requires the declaration to activate.
_MAP_TABLE = {"business_key": "cell_key", "map_key_columns": ["lot", "slot"],
              "column_types": dict(_MAP_COLS)}

VDR_TABLES = {
    # The map that DECLARES the reference.
    "vdr_test_target_map": dict(_MAP_TABLE),
    # The map that IS the valid-die set.
    "vdr_test_template_map": dict(_MAP_TABLE),
    # A second template, for the rotated-frame case.
    "vdr_test_rot_map": dict(_MAP_TABLE),
    # Cannot be interpreted as a map (no coordinates) — explicit refusal axis.
    "vdr_test_notamap": {"business_key": "row_key",
                         "column_types": {"row_key": "string", "memo": "string"}},
    "wafer_map_metadata": {
        "business_key": "map_pk",
        "column_types": {"map_pk": "string", "target_table": "string",
                         "map_id": "string", "grid_metadata": "string"},
    },
}

# 300mm wafer, 60mm chips on a 6x6 grid: the circle CROPS the grid hard
# (bbox minC/minR = 1, 12 of 36 cells inside). A non-cropping fixture would let
# a circle implementation and a map implementation agree by accident.
PHYS_CROP = {"phys_wafer_dia": 300.0, "phys_chip_x": 60.0, "phys_chip_y": 60.0,
             "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}

GRID6 = {"grid_cols": 6, "grid_rows": 6, "grid_start_x": 1, "grid_start_y": 1,
         "grid_y_invert": False, "side": "front", "rotation": 0, **PHYS_CROP}

MAP_KEY = "LOT_1"          # the canonical identity (slot is number-declared)
MAP_KEY_PADDED = "LOT_01"  # what a parsed material token hands over


def _add(db, table, **cols):
    model = models.DYNAMIC_TABLES[table]
    bk = VDR_TABLES[table]["business_key"]
    db.add(model(row_id=str(uuid.uuid4()),
                 business_key_val=str(cols.get(bk) or uuid.uuid4()), **cols))


def _meta_raw(db, target_table, map_id, **meta_over):
    """A metadata row whose grid_metadata carries `meta_over` VERBATIM.

    `_meta` cannot express `valid_die_ref: null` — its keyword default is the
    "no declaration" signal — and an EXPLICIT null is a distinct state from an
    absent key (M4② `ref_declares_null_is_not_a_chain`).
    """
    meta = dict(GRID6)
    meta.update(meta_over)
    model = models.DYNAMIC_TABLES["wafer_map_metadata"]
    db.add(model(row_id=str(uuid.uuid4()),
                 business_key_val=f"{target_table}_{map_id}",
                 map_pk=f"{target_table}_{map_id}", target_table=target_table,
                 map_id=map_id, grid_metadata=json.dumps(meta)))
    return meta


def _meta(db, target_table, map_id, rotation=0, valid_die_ref=None, **over):
    over = dict(over, rotation=rotation)
    if valid_die_ref is not None:
        over["valid_die_ref"] = valid_die_ref
    return _meta_raw(db, target_table, map_id, **over)


def _cells(db, table, coords, lot="LOT", slot=1):
    for i, (x, y) in enumerate(coords):
        _add(db, table, cell_key=f"{table}-{x}-{y}-{i}", lot=lot, slot=slot,
             x=x, y=y, val="1")


@pytest.fixture()
def vdr_env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(VDR_TABLES)
    crud.TABLE_CONFIG.update(VDR_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    monkeypatch.setattr(map_overlay, "CONFIG_PATH", str(tmp_path / "none.json"))
    map_overlay._FRAME_TF_CACHE.clear()
    return db_session


def _circle_valid_visual(meta):
    """INDEPENDENT ORACLE: what the CIRCLE says, in stored (visual) coordinates.

    Built from the transformer layer the rest of the server uses, so it carries
    the bbox/start/y-invert conventions automatically (server-pm memory: never
    hand-write the round trip). This is the answer INV-M4-2 must NOT return.
    """
    tf = map_overlay._frame_transformer(meta, map_overlay._grid_of(meta))
    out = set()
    for r in range(tf.visual_rows):
        for c in range(tf.visual_cols):
            if tf.is_inside_wafer(c, r):
                out.add(tf.cell_to_visual(c, r))
    return out


def _resolve(db, table="vdr_test_target_map", key=MAP_KEY, **kw):
    return map_overlay.resolve_valid_die_set(db, {}, table, key, **kw)


# ---------------------------------------------------------------------------
# The fixture itself must have a live defect axis
# ---------------------------------------------------------------------------

def test_fixture_circle_actually_crops(vdr_env):
    """Guard on the guard: if the circle accepted the whole 6x6 grid, every
    INV-M4-2 assertion below would be satisfiable by a circle implementation."""
    circle = _circle_valid_visual(GRID6)
    assert len(circle) == 12, f"expected a cropping fixture, got {len(circle)}/36"
    assert (1, 1) not in circle      # the corner the template will ADD
    assert (2, 2) in circle          # the cell the template will REMOVE


# ---------------------------------------------------------------------------
# INV-M4-1 — no valid_die_ref -> baseline behaviour, byte for byte
# ---------------------------------------------------------------------------

def test_undeclared_ref_is_not_declared_and_serves_no_cells(vdr_env):
    db = vdr_env
    _meta(db, "vdr_test_target_map", MAP_KEY)
    db.commit()

    out = _resolve(db)
    assert out["declared"] is False
    assert out["status"] == map_overlay.STATUS_NOT_DECLARED
    assert out["ref"] is None
    assert "cells" not in out, "an undeclared ref must not answer with a set"


def test_declaration_does_not_perturb_frame_axes(vdr_env):
    """`frame_axes` keys the transformer cache and every alignment decision. If
    the new field leaked into it, adding a ref would silently re-frame the map."""
    plain = dict(GRID6)
    with_ref = dict(GRID6, valid_die_ref={"table": "vdr_test_template_map"})
    assert map_overlay.frame_axes(plain) == map_overlay.frame_axes(with_ref)


def test_declaration_is_inert_on_the_overlay_path(vdr_env):
    """The overlay endpoint is the existing consumer of map metas. Its output
    must not move when a ref is declared on either side (INV-M4-1)."""
    db = vdr_env
    _cells(db, "vdr_test_template_map", [(2, 2), (3, 3)])
    _meta(db, "vdr_test_target_map", MAP_KEY)
    _meta(db, "vdr_test_template_map", MAP_KEY)
    db.commit()
    before = map_overlay.get_overlay(db, {}, "vdr_test_target_map", MAP_KEY,
                                     [("vdr_test_template_map", None)])

    # re-register both metas WITH a declaration
    db.query(models.DYNAMIC_TABLES["wafer_map_metadata"]).delete()
    ref = {"table": "vdr_test_template_map", "map_id": MAP_KEY}
    _meta(db, "vdr_test_target_map", MAP_KEY, valid_die_ref=ref)
    _meta(db, "vdr_test_template_map", MAP_KEY, valid_die_ref=ref)
    db.commit()
    map_overlay._FRAME_TF_CACHE.clear()
    after = map_overlay.get_overlay(db, {}, "vdr_test_target_map", MAP_KEY,
                                    [("vdr_test_template_map", None)])

    assert json.dumps(after, sort_keys=True) == json.dumps(before, sort_keys=True)


# ---------------------------------------------------------------------------
# INV-M4-2 — the referenced map is the SOLE basis
# ---------------------------------------------------------------------------

def test_referenced_map_is_the_whole_answer_and_the_circle_is_not(vdr_env):
    db = vdr_env
    # (0,0) and (1,1) are OUTSIDE the circle; (2,2) is INSIDE it but absent here.
    template = {(0, 0), (1, 1), (2, 3), (3, 2), (4, 4)}
    _cells(db, "vdr_test_template_map", template)
    _meta(db, "vdr_test_target_map", MAP_KEY,
          valid_die_ref={"table": "vdr_test_template_map", "map_id": MAP_KEY})
    _meta(db, "vdr_test_template_map", MAP_KEY)
    db.commit()

    out = _resolve(db)
    assert out["status"] == map_overlay.STATUS_OK
    assert out["declared"] is True
    assert set(out["cells"]) == template

    circle = _circle_valid_visual(GRID6)
    assert set(out["cells"]) != circle, "answer coincides with the circle — axis dead"
    # the template ADDS dies the circle rejects (the tape-map case)...
    assert {(0, 0), (1, 1)} <= set(out["cells"]) and not ({(0, 0), (1, 1)} & circle)
    # ...and REMOVES dies the circle accepts.
    assert (2, 2) in circle and (2, 2) not in set(out["cells"])


def test_geometry_that_no_circle_can_express(vdr_env):
    """A rectangular tape strip — the shape the whole track exists for."""
    db = vdr_env
    strip = {(x, 3) for x in range(6)}
    _cells(db, "vdr_test_template_map", strip)
    _meta(db, "vdr_test_target_map", MAP_KEY,
          valid_die_ref={"table": "vdr_test_template_map", "map_id": MAP_KEY})
    _meta(db, "vdr_test_template_map", MAP_KEY)
    db.commit()

    out = _resolve(db)
    assert set(out["cells"]) == strip
    assert not (strip <= _circle_valid_visual(GRID6))


def test_reference_is_read_in_the_referring_frame_not_raw(vdr_env):
    """A template stored in a 180-rotated frame must land on the target frame
    through the project's single transform, not be copied verbatim."""
    db = vdr_env
    stored = {(1, 1), (2, 3), (4, 4)}
    _cells(db, "vdr_test_rot_map", stored)
    _meta(db, "vdr_test_target_map", MAP_KEY,
          valid_die_ref={"table": "vdr_test_rot_map", "map_id": MAP_KEY})
    rot_meta = _meta(db, "vdr_test_rot_map", MAP_KEY, rotation=180)
    db.commit()

    transform = map_overlay.make_frame_transform(rot_meta, dict(GRID6))
    expected = {transform(x, y) for (x, y) in stored}

    out = _resolve(db)
    assert out["status"] == map_overlay.STATUS_OK
    assert set(out["cells"]) == expected
    assert set(out["cells"]) != stored, "180 rotation was a no-op — axis dead"
    assert out["align_applied"]["origin"] == map_overlay.ALIGN_ORIGIN_DERIVED


def test_table_omitted_inherits_the_referring_map_table(vdr_env):
    """The common case: a product template map living in the SAME table."""
    db = vdr_env
    _cells(db, "vdr_test_target_map", [(1, 1), (2, 3)], lot="TPL")
    _meta(db, "vdr_test_target_map", MAP_KEY, valid_die_ref={"map_id": "TPL_1"})
    _meta(db, "vdr_test_target_map", "TPL_1")
    db.commit()

    out = _resolve(db)
    assert out["status"] == map_overlay.STATUS_OK
    assert out["ref"] == {"table": "vdr_test_target_map", "map_id": "TPL_1"}
    assert set(out["cells"]) == {(1, 1), (2, 3)}


def test_bare_string_declaration_is_a_map_key(vdr_env):
    """Contract grammar (client `parseValidDieRef` mirror): a bare string is the
    MAP KEY, not a table name. Reading it as a table would resolve the wrong map."""
    db = vdr_env
    _cells(db, "vdr_test_target_map", [(1, 1)], lot="TPL")
    _meta(db, "vdr_test_target_map", MAP_KEY, valid_die_ref="TPL_1")
    _meta(db, "vdr_test_target_map", "TPL_1")
    db.commit()

    out = _resolve(db)
    assert out["status"] == map_overlay.STATUS_OK
    assert out["ref"] == {"table": "vdr_test_target_map", "map_id": "TPL_1"}


def test_target_table_and_map_key_aliases_are_accepted(vdr_env):
    """`target_table`/`map_key` are the wafer_map_metadata column names for the
    same pair — the client accepts both, so the server must too."""
    db = vdr_env
    _cells(db, "vdr_test_template_map", [(1, 1)])
    _meta(db, "vdr_test_target_map", MAP_KEY,
          valid_die_ref={"target_table": "vdr_test_template_map", "map_key": MAP_KEY})
    _meta(db, "vdr_test_template_map", MAP_KEY)
    db.commit()

    out = _resolve(db)
    assert out["status"] == map_overlay.STATUS_OK
    assert out["ref"] == {"table": "vdr_test_template_map", "map_id": MAP_KEY}


# ---------------------------------------------------------------------------
# INV-M4-3 — unresolvable -> refuse with a cause, NEVER a silent circle
# ---------------------------------------------------------------------------

def _assert_refused(out, status):
    assert out["declared"] is True
    assert out["status"] == status, out
    assert out.get("detail"), "a refusal must state its cause"
    assert "cells" not in out, "a refusal must not answer with a set"


@pytest.mark.parametrize("ref,status", [
    # the reference points somewhere that does not exist / is not a map
    ({"table": "vdr_test_nosuch_map", "map_id": MAP_KEY}, map_overlay.STATUS_SOURCE_MISSING),
    ({"table": "vdr_test_notamap", "map_id": MAP_KEY}, map_overlay.STATUS_SOURCE_MISSING),
    # the declaration itself cannot be read (grammar violations)
    ({"table": "vdr_test_template_map"}, map_overlay.STATUS_SOURCE_MISSING),   # no map_id
    ({"map_id": "   "}, map_overlay.STATUS_SOURCE_MISSING),                    # blank map_id
    ("", map_overlay.STATUS_SOURCE_MISSING),
    ("   ", map_overlay.STATUS_SOURCE_MISSING),
    (42, map_overlay.STATUS_SOURCE_MISSING),
    ([], map_overlay.STATUS_SOURCE_MISSING),
])
def test_unresolvable_reference_is_refused(vdr_env, ref, status):
    db = vdr_env
    _meta(db, "vdr_test_target_map", MAP_KEY, valid_die_ref=ref)
    db.commit()
    _assert_refused(_resolve(db), status)


def test_an_unreadable_declaration_is_not_folded_into_not_declared(vdr_env):
    """The rule the client states in one line: only null/absent is "no
    declaration". Folding a typo into "no declaration" returns it silently to
    circle geometry — the exact indistinguishability INV-M4-3 forbids."""
    db = vdr_env
    _meta(db, "vdr_test_target_map", MAP_KEY, valid_die_ref=42)
    db.commit()
    out = _resolve(db)
    assert out["declared"] is True
    assert out["status"] != map_overlay.STATUS_NOT_DECLARED


def test_reference_with_zero_rows_is_refused_not_read_as_zero_valid_dies(vdr_env):
    """An empty template almost certainly means "not loaded yet". Answering
    "no die is valid" would erase the user's whole map."""
    db = vdr_env
    _meta(db, "vdr_test_target_map", MAP_KEY,
          valid_die_ref={"table": "vdr_test_template_map", "map_id": MAP_KEY})
    _meta(db, "vdr_test_template_map", MAP_KEY)
    db.commit()
    _assert_refused(_resolve(db), map_overlay.STATUS_NO_DATA)


def test_reference_with_unregistered_meta_is_refused(vdr_env):
    """Asymmetric knowledge: we know the referring frame but not the referenced
    one. Assuming identity would silently accept a rotated template
    (bonding_plan's canonical-frame rule, same reasoning)."""
    db = vdr_env
    _cells(db, "vdr_test_template_map", [(1, 1), (2, 3)])
    _meta(db, "vdr_test_target_map", MAP_KEY,
          valid_die_ref={"table": "vdr_test_template_map", "map_id": MAP_KEY})
    db.commit()   # NO meta row for the template
    _assert_refused(_resolve(db), map_overlay.STATUS_ALIGN_UNAVAILABLE)


def test_incompatible_grid_dims_are_refused(vdr_env):
    db = vdr_env
    _cells(db, "vdr_test_template_map", [(1, 1), (2, 3)])
    _meta(db, "vdr_test_target_map", MAP_KEY,
          valid_die_ref={"table": "vdr_test_template_map", "map_id": MAP_KEY})
    _meta(db, "vdr_test_template_map", MAP_KEY, grid_cols=8, grid_rows=8)
    db.commit()
    _assert_refused(_resolve(db), map_overlay.STATUS_ALIGN_UNAVAILABLE)


def test_reference_over_the_cell_cap_is_refused_not_truncated(vdr_env):
    """A truncated valid-die set is a WRONG set that looks like a right one."""
    db = vdr_env
    _cells(db, "vdr_test_template_map", [(x, 0) for x in range(5)])
    _meta(db, "vdr_test_target_map", MAP_KEY,
          valid_die_ref={"table": "vdr_test_template_map", "map_id": MAP_KEY})
    _meta(db, "vdr_test_template_map", MAP_KEY)
    db.commit()

    out = _resolve(db, cell_cap=3)
    _assert_refused(out, map_overlay.STATUS_REF_UNAVAILABLE)
    assert "3" in out["detail"], "the refusal must name the cap that was hit"


def test_refusal_never_degrades_to_the_circle(vdr_env):
    """The defect class this round removes: a fallback that makes a wrong answer
    indistinguishable from a right one."""
    db = vdr_env
    _meta(db, "vdr_test_target_map", MAP_KEY,
          valid_die_ref={"table": "vdr_test_nosuch_map", "map_id": MAP_KEY})
    db.commit()
    out = _resolve(db)
    assert out.get("cells") is None
    assert out.get("count") is None
    assert out["status"] != map_overlay.STATUS_OK


def test_a_malformed_declaration_never_blocks_the_write_path(vdr_env):
    """Value ordering: the user's data beats loudness. A broken declaration is
    reported at READ time — it must never reject the metadata row itself
    (the `_validate_effort` defect, one round earlier)."""
    db = vdr_env
    _meta(db, "vdr_test_target_map", MAP_KEY, valid_die_ref={"nonsense": True})
    db.commit()
    row = (db.query(models.DYNAMIC_TABLES["wafer_map_metadata"])
           .filter_by(map_id=MAP_KEY, target_table="vdr_test_target_map").first())
    assert row is not None, "the row must survive a malformed declaration"
    assert _resolve(db)["status"] != map_overlay.STATUS_OK


# ---------------------------------------------------------------------------
# INV-M4-4 — the 7b canonicalisation, proved by mutation
# ---------------------------------------------------------------------------

def _seed_padded_ref(db):
    """The template stores slot 1 (number-declared); the declaration writes the
    padded token 'LOT_01' a parser would hand over."""
    _cells(db, "vdr_test_template_map", [(1, 1), (2, 3)], slot=1)
    _meta(db, "vdr_test_target_map", MAP_KEY,
          valid_die_ref={"table": "vdr_test_template_map", "map_id": MAP_KEY_PADDED})
    _meta(db, "vdr_test_template_map", MAP_KEY)
    db.commit()


def test_padded_ref_key_resolves_against_the_stored_number(vdr_env):
    db = vdr_env
    _seed_padded_ref(db)
    out = _resolve(db)
    assert out["status"] == map_overlay.STATUS_OK
    assert set(out["cells"]) == {(1, 1), (2, 3)}


def test_mutation_raw_key_loses_the_reference(vdr_env, monkeypatch):
    """MUTATION TWIN: degrade canonicalisation to raw str() and the same
    declaration must stop resolving. Without this the test above would pass on
    an implementation that added its own second normalisation."""
    db = vdr_env
    _seed_padded_ref(db)
    monkeypatch.setattr(map_overlay, "canonical_key_value",
                        lambda v, t: None if v is None else str(v))
    out = _resolve(db)
    assert out["status"] != map_overlay.STATUS_OK, \
        "resolution survived a broken canonicalizer — it is not going through it"


# ---------------------------------------------------------------------------
# Scale — one resolution per distinct ref per work unit
# ---------------------------------------------------------------------------

def test_repeated_resolution_within_a_work_unit_costs_one_query(vdr_env):
    db = vdr_env
    _cells(db, "vdr_test_template_map", [(1, 1), (2, 3)])
    _meta(db, "vdr_test_target_map", MAP_KEY,
          valid_die_ref={"table": "vdr_test_template_map", "map_id": MAP_KEY})
    _meta(db, "vdr_test_template_map", MAP_KEY)
    db.commit()

    from sqlalchemy import event
    engine = db.get_bind()
    seen = []

    def _count(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        cache = {}
        first = _resolve(db, cache=cache)
        n_first = len(seen)
        second = _resolve(db, cache=cache)
        n_second = len(seen)
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert first["status"] == map_overlay.STATUS_OK
    assert set(second["cells"]) == set(first["cells"])
    assert n_first > 0
    assert n_second == n_first, f"cached resolution still queried: {seen[n_first:]}"
    # one target-meta snapshot + one ref resolution
    assert len(cache) == 2


def test_two_maps_sharing_a_ref_and_frame_resolve_it_once(vdr_env):
    """"one resolution per DISTINCT ref per work unit" — not per map. The second
    map may re-read its own meta, but must not re-scan the template."""
    db = vdr_env
    _cells(db, "vdr_test_template_map", [(1, 1), (2, 3)])
    ref = {"table": "vdr_test_template_map", "map_id": MAP_KEY}
    _meta(db, "vdr_test_target_map", MAP_KEY, valid_die_ref=ref)
    _meta(db, "vdr_test_rot_map", MAP_KEY, valid_die_ref=ref)   # same frame axes
    _meta(db, "vdr_test_template_map", MAP_KEY)
    db.commit()

    from sqlalchemy import event
    engine = db.get_bind()
    seen = []

    def _count(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        cache = {}
        a = _resolve(db, table="vdr_test_target_map", cache=cache)
        n_a = len(seen)
        b = _resolve(db, table="vdr_test_rot_map", cache=cache)
        n_b = len(seen)
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert a["status"] == b["status"] == map_overlay.STATUS_OK
    assert set(a["cells"]) == set(b["cells"])
    # the second map costs exactly its own meta lookup — the template is not re-read
    assert n_b - n_a == 1, seen[n_a:]
    assert len(cache) == 3        # two metas + ONE ref resolution


def test_cache_is_keyed_by_the_referring_frame(vdr_env):
    """The same template resolved onto a differently-framed map is a DIFFERENT
    answer — a cache keyed by the ref alone would serve the first map's set."""
    db = vdr_env
    stored = {(1, 1), (2, 3), (4, 4)}
    _cells(db, "vdr_test_rot_map", stored)
    _meta(db, "vdr_test_target_map", MAP_KEY,
          valid_die_ref={"table": "vdr_test_rot_map", "map_id": MAP_KEY})
    _meta(db, "vdr_test_template_map", MAP_KEY, rotation=180,
          valid_die_ref={"table": "vdr_test_rot_map", "map_id": MAP_KEY})
    _meta(db, "vdr_test_rot_map", MAP_KEY)
    db.commit()

    cache = {}
    a = _resolve(db, table="vdr_test_target_map", cache=cache)
    b = _resolve(db, table="vdr_test_template_map", cache=cache)
    assert a["status"] == b["status"] == map_overlay.STATUS_OK
    assert set(a["cells"]) != set(b["cells"])
    assert len(cache) == 4        # two metas + two DISTINCT ref resolutions


# ---------------------------------------------------------------------------
# The contract symbol — `map_overlay.resolve_valid_die_basis(meta, resolver)`
# Registered in contracts/map_seam/vectors.json as `valid_die_basis`.
# Contract: -> {basis, source, reason}, source in "ref" | "circle" | "refused".
# ---------------------------------------------------------------------------

def test_basis_without_a_declaration_is_the_circle(vdr_env):
    """INV-M4-1 at the decision point. `circle` means "2a9f6c4 governs"."""
    out = map_overlay.resolve_valid_die_basis(dict(GRID6))
    assert out["source"] == map_overlay.SOURCE_CIRCLE
    assert out["reason"] == ""
    assert out["basis"] == map_overlay.circle_die_mask(GRID6)
    assert len(out["basis"]) == 12


def test_circle_mask_is_the_engine_answer_in_frame_indices(vdr_env):
    """The space matters: the mask baseline the seam scores is
    `is_cell_inside_wafer(c, r, C, R)` over the FRAME grid, dims swapped at
    90/270. A rotated map whose mask ignored the swap would pass a square
    fixture, so this asserts the swap on an ANISOTROPIC grid."""
    from utils.physical_wafer_engine import PhysicalWaferEngine

    meta = dict(GRID6, grid_cols=7, grid_rows=5, rotation=90)
    dia, cx, cy, ox, oy, margin = map_overlay._frame_phys_params(meta)
    eng = PhysicalWaferEngine(wafer_diameter_mm=dia, chip_size_x_mm=cx,
                              chip_size_y_mm=cy, edge_exclusion_mm=margin,
                              offset_x_mm=ox, offset_y_mm=oy)
    cols, rows = 5, 7                       # rotation 90 -> frame dims swap
    expected = {(c, r) for r in range(rows) for c in range(cols)
                if eng.is_cell_inside_wafer(c, r, cols, rows)}
    assert map_overlay.circle_die_mask(meta) == expected
    assert max(c for (c, _r) in expected) < cols, "frame dims were not swapped"


def test_basis_with_a_resolved_ref_is_the_ref_alone(vdr_env):
    """INV-M4-2. Intersecting with the circle is the tempting bug: it LOOKS
    conservative while silently dropping dies the template declares valid."""
    meta = dict(GRID6, valid_die_ref="TPL_1")
    ref_cells = {(0, 0), (1, 1), (2, 3)}    # (0,0) and (1,1) are outside the circle
    out = map_overlay.resolve_valid_die_basis(meta, lambda ref: ref_cells)

    assert out["source"] == map_overlay.SOURCE_REF
    assert out["basis"] == frozenset(ref_cells)
    assert out["reason"] == ""
    circle = map_overlay.circle_die_mask(meta)
    assert out["basis"] != circle & frozenset(ref_cells), "ref was intersected with the circle"
    assert not (out["basis"] <= circle), "the ref adds nothing the circle rejects — axis dead"


def test_basis_passes_the_parsed_ref_to_the_resolver(vdr_env):
    seen = []
    map_overlay.resolve_valid_die_basis(
        dict(GRID6, valid_die_ref="TPL_1"),
        lambda ref: (seen.append(ref), {(1, 1)})[1],
        table="vdr_test_target_map")
    assert seen == [{"table": "vdr_test_target_map", "map_id": "TPL_1"}]


@pytest.mark.parametrize("resolver", [
    lambda ref: None,                                    # could not resolve
    lambda ref: set(),                                   # zero cells is not an answer
    lambda ref: {"status": "source_missing", "detail": "테이블 없음"},
    lambda ref: (_ for _ in ()).throw(RuntimeError("boom")),
])
def test_basis_refuses_instead_of_falling_back_to_the_circle(vdr_env, resolver):
    """INV-M4-3. Every one of these would produce a plausible-looking map if it
    degraded to circle geometry, and the operator would never learn."""
    meta = dict(GRID6, valid_die_ref="TPL_MISSING")
    out = map_overlay.resolve_valid_die_basis(meta, resolver)
    assert out["source"] == map_overlay.SOURCE_REFUSED
    assert out["basis"] is None
    assert out["reason"], "a refusal must state its cause"
    assert out["basis"] != map_overlay.circle_die_mask(meta)


def test_basis_refuses_an_unreadable_declaration_without_a_resolver_call(vdr_env):
    called = []
    out = map_overlay.resolve_valid_die_basis(
        dict(GRID6, valid_die_ref=42), lambda ref: called.append(ref) or {(1, 1)})
    assert out["source"] == map_overlay.SOURCE_REFUSED
    assert out["reason"]
    assert called == [], "an unreadable declaration must not reach the resolver"


def test_basis_source_vocabulary_is_exactly_the_contract(vdr_env):
    assert (map_overlay.SOURCE_REF, map_overlay.SOURCE_CIRCLE,
            map_overlay.SOURCE_REFUSED) == ("ref", "circle", "refused")


def test_the_db_resolver_plugs_straight_into_the_basis_function(vdr_env):
    """The two halves must compose: `resolve_valid_die_set`'s return is one of
    the shapes `resolve_valid_die_basis` accepts. If they drifted apart the
    endpoint and the decision point would answer differently."""
    db = vdr_env
    template = {(0, 0), (1, 1), (2, 3)}
    _cells(db, "vdr_test_template_map", template)
    meta = _meta(db, "vdr_test_target_map", MAP_KEY,
                 valid_die_ref={"table": "vdr_test_template_map", "map_id": MAP_KEY})
    _meta(db, "vdr_test_template_map", MAP_KEY)
    db.commit()

    out = map_overlay.resolve_valid_die_basis(
        meta,
        lambda ref: map_overlay.resolve_valid_die_set(
            db, {}, "vdr_test_target_map", MAP_KEY),
        table="vdr_test_target_map")
    assert out["source"] == map_overlay.SOURCE_REF
    assert out["basis"] == frozenset(template)


def test_the_db_resolvers_refusal_carries_its_cause_into_the_basis(vdr_env):
    db = vdr_env
    meta = _meta(db, "vdr_test_target_map", MAP_KEY,
                 valid_die_ref={"table": "vdr_test_nosuch_map", "map_id": MAP_KEY})
    db.commit()

    out = map_overlay.resolve_valid_die_basis(
        meta,
        lambda ref: map_overlay.resolve_valid_die_set(
            db, {}, "vdr_test_target_map", MAP_KEY),
        table="vdr_test_target_map")
    assert out["source"] == map_overlay.SOURCE_REFUSED
    assert "vdr_test_nosuch_map" in out["reason"], \
        "the refusal must name the reference that failed, not a generic message"


# ---------------------------------------------------------------------------
# The declaration must survive the server's own write paths (value ordering #2)
# ---------------------------------------------------------------------------

def test_ingestion_auto_registration_never_clobbers_a_declared_ref(vdr_env):
    """`map_meta_registrar` fills HOLES. If it ever overwrote an existing meta,
    one ingestion batch would erase a hand-declared valid_die_ref and the map
    would silently revert to circle geometry.

    (`test_map_meta_registrar.test_existing_meta_is_never_overwritten` pins the
    absent-only rule in general; this pins it for the field M4 introduces.)
    """
    import map_meta_registrar
    db = vdr_env
    ref = {"table": "vdr_test_template_map", "map_id": MAP_KEY}
    _meta(db, "vdr_test_target_map", MAP_KEY, valid_die_ref=ref)
    db.commit()
    map_meta_registrar.reset_known_cache()

    collector = map_meta_registrar.MapMetaCollector(
        "vdr_test_target_map", VDR_TABLES["vdr_test_target_map"])
    assert collector.active, "the collector must be live, or this proves nothing"
    collector.collect([{"lot": "LOT", "slot": 1, "x": 9, "y": 9}])
    collector.flush(db)

    stored = json.loads(
        db.query(models.DYNAMIC_TABLES["wafer_map_metadata"])
        .filter_by(target_table="vdr_test_target_map", map_id=MAP_KEY)
        .first().grid_metadata)
    assert stored.get("valid_die_ref") == ref


# ---------------------------------------------------------------------------
# M4② INV-M4-6 — the ONE-HOP LIMIT, at the resolver
#
# A valid-die map is a map, so it can declare a `valid_die_ref` of its own.
# `contracts/map_seam/valid_die_chain_cases` scores the PURE predicate
# (`map_overlay.valid_die_chain_error`) and says in as many words what it cannot
# reach: the CALLER. That the resolver consults the guard at all, that it hands
# it CANONICAL identities on both sides, that a refusal arrives as `refused`
# instead of the middle map's cells, and that the answer is not served out of a
# cache keyed without the declaring map — all four are DB-bound, and they are
# what this section owns.
# ---------------------------------------------------------------------------

# A template that DIFFERS from the circle mask — (1, 1) is outside it (see
# test_fixture_circle_actually_crops). A chain that silently resolved to these
# cells would otherwise be indistinguishable from circle geometry.
_TPL = [(1, 1), (2, 3)]


def _declaring_meta(ref):
    """The DECLARING map's metadata, built in memory so one seeded fixture can be
    resolved under several declarations without re-writing the row."""
    return dict(GRID6, valid_die_ref=ref)


def _seed_two_templates(db):
    """Two templates with IDENTICAL cells and IDENTICAL frames. The ONLY
    difference is that one declares a `valid_die_ref` of its own.

    That is the whole point of the fixture: any assertion below that separates
    them is separating them on the declaration and nothing else.
    """
    _cells(db, "vdr_test_template_map", _TPL)
    _cells(db, "vdr_test_rot_map", _TPL)
    _meta(db, "vdr_test_template_map", MAP_KEY)
    _meta(db, "vdr_test_rot_map", MAP_KEY, valid_die_ref="TPL_X")
    db.commit()


def _ref_to(table):
    return {"table": table, "map_id": MAP_KEY}


def test_only_the_middle_declaration_separates_a_legal_hop_from_a_chain(vdr_env):
    """⭐ INV-M4-6 with its negative control in the same test.

    A guard that refuses every reference passes every refusal assertion in this
    section while disabling the feature the round ships — so the legal hop is
    asserted against the SAME cells, from the SAME frame, in the same breath.
    """
    db = vdr_env
    _seed_two_templates(db)

    legal = _resolve(db, target_meta=_declaring_meta(_ref_to("vdr_test_template_map")))
    chained = _resolve(db, target_meta=_declaring_meta(_ref_to("vdr_test_rot_map")))

    assert legal["status"] == map_overlay.STATUS_OK
    assert set(legal["cells"]) == set(_TPL)
    _assert_refused(chained, map_overlay.STATUS_REF_UNAVAILABLE)


def test_a_two_level_chain_never_serves_the_middle_maps_cells(vdr_env):
    """The defect verbatim: B's stored cells are served while B has declared that
    its own valid dies are C's. The operator sees a resolved reference over a set
    nobody declared."""
    db = vdr_env
    _seed_two_templates(db)
    out = _resolve(db, target_meta=_declaring_meta(_ref_to("vdr_test_rot_map")))
    assert out.get("cells") is None and out.get("count") is None
    assert out["status"] != map_overlay.STATUS_OK


def test_a_cycle_is_refused_by_the_one_hop_rule_alone(vdr_env):
    """A -> B -> A needs no visited set and no recursion depth: B declares,
    therefore A refuses. A second mechanism here would be a second answer to a
    question the one-hop rule already answers."""
    db = vdr_env
    _cells(db, "vdr_test_template_map", _TPL)
    _meta(db, "vdr_test_template_map", MAP_KEY, valid_die_ref=MAP_KEY)  # B -> A
    db.commit()
    _assert_refused(
        _resolve(db, target_meta=_declaring_meta(_ref_to("vdr_test_template_map"))),
        map_overlay.STATUS_REF_UNAVAILABLE)


@pytest.mark.parametrize("declared", ["", 0, False, {"nonsense": True}])
def test_a_falsy_or_broken_middle_declaration_is_still_a_declaration(vdr_env, declared):
    """"Declared" means here exactly what it means in the parser: only
    `null`/absent is absence.

    `if ref_meta["valid_die_ref"]:` is the shortest way to write this guard and it
    is wrong for `0`, `False` and `""`; `parse(ref_meta)[0] is not None` is the
    next-shortest and it folds a BROKEN middle declaration into absence — the
    phase-1 silent fallback, one level down, using the cells of a map whose own
    validity is refused.
    """
    db = vdr_env
    _cells(db, "vdr_test_template_map", _TPL)
    _meta(db, "vdr_test_template_map", MAP_KEY, valid_die_ref=declared)
    db.commit()
    _assert_refused(
        _resolve(db, target_meta=_declaring_meta(_ref_to("vdr_test_template_map"))),
        map_overlay.STATUS_REF_UNAVAILABLE)


def test_an_explicit_null_on_the_middle_map_is_absence_not_a_chain(vdr_env):
    """INV-M4-6's other direction. A guard testing key PRESENCE rather than value
    refuses this legitimate reference, and the operator is told their template is
    a chain when it is not."""
    db = vdr_env
    _cells(db, "vdr_test_template_map", _TPL)
    _meta_raw(db, "vdr_test_template_map", MAP_KEY, valid_die_ref=None)
    db.commit()
    out = _resolve(db, target_meta=_declaring_meta(_ref_to("vdr_test_template_map")))
    assert out["status"] == map_overlay.STATUS_OK
    assert set(out["cells"]) == set(_TPL)


def test_a_self_reference_is_refused_instead_of_resolving_to_a_tautology(vdr_env):
    """⭐ A -> A. The map's own stored cells become its own validity criterion, so
    every cell that exists is valid — true by construction, therefore saying
    nothing, and wearing a resolved reference's chip while it says it."""
    db = vdr_env
    _cells(db, "vdr_test_target_map", _TPL)
    _meta(db, "vdr_test_target_map", MAP_KEY, valid_die_ref=MAP_KEY)
    db.commit()
    out = _resolve(db)
    _assert_refused(out, map_overlay.STATUS_REF_UNAVAILABLE)
    assert set(_TPL) != set(), "empty fixture — the tautology would be invisible"


def test_the_two_refusals_are_told_apart_at_the_resolver(vdr_env):
    """Different problems, different fixes — re-point the reference vs. flatten
    the template. The predicate keeps them apart (contract); this asserts the
    resolver does not collapse both into one generic 'reference failed'."""
    db = vdr_env
    _cells(db, "vdr_test_target_map", _TPL)
    _cells(db, "vdr_test_rot_map", _TPL)
    _meta(db, "vdr_test_rot_map", MAP_KEY, valid_die_ref="TPL_X")
    _meta(db, "vdr_test_target_map", MAP_KEY)
    db.commit()

    mine = _resolve(db, target_meta=_declaring_meta(MAP_KEY))
    chained = _resolve(db, target_meta=_declaring_meta(_ref_to("vdr_test_rot_map")))
    assert mine["detail"] and chained["detail"]
    assert mine["detail"] != chained["detail"]


# --- the identities the guard compares must be CANONICAL (INV-M4-4 reuse) -----

def test_a_padded_self_reference_is_still_a_self_reference(vdr_env):
    """The declared key rides 7b before the comparison: `slot` is number-declared,
    so `LOT_01` IS the map `LOT_1`. A guard fed raw declaration text calls this an
    ordinary reference and resolves the tautology."""
    db = vdr_env
    _cells(db, "vdr_test_target_map", _TPL)
    _meta(db, "vdr_test_target_map", MAP_KEY, valid_die_ref=MAP_KEY_PADDED)
    db.commit()
    _assert_refused(_resolve(db), map_overlay.STATUS_REF_UNAVAILABLE)


def test_mutation_raw_key_hides_a_padded_self_reference(vdr_env, monkeypatch):
    """MUTATION TWIN for the test above. Degrade the ONE canonicalizer to raw
    `str()` and the padded declaration must stop being reported as a self
    reference — otherwise the test above is passing on a guard that carries its
    own normalisation, which INV-M4-4 forbids."""
    db = vdr_env
    _cells(db, "vdr_test_target_map", _TPL)
    _meta(db, "vdr_test_target_map", MAP_KEY)
    db.commit()

    # ORACLE: the verdict the UNPADDED self-reference produces. Comparing against
    # it (rather than against "some other string") is what stops this twin from
    # passing on a padded declaration that failed for an unrelated reason.
    verdict = _resolve(db, target_meta=_declaring_meta(MAP_KEY))["detail"]
    assert verdict, "the oracle is not a refusal — the twin below would be vacuous"
    assert _resolve(db, target_meta=_declaring_meta(MAP_KEY_PADDED))["detail"] == verdict

    monkeypatch.setattr(map_overlay, "canonical_key_value",
                        lambda v, t: None if v is None else str(v))
    assert _resolve(db, target_meta=_declaring_meta(MAP_KEY_PADDED))["detail"] != verdict, \
        "the self-reference verdict survived a broken canonicalizer — the guard " \
        "is normalising on its own instead of riding canonical_key_value"


def test_the_declaring_maps_own_key_is_canonicalised_before_the_comparison(vdr_env):
    """The OTHER side of the same comparison, and it has its own line of code.

    A caller that canonicalises the reference but hands the guard the raw home key
    misses `LOT_01 -> LOT_1` self-reference whenever the padded spelling is the one
    the caller was given — and then serves the tautology.
    """
    db = vdr_env
    _cells(db, "vdr_test_target_map", _TPL)
    db.commit()
    _assert_refused(
        map_overlay.resolve_valid_die_set(
            db, {}, "vdr_test_target_map", MAP_KEY_PADDED,
            target_meta=_declaring_meta(MAP_KEY)),
        map_overlay.STATUS_REF_UNAVAILABLE)


# --- INV-M4-3 at the new refusal route ---------------------------------------

def test_a_chain_refusal_reaches_the_basis_as_refused_with_its_reason(vdr_env):
    """The branch point must see `refused`, never `circle`. A chain that degraded
    to circle geometry would be the silent fallback INV-M4-3 forbids, reached
    through the door M4② opens."""
    db = vdr_env
    _seed_two_templates(db)
    meta = _declaring_meta(_ref_to("vdr_test_rot_map"))

    resolved = _resolve(db, target_meta=meta)
    out = map_overlay.resolve_valid_die_basis(
        meta,
        lambda ref: map_overlay.resolve_valid_die_set(
            db, {}, "vdr_test_target_map", MAP_KEY, target_meta=meta),
        table="vdr_test_target_map")

    assert out["source"] == map_overlay.SOURCE_REFUSED
    assert out["basis"] is None, "a refusal shipped a fallback basis"
    assert resolved["detail"] in out["reason"], \
        "the chain reason was replaced by a generic one — the operator is told the " \
        "reference failed without being told it is a chain"


# --- scale and cache scoping --------------------------------------------------

def _select_recorder(db):
    from sqlalchemy import event
    seen = []

    def _count(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", _count)
    return seen, lambda: event.remove(db.get_bind(), "before_cursor_execute", _count)


def test_the_chain_guard_reads_no_metadata_of_its_own(vdr_env):
    """[Scale] `bonding_map` is ~1.7M rows. The guard must ride the metadata the
    resolver ALREADY loaded — one metadata read per reference per work unit, never
    a lookup of its own and never anything per cell."""
    db = vdr_env
    _seed_two_templates(db)
    _meta(db, "vdr_test_target_map", MAP_KEY, valid_die_ref=_ref_to("vdr_test_rot_map"))
    db.commit()

    seen, stop = _select_recorder(db)
    try:
        cache = {}
        first = _resolve(db, cache=cache)
        n_first = len(seen)
        second = _resolve(db, cache=cache)
        n_second = len(seen)
    finally:
        stop()

    _assert_refused(first, map_overlay.STATUS_REF_UNAVAILABLE)
    assert second == first
    assert n_second == n_first, f"the cached refusal still queried: {seen[n_first:]}"
    meta_reads = [s for s in seen[:n_first] if "wafer_map_metadata" in s]
    assert len(meta_reads) == 2, \
        f"expected the declaring map's meta + the referenced map's meta, got " \
        f"{len(meta_reads)}: {meta_reads}"


def test_a_self_refusal_is_never_served_from_cache_to_another_map(vdr_env):
    """The refusal is a property of the PAIR, the cells are a property of the
    reference — so one cache entry cannot carry both.

    `LOT_1 -> LOT_1` and `LOT_2 -> LOT_1` share a reference AND a frame, which is
    exactly the cache key that makes two maps share one resolution. If the self
    verdict rides in that entry, the second map is refused for a reference it
    never made.

    The declarations are handed in rather than stored, and that is the only shape
    in which the two answers can DIFFER: a map whose stored metadata declares
    itself is also a chain for everyone pointing at it, so both would be refused
    and the collision would only swap one reason for another.
    """
    db = vdr_env
    _cells(db, "vdr_test_target_map", _TPL, slot=1)      # the map LOT_1
    _meta(db, "vdr_test_target_map", MAP_KEY)            # ...and it declares nothing
    db.commit()

    for order in ("self_first", "other_first"):
        cache = {}
        calls = [("LOT_2", map_overlay.STATUS_OK), (MAP_KEY, map_overlay.STATUS_REF_UNAVAILABLE)]
        if order == "self_first":
            calls.reverse()
        for key, expect in calls:
            out = map_overlay.resolve_valid_die_set(
                db, {}, "vdr_test_target_map", key,
                target_meta=_declaring_meta(MAP_KEY), cache=cache)
            assert out["status"] == expect, f"{order}/{key}: {out}"
            if expect == map_overlay.STATUS_OK:
                assert set(out["cells"]) == set(_TPL)


# ---------------------------------------------------------------------------
# M4② — the WRITER (`apply_valid_die_ref`), composed with the real resolver
#
# `contracts/map_seam/valid_die_authoring_cases` scores the writer through the
# READER. What no pure vector can show is that what the writer produces is what
# THIS resolver, against a real row, actually reads.
# ---------------------------------------------------------------------------

def test_the_writer_and_the_resolver_compose_in_both_directions(vdr_env):
    db = vdr_env
    _cells(db, "vdr_test_template_map", _TPL)
    _meta(db, "vdr_test_template_map", MAP_KEY)
    db.commit()

    base = dict(GRID6)
    declared = map_overlay.apply_valid_die_ref(base, _ref_to("vdr_test_template_map"))
    assert "valid_die_ref" not in base, "the writer mutated its argument"

    out = _resolve(db, target_meta=declared)
    assert out["status"] == map_overlay.STATUS_OK
    assert set(out["cells"]) == set(_TPL)

    cleared = map_overlay.apply_valid_die_ref(declared, None)
    assert _resolve(db, target_meta=cleared)["status"] == map_overlay.STATUS_NOT_DECLARED
    assert declared.get("valid_die_ref"), "clearing mutated the metadata it was given"


def test_a_blank_key_clears_rather_than_pinning_the_map_to_refused(vdr_env):
    """⭐ The unrecoverable state, proved against the real reader. `valid_die_ref`
    lives in a JSON payload with no other editor: a cleared form field written
    through as `""` is a DECLARATION by the phase-1 rule, so the map is refused
    forever with no UI path back."""
    db = vdr_env
    for blank in ("", "   ", {"table": "vdr_test_template_map", "map_id": ""}):
        meta = map_overlay.apply_valid_die_ref(dict(GRID6, valid_die_ref="TPL_1"), blank)
        out = _resolve(db, target_meta=meta)
        assert out["status"] == map_overlay.STATUS_NOT_DECLARED, \
            f"{blank!r} was written as a declaration: {meta.get('valid_die_ref')!r}"
        assert map_overlay.resolve_valid_die_basis(
            meta, table="vdr_test_target_map")["source"] == map_overlay.SOURCE_CIRCLE
