# -*- coding: utf-8 -*-
"""The flush writes a dynamic table's changed rows ONE array UPDATE per set of changed columns on PostgreSQL
(lead 8af4d378c ㄱ): two rules changing different columns on interleaved rows of one table made the ORM send an UPDATE
per row (box c1: ~1,000 for a 1,000-row chain group). SQLite keeps the ORM's own flush.

  shapes      2,000 rows, two interleaved sets of changed columns -> 2 UPDATEs (PG), the row count does not matter
  same bytes  rows · layers · history lines · outbox events are what the ORM's flush leaves
  read again  the session reads the new values, before and after it expires
  row gone    an UPDATE that touches fewer rows than it names is refused, as the ORM refuses it
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest                                                         # noqa: E402
from sqlalchemy import MetaData, event, text                          # noqa: E402
from sqlalchemy.orm import Session                                    # noqa: E402

import event_constants                                                # noqa: E402
from database import crud, database, models, schemas                  # noqa: E402
from database.context import channel, outbox_mode                     # noqa: E402
from utils.payload_helper import get_payload_dict                     # noqa: E402

T = "shape_rows"
TABLES = {T: {"business_key": "k", "column_types": {"k": "string", "a": "string", "b": "string", "n": "number"}}}
ROWS = 2000


@pytest.fixture(name="db", params=["sqlite", pytest.param("pg", marks=pytest.mark.pg)])
def fixture_db(request):
    session = request.getfixturevalue("pg_session" if request.param == "pg" else "db_session")
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    if request.param == "pg":
        from conftest import PG_TEST_SCHEMA
        scratch = MetaData(schema=PG_TEST_SCHEMA)
        models.DYNAMIC_TABLES[T].__table__.to_metadata(scratch, schema=None)
        scratch.drop_all(session.get_bind())
        scratch.create_all(session.get_bind())
    else:
        database.Base.metadata.create_all(bind=session.get_bind())
    try:
        yield session
    finally:
        if request.param == "pg":
            session.rollback()
            with session.get_bind().begin() as conn:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, T)))


def _write(db, items, tx):
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(source_name=source, updated_by="shape", business_key_val=k, updates=updates)
            for k, source, updates in items], transaction_id=tx))
    db.commit()


def _seed_and_cross(db):
    """2,000 rows; then one batch: even rows' `a` by a file, odd rows' `b` by a person - two shapes, interleaved."""
    _write(db, [("K%04d" % i, "f0.csv", {"k": "K%04d" % i, "a": "a0", "b": "b0", "n": i}) for i in range(ROWS)], "seed")
    _write(db, [("K%04d" % i, "f1.csv", {"a": "a1"}) if i % 2 == 0 else ("K%04d" % i, crud.USER_SOURCE, {"b": "b1"})
                for i in range(ROWS)], "cross")


def _updates_of(db, run):
    seen = []

    def count(conn, cursor, statement, params, context, many):
        if " ".join(statement.split()).upper().startswith(("UPDATE %s" % T).upper()) or \
                " ".join(statement.split()).upper().startswith(('UPDATE "%s"' % T).upper()):
            seen.append(statement)

    engine = db.get_bind()
    event.listen(engine, "after_cursor_execute", count)
    try:
        run()
    finally:
        event.remove(engine, "after_cursor_execute", count)
    return seen


def _state(db):
    """What the write left, by business key: rows, layers, history lines, the cross batch's events."""
    db.expire_all()
    model = models.DYNAMIC_TABLES[T]
    by_id = {row.row_id: row.business_key_val for row in db.query(model)}
    rows = sorted(((row.business_key_val, row.a, row.b, row.n) for row in db.query(model)), key=repr)
    layers = sorted(((by_id[s.row_id], s.column_name, s.source_name, str(s.value), s.updated_by)
                    for s in db.query(models.CellSource).filter_by(table_name=T)), key=repr)
    history = sorted(((by_id.get(h.row_id), h.column_name, h.old_value, h.new_value, h.source_name, h.updated_by)
                     for h in db.query(models.AuditLog).filter_by(table_name=T)), key=repr)
    events = []
    for event_row in db.query(models.DatabaseOutbox).filter_by(table_name=T).order_by(models.DatabaseOutbox.id):
        payload = get_payload_dict(event_row)
        if payload.get("transaction_id") != "cross":
            continue
        old = payload.get(event_constants.OLD_VALUES_KEY) or [{}] * len(payload["row_ids"])
        # per row - which rows share a 1,000-row event follows the session's own set order, run to run
        events.extend((by_id[r], event_row.event_type, tuple(payload.get("columns") or ()), tuple(sorted(o.items())))
                      for r, o in zip(payload["row_ids"], old))
    return rows, layers, history, sorted(events, key=repr)


