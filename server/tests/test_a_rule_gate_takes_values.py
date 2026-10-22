# -*- coding: utf-8 -*-
"""A chain rule's row gates take values (소유자 10-21 「체인 행 내 특정 값일 때 제외하는 거는」, 총괄 9a5206e0b ·
23fb6060d): a `require` · `exclude` item is a column name - blank or filled, as before - or {column: [values]} - one of
them, the cell and the values spelled by the one key speller by the column's declared type (1460cfef2).

  one set     `gate_misses` (Python) and `gate_conditions` (SQL) take the same rows of one fixture, gate by gate
  the line    «not handed over» names the values beside the column
  left        an edit into an excluded value is, to a rule that reads rows that left, a row that left
  refused     an item that is neither a name nor {column: [non-empty scalar values]}, or names no column the table has
  the join    `on.exclude` with values: such a value-table row is no answer
  the reader  a value item's column wakes the rule; a copy and its recount pair by their items
"""
import json
import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import chain_bindings
import event_constants
import mapper_sdk
from chain import ingestion_worker as worker
from chain import rule_run, rule_shape
from database import crud, models, schemas
from database.context import outbox_mode
from database.database import Base
from utils.payload_helper import get_payload_dict

SRC, DST = "vg_log", "vg_answer"
TABLES = {
    SRC: {"business_key": "k", "composite_key_source": ["k"],
          "column_types": {"k": "string", "status": "string", "n": "number", "v": "string"},
          "display_columns": ["k", "status", "n", "v"]},
    DST: {"business_key": "k", "composite_key_source": ["k"],
          "column_types": {"k": "string", "v": "string"}, "display_columns": ["k", "v"]},
}
ROWS = [{"k": "A", "status": "SCRAP", "n": 1}, {"k": "B", "status": "OK", "n": 1.0},
        {"k": "C", "status": "", "n": 2}, {"k": "D", "status": None, "n": None},
        {"k": "E", "status": "scrap", "n": 4}, {"k": "F", "status": "OK", "n": 3}]


@pytest.fixture(name="db")
def fixture_db():
    mapper_sdk.discover()
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _push(db, table, rows):
    with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(r), source_name="seed", updated_by="vg") for r in rows]))
        db.commit()


@pytest.mark.parametrize("gates, taken", [
    ({"exclude": [{"status": ["SCRAP"]}]}, "BCDEF"),
    ({"require": [{"status": ["OK"]}]}, "BF"),
    ({"exclude": [{"n": ["001"]}]}, "CDEF"),                    # 1 · 1.0 · 001 one value
    ({"require": [{"n": [2, "3.0"]}]}, "CF"),
    ({"require": [{"status": [""]}]}, "CD"),                     # "" is a blank
    ({"require": ["status", {"n": [1]}]}, "AB"),                 # a name and a value item together
    ({"exclude": [{"status": ["SCRAP", ""]}]}, "BEF"),
])
def test_python_and_sql_take_the_same_rows(db, gates, taken):
    _push(db, SRC, ROWS)
    model = models.DYNAMIC_TABLES[SRC]
    rows = db.query(model).all()
    by_python = "".join(sorted(r.k for r in rows if not rule_run.gate_misses(
        gates, {c: getattr(r, c) for c in ("status", "n")}, SRC)))
    by_sql = "".join(sorted(r.k for r in db.query(model).filter(*rule_run.gate_conditions(gates, model))))
    assert (by_python, by_sql) == (taken, taken)


def _payload(row_id, old=None, **values):
    payload = {"row_id": row_id, "data": {c: {"value": v} for c, v in values.items()}}
    if old:
        payload[event_constants.OLD_VALUES_KEY] = old
    return payload


RULE = {"name": "vg_copy", "trigger_table": SRC, "target_table": DST, "exclude": [{"status": ["SCRAP"]}]}


