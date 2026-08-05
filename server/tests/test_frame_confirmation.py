"""[Spec MAP_ALIGNMENT_SPEC 0.2 layer 8] The coordinate-system confirmation record.

The three things asserted here are exactly the three the enrichment path cannot carry --
the source LIST, the per-source alignment, and the VERSION. If any of them stops being
true, this record has no reason to exist separately from `eqp_frame_attribution`.
"""
import pytest

import frame_confirmation as fc
from database import models

# The unit is whatever the enrichment rule declares. These tests carry a miniature
# declaration rather than a column name, for the same reason the production code does not
# hardcode one: the moment a column name is written here it becomes a second spelling of
# the decision unit and can drift from `enrichment_rules.json`.
RULE = {"name": "eqp_product_frame_attribution",
        "derived_table": "eqp_frame_attribution",
        "decision_key": ["dt_eqp", "product"],
        "target_fields": ["core_frame", "dt_frame"]}

# 🔴 A SECOND RULE, AND IT IS NOT DECORATION. Every test above uses the rule whose
#    `target_fields` happen to be spelled the same as the two storage columns, so the whole
#    file passed while the storage could only hold ONE rule's answer. A fixture that only
#    exercises the coincidence cannot see the defect: measured 2026-08-06 against the live
#    route, `dt_job_lot_slot_attribution` recorded `core_frame=None, dt_frame=None` and
#    answered 200. This declaration is the defect axis - its target fields are neither
#    `core_frame` nor `dt_frame`, so anything that stores by hardcoded column name fails here.
OTHER_RULE = {"name": "dt_job_lot_slot_attribution",
              "derived_table": "dt_job_attribution",
              "decision_key": ["dt_job"],
              "target_fields": ["dt_lot_confirmed", "dt_slot_confirmed"]}


def _unit(eqp, product):
    return {"dt_eqp": eqp, "product": product}


def _contrib(role, table, name, frame="rot0_front", dx=0, dy=0, **kw):
    d = {"role": role, "source_table": table, "map_id": role + "_map",
         "source_name": name, "applied_frame": frame, "shift_dx": dx, "shift_dy": dy}
    d.update(kw)
    return d


def test_the_record_carries_the_source_list_one_row_per_contributor(db_session):
    """N sources consolidated leave N rows, not one blob."""
    contributors = [
        _contrib("total_chips", "core_wafer_map", "user"),
        _contrib("defect", "dt_log", "pipeline_parser", "rot90_front", -1, 2),
        _contrib("eds_fail", "dt_log", "chain_ingestion", "rot90_front", -1, 2),
    ]
    h = fc.record_confirmation(db_session, RULE, _unit("EQP-A", "P1"), contributors,
                               confirmed_by="tester",
                               frames={"dt_frame": "rot90_front"})

    rows = (db_session.query(models.FrameConfirmationSource)
            .filter_by(confirmation_uid=h.confirmation_uid).all())
    assert len(rows) == len(contributors)
    assert {r.role for r in rows} == {"total_chips", "defect", "eds_fail"}


def test_each_source_keeps_its_own_alignment_including_the_shift(db_session):
    """The frame alone is not the alignment. A dropped shift moves every die."""
    h = fc.record_confirmation(
        db_session, RULE, _unit("EQP-A", "P2"),
        [_contrib("total_chips", "core_wafer_map", "user"),
         _contrib("defect", "dt_log", "pipeline_parser", "rot90_front", -1, 2)],
        # Named because a confirmation that names no frame is now refused (D-1). The subject
        # of this test is the per-source shift, which is unchanged by naming the answer.
        confirmed_by="tester", frame="rot0_front")

    by_role = {r.role: r for r in db_session.query(models.FrameConfirmationSource)
               .filter_by(confirmation_uid=h.confirmation_uid)}
    assert (by_role["defect"].applied_frame, by_role["defect"].shift_dx,
            by_role["defect"].shift_dy) == ("rot90_front", -1, 2)
    assert (by_role["total_chips"].applied_frame, by_role["total_chips"].shift_dx,
            by_role["total_chips"].shift_dy) == ("rot0_front", 0, 0)


