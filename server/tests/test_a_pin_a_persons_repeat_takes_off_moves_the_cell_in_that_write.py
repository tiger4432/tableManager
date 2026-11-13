# -*- coding: utf-8 -*-
"""The merge covers the columns a write touched (lead 11-12 b) - its lines' columns AND the cells whose pin it took
off. A person re-sending the value it already says writes no line (a repeat), yet takes the cell's pin off; the cell's
shown value moves to the person's in that same write. A merge narrowed to the lines' columns would leave the pinned
value standing."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from conftest import retire_dynamic_model
from database import crud, models, schemas
from database.database import Base

TABLE = "zz_pin_repeat"
COLUMNS = {"k": "string", "job": "string", "n": "string", "m": "string"}
CONFIG = {TABLE: {"business_key": "k", "composite_key_source": ["job"], "column_types": COLUMNS,
                  "display_columns": list(COLUMNS)}}


@pytest.fixture(name="db")
def fixture_db():
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(TABLE)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(CONFIG)
    crud.TABLE_CONFIG.update(CONFIG)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    from tests.support import line_tables

    line_tables.build(engine, TABLE)                                   # the product's shape: a table keeps lines
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(TABLE)


def _write(db, updates, source, row_id=None):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=row_id, updates=updates, source_name=source, updated_by="probe")]))
    db.commit()


def _row(db, row_id):
    db.expire_all()
    return db.query(models.DYNAMIC_TABLES[TABLE]).filter_by(row_id=row_id).one()


def test_a_persons_repeat_takes_the_pin_off_and_the_cell_moves_in_that_write(db):
    model = models.DYNAMIC_TABLES[TABLE]
    _write(db, {"job": "J1", "n": "a", "m": "x"}, "file_a.csv")
    row_id = db.query(model).filter_by(job="J1").one().row_id
    _write(db, {"job": "J1", "n": "u"}, crud.USER_SOURCE, row_id=row_id)
    assert _row(db, row_id).n == "u", "CANARY: the person's value shows"
    crud.set_cell_manual_priority_batch(db, TABLE, [{"row_id": row_id, "column_name": "n"}], "file_a.csv")
    assert (_row(db, row_id).n, _row(db, row_id).m) == ("a", "x"), "CANARY: the pin shows file_a's value"
    _write(db, {"job": "J1", "n": "u"}, crud.USER_SOURCE, row_id=row_id)   # a repeat: no line, the pin comes off
    assert _row(db, row_id).n == "u"
