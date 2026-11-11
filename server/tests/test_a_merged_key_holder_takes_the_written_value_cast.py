"""총괄 88761926b: when a key edit makes a row collide with the row holding that key, the merge writes the edit's
values onto the holder CAST as every write casts them - a float 1.0 into a text column is «1», not «1.0»
(the old merge body set the raw value).
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.database import Base                                    # noqa: E402
from database import crud, models, schemas                            # noqa: E402

T = "zz_merge_cast"
CFG = {T: {"business_key": "map_pk", "composite_key_source": ["map_id", "die_no"], "composite_key_separator": "_",
           "column_types": {"map_pk": "string", "map_id": "string", "die_no": "string", "note": "string",
                            "qty": "number"}}}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(CFG)
    crud.TABLE_CONFIG.update(CFG)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _write(db, **item):
    crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        source_name="user", updated_by="someone", **item)]))
    db.commit()


def test_the_holder_takes_the_edit_cast(db):
    _write(db, updates={"map_id": "M1", "die_no": "3", "note": "a"})
    _write(db, updates={"map_id": "M1", "die_no": "4", "note": "b"})
    model = models.DYNAMIC_TABLES[T]
    mover = db.query(model).filter(model.business_key_val == "M1_4").one().row_id
    _write(db, row_id=mover, updates={"die_no": "3", "note": 1.0})          # collides with M1_3
    rows = [(r.business_key_val, r.note) for r in db.query(model).all()]
    assert rows == [("M1_3", "1")], rows


def test_a_refused_edit_value_is_said_and_the_merged_value_is_kept(db):
    """App QA of 1460cfef2 ①: a value the column refuses is dropped as before, and said - by the write door, before
    the merge (`update_item_as_line`; the old merge body that said it too retired with the lines, 11-11)."""
    _write(db, updates={"map_id": "M1", "die_no": "3", "qty": 5})
    _write(db, updates={"map_id": "M1", "die_no": "4", "qty": 7})
    model = models.DYNAMIC_TABLES[T]
    shell = db.query(model).filter(model.business_key_val == "M1_4").one().row_id
    report = {}
    crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        row_id=shell, updates={"die_no": "3", "qty": "abc"}, source_name="user", updated_by="someone")]),
        drop_report=report)
    db.commit()
    assert report["by_reason_column"] == {crud.DROP_VALUE_REFUSED: {"qty": 1}}, report
    assert report["refused_values"] == {"qty": {"cells": 1, "first": "abc"}}, report
    assert [(r.business_key_val, r.qty) for r in db.query(model).all()] == [("M1_3", 7)]
