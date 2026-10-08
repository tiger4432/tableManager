"""The emergency stop (소유자 「오늘 보면 이런 대형 사고에서 끌 방법이 없는 게 문제였으」, 총괄
3840af307 · 2dbbfd1e5): Pause stops the chain within seconds and loses nothing, and events can
be set aside by table, rule or transaction and run again later, each rule once.

  pause, Python-bound group   rewound at its next stage boundary · not charged · Resume runs it
  pause, a running query      cancelled by the pause itself, not waited out (PostgreSQL)
  pause survives a restart     a fresh process reads it
  health                      `paused`, its own word, degraded - a bigger verdict still wins
  set aside                   only the scope - collapsed events too - and nothing deleted
  run again                   the rows those events named, each rule once - nothing downstream
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


def test_running_them_again_runs_each_rule_once_and_wakes_nothing_downstream(db, monkeypatch):
    """소유자 09-27 「큰 소급 치워둔거니 한번만」. The grid's click replay still cascades - that
    half is the parametrized replay cell in test_a_chain_write_reads_as_the_chain_whatever_its_layer."""
    rules = _bumpers()
    downstream = rules[1]
    monkeypatch.setattr(replay, "load_rules", lambda: rules)
    _write(db, PA, [{"k": "K1", "n": "0"}])
    _write(db, PA, [{"k": "K2", "n": "0"}, {"k": "K3", "n": "0"}], collapsed=True)
    _drain(db, rules)
    assert _values(db, PA) == [("K1", "2"), ("K2", "2"), ("K3", "2")], \
        "the live chain wakes the opted-in b -> a here, or the cell below proves nothing"

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

    before = db.query(models.DatabaseOutbox.id).order_by(models.DatabaseOutbox.id.desc()).first()[0]
    out = retroactive.execute({"run_id": "es2", "op": "rerun_set_aside",
                               "params": {"tables": PA}}, log=lambda m: None)
    assert out["status"] == "ok", out["error"]
    _drain(db, rules)

    wrote = (db.query(models.DatabaseOutbox)
             .filter(models.DatabaseOutbox.id > before, models.DatabaseOutbox.table_name == PB)
             .all())
    assert wrote, "a -> b ran once and wrote b"
    assert [e.id for e in wrote if worker.fires(downstream, e)] == []
    assert _values(db, PB) == [("K1", "1"), ("K2", "1"), ("K3", "1")]
    assert _values(db, PA) == [("K1", "0"), ("K2", "0"), ("K3", "0")]


# ------------------------------------------------------------------ × on one queue line (소유자 10-08)

@pytest.fixture(name="routed")
def fixture_routed(tmp_path, monkeypatch):
    """(session, the routes on it) - one in-memory database every thread sees, since the test
    client answers on a thread of its own."""
    import main
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from database.database import get_db

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    _tables(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    monkeypatch.setattr("database.database.SessionLocal", lambda: _NoClose(session))
    main.app.dependency_overrides[get_db] = lambda: session
    try:
        yield session, TestClient(main.app)
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


@pytest.fixture(name="db_q")
def fixture_db_q(routed):
    return routed[0]


@pytest.fixture(name="queue")
def fixture_queue(routed):
    return routed[1]


def _lines(client):
    return client.get("/admin/chain/queue").json()["waiting_transactions"]


def _key_of(client, table):
    [line] = [line for line in _lines(client) if table in line["tables"]]
    return line["cancel"]["key"]


def _cross(client, key, **headers):
    return client.post("/admin/chain/queue/cancel", json={"key": key}, headers=headers)


def _rows(db, table):
    db.expire_all()
    return [(e.status, e.processed_chain, e.retry_count or 0,
             get_payload_dict(e).get(event_constants.CANCEL_MARK))
            for e in db.query(models.DatabaseOutbox).filter_by(table_name=table)]


SET_ASIDE = ("SUCCESS", True, 0, set_aside.OPERATOR)


def test_a_cross_sets_its_lines_waiting_events_aside_and_leaves_the_others(db_q, queue):
    db = db_q
    from ledger import followup as ledger_followup

    _write(db, PA, [{"k": "K1", "n": "0"}])
    _write(db, PB, [{"k": "K2", "n": "0"}])
    [line] = [line for line in _lines(queue) if PA in line["tables"]]
    assert line["cancel"]["key"] == line["transaction_id"]
    other = [e.id for e in _pending(db) if e.table_name == PB]
    followed = ledger_followup.outbox_depth(db.get_bind())

    answer = _cross(queue, line["cancel"]["key"], **{"X-User": "kim"})

    assert (answer.status_code, answer.json()) == (200, {"skipped_events": 1, "cancelled_pid": None})
    assert _rows(db, PA) == [SET_ASIDE]
    assert [e.id for e in _pending(db)] == other                               # the other line waits
    assert ledger_followup.outbox_depth(db.get_bind()) == followed + 1         # the ledger follows it
    said = [(a.table_name, a.old_value, a.new_value, a.updated_by)
            for a in db.query(models.AuditLog).filter_by(source_name=set_aside.QUEUE_SKIP_SOURCE)]
    assert said == [(PA, line["cancel"]["key"], 1, "kim")]


def test_a_line_already_in_the_workers_batch_does_not_run_once_set_aside(db_q, queue, monkeypatch):
    db = db_q
    _write(db, PA, [{"k": "K1", "n": "0"}])
    _write(db, PB, [{"k": "K2", "n": "0"}])
    order, groups = _groups(_pending(db))                                       # the worker holds both
    assert _cross(queue, _key_of(queue, PA)).json()["skipped_events"] == 1
    ran = []
    monkeypatch.setattr(worker, "_process_chain_transaction_group_sync",
                        lambda tx, events, session, rules: ran.append(events[0].table_name) or (True, None, []))

    asyncio.run(worker.process_pending_groups(db, order, groups, [], None))

    assert ran == [PB]
    assert _rows(db, PA) == [SET_ASIDE]


def test_a_group_set_aside_while_it_runs_is_neither_failed_nor_retried_and_the_next_runs(
        db_q, queue, monkeypatch):
    db = db_q
    _write(db, PA, [{"k": "K1", "n": "0"}])
    _write(db, PB, [{"k": "K2", "n": "0"}])
    key = _key_of(queue, PA)
    ran = []

    def body(tx_id, events, session, rules):
        ran.append(events[0].table_name)
        if events[0].table_name == PA:
            # × while it runs: the mark is committed, then the query it waits on is cancelled
            assert _cross(queue, key).json()["skipped_events"] == 1
            return False, "canceling statement due to user request", []
        return True, None, []
    monkeypatch.setattr(worker, "_process_chain_transaction_group_sync", body)
    order, groups = _groups(_pending(db))

    failed_any = asyncio.run(worker.process_pending_groups(db, order, groups, [], None))

    assert _rows(db, PA) == [SET_ASIDE]                                         # not FAILED, not RETRYING
    assert ran == [PA, PB] and failed_any is False and chain_control.paused() is None


@pytest.mark.parametrize("state", ["running", "done"])
def test_a_runs_line_answers_what_the_runs_own_cancel_answers(db_q, queue, state):
    db = db_q
    def fresh():
        db.query(models.RetroactiveRun).filter_by(run_id="es-run").delete()
        db.add(models.RetroactiveRun(run_id="es-run", op="chain_replay", state=state))
        db.commit()

    fresh()
    crossed = _cross(queue, "es-run")
    fresh()
    own = queue.post("/admin/retroactive/runs/es-run/cancel")
    assert (crossed.status_code, crossed.json()) == (own.status_code, own.json())


def test_a_key_that_no_longer_waits_says_what_became_of_it(db_q, queue):
    db = db_q
    _write(db, PA, [{"k": "K1", "n": "0"}])
    _write(db, PB, [{"k": "K2", "n": "0"}])
    db.add(models.DatabaseOutbox(event_uuid="es-no-tx", table_name="es_no_tx", event_type="EDIT",
                                 payload={"row_id": "x"}, processed_chain=False))
    db.commit()
    by_table = {table: _key_of(queue, table) for table in (PA, PB)}
    [row_key] = [line["cancel"]["key"] for line in _lines(queue)
                 if line["cancel"]["key"].startswith(event_constants.QUEUE_ROW_KEY_PREFIX)]
    for event in [e for e in _pending(db) if e.table_name == PB]:
        event_constants.mark_processed(event, "SUCCESS")
    db.commit()

    answers = {"waiting": _cross(queue, by_table[PA]).json(),
               "set_aside": _cross(queue, by_table[PA]).json(),
               "row": _cross(queue, row_key).json(),
               "row_again": _cross(queue, row_key).json(),
               "processed": _cross(queue, by_table[PB]).json(),
               "gone": _cross(queue, "es-never-a-line").json()}
    assert answers == {"waiting": {"skipped_events": 1, "cancelled_pid": None},
                       "set_aside": {"skipped_events": 0, "already": "set_aside"},
                       "row": {"skipped_events": 1, "cancelled_pid": None},
                       "row_again": {"skipped_events": 0, "already": "set_aside"},
                       "processed": {"skipped_events": 0, "already": "processed"},
                       "gone": {"skipped_events": 0, "already": "gone"}}


@pytest.mark.parametrize("body", [{"key": ""}, {"key": "  "}, {"key": 5}, {}, {"key": "outbox#x"}],
                         ids=["empty", "blank", "number", "none", "row-key-not-a-number"])
def test_a_key_that_is_not_a_line_key_is_refused_and_nothing_moves(db_q, queue, body):
    db = db_q
    _write(db, PA, [{"k": "K1", "n": "0"}])
    answer = queue.post("/admin/chain/queue/cancel", json=body)
    assert answer.status_code == 422 and isinstance(answer.json()["detail"], str)
    assert len(_pending(db)) == 1


def test_setting_aside_leaves_a_row_the_chain_already_ended(db_q):
    db = db_q
    _write(db, PA, [{"k": "K1", "n": "0"}])
    [event] = _pending(db)
    event_constants.mark_processed(event, "SUCCESS")
    db.commit()
    assert set_aside._mark(db, [event.id], "late") == 0
    db.commit()
    assert _rows(db, PA) == [("SUCCESS", True, 0, None)]


@pytest.mark.pg
def test_a_cross_on_the_running_line_cancels_its_query_and_its_rows_stay_set_aside(pg_engine, monkeypatch):
    import main
    from fastapi.testclient import TestClient
    from database.database import get_db

    monkeypatch.setattr(process_logging, "active_process_name", lambda: "Chain")
    _tables(pg_engine)
    db = sessionmaker(bind=pg_engine)()
    other = sessionmaker(bind=pg_engine)()
    main.app.dependency_overrides[get_db] = lambda: other
    try:
        _write(db, PA, [{"k": "K1", "n": "0"}])
        _write(db, PB, [{"k": "K2", "n": "0"}])
        client = TestClient(main.app)
        running, waiting = _key_of(client, PA), _key_of(client, PB)
        ran = []

        def body(tx_id, events, session, rules):
            ran.append(events[0].table_name)
            if events[0].table_name == PA:
                try:
                    with alignment_batch_counts.stage("mapper"):
                        session.execute(text("SELECT pg_sleep(30)"))
                except Exception as exc:                            # noqa: BLE001 - as a rule run does
                    return False, str(exc), []
            return True, None, []

        thread, out = _run_pending_in_background(db, body, monkeypatch)
        assert _wait(lambda: running in (((heartbeat.read_all().get("chain") or {}).get("work") or {})
                                         .get("facts", {}).get("line_keys") or ())), "no running line"
        assert _wait(lambda: ((heartbeat.read_all().get("chain") or {}).get("work") or {})
                     .get("facts", {}).get("db_pid")), "the group never published its pid"
        # × on a line that is NOT running sets it aside and cancels nothing
        assert _cross(client, waiting).json() == {"skipped_events": 1, "cancelled_pid": None}
        assert thread.is_alive(), "a × on another line stopped the running group"
        crossed = _cross(client, running).json()
        started = time.time()
        thread.join(15)

        assert crossed["skipped_events"] == 1 and crossed["cancelled_pid"], crossed
        assert time.time() - started < 5, "the × waited the query out"
        assert out == {"failed_any": False}, out
        assert _rows(db, PA) == [SET_ASIDE] and _rows(db, PB) == [SET_ASIDE]
        assert ran == [PA] and chain_control.paused() is None
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        db.rollback()
        db.close()
        other.close()
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def test_a_group_says_which_line_it_is_as_it_starts_not_a_slice_later(db_q, queue, monkeypatch):
    """The × reads the running line from the beat file; at the default slice it reached the file
    20 s late - the window an operator presses in (총괄 10-08)."""
    db = db_q
    monkeypatch.setattr(heartbeat, "HEARTBEAT_SLICE_SECONDS", 600.0)
    _write(db, PA, [{"k": "K1", "n": "0"}])
    key = _key_of(queue, PA)
    seen = []

    def body(tx_id, events, session, rules):
        seen.append(((heartbeat.read_all().get("chain") or {}).get("work") or {})
                    .get("facts", {}).get("line_keys"))
        return True, None, []
    monkeypatch.setattr(worker, "_process_chain_transaction_group_sync", body)
    order, groups = _groups(_pending(db))
    asyncio.run(worker.process_pending_groups(db, order, groups, [], None))
    assert seen == [[key]]


#: The waiting queue the owner set aside from (소유자 10-08 「빼 두기가 5분 넘게」).
FLOODED = 50_000


def test_a_cross_and_a_transactions_set_aside_read_only_their_lines_rows(db_q, queue):
    from sqlalchemy import event

    db = db_q
    _write(db, PA, [{"k": "K1", "n": "0"}])          # first, so its line heads the capped list
    db.execute(models.DatabaseOutbox.__table__.insert(), [
        {"event_uuid": "es-flood-%d" % i, "event_type": "EDIT", "table_name": "es_flood",
         "payload": {"transaction_id": "es-flood-%d" % (i // 10), "row_id": "r%d" % i},
         "processed_chain": False, "status": "PENDING", "retry_count": 0} for i in range(FLOODED)])
    db.commit()
    key = _key_of(queue, PA)
    loaded = []

    def on_load(target, _context):
        loaded.append(target.id)
    event.listen(models.DatabaseOutbox, "load", on_load)
    try:
        crossed = _cross(queue, key).json()
        on_cross = len(loaded)
        by_operator = set_aside.set_aside(db, transactions=["es-flood-7"], apply=True)
    finally:
        event.remove(models.DatabaseOutbox, "load", on_load)

    assert crossed["skipped_events"] == 1 and by_operator["marked"] == 10
    # each row of the line read twice here - the scope, then SQLite's per-object mark (PostgreSQL
    # marks set-based and reads none) - and no row of the other 50,000
    assert (on_cross, len(loaded) - on_cross) == (2 * 1, 2 * 10), "rows read: a line's, not the queue's"


def test_a_cross_answers_at_once_while_another_run_is_in_flight(db_q, queue):
    db = db_q
    db.add(models.RetroactiveRun(run_id="es-busy", op="withdraw", state=retroactive.RUN_RUNNING,
                                 runner="elsewhere:1"))
    db.commit()
    assert retroactive.gate_refusal(db), "the gate is not closed - this measures nothing"
    _write(db, PA, [{"k": "K1", "n": "0"}])
    started = time.time()
    answer = _cross(queue, _key_of(queue, PA))
    assert (answer.status_code, answer.json()["skipped_events"]) == (200, 1)
    assert time.time() - started < 5 and _rows(db, PA) == [SET_ASIDE]


def test_a_queued_run_is_cancelled_at_once_and_the_run_behind_it_starts(db_q, queue, tmp_path, monkeypatch):
    from run_auto_update import MultiDiscoveryScheduler

    db = db_q
    for run in ("es-q1", "es-q2"):
        db.add(models.RetroactiveRun(run_id=run, op="withdraw", state=retroactive.RUN_QUEUED))
        db.add(models.DatabaseOutbox(event_uuid=run, event_type=event_constants.EVENT_RETROACTIVE_RUN,
                                     table_name=retroactive.RUN_EVENT_TABLE,
                                     payload={"run_id": run, "op": "withdraw"}, processed_chain=False))
    db.commit()

    crossed = _cross(queue, "es-q1").json()

    assert (crossed["state"], crossed["released"]) == (retroactive.RUN_CANCELLED, True)
    assert retroactive.gate_refusal(db) is None                                 # the gate is open
    started = []
    monkeypatch.setattr(retroactive, "spawn_claimed", lambda run_id, log=None: started.append(run_id))
    scheduler = MultiDiscoveryScheduler(check_interval=5, server_dir=str(tmp_path))
    for _tick in range(2):                       # the cancelled one's wake-up row, then the next run
        scheduler.handle_retroactive_trigger(db)
    assert started == ["es-q2"]


def test_a_running_runs_cancel_is_asked_as_before(db_q, queue):
    db = db_q
    db.add(models.RetroactiveRun(run_id="es-r1", op="withdraw", state=retroactive.RUN_RUNNING))
    db.commit()
    crossed = _cross(queue, "es-r1").json()
    assert (crossed["state"], crossed["released"]) == (retroactive.RUN_CANCEL_REQUESTED, False)


def test_the_queue_reads_its_waiting_rows_in_a_fixed_few_queries_and_names_a_one_row_line(db_q, queue):
    """총괄 6d7046a42: the lines and the kinds are two reads of the waiting rows however many lines
    wait (it was seven queries, two of them over every payload); a one-row line names its row as a
    value (6c678dd13) beside the old text."""
    from sqlalchemy import event

    def queries():
        """(statements that read the outbox, the answer)"""
        seen = []
        listen = lambda conn, cur, statement, params, ctx, many: seen.append(statement)   # noqa: E731
        event.listen(db_q.get_bind(), "before_cursor_execute", listen)
        try:
            answer = queue.get("/admin/chain/queue")
        finally:
            event.remove(db_q.get_bind(), "before_cursor_execute", listen)
        assert answer.status_code == 200, answer.text
        return sum(1 for statement in seen if "database_outbox" in statement), answer.json()

    for k in range(3):
        _write(db_q, PA, [{"k": "Q%d" % k, "n": "0"}])                 # three transaction lines
    few, _answer = queries()
    for k in range(3, 40):
        _write(db_q, PA, [{"k": "Q%d" % k, "n": "0"}])
    many, _answer = queries()
    assert few == many == 2, (few, many)                             # the kinds, and the lines

    row = models.DatabaseOutbox(event_uuid="one-row", event_type="CREATE", table_name=PB,
                                payload={"row_id": "r1"}, processed_chain=False)
    db_q.add(row)
    db_q.commit()
    _count, answer = queries()
    [line] = [line for line in answer["waiting_transactions"] if line.get("outbox_id") is not None]
    assert (line["outbox_id"], line["transaction_id"]) == (row.id, "(no tx · outbox#%d)" % row.id)
