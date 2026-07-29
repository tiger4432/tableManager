"""[F5] Load-time preset routing — which physical spec a map opens with.

The declaration chain is ORDERED and the order is the contract:

    map key -> lot token -> (1) product-code lookup table -> code -> preset
                            (2) ordered text-pattern rules, first match wins
                            (3) no routing at all

The invariants under test, and what each one is protecting:

  INV-R-1  works with NO lookup declared (patterns only). That is the normal
           state of this environment — the lookup table exists only in
           production — so a code path that needs it would be unverifiable here.
  INV-R-2  a lookup MISS is normal, not an exception: it falls silently through
           to (2) and never logs at warning level. The table is incomplete by
           design.
  INV-R-3  (1) and (2) both empty -> routing is refused EXPLICITLY. Never a
           plausible preset. A wrong preset changes `inside`, and `inside` is
           the set of cells that can be stored.
  INV-R-4  every key rides the 7b canonicalisation (`canonical_key_value`).
           Proved with mutation twins on all THREE places it decides an answer,
           because a second normalisation here would re-open the defect fixed
           in 7b (`LOT_01` failing to find `LOT_1`).
  INV-R-5  one resolution per MAP LOAD — at most one lookup query, and zero
           queries when nothing is declared.
  INV-R-6  rules are an ORDERED list, first match wins, and the response says
           which rule decided and why.

Plus the absolute priority rule that sits above all of them: stored
`wafer_map_metadata` > routing > panel. Routing must never overwrite a
registered spec.

[Isolation] Every table name carries the `pr_test_` prefix so it can never
collide with a real table in the user's gitignored config (server-pm memory:
the `bonding_log` trap).
"""
import json
import logging
import uuid
from contextlib import contextmanager

import pytest

import map_overlay
import map_preset_routing as routing_mod
from database import crud, models

MAP_TABLE = "pr_test_map"
NUM_MAP_TABLE = "pr_test_nummap"
LOOKUP_TABLE = "pr_test_product_master"
NUMCODE_TABLE = "pr_test_numcode_master"
ABSENT_TABLE = "pr_test_never_registered"

# `slot` is number-declared on purpose: the map identity then reads `LOT_1`
# while a parsed token spells it `LOT_01`, which is the exact 7b defect axis.
_MAP_COLS = {"cell_key": "string", "lot": "string", "slot": "number",
             "x": "number", "y": "number", "val": "string"}

PR_TABLES = {
    MAP_TABLE: {"business_key": "cell_key", "map_key_columns": ["lot", "slot"],
                "column_types": dict(_MAP_COLS)},
    # A map whose LOT column is number-declared. Pattern matching is a pure
    # Python string comparison, so canonicalisation of the lot token decides
    # the answer with no database affinity to paper over a break.
    NUM_MAP_TABLE: {"business_key": "cell_key", "map_key_columns": ["lot", "slot"],
                    "column_types": dict(_MAP_COLS, lot="number")},
    LOOKUP_TABLE: {"business_key": "lot",
                   "column_types": {"lot": "string", "product_code": "string"}},
    # A lookup whose product code column is number-declared: the stored 1234.0
    # must be read back as '1234' to meet a declared `product_presets` key.
    NUMCODE_TABLE: {"business_key": "lot",
                    "column_types": {"lot": "string", "product_code": "number"}},
    "wafer_map_metadata": {
        "business_key": "map_pk",
        "column_types": {"map_pk": "string", "target_table": "string",
                         "map_id": "string", "grid_metadata": "string"},
    },
}

PRESETS = {
    "core_std": {"name": "CORE", "phys_chip_x": 7.0, "phys_chip_y": 7.0},
    "tape_std": {"name": "TAPE", "phys_chip_x": 15.0, "phys_chip_y": 15.0},
    "custom_1784890104442": {"name": "4A", "phys_chip_x": 11.0, "phys_chip_y": 13.0},
}

GRID = {"grid_cols": 6, "grid_rows": 6, "grid_start_x": 1, "grid_start_y": 1,
        "grid_y_invert": False, "side": "front", "rotation": 0,
        "phys_wafer_dia": 300.0, "phys_chip_x": 60.0, "phys_chip_y": 60.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}

MAP_KEY = "AF01_1"          # the canonical identity (slot is number-declared)
MAP_KEY_PADDED = "AF01_01"  # what a parsed material token hands over
LOT = "AF01"


