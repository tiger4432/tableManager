# -*- coding: utf-8 -*-
"""총괄 60d7e8e42 · 8d10633ae — a ledger branch, end to end on PostgreSQL, on the shipped sample.

The default world and a branch `w_<name>` share every source table. The branch changes ONE
source's declaration (wafer_process_recipe); translating it writes only that source into the
branch, and the walk reads the branch's view: the branch's atoms of that source and the
default's atoms of every other one - including a default row written after the branch was
made. Merging promotes the declaration and a whole-source rescope leaves no atom of the old
declaration; deleting the branch leaves no schema and no file.
"""
import copy
import json
import os
import shutil
import sys
from datetime import datetime, timezone

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
from ledger import backfill, schema                                 # noqa: E402
from ledger.store import LedgerStore                                # noqa: E402
from ledger_api import ledger_subgraph                              # noqa: E402

pytestmark = pytest.mark.pg
SAMPLE = os.path.join(SERVER_DIR, "config", "sample")
TABLES = ("wafer_process", "lot_slot_wafer")
CHANGED, KEPT = "wafer_process_recipe", "lot_slot_wafer"
ADDED = "zz_wafer_at_step"
WORLD = "exp" + "".join(ch for ch in RUN_TOKEN.lower() if ch.isalnum())[:20]
EVENT_TIME = "2026-09-30 10:00:00"


def _sample(name):
    with open(os.path.join(SAMPLE, name), encoding="utf-8") as fh:
        return json.load(fh)


def _branch_document():
    """The sample, with wafer_process_recipe saying its core sentence without the `when`."""
    document = _sample("ledger_config.json.sample")
    mappings = document["sources"][CHANGED]["bind"]["mappings"]
    mappings.pop("dtwafer-processed-with-recipe")
    mappings["wafer-processed-with-recipe"].pop("when", None)
    return document


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    config = tmp_path / "config"
    (config / "ontology").mkdir(parents=True)
    (config / "ontology_worlds" / WORLD).mkdir(parents=True)
    shutil.copy(os.path.join(SAMPLE, "table_config.json.sample"), config / "table_config.json")
    shutil.copy(os.path.join(SAMPLE, "ledger_config.json.sample"),
                config / "ontology" / "ledger_config.json")
    (config / "ontology_worlds" / WORLD / "ledger_config.json").write_text(
        json.dumps(_branch_document()), encoding="utf-8")
    monkeypatch.setattr(paths, "CONFIG_DIR", str(config))

    declared = {name: _sample("table_config.json.sample")[name] for name in TABLES}
    saved = dict(crud.TABLE_CONFIG)
    for name in TABLES:
        retire_dynamic_model(name)
    models.init_dynamic_models(declared)
    crud.TABLE_CONFIG.update(declared)

    def clean():
        with pg_engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS w_%s CASCADE" % WORLD))
            for name in TABLES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
                conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": name})
                conn.execute(text("DELETE FROM database_outbox WHERE table_name = :t"), {"t": name})
        raw = pg_engine.raw_connection()
        try:
            schema.ensure_schema(raw)
            schema.ensure_partition(raw, datetime(2026, 9, 30, 1, 0, tzinfo=timezone.utc))
            with raw.cursor() as cursor:
                for source in (CHANGED, KEPT):
                    cursor.execute(f"DELETE FROM {schema.LEDGER_TABLE} WHERE source_who = %s", (source,))
                    cursor.execute(f"DELETE FROM {schema.ROW_REF_TABLE} WHERE source_who = %s", (source,))
            raw.commit()
        finally:
            raw.close()

    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in TABLES:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    try:
        yield {"db": session, "engine": pg_engine, "config": config}
    finally:
        session.close()
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in TABLES:
            retire_dynamic_model(name)


def _write(world, table, rows):
    db = world["db"]
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="user", updated_by="probe")
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


