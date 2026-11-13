# -*- coding: utf-8 -*-
"""A formula's write (lead 10-28 ㄴ): a chain write to a formula column holds no layer - the value is the declaration's -
and leaves no line a row; its history is one receipt per batch and formula (`crud.receipt_log`, split under the audit
value cap), which the ledger's receipts are written by too.

    seat                               gate
    the write core                     no cell_sources row, no ROW_UPDATE line; one receipt naming the rows it changed
    a person's layer                   stays over the formula
    an answer that is blank / unfit    written blank and counted - on the receipt and in one line
    crud.receipt_log                   split under the cap, every id once in order; the ledger's line as before + label
    grid_read.transaction_rows         the grid and the export select the rows a receipt names
"""
import asyncio
import json

import pytest

from chain import formula
from chain import ingestion_worker as worker
from database import crud, models
from event_constants import MAX_AUDIT_VALUE_CHARS
from ledger.runtime_v2 import RECEIPT_COLUMN, RECEIPT_LABEL, RECEIPT_SOURCE
from tests.test_a_formula_on_a_column_is_a_join_onto_its_own_row import T, _drain, _put, fixture_db  # noqa: F401


@pytest.fixture(name="rules")
def fixture_rules(tmp_path, monkeypatch):
    def declare(text, column="c"):
        path = tmp_path / "chain_rules.json"
        path.write_text(json.dumps({"rules": [formula.to_declaration(T, column, text)]}), encoding="utf-8")
        monkeypatch.setattr(worker, "RULES_PATH", str(path))
        worker.forget_loaded_chain_rules()
        return [rule for rule in worker.load_chain_rules() if str(rule.get("name")).startswith("formula ")]
    yield declare
    worker.forget_loaded_chain_rules()


def _c(db):
    db.expire_all()
    return {row.k: row.c for row in db.query(models.DYNAMIC_TABLES[T]).order_by("k")}


def _receipts(db):
    return [log.new_value for log in db.query(models.AuditLog).filter(models.AuditLog.column_name == RECEIPT_COLUMN)
            .order_by(models.AuditLog.id)]


def _ids(db):
    return {row.k: row.row_id for row in db.query(models.DYNAMIC_TABLES[T])}


def test_the_write_holds_no_layer_and_leaves_one_receipt_naming_its_rows(db, rules):
    _put(db, [{"k": "k1", "a": 1, "b": 2}, {"k": "k2", "a": 10, "b": 0}])
    _drain(db, rules("=[a]+[b]*3"))
    assert _c(db) == {"k1": 7, "k2": 10}
    assert db.query(models.CellSource).filter(models.CellSource.column_name == "c").count() == 0
    assert db.query(models.AuditLog).filter(models.AuditLog.column_name == "ROW_UPDATE").count() == 0
    ids = _ids(db)
    assert _receipts(db) == [{"receipt_label": "formula fx.c", "blank": 0, "refused": 0, "rows": 2, "part": 1,
                              "parts": 1, "row_ids": [ids["k1"], ids["k2"]]}]


def test_a_persons_value_stays_over_the_formula(db, rules):
    declared = rules("=[a]+[b]*3")
    _put(db, [{"k": "k1", "a": 1, "b": 2, "c": 100}, {"k": "k2", "a": 1, "b": 1}])
    _drain(db, declared)
    _put(db, [{"k": "k1", "a": 5}, {"k": "k2", "a": 5}])
    _drain(db, declared)
    assert _c(db) == {"k1": 100, "k2": 8}


def test_a_blank_and_an_unfitting_answer_are_written_blank_and_counted(db, rules, caplog):
    _put(db, [{"k": "k1", "t": "4"}, {"k": "k2", "t": "four"}, {"k": "k3", "a": 1}])
    _drain(db, rules("=[t]"))
    assert _c(db) == {"k1": 4, "k2": None, "k3": None}
    assert [(said["blank"], said["refused"], said["rows"]) for said in _receipts(db)] == [(1, 1, 1)]
    assert "[Formula] formula fx.c: 1 blank answer(s), 1 not of the column's type - written blank" in caplog.text


def test_one_blank_operand_answers_blank_and_is_counted(db, rules):
    """not 0 as a spreadsheet reads a blank (owner 10-28 ㄱ, as Spotfire: contracts add.null · multiply.rows)"""
    _put(db, [{"k": "k1", "a": 1, "b": 2}, {"k": "k2", "a": 1, "b": 2, "t": "3"}])
    _drain(db, rules("=[a]+[b]*[t]"))
    assert _c(db) == {"k1": None, "k2": 7}
    assert [(said["blank"], said["refused"], said["rows"]) for said in _receipts(db)] == [(1, 0, 1)]


def test_an_answer_gone_blank_blanks_the_column(db, rules):
    declared = rules("=[a]/[b]")
    _put(db, [{"k": "k1", "a": 6, "b": 2}, {"k": "k2", "a": 6, "b": 3}])
    _drain(db, declared)
    assert _c(db) == {"k1": 3, "k2": 2}
    _put(db, [{"k": "k1", "b": 0}, {"k": "k2", "b": ""}])
    _drain(db, declared)
    assert _c(db) == {"k1": None, "k2": None}, "a division by 0 and an operand blanked - no old value is kept"


