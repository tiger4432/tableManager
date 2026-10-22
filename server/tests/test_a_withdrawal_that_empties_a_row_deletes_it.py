# -*- coding: utf-8 -*-
"""총괄 69b8b029c (소유자 10-21 「체인 껍데기는 여전함 · 회수된 게 키이긴 함」): a withdrawal that takes the last layer of a
row the chain filled - its key's too - left the row with its key blank and its business key standing, and nothing
asked whether it was a shell. The chain's write seat asked; the seats that take layers back did not. Every one asks
the one judgement now (`cell_layer.shells`) and deletes by the one door (`cell_layer.delete_shells`): the worker's
withdrawal (an edit, a deletion, what a replay woke) and R2's. A blank recount leaves it to its write, which asks
after the recount.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import cell_layer, replay                                       # noqa: E402
from chain import ingestion_worker as worker                               # noqa: E402
from database.database import Base                                         # noqa: E402
from database import crud, models, schemas                                 # noqa: E402

SRC, TGT = "wd_src", "wd_tgt"
TABLES = {
    SRC: {"business_key": "k", "column_types": {"k": "string", "v": "string"}, "display_columns": ["k", "v"]},
    TGT: {"business_key": "k", "column_types": {"k": "string", "v": "string"}, "display_columns": ["k", "v"]},
}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _copy(db, key, origin, source=crud.CHAIN_SOURCE):
    """The row a copy rule writes whole - its key too - stamped with the source row it read."""
    crud.apply_batch_updates(db, TGT, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        updates={"k": key, "v": "x"}, source_name=source, updated_by="wd_copy", origin_row_id=origin)]))
    db.commit()
    return db.query(models.DYNAMIC_TABLES[TGT]).filter_by(business_key_val=key).one().row_id


def _rows(db):
    return sorted((r.business_key_val, r.k, r.v) for r in db.query(models.DYNAMIC_TABLES[TGT]))


def _mark(db):
    return max([e.id for e in db.query(models.DatabaseOutbox)] or [0])


def _told(db, row_id, after):
    """The EDIT events staged after `after` that name this row."""
    return [e.id for e in db.query(models.DatabaseOutbox).filter_by(table_name=TGT, event_type="EDIT")
            if e.id > after and row_id in str(e.payload)]


@pytest.mark.parametrize("why", ["edited", "deleted"])
def test_a_withdrawal_that_empties_a_row_deletes_it(db, why):
    gone = _copy(db, "a", "src-a")
    _copy(db, "b", "src-b")
    mark = _mark(db)
    stats = worker._withdraw_and_tell(db, SRC, ["src-a"], why)

    assert stats["rows_deleted"] == 1
    assert _rows(db) == [("b", "b", "x")], "the row src-a fed stands with its key blank"
    history = db.query(models.AuditLog).filter_by(table_name=TGT, row_id=gone, column_name="DELETE").all()
    assert [h.updated_by for h in history] == [cell_layer.SHELL_DELETER]
    deletions = [e.payload for e in db.query(models.DatabaseOutbox).filter_by(table_name=TGT, event_type="DELETE")
                 if e.id > mark]
    assert [(d["updated_by"], d["row_ids"]) for d in deletions] == [(cell_layer.SHELL_DELETER, [gone])]


def test_a_row_another_source_still_holds_stays_and_is_told(db):
    row_id = _copy(db, "a", "src-a")
    _copy(db, "a", None, source="file_a.csv")
    mark = _mark(db)
    stats = worker._withdraw_and_tell(db, SRC, ["src-a"], "edited")

    assert stats["rows_deleted"] == 0
    assert _rows(db) == [("a", "a", "x")]
    assert _told(db, row_id, mark), "the row that lost a layer is not told"


def test_a_blank_recount_leaves_the_row_to_its_write(db):
    _copy(db, "a", "src-a")
    stats = worker._withdraw_and_tell(db, SRC, ["src-a"], "blank", ask_shells=False)

    assert stats["rows_deleted"] == 0
    assert _rows(db) == [("a", None, None)], "canary: the withdrawal emptied the row"


def test_r2_deletes_the_row_it_empties_and_its_preview_said_at_most_that_many(db):
    _copy(db, "a", "src-a")
    _copy(db, "b", None, source="file_b.csv")
    [layer] = {s.source_name for s in db.query(models.CellSource).filter_by(table_name=TGT, row_id=_copy(db, "a", "src-a"))}
    db.rollback()

    preview = replay.count_withdrawable(db, TGT, layer)
    stats = replay.withdraw_source(db, TGT, layer, apply=True)

    assert preview["rows_emptied"] == 1
    assert stats["rows_deleted"] == 1
    assert _rows(db) == [("b", "b", "x")]


def test_r2_withdraws_a_page_and_deletes_its_shells_in_one_commit(db, monkeypatch):
    """총괄 g33 · g85: R2 committed its withdrawal page by page and the shells it left once at the end - a death
    between left the rows standing with their keys blank. Now a page's shells go in that page's commit."""
    row_id = _copy(db, "a", "src-a")
    [layer] = {s.source_name for s in db.query(models.CellSource).filter_by(table_name=TGT, row_id=row_id)}
    layers = db.query(models.CellSource).filter_by(table_name=TGT, row_id=row_id, source_name=layer).count()
    db.rollback()

    def dies(*_args):
        raise RuntimeError("killed at the shells")
    monkeypatch.setattr(cell_layer, "delete_shells", dies)
    with pytest.raises(RuntimeError, match="killed at the shells"):
        replay.withdraw_source(db, TGT, layer, apply=True)
    db.rollback()

    assert _rows(db) == [("a", "a", "x")], "the page's withdrawal outlived its shells' death"
    assert db.query(models.CellSource).filter_by(table_name=TGT, row_id=row_id, source_name=layer).count() == layers == 2
