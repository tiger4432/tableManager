# -*- coding: utf-8 -*-
"""One poisoned on-demand request stopped every on-demand request after it, in silence.

The `SCHEDULER_RUN_NOW` watcher selected `order_by(id.asc()).first()` among unprocessed
rows and, when handling threw, logged and stopped: no rollback, no `status`, and
`processed_chain` left False. So the same row was picked again on every tick FOREVER and
every request queued behind it never ran -- nothing raised, nothing on screen, and a
restart did not clear it because the fault is in the row rather than in the process.

🔴 THE REPAIR ALREADY EXISTED, ON THE OTHER WATCHER. The `RETROACTIVE_RUN` handler in the
same file carries it, and its comment gives the reason: "a request that threw is finished,
not pending, and leaving it unmarked stopped production". The fix had landed on one of the
two, so this is a CLASS repair with the sibling as the template, not a new idea.

⚠️ AND THE CLASS SPLITS. Four handlers select an unprocessed outbox row; only two have this
shape. The two `SYSTEM_RELOAD` watchers select `id.desc()` behind an in-memory high-water
mark, so a failure there does not re-pick and does not block a FIFO head -- it fails the
other way, quietly running on stale rules. Repairing all four alike would have "fixed" two
handlers that do not have this defect.
"""
import json
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                           # noqa: E402
from database import models                                      # noqa: E402


def trigger_row(db, *, table_name="dt_map", script_name="boom.py", payload=None):
    row = models.DatabaseOutbox(
        event_uuid=str(uuid.uuid4()), table_name=table_name,
        event_type=event_constants.EVENT_SCHEDULER_RUN_NOW,
        payload=payload if payload is not None else json.dumps(
            {"table_name": table_name, "script_name": script_name}),
        processed_chain=False)
    db.add(row)
    db.flush()
    return row


def watcher(db_session, *, explode):
    """The scheduler's watcher, with its one side effect replaced."""
    import run_auto_update

    scheduler = run_auto_update.MultiDiscoveryScheduler.__new__(
        run_auto_update.MultiDiscoveryScheduler)
    calls = []

    def on_demand(table_name, script_name):
        calls.append((table_name, script_name))
        if explode(table_name, script_name):
            raise RuntimeError("the collector for %s blew up" % script_name)

    scheduler.run_collector_on_demand = on_demand
    return scheduler, calls


def take_one(scheduler, db):
    """One tick of the SCHEDULER_RUN_NOW half.

    ⚠️ THIS MIRRORS THE HANDLER, IT DOES NOT DRIVE IT. The real one lives inside a
    200-line loop that builds its own session, sleeps, and rediscovers collectors, so it
    cannot be called for one row. So the file is scored twice and the two halves answer
    different questions: the SOURCE assertions above check that the real site carries the
    repair, and these check that the repair's SHAPE actually unblocks a queue. Neither is
    sufficient alone -- a mirror that drifts would pass while the site regressed, which is
    why the source assertions are not decoration.

    ⚠️ AND THE ROLLBACK IS A SAVEPOINT HERE, for the fixture rather than for the design:
    `db_session` wraps the test in one transaction, so a bare `db.rollback()` would discard
    the rows the test just wrote instead of only the failed unit. A savepoint gives the
    production semantics -- the failed work is undone, the mark that follows it is not.
    """
    latest = (db.query(models.DatabaseOutbox)
              .filter(models.DatabaseOutbox.event_type
                      == event_constants.EVENT_SCHEDULER_RUN_NOW,
                      models.DatabaseOutbox.processed_chain == False)  # noqa: E712
              .order_by(models.DatabaseOutbox.id.asc()).first())
    if latest is None:
        return None
    payload_data = None
    savepoint = db.begin_nested()
    try:
        payload_data = (json.loads(latest.payload) if isinstance(latest.payload, str)
                        else latest.payload)
        scheduler.run_collector_on_demand(payload_data.get("table_name"),
                                          payload_data.get("script_name"))
        latest.processed_chain = True
        savepoint.commit()
        db.flush()
    except Exception:
        savepoint.rollback()
        latest.status = "FAILED"
        latest.processed_chain = True
        db.flush()
    return latest


# ------------------------------------------------------------------ the shape is in place

def test_the_handler_marks_a_thrown_request_finished():
    """🔴 THE SOURCE ASSERTION. The behaviour lives inside a long loop method, so this
    scores the repair where it was made -- and it is the sibling's exact shape."""
    import inspect

    import run_auto_update

    body = inspect.getsource(run_auto_update.MultiDiscoveryScheduler.run)
    head = body.split("SCHEDULER_RUN_NOW trigger", 1)[1][:900]
    assert 'status = "FAILED"' in head, "a thrown request is left pending again"
    assert "processed_chain = True" in head
    assert "db.rollback()" in head, "the failed transaction is not rolled back"


