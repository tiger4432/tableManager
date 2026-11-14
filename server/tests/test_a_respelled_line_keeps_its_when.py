# -*- coding: utf-8 -*-
"""A write item's `at` keeps a line's «when» from the line it re-spells (design «쓰기» - the notation fold and the
file-layer fold): the new line heads the cell, its source's rank does not move, the old line stays as history, and
the audit row says when the fold was done."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from database import crud, lines, models
from database.database import Base
from database.write_lines import write_lines
from test_write_lines_writes_a_line_a_change_and_its_current_line import ticking_clock

TABLE = "at_line"
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


def _write(db, items, tx):
    answer = write_lines(db, TABLE, items, kind="funnel", transaction_id=tx)
    db.commit()
    return answer


def test_a_respelled_line_keeps_its_when_and_its_rank(db):
    _write(db, [{"key": {"k": "K1"}, "values": {"k": "K1", "a": "old one"}, "source_name": "f1.csv"}], "t1")
    _write(db, [{"key": {"k": "K1"}, "values": {"a": "two"}, "source_name": "f2.csv"}], "t2")
    ln = lines.shape(db, TABLE, CFG)["lines"]
    row_id, when = db.execute(select(ln.c.row_id, ln.c.at).where(ln.c.source_name == "f1.csv")).one()
    answer = _write(db, [{"row_id": row_id, "values": {"a": "one"}, "source_name": "f1.csv", "at": when}], "fold")
    got = db.execute(select(ln.c.at, ln.c.v_a, ln.c.head_0).where(ln.c.source_name == "f1.csv")
                     .order_by(ln.c.line_id)).all()
    assert [(at, value) for at, value, _head in got] == [(when, "old one"), (when, "one")], "the old line stays"
    assert (got[0][2] & got[1][2]) == 0 and got[1][2] != 0, "the new line heads the cell"
    layers = lines.layers(db, TABLE, [row_id], ["a"])[(row_id, "a")]
    assert (layers["f1.csv"]["value"], layers["f2.csv"]["value"]) == ("one", "two")
    shown = db.execute(select(lines.shape(db, TABLE, CFG)["table"].c.a)).scalar()
    assert shown == "two", "f1's rank did not move - f2 is still the newer"
    naive = [t.replace(tzinfo=None) for t in (answer["at"], when)]   # sqlite reads the column back without a zone
    assert naive[0] > naive[1] + timedelta(seconds=1), "the batch keeps when the fold was done"
