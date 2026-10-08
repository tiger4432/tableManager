"""A chain queue line runs in a slot process of its own (총괄 19f6a9277, 소유자 「프로세스 할당 지어」 ·
「뭐 큰 거 하나 돌리면 아주 시스템 마비」 · 「그럼 내가 kill 9 pid 로도 지울 수 있잖아」), and two slots
never write one table across each other (데이터 가드 ㉮ ㄱ).

  table locks     a replay group that read R=v1 before a person saved v2 lands first; the group
                  that runs the save waits for its tables, then writes d(v2)
  real slots      `python -m tests.support.scratch_slot <n>` - the real slot body on this test's
                  scratch schema and data root; this test process is the dispatcher
    other lines   a line held in one slot does not hold a line in another; a drained line is not
                  given again
    one log       a slot's log lines land in the dispatcher's log under `[slot n pid P]`
    set aside     by table: the group holding those events is cut and rewinds, the rest of its line
                  runs on in the same slot; a mapper error is a failure as before; a group holding
                  none of them is not cut; a cut that lands on a group anyway rewinds it
    ×             stops that line's slot only - its events set aside, a new slot started
    kill          a slot killed by pid: its line's waiting events set aside by name, not run again
    pause         the held group is rewound, nothing is given; Resume runs the line
    order         a row-by-row line resting after a failure keeps a later one on its tables waiting
    same table    a person's line on a replay's tables waits one replay group, not the replay
"""
import importlib
import json
import logging
import os
import sys
import textwrap
import threading
import time

import psutil
import pytest
from sqlalchemy import text
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
from chain import set_aside, slots, table_locks                       # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from database.context import channel, outbox_mode, retroactive_run    # noqa: E402
from database.database import Base, connection_name                   # noqa: E402
from tests.support import isolated_pg, scratch_slot                   # noqa: E402
from runtime import running as running_seat                          # noqa: E402
from utils import heartbeat                                           # noqa: E402
from utils import logger as process_logging                           # noqa: E402
from utils.payload_helper import get_payload_dict                     # noqa: E402

SA, SB, SC, SD = "sl_a", "sl_b", "sl_c", "sl_d"
TABLES = {name: {"business_key": "k", "composite_key_source": ["k"],
                 "column_types": {"k": "string", "n": "string"}, "display_columns": ["k", "n"]}
          for name in (SA, SB, SC, SD)}
COPY = """
import os
import time

HOOK = None


def copy(db, payload, rule=None):
    handed = payload if isinstance(payload, list) else [payload]
    out = []
    for p in handed:
        data = p.get("data") or {}
        k = (data.get("k") or {}).get("value")
        n = (data.get("n") or {}).get("value")
        if HOOK is not None:
            HOOK(n)
        gate = os.environ.get("SL_GATE")
        if gate and str(n).startswith("hold"):
            while os.path.exists(gate):
                time.sleep(0.05)
        if str(n).startswith("sleep-"):                  # held IN a statement - a cancel cuts it
            from sqlalchemy import text
            db.execute(text("SELECT pg_sleep(:s)"), {"s": float(str(n).split("-")[1])})
        once = os.environ.get("SL_FAIL_ONCE")
        if once and os.path.exists(once + "-" + str(n)):
            os.remove(once + "-" + str(n))
            raise RuntimeError("failing once for " + str(n))
        out.append({"business_key_val": k, "updates": {"k": k, "n": n}})
    return {"updates": out}
"""


def _rule(name, trigger, target):
    return {"name": name, "enabled": True, "is_batch": True, "trigger_table": trigger,
            "target_table": target, "mapper_module": "sl_copy", "mapper_function": "copy",
            "allow_chain_trigger": False, "max_group_attempts": 3}


COPY_RULE = _rule("sl_a_to_b", SA, SB)
RULES = [COPY_RULE, _rule("sl_c_to_d", SC, SD)]
SET_ASIDE = ("SUCCESS", True, set_aside.OPERATOR)


