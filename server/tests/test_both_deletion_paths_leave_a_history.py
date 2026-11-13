# -*- coding: utf-8 -*-
"""「무엇이 지워졌나」 has an answer for BOTH ways a row can go - a «deleted» line each (cell-source overhaul).

🔴 THE HALF THAT STAYED OPEN. `delete_rows_batch` had recorded every row it removed since
long before; the map purge recorded none. Same act — 「행을 지운다」 — and only one of them
left a place to ask afterwards.

⚠️ ONE PLACE, WHICH IS WHAT MAKES THE MUTATION SPLIT. `record_row_deletions` is called by
both paths, so deleting the recording in that one place has to redden BOTH of the path tests
below. If only one goes red, the paths are not sharing after all and this file says so.
"""
import ast
import inspect

import pytest
from sqlalchemy import select

from database import crud, lines, models, schemas
from database.database import Base

TABLE = "del_hist"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string"}}


@pytest.fixture(name="db")
def fixture_db(db_session, monkeypatch):
    models.init_dynamic_models({TABLE: CFG})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    Base.metadata.create_all(bind=db_session.get_bind())
    lines.ensure_line_table(db_session, TABLE, CFG)
    db_session.commit()
    return db_session


def seeded(db, keys):
    """Rows the doors can find. 🔴 THE FIXTURE IS PART OF THE ASSERTION: with nothing to find, 「it wrote no history」
    and 「there was nothing to write about」 look the same."""
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val=k, updates={"k": k, "a": "x"}, source_name="f1.csv", updated_by="loader") for k in keys]))
    model = models.DYNAMIC_TABLES[TABLE]
    return [r.row_id for r in db.query(model).filter(model.business_key_val.in_(keys)).order_by(model.row_id)]


def deleted_lines(db):
    ln = lines.shape(db, TABLE, CFG)["lines"]
    return db.execute(select(ln.c.row_id, ln.c.business_key_val, ln.c.written_by, ln.c.batch)
                      .where(ln.c.line_kind == "deleted").order_by(ln.c.line_id)).all()


# --------------------------------------------------------------- the two doors

def test_a_map_purge_leaves_a_line_saying_what_went(db):
    """🔴 THE GATE. Not 「a table shrank」 — WHICH rows, one line each."""
    ids = seeded(db, ["K1", "K2", "K3"])
    crud.purge_map_rows(db, models.DYNAMIC_TABLES[TABLE], TABLE, ids)
    db.flush()
    assert sorted(r.row_id for r in deleted_lines(db)) == sorted(ids)


def test_a_batch_delete_leaves_a_line_saying_what_went(db):
    ids = seeded(db, ["K1", "K2"])
    assert crud.delete_rows_batch(db, TABLE, ids, "kim") == 2
    assert sorted((r.row_id, r.written_by) for r in deleted_lines(db)) == sorted((i, "kim") for i in ids)


def test_a_door_records_nothing_when_there_was_nothing_to_delete(db):
    """⚠️ ABSENT IS NOT ZERO. Ids that do not exist get no history for rows that never went anywhere."""
    seeded(db, ["K1"])
    crud.purge_map_rows(db, models.DYNAMIC_TABLES[TABLE], TABLE, ["no-such-row"])
    assert crud.delete_rows_batch(db, TABLE, ["no-such-row"], "kim") == 0
    assert deleted_lines(db) == []


# ------------------------------------------------- one recorder, and what it carries

def test_the_helper_is_what_the_batch_path_uses():
    """🔴 THE TWO PATHS SHARING IS THE PROPERTY - asserted on the code, because a copied block passes a behaviour
    test just as well."""
    for door in (crud.delete_rows_batch, crud.purge_map_rows):
        body = ast.unparse(ast.parse(inspect.getsource(door).lstrip()).body[0])
        assert "record_row_deletions(" in body, "%s stopped sharing the recorder" % door.__name__


def test_the_recorder_writes_one_line_per_row_and_carries_the_key_and_the_transaction(db):
    ids = seeded(db, ["K1", "K2"])
    answer = crud.record_row_deletions(db, TABLE, ids, "tester", "tx-del")
    db.flush()
    assert [s["work"] for s in answer["items"]] == ["delete", "delete"]
    assert sorted(tuple(r) for r in deleted_lines(db)) == sorted(
        [(ids[0], "K1", "tester", "tx-del"), (ids[1], "K2", "tester", "tx-del")])


def test_the_deletions_entries_are_its_lines(db):
    """What the delete route's notification carries: the line ids of the answer, «row deleted», by whom."""
    ids = seeded(db, ["K1"])
    entries = []
    crud.delete_rows_batch(db, TABLE, ids, "kim", deleted_lines=entries)
    [entry] = entries
    assert (entry["row_id"], entry["column_name"], entry["new_value"], entry["updated_by"], entry["business_key"],
            entry["is_row_deleted"]) == (ids[0], crud.ROW_DELETION_COLUMN, "row deleted", "kim", "K1", True), entry
