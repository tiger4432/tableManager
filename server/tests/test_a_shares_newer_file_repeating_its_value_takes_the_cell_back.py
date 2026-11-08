# -*- coding: utf-8 -*-
"""A newer file from one share that repeats its old value takes the cell back from another share's change (소유자
11-08 ㄱ «층을 새로하지 말고 순서를 바꿔»; QA 11-08 on bc83b1191): share A's f1 says v, share B's g1 then says w, share
A's f2 says v again - the cell shows v, share A's layer goes to the front (no new layer), one EDIT. The same file
resent says nothing new and changes nothing (the seat's `source_unchanged`).
"""
import os
import sys
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.database import Base                                  # noqa: E402

T = "sf_tgt"
TABLES = {T: {"business_key": "k", "composite_key_source": ["k"],
              "column_types": {"k": "string", "v": "string"}, "display_columns": ["k", "v"]}}
T0 = datetime(2026, 11, 8, 9, 0, 0)


def _ext(share_root, name):
    return crud.external_layer_name("workspace", "%s@%s" % (T, share_root), "%s\\%s" % (share_root, name))


A1, A2, B1 = _ext("c:\\share_a", "f1.csv"), _ext("c:\\share_a", "f2.csv"), _ext("c:\\share_b", "g1.csv")


@pytest.fixture(name="db")
def fixture_db(monkeypatch):
    clock = iter(T0 + timedelta(minutes=n) for n in range(1000))
    monkeypatch.setattr(crud, "layer_instant", lambda: next(clock))
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
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
            updates={"k": "K", "v": value}, source_name=source_name, updated_by="sf")]))
    db.commit()


def _cell(db):
    """(the value the cell shows, {layer: value}, the layer newest by ingested_at)."""
    db.expire_all()
    row = db.query(models.DYNAMIC_TABLES[T]).filter_by(business_key_val="K").one()
    layers = db.query(models.CellSource).filter_by(table_name=T, row_id=row.row_id, column_name="v").all()
    return row.v, {s.source_name: s.value for s in layers}, max(layers, key=lambda s: s.ingested_at).source_name


def test_a_shares_newer_file_repeating_its_value_moves_its_layer_to_the_front(db):
    _write(db, A1, "v")
    _write(db, B1, "w")
    assert _cell(db) == ("w", {A1: "v", B1: "w"}, B1), "canary: share b's change shows"
    before = db.query(models.DatabaseOutbox).count()
    _write(db, A2, "v")
    assert _cell(db) == ("v", {A1: "v", B1: "w"}, A1), "one layer a share - share a's to the front, none made"
    told = [e.event_type for e in db.query(models.DatabaseOutbox).order_by(models.DatabaseOutbox.id).all()[before:]]
    assert told == ["EDIT"], told


def test_the_same_file_resent_changes_nothing(db):
    _write(db, A1, "v")
    _write(db, B1, "w")
    before = db.query(models.DatabaseOutbox).count()
    _write(db, A1, "v")
    assert _cell(db) == ("w", {A1: "v", B1: "w"}, B1), "a value sent again is not a new statement"
    assert db.query(models.DatabaseOutbox).count() == before
