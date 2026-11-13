# -*- coding: utf-8 -*-
"""A chain write that says what the cell already shows makes no layer (소유자 11-08: «쓰레기 체인 층» in production -
a mapper handing back a file's cells rewrote each of them as a chain layer of the same value).

  ① the chain writes the shown value: no chain layer      ② a different value: its layer, as before
  ③ a person writes the shown value: their layer, as before  ④ the file layer under it goes: the cell's EDIT wakes
    the rules on the table, so the one writing it runs again and fills the hole
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.database import Base                                  # noqa: E402
from tests.support import line_tables                               # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

T, FILE = "sv_tgt", "sv_file.csv"
TABLES = {T: {"business_key": "k", "composite_key_source": ["k"],
              "column_types": {"k": "string", "v": "string"}, "display_columns": ["k", "v"]}}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    line_tables.build(engine, T)                   # a cell's layers are its lines' (A 11-11)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.pop(T, None)


def _write(db, source_name, value):
    from database.context import channel, outbox_mode

    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            updates={"k": "K", "v": value}, source_name=source_name, updated_by="sv")]))
    db.commit()


def _layers(db):
    """{layer: value} of the cell (K, v), and the value it shows."""
    db.expire_all()
    row = db.query(models.DYNAMIC_TABLES[T]).filter_by(business_key_val="K").one()
    from database import lines

    return row.v, {name: layer["value"] for name, layer in
                   lines.layers(db, T, [row.row_id], columns=["v"]).get((row.row_id, "v"), {}).items()}


def test_a_chain_write_of_the_shown_value_makes_no_layer_and_a_different_one_does(db):
    _write(db, FILE, "A")
    _write(db, crud.CHAIN_SOURCE, "A")
    assert _layers(db) == ("A", {FILE: "A"})
    _write(db, crud.CHAIN_SOURCE, "B")
    assert _layers(db)[1] == {FILE: "A", crud.CHAIN_SOURCE: "B"}
    _write(db, crud.USER_SOURCE, "C")                   # a person's C shows over the chain's B
    _write(db, crud.CHAIN_SOURCE, "C")                  # a layer the chain holds is kept true, not left at B
    assert _layers(db) == ("C", {FILE: "A", crud.CHAIN_SOURCE: "C", crud.USER_SOURCE: "C"})


def test_a_person_writing_the_shown_value_keeps_their_layer(db):
    _write(db, FILE, "A")
    _write(db, crud.USER_SOURCE, "A")
    assert _layers(db)[1] == {FILE: "A", crud.USER_SOURCE: "A"}


def test_the_file_layer_going_tells_the_column_so_the_chain_runs_again(db):
    _write(db, FILE, "A")
    _write(db, crud.CHAIN_SOURCE, "A")
    before = db.query(models.DatabaseOutbox).count()
    row_id = db.query(models.DYNAMIC_TABLES[T]).filter_by(business_key_val="K").one().row_id
    crud.delete_cell_source_batch(db, T, [{"row_id": row_id, "column_name": "v"}], FILE)
    db.commit()
    assert _layers(db) == (None, {})
    told = db.query(models.DatabaseOutbox).order_by(models.DatabaseOutbox.id).all()[before:]
    # an EDIT naming v - or naming no columns, 「모른다」, which wakes every rule on the table
    said = [(e.event_type, get_payload_dict(e).get("columns")) for e in told]
    assert len(said) == 1 and said[0][0] == "EDIT" and (said[0][1] is None or "v" in said[0][1]), said
    _write(db, crud.CHAIN_SOURCE, "A")                  # the rule run again: the cell shows nothing, so its layer is made
    assert _layers(db) == ("A", {crud.CHAIN_SOURCE: "A"})
