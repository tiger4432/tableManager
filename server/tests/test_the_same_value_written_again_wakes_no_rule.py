# -*- coding: utf-8 -*-
"""총괄 f5ff1e3e9 ㄴ: a row that keeps its value stages no outbox event. The flush hook staged one for a row handed
the value it already held - with no column names, which wakes every rule on the table - and the cell menu's layer
delete and pin did that hand-back on every cell whose shown value did not move. A time column on PostgreSQL is where
the doors matter on their own: the row holds a datetime and the layer its text, so a hand-back reads as an edit."""
import uuid

import pytest
from sqlalchemy import MetaData, text

from database import crud, models, schemas
from database.models import DatabaseOutbox
import event_constants

pytestmark = pytest.mark.pg
TABLE = "same_again_probe"
ENTRY = {"business_key": "k", "composite_key_source": ["k"],
         "column_types": {"k": "string", "d": "datetime", "s": "string"}}
OLDER, NEWER = "2026-10-22T10:00:00+09:00", "2026-10-23T10:00:00+09:00"


def _events(db):
    db.expire_all()
    return [(e.event_type, sorted((e.payload or {}).get(event_constants.OLD_VALUES_KEY) or ()))
            for e in db.query(DatabaseOutbox).filter(DatabaseOutbox.table_name == TABLE).order_by(DatabaseOutbox.id)]


@pytest.fixture
def world(pg_engine, pg_session, monkeypatch):
    from conftest import PG_TEST_SCHEMA

    models.init_dynamic_models({TABLE: ENTRY})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[TABLE].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    try:
        yield pg_session
    finally:
        pg_session.rollback()
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))


def _write(db, source, **cells):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val="K", updates=dict(cells, k="K"), source_name=source, updated_by="probe")],
        transaction_id=str(uuid.uuid4())))
    db.commit()


def _row(db):
    db.expire_all()
    return db.query(models.DYNAMIC_TABLES[TABLE]).one()


def _a_file_layer_under_a_persons(db):
    _write(db, "lot_a.csv", d=OLDER, s="file")
    _write(db, "user", d=NEWER, s="person")
    row = _row(db)
    assert (row.d.isoformat(), row.s) == (NEWER, "person")             # canary: the person's layer is shown
    return row.row_id, len(_events(db))


def test_a_row_handed_the_value_it_holds_stages_no_event(world):
    db = world
    _write(db, "lot_a.csv", s="kept")
    before = len(_events(db))
    row = _row(db)
    row.s = row.s
    assert row in db.dirty                                            # the hand-back the doors did
    db.commit()
    assert _events(db)[before:] == []
    row = _row(db)
    row.s = "moved"
    db.commit()
    assert _events(db)[before:] == [("EDIT", ["s"])]                  # canary: a real change still stages its edit


@pytest.mark.parametrize("door", ["delete the file layer", "pin the shown layer"])
def test_a_cell_menu_door_that_leaves_the_shown_value_stages_no_event(world, door):
    db = world
    row_id, before = _a_file_layer_under_a_persons(db)
    if door == "delete the file layer":
        crud.delete_cell_source_batch(db, TABLE, [{"row_id": row_id, "column_name": "d"}], "lot_a.csv")
    else:
        crud.set_cell_manual_priority_batch(db, TABLE, [{"row_id": row_id, "column_name": "d"}], "user", "probe")
    db.commit()
    assert _row(db).d.isoformat() == NEWER
    assert _events(db)[before:] == []


@pytest.mark.parametrize("door", ["delete the person's layer", "pin the file layer"])
def test_a_cell_menu_door_that_moves_the_shown_value_stages_its_edit(world, door):
    db = world
    row_id, before = _a_file_layer_under_a_persons(db)
    if door == "delete the person's layer":
        crud.delete_cell_source_batch(db, TABLE, [{"row_id": row_id, "column_name": "d"}], "user")
    else:
        crud.set_cell_manual_priority_batch(db, TABLE, [{"row_id": row_id, "column_name": "d"}], "lot_a.csv", "probe")
    db.commit()
    assert _row(db).d.isoformat() == OLDER
    assert _events(db)[before:] == [("EDIT", ["d"])]