def _rows(world, relation, *columns):
    with world["engine"].connect() as conn:
        return sorted(tuple(r) for r in conn.execute(text(
            "SELECT %s FROM %s WHERE source_who IN (:a, :b)" % (", ".join(columns), relation)),
            {"a": CHANGED, "b": KEPT}))


def test_the_branch_translates_what_it_changed_and_walks_the_rest_from_the_default(world):
    _seed(world)
    names = schema.require_world(WORLD)
    default_before = _rows(world, schema.LEDGER_TABLE, "source_who", "source_translator_ver")

    assert schema.changed_sources(names) == {CHANGED}
    LedgerStore(world["engine"], world=WORLD).ensure_schema()     # what the CLI entry does
    backfill.run(world["engine"], source=CHANGED, world=WORLD)

    assert _rows(world, schema.LEDGER_TABLE, "source_who", "source_translator_ver") == default_before
    assert {who for (who,) in _rows(world, names.ledger, "source_who")} == {CHANGED}
    legs = set(_rows(world, names.read_relation, "source_who", "world_leg"))
    assert legs == {(CHANGED, "branch"), (KEPT, "default")}, legs

    with world["engine"].connect() as conn:
        lookup = ledger_subgraph.SqlEvidenceLookup(conn, relation=names.read_relation)
        claims, _cut = lookup.claims_for_entities([("wafer", {"wafer": "W1"})], "both", 50)
    assert {claim.source_who for claim in claims} == {CHANGED, KEPT}

    # and through the walk route's own door, naming the world with one argument
    from fastapi import HTTPException
    from ledger import explorer, trace_router

    with world["engine"].connect() as conn:
        payload = trace_router._evidence_graph(
            conn, node_id=explorer.entity_id("wafer", {"wafer": "W1"}), hops=3,
            direction="both", node_limit=100, edge_limit=200, world=WORLD)
    predicates = {edge.get("predicate") for edge in payload["edges"]}
    assert {"processed_with", "has_wafer"} <= predicates, predicates

    # 🔴 THE VIEW'S SHAPE, BY PLAN: a filter on the partitioned default's leg keeps the union
    # from flattening (a Subquery Scan over every partition - box 09-30: 0.43 ms -> 775 ms).
    class _Plan(ledger_subgraph.SqlEvidenceLookup):
        def _execute(self, sql, params):
            self.plan = "\n".join(row[0] for row in trace_router.trace._fetch(
                self.connection, "EXPLAIN " + sql, params))
            return []

    with world["engine"].connect() as conn:
        planned = _Plan(conn, relation=names.read_relation)
        planned.claims_for_entities([("wafer", {"wafer": "W1"})], "outgoing", 50)
    assert "Subquery Scan" not in planned.plan, planned.plan
    assert trace_router.ledger_declaration_catalog(world=None)["worlds"] == [WORLD]
    with pytest.raises(HTTPException) as refused:
        trace_router._world("nowhere")
    assert refused.value.status_code == 404
    assert refused.value.detail["reason"] == "world_unknown"

    # a default row written AFTER the branch was made is seen through the branch
    _write(world, "lot_slot_wafer", [{"lot_slot_wafer_key": "K2", "lot": "L1", "slot": "2",
                                      "wafer": "W2", "event_type": "load",
                                      "event_time": EVENT_TIME}])
    backfill.run(world["engine"], source=KEPT)
    walked = [(kind, json.loads(keys))
              for kind, keys in _rows(world, names.read_relation, "subject_type",
                                      "subject_keys::text")]
    assert ("lot_slot", {"lot": "L1", "slot": "2"}) in walked, walked


def _branch_translated(world):
    _seed(world)
    LedgerStore(world["engine"], world=WORLD).ensure_schema()
    backfill.run(world["engine"], source=CHANGED, world=WORLD)
    return schema.require_world(WORLD)


