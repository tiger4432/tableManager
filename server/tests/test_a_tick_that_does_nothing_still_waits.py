# -*- coding: utf-8 -*-
"""S-252. 체인 루프는 «자기가 소비할 수 있는 행»만 가져오고, 진행 0 인 틱 뒤에는 «기다린다».

🔴 THE OUTAGE, MEASURED WITH py-spy 2026-09-15. The owner pressed a join backfill in the
box. That wrote ONE `RETROACTIVE_RUN` outbox row - a CONTROL type owned by the scheduler
(`run_auto_update.py`), which was not running there. The chain loop fetched that row every
tick (its pending query had no type filter), skipped it as CONTROL, and then found
`pending_events` non-empty - so it never reached the `await listener.wait(2.0)` that is the
only yield on the idle path. **A loop with no `await`.**

⛔ AND IT RUNS ON THE EVENT-LOOP THREAD. Every uvicorn request, static HTML included,
stopped answering. Nothing was blocked in the database (`pg_blocking_pids` = 0) and no
restart was needed: starting the scheduler consumed the row and HTTP came back - which is
what proved the diagnosis.

🔴 「ROWS WERE FETCHED」 AND 「THERE IS WORK」 ARE DIFFERENT FACTS, and treating them as one
IS the loop. Both repairs are scored here: the query stops asking for another daemon's
rows, AND a tick that did nothing waits anyway - so the next kind of row this loop cannot
use costs a wait rather than a starved process.
"""
import asyncio
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from database import models                                         # noqa: E402

CONTROL = event_constants.EVENT_RETROACTIVE_RUN


@pytest.fixture(name="empty_queue")
def fixture_empty_queue(db_session):
    """⚠️ THE SHARED FIXTURE ARRIVES WITH ROWS ALREADY WAITING, and a test that assumed an
    empty outbox would be asserting about them instead of about this round. Finishing them
    first makes 「what this query returns」 a statement about the rows THIS test made."""
    db_session.query(models.DatabaseOutbox).update({"processed_chain": True})
    db_session.commit()
    return db_session


def _row(db, event_type, table_name="dt_log"):
    import uuid

    row = models.DatabaseOutbox(event_uuid=str(uuid.uuid4()), event_type=event_type,
                                table_name=table_name, payload={},
                                processed_chain=False, status="PENDING")
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the query: another daemon's row is not this loop's queue
# ---------------------------------------------------------------------------

def test_a_control_row_is_not_fetched_at_all(empty_queue):
    """🔴 THE ROW THAT FROZE THE BOX. It is addressed to the scheduler; this loop has
    always skipped it AFTER fetching, and fetching is what kept the tick 「busy」."""
    _row(empty_queue, CONTROL, event_constants.RETROACTIVE_RUN_TABLE)

    assert worker.pending_chain_events(empty_queue) == []


def test_a_data_row_beside_it_is_still_fetched(empty_queue):
    """⚠️ THE CONTROL, AND IT MUST FAIL FOR A DIFFERENT REASON IF THE FILTER GOES TOO FAR.
    A filter that took the data row too would make this loop quiet by making it useless."""
    _row(empty_queue, CONTROL, event_constants.RETROACTIVE_RUN_TABLE)
    wanted = _row(empty_queue, "CREATE")

    fetched = worker.pending_chain_events(empty_queue)

    assert [event.id for event in fetched] == [wanted.id]


@pytest.mark.parametrize("control_type", sorted(event_constants.CONTROL_EVENT_TYPES))
def test_every_control_type_is_excluded_not_just_the_one_that_broke_it(empty_queue,
                                                                      control_type):
    """⚠️ MEMBERSHIP IN THE SHARED SET, NOT THE ONE NAME FROM THE INCIDENT. A second
    control type was added once already (`RETROACTIVE_RUN` - the one that froze the box),
    and a filter naming a literal would have let the next one through the same way."""
    _row(empty_queue, control_type)

    assert worker.pending_chain_events(empty_queue) == []


def test_the_head_watch_never_sees_a_row_it_cannot_drain(empty_queue):
    """⚠️ THE STALL INSTRUMENT WATCHES THE HEAD OF THIS FETCH. A row nobody here can drain
    sitting at that head is a permanent 「the queue is not moving」 - the instrument would
    be right about the row and wrong about the loop."""
    _row(empty_queue, CONTROL, event_constants.RETROACTIVE_RUN_TABLE)

    fetched = worker.pending_chain_events(empty_queue)
    watch = worker.QueueHeadWatch(stall_after=60.0, now=1000.0)

    assert watch.observe(len(fetched), fetched[0].id if fetched else None,
                         now=2000.0) is None


