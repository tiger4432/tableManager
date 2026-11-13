# -*- coding: utf-8 -*-
"""S-74. The product's DELETE door staged no outbox event, so nothing downstream saw a delete.

🔴 MEASURED 2026-09-08, this box's whole outbox history: CREATE 1,618, RETROACTIVE_RUN 1,
DELETE **0** -- while an EDIT of the same row stages normally. The chain and the ledger's
follow-up, which withdraws a deleted row's facts, had therefore never once received a live
deletion.

Since the cell-source overhaul a delete is a «deleted» line (`crud.record_row_deletions` -> `write_lines`), which
stages the DELETE in its own transaction - one author for every door, so this file runs the doors and reads the
outbox rather than reading their code for a staging call.
"""
import inspect

import pytest

from database import crud, lines, models, schemas
from database.database import Base

TABLE = "del_ob"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string"}}


@pytest.fixture(name="db")
def fixture_db(db_session, monkeypatch):
    models.init_dynamic_models({TABLE: CFG})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    Base.metadata.create_all(bind=db_session.get_bind())
    lines.ensure_line_table(db_session, TABLE, CFG)
    crud.apply_batch_updates(db_session, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val=k, updates={"k": k, "a": "x"}, source_name="f1.csv", updated_by="loader")
        for k in ("K1", "K2")]))
    return db_session


def _ids(db):
    m = models.DYNAMIC_TABLES[TABLE]
    return [r.row_id for r in db.query(m).order_by(m.row_id)]


def _deletes(db):
    return [e.payload.get("row_ids") for e in db.query(models.DatabaseOutbox).filter_by(
        event_type="DELETE", table_name=TABLE).order_by(models.DatabaseOutbox.id)]


def test_the_batch_delete_stages_the_event(db):
    ids = _ids(db)
    crud.delete_rows_batch(db, TABLE, ids, "kim")
    assert _deletes(db) == [ids]


def test_no_door_spells_the_staging_itself():
    """⛔ NOT A SECOND SPELLING. Two ways to announce a deletion is how one of them comes to be forgotten -- which is
    the shape this whole defect had. Both doors reach it through the one recorder."""
    for door in (crud.delete_rows_batch, crud.purge_map_rows):
        code = inspect.getsource(door).split('"""')[-1]
        assert "stage_collapsed_event(" not in code and "record_row_deletions(" in code, door.__name__


def test_the_single_row_door_delegates_rather_than_repeating():
    """`delete_row` must reach the outbox by calling the batch, not by staging its own."""
    code = inspect.getsource(crud.delete_row).split('"""')[-1]
    assert "delete_rows_batch(" in code and "stage_collapsed_event(" not in code


def test_it_announces_the_rows_that_were_actually_removed(db):
    """A delete of something already gone is not a deletion: the event names the rows that went, not what the caller
    asked for."""
    [first, _second] = _ids(db)
    assert crud.delete_rows_batch(db, TABLE, [first, "no-such-row"], "kim") == 1
    assert _deletes(db) == [[first]]
