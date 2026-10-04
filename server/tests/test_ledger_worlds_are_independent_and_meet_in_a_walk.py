# -*- coding: utf-8 -*-
"""총괄 e1f54cd72 · e67ef53f3 · 092a6f9e5 — ledger worlds.

Each world has its own declaration and its own atoms and refers to no other (소유자 10-04). One
layout file says which world OPERATES - every seat that names no world reads and writes it - and
which follow their tables live: all, unless switched off. Worlds meet only in a walk that picks
several - their atoms read together, nothing filtered, each labelled with its world.
"""
import copy
import json
import os
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import MetaData, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
from support.isolated_pg import RUN_TOKEN                          # noqa: E402
import event_constants                                              # noqa: E402
import paths                                                        # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.context import channel                                # noqa: E402
from ledger import backfill, explorer, followup, schema, trace_router  # noqa: E402
from ledger.setup import load_setup                                 # noqa: E402
from ledger.store import LedgerStore                                # noqa: E402

SAMPLE = os.path.join(SERVER_DIR, "config", "sample")
CHANGED, KEPT = "wafer_process_recipe", "lot_slot_wafer"
TABLES = ("wafer_process", "lot_slot_wafer")
VIEW = schema.ATOM_ROWS_VIEW
TOKEN = "".join(ch for ch in RUN_TOKEN.lower() if ch.isalnum())[:16]
A, C = "a" + TOKEN, "c" + TOKEN
DEFAULT = schema.DEFAULT_WORLD
EVENT_TIME = "2026-09-30 10:00:00"
LATER = "2026-09-30 11:00:00"


def _sample(name):
    with open(os.path.join(SAMPLE, name), encoding="utf-8") as fh:
        return json.load(fh)


def _only(*sources, one=False):
    """The sample declaring `sources` alone - `one`: `processed_with@1` holds one recipe."""
    document = _sample("ledger_config.json.sample")
    document["sources"] = {name: document["sources"][name] for name in sources}
    if one:
        document["vocabulary"]["processed_with@1"]["cardinality"] = "one"
    return document


def _registering(column):
    """`_only(CHANGED)`, and each wafer registered with one attribute `label` read from `column`."""
    document = _only(CHANGED)
    if "wafer@1" not in document["vocabulary"]["register@1"]["subjects"]:
        document["vocabulary"]["register@1"]["subjects"].append("wafer@1")
    document["entities"]["wafer@1"]["attributes"] = ["label"]
    bind = document["sources"][CHANGED]["bind"]
    bind["entities"] = {"wafer@1": {"attributes": {"label": {"kind": "column", "column": column}}}}
    bind["mappings"]["wafer-registered"] = {"predicate": "register@1", "bind": {
        "occurred_at": {"kind": "column", "column": "eventtime"},
        "subject": {"kind": "entity", "entity_type": "wafer@1",
                    "keys": {"wafer": {"kind": "column", "column": "wafer_id"}}}}}
    return document


def _declare(world, document):
    root = Path(paths.config_path("ontology_worlds", world))
    root.mkdir(parents=True, exist_ok=True)
    (root / "ledger_config.json").write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture(name="config")
def fixture_config(tmp_path, monkeypatch):
    config = tmp_path / "config"
    (config / "ontology").mkdir(parents=True)
    shutil.copy(os.path.join(SAMPLE, "table_config.json.sample"), config / "table_config.json")
    shutil.copy(os.path.join(SAMPLE, "ledger_config.json.sample"),
                config / "ontology" / "ledger_config.json")
    monkeypatch.setattr(paths, "CONFIG_DIR", str(config))
    return config


# ------------------------------------------------------------------ the seat, no database

def test_no_layout_is_today(config):
    assert schema.operating_world() == DEFAULT
    assert schema.world_names() == schema.world_names(DEFAULT)
    assert (schema.world_names().world, schema.world_names().name) == (None, DEFAULT)
    assert schema.live_worlds() == [DEFAULT]
    _declare(A, _sample("ledger_config.json.sample"))
    assert schema.live_worlds() == [DEFAULT, A]                      # a world made follows live
    assert schema.world_names(A).declaration_root != schema.world_names().declaration_root


