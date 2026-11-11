# -*- coding: utf-8 -*-
"""총괄 10-24: the write funnel reads the stored layers of the columns its batch WRITES, not of every column - box
board B read six columns' 6,000 layers to write one column of 1,000 rows. (Its oracles - the old door's caches
against the database - retired with that door, 11-11.)

  what it saves       20 rows x 6 columns of layers, one column written: 20 layers read, not 120
"""
import json
import os
import sys

import pytest
from sqlalchemy import MetaData, event, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
from database import crud, models, schemas                           # noqa: E402

pytestmark = pytest.mark.pg
TABLE = "lr_cells"
COLUMNS = {"k": "string", "job": "string", "x": "number", "y": "number", "a": "number", "b": "string",
           "c": "string", "lot": "string"}
CONFIG = {TABLE: {"business_key": "k", "composite_key_source": ["job", "x", "y"], "map_key_columns": ["job"],
                  "column_types": COLUMNS, "display_columns": list(COLUMNS)}}
VOLATILE = {"transaction_id", "timestamp", "created_at", "updated_at", "processed_at",
            "broadcast_at", "event_uuid", "ingested_at", "id", "tx_id"}


@pytest.fixture(name="world")
def fixture_world(pg_engine, tmp_path, monkeypatch):
    import notation_norm
    from database import config_watcher

    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"),
                            {"s": PG_TEST_SCHEMA}).scalar() == 1
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(TABLE)
    models.init_dynamic_models(CONFIG)
    crud.TABLE_CONFIG.update(CONFIG)
    rules = tmp_path / "notation_rules.json"
    rules.write_text(json.dumps({"columns": {TABLE: {"lot": {"write": True, "rules": {"replace": [[" *[.] *", "."]]}}}}}),
                     encoding="utf-8")
    monkeypatch.setattr(notation_norm, "NOTATION_RULES_PATH", str(rules))
    config_watcher.forget_held()
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
        config_watcher.forget_held()


def _item(updates, source, row_id=None):
    return schemas.GeneralUpdateItem(row_id=row_id, updates=updates, source_name=source, updated_by="probe")


def _at(job, x, y, **values):
    return {"job": job, "x": x, "y": y, **values}


def _write(db, items, **batch):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=items, **batch))
    db.commit()


def _clean(world):
    with world["engine"].begin() as conn:
        conn.execute(text('DELETE FROM "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
        for table in ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox"):
            conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t' % (PG_TEST_SCHEMA, table)), {"t": TABLE})


def test_one_column_written_reads_that_columns_layers_only(world):
    db = world["db"]
    _clean(world)
    _write(db, [_item(_at("J5", i, 1, a=i, b="b", c="c", lot="L"), "chain:w") for i in range(20)])
    read = []

    def count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("SELECT") and "FROM cell_sources" in statement:
            read.append(cursor.rowcount)
    event.listen(world["engine"], "after_cursor_execute", count)
    try:
        _write(db, [_item(_at("J5", i, 1, a=i + 100), "chain:w") for i in range(20)])
    finally:
        event.remove(world["engine"], "after_cursor_execute", count)
    with world["engine"].connect() as conn:
        stored = conn.execute(text("SELECT count(*) FROM \"%s\".cell_sources WHERE table_name = :t"
                                   % PG_TEST_SCHEMA), {"t": TABLE}).scalar()
    assert stored == 20 * 8, "canary: a layer in each of the eight columns (keys included) of 20 rows"
    # the batch writes a and the four key columns (the key is assembled into `k`)
    assert sum(read) == 20 * 5, read