def test_a_merge_promotes_the_declaration_and_leaves_no_atom_of_the_old_one(world):
    from ledger.config_explorer_service import OntologyExplorerService
    from ledger.setup import load_setup
    from ledger.setup_registry import cursor_translator_version

    names = _branch_translated(world)

    def versions(relation):
        return {version for who, version in _rows(
            world, relation, "source_who", "source_translator_ver") if who == CHANGED}

    before, in_branch = versions(schema.LEDGER_TABLE), versions(names.ledger)
    assert before and in_branch and not before & in_branch
    branch_version = cursor_translator_version(
        load_setup(names.declaration_root).snapshot, CHANGED)

    # the save gate the explorer already is, on the default world, with the branch's text
    default = schema.world_names()
    service = OntologyExplorerService(config_root=default.declaration_root,
                                      draft_root=default.draft_root)
    _setup, index, *_rest = service.active()
    draft = service.create_draft(target_key="source_plan|" + CHANGED,
                                 base_snapshot_hash=index.snapshot_hash)
    saved = service.save_draft(draft["draft_id"], expected_revision=0,
                               raw=json.dumps(_branch_document()["sources"][CHANGED]))
    assert saved["preview_valid"] is True, saved.get("validation_errors")
    service.activate_draft(draft["draft_id"], expected_revision=1, reload_callback=lambda: None)

    merged = load_setup(default.declaration_root)
    assert cursor_translator_version(merged.snapshot, CHANGED) == branch_version
    backfill.rescope(world["engine"], merged, CHANGED, None, None, apply=True,
                     page_rows=backfill.RESCOPE_PAGE_ROWS, whole_source=True)

    after = versions(schema.LEDGER_TABLE)
    assert after == in_branch, (after, in_branch)     # what the branch said, the default says
    assert not after & before                          # no atom of the old declaration


def test_a_whole_source_refresh_takes_the_atoms_of_a_row_the_source_lost(world):
    """총괄 3a109bfd9 ③: a branch has no follow-up, and the default's can miss a delete. A
    whole-source refresh withdraws what the relation lost, in every world, the way a delete is."""
    from ledger.setup import load_setup

    names = _branch_translated(world)
    _write(world, "wafer_process", [{"proc_id": "P2", "wafer_id": "W2", "step": "S1",
                                     "recipe_id": "RCP-1", "eventtime": EVENT_TIME}])
    for name in (None, WORLD):
        backfill.run(world["engine"], source=CHANGED, world=name)
    with world["engine"].begin() as conn:                     # no outbox row: nobody follows it
        conn.execute(text('DELETE FROM "%s"."wafer_process" WHERE proc_id = :p' % PG_TEST_SCHEMA),
                     {"p": "P2"})

    def atoms_of(relation, wafer):
        with world["engine"].connect() as conn:
            return conn.execute(text(
                "SELECT count(*) FROM %s WHERE source_who = :s AND subject_keys::text LIKE :w"
                % relation), {"s": CHANGED, "w": '%%"%s"%%' % wafer}).scalar()

    for name, relation in ((None, schema.LEDGER_TABLE), (WORLD, names.ledger)):
        setup = load_setup(schema.require_world(name).declaration_root)
        assert atoms_of(relation, "W2") > 0 and atoms_of(relation, "W1") > 0, name
        said = backfill.rescope(world["engine"], setup, CHANGED, None, None, apply=False,
                                whole_source=True, world=name)      # the cheap preview
        assert (said["relation_rows"], said["gone_rows"], said["gone_atoms"]) == (
            1, 1, atoms_of(relation, "W2")), (name, said)
        done = backfill.rescope(world["engine"], setup, CHANGED, None, None, apply=True,
                                page_rows=backfill.RESCOPE_PAGE_ROWS, whole_source=True,
                                world=name)
        assert (done["gone_rows"], done["gone_withdrawn"] > 0) == (1, True), (name, done)
        assert atoms_of(relation, "W2") == 0 and atoms_of(relation, "W1") > 0, name
        again = backfill.rescope(world["engine"], setup, CHANGED, None, None, apply=True,
                                 page_rows=backfill.RESCOPE_PAGE_ROWS, whole_source=True,
                                 world=name)
        assert (again["gone_rows"], again["gone_withdrawn"]) == (0, 0), (name, again)
        said = backfill.rescope(world["engine"], setup, CHANGED, None, None, apply=False,
                                whole_source=True, world=name)
        assert (said["gone_rows"], said["gone_atoms"]) == (0, 0), (name, said)


