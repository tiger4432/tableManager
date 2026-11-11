# -*- coding: utf-8 -*-
"""Lead 11-06 (owner «가상화로 걷는 모드 하나 만들어»): engine=virtual reads the declaration from its own tables; on a
ledger translated from those tables it draws the walk the stored ledger draws.

  the board   the sample's two sources (wafer -> recipe, a `one` predicate · lot slot -> wafer) on their tables,
              translated by the backfill into the stored ledger
  the cells   a walk · a time window · the old facts too (include_superseded) · walk-shadow's bins ·
              the key list · a continued walk refused · the stored answer carries no engine cell
"""
import json
import os
import re
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import paths                                                        # noqa: E402
from ledger import backfill, explorer, schema, trace, trace_router, walk_shadow  # noqa: E402
from ledger.setup import load_setup                                 # noqa: E402
from ledger_api import ledger_subgraph                              # noqa: E402
from test_ledger_worlds_are_independent_and_meet_in_a_walk import (  # noqa: E402,F401
    CHANGED, KEPT, _only, _timed, _write, fixture_config, fixture_world)

pytestmark = pytest.mark.pg


@pytest.fixture(autouse=True)
def _times_declared(monkeypatch):
    """The world's tables built with the sources' time columns declared datetime (`_timed`)."""
    import test_ledger_worlds_are_independent_and_meet_in_a_walk as worlds

    sample = worlds._sample
    monkeypatch.setattr(worlds, "_sample", lambda name: _timed(sample(name)) if name.startswith("table_config")
                        else sample(name))
ROWS = [{"proc_id": "P1", "wafer_id": "W1", "step": "S1", "recipe_id": "RCP-1", "eventtime": "2026-09-30 10:00:00"},
        {"proc_id": "P2", "wafer_id": "W1", "step": "S2", "recipe_id": "RCP-2", "eventtime": "2026-09-30 11:00:00"},
        {"proc_id": "P3", "wafer_id": "W2", "step": "S1", "recipe_id": "RCP-1", "eventtime": "2026-09-30 10:00:00"},
        {"proc_id": "P4", "wafer_id": "W3", "recipe_id": "RCP-3", "eventtime": "2026-09-30 12:00:00"}]
SEATS = [{"lot_slot_wafer_key": "K1", "lot": "L1", "slot": "1", "wafer": "W1", "event_type": "load",
          "event_time": "2026-09-30 10:00:00"},
         {"lot_slot_wafer_key": "K2", "lot": "L1", "slot": "2", "wafer": "W2", "event_type": "load",
          "event_time": "2026-09-30 10:30:00"}]


@pytest.fixture(name="board")
def fixture_board(world):
    return _board(world, _only(CHANGED, KEPT, one=True))


REGISTER = "register@1"


@pytest.fixture(name="registering")
def fixture_registering(world):
    """The board, and the recipe source registering each wafer - a sentence with no object, no attribute."""
    document = _only(CHANGED, KEPT, one=True)
    subjects = document["vocabulary"][REGISTER]["subjects"]
    if "wafer@1" not in subjects:
        subjects.append("wafer@1")
    document["sources"][CHANGED]["bind"]["mappings"]["wafer-registered"] = {"predicate": REGISTER, "bind": {
        "occurred_at": {"kind": "column", "column": "eventtime"},
        "subject": {"kind": "entity", "entity_type": "wafer@1",
                    "keys": {"wafer": {"kind": "column", "column": "wafer_id"}}}}}
    return _board(world, document)


def _board(world, document, rows=ROWS):
    import notation_norm

    with world["engine"].begin() as conn:
        conn.connection.cursor().execute(notation_norm.key_instant_sql() + notation_norm.key_number_sql())
    with open(os.path.join(paths.config_path("ontology"), "ledger_config.json"), "w", encoding="utf-8") as fh:
        json.dump(document, fh)
    trace_router._COMPILED.clear()
    _write(world, "wafer_process", rows)
    _write(world, "lot_slot_wafer", SEATS)
    for source in (CHANGED, KEPT):
        backfill.run(world["engine"], source=source)
    return world


def _walk(board, engine, **asked):
    seeds = {"positive": [explorer.entity_id("lot_slot", {"lot": "L1", "slot": "1"}),
                          explorer.entity_id("wafer", {"wafer": "W3"})], "negative": []}
    with board["engine"].connect() as conn:
        return trace_router._evidence_graph(conn, node_id=seeds, hops=3, direction="both", node_limit=200,
                                            edge_limit=400, engine=engine, **asked)