def test_a_re_confirmation_is_a_new_version_and_the_old_one_survives(db_session):
    """This is what `eqp_frame_attribution` structurally cannot do: its cell is UNIQUE per
    (table, row, column, source_name), so re-confirming overwrites in place and leaves the
    earlier decision with no identity for derived rows to point at."""
    v1 = fc.record_confirmation(
        db_session, RULE, _unit("EQP-B", "P1"),
        [_contrib("total_chips", "core_wafer_map", "user")],
        confirmed_by="tester", frames={"dt_frame": "rot0_front"})
    v2 = fc.record_confirmation(
        db_session, RULE, _unit("EQP-B", "P1"),
        [_contrib("total_chips", "core_wafer_map", "user")],
        confirmed_by="tester", frames={"dt_frame": "rot180_front"})

    assert (v1.version, v2.version) == (1, 2)
    assert v1.confirmation_uid != v2.confirmation_uid

    db_session.refresh(v1)
    assert v1.superseded_by == v2.confirmation_uid   # pointed at, not deleted
    assert v1.dt_frame == "rot0_front"               # the earlier decision is still readable
    assert v2.supersedes_uid == v1.confirmation_uid   # the chain walks both ways
    live = fc.live_confirmation(db_session, RULE["name"],
                                fc.compose_unit_key(RULE, _unit("EQP-B", "P1")))
    assert live.confirmation_uid == v2.confirmation_uid


def test_a_consolidated_record_carries_its_weakest_contributor(db_session):
    """Spec 0.2 layer 9. Three sources where one is unranked does not produce a confirmed
    record. The picker is the same expression graph_materializer uses for cell-layer truth,
    and both reach `crud.get_source_priority`, so the ordering has one origin."""
    contributors = [
        _contrib("total_chips", "core_wafer_map", "user"),            # priority 0
        _contrib("defect", "dt_log", "chain_ingestion"),              # priority 4
        _contrib("eds_fail", "dt_log", "some_ingested_file.csv"),     # unranked
    ]
    h = fc.record_confirmation(db_session, RULE, _unit("EQP-C", "P1"), contributors,
                               confirmed_by="tester", frame="rot0_front")

    assert h.weakest_source == "some_ingested_file.csv"
    assert h.weakest_priority == fc.UNRANKED

    # ...and the same input must give the same answer every run.
    assert fc.weakest_contributor(list(reversed(contributors)))[0] == h.weakest_source


def test_an_excluded_source_is_recorded_rather_than_omitted(db_session):
    """Otherwise "this source was never offered" and "this source was refused" become
    indistinguishable the moment anyone reads the record back."""
    h = fc.record_confirmation(
        db_session, RULE, _unit("EQP-D", "P1"),
        [_contrib("total_chips", "core_wafer_map", "user"),
         _contrib("used_chips", "bonding_log", "chain_ingestion",
                  frame=None, dx=None, dy=None, excluded_reason="meta_missing")],
        confirmed_by="tester", frame="rot0_front")

    rows = {r.role: r for r in db_session.query(models.FrameConfirmationSource)
            .filter_by(confirmation_uid=h.confirmation_uid)}
    assert rows["used_chips"].excluded_reason == "meta_missing"
    assert rows["used_chips"].applied_frame is None


def test_a_confirmation_with_no_contributors_is_refused(db_session):
    """"Which sources were consolidated" IS the content of this record."""
    with pytest.raises(fc.ConfirmationRefused):
        fc.record_confirmation(db_session, RULE, _unit("EQP-E", "P1"), [],
                               confirmed_by="tester")
    assert fc.live_confirmation(db_session, RULE["name"], fc.compose_unit_key(RULE, _unit("EQP-E", "P1"))) is None


def test_the_derived_cell_scope_is_a_query_and_never_a_deletion(db_session):
    """Spec 0.3 note 4: the stamp is at `cell_sources` granularity, and re-derivation stays
    with `chain_replay.withdraw_source`. This module hands over a scope, not a fourth
    spelling of retraction."""
    h = fc.record_confirmation(
        db_session, RULE, _unit("EQP-F", "P1"),
        [_contrib("total_chips", "core_wafer_map", "user")],
        confirmed_by="tester", frame="rot0_front")

    db_session.add(models.CellSource(
        table_name="eqp_frame_attribution", row_id="r1", column_name="dt_frame",
        source_name="user", value="rot0_front", confirmation_uid=h.confirmation_uid))
    db_session.add(models.CellSource(
        table_name="eqp_frame_attribution", row_id="r2", column_name="dt_frame",
        source_name="user", value="rot0_front"))          # unstamped, must stay outside
    db_session.commit()

    scope = fc.derived_cell_scope(db_session, h.confirmation_uid)
    assert [c.row_id for c in scope] == ["r1"]

    # Reading the scope removes nothing - the unstamped sibling is still there, and so is
    # the stamped one. Counted over the rows this test wrote, because the fixture database
    # carries rows from elsewhere and a whole-table count would assert about those instead.
    mine = (db_session.query(models.CellSource)
            .filter(models.CellSource.table_name == "eqp_frame_attribution",
                    models.CellSource.row_id.in_(["r1", "r2"])).all())
    assert sorted(c.row_id for c in mine) == ["r1", "r2"]


