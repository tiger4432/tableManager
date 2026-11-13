# -*- coding: utf-8 -*-
"""A person pinning the source a cell shows (`crud.set_cell_manual_priority_batch`, the grid's «Pin») is a «mark»
line (cell-source overhaul): the pin stays in cell_overwrites, the row whose pin moved gets one mark line, and the
row is merged again - the pinned source's head line shows; the same source again takes the pin off; a source with no
head line on the cell is skipped. The history entry names the moved cell, no before value."""
import pytest
from sqlalchemy import select

from database import crud, lines, models, schemas
from database.database import Base
from test_write_lines_writes_a_line_a_change_and_its_current_line import ticking_clock

TABLE = "pin_line"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string", "b": "string"}}


@pytest.fixture(name="db")
def fixture_db(db_session, monkeypatch):
    models.init_dynamic_models({TABLE: CFG})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    Base.metadata.create_all(bind=db_session.get_bind())
    lines.ensure_line_table(db_session, TABLE, CFG)
    db_session.commit()
    ticking_clock(monkeypatch)
    return db_session


def _say(db, source, values):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val="K1", updates={"k": "K1", **values}, source_name=source, updated_by="kim")]))


def _row(db):
    model = models.DYNAMIC_TABLES[TABLE]
    db.expire_all()
    return db.query(model).filter(model.business_key_val == "K1").one()


def _mark(db, column="a"):
    m = db.query(models.CellOverwrite).filter_by(table_name=TABLE, row_id=_row(db).row_id, column_name=column).first()
    return None if m is None else (m.is_overwrite, m.manual_priority_source)


def _mark_lines(db):
    ln = lines.shape(db, TABLE, CFG)["lines"]
    return db.execute(select(ln.c.row_id, ln.c.source_name, ln.c.written_by).where(ln.c.line_kind == "mark")
                      .order_by(ln.c.line_id)).all()


def _pin(db, source, columns=("a",)):
    return crud.set_cell_manual_priority_batch(db, TABLE, [{"row_id": _row(db).row_id, "column_name": c}
                                                           for c in columns], source, "lee")


def test_a_pin_shows_the_pinned_source_and_says_so(db):
    _say(db, "f1.csv", {"a": "one"})
    _say(db, "f2.csv", {"a": "two"})
    assert _row(db).a == "two", "canary: the newer file shows"
    rows, logs, gone = _pin(db, "f1.csv")
    assert (_row(db).a, _mark(db), [r.row_id for r in rows], gone) == ("one", (True, "f1.csv"), [_row(db).row_id], [])
    assert [(l["column_name"], l["new_value"], l["old_value"], l["source_name"], l["updated_by"]) for l in logs] == [
        ("a", "one", None, "set_priority:f1.csv", "lee")], logs
    assert _mark_lines(db) == [(_row(db).row_id, "f1.csv", "lee")]


def test_the_same_source_again_takes_the_pin_off(db):
    _say(db, "f1.csv", {"a": "one"})
    _say(db, "f2.csv", {"a": "two"})
    _pin(db, "f1.csv")
    rows, logs, _gone = _pin(db, "f1.csv")
    assert (_row(db).a, _mark(db), len(rows)) == ("two", None, 1)
    assert [(l["new_value"], l["source_name"]) for l in logs] == [("two", "set_priority:None")], logs
    assert len(_mark_lines(db)) == 2, "one mark line a pin that moved"


def test_a_pin_on_the_source_already_shown_writes_its_line_and_no_entry(db):
    _say(db, "f1.csv", {"a": "one"})
    _say(db, "f2.csv", {"a": "two"})
    rows, logs, _gone = _pin(db, "f2.csv")
    assert (_row(db).a, _mark(db), logs, len(rows)) == ("two", (True, "f2.csv"), [], 1)
    assert len(_mark_lines(db)) == 1, "a pin set is a mark line though the shown value stays"


def test_a_source_with_no_line_on_the_cell_is_skipped(db):
    _say(db, "f1.csv", {"a": "one", "b": "bee"})
    _say(db, "f2.csv", {"b": "two"})
    rows, logs, _gone = _pin(db, "f2.csv", columns=("a",))
    assert (_row(db).a, _mark(db), rows, logs, _mark_lines(db)) == ("one", None, [], [], [])


def test_taking_off_no_pin_writes_no_line(db):
    _say(db, "f1.csv", {"a": "one"})
    rows, logs, _gone = _pin(db, None)
    assert (_row(db).a, _mark(db), len(rows), logs, _mark_lines(db)) == ("one", None, 1, [], [])


def test_a_persons_cell_keeps_its_overwrite_mark_when_the_pin_comes_off(db):
    _say(db, "f1.csv", {"a": "one"})
    _say(db, crud.USER_SOURCE, {"a": "mine"})
    assert (_row(db).a, _mark(db)) == ("mine", (True, None)), "canary: a person's write marks its cell"
    _pin(db, "f1.csv")
    assert (_row(db).a, _mark(db)) == ("one", (True, "f1.csv"))
    _pin(db, None)
    assert (_row(db).a, _mark(db)) == ("mine", (True, None))


def test_only_the_cells_whose_pin_moved_are_on_the_line(db):
    _say(db, "f1.csv", {"a": "one", "b": "bee"})
    _say(db, "f2.csv", {"a": "two", "b": "two"})
    _pin(db, "f1.csv", columns=("a",))
    rows, logs, _gone = _pin(db, "f1.csv", columns=("a", "b"))       # a: toggled off · b: pinned
    assert (_row(db).a, _row(db).b, _mark(db, "a"), _mark(db, "b")) == ("two", "bee", None, (True, "f1.csv"))
    assert sorted((l["column_name"], l["source_name"]) for l in logs) == [
        ("a", "set_priority:None"), ("b", "set_priority:f1.csv")], logs
