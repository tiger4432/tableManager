# -*- coding: utf-8 -*-
"""A formula follows the cells it reads, as a spreadsheet's cell does (owner 10-28 «1 ㄱ»): its rule is woken by what
other rules write too (`allow_chain_trigger`, written by `formula.to_declaration`), so a formula reading a column a rule
writes, or another formula's column, is not left on the old value. Measured with the events the grid and a file write
(collapsed - they name the columns they set). Two that read each other are refused -
test_rules_that_wake_each_other_by_column_are_refused.

    case                                        gate
    a column another rule writes                the formula follows it
    another formula's column                    the formula follows it
    its own write                               wakes nothing - one receipt an edit
"""
import json

import pytest

import event_constants
from chain import formula
from chain import ingestion_worker as worker
from database import crud, models, schemas
from database.context import channel, outbox_mode
from ledger.runtime_v2 import RECEIPT_COLUMN
from tests.test_a_formula_on_a_column_is_a_join_onto_its_own_row import T, _drain, fixture_db  # noqa: F401


def _put(db, rows):
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="user", updated_by="user") for row in rows]))
        db.commit()


@pytest.fixture(name="declare")
def fixture_declare(tmp_path, monkeypatch):
    def declare(*formulas):
        path = tmp_path / "chain_rules.json"
        path.write_text(json.dumps({"rules": [formula.to_declaration(T, column, text) for column, text in formulas]}),
                        encoding="utf-8")
        monkeypatch.setattr(worker, "RULES_PATH", str(path))
        worker.forget_loaded_chain_rules()
        return worker.load_chain_rules()
    yield declare
    worker.forget_loaded_chain_rules()


def _row(db):
    db.expire_all()
    row = db.query(models.DYNAMIC_TABLES[T]).filter_by(k="k1").one()
    return {column: getattr(row, column) for column in ("a", "b", "c")}


def test_a_formula_follows_a_column_another_rule_writes(db, declare):
    rules = declare(("a", "=[t]+0"), ("c", "=[a]*2"))
    _put(db, [{"k": "k1", "t": "1"}])
    _drain(db, rules)
    _put(db, [{"k": "k1", "t": "5"}])
    _drain(db, rules)
    assert _row(db) == {"a": 5, "b": None, "c": 10}


def test_a_formula_follows_another_formula(db, declare):
    rules = declare(("b", "=[a]+1"), ("c", "=[b]*2"))
    _put(db, [{"k": "k1", "a": 1}])
    _drain(db, rules)
    _put(db, [{"k": "k1", "a": 5}])
    _drain(db, rules)
    assert _row(db) == {"a": 5, "b": 6, "c": 12}


def test_its_own_write_wakes_nothing(db, declare, monkeypatch):
    from chain import join_into

    rules = declare(("c", "=[a]*2"))
    _put(db, [{"k": "k1", "a": 1}])
    _drain(db, rules)
    ran, answer = [], join_into.answer
    monkeypatch.setattr(join_into, "answer",
                        lambda db_, rule, read: ran.append(rule.get("name")) or answer(db_, rule, read))
    _put(db, [{"k": "k1", "a": 5}])
    _drain(db, rules)
    receipts = db.query(models.AuditLog).filter(models.AuditLog.column_name == RECEIPT_COLUMN).count()
    assert _row(db)["c"] == 10 and receipts == 2 and ran == ["formula fx.c"], "one run an edit"
