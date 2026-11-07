# -*- coding: utf-8 -*-
"""A retroactive run held up by another backend says so in its record's `waiting` - the line under its row in the
admin queue (소유자 ㄱ, 총괄 11-08): «waiting <lock> on pid <p> (<the work on it>) · <s>»; `phase` keeps the stage alone.

  named    the holder's pid is the db_pid of an open work claim (a chain slot's) - it names that work and its rule
  plain    a holder no claim names - its application
  queue    the queue's running item carries it; nothing held up - null; the run's end empties it
"""
import re
import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from admin import retroactive
from conftest import PG_TEST_SCHEMA
from support import hold_world as hw
from support.isolated_pg import scratch_connect_args

pytestmark = pytest.mark.pg
RUN = "waits-run"
ROWS = 30


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    for w in hw.build(pg_engine, monkeypatch, tmp_path, batch=True):
        hw.push(w, [{"log_id": "L%03d" % i, "dt_job": "J%d" % (i % 3), "dt_x": i, "dt_y": 1, "netdie": i}
                    for i in range(ROWS)])
        hw.settle(w)
        import database.database as database
        monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=pg_engine))
        monkeypatch.setattr(retroactive, "_ledger_setup", lambda params: w["setup"])
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM retroactive_runs WHERE run_id = :r"), {"r": RUN})
            conn.execute(text("INSERT INTO retroactive_runs (run_id, op, state) VALUES (:r, 'ledger_rescope', 'queued')"),
                         {"r": RUN})
        try:
            yield w
        finally:
            with pg_engine.begin() as conn:
                conn.execute(text("DELETE FROM retroactive_runs WHERE run_id = :r"), {"r": RUN})


def _record(engine):
    """-> (phase, waiting) on the run's record."""
    with engine.connect() as conn:
        return tuple(conn.execute(text("SELECT phase, waiting FROM retroactive_runs WHERE run_id = :r"),
                                  {"r": RUN}).one())


def _run_held(world, monkeypatch, pg_engine, claim=None):
    """The run through its own door (`retroactive.execute`, the Re-translate button's op) with its source locked by
    another connection for 3 s -> (every (phase, waiting) told, the holder's pid). `claim`: (beat name, what, rule) - an open work
    claim whose db_pid is the holder's, its beat file written."""
    import psycopg2

    from utils import heartbeat

    monkeypatch.setattr(retroactive, "BEAT_SECONDS", 0.5)
    monkeypatch.setattr(retroactive, "LOOK_SECONDS", 0.2)
    monkeypatch.setattr(retroactive, "translate_slices", lambda: (1, 1))   # one process - the beat's
    import ingestion.settings
    monkeypatch.setattr(ingestion.settings, "read_ingestion_settings", lambda path=None: {"retroactive_debug": True})
    told = []
    real_tell = retroactive.RunControl.tell

    def tell(self):
        real_tell(self)
        if self.run_id == RUN:
            told.append(_record(pg_engine))
    monkeypatch.setattr(retroactive.RunControl, "tell", tell)
    dsn = pg_engine.url.render_as_string(hide_password=False).replace("postgresql+psycopg2", "postgresql")
    holder = psycopg2.connect(dsn, application_name="c_lock_holder", **scratch_connect_args(PG_TEST_SCHEMA))
    claimed = None
    try:
        with holder.cursor() as cur:
            cur.execute("SELECT current_schema(), pg_backend_pid()")
            schema, pid = cur.fetchone()
            assert schema == PG_TEST_SCHEMA
            cur.execute("LOCK TABLE hc_official IN ACCESS EXCLUSIVE MODE")     # the source every page reads
        if claim is not None:
            # the claim on a thread of its own, as a slot's is in a process of its own - the run's notes on this
            # thread never reach it
            name, what, rule = claim
            planted, done = threading.Event(), threading.Event()

            def hold_claim():
                with heartbeat.work_claim(name, what, acted_on=True):
                    heartbeat.note_work(db_pid=pid, rule_run={"rule": rule, "started": time.time()})
                    heartbeat.beat(name, force=True)
                    planted.set()
                    done.wait(30)
            claimed = threading.Thread(target=hold_claim, daemon=True)
            claimed.start()
            assert planted.wait(10), "CANARY: the claim was planted"
        release = threading.Timer(3.0, holder.rollback)
        release.start()
        started = time.monotonic()
        out = retroactive.execute({"op": "ledger_rescope", "run_id": RUN,
                                   "params": {"source": hw.SOURCE, "whole_source": True}}, log=lambda line: None)
        release.join()
        assert out["status"] == "ok", out
        assert time.monotonic() - started >= 2.5, "CANARY: the run did wait on the lock"
    finally:
        if claimed is not None:
            done.set()
            claimed.join(10)
        holder.close()
    return told, pid


