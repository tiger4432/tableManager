# -*- coding: utf-8 -*-
"""총괄 793017c62 · edcc0568c (10-12 demo) — the walks a folded lump asks for, on PostgreSQL.

The owner's measurement shape (board, 10-08): wafer ─measured▶ measurement_event(value) ─used▶ recipe ·
─of▶ quantity. Process events: wafer ─underwent▶ process_event. Rows go the product's way - the sample's
own `metro` and `process_event` tables, a ledger declaration under a temporary config root, `backfill.run`
- and the walks are GET /api/ledger/subgraph on a bare app.

  wafer start          the start wafer's measurements; the recipe is static, so other wafers' stay out
  recipe, one step     every measurement that used the recipe - the start wafer's and the others' - with
                       its value and the time it was measured; `since`/`until` cut it, `node_limit` caps it
  process-event lump   the lump's members as seeds, through their wafer to that wafer's measurements

`WALK_FOLD_CAPTURE_DIR` set: the three answers are written there (client2/tests/fixtures/capture_walk_fold.py).
"""
import copy
import io
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
import event_constants                                              # noqa: E402
import paths                                                        # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.context import channel                                # noqa: E402
from ledger import backfill, explorer, schema, trace_router         # noqa: E402

pytestmark = pytest.mark.pg
SAMPLE = os.path.join(SERVER_DIR, "config", "sample")
METRO, PROCESS = "metro", "process_event"
SOURCES = (METRO, PROCESS)
EVENT = {"occurred_at": {"kind": "column", "column": "event_time"}}
READ = {"unit": "row", "identity": ["row_id"], "order_by": ["row_id"], "cursor": {"columns": ["row_id"]},
        "occurred_at": {"column": "event_time", "timezone": "Asia/Seoul"}}
MAP = {"implementation_id": "declarative-role", "implementation_version": 1, "unit": {"kind": "row"}}


def _role(entity_type, key, column):
    return {"kind": "entity", "entity_type": entity_type, "keys": {key: {"kind": "column", "column": column}}}


def _link(predicate, subject, target):
    return {"predicate": predicate, "bind": {**EVENT, "subject": subject, "target": target}}


def _sample(name):
    with open(os.path.join(SAMPLE, name), encoding="utf-8") as fh:
        return json.load(fh)


def declaration():
    """The sample's entities and vocabulary, plus the owner's measurement shape and process events."""
    document = _sample("ledger_config.json.sample")
    document["entities"]["measurement_event@1"] = {"keys": ["event"], "attributes": ["value"], "label": ["value"]}
    document["entities"]["process_event@1"] = {"keys": ["event"], "attributes": ["step"], "label": ["step"]}
    qualifiers = {"required": [], "optional": []}
    for name, subjects, target in (("measured@1", "wafer@1", "measurement_event@1"),
                                   ("used@1", "measurement_event@1", "recipe@1"),
                                   ("of@1", "measurement_event@1", "quantity@1"),
                                   ("underwent@1", "wafer@1", "process_event@1")):
        document["vocabulary"][name] = {"status": "active", "subjects": [subjects],
                                        "object": {"kind": "entity_ref", "types": [target],
                                                   "qualifiers": copy.deepcopy(qualifiers)}}
    wafer = _role("wafer@1", "wafer", "wafer_id")
    measurement = _role("measurement_event@1", "event", "txn_seq")
    document["sources"] = {
        METRO: {"relation": METRO, "read": READ, "map": MAP, "bind": {
            "entities": {"measurement_event@1": {"attributes": {"value": {"kind": "column", "column": "value"}}}},
            "mappings": {
                "wafer-measured": _link("measured@1", wafer, measurement),
                "event-used-recipe": _link("used@1", measurement, _role("recipe@1", "recipe", "rcp_id")),
                "event-of-quantity": _link("of@1", measurement, _role("quantity@1", "quantity", "item_id"))}}},
        PROCESS: {"relation": PROCESS, "read": READ, "map": MAP, "bind": {
            "entities": {"process_event@1": {"attributes": {"step": {"kind": "column", "column": "step_seq"}}}},
            "mappings": {"wafer-underwent": _link("underwent@1", wafer,
                                                  _role("process_event@1", "event", "txn_seq"))}}},
    }
    return document


