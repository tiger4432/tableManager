# -*- coding: utf-8 -*-
"""총괄 363db7dfa · 1dd4091a6 — end to end, on PostgreSQL, on the shipped sample: a process row is
said about the core wafer while its step is unlisted; a person lists the step as DT in
step_phase, the join copies DT onto the row, the ledger follows that edit, and the row's atom
moves to the dtwafer - the old one gone, not superseded. Emptying the step's mat_type moves it
back; deleting the step_phase row does not reach the rows it filled.

Every seat is the product's: `crud` writes, the chain's own transaction-group body (which is
also where the ledger follow-up is queued), `followup.drain_once` with the sample setup.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import MetaData, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
import event_constants                                              # noqa: E402
import mapper_sdk                                                   # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from chain import rule_shape                                        # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.context import channel                                # noqa: E402
from ledger import followup, schema                                 # noqa: E402
from ledger.implementations import (role_mapper_registry,           # noqa: E402
                                    trusted_implementations)
from ledger.setup import LedgerSetup                                # noqa: E402
from ledger.setup_bundle import (load_physical_catalog,             # noqa: E402
                                 require_ready_bundle, validate_bundle)
from ledger.setup_registry import compile_setup_snapshot            # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

pytestmark = pytest.mark.pg
SAMPLE = os.path.join(SERVER_DIR, "config", "sample")
TABLES = ("wafer_process", "step_phase")
SOURCE = "wafer_process_recipe"
JOIN = "step_phase_to_wafer_process"
EVENT_TIME = "2026-09-30 10:00:00"


def _sample(name):
    with open(os.path.join(SAMPLE, name), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch):
    mapper_sdk.discover()
    declared = {name: _sample("table_config.json.sample")[name] for name in TABLES}
    saved = dict(crud.TABLE_CONFIG)
    for name in TABLES:
        retire_dynamic_model(name)
    models.init_dynamic_models(declared)
    crud.TABLE_CONFIG.update(declared)

    def clean():
        with pg_engine.begin() as conn:
            for name in TABLES:
                # ⚠️ QUALIFIED: an unqualified name falls through the search path to `public`
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
                conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": name})
                conn.execute(text("DELETE FROM database_outbox WHERE table_name = :t"), {"t": name})
        raw = pg_engine.raw_connection()
        try:
            schema.ensure_schema(raw)
            schema.ensure_partition(raw, datetime(2026, 9, 30, 1, 0, tzinfo=timezone.utc))
            with raw.cursor() as cursor:
                cursor.execute(f"DELETE FROM {schema.LEDGER_TABLE} WHERE source_who = %s", (SOURCE,))
                cursor.execute(f"DELETE FROM {schema.ROW_REF_TABLE} WHERE source_who = %s", (SOURCE,))
            raw.commit()
        finally:
            raw.close()

    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in TABLES:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    monkeypatch.setattr(worker, "_READ_BY_SOURCE_NAME", set())
    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    bundle = require_ready_bundle(validate_bundle(_sample("ledger_config.json.sample"),
                                                  catalog=catalog))
    setup = LedgerSetup(
        config_root=Path(SAMPLE), bundle=bundle,
        snapshot=compile_setup_snapshot(bundle, trusted_implementations(), catalog=catalog),
        mappers=role_mapper_registry(), catalog=catalog)
    join = next(r for r in _sample("chain_rules.json.sample")["rules"] if r.get("name") == JOIN)
    rules = rule_shape.expand_declaration(join, crud.TABLE_CONFIG)[0]
    followup.reset()
    try:
        yield {"db": session, "engine": pg_engine, "setup": setup, "rules": rules}
    finally:
        session.close()
        followup.reset()
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in TABLES:
            retire_dynamic_model(name)


def _write(world, table, rows, layer="user"):
    db = world["db"]
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name=layer, updated_by="probe")
            for row in rows]))
        db.commit()


def _settle(world, rounds=40):
    """The chain's transaction-group body until nothing is pending, then the ledger follow-up
    until its queue is empty - the two loops the chain worker runs."""
    db = world["db"]
    for _ in range(rounds):
        pending = (db.query(models.DatabaseOutbox)
                   .filter(models.DatabaseOutbox.processed_chain.is_(False),
                           models.DatabaseOutbox.table_name.in_(list(TABLES)))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            break
        groups = {}
        for event in pending:
            groups.setdefault(get_payload_dict(event).get("transaction_id"), []).append(event)
        for tx_id, events in groups.items():
            ok, error, _ = worker._process_chain_transaction_group_sync(
                tx_id, events, db, world["rules"])
            assert ok, error
            for event in events:
                event_constants.mark_processed(event, "SUCCESS")
            db.commit()
    else:
        raise AssertionError("the chain did not settle")
    while followup.queue_depth():
        done = followup.drain_once(world["engine"], world["setup"])
        assert not any("error" in (s or {}) for s in (done or {}).get("sources", {}).values()), done


def _said(world):
    with world["engine"].connect() as conn:
        return sorted(tuple(r) for r in conn.execute(text(
            f"SELECT subject_type, subject_keys->>'wafer' FROM {schema.LEDGER_TABLE} "
            "WHERE source_who = :s"), {"s": SOURCE}))


def _mat_type(world):
    with world["engine"].connect() as conn:
        return conn.execute(text('SELECT mat_type FROM "wafer_process" WHERE proc_id = :p'),
                            {"p": "P1"}).scalar()


def test_a_step_listed_as_dt_moves_the_rows_atom_and_emptying_it_moves_it_back(world):
    _write(world, "wafer_process", [{"proc_id": "P1", "wafer_id": "W1", "step": "S9",
                                     "recipe_id": "RCP-1", "eventtime": EVENT_TIME}])
    _settle(world)
    assert _said(world) == [("wafer", "W1")]

    _write(world, "step_phase", [{"step": "S9", "mat_type": "DT"}])
    _settle(world)
    assert _mat_type(world) == "DT"
    assert _said(world) == [("dtwafer", "W1")]          # the core wafer's atom is gone

    _write(world, "step_phase", [{"step": "S9", "mat_type": ""}])
    _settle(world)
    assert _mat_type(world) in (None, "")
    assert _said(world) == [("wafer", "W1")]


def test_deleting_the_step_phase_row_does_not_reach_the_rows_it_filled(world):
    _write(world, "wafer_process", [{"proc_id": "P1", "wafer_id": "W1", "step": "S9",
                                     "recipe_id": "RCP-1", "eventtime": EVENT_TIME}])
    _write(world, "step_phase", [{"step": "S9", "mat_type": "DT"}])
    _settle(world)
    assert _mat_type(world) == "DT"
    db = world["db"]
    row_id = db.execute(text('SELECT row_id FROM "step_phase" WHERE step = :s'), {"s": "S9"}).scalar()
    crud.delete_rows_batch(db, "step_phase", [row_id], "probe")
    db.commit()
    _settle(world)
    assert _mat_type(world) == "DT"
    assert _said(world) == [("dtwafer", "W1")]
