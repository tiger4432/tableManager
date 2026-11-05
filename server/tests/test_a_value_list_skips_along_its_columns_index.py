# -*- coding: utf-8 -*-
"""A column's value list (`grid_read.column_values`, 총괄 11-05) with nothing else narrowing and a btree leading on the
column reads one index probe per value (`_skipped_values`) - and answers what DISTINCT over the rows answers: sorted,
the blank cells ('' and NULL) one null at the end, the cap and `more` alike.

  column \\ index      (column, row_id) btree           none
  text with '' · NULL  skip == DISTINCT, skip used      DISTINCT (skip says None)
  number with NULL     skip == DISTINCT, skip used      DISTINCT
  any narrowing        DISTINCT (skip not asked)
"""
import pytest
from sqlalchemy import text

import grid_read
from conftest import retire_dynamic_model
from database import crud, models

pytestmark = pytest.mark.pg
TABLE = "zz_value_list"
ENTRY = {"business_key": "row_id", "column_types": {"lot": "string", "num": "number", "bare": "string"}}
LOTS = ["L3", "", None, "L1", "L1", "L2", None, "L10"]


@pytest.fixture(name="table")
def fixture_table(pg_session, monkeypatch):
    models.init_dynamic_models({TABLE: ENTRY})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    model = models.DYNAMIC_TABLES[TABLE]
    engine = pg_session.get_bind()
    model.__table__.create(bind=engine)
    try:
        pg_session.add_all([model(row_id="r%d" % n, lot=lot, bare=lot, num=None if lot is None else float(n % 3))
                            for n, lot in enumerate(LOTS)])
        pg_session.commit()
        with engine.begin() as c:
            c.execute(text('CREATE INDEX zz_value_list_lot ON "%s" (lot, row_id)' % TABLE))
            c.execute(text('CREATE INDEX zz_value_list_num ON "%s" (num, row_id)' % TABLE))
            c.execute(text('ANALYZE "%s"' % TABLE))
        assert pg_session.query(model).count() == len(LOTS), "CANARY: the rows"
        yield model
    finally:
        pg_session.rollback()
        model.__table__.drop(bind=engine)
        retire_dynamic_model(TABLE)


def _both(db, model, column, monkeypatch, **narrowing):
    skipped = []
    real = grid_read._skipped_values
    monkeypatch.setattr(grid_read, "_skipped_values", lambda *a: skipped.append(real(*a)) or skipped[-1])
    first = grid_read.column_values(db, TABLE, model, column, **narrowing)
    monkeypatch.setattr(grid_read, "_skipped_values", lambda *a: None)
    return first, grid_read.column_values(db, TABLE, model, column, **narrowing), skipped


@pytest.mark.parametrize("column, values", [("lot", ["L1", "L10", "L2", "L3", None]), ("num", [0.0, 1.0, 2.0, None])])
def test_the_skip_answers_as_distinct_does(pg_session, table, monkeypatch, column, values):
    skip, distinct, skipped = _both(pg_session, table, column, monkeypatch)
    assert skipped and skipped[0] is not None, "the skip was not taken - an index leads with %s" % column
    assert skip == distinct == {"column": column, "values": values, "more": False}


def test_the_cap_is_the_same_on_both(pg_session, table, monkeypatch):
    monkeypatch.setattr(grid_read, "VALUES_CAP", 2)
    skip, distinct, skipped = _both(pg_session, table, "lot", monkeypatch)
    assert skipped[0] is not None
    assert skip == distinct == {"column": "lot", "values": ["L1", "L10", None], "more": True}


def test_no_index_or_a_narrowing_reads_distinct(pg_session, table, monkeypatch):
    _, distinct, skipped = _both(pg_session, table, "bare", monkeypatch)
    assert skipped == [None] and distinct["values"] == ["L1", "L10", "L2", "L3", None]
    _, _, skipped = _both(pg_session, table, "lot", monkeypatch, search="1")
    assert skipped == [], "a search narrows - the skip is not asked"
