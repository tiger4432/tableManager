# -*- coding: utf-8 -*-
"""총괄 bce43236b: a row THIS batch created has no stored cell history, so its later items read the
batch's own caches instead of one SELECT per cell. (Its oracle - the old door's cache against the database -
retired with that door, 11-11.)

  and what it saves             a value then a hold for each of 200 new rows asks the stored
                                history nothing (it was one SELECT a cell: ~2,000 for 1,000 rows)
"""
import os
import sys

import pytest
from sqlalchemy import MetaData, event, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
from database import crud, models, schemas                           # noqa: E402

pytestmark = pytest.mark.pg
TABLE = "bw_rows"
COLUMNS = {"k": "string", "job": "string", "x": "number", "y": "number", "netdie": "number",
           "hold": "string"}
CONFIG = {TABLE: {"business_key": "k", "composite_key_source": ["job", "x", "y"],
                  "column_types": COLUMNS, "display_columns": list(COLUMNS)}}
VOLATILE = {"transaction_id", "timestamp", "created_at", "updated_at", "processed_at",
            "broadcast_at", "event_uuid", "ingested_at", "id", "tx_id"}


@pytest.fixture(name="world")
def fixture_world(pg_engine):
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"),
                            {"s": PG_TEST_SCHEMA}).scalar() == 1
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(TABLE)
    models.init_dynamic_models(CONFIG)
    crud.TABLE_CONFIG.update(CONFIG)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[TABLE].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    try:
        yield {"db": session, "engine": pg_engine}
    finally:
        session.close()
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(TABLE)


def _item(updates, source, row_id=None):
    return schemas.GeneralUpdateItem(row_id=row_id, updates=updates, source_name=source,
                                     updated_by="probe")


def _keys(job):
    return {"job": job, "x": 1, "y": 2}


def test_a_rows_later_items_ask_the_stored_history_nothing(world):
    """The copy rule's shape: a value item then a hold item per row, under two sources."""
    asked = []

    def count(conn, cursor, statement, *args):
        if "FROM cell_sources" in statement or "FROM cell_overwrites" in statement:
            asked.append(statement)
    event.listen(world["engine"], "before_cursor_execute", count)
    try:
        crud.apply_batch_updates(world["db"], TABLE, schemas.GeneralUpdateBatch(updates=[
            item for i in range(200) for item in (
                _item({**_keys("J%03d" % i), "netdie": i}, "chain:copy"),
                _item({**_keys("J%03d" % i), "hold": "h"}, "chain:copy:hold"))]))
        world["db"].commit()
    finally:
        event.remove(world["engine"], "before_cursor_execute", count)
    with world["engine"].connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM "%s"."%s"' % (PG_TEST_SCHEMA, TABLE))).scalar() == 200
    assert len(asked) <= 2, (len(asked), asked[:2])
