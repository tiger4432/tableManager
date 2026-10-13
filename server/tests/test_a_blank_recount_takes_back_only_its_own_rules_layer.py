# -*- coding: utf-8 -*-
"""A decide's aggregation fills its own target field, and a blank recount takes back only what its rule wrote
(lead 3e5c9a69e, rebuilt after the NO-GO of 4bb3b4d85 - lead bc9710454 가, 가-1 ㄱ).

The chain signs every layer it writes with the rule that proposed it (`rule_run.signed`); the mapper only reads -
a blank aggregate is left out of the write and named in the item's `withdraw`; after the batch is written the
worker's one withdrawal door takes back, on those cells, the plain chain layer that rule wrote last and the
backfill's old `enrichment_backfill` layer. A join's layer (named per source row) and a rule's that wrote the cell
after it stay. The backfill writes the chain's layer under the same rule, so its value goes the same way.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import anyio                                                          # noqa: E402
import pytest                                                         # noqa: E402

from chain import enrichment                                          # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from tests.support.enrich_decl import enrich_chain_rules, write_rules  # noqa: E402

SRC, INV, BARE = "agt_log", "agt_inv", "agt_bare"
TABLES = {
    SRC: {"business_key": "log_id",
          "column_types": {"log_id": "string", "job": "string", "lot": "string", "t": "string"}},
    INV: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "lot": "string", "first_t": "string",
                           "last_t": "string", "n": "number"}},
    # keys and one value aggregation - a row whose recount is blank has only its keys left
    BARE: {"business_key": "job", "composite_key_source": ["job"],
           "column_types": {"job": "string", "last_lot": "string"}},
}
TARGETS = ["lot", "first_t", "last_t", "n"]
RULE = {
    "agt_rule": {
        "source_table": SRC, "derived_table": INV, "decision_key": ["job"], "target_fields": TARGETS,
        "aggregations": {"lot": {"fn": "unique_concat", "column": "lot"},
                         "first_t": {"fn": "min", "column": "t"},
                         "last_t": {"fn": "max", "column": "t"},
                         "n": "count"}},
    "agt_bare": {
        "source_table": SRC, "derived_table": BARE, "decision_key": ["job"], "target_fields": [],
        "aggregations": {"last_lot": {"fn": "max", "column": "lot"}}},
}
DEDUP = enrichment.config.synthesized_rule_names("agt_rule")[0]
FILE_LAYER = "inventory_2026_10.csv"


@pytest.fixture(name="db")
def fixture_db(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    write_rules(tmp_path, monkeypatch, RULE)
    return db_session


def _write(db, table, tx, source, items, by=None):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(source_name=source, updated_by=by or source, **item) for item in items],
        transaction_id=tx, silent=True))


def _chain(db, tx):
    from chain.ingestion_worker import process_chain_transaction_group
    from database.models import DatabaseOutbox

    rules = enrich_chain_rules(known_tables=crud.TABLE_CONFIG)
    events = [e for e in db.query(DatabaseOutbox).filter(
        DatabaseOutbox.table_name == SRC, DatabaseOutbox.processed_chain == False  # noqa: E712
    ).order_by(DatabaseOutbox.id.asc()).all() if (e.payload or {}).get("transaction_id") == tx]
    assert events, tx
    said = []

    async def run():
        ok, err, messages = await process_chain_transaction_group(tx, events, db, rules)
        assert ok, err
        said.extend(messages)
        for event in events:
            event.processed_chain = True
        db.commit()

    anyio.run(run)
    return said


def _row(db, job, table=INV):
    db.expire_all()
    return db.query(models.DYNAMIC_TABLES[table]).filter_by(business_key_val=job).one_or_none()


def _layers(db, job, column, by=False):
    row = _row(db, job)
    return {layer.source_name: (layer.value, layer.updated_by) if by else layer.value
            for layer in db.query(models.CellSource).filter_by(
                table_name=INV, row_id=str(row.row_id), column_name=column)}


def _source_row(db, log_id):
    return db.query(models.DYNAMIC_TABLES[SRC]).filter_by(business_key_val=log_id).one().row_id


def _in_queue(db, job):
    model = models.DYNAMIC_TABLES[INV]
    rule = enrichment.config._validate_rule("agt_rule", RULE["agt_rule"], crud.TABLE_CONFIG)[0]
    return db.query(model).filter(model.business_key_val == job,
                                  enrichment.config.queue_predicate_condition(model, rule)).count() == 1


def _confirm_may_write(db, job, column):
    row = _row(db, job)
    return (row.row_id, column) in enrichment.candidates.find_unresolved_cells(
        db, INV, [row.row_id], [column])


def _blank_lines(caplog):
    """The withdrawal door's line for a blank recount on INV, up to its counts (`_withdraw_and_tell`)."""
    return [r.getMessage().split("[ChainRetract] ")[1].split(" protected_skipped")[0] for r in caplog.records
            if "[ChainRetract] table=%s blank_rows=" % INV in r.getMessage()]