def test_every_seat_that_names_no_world_reads_the_operating_one(config):
    from ledger import config as ledger_config
    from ledger import setup as ledger_setup
    from ledger_api import declared_entities

    _declare(A, _sample("ledger_config.json.sample"))
    entry = schema.operate(A, "tester")
    root = os.path.normcase(os.path.normpath(schema.world_names(A).declaration_root))

    def norm(path):
        return os.path.normcase(os.path.normpath(str(path)))

    assert schema.world_names().world == A and LedgerStore(None).names.world == A
    assert [names.world for names in trace_router._worlds(None)] == [A]  # the walk route
    assert norm(os.path.dirname(ledger_config.config_path())) == root
    assert norm(os.path.dirname(declared_entities._config_path())) == root
    assert norm(load_setup().config_root) == norm(Path(root).resolve())
    # the default BY NAME stays the default
    assert schema.LEDGER_TABLE == "ledger_events"
    assert norm(ledger_setup.DEFAULT_ONTOLOGY_ROOT) != root
    assert (entry["world"], entry["by"]) == (A, "tester")

    schema.operate(DEFAULT)
    assert schema.world_names().world is None
    assert [h["world"] for h in schema.layout()["history"]] == [A, DEFAULT]
    with pytest.raises(LookupError):
        schema.operate("nope")


def test_a_world_is_switched_off_and_on_by_name_and_the_history_says_who(config):
    _declare(A, _sample("ledger_config.json.sample"))
    entry = schema.set_live(A, False, "tester")
    assert (schema.live(A), schema.live_worlds()) == (False, [DEFAULT])
    assert (entry["world"], entry["live"], entry["by"]) == (A, False, "tester")
    schema.set_live(A, True)
    assert (schema.live(A), schema.live_worlds()) == (True, [DEFAULT, A])
    assert [(h["world"], h["live"]) for h in schema.layout()["history"]] == [(A, False), (A, True)]
    with pytest.raises(LookupError):
        schema.set_live("nope", False)


def test_the_operating_world_and_the_default_are_not_deleted(config):
    _declare(A, _sample("ledger_config.json.sample"))
    schema.operate(A)
    with pytest.raises(ValueError, match="operating"):
        schema.world_deletion(None, A)
    with pytest.raises(ValueError):
        schema.world_deletion(None, DEFAULT)


def test_every_answer_that_lists_the_worlds_carries_one_shape(config):
    """총괄 e51e3e417: the declaration answer, /tables and the explorer's list - which also says
    which world follows live (총괄 092a6f9e5)."""
    import main
    from fastapi import HTTPException
    from ledger_api import ontology_config_explorer_router as explorer_router

    _declare(A, _sample("ledger_config.json.sample"))
    schema.operate(A)
    expected = {"worlds": [DEFAULT, A], "operating": A}
    for answer in (trace_router.ledger_declaration_catalog(world=None), main.list_tables(),
                   explorer_router.list_worlds()):
        assert {key: answer[key] for key in expected} == expected
    schema.set_live(A, False)
    assert explorer_router.list_worlds()["live"] == {DEFAULT: True, A: False}
    with pytest.raises(HTTPException) as refused:                    # 총괄 f1ad96964 ①
        trace_router._worlds("nowhere")
    assert refused.value.detail["worlds"] == expected["worlds"]


def test_a_walk_reads_the_worlds_picked_in_the_order_picked_and_filters_none(config):
    _declare(A, _sample("ledger_config.json.sample"))
    _declare(C, _sample("ledger_config.json.sample"))
    assert [n.name for n in trace_router._worlds([C, A, C, " "])] == [C, A]
    assert [n.name for n in trace_router._worlds(A)] == [A]
    assert [n.name for n in trace_router._worlds(None)] == [DEFAULT]
    relation = schema.walk_relation(trace_router._worlds([C, A]))
    assert relation.index("'%s'::text AS world" % C) < relation.index("'%s'::text AS world" % A)
    assert relation.count(" UNION ALL ") == 1 and "WHERE" not in relation


def test_a_walk_over_worlds_is_spelled_with_no_ledger_read(config):
    """클라 3c2d62f28: a branch view built its columns from the default ledger's catalogue and,
    where that ledger could not be seen, came out as `SELECT '<w>'::text AS world_leg,  FROM`.
    The walk's union names its columns from one constant and reads no catalogue - a branch
    alone does not even name the default's ledger."""
    _declare(A, _sample("ledger_config.json.sample"))
    relation = schema.walk_relation(trace_router._worlds([A]))
    assert relation == "(SELECT '%s'::text AS world, %s FROM w_%s.ledger_events)" % (
        A, ", ".join(schema.LEDGER_COLUMNS), A)


def test_a_name_two_worlds_declare_is_the_first_picked(config):
    document = _sample("ledger_config.json.sample")
    document["entities"]["tool@1"] = {"keys": ["tool"]}
    _declare(A, document)
    document = copy.deepcopy(document)
    document["entities"]["tool@1"] = {"keys": ["tool", "site"]}
    _declare(C, document)
    declared, whose = trace_router._declaration_and_whose([C, A])
    assert (declared["entities"]["tool@1"]["keys"], whose["entities"]["tool@1"]) == (
        ["tool", "site"], C)
    catalogue = trace_router.ledger_declaration_catalog(world=[A, C])
    (tool,) = [item for item in catalogue["entities"] if item["type"] == "tool@1"]
    assert (tool["keys"], tool["world"]) == (["tool"], A)
    assert {item["world"] for item in catalogue["predicates"]} == {A}


