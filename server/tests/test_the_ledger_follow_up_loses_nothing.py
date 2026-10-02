# -*- coding: utf-8 -*-
"""총괄 bb9b1c19c (가) · 1472ec1cc — the ledger's follow-up loses nothing (소유자 10-02 「누락 절대 없고」).

The live queue is the outbox row's ledger mark (`ledger_state`), on PostgreSQL, on the hold
world: the chain group commits and marks its events processed; the ledger takes them from the
outbox after that, as it used to take them from memory.

  restart between the chain's commit and the drain     every row still said (today: 0 of 2,000)
  more events than the memory queue held               none dropped
  a follow that fails                                  listed, and back on the queue by one call
  an event no rule matches                             followed
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from database import crud, models, schemas                          # noqa: E402
from ledger import backfill, followup                               # noqa: E402
from support import hold_world as hw                                # noqa: E402

pytestmark = pytest.mark.pg


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path)


def _rows(n, start=0):
    return [{"log_id": "L%05d" % i, "dt_job": "J%05d" % i, "dt_x": 1, "dt_y": 2, "netdie": i % 97}
            for i in range(start, start + n)]


def test_a_restart_between_the_chains_commit_and_the_drain_loses_nothing(world):
    hw.push(world, _rows(2000))
    hw.run_chain(world)
    followup.reset()                                                  # the restart
    assert followup.outbox_depth(world["engine"]) > 0
    hw.settle(world)
    assert len(hw.said(world)) == 2000
    assert followup.outbox_depth(world["engine"]) == 0


def test_the_ledger_follows_what_the_chain_has_processed(world):
    """The moment the group step used to queue it: an event the chain has not run waits."""
    hw.push(world, _rows(1))
    assert followup.drain_outbox_once(world["engine"], world["setup"]) is None
    hw.run_chain(world)
    assert followup.drain_outbox_once(world["engine"], world["setup"]) is not None


def test_more_events_than_the_memory_queue_held_are_all_followed(world, monkeypatch):
    monkeypatch.setattr(followup, "MAX_QUEUED_EVENTS", 3)
    for i in range(8):
        hw.push(world, _rows(1, start=i))
    hw.settle(world)
    assert len(hw.said(world)) == 8
    assert "dropped" not in (followup.note() or "")


def test_a_failed_follow_is_listed_and_put_back_by_one_call(world, monkeypatch):
    real = backfill.rescope

    def fails(*args, **kwargs):
        raise RuntimeError("the source could not be read")

    monkeypatch.setattr(backfill, "rescope", fails)
    hw.push(world, _rows(1))
    hw.run_chain(world)
    while followup.drain_outbox_once(world["engine"], world["setup"]) is not None:
        pass
    total, listed = followup.failed_events(world["engine"])
    assert total >= 1 and hw.said(world) == []
    assert all("the source could not be read" in state for _id, _t, _e, state in listed)
    monkeypatch.setattr(backfill, "rescope", real)
    assert followup.requeue_failed(world["engine"]) == total
    hw.settle(world)
    assert followup.failed_events(world["engine"])[0] == 0
    assert len(hw.said(world)) == 1


def test_an_event_no_rule_matches_is_followed(world):
    world["rules"] = []
    db = world["db"]
    crud.apply_batch_updates(db, hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={**hw.KEY, "netdie": 5, "hold": "agreed"},
                                  source_name=crud.USER_SOURCE, updated_by="person")]))
    db.commit()
    hw.settle(world)
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 5.0)]
    assert db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == hw.OFFICIAL,
        models.DatabaseOutbox.ledger_state != followup.LEDGER_DONE).count() == 0


def _event(db, event_type="EDIT", processed=True, state=None, days_old=0):
    from datetime import datetime, timedelta, timezone
    row = models.DatabaseOutbox(event_uuid="hc-%s-%s" % (event_type, days_old), event_type=event_type,
                                table_name=hw.LOG, payload={"row_id": "r-none"},
                                processed_chain=processed, ledger_state=state,
                                created_at=datetime.now(timezone.utc) - timedelta(days=days_old))
    db.add(row)
    db.commit()
    return row.id


def test_a_kind_the_ledger_does_not_follow_is_marked_done_on_the_way_past(world):
    db = world["db"]
    reload_id = _event(db, event_type="SYSTEM_RELOAD")
    assert followup.drain_outbox_once(world["engine"], world["setup"]) is None
    db.expire_all()
    assert db.get(models.DatabaseOutbox, reload_id).ledger_state == followup.LEDGER_DONE


def test_the_purge_keeps_an_old_event_the_ledger_has_yet_to_follow(world):
    from sqlalchemy.orm import sessionmaker
    from chain import ingestion_worker as worker

    db = world["db"]
    waiting = _event(db, days_old=30)
    followed = _event(db, state=followup.LEDGER_DONE, days_old=30)
    worker.purge_expired_outbox_sync(sessionmaker(bind=world["engine"]), retention_days=7)
    db.expire_all()
    assert db.get(models.DatabaseOutbox, waiting) is not None
    assert db.get(models.DatabaseOutbox, followed) is None


def test_the_migration_marks_the_old_events_done_and_leaves_the_unprocessed_to_follow(world):
    from conftest import PG_TEST_SCHEMA
    from sqlalchemy import text
    from migrations import add_outbox_ledger_state as migration

    db = world["db"]
    db.execute(text('ALTER TABLE "%s".database_outbox DROP COLUMN ledger_state' % PG_TEST_SCHEMA))
    db.commit()
    for processed in (True, False):
        db.execute(text('INSERT INTO "%s".database_outbox (event_uuid, event_type, table_name, '
                        'payload, processed_chain) VALUES (:u, :e, :t, :p, :c)' % PG_TEST_SCHEMA),
                   {"u": "hc-mig-%s" % processed, "e": "EDIT", "t": hw.LOG, "p": "{}", "c": processed})
    db.commit()
    db.close()                                   # no open transaction of this run in the way
    for _ in range(2):                                                # idempotent
        connection = world["engine"].raw_connection()
        try:
            migration.apply(connection)
        finally:
            connection.close()
    states = dict(db.execute(text('SELECT processed_chain, ledger_state FROM "%s".database_outbox '
                                  "WHERE event_uuid LIKE 'hc-mig-%%'" % PG_TEST_SCHEMA)).fetchall())
    assert states == {True: followup.LEDGER_DONE, False: None}
    assert db.execute(text("SELECT to_regclass(:i) IS NOT NULL"),
                      {"i": "%s.%s" % (PG_TEST_SCHEMA, migration.INDEX)}).scalar()


def test_the_workers_drain_takes_from_the_outbox(world, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from chain import ingestion_worker as worker
    import ledger.setup

    monkeypatch.setattr(ledger.setup, "load_setup", lambda *a, **k: world["setup"])
    hw.push(world, _rows(1))
    hw.run_chain(world)
    followup.reset()
    before = followup.outbox_depth(world["engine"])
    done = worker._drain_ledger_followup_sync(sessionmaker(bind=world["engine"]))
    assert done is not None and followup.outbox_depth(world["engine"]) == before - 1


def _held_after_writing(world):
    """A session idle in a transaction that WROTE to the outbox - what holds both steps."""
    from conftest import PG_TEST_SCHEMA
    from sqlalchemy import text

    held = world["engine"].connect()
    held.begin()
    held.execute(text('INSERT INTO "%s".database_outbox (event_uuid, event_type, table_name, '
                      "payload, processed_chain) VALUES ('hc-held', 'EDIT', 'hc', '{}', true)"
                      % PG_TEST_SCHEMA))
    return held, held.execute(text("SELECT pg_backend_pid()")).scalar()


def _apply(world, migration):
    connection = world["engine"].raw_connection()
    try:
        migration.apply(connection)
    finally:
        connection.close()


def test_the_migration_names_the_session_it_waited_for_and_finishes_after(world, monkeypatch):
    """총괄 a3d19dc51 ③: an open transaction on the outbox stops the run by name, never in silence;
    run again after it ends and the column and the index are there."""
    from conftest import PG_TEST_SCHEMA
    from sqlalchemy import text
    from migrations import add_outbox_ledger_state as migration

    monkeypatch.setattr(migration, "LOCK_TIMEOUT", "1s")
    world["db"].execute(text('ALTER TABLE "%s".database_outbox DROP COLUMN ledger_state' % PG_TEST_SCHEMA))
    world["db"].commit()
    world["db"].close()
    held, pid = _held_after_writing(world)
    try:
        with pytest.raises(migration.Waited) as stopped:
            _apply(world, migration)
        assert "add column" in str(stopped.value) and "pid %d" % pid in str(stopped.value)
    finally:
        held.rollback()
        held.close()
    _apply(world, migration)
    connection = world["engine"].raw_connection()
    try:
        assert migration._column_exists(connection) and migration._index_valid(connection) is True
    finally:
        connection.close()


def test_an_index_build_cut_off_is_dropped_and_built_again(world, monkeypatch):
    from conftest import PG_TEST_SCHEMA
    from sqlalchemy import text
    from migrations import add_outbox_ledger_state as migration

    monkeypatch.setattr(migration, "LOCK_TIMEOUT", "1s")
    world["db"].execute(text('DROP INDEX "%s".%s' % (PG_TEST_SCHEMA, migration.INDEX)))
    world["db"].commit()
    world["db"].close()
    held, pid = _held_after_writing(world)
    try:
        with pytest.raises(migration.Waited) as stopped:
            _apply(world, migration)
        assert "build the index" in str(stopped.value) and "pid %d" % pid in str(stopped.value)
        connection = world["engine"].raw_connection()
        try:
            assert migration._index_valid(connection) is False            # left by the cut-off
        finally:
            connection.close()
    finally:
        held.rollback()
        held.close()
    _apply(world, migration)
    connection = world["engine"].raw_connection()
    try:
        assert migration._index_valid(connection) is True
    finally:
        connection.close()
