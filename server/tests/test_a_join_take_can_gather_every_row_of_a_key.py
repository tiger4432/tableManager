# -*- coding: utf-8 -*-
"""Owner 10-20 「a 테이블에서 b 테이블로 집계해서 조인」 · 「uniqueconcat 해서 붙이는 게 필요」 (lead 0eb7ad0c6): a join's
`take` item saying `fn` (count · min · max · unique_concat) gathers EVERY value-table row of a key into the left row's
cell, by the gap fill's calculation. No origin on that cell and a blank one withdrawn - so a row deleted or moved off
the key is recounted, never taken back with the rest. The chain here is its batch body (`drain_events`) over the
rules the loader stands from the declaration."""
import asyncio
import json
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import chain_bindings                                                 # noqa: E402
import event_constants                                                # noqa: E402
import mapper_sdk                                                     # noqa: E402
import paths                                                          # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from chain import rule_shape                                          # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from database.context import channel, outbox_mode                     # noqa: E402
from database.database import Base                                    # noqa: E402
from utils import heartbeat                                           # noqa: E402

TABLES = {"ja_src": {"business_key": "rid", "composite_key_source": ["rid"],
                     "column_types": {"rid": "string", "k": "string", "v": "string", "n": "number"},
                     "display_columns": ["rid", "k", "v", "n"]},
          "ja_tgt": {"business_key": "k", "composite_key_source": ["k"],
                     "column_types": {"k": "string", "vs": "string", "cnt": "number", "nmin": "number",
                                      "nmax": "number", "vone": "string"},
                     "display_columns": ["k", "vs", "cnt", "nmin", "nmax", "vone"]}}
GATHER = [{"from": "v", "into": "vs", "fn": "unique_concat"}, {"from": "rid", "into": "cnt", "fn": "count"},
          {"from": "n", "into": "nmin", "fn": "min"}, {"from": "n", "into": "nmax", "fn": "max"}]


def _declaration(take, key=None):
    out = {"name": "ja", "on": {"table": "ja_src"}, "into": {"table": "ja_tgt"},
           "derive": {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}], "take": take}}}
    if key:
        out["key"] = key
    return out


class _NoClose:
    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


async def _no_post(_endpoint, _payload):
    return True


@pytest.fixture(name="db")
def fixture_db(tmp_path, monkeypatch):
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
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _rules(tmp_path, monkeypatch, take):
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [_declaration(take)]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    rules = [r for r in worker.load_chain_rules() if str(r.get("name") or "").startswith("ja")]
    monkeypatch.setattr(worker, "loaded_chain_rules", lambda: list(rules))
    return rules


def _drain(db, rules):
    for _ in range(40):
        pending = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            return
        asyncio.run(worker.drain_events(db, pending, rules, None))
    raise AssertionError("the chain did not settle")


def _put(db, table, rows):
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_PER_ROW):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="ja") for row in rows]))
        db.commit()


def _delete(db, rid):
    row_id = db.query(models.DYNAMIC_TABLES["ja_src"]).filter_by(rid=rid).one().row_id
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_PER_ROW):
        crud.delete_rows_batch(db, "ja_src", [row_id], "ja")
        db.commit()


def _cells(db, k, columns=("vs", "cnt", "nmin", "nmax")):
    db.expire_all()
    row = db.query(models.DYNAMIC_TABLES["ja_tgt"]).filter_by(k=k).one()
    return tuple(getattr(row, column) for column in columns)


def _origins(db, columns):
    """The origins on the layers this join wrote in `columns` of the target table - a gathered cell carries none."""
    return {layer.origin_row_id for layer in db.query(models.CellSource).filter(
        models.CellSource.table_name == "ja_tgt", models.CellSource.column_name.in_(list(columns)))}


