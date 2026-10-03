# -*- coding: utf-8 -*-
"""총괄 1495534c9: a write's layer dict always carries `origin_row_id` (09-16, e1318d28d) and a
merge's did not, so a batch holding both sent `bulk_upsert_cell_sources` a ragged list - a
CompileError when the first mapping in sort order had the key, the whole chunk's origin NULL
without a word when it had not. A merge carries it now (the shell's layer keeps its own; a
person's backup none), and the one upsert seat gives every mapping the same keys."""
import os
import sys

import pytest
from sqlalchemy import MetaData, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
from database import crud, models, schemas                           # noqa: E402

LOW, HIGH = "00000000-0000-7000-8000-000000000001", "ffffffff-ffff-7fff-bfff-fffffffffff1"
SHELL = "88888888-8888-7888-8888-888888888888"
SAFE = "xscope_safe_map"                      # conftest's sqlite table: key [lot, slot, cx, cy]
PG_TABLE = "zz_origin_merge"


def _write(db, table, items):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=row_id, updates=updates, source_name=source,
                                  updated_by="t", origin_row_id=origin)
        for row_id, updates, source, origin in items]))
    db.commit()


def _cell(lot, cx, bn):
    return {"lot": lot, "slot": "1", "cx": cx, "cy": 1, "bn": bn}


def _scenario(db, table, holder_first):
    """The holder, a shell and a third row; then ONE batch: a write to the third row and a
    write that moves the shell's key part onto the holder's key (a merge)."""
    holder, other = (LOW, HIGH) if holder_first else (HIGH, LOW)
    _write(db, table, [(holder, _cell("L1", 1, "h"), "chain:a", "SRC-H"),
                       (SHELL, _cell("L1", 2, "s"), "chain:a", "SRC-S"),
                       (other, _cell("L9", 9, "o"), "chain:a", "SRC-O")])
    _write(db, table, [(other, {"bn": "o2"}, "chain:b", "SRC-O2"),
                       (SHELL, {"cx": 1}, "chain:b", "SRC-S2")])
    layers = {(row_id, column, source): origin for row_id, column, source, origin in db.execute(
        text("SELECT row_id, column_name, source_name, origin_row_id FROM cell_sources "
             "WHERE table_name = :t"), {"t": table})}
    rows = sorted(r for (r,) in db.execute(text('SELECT row_id FROM "%s"' % table)))
    return holder, other, rows, layers


def _gate(db, table, holder_first):
    holder, other, rows, layers = _scenario(db, table, holder_first)
    assert rows == sorted([holder, other]), rows                       # the shell merged
    assert layers[(other, "bn", "chain:b")] == "SRC-O2"                # the write keeps its origin
    inherited = {origin for (row_id, column, source), origin in layers.items()
                 if row_id == holder and column == "bn" and source.startswith("chain:a")
                 and source != "chain:a"}
    assert inherited == {"SRC-S"}, layers                              # the shell's layer keeps its own


@pytest.mark.parametrize("holder_first", [True, False], ids=["holder-sorts-first", "write-sorts-first"])
def test_a_merge_and_a_write_in_one_batch_keep_every_origin_sqlite(db_session, holder_first):
    _gate(db_session, SAFE, holder_first)


@pytest.mark.parametrize("first_has_it", [True, False], ids=["first-has-origin", "first-lacks-origin"])
def test_the_upsert_seat_gives_a_ragged_list_one_key_set(db_session, first_has_it):
    """The seat itself, with a list a future site might send ragged again: no error, and the
    mapping that carries an origin keeps it."""
    def layer(row_id, **more):
        return {"table_name": SAFE, "row_id": row_id, "column_name": "bn", "source_name": "x",
                "value": "v", "updated_by": "t", "ingested_at": None, **more}

    with_origin, without = layer(LOW, origin_row_id="SRC-1"), layer(HIGH)
    if not first_has_it:
        with_origin, without = layer(HIGH, origin_row_id="SRC-1"), layer(LOW)
    crud.bulk_upsert_cell_sources(db_session, [with_origin, without])
    db_session.commit()
    origins = dict(db_session.execute(text(
        "SELECT row_id, origin_row_id FROM cell_sources WHERE table_name = :t"), {"t": SAFE}).all())
    assert origins == {with_origin["row_id"]: "SRC-1", without["row_id"]: None}, origins


@pytest.fixture(name="pg_db")
def fixture_pg_db(pg_engine):
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"),
                            {"s": PG_TEST_SCHEMA}).scalar() == 1
    config = {PG_TABLE: {"business_key": "cell_key", "composite_key_source": ["lot", "slot", "cx", "cy"],
                         "composite_key_separator": "_",
                         "column_types": {"cell_key": "string", "lot": "string", "slot": "string",
                                          "cx": "number", "cy": "number", "bn": "string"}}}
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(PG_TABLE)
    models.init_dynamic_models(config)
    crud.TABLE_CONFIG.update(config)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[PG_TABLE].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    try:
        yield session
    finally:
        session.close()
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, PG_TABLE)))
            for side in ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox"):
                conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t'
                                  % (PG_TEST_SCHEMA, side)), {"t": PG_TABLE})
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(PG_TABLE)


@pytest.mark.pg
@pytest.mark.parametrize("holder_first", [True, False], ids=["holder-sorts-first", "write-sorts-first"])
def test_a_merge_and_a_write_in_one_batch_keep_every_origin_pg(pg_db, holder_first):
    _gate(pg_db, PG_TABLE, holder_first)
