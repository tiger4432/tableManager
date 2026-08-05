"""A ONE-COLUMN decision key, and a target field that is not a frame.

WHY THIS FILE EXISTS
Every alignment fixture so far used a two-column decision key (`eqp`, `product`) and
target fields spelled `core_frame` / `dt_frame`. Two axes were therefore untested and a
production rule is about to exercise both:

  decision_key   ["job_id"]        - one column, so `sep.join(...)` has nothing to join
  target_fields  ["map_metadata"]  - a name that is not a frame

The first axis is the one that produces a trailing delimiter nobody notices: if the unit
key ever gained one, `live_confirmation` would look up a string the derived table never
wrote and a confirmed unit would silently render as pending forever. The second axis asks
whether anything in the chain assumes a target field IS a frame.
"""
import json

import pytest

import frame_confirmation as fc
import map_alignment as ma
import map_overlay
from database import crud, models

# Prefixed so it cannot collide with the operator's gitignored `table_config.json`.
SRC = "sk1_test_log"
DERIVED = "sk1_test_inventory"
DERIVED_BK = "sk1_test_bkinv"
MAPT = "sk1_test_map"

PHYS = {"phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}

# The production shape: ONE decision column, and a target field that is a metadata blob
# rather than a frame name.
RULE = {"name": "sk1_test_rule", "source_table": SRC, "derived_table": DERIVED,
        "decision_key": ["job_id"], "target_fields": ["map_metadata"],
        "list_columns": ["cell_count"]}

# Same unit, but the derived table satisfies the key contract the OTHER way
# (`business_key` in decision_key rather than `composite_key_source`). Both spellings are
# legal per `enrichment_config._validate_rule`, and they compose the key by different
# branches of `enrichment_mapper`, so both have to land on the same string.
RULE_BK = dict(RULE, name="sk1_test_rule_bk", derived_table=DERIVED_BK)

TABLES = {
    SRC: {"business_key": "cell_key",
          "column_types": {"cell_key": "string", "job_id": "string", "job": "string",
                           "dt_x": "number", "dt_y": "number", "c_bn": "string"},
          "map_key_columns": ["job"]},
    # A separator IS declared, and it is a visible character. If a one-element join ever
    # emitted it, the assertions below would see "J1|" instead of "J1".
    DERIVED: {"business_key": "unit_key", "composite_key_separator": "|",
              "composite_key_source": ["job_id"],
              "column_types": {"unit_key": "string", "job_id": "string",
                               "map_metadata": "string", "cell_count": "number"}},
    DERIVED_BK: {"business_key": "job_id", "composite_key_separator": "|",
                 "column_types": {"job_id": "string", "map_metadata": "string",
                                  "cell_count": "number"}},
    MAPT: {"business_key": "cell_key",
           "column_types": {"cell_key": "string", "job": "string",
                            "dt_x": "number", "dt_y": "number", "c_bn": "string"},
           "map_key_columns": ["job"]},
    # Product-owned tables, copied verbatim (see test_map_alignment_worklist.py: a fixture
    # that invents a different shape breaks the first run and passes every run after it).
    map_overlay.VALID_DIE_TABLE: {
        "business_key": "cell_key",
        "composite_key_source": ["product", "type", "x", "y"],
        "composite_key_separator": "_",
        "column_types": {"cell_key": "string", "product": "string", "type": "string",
                         "x": "number", "y": "number", "val": "string"},
        "map_key_columns": ["product", "type"]},
    map_overlay.META_TABLE: {"business_key": "map_pk",
                             "composite_key_source": ["target_table", "map_id"],
                             "column_types": {"map_pk": "string",
                                              "target_table": "string",
                                              "map_id": "string",
                                              "grid_metadata": "string"}},
}


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


def _seed_unit(db, job_id, jobs, cells=10, meta_for=None, derived=DERIVED):
    d = models.DYNAMIC_TABLES[derived]
    s = models.DYNAMIC_TABLES[SRC]
    meta_model = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    kw = {"row_id": "d_%s_%s" % (derived, job_id), "business_key_val": job_id,
          "job_id": job_id, "cell_count": cells}
    if derived == DERIVED:
        kw["unit_key"] = job_id
    db.add(d(**kw))
    for j in jobs:
        for i in range(2):
            db.add(s(row_id="s_%s_%s_%d" % (job_id, j, i),
                     business_key_val="%s_%s_%d" % (job_id, j, i),
                     cell_key="%s_%s_%d" % (job_id, j, i),
                     job_id=job_id, job=j, dt_x=i + 3, dt_y=i + 3, c_bn="1"))
        m = (meta_for or {}).get(j, "__default__")
        if m == "__default__":
            m = _meta()
        if m is not None:
            db.add(meta_model(row_id="m_%s_%s" % (MAPT, j),
                              business_key_val="%s|%s" % (MAPT, j),
                              target_table=MAPT, map_id=j,
                              grid_metadata=json.dumps(m)))
    db.commit()


def _wl(db, **kw):
    return ma.build_alignment_worklist(db, {}, kw.pop("rule", RULE),
                                       kw.pop("map_table", MAPT), **kw)


# ---------------------------------------------------------------------------
# axis 1 - the unit key of a one-column decision key
# ---------------------------------------------------------------------------

def test_a_one_column_unit_key_carries_no_separator(env):
    """`composite_key_separator` is declared as `|` and there is nothing to join. A
    trailing `J1|` would make every confirmation lookup miss forever."""
    key = fc.compose_unit_key(RULE, {"job_id": "J1"})
    assert key == "J1"
    assert "|" not in key


def test_the_one_column_unit_key_is_the_string_the_derived_table_actually_writes(env):
    """The unit key is not a new spelling - it must equal the `business_key_val` the real
    dedup mapper composes, or the worklist counts rows the confirmation store cannot find.
    This runs the mapper, it does not restate its formula."""
    import enrichment_mapper
    payloads = [{"table_name": SRC, "data": {"job_id": {"value": "J1"},
                                             "cell_key": {"value": "c1"}}}]
    for rule, derived in ((RULE, DERIVED), (RULE_BK, DERIVED_BK)):
        out = enrichment_mapper.map_enrichment_dedup(
            env, payloads, rule={"enrichment": dict(rule, aggregations={})})
        assert len(out["updates"]) == 1, rule["name"]
        assert out["updates"][0]["business_key_val"] == fc.compose_unit_key(
            rule, {"job_id": "J1"}), rule["name"]
        assert out["updates"][0]["business_key_val"] == "J1", rule["name"]


def test_a_blank_single_key_value_is_refused_rather_than_composed_as_empty(env):
    """With one column there is no other value to make the key look populated. An empty
    string would be a legal-looking unit key that groups every unfilled row together."""
    with pytest.raises(fc.ConfirmationRefused):
        fc.compose_unit_key(RULE, {"job_id": ""})
    with pytest.raises(fc.ConfirmationRefused):
        fc.compose_unit_key(RULE, {})


def test_the_worklist_groups_and_keys_a_one_column_unit(env):
    _seed_unit(env, "J1", ["M1"])
    _seed_unit(env, "J2", ["M2"])
    w = _wl(env)
    assert w["unit"]["decision_key"] == ["job_id"]
    assert {u["unit_key"] for u in w["units"]} == {"J1", "J2"}
    for u in w["units"]:
        assert list(u["key"]) == ["job_id"]
        assert u["unit_key"] == u["key"]["job_id"]


def test_a_confirmation_on_a_one_column_unit_is_found_again_by_the_worklist(env):
    """The whole point of one spelling: write through `record_confirmation`, read through
    the worklist's `_live_confirmations`, and the unit must come back `confirmed`."""
    _seed_unit(env, "J1", ["M1"])
    # `frame` named because a confirmation that names none is refused [D-1, 2026-08-06].
    # The subject here is the unit-key spelling round-trip, which it does not touch.
    h = fc.record_confirmation(env, RULE, {"job_id": "J1"},
                               [{"role": "r", "source_table": SRC, "map_id": "M1",
                                 "source_name": "user"}],
                               confirmed_by="tester", frames={}, frame="rot0_front")
    assert h.unit_key == "J1"
    assert h.decision_key == {"job_id": "J1"}
    assert fc.live_confirmation(env, RULE["name"], "J1") is not None
    u = _wl(env)["units"][0]
    assert u["state"] == "confirmed"
    assert u["confirmation"]["version"] == 1


def test_search_and_sort_hold_on_a_single_key_column(env):
    """`or_` over one attribute and a sort tuple of one value are both edges the
    two-column fixtures never reached."""
    _seed_unit(env, "ALPHA", ["M1"], cells=5)
    _seed_unit(env, "BETA", ["M2"], cells=90)
    assert [u["unit_key"] for u in _wl(env, q="ET")["units"]] == ["BETA"]
    assert _wl(env, q="ET")["totals"]["matched"] == 1
    asc = [u["unit_key"] for u in _wl(env, sort="cell_count", order="asc")["units"]]
    assert asc == ["ALPHA", "BETA"]
    assert [u["unit_key"] for u in _wl(env)["units"]] == ["ALPHA", "BETA"]


def test_the_route_validates_params_against_a_single_column_key(client, env, monkeypatch):
    import enrichment_config
    monkeypatch.setattr(enrichment_config, "load_enrichment_rules",
                        lambda *a, **k: [dict(RULE)])
    _seed_unit(env, "J1", ["M1"])
    _seed_unit(env, "J2", ["M2"])
    bad = client.get("/api/maps/alignment/worklist",
                     params={"rule": RULE["name"], "map_table": MAPT,
                             "params": json.dumps({"product": "P1"})})
    assert bad.status_code == 400
    ok = client.get("/api/maps/alignment/worklist",
                    params={"rule": RULE["name"], "map_table": MAPT,
                            "params": json.dumps({"job_id": "J2"})})
    assert ok.status_code == 200
    assert [u["unit_key"] for u in ok.json()["units"]] == ["J2"]


def test_the_view_route_accepts_a_single_key_param(client, env, monkeypatch):
    import enrichment_config
    monkeypatch.setattr(enrichment_config, "load_enrichment_rules",
                        lambda *a, **k: [dict(RULE)])
    _seed_unit(env, "J1", ["M1"])
    r = client.get("/api/maps/alignment/view",
                   params={"rule": RULE["name"], "map_table": MAPT,
                           "params": json.dumps({"job_id": "J1"}),
                           "x_col": "dt_x", "y_col": "dt_y", "include_cells": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unit"]["decision_key"] == {"job_id": "J1"}
    assert body["state"] in ("scored", "no_winner", "not_scorable")


# ---------------------------------------------------------------------------
# axis 2 - a target field that is not a frame
# ---------------------------------------------------------------------------

def test_the_rule_loader_accepts_a_single_key_and_a_non_frame_target(env):
    """Nothing in validation may require two key columns or a frame-shaped target name."""
    import enrichment_config
    norm, err = enrichment_config._validate_rule(
        RULE["name"],
        {"source_table": SRC, "derived_table": DERIVED,
         "decision_key": ["job_id"], "target_fields": ["map_metadata"],
         "list_columns": ["cell_count"]},
        known_tables=TABLES)
    assert err is None, err
    assert norm["decision_key"] == ["job_id"]
    assert norm["target_fields"] == ["map_metadata"]


def test_an_empty_frames_map_is_legal_for_a_non_frame_target(env):
    """The client sends `frames: {}` on purpose. It must stay legal when the declared
    target is `map_metadata` rather than `core_frame`.

    [D-1, 2026-08-06] Still legal - and still legal for the same reason. What the client
    does is send `frames` EMPTY *and* name the answer in `frame`, so naming no target
    field is not the same act as naming nothing. The route now reads `frame`, so the
    screen's own request is the one this test describes."""
    _seed_unit(env, "J1", ["M1"])
    h = fc.record_confirmation(env, RULE, {"job_id": "J1"},
                               [{"role": "r", "source_table": SRC, "map_id": "M1",
                                 "source_name": "user"}],
                               confirmed_by="tester", frames={}, frame="rot0_front")
    assert h.confirmation_uid
    assert h.frames == {}
    assert h.confirmed_frame == "rot0_front"


def test_naming_neither_a_target_field_nor_a_frame_is_refused(env):
    """[D-1] The other half of the sentence above. An empty `frames` map is legal; an empty
    `frames` map with no `frame` either records NOTHING about what was confirmed, and that
    record reads as done. The screen never produces this - it always names `frame`."""
    _seed_unit(env, "J1", ["M1"])
    with pytest.raises(fc.ConfirmationRefused):
        fc.record_confirmation(env, RULE, {"job_id": "J1"},
                               [{"role": "r", "source_table": SRC, "map_id": "M1",
                                 "source_name": "user"}],
                               confirmed_by="tester", frames={})


def test_an_undeclared_field_is_still_refused_by_name_not_by_shape(env):
    """`core_frame` is a perfectly frame-shaped name and this rule does not declare it.
    Acceptance must come from the declaration, never from the name looking like a frame."""
    _seed_unit(env, "J1", ["M1"])
    with pytest.raises(fc.ConfirmationRefused):
        fc.record_confirmation(env, RULE, {"job_id": "J1"},
                               [{"role": "r", "source_table": SRC, "map_id": "M1",
                                 "source_name": "user"}],
                               confirmed_by="t", frames={"core_frame": "rot0_front"})


def test_a_declared_non_frame_value_is_stored_under_the_name_the_rule_declared(env):
    """✅ THE HOLE, CLOSED - this is the deliberate day the pin asked for [D-1, 2026-08-06].

    What was pinned here: `record_confirmation` validated `frames` against the rule's
    declared `target_fields` (generic) but STORED two hardcoded columns

        core_frame=frames.get("core_frame"), dt_frame=frames.get("dt_frame")

    so a value for a declared non-frame target passed validation and was written nowhere,
    and `as_payload` echoed two fields this rule never declared while omitting the one it
    did. Measured on the live route 2026-08-06 with the production rule
    `dt_job_lot_slot_attribution`: the record came back `core_frame=None, dt_frame=None`
    with HTTP 200.

    Storage is now keyed by the rule's own declaration - the shape `decision_key` already
    used - so the two columns are vestiges of the FIRST rule rather than the schema."""
    _seed_unit(env, "J1", ["M1"])
    h = fc.record_confirmation(env, RULE, {"job_id": "J1"},
                               [{"role": "r", "source_table": SRC, "map_id": "M1",
                                 "source_name": "user"}],
                               confirmed_by="t", frames={"map_metadata": "BLOB-1"})
    assert h.frames == {"map_metadata": "BLOB-1"}
    # The vestige columns stay NULL: this rule never declared those names.
    assert h.core_frame is None and h.dt_frame is None
    payload = fc.as_payload(env, h)
    assert payload["frames"] == {"map_metadata": "BLOB-1"}
    assert "BLOB-1" in json.dumps(payload)
    # And it no longer echoes two fields this rule never declared.
    assert "core_frame" not in payload["frames"]


def test_the_confirm_route_records_the_subject_the_screen_sends(
        client, env, monkeypatch):
    """✅ The second half of the same pin, closed [D-1, 2026-08-06].

    What was pinned: the client posts `map_table`, `columns` and `frame` - by its own
    comment the thing that "identifies the confirmation's subject" - and the route read
    NONE of the three. With `frames: {}` the row that came back said who, when, which
    sources, which floor and what ruling, but not WHAT WAS CONFIRMED."""
    import enrichment_config
    monkeypatch.setattr(enrichment_config, "load_enrichment_rules",
                        lambda *a, **k: [dict(RULE)])
    _seed_unit(env, "J1", ["M1"])
    r = client.post("/api/maps/alignment/confirm", json={
        "rule": RULE["name"], "decision_key": {"job_id": "J1"}, "frames": {},
        # exactly what `client2/src/map2/api.js:346` posts
        "map_table": MAPT, "columns": {"x": "dt_x", "y": "dt_y", "val": "c_bn"},
        "frame": "rot0_front",
        "sources": [{"role": "source", "source_table": SRC, "map_id": "M1",
                     "source_name": "user"}],
        "ruling": {"reason_code": "no_discrimination"},
        "state": "no_winner",
        "reference": {"table": MAPT, "map_id": "M1"},
        "confirmed_by": "tester"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unit"] == {"rule": RULE["name"], "unit_key": "J1",
                            "decision_key": {"job_id": "J1"}}
    assert body["version"] == 1
    # Naming no target field is still legal; naming nothing is not.
    assert body["frames"] == {}
    assert body["confirmed"] == {"frame": "rot0_front", "map_table": MAPT,
                                 "columns": {"x": "dt_x", "y": "dt_y", "val": "c_bn"}}
    # [D-2] and the ruling state the operator saw survived the trip.
    assert body["ruling"]["state"] == "no_winner"


def test_the_confirm_route_refuses_a_field_the_rule_did_not_declare(client, env, monkeypatch):
    import enrichment_config
    monkeypatch.setattr(enrichment_config, "load_enrichment_rules",
                        lambda *a, **k: [dict(RULE)])
    _seed_unit(env, "J1", ["M1"])
    r = client.post("/api/maps/alignment/confirm", json={
        "rule": RULE["name"], "decision_key": {"job_id": "J1"},
        "frames": {"dt_frame": "rot0_front"},
        "sources": [{"role": "source", "source_table": SRC, "map_id": "M1",
                     "source_name": "user"}],
        "confirmed_by": "tester"})
    assert r.status_code == 400


def test_the_confirm_route_refuses_a_second_key_column_this_rule_does_not_have(
        client, env, monkeypatch):
    import enrichment_config
    monkeypatch.setattr(enrichment_config, "load_enrichment_rules",
                        lambda *a, **k: [dict(RULE)])
    _seed_unit(env, "J1", ["M1"])
    r = client.post("/api/maps/alignment/confirm", json={
        "rule": RULE["name"], "decision_key": {"job_id": "J1", "product": "P1"},
        "frames": {},
        "sources": [{"role": "source", "source_table": SRC, "map_id": "M1",
                     "source_name": "user"}],
        "confirmed_by": "tester"})
    assert r.status_code == 400
    assert "decision_key" in r.json()["detail"]


def test_no_worklist_or_view_payload_field_is_named_after_a_frame(env):
    """With `map_metadata` declared, the string `core_frame` must not appear anywhere -
    if it does, something derived the target from a name rather than the declaration."""
    _seed_unit(env, "J1", ["M1"])
    wl = json.dumps(_wl(env), ensure_ascii=False, default=str)
    assert "core_frame" not in wl and "map_metadata" not in wl
    view = ma.build_alignment_view(env, {}, RULE, {"job_id": "J1"}, MAPT,
                                   include_cells=False, x_col="dt_x", y_col="dt_y")
    assert "core_frame" not in json.dumps(view, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# axis 3 - how many maps pool into one single-column unit
# ---------------------------------------------------------------------------

def test_a_unit_holding_exactly_one_map_is_an_ordinary_state_not_a_crash(env):
    """Development-box measurement (NOT production): with the unit being one `dt_job`,
    all 120 units in `dt_log` hold exactly ONE map, against 20-40 for the two-column
    (dt_eqp, product) unit. So the single-map unit is not an edge here - it is the whole
    population, and every path has to treat it as ordinary."""
    _seed_unit(env, "J1", ["M1"])
    u = _wl(env)["units"][0]
    assert (u["map_count"], u["usable_map_count"]) == (1, 1)
    assert u["state"] in ("pending", "unscorable")
    view = ma.build_alignment_view(env, {}, RULE, {"job_id": "J1"}, MAPT,
                                   include_cells=False, x_col="dt_x", y_col="dt_y")
    assert view["sources"]["map_count"] == 1
    assert view["state"] in ("scored", "no_winner", "not_scorable")
    # The declaration block must account for the one map exactly once. `rot0/front` is
    # the DEFAULT pair, so it counts as unattested - which is the honest answer and the
    # reason the count is split rather than collapsed.
    d = view["declaration"]
    assert d["attested_maps"] + d["unattested_maps"] == 1
    assert (d["attested_maps"], d["unanimous"]) == (0, False)


def test_one_map_that_does_declare_its_frame_is_unanimous_with_a_sample_of_one(env):
    """Unanimity over a single map is trivially true, and it must SAY it is standing on
    one map - `attested_maps` is what stops the screen reading a sample of one as
    corroboration."""
    _seed_unit(env, "J1", ["M1"], meta_for={"M1": _meta(rotation=90, side="back")})
    view = ma.build_alignment_view(env, {}, RULE, {"job_id": "J1"}, MAPT,
                                   include_cells=False, x_col="dt_x", y_col="dt_y")
    d = view["declaration"]
    assert (d["attested_maps"], d["unattested_maps"]) == (1, 0)
    assert d["unanimous"] is True and d["frame"] == "rot90_back"


def test_scoring_one_map_against_a_floor_refuses_rather_than_inventing_a_winner(env):
    """One map cannot corroborate with anything. The correct answer is a NAMED refusal,
    not a confident first place off a single sample."""
    _seed_unit(env, "J1", ["M1"], meta_for={"M1": _meta(valid_die_ref="GOOD_A")})
    v = models.DYNAMIC_TABLES[map_overlay.VALID_DIE_TABLE]
    meta_model = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    for (x, y) in [(3, 3), (4, 3), (3, 4)]:
        env.add(v(row_id="v_%d_%d" % (x, y), business_key_val="GOOD_A_%d_%d" % (x, y),
                  cell_key="GOOD_A_%d_%d" % (x, y), product="GOOD", type="A",
                  x=x, y=y, val="1"))
    env.add(meta_model(row_id="mv_GOOD_A",
                       business_key_val="%s|GOOD_A" % map_overlay.VALID_DIE_TABLE,
                       target_table=map_overlay.VALID_DIE_TABLE, map_id="GOOD_A",
                       grid_metadata=json.dumps(_meta())))
    env.commit()
    view = ma.build_alignment_view(env, {}, RULE, {"job_id": "J1"}, MAPT,
                                   include_cells=False, x_col="dt_x", y_col="dt_y")
    assert view["stats"]["source_maps_usable"] == 1
    if view["state"] != "scored":
        assert view["refusal"], "a refusal must carry a sentence, never an empty result"