def _drawn(payload):
    """What both engines draw alike - an edge's `basis` and claim ids are the stored ledger's own (owner 11-07: the read
    is SQL alone, no byte parity with the stored record)."""
    nodes = sorted(json.dumps({k: n.get(k) for k in ("id", "type", "keys", "attributes")}, sort_keys=True)
                   for n in payload["nodes"])
    edges = sorted(json.dumps({k: e.get(k) for k in ("id", "source", "target", "predicate", "qualifiers",
                                                      "occurred_at", "not_current", "worlds")},
                              sort_keys=True, default=str) for e in payload["edges"])
    return nodes, edges, payload.get("truncated")


@pytest.mark.parametrize("asked", [{}, {"since": "2026-09-30T01:30:00+00:00"}, {"include_superseded": True}],
                         ids=["walk", "since", "old facts too"])
def test_the_virtual_walk_draws_the_walk_the_ledger_draws(board, asked):
    stored, virtual = _walk(board, "stored", **asked), _walk(board, "virtual", **asked)
    assert _drawn(virtual) == _drawn(stored)
    assert all(re.fullmatch(r"(wafer_process|lot_slot_wafer):[0-9a-f-]{36}", e["basis"]) for e in virtual["edges"])
    assert len(stored["edges"]) >= (1 if asked.get("since") else 3), "canary: the walk crosses both sources"
    assert "engine" not in stored, "the stored answer is today's - no new cell"
    said = virtual["engine"]
    assert said == {"name": "virtual", "left_out": [], "scans": said["scans"], "served": said["served"], "legs": said["legs"]}
    assert {end["table"] for end in said["scans"] + said["served"]} <= {"wafer_process", "lot_slot_wafer"}
    # each leg read timed (lead 11-11): the walk's own tables, a statement at least each, the rows it read
    assert said["legs"] and {leg["table"] for leg in said["legs"]} <= {"wafer_process", "lot_slot_wafer"}
    assert all(leg["statements"] >= 1 and leg["seconds"] >= 0 for leg in said["legs"])
    assert sum(leg["rows"] for leg in said["legs"]) >= len(virtual["edges"]) > 0 or asked.get("since")


def test_the_three_questions_are_three_answers(board):
    """Not vacuous: the window and the old facts change what this board draws."""
    whole = _drawn(_walk(board, "virtual"))[1]
    assert _drawn(_walk(board, "virtual", since="2026-09-30T01:30:00+00:00"))[1] != whole
    assert _drawn(_walk(board, "virtual", include_superseded=True))[1] != whole


def test_walk_shadow_finds_no_difference(board):
    _shadow_finds_no_difference(board)


def test_a_sentence_with_no_object_is_read_as_the_ledger_holds_it(registering):
    """11-10 (owner «가상 일괄», lead ㄷ): a registration is a leg with no object end - not left out; each atom the
    virtual read makes is the stored one (walk-shadow per predicate), and the walk draws what the stored walk draws."""
    raw = registering["engine"].raw_connection()
    try:
        legs, left_out = trace_router._compiled(raw, (schema.require_world(None),))
    finally:
        raw.rollback()
        raw.close()
    assert left_out == []
    [mine] = [leg for leg in legs if leg.sentence == "wafer-registered"]
    assert mine.ends["incoming"] == (None, {})
    said = _shadow_finds_no_difference(registering, follow=[mine.predicate])
    assert said[CHANGED]["atoms"]["stored"] >= 3, "canary: the stored ledger holds the registrations"
    stored, virtual = _walk(registering, "stored"), _walk(registering, "virtual")
    assert _drawn(virtual) == _drawn(stored) and virtual["engine"]["left_out"] == []


def test_a_source_with_entity_attributes_is_read_with_them(world):
    """Lead 11-10 stage 2: a source whose wafers carry an attribute - its declared registration sentence says it - is
    read whole: nothing left out, walk-shadow finds every atom of the source (the registrations with their attribute
    included, and no second registration of a type the source registers itself), the walk draws what the stored one
    draws, attribute and all."""
    from test_ledger_worlds_are_independent_and_meet_in_a_walk import _registering

    document = _registering("step")
    document["sources"][KEPT] = _only(CHANGED, KEPT)["sources"][KEPT]
    board = _board(world, document)
    raw = board["engine"].raw_connection()
    try:
        legs, left_out = trace_router._compiled(raw, (schema.require_world(None),))
    finally:
        raw.rollback()
        raw.close()
    assert left_out == []
    said = _shadow_finds_no_difference(board, follow=sorted({leg.predicate for leg in legs if leg.source == CHANGED}))
    assert said[CHANGED]["atoms"]["stored"] >= 7, "canary: edges and registrations both"
    stored, virtual = _walk(board, "stored"), _walk(board, "virtual")
    assert _drawn(virtual) == _drawn(stored) and len(stored["edges"]) >= 3
    labelled = [n for n in stored["nodes"] if n["type"] == "wafer" and (n.get("attributes") or {}).get("label")]
    assert labelled, "canary: the stored walk draws the attribute"


