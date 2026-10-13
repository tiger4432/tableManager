# -*- coding: utf-8 -*-
"""총괄 fa5417c28 (a short QA of 19d6da585, the ledger's own process) - where the chain ends a deletion's event, what its
row fed is withdrawn: a group's commit (its deleted rows read before it, so no event is loaded again), an operator's
set-aside and a refusal past the depth limit (a row deleted is a fact whether or not a rule runs on it). A failed
withdrawal leaves the session usable. A chain loop with no ledger beating says so; the isolated stack runs the
launcher's own chain and ledger children.
"""
import asyncio
import importlib.util
import logging
import os
import sys

import pytest
from sqlalchemy import event as sa_event, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                              # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from chain import set_aside                                         # noqa: E402
from database import models                                        # noqa: E402
from support import hold_world as hw                                # noqa: E402
from utils import heartbeat                                         # noqa: E402


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path)


def _fed_by_l1(world):
    """(the log row L1's id, the layers it fed)."""
    db = world["db"]
    row_id = db.execute(text('SELECT row_id FROM "%s" WHERE log_id = \'L1\'' % hw.LOG)).scalar()
    return row_id, db.execute(text("SELECT count(*) FROM cell_sources WHERE origin_row_id = :r"),
                              {"r": row_id}).scalar()


def _deletion_waiting(world):
    """L1 copied by the chain, then deleted - its DELETE event waiting. -> (row id, the event)."""
    hw.push(world, [{"log_id": "L1", **hw.KEY, "netdie": 5}])
    hw.run_chain(world)
    row_id, fed = _fed_by_l1(world)
    assert fed > 0, "CANARY: the copy fed the official row from L1"
    hw.delete(world, "L1")
    db = world["db"]
    waiting = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False),
                                                      models.DatabaseOutbox.event_type == "DELETE").all())
    assert len(waiting) == 1, waiting
    return row_id, waiting[0]


def _fed(world, row_id):
    return world["db"].execute(text("SELECT count(*) FROM cell_sources WHERE origin_row_id = :r"),
                               {"r": row_id}).scalar()


@pytest.mark.pg
def test_a_group_withdraws_its_deletions_and_loads_no_event_again_after_its_commit(world):
    row_id, deletion = _deletion_waiting(world)
    reloads = []

    def count(conn, cursor, statement, parameters, context, executemany):
        if "FROM database_outbox" in statement and "database_outbox.id = %(pk_1)s" in statement:
            reloads.append(statement)

    sa_event.listen(world["engine"], "before_cursor_execute", count)
    try:
        asyncio.run(worker.drain_events(world["db"], [deletion], world["rules"],
                                        sessionmaker(bind=world["engine"])))
    finally:
        sa_event.remove(world["engine"], "before_cursor_execute", count)
    assert _fed(world, row_id) == 0, "the group's commit took back what the deleted row fed"
    assert reloads == [], "an event was loaded again after the group's commit"


@pytest.mark.pg
def test_a_deletion_an_operator_sets_aside_still_takes_back_what_its_row_fed(world):
    row_id, deletion = _deletion_waiting(world)
    done = set_aside.set_aside(world["db"], ids=[deletion.id], apply=True)
    assert done["marked"] == 1, done
    assert _fed(world, row_id) == 0


@pytest.mark.pg
def test_a_deletion_past_the_depth_limit_still_takes_back_what_its_row_fed(world):
    row_id, deletion = _deletion_waiting(world)
    db = world["db"]
    deletion.payload = dict(deletion.payload, **{event_constants.CHAIN_DEPTH_KEY: 999})
    db.commit()
    assert asyncio.run(worker.drain_events(db, [deletion], world["rules"], sessionmaker(bind=world["engine"]))) is None
    db.refresh(deletion)
    assert deletion.status == "FAILED", "CANARY: refused past the limit"
    assert _fed(world, row_id) == 0


@pytest.mark.pg
def test_a_failed_withdrawal_leaves_the_session_usable(world, monkeypatch):
    db = world["db"]
    monkeypatch.setattr(worker, "_withdraw_and_tell", lambda db, *a, **k: db.execute(text("SELECT 1 / 0")))
    worker._retract_what_those_rows_fed(db, hw.LOG, ["gone"])
    assert db.execute(text("SELECT 1")).scalar() == 1


def test_a_chain_loop_says_when_no_ledger_beats(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="Chain")
    for beats, says in (({}, "no beat"), ({"ledger": {"stale": True, "age_seconds": 130.0}}, "last beat 130 s ago"),
                        ({"ledger": {"stale": False, "age_seconds": 3.0}}, None)):
        caplog.clear()
        monkeypatch.setattr(heartbeat, "read_all", lambda beats=beats, **_: beats)
        asyncio.run(worker._say_if_no_ledger_beats(after=0))
        said = [r.getMessage() for r in caplog.records if "no ledger process beats" in r.getMessage()]
        assert said == ([] if says is None else [said[0]]) and (says is None or "(%s)" % says in said[0]), (beats, said)


def test_the_isolated_stack_runs_the_launchers_chain_and_ledger_children():
    path = os.path.join(os.path.dirname(__file__), "..", "scripts", "dev_env", "devenv.py")
    spec = importlib.util.spec_from_file_location("_devenv_under_test", path)
    devenv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(devenv)
    workers = devenv._workers()
    assert [name for name, _cmd in workers] == ["chain", "ledger"]
    assert [os.path.basename(cmd[-1]) for _name, cmd in workers] == ["run_chain_worker.py", "run_ledger_worker.py"]