def test_a_type_the_named_world_does_not_declare_is_refused_by_that_world(config):
    """총괄 5fec118bb ②: the default declares tool, A does not - asked in A, the key search
    refuses it as not declared THERE (it said 「'tool' declares no keys」)."""
    from fastapi import HTTPException

    document = _sample("ledger_config.json.sample")
    document["entities"]["tool@1"] = {"keys": ["tool"]}
    (config / "ontology" / "ledger_config.json").write_text(json.dumps(document), encoding="utf-8")
    _declare(A, _sample("ledger_config.json.sample"))
    with pytest.raises(HTTPException) as refused:
        trace_router.ledger_key_values(type="tool", key=None,
                                       limit=trace_router.KEY_VALUE_DEFAULT_LIMIT, world=A, db=None)
    detail = refused.value.detail
    assert (refused.value.status_code, detail["reason"], detail["world"]) == (
        422, "node_type_not_declared", A)
    assert detail["message"].startswith("type 'tool' is not declared in world %s" % A)


# ------------------------------------------------------------------ on PostgreSQL

@pytest.fixture(name="world")
def fixture_world(pg_engine, config, monkeypatch):
    import database.database as database_module
    from ledger_api import ontology_config_explorer_router as explorer_router

    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"),
                            {"s": PG_TEST_SCHEMA}).scalar() == 1
    monkeypatch.setattr(database_module, "engine", pg_engine)
    monkeypatch.setattr(explorer_router, "_services", {})
    sample = _sample("table_config.json.sample")
    declared = {name: sample[name] for name in (*TABLES, VIEW)}
    saved = dict(crud.TABLE_CONFIG)
    for name in declared:
        retire_dynamic_model(name)
    models.init_dynamic_models(declared)
    crud.TABLE_CONFIG.update(declared)

    def clean():
        with pg_engine.begin() as conn:
            for world in (A, C):
                conn.execute(text("DROP SCHEMA IF EXISTS w_%s CASCADE" % world))
            for name in TABLES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
                for side in ("cell_sources", "database_outbox", "audit_logs"):
                    conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t'
                                      % (PG_TEST_SCHEMA, side)), {"t": name})
        raw = pg_engine.raw_connection()
        try:
            schema.ensure_schema(raw)
            from datetime import datetime, timezone
            schema.ensure_partition(raw, datetime(2026, 9, 30, 1, 0, tzinfo=timezone.utc))
            with raw.cursor() as cursor:
                for source in (CHANGED, KEPT):
                    cursor.execute(f"DELETE FROM {schema.LEDGER_TABLE} WHERE source_who = %s", (source,))
                    cursor.execute(f"DELETE FROM {schema.ROW_REF_TABLE} WHERE source_who = %s", (source,))
            raw.commit()
        finally:
            raw.close()
        schema._ensured.clear()

    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in TABLES:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    maker = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)
    session = maker()
    try:
        yield {"db": session, "maker": maker, "engine": pg_engine, "router": explorer_router}
    finally:
        session.close()
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in declared:
            retire_dynamic_model(name)


def _write(world, table, rows, key=None):
    """`key`: the row's business key, for a write that changes a row rather than makes one."""
    db = world["db"]
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, business_key_val=key, source_name="user",
                                      updated_by="probe")
            for row in rows]))
        db.commit()


def _seed(world):
    _write(world, "wafer_process", [{"proc_id": "P1", "wafer_id": "W1", "step": "S1",
                                     "recipe_id": "RCP-1", "eventtime": EVENT_TIME}])
    _write(world, "lot_slot_wafer", [{"lot_slot_wafer_key": "K1", "lot": "L1", "slot": "1",
                                      "wafer": "W1", "event_type": "load",
                                      "event_time": EVENT_TIME}])
    for source in (CHANGED, KEPT):
        backfill.run(world["engine"], source=source)


def _rows(world, relation, *columns, where=""):
    with world["engine"].connect() as conn:
        return sorted(tuple(r) for r in conn.execute(text(
            "SELECT %s FROM %s WHERE source_who IN (:a, :b) %s"
            % (", ".join(columns), relation, where)), {"a": CHANGED, "b": KEPT}))


def _saying(world, relation, needle):
    """Sources whose atoms in `relation` carry `needle` in their keys or payload."""
    return {who for (who,) in _rows(world, relation, "source_who",
                                    where="AND (subject_keys::text || coalesce(object_payload::text, '')) "
                                          "LIKE '%%%s%%'" % needle)}