def test_a_role_with_attributes_registers_its_node_once_a_row_and_only_with_a_value(world):
    """Lead 11-10 stage 2: a source registering nothing itself, its wafers carrying `label` (from `step`) in two sentences
    of one row - the translator registers each wafer ONCE a row (one molecule, one fact), and not for a row whose
    `step` is blank (P4). Walk-shadow on «register» finds the stored registrations, no more, no fewer."""
    document = _only(CHANGED, KEPT, one=True)
    subjects = document["vocabulary"][REGISTER]["subjects"]
    if "wafer@1" not in subjects:
        subjects.append("wafer@1")
    document["entities"]["wafer@1"]["attributes"] = ["label"]
    bind = document["sources"][CHANGED]["bind"]
    bind["entities"] = {"wafer@1": {"attributes": {"label": {"kind": "column", "column": "step"}}}}
    bind["mappings"]["wafer-processed-again"] = json.loads(json.dumps(bind["mappings"]["wafer-processed-with-recipe"]))
    board = _board(world, document)
    raw = board["engine"].raw_connection()
    try:
        legs, left_out = trace_router._compiled(raw, (schema.require_world(None),))
    finally:
        raw.rollback()
        raw.close()
    assert left_out == []
    said = _shadow_finds_no_difference(board, follow=[REGISTER.split("@")[0]])
    assert said[CHANGED]["atoms"]["stored"] == 3, "canary: W1 twice (P1, P2) and W2 once (P3) - P4 has no step"


def test_a_value_object_is_read_as_the_ledger_holds_it(world):
    """Lead 11-10 value objects stage 2: a sentence whose object is a value - a string one here, which the stored
    translator refused row by row until its value role stopped being read as a required qualifier (the claim's own
    qualifier names, `setup_registry`) - is read whole: nothing left out, walk-shadow finds every atom of the source
    (the values included), the walk draws what the stored walk draws - a row whose value is blank keeping its edges, its value unsaid."""
    document = _only(CHANGED, KEPT, one=True)
    document["vocabulary"]["has_netdie@1"]["subjects"] = ["wafer@1"]              # a value predicate the sample has
    document["vocabulary"]["has_netdie@1"]["object"]["value_type"] = "string"
    document["sources"][CHANGED]["bind"]["mappings"]["wafer-step-value"] = {"predicate": "has_netdie@1", "bind": {
        "occurred_at": {"kind": "column", "column": "eventtime"},
        "subject": {"kind": "entity", "entity_type": "wafer@1",
                    "keys": {"wafer": {"kind": "column", "column": "wafer_id"}}},
        "value": {"kind": "column", "column": "step"}}}
    board = _board(world, document)
    raw = board["engine"].raw_connection()
    try:
        legs, left_out = trace_router._compiled(raw, (schema.require_world(None),))
    finally:
        raw.rollback()
        raw.close()
    assert left_out == []
    [valued] = [leg for leg in legs if leg.sentence == "wafer-step-value"]
    said = _shadow_finds_no_difference(board, follow=[valued.predicate])
    assert said[CHANGED]["atoms"]["stored"] == 3, "canary: the stored ledger holds the values (P1-P3; P4 has no step)"
    stored, virtual = _walk(board, "stored"), _walk(board, "virtual")
    assert _drawn(virtual) == _drawn(stored)
    assert len(stored["edges"]) >= 3, "P4's edges stay - a blank value unsays its own sentence alone (lead 11-10)"