@pytest.fixture()
def pr_env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(PR_TABLES)
    crud.TABLE_CONFIG.update(PR_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    monkeypatch.setattr(map_overlay, "CONFIG_PATH", str(tmp_path / "none.json"))
    routing_mod._SCAN_NOTED.clear()
    return db_session


def _product(db, lot, code, table=LOOKUP_TABLE):
    model = models.DYNAMIC_TABLES[table]
    db.add(model(row_id=str(uuid.uuid4()), business_key_val=str(lot),
                 lot=lot, product_code=code))


def _meta(db, target_table, map_id):
    model = models.DYNAMIC_TABLES["wafer_map_metadata"]
    db.add(model(row_id=str(uuid.uuid4()),
                 business_key_val=f"{target_table}_{map_id}",
                 map_pk=f"{target_table}_{map_id}", target_table=target_table,
                 map_id=map_id, grid_metadata=json.dumps(GRID)))


def _cfg(table=MAP_TABLE, **decl):
    return {"preset_routing": {table: decl}}


def _resolve(db, cfg, table=MAP_TABLE, map_key=MAP_KEY, presets=None):
    return routing_mod.resolve_preset_routing(
        db, cfg, table, map_key, PRESETS if presets is None else presets)


_PREFIX_RULE = {"name": "AF family", "match": "prefix", "value": "AF",
                "preset": "core_std"}


@contextmanager
def _selects(db, needle=None):
    """Collect SELECT statements issued inside the block (optionally filtered)."""
    from sqlalchemy import event
    engine = db.get_bind()
    seen = []

    def _cb(conn, cursor, statement, params, context, executemany):
        if not statement.lstrip().upper().startswith("SELECT"):
            return
        if needle is None or needle.lower() in statement.lower():
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", _cb)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", _cb)


def _break_canonicalisation(monkeypatch):
    """Degrade 7b canonicalisation to a raw str(). Every INV-R-4 twin below
    asserts the ANSWER moves when this is applied — an implementation carrying
    its own second normalisation would survive it, which is the thing forbidden."""
    monkeypatch.setattr(map_overlay, "canonical_key_value",
                        lambda v, t: None if v is None else str(v))


# ---------------------------------------------------------------------------
# The fixture itself must have live defect axes
# ---------------------------------------------------------------------------

def test_fixture_axes_are_live(pr_env):
    """Guard on the guards. If these three canonicalisations were no-ops on this
    fixture, every INV-R-4 twin below would be vacuous."""
    assert map_overlay.canonical_bind_value(MAP_TABLE, "slot", "01") == "1"
    assert map_overlay.canonical_bind_value(NUM_MAP_TABLE, "lot", "007") == "7"
    assert map_overlay.canonical_bind_value(NUMCODE_TABLE, "product_code", 1234.0) == "1234"


# ---------------------------------------------------------------------------
# INV-R-1 — no lookup declared is the NORMAL configuration
# ---------------------------------------------------------------------------

def test_patterns_answer_with_no_lookup_declared(pr_env):
    """The state of this environment: no product lookup exists anywhere."""
    out = _resolve(pr_env, _cfg(rules=[_PREFIX_RULE]))
    assert out["status"] == routing_mod.STATUS_OK
    assert out["preset_key"] == "core_std"
    assert out["preset"]["name"] == "CORE"
    assert out["lookup"] == {"declared": False, "status": "not_declared",
                            "product_code": None}


def test_declared_lookup_whose_table_does_not_exist_still_routes(pr_env):
    """Same code, different declaration. A declaration carried over from
    production must degrade to (2), not to an error — otherwise the production
    config could never be exercised outside production."""
    out = _resolve(pr_env, _cfg(
        product_lookup={"table": ABSENT_TABLE, "key_column": "lot",
                        "value_column": "product_code"},
        product_presets={"AB12": "tape_std"},
        rules=[_PREFIX_RULE]))
    assert out["status"] == routing_mod.STATUS_OK
    assert out["preset_key"] == "core_std", "fell back to patterns, as declared"
    assert out["lookup"]["status"] == routing_mod.LOOKUP_TABLE_ABSENT


def test_no_declaration_at_all_is_not_an_error(pr_env):
    out = _resolve(pr_env, {})
    assert out["status"] == routing_mod.STATUS_NOT_DECLARED
    assert out["preset_key"] is None


