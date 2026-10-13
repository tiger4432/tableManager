# -*- coding: utf-8 -*-
"""A decide's aggregation may share its column with a target field (owner 10-13, 3e5c9a69e ㄱ).

The aggregation writes that column as the chain's layer; a person, or a layer the rank table puts
above the chain, is what shows. A blank aggregate writes no layer and withdraws the chain layer it
wrote before, so the row is back in the queue and the auto-confirm may fill it. Today's cause of
the owner's always-blank dt_lot was the mapper dropping such an aggregation (`col not in target_fields`).
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import anyio                                                          # noqa: E402
import pytest                                                         # noqa: E402

from chain import enrichment                                          # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from tests.support.enrich_decl import enrich_chain_rules, write_rules  # noqa: E402

SRC, INV = "agt_log", "agt_inv"
TABLES = {
    SRC: {"business_key": "log_id",
          "column_types": {"log_id": "string", "job": "string", "lot": "string", "t": "string"}},
    INV: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "lot": "string", "first_t": "string",
                           "last_t": "string", "n": "number"}},
}
TARGETS = ["lot", "first_t", "last_t", "n"]
RULE = {"agt_rule": {
    "source_table": SRC, "derived_table": INV, "decision_key": ["job"], "target_fields": TARGETS,
    "aggregations": {"lot": {"fn": "unique_concat", "column": "lot"},
                     "first_t": {"fn": "min", "column": "t"},
                     "last_t": {"fn": "max", "column": "t"},
                     "n": "count"}}}
FILE_LAYER = "inventory_2026_10.csv"


@pytest.fixture(name="db")
def fixture_db(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    write_rules(tmp_path, monkeypatch, RULE)
    return db_session


def _write(db, table, tx, source, items):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(source_name=source, updated_by=source, **item) for item in items],
        transaction_id=tx, silent=True))


def _chain(db, tx):
    from chain.ingestion_worker import process_chain_transaction_group
    from database.models import DatabaseOutbox

    rules = enrich_chain_rules(known_tables=crud.TABLE_CONFIG)
    events = [e for e in db.query(DatabaseOutbox).filter(
        DatabaseOutbox.table_name == SRC, DatabaseOutbox.processed_chain == False  # noqa: E712
    ).order_by(DatabaseOutbox.id.asc()).all() if (e.payload or {}).get("transaction_id") == tx]
    assert events, tx

    async def run():
        ok, err, _messages = await process_chain_transaction_group(tx, events, db, rules)
        assert ok, err
        for event in events:
            event.processed_chain = True
        db.commit()

    anyio.run(run)


def _row(db, job):
    db.expire_all()
    return db.query(models.DYNAMIC_TABLES[INV]).filter_by(business_key_val=job).one()


def _layers(db, job, column):
    row = _row(db, job)
    return {layer.source_name: layer.value for layer in db.query(models.CellSource).filter_by(
        table_name=INV, row_id=str(row.row_id), column_name=column)}


def _in_queue(db, job):
    model = models.DYNAMIC_TABLES[INV]
    rule = enrichment.config._validate_rule("agt_rule", RULE["agt_rule"], crud.TABLE_CONFIG)[0]
    return db.query(model).filter(model.business_key_val == job,
                                  enrichment.config.queue_predicate_condition(model, rule)).count() == 1


def _confirm_may_write(db, job, column):
    row = _row(db, job)
    return (row.row_id, column) in enrichment.candidates.find_unresolved_cells(
        db, INV, [row.row_id], [column])


def test_each_aggregation_fills_its_target_and_a_person_stays_on_top(db):
    _write(db, SRC, "t1", "pipeline_parser", [
        {"updates": {"log_id": "L1", "job": "J1", "lot": "A", "t": "2026-10-01"}},
        {"updates": {"log_id": "L2", "job": "J1", "lot": "B", "t": "2026-10-03"}}])
    _chain(db, "t1")
    row = _row(db, "J1")
    assert (row.lot, row.first_t, row.last_t, row.n) == ("A, B", "2026-10-01", "2026-10-03", 2)
    assert _layers(db, "J1", "lot") == {crud.CHAIN_SOURCE: "A, B"}
    assert not _in_queue(db, "J1"), "every target is filled, as a confirmed row is"

    _write(db, INV, "p1", crud.USER_SOURCE, [{"business_key_val": "J1", "updates": {"lot": "P"}}])
    _write(db, SRC, "t2", "pipeline_parser", [
        {"updates": {"log_id": "L3", "job": "J1", "lot": "C", "t": "2026-09-30"}}])
    _chain(db, "t2")
    row = _row(db, "J1")
    assert row.lot == "P", "the recount must not overwrite the person"
    assert _layers(db, "J1", "lot") == {crud.CHAIN_SOURCE: "A, B, C", crud.USER_SOURCE: "P"}
    assert (row.first_t, row.n) == ("2026-09-30", 3)


def test_a_blank_aggregate_writes_no_layer_and_leaves_the_row_to_the_confirm(db):
    _write(db, SRC, "t1", "pipeline_parser", [{"updates": {"log_id": "L1", "job": "J2"}}])
    _chain(db, "t1")
    row = _row(db, "J2")
    assert (row.lot, row.first_t, row.last_t, row.n) == (None, None, None, 1)
    assert all(_layers(db, "J2", column) == {} for column in ("lot", "first_t", "last_t"))
    assert _in_queue(db, "J2")
    assert all(_confirm_may_write(db, "J2", column) for column in ("lot", "first_t", "last_t"))

    _write(db, INV, "c1", enrichment.candidates.SOURCE_NAME,
           [{"business_key_val": "J2", "updates": {"lot": "AC"}}])
    assert _row(db, "J2").lot == "AC"


def test_an_aggregate_that_turns_blank_withdraws_the_chain_layer_it_wrote(db):
    _write(db, SRC, "t1", "pipeline_parser", [
        {"updates": {"log_id": "L1", "job": "J3", "lot": "X", "t": "2026-10-02"}}])
    _chain(db, "t1")
    assert _row(db, "J3").lot == "X" and not _in_queue(db, "J3")
    assert _layers(db, "J3", "lot") == {crud.CHAIN_SOURCE: "X"}

    row_id = db.query(models.DYNAMIC_TABLES[SRC]).filter_by(business_key_val="L1").one().row_id
    _write(db, SRC, "t2", crud.USER_SOURCE, [{"row_id": row_id, "updates": {"lot": None}}])
    _chain(db, "t2")
    assert _layers(db, "J3", "lot") == {}, "the chain layer of the old aggregate must go"
    assert _row(db, "J3").lot is None
    assert _in_queue(db, "J3") and _confirm_may_write(db, "J3", "lot")


@pytest.mark.parametrize("file_source", [FILE_LAYER, "pipeline_parser"])
def test_with_a_file_layer_on_the_cell_the_rank_table_says_what_shows(db, file_source):
    _write(db, SRC, "t1", "pipeline_parser", [{"updates": {"log_id": "L1", "job": "J4", "lot": "AGG"}}])
    _chain(db, "t1")
    _write(db, INV, "f1", file_source, [{"business_key_val": "J4", "updates": {"lot": "FILE"}}])
    layers = _layers(db, "J4", "lot")
    assert layers == {crud.CHAIN_SOURCE: "AGG", file_source: "FILE"}
    top = min(layers, key=lambda name: crud.get_source_priority(name, INV))
    assert _row(db, "J4").lot == layers[top]

    row_id = db.query(models.DYNAMIC_TABLES[SRC]).filter_by(business_key_val="L1").one().row_id
    _write(db, SRC, "t2", crud.USER_SOURCE, [{"row_id": row_id, "updates": {"lot": None}}])
    _chain(db, "t2")
    assert _layers(db, "J4", "lot") == {file_source: "FILE"}
    assert _row(db, "J4").lot == "FILE", "a blank aggregate leaves the file's value showing"