@pytest.fixture(autouse=True)
def box(tmp_path, monkeypatch):
    """This test's data root: its config, its heartbeats, its mapper."""
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))
    beats = tmp_path / "config" / heartbeat.HEARTBEAT_DIRNAME            # where the slots beat
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(beats))
    monkeypatch.setattr(heartbeat, "heartbeat_path", lambda name: str(beats / (name + ".json")))
    monkeypatch.setattr(process_logging, "active_process_name", lambda: "Chain")
    mapper_sdk.discover()
    (tmp_path / "sl_copy.py").write_text(textwrap.dedent(COPY), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("sl_copy", None)
    yield importlib.import_module("sl_copy")
    sys.modules.pop("sl_copy", None)
    for name in TABLES:
        crud.TABLE_CONFIG.pop(name, None)


def _tables(engine):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)


def _write(db, table, rows, collapsed=False, tx=None, commit=True):
    with channel(event_constants.CHANNEL_API), outbox_mode(
            event_constants.OUTBOX_MODE_COLLAPSED if collapsed else event_constants.OUTBOX_MODE_PER_ROW):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="sl")
            for row in rows], transaction_id=tx))
        if commit:
            db.commit()


def _one_line(db, writes):
    """Rows of several tables as ONE transaction's events - one queue line - written while the chain
    is paused, so the line's first group holds them all."""
    chain_control.pause("test", "write one line")
    tx = "sl-tx-%d" % (time.time() * 1000)
    try:
        for table, rows in writes:
            _write(db, table, rows, tx=tx)
    finally:
        chain_control.resume()
    return tx


def _this_runs_slots():
    """`LIKE` for this run's slot connections - another run's slots share the test database."""
    return connection_name(scratch_slot.process_name("%", isolated_pg.RUN_TOKEN))


def _in_a_statement(engine):
    """A slot's group held inside a statement (the mapper's `sleep-`) - what a cancel cuts."""
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT pid FROM pg_stat_activity WHERE application_name LIKE :slots"
            " AND state = 'active' AND query LIKE 'SELECT pg_sleep%'"), {"slots": _this_runs_slots()}).scalar()


def _events_of(db, table, key):
    """Every event of `table` that names the row of business key `key`, oldest first."""
    db.expire_all()
    row_id = db.query(models.DYNAMIC_TABLES[table].row_id).filter_by(k=key).scalar()
    return [e for e in db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.table_name == table)
            .order_by(models.DatabaseOutbox.id)
            if row_id in (get_payload_dict(e).get("row_ids") or [get_payload_dict(e).get("row_id")])]


def _ended(events):
    return [(e.status, e.processed_chain, get_payload_dict(e).get(event_constants.CANCEL_MARK)) for e in events]


def _done(db, table, key):
    """Every event of that row ended - its value written is not yet its ending written."""
    events = _events_of(db, table, key)
    return bool(events) and all(e.processed_chain for e in events)


def _value(db, table, key):
    db.expire_all()
    return db.query(models.DYNAMIC_TABLES[table].n).filter_by(k=key).scalar()


def _wait(predicate, seconds=10.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    return None


def _run_group(engine, events_of, out, name):
    """One slot's group on a thread of its own - its own session, its own lock connection."""
    def run():
        session = sessionmaker(bind=engine)()
        try:
            events = events_of(session)
            tx = get_payload_dict(events[0]).get("transaction_id")
            out[name] = worker._claimed_group_sync(tx, events, session, [COPY_RULE])
            session.commit()
        except BaseException as exc:                                  # noqa: BLE001
            out[name] = exc
        finally:
            session.close()
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def _waits_on_a_table_lock(engine):
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"
            " AND classid = :space"), {"space": table_locks.LOCK_SPACE}).scalar()


