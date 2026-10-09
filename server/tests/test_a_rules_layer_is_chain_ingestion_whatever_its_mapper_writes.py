# -*- coding: utf-8 -*-
"""총괄 09f3cd289 ① — a rule's write goes under chain_ingestion whatever its mapper wrote (소유자 10-09
「모든 맵퍼의 소스네임은 chain_ingestion 에서 못 바꾸게 해야 할 듯」 · 「체인 출력이 예전 체인에 덮여 있네」).

  ① the name a mapper wrote -> chain_ingestion (a row layer keeps its bracket); @mapper(source_name=) told once
  ② an old chain_ingestion layer, and a mapper that writes 'dt_inventory': the new value shows
  ④ a person's layer still wins
  ⑤ auto-confirm's two names and the enrichment backfill's stay as written
"""
import json
import logging
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
import mapper_sdk                                                   # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from chain import rule_order                                        # noqa: E402
from chain.enrichment import backfill, candidates                   # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.database import Base                                  # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

T = "ln_inv"
TABLES = {T: {"business_key": "k", "composite_key_source": ["k"],
              "column_types": {c: "string" for c in ("k", "a", "x")}, "display_columns": ["k", "a", "x"]}}
NAMED = {"name": None}          # the source_name the mapper writes this time; None = the item says none


def _body(db, payload, rule=None):
    out = []
    for one in (payload if isinstance(payload, list) else [payload]):
        data = {k: (v or {}).get("value") for k, v in (one.get("data") or {}).items()}
        item = {"updates": {"k": data["k"], "x": "%s!" % data.get("a")}, "origin_row_id": one["row_id"]}
        if NAMED["name"] is not None:
            item["source_name"] = NAMED["name"]
        out.append(item)
    return {"updates": out}


RULE = {"name": "ln_rule", "mapper": "ln_mapper", "enabled": True, "is_batch": True, "trigger_table": T,
        "target_table": T, "trigger_columns": ["a"]}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    mapper_sdk.register("ln_mapper", _body)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.pop(T, None)
        mapper_sdk.MAPPER_REGISTRY.pop("ln_mapper", None)
        mapper_sdk.MAPPER_PARAMS.pop("ln_mapper", None)


def _write(db, source_name, **cells):
    from database.context import channel, outbox_mode

    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            updates=dict(cells), source_name=source_name, updated_by="ln")]))
    db.commit()


def _drain(db):
    for _ in range(4):
        pending = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            return
        groups = {}
        for e in pending:
            groups.setdefault(get_payload_dict(e).get("transaction_id"), []).append(e)
        for tx_id, events in groups.items():
            ok, error, _ = worker._process_chain_transaction_group_sync(tx_id, events, db, [dict(RULE)])
            assert ok, error
            for e in events:
                event_constants.mark_processed(e, "SUCCESS")
            db.commit()
    raise AssertionError("the chain did not settle")


def _x(db, k="K1"):
    db.expire_all()
    row = db.query(models.DYNAMIC_TABLES[T]).filter_by(business_key_val=k).one()
    layers = {s.source_name: s.value for s in db.query(models.CellSource).filter_by(
        table_name=T, row_id=row.row_id, column_name="x")}
    return row.x, layers


@pytest.mark.parametrize("written, layer", [
    ("dt_inventory", "chain_ingestion"),
    ("dt_inventory (r9)", "chain_ingestion (r9)"),
    ("user", "chain_ingestion"),
    ("collision_merge", "chain_ingestion"),
    ("pipeline_parser", "chain_ingestion"),
    (None, "chain_ingestion"),                    # an item that names none was the person's layer
])
def test_1_the_name_a_mapper_wrote_is_written_as_chain_ingestion(db, written, layer):
    NAMED["name"] = written
    _write(db, "user", k="K1", a="v")
    _drain(db)
    assert _x(db) == ("v!", {layer: "v!"})


@pytest.mark.parametrize("meant", [candidates.SOURCE_NAME, candidates.SOURCE_NAME_PARTIAL_KEY,
                                   backfill.SOURCE_NAME])
def test_5_the_names_the_product_gave_a_meaning_stay(db, meant):
    NAMED["name"] = meant
    _write(db, "user", k="K1", a="v")
    _drain(db)
    assert _x(db) == ("v!", {meant: "v!"})


def test_2_an_old_chain_layer_is_written_over_not_left_on_top(db):
    """The owner's symptom: the old layer (4) beat the mapper's own name (99) whatever the time."""
    _write(db, crud.CHAIN_SOURCE, k="K1", x="old")
    NAMED["name"] = "dt_inventory"
    _write(db, "user", k="K1", a="new")
    _drain(db)
    assert _x(db) == ("new!", {"chain_ingestion": "new!"})


def test_4_a_persons_layer_still_wins(db):
    _write(db, "user", k="K1", x="typed")
    NAMED["name"] = "dt_inventory"
    _write(db, "user", k="K1", a="v")
    _drain(db)
    assert _x(db) == ("typed", {"user": "typed", "chain_ingestion": "v!"})


def test_1_a_decorated_mappers_source_name_is_told_once_when_the_declaration_is_read(
        db, monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)

    @mapper_sdk.mapper(name="ln_named", source_name="dt_inventory")
    def ln_named(df, db):
        return df

    @mapper_sdk.mapper(name="ln_plain")
    def ln_plain(df, db):
        return df

    try:
        path = tmp_path / "chain_rules.json"
        path.write_text(json.dumps({"rules": [
            dict(RULE, name="ln_says", mapper="ln_named"), dict(RULE, name="ln_quiet", mapper="ln_plain",
                                                                trigger_columns=["x"])]}), encoding="utf-8")
        monkeypatch.setattr(worker, "RULES_PATH", str(path))
        monkeypatch.setattr(rule_order, "_SAID_FOR", None)
        for _ in range(2):                                   # the same declaration read twice: told once
            worker.load_chain_rules()
            worker.say_the_declaration()
        said = [r.getMessage() for r in caplog.records if "is written as chain_ingestion" in r.getMessage()]
        assert said == ["[ChainRules] ln_says: source_name 'dt_inventory' is written as chain_ingestion"]
    finally:
        for name in ("ln_named", "ln_plain"):
            mapper_sdk.MAPPER_REGISTRY.pop(name, None)
            mapper_sdk.MAPPER_PARAMS.pop(name, None)
            mapper_sdk.MAPPER_FACTS.pop(name, None)
