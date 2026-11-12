# -*- coding: utf-8 -*-
"""총괄 9280922aa: two machine sources writing one cell in ONE batch - the later item wins, as it
does when the two arrive in two batches (`compute_priority_value`: of equal rank, the newest
delivery is the fact). Each layer stamped `datetime.now()`; two items in one clock tick tied and
the source NAME picked the earlier, so a batch's answer depended on the clock.

  one cell, twice      chain:a writes 1, then chain:b writes 2 - on a tie the name picks 1
  ROWS pairs           items take a fraction of the clock's step, so with the old stamp many
                       pairs fall in one tick (the canary counts the layers' stamps)
  one batch == two     the cell, chain:b's head line and the row's last outbox event say 2 - on the lines (the
                       overhaul: one batch's lines share an instant, the later line wins - rank 2c)
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import retire_dynamic_model                            # noqa: E402
from database import crud, lines, models, schemas                    # noqa: E402
from database.database import Base                                   # noqa: E402

TABLE = "lt_rows"
CONFIG = {TABLE: {"business_key": "k", "composite_key_source": ["k"],
                  "column_types": {"k": "string", "n": "string"}, "display_columns": ["k", "n"]}}
ROWS = 200


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

    line_tables.build(engine, TABLE)                                   # the product's shape: a table keeps lines
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(TABLE)


def _item(key, source, n):
    return schemas.GeneralUpdateItem(updates={"k": key, "n": n}, source_name=source,
                                     updated_by="probe")


def _write(db, items):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=items))
    db.commit()


def test_the_later_item_of_one_batch_wins_as_in_two(db):
    one = ["A%03d" % i for i in range(ROWS)]
    two = ["B%03d" % i for i in range(ROWS)]
    _write(db, [item for key in one for item in (_item(key, "chain:a", "1"), _item(key, "chain:b", "2"))])
    _write(db, [_item(key, "chain:a", "1") for key in two])
    _write(db, [_item(key, "chain:b", "2") for key in two])

    model = models.DYNAMIC_TABLES[TABLE]
    keyed = {row.row_id: row.business_key_val for row in db.query(model)}
    said = {keyed[r]: layers for (r, _c), layers in lines.layers(db, TABLE, list(keyed), ["n"]).items()}
    assert len(said) == 2 * ROWS and all(set(s) == {"chain:a", "chain:b"} for s in said.values())
    assert all(s["chain:b"]["line_id"] > s["chain:a"]["line_id"] for s in said.values())   # the later item, later

    shown = {row.business_key_val: row.n for row in db.query(model)}
    last_sent = {}
    for event in db.query(models.DatabaseOutbox).filter_by(table_name=TABLE).order_by(models.DatabaseOutbox.id):
        last_sent[event.payload["business_key"]] = event.payload["data"]["n"]["value"]
    for keys in (one, two):
        assert [shown[key] for key in keys] == ["2"] * ROWS
        assert [key for key in keys if said[key]["chain:b"]["value"] != "2"] == []
        assert [last_sent[key] for key in keys] == ["2"] * ROWS