@pytest.mark.pg
def test_a_replay_that_read_v1_before_a_person_saved_v2_cannot_land_after_the_v2_group(pg_engine, box):
    mapper = box
    _tables(pg_engine)
    db = sessionmaker(bind=pg_engine)()
    key = "R-%d" % int(time.time() * 1000)                    # the schema is the session's
    try:
        _write(db, SA, [{"k": key, "n": "v1"}], collapsed=True)        # the replay's event
        [replay] = _events_of(db, SA, key)
        read_v1, go = threading.Event(), threading.Event()

        def hook(n):
            if n == "v1":
                read_v1.set()
                assert go.wait(20), "the test never let the replay group go on"
        mapper.HOOK = hook
        out = {}
        a = _run_group(pg_engine, lambda s: [s.get(models.DatabaseOutbox, replay.id)], out, "replay")
        assert read_v1.wait(15), "the replay group never read its row"

        _write(db, SA, [{"k": key, "n": "v2"}])                      # a person saves v2
        [save] = [e for e in _events_of(db, SA, key) if e.id != replay.id]
        b = _run_group(pg_engine, lambda s: [s.get(models.DatabaseOutbox, save.id)], out, "save")
        # the save's group waits on the replay's tables - or, without the locks, runs to the end
        assert _wait(lambda: _waits_on_a_table_lock(pg_engine) or not b.is_alive(), 10)
        go.set()
        a.join(20)
        b.join(20)

        assert out["replay"][0] and out["save"][0], out
        assert _value(db, SB, key) == "v2"
    finally:
        mapper.HOOK = None
        db.rollback()
        db.close()


# ------------------------------------------------------------------------------ real slots