#: (txn_seq, wafer, step, recipe, quantity, value, event_time) - RCP-A holds the start wafer W1's two and
#: two other wafers'; M5 is another recipe's.
MEASUREMENTS = [("M1", "W1", "S1", "RCP-A", "THK", "10.1", "2026-10-01 09:10:00"),
                ("M2", "W1", "S2", "RCP-A", "THK", "10.4", "2026-10-01 11:10:00"),
                ("M3", "W2", "S1", "RCP-A", "THK", "9.7", "2026-10-01 10:10:00"),
                ("M4", "W3", "S1", "RCP-A", "THK", "12.9", "2026-10-01 13:10:00"),
                ("M5", "W3", "S1", "RCP-B", "THK", "5.0", "2026-10-01 13:20:00")]
#: (txn_seq, wafer, step, event_time)
PROCESS_EVENTS = [("P1", "W1", "S1", "2026-10-01 09:00:00"), ("P2", "W1", "S2", "2026-10-01 11:00:00"),
                  ("P3", "W2", "S1", "2026-10-01 10:00:00"), ("P4", "W3", "S1", "2026-10-01 13:00:00")]


def _id(entity_type, key, value):
    return explorer.entity_id(entity_type, {key: value})


WALKS = {
    "walk_fold_wafer": [("id", _id("wafer", "wafer", "W1")), ("positive", _id("wafer", "wafer", "W1")),
                        ("hops", "2")],
    "walk_fold_recipe_step": [("id", _id("recipe", "recipe", "RCP-A")), ("hops", "1"), ("direction", "incoming"),
                              ("since", "2026-10-01T00:00:00+09:00"), ("until", "2026-10-02T00:00:00+09:00"),
                              ("node_limit", "200"), ("collect", "measurement_event")],
    "walk_fold_process_lump": [("id", _id("process_event", "event", "P1")),
                               ("positive", _id("process_event", "event", "P1")),
                               ("positive", _id("process_event", "event", "P2")),
                               ("hops", "2"), ("direction", "both"), ("follow", "underwent"),
                               ("follow", "measured"), ("collect", "measurement_event")],
}


@pytest.fixture(name="client")
def fixture_client(pg_engine, tmp_path, monkeypatch):
    import database.database as database_module
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from database.database import get_db
    from ledger_api import ledger_subgraph

    config = tmp_path / "config"
    (config / "ontology").mkdir(parents=True)
    tables = _sample("table_config.json.sample")
    tables[METRO] = dict(tables[METRO], business_key="txn_seq")      # the sample declares no key for it
    (config / "table_config.json").write_text(json.dumps(tables), encoding="utf-8")
    (config / "ontology" / "ledger_config.json").write_text(json.dumps(declaration()), encoding="utf-8")
    monkeypatch.setattr(paths, "CONFIG_DIR", str(config))
    monkeypatch.setattr(database_module, "engine", pg_engine)
    ledger_subgraph.reset_declaration_cache()
    declared = {name: tables[name] for name in SOURCES}
    saved = dict(crud.TABLE_CONFIG)
    for name in declared:
        retire_dynamic_model(name)
    models.init_dynamic_models(declared)
    crud.TABLE_CONFIG.update(declared)

    def clean():
        with pg_engine.begin() as conn:
            for name in SOURCES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
                for side in ("cell_sources", "database_outbox", "audit_logs"):
                    conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t' % (PG_TEST_SCHEMA, side)),
                                 {"t": name})
        raw = pg_engine.raw_connection()
        try:
            schema.ensure_schema(raw)
            schema.ensure_partition(raw, datetime(2026, 10, 1, tzinfo=timezone.utc))
            with raw.cursor() as cursor:
                for source in SOURCES:
                    cursor.execute(f"DELETE FROM {schema.LEDGER_TABLE} WHERE source_who = %s", (source,))
                    cursor.execute(f"DELETE FROM {schema.ROW_REF_TABLE} WHERE source_who = %s", (source,))
            raw.commit()
        finally:
            raw.close()
        schema._ensured.clear()

    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in SOURCES:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    try:
        _write(session, METRO, [dict(zip(("txn_seq", "wafer_id", "step_seq", "rcp_id", "item_id", "value",
                                          "event_time"), row)) for row in MEASUREMENTS])
        _write(session, PROCESS, [dict(zip(("txn_seq", "wafer_id", "step_seq", "event_time"), row))
                                  for row in PROCESS_EVENTS])
        for source in SOURCES:
            backfill.run(pg_engine, source=source)
        app = FastAPI()
        app.include_router(trace_router.router)

        def scratch_db():
            yield session
        app.dependency_overrides[get_db] = scratch_db
        yield TestClient(app)
    finally:
        session.close()
        ledger_subgraph.reset_declaration_cache()
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in declared:
            retire_dynamic_model(name)