def _make(world, name, document, *sources):
    """World `name` declared with `document` and its `sources` translated into it."""
    _declare(name, document)
    LedgerStore(world["engine"], world=name).ensure_schema()
    for source in sources:
        backfill.run(world["engine"], source=source, world=name)
    return schema.require_world(name)


def _operate(world, name):
    return world["router"].operate_world(SimpleNamespace(headers={"X-User": "tester"}),
                                         {"world": name})


def _follow(world):
    from chain import ingestion_worker

    with world["engine"].begin() as conn:
        conn.execute(text('UPDATE "%s".database_outbox SET processed_chain = true '
                          "WHERE table_name IN ('wafer_process', 'lot_slot_wafer')" % PG_TEST_SCHEMA))
    for _ in range(200):
        if ingestion_worker._drain_ledger_followup_sync(world["maker"]) is None:
            return
    raise AssertionError("the follow-up did not drain")


def _graph(world, worlds, node_type, keys, hops=2):
    with world["engine"].connect() as conn:
        return trace_router._evidence_graph(
            conn, node_id=explorer.entity_id(node_type, keys), hops=hops, direction="both",
            node_limit=200, edge_limit=400, world=worlds)


def _edges(world, worlds, node_type, keys, hops=2):
    payload = _graph(world, worlds, node_type, keys, hops)
    keys_of = {node["id"]: node.get("keys") for node in payload["nodes"]}
    return [{**edge, "far": json.dumps(keys_of.get(edge["target"]), sort_keys=True)}
            for edge in payload["edges"]]


def _walk(world, worlds, node_type, keys, hops=2):
    """(world, predicate, the far node's keys) for each world that says each edge a walk reads."""
    return sorted((said["world"], edge["predicate"], edge["far"])
                  for edge in _edges(world, worlds, node_type, keys, hops)
                  for said in edge["by_world"])


@pytest.mark.pg
def test_two_worlds_are_independent_and_meet_only_in_a_walk_that_picks_both(world):
    _seed(world)
    a = _make(world, A, _only(KEPT), KEPT)                           # lot slot -> wafer
    c = _make(world, C, _only(CHANGED), CHANGED)                     # wafer -> recipe
    assert {who for (who,) in _rows(world, a.ledger, "source_who")} == {KEPT}
    assert {who for (who,) in _rows(world, c.ledger, "source_who")} == {CHANGED}

    seat = {"lot": "L1", "slot": "1"}
    both = _walk(world, [A, C], "lot_slot", seat)
    assert {(w, p) for w, p, _ in both} == {(A, "has_wafer"), (C, "processed_with")}  # crosses
    assert {(w, p) for w, p, _ in _walk(world, [C], "wafer", {"wafer": "W1"})} == {
        (C, "processed_with")}                                       # C alone: no atom of A
    assert {w for w, _, _ in _walk(world, None, "lot_slot", seat)} == {DEFAULT}

    # A gains a source later; C does not move
    before = _rows(world, c.ledger, "id")
    _declare(A, _only(KEPT, CHANGED))
    backfill.run(world["engine"], source=CHANGED, world=A)
    assert _rows(world, c.ledger, "id") == before
    assert {who for (who,) in _rows(world, a.ledger, "source_who")} == {KEPT, CHANGED}

    # the same source in both: one edge, each world's evidence beside it (총괄 ee0f66e7b)
    (edge,) = [e for e in _edges(world, [A, C], "wafer", {"wafer": "W1"}, hops=1)
               if e["predicate"] == "processed_with"]
    assert sorted(edge["worlds"]) == sorted([A, C])
    assert sorted(said["world"] for said in edge["by_world"]) == sorted([A, C])
    assert len({said["claim_id"] for said in edge["by_world"]}) == 2
    (alone,) = [e for e in _edges(world, [C], "wafer", {"wafer": "W1"}, hops=1)
                if e["predicate"] == "processed_with"]
    assert (alone["id"], alone["worlds"]) == (edge["id"], [C])      # the id does not move