class _Dispatcher:
    """The chain loop's turn, on a thread: this test's process gives its slots their lines."""

    def __init__(self, engine):
        self.engine, self.errors, self.stop, self.asked = engine, [], threading.Event(), 0
        self.pool = slots.SlotPool()
        self.thread = threading.Thread(target=self._run, name="test-dispatcher", daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stop.is_set():
            session = sessionmaker(bind=self.engine)()
            asked = 0
            try:
                asked = self.pool.tick(session, RULES)
            except Exception as exc:                                  # noqa: BLE001
                self.errors.append(exc)
            finally:
                session.close()
            self.asked += asked
            if not asked:
                self.pool.woken.wait(0.1)

    def close(self):
        self.stop.set()
        self.thread.join(10)
        for slot in list(self.pool.slots.values()):
            slot.let_go()
            try:
                slot.proc.wait(10)
            except Exception:                                         # noqa: BLE001
                slot.proc.kill()


@pytest.fixture(name="slot_box")
def fixture_slot_box(pg_engine, box, tmp_path, monkeypatch):
    """Two real slot processes on this test's schema and data root, and a dispatcher."""
    url, why = isolated_pg.resolve_url()
    if url is None:
        pytest.skip(why)
    _tables(pg_engine)
    config = tmp_path / "config"
    (config / "table_config.json").write_text(json.dumps(TABLES), encoding="utf-8")
    (config / "chain_rules.json").write_text(json.dumps({"rules": RULES}), encoding="utf-8")
    gate, fail_once = tmp_path / "gate", tmp_path / "fail-once"
    # API_BASE_URL: a closed local port - a slot's notices never reach the API a box runs
    for name, value in (("ASSY_DATA_ROOT", str(tmp_path)), ("PYTHONPATH", str(tmp_path)),
                        ("API_BASE_URL", "http://127.0.0.1:9"),
                        (isolated_pg.PG_TEST_URL_ENV, url),
                        ("ASSY_SLOT_TEST_SCHEMA", isolated_pg.scratch_schema("assy_pytest_pg")),
                        (scratch_slot.RUN_ENV, isolated_pg.RUN_TOKEN),
                        ("SL_GATE", str(gate)), ("SL_FAIL_ONCE", str(fail_once))):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(slots, "SLOT_MODULE", "tests.support.scratch_slot")
    # this run's slot names - what the dispatcher ends a dead slot's connections by
    monkeypatch.setattr(slots, "process_name", lambda index: scratch_slot.process_name(index, isolated_pg.RUN_TOKEN))
    monkeypatch.setattr(slots, "RESTART_REST_SECONDS", 0.5)
    wanted = {"n": 2}
    monkeypatch.setattr(slots, "chain_slots", lambda settings=None: wanted["n"])
    dispatcher = _Dispatcher(pg_engine)
    db = sessionmaker(bind=pg_engine)()
    box = type("SlotBox", (), {})()
    box.db, box.dispatcher, box.gate, box.fail_once, box.wanted = db, dispatcher, gate, fail_once, wanted
    try:
        assert _wait(lambda: len(_live_slots()) == 2, 90), ("the slots never came up", _live_slots())
        yield box
    finally:
        chain_control.resume()
        if gate.exists():
            gate.unlink()
        dispatcher.close()
        db.rollback()
        db.close()
        assert not dispatcher.errors, dispatcher.errors


def _live_slots():
    return {name: beat for name, beat in heartbeat.read_all().items()
            if name.startswith(slots.BEAT_PREFIX) and not beat.get("stale")}


def _slot_of(line):
    """The facts of the slot holding `line` - its pid among them - or None."""
    return running_seat.chain_lines_running().get(line)


def _state_of(line):
    return event_constants.chain_state_of(False, "PENDING", running=_slot_of(line), paused=chain_control.paused())


def _key_of(db, table, key):
    [event] = _events_of(db, table, key)[:1]
    return get_payload_dict(event).get("transaction_id")


def _held(db, table, key):
    """`(line key, slot pid)` once a slot holds the line of `key`'s first event."""
    line = _key_of(db, table, key)
    found = _wait(lambda: _slot_of(line), 30)
    assert found, ("no slot holds the line", line, running_seat.chain_lines_running())
    return line, found["pid"]


@pytest.mark.pg
def test_a_line_held_in_one_slot_does_not_hold_a_line_in_another(slot_box):
    db, stamp = slot_box.db, "%d" % (time.time() * 1000)
    slot_box.gate.write_text("held", encoding="utf-8")
    _write(db, SA, [{"k": "A" + stamp, "n": "hold-1"}])
    line, pid = _held(db, SA, "A" + stamp)
    assert slots.is_slot(pid, slots.holding(line)[0]), "the pid on the list is not a slot process"

    _write(db, SC, [{"k": "C" + stamp, "n": "c1"}])
    assert _wait(lambda: _value(db, SD, "C" + stamp) == "c1", 30), "another line waited behind the held one"
    assert _value(db, SB, "A" + stamp) is None and (_slot_of(line) or {}).get("pid") == pid

    slot_box.gate.unlink()
    assert _wait(lambda: _value(db, SB, "A" + stamp) == "hold-1", 30)

    # once nothing waits, nothing is given: a drained line is not handed out again from the window
    # read before it drained (it was - asked, drained and given again every few ms until the next read)
    waiting = db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
    assert _wait(lambda: db.expire_all() or waiting.count() == 0, 30)
    asked = slot_box.dispatcher.asked
    time.sleep(1.2)
    assert slot_box.dispatcher.asked == asked, "a drained line was given again"


@pytest.mark.pg
def test_a_slots_log_lines_land_in_the_dispatchers_log_under_its_pid(slot_box, caplog):
    """One chain log (총괄 19f6a9277 ㉯): a slot writes no file; its lines come up its stderr."""
    caplog.set_level(logging.INFO)
    slot_box.wanted["n"] = 3
    assert _wait(lambda: slots.beat_name(3) in _live_slots(), 60), ("slot 3 never came up", _live_slots())
    pid = _live_slots()[slots.beat_name(3)]["pid"]
    said = "[slot 3 pid %d] [Chain] slot 3 up, pid %d" % (pid, pid)
    assert _wait(lambda: said in [r.getMessage() for r in caplog.records], 10), \
        [r.getMessage() for r in caplog.records if "slot 3" in r.getMessage()]


@pytest.mark.pg
@pytest.mark.parametrize("kind", ["transaction", "done run"])
def test_a_cross_on_a_running_line_stops_its_slot_only(slot_box, kind):
    """A replay that is `done` once it has staged its events is stopped the same way (총괄 e2b5b6f35)."""
    db, stamp = slot_box.db, "%d" % (time.time() * 1000)
    slot_box.gate.write_text("held", encoding="utf-8")
    rows = [{"k": "A" + stamp, "n": "hold-1"}, {"k": "B" + stamp, "n": "hold-2"}]
    if kind == "done run":
        run_id = "sl-run-" + stamp
        db.add(models.RetroactiveRun(run_id=run_id, op="chain_replay", state=retroactive.RUN_DONE))
        db.commit()
        with retroactive_run(run_id):
            _write(db, SA, rows)
        line = run_id
        found = _wait(lambda: _slot_of(line), 30)
        assert found, ("no slot holds the run's line", running_seat.chain_lines_running())
        pid = found["pid"]
    else:
        _write(db, SA, rows)
        line, pid = _held(db, SA, "A" + stamp)
    named = _wait(lambda: [name for name, beat in _live_slots().items() if beat.get("pid") == pid], 10)
    assert named, ("no live beat has the slot's pid", pid, _live_slots())
    index = int(named[0][len(slots.BEAT_PREFIX):])
    with db.get_bind().connect() as conn:
        backends = conn.execute(text("SELECT array_agg(pid) FROM pg_stat_activity WHERE application_name = :name"),
                                {"name": connection_name(slots.process_name(index))}).scalar()
    assert backends, "the slot holds no connection - else its end measures nothing"

    answer = chain_control.stop_line(db, line, "kim")

    assert (answer["skipped_events"], answer["slot_pid"]) == (2, pid), answer
    assert answer.get("run") == (retroactive.RUN_DONE if kind == "done run" else None), answer
    # the × answers once the slot and its connections have ended (총괄 54a53f894 - it counts after)
    assert not psutil.pid_exists(pid), "the × answered while its slot was running"
    with db.get_bind().connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE pid = ANY(:pids)"),
                            {"pids": backends}).scalar() == 0, "the × answered while its slot's connections were up"
    assert _ended(_events_of(db, SA, "A" + stamp) + _events_of(db, SA, "B" + stamp)) == [SET_ASIDE] * 2
    assert _wait(lambda: len(_live_slots()) == 2 and pid not in {b["pid"] for b in _live_slots().values()}, 60), \
        "no new slot came up"
    slot_box.gate.unlink()
    _write(db, SC, [{"k": "C" + stamp, "n": "c1"}])
    assert _wait(lambda: _value(db, SD, "C" + stamp) == "c1", 30)
    assert _value(db, SB, "A" + stamp) is None


