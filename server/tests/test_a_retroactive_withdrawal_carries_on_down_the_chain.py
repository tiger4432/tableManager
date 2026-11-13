# -*- coding: utf-8 -*-
"""The reprocessing screen's withdrawal carries on down the chain (owner 11-10 «소급 ㄱ», lead): rule 1 copies X.val
into Y, rule 2 (allow_chain_trigger) copies Y.val into Z. Withdrawing rule 1's layer from Y through the withdraw
operation takes Z's value back too - before, Z kept «v1» and the queue said the rule did not opt in. Any other
retroactive write still wakes nothing (owner 09-26): the same withdrawal outside the operation leaves Z as it was."""
import asyncio
import json

import pytest

import event_constants
from admin import retroactive
from chain import cell_layer
from chain import ingestion_worker as worker
from database import crud, lines, models, schemas
from database.context import channel, outbox_mode
from tests.test_a_join_take_can_gather_every_row_of_a_key import _NoClose, _no_post

X, Y, Z = "rw_x", "rw_y", "rw_z"
TABLES = {t: {"business_key": "k", "column_types": {"k": "string", "val": "string"}, "display_columns": ["k", "val"]}
          for t in (X, Y, Z)}


def _join(name, on, into, chain_trigger):
    rule = {"name": name, "enabled": True, "on": {"table": on}, "into": {"table": into},
            "derive": {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}],
                                                "take": [{"from": "val", "into": "val"}]}}}
    if chain_trigger:
        rule["allow_chain_trigger"] = True
    return rule


RULES = [_join("x_to_y", X, Y, False), _join("y_to_z", Y, Z, True)]


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


def _vals(db, table):
    db.expire_all()
    return {r.k: r.val for r in db.query(models.DYNAMIC_TABLES[table])}


def _rule_1s_layer(db):
    _put(db, Y, [{"k": "A"}]); _put(db, Z, [{"k": "A"}]); _drain(db)
    _put(db, X, [{"k": "A", "val": "v1"}]); _drain(db)
    assert (_vals(db, Y), _vals(db, Z)) == ({"A": "v1"}, {"A": "v1"})
    row_ids = [r.row_id for r in db.query(models.DYNAMIC_TABLES[Y])]
    ((source,),) = [list(cell) for cell in lines.layers(db, Y, row_ids, columns=["val"]).values()]
    return source


def test_the_withdraw_operation_carries_on_to_the_next_chain(db):
    layer = _rule_1s_layer(db)
    with channel(event_constants.CHANNEL_RETROACTIVE):
        retroactive._run_withdraw(db, {"table": Y, "source": layer}, log=lambda m: None)
        db.commit()
    _drain(db)
    assert (_vals(db, Y), _vals(db, Z)) == ({"A": None}, {"A": None})


def test_any_other_retroactive_write_still_wakes_nothing(db):
    layer = _rule_1s_layer(db)
    with channel(event_constants.CHANNEL_RETROACTIVE):
        cell_layer.withdraw_source(db, Y, layer, apply=True)
        db.commit()
    _drain(db)
    assert (_vals(db, Y), _vals(db, Z)) == ({"A": None}, {"A": "v1"})