def test_the_line_names_the_values(db, caplog):
    rows = [_payload("a", status="SCRAP"), _payload("b", status="OK")]
    with caplog.at_level(logging.INFO):
        kept, _ = rule_run.held_back(RULE, rows)
        rule_run.held_back(dict(RULE, exclude=None, require=[{"status": ["OK"]}, "n"]), rows)
    assert [p["row_id"] for p in kept] == ["b"]
    said = [r.getMessage() for r in caplog.records]
    assert any("excluding value(s) found: status [SCRAP]=1" in line for line in said), said
    assert any("required column(s) empty: n=2; required value(s) missing: status [OK]=1" in line for line in said), said


def test_an_edit_into_an_excluded_value_is_a_row_that_left(db):
    rule = dict(RULE, allow_delete_trigger=True)
    kept, _ = rule_run.held_back(rule, [_payload("a", old={"status": "OK"}, status="SCRAP")])
    assert kept == [{"row_id": "a", "data": {}, event_constants.OLD_VALUES_KEY: {"status": "OK"}}]


@pytest.mark.parametrize("item, code", [
    ({}, "bad_exclude"), ({"status": []}, "bad_exclude"), ({"status": [["x"]]}, "bad_exclude"),
    ({"status": [True]}, "bad_exclude"), ("", "bad_exclude"), ({"nope": ["x"]}, "unknown_exclude_column"),
])
def test_the_loader_refuses_an_item_by_name(db, tmp_path, monkeypatch, caplog, item, code):
    rule = {"name": "vg_bad", "enabled": True, "is_batch": True, "trigger_table": SRC, "target_table": DST,
            "mapper": "vg_spy", "exclude": [item]}
    good = dict(rule, name="vg_good", exclude=[{"status": ["SCRAP"]}])
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "vg_spy", lambda db, payload, rule=None: {"updates": []})
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [rule, good]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    with caplog.at_level(logging.ERROR):
        loaded = {r.get("name") for r in worker.load_chain_rules()}
    assert "vg_good" in loaded and "vg_bad" not in loaded
    assert "vg_bad(%s)" % code in " ".join(r.getMessage() for r in caplog.records)


def _drain(db, rules, rounds=6):
    for _ in range(rounds):
        pending = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            return
        groups = {}
        for e in pending:
            groups.setdefault(get_payload_dict(e).get("transaction_id"), []).append(e)
        for tx_id, events in groups.items():
            ok, error, _ = worker._process_chain_transaction_group_sync(tx_id, events, db, rules)
            assert ok, error
            for e in events:
                event_constants.mark_processed(e, "SUCCESS")
            db.commit()
    raise AssertionError("the chain did not settle")


def test_a_join_takes_no_answer_from_a_value_row_its_exclude_names(db):
    stood, refusal, _notes = rule_shape.expand_declaration(
        {"name": "vg_join", "on": {"table": SRC, "exclude": [{"status": ["SCRAP"]}]},
         "derive": {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}], "take": [{"from": "v", "into": "v"}]}},
         "into": {"table": DST}}, crud.TABLE_CONFIG)
    assert refusal is None
    _push(db, DST, [{"k": "A"}, {"k": "B"}])
    _push(db, SRC, [{"k": "A", "status": "SCRAP", "v": "a"}, {"k": "B", "status": "OK", "v": "b"}])
    _drain(db, stood)
    assert {r.k: r.v for r in db.query(models.DYNAMIC_TABLES[DST]).all()} == {"A": None, "B": "b"}


def test_a_value_items_column_wakes_the_rule():
    assert worker.wake_columns({"trigger_columns": ["v"], "exclude": [{"status": ["SCRAP"]}, "n"]}) == [
        "v", "status", "n"]


def test_a_copy_and_its_recount_pair_by_their_value_items():
    from mappers import hold_copy

    gate = [{"status": ["SCRAP"]}]
    copy = {"name": "c", "trigger_table": SRC, "target_table": DST, "exclude": gate}
    recount = {"name": "r", "trigger_table": DST, "target_table": DST, "params": {"source_table": SRC}}
    assert hold_copy._paired([copy, recount]) == []
    assert copy[chain_bindings.SOURCE_GATE_KEYS["exclude"]] == recount[chain_bindings.SOURCE_GATE_KEYS["exclude"]] == gate