@pytest.mark.pg
def test_setting_a_table_aside_cuts_the_group_holding_it_and_its_line_runs_on_in_the_slot(slot_box, pg_engine):
    """총괄 10-08: setting table A aside cuts the query of the group holding A's event - not the
    slot. The group rewinds: the line's table-B event waits with its attempts as they were and
    runs to the end."""
    db, stamp = slot_box.db, "%d" % (time.time() * 1000)
    line = _one_line(db, [(SA, [{"k": "A" + stamp, "n": "sleep-20"}]), (SC, [{"k": "C" + stamp, "n": "c1"}])])
    held = _wait(lambda: _slot_of(line), 30)
    assert held and _wait(lambda: _in_a_statement(pg_engine), 30), "the group never reached its statement"

    assert set_aside.set_aside(db, tables=[SA], apply=True)["marked"] == 1

    assert _wait(lambda: _done(db, SC, "C" + stamp), 15), "table B's event did not run on"
    assert _value(db, SD, "C" + stamp) == "c1"
    assert _value(db, SB, "A" + stamp) is None and _ended(_events_of(db, SA, "A" + stamp)) == [SET_ASIDE]
    assert [(e.status, e.retry_count) for e in _events_of(db, SC, "C" + stamp)] == [("SUCCESS", 0)]
    assert held["pid"] in {b["pid"] for b in _live_slots().values()}, "the slot was stopped"


