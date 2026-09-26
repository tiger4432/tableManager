"""The emergency stop (소유자 「오늘 보면 이런 대형 사고에서 끌 방법이 없는 게 문제였으」, 총괄
3840af307 · 2dbbfd1e5): Pause stops the chain within seconds and loses nothing, and events can
be set aside by table, rule or transaction and run again later with the result they would have
had.

  pause, Python-bound group   rewound at its next stage boundary · not charged · Resume runs it
  pause, a running query      cancelled by the pause itself, not waited out (PostgreSQL)
  pause survives a restart     a fresh process reads it
  health                      `paused`, its own word, degraded - a bigger verdict still wins
  set aside                   only the scope - collapsed events too - and nothing deleted
  run again                   the rows those events named, cascading as the chain would have
"""
import asyncio
import os
import subprocess
import sys
import textwrap
import threading
import time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                                # noqa: E402
import mapper_sdk                                                     # noqa: E402
import paths                                                          # noqa: E402
from admin import retroactive                                         # noqa: E402
from chain import control as chain_control                            # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from chain import replay, set_aside                                   # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from database.context import channel, outbox_mode                     # noqa: E402
from database.database import Base                                    # noqa: E402
from maps import alignment_batch_counts                               # noqa: E402
from runtime.health import compute_health                             # noqa: E402
from utils import heartbeat                                           # noqa: E402
from utils import logger as process_logging                           # noqa: E402
from utils.payload_helper import get_payload_dict                     # noqa: E402

PA, PB = "es_a", "es_b"
TABLES = {name: {"business_key": "k", "composite_key_source": ["k"],
                 "column_types": {"k": "string", "n": "string"}, "display_columns": ["k", "n"]}
          for name in (PA, PB)}
BUMP = """
def bump(db, payload, rule=None):
    handed = payload if isinstance(payload, list) else [payload]
    out = []
    for p in handed:
        data = p.get("data") or {}
        k = (data.get("k") or {}).get("value")
        n = int((data.get("n") or {}).get("value") or 0)
        out.append({"business_key_val": k, "updates": {"k": k, "n": str(n + 1)}})
    return {"updates": out}
"""
DB_OK = {"status": "ok", "latency_ms": 1.0}
OUTBOX_OK = {"pending": 0, "pending_capped": False, "oldest_age_seconds": None}


class _NoClose:
    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


@pytest.fixture(autouse=True)
def control_in_tmp(tmp_path, monkeypatch):
    """The control file and the beats live in this test's own directory."""
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path / "beats"))
    monkeypatch.setattr(heartbeat, "heartbeat_path",
                        lambda name: str(tmp_path / "beats" / (name + ".json")))
    monkeypatch.setattr(heartbeat, "HEARTBEAT_SLICE_SECONDS", 0.2)
    yield tmp_path


def _tables(engine):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)


@pytest.fixture(name="db")
def fixture_db(tmp_path, monkeypatch):
    mapper_sdk.discover()
    (tmp_path / "es_bump.py").write_text(textwrap.dedent(BUMP), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("es_bump", None)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    _tables(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    monkeypatch.setattr("database.database.SessionLocal", lambda: _NoClose(session))
    monkeypatch.setattr(retroactive, "announce_progress", lambda *a, **k: None)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)
        sys.modules.pop("es_bump", None)


def _write(db, table, rows, collapsed=False):
    with channel(event_constants.CHANNEL_API), outbox_mode(
            event_constants.OUTBOX_MODE_COLLAPSED if collapsed
            else event_constants.OUTBOX_MODE_PER_ROW):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="es")
            for row in rows]))
        db.commit()


def _pending(db):
    return (db.query(models.DatabaseOutbox)
            .filter(models.DatabaseOutbox.processed_chain.is_(False))
            .order_by(models.DatabaseOutbox.id).all())


def _groups(events):
    groups = {}
    for event in events:
        groups.setdefault(get_payload_dict(event).get("transaction_id"), []).append(event)
    return list(groups), groups


def _run_pending_in_background(db, body, monkeypatch):
    """`process_pending_groups` over what is pending, on a thread of its own."""
    monkeypatch.setattr(worker, "_process_chain_transaction_group_sync", body)
    order, groups = _groups(_pending(db))
    out = {}

    def run():
        try:
            out["failed_any"] = asyncio.run(worker.process_pending_groups(
                db, order, groups, [], None))
        except BaseException as exc:                              # noqa: BLE001
            out["error"] = exc
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, out


