# -*- coding: utf-8 -*-
"""Lead 11-07 (pfab ㉡): the layers of rows THIS batch inserted go by COPY; every other layer is upserted as before.

  the orphans   a new row whose id already holds layers (box 11-07: 25 of 58 tables) is upserted over them, not refused
  the refusal   a unique conflict inside the COPY itself is an IntegrityError - the class the catching seats name
  the chunks    the COPY goes a chunk at a time, each counted in the request's database time (QA 11-08)
"""
import datetime
import os
import sys

import psycopg2
import pytest
import uuid6
from sqlalchemy import MetaData, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
from database import crud, models, schemas                           # noqa: E402

pytestmark = pytest.mark.pg
TABLE = "nc_cells"
COLUMNS = {"k": "string", "a": "number", "b": "string"}
CONFIG = {TABLE: {"business_key": "k", "composite_key_source": ["k"], "column_types": COLUMNS,
                  "display_columns": list(COLUMNS)}}


@pytest.fixture(name="world")
def fixture_world(pg_engine):
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
        _clear(pg_engine)
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(TABLE)


def _clear(engine):
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
        for table in ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox"):
            conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t' % (PG_TEST_SCHEMA, table)), {"t": TABLE})


def test_a_new_row_whose_id_holds_orphan_layers_is_written_over_them(world, monkeypatch):
    db, engine = world["db"], world["engine"]
    row_id = str(uuid6.uuid7())
    with engine.begin() as conn:                                        # layers left under an id no row carries
        for column, source in (("a", "f9.csv"), ("b", "old.csv")):
            conn.execute(text('INSERT INTO "%s".cell_sources (table_name, row_id, column_name, source_name, value, '
                              "updated_by) VALUES (:t, :r, :c, :s, '1', 'seed')" % PG_TEST_SCHEMA),
                         {"t": TABLE, "r": row_id, "c": column, "s": source})
    sends = []
    real_send = crud._pg_multirow_upsert
    monkeypatch.setattr(crud, "_pg_multirow_upsert",
                        lambda *a, **k: sends.append(bool(k.get("copy"))) or real_send(*a, **k))
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=row_id, updates={"k": "z1", "a": 5, "b": "x"}, source_name="f9.csv",
                                  updated_by="probe"),
        schemas.GeneralUpdateItem(updates={"k": "z2", "a": 6, "b": "y"}, source_name="f9.csv", updated_by="probe")]))
    db.commit()
    assert sends == [True, False], sends                                # z2 by COPY, the orphan's row by the upsert
    with engine.connect() as conn:
        assert conn.execute(text('SELECT k, a, b FROM "%s"."%s" WHERE row_id = :r' % (PG_TEST_SCHEMA, TABLE)),
                            {"r": row_id}).fetchall() == [("z1", 5, "x")]
        layers = dict(((c, s), v) for c, s, v in conn.execute(text(
            'SELECT column_name, source_name, value::text FROM "%s".cell_sources WHERE row_id = :r' % PG_TEST_SCHEMA),
            {"r": row_id}))
    assert layers[("a", "f9.csv")] == "5" and layers[("b", "f9.csv")] == '"x"' and layers[("b", "old.csv")] == "1"


def test_a_unique_conflict_inside_the_copy_is_an_integrity_error(world):
    db, engine = world["db"], world["engine"]
    row_id = str(uuid6.uuid7())
    layer = {"table_name": TABLE, "row_id": row_id, "column_name": "a", "source_name": "f9.csv", "value": 1,
             "updated_by": "probe", "ingested_at": datetime.datetime.now(datetime.timezone.utc), "origin_row_id": None}
    with engine.begin() as conn:
        conn.execute(text('INSERT INTO "%s".cell_sources (table_name, row_id, column_name, source_name, value, '
                          "updated_by) VALUES (:t, :r, 'a', 'f9.csv', '1', 'seed')" % PG_TEST_SCHEMA),
                     {"t": TABLE, "r": row_id})
    with pytest.raises(IntegrityError) as caught:                       # the class the three catching seats name
        crud._pg_multirow_upsert(db, models.CellSource.__table__, [layer], list(crud.CELL_SOURCE_CONFLICT_COLS),
                                 list(crud.CELL_SOURCE_UPDATE_COLS), crud.BULK_CHUNK_SIZE, copy=True)
    assert isinstance(caught.value.orig, psycopg2.errors.UniqueViolation)
    db.rollback()


def test_the_copy_goes_a_chunk_at_a_time_and_each_is_counted(world, monkeypatch):
    from runtime import request_timing

    db, engine = world["db"], world["engine"]
    told = []
    monkeypatch.setattr(request_timing, "add", lambda seconds, queries: told.append(queries))
    now = datetime.datetime.now(datetime.timezone.utc)
    layers = [{"table_name": TABLE, "row_id": str(uuid6.uuid7()), "column_name": "a", "source_name": "f9.csv",
               "value": n, "updated_by": "probe", "ingested_at": now, "origin_row_id": None} for n in range(5)]
    assert crud._pg_multirow_upsert(db, models.CellSource.__table__, layers, list(crud.CELL_SOURCE_CONFLICT_COLS),
                                    list(crud.CELL_SOURCE_UPDATE_COLS), 2, copy=True)
    db.commit()
    assert told == [1, 1, 1], told                                      # 2 + 2 + 1
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM "%s".cell_sources WHERE table_name = :t' % PG_TEST_SCHEMA),
                            {"t": TABLE}).scalar() == 5