def _refuse(path, source):
    """`source` read by an order that is not a column: the loader leaves it out alone."""
    with open(path, encoding="utf-8") as fh:
        document = json.load(fh)
    document["sources"][source]["read"]["order_by"] = ["no_such_column"]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(document, fh)


def test_a_source_refused_on_both_sides_is_the_defaults_and_on_one_side_the_branchs(world):
    """총괄 (10-01) 가: refused on both sides, the branch has nothing new to say about a source,
    so its view keeps the default's atoms (it spoke of LESS than the default before);
    refused on one side only, the two declarations differ."""
    names = _branch_translated(world)
    default = schema.world_names()
    _refuse(names.declaration_path, KEPT)
    assert KEPT in schema.changed_sources(names)                  # one side: changed
    _refuse(default.declaration_path, KEPT)
    assert schema.changed_sources(names) == {CHANGED}             # both sides: not
    backfill.refresh_world_view(world["engine"], WORLD)
    legs = set(_rows(world, names.read_relation, "source_who", "world_leg"))
    assert (KEPT, "default") in legs, legs


def test_deleting_the_branch_leaves_no_schema_and_no_file(world):
    names = _branch_translated(world)
    preview = schema.world_deletion(world["engine"], WORLD)
    assert preview["atoms"] > 0 and preview["files"], preview

    with pytest.raises(ValueError):
        schema.drop_world(world["engine"], WORLD, preview["atoms"] + 1)   # a moved count
    schema.drop_world(world["engine"], WORLD, preview["atoms"])

    with world["engine"].connect() as conn:
        assert conn.execute(text("SELECT to_regnamespace(:s)"), {"s": names.schema}).scalar() is None
    assert not os.path.exists(names.declaration_root)
    assert WORLD not in schema.worlds()
    with pytest.raises(ValueError):
        schema.world_deletion(world["engine"], None)                     # the default: never


def test_a_branch_that_adds_a_source_writes_only_that_source(world):
    """총괄 c23b02aeb ③ — rows are queued by TABLE, so translating a NEW source that reads
    wafer_process also wrote wafer_process_recipe into the branch, and the view then hid that
    source's default atoms (box: 10 -> 8 on a partly translated branch). A branch writes only
    the sources it speaks for; the one it did not change stays the default's in its view."""
    _seed(world)
    document = _sample("ledger_config.json.sample")
    document["entities"]["stepno@1"] = {"keys": ["step"]}
    document["vocabulary"]["at_step@1"] = {
        "status": "active", "subjects": ["wafer@1"],
        "object": {"kind": "entity_ref", "types": ["stepno@1"],
                   "qualifiers": {"required": [], "optional": []}}}
    added = copy.deepcopy(document["sources"][CHANGED])
    said = added["bind"]["mappings"]["wafer-processed-with-recipe"]["bind"]
    added["bind"]["mappings"] = {"wafer-at-step": {"predicate": "at_step@1", "bind": {
        "occurred_at": said["occurred_at"], "subject": said["subject"],
        "target": {"kind": "entity", "entity_type": "stepno@1",
                   "keys": {"step": {"kind": "column", "column": "step"}}}}}}
    document["sources"][ADDED] = added
    (world["config"] / "ontology_worlds" / WORLD / "ledger_config.json").write_text(
        json.dumps(document), encoding="utf-8")
    names = schema.require_world(WORLD)
    assert schema.changed_sources(names) == {ADDED}

    LedgerStore(world["engine"], world=WORLD).ensure_schema()
    backfill.run(world["engine"], source=ADDED, world=WORLD)

    with world["engine"].connect() as conn:
        written = {who for (who,) in conn.execute(text(
            "SELECT DISTINCT source_who FROM %s" % names.ledger))}
        legs = set(conn.execute(text(
            "SELECT source_who, world_leg FROM %s WHERE source_who IN (:a, :b)"
            % names.read_relation), {"a": CHANGED, "b": ADDED}).fetchall())
    assert written == {ADDED}, written
    assert legs == {(ADDED, "branch"), (CHANGED, "default")}, legs