def _bumpers():
    def rule(name, trigger, target, opt_in):
        return {"name": name, "enabled": True, "is_batch": True, "trigger_table": trigger,
                "target_table": target, "mapper_module": "es_bump",
                "mapper_function": "bump", "allow_chain_trigger": opt_in}
    # a -> b is woken by what a person writes; b -> a also by what the chain writes.
    return [rule("es_a_to_b", PA, PB, False), rule("es_b_to_a", PB, PA, True)]


def _drain(db, rules, rounds=30):
    for _ in range(rounds):
        pending = _pending(db)
        if not pending:
            return
        order, groups = _groups(pending)
        for tx_id in order:
            ok, error, _ = worker._process_chain_transaction_group_sync(
                tx_id, groups[tx_id], db, rules)
            assert ok, error
            for event in groups[tx_id]:
                event_constants.mark_processed(event, "SUCCESS")
            db.commit()
    raise AssertionError("the chain did not settle")


def _values(db, table):
    model = models.DYNAMIC_TABLES[table]
    return sorted((r.k, r.n) for r in db.query(model).all())


# ------------------------------------------------------------------------------- pause

def test_a_paused_group_is_rewound_at_a_stage_and_not_charged(db, monkeypatch):
    _write(db, PA, [{"k": "K1", "n": "0"}, {"k": "K2", "n": "0"}])
    events = _pending(db)
    assert events and all(e.retry_count in (0, None) for e in events)

    def slow(tx_id, evs, session, rules):
        for step in range(30):                              # 3 s if nothing stops it
            with alignment_batch_counts.stage("write:t%d" % step):
                time.sleep(0.1)
        return True, None, []

    thread, out = _run_pending_in_background(db, slow, monkeypatch)
    time.sleep(0.3)
    chain_control.pause("test", "incident drill")
    started = time.time()
    thread.join(10)
    assert time.time() - started < 1.5, "the group ran on past its next stage"
    assert out == {"failed_any": False}, out
    db.expire_all()
    for event in _pending(db):
        assert event.status == "PENDING" and event.retry_count in (0, None)
    assert len(_pending(db)) == len(events), "a paused group's events stay queued"

    chain_control.resume()
    thread, out = _run_pending_in_background(db, lambda *a: (True, None, []), monkeypatch)
    thread.join(10)
    assert out == {"failed_any": False} and _pending(db) == []


def test_while_paused_no_group_is_taken(db, monkeypatch):
    _write(db, PA, [{"k": "K1", "n": "0"}])
    ran = []
    chain_control.pause("test", "before the batch")

    thread, out = _run_pending_in_background(
        db, lambda *a: ran.append(1) or (True, None, []), monkeypatch)
    thread.join(10)

    assert ran == [] and len(_pending(db)) == 1


def test_a_pause_is_still_there_after_a_restart(control_in_tmp):
    chain_control.pause("test", "held over a restart")

    fresh = subprocess.run(
        [sys.executable, "-c", "from chain import control; print(control.paused()['reason'])"],
        cwd=SERVER_DIR, capture_output=True, text=True,
        env=dict(os.environ, ASSY_DATA_ROOT=str(control_in_tmp), PYTHONIOENCODING="utf-8"))

    assert fresh.stdout.strip() == "held over a restart", fresh.stderr[-500:]
    chain_control.resume()
    assert chain_control.paused() is None


def _health(state=None, stale=False):
    beats = {"chain": {"pid": os.getpid(), "beats": 5, "age_seconds": 999 if stale else 1.0,
                       "stale": stale, "stale_after_seconds": 60.0, "state": state}}
    sup = {"supervisor_pid": 42, "updated_at": time.time(), "failed_children": [],
           "events": [], "children": {"Chain": {
               "state": "running", "heartbeat": "chain", "pid": os.getpid(), "restarts": 0,
               "uptime_seconds": 3600.0, "last_exit_code": None, "failure_reason": None}}}
    payload, _code = compute_health(DB_OK, beats, sup, OUTBOX_OK, 60.0, backup_result=None)
    return payload["status"], payload["checks"]["workers"]["chain"]["status"]


def test_health_says_paused_in_its_own_word_and_a_wedge_still_wins():
    assert _health() == ("ok", "ok")
    assert _health(state="paused") == ("degraded", "paused")
    assert _health(state="paused", stale=True)[1] == "wedged"


