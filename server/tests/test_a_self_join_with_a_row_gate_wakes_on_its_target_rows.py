"""A join of one table onto itself whose source side has a row gate wakes on its target rows too (lead 11-10 ㄱ,
owner «date 가 복사되어야 함»): an unpivot copies the `date` item's value to the other items of its batch, whichever
row came first. Without a gate one table is both sides and one rule is enough (the control)."""
import asyncio
import json

import pytest

import event_constants
from chain import ingestion_worker as worker
from chain import rule_shape
from database import crud, models, schemas
from database.context import channel, outbox_mode
from tests.test_a_join_take_can_gather_every_row_of_a_key import _NoClose, _no_post

T = "uv"
TABLES = {T: {"business_key": "rk", "composite_key_source": ["batch", "item_id"],
              "column_types": {"rk": "string", "batch": "string", "item_id": "string", "value": "string",
                               "date": "string"},
              "display_columns": ["batch", "item_id", "value", "date"]}}
RULE = {"name": "date_from_item", "enabled": True,
        "on": {"table": T, "require": [{"item_id": ["date"]}]}, "into": {"table": T},
        "derive": {"kind": "join", "join": {"on": [{"left": "batch", "right": "batch"}],
                                            "take": [{"from": "value", "into": "date"}]}}}


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
    path.write_text(json.dumps({"rules": [RULE]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    worker.forget_loaded_chain_rules()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.pop(T, None)
        worker.forget_loaded_chain_rules()


def _put(db, rows):
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_PER_ROW):
        crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="f.csv", updated_by="w") for row in rows]))
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


def _dates(db):
    db.expire_all()
    return {(r.batch, r.item_id): r.date for r in db.query(models.DYNAMIC_TABLES[T]).order_by("batch", "item_id")}



def _chain_writes(db):
    """The chain's row lines in the audit log (one per row it wrote)."""
    return db.query(models.AuditLog).filter(models.AuditLog.table_name == T,
                                            models.AuditLog.source_name.like("chain_ingestion%")).count()


def test_the_companion_stands_ungated_and_the_gateless_self_join_stands_none(db):
    stood, refusal, _ = rule_shape.expand_declaration(RULE, crud.TABLE_CONFIG)
    gates = {rule["name"]: (rule.get("require"), (rule.get("params") or {}).get("require")) for rule in stood}
    assert refusal is None
    assert gates == {"date_from_item": ([{"item_id": ["date"]}], [{"item_id": ["date"]}]),
                     "date_from_item:target": (None, [{"item_id": ["date"]}])}
    gateless = dict(RULE, on={"table": T})
    assert [rule["name"] for rule in rule_shape.expand_declaration(gateless, crud.TABLE_CONFIG)[0]] == ["date_from_item"]


def test_every_item_of_a_batch_gets_its_date_whichever_row_came_first(db):
    # ① the date row first, the other items after - the case no rule woke for
    _put(db, [{"batch": "B1", "item_id": "date", "value": "3월 5일"}]); _drain(db)
    _put(db, [{"batch": "B1", "item_id": "temp", "value": "21"}, {"batch": "B1", "item_id": "rh", "value": "40"}])
    _drain(db)
    assert _dates(db) == {("B1", "date"): "3월 5일", ("B1", "rh"): "3월 5일", ("B1", "temp"): "3월 5일"}
    # ② the other items first, the date row after
    _put(db, [{"batch": "B2", "item_id": "temp", "value": "22"}, {"batch": "B2", "item_id": "rh", "value": "41"}])
    _drain(db)
    _put(db, [{"batch": "B2", "item_id": "date", "value": "11월 9일"}]); _drain(db)
    # ③ the date value changes: both halves wake on the date row and give the same answer - three rows written, once
    before = _chain_writes(db)
    _put(db, [{"batch": "B1", "item_id": "date", "value": "12월 25일"}]); _drain(db)
    assert _chain_writes(db) - before == 3
    assert _dates(db) == {("B1", "date"): "12월 25일", ("B1", "rh"): "12월 25일", ("B1", "temp"): "12월 25일",
                          ("B2", "date"): "11월 9일", ("B2", "rh"): "11월 9일", ("B2", "temp"): "11월 9일"}
    # a row whose answer it already holds: woken, nothing written
    before = _chain_writes(db)
    _put(db, [{"batch": "B1", "item_id": "temp", "value": "23", "date": "12월 25일"}]); _drain(db)
    _put(db, [{"batch": "B1", "item_id": "p", "value": "1"}]); _drain(db)
    assert _chain_writes(db) - before == 1
