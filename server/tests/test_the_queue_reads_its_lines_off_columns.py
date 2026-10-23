# -*- coding: utf-8 -*-
"""The chain queue's lines are read off three outbox columns, not off the payload (총괄 c0e6906f1, 소유자 「ㄱ」): a
waiting event of a replay page carries ~40 KB of row ids, and the slot's window and the dispatcher's line list read
every waiting one's payload - 20,000 waiting: 2.3 s and 3.9 s a read.

  every write seat   its row's run_id · transaction_id · row_count are what the payload's SQL reading says
  the line list      the same lines, rows and runs as the payload's reading - run, transaction, row, string payloads
  the fill           a waiting row written before the columns is given them by the same rule; again, none
  PostgreSQL         the seats only it reaches (the notation fold's table insert, an index ask), and a line's window
                     read through idx_outbox_line
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, func, literal, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                                # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from database.context import channel, outbox_mode, retroactive_run    # noqa: E402
from database.database import Base                                    # noqa: E402
from conftest import retire_dynamic_model                             # noqa: E402

T = "lc_probe"
TABLE = {"business_key": "k", "composite_key_source": ["k"], "column_types": {"k": "string", "v": "string"},
         "display_columns": ["k", "v"]}
RUN = "lc-run-1"


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    models.init_dynamic_models({T: TABLE})
    crud.TABLE_CONFIG[T] = TABLE
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    crud.TABLE_CONFIG.pop(T, None)
    retire_dynamic_model(T)


def _write(db, rows, collapsed):
    with channel(event_constants.CHANNEL_API), outbox_mode(
            event_constants.OUTBOX_MODE_COLLAPSED if collapsed else event_constants.OUTBOX_MODE_PER_ROW):
        crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="lc") for row in rows]))
        db.commit()


def _payload_reading(db, after=0):
    """{id: (run_id, transaction_id, row_count)} as the payload's SQL reads them - the queue's reading before."""
    p = models.DatabaseOutbox.payload
    return {row[0]: tuple(row[1:]) for row in db.execute(select(
        models.DatabaseOutbox.id, p["run_id"].as_string(), p["transaction_id"].as_string(),
        p["row_count"].as_integer()).where(models.DatabaseOutbox.id > after))}


def _columns(db, after=0):
    o = models.DatabaseOutbox
    return {row[0]: tuple(row[1:]) for row in db.execute(select(o.id, o.run_id, o.transaction_id, o.row_count)
                                                          .where(o.id > after))}


def _last_id(db):
    return db.execute(select(func.coalesce(func.max(models.DatabaseOutbox.id), 0))).scalar()


def _seat_rows(db, seat):
    """The rows one write seat wrote -> {id: columns}, {id: payload reading}."""
    before = _last_id(db)
    seat(db)
    db.commit()
    return _columns(db, before), _payload_reading(db, before)


def _collapsed_under_a_run(db):
    with retroactive_run(RUN):
        _write(db, [{"k": "a%d" % i, "v": "x"} for i in range(3)], collapsed=True)


def _per_row(db):
    _write(db, [{"k": "b1", "v": "y"}, {"k": "b2", "v": "y"}], collapsed=False)


def _per_row_off_the_orm(db):
    """`replay.fold_written_notation`'s row-by-row events go in by a table insert, off the ORM's flush."""
    from chain import replay

    _write(db, [{"k": "c1", "v": "1.0"}], collapsed=False)
    model = models.DYNAMIC_TABLES[T]
    row = db.query(model).filter(model.business_key_val == "c1").one()
    row.v = "1.0"
    db.query(models.CellSource).filter(models.CellSource.table_name == T, models.CellSource.row_id == row.row_id,
                                       models.CellSource.column_name == "v").one().value = 1.0
    db.commit()
    with outbox_mode(event_constants.OUTBOX_MODE_PER_ROW):
        assert replay.fold_written_notation(db, T, apply=True)["cells_folded"] == 1, "the fold wrote nothing"


def _a_scheduler_run(db):
    from admin import retroactive

    retroactive.publish(db, "resolve", {"table": T})


def _a_reload(db):
    from runtime import system_reload

    system_reload.publish_reload(db)


def _an_undelivered_mark(db):
    import internal_event_client

    assert internal_event_client.record_undelivered_notification(lambda: db, T, "/internal/x", "refused")


def _a_run_now_trigger(db):
    import main

    assert main.trigger_auto_update_run_now(table_name=T, script_name="s.py", db=db)["status"] == "success"


def _an_index_ask(db):
    from runtime import index_wants

    assert index_wants.ask(T, ["v"], "a probe", 9.0, db.get_bind()), "no ask was written"


SEATS = {"collapsed under a run": _collapsed_under_a_run, "per row": _per_row, "a scheduler's run": _a_scheduler_run,
         "a reload": _a_reload, "an undelivered mark": _an_undelivered_mark, "a run-now trigger": _a_run_now_trigger}
#: The seats only PostgreSQL reaches: the fold writes by value there alone (`replay.FOLD_BY_VALUE_DIALECTS`), and an
#: index ask is PostgreSQL's.
PG_SEATS = {"per row off the ORM": _per_row_off_the_orm, "an index ask": _an_index_ask}
#: What each seat's rows carry, so a payload that lost its keys does not pass as «both empty».
CARRIES = {"collapsed under a run": "run", "per row": "transaction", "per row off the ORM": "transaction",
           "a scheduler's run": "run", "a reload": "transaction", "an undelivered mark": "nothing",
           "a run-now trigger": "nothing", "an index ask": "nothing"}


def _assert_the_seat(db, seat, write):
    columns, payload = _seat_rows(db, write)
    assert columns, "the seat wrote no outbox row - this measures nothing"
    assert columns == payload
    carried = {"run": all(c[0] for c in columns.values()),
               "transaction": all(c[1] and not c[0] for c in columns.values()),
               "nothing": all(c == (None, None, None) for c in columns.values())}
    assert carried[CARRIES[seat]], columns


@pytest.mark.parametrize("seat", sorted(SEATS))
def test_every_write_seat_gives_its_row_the_columns_its_payload_says(db, seat):
    _assert_the_seat(db, seat, SEATS[seat])


def _old_lines(db):
    """The line list as the payload read it before - key, run, rows - over the waiting rows."""
    o, p = models.DatabaseOutbox, models.DatabaseOutbox.payload
    key = func.coalesce(p["run_id"].as_string(), p["transaction_id"].as_string(),
                        literal(event_constants.QUEUE_ROW_KEY_PREFIX).concat(func.cast(o.id, models.String)))
    return sorted(db.execute(select(key, func.max(p["run_id"].as_string()),
                                    func.sum(func.coalesce(p["row_count"].as_integer(), 1)), func.min(o.id))
                             .where(o.processed_chain == False).group_by(key)).all(),   # noqa: E712
                  key=lambda r: r[3])


def test_the_line_list_answers_as_the_payload_did(db):
    from chain import queue_lines

    for seat in SEATS.values():
        seat(db)
        db.commit()
    old = _old_lines(db)
    assert len({line[1] is not None for line in old}) == 2 and len(old) >= 5, old
    new = sorted(((line.key, line.run, line.rows, line.first_id) for line in queue_lines.waiting_lines(db, 100)),
                 key=lambda r: r[3])
    assert sorted(new) == sorted(tuple(line) for line in old)
    for key, _run, _rows, _first in old:
        narrow, line = event_constants.queue_line_rows(models.DatabaseOutbox, key)
        window = [e.id for e in db.query(models.DatabaseOutbox.id).filter(
            models.DatabaseOutbox.processed_chain == False, narrow, line)]                 # noqa: E712
        assert window and all(_line_of(db, i) == key for i in window), key


def _line_of(db, event_id):
    o = models.DatabaseOutbox
    return db.execute(select(event_constants.queue_line_key(o)).where(o.id == event_id)).scalar()


def test_a_waiting_row_written_before_the_columns_is_given_them_once(db):
    for seat in SEATS.values():
        seat(db)
        db.commit()
    want = _payload_reading(db)
    db.execute(text("UPDATE database_outbox SET run_id = NULL, transaction_id = NULL, row_count = NULL"))
    db.commit()
    waiting = {i for (i,) in db.execute(text("SELECT id FROM database_outbox WHERE processed_chain = 0"))}
    carrying = {i for i in waiting if any(v is not None for v in want[i])}
    assert carrying, "no waiting row carries a run or a transaction - this measures nothing"
    said = []

    assert models.fill_outbox_line_columns(db.get_bind(), say=said.append) == len(carrying)
    assert {i: c for i, c in _columns(db).items() if i in waiting} == {i: want[i] for i in waiting}
    assert models.fill_outbox_line_columns(db.get_bind(), say=said.append) == 0
    assert said[0] == ("[Chain] outbox line columns: %d of %d waiting event(s) without them filled"
                       % (len(carrying), len(waiting)))


@pytest.fixture(name="pg_db")
def fixture_pg_db(pg_engine):
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(T)
    models.init_dynamic_models({T: TABLE})
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"' % T))
        conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": T})
        conn.execute(text("DELETE FROM database_outbox"))
    Base.metadata.create_all(bind=pg_engine, tables=[models.DYNAMIC_TABLES[T].__table__])
    crud.TABLE_CONFIG[T] = TABLE
    db = sessionmaker(bind=pg_engine, autoflush=False)()
    try:
        yield db
    finally:
        db.close()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(T)
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"' % T))
            conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": T})
            conn.execute(text("DELETE FROM database_outbox"))


@pytest.mark.pg
@pytest.mark.parametrize("seat", sorted(PG_SEATS))
def test_the_seats_postgresql_alone_reaches_give_their_rows_the_columns(pg_db, seat):
    _assert_the_seat(pg_db, seat, PG_SEATS[seat])


@pytest.mark.pg
def test_a_lines_window_is_read_through_its_index(pg_db):
    from chain import ingestion_worker

    _collapsed_under_a_run(pg_db)
    _per_row(pg_db)
    pg_db.execute(text("ANALYZE database_outbox"))
    assert ingestion_worker.pending_chain_events(pg_db, line=RUN), "the run's line waits - else this measures nothing"
    o = models.DatabaseOutbox
    narrow, line = event_constants.queue_line_rows(o, RUN)
    query = select(o.id).where(o.processed_chain == False, narrow, line).order_by(o.id).limit(200)   # noqa: E712
    sql = str(query.compile(dialect=pg_db.get_bind().dialect, compile_kwargs={"literal_binds": True}))
    pg_db.execute(text("SET LOCAL enable_seqscan = off"))
    plan = "\n".join(row[0] for row in pg_db.execute(text("EXPLAIN " + sql)))
    pg_db.rollback()
    assert "idx_outbox_line" in plan, plan