# ── 총괄 c23b02aeb ② — the view is made again at the doors that make and save a branch ──
# Only backfill made a branch's view, so a branch whose change moves no source (a `static` flip)
# had none and its walk answered 503, and a save that changed which sources the branch speaks
# for left the view excluding the old set.

@pytest.fixture(name="doors")
def fixture_doors(world, monkeypatch):
    import database.database as database_module
    from ledger_api import ontology_config_explorer_router as explorer_router
    from runtime import system_reload

    monkeypatch.setattr(database_module, "engine", world["engine"])
    monkeypatch.setattr(system_reload, "reload_system_configs", lambda db: None)
    monkeypatch.setattr(explorer_router, "_services", {})
    _seed(world)
    return explorer_router


def test_a_branch_made_through_bootstrap_is_walked_before_anything_is_translated(world, doors):
    from ledger import explorer, trace_router

    made = "v" + WORLD[1:]
    try:
        doors.bootstrap_config(world=made)
        with world["engine"].connect() as conn:
            payload = trace_router._evidence_graph(
                conn, node_id=explorer.entity_id("wafer", {"wafer": "W1"}), hops=2,
                direction="both", node_limit=100, edge_limit=200, world=made)
        assert {"processed_with", "has_wafer"} <= {e.get("predicate") for e in payload["edges"]}
    finally:
        if made in schema.worlds():
            preview = schema.world_deletion(world["engine"], made)
            schema.drop_world(world["engine"], made, preview["atoms"])


def _saved_legs(world):
    names = schema.require_world(WORLD)
    return schema.changed_sources(names), set(_rows(world, names.read_relation,
                                                    "source_who", "world_leg"))


def test_a_save_that_changes_a_source_takes_its_default_atoms_out_of_the_view(world, doors):
    service = doors._service_for(WORLD)
    _setup, index, *_rest = service.active()
    draft = service.create_draft(target_key="source_plan|" + KEPT,
                                 base_snapshot_hash=index.snapshot_hash)
    source = _branch_document()["sources"][KEPT]
    source["bind"]["mappings"]["seat-holds-wafer-saved"] = source["bind"]["mappings"].pop(
        "seat-holds-wafer")
    saved = service.save_draft(draft["draft_id"], expected_revision=0, raw=json.dumps(source))
    assert saved["preview_valid"] is True, saved.get("validation_errors")
    doors.activate_draft(draft["draft_id"], payload={"expected_revision": 1},
                         db=world["db"], world=WORLD)

    changed, legs = _saved_legs(world)
    assert changed == {CHANGED, KEPT}
    assert (KEPT, "default") not in legs and (CHANGED, "default") not in legs, legs


def test_a_deleted_declaration_takes_its_default_atoms_out_of_the_view(world, doors):
    service = doors._service_for(WORLD)
    _setup, index, *_rest = service.active()
    doors.delete_declaration("source_plan|" + KEPT, base_snapshot_hash=index.snapshot_hash,
                             db=world["db"], world=WORLD)

    changed, legs = _saved_legs(world)
    assert KEPT in changed
    assert (KEPT, "default") not in legs, legs