# ---------------------------------------------------------------------------
# INV-R-2 — a lookup MISS is normal: silent, and it falls through
# ---------------------------------------------------------------------------

def test_lookup_miss_falls_through_to_patterns_without_warning(pr_env, caplog):
    db = pr_env
    _product(db, "SOMEONE_ELSE", "AB12")   # the table exists but not this lot
    db.commit()

    cfg = _cfg(product_lookup={"table": LOOKUP_TABLE, "key_column": "lot",
                               "value_column": "product_code"},
               product_presets={"AB12": "tape_std"},
               rules=[_PREFIX_RULE])

    with caplog.at_level(logging.DEBUG):
        out = _resolve(db, cfg)

    # The miss path actually ran (without this the "no warnings" claim is vacuous)
    assert out["lookup"]["status"] == routing_mod.LOOKUP_MISS
    assert out["status"] == routing_mod.STATUS_OK
    assert out["preset_key"] == "core_std"

    loud = [r for r in caplog.records
            if r.levelno >= logging.WARNING and r.name == routing_mod.__name__]
    assert loud == [], f"a normal miss logged at warning level: {[r.message for r in loud]}"


def test_lookup_hit_for_an_unmapped_product_code_also_falls_through(pr_env):
    """The lookup answered but nobody has declared a preset for that code yet.
    Still normal while the mapping is being filled in."""
    db = pr_env
    _product(db, LOT, "ZZ99")
    db.commit()
    out = _resolve(db, _cfg(
        product_lookup={"table": LOOKUP_TABLE, "key_column": "lot",
                        "value_column": "product_code"},
        product_presets={"AB12": "tape_std"},
        rules=[_PREFIX_RULE]))
    assert out["lookup"]["status"] == routing_mod.LOOKUP_UNMAPPED
    assert out["lookup"]["product_code"] == "ZZ99"
    assert out["preset_key"] == "core_std"


# ---------------------------------------------------------------------------
# INV-R-3 — nothing matched means NO ROUTING, never a plausible preset
# ---------------------------------------------------------------------------

def test_declared_but_unmatched_refuses_instead_of_picking_a_preset(pr_env):
    """Rules exist and presets exist; the lot matches none of them. An
    implementation that fell back to "the first rule" or "the first preset"
    fails here — and that failure mode is what changes `inside` silently."""
    out = _resolve(pr_env, _cfg(rules=[
        {"name": "tape", "match": "prefix", "value": "T", "preset": "tape_std"},
        {"name": "base", "match": "prefix", "value": "B", "preset": "core_std"},
    ]))
    assert out["status"] == routing_mod.STATUS_NO_MATCH
    assert out["preset_key"] is None
    assert out["preset"] is None
    assert LOT in out["detail"]


def test_dangling_preset_reference_refuses_and_names_the_ghost(pr_env):
    """A typo must not fall through to the next rule: that would answer with a
    preset nobody selected and hide the typo forever.

    The second rule MATCHES and names a REAL preset on purpose — falling
    through would produce a confident wrong answer, which is the outcome this
    guards, not a mere `no_match`."""
    out = _resolve(pr_env, _cfg(rules=[
        {"name": "typo", "match": "prefix", "value": "AF", "preset": "no_such_preset"},
        {"name": "catch all", "match": "contains", "value": "F", "preset": "tape_std"},
    ]))
    assert out["status"] == routing_mod.STATUS_PRESET_MISSING
    assert out["preset_key"] is None
    assert out["matched_by"]["rule"] == "typo", "the offending rule must be named"
    assert "no_such_preset" in out["detail"]


@pytest.mark.parametrize("cfg,table,map_key", [
    ({}, MAP_TABLE, MAP_KEY),                                   # not_declared
    (_cfg(rules=[{"name": "n", "match": "prefix", "value": "ZZ",
                  "preset": "core_std"}]), MAP_TABLE, MAP_KEY),  # no_match
])
def test_every_non_ok_status_carries_no_preset(pr_env, cfg, table, map_key):
    out = _resolve(pr_env, cfg, table=table, map_key=map_key)
    assert out["status"] != routing_mod.STATUS_OK
    assert out["preset_key"] is None and out["preset"] is None


def test_a_table_that_is_not_a_map_is_refused_not_guessed(pr_env):
    out = _resolve(pr_env, _cfg(table=LOOKUP_TABLE, rules=[_PREFIX_RULE]),
                   table=LOOKUP_TABLE)
    assert out["status"] == routing_mod.STATUS_UNRESOLVABLE
    assert out["preset_key"] is None


