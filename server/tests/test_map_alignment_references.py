"""The reference (floor) catalog, asked WITHOUT an enrichment rule.

WHY THIS FILE EXISTS SEPARATELY FROM THE WORKLIST TESTS
The list of floors that actually resolve used to ride on the worklist response only, so
reaching it required `?rule=`. That was a FALSE dependency: which floors resolve is a
property of the map table, not of the enrichment rule being worked. A deployment that had
not declared an alignment rule yet got nothing from the worklist and lost the floor list
with it - including a floor that had both halves. So the load-bearing property of this
file is that NOT ONE test here mentions a rule, a decision key, or a derived table.

WHY THE `not_offered` TESTS ARE THE OTHER HALF
"Not offered" with no reason is what sends an operator to a person instead of to a repair.
Every candidate that was examined and refused comes back NAMED, with a `reason_code`, a
sentence, and its `COUNT(*)` - because "it has cells and is still not offered" is the
single most useful fact and a bare count cannot carry it.
"""
import json

import pytest

import map_alignment as ma
import map_overlay
from database import crud, models

PHYS = {"phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}

# Both tables below are PRODUCT-OWNED and PINNED - the floor store by
# `map_overlay.VALID_DIE_TABLE` (ruling 1-a) and the spec store by
# `map_overlay.META_TABLE`. A fixture cannot rename them out of the way, so their
# declarations are copied VERBATIM from `table_config.json`: `Base.metadata` outlives one
# test, and a fixture that invents a different shape breaks the first run and passes every
# run after it, which reads as flakiness rather than as the fixture's fault.
TABLES = {
    map_overlay.VALID_DIE_TABLE: {
        "business_key": "cell_key",
        "composite_key_source": ["product", "type", "x", "y"],
        "composite_key_separator": "_",
        "column_types": {"cell_key": "string", "product": "string", "type": "string",
                         "x": "number", "y": "number", "val": "string"},
        "map_key_columns": ["product", "type"]},
    # A map table keyed on ONE column, so the separator inside its key is ordinary rather
    # than ambiguous. Prefixed so it cannot collide with a table in the operator's
    # gitignored config - a collision there wins the shared in-memory schema and surfaces
    # months later as `no such column`.
    "refcat_test_singlekey": {
        "business_key": "cell_key",
        "column_types": {"cell_key": "string", "job": "string",
                         "x": "number", "y": "number", "val": "string"},
        "map_key_columns": ["job"]},
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


def _seed_floor(db, product, type_, cells, meta="__default__", map_id=None, coords=None):
    """A floor needs BOTH halves: cells under a key that splits, and a metadata row.

    `map_id` overrides the registered spelling so a test can seed the exact mismatch it is
    about. `coords` overrides what goes into x/y so a test can seed unreadable ones.
    """
    v = models.DYNAMIC_TABLES[map_overlay.VALID_DIE_TABLE]
    meta_model = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    for i, (x, y) in enumerate(cells):
        cx, cy = (coords[i] if coords else (x, y))
        db.add(v(row_id="v_%s_%s_%d_%d" % (product, type_, x, y),
                 business_key_val="%s_%s_%d_%d" % (product, type_, x, y),
                 cell_key="%s_%s_%d_%d" % (product, type_, x, y),
                 product=product, type=type_, x=cx, y=cy, val="1"))
    if meta is not None:
        mid = map_id or ma.compose_map_id([product, type_])
        blob = json.dumps(_meta()) if meta == "__default__" else meta
        db.add(meta_model(row_id="mv_" + mid,
                          business_key_val="%s|%s" % (map_overlay.VALID_DIE_TABLE, mid),
                          target_table=map_overlay.VALID_DIE_TABLE, map_id=mid,
                          grid_metadata=blob))
    db.commit()


def _not_offered(cat, map_id):
    return next(n for n in cat["not_offered"] if n["map_id"] == map_id)


# ---------------------------------------------------------------------------
# the question is answerable without a rule - the whole point of the decoupling
# ---------------------------------------------------------------------------

def test_the_floor_list_answers_with_no_rule_declared(env, client):
    """No `?rule=`, no decision key, no derived table. A deployment that has not declared
    an alignment rule yet must still be able to ask which floors resolve - the previous
    shape took this answer down with the worklist, and that is the bug being fixed."""
    _seed_floor(env, "GOOD", "A", [(3, 3), (4, 3), (3, 4)])
    r = client.get("/api/maps/alignment/references")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == ma.REFERENCE_CATALOG_SERVED
    assert [i["map_id"] for i in body["items"]] == ["GOOD_A"]


def test_the_route_returns_the_catalog_unwrapped(env, client):
    """One subject, so no envelope: a `{references: {...}}` layer would carry no
    information. The worklist keeps its `selection.` nesting because there it is one
    selection fact among several."""
    _seed_floor(env, "GOOD", "A", [(3, 3)])
    body = client.get("/api/maps/alignment/references").json()
    direct = ma.resolve_reference_catalog(env, {})
    assert set(body) == set(direct)
    assert body["items"] == direct["items"]


def test_one_resolution_path_serves_both_callers(env, client):
    """The route and the worklist field must not be two implementations of "does it
    resolve". They are the same function, so they cannot disagree - and the detail view
    goes through the same `_load_reference`, so the list cannot promise what the detail
    refuses."""
    _seed_floor(env, "GOOD", "A", [(3, 3), (4, 3)])
    body = client.get("/api/maps/alignment/references").json()
    for item in body["items"]:
        ref = ma._resolve_reference(env, {}, "%s:%s" % (item["table"], item["map_id"]),
                                    [], 1)
        assert ref["state"] == ma.REFERENCE_RESOLVED


# ---------------------------------------------------------------------------
# "not offered" always says WHICH - the report that started this round
# ---------------------------------------------------------------------------

def test_a_floor_with_both_halves_that_is_refused_is_named_with_its_cause(env, client):
    """The product owner's report: cells AND a metadata row, still not offered. Whatever
    disqualifies it, the answer must say so - a count and one anonymous example sentence
    is what sent them to a person instead of to the repair."""
    _seed_floor(env, "GOOD", "A", [(3, 3)])
    auto = _meta(phys_chip_x=1, phys_chip_y=1, auto_registered=True)
    _seed_floor(env, "AUTO", "B", [(5, 5), (6, 5)], meta=json.dumps(auto))
    cat = client.get("/api/maps/alignment/references").json()

    assert [i["map_id"] for i in cat["items"]] == ["GOOD_A"], "still only what resolves"
    bad = _not_offered(cat, "AUTO_B")
    assert bad["reason_code"] == ma.REF_REFUSAL_GEOMETRY
    assert bad["cell_count"] == 2, "it HAS cells - that fact is the whole clue"
    assert bad["reason"]


def test_a_metadata_row_with_a_blank_spec_is_not_reported_as_unregistered(env, client):
    """`load_map_meta` answers None for BOTH "no row" and "row with an empty blob", and the
    two are opposite repairs (register it vs measure it). Telling an operator their
    registered map is not registered is a false sentence, and they will go looking for the
    row they can already see."""
    _seed_floor(env, "BLANK", "B", [(5, 5)], meta="")
    cat = client.get("/api/maps/alignment/references").json()
    bad = _not_offered(cat, "BLANK_B")
    assert bad["reason_code"] == ma.REF_REFUSAL_META_UNREADABLE
    assert "등록되지 않았습니다" not in bad["reason"]


def test_a_spec_row_pointing_at_no_cells_is_told_apart_from_a_missing_row(env, client):
    _seed_floor(env, "EMPTY", "B", [])
    bad = _not_offered(client.get("/api/maps/alignment/references").json(), "EMPTY_B")
    assert bad["reason_code"] == ma.REF_REFUSAL_NO_CELLS
    assert bad["cell_count"] == 0


def test_rows_present_but_coordinates_unreadable_is_its_own_cause(env, client):
    """Cells counted, zero of them usable - here because x/y came in null. `COUNT(*)`
    cannot see this and neither can the operator: the map looks populated everywhere
    else, and only the reference path drops the rows."""
    _seed_floor(env, "JUNK", "B", [(1, 1), (2, 2)], coords=[(None, None), (None, None)])
    bad = _not_offered(client.get("/api/maps/alignment/references").json(), "JUNK_B")
    assert bad["reason_code"] == ma.REF_REFUSAL_COORDS_UNREADABLE
    assert bad["cell_count"] == 2


# ---------------------------------------------------------------------------
# the key round trip - the quietest way a both-halves floor disappears
# ---------------------------------------------------------------------------

def test_composing_a_map_id_is_not_reversible_when_the_first_key_holds_the_separator():
    """The oracle, with no database in it. `compose_map_id` joins on '_' and
    `map_key_parts` lets the LAST column absorb the remainder, so the two are not inverses:
    a product name containing '_' comes back split at the wrong underscore. Every seeded
    reproduction below rests on this, so it is asserted here on its own."""
    binding = {"key_columns": ["product", "type"]}
    composed = ma.compose_map_id(["A_B", "C"])
    assert composed == "A_B_C"
    assert map_overlay.map_key_parts(binding, composed) == [("product", "A"),
                                                            ("type", "B_C")]


def test_a_floor_whose_key_recomposes_wrongly_says_what_it_actually_queried(env, client):
    """Both halves present, cells sitting right there, and the floor never appears. The
    cell query went to `product='A'`/`type='B_C'` and met nothing. The answer has to name
    the columns it bound, because nothing else on the screen can reveal this."""
    _seed_floor(env, "A_B", "C", [(3, 3), (4, 4)])
    cat = client.get("/api/maps/alignment/references").json()
    assert cat["items"] == []
    bad = _not_offered(cat, "A_B_C")
    assert bad["reason_code"] == ma.REF_REFUSAL_KEY_AMBIGUOUS
    assert "product='A'" in bad["reason"] and "type='B_C'" in bad["reason"]


def test_a_single_token_key_cannot_split_into_two_columns(env, client):
    """The other end of the same axis: fewer tokens than key columns. It gets its own name
    because the repair differs - a one-token spec row can never address a two-column key
    no matter how many cells are added, whereas plain `no_cells` is fixed by adding them."""
    _seed_floor(env, "OTHER", "X", [(3, 3)], meta=None)
    _seed_floor(env, "SOLO", "", [], map_id="SOLO")
    bad = _not_offered(client.get("/api/maps/alignment/references").json(), "SOLO")
    assert bad["reason_code"] == ma.REF_REFUSAL_KEY_UNSPLIT


def test_one_key_column_absorbs_the_separator_and_is_never_called_ambiguous(env):
    """The guard on my own diagnosis. With a single key column the absorb-the-remainder
    rule IS the round trip, so `dt_job='MID_01'` is an ordinary key. Counting separators
    without checking how many columns want them would accuse a healthy key and send the
    operator to rename a map that was fine."""
    meta_model = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    env.add(meta_model(row_id="mv_single", business_key_val="refcat_test_singlekey|MID_01",
                       target_table="refcat_test_singlekey", map_id="MID_01",
                       grid_metadata=json.dumps(_meta())))
    env.commit()
    ref = ma._load_reference(env, {}, "refcat_test_singlekey", "MID_01", "explicit", 1)
    assert ref["reason_code"] == ma.REF_REFUSAL_NO_CELLS
    assert "job='MID_01'" in ref["reason"], "the whole key went to the one column"


# ---------------------------------------------------------------------------
# everything that was already right stays right
# ---------------------------------------------------------------------------

def test_an_empty_offer_list_is_an_answer_and_not_an_error(env, client):
    """Half the map population cannot be a floor; that is ordinary. `served` with an empty
    list says "we looked and nothing qualifies", which a bare `[]` cannot distinguish from
    "we could not look"."""
    cat = client.get("/api/maps/alignment/references").json()
    assert cat["state"] == ma.REFERENCE_CATALOG_SERVED
    assert (cat["items"], cat["examined"], cat["reason"]) == ([], 0, None)


def test_an_unservable_catalog_is_a_different_state(env):
    saved = models.DYNAMIC_TABLES.pop(map_overlay.META_TABLE)
    try:
        cat = ma.resolve_reference_catalog(env, {})
    finally:
        models.DYNAMIC_TABLES[map_overlay.META_TABLE] = saved
    assert cat["state"] == ma.REFERENCE_CATALOG_UNAVAILABLE
    assert cat["items"] == [] and cat["reason"]


def test_every_offer_says_which_kind_it_is_in_the_view_s_own_words(env, client):
    """Same vocabulary as `/view`'s `reference.kind` - two spellings of one fact is the
    defect this round is closing. The reachable subset differs: `/view` can answer `none`
    because a unit may have no reference at all, whereas every item here resolved by
    construction, so `none` can never appear."""
    _seed_floor(env, "GOOD", "A", [(3, 3), (4, 3)])
    item = client.get("/api/maps/alignment/references").json()["items"][0]
    assert item["kind"] in (ma.REFERENCE_KIND_VALUES, ma.REFERENCE_KIND_OCCUPANCY)
    assert item["kind"] != ma.REFERENCE_KIND_NONE
    assert item["grid"] == {"cols": 13, "rows": 13}


def test_sizes_are_counted_and_not_fetched(env, client):
    """A picker showing size must not pull every floor's cells. `_load_reference` is asked
    for existence only (cap 1) and the size comes from `COUNT(*)`."""
    _seed_floor(env, "BIG", "A", [(x, y) for x in range(3, 10) for y in range(3, 10)])
    item = client.get("/api/maps/alignment/references").json()["items"][0]
    assert item["cell_count"] == 49
    ref = ma._resolve_reference(env, {}, "%s:BIG_A" % map_overlay.VALID_DIE_TABLE, [], 1)
    assert len(ref["cells"]) == 1 and ref["count"] == 1


def test_a_declared_pointer_with_no_spec_row_is_not_a_candidate_at_all(env, client):
    """The eight declared `valid_die_ref` pointers that resolve zero times are still not
    offered, and they are not even examined: candidacy starts at the spec row."""
    _seed_floor(env, "NOMETA", "B", [(5, 5)], meta=None)
    cat = client.get("/api/maps/alignment/references").json()
    assert cat["items"] == [] and cat["examined"] == 0 and cat["not_offered"] == []


def test_the_catalog_writes_nothing(env, client):
    _seed_floor(env, "GOOD", "A", [(3, 3)])
    before = {t: env.query(models.DYNAMIC_TABLES[t]).count()
              for t in (map_overlay.VALID_DIE_TABLE, map_overlay.META_TABLE)}
    client.get("/api/maps/alignment/references")
    after = {t: env.query(models.DYNAMIC_TABLES[t]).count()
             for t in (map_overlay.VALID_DIE_TABLE, map_overlay.META_TABLE)}
    assert before == after


# ---------------------------------------------------------------------------
# `?table=` filters REPORTING, and does not narrow the candidate set
# ---------------------------------------------------------------------------

def test_the_table_filter_narrows_which_tables_are_reported(env, client):
    _seed_floor(env, "GOOD", "A", [(3, 3)])
    body = client.get("/api/maps/alignment/references",
                      params={"table": map_overlay.VALID_DIE_TABLE}).json()
    assert body["filter"] == map_overlay.VALID_DIE_TABLE
    assert [i["map_id"] for i in body["items"]] == ["GOOD_A"]


def test_filtering_to_a_table_that_holds_no_floors_says_so(env, client):
    """Reads of a floor are PINNED to `valid_die_ref` whatever a declaration names, so
    asking about another map table is answerable - "we looked, floors are not stored
    there" - and that is a served answer, not a failure."""
    _seed_floor(env, "GOOD", "A", [(3, 3)])
    body = client.get("/api/maps/alignment/references",
                      params={"table": map_overlay.META_TABLE}).json()
    assert body["state"] == ma.REFERENCE_CATALOG_SERVED
    assert body["items"] == [] and body["reason"]


def test_an_unknown_table_is_refused_rather_than_answered_as_empty(env, client):
    r = client.get("/api/maps/alignment/references", params={"table": "no_such_table"})
    assert r.status_code == 404


def test_the_cap_is_declared_when_it_bites(env, client):
    for i in range(4):
        _seed_floor(env, "P%d" % i, "T", [(3, 3)])
    body = client.get("/api/maps/alignment/references", params={"cap": 2}).json()
    assert body["examined"] == 2 and body["truncated"] is True
