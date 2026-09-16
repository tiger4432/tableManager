"""The slow-prefetch diagnostic reads rows a commit has expired and a close detached.

Production, 2026-09-16, after three days of one auto-update output not ingesting under
the sentence 「Instance <...> is not bound to a Session」. The seat is
`_maybe_explain_slow_prefetch`, added to EXPLAIN a prefetch nobody can run SQL against
(판정 276). It samples the batch's row ids with a plain attribute read:

    rid = getattr(row, "row_id", None)

The ingest loop gives it objects that `crud.apply_batch_updates` returned. That call
commits, and a commit EXPIRES every object it touched (`expire_on_commit` is
SQLAlchemy's default and `database.py` never turns it off); the chunk's session is then
CLOSED in a `finally` before this line runs, which detaches them. An expired attribute
on a detached object cannot be refreshed, so the read raises - and it raised inside the
chunk loop, taking the whole file with it.

The two properties pinned here are the two halves of that sentence: the id is obtainable
without the database, and the diagnostic returns instead of raising when handed exactly
the production shape (slow prefetch, detached rows).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import DetachedInstanceError

from database import crud, models, schemas
from database.database import Base
from parsers.directory_watcher import (
    _maybe_explain_slow_prefetch,
    _row_id_without_a_refresh,
)
from sql_budget import record_statements

TABLE = "d39_detached_probe"
CONFIG = {
    TABLE: {
        "business_key": "probe_id",
        "column_types": {"probe_id": "string", "note": "string"},
    },
}


@pytest.fixture
def probe_db():
    models.init_dynamic_models(CONFIG)
    crud.TABLE_CONFIG.update(CONFIG)
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.pop(TABLE, None)


def _rows_as_the_chunk_loop_leaves_them(db):
    """Exactly what the ingest loop holds when the diagnostic runs: rows returned by
    `apply_batch_updates` (which committed, expiring them) after the chunk session was
    closed (detaching them)."""
    batch = schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(business_key_val="P-%d" % i,
                                  updates={"probe_id": "P-%d" % i, "note": "n"},
                                  source_name="user", updated_by="tester")
        for i in range(3)
    ], transaction_id="d39", silent=True)
    results, _cells, _logs, _deleted = crud.apply_batch_updates(db, TABLE, batch)
    db.commit()
    db.close()
    return [item[0] if isinstance(item, tuple) else item for item in results]


def test_the_plain_attribute_read_raises_on_exactly_these_rows(probe_db):
    """The defect itself, so nobody restores the one-liner as an obvious simplification."""
    rows = _rows_as_the_chunk_loop_leaves_them(probe_db)
    with pytest.raises(DetachedInstanceError):
        getattr(rows[0], "row_id")


def test_the_row_id_is_read_without_a_round_trip(probe_db):
    rows = _rows_as_the_chunk_loop_leaves_them(probe_db)
    with record_statements(probe_db) as calls:
        ids = [_row_id_without_a_refresh(r) for r in rows]
    assert all(ids), ids
    assert len(set(ids)) == 3
    #: Not just "it did not raise" - the read the owner paid 10 s of prefetch for is one
    #: SELECT per object, and this asserts there are none at all.
    assert calls == [], [c.sql for c in calls]


def test_a_slow_prefetch_over_detached_rows_returns_instead_of_raising(probe_db):
    rows = _rows_as_the_chunk_loop_leaves_them(probe_db)
    summary = {"write_steps": {"prefetch": 900.0}}   # far over any declared threshold
    assert _maybe_explain_slow_prefetch(probe_db, TABLE, summary, rows, False)