def test_a_receipt_is_split_under_the_cap_and_names_every_row_once():
    ids = ["0190f0aa-%04d-7000-8000-000000000000" % i for i in range(300)]
    lines = crud.receipt_log(None, T, "batch", "formula fx.c", {"blank": 0}, "chain_ingestion", "w", "tx", row_ids=ids)
    said = [line["new_value"] for line in lines]
    assert len(said) > 1 and all(len(repr(value)) <= MAX_AUDIT_VALUE_CHARS for value in said)
    assert [row for value in said for row in value["row_ids"]] == ids
    assert [(value["part"], value["parts"], value["rows"]) for value in said] == [
        (k, len(said), len(value["row_ids"])) for k, value in enumerate(said, 1)]
    assert sum(value["rows"] for value in said) == 300, "a group's lines sum to its rows"
    assert {line["transaction_id"] for line in lines} == {"tx"} and {line["row_id"] for line in lines} == {"batch"}


@pytest.mark.parametrize("tx", ["chain_x", None])
def test_a_ledger_receipt_is_the_line_it_was_with_its_label(tx):
    facts = {"rows": 3, "atoms_written": 5, "status": "ok", "world": "w"}
    before = crud.create_audit_log(None, "rel", "b1", RECEIPT_COLUMN, None, facts, RECEIPT_SOURCE, "who",
                                   transaction_id=tx, add_to_cache=False)
    before["transaction_id"] = tx
    [after] = crud.receipt_log(None, "rel", "b1", RECEIPT_LABEL, facts, RECEIPT_SOURCE, "who", tx)
    assert after["new_value"] == dict(facts, receipt_label="Ledger batch")
    assert {k: v for k, v in after.items() if k not in ("new_value", "timestamp")} == \
        {k: v for k, v in before.items() if k not in ("new_value", "timestamp")}


def test_the_history_says_formula_and_the_rows_its_receipt_names(db, rules):
    """Owner 11-12 ㄴ «영수증만, 화면은 수식 계산 · N 행»: the formula's batch says «formula», its rows are the ones its
    receipt names (no line a row) - the panel's count and the transaction's row list (GET /audit_logs/transaction)."""
    from sqlalchemy import select

    from admin import audit_history
    from database import lines

    _put(db, [{"k": "k1", "a": 1, "b": 2}, {"k": "k2", "a": 3, "b": 0}])
    _drain(db, rules("=[a]+[b]*3"))
    tx = db.query(models.AuditLog.transaction_id).filter(models.AuditLog.column_name == RECEIPT_COLUMN).scalar()
    ab = lines.AuditBatch.__table__
    assert [(r.table_name, r.written_by, r.work_kind) for r in db.execute(select(ab).where(ab.c.transaction_id == tx))
            ] == [(T, "formula %s.c" % T, "formula")]
    ids = _ids(db)
    assert audit_history.changed_rows(db, T, tx) == (2, False)
    entries, ended = audit_history.group_rows(db, T, tx, 10)
    assert ended is None
    assert [(e["row_id"], e["business_key"], e["updated_by"]) for e in entries] == [
        (ids["k1"], "k1", "formula %s.c" % T), (ids["k2"], "k2", "formula %s.c" % T)]
    assert len({e["id"] for e in entries}) == 2                  # one entry, one id - one receipt line names both (D)


def test_a_receipt_names_its_rows_as_text(db):
    """A receipt's row_ids meet a text row_id column (PG: text = integer is an error) - read as text in the one seat."""
    db.add(models.AuditLog(table_name=T, row_id="-", column_name=RECEIPT_COLUMN, transaction_id="tx-int",
                           new_value={"row_ids": [7, "r8"]}, source_name="s", updated_by="s"))
    db.commit()
    assert list(crud.receipt_row_ids(db, T, "tx-int")) == ["7", "r8"]


def test_the_grid_and_the_export_select_the_rows_a_receipt_names(db, rules):
    import main
    from grid_read import narrowed_table_query

    _put(db, [{"k": "k1", "a": 1, "b": 2}, {"k": "k2", "a": 3, "b": 0}])
    _drain(db, rules("=[a]+[b]*3"))
    tx = db.query(models.AuditLog.transaction_id).filter(models.AuditLog.column_name == RECEIPT_COLUMN).scalar()
    _put(db, [{"k": "k3", "a": 5}])                           # a row this transaction did not touch
    model = models.DYNAMIC_TABLES[T]
    assert sorted(row.k for row in narrowed_table_query(db, T, model, transaction_id=tx)[0]) == ["k1", "k2"]
    response = main.export_table_csv(T, transaction_id=tx, q=None, cols=None, filters=None, world=None, db=db)

    async def body():
        return b"".join([chunk if isinstance(chunk, bytes) else chunk.encode() async for chunk in
                         response.body_iterator])

    rows = asyncio.run(body()).decode("utf-8-sig").strip().splitlines()
    assert len(rows) == 3, rows
