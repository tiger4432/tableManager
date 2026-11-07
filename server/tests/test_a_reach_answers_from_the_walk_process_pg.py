# -*- coding: utf-8 -*-
"""Lead 11-07: reach runs in a walk pool process (`in_pool`), and that process reads a table through its model - so the
pool process builds the tables' models as the server's start does (`process_pool._serve`). Before, a pool process had
none: every table read as «a view - its rows have no row_id» and reach answered 0 rows on the box (A, 8085).

The request goes API -> a real walk process -> reach, on a throwaway PostgreSQL database and a data root on disk - the
process reads the server's engine and data root, never the test's (`tests/support/pools.py`).

  a table    rows > 0 (the wafer's process rows), both engines
  a view     still left out by name
  a reload   a table added to table_config.json is read by the process `recycle` starts after it - not by the old one
"""
import copy
import json
import os
import shutil
import sys
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                              # noqa: E402
import paths                                                        # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.context import channel                                # noqa: E402
from ledger import backfill, schema                                 # noqa: E402
from runtime import process_pool                                    # noqa: E402
from support.isolated_pg import RUN_TOKEN, declared_as_test_database, resolve_url  # noqa: E402
from conftest import retire_dynamic_model                            # noqa: E402
from test_a_reach_is_the_rows_the_walk_read_pg import PROCESSES, SEATS, WAFERS  # noqa: E402
from test_ledger_worlds_are_independent_and_meet_in_a_walk import CHANGED, KEPT, SAMPLE, _only, _sample  # noqa: E402

pytestmark = pytest.mark.pg
TABLES = ("wafer_process", "lot_slot_wafer")
ADDED = "reach_added"


def _write(engine, table, rows):
    with Session(bind=engine) as db, channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="user", updated_by="probe") for row in rows]))
        db.commit()


@pytest.fixture(name="box")
def fixture_box(tmp_path, monkeypatch):
    import database.database as database_module
    import notation_norm

    url, reason = resolve_url()
    if url is None:
        pytest.skip(reason)
    name = "assy_reach_%s" % "".join(ch for ch in RUN_TOKEN.lower() if ch.isalnum())[:20]
    maintenance = make_url(url).set(database="postgres").render_as_string(hide_password=False)
    throwaway = make_url(url).set(database=name).render_as_string(hide_password=False)

    def ask(sql):
        with declared_as_test_database(maintenance), create_engine(
                maintenance, poolclass=NullPool, isolation_level="AUTOCOMMIT").connect() as conn:
            conn.execute(text(sql))

    config = tmp_path / "config"
    (config / "ontology").mkdir(parents=True)
    shutil.copy(os.path.join(SAMPLE, "table_config.json.sample"), config / "table_config.json")
    (config / "ontology" / "ledger_config.json").write_text(json.dumps(_only(CHANGED, KEPT)), encoding="utf-8")
    monkeypatch.setattr(paths, "CONFIG_DIR", str(config))
    # the walk process's: the server's data root and engine are these (inherited at its start)
    monkeypatch.setenv("ASSY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", throwaway)
    monkeypatch.setenv("ASSY_TEST_DATABASE_URL", throwaway)
    monkeypatch.setattr(process_pool, "_settings", lambda: {"walk_processes": 1, "walk_seconds_max": 300})

    sample = _sample("table_config.json.sample")
    declared = {table: sample[table] for table in (*TABLES, schema.ATOM_ROWS_VIEW)}
    saved = dict(crud.TABLE_CONFIG)
    ask('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % name)
    ask('CREATE DATABASE "%s"' % name)
    engine = create_engine(throwaway, poolclass=NullPool)
    try:
        for table in declared:
            retire_dynamic_model(table)
        models.init_dynamic_models(declared)
        crud.TABLE_CONFIG.update(declared)
        monkeypatch.setattr(database_module, "engine", engine)
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        models.Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.connection.cursor().execute(notation_norm.key_instant_sql() + notation_norm.key_number_sql())
        raw = engine.raw_connection()
        try:
            schema.ensure_schema(raw)
            schema.ensure_partition(raw, datetime(2026, 9, 30, 1, 0, tzinfo=timezone.utc))
            raw.commit()
        finally:
            raw.close()
        schema._ensured.clear()
        _write(engine, "wafer_process", PROCESSES)
        _write(engine, "lot_slot_wafer", SEATS)
        for source in (CHANGED, KEPT):
            backfill.run(engine, source=source)
        yield {"engine": engine, "config": config, "sample": sample}
    finally:
        process_pool._drain(process_pool.WALK)
        engine.dispose()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for table in (*declared, ADDED):
            retire_dynamic_model(table)
        ask('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % name)


def _client(box):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from database.database import get_db
    from ledger import trace_router

    app = FastAPI()
    app.include_router(trace_router.router)

    def db():
        with Session(bind=box["engine"]) as session:
            yield session
    app.dependency_overrides[get_db] = db
    return TestClient(app)


def _reach(client, engine, **asked):
    answer = client.post("/api/ledger/subgraph", params={"engine": engine}, json={"reach": {**WAFERS, **asked}})
    assert answer.status_code == 200, answer.text
    return answer.json()


def _walk_processes():
    return {worker[0].pid for worker in process_pool.WALK.idle}


def test_a_table_is_reached_from_the_walk_process_and_a_view_is_left_out(box):
    with box["engine"].connect() as conn:
        rows = {row for (row,) in conn.execute(text("SELECT row_id FROM wafer_process WHERE wafer_id = 'W1'"))}
    assert len(rows) == 2, "canary: the board has W1's two process rows"
    client = _client(box)
    for engine in ("stored", "virtual"):
        said = _reach(client, engine, values=["W1"])
        assert set(said["rows"]) == rows and not [item for item in said["left_out"] if "view" in item["why"]], said
        assert _walk_processes() - {os.getpid()}, "the answer came from a walk process"
        said = _reach(client, engine, values=["W1"], to=schema.ATOM_ROWS_VIEW)
        assert said["rows"] == [] and said["left_out"] == [
            {"why": "a view - its rows have no row_id", "table": schema.ATOM_ROWS_VIEW, "sources": []}], said


def test_a_table_added_is_read_by_the_walk_process_started_after_the_reload(box):
    client = _client(box)
    added = copy.deepcopy(box["sample"]["lot_slot_wafer"])
    _reach(client, "stored", values=["W1"])
    first = _walk_processes()
    assert first, "canary: a walk process is up"
    models.init_dynamic_models({ADDED: added})                     # the table in the database (this process's DDL)
    models.Base.metadata.tables[ADDED].create(box["engine"])
    _write(box["engine"], ADDED, SEATS[:1])
    said = _reach(client, "stored", table=ADDED, values=["W1"])
    assert {"why": "a view - its rows have no row_id", "table": ADDED, "sources": []} in said["left_out"], \
        "the process started before the table was declared does not know it"
    path = box["config"] / "table_config.json"
    declared = json.loads(path.read_text(encoding="utf-8"))
    declared[ADDED] = added
    path.write_text(json.dumps(declared), encoding="utf-8")
    process_pool._warmed[0] = True                                  # recycle runs where the pools were warmed
    try:
        process_pool.recycle()                                      # what a table config reload calls
    finally:
        process_pool._warmed[0] = False
    said = _reach(client, "stored", table=ADDED, values=["W1"])
    assert not [item for item in said["left_out"] if "view" in item["why"]], said
    assert _walk_processes() and not _walk_processes() & first, "a new walk process answered"
