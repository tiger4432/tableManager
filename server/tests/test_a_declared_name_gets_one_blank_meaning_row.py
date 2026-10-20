# -*- coding: utf-8 -*-
"""e38466810 (owner 10-20 「뜻은 표에」, lead 10-21): one meaning row per entity and predicate the declaration names,
made blank by `ledger.meanings.fill_blank_meanings` where the declaration is read again in the API
(`config_watcher`'s ontology row). Only what is missing is written; a person's value and a retired name's row stay."""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)

import product_tables  # noqa: E402
from database import crud, models, schemas  # noqa: E402
from database.database import Base  # noqa: E402
from ledger import meanings, trace_router  # noqa: E402

TABLE = product_tables.MEANING_TABLE
DECLARATION = {"entities": {"wafer@1": {}, "die@1": {}},
               "vocabulary": {"bonded_from@1": {}, "processed_with@1": {}, "in_container": {}}}


@pytest.fixture
def box(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "meanings.db"))
    cfg = {TABLE: product_tables.effective_declaration(product_tables.PRODUCT_TABLES[TABLE])}
    models.init_dynamic_models(cfg)
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, cfg[TABLE])
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    declaration = dict(DECLARATION)
    monkeypatch.setattr(trace_router, "_declaration", lambda world=None: declaration)
    yield engine, declaration
    engine.dispose()


def _rows(engine):
    model = models.DYNAMIC_TABLES[TABLE]
    with Session(bind=engine) as db:
        return {(r.target_kind, r.target_name): r.meaning for r in db.query(model)}


def test_every_declared_name_gets_a_blank_row_and_a_rerun_writes_none(box):
    engine, _ = box
    assert meanings.fill_blank_meanings(engine) == 5
    assert _rows(engine) == {("entity", "wafer"): None, ("entity", "die"): None,
                             ("predicate", "bonded_from"): None, ("predicate", "processed_with"): None,
                             ("predicate", "in_container"): None}
    assert meanings.fill_blank_meanings(engine) == 0


def test_a_persons_meaning_and_a_retired_names_row_stay(box):
    engine, declaration = box
    meanings.fill_blank_meanings(engine)
    with Session(bind=engine) as db:
        crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            updates={"target_kind": "entity", "target_name": "wafer", "meaning": "a silicon disc"},
            source_name="user", updated_by="hc")]))
        db.commit()
    declaration["entities"] = {"wafer@1": {}, "lot@1": {}}
    assert meanings.fill_blank_meanings(engine) == 1
    rows = _rows(engine)
    assert rows[("entity", "wafer")] == "a silicon disc" and ("entity", "die") in rows and rows[("entity", "lot")] is None


def test_the_ontology_row_writes_only_where_it_was_given_the_engine(box):
    from database import config_watcher

    engine, _ = box
    config_watcher._ontology(None, None)
    assert _rows(engine) == {}
    config_watcher._ontology(None, engine)
    assert len(_rows(engine)) == 5


def test_an_uninstalled_meaning_table_is_said_not_raised(box, monkeypatch, caplog):
    engine, _ = box
    monkeypatch.delitem(models.DYNAMIC_TABLES, TABLE)
    assert meanings.fill_blank_meanings(engine) is None
    assert any("install_product_tables.py --apply" in r.getMessage() for r in caplog.records)
