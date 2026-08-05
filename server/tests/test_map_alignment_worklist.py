"""The alignment WORKLIST: which decision unit should the operator open.

WHY THE UNSCORABLE TESTS ARE THE LOAD-BEARING ONES
Roughly half the map population cannot be aligned at all - on the development box
`wafer_map_metadata` holds 668 rows of which 320 are `auto_registered`, and all 8
`valid_die_ref` declarations resolve to nothing. So `unscorable` is the COMMON case,
not an edge, and the tests that matter are the ones asserting it is a first-class state
with a NAMED cause rather than a zero, a null, or an empty list. A worklist that renders
"0 maps / no score" for half its rows has told the operator nothing about what to fix.

WHY THERE IS NO FRAME-FIELD AXIS HERE
`core_frame`/`dt_frame` are NAMES. The units are the coordinate columns, and which pair
gets read is chosen at the view route. The worklist answers only what is independent of
that choice, and `test_the_worklist_never_names_a_frame_field` is what keeps it so.
"""
import json

import pytest

import map_alignment as ma
import map_overlay
from database import crud, models

# Test table names carry a prefix that cannot exist in the operator's gitignored
# `config/table_config.json`. A collision there makes `init_dynamic_models` win the
# shared in-memory sqlite schema and `create_all(checkfirst)` skip - which surfaces as
# `no such column` months later, when the operator happens to add a table of that name.
SRC = "wl_test_log"
DERIVED = "wl_test_unit"
MAPT = "wl_test_map"
OTHER_MAPT = "wl_test_othermap"
UNKEYED_MAPT = "wl_test_unkeyed"