def test_a_blank_required_qualifier_unsays_its_sentence_alone(world):
    """Lead 11-10 (ㄱ, the owner's «빈 거는 무시» 10-12 and «빈키행은 무시» 11-01): a required qualifier left blank on
    a row unsays that sentence there - not the row - in both engines; the row's edges stay. It refused the whole row
    (`missing_binding_value`) and the virtual walk left the source out."""
    document = _only(CHANGED, KEPT, one=True)
    vocabulary = document["vocabulary"]["has_netdie@1"]
    vocabulary["subjects"] = ["wafer@1"]
    vocabulary["object"]["value_type"] = "string"
    vocabulary["object"]["qualifiers"] = {"required": ["step"], "optional": []}
    document["sources"][CHANGED]["bind"]["mappings"]["wafer-recipe-value"] = {"predicate": "has_netdie@1", "bind": {
        "occurred_at": {"kind": "column", "column": "eventtime"},
        "subject": {"kind": "entity", "entity_type": "wafer@1",
                    "keys": {"wafer": {"kind": "column", "column": "wafer_id"}}},
        "value": {"kind": "column", "column": "recipe_id"},
        "step": {"kind": "column", "column": "step"}}}
    board = _board(world, document)
    raw = board["engine"].raw_connection()
    try:
        legs, left_out = trace_router._compiled(raw, (schema.require_world(None),))
    finally:
        raw.rollback()
        raw.close()
    assert left_out == []
    [qualified] = [leg for leg in legs if leg.sentence == "wafer-recipe-value"]
    said = _shadow_finds_no_difference(board, follow=[qualified.predicate])
    assert said[CHANGED]["atoms"]["stored"] == 3, "P1-P3 say it with their step; P4 (no step) does not"
    stored, virtual = _walk(board, "stored"), _walk(board, "virtual")
    assert _drawn(virtual) == _drawn(stored)
    assert len(stored["edges"]) >= 3, "P4's edges stay - its blank step unsays only the qualified sentence"


@pytest.fixture(name="thick")
def fixture_thick(config, monkeypatch):
    """wafer_process holds a float `thick` (table_config «number») - asked before `world`, which builds the table."""
    import test_ledger_worlds_are_independent_and_meet_in_a_walk as worlds

    catalogue = json.loads((config / "table_config.json").read_text(encoding="utf-8"))
    catalogue["wafer_process"]["column_types"]["thick"] = "number"
    (config / "table_config.json").write_text(json.dumps(catalogue), encoding="utf-8")
    sample = worlds._sample

    def floated(name):
        document = sample(name)
        if name.startswith("table_config"):
            document["wafer_process"]["column_types"]["thick"] = "number"
        return document
    monkeypatch.setattr(worlds, "_sample", floated)


def test_a_float_qualifier_is_read_as_the_ledger_holds_it(thick, world):
    """Owner on ops 11-11 («qualifier float»): a qualifier read from a float column - 9.0, 0.1 and two blank cells -
    compiles (nothing left out) and each atom the virtual read makes is the stored one; the walk draws what the stored
    walk draws, a blank saying no qualifier on both. (A NaN cell: the stored page refuses its row - `roleframe.
    _row_sort_token` - while the virtual read draws the row without the qualifier; not ruled here.)"""
    document = _only(CHANGED, KEPT, one=True)
    document["sources"][CHANGED]["bind"]["mappings"]["wafer-processed-with-recipe"]["bind"]["step"] = {
        "kind": "column", "column": "thick"}
    rows = [dict(row, thick=value) for row, value in zip(ROWS, (9.0, 0.1, None, None))]
    board = _board(world, document, rows=rows)
    raw = board["engine"].raw_connection()
    try:
        legs, left_out = trace_router._compiled(raw, (schema.require_world(None),))
    finally:
        raw.rollback()
        raw.close()
    assert left_out == []
    [floated] = [leg for leg in legs if leg.sentence == "wafer-processed-with-recipe"]
    assert floated.qualifiers == {"step": {"column": "thick", "kind": "float"}}
    _shadow_finds_no_difference(board, follow=[floated.predicate])
    stored, virtual = _walk(board, "stored", include_superseded=True), _walk(board, "virtual", include_superseded=True)
    assert _drawn(virtual) == _drawn(stored), [(sorted(set(v) - set(s)), sorted(set(s) - set(v)))
                                               for v, s in zip(_drawn(virtual)[:2], _drawn(stored)[:2])]
    said = sorted(str((e.get("qualifiers") or {}).get("step")) for e in stored["edges"] if e["predicate"] == floated.predicate)
    assert set(said) == {"0.1", "9.0", "None"}, "canary: 9.0 and 0.1 said, a blank not - %s" % said


