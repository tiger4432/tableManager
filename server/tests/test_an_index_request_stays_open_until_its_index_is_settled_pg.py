# -*- coding: utf-8 -*-
"""총괄 11-07 ㄱ (소유자 «미뤄진 인덱스 알아서 시간 빌 때 지면 안 됨?»): an index request (INDEX_WANTED) is closed by what
happened to its index, not when it is taken - the put-off one stays an open row, so a scheduler started again alone
takes it from the database and builds it once nothing holds its table.

  put off      a writer left open past the wait -> the row stays open, no index; asked again -> still one row
  taken again  the line's memory empty (a restart) and the writer gone -> built, the row SUCCESS
  ruled out    its table at auto_index_per_table -> the row FAILED, said
  one wait     two requests held: the oldest waits the whole wait, the other none (⑴) - both stay open
  backlog      an open request is not the chain's backlog: health's outbox check and the loop's depth leave it out,
               as the chain worker's claim does (one predicate, event_constants.chain_waiting)
"""
import json
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from database import crud, models

pytestmark = pytest.mark.pg
TABLE = "ix_ask_probe"
ENTRY = {"business_key": "k", "composite_key_source": ["k"],
         "column_types": {"k": "string", "s": "string", "n": "number"}}


@pytest.fixture(name="table")
def fixture_table(pg_engine, monkeypatch):
    from sqlalchemy import MetaData

    import event_constants
    from chain import ingestion_worker as worker
    from conftest import PG_TEST_SCHEMA
    from runtime import maintenance_line, system_reload

    models.init_dynamic_models({TABLE: ENTRY})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[TABLE].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text('INSERT INTO "%s"."%s" (row_id, business_key_val, k, s, n) '
                          "SELECT 'r' || g, 'K' || g, 'K' || g, 'S' || (g %% 7), g FROM generate_series(1, 200) g"
                          % (PG_TEST_SCHEMA, TABLE)))
    monkeypatch.setattr(models, "INDEX_WAIT_BEFORE_SECONDS", 1.0)
    monkeypatch.setattr(models, "INDEX_WAIT_POLL_SECONDS", 0.2)
    monkeypatch.setattr(maintenance_line, "_LEFT", [])
    monkeypatch.setattr(system_reload, "reloads_after", lambda db, mark: [])
    monkeypatch.setattr(system_reload, "reload_for", lambda *a: False)
    monkeypatch.setattr(worker, "_analyze_stale_tables_sync", lambda *a, **k: None)
    try:
        yield pg_engine
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
            conn.execute(text("DELETE FROM database_outbox WHERE event_type = :t"),
                         {"t": event_constants.EVENT_INDEX_WANTED})


def _rows(engine):
    """[(columns, processed_chain, status)] of this table's requests, oldest first."""
    import event_constants

    with engine.connect() as conn:
        return [(json.loads(p)["columns"] if isinstance(p, str) else p["columns"], done, status)
                for p, done, status in conn.execute(text(
                    "SELECT payload, processed_chain, status FROM database_outbox WHERE event_type = :t "
                    "AND table_name = :table ORDER BY id"), {"t": event_constants.EVENT_INDEX_WANTED, "table": TABLE})]


def _autos(engine):
    return sorted(row["name"] for row in models.index_states(engine, {TABLE: ENTRY}, static=False)["declared"]
                  if row["source"] == "auto")


def _held(engine):
    """A writer of the table left open past the wait before a build -> its connection."""
    holder = engine.connect()
    holder.execute(text("INSERT INTO \"%s\" (row_id, business_key_val, k) VALUES ('held', 'H', 'H')" % TABLE))
    time.sleep(1.5)
    return holder


def _poll(engine):
    from runtime import maintenance_line

    maintenance_line.poll_once(sessionmaker(bind=engine), 0)


def test_a_put_off_request_stays_open_and_is_built_when_taken_again(table):
    from runtime import index_wants, maintenance_line

    assert index_wants.ask(TABLE, ["s"], models.AUTO_SLOW_SORT, 1.5, table) is True
    holder = _held(table)
    try:
        _poll(table)
        assert _rows(table) == [(["s"], False, "PENDING")] and _autos(table) == [], "put off - open, nothing built"
        assert index_wants.ask(TABLE, ["s"], models.AUTO_SLOW_SORT, 1.5, table) is False, "the open row is the ask"
        assert len(_rows(table)) == 1
    finally:
        holder.rollback()
        holder.close()
    maintenance_line._LEFT[:] = []                                   # a scheduler started again: its memory empty
    _poll(table)
    assert _autos(table) == [models.auto_index_name(TABLE, ["s"], models.AUTO_SLOW_SORT)], "taken from its row, built"
    assert _rows(table) == [(["s"], True, "SUCCESS")]


def test_a_request_ruled_out_is_closed_failed(table, monkeypatch):
    from parsers import directory_watcher
    from runtime import index_wants

    assert index_wants.ask(TABLE, ["s"], models.AUTO_SLOW_SORT, 1.5, table) is True
    monkeypatch.setattr(directory_watcher, "auto_index_per_table", lambda: 0)    # its table at the cap
    _poll(table)
    assert _rows(table) == [(["s"], True, "FAILED")] and _autos(table) == []