def test_a_key_s_rows_are_gathered_and_recounted_as_they_come_leave_and_move(db, tmp_path, monkeypatch):
    rules = _rules(tmp_path, monkeypatch, GATHER)
    value_side = [r for r in rules if r.get("trigger_table") == "ja_src"]
    assert [r.get(chain_bindings.ALLOW_DELETE_TRIGGER_KEY) for r in value_side] == [True]
    assert [r.get(chain_bindings.ALLOW_DELETE_TRIGGER_KEY) for r in rules if r.get("trigger_table") == "ja_tgt"] \
        == [None]
    _put(db, "ja_tgt", [{"k": "k1"}, {"k": "k2"}])
    _put(db, "ja_src", [{"rid": "r1", "k": "k1", "v": "x", "n": 3}, {"rid": "r2", "k": "k1", "v": "y", "n": 1},
                        {"rid": "r3", "k": "k1", "v": "x", "n": 2}])
    _drain(db, rules)
    assert _cells(db, "k1") == ("x, y", 3, 1, 3)
    assert _origins(db, ("vs", "cnt", "nmin", "nmax")) == {None}
    _put(db, "ja_src", [{"rid": "r4", "k": "k1", "v": "z", "n": 5}])
    _drain(db, rules)
    assert _cells(db, "k1") == ("x, y, z", 4, 1, 5)
    # the key's first row goes and its value stays («x, y, z» again - the write finds the cell already so)
    _delete(db, "r1")
    _drain(db, rules)
    assert _cells(db, "k1") == ("x, y, z", 3, 1, 5)
    assert _origins(db, ("vs", "cnt", "nmin", "nmax")) == {None}
    # a row moves to another key: both keys are recounted
    _put(db, "ja_src", [{"rid": "r2", "k": "k2"}])
    _drain(db, rules)
    assert _cells(db, "k1") == ("x, z", 2, 2, 5)
    assert _cells(db, "k2") == ("y", 1, 1, 1)
    assert _origins(db, ("vs", "cnt", "nmin", "nmax")) == {None}
    # the last row of a key goes: what the join wrote there is taken back, count included - not 0
    _delete(db, "r2")
    _drain(db, rules)
    assert _cells(db, "k2") == (None, None, None, None)


def test_a_target_row_that_arrives_late_gets_its_key_s_rows_gathered(db, tmp_path, monkeypatch):
    rules = _rules(tmp_path, monkeypatch, GATHER)
    _put(db, "ja_src", [{"rid": "r1", "k": "k9", "v": "b", "n": 7}, {"rid": "r2", "k": "k9", "v": "a", "n": 4}])
    _drain(db, rules)
    _put(db, "ja_tgt", [{"k": "k9"}])
    _drain(db, rules)
    assert _cells(db, "k9") == ("a, b", 2, 4, 7)


def test_a_take_without_fn_still_refuses_two_rows_beside_a_gathering_one(db, tmp_path, monkeypatch):
    rules = _rules(tmp_path, monkeypatch, [{"from": "v", "into": "vs", "fn": "unique_concat"},
                                           {"from": "v", "into": "vone"}])
    _put(db, "ja_tgt", [{"k": "k1"}, {"k": "k2"}])
    _put(db, "ja_src", [{"rid": "r1", "k": "k1", "v": "x"}, {"rid": "r2", "k": "k1", "v": "y"},
                        {"rid": "r3", "k": "k2", "v": "w"}])
    _drain(db, rules)
    assert _cells(db, "k1", ("vs", "vone")) == ("x, y", None)
    assert _cells(db, "k2", ("vs", "vone")) == ("w", "w")
    r3 = db.query(models.DYNAMIC_TABLES["ja_src"]).filter_by(rid="r3").one().row_id
    assert _origins(db, ("vs",)) == {None} and _origins(db, ("vone",)) == {r3}


@pytest.mark.parametrize("take,key,words", [
    (GATHER[:1], {"unique": True}, "key.unique and take fn (vs) cannot stand together"),
    ([{"from": "v", "into": "vs", "fn": "sum"}], None, "take 'vs' fn 'sum' - one of count · min · max · unique_concat"),
    ([{"from": "v", "into": "vs", "fn": "min"}], None, "take 'vs' fn min over ja_src.v, a string column"),
])
def test_a_gathering_take_that_cannot_stand_is_refused_by_name(db, take, key, words):
    _rules_, refusal, _notes = rule_shape.expand_declaration(_declaration(take, key))
    assert refusal is not None and words in refusal, refusal
