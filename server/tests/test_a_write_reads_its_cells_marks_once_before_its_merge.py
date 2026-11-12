# -*- coding: utf-8 -*-
"""A write that asks other sources (a file's, a chain's) reads its cells' cell_overwrites rows once before its merge:
step 2 reads them for the pins, step 4½ (`_marks`) takes that read - nothing writes cell_overwrites between the two
(lead 11-12 ㄷ: the fold page read cell_overwrites three times a write). The merge's own read of the pins is the
other one (it follows step 4½'s writes)."""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from conftest import retire_dynamic_model
from database import crud, models, schemas
from database.database import Base

TABLE = "zz_marks_once"
N = 50
COLUMNS = {"k": "string", "a": "string", "b": "string"}
CONFIG = {TABLE: {"business_key": "k", "column_types": COLUMNS, "display_columns": list(COLUMNS)}}


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

    line_tables.build(engine, TABLE)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(TABLE)


def _write(db, source, value):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val="K%d" % i, updates={"k": "K%d" % i, "a": value}, source_name=source, updated_by="probe")
        for i in range(N)]))
    db.commit()


@pytest.mark.parametrize("source", ["f2.csv", crud.CHAIN_SOURCE])
def test_a_write_asking_other_sources_reads_cell_overwrites_once_before_its_merge(db, source):
    _write(db, "f1.csv", "1")
    seen = []
    listen = lambda conn, cursor, statement, *a: seen.append(statement)   # noqa: E731
    event.listen(db.get_bind(), "before_cursor_execute", listen)
    try:
        _write(db, source, "2")
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listen)
    db.expire_all()
    assert {r.a for r in db.query(models.DYNAMIC_TABLES[TABLE]).all()} == {"2"}, "CANARY: the write moved the cells"
    read = [s for s in seen if s.lstrip().upper().startswith("SELECT") and "cell_overwrites" in s]
    assert len(read) == 2, read                 # step 2 (pins, taken by step 4½) and the merge's pins