# ---------------------------------------------------------------------------
# Absolute priority — stored metadata > routing > panel
# ---------------------------------------------------------------------------

def test_a_registered_spec_suppresses_routing(pr_env):
    db = pr_env
    cfg = _cfg(rules=[_PREFIX_RULE])
    # Oracle: without a meta row the very same call routes.
    assert _resolve(db, cfg)["status"] == routing_mod.STATUS_OK

    _meta(db, MAP_TABLE, MAP_KEY)
    db.commit()

    out = _resolve(db, cfg)
    assert out["status"] == routing_mod.STATUS_META_PRESENT
    assert out["preset_key"] is None, "routing overwrote a registered spec"


def test_padded_key_still_finds_the_registered_spec(pr_env):
    """INV-R-4 (a): the meta row is keyed by the STORED identity `AF01_1`. A
    parsed token spelling it `AF01_01` must still be recognised as registered —
    otherwise routing would re-spec a map that already has a spec."""
    db = pr_env
    _meta(db, MAP_TABLE, MAP_KEY)
    db.commit()
    out = _resolve(db, _cfg(rules=[_PREFIX_RULE]), map_key=MAP_KEY_PADDED)
    assert out["canonical_map_key"] == MAP_KEY
    assert out["status"] == routing_mod.STATUS_META_PRESENT


def test_mutation_padded_key_stops_seeing_the_registered_spec(pr_env, monkeypatch):
    """MUTATION TWIN of the test above."""
    db = pr_env
    _meta(db, MAP_TABLE, MAP_KEY)
    db.commit()
    _break_canonicalisation(monkeypatch)
    out = _resolve(db, _cfg(rules=[_PREFIX_RULE]), map_key=MAP_KEY_PADDED)
    assert out["status"] != routing_mod.STATUS_META_PRESENT, \
        "the meta lookup survived a broken canonicalizer — it is normalising on its own"


# ---------------------------------------------------------------------------
# INV-R-4 — one canonicalisation, proved where it decides the answer
# ---------------------------------------------------------------------------

def test_lot_token_is_canonicalised_before_pattern_matching(pr_env):
    """(b) `lot` is number-declared here, so the stored identity of `007` is
    `7`. Matching is a pure Python string comparison — no database affinity can
    rescue a break."""
    out = _resolve(pr_env, _cfg(table=NUM_MAP_TABLE, rules=[
        {"name": "wafer seven", "match": "equals", "value": "7", "preset": "tape_std"}]),
        table=NUM_MAP_TABLE, map_key="007_1")
    assert out["status"] == routing_mod.STATUS_OK
    assert out["matched_by"]["lot"] == "7"
    assert out["preset_key"] == "tape_std"


def test_mutation_raw_lot_token_stops_matching(pr_env, monkeypatch):
    """MUTATION TWIN of the test above."""
    _break_canonicalisation(monkeypatch)
    out = _resolve(pr_env, _cfg(table=NUM_MAP_TABLE, rules=[
        {"name": "wafer seven", "match": "equals", "value": "7", "preset": "tape_std"}]),
        table=NUM_MAP_TABLE, map_key="007_1")
    assert out["status"] != routing_mod.STATUS_OK, \
        "the lot token survived a broken canonicalizer"


def test_product_code_is_canonicalised_before_the_preset_mapping(pr_env):
    """(c) the code column is number-declared, so a stored 1234 round-trips as
    1234.0 through a Float column. The declared mapping key is `1234`."""
    db = pr_env
    _product(db, LOT, 1234.0, table=NUMCODE_TABLE)
    db.commit()
    out = _resolve(db, _cfg(
        product_lookup={"table": NUMCODE_TABLE, "key_column": "lot",
                        "value_column": "product_code"},
        product_presets={"1234": "tape_std"}))
    assert out["lookup"]["product_code"] == "1234"
    assert out["status"] == routing_mod.STATUS_OK
    assert out["preset_key"] == "tape_std"


def test_mutation_raw_product_code_stops_mapping(pr_env, monkeypatch):
    """MUTATION TWIN of the test above."""
    db = pr_env
    _product(db, LOT, 1234.0, table=NUMCODE_TABLE)
    db.commit()
    _break_canonicalisation(monkeypatch)
    out = _resolve(db, _cfg(
        product_lookup={"table": NUMCODE_TABLE, "key_column": "lot",
                        "value_column": "product_code"},
        product_presets={"1234": "tape_std"}))
    assert out["status"] != routing_mod.STATUS_OK, \
        "the product code survived a broken canonicalizer"