def test_a_half_bound_decision_unit_is_refused(db_session):
    """A confirmation of half a unit does not know what it confirmed. The view route may
    filter on a partial key; the write route may not."""
    with pytest.raises(fc.ConfirmationRefused) as e:
        fc.record_confirmation(db_session, RULE, {"dt_eqp": "EQP-G"},
                               [_contrib("total_chips", "core_wafer_map", "user")],
                               confirmed_by="tester")
    assert "product" in str(e.value)


def test_a_frame_target_the_rule_never_declared_is_refused(db_session):
    """`target_fields` is the canon for what may be confirmed, the same way `decision_key`
    is the canon for the unit. Neither is written down in this module."""
    with pytest.raises(fc.ConfirmationRefused):
        fc.record_confirmation(db_session, RULE, _unit("EQP-H", "P1"),
                               [_contrib("total_chips", "core_wafer_map", "user")],
                               confirmed_by="tester",
                               frames={"bonding_frame": "rot0_front"})


def test_a_rule_whose_targets_are_not_the_two_storage_columns_still_records_its_frames(
        db_session):
    """[D-1] The frames a rule DECLARES are the frames that get stored, whatever they are named.

    Storage used to be two columns named after the FIRST rule's target fields, so any other
    rule's answer went in as NULL and the write still succeeded. The field that records WHAT
    WAS CONFIRMED was empty on a record that read as done."""
    h = fc.record_confirmation(
        db_session, OTHER_RULE, {"dt_job": "SYN-IDX-FULL-R0"},
        [_contrib("source", "dt_map", "user")],
        confirmed_by="tester",
        frames={"dt_lot_confirmed": "rot0_front", "dt_slot_confirmed": "rot0_front"})

    assert h.frames == {"dt_lot_confirmed": "rot0_front",
                        "dt_slot_confirmed": "rot0_front"}
    assert fc.as_payload(db_session, h)["frames"] == {
        "dt_lot_confirmed": "rot0_front", "dt_slot_confirmed": "rot0_front"}


def test_the_two_legacy_columns_still_carry_the_first_rules_answer(db_session):
    """[D-1] Additive, not a replacement. `core_frame`/`dt_frame` are vestiges of the first
    declaration - the same standing `dt_eqp`/`product` already have - and demoting them must
    not stop them being readable for the rule that declared those names."""
    h = fc.record_confirmation(
        db_session, RULE, _unit("EQP-J", "P1"),
        [_contrib("total_chips", "core_wafer_map", "user")],
        confirmed_by="tester",
        frames={"core_frame": "rot0_front", "dt_frame": "rot90_front"})

    assert (h.core_frame, h.dt_frame) == ("rot0_front", "rot90_front")
    assert h.frames == {"core_frame": "rot0_front", "dt_frame": "rot90_front"}


def test_a_confirmation_that_names_no_frame_at_all_is_refused(db_session):
    """[D-1] The refusal the null exposed. A record whose "what was confirmed" is empty is
    worse than no record, because it reads as done. Naming nothing is now a 400, not a NULL."""
    with pytest.raises(fc.ConfirmationRefused) as e:
        fc.record_confirmation(db_session, OTHER_RULE, {"dt_job": "SYN-NOFRAME"},
                               [_contrib("source", "dt_map", "user")],
                               confirmed_by="tester", frames={})
    assert "프레임" in str(e.value)
    assert fc.live_confirmation(
        db_session, OTHER_RULE["name"],
        fc.compose_unit_key(OTHER_RULE, {"dt_job": "SYN-NOFRAME"})) is None


def test_a_declared_target_with_an_empty_frame_is_refused(db_session):
    """[D-1] Naming the field and leaving the answer blank is the same hole with a key on it."""
    with pytest.raises(fc.ConfirmationRefused):
        fc.record_confirmation(db_session, OTHER_RULE, {"dt_job": "SYN-BLANK"},
                               [_contrib("source", "dt_map", "user")],
                               confirmed_by="tester",
                               frames={"dt_lot_confirmed": ""})