def test_the_failure_names_the_row_and_the_request_but_not_the_payload():
    """⚠️ The reason must survive, and the payload body must not: it is operational data,
    and a big one is how a recovery path becomes the next incident."""
    import inspect

    import run_auto_update

    body = inspect.getsource(run_auto_update.MultiDiscoveryScheduler.run)
    head = body.split("SCHEDULER_RUN_NOW trigger", 1)[1][:900]
    for named in ("outbox#%s", "table=%s", "script=%s"):
        assert named in head, "the failure stopped naming %s" % named
    assert "latest_trigger.payload" not in head


def test_it_says_so_when_even_the_marking_fails():
    """If the mark cannot be written the block remains -- and that has to be a sentence,
    not a silence, or the queue is stuck with nothing said."""
    import inspect

    import run_auto_update

    body = inspect.getsource(run_auto_update.MultiDiscoveryScheduler.run)
    assert "the queue is still blocked" in body


def test_retry_count_is_not_raised():
    """⛔ A request that could not be parsed or run will not parse or run next time.
    Raising it would put this row into a retry budget it can never spend."""
    import inspect

    import run_auto_update

    body = inspect.getsource(run_auto_update.MultiDiscoveryScheduler.run)
    head = body.split("SCHEDULER_RUN_NOW trigger", 1)[1][:900]
    assert "retry_count" not in head


# ------------------------------------------------------- the behaviour, on rows

def test_a_thrown_row_is_not_picked_up_again(db_session):
    """🔴 GATE ①. The same row on the next tick, and the one after, is the whole defect."""
    scheduler, calls = watcher(db_session, explode=lambda t, s: True)
    row = trigger_row(db_session, script_name="boom.py")

    first = take_one(scheduler, db_session)
    assert first is not None and first.id == row.id
    assert take_one(scheduler, db_session) is None, "the poisoned row was picked up again"
    assert take_one(scheduler, db_session) is None
    assert len(calls) == 1, "the collector ran more than once for one failed request"


def test_a_good_request_behind_it_gets_through(db_session):
    """🔴 GATE ②. This is what "the queue is blocked" means, as an assertion."""
    scheduler, calls = watcher(db_session,
                               explode=lambda t, s: s == "boom.py")
    trigger_row(db_session, script_name="boom.py")
    good = trigger_row(db_session, script_name="fine.py")

    take_one(scheduler, db_session)                      # the poisoned one
    second = take_one(scheduler, db_session)
    assert second is not None and second.id == good.id
    assert ("dt_map", "fine.py") in calls


def test_the_failure_is_recorded_on_the_row(db_session):
    """🔴 GATE ③. Swallowed silently is not repaired; the row has to say it failed."""
    scheduler, _ = watcher(db_session, explode=lambda t, s: True)
    row = trigger_row(db_session)
    take_one(scheduler, db_session)
    db_session.refresh(row)
    assert row.status == "FAILED"
    assert row.processed_chain is True


def test_an_unparseable_payload_is_finished_too(db_session):
    """The parse itself can throw, which is why the payload name is bound before the try --
    an unbound name in the failure branch would replace the reason with a NameError."""
    scheduler, calls = watcher(db_session, explode=lambda t, s: False)
    row = trigger_row(db_session, payload="{ not json")
    take_one(scheduler, db_session)
    db_session.refresh(row)
    assert row.processed_chain is True and row.status == "FAILED"
    assert calls == [], "a request that would not parse still reached the collector"


def test_a_successful_request_is_not_marked_failed(db_session):
    """⚠️ THE OTHER HALF. A repair that marked everything FAILED would pass every
    assertion above and destroy the working path."""
    scheduler, calls = watcher(db_session, explode=lambda t, s: False)
    row = trigger_row(db_session, script_name="fine.py")
    take_one(scheduler, db_session)
    db_session.refresh(row)
    assert row.processed_chain is True
    assert row.status != "FAILED"
    assert calls == [("dt_map", "fine.py")]


# ------------------------------------------------- ⚠️ the class, and where it does NOT apply

def test_the_reload_watchers_are_a_different_shape_and_are_left_alone():
    """⛔ THE COUNT THAT KEPT THIS FROM BEING FOUR EDITS. Both `SYSTEM_RELOAD` watchers
    select `id.desc()` behind an in-memory high-water mark, so a failure neither re-picks
    the row nor blocks a FIFO head. Marking them FAILED would be repairing a defect they
    do not have."""
    import inspect

    import chain_ingestion_worker
    import run_auto_update

    for source in (inspect.getsource(run_auto_update.MultiDiscoveryScheduler.run),
                   inspect.getsource(chain_ingestion_worker.start_chain_ingestion_worker)):
        head = source.split('"SYSTEM_RELOAD"', 1)[1][:400]
        assert "id.desc()" in head, "a reload watcher started reading oldest-first"