@pytest.mark.pg
def test_a_nodes_attribute_shows_each_worlds_value_beside_the_one(world):
    """총괄 4e1e49fe9: two worlds say one wafer's `label` differently -> a walk over both shows each
    world's value with when and who; the one value and the conflict count are today's."""
    _seed(world)
    _make(world, A, _registering("step"), CHANGED)
    _make(world, C, _registering("recipe_id"), CHANGED)
    seed = explorer.entity_id("wafer", {"wafer": "W1"})

    def node_and_when(worlds):
        payload = _graph(world, worlds, "wafer", {"wafer": "W1"}, hops=1)
        when = {said["world"]: said["occurred_at"] for edge in payload["edges"]
                if edge["predicate"] == "processed_with" for said in edge["by_world"]}
        (node,) = [node for node in payload["nodes"] if node["id"] == seed]
        return node, when

    node, when = node_and_when([A, C])
    assert set(when) == {A, C} and None not in when.values()        # canary: an event time each
    assert node["attributes_by_world"] == {"label": [
        {"world": A, "value": "S1", "occurred_at": when[A], "source_who": CHANGED},
        {"world": C, "value": "RCP-1", "occurred_at": when[C], "source_who": CHANGED}]}
    assert node["attributes"]["label"] in ("S1", "RCP-1") and node["attribute_conflicts"] == 1

    alone, when = node_and_when([C])
    assert alone["attributes_by_world"] == {"label": [
        {"world": C, "value": "RCP-1", "occurred_at": when[C], "source_who": CHANGED}]}
    assert (alone["attributes"], alone["attribute_conflicts"]) == ({"label": "RCP-1"}, 0)


@pytest.mark.pg
def test_a_fact_is_current_or_not_within_its_own_world(world):
    """A later fact of a `one` predicate in C does not hide A's - a source two worlds translated
    shows from both."""
    _seed(world)
    _make(world, A, _only(CHANGED, one=True), CHANGED)
    _make(world, C, _only(CHANGED, one=True), CHANGED)
    schema.set_live(A, False)
    _write(world, "wafer_process", [{"proc_id": "P2", "wafer_id": "W1", "step": "S2",
                                     "recipe_id": "RCP-9", "eventtime": LATER}])
    _follow(world)
    seen = {(w, json.loads(far).get("recipe")) for w, p, far in
            _walk(world, [A, C], "wafer", {"wafer": "W1"}, hops=1) if p == "processed_with"}
    assert seen == {(A, "RCP-1"), (C, "RCP-9")}, seen


@pytest.mark.pg
def test_every_live_world_follows_an_edit_and_one_switched_on_again_catches_up(world, monkeypatch):
    """총괄 092a6f9e5 · 71880678a ②: an edit reaches every live world. A world switched off
    misses a row made, a row edited and a row deleted; switching it on submits one job through
    the job door, and when it ends nothing is left, nothing has drifted and the lost row's atoms
    are gone."""
    from admin import retroactive
    from database import models
    from tests.support.retro_door import run_without_a_record

    monkeypatch.setattr(backfill, "beat", lambda result: None)
    _seed(world)
    _write(world, "wafer_process", [{"proc_id": "P4", "wafer_id": "W4", "step": "S1",
                                     "recipe_id": "RCP-4", "eventtime": EVENT_TIME}])
    _follow(world)
    a = _make(world, A, _only(KEPT, CHANGED), CHANGED, KEPT)
    c = _make(world, C, _only(CHANGED), CHANGED)
    _write(world, "wafer_process", [{"proc_id": "P1", "recipe_id": "RCP-2"}], key="P1")
    _follow(world)
    for relation in (schema.LEDGER_TABLE, a.ledger, c.ledger):
        assert _saying(world, relation, "RCP-2") == {CHANGED}, relation

    schema.set_live(C, False)
    _write(world, "wafer_process", [{"proc_id": "P1", "recipe_id": "RCP-3"}], key="P1")
    _write(world, "wafer_process", [{"proc_id": "P3", "wafer_id": "W3", "step": "S1",
                                     "recipe_id": "RCP-7", "eventtime": EVENT_TIME}])
    with world["engine"].connect() as conn:
        (gone,) = conn.execute(text('SELECT row_id FROM "%s".wafer_process WHERE proc_id = :p'
                                    % PG_TEST_SCHEMA), {"p": "P4"}).one()
    crud.delete_rows_batch(world["db"], "wafer_process", [gone], "probe")
    _follow(world)
    assert (_saying(world, a.ledger, "RCP-3"), _saying(world, a.ledger, "RCP-4")) == ({CHANGED}, set())
    assert (_saying(world, c.ledger, "RCP-3"), _saying(world, c.ledger, "RCP-7"),
            _saying(world, c.ledger, "RCP-4")) == (set(), set(), {CHANGED})   # C missed all three
    setup = load_setup(c.declaration_root)

    def left():
        """(rows the index does not name, rows drifted, rows lost and still indexed)"""
        engine = world["engine"]
        return (len(backfill.rows_missing_from_the_index(engine, setup, CHANGED, 100, world=C)),
                backfill.rows_drifted(engine, setup, CHANGED, world=C)["rows_drifted"],
                len(backfill.rows_gone_from_the_source(engine, setup, CHANGED, world=C)))

    assert left() == (1, 1, 1)
    counted = retroactive.count(SimpleNamespace(get_bind=lambda: world["engine"],
                                                rollback=lambda: None),
                                "ledger_catch_up", {"world": C})
    assert counted["affected"] == 3 and counted["extra"]["sources"][CHANGED] == {
        "rows_new": 1, "rows_drifted": 1, "rows_gone": 1}

    # 총괄 6091a7ae3 ②: a person's census says the three apart - the table less the index nets
    # the new row against the lost one - and names the catch-up; the paced tick carries them
    store = LedgerStore(world["engine"], world=C)

    def person_census(exact=True):
        said = backfill.measure_and_store(world["engine"], setup, CHANGED, store,
                                          exact_rows=exact)
        return ({box: said[box]["estimate"] for box in
                 ("difference", "rows_new", "rows_drifted", "rows_gone")}, said.get("next_step"))

    behind = ({"difference": 0, "rows_new": 1, "rows_drifted": 1, "rows_gone": 1},
              "python -m ledger.backfill --world %s --catch-up" % C)
    assert person_census() == behind
    assert person_census(exact=False) == behind
    answer = world["router"].set_world_live(
        C, SimpleNamespace(headers={"X-User": "tester"}), {"live": True}, db=world["db"])
    queued = world["db"].query(models.RetroactiveRun).filter(
        models.RetroactiveRun.run_id == answer["run_id"]).one()
    try:
        assert (answer["live"][C], queued.op, json.loads(queued.params)["world"]) == (
            True, "ledger_catch_up", C)
        run_without_a_record(world["engine"])(queued.op, json.loads(queued.params))
        assert left() == (0, 0, 0)
        census = backfill.rows_not_yet_translated(world["engine"], setup, CHANGED, world=C)
        assert (census["not_yet"], _saying(world, c.ledger, "RCP-4")) == (0, set())
        assert person_census() == ({"difference": 0, "rows_new": 0, "rows_drifted": 0,
                                    "rows_gone": 0}, None)
        assert (_saying(world, c.ledger, "RCP-3"), _saying(world, c.ledger, "RCP-7")) == (
            {CHANGED}, {CHANGED})
    finally:
        with world["engine"].begin() as conn:
            conn.execute(text('DELETE FROM "%s".retroactive_runs WHERE run_id = :r'
                              % PG_TEST_SCHEMA), {"r": answer["run_id"]})
            conn.execute(text('DELETE FROM "%s".database_outbox WHERE table_name = :t'
                              % PG_TEST_SCHEMA), {"t": retroactive.RUN_EVENT_TABLE})


