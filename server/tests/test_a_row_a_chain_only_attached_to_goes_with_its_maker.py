# -*- coding: utf-8 -*-
"""The owner's official master (lead 11-10): chain 1 copies a_official's agreed rows into the master and makes them;
chain 2 only attaches b_official's value onto them. When chain 1 takes its row back - agree leaves, or the a row is
deleted - the master row goes with chain 2's layer, and chain 2 hears the DELETE. Before, chain 2's valued layer kept
the row alive as («K1», no value, «b1»). A person's part or another writer that made the row still keeps it."""
import asyncio
import json

import pytest

import event_constants
from chain import cell_layer
from chain import ingestion_worker as worker
from database import crud, models, schemas
from database.context import channel, outbox_mode
from tests.test_a_join_take_can_gather_every_row_of_a_key import _NoClose, _no_post

import mappers.hold_copy  # noqa: F401 - registers

A, MASTER, B = "ms_a", "ms_master", "ms_b"
TABLES = {A: {"business_key": "log_id", "composite_key_source": ["log_id"],
              "column_types": {"log_id": "string", "k": "string", "val": "string", "status": "string"},
              "display_columns": ["log_id", "k", "val", "status"]},
          MASTER: {"composite_key_source": ["k"],
                   "column_types": {"k": "string", "val": "string", "hold": "string", "bval": "string"},
                   "display_columns": ["k", "val", "hold", "bval"]},
          B: {"business_key": "k", "column_types": {"k": "string", "bval": "string"}, "display_columns": ["k", "bval"]}}
RULES = [{"name": "a_to_master", "enabled": True, "trigger_table": A, "target_table": MASTER,
          "mapper": "copy_rows_with_hold", "require": [{"status": ["agree"]}],
          "params": {"key_columns": ["k"], "columns": ["val"], "hold_column": "hold"}},
         {"name": "b_onto_master", "enabled": True, "on": {"table": B}, "into": {"table": MASTER},
          "allow_chain_trigger": True,
          "derive": {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}],
                                              "take": [{"from": "bval", "into": "bval"}]}}}]
X, Y = A, MASTER


@pytest.fixture(name="db")
def fixture_db(tmp_path, monkeypatch):
    import mapper_sdk
    import paths
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from database.database import Base
    from utils import heartbeat

    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path / "beats"))
    monkeypatch.setattr(heartbeat, "heartbeat_path", lambda name: str(tmp_path / "beats" / (name + ".json")))
    monkeypatch.setattr(worker, "post_event_async", _no_post)
    mapper_sdk.discover()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    monkeypatch.setattr("database.database.SessionLocal", lambda: _NoClose(session))
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": RULES}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    worker.forget_loaded_chain_rules()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for t in TABLES:
            crud.TABLE_CONFIG.pop(t, None)
        worker.forget_loaded_chain_rules()


def _put(db, table, rows, source="f.csv"):
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_PER_ROW):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name=source, updated_by="w") for row in rows]))
        db.commit()


def _drain(db):
    rules = worker.load_chain_rules()
    for _ in range(20):
        pending = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            return
        asyncio.run(worker.drain_events(db, pending, rules, None))
    raise AssertionError("did not settle")


def _master(db):
    db.expire_all()
    return [(r.k, r.val, r.bval) for r in db.query(models.DYNAMIC_TABLES[MASTER])]


def _last_event(db):
    return db.query(models.DatabaseOutbox.id).order_by(models.DatabaseOutbox.id.desc()).first()[0]


def _deletes_heard(db, after):
    """The master's DELETE events since `after`, each with chain 2's refusal (None = it takes the event)."""
    rule = next(r for r in worker.load_chain_rules() if r.get("trigger_table") == MASTER)
    return [worker.fire_refusal(rule, e) for e in db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.id > after, models.DatabaseOutbox.table_name == MASTER,
        models.DatabaseOutbox.event_type == "DELETE")]


def _official(db, made_by=None):
    _put(db, B, [{"k": "K1", "bval": "b1"}]); _drain(db)
    if made_by:
        made_by(db)
    _put(db, A, [{"log_id": "L1", "k": "K1", "val": "a1", "status": "agree"}]); _drain(db)
    assert _master(db) == [("K1", "a1", "b1")]
    return _last_event(db)


def _agree_leaves(db):
    _put(db, A, [{"log_id": "L1", "k": "K1", "val": "a1", "status": "hold"}]); _drain(db)


def _a_row_deleted(db):
    with channel(event_constants.CHANNEL_API):
        crud.delete_rows_batch(db, A, [db.query(models.DYNAMIC_TABLES[A]).one().row_id], "user")
        db.commit()
    _drain(db)


@pytest.mark.parametrize("take_back", [_agree_leaves, _a_row_deleted])
def test_the_row_chain_1_made_goes_with_chain_2s_value(db, take_back):
    after = _official(db)
    take_back(db)
    assert _master(db) == []
    assert _deletes_heard(db, after) == [None]
    assert not db.query(models.CellSource).filter_by(table_name=MASTER).count()


def _a_person_wrote(db):
    _put(db, MASTER, [{"k": "K1", "hold": "mine"}], source=crud.USER_SOURCE)


def _a_file_made_it(db):
    _put(db, MASTER, [{"k": "K1"}], source="master.csv")


@pytest.mark.parametrize("made_by, left", [(_a_person_wrote, ("K1", None, "b1")),
                                           (_a_file_made_it, ("K1", None, "b1"))])
@pytest.mark.parametrize("take_back", [_agree_leaves, _a_row_deleted])
def test_a_person_or_another_maker_keeps_it(db, made_by, left, take_back):
    after = _official(db, made_by)
    take_back(db)
    assert _master(db) == [left]
    assert _deletes_heard(db, after) == []


def test_what_keeps_the_row_names_its_maker_not_the_attacher(db):
    _official(db)
    row_id = db.query(models.DYNAMIC_TABLES[MASTER]).one().row_id
    keepers = cell_layer.person_rows(db, MASTER, [row_id])[row_id]
    assert keepers and all("a_to_master" in name for name in keepers)
    # the rule taking it back keeps nothing of its own
    assert cell_layer.person_rows(db, MASTER, [row_id], own={row_id: {"a_to_master"}}) == {}