@pytest.mark.pg
def test_a_set_aside_cuts_a_group_waiting_for_a_table_and_its_line_runs_on_in_the_slot(slot_box, pg_engine):
    """The cut also reaches a group waiting for a table another slot's group holds - its lock
    connection's query. The wait raised out of the group and ended the slot, and the slot's end
    set its whole line aside; now the batch is tried again with its events as they were."""
    db, stamp = slot_box.db, "%d" % (time.time() * 1000)
    run_id = "sl-run-" + stamp
    db.add(models.RetroactiveRun(run_id=run_id, op="chain_replay", state=retroactive.RUN_DONE))
    db.commit()
    with retroactive_run(run_id):
        _write(db, SA, [{"k": "R" + stamp, "n": "sleep-8"}], collapsed=True)    # its group holds sl_a · sl_b
    assert _wait(lambda: _in_a_statement(pg_engine), 30), "the replay never reached its statement"
    tx = "sl-tx-" + stamp
    _write(db, SA, [{"k": "A" + stamp, "n": "a1"}], tx=tx, commit=False)
    _write(db, SC, [{"k": "C" + stamp, "n": "c1"}], tx=tx)                     # one line, one commit

    def waiting_for_a_table():
        facts = _slot_of(tx) or {}
        return facts if str(facts.get("stage") or "").startswith(event_constants.CHAIN_WAITING_FOR) else None
    held = _wait(waiting_for_a_table, 30)
    assert held, ("the line never waited for a table", _slot_of(tx))
    [a_event] = _events_of(db, SA, "A" + stamp)

    set_aside.set_aside(db, ids=[a_event.id], apply=True)

    assert _wait(lambda: _done(db, SC, "C" + stamp), 30) and _value(db, SD, "C" + stamp) == "c1"
    assert _ended(_events_of(db, SA, "A" + stamp)) == [SET_ASIDE]
    assert [(e.status, e.retry_count) for e in _events_of(db, SC, "C" + stamp)] == [("SUCCESS", 0)]
    assert held["pid"] in {b["pid"] for b in _live_slots().values()}, "the slot was stopped"


@pytest.mark.pg
def test_a_mapper_error_in_a_group_a_set_aside_landed_on_is_a_failure_as_before(slot_box):
    """총괄 10-08: only a cut statement rewinds. Table A set aside while its group waits outside a
    statement (nothing to cut), then table B's mapper raises: B is charged an attempt - this rule
    allows 3; the default 1 would end it FAILED."""
    db, stamp = slot_box.db, "%d" % (time.time() * 1000)
    slot_box.gate.write_text("held", encoding="utf-8")
    c = "c" + stamp
    (slot_box.fail_once.parent / ("fail-once-" + c)).write_text("once", encoding="utf-8")
    line = _one_line(db, [(SA, [{"k": "A" + stamp, "n": "hold-1"}]), (SC, [{"k": "C" + stamp, "n": c}])])
    assert _wait(lambda: str((_slot_of(line) or {}).get("stage") or "").startswith("mapper"), 30)

    set_aside.set_aside(db, tables=[SA], apply=True)
    slot_box.gate.unlink()

    assert _wait(lambda: _done(db, SC, "C" + stamp), 30) and _value(db, SD, "C" + stamp) == c
    assert _value(db, SB, "A" + stamp) is None and _ended(_events_of(db, SA, "A" + stamp)) == [SET_ASIDE]
    assert [(e.status, e.retry_count) for e in _events_of(db, SC, "C" + stamp)] == [("SUCCESS", 1)]


@pytest.mark.pg
def test_a_set_aside_cuts_no_group_that_does_not_hold_its_events(slot_box, pg_engine):
    db, stamp = slot_box.db, "%d" % (time.time() * 1000)
    slot_box.gate.write_text("held", encoding="utf-8")
    _write(db, SA, [{"k": "A" + stamp, "n": "hold-1"}])
    _held(db, SA, "A" + stamp)
    _write(db, SC, [{"k": "C" + stamp, "n": "sleep-3"}])         # another line, another slot
    assert _wait(lambda: _in_a_statement(pg_engine), 30), "the other group never reached its statement"

    set_aside.set_aside(db, tables=[SA], apply=True)

    assert _wait(lambda: _done(db, SC, "C" + stamp), 15) and _value(db, SD, "C" + stamp) == "sleep-3"
    assert [(e.status, e.retry_count) for e in _events_of(db, SC, "C" + stamp)] == [("SUCCESS", 0)]