def test_the_aligned_coordinates_are_the_subject_of_the_record(db_session):
    """[D-1] The primitive, by the 2026-08-05 ruling the client already implements
    (`client2/src/map2/api.js:349`): what a confirmation records is WHICH COORDINATES WERE
    ALIGNED - table, x, y, value, and the frame they were aligned at. The client has been
    sending exactly this in `frame`/`columns`/`map_table` and the route read none of it, so
    every confirmation made through the screen recorded no answer at all."""
    h = fc.record_confirmation(
        db_session, OTHER_RULE, {"dt_job": "SYN-SUBJ"},
        [_contrib("source", "dt_map", "user")],
        confirmed_by="tester", frame="rot0_front", map_table="dt_map",
        columns={"x": "DT_X", "y": "DT_Y", "val": "DT_BIN"})

    assert h.confirmed_frame == "rot0_front"
    assert (h.map_table, h.x_col, h.y_col, h.value_col) == (
        "dt_map", "DT_X", "DT_Y", "DT_BIN")
    out = fc.as_payload(db_session, h)
    assert out["confirmed"] == {"frame": "rot0_front", "map_table": "dt_map",
                                "columns": {"x": "DT_X", "y": "DT_Y", "val": "DT_BIN"}}


def test_a_named_frame_alone_satisfies_the_refusal(db_session):
    """[D-1] The screen sends `frames` EMPTY on purpose and names the frame in `frame`. That
    is an answer, so it must not be refused - the refusal is for recording NOTHING."""
    h = fc.record_confirmation(
        db_session, OTHER_RULE, {"dt_job": "SYN-FRAMEONLY"},
        [_contrib("source", "dt_map", "user")],
        confirmed_by="tester", frame="rot90_back", frames={})
    assert h.confirmed_frame == "rot90_back"


# ---------------------------------------------------------------------------
# [D-2] The ruling state. `/view` puts it at the TOP LEVEL of its response, never inside
# `ruling` - measured 2026-08-06: the live ruling dict has no `state` key at all. The write
# path read `ruling["state"]`, found nothing, and defaulted. The result was one record saying
# both "not scored" and "the winner is rot0_front".
# ---------------------------------------------------------------------------

LIVE_RULING = {"metric": "index", "placed_cells": 88, "source_map_count": 1,
               "excluded_map_count": 0, "excluded_reason_code": None,
               "margin": 87, "discriminating": 87, "winner": "rot0_front",
               "reason_code": None, "geometry_assumed": False}


def test_a_transported_state_is_recorded_rather_than_defaulted(db_session):
    """The operator's state, sent where `/view` puts it, survives to the record."""
    h = fc.record_confirmation(
        db_session, OTHER_RULE, {"dt_job": "SYN-STATE-1"},
        [_contrib("source", "dt_map", "user")],
        confirmed_by="tester", frame="rot0_front",
        ruling=dict(LIVE_RULING), state="scored")
    assert h.ruling_state == "scored"


def test_a_ruling_that_names_a_winner_is_never_recorded_as_unscored(db_session):
    """[D-2] THE DEFECT. `/view` does not put `state` inside `ruling`, so a client that
    forwards the ruling verbatim - which is what the route docstring instructs and what
    `client2/src/map2/decode.js:243` does - produced a record that contradicted itself."""
    h = fc.record_confirmation(
        db_session, OTHER_RULE, {"dt_job": "SYN-STATE-2"},
        [_contrib("source", "dt_map", "user")],
        confirmed_by="tester", frame="rot0_front", ruling=dict(LIVE_RULING))

    assert h.winner_frame == "rot0_front"
    assert h.ruling_state == "scored"
    assert h.ruling_state != "unscored"


def test_a_state_that_contradicts_its_own_winner_is_refused(db_session):
    """A ruling naming a winner IS a scored ruling (`map_alignment.build_alignment_view`
    decides the view's state by that same test). A record asserting otherwise is the
    incoherence this defect was, arriving explicitly instead of by default."""
    with pytest.raises(fc.ConfirmationRefused) as e:
        fc.record_confirmation(db_session, OTHER_RULE, {"dt_job": "SYN-STATE-3"},
                               [_contrib("source", "dt_map", "user")],
                               confirmed_by="tester", frame="rot0_front",
                               ruling=dict(LIVE_RULING), state="not_scorable")
    assert "rot0_front" in str(e.value)


