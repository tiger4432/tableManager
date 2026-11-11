# -*- coding: utf-8 -*-
"""A row made on an id that still holds layers (an orphan's - a row removed before its layers were) computes from
them (QA 11-08): the batch prefetch reads the layers of an id it was handed and found no row for, so the new row shows
what its stored person's layer and pin say, not the incoming file's value. «Is this a new, empty row» has one answer -
the id was not read (the old door's read-cell set) - for the cell read and the COPY alike.
"""
from datetime import datetime

import pytest
import uuid6
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from conftest import retire_dynamic_model
from database import crud, models, schemas
from database.database import Base

TABLE = "zz_orphan_row"
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


def test_a_row_made_on_an_orphans_id_shows_what_its_layers_and_pin_say(db):
    orphan = str(uuid6.uuid7())
    db.add(models.CellSource(table_name=TABLE, row_id=orphan, column_name="n", source_name="user", value="person",
                             updated_by="u", ingested_at=datetime(2026, 8, 1)))
    db.add(models.CellOverwrite(table_name=TABLE, row_id=orphan, column_name="n", is_overwrite=True, updated_by="u",
                                updated_at=datetime(2026, 8, 1), manual_priority_source="user"))
    db.commit()
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        row_id=orphan, updates={"job": "J9", "n": "file"}, source_name="f.csv", updated_by="t")]))
    db.commit()
    row = db.query(models.DYNAMIC_TABLES[TABLE]).filter_by(row_id=orphan).one()
    layers = {s.source_name: s.value for s in db.query(models.CellSource).filter_by(
        table_name=TABLE, row_id=orphan, column_name="n")}
    assert layers == {"user": "person", "f.csv": "file"}, "canary: both layers stored"
    assert row.n == "person", "the pinned person's layer shows"


def test_a_row_made_on_a_new_id_still_reads_nothing(db):
    """The minted id is not read - its cells are known empty, no SELECT of its layers (총괄 bce43236b)."""
    from sqlalchemy import event

    asked = []
    hook = lambda conn, cursor, statement, *_: asked.append(statement)        # noqa: E731
    event.listen(db.get_bind(), "before_cursor_execute", hook)
    try:
        crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            updates={"job": "J1", "n": "file"}, source_name="f.csv", updated_by="t")]))
        db.commit()
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", hook)
    assert asked, "canary: statements were seen"
    assert not [s for s in asked if s.lstrip().upper().startswith("SELECT") and "FROM cell_sources" in s], asked
    assert db.query(models.DYNAMIC_TABLES[TABLE]).one().n == "file"