# ---------------------------------------------------------------------------
# ⛔ ⓑ — the shape: a tick that did nothing waits anyway
# ---------------------------------------------------------------------------

class _StopWhenAnswered(BaseException):
    """🔴 A `BaseException`, AND THAT IS THE POINT. The loop catches `Exception` and sleeps
    three seconds - itself a yield - so an ordinary exception would end this test by doing
    the very thing it exists to detect the absence of."""


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def first(self):
        return None

    def all(self):
        return list(self.rows)


class _Session:
    """⚠️ BOUNDED ON BOTH SIDES, AND NEITHER BOUND IS A CLOCK. A wall-clock bound cannot end
    a loop that never awaits - `asyncio.wait_for` needs a yield before it can cancel - so
    the defect this file is about would make the TEST hang instead of failing. Enough yields
    ends the run as a pass; too many queries without one ends it as a failure. Both in
    milliseconds."""

    def __init__(self, rows, enough_waits, patience):
        self.rows = rows
        self.enough_waits = enough_waits
        self.patience = patience
        self.queries = 0

    def query(self, *a, **k):
        self.queries += 1
        if _Listener.waits >= self.enough_waits or self.queries > self.patience:
            raise _StopWhenAnswered()
        return _Query(self.rows)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _Listener:
    """Counts the yields. The count IS the subject of this half."""

    waits = 0

    def __init__(self, *a, **k):
        pass

    async def start(self):
        pass

    async def stop(self):
        pass

    def close(self):
        pass

    async def wait(self, timeout):
        type(self).waits += 1
        await asyncio.sleep(0)
        return False


class _Control:
    """A CONTROL row that reached the loop ANYWAY - the fetch filter is not the only way one
    could arrive, and the shape has to hold without it."""
    id = 5137807
    event_type = CONTROL
    table_name = event_constants.RETROACTIVE_RUN_TABLE
    payload = {}
    processed_chain = False


async def _noop_coroutine(*_a, **_k):
    return None


@pytest.fixture(name="loop_over")
def fixture_loop_over(monkeypatch):
    """The REAL loop, over a queue this round decides."""
    def _run(rows, enough_waits=3, patience=400):
        _Listener.waits = 0
        sessions = []
        # 🔴 THE LOOP STANDS DOWN IF ANOTHER ONE IS LIVE, and on a developer box one usually
        # IS - so without this the fixture measures whether a chain worker happens to be
        # running rather than what the loop does. Measured: `start_chain_ingestion_worker`
        # returned before its first query, and this file went green or red with the machine.
        monkeypatch.setattr(worker, "another_chain_loop_is_running", lambda *a, **k: None)
        monkeypatch.setattr(worker, "OutboxListener", _Listener)
        monkeypatch.setattr(worker, "load_chain_rules", lambda: [])
        monkeypatch.setattr(worker, "warmup_worker", lambda *a, **k: None)
        monkeypatch.setattr(worker, "sweep_undelivered_broadcasts", _noop_coroutine)
        monkeypatch.setattr(worker.internal_event_client, "startup_lines",
                            lambda *a, **k: [])
        monkeypatch.setattr(worker.heartbeat, "beat", lambda *a, **k: None)

        def factory():
            if not sessions:
                sessions.append(_Session(rows, enough_waits, patience))
            return sessions[0]

        async def go():
            try:
                await asyncio.wait_for(
                    worker.start_chain_ingestion_worker(factory), 30.0)
            except (_StopWhenAnswered, asyncio.TimeoutError):
                pass

        asyncio.run(go())
        return _Listener.waits
    return _run


def test_a_tick_that_fetched_rows_and_did_nothing_still_yields(loop_over):
    """🔴 THE GATE OF THIS ROUND, AND IT IS THE SHAPE RATHER THAN THE CAUSE. The fetch
    returns a row the loop cannot use; before this, `pending_events` being non-empty sent
    the tick straight round again with no `await` and the process starved. The run ends as
    soon as three yields happen; four hundred queries without one is the freeze the owner
    saw."""
    assert loop_over([_Control()]) >= 3, "400 queries and no yield - the hot spin"


def test_an_empty_queue_yields_as_it_always_did(loop_over):
    """⚠️ THE PATH THAT WAS ALREADY RIGHT, so a repair that MOVED the yield rather than
    adding one would show up here rather than in production."""
    assert loop_over([]) >= 3
