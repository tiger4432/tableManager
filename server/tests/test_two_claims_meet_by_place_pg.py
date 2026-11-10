# -*- coding: utf-8 -*-
"""Two claims at once on PostgreSQL meet only where they both write (lead 11-10 ㄱ).

`retroactive.claim` checks the gate and writes the running row under one advisory lock. Two claimers on two
connections, released together, with the check slowed so both sit inside it if the lock did not hold them apart:

    same place    exactly one runs, the other is refused with the place they share
    apart         both run
"""
import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from admin import retroactive

pytestmark = pytest.mark.pg
PLACES = {"ledger_backfill": {"ledger:w1"}, "ledger_rescope": {"ledger:w1"}, "chain_replay": {"table:t1"}}


@pytest.fixture(name="claims")
def fixture_claims(pg_engine, monkeypatch):
    import database.database as database

    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=pg_engine))
    monkeypatch.setattr(retroactive, "writes", lambda op, params: PLACES.get(op, {"table:other_tests"}))
    real = retroactive.gate_refusal

    def slow(db, op=None, params=None):
        said = real(db, op, params)
        time.sleep(0.5)                 # both claimers inside the check, if the lock let them be
        return said
    monkeypatch.setattr(retroactive, "gate_refusal", slow)
    # the scratch schema lives for the whole run - runs other tests left in flight are set aside, then put back
    with pg_engine.begin() as conn:
        conn.execute(text("UPDATE retroactive_runs SET state = 'aside_' || state WHERE state IN "
                          "('running', 'cancel_requested')"))
        assert retroactive.in_flight_runs(sessionmaker(bind=conn)()) == [], "CANARY: nothing in flight"
    made = []
    try:
        yield made
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM retroactive_runs WHERE run_id = ANY(:ids)"), {"ids": made})
            conn.execute(text("UPDATE retroactive_runs SET state = substr(state, 7) WHERE state LIKE 'aside_%'"))


def _at_once(ops, made):
    """-> [(op, run_id or the refusal)] of claims released together, one connection each."""
    gate, got = threading.Barrier(len(ops)), {}

    def one(i, op):
        gate.wait()
        try:
            run_id = retroactive.claim(op=op, params={})
            made.append(run_id)
            got[i] = (op, run_id)
        except retroactive.RetroactiveRefused as refused:
            got[i] = (op, refused)
    threads = [threading.Thread(target=one, args=(i, op)) for i, op in enumerate(ops)]
    for each in threads:
        each.start()
    for each in threads:
        each.join(30)
    assert len(got) == len(ops), "CANARY: every claimer answered"
    return [got[i] for i in range(len(ops))]


def test_two_claims_on_the_same_place_take_turns(claims):
    got = _at_once(["ledger_backfill", "ledger_rescope"], claims)
    ran = [run for _op, run in got if isinstance(run, str)]
    refused = [str(run) for _op, run in got if isinstance(run, retroactive.RetroactiveRefused)]
    assert len(ran) == 1 and len(refused) == 1, got
    assert ("run_id=%s" % ran[0]) in refused[0] and "both write ledger:w1" in refused[0]


def test_two_claims_writing_apart_both_run(claims):
    got = _at_once(["ledger_backfill", "chain_replay"], claims)
    assert all(isinstance(run, str) for _op, run in got), got