def _shadow_finds_no_difference(board, follow=None):
    """walk-shadow over each source: the same atoms both ways, no bin - {source: what it said}."""
    out = {}
    raw = board["engine"].raw_connection()
    try:
        def fetch(sql, params=None):
            return trace._fetch(raw, sql, params)
        names = schema.require_world(None)
        snapshot = load_setup(names.declaration_root).snapshot
        legs, left_out = trace_router._compiled(raw, (names,))
        assert [item for item in left_out if not item["why"].endswith(" not read")] == [] and {leg.source for leg in legs} == {CHANGED, KEPT}
        for source in (CHANGED, KEPT):
            mine = [leg for leg in legs if leg.source == source]
            others = {names.name: [other for other in snapshot.source_plans if other != source]}
            seeds = [(kind, json.loads(keys)) for kind, keys in fetch(
                "SELECT DISTINCT subject_type, subject_keys::text FROM %s WHERE source_who = %%(s)s" % names.ledger,
                {"s": source})]
            said = walk_shadow.shadow(
                fetch, names.ledger, snapshot.source_plans[source],
                ledger_subgraph.SqlEvidenceLookup(raw, worlds=(names,), leave_out=others),
                ledger_subgraph.VirtualEvidenceLookup(raw, mine, worlds=(names,)), seeds,
                follow or sorted({leg.predicate for leg in mine}))
            if follow is None or source == CHANGED:
                assert said["atoms"]["stored"] and said["atoms"]["stored"] == said["atoms"]["virtual"], said
            assert said["bins"] == {"spelling": 0, "stale": 0, "stored-only": 0, "real": 0, "tie_split": 0}, said
            out[source] = said
        return out
    finally:
        raw.rollback()
        raw.close()


def test_the_key_list_follows_the_engine(board):
    session = board["db"]
    stored = trace_router.ledger_key_values(type="wafer", key=None, limit=50, world=None, starts_with=None,
                                            db=session, engine="stored")
    virtual = trace_router.ledger_key_values(type="wafer", key=None, limit=50, world=None, starts_with=None,
                                             db=session, engine="virtual")
    assert virtual["nodes"] == stored["nodes"] and len(stored["nodes"]) == 3
    assert "engine" not in stored and virtual["engine"]["name"] == "virtual"


def test_a_member_two_hubs_reach_at_one_time_joins_the_same_hub_on_both_engines(world, monkeypatch):
    """Lead 11-07: six wafers each processed with RCP-A and RCP-B at the same instant, the recipes walked with
    processed_with a hub - which hub a wafer joins is the read's order (`READ_ORDER`: time, then the atom's own content),
    not an id the two engines spell differently."""
    import notation_norm

    with world["engine"].begin() as conn:
        conn.connection.cursor().execute(notation_norm.key_instant_sql() + notation_norm.key_number_sql())
    with open(os.path.join(paths.config_path("ontology"), "ledger_config.json"), "w", encoding="utf-8") as fh:
        json.dump(_only(CHANGED, KEPT), fh)
    trace_router._COMPILED.clear()
    _write(world, "wafer_process", [{"proc_id": "P%d%s" % (n, recipe), "wafer_id": "W%d" % n, "recipe_id": "RCP-" + recipe,
                                     "eventtime": "2026-09-30 10:00:00"} for n in range(6) for recipe in "AB"])
    backfill.run(world["engine"], source=CHANGED)
    monkeypatch.setattr(trace_router, "_hub_predicates", lambda world=None: frozenset({"processed_with"}))
    seeds = {"positive": [explorer.entity_id("recipe", {"recipe": "RCP-" + recipe}) for recipe in "AB"],
             "negative": []}
    hubs = {}
    for engine in ("stored", "virtual"):
        with world["engine"].connect() as conn:
            payload = trace_router._evidence_graph(conn, node_id=seeds, hops=1, direction="both", node_limit=200,
                                                   edge_limit=400, engine=engine)
        hubs[engine] = sorted((node["id"], node["hub"]["count"]) for node in payload["nodes"]
                              if node.get("node_kind") == "hub")
    assert sum(count for _id, count in hubs["stored"]) == 6, hubs           # canary: the six wafers are members
    assert hubs["stored"] == hubs["virtual"], hubs