@pytest.mark.pg
def test_an_edit_is_translated_once_and_writes_what_two_translations_wrote(world, monkeypatch):
    """총괄 6091a7ae3 ①: the translation that aims an edit's withdrawal is the one written - one
    per source per world, not two - and what it writes is what the second translation wrote."""
    from ledger import runtime_v2, setup as ledger_setup

    _seed(world)
    _follow(world)                                               # the seed's own events first
    calls = []
    real = runtime_v2.preview_cursor_batch

    def counted(*args, **kwargs):
        calls.append(args[1])
        return real(*args, **kwargs)

    monkeypatch.setattr(runtime_v2, "preview_cursor_batch", counted)
    monkeypatch.setattr(ledger_setup, "preview_cursor_batch", counted)
    _write(world, "wafer_process", [{"proc_id": "P1", "recipe_id": "RCP-2"}], key="P1")
    _follow(world)
    assert calls == [CHANGED]

    def said():
        return _rows(world, schema.LEDGER_TABLE, "predicate", "subject_keys::text",
                     "coalesce(object_payload::text, '')", "occurred_at", "source_raw_ref",
                     where="AND source_who = :a")

    once = said()
    assert once and _saying(world, schema.LEDGER_TABLE, "RCP-2") == {CHANGED}
    # the same row remade the old way - translated to aim the withdrawal, then again to write
    aim = backfill._preview_frame
    monkeypatch.setattr(backfill, "_preview_frame", lambda *a, **k: {**aim(*a, **k), "preview": None})
    setup = load_setup(schema.world_names().declaration_root)
    column = followup.scope_column(setup.snapshot.source_plans[CHANGED])
    with world["engine"].connect() as conn:
        values = [row[0] for row in conn.execute(text(
            'SELECT "%s" FROM "%s".wafer_process WHERE proc_id = :p' % (column, PG_TEST_SCHEMA)),
            {"p": "P1"})]
    backfill.rescope(world["engine"], setup, CHANGED, column, values, apply=True)
    assert calls == [CHANGED, CHANGED, CHANGED]                  # canary: that way was twice
    assert said() == once