@pytest.mark.pg
def test_a_pause_cancels_the_query_a_group_is_waiting_on(pg_engine, monkeypatch):
    monkeypatch.setattr(process_logging, "active_process_name", lambda: "Chain")
    _tables(pg_engine)
    db = sessionmaker(bind=pg_engine)()
    try:
        _write(db, PA, [{"k": "K1", "n": "0"}])
        before = len(_pending(db))

        def sleeps(tx_id, evs, session, rules):
            with alignment_batch_counts.stage("mapper"):
                session.execute(text("SELECT pg_sleep(30)"))
            return True, None, []

        thread, out = _run_pending_in_background(db, sleeps, monkeypatch)
        assert _wait(lambda: ((heartbeat.read_all().get("chain") or {}).get("work") or {})
                     .get("facts", {}).get("db_pid")), "the group never published its pid"
        other = sessionmaker(bind=pg_engine)()
        try:
            state = chain_control.pause_now(other, "test", "a query that would take 30 s")
        finally:
            other.close()
        started = time.time()
        thread.join(15)

        assert state["cancelled_pid"], state
        assert time.time() - started < 5, "the pause waited the query out"
        assert out == {"failed_any": False}, out
        db.rollback()
        assert len(_pending(db)) == before
        assert all(e.retry_count in (0, None) for e in _pending(db))
    finally:
        chain_control.resume()
        db.rollback()
        db.close()
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _wait(predicate, seconds=10.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    return None


# ---------------------------------------------------------------------------- set aside

def test_set_aside_takes_only_its_scope_collapsed_events_too_and_deletes_nothing(db):
    _write(db, PA, [{"k": "K1", "n": "0"}])                           # per-row
    _write(db, PA, [{"k": "K2", "n": "0"}, {"k": "K3", "n": "0"}], collapsed=True)
    _write(db, PB, [{"k": "K9", "n": "0"}])
    total = db.query(models.DatabaseOutbox).count()

    dry = set_aside.set_aside(db, tables=[PA])
    assert dry == {"events": 2, "rows": 3, "by_table": {PA: 2}}
    assert len(_pending(db)) == 3, "a dry run changes nothing"

    set_aside.set_aside(db, tables=[PA], apply=True, reason="drill")

    assert db.query(models.DatabaseOutbox).count() == total, "nothing may be deleted"
    assert [e.table_name for e in _pending(db)] == [PB]
    marked = [get_payload_dict(e) for e in db.query(models.DatabaseOutbox).all()
              if get_payload_dict(e).get(event_constants.CANCEL_MARK)]
    assert len(marked) == 2 and all(p[event_constants.CANCEL_REASON] == "drill" for p in marked)


def test_a_rule_or_a_transaction_scope_narrows_it(db, monkeypatch):
    monkeypatch.setattr(replay, "load_rules", _bumpers)
    _write(db, PA, [{"k": "K1", "n": "0"}])
    _write(db, PB, [{"k": "K9", "n": "0"}])
    tx = get_payload_dict(_pending(db)[1]).get("transaction_id")

    assert set_aside.set_aside(db, rules=["es_a_to_b"])["by_table"] == {PA: 1}
    assert set_aside.set_aside(db, transactions=[tx])["by_table"] == {PB: 1}
    assert set_aside.set_aside(db, tables=[PA], transactions=[tx])["events"] == 0


def test_running_them_again_gives_the_cells_the_chain_would_have_written(db, monkeypatch):
    rules = _bumpers()
    monkeypatch.setattr(replay, "load_rules", lambda: rules)
    _write(db, PA, [{"k": "K1", "n": "0"}])
    _write(db, PA, [{"k": "K2", "n": "0"}, {"k": "K3", "n": "0"}], collapsed=True)
    _drain(db, rules)
    untouched = (_values(db, PA), _values(db, PB))
    assert untouched[1] == [("K1", "1"), ("K2", "1"), ("K3", "1")]
    assert untouched[0] == [("K1", "2"), ("K2", "2"), ("K3", "2")], \
        "the fixture has no opted-in downstream, so a cascade would not show"

    # The same writes on fresh rows, set aside instead of run, then run again.
    for name in TABLES:
        db.query(models.DYNAMIC_TABLES[name]).delete()
    db.commit()
    _write(db, PA, [{"k": "K1", "n": "0"}])
    _write(db, PA, [{"k": "K2", "n": "0"}, {"k": "K3", "n": "0"}], collapsed=True)
    out = retroactive.execute({"run_id": "es1", "op": "set_aside",
                               "params": {"tables": PA, "reason": "drill"}}, log=lambda m: None)
    assert out["status"] == "ok", out["error"]
    assert _pending(db) == []

    out = retroactive.execute({"run_id": "es2", "op": "rerun_set_aside",
                               "params": {"tables": PA}}, log=lambda m: None)
    assert out["status"] == "ok", out["error"]
    _drain(db, rules)

    assert (_values(db, PA), _values(db, PB)) == untouched