PHYS = {"phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}

RULE = {"name": "wl_test_rule", "source_table": SRC, "derived_table": DERIVED,
        "decision_key": ["eqp", "product"], "target_fields": ["core_frame", "dt_frame"],
        "list_columns": ["cell_count"]}

TABLES = {
    SRC: {"business_key": "cell_key",
          "column_types": {"cell_key": "string", "eqp": "string", "product": "string",
                           "job": "string", "other_key": "string",
                           "dt_x": "number", "dt_y": "number",
                           "core_x": "number", "core_y": "number", "c_bn": "string"},
          "map_key_columns": ["job"]},
    DERIVED: {"business_key": "unit_key", "composite_key_separator": "|",
              "composite_key_source": ["eqp", "product"],
              "column_types": {"unit_key": "string", "eqp": "string",
                               "product": "string", "cell_count": "number"}},
    MAPT: {"business_key": "cell_key",
           "column_types": {"cell_key": "string", "job": "string",
                            "dt_x": "number", "dt_y": "number", "c_bn": "string"},
           "map_key_columns": ["job"]},
    OTHER_MAPT: {"business_key": "cell_key",
                 "column_types": {"cell_key": "string", "other_key": "string",
                                  "dt_x": "number", "dt_y": "number"},
                 "map_key_columns": ["other_key"]},
    # Declared as a map table, but keyed on a column the source does not have.
    UNKEYED_MAPT: {"business_key": "cell_key",
                   "column_types": {"cell_key": "string", "absent_col": "string"},
                   "map_key_columns": ["absent_col"]},
    # The metadata table is PRODUCT-OWNED - its real declaration lives in
    # `table_config.json` and is repeated here verbatim. Inventing a business key for it
    # would redefine the shared model, and `Base.metadata` outlives one test: the first
    # run would fail on a column the already-created table does not have and every run
    # after it would pass, which reads as flakiness rather than as the fixture's fault.
    # The floor store is PINNED to this table name (`map_overlay.VALID_DIE_TABLE`, ruling
    # 1-a), so a fixture cannot rename it out of the way. Its declaration is therefore
    # copied verbatim from `table_config.json` for the same reason the metadata table's is:
    # `Base.metadata` is shared, so a fixture that invents a different shape breaks the
    # first run and passes every run after it.
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


def _auto_meta(**kw):
    """The shape 320 of the 668 production rows carry: values present, but flagged as
    synthetic. `geometry_declaration` refuses it, and that refusal is the whole reason
    `unscorable` dominates."""
    m = _meta(**kw)
    m.update({"phys_chip_x": 1, "phys_chip_y": 1, "auto_registered": True})
    return m


@pytest.fixture()
def env(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    map_overlay._FRAME_TF_CACHE.clear()
    return db_session


def _seed_unit(db, eqp, product, jobs, cells=10, meta_for=None, other_keys=()):
    """One decision unit: a derived-table row plus its source rows and map metas.

    `meta_for` maps job -> meta dict (or None to leave the map unregistered), which is
    how a fixture chooses between the three unscorable causes without the test having to
    know how the judgement is spelled.
    """
    d = models.DYNAMIC_TABLES[DERIVED]
    s = models.DYNAMIC_TABLES[SRC]
    meta_model = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    key = "%s|%s" % (eqp, product)
    db.add(d(row_id="d_" + key, business_key_val=key, unit_key=key,
             eqp=eqp, product=product, cell_count=cells))
    for j in jobs:
        for i in range(2):
            db.add(s(row_id="s_%s_%s_%d" % (key, j, i),
                     business_key_val="%s_%s_%d" % (key, j, i),
                     cell_key="%s_%s_%d" % (key, j, i), eqp=eqp, product=product,
                     job=j, other_key=(other_keys[0] if other_keys else "OK1"),
                     dt_x=i, dt_y=i, core_x=i, core_y=i, c_bn="1"))
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
    return ma.build_alignment_worklist(db, {}, RULE, kw.pop("map_table", MAPT), **kw)


# ---------------------------------------------------------------------------
# the unit comes from the rule, not from a column name
# ---------------------------------------------------------------------------

def test_the_unit_is_whatever_the_rule_declares_and_is_echoed_back(env):
    _seed_unit(env, "E1", "P1", ["J1"])
    w = _wl(env)
    assert w["unit"]["decision_key"] == RULE["decision_key"]
    assert w["unit"]["rule"] == RULE["name"]
    assert list(w["units"][0]["key"]) == RULE["decision_key"]


def test_the_unit_key_is_the_same_string_the_confirmation_record_composes(env):
    """If the worklist composed its own unit key, a confirmed unit would look pending -
    the lookup would simply miss. One spelling, in `frame_confirmation`."""
    import frame_confirmation as fc
    _seed_unit(env, "E1", "P1", ["J1"])
    w = _wl(env)
    assert w["units"][0]["unit_key"] == fc.compose_unit_key(
        RULE, {"eqp": "E1", "product": "P1"})


def test_the_worklist_never_names_a_frame_field(env):
    """`core_frame`/`dt_frame` are names, not units. The moment one appears in this
    payload it becomes a second place that fact is written."""
    _seed_unit(env, "E1", "P1", ["J1"])
    blob = json.dumps(_wl(env), ensure_ascii=False, default=str)
    for name in RULE["target_fields"]:
        assert name not in blob, "%s leaked into the worklist payload" % name


# ---------------------------------------------------------------------------
# the three states, and the one that dominates
# ---------------------------------------------------------------------------

def test_the_state_vocabulary_is_closed(env):
    _seed_unit(env, "E1", "P1", ["J1"])
    w = _wl(env)
    assert set(w["states"]) == {"pending", "confirmed", "unscorable"}
    for u in w["units"]:
        assert u["state"] in w["states"]


def test_a_unit_with_no_registered_map_is_unscorable_and_says_which(env):
    _seed_unit(env, "E1", "P1", ["J1", "J2"], meta_for={"J1": None, "J2": None})
    u = _wl(env)["units"][0]
    assert u["state"] == "unscorable"
    assert u["reason_code"] == ma.EXCLUDE_META_MISSING
    # not a zero and not a null: the maps ARE there, their specs are not.
    assert (u["map_count"], u["usable_map_count"]) == (2, 0)


def test_an_auto_registered_population_is_unscorable_not_scored_at_zero(env):
    """320 of 668 production metas look like this. Rendering them as a score of nothing
    is the exact opposite statement from 'there was nothing to measure'."""
    _seed_unit(env, "E1", "P1", ["J1", "J2"],
               meta_for={"J1": _auto_meta(), "J2": _auto_meta()})
    u = _wl(env)["units"][0]
    assert (u["state"], u["reason_code"]) == ("unscorable", ma.EXCLUDE_GEOMETRY_REFUSED)
    assert u["usable_map_count"] == 0


def test_a_usable_population_with_no_reference_is_unscorable_for_the_reference(env):
    """The dominant production cause: geometry is fine, there is simply no valid-die map.
    Reporting it as `geometry_refused` would send the operator to fix the wrong thing."""
    _seed_unit(env, "E1", "P1", ["J1"])
    u = _wl(env)["units"][0]
    assert (u["state"], u["reason_code"]) == ("unscorable", ma.REASON_REFERENCE_ABSENT)
    assert u["usable_map_count"] == 1


def test_a_confirmed_geometry_counts_as_usable_and_is_not_offered_the_assumption(env):
    """[D7] The list and the detail must not disagree about the same map.

    A confirmed geometry is not `declared` — nobody measured this map — so a counter that
    asks "is this declared?" calls it unusable AND offers to borrow for it, while the
    detail scores it without borrowing anything (`phys_needs_basis` is False). Both
    counters therefore ask the DETAIL's question, and this is the fixture that separates
    the two questions: the meta below carries no `phys_*` declaration of its own beyond the
    derived values and the marker, so `geometry_declaration` answers `confirmed`, not
    `declared`.
    """
    confirmed = _meta()
    confirmed[map_overlay.PHYS_CONFIRMED_KEY] = {
        "table": map_overlay.VALID_DIE_TABLE, "map_id": "PRD_A",
        "confirmation_uid": "fc_seed", "confirmed_by": "operator",
        "confirmed_at": "2026-08-06T00:00:00+00:00"}
    _seed_unit(env, "E1", "P1", ["J1"], meta_for={"J1": confirmed})

    u = _wl(env)["units"][0]
    assert map_overlay.geometry_declaration(confirmed) == map_overlay.GEOMETRY_CONFIRMED
    assert map_overlay.geometry_declaration(confirmed) != map_overlay.GEOMETRY_DECLARED
    assert u["usable_map_count"] == 1, "the list called a confirmed map unusable"
    assert u["assumable_map_count"] == 0, \
        "the list offered to borrow geometry for a map that already has confirmed geometry"


def test_a_declared_but_unresolvable_reference_is_a_different_cause(env):
    """'no reference declared' and 'the declared reference does not resolve' need
    different repairs, so they cannot collapse into one code."""
    _seed_unit(env, "E1", "P1", ["J1"],
               meta_for={"J1": _meta(valid_die_ref="NOT_REGISTERED")})
    u = _wl(env)["units"][0]
    assert (u["state"], u["reason_code"]) == ("unscorable", ma.REASON_REFERENCE_REFUSED)


def test_a_map_table_the_source_cannot_key_is_named_not_silently_empty(env):
    _seed_unit(env, "E1", "P1", ["J1"])
    w = _wl(env, map_table=UNKEYED_MAPT)
    assert w["units"][0]["reason_code"] == ma.REASON_MAP_KEYS_UNAVAILABLE
    cat = {c["table"]: c for c in w["selection"]["map_tables"]}
    assert cat[UNKEYED_MAPT]["selectable"] is False
    assert "absent_col" in cat[UNKEYED_MAPT]["reason"]
    assert cat[MAPT]["selectable"] is True


def test_a_live_confirmation_makes_the_unit_confirmed(env):
    import frame_confirmation as fc
    _seed_unit(env, "E1", "P1", ["J1"])
    fc.record_confirmation(env, RULE, {"eqp": "E1", "product": "P1"},
                           [{"role": "r", "source_table": SRC, "map_id": "J1",
                             "source_name": "user"}],
                           confirmed_by="tester", frames={"dt_frame": "rot0_front"})
    u = _wl(env)["units"][0]
    assert u["state"] == "confirmed"
    assert u["confirmation"]["version"] == 1
    assert u["confirmation"]["confirmed_by"] == "tester"


def test_a_superseded_confirmation_alone_does_not_confirm_the_unit(env):
    """Only the LIVE record counts. Reading superseded rows would keep a unit marked
    confirmed after its decision was withdrawn."""
    import frame_confirmation as fc
    from database import models as m
    _seed_unit(env, "E1", "P1", ["J1"])
    # `frame` named because a confirmation that names none is refused [D-1, 2026-08-06].
    # The subject here is which record the worklist reads, not what was confirmed.
    h = fc.record_confirmation(env, RULE, {"eqp": "E1", "product": "P1"},
                               [{"role": "r", "source_table": SRC, "map_id": "J1",
                                 "source_name": "user"}],
                               confirmed_by="tester", frame="rot0_front")
    h.superseded_by = "gone"
    env.commit()
    assert _wl(env)["units"][0]["state"] == "unscorable"


# ---------------------------------------------------------------------------
# the aggregate the client is told not to compute
# ---------------------------------------------------------------------------

def test_the_unscorable_total_is_counted_by_the_server(env):
    _seed_unit(env, "E1", "P1", ["J1"], meta_for={"J1": None})
    _seed_unit(env, "E1", "P2", ["J3"], meta_for={"J3": None})
    _seed_unit(env, "E2", "P1", ["J5"], meta_for={"J5": None})
    w = _wl(env)
    assert w["totals"]["unscorable"] == 3
    assert w["totals"]["by_state"] == {"pending": 0, "confirmed": 0, "unscorable": 3}


def test_the_aggregate_covers_every_judged_unit_not_just_the_returned_page(env):
    """The client sinks unscorable rows below a boundary and names the total ONCE. A
    total computed after the page cut would name a smaller number than the truth."""
    for i in range(5):
        _seed_unit(env, "E%d" % i, "P1", ["J%d" % i], meta_for={"J%d" % i: None})
    w = _wl(env, limit=2)
    assert w["totals"]["returned"] == 2
    assert w["totals"]["judged"] == 5
    assert w["totals"]["unscorable"] == 5


def test_the_sentence_is_composed_once_per_cause_not_once_per_row(env):
    """A per-row sentence makes the index heavier than the thing it indexes, and the
    extra bytes are the same sentence repeated - not information."""
    for i in range(4):
        _seed_unit(env, "E%d" % i, "P1", ["J%d" % i], meta_for={"J%d" % i: None})
    w = _wl(env)
    sentence = ma._WORKLIST_REASON_TEXT[ma.EXCLUDE_META_MISSING]
    assert json.dumps(w["unscorable_reasons"], ensure_ascii=False).count(sentence) == 1
    assert json.dumps(w["units"], ensure_ascii=False).count(sentence) == 0
    assert [r["count"] for r in w["unscorable_reasons"]] == [4]


def test_the_refusal_sentence_has_exactly_one_spelling(env):
    """The list and the detail view answer the same fact. Spelled twice, one gets fixed
    and the same unit says different things in two places - the two-spelling defect."""
    detail = ma.compose_refusal(ma.STATE_NOT_SCORABLE,
                                {"state": ma.REFERENCE_ABSENT}, ma._Excluded(),
                                {}, 1, [])
    assert detail == ma.TEXT_REFERENCE_ABSENT
    assert ma._WORKLIST_REASON_TEXT[ma.REASON_REFERENCE_ABSENT] == ma.TEXT_REFERENCE_ABSENT
    assert ma.TEXT_REFERENCE_ABSENT == "기준 없음 - 유효 다이 맵 미지정"


def test_no_metric_in_the_payload_is_a_percentage(env):
    _seed_unit(env, "E1", "P1", ["J1", "J2"], meta_for={"J1": None})
    w = _wl(env)
    for u in w["units"]:
        for k, v in u.items():
            assert "percent" not in k and "pct" not in k and "ratio" not in k
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                assert float(v) == int(v), "%s is fractional - a count is not a ratio" % k
    assert "%" not in json.dumps(w, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# search and sort are the server's job
# ---------------------------------------------------------------------------

def test_search_is_a_substring_over_the_key_values(env):
    _seed_unit(env, "ALPHA", "P1", ["J1"])
    _seed_unit(env, "BETA", "P1", ["J2"])
    _seed_unit(env, "GAMMA", "P2", ["J3"])
    assert [u["key"]["eqp"] for u in _wl(env, q="ET")["units"]] == ["BETA"]
    assert {u["key"]["eqp"] for u in _wl(env, q="P1")["units"]} == {"ALPHA", "BETA"}
    assert _wl(env, q="ET")["totals"]["matched"] == 1


def test_search_narrows_before_the_rows_are_judged(env):
    """Filtering after judging would do the whole map/meta pass for rows nobody asked
    for - which is the cost the search exists to avoid."""
    _seed_unit(env, "ALPHA", "P1", ["J1"])
    _seed_unit(env, "BETA", "P1", ["J2"])
    w = _wl(env, q="ALPHA")
    assert w["totals"]["judged"] == 1
    assert w["stats"]["metas_read"] == 1


def test_the_client_names_the_sort_and_both_directions_hold(env):
    _seed_unit(env, "E1", "P1", ["J1"], cells=5)
    _seed_unit(env, "E2", "P1", ["J2", "J3"], cells=90)
    asc = [u["unit_key"] for u in _wl(env, sort="map_count", order="asc")["units"]]
    desc = [u["unit_key"] for u in _wl(env, sort="map_count", order="desc")["units"]]
    assert asc == list(reversed(desc))
    assert desc[0] == "E2|P1"
    by_cells = _wl(env, sort="cell_count", order="desc")["units"]
    assert by_cells[0]["unit_key"] == "E2|P1"


def test_a_declared_list_column_becomes_a_sort_key_without_being_named_in_code(env):
    assert "cell_count" in ma.worklist_sort_keys(RULE)
    assert "cell_count" not in ma.worklist_sort_keys(dict(RULE, list_columns=[]))


def test_sorting_by_state_orders_on_strength_not_on_the_spelling(env):
    """Alphabetically `confirmed` < `pending` < `unscorable`, which is neither the
    weakest-first nor the strongest-first order the screen wants."""
    assert (ma.UNIT_STATE_STRENGTH["unscorable"]
            < ma.UNIT_STATE_STRENGTH["pending"]
            < ma.UNIT_STATE_STRENGTH["confirmed"])
    import frame_confirmation as fc
    _seed_unit(env, "E1", "P1", ["J1"], meta_for={"J1": None})
    _seed_unit(env, "E2", "P1", ["J2"])
    fc.record_confirmation(env, RULE, {"eqp": "E2", "product": "P1"},
                           [{"role": "r", "source_table": SRC, "map_id": "J2",
                             "source_name": "user"}], confirmed_by="t",
                           frame="rot0_front")
    states = [u["state"] for u in _wl(env, sort="state", order="desc")["units"]]
    assert states == ["confirmed", "unscorable"]


def test_paging_slices_after_the_sort(env):
    for i in range(4):
        _seed_unit(env, "E%d" % i, "P1", ["J%d" % i], cells=i)
    page = _wl(env, sort="cell_count", order="desc", limit=2, offset=1)
    assert [u["unit_key"] for u in page["units"]] == ["E2|P1", "E1|P1"]


# ---------------------------------------------------------------------------
# scale: the cost is the map population, not the log
# ---------------------------------------------------------------------------

def test_map_specs_are_read_in_one_pass_not_once_per_map(env):
    """`load_map_meta` per map is N+1, and here N is the MAP population - 544 core maps
    for four units on the development box."""
    calls = []
    orig = map_overlay.load_map_meta

    def spy(db, table, map_id):
        calls.append(map_id)
        return orig(db, table, map_id)

    map_overlay.load_map_meta = spy
    try:
        _seed_unit(env, "E1", "P1", ["J%d" % i for i in range(12)])
        w = _wl(env)
    finally:
        map_overlay.load_map_meta = orig
    assert w["units"][0]["map_count"] == 12
    assert w["stats"]["metas_read"] == 12
    # The only per-map loader call allowed is the reference resolution, which is one
    # lookup for the whole request - never one per source map.
    assert len(calls) <= 1, "map specs were read one at a time: %s" % calls


def test_one_reference_is_resolved_once_for_the_whole_request(env):
    """Every unit asking the same question would otherwise re-query the same reference
    map - N+1 across units instead of across maps."""
    calls = []
    orig = map_overlay.load_map_meta

    def spy(db, table, map_id):
        calls.append((table, map_id))
        return orig(db, table, map_id)

    for i in range(4):
        _seed_unit(env, "E%d" % i, "P1", ["J%d" % i],
                   meta_for={"J%d" % i: _meta(valid_die_ref="SHARED_REF")})
    map_overlay.load_map_meta = spy
    try:
        w = _wl(env)
    finally:
        map_overlay.load_map_meta = orig
    assert w["totals"]["unscorable"] == 4
    assert len(calls) == 1, "the same reference was resolved per unit: %s" % calls


def test_truncation_is_announced_and_never_silent(env):
    for i in range(4):
        _seed_unit(env, "E%d" % i, "P1", ["J%d" % i])
    w = ma.build_alignment_worklist(env, {}, RULE, MAPT, unit_cap=2)
    assert w["totals"]["units_truncated"] is True
    assert w["totals"]["judged"] == 2
    assert w["totals"]["matched"] == 4


def test_the_worklist_writes_nothing(env):
    _seed_unit(env, "E1", "P1", ["J1"])
    before = {t: env.query(models.DYNAMIC_TABLES[t]).count()
              for t in (SRC, DERIVED, map_overlay.META_TABLE)}
    before["fc"] = env.query(models.FrameConfirmation).count()
    _wl(env)
    after = {t: env.query(models.DYNAMIC_TABLES[t]).count()
             for t in (SRC, DERIVED, map_overlay.META_TABLE)}
    after["fc"] = env.query(models.FrameConfirmation).count()
    assert before == after


# ---------------------------------------------------------------------------
# what the operator selects - the gap this route closes
# ---------------------------------------------------------------------------

def _seed_floor(db, product, type_, cells, register=True, values=True):
    """A floor needs BOTH halves: cells under a key that splits, and a metadata row.
    `register=False` seeds only the cells - the shape that is declared but does not resolve."""
    v = models.DYNAMIC_TABLES[map_overlay.VALID_DIE_TABLE]
    meta_model = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    for (x, y) in cells:
        db.add(v(row_id="v_%s_%s_%d_%d" % (product, type_, x, y),
                 business_key_val="%s_%s_%d_%d" % (product, type_, x, y),
                 cell_key="%s_%s_%d_%d" % (product, type_, x, y),
                 product=product, type=type_, x=x, y=y,
                 val=("1" if values else None)))
    if register:
        map_id = "%s_%s" % (product, type_)
        db.add(meta_model(row_id="mv_" + map_id,
                          business_key_val="%s|%s" % (map_overlay.VALID_DIE_TABLE, map_id),
                          target_table=map_overlay.VALID_DIE_TABLE, map_id=map_id,
                          grid_metadata=json.dumps(_meta())))
    db.commit()


def test_only_references_that_actually_resolve_are_offered(env):
    """Eight `valid_die_ref` declarations exist on the development box and ZERO of them
    resolve. Listing what is declared would put eight unselectable names in the picker and
    teach the operator that the picker lies. The list carries what can be chosen."""
    _seed_unit(env, "E1", "P1", ["J1"])
    _seed_floor(env, "GOOD", "A", [(3, 3), (4, 3), (3, 4)])
    _seed_floor(env, "NOMETA", "B", [(5, 5)], register=False)   # cells, no metadata row
    cat = _wl(env)["selection"]["references"]
    assert cat["state"] == ma.REFERENCE_CATALOG_SERVED
    assert [i["map_id"] for i in cat["items"]] == ["GOOD_A"]
    assert cat["examined"] == 1, "an unregistered floor is not even a candidate"


def test_a_registered_floor_with_no_cells_is_counted_as_rejected_with_a_cause(env):
    """The other half-a-floor: a metadata row pointing at nothing. It must not be offered,
    and the count alone would leave the operator without a repair."""
    _seed_unit(env, "E1", "P1", ["J1"])
    _seed_floor(env, "GOOD", "A", [(3, 3), (4, 3)])
    _seed_floor(env, "EMPTY", "B", [], register=True)
    cat = _wl(env)["selection"]["references"]
    assert [i["map_id"] for i in cat["items"]] == ["GOOD_A"]
    assert (cat["examined"], cat["rejected"]) == (2, 1)
    assert cat["rejected_example"] and "EMPTY_B" in cat["rejected_example"]


def test_each_offer_says_which_kind_it_is(env):
    """A floor carrying values and one carrying only occupancy are different offers, and the
    difference decides what the screen can answer at all - occupancy is flat, and on a
    circular footprint it carries no orientation signal whatever. The operator must see it
    BEFORE spending a run finding out."""
    _seed_unit(env, "E1", "P1", ["J1"])
    _seed_floor(env, "GOOD", "A", [(3, 3), (4, 3)])
    item = _wl(env)["selection"]["references"]["items"][0]
    assert item["kind"] == ma.REFERENCE_KIND_VALUES
    assert item["cell_count"] == 2
    assert item["grid"] == {"cols": 13, "rows": 13}


def test_an_empty_offer_list_is_an_answer_and_not_an_error(env):
    """Half the map population cannot be a floor; that is ordinary. `served` with an empty
    list and a count of what was looked at says "we looked and nothing qualifies" - which a
    bare `[]` cannot distinguish from "we could not look"."""
    _seed_unit(env, "E1", "P1", ["J1"])
    cat = _wl(env)["selection"]["references"]
    assert cat["state"] == ma.REFERENCE_CATALOG_SERVED
    assert cat["items"] == []
    assert cat["examined"] == 0
    assert cat["reason"] is None


def test_an_unservable_catalog_is_a_different_state(env):
    saved = models.DYNAMIC_TABLES.pop(map_overlay.META_TABLE)
    try:
        cat = ma.resolve_reference_catalog(env, {})
    finally:
        models.DYNAMIC_TABLES[map_overlay.META_TABLE] = saved
    assert cat["state"] == ma.REFERENCE_CATALOG_UNAVAILABLE
    assert cat["items"] == []
    assert cat["reason"]


def test_the_offer_list_and_the_view_agree_on_what_resolves(env):
    """The list must not promise what the detail refuses. Both go through
    `_load_reference` - if the catalog re-implemented "does it resolve", the day the two
    spellings diverge is the day a chosen floor comes back not_scorable."""
    _seed_unit(env, "E1", "P1", ["J1"])
    _seed_floor(env, "GOOD", "A", [(3, 3), (4, 3), (3, 4)])
    offered = _wl(env)["selection"]["references"]["items"]
    for item in offered:
        spec = "%s:%s" % (item["table"], item["map_id"])
        ref = ma._resolve_reference(env, {}, spec, [], 1)
        assert ref["state"] == ma.REFERENCE_RESOLVED, spec


def test_the_offer_list_counts_cells_rather_than_fetching_them(env):
    """A picker showing size must not pull every floor's cells on every keystroke - the
    worklist is an index and its search re-runs on typing."""
    _seed_unit(env, "E1", "P1", ["J1"])
    _seed_floor(env, "BIG", "A", [(x, y) for x in range(3, 10) for y in range(3, 10)])
    item = _wl(env)["selection"]["references"]["items"][0]
    assert item["cell_count"] == 49
    # `_load_reference` is asked for existence only; a cap of 1 is what keeps it cheap.
    ref = ma._resolve_reference(env, {}, "%s:BIG_A" % map_overlay.VALID_DIE_TABLE, [], 1)
    assert len(ref["cells"]) == 1 and ref["count"] == 1


def test_the_worklist_field_and_the_rule_less_route_are_the_same_answer(env):
    """`selection.references` stays on the worklist so a client that already has a rule
    needs no second call - but it must be the SAME computation the rule-less route serves,
    not a second one. The day these are two implementations is the day a floor is offered
    on one screen and missing on the other. One function, two callers."""
    _seed_unit(env, "E1", "P1", ["J1"])
    _seed_floor(env, "GOOD", "A", [(3, 3), (4, 3)])
    auto = dict(_auto_meta())
    _seed_floor(env, "AUTO", "B", [(5, 5)])
    env.query(models.DYNAMIC_TABLES[map_overlay.META_TABLE]).filter_by(
        map_id="AUTO_B").update({"grid_metadata": json.dumps(auto)})
    env.commit()
    assert _wl(env)["selection"]["references"] == ma.resolve_reference_catalog(env, {})


def test_a_floor_refused_on_the_worklist_is_named_there_too(env):
    """The worklist's copy carries the same `not_offered` detail, so an operator who never
    opens the standalone route still learns which map was refused and why."""
    _seed_unit(env, "E1", "P1", ["J1"])
    _seed_floor(env, "EMPTY", "B", [])
    cat = _wl(env)["selection"]["references"]
    assert [n["map_id"] for n in cat["not_offered"]] == ["EMPTY_B"]
    assert cat["not_offered"][0]["reason_code"] == ma.REF_REFUSAL_NO_CELLS


def test_the_map_table_choices_come_from_the_declaration_not_from_a_list_in_code(env):
    _seed_unit(env, "E1", "P1", ["J1"])
    tables = {c["table"] for c in _wl(env)["selection"]["map_tables"]}
    declared = {t for t, c in crud.TABLE_CONFIG.items() if c.get("map_key_columns")}
    assert tables == declared


def test_the_coordinate_columns_are_the_real_ones_and_are_not_paired_for_the_operator(env):
    """Pairing `*_x` with `*_y` by name is a guess, and a guess shipped in the payload
    starts impersonating a declaration."""
    _seed_unit(env, "E1", "P1", ["J1"])
    coord = _wl(env)["selection"]["coordinates"]
    assert set(coord["numeric_columns"]) == {"dt_x", "dt_y", "core_x", "core_y"}
    assert "pairs" not in coord


def test_the_undeclared_target_to_column_mapping_is_reported_not_resolved(env):
    """Two target fields and four coordinate columns, and nothing declares which pair
    feeds which field. Picking one here would invent the declaration."""
    _seed_unit(env, "E1", "P1", ["J1"])
    codes = {a["code"] for a in _wl(env)["selection"]["ambiguity"]}
    assert "target_to_columns_undeclared" in codes
    single = dict(RULE, target_fields=["dt_frame"])
    assert not any(a["code"] == "target_to_columns_undeclared"
                   for a in ma.binding_ambiguity(
                       single, ma.coordinate_column_catalog({}, SRC)))


# ---------------------------------------------------------------------------
# the route
# ---------------------------------------------------------------------------

def _rules_patch(monkeypatch):
    import enrichment_config
    monkeypatch.setattr(enrichment_config, "load_enrichment_rules",
                        lambda *a, **k: [dict(RULE)])


def test_route_404s_on_an_unknown_rule(client, env, monkeypatch):
    _rules_patch(monkeypatch)
    r = client.get("/api/maps/alignment/worklist",
                   params={"rule": "nope", "map_table": MAPT})
    assert r.status_code == 404


def test_route_400s_on_a_params_key_the_rule_does_not_declare(client, env, monkeypatch):
    """Same discipline as the view route and `/enrichment/rules/{r}/references/{i}`:
    an undeclared column is a refusal, never a filter that silently does nothing."""
    _rules_patch(monkeypatch)
    r = client.get("/api/maps/alignment/worklist",
                   params={"rule": RULE["name"], "map_table": MAPT,
                           "params": json.dumps({"not_a_key": "x"})})
    assert r.status_code == 400
    assert "decision_key" in r.json()["detail"]


def test_route_accepts_a_declared_params_key_as_a_filter(client, env, monkeypatch):
    _rules_patch(monkeypatch)
    _seed_unit(env, "E1", "P1", ["J1"])
    _seed_unit(env, "E2", "P2", ["J2"])
    r = client.get("/api/maps/alignment/worklist",
                   params={"rule": RULE["name"], "map_table": MAPT,
                           "params": json.dumps({"product": "P2"})})
    assert r.status_code == 200
    assert [u["key"]["eqp"] for u in r.json()["units"]] == ["E2"]


def test_route_400s_on_a_sort_key_it_does_not_offer(client, env, monkeypatch):
    _rules_patch(monkeypatch)
    r = client.get("/api/maps/alignment/worklist",
                   params={"rule": RULE["name"], "map_table": MAPT, "sort": "whatever"})
    assert r.status_code == 400


def test_route_400s_on_an_undeclared_map_table(client, env, monkeypatch):
    _rules_patch(monkeypatch)
    r = client.get("/api/maps/alignment/worklist",
                   params={"rule": RULE["name"], "map_table": DERIVED})
    assert r.status_code == 400
