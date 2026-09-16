# -*- coding: utf-8 -*-
"""S-279 · 판정 431. A deleted row's history names the caller, through either door.

🔴 IT WAS NOT AN ABSENCE, IT WAS A FALSE AUTHOR. `crud.delete_row` took
`user_name: str = "system"`, and the only caller that relied on that default was
`DELETE /tables/{table}/rows/{row_id}`, which had no author parameter at all. So a deletion a
PERSON asked for was recorded as the system's. A missing name is a fact; 「system 이 했다」 is
a different fact, and the audit log is the place this product answers 「누가 지웠나」.

⚠️ THE OTHER DOOR WAS NOT CLEAN EITHER, which the ruling's own measurement did not reach: the
BATCH path carried the same default twice - `crud.delete_rows_batch` and
`schemas.RowDeleteBatch.user_name` - and was correct only because this box's client happens to
send a name every time. A default that is right because of who calls it is not right.

⚠️ AND THE ROUTE'S PARAMETER IS OPTIONAL ON PURPOSE. It is public, so requiring it would refuse
callers that work today. An unnamed caller is written down as unnamed.
"""
import inspect
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                                # noqa: E402
from database.database import Base                                    # noqa: E402
from database import crud, models, schemas                            # noqa: E402

TABLE = "s431_rows"
TABLES = {
    TABLE: {
        "business_key": "part_no",
        "composite_key_source": ["part_no"],
        "column_types": {"part_no": "string", "note": "string"},
        "display_columns": ["part_no", "note"],
    },
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
        crud.TABLE_CONFIG.pop(TABLE, None)


def _seed(db, part_no):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"part_no": part_no, "note": "n"},
                                  source_name="seed", updated_by="s431")]))
    db.commit()
    return db.query(models.DYNAMIC_TABLES[TABLE]).filter_by(business_key_val=part_no).one().row_id


def _authors_of_deletions(db, row_id):
    """Who the history says removed this row. Keyed by `row_id` - the audit table keys by the
    row, and the business key is not one of its columns (measured, not assumed)."""
    return [log.updated_by for log in db.query(models.AuditLog).filter(
        models.AuditLog.table_name == TABLE,
        models.AuditLog.row_id == row_id).all()]


# ---------------------------------------------------------------------------
# 🔴 one fixture, both doors - the point is that they AGREE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("door", ("single", "batch"))
def test_the_author_of_a_deletion_is_the_caller_not_the_system(db, door):
    """⛔ THE TWO DOORS SCORED THE SAME WAY. Each was tested on its own before and each passed:
    the batch one recorded a name because its caller always supplies one, and the single one
    recorded 「system」 and nothing said that was wrong. What no test asked was whether the two
    answer the SAME question the same way."""
    part_no = "P-%s" % door
    row_id = _seed(db, part_no)

    if door == "single":
        crud.delete_row(db, TABLE, row_id, "alice")
    else:
        crud.delete_rows_batch(db, TABLE, [row_id], "alice")
    db.commit()

    authors = _authors_of_deletions(db, row_id)
    assert authors, "the deletion left no history at all, so this proves nothing"
    assert "system" not in authors, (
        "%s door recorded the system as the author of a deletion a person asked for: %s"
        % (door, authors))
    assert "alice" in authors, authors


@pytest.mark.parametrize("door", ("delete_row", "delete_rows_batch"))
def test_neither_delete_door_has_an_author_to_fall_back_on(door):
    """🔴 THE SHAPE, NOT ONLY THE VALUE. A default that spells a name can only ever be wrong
    when nobody gave one, and it is invisible at the call site - which is why the route went
    years without an author parameter and nothing was red. Removing the default makes the
    omission a TypeError at the boundary instead of a false sentence in the history."""
    parameters = inspect.signature(getattr(crud, door)).parameters

    assert parameters["user_name"].default is inspect.Parameter.empty, (
        "%s still has an author to fall back on: %r" % (door, parameters["user_name"].default))


def test_a_caller_that_did_not_say_who_is_written_down_as_unnamed():
    """⚠️ 「모른다」를 적어야 하면 그 낱말을 적는다. The public route keeps working without an
    author - what changes is that the history says so rather than naming the system."""
    assert event_constants.AUTHOR_NOT_STATED != "system"
    assert schemas.RowDeleteBatch(row_ids=["r1"]).user_name == event_constants.AUTHOR_NOT_STATED


def test_the_public_route_takes_an_author_and_hands_it_on():
    """The wiring, read off the route itself: a parameter nobody passes on is decoration."""
    import main

    parameters = inspect.signature(main.delete_row).parameters
    assert "user_name" in parameters, "the route cannot be told who is deleting"
    assert parameters["user_name"].default is None, (
        "a public route that REQUIRES the name would refuse callers that work today")

    body = inspect.getsource(main.delete_row)
    assert "crud.delete_row, db, table_name, row_id, author" in body, (
        "the route takes an author and does not hand it to the deletion")
    assert "AUTHOR_NOT_STATED" in body, (
        "an unnamed caller must be written down as unnamed, not left to a default")