def _clear_lot(db, tx, log_id):
    _write(db, SRC, tx, crud.USER_SOURCE, [{"row_id": _source_row(db, log_id), "updates": {"lot": None}}])
    return _chain(db, tx)


def test_each_aggregation_fills_its_target_signed_by_its_rule_and_a_person_stays_on_top(db):
    _write(db, SRC, "t1", "pipeline_parser", [
        {"updates": {"log_id": "L1", "job": "J1", "lot": "A", "t": "2026-10-01"}},
        {"updates": {"log_id": "L2", "job": "J1", "lot": "B", "t": "2026-10-03"}}])
    _chain(db, "t1")
    row = _row(db, "J1")
    assert (row.lot, row.first_t, row.last_t, row.n) == ("A, B", "2026-10-01", "2026-10-03", 2)
    assert _layers(db, "J1", "lot", by=True) == {crud.CHAIN_SOURCE: ("A, B", DEDUP)}
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


def test_a_blank_recount_takes_back_its_rules_layer_on_that_cell_only_and_the_grid_hears(db, caplog):
    _write(db, SRC, "t1", "pipeline_parser", [
        {"updates": {"log_id": "L1", "job": "J3", "lot": "X", "t": "2026-10-02"}},
        {"updates": {"log_id": "L5", "job": "J5", "lot": "Y", "t": "2026-10-05"}}])
    _chain(db, "t1")
    assert _layers(db, "J3", "lot") == {crud.CHAIN_SOURCE: "X"} and not _in_queue(db, "J3")

    caplog.set_level("INFO", logger="Chain")
    said = _clear_lot(db, "t2", "L1")
    assert _layers(db, "J3", "lot") == {}, "the rule's own layer of the blank aggregate goes"
    assert _blank_lines(caplog) == ["table=%s blank_rows=1 groups=1 cells_withdrawn=1" % INV], "one line, what it took"
    assert _row(db, "J3").lot is None
    assert _in_queue(db, "J3") and _confirm_may_write(db, "J3", "lot")
    # the same rule's other columns on that row, and the same column on another row, stay
    assert _layers(db, "J3", "first_t") == {crud.CHAIN_SOURCE: "2026-10-02"}
    assert _layers(db, "J5", "lot") == {crud.CHAIN_SOURCE: "Y"} and _row(db, "J5").lot == "Y"
    # the grid's message carries the row with the value it shows now
    row_id = _row(db, "J3").row_id
    shown = [item["data"]["lot"]["value"] for message in said if message.get("table_name") == INV
             for item in message.get("items") or () if item["row_id"] == row_id]
    assert shown == [None], said


def test_a_joins_layer_on_the_cell_stays(db):
    _write(db, SRC, "t1", "pipeline_parser", [{"updates": {"log_id": "L1", "job": "J3", "lot": "X"}}])
    _chain(db, "t1")
    joined = crud.merged_layer_name(crud.CHAIN_SOURCE, "O9")
    _write(db, INV, "j1", joined, [{"business_key_val": "J3", "origin_row_id": "O9", "updates": {"lot": "JOIN"}}],
           by="some_join")
    assert set(_layers(db, "J3", "lot")) == {crud.CHAIN_SOURCE, joined}

    _clear_lot(db, "t2", "L1")
    assert _layers(db, "J3", "lot") == {joined: "JOIN"}
    assert _row(db, "J3").lot == "JOIN"


