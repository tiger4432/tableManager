"""The coordinate triple is the primitive; the declared binding is a preset that PROPOSES it.

WHY THIS FILE EXISTS
`build_alignment_view` used to read x/y from `_binding_of(cfg, source_table)`, which for a
table like `dt_log` is declared as `dt_x`/`dt_y`. Opening the same unit with
`map_table=core_wafer_map` therefore pooled DT coordinates under CORE map ids, and
`core_x`/`core_y` were unreachable through the route at all. That is the failure mode where
the picture lines up perfectly and every value is wrong (spec section 7, I3) - and a client
column picker on top of it would have been a control that does nothing.

THE LOAD-BEARING TEST is `test_choosing_the_other_pair_actually_changes_what_is_read`.
Everything else here checks reporting; that one is the only assertion that would notice the
route accepting the columns and then ignoring them.
"""
import json

import pytest

import map_alignment as ma
import map_overlay
from database import crud, models

SRC = "colsel_test_log"
MAPT = "colsel_test_map"
REFT = "colsel_test_ref"
BARE = "colsel_test_bare"          # no declared binding, no literal x/y -> nothing to propose
GUESS = "colsel_test_guess"        # derivable x/y, but the value column can only be guessed

PHYS = {"phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}

RULE = {"name": "colsel_test_rule", "source_table": SRC,
        "derived_table": "colsel_test_unit", "decision_key": ["eqp", "product"],
        "target_fields": ["core_frame", "dt_frame"]}

TABLES = {
    SRC: {"business_key": "cell_key",
          "column_types": {"cell_key": "string", "eqp": "string", "product": "string",
                           "job": "string", "dt_x": "number", "dt_y": "number",
                           "core_x": "number", "core_y": "number", "c_bn": "string"},
          "map_key_columns": ["job"]},
    MAPT: {"business_key": "cell_key",
           "column_types": {"cell_key": "string", "job": "string",
                            "dt_x": "number", "dt_y": "number"},
           "map_key_columns": ["job"]},
    REFT: {"business_key": "cell_key",
           "column_types": {"cell_key": "string", "ref_id": "string",
                            "rx": "number", "ry": "number", "rv": "string"},
           "map_key_columns": ["ref_id"]},
    BARE: {"business_key": "cell_key",
           "column_types": {"cell_key": "string", "eqp": "string", "product": "string",
                            "job": "string", "a": "number"},
           "map_key_columns": ["job"]},
    # [F2] Literal x/y and a key, but NO column matching the declared value candidates -
    # so the derivation falls through to "first other column", which is a GUESS. This is
    # the only shape that reaches `source == "fallback_guess"`, and without it the guard
    # against proposing a guess has no test that executes it.
    GUESS: {"business_key": "cell_key",
            "column_types": {"cell_key": "string", "job": "string", "x": "number",
                             "y": "number", "zz": "string"},
            "map_key_columns": ["job"]},
    map_overlay.META_TABLE: {"business_key": "map_pk",
                             "composite_key_source": ["target_table", "map_id"],
                             "column_types": {"map_pk": "string",
                                              "target_table": "string",
                                              "map_id": "string",
                                              "grid_metadata": "string"}},
}

# The preset layer, in the shape `map_overlay_config.json` really carries it. `dt_x`/`dt_y`
# here is the whole point: it is a declaration about ONE of the two coordinate pairs the
# source table holds, and before this change it silently won for both map tables.
CFG = {"table_bindings": {
    SRC: {"columns": {"x": "dt_x", "y": "dt_y", "val": "c_bn", "key_columns": ["job"]}},
    REFT: {"columns": {"x": "rx", "y": "ry", "val": "rv", "key_columns": ["ref_id"]}},
}}

# Same declaration with the value column removed - the site that keeps no value column.
CFG_NO_VAL = {"table_bindings": {
    SRC: {"columns": {"x": "dt_x", "y": "dt_y", "key_columns": ["job"]}},
    REFT: {"columns": {"x": "rx", "y": "ry", "val": "rv", "key_columns": ["ref_id"]}},
}}


def _meta(**kw):
    m = {"grid_cols": 13, "grid_rows": 13, "rotation": 0, "side": "front",
         "grid_y_invert": False, "grid_start_x": 1, "grid_start_y": 1}
    m.update(PHYS)
    m.update(kw)
    return m


@pytest.fixture()
def env(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    map_overlay._FRAME_TF_CACHE.clear()
    return db_session


def _seed(db):
    """One unit, one map. The two coordinate pairs are DELIBERATELY different values, so
    reading the wrong pair is visible rather than coincidentally identical."""
    s = models.DYNAMIC_TABLES[SRC]
    meta_model = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    for i in range(3):
        db.add(s(row_id="s%d" % i, business_key_val="s%d" % i, cell_key="s%d" % i,
                 eqp="E1", product="P1", job="J1",
                 dt_x=1 + i, dt_y=1, core_x=7 + i, core_y=9, c_bn="A"))
    db.add(meta_model(row_id="m1", business_key_val="%s|J1" % MAPT,
                      target_table=MAPT, map_id="J1",
                      grid_metadata=json.dumps(_meta())))
    db.commit()


def _seed_reference(db):
    r = models.DYNAMIC_TABLES[REFT]
    meta_model = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    for i in range(4):
        db.add(r(row_id="r%d" % i, business_key_val="r%d" % i, cell_key="r%d" % i,
                 ref_id="R1", rx=3 + i, ry=4, rv="1"))
    db.add(meta_model(row_id="mr", business_key_val="%s|R1" % REFT,
                      target_table=REFT, map_id="R1",
                      grid_metadata=json.dumps(_meta())))
    db.commit()


def _view(db, cfg=CFG, **kw):
    return ma.build_alignment_view(db, cfg, RULE, {"eqp": "E1", "product": "P1"},
                                   MAPT, **kw)


# ---------------------------------------------------------------------------
# the primitive actually drives the read
# ---------------------------------------------------------------------------

def test_choosing_the_other_pair_actually_changes_what_is_read(env):
    """The one assertion that notices a route which accepts the columns and ignores them.

    Before this change the declared binding won unconditionally, so BOTH of these calls
    returned the dt coordinates and `core_x`/`core_y` could not be reached at all.
    """
    _seed(env)
    proposed = _view(env)["sources"]["cells"]
    chosen = _view(env, x_col="core_x", y_col="core_y")["sources"]["cells"]
    assert sorted(proposed) == [[1, 1], [2, 1], [3, 1]]
    assert sorted(chosen) == [[7, 9], [8, 9], [9, 9]]
    assert proposed != chosen


def test_the_declared_binding_still_supplies_the_columns_when_none_are_named(env):
    """The preset is not deleted. Omitting the columns must behave exactly as before."""
    _seed(env)
    cols = _view(env)["unit"]["columns"]
    assert (cols["x"]["column"], cols["y"]["column"]) == ("dt_x", "dt_y")
    assert cols["proposal"]["source"] == "declared"


def test_a_proposal_is_reported_differently_from_a_choice(env):
    """A default rendered like a decision is how a plausible default impersonates a
    declaration (spec section 7, I4)."""
    _seed(env)
    proposed = _view(env)["unit"]["columns"]
    assert [proposed[a]["origin"] for a in ("x", "y")] == [ma.COLUMN_PROPOSED] * 2

    mixed = _view(env, x_col="core_x")["unit"]["columns"]
    assert mixed["x"]["origin"] == ma.COLUMN_CHOSEN
    assert mixed["y"]["origin"] == ma.COLUMN_PROPOSED
    assert (mixed["x"]["column"], mixed["y"]["column"]) == ("core_x", "dt_y")


def test_the_proposal_is_carried_alongside_the_answer_not_replaced_by_it(env):
    """The operator must be able to see what they overrode."""
    _seed(env)
    cols = _view(env, x_col="core_x", y_col="core_y")["unit"]["columns"]
    assert (cols["proposal"]["x"], cols["proposal"]["y"]) == ("dt_x", "dt_y")


# ---------------------------------------------------------------------------
# validation, against the table's real schema
# ---------------------------------------------------------------------------

def test_a_column_the_table_does_not_have_is_refused(env):
    """Same discipline as validating `params` against the rule's own `decision_key`: an
    unknown name is a refusal, never a silent zero-row read."""
    _seed(env)
    for kw in ({"x_col": "nope"}, {"y_col": "nope"}, {"value_col": "nope"}):
        with pytest.raises(ValueError) as e:
            _view(env, **kw)
        assert "nope" in str(e.value)


def test_a_source_with_nothing_to_propose_refuses_instead_of_guessing(env):
    """No declared binding and no conventional x/y. Guessing a pair here would be the
    synthetic-default defect with a different spelling."""
    rule = dict(RULE, source_table=BARE)
    with pytest.raises(ValueError) as e:
        ma.build_alignment_view(env, {}, rule, {"eqp": "E1", "product": "P1"}, MAPT)
    assert "x/y" in str(e.value)


def test_a_bare_table_accepts_columns_named_explicitly(env):
    """The refusal above is about the PROPOSAL being unavailable, not about the table."""
    cols = ma.resolve_source_columns({}, SRC, models.DYNAMIC_TABLES[SRC],
                                     x_col="core_x", y_col="core_y")
    assert (cols["x"]["column"], cols["y"]["column"]) == ("core_x", "core_y")
    assert cols["x"]["origin"] == ma.COLUMN_CHOSEN
    assert cols["proposal"] is None


def test_the_guess_fixture_really_produces_a_guess(env):
    """Guard on the fixture, not on the code. The first version of the test below asserted
    against a table whose binding does not resolve at all, so it SKIPPED - and a skipped
    test proves nothing. Defect injection caught it: removing the guard stayed green."""
    info = map_overlay.resolve_binding_info({}, GUESS)
    assert info is not None
    assert info["source"] == "fallback_guess"
    assert info["val"] == "zz"


def test_a_guessed_value_column_is_never_offered_as_a_proposal(env):
    """[F2] The data paths refuse a value column that is a guess rather than a candidate
    match. A proposal is something the operator can accept as-is, so a guess cannot be one -
    otherwise the screen offers a column nobody chose and the data path would not read."""
    cols = ma.resolve_source_columns({}, GUESS, models.DYNAMIC_TABLES[GUESS])
    assert (cols["x"]["column"], cols["y"]["column"]) == ("x", "y")
    assert cols["x"]["origin"] == ma.COLUMN_PROPOSED
    assert cols["value"]["column"] is None
    assert cols["value"]["origin"] == ma.COLUMN_ABSENT
    assert cols["value"]["reason"] == ma._VALUE_GUESS_REASON


def test_a_guessed_value_column_can_still_be_chosen_explicitly(env):
    """Refusing to PROPOSE it is not refusing to read it. The operator naming the column
    is exactly the evidence the derivation lacked."""
    cols = ma.resolve_source_columns({}, GUESS, models.DYNAMIC_TABLES[GUESS],
                                     value_col="zz")
    assert cols["value"]["column"] == "zz"
    assert cols["value"]["origin"] == ma.COLUMN_CHOSEN


# ---------------------------------------------------------------------------
# an absent value column changes the QUESTION, and says so
# ---------------------------------------------------------------------------

def test_comparison_kind_follows_the_weakest_side(env):
    """Same rule the confirmation record applies to its contributors: the combined answer
    follows the weakest contributor. A reference carrying values cannot make a value
    comparison possible when the source has no value column to compare."""
    assert ma.comparison_kind(ma.REFERENCE_KIND_VALUES, "c_bn") == ma.REFERENCE_KIND_VALUES
    assert ma.comparison_kind(ma.REFERENCE_KIND_VALUES, None) == ma.REFERENCE_KIND_OCCUPANCY
    assert ma.comparison_kind(ma.REFERENCE_KIND_OCCUPANCY, "c_bn") == ma.REFERENCE_KIND_OCCUPANCY
    assert ma.comparison_kind(ma.REFERENCE_KIND_NONE, "c_bn") == ma.REFERENCE_KIND_NONE


def test_an_absent_value_column_lands_in_reference_kind_not_in_a_vague_result(env):
    """Occupancy alone is flat - 8 candidates inside 4 points, and one measured case had
    all 8 occupying the SAME dies while value agreement settled it by 374 dies. So an
    absent value column must read as 'this run could only ask about occupancy', never as
    a normal run that happened to be inconclusive."""
    _seed(env)
    _seed_reference(env)
    spec = "%s:R1" % REFT
    with_val = _view(env, reference_spec=spec, include_cells=False)
    assert with_val["reference"]["state"] == ma.REFERENCE_RESOLVED
    assert with_val["reference"]["kind"] == ma.REFERENCE_KIND_VALUES

    without = _view(env, cfg=CFG_NO_VAL, reference_spec=spec, include_cells=False)
    assert without["reference"]["state"] == ma.REFERENCE_RESOLVED
    assert without["unit"]["columns"]["value"]["column"] is None
    # a site that declares no value column is a NORMAL site, not a broken declaration:
    # `resolve_binding_info` fills the missing key with the literal default the data path
    # uses, so the proposal names a column that is not there. That is an absence with a
    # sentence, never a refusal.
    assert without["unit"]["columns"]["value"]["reason"]
    assert without["reference"]["kind"] == ma.REFERENCE_KIND_OCCUPANCY
    # and the reference map itself is unchanged - the degradation came from the source
    assert without["reference"]["map_kind"] == ma.REFERENCE_KIND_VALUES


def test_the_operator_can_ask_for_occupancy_only_on_a_table_that_declares_a_value(env):
    """Three things must be sayable: choose a column, take the proposal, go without.
    Omission already means "propose", so it cannot also mean "none" - and without a third
    spelling, a site whose binding declares a value column (every fixture table here, and
    `dt_log` in production) could never request the occupancy-only run. That run is exactly
    what tells a real tie apart from a reference that could not discriminate."""
    _seed(env)
    _seed_reference(env)
    spec = "%s:R1" % REFT
    default = _view(env, reference_spec=spec, include_cells=False)
    assert default["unit"]["columns"]["value"]["column"] == "c_bn"
    assert default["reference"]["kind"] == ma.REFERENCE_KIND_VALUES

    none = _view(env, reference_spec=spec, include_cells=False, value_col="")
    assert none["unit"]["columns"]["value"]["column"] is None
    assert none["unit"]["columns"]["value"]["origin"] == ma.COLUMN_ABSENT
    assert none["unit"]["columns"]["value"]["reason"]
    assert none["reference"]["kind"] == ma.REFERENCE_KIND_OCCUPANCY
    assert none["reference"]["map_kind"] == ma.REFERENCE_KIND_VALUES


def test_an_explicit_none_is_told_apart_from_nothing_being_available(env):
    """Both land on `absent`, but the sentences differ - the repairs differ too."""
    asked = ma.resolve_source_columns(CFG, SRC, models.DYNAMIC_TABLES[SRC], value_col="")
    unavailable = ma.resolve_source_columns({}, GUESS, models.DYNAMIC_TABLES[GUESS])
    assert asked["value"]["origin"] == unavailable["value"]["origin"] == ma.COLUMN_ABSENT
    assert asked["value"]["reason"] != unavailable["value"]["reason"]


def test_route_empty_value_col_means_occupancy_only(client, env, monkeypatch):
    _patch(monkeypatch)
    _seed(env)
    r = client.get("/api/maps/alignment/view",
                   params={"rule": RULE["name"], "map_table": MAPT,
                           "params": json.dumps({"eqp": "E1", "product": "P1"}),
                           "value_col": ""})
    assert r.status_code == 200
    assert r.json()["unit"]["columns"]["value"]["column"] is None


def test_the_reference_loader_carries_the_values_it_selects(env):
    """`_cells_of` used to SELECT the value column and return only x/y, so `reference.kind:
    "values"` was a declaration nothing acted on and the scorer only ever saw occupancy.
    Defect injection found this gap: the pure scorer tests pass their values in directly, so
    dropping the value on the DB path left them all green."""
    _seed(env)
    _seed_reference(env)
    cells, values, truncated, kind = ma._cells_of(env, CFG, REFT, "R1", 100)
    assert kind == ma.REFERENCE_KIND_VALUES
    assert len(values) == len(cells) > 0
    assert set(values) == {"1"}, values

    v = _view(env, reference_spec="%s:R1" % REFT, include_cells=False)
    assert v["reference"]["kind"] == ma.REFERENCE_KIND_VALUES
    assert all(c["value_agreement"] is not None for c in v["candidates"])
    # 🔴 CHANGED 2026-08-06, and the replacement is a SHARPER test of the same thing.
    #    This used to require `metric == values`. It cannot any more, and it should never have
    #    been the check: this fixture's reference says 'rv=1' and its source says 'c_bn=A', so
    #    the two vocabularies share nothing and value mode can only ever score zero. Ranking on
    #    that produced `no_overlap`, which reads as a geometry failure - the exact confusion
    #    that cost the operator a day. The axis is now demoted, by name, and ranking falls back.
    #
    #    What this test is FOR is that `_cells_of` carries the values through, and the new
    #    assertion proves it harder: if the loader dropped them the scorer would see no source
    #    vocabulary at all, `value_axis` would be `absent`, and the reason would be null.
    assert v["ruling"]["value_axis"] == ma.VALUE_AXIS_REPORTED
    assert v["ruling"]["value_axis_reason"] == ma.VALUE_AXIS_DISJOINT
    assert v["stats"]["value_vocab_shared"] == 0
    assert v["ruling"]["metric"] == ma.METRIC_OCCUPANCY


def test_the_view_serves_the_declared_thresholds_and_omits_undeclared_ones(env):
    """A null threshold on the wire becomes 0 in the reader (`Number(null) === 0`), which is
    "always rank". Absent keys are absent."""
    _seed(env)
    _seed_reference(env)
    spec = "%s:R1" % REFT
    none = _view(env, reference_spec=spec, include_cells=False)
    assert none["thresholds"] == {}
    # 🔴 CHANGED 2026-08-06. The old assertion here was `reason_code == no_overlap`, and the
    #    comment explained it as "this fixture's source cells land nowhere near the reference".
    #    That reading was wrong about its own fixture: the ZERO was the VALUE axis (rv='1' vs
    #    c_bn='A' share no word), not the footprint - occupancy does find an overlap under the
    #    solved shift. Now that a disjoint vocabulary demotes the value axis instead of ranking
    #    on its zeros, the run ranks on occupancy and names a frame.
    #
    #    This test is about THRESHOLDS, so what it needs to pin here is that the run got far
    #    enough to consult them, and that the demotion is visible rather than silent.
    assert none["ruling"]["placed_cells"] > 0, "cells reached the scorer"
    assert none["ruling"]["metric"] == ma.METRIC_OCCUPANCY
    assert none["ruling"]["value_axis_reason"] == ma.VALUE_AXIS_DISJOINT

    cfg = dict(CFG, alignment={"min_margin_dies": 4, "min_discriminating_dies": 2})
    both = _view(env, cfg=cfg, reference_spec=spec, include_cells=False)
    assert both["thresholds"] == {"min_margin_dies": 4, "min_discriminating_dies": 2}

    half = _view(env, cfg=dict(CFG, alignment={"min_margin_dies": 4}),
                 reference_spec=spec, include_cells=False)
    assert half["thresholds"] == {"min_margin_dies": 4}
    assert "min_discriminating_dies" not in half["thresholds"]


def test_a_run_with_no_reference_still_counts_the_maps_it_could_have_scored(env):
    """🔴 AN UNMEASURED COUNT MUST NOT BE REPORTED AS ZERO. With no reference plugged in the
    scorer never runs, so `stats` is empty and `usable_map_count` used to fall out of
    `stats.get(..., 0)` - a fabricated zero reading as "no map here is usable", about a unit
    that is one plug away from scoring. The branch already applies the scorer's own three
    gates to build the exclusion tally, so the survivors ARE measured; they just were not
    reported.
    """
    _seed(env)                       # one map, declared geometry, three cells, no reference
    v = _view(env, include_cells=False)
    assert v["reference"]["state"] == ma.REFERENCE_ABSENT
    assert v["sources"]["map_count"] == 1
    assert v["excluded_total"] == 0
    assert v["sources"]["usable_map_count"] == 1, (
        "the map passes all three gates - reporting 0 says the unit is hopeless when it is "
        "one reference away from a verdict")


def test_the_reference_map_kind_is_not_folded_into_the_comparison_kind(env):
    """Folding them would send the operator to fix the reference map when the missing
    piece is on the source side."""
    _seed(env)
    _seed_reference(env)
    v = _view(env, cfg=CFG_NO_VAL, reference_spec="%s:R1" % REFT, include_cells=False)
    assert v["reference"]["kind"] != v["reference"]["map_kind"]


# ---------------------------------------------------------------------------
# the worklist reports the real state of the preset
# ---------------------------------------------------------------------------

def test_the_worklist_no_longer_calls_the_binding_a_pin(env):
    """The ambiguity entry survives the fix and tells the truth: the binding PROPOSES one
    pair, and the others are reachable by naming them. Keeping the old wording would leave
    a second spelling of a fact that changed."""
    coord = ma.coordinate_column_catalog(CFG, SRC)
    codes = {a["code"] for a in ma.binding_ambiguity(RULE, coord)}
    assert "declared_binding_proposes_one_pair" in codes
    assert "declared_binding_pins_one_pair" not in codes
    entry = next(a for a in ma.binding_ambiguity(RULE, coord)
                 if a["code"] == "declared_binding_proposes_one_pair")
    assert "x_col" in entry["detail"] and "core_x" in entry["detail"]


# ---------------------------------------------------------------------------
# the route
# ---------------------------------------------------------------------------

def _patch(monkeypatch):
    import enrichment_config
    import main
    monkeypatch.setattr(enrichment_config, "load_enrichment_rules",
                        lambda *a, **k: [dict(RULE)])
    monkeypatch.setattr(main.map_overlay_module, "load_overlay_config",
                        lambda *a, **k: dict(CFG))


def test_route_passes_the_columns_through(client, env, monkeypatch):
    _patch(monkeypatch)
    _seed(env)
    r = client.get("/api/maps/alignment/view",
                   params={"rule": RULE["name"], "map_table": MAPT,
                           "params": json.dumps({"eqp": "E1", "product": "P1"}),
                           "x_col": "core_x", "y_col": "core_y"})
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["sources"]["cells"]) == [[7, 9], [8, 9], [9, 9]]
    assert body["unit"]["columns"]["x"]["origin"] == "chosen"


def test_route_400s_on_a_column_the_table_does_not_have(client, env, monkeypatch):
    _patch(monkeypatch)
    _seed(env)
    r = client.get("/api/maps/alignment/view",
                   params={"rule": RULE["name"], "map_table": MAPT,
                           "params": json.dumps({"eqp": "E1", "product": "P1"}),
                           "x_col": "not_a_column"})
    assert r.status_code == 400
    assert "not_a_column" in r.json()["detail"]


def test_route_without_columns_is_unchanged(client, env, monkeypatch):
    """The parameters are additive: an existing caller that names none must get exactly
    what it got before."""
    _patch(monkeypatch)
    _seed(env)
    r = client.get("/api/maps/alignment/view",
                   params={"rule": RULE["name"], "map_table": MAPT,
                           "params": json.dumps({"eqp": "E1", "product": "P1"})})
    assert r.status_code == 200
    assert sorted(r.json()["sources"]["cells"]) == [[1, 1], [2, 1], [3, 1]]
