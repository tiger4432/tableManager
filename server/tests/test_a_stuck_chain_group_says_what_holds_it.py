"""A chain group that stops moving says what holds it (총괄 fc1c0781d · 61830c1af · 948ee98b5).

Production showed `chain = wedged` while its log kept moving: the beat came only from the
loop head, a group that ran long read `wedged` whether it moved or not, and nothing said
what the stuck backend was doing. The cells force each shape on a real PostgreSQL:

  held by a lock      -> stalled · the line names the holder's pid, name and state
  its own slow query  -> stalled · the line says its own query is active, no lock
  a long MOVING group -> neither stalled nor wedged
  the sampler and diagnose_db_health say it through the same function
  a gone chain worker's query is ended at the next start; another name is not
"""
import asyncio
import os
import subprocess
import sys
import threading
import time
import types

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

import db_waits
from chain import ingestion_worker as iw
from maps import alignment_batch_counts
from runtime.health import compute_health
from utils import heartbeat
from utils import logger as process_logging

#: The beat file is written at most once a second (`MIN_WRITE_INTERVAL_SEC`), so the
#: staleness window here has to clear that plus a slice.
SLICE, STALL, STALE = 0.2, 1.5, 2.0
DB_OK = {"status": "ok", "latency_ms": 1.0}
OUTBOX_OK = {"pending": 0, "pending_capped": False, "oldest_age_seconds": None}
SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _probe_events_are_still_waiting(monkeypatch):
    """The probe's events are not outbox rows: each is still waiting - the worker asks before a
    group runs and before its ending is written (소유자 10-08)."""
    monkeypatch.setattr(iw, "_still_waiting", lambda db, events: (list(events), set()))


@pytest.fixture()
def fast(monkeypatch, tmp_path):
    """Seconds instead of minutes - the same code, shorter numbers."""
    monkeypatch.setattr(heartbeat, "HEARTBEAT_SLICE_SECONDS", SLICE)
    monkeypatch.setattr(heartbeat, "DEFAULT_STALL_AFTER_SEC", STALL)
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path))
    monkeypatch.setattr(heartbeat, "heartbeat_path",
                        lambda name: os.path.join(str(tmp_path), name + ".json"))


def _named(monkeypatch, process):
    """Connections opened from now on are this process's (`connection_name`)."""
    monkeypatch.setattr(process_logging, "active_process_name", lambda: process)


def _health():
    sup = {"supervisor_pid": 42, "updated_at": time.time(), "failed_children": [],
           "events": [], "children": {"Chain": {
               "state": "running", "heartbeat": "chain", "pid": os.getpid(), "restarts": 0,
               "uptime_seconds": 3600.0, "last_exit_code": None, "failure_reason": None}}}
    payload, _code = compute_health(DB_OK, heartbeat.read_all(stale_after=STALE,
                                                              stall_after=STALL),
                                    sup, OUTBOX_OK, STALE, backup_result=None)
    return payload["checks"]["workers"]["chain"]["status"], " | ".join(payload["problems"])


def _run_group_in_background(db, body, monkeypatch):
    """`process_pending_groups` - the production caller - over one group whose body is
    `body`, on a thread of its own so the test can look while it runs."""
    monkeypatch.setattr(iw, "_process_chain_transaction_group_sync", body)
    event = types.SimpleNamespace(id=1, table_name="stall_probe", payload={},
                                  event_uuid="e1", event_type="UPDATE")
    out = {}

    def run():
        try:
            out["failed_any"] = asyncio.run(iw.process_pending_groups(
                db, ["tx1"], {"tx1": [event]}, [], None))
        except BaseException as exc:                              # noqa: BLE001
            out["error"] = exc
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, out