def test_another_rule_that_wrote_the_cell_last_keeps_its_value(db, caplog):
    _write(db, SRC, "t1", "pipeline_parser", [{"updates": {"log_id": "L1", "job": "J3", "lot": "X"}}])
    _chain(db, "t1")
    assert _blank_lines(caplog) == [], "a new row's blank aggregate has nothing to take back - no line"
    _write(db, INV, "b1", crud.CHAIN_SOURCE, [{"business_key_val": "J3", "updates": {"lot": "B"}}], by="rule_b")
    assert _layers(db, "J3", "lot", by=True) == {crud.CHAIN_SOURCE: ("B", "rule_b")}

    caplog.clear()
    _clear_lot(db, "t2", "L1")
    assert _layers(db, "J3", "lot", by=True) == {crud.CHAIN_SOURCE: ("B", "rule_b")}
    assert _blank_lines(caplog) == [], "nothing of its rule's on the cell - no withdrawal, no line"
    assert _row(db, "J3").lot == "B"


def test_a_backfilled_value_goes_when_its_source_goes_and_the_job_is_recounted(db):
    from chain.enrichment import backfill

    # two source rows of one job, never seen by the chain - the backfill makes the row. A deletion alone does not
    # recount today (its event carries no old key); the remaining row's edit does.
    _write(db, SRC, "s1", "pipeline_parser", [
        {"updates": {"log_id": "L1", "job": "J6", "lot": "X", "t": "2026-10-06"}},
        {"updates": {"log_id": "L2", "job": "J6"}}])
    rule = backfill.load_rule("agt_rule", crud.TABLE_CONFIG)
    stats = backfill.run_backfill(db, rule, apply=True, log=lambda *_: None)
    assert stats["created_rows"] == 1, stats
    assert _layers(db, "J6", "lot", by=True) == {crud.CHAIN_SOURCE: ("X", DEDUP)}

    crud.delete_rows_batch(db, SRC, [_source_row(db, "L1")], "someone")
    db.commit()
    _write(db, SRC, "t2", "pipeline_parser", [{"row_id": _source_row(db, "L2"), "updates": {"t": "2026-10-07"}}])
    _chain(db, "t2")
    assert _layers(db, "J6", "lot") == {} and _row(db, "J6").lot is None
    assert (_row(db, "J6").n, _row(db, "J6").first_t) == (1, "2026-10-07")


def test_an_old_backfill_layer_goes_with_the_blank(db):
    from chain.enrichment import backfill

    _write(db, SRC, "t1", "pipeline_parser", [{"updates": {"log_id": "L1", "job": "J3", "lot": "X"}}])
    _chain(db, "t1")
    _write(db, INV, "o1", backfill.SOURCE_NAME, [{"business_key_val": "J3", "updates": {"lot": "OLD"}}])
    assert _layers(db, "J3", "lot") == {crud.CHAIN_SOURCE: "X", backfill.SOURCE_NAME: "OLD"}

    _clear_lot(db, "t2", "L1")
    assert _layers(db, "J3", "lot") == {} and _row(db, "J3").lot is None


def test_a_derived_row_its_recount_left_with_only_its_keys_goes(db):
    _write(db, SRC, "t1", "pipeline_parser", [{"updates": {"log_id": "L7", "job": "J7", "lot": "Z"}}])
    _chain(db, "t1")
    assert _row(db, "J7", BARE).last_lot == "Z"

    _clear_lot(db, "t2", "L7")
    assert _row(db, "J7", BARE) is None, "keys alone, all the chain's - the row goes as before"


@pytest.mark.parametrize("file_source", [FILE_LAYER, "pipeline_parser"])
def test_with_a_file_layer_on_the_cell_the_rank_table_says_what_shows(db, file_source):
    _write(db, SRC, "t1", "pipeline_parser", [{"updates": {"log_id": "L1", "job": "J4", "lot": "AGG"}}])
    _chain(db, "t1")
    _write(db, INV, "f1", file_source, [{"business_key_val": "J4", "updates": {"lot": "FILE"}}])
    layers = _layers(db, "J4", "lot")
    assert layers == {crud.CHAIN_SOURCE: "AGG", file_source: "FILE"}
    top = min(layers, key=lambda name: crud.get_source_priority(name, INV))
    assert _row(db, "J4").lot == layers[top]

    _clear_lot(db, "t2", "L1")
    assert _layers(db, "J4", "lot") == {file_source: "FILE"}
    assert _row(db, "J4").lot == "FILE", "a blank aggregate leaves the file's value showing"
