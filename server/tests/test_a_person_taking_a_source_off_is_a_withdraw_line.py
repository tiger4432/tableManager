# -*- coding: utf-8 -*-
"""A person taking a source off cells (`crud.delete_cell_source_batch`, the grid's «delete source») is a withdraw line
(cell-source overhaul): the cell shows what the other lines say; a pin on that source comes off; a person's own value
taken off takes its overwrite mark; the history entry names the moved cell, no before value."""
import pytest
from sqlalchemy import select

from database import crud, lines, models, schemas
from database.database import Base
from test_write_lines_writes_a_line_a_change_and_its_current_line import ticking_clock

TABLE = "ds_line"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string"}}


@pytest.fixture(name="db")
def fixture_db(db_session, monkeypatch):
    models.init_dynamic_models({TABLE: CFG})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    Base.metadata.create_all(bind=db_session.get_bind())
    lines.ensure_line_table(db_session, TABLE, CFG)
    db_session.commit()
    ticking_clock(monkeypatch)
    return db_session


def _say(db, source, value):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val="K1", updates={"k": "K1", "a": value}, source_name=source, updated_by="kim")]))


def _row(db):
    model = models.DYNAMIC_TABLES[TABLE]
    db.expire_all()
    return db.query(model).filter(model.business_key_val == "K1").one()


def _mark(db):
    m = db.query(models.CellOverwrite).filter_by(table_name=TABLE, row_id=_row(db).row_id, column_name="a").first()
    return None if m is None else (m.is_overwrite, m.manual_priority_source)


def _take(db, source):
    return crud.delete_cell_source_batch(db, TABLE, [{"row_id": _row(db).row_id, "column_name": "a"}], source)


def test_taking_the_shown_source_off_shows_the_next_and_says_so(db):
    _say(db, "f1.csv", "one")
    _say(db, "f2.csv", "two")
    rows, logs = _take(db, "f2.csv")
    ln = lines.shape(db, TABLE, CFG)["lines"]
    assert (_row(db).a, [r.row_id for r in rows]) == ("one", [_row(db).row_id])
    assert [(l["column_name"], l["new_value"], l["old_value"], l["source_name"]) for l in logs] == [
        ("a", "one", None, "delete_source:f2.csv")], logs
    assert db.execute(select(ln.c.source_name).where(ln.c.line_kind == "withdraw")).scalars().all() == ["f2.csv"]


def test_a_pin_on_the_source_comes_off_with_it(db):
    _say(db, "f1.csv", "one")
    _say(db, "f2.csv", "two")
    db.add(models.CellOverwrite(table_name=TABLE, row_id=_row(db).row_id, column_name="a", is_overwrite=False,
                                updated_by="kim", manual_priority_source="f2.csv"))
    db.commit()
    _take(db, "f2.csv")
    assert (_row(db).a, _mark(db)) == ("one", None)


def test_a_persons_value_taken_off_takes_its_mark(db):
    _say(db, "f1.csv", "one")
    _say(db, crud.USER_SOURCE, "mine")
    assert (_row(db).a, _mark(db)) == ("mine", (True, None)), "canary: a person's write marks its cell"
    _take(db, crud.USER_SOURCE)
    assert (_row(db).a, _mark(db)) == ("one", None)


def test_a_source_not_on_the_cell_changes_nothing(db):
    _say(db, "f1.csv", "one")
    rows, logs = _take(db, "f9.csv")
    assert (_row(db).a, logs, len(rows)) == ("one", [], 1)