@pytest.mark.pg
def test_each_live_world_leaves_its_own_receipt_and_says_which(world):
    """총괄 6091a7ae3 ③: one event followed in two live worlds leaves two batch receipts on the
    timeline, each naming the world it wrote into."""
    from ledger import runtime_v2

    _seed(world)
    _make(world, A, _only(CHANGED), CHANGED)
    _follow(world)                                               # the seed's own events first
    _write(world, "wafer_process", [{"proc_id": "P1", "recipe_id": "RCP-2"}], key="P1")
    with world["engine"].connect() as conn:
        (tx,) = conn.execute(text(
            'SELECT payload->>\'transaction_id\' FROM "%s".database_outbox WHERE table_name = '
            "'wafer_process' AND ledger_state IS NULL ORDER BY id DESC LIMIT 1"
            % PG_TEST_SCHEMA)).one()
    _follow(world)
    with world["engine"].connect() as conn:
        said = sorted((row[0] for row in conn.execute(text(
            'SELECT new_value->>\'world\' FROM "%s".audit_logs WHERE column_name = :c '
            "AND transaction_id = :t" % PG_TEST_SCHEMA),
            {"c": runtime_v2.RECEIPT_COLUMN, "t": tx})), key=str)
    assert tx and said == sorted([DEFAULT, A]), said


@pytest.mark.pg
def test_with_no_branch_the_follow_up_and_the_walk_are_todays(world):
    _seed(world)
    _write(world, "lot_slot_wafer", [{"lot_slot_wafer_key": "K1", "wafer": "W5"}], key="K1")
    _follow(world)
    assert _saying(world, schema.LEDGER_TABLE, "W5") == {KEPT}
    assert {w for w, _, _ in _walk(world, None, "lot_slot", {"lot": "L1", "slot": "1"})} == {DEFAULT}


@pytest.mark.pg
def test_a_deletion_is_withdrawn_in_every_live_world_and_not_in_one_switched_off(world):
    _seed(world)
    a = _make(world, A, _only(CHANGED), CHANGED)
    c = _make(world, C, _only(CHANGED), CHANGED)
    schema.set_live(C, False)
    with world["engine"].begin() as conn:
        (row_id,) = conn.execute(text('SELECT row_id FROM "%s".wafer_process' % PG_TEST_SCHEMA)).one()
        conn.execute(text('DELETE FROM "%s".wafer_process' % PG_TEST_SCHEMA))
    item = ("wafer_process", (row_id,), "DELETE", time.time(), None, 0, None)
    followup._follow_worlds(item, world["engine"], [
        (name, load_setup(schema.world_names(name).declaration_root))
        for name in schema.live_worlds()])
    assert _rows(world, a.ledger, "source_who") == []
    assert _rows(world, schema.LEDGER_TABLE, "source_who", where="AND source_who = :a") == []
    assert _rows(world, c.ledger, "source_who")                      # off: left as it was


@pytest.mark.pg
def test_every_worlds_ledger_has_the_columns_the_walk_names(world):
    """The constant the union reads its columns from is the table's own, default and branch."""
    _make(world, A, _only(CHANGED))
    with world["engine"].connect() as conn:
        for names in (schema.world_names(DEFAULT), schema.world_names(A)):
            columns = {row[0] for row in conn.execute(text(
                "SELECT attname FROM pg_attribute WHERE attrelid = to_regclass(:r) "
                "AND attnum > 0 AND NOT attisdropped"), {"r": names.ledger})}
            assert columns == set(schema.LEDGER_COLUMNS), names.ledger


@pytest.mark.pg
def test_a_two_world_walk_stays_flat(world):
    """Box EXPLAIN 09-30: a filter on a union kept the planner from flattening it (0.43 ms ->
    775 ms). The walk's union filters nothing, so its legs keep their indexes."""
    from ledger_api import ledger_subgraph

    _seed(world)
    _make(world, A, _only(CHANGED), CHANGED)

    class _Plan(ledger_subgraph.SqlEvidenceLookup):
        def _execute(self, sql, params):
            self.plan = "\n".join(row[0] for row in trace_router.trace._fetch(
                self.connection, "EXPLAIN " + sql, params))
            return []

    with world["engine"].connect() as conn:
        planned = _Plan(conn, worlds=trace_router._worlds([DEFAULT, A]))
        planned.claims_for_entities([("wafer", {"wafer": "W1"})], "outgoing", 50)
    assert "Subquery Scan" not in planned.plan, planned.plan