def test_a_poll_waits_for_the_oldest_put_off_request_only(table, monkeypatch):
    from runtime import index_wants, maintenance_line

    said = []

    class Logger:
        def __getattr__(self, _level):
            return lambda line, *args: said.append(line % args if args else line)

    monkeypatch.setattr(maintenance_line, "logger", Logger())
    assert index_wants.ask(TABLE, ["s"], models.AUTO_SLOW_SORT, 1.5, table) is True
    assert index_wants.ask(TABLE, ["n"], models.AUTO_SLOW_SORT, 1.5, table) is True
    holder = _held(table)
    try:
        _poll(table)
    finally:
        holder.rollback()
        holder.close()
    put_off = [line for line in said if "not built - waited" in line]
    assert len(put_off) == 2 and "waited 1s" in put_off[0] and "waited 0s" in put_off[1], said
    assert [done for _columns, done, _status in _rows(table)] == [False, False], "both stay open"


def test_an_open_request_is_not_the_chain_s_backlog(table):
    import event_constants
    from chain import ingestion_worker as worker
    from runtime import health, index_wants, loops

    db = sessionmaker(bind=table)()
    try:
        before = (health.probe_outbox(db)["pending"], loops._outbox_depth(db), len(worker.pending_chain_events(db)))
        assert index_wants.ask(TABLE, ["s"], models.AUTO_SLOW_SORT, 1.5, table) is True
        assert _rows(table) == [(["s"], False, "PENDING")], "CANARY: an open request"
        after = (health.probe_outbox(db)["pending"], loops._outbox_depth(db), len(worker.pending_chain_events(db)))
        outbox = models.DatabaseOutbox
        mine = (db.query(outbox).filter(outbox.table_name == TABLE, outbox.processed_chain.is_(False)).count(),
                db.query(outbox).filter(outbox.table_name == TABLE, *event_constants.chain_waiting(outbox)).count())
    finally:
        db.close()
    assert after == before, (before, after)
    assert mine == (1, 0), "the request is open, and outside the chain's waiting set"


def _pending(db, limit, line):
    """What a slot given `line` reads of it - the chain's waiting rows (`pending_chain_events`)."""
    from chain import ingestion_worker

    return ingestion_worker.pending_chain_events(db, limit=limit, line=line)


def test_open_requests_more_than_the_slots_leave_a_data_line_given(table):
    """B's board: open index requests ahead of a data line, more than the slots and no scheduler - the lines a slot is
    given (chain.queue_lines.waiting_lines chain_only, cut at the slot count) hold the data line, not the requests."""
    import event_constants
    from chain import queue_lines, slots
    from runtime import index_wants

    for column in ("s", "n", "k"):
        assert index_wants.ask(TABLE, [column], models.AUTO_SLOW_SORT, 1.5, table) is True
    db = sessionmaker(bind=table)()
    try:
        db.add(models.DatabaseOutbox(table_name=TABLE, event_type="INSERT", event_uuid=str(uuid.uuid4()),
                                     payload={"row_id": "r1", "transaction_id": "data-line"}))
        db.commit()
        assert len(_rows(table)) == 3, "CANARY: three open requests ahead"
        # what a slot given each line reads of it (the chain's waiting rows)
        given = [(e.table_name, e.event_type) for line in queue_lines.waiting_lines(db, 2, chain_only=True)
                 for e in _pending(db, limit=200, line=line.key)]
        dispatched = [line["line"] for line in slots.SlotPool(spawn=lambda index: None)._givable(db, [], set(), 2)[0]]
        listed = queue_lines.waiting_lines(db, 10)
    finally:
        db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.transaction_id == "data-line").delete()
        db.commit()
        db.close()
    assert given == [(TABLE, "INSERT")], given
    assert event_constants.EVENT_INDEX_WANTED not in {kind for _t, kind in given}
    assert len(listed) == 4, "the queue screen still lists the open requests"
    assert dispatched == ["data-line"], dispatched


def test_a_line_mixing_a_control_row_and_a_data_row_gives_the_data_row_and_lists_both(table):
    """총괄 11-07: one transaction holding a control row and a data row - the line a slot is given counts the data row
    only (events, rows); the queue screen's line counts both."""
    import event_constants
    from chain import queue_lines

    outbox = models.DatabaseOutbox
    db = sessionmaker(bind=table)()
    try:
        db.add(outbox(table_name=TABLE, event_type=event_constants.EVENT_INDEX_WANTED, event_uuid=str(uuid.uuid4()),
                      payload={"columns": ["s"], "transaction_id": "mixed-line"}))
        db.add(outbox(table_name=TABLE, event_type="INSERT", event_uuid=str(uuid.uuid4()),
                      payload={"row_id": "r1", "transaction_id": "mixed-line"}))
        db.commit()
        assert db.query(outbox).filter(outbox.transaction_id == "mixed-line").count() == 2, "CANARY: both rows"
        # the line a slot is given: what it reads of it (the chain's waiting rows); the screen: the line's counts
        given = [(l.key, [(e.table_name, e.event_type) for e in _pending(db, limit=200, line=l.key)])
                 for l in queue_lines.waiting_lines(db, 10, chain_only=True)]
        lines = queue_lines.waiting_lines(db, 10)
        counts = queue_lines.line_counts(db, lines)
        listed = [(l.key, counts[l.key].events, counts[l.key].rows, sorted(counts[l.key].pairs)) for l in lines]
    finally:
        db.query(outbox).filter(outbox.transaction_id == "mixed-line").delete()
        db.commit()
        db.close()
    assert given == [("mixed-line", [(TABLE, "INSERT")])], given
    assert listed == [("mixed-line", 2, 2, sorted([(TABLE, event_constants.EVENT_INDEX_WANTED), (TABLE, "INSERT")]))], \
        listed
