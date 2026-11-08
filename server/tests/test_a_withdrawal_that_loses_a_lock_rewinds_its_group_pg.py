# -*- coding: utf-8 -*-
"""A withdrawal of what deleted rows fed that loses a lock (a deadlock, a lock timeout - `db_safety.lost_a_lock`) is
never only a log line (총괄 11-07): it is raised at once (QA 11-08 - a retry inside ran after its pages had released
their steps and found nothing) - the group rewinds, a × is told 409 `SAVE_AGAIN`, and the cells and the events stay
as they were for the next try."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

import db_safety
from chain import ingestion_worker as worker
from chain import set_aside, table_locks
from database import crud, models
from support import hold_world as hw
from utils import heartbeat
from utils.payload_helper import get_payload_dict

pytestmark = pytest.mark.pg
OUTBOX = models.DatabaseOutbox


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    monkeypatch.setattr(heartbeat, "beat", lambda *a, **k: None)
    monkeypatch.setattr(heartbeat, "note_work", lambda *a, **k: None)
    monkeypatch.setattr(heartbeat, "read_all", lambda: {})
    yield from hw.build(pg_engine, monkeypatch, tmp_path)


def _losing(monkeypatch, times):
    """`_withdraw_and_tell` loses a lock the first `times` calls, as PostgreSQL breaking a deadlock says it."""
    real, calls = worker._withdraw_and_tell, []

    def withdraw(*a, **k):
        calls.append(1)
        if len(calls) <= times:
            raise OperationalError("SELECT 1 FOR UPDATE", {}, Exception("deadlock detected"))
        return real(*a, **k)
    monkeypatch.setattr(worker, "_withdraw_and_tell", withdraw)
    return calls


def _deleted(world):
    db = world["db"]
    hw.push(world, [{"log_id": "L%d" % i, "dt_job": "J%d" % i, "dt_x": i, "dt_y": 1, "netdie": i} for i in range(3)])
    hw.settle(world)
    ids = [r[0] for r in db.execute(text('SELECT row_id FROM "%s"' % hw.LOG))]
    crud.delete_rows_batch(db, hw.LOG, ids, "hc")
    db.commit()
    events = (db.query(OUTBOX).filter(OUTBOX.processed_chain.is_(False), OUTBOX.table_name == hw.LOG)
              .order_by(OUTBOX.id).all())
    return ids, events


def _fed(world, ids):
    return world["db"].execute(text("SELECT count(*) FROM cell_sources WHERE table_name = :t AND origin_row_id = ANY(:i)"),
                               {"t": hw.OFFICIAL, "i": ids}).scalar()


def test_lost_once_it_is_raised_and_the_cells_stay_for_the_next_try(world, monkeypatch):
    ids, _events = _deleted(world)
    fed = _fed(world, ids)
    assert fed > 0
    calls = _losing(monkeypatch, 1)
    with pytest.raises(OperationalError):
        worker._withdraw_unanswered_deletions(world["db"], {hw.LOG: ids}, "unanswered")
    world["db"].rollback()
    world["db"].expire_all()
    assert len(calls) == 1 and _fed(world, ids) == fed


def test_lost_the_group_rewinds_and_nothing_is_ended(world, monkeypatch):
    ids, events = _deleted(world)
    fed = _fed(world, ids)
    _losing(monkeypatch, 1)
    tx_id = get_payload_dict(events[0]).get("transaction_id")
    ok, reason = worker._claimed_group_sync(tx_id, events, world["db"], world["rules"])[:2]
    world["db"].rollback()
    assert not ok and table_locks.rewinds(reason) and db_safety.lost_a_lock(reason), reason
    world["db"].expire_all()
    assert _fed(world, ids) == fed
    assert {e.processed_chain for e in world["db"].query(OUTBOX).filter(OUTBOX.id.in_([e.id for e in events]))} == {False}


def test_lost_a_cross_is_raised_to_its_409_and_marks_nothing(world, monkeypatch):
    ids, events = _deleted(world)
    fed = _fed(world, ids)
    _losing(monkeypatch, 1)
    tx_id = get_payload_dict(events[0]).get("transaction_id")
    with pytest.raises(OperationalError) as raised:
        set_aside.set_aside_line(world["db"], tx_id, set_aside.OPERATOR)
    world["db"].rollback()
    assert db_safety.lost_a_lock(raised.value)                 # main's handler: 409 SAVE_AGAIN
    world["db"].expire_all()
    assert _fed(world, ids) == fed
    assert {(e.processed_chain, get_payload_dict(e).get("cancelled_by"))
            for e in world["db"].query(OUTBOX).filter(OUTBOX.id.in_([e.id for e in events]))} == {(False, None)}
