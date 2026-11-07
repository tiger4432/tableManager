# -*- coding: utf-8 -*-
"""총괄 10-11 ㄴ (소유자의 계측 이벤트 맵핑 표 - key and a count, no field for a person): a decide whose derived row carries only its key and
its aggregations - no field for a person - stands, writes a row per key with its counts, and queues nothing.

  fields [] or none + aggregations     stands; one row per key, die_count = the rows of that key
  fields [] + no aggregations          stands too - a row per key, its key alone (owner 10-23: a report table's rows)
  the queue                            no row of a fields-less rule is work for a person; resolved = every row"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import mapper_sdk                                                     # noqa: E402
from chain import enrichment, rule_shape                              # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from database.database import Base                                    # noqa: E402
from database import crud, models, schemas                            # noqa: E402

DIE = "nf_die"
PAIR = "nf_pair"
TABLES = {
    DIE: {"business_key": "die_key", "composite_key_source": ["die_key"],
          "column_types": {"die_key": "string", "bonded_wafer": "string", "core_wafer": "string", "note": "string"}},
    PAIR: {"business_key": None, "composite_key_source": ["bonded_wafer", "core_wafer"],
           "column_types": {"bonded_wafer": "string", "core_wafer": "string", "die_count": "number",
                            "note_min": "string"}},
}
KEY = ["bonded_wafer", "core_wafer"]
COUNT = {"die_count": "count"}


@pytest.fixture(name="db")
def fixture_db():
    mapper_sdk.discover()
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _declared(decide):
    return rule_shape.expand_declaration(
        {"name": "nf_pairs", "on": {"table": DIE, "require": KEY}, "into": {"table": PAIR},
         "derive": {"kind": "decide", "decide": decide}}, crud.TABLE_CONFIG)


@pytest.mark.parametrize("fields", [[], None], ids=["empty", "unwritten"])
def test_no_fields_with_aggregations_stands(db, fields):
    decide = {"key": KEY, "aggregations": COUNT}
    if fields is not None:
        decide["fields"] = fields
    rules, refusal = _declared(decide)[:2]
    assert refusal is None, refusal
    assert [r for r in rules if r["name"].startswith("enrichment_dedup:")], [r["name"] for r in rules]


def test_no_fields_and_no_aggregations_writes_a_row_per_key_its_key_alone(db):
    pair = _seed_and_run(db, {"key": KEY, "fields": []})
    rows = sorted((r.bonded_wafer, r.core_wafer, r.die_count) for r in db.query(pair).all())
    assert rows == [("W1", "C1", None), ("W1", "C2", None), ("W2", "C1", None)]


def _seed_and_run(db, decide=None):
    dies = [("W1", "C1")] * 3 + [("W1", "C2")] * 2 + [("W2", "C1")]
    crud.apply_batch_updates(db, DIE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"die_key": "D%d" % i, "bonded_wafer": w, "core_wafer": c},
                                  source_name="seed", updated_by="nf") for i, (w, c) in enumerate(dies)]))
    db.commit()
    rules = _declared(decide or {"key": KEY, "fields": [], "aggregations": COUNT})[0]
    events = db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.table_name == DIE).all()
    assert events, "CANARY: the die rows staged events"
    worker._process_chain_transaction_group_sync(
        "tx-nf", events, db, [r for r in rules if r["name"].startswith("enrichment_dedup:")])
    db.commit()
    db.expire_all()
    return models.DYNAMIC_TABLES[PAIR]


def test_a_row_per_key_with_its_count(db):
    pair = _seed_and_run(db)
    rows = sorted((r.bonded_wafer, r.core_wafer, int(r.die_count)) for r in db.query(pair).all())
    assert rows == [("W1", "C1", 3), ("W1", "C2", 2), ("W2", "C1", 1)]


def test_a_fields_less_rule_queues_nothing(db):
    pair = _seed_and_run(db)
    rule, why = enrichment.config._validate_rule(
        "nf_pairs", {"source_table": DIE, "derived_table": PAIR, "decision_key": KEY, "target_fields": [],
                     "aggregations": COUNT}, crud.TABLE_CONFIG)
    assert rule is not None, why
    every = db.query(pair).count()
    assert every == 3, "CANARY: the pair rows were written"

    def rows(scope):
        return db.query(pair).filter(enrichment.config.queue_predicate_condition(pair, rule, scope)).count()

    assert [rows(s) for s in enrichment.config.QUEUE_SCOPES] == [
        every if s == enrichment.config.QUEUE_SCOPE_RESOLVED else 0 for s in enrichment.config.QUEUE_SCOPES]



def test_a_derived_row_whose_aggregation_is_blank_stays_trigger_after_trigger(db):
    """총괄 10-12 (소유자 「행파생 자꾸 파생하고 지 혼자 회수하는데?」): a row per key whose only aggregation is blank - the
    rows of that key carry no value for it. The chain's shell question (5eee501eb, «a row THIS WRITE EMPTIED») took
    the row the same write had just made for a shell and deleted it, and the next trigger made it again."""
    pair = _seed_and_run(db, {"key": KEY, "fields": [], "aggregations": {"note_min": {"fn": "min", "column": "note"}}})
    die = models.DYNAMIC_TABLES[DIE]
    seen = max(e.id for e in db.query(models.DatabaseOutbox))
    crud.apply_batch_updates(db, DIE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        row_id=db.query(die).filter(die.die_key == "D0").one().row_id, updates={"core_wafer": "C9"},
        source_name="seed", updated_by="nf")]))
    db.commit()
    worker._process_chain_transaction_group_sync(
        "tx-nf-2", db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.id > seen).all(), db,
        [r for r in _declared({"key": KEY, "fields": [], "aggregations": {"note_min": {"fn": "min", "column": "note"}}})[0]
         if r["name"].startswith("enrichment_dedup:")])
    db.commit()
    db.expire_all()
    assert sorted((r.bonded_wafer, r.core_wafer, r.note_min) for r in db.query(pair).all()) == [
        ("W1", "C1", None), ("W1", "C2", None), ("W1", "C9", None), ("W2", "C1", None)]