@pytest.mark.pg
def test_a_cut_that_lands_on_a_group_nothing_was_set_aside_from_rewinds_it(slot_box, pg_engine):
    """총괄 10-08: a cancel that is not the statement limit's - aimed at a group that ended in
    between, a pause's, an operator's - rewinds the group it lands on: not failed, not charged, it
    runs again to its end."""
    db, stamp = slot_box.db, "%d" % (time.time() * 1000)
    _write(db, SC, [{"k": "C" + stamp, "n": "sleep-3"}])
    pid = _wait(lambda: _in_a_statement(pg_engine), 30)
    assert pid, "the group never reached its statement"
    with pg_engine.connect() as conn:                       # nothing set aside: the cut aimed elsewhere
        assert conn.execute(text("SELECT pg_cancel_backend(:pid)"), {"pid": pid}).scalar()

    assert _wait(lambda: _done(db, SC, "C" + stamp), 30) and _value(db, SD, "C" + stamp) == "sleep-3"
    assert [(e.status, e.retry_count) for e in _events_of(db, SC, "C" + stamp)] == [("SUCCESS", 0)]


@pytest.mark.pg
def test_a_slot_killed_by_its_pid_sets_its_line_aside_and_the_line_does_not_run_again(slot_box):
    db, stamp = slot_box.db, "%d" % (time.time() * 1000)
    slot_box.gate.write_text("held", encoding="utf-8")
    _write(db, SA, [{"k": "A" + stamp, "n": "hold-1"}])
    line, pid = _held(db, SA, "A" + stamp)

    psutil.Process(pid).kill()                       # the owner's taskkill /F /PID
    reason = "slot pid %d ended (exit " % pid
    assert _wait(lambda: all(get_payload_dict(e).get(event_constants.CANCEL_REASON, "").startswith(reason)
                             for e in _events_of(db, SA, "A" + stamp)), 20), _ended(_events_of(db, SA, "A" + stamp))
    slot_box.gate.unlink()                           # a line given again would now run to its end
    assert _wait(lambda: len(_live_slots()) == 2 and pid not in {b["pid"] for b in _live_slots().values()}, 60)
    _write(db, SC, [{"k": "C" + stamp, "n": "c1"}])
    assert _wait(lambda: _value(db, SD, "C" + stamp) == "c1", 30)
    assert _value(db, SB, "A" + stamp) is None and _ended(_events_of(db, SA, "A" + stamp)) == [SET_ASIDE]
    said = [(a.table_name, a.old_value, a.updated_by) for a in
            db.query(models.AuditLog).filter_by(source_name=set_aside.QUEUE_SKIP_SOURCE) if a.old_value == line]
    assert said == [(SA, line, slots.CHAIN_WORKER)]


@pytest.mark.pg
def test_a_pause_rewinds_the_held_group_and_resume_runs_the_line(slot_box):
    db, stamp = slot_box.db, "%d" % (time.time() * 1000)
    slot_box.gate.write_text("held", encoding="utf-8")
    _write(db, SA, [{"k": "A" + stamp, "n": "hold-1"}])
    line, pid = _held(db, SA, "A" + stamp)

    chain_control.pause_now(db, "test", "pause a held line")
    assert _state_of(line)["state"] == event_constants.CHAIN_STATE_PAUSED
    slot_box.gate.unlink()                           # the group goes on to its next stage, and stops there
    assert _wait(lambda: _slot_of(line) is None, 20), "the slot still holds the line"
    asked = slot_box.dispatcher.asked
    _write(db, SC, [{"k": "C" + stamp, "n": "c1"}])
    time.sleep(1.0)
    assert [_value(db, SB, "A" + stamp), _value(db, SD, "C" + stamp)] == [None, None], "a line ran while paused"
    # a slot refuses a batch while paused too - the dispatcher asking anyway is a spin, not a stop
    assert slot_box.dispatcher.asked == asked, "the dispatcher gave lines while paused"
    assert [e.processed_chain for e in _events_of(db, SA, "A" + stamp)] == [False]

    chain_control.resume()
    assert _wait(lambda: _value(db, SB, "A" + stamp) == "hold-1" and _value(db, SD, "C" + stamp) == "c1", 30)


@pytest.mark.pg
def test_a_row_by_row_line_resting_after_a_failure_keeps_a_later_one_on_its_tables_waiting(slot_box):
    db, stamp = slot_box.db, "%d" % (time.time() * 1000)
    key = "R" + stamp
    (slot_box.fail_once.parent / ("fail-once-a" + stamp)).write_text("once", encoding="utf-8")
    _write(db, SA, [{"k": key, "n": "a" + stamp}])            # fails once, rests, runs again
    _write(db, SA, [{"k": key, "n": "b" + stamp}])            # the later save of the same row
    assert _wait(lambda: all(e.processed_chain for e in _events_of(db, SA, key)), 30)
    assert _value(db, SB, key) == "b" + stamp


