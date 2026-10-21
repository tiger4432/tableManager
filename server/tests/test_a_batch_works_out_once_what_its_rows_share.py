# -*- coding: utf-8 -*-
"""총괄 249b43409 ㄱ': the write door works out ONCE per batch what is the same for all its rows -
a source's declared rank, whether the model holds a column - and every row still gets its own answer.

  ranks     one batch, sources of two ranks in either order on one cell: the declared rank wins,
            not the newer layer - a memo that answers one source for another picks the newer
  unmapped  one batch, a column the model holds and one it does not on every row: the one it does
            not is dropped on each row by name, the others are written
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import retire_dynamic_model                            # noqa: E402
from database import crud, models, schemas                           # noqa: E402
from database.database import Base                                   # noqa: E402

TABLE = "bp_rows"
CONFIG = {TABLE: {"business_key": "k", "composite_key_source": ["k"],
                  "column_types": {"k": "string", "n": "string"}, "display_columns": ["k", "n"],
                  "source_priority": {"high": 0, "low": 5}}}


@pytest.fixture(name="db")
def fixture_db():
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(TABLE)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(CONFIG)
    crud.TABLE_CONFIG.update(CONFIG)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(TABLE)


def _item(source, **cells):
    return schemas.GeneralUpdateItem(updates=cells, source_name=source, updated_by="probe")


def test_each_source_keeps_its_own_rank_in_one_batch(db):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        _item("high", k="A", n="high first"), _item("low", k="A", n="low later"),
        _item("low", k="B", n="low first"), _item("high", k="B", n="high later"),
        _item("low", k="C", n="low alone")]))
    db.commit()
    shown = {row.business_key_val: row.n for row in db.query(models.DYNAMIC_TABLES[TABLE])}
    assert shown == {"A": "high first", "B": "high later", "C": "low alone"}, shown


def test_a_column_the_model_does_not_hold_is_dropped_on_each_row(db):
    crud.TABLE_CONFIG[TABLE] = dict(CONFIG[TABLE], column_types=dict(
        CONFIG[TABLE]["column_types"], late="string"))
    assert "late" not in models.DYNAMIC_TABLES[TABLE].__table__.columns
    drop = {}
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        _item("high", k=key, n="v" + key, late="x") for key in ("A", "B", "C")], silent=True),
        None, drop)
    db.commit()
    shown = {row.business_key_val: row.n for row in db.query(models.DYNAMIC_TABLES[TABLE])}
    layers = {(layer.row_id, layer.column_name) for layer in db.query(models.CellSource).filter_by(
        table_name=TABLE)}
    assert shown == {"A": "vA", "B": "vB", "C": "vC"}, shown
    assert {column for _row, column in layers} == {"k", "n"} and len(layers) == 6, layers
    assert drop["by_reason"] == {crud.DROP_UNMAPPED_COLUMN: 3} and drop["by_column"] == {"late": 3}, drop