def test_a_read_cut_at_a_tie_keeps_the_same_atom_under_any_collation(world):
    """Lead 11-07 ㄴ: two wafers processed with one recipe at one instant, keys «a1» and «B1» - a read cut at 1 keeps
    the one first in the C order (the key's, `_read_order_key`) on both engines, whatever the database's collation
    (a linguistic one puts «B1» first)."""
    import notation_norm

    with world["engine"].begin() as conn:
        conn.connection.cursor().execute(notation_norm.key_instant_sql() + notation_norm.key_number_sql())
    with open(os.path.join(paths.config_path("ontology"), "ledger_config.json"), "w", encoding="utf-8") as fh:
        json.dump(_only(CHANGED, KEPT), fh)
    trace_router._COMPILED.clear()
    _write(world, "wafer_process", [{"proc_id": "P" + wafer, "wafer_id": wafer, "recipe_id": "RCP-T",
                                     "eventtime": "2026-09-30 10:00:00"} for wafer in ("B1", "a1")])
    backfill.run(world["engine"], source=CHANGED)
    raw = world["engine"].raw_connection()
    try:
        names = schema.require_world(None)
        legs, _ = trace_router._compiled(raw, (names,))
        seed = [("recipe", {"recipe": "RCP-T"})]
        for lookup in (ledger_subgraph.SqlEvidenceLookup(raw, worlds=(names,)),
                       ledger_subgraph.VirtualEvidenceLookup(raw, [leg for leg in legs if leg.source == CHANGED],
                                                            worlds=(names,))):
            whole, _ = lookup.claims_for_entities(seed, "both", 10, follow=["processed_with"])
            assert len(whole) == 2, "canary: both wafers are read"
            atoms, cut = lookup.claims_for_entities(seed, "both", 1, follow=["processed_with"])
            assert cut and [atom.subject_keys for atom in atoms] == [{"wafer": "a1"}], type(lookup).__name__
    finally:
        raw.rollback()
        raw.close()


def test_a_source_refused_for_a_text_time_keeps_its_stored_facts_and_leaves_the_virtual_walk(board):
    """Owner 11-07 «원장 소스에는 datetime만»: a source whose time column is declared text is refused when the declaration
    is loaded - the stored ledger keeps what it translated (its walk reads the ledger's rows, no plan), and the virtual
    walk leaves the source out by name."""
    before = _drawn(_walk(board, "stored"))
    assert any('"predicate": "processed_with"' in edge for edge in before[1]), "canary: the source's facts are drawn"
    path = paths.config_path("table_config.json")
    with open(path, encoding="utf-8") as fh:
        catalog = json.load(fh)
    catalog["wafer_process"]["column_types"]["eventtime"] = "string"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(catalog, fh)
    trace_router._COMPILED.clear()

    assert _drawn(_walk(board, "stored")) == before
    left_out = _walk(board, "virtual")["engine"]["left_out"]
    assert [item["source"] for item in left_out] == [CHANGED]
    assert "eventtime is string - declare eventtime datetime" in left_out[0]["why"], left_out


def test_a_virtual_walk_is_not_continued(board):
    with pytest.raises(HTTPException) as refused:
        trace_router.evidence_subgraph(node_id=explorer.entity_id("wafer", {"wafer": "W1"}), engine="virtual",
                                       resumable=True, db=board["db"], world=None, follow=None, collect=None,
                                       expand=None, seed_type=None, group_by=None, measure=None, since=None,
                                       until=None, around=None, earlier=None, later=None, positive=None,
                                       negative=None, resume=None)
    assert refused.value.status_code == 422 and refused.value.detail["reason"] == "virtual_walk_not_continued"


def test_a_walk_naming_no_engine_answers_from_the_tables_when_the_ledger_holds_nothing(world):
    """11-10 (owner «다 가상걷기로 해» · «전면 가상전환»): the operation's worlds are paused, so their ledger stops where it
    stopped - a walk naming no engine reads the tables, not that ledger. Here nothing was ever translated."""
    import notation_norm

    with world["engine"].begin() as conn:
        conn.connection.cursor().execute(notation_norm.key_instant_sql() + notation_norm.key_number_sql())
    with open(os.path.join(paths.config_path("ontology"), "ledger_config.json"), "w", encoding="utf-8") as fh:
        json.dump(_only(CHANGED, KEPT, one=True), fh)
    trace_router._COMPILED.clear()
    _write(world, "wafer_process", ROWS)
    _write(world, "lot_slot_wafer", SEATS)
    stored, unnamed, virtual = (_walk(world, engine) for engine in ("stored", None, "virtual"))
    assert not stored["edges"], "canary: the ledger holds nothing"
    assert len(unnamed["edges"]) >= 3 and unnamed["engine"]["name"] == "virtual", unnamed.get("engine")
    assert _drawn(unnamed) == _drawn(virtual)