def _wait_for(predicate, seconds=20.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    return None


def _published_stall():
    work = (heartbeat.read_all(stale_after=STALE, stall_after=STALL).get("chain") or {}).get(
        "work") or {}
    return work.get("stalled_on")


@pytest.fixture()
def probe_table(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS stall_probe (k int PRIMARY KEY, v text)"))
        conn.execute(text("INSERT INTO stall_probe VALUES (1, 'seed') ON CONFLICT DO NOTHING"))
    yield pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS stall_probe"))


def _backend_pid(connection):
    return connection.connection.dbapi_connection.get_backend_pid()


@pytest.mark.pg
def test_a_group_held_by_a_lock_is_stalled_and_names_who_holds_it(
        probe_table, fast, monkeypatch, caplog):
    _named(monkeypatch, "Watcher")
    holder = probe_table.connect()
    holder.execute(text("UPDATE stall_probe SET v = 'held' WHERE k = 1"))
    holder_pid = _backend_pid(holder)

    _named(monkeypatch, "Chain")
    db = sessionmaker(bind=probe_table)()
    db.execute(text("SELECT 1"))          # the batch's transaction begins on the loop thread
    group_pid = _backend_pid(db.connection())

    def body(tx_id, events, session, rules):
        with alignment_batch_counts.stage("write:stall_probe"):
            session.execute(text("UPDATE stall_probe SET v = 'chain' WHERE k = 1"))
        return True, None, []

    thread, out = _run_group_in_background(db, body, monkeypatch)
    try:
        said = _wait_for(_published_stall)
        assert said, ("a group held past the stall window never said what holds it",
                      out, heartbeat.open_claims())
        status, problems = _health()
    finally:
        holder.rollback()
        holder.close()
    thread.join(20)
    try:
        assert status == "stalled", (status, problems)
        for part in ("in write:stall_probe", "db pid %d" % group_pid, "waiting Lock:",
                     "on pid %d" % holder_pid, "assy_watcher", "idle in transaction",
                     "UPDATE stall_probe"):
            assert part in said, (part, said)
        assert said in problems, "health and the log must carry the same sentence"
        lines = [r.getMessage() for r in caplog.records if " stalled " in r.getMessage()]
        assert len(lines) == 1 and said in lines[0], lines   # once per episode
        assert out == {"failed_any": False}, out
        assert not [c for c in heartbeat.open_claims() if c["name"] == "chain"]
        assert _health()[0] == "ok"
    finally:
        db.rollback()
        db.close()


@pytest.mark.pg
def test_a_group_in_its_own_slow_query_says_so_with_no_lock(
        probe_table, fast, monkeypatch):
    _named(monkeypatch, "Chain")
    db = sessionmaker(bind=probe_table)()

    def body(tx_id, events, session, rules):
        with alignment_batch_counts.stage("mapper"):
            session.execute(text("SELECT pg_sleep(4)"))
        return True, None, []

    thread, out = _run_group_in_background(db, body, monkeypatch)
    said = _wait_for(_published_stall)
    status, _problems = _health()
    thread.join(20)
    db.close()
    assert status == "stalled"
    assert said and "in mapper" in said and "its own query active" in said, said
    assert "(no lock, Timeout:PgSleep)" in said and "pg_sleep(4)" in said, said
    assert out == {"failed_any": False}, out


def test_a_long_group_whose_stages_move_is_neither_stalled_nor_wedged(fast, monkeypatch):
    db = types.SimpleNamespace(get_bind=lambda: types.SimpleNamespace(url=None),
                               commit=lambda: None, rollback=lambda: None,
                               in_transaction=lambda: False)

    def body(tx_id, events, session, rules):
        for step in range(10):                    # 3 s in all - twice the stall window
            with alignment_batch_counts.stage("write:t%d" % step):
                time.sleep(0.3)
        return True, None, []

    thread, out = _run_group_in_background(db, body, monkeypatch)
    seen = set()
    _wait_for(lambda: [c for c in heartbeat.open_claims() if c["name"] == "chain"], 5)
    while thread.is_alive():
        seen.add(_health()[0])
        time.sleep(0.1)
    thread.join(5)
    assert seen == {"ok"}, seen
    assert out == {"failed_any": False}, out


def test_a_changed_backend_pid_is_on_disk_before_the_next_beat(fast):
    """A pause and a set-aside cancel by the pid the beat FILE names, from another process - a
    commit inside a group hands its session another pooled connection (총괄 10-08)."""
    def on_disk():
        return ((heartbeat.read_all().get("chain") or {}).get("work") or {}).get("facts", {}).get("db_pid")

    with heartbeat.work_claim("chain", "tx probe", acted_on=True):
        heartbeat.note_work(db_pid=101)
        assert on_disk() == 101
        heartbeat.note_work(db_pid=202)                # well inside the beat's write interval
        assert on_disk() == 202
    # a claim nobody acts on from outside (a file's ingestion) keeps the one-write-a-second bound
    with heartbeat.work_claim("chain", "tx probe"):
        heartbeat.note_work(db_pid=303)
        assert on_disk() is None


def test_a_stall_check_that_raises_goes_quiet_and_the_group_finishes(fast, monkeypatch,
                                                                     caplog):
    db = types.SimpleNamespace(commit=lambda: None, rollback=lambda: None,
                               in_transaction=lambda: False)

    async def breaks(session):
        raise RuntimeError("probe broke")
    monkeypatch.setattr(iw, "_say_what_a_stalled_group_waits_on", breaks)

    def body(tx_id, events, session, rules):
        time.sleep(3 * SLICE)
        return True, None, []

    thread, out = _run_group_in_background(db, body, monkeypatch)
    thread.join(10)
    assert out == {"failed_any": False}, out
    assert any("stall check went quiet" in r.getMessage() and "probe broke" in r.getMessage()
               for r in caplog.records)


CANNED = {"pid": 7, "app": "assy_chain", "state": "active", "wait_type": "Lock",
          "wait": "Lock:transactionid", "xact_age": 40.0, "query_age": 39.0,
          "state_age": 39.0, "query": "UPDATE t SET v = 1",
          "blocker": {"pid": 9, "app": "assy_watcher", "state": "idle in transaction",
                      "xact_age": 720.0, "state_age": 700.0, "query": "UPDATE t SET v = 2"}}


def test_the_sentence_has_one_shape_per_thing_a_backend_can_be_doing():
    assert db_waits.wait_sentence(CANNED) == (
        "waiting Lock:transactionid on pid 9 (assy_watcher, idle in transaction 12 min): "
        "UPDATE t SET v = 2")
    active = dict(CANNED, blocker=None, wait=None, wait_type=None, query_age=305.0)
    assert db_waits.wait_sentence(active) == (
        "its own query active 305 s (no lock): UPDATE t SET v = 1")
    idle = dict(active, state="idle in transaction", state_age=42.0)
    assert db_waits.wait_sentence(idle) == (
        "idle in transaction 42 s - the time is not in the database "
        "(last query: UPDATE t SET v = 1)")
    assert db_waits.wait_sentence(None, 5) == (
        "pid 5 is not in pg_stat_activity - its connection is gone")


def _dsn(engine):
    return engine.url.set(drivername="postgresql").render_as_string(hide_password=False)


@pytest.mark.pg
def test_the_chunk_sampler_says_it_through_the_one_function(pg_engine, monkeypatch):
    from parsers.directory_watcher import ChunkWaitSampler
    monkeypatch.setattr(db_waits, "backend_waits", lambda conn, pid=None: [CANNED])
    sampler = ChunkWaitSampler(_dsn(pg_engine), 7).start()
    _wait_for(lambda: sampler.counts, 5)
    summary = sampler.stop().summary()
    assert db_waits.wait_sentence(CANNED) in summary, summary
    assert "Lock:transactionid" in summary, summary


def _blocked_pair(engine, monkeypatch):
    """A holder named by the listener (assy_watcher) and a waiter (assy_chain) queued
    behind it on the same row."""
    _named(monkeypatch, "Watcher")
    holder = engine.connect()
    holder.execute(text("UPDATE stall_probe SET v = 'held' WHERE k = 1"))
    _named(monkeypatch, "Chain")
    waiter = engine.connect()
    waiter_pid = _backend_pid(waiter)
    thread = threading.Thread(target=lambda: waiter.execute(
        text("UPDATE stall_probe SET v = 'waiting' WHERE k = 1")), daemon=True)
    thread.start()

    def queued():
        with engine.connect() as look:
            rows = db_waits.backend_waits(look.connection.dbapi_connection, waiter_pid)
        return rows and rows[0]["blocker"]
    assert _wait_for(queued, 10), "the waiter never queued behind the holder"
    return holder, waiter, thread


@pytest.mark.pg
def test_diagnose_db_health_names_the_holder(probe_table, monkeypatch):
    holder, waiter, thread = _blocked_pair(probe_table, monkeypatch)
    try:
        done = subprocess.run(
            [sys.executable, os.path.join(SERVER_DIR, "scripts", "diagnose_db_health.py")],
            cwd=SERVER_DIR, capture_output=True, timeout=300,
            env=dict(os.environ, DATABASE_URL=_dsn(probe_table),
                     PYTHONIOENCODING="utf-8"))
    finally:
        holder.rollback()
        holder.close()
        thread.join(10)
        waiter.rollback()
        waiter.close()
    out = done.stdout.decode("utf-8", "replace")
    section = out.split("3. LOCK WAITS", 1)[-1].split("4. BLOAT", 1)[0]
    assert "(assy_chain) waiting Lock:" in section, out[-3000:]
    assert "assy_watcher, idle in transaction" in section, section


def _orphan(dsn, name):
    """A process that opens a connection called `name`, starts a long query, and is killed
    while it runs - what a restarted worker leaves behind."""
    code = ("import psycopg2, sys\n"
            "c = psycopg2.connect(sys.argv[1], application_name=sys.argv[2])\n"
            "print(c.get_backend_pid(), flush=True)\n"
            "c.cursor().execute('SELECT pg_sleep(60)')\n")
    proc = subprocess.Popen([sys.executable, "-c", code, dsn, name], stdout=subprocess.PIPE)
    pid = int(proc.stdout.readline())
    return proc, pid


def _running(engine, pid):
    with engine.connect() as look:
        return look.execute(text("SELECT state = 'active' AND query LIKE '%pg_sleep%'"
                                 " FROM pg_stat_activity WHERE pid = :p"), {"p": pid}).scalar()


def _alive(engine, pid):
    with engine.connect() as look:
        return bool(look.execute(text("SELECT count(*) FROM pg_stat_activity WHERE pid = :p"),
                                 {"p": pid}).scalar())


@pytest.mark.pg
def test_a_new_chain_worker_ends_what_a_gone_one_left_and_nothing_else(
        pg_engine, monkeypatch, caplog):
    dsn = _dsn(pg_engine)
    chain_proc, chain_left = _orphan(dsn, "assy_chain")
    retro_proc, retro_left = _orphan(dsn, "assy_retroactive")
    for proc, left in ((chain_proc, chain_left), (retro_proc, retro_left)):
        assert _wait_for(lambda: _running(pg_engine, left), 10), "never started"
        proc.kill()
        proc.wait(10)
    monkeypatch.setattr(iw, "_IMPORTED_AT", time.time())
    time.sleep(0.05)
    import psycopg2
    mine = psycopg2.connect(dsn, application_name="assy_chain")    # opened after the start
    try:
        _named(monkeypatch, "Chain")
        monkeypatch.setattr(iw, "another_chain_loop_is_running", lambda now=None: None)
        iw._end_queries_a_gone_chain_worker_left_sync(sessionmaker(bind=pg_engine))
        assert _wait_for(lambda: not _alive(pg_engine, chain_left), 10), \
            "the gone worker's query is still running"
        assert _alive(pg_engine, retro_left), "a connection under another name was ended"
        with mine.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,), "this process's own connection was ended"
        lines = [r.getMessage() for r in caplog.records if "left by a chain worker" in
                 r.getMessage()]
        # Other cells of this run may have left connections under the same name; the
        # line for THIS orphan is one, and nothing is said about the other two.
        ours = [line for line in lines if "pid %d," % chain_left in line]
        assert len(ours) == 1 and "ended" in ours[0] and "pg_sleep(60)" in ours[0], lines
        assert not [line for line in lines
                    if "pid %d," % retro_left in line
                    or "pid %d," % mine.get_backend_pid() in line], lines
    finally:
        mine.close()
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT pg_terminate_backend(:p)"), {"p": retro_left})


@pytest.mark.pg
def test_every_connection_carries_its_process_name_unless_it_named_itself(
        pg_engine, monkeypatch):
    import db_safety
    from database.database import connection_name
    _named(monkeypatch, "Watcher")
    with pg_engine.connect() as conn:
        name = conn.execute(text("SELECT application_name FROM pg_stat_activity"
                                 " WHERE pid = pg_backend_pid()")).scalar()
    assert name == connection_name() == "assy_watcher"
    readonly = db_safety.open_readonly_engine(pg_engine.url)
    try:
        with readonly.connect() as conn:
            kept = conn.execute(text("SELECT application_name FROM pg_stat_activity"
                                     " WHERE pid = pg_backend_pid()")).scalar()
    finally:
        readonly.dispose()
    assert kept == "assy_readonly_pass"
