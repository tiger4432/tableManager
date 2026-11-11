# -*- coding: utf-8 -*-
"""A layer stored «""» before the write boundary folded blanks (box: 67 of 07-17 ~ 08-07) can still win a cell: the
cell shows None, not "" (총괄 11-05 (a)+(b)) - the value a cell shows from its layers passes `crud.none_if_blank`
(`compute_priority_value`), and so does a merged row's moved value.

  door that puts a stored value on the row        the cell
  a file writing the same cell (the "" ranks)     None
  another layer deleted                           None
  a key merge moving the row's ""                 nothing moved - the holder keeps its value, as for None
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from conftest import retire_dynamic_model
from database import crud, models, schemas
from database.database import Base

TABLE = "zz_old_blank"
COLUMNS = {"k": "string", "job": "string", "n": "string"}
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


def _old_blank(db, job="J1", shown=None):
    """A row whose «n» holds a person's "" layer stored before the fold, beside a file's «f» - planted as it sits on
    the box. `shown`: what the row itself holds («f» until a door re-answers the cell)."""
    model = models.DYNAMIC_TABLES[TABLE]
    _write(db, {"job": job, "n": "f"}, "file_a.csv")
    row = db.query(model).filter_by(job=job).one()
    db.add(models.CellSource(table_name=TABLE, row_id=row.row_id, column_name="n", source_name=crud.USER_SOURCE,
                             value="", updated_by="probe", ingested_at=datetime(2026, 7, 17, tzinfo=timezone.utc)))
    if shown is not None:
        db.query(model).filter_by(row_id=row.row_id).update({"n": shown})
    db.commit()
    assert db.query(model).filter_by(row_id=row.row_id).one().n == (shown if shown is not None else "f"), "CANARY: the row before a door"
    return row.row_id


def _shown(db, row_id):
    db.expire_all()
    return db.query(models.DYNAMIC_TABLES[TABLE]).filter_by(row_id=row_id).one().n


def test_a_file_writing_the_cell(db):
    row_id = _old_blank(db)
    _write(db, {"job": "J1", "n": "g"}, "file_b.csv")
    assert _shown(db, row_id) is None


def test_another_layer_deleted(db):
    row_id = _old_blank(db)
    crud.delete_cell_source_batch(db, TABLE, [{"row_id": row_id, "column_name": "n"}], "file_a.csv")
    db.commit()
    assert _shown(db, row_id) is None


@pytest.mark.parametrize("held", ["", None])
def test_a_key_merge_moves_a_blank_as_it_moves_none(db, held):
    """A merged row's blank («""» held before the fold, or None) moves nothing - the holder keeps its value."""
    _write(db, {"job": "J0", "n": "h"}, "file_c.csv")
    holder = db.query(models.DYNAMIC_TABLES[TABLE]).filter_by(job="J0").one().row_id
    merged = _old_blank(db, job="J5", shown="")
    if held is None:
        db.query(models.DYNAMIC_TABLES[TABLE]).filter_by(row_id=merged).update({"n": None})
        db.commit()
    _write(db, {"job": "J0"}, "chain:m", row_id=merged)                   # J5 re-keyed onto J0: merged into it
    assert [row.row_id for row in db.query(models.DYNAMIC_TABLES[TABLE])] == [holder]
    assert _shown(db, holder) == "h"