def test_interleaved_shapes_are_one_update_each(db):
    statements = _updates_of(db, lambda: _seed_and_cross(db))
    cross = [s for s in statements]
    if db.get_bind().dialect.name == "postgresql":
        assert len(cross) == 2, "one array UPDATE per set of changed columns, not one per row"
    rows, _layers, _history, _events = _state(db)
    assert rows[:2] == [("K0000", "a1", "b0", 0), ("K0001", "a0", "b1", 1)]


@pytest.mark.pg
def test_the_flush_leaves_the_bytes_the_orm_leaves(db):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("the array writer is PostgreSQL's")
    from conftest import PG_TEST_SCHEMA

    def empty():
        db.rollback()             # the session's reads hold the tables a TRUNCATE waits for
        with db.get_bind().begin() as conn:
            conn.execute(text('TRUNCATE "%s"."%s", "%s".cell_sources, "%s".audit_logs, "%s".database_outbox'
                              % (PG_TEST_SCHEMA, T, PG_TEST_SCHEMA, PG_TEST_SCHEMA, PG_TEST_SCHEMA)))

    event.remove(Session, "before_flush", database.write_changed_rows_by_shape)
    try:
        orm = _updates_of(db, lambda: _seed_and_cross(db))
        by_orm = _state(db)
    finally:
        event.listen(Session, "before_flush", database.write_changed_rows_by_shape)
    empty()
    arrays = _updates_of(db, lambda: _seed_and_cross(db))

    assert len(orm) > 100 and len(arrays) == 2, "control: the ORM sends a statement per interleaved row"
    assert _state(db) == by_orm


@pytest.mark.pg
def test_the_session_reads_the_new_values(db):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("the array writer is PostgreSQL's")
    _seed_and_cross(db)
    model = models.DYNAMIC_TABLES[T]
    row = db.query(model).filter_by(business_key_val="K0000").one()
    row.a, row.n = "a2", 7
    other = db.query(model).filter_by(business_key_val="K0002").one()
    other.a, other.n = "a3", 8
    db.flush()
    assert (db.query(model).filter_by(business_key_val="K0000").one().a, row.n) == ("a2", 7)
    db.commit()
    db.expire_all()
    assert [(r.a, r.n) for r in db.query(model).filter(model.business_key_val.in_(["K0000", "K0002"]))
            .order_by(model.business_key_val)] == [("a2", 7), ("a3", 8)]


@pytest.mark.pg
def test_a_row_gone_from_under_the_write_is_refused(db):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("the array writer is PostgreSQL's")
    from conftest import PG_TEST_SCHEMA

    _seed_and_cross(db)
    model = models.DYNAMIC_TABLES[T]
    row = db.query(model).filter_by(business_key_val="K0004").one()
    row.a = "a9"
    with db.get_bind().begin() as conn:      # another writer deletes it
        conn.execute(text('DELETE FROM "%s"."%s" WHERE k = :k' % (PG_TEST_SCHEMA, T)), {"k": "K0004"})
    with pytest.raises(RuntimeError, match="went from under the write"):
        db.flush()