@pytest.mark.pg
def test_a_persons_line_on_a_replays_tables_waits_one_replay_group_not_the_replay(slot_box):
    """The box's number, said in the report: how long a person's save waits while a replay of
    1,000-row groups runs on the same tables."""
    db, stamp = slot_box.db, "%d" % (time.time() * 1000)
    run_id = "sl-run-" + stamp
    db.add(models.RetroactiveRun(run_id=run_id, op="chain_replay", state=retroactive.RUN_DONE))
    db.commit()
    with retroactive_run(run_id):
        for page in range(4):
            _write(db, SA, [{"k": "P%s-%d-%d" % (stamp, page, i), "n": "r"} for i in range(1000)], collapsed=True)
    def replay_waiting():
        db.expire_all()
        return sum(1 for e in db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
                   if get_payload_dict(e).get("run_id") == run_id)

    started = _wait(lambda: _slot_of(run_id), 30)
    assert started, "the replay line never started"
    left_at_save, saved_at = replay_waiting(), time.time()
    _write(db, SA, [{"k": "S" + stamp, "n": "s1"}])
    assert _wait(lambda: _value(db, SB, "S" + stamp) == "s1", 60)
    waited, left_at_done = time.time() - saved_at, replay_waiting()
    print("[slot-test] a person's save on the replay's tables finished in %.2f s; replay groups waiting "
          "at the save %d, at its end %d (this box, 1,000-row groups)" % (waited, left_at_save, left_at_done))
    assert left_at_done > 0, "the replay finished first - this measured nothing"
    # the running replay group ends, then the save's group runs: at most that one group finished between
    assert left_at_save - left_at_done <= 1, (left_at_save, left_at_done)


class _ConnectionPeak:
    """The most database connections the slots held at once while it ran - sampled."""

    def __init__(self, engine):
        self.engine, self.peak, self.peak_all, self._stop = engine, 0, 0, threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def _sample(self):
        with self.engine.connect() as conn:
            while not self._stop.wait(0.05):
                slots_now, all_now = conn.execute(text(
                    "SELECT count(*) FILTER (WHERE application_name LIKE :slots), count(*)"
                    " FROM pg_stat_activity WHERE datname = current_database()"),
                    {"slots": _this_runs_slots()}).one()
                self.peak, self.peak_all = max(self.peak, slots_now), max(self.peak_all, all_now)

    def stop(self):
        self._stop.set()
        self._thread.join(5)
        return self.peak, self.peak_all


@pytest.mark.pg
def test_a_line_behind_three_thousand_replay_events_takes_the_free_slot(slot_box, pg_engine):
    """총괄 19f6a9277 «배정 창은 행이 아니라 줄»: a window of the first rows held only the replay's
    rows, and the line behind them was never seen while a slot stood free."""
    db, stamp = slot_box.db, "%d" % (time.time() * 1000)
    run_id = "sl-big-" + stamp
    db.add(models.RetroactiveRun(run_id=run_id, op="chain_replay", state=retroactive.RUN_DONE))
    db.commit()
    slot_box.gate.write_text("held", encoding="utf-8")
    with retroactive_run(run_id):
        _write(db, SA, [{"k": "B%s-%d" % (stamp, i), "n": "hold-%d" % i} for i in range(3000)])
    assert _wait(lambda: _slot_of(run_id), 30), "the replay line never started"
    peak = _ConnectionPeak(pg_engine)
    try:
        _write(db, SC, [{"k": "C" + stamp, "n": "c1"}])
        assert _wait(lambda: _value(db, SD, "C" + stamp) == "c1", 30), "the line behind the replay never ran"
        assert _value(db, SB, "B%s-0" % stamp) is None, "the replay ran first - this measured nothing"
    finally:
        slots_peak, all_peak = peak.stop()
        print("[slot-test] connections while 2 slots ran a 3,000-event replay and a live line: slots' peak %d,"
              " this database's peak %d (this box)" % (slots_peak, all_peak))