# ---------------------------------------------------------------------------
# INV-R-5 — one resolution per map load
# ---------------------------------------------------------------------------

def test_resolution_costs_at_most_one_lookup_query(pr_env):
    db = pr_env
    _product(db, LOT, "AB12")
    db.commit()
    cfg = _cfg(product_lookup={"table": LOOKUP_TABLE, "key_column": "lot",
                               "value_column": "product_code"},
               product_presets={"AB12": "tape_std"})
    with _selects(db, needle=LOOKUP_TABLE) as seen:
        out = _resolve(db, cfg)
    assert out["preset_key"] == "tape_std"
    assert len(seen) == 1, f"expected exactly one lookup query, got {len(seen)}"


def test_an_undeclared_table_costs_zero_queries(pr_env):
    """The normal state of this environment must not pay for a feature it has
    not declared — including the metadata probe."""
    db = pr_env
    with _selects(db) as seen:
        out = _resolve(db, {})
    assert out["status"] == routing_mod.STATUS_NOT_DECLARED
    assert seen == [], f"an undeclared table issued queries: {seen}"


def test_patterns_only_never_touches_the_lookup_table(pr_env):
    db = pr_env
    _product(db, LOT, "AB12")
    db.commit()
    with _selects(db, needle=LOOKUP_TABLE) as seen:
        _resolve(db, _cfg(rules=[_PREFIX_RULE]))
    assert seen == []


# ---------------------------------------------------------------------------
# INV-R-6 — ordered list, first match wins, and the response says which
# ---------------------------------------------------------------------------

_BOTH_MATCH = [
    {"name": "narrow", "match": "prefix", "value": "AF", "preset": "core_std"},
    {"name": "broad", "match": "contains", "value": "F", "preset": "tape_std"},
]


def test_first_matching_rule_wins_and_is_named(pr_env):
    out = _resolve(pr_env, _cfg(rules=_BOTH_MATCH))
    assert out["preset_key"] == "core_std"
    assert out["matched_by"] == {"stage": routing_mod.STAGE_PATTERN,
                                 "rule": "narrow", "lot": LOT, "product_code": None}


def test_reversing_the_declaration_reverses_the_answer(pr_env):
    """The defect injection for the test above: if evaluation did not consult
    declaration ORDER (a dict, a sort, a "most specific wins" heuristic), this
    flip would not happen and both tests would still pass individually."""
    out = _resolve(pr_env, _cfg(rules=list(reversed(_BOTH_MATCH))))
    assert out["preset_key"] == "tape_std"
    assert out["matched_by"]["rule"] == "broad"


def test_the_lookup_stage_wins_over_a_matching_pattern(pr_env):
    """Stage order is the contract: (1) answers before (2) is consulted, even
    when (2) would have matched and pointed somewhere else."""
    db = pr_env
    _product(db, LOT, "AB12")
    db.commit()
    out = _resolve(db, _cfg(
        product_lookup={"table": LOOKUP_TABLE, "key_column": "lot",
                        "value_column": "product_code"},
        product_presets={"AB12": "tape_std"},
        rules=[_PREFIX_RULE]))
    assert out["preset_key"] == "tape_std"
    assert out["matched_by"]["stage"] == routing_mod.STAGE_PRODUCT_LOOKUP
    assert out["matched_by"]["product_code"] == "AB12"
    assert out["matched_by"]["rule"] == "product_presets['AB12']"


@pytest.mark.parametrize("kind,value,expect", [
    ("equals", "AF01", True), ("equals", "AF0", False),
    ("prefix", "AF", True), ("prefix", "F", False),
    ("suffix", "01", True), ("suffix", "AF", False),
    ("contains", "F0", True), ("contains", "XX", False),
    ("regex", r"^AF\d{2}$", True), ("regex", r"^ZZ", False),
    ("equals", "af01", False),   # matching is case-sensitive
])
def test_match_kinds(pr_env, kind, value, expect):
    out = _resolve(pr_env, _cfg(rules=[
        {"name": "r", "match": kind, "value": value, "preset": "core_std"}]))
    assert (out["status"] == routing_mod.STATUS_OK) is expect