@pytest.mark.pg
def test_the_census_the_panel_and_a_backfill_naming_no_world_are_the_operating_worlds(world, monkeypatch):
    from admin import retroactive
    from chain import ingestion_worker
    from ledger import admin, census_cli
    from tests.support.retro_door import run_without_a_record

    monkeypatch.setattr(retroactive, "run_here", run_without_a_record(world["engine"]))
    monkeypatch.setattr(backfill, "beat", lambda result: None)
    _seed(world)
    a = _make(world, A, _only(KEPT, CHANGED), CHANGED, KEPT)
    _operate(world, A)
    for source in (CHANGED, KEPT):                                   # the paced tick
        ingestion_worker._measure_one_source_sync(world["maker"], source)
    census = trace_router._row_census_by_source()
    assert {source: census[source]["world"] for source in census} == {CHANGED: A, KEPT: A}
    assert census_cli.main(["--source", KEPT, "--world", DEFAULT]) == 0
    assert census_cli.main(["--world", "nope"]) == 2
    panel = admin.ingestion_view(world["db"], [CHANGED, KEPT])["sources"]
    assert {row["world"] for row in panel} == {A}
    _write(world, "lot_slot_wafer", [{"lot_slot_wafer_key": "K2", "lot": "L1", "slot": "2",
                                      "wafer": "W2", "event_type": "load",
                                      "event_time": EVENT_TIME}])
    assert backfill.main(["--source", KEPT]) == 0
    assert (_saying(world, a.ledger, "W2"), _saying(world, schema.LEDGER_TABLE, "W2")) == ({KEPT}, set())


def _stale_then_restamp(world, name, restamp):
    """Each cursor of world `name` given a fingerprint only the grammar moved, then `restamp()`:
    -> what each cursor carries after, and what that world's declaration wants."""
    from ledger.setup_registry import cursor_translator_version

    cursor = schema.world_names(name).cursor
    with world["engine"].begin() as conn:
        conn.execute(text("UPDATE %s SET translator_ver = 'ledger-v2:stale'" % cursor))
    restamp()
    setup = load_setup(schema.world_names(name).declaration_root)
    with world["engine"].connect() as conn:
        stamped = dict(conn.execute(text("SELECT source, translator_ver FROM %s" % cursor)).all())
    return stamped, {source: cursor_translator_version(setup.snapshot, source) for source in stamped}


@pytest.mark.pg
def test_the_boot_restamp_and_the_script_naming_no_world_move_the_operating_worlds_cursors(world):
    from chain import ingestion_worker
    from scripts import ledger_restamp_cursor

    _seed(world)
    _make(world, A, _only(KEPT, CHANGED), CHANGED, KEPT)
    _operate(world, A)
    for source in (CHANGED, KEPT):                                   # the census makes the rows
        ingestion_worker._measure_one_source_sync(world["maker"], source)
    for restamp in (lambda: ingestion_worker._restamp_moved_fingerprints_sync(world["maker"]),
                    lambda: ledger_restamp_cursor.main(["--apply"])):
        stamped, wanted = _stale_then_restamp(world, A, restamp)
        assert stamped and stamped == wanted


@pytest.mark.pg
def test_a_world_copied_starts_as_that_declaration_once_and_is_walked_before_it_is_translated(world):
    _seed(world)
    _make(world, A, _only(KEPT))
    world["router"].bootstrap_config(world=C, copy_from=A)
    with open(schema.world_names(C).declaration_path, encoding="utf-8") as fh:
        assert json.load(fh)["sources"].keys() == {KEPT}
    _declare(A, _only(KEPT, CHANGED))                                # A moves on; C does not
    with open(schema.world_names(C).declaration_path, encoding="utf-8") as fh:
        assert json.load(fh)["sources"].keys() == {KEPT}
    assert _walk(world, [C], "wafer", {"wafer": "W1"}) == []         # made, empty, walkable
    assert {w for w, _, _ in _walk(world, [C, DEFAULT], "wafer", {"wafer": "W1"})} == {DEFAULT}


@pytest.mark.pg
def test_the_grid_reads_the_atom_view_of_the_world_it_names(world):
    import main
    from fastapi import HTTPException

    _seed(world)
    _make(world, A, _only(CHANGED), CHANGED)

    def count(name):
        with world["engine"].connect() as conn:
            return conn.execute(text("SELECT count(*) FROM %s" % name)).scalar()

    in_a = count("w_%s.%s" % (A, VIEW))
    in_default = count(VIEW)
    assert in_a and in_default and in_a != in_default
    db = world["db"]
    assert main.get_table_data_count(VIEW, world=A, db=db)["total"] == in_a
    page = json.loads(main.get_table_data(VIEW, order_by="atom_id", world=A, db=db).body)
    assert len(page["data"]) == in_a
    assert main.get_table_data_count(VIEW, db=db)["total"] == in_default    # no world: operating
    with pytest.raises(HTTPException) as refused:
        main.get_table_data_count(VIEW, world="nope", db=db)
    assert refused.value.status_code == 404 and refused.value.detail["reason"] == "world_unknown"
    _operate(world, A)
    assert main.get_table_data_count(VIEW, db=db)["total"] == in_a
    listed = main.list_tables()
    assert (listed["operating"], A in listed["worlds"], listed["per_world"]) == (A, True, [VIEW])
