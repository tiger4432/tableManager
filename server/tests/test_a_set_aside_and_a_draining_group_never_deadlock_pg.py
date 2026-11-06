# -*- coding: utf-8 -*-
"""A × (or a cancelled run's set-aside) landing on a group that is ending deleted rows' events never deadlocks with it
(총괄 11-07, the run 7553f6432f49 of 11-06): both lock the rows the deleted rows fed, THEN the outbox - one order, in
one commit each (09f58844f). The group is held between its withdrawal and its outbox lock until the × waits on a
lock; set-aside used to mark the outbox first and wait on the group's rows while the group waited on its marks."""
import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from chain import ingestion_worker as worker
from chain import set_aside
from database import crud, models
from support import hold_world as hw
from utils import heartbeat
from utils.payload_helper import get_payload_dict

pytestmark = pytest.mark.pg
ROUNDS = 10
OUTBOX = models.DatabaseOutbox


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    monkeypatch.setattr(heartbeat, "beat", lambda *a, **k: None)
    monkeypatch.setattr(heartbeat, "note_work", lambda *a, **k: None)
    monkeypatch.setattr(heartbeat, "read_all", lambda: {})
    yield from hw.build(pg_engine, monkeypatch, tmp_path)


def _waits_or_ended(engine, pid, thread, seconds=20.0):
    end = time.monotonic() + seconds
    with engine.connect() as conn:
        while time.monotonic() < end:
            if not thread.is_alive() or conn.execute(text(
                    "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :p"), {"p": pid}).scalar():
                return True
            time.sleep(0.02)
    return False


def _one_round(world, monkeypatch, n):
    db = world["db"]
    hw.push(world, [{"log_id": "D%d_%d" % (n, i), "dt_job": "J%d_%d" % (n, i), "dt_x": i, "dt_y": 1, "netdie": i}
                    for i in range(3)])
    hw.settle(world)
    ids = [r[0] for r in db.execute(text('SELECT row_id FROM "%s" WHERE log_id LIKE :p' % hw.LOG), {"p": "D%d_%%" % n})]
    crud.delete_rows_batch(db, hw.LOG, ids, "hc")
    db.commit()
    events = (db.query(OUTBOX).filter(OUTBOX.processed_chain.is_(False), OUTBOX.table_name == hw.LOG)
              .order_by(OUTBOX.id).all())
    assert events and {e.event_type for e in events} == {"DELETE"}
    tx_id = get_payload_dict(events[0]).get("transaction_id")
    other = sessionmaker(bind=world["engine"])()
    pid = other.connection().connection.dbapi_connection.get_backend_pid()
    out = {}

    def cross():
        try:
            out["cross"] = set_aside.set_aside_line(other, tx_id, set_aside.OPERATOR)
        except Exception as exc:                            # noqa: BLE001 - the round's answer
            out["cross_error"] = repr(exc)
            other.rollback()
    thread = threading.Thread(target=cross)
    real = worker._ran_though_set_aside

    def after_the_cross_waits(*a, **k):                     # the group has withdrawn; its outbox lock is next
        thread.start()
        out["cross_waited"] = _waits_or_ended(world["engine"], pid, thread)
        return real(*a, **k)
    monkeypatch.setattr(worker, "_ran_though_set_aside", after_the_cross_waits)
    try:
        out["group"] = worker._claimed_group_sync(tx_id, events, db, world["rules"])[:2]
    except Exception as exc:                                # noqa: BLE001
        out["group_error"] = repr(exc)
        db.rollback()
    finally:
        monkeypatch.setattr(worker, "_ran_though_set_aside", real)
    thread.join(30)
    other.close()
    db.rollback()
    db.expire_all()
    out["ended"] = sorted({(e.status, e.processed_chain, get_payload_dict(e).get("cancelled_by"))
                           for e in db.query(OUTBOX).filter(OUTBOX.id.in_([e.id for e in events]))})
    return out


def _deadlocks(engine):
    """The database's deadlock count - a withdrawal swallows its own (`[ChainRetract] retraction failed`), so the
    answers cannot count them. Other backends report theirs within a second of going idle."""
    time.sleep(2)
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_stat_clear_snapshot()"))
        return conn.execute(text("SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()")).scalar()


def test_a_cross_on_a_group_ending_deleted_rows_waits_for_it_and_the_rows_read_as_ran(world, monkeypatch):
    before = _deadlocks(world["engine"])
    rounds = [_one_round(world, monkeypatch, n) for n in range(ROUNDS)]
    deadlocks = _deadlocks(world["engine"]) - before
    assert deadlocks == 0, "%d of %d rounds deadlocked: %r" % (deadlocks, ROUNDS, rounds[:2])
    for r in rounds:
        assert r["cross_waited"] and r["group"] == (True, None), r
        assert r["ended"] == [("SUCCESS", True, None)], r
        assert r["cross"]["marked"] == 0, r