def test_an_untransported_state_is_named_as_untransported_not_as_unscored(db_session):
    """A no-winner ruling is confirmable (the screen enables it - `view_model.js:941`), and
    from the ruling alone the write path cannot tell `no_winner` from `not_scorable`. It says
    so. `unscored` asserts scoring did not happen, and here it did."""
    h = fc.record_confirmation(
        db_session, OTHER_RULE, {"dt_job": "SYN-STATE-4"},
        [_contrib("source", "dt_map", "user")],
        confirmed_by="tester", frame="rot0_front",
        ruling={"winner": None, "reason_code": "tie", "margin": 0})
    assert h.ruling_state == fc.STATE_NOT_TRANSPORTED
    assert h.ruling_state != "unscored"


def test_the_state_vocabulary_has_one_origin(db_session):
    """The states are `map_alignment`'s. Spelling them here would make a second set that can
    drift from the one the screen was looking at - the same discipline `bonding_plan`'s
    BINDING_* block and this module's `_ASSUMED` token already follow."""
    import map_alignment
    assert fc.ACCEPTED_RULING_STATES == {map_alignment.STATE_SCORED,
                                         map_alignment.STATE_NO_WINNER,
                                         map_alignment.STATE_NOT_SCORABLE}


def test_the_unit_key_is_the_derived_tables_own_key_spelling(db_session):
    """`unit_key` has to be the same string `eqp_frame_attribution.business_key_val` carries,
    otherwise the record and the enrichment row describe the same decision under two names."""
    from database import crud
    sep = (crud.TABLE_CONFIG.get(RULE["derived_table"]) or {}).get(
        "composite_key_separator", "_")
    assert fc.compose_unit_key(RULE, _unit("EQP-I", "P1")) == sep.join(["EQP-I", "P1"])


# ---------------------------------------------------------------------------
# The route. Layer 8 is the only write in the chain, so the tests that matter most are
# the ones asserting it cannot be reached by accident.
# ---------------------------------------------------------------------------

CONFIRM_ROUTE = "/api/maps/alignment/confirm"


@pytest.fixture
def declared_rule(monkeypatch):
    """`enrichment_rules.json` is a gitignored site asset and the suite replaces
    `crud.TABLE_CONFIG` with a SQLite-shaped fixture, so the real rule is not loadable here.
    Serving the declaration from the fixture keeps these tests about the ROUTE - its
    validation, its refusals, its response - rather than about one site's config file."""
    import enrichment_config
    monkeypatch.setattr(enrichment_config, "load_enrichment_rules",
                        lambda **kw: [RULE])
    return RULE


def _body(**over):
    b = {
        "rule": "eqp_product_frame_attribution",
        "decision_key": {"dt_eqp": "EQP-R1", "product": "P1"},
        "frames": {"core_frame": "rot0_front", "dt_frame": "rot90_front"},
        "reference": {"table": "core_wafer_map", "map_id": "M1"},
        "ruling": {"state": "scored", "winner": "rot90_front", "margin": 7,
                   "discriminating": 40},
        "sources": [dict(_contrib("total_chips", "core_wafer_map", "user")),
                    dict(_contrib("defect", "dt_log", "chain_ingestion",
                                  "rot90_front", -1, 2))],
        "confirmed_by": "tester",
    }
    b.update(over)
    return b


def test_the_write_has_no_get_twin(client):
    """Exploring writes nothing. A GET that reaches layer 8 would make the read path
    capable of the one thing the read path must never do."""
    assert client.get(CONFIRM_ROUTE).status_code == 404


def test_the_route_records_and_returns_what_it_just_wrote(client, declared_rule):
    """The screen must not have to re-fetch to find out what it did."""
    res = client.post(CONFIRM_ROUTE, json=_body())
    assert res.status_code == 200
    out = res.json()
    assert out["confirmation_uid"].startswith("fc_")
    assert out["version"] == 1
    assert out["unit"]["decision_key"] == {"dt_eqp": "EQP-R1", "product": "P1"}
    assert out["frames"]["dt_frame"] == "rot90_front"
    # The ruling came back exactly as sent - the write path did not re-score it.
    assert out["ruling"]["winner"] == "rot90_front" and out["ruling"]["margin"] == 7
    assert {s["role"] for s in out["sources"]} == {"total_chips", "defect"}
    assert out["weakest"]["source_name"] == "chain_ingestion"


