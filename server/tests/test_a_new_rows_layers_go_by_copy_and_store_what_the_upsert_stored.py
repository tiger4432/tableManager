# -*- coding: utf-8 -*-
"""Lead 11-07 (pfab ㉡): the layers of rows THIS batch inserted go by COPY; every other layer is upserted as before.

  the answer    a batch mixing new rows and stored rows stores the same layers - cell by cell - as the upsert alone
  the orphans   a new row whose id already holds layers (box 11-07: 25 of 58 tables) is upserted over them, not refused
  the refusal   a unique conflict inside the COPY itself is an IntegrityError - the class the catching seats name
  the canary    the mixed batch sent some layers by COPY and some by upsert
"""
import datetime
import json
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
ODD = "tab\there\nnewline \\ back 'quote' \"dq\" 한글"


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


def _write(db, rows, source):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=r, source_name=source, updated_by="probe") for r in rows]))
    db.commit()


def _story(db):
    _write(db, [{"k": "r%d" % i, "a": i, "b": "b%d" % i} for i in range(6)], "f1.csv")             # all new
    _write(db, [{"k": "r%d" % i, "a": 100 + i, "b": ODD} for i in range(3)]                      # stored, same layer
           + [{"k": "n%d" % i, "a": i, "b": ODD if i else None} for i in range(3)], "f1.csv")    # new, one blank
    _write(db, [{"k": "r0", "a": 7}, {"k": "n1", "b": "second"}, {"k": "m0", "a": 1}], "f2.csv")  # a second source


def _layers(engine):
    with engine.connect() as conn:
        keys = dict(conn.execute(text('SELECT row_id, k FROM "%s"."%s"' % (PG_TEST_SCHEMA, TABLE))).fetchall())
        return {(keys[r[0]], r[1], r[2]): (r[3], r[4], r[5], r[6]) for r in conn.execute(text(
            "SELECT row_id, column_name, source_name, value::text, updated_by, origin_row_id, ingested_at IS NULL "
            'FROM "%s".cell_sources WHERE table_name = :t' % PG_TEST_SCHEMA), {"t": TABLE})}


def _cells(engine):
    with engine.connect() as conn:
        return sorted(conn.execute(text('SELECT k, a, b FROM "%s"."%s"' % (PG_TEST_SCHEMA, TABLE))).fetchall())


def test_a_mixed_batch_stores_by_copy_what_the_upsert_alone_stored(world, monkeypatch):
    db, engine = world["db"], world["engine"]
    sends = []
    real_send = crud._pg_multirow_upsert
    monkeypatch.setattr(crud, "_pg_multirow_upsert",
                        lambda *a, **k: sends.append(bool(k.get("copy"))) or real_send(*a, **k))
    _story(db)
    by_copy, cells_by_copy = _layers(engine), _cells(engine)
    assert True in sends and False in sends, sends                      # canary: both doors were taken
    _clear(engine)

    real = crud.bulk_upsert_cell_sources
    monkeypatch.setattr(crud, "bulk_upsert_cell_sources",
                        lambda db_, mappings, chunk_size=crud.BULK_CHUNK_SIZE, new_rows=frozenset():
                        real(db_, mappings, chunk_size))
    _story(db)
    by_upsert, cells_by_upsert = _layers(engine), _cells(engine)

    assert len(by_upsert) > 20 and by_copy == by_upsert
    assert cells_by_copy == cells_by_upsert
    assert [k for k, (v, *_) in by_copy.items() if v and json.loads(v) == ODD]  # the escaped text came back whole


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


