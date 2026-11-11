# -*- coding: utf-8 -*-
"""A formula column is the merge's candidate (lead 11-11 안 1): the write that moves its operands moves it, and the
formula rule's own write - nothing left to say - merges its rows again with no line (lead 11-11 (가)).

    door                                   c                       mark lines
    an operand written ten times           the formula, each time  0
    R1 after the formula is saved          the formula             0
"""
from sqlalchemy import text

from chain import replay
from database import lines, models
from tests.test_a_formula_on_a_column_is_a_join_onto_its_own_row import T, _drain, _put, fixture_db  # noqa: F401
from tests.test_a_formula_write_holds_no_layer_and_leaves_a_receipt import _c, fixture_rules  # noqa: F401


def _marks(db):
    return db.execute(text("SELECT count(*) FROM \"%s\" WHERE line_kind = 'mark'" % lines.lines_relation(T))).scalar()


def test_an_operand_written_ten_times_moves_the_formula_and_leaves_no_mark_line(db, rules):
    declared = rules("=[a]+[b]*3")
    _put(db, [{"k": "k1", "a": 1, "b": 2}])
    _drain(db, declared)
    for n in range(10):
        _put(db, [{"k": "k1", "a": n}])
        _drain(db, declared)
        assert _c(db) == {"k1": n + 6}, n
    assert _marks(db) == 0


def test_r1_after_a_formula_is_saved_writes_its_answer_into_the_column(db, rules):
    _put(db, [{"k": "k1", "a": 1, "b": 2}, {"k": "k2", "a": 10, "b": 0}])
    db.query(models.DatabaseOutbox).update({"processed_chain": True})   # the rows were there before the formula
    db.commit()
    declared = rules("=[a]+[b]*3")
    assert _c(db) == {"k1": None, "k2": None}
    replay.replay_rule(db, declared[0], apply=True, log=lambda _l: None)
    _drain(db, declared)
    assert _c(db) == {"k1": 7, "k2": 10} and _marks(db) == 0
    assert db.query(models.CellSource).filter(models.CellSource.column_name == "c").count() == 0