def test_a_run_held_by_a_chain_slot_names_it_in_its_waiting(world, monkeypatch, pg_engine):
    told, pid = _run_held(world, monkeypatch, pg_engine,
                          claim=("chain-slot-9", "tx T1 · 30 row(s) of zz_pfab", "pf_note_back"))
    waits = [waiting for _phase_told, waiting in told if waiting]
    assert waits, told
    assert re.match(r"waiting Lock:relation on pid %d \(chain-slot-9 · tx T1 · 30 row\(s\) of zz_pfab, rule "
                    r"pf_note_back, [a-z ]+ \d+ s\): \S" % pid, waits[0]), waits[0]
    assert all("waiting" not in (phase or "") for phase, _waiting in told), "the stage alone in phase"
    assert _record(pg_engine)[1] is None, "the run ended - its waiting emptied"


def test_a_holder_no_claim_names_is_named_by_its_application(world, monkeypatch, pg_engine):
    told, pid = _run_held(world, monkeypatch, pg_engine)
    waits = [waiting for _phase_told, waiting in told if waiting]
    assert waits and waits[0].startswith("waiting Lock:relation on pid %d (c_lock_holder, " % pid), told


def test_the_queue_s_running_item_carries_the_wait_and_none_without_one(world, pg_engine):
    from datetime import datetime, timezone

    from runtime import running

    with pg_engine.begin() as conn:
        conn.execute(text("UPDATE retroactive_runs SET state = 'running', started_at = now(), runner = 'x' "
                          "WHERE run_id = :r"), {"r": RUN})
    control = retroactive.RunControl(RUN, op="ledger_rescope", log=lambda line: None)
    control.announcing = False
    control.stages.append(("write", time.monotonic(), None))
    control.tell()
    assert _record(pg_engine) == ("Page 1: write", None), "nothing held up - no waiting"
    db = sessionmaker(bind=pg_engine)()
    try:
        assert [item["waiting"] for item in running._retroactive(db, datetime.now(timezone.utc))] == [None]
        control.waiting = "waiting Lock:relation on pid 7 (chain-slot-1 · tx A) · 4 s"
        control.tell()
        assert _record(pg_engine) == ("Page 1: write", control.waiting)
        items = running._retroactive(db, datetime.now(timezone.utc))
        assert [item["waiting"] for item in items] == ["waiting Lock:relation on pid 7 (chain-slot-1 · tx A) · 4 s"]
    finally:
        db.close()
    control.stop_telling()
    assert _record(pg_engine) == ("Page 1: write", None), "the run's end empties its waiting"


def test_work_on_names_the_claim_whose_pid_it_is():
    import db_waits

    now = time.time()
    beats = {"chain-slot-1": {"stale": False, "work": {"what": "tx A · 5 row(s) of t", "facts": {
                 "db_pid": 11, "rule_run": {"rule": "r1", "started": now}}}},
             "chain-slot-2": {"stale": False, "work": {"what": "tx B", "facts": {"lock_db_pid": 12}}},
             "watcher": {"stale": True, "work": {"what": "file f", "facts": {"db_pid": 13}}}}
    assert db_waits.work_on(11, beats) == "chain-slot-1 · tx A · 5 row(s) of t, rule r1"
    assert db_waits.work_on(12, beats) == "chain-slot-2 · tx B", "a lock connection's pid names its claim too"
    assert db_waits.work_on(13, beats) is None, "a stale beat names nothing"
    assert db_waits.work_on(99, beats) is None