def test_a_second_confirmation_through_the_route_is_version_two(client, declared_rule):
    first = client.post(CONFIRM_ROUTE, json=_body(
        decision_key={"dt_eqp": "EQP-R2", "product": "P1"})).json()
    second = client.post(CONFIRM_ROUTE, json=_body(
        decision_key={"dt_eqp": "EQP-R2", "product": "P1"},
        frames={"dt_frame": "rot180_front"})).json()
    assert (first["version"], second["version"]) == (1, 2)
    assert second["supersedes"] == first["confirmation_uid"]


@pytest.fixture
def other_declared_rule(monkeypatch):
    """The rule whose target fields are not the two storage columns - the defect axis, served
    through the route rather than only the module."""
    import enrichment_config
    monkeypatch.setattr(enrichment_config, "load_enrichment_rules",
                        lambda **kw: [RULE, OTHER_RULE])
    return OTHER_RULE


def _screen_body(**over):
    """The body `client2/src/map2/api.js:346` actually posts. Not a body invented here: the
    screen sends `frames` EMPTY by ruling and names the answer in `frame`/`columns`/
    `map_table`, and it forwards `/view`'s ruling verbatim - which carries no `state`."""
    b = {
        "rule": "dt_job_lot_slot_attribution",
        "decision_key": {"dt_job": "SYN-IDX-FULL-R0"},
        "frames": {},
        "map_table": "dt_map",
        "columns": {"x": "DT_X", "y": "DT_Y", "val": "DT_BIN"},
        "frame": "rot0_front",
        "sources": [dict(_contrib("source", "dt_map", "user"))],
        "ruling": dict(LIVE_RULING),
        "reference": {"table": "valid_die_ref", "map_id": "PRD-A_DT13"},
        "confirmed_by": "tester",
    }
    b.update(over)
    return b


def test_the_route_records_what_the_screen_actually_sends(client, other_declared_rule):
    """[D-1 + D-2, through the route] Reproduced against the live server 2026-08-06: this
    exact body returned 200 with `core_frame: null, dt_frame: null` and
    `ruling.state: "unscored"` beside `winner: "rot0_front"`."""
    res = client.post(CONFIRM_ROUTE, json=_screen_body())
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["confirmed"]["frame"] == "rot0_front"
    assert out["confirmed"]["map_table"] == "dt_map"
    assert out["confirmed"]["columns"] == {"x": "DT_X", "y": "DT_Y", "val": "DT_BIN"}
    assert out["ruling"]["state"] == "scored"
    assert out["ruling"]["winner"] == "rot0_front"


def test_the_route_takes_the_state_from_where_the_view_puts_it(client, other_declared_rule):
    """`/view` answers `state` at the TOP LEVEL of its response, so that is where the confirm
    body carries it. One transcription rule for the screen: copy `ruling` and copy `state`."""
    res = client.post(CONFIRM_ROUTE, json=_screen_body(
        decision_key={"dt_job": "SYN-TOPSTATE"},
        ruling={"winner": None, "reason_code": "tie", "margin": 0},
        state="no_winner"))
    assert res.status_code == 200, res.text
    assert res.json()["ruling"]["state"] == "no_winner"


def test_the_route_refuses_a_confirmation_that_names_no_frame(client, other_declared_rule):
    res = client.post(CONFIRM_ROUTE, json=_screen_body(
        decision_key={"dt_job": "SYN-ROUTE-NOFRAME"}, frame=None, frames={}))
    assert res.status_code == 400


@pytest.mark.parametrize("bad,field", [
    ({"decision_key": {"dt_eqp": "EQP-R3"}}, "product"),
    ({"decision_key": {"not_a_key": "x"}}, "invalid"),
    ({"frames": {"bonding_frame": "rot0_front"}}, "bonding_frame"),
    ({"sources": []}, None),
    ({"confirmed_by": ""}, "confirmed_by"),
    ({"rule": "no_such_rule"}, None),
    # [D-2] An explicit state that contradicts the ruling it travelled with.
    ({"state": "not_scorable"}, "rot90_front"),
    # [D-1] A state outside the vocabulary `map_alignment` declares.
    ({"state": "probably_fine"}, "probably_fine"),
])
def test_a_refused_confirmation_writes_nothing(client, db_session, declared_rule, bad, field):
    """Every refusal path is also a no-write path. A half-written confirmation claims to
    carry a source list while carrying the wrong one, which is worse than none."""
    before = db_session.query(models.FrameConfirmation).count()
    res = client.post(CONFIRM_ROUTE, json=_body(**bad))
    assert res.status_code in (400, 404)
    if field:
        assert field in res.json()["detail"]
    assert db_session.query(models.FrameConfirmation).count() == before