# ---------------------------------------------------------------------------
# Declaration validation — bad pieces are DROPPED, never repaired
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    {"name": "no match kind", "value": "AF", "preset": "core_std"},
    {"name": "unknown kind", "match": "startswith", "value": "AF", "preset": "core_std"},
    {"name": "no value", "match": "prefix", "preset": "core_std"},
    {"name": "no preset", "match": "prefix", "value": "AF"},
    {"name": "bad regex", "match": "regex", "value": "AF(", "preset": "core_std"},
    {"name": "disabled", "match": "prefix", "value": "AF", "preset": "core_std",
     "enabled": False},
])
def test_invalid_rules_are_dropped_not_repaired(pr_env, bad):
    """A dropped rule must not be silently promoted to a default matcher — the
    answer has to be "no routing", not "some routing"."""
    out = _resolve(pr_env, _cfg(rules=[bad]))
    assert out["status"] == routing_mod.STATUS_NOT_DECLARED
    assert out["preset_key"] is None


def test_an_incomplete_lookup_declaration_is_dropped_but_patterns_survive(pr_env):
    out = _resolve(pr_env, _cfg(
        product_lookup={"table": LOOKUP_TABLE},   # no key/value column
        rules=[_PREFIX_RULE]))
    assert out["status"] == routing_mod.STATUS_OK
    assert out["lookup"]["declared"] is False


def test_disabled_table_declaration_is_not_declared(pr_env):
    out = _resolve(pr_env, _cfg(enabled=False, rules=[_PREFIX_RULE]))
    assert out["status"] == routing_mod.STATUS_NOT_DECLARED


def test_lot_key_part_selects_a_named_key_column(pr_env):
    """`slot` as the routing axis proves the part is SELECTED, not assumed to
    be the first one."""
    out = _resolve(pr_env, _cfg(lot_key_part="slot", rules=[
        {"name": "slot one", "match": "equals", "value": "1", "preset": "tape_std"}]))
    assert out["status"] == routing_mod.STATUS_OK
    assert out["matched_by"]["lot"] == "1"


def test_an_unknown_lot_key_part_is_refused(pr_env):
    out = _resolve(pr_env, _cfg(lot_key_part="nosuch", rules=[_PREFIX_RULE]))
    assert out["status"] == routing_mod.STATUS_UNRESOLVABLE
    assert out["preset_key"] is None


# ---------------------------------------------------------------------------
# Preset reference form — key first, then `name`
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ref,expect_key", [
    ("core_std", "core_std"),                       # by key
    ("CORE", "core_std"),                           # by name
    ("4A", "custom_1784890104442"),                 # by name, opaque key
])
def test_a_rule_may_name_a_preset_by_key_or_by_name(pr_env, ref, expect_key):
    out = _resolve(pr_env, _cfg(rules=[
        {"name": "r", "match": "prefix", "value": "AF", "preset": ref}]))
    assert out["preset_key"] == expect_key


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------

def test_endpoint_serves_the_resolution(client, pr_env, tmp_path, monkeypatch):
    import main
    cfg_path = tmp_path / "map_overlay_config.json"
    cfg_path.write_text(json.dumps(_cfg(rules=[_PREFIX_RULE])), encoding="utf-8")
    monkeypatch.setattr(map_overlay, "CONFIG_PATH", str(cfg_path))
    monkeypatch.setattr(main, "load_maps_config", lambda: {"presets": PRESETS})

    res = client.get("/api/maps/preset-routing",
                     params={"table": MAP_TABLE, "map_key": MAP_KEY_PADDED})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["preset_key"] == "core_std"
    assert body["preset"]["name"] == "CORE"
    assert body["canonical_map_key"] == MAP_KEY
    assert body["matched_by"]["rule"] == "AF family"
    assert body["lookup"]["declared"] is False


def test_endpoint_is_json_not_the_static_catch_all(client, pr_env):
    """server-pm memory: a non-existent path is answered by the static
    catch-all with HTML at 200, so a route test must prove the body is JSON."""
    res = client.get("/api/maps/preset-routing",
                     params={"table": MAP_TABLE, "map_key": MAP_KEY})
    assert res.status_code == 200
    assert res.json()["table"] == MAP_TABLE


def test_endpoint_requires_both_parameters(client, pr_env):
    assert client.get("/api/maps/preset-routing",
                      params={"table": MAP_TABLE}).status_code == 422