def _write(db, table, rows):
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="user", updated_by="demo") for row in rows]))
    db.commit()


def _walk(client, params):
    res = client.get("/api/ledger/subgraph", params=params)
    assert res.status_code == 200, res.text[:600]
    return res.json()


def _events(body):
    return {n["keys"]["event"]: n for n in body["nodes"] if n["type"] == "measurement_event"}


def test_a_recipe_walk_brings_the_measurements_other_wafers_made(client):
    wafer = _walk(client, WALKS["walk_fold_wafer"])
    recipe = _walk(client, WALKS["walk_fold_recipe_step"])
    lump = _walk(client, WALKS["walk_fold_process_lump"])

    # the start wafer's own; the static recipe keeps other wafers' out of this walk
    assert sorted(_events(wafer)) == ["M1", "M2"]
    assert "recipe" in {n["type"] for n in wafer["nodes"]}
    # one step from the recipe: every measurement that used it, its value and when it was measured
    events = _events(recipe)
    assert sorted(events) == ["M1", "M2", "M3", "M4"]
    for name, node in events.items():
        said = node["attributes_by_world"]["value"][0]
        assert node["attributes"]["value"] == said["value"] and said["occurred_at"], (name, node)
    # the lump's members, through their wafer, to that wafer's measurements
    assert sorted(_events(lump)) == ["M1", "M2"]

    if os.environ.get("WALK_FOLD_CAPTURE_DIR"):
        _capture(os.environ["WALK_FOLD_CAPTURE_DIR"], {"walk_fold_wafer": wafer, "walk_fold_recipe_step": recipe,
                                                        "walk_fold_process_lump": lump})


def test_the_recipe_step_is_cut_by_its_window_and_capped_by_its_limit(client):
    asked = [(k, v) for k, v in WALKS["walk_fold_recipe_step"] if k not in ("since", "node_limit")]
    cut = _walk(client, asked + [("since", "2026-10-01T10:30:00+09:00"), ("node_limit", "10")])

    assert sorted(_events(cut)) == ["M2", "M4"], "the window did not cut the earlier two"
    assert cut["truncated"]["interval_excluded"] == 2
    assert cut["limits"]["nodes"] == 10


def _capture(directory, bodies):
    import subprocess

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=SERVER_DIR, capture_output=True, text=True,
                            check=True).stdout.strip()
    for name, body in bodies.items():
        asked = WALKS[name]
        with io.open(os.path.join(directory, name + ".json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"_what": "REAL server output (repository route code, PostgreSQL scratch schema, the "
                                "declaration in %s). GET /api/ledger/subgraph?%s" % (
                                    os.path.basename(__file__),
                                    "&".join("%s=%s" % pair for pair in asked)),
                       "_server_at": commit, "_asked": asked, **body}, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
