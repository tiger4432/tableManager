# -*- coding: utf-8 -*-
"""총괄 bce43236b: a row THIS batch created has no stored cell history, so its later items read the
batch's own caches instead of one SELECT per cell. The answer must be the one a door that asks the
database for every cell gives - with a pin, the human layer and a collision merge in play.

  a row the batch made          nothing about it is stored before the batch: a pin comes through
                                the pin door, a merge copy needs a row reached by its stored id,
                                and what the batch itself staged lives in its caches - so the
                                database answers "none", which the caches say (the oracle asks it)
  before the batch              P: the user's value, a collision merge of Q into it, then a pin
  the same batch, one call      i1 makes N · i2 the user writes N · i3 a machine writes N ·
                                i4 a machine writes P · i5 makes M by a named id · i6 writes M again
  the oracle                    `_load_metadata_row_cell` told nothing up front, so it asks the
                                database for every cell - the same rows, layers, overwrites,
                                outbox and audit lines
  and what it saves             a value then a hold for each of 200 new rows asks the stored
                                history nothing (it was one SELECT a cell: ~2,000 for 1,000 rows)
"""
import json
import os
import sys

import pytest
import uuid6
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


def _clean(world):
    with world["engine"].begin() as conn:
        conn.execute(text('DELETE FROM "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
        for table in ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox"):
            conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t' % (PG_TEST_SCHEMA, table)),
                         {"t": TABLE})


def _scenario(world):
    """Before: P user-written, Q merged into P, then P pinned. Then the batch under test."""
    db = world["db"]
    _clean(world)
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        _item({**_keys("J1"), "netdie": 1}, "user"),
        _item({**_keys("J1"), "hold": "x"}, "chain:hc_copy"),
        _item({**_keys("J5"), "netdie": 3}, "chain:q")]))
    db.commit()
    ids = dict(db.execute(text('SELECT job, row_id FROM "%s"."%s"' % (PG_TEST_SCHEMA, TABLE))).all())
    p, q = ids["J1"], ids["J5"]
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        _item({**_keys("J1"), "netdie": 4}, "chain:m", row_id=q)]))          # Q re-keyed into P
    db.commit()
    crud.set_cell_manual_priority_batch(db, TABLE, [{"row_id": p, "column_name": "netdie"}], "user")
    db.commit()
    m = str(uuid6.uuid7())
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        _item({**_keys("J9"), "netdie": 5}, "chain:a"),                      # i1 makes N
        _item({**_keys("J9"), "netdie": 6}, "user"),                         # i2 user on N
        _item({**_keys("J9"), "netdie": 7, "hold": "h"}, "chain:b"),         # i3 machine on N
        _item({**_keys("J1"), "netdie": 8}, "chain:a"),                      # i4 P
        _item({**_keys("J7"), "netdie": 10}, "chain:d", row_id=m),           # i5 makes M
        _item({**_keys("J7"), "netdie": 11, "hold": "y"}, "chain:e", row_id=m),  # i6 M again
    ]))
    db.commit()
    return _dump(world, {m: "M", p: "P", q: "Q"})


def _dump(world, named):
    s = PG_TEST_SCHEMA
    with world["engine"].connect() as conn:
        def q(sql):
            return [dict(r._mapping) for r in conn.execute(text(sql))]
        keys = dict(named)
        rows = {}
        for r in q('SELECT row_id, business_key_val, %s FROM "%s"."%s"'
                   % (", ".join('"%s"' % c for c in COLUMNS), s, TABLE)):
            keys.setdefault(r["row_id"], r["business_key_val"])
            rows[str(r["business_key_val"])] = {c: r[c] for c in COLUMNS}

        def norm(value):
            if isinstance(value, dict):
                return {k: norm(v) for k, v in sorted(value.items()) if k not in VOLATILE}
            if isinstance(value, list):
                return [norm(v) for v in value]
            if isinstance(value, str) and value in keys:
                return "<%s>" % keys[value]
            return value

        def lines(table):
            return sorted(json.dumps(norm(r), sort_keys=True, default=str) for r in q(
                "SELECT * FROM \"%s\".%s WHERE table_name = '%s'" % (s, table, TABLE)))
        return {"rows": rows, "cell_sources": lines("cell_sources"),
                "cell_overwrites": lines("cell_overwrites"), "outbox": lines("database_outbox"),
                "audit": lines("audit_logs")}


def test_a_row_the_batch_made_reads_what_the_database_would_say(world, monkeypatch):
    product = _scenario(world)
    lines = product["cell_sources"] + product["cell_overwrites"] + product["audit"]
    assert any("collision_merge" in line for line in lines), "canary: Q was merged into P"
    assert any('"manual_priority_source": "user"' in line for line in product["cell_overwrites"]), \
        "canary: P is pinned"
    n_sources = {json.loads(line)["source_name"] for line in product["cell_sources"]
                 if json.loads(line)["row_id"] == "<J9_1_2>"}
    assert {"chain:a", "user", "chain:b"} <= n_sources, ("canary: N was made and written again "
                                                         "in one batch", n_sources)

    real = crud._load_metadata_row_cell

    def asks_the_database(db, table_name, row_id, col_name, is_new, sources_cache,
                          overwrites_cache, cell_sources_to_upsert, cell_overwrites_to_upsert,
                          prefetched_row_ids=None):
        return real(db, table_name, row_id, col_name, is_new, sources_cache, overwrites_cache,
                    cell_sources_to_upsert, cell_overwrites_to_upsert, None)
    monkeypatch.setattr(crud, "_load_metadata_row_cell", asks_the_database)
    oracle = _scenario(world)

    assert product == oracle


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
