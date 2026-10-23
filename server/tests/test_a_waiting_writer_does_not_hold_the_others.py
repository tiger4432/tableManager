# -*- coding: utf-8 -*-
"""C 간섭 · 총괄 1ff4dcc6c ⑤ ② ④: what one writer waits on must not hold the others.

  ⑤ a retroactive run reads changed declarations at its page boundaries - the slot's own boundary reload
    (`ingestion_worker.reload_at_boundary`), its child watching the files as a slot does
  ② the retroactive gate stays closed while a replay's staged events wait in the chain queue, and the writer
    outside it (`backfill --drifted --apply`) passes it
  ④ a group waits for a table at most the chain statement limit, then is rewound - not set aside, not charged - and
    the rest of its batch waits with it
"""
import logging
import time
from types import SimpleNamespace

import pytest

import event_constants
from admin import retroactive
from chain import ingestion_worker as ciw
from chain import table_locks
from database import config_watcher, crud, models, schemas
from database.context import outbox_mode
from database.models import DatabaseOutbox
from runtime import system_reload
from tests.test_retroactive_admin import retro_env  # noqa: F401 - its session and tables

SRC, DST = "wait_src", "wait_dst"
TABLES = {name: {"business_key": "key_id", "column_types": {"key_id": "string", "qty": "number"}}
          for name in (SRC, DST)}
RULES = [{"name": "wait_rule", "trigger_table": SRC, "target_table": DST, "mapper": "wait_mapper",
          "is_batch": True, "enabled": True}]


# ------------------------------------------------------------------------------ ⑤

def test_a_boundary_reload_applies_the_files_and_the_reload_rows_as_the_reader_takes_them(monkeypatch):
    rows = [SimpleNamespace(id=11, payload={}), SimpleNamespace(id=12, payload={"scope": system_reload.SCOPE_JOIN_KEYS})]
    done = []
    monkeypatch.setattr("database.database.SessionLocal", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(system_reload, "reloads_after", lambda session, seen: [r for r in rows if r.id > seen])
    monkeypatch.setattr(config_watcher, "apply_pending", lambda: done.append("files") or ["table_config.json"])
    monkeypatch.setattr(ciw, "reload_rules", lambda work: done.append(work))

    assert ciw.reload_at_boundary(system_reload.RETROACTIVE, 10) == (True, 12)
    assert done == ["files", system_reload.FULL], "a Reload row past the mark is the whole reload"
    done.clear()
    assert ciw.reload_at_boundary(system_reload.RETROACTIVE, 11) == (True, 12)
    assert done == ["files", system_reload.SCOPE_JOIN_KEYS], "a retroactive run writes - it forgets the join keys"
    done.clear()
    monkeypatch.setattr(config_watcher, "apply_pending", lambda: [])
    assert ciw.reload_at_boundary(system_reload.RETROACTIVE, 12) == (False, 12) and done == []


def test_each_page_boundary_reloads_and_a_reload_that_fails_does_not_stop_the_run(monkeypatch, caplog):
    asked = []

    def boundary(reader, seen):
        asked.append((reader, seen))
        if len(asked) == 2:
            raise RuntimeError("the database went away")
        return True, seen + 1

    monkeypatch.setattr(system_reload, "reload_mark", lambda: 5)
    monkeypatch.setattr(ciw, "reload_at_boundary", boundary)
    control = SimpleNamespace(progress=lambda *a: None, stop_requested=lambda: False, step=None)
    hook = retroactive._checkpoint(control)
    with caplog.at_level(logging.INFO):
        assert [hook(n) for n in (10, 20, 30)] == [False, False, False]
    assert asked == [(system_reload.RETROACTIVE, 5), (system_reload.RETROACTIVE, 6), (system_reload.RETROACTIVE, 6)]
    said = [r.getMessage() for r in caplog.records]
    assert any("the next page tries" in line for line in said)
    assert sum("declarations read again at a page boundary" in line for line in said) == 2


def test_the_childs_watcher_waits_for_the_page_boundary(monkeypatch):
    from admin import retroactive_run

    order = []
    monkeypatch.setattr(config_watcher, "start_config_watcher",
                        lambda engine=None, boundary=False: order.append(("watch", engine, boundary)))
    monkeypatch.setattr(retroactive, "run_claimed", lambda run_id, log=None: order.append(("run", run_id)))
    assert retroactive_run.main(["r-1"]) == 0
    assert order == [("watch", None, True), ("run", "r-1")]


# ------------------------------------------------------------------------------ ②

def _waiting(db, run_id, replay=True, processed=False, table="retro_test_source", uuid=""):
    payload = {"transaction_id": "tx-" + run_id, event_constants.RUN_KEY: run_id}
    if replay:
        payload[event_constants.REPLAY_KEY] = True
    row = DatabaseOutbox(event_uuid="u-%s-%s-%s-%s" % (run_id, replay, processed, uuid), event_type="EDIT", table_name=table,
                         payload=payload, processed_chain=processed, status="SUCCESS" if processed else "PENDING")
    db.add(row)
    db.commit()
    return row


def test_the_gate_stays_closed_while_a_replays_events_wait(retro_env):
    db = retro_env
    assert retroactive.gate_refusal(db) is None
    _waiting(db, "r-plain", replay=False)
    _waiting(db, "r-done", processed=True)
    assert retroactive.gate_refusal(db) is None, "an ordinary event, or a replay event that ran, holds nothing"
    _waiting(db, "r-wait", uuid="a")
    _waiting(db, "r-wait", uuid="b")
    said = retroactive.gate_refusal(db)
    assert said and "run_id=r-wait" in said and "2 of its event(s) on retro_test_source" in said
    assert "every retroactive run, on any table, waits" in said
    with pytest.raises(retroactive.RetroactiveRefused, match="r-wait"):
        retroactive.claim(op="probe_op", params={})


def test_drifted_apply_goes_through_the_rescope_run(monkeypatch):
    from ledger import backfill

    went = []
    import ledger.store
    monkeypatch.setattr(ledger.store.LedgerStore, "ensure_schema", lambda self: None)
    import ledger.schema
    import ledger.setup
    monkeypatch.setattr(ledger.schema, "require_world", lambda world: SimpleNamespace(name="w", declaration_root="d"))
    monkeypatch.setattr(ledger.setup, "load_setup", lambda root: "setup")
    monkeypatch.setattr(backfill, "drifted_scope", lambda engine, setup, source, world=None: ("lot", ["L1", "L2"]))
    monkeypatch.setattr(backfill, "_written", lambda op, params: went.append((op, params)) or {"inserted": 2})
    monkeypatch.setattr(backfill, "retranslate_drifted", lambda *a, **k: pytest.fail("ran outside the gate"))
    assert backfill.main(["--source", "s1", "--drifted", "--apply"]) == 0
    assert went == [("ledger_rescope", {"source": "s1", "scope_column": "lot", "scope_values": ["L1", "L2"],
                                        "world": "w"})]


# ------------------------------------------------------------------------------ ④

@pytest.fixture()
def db(db_session, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    monkeypatch.setattr(ciw, "_RULES_DOCUMENT", {})
    return db_session


def _seed(db, tx, n=2):
    with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, SRC, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"key_id": "%s-%d" % (tx, i), "qty": float(i)}, source_name="f.csv",
                                      updated_by="t", business_key_val="%s-%d" % (tx, i)) for i in range(n)],
            transaction_id=tx, silent=True))
    return [e for e in db.query(DatabaseOutbox).order_by(DatabaseOutbox.id).all()
            if (e.payload or {}).get("transaction_id") == tx]


@pytest.mark.anyio
async def test_a_table_not_held_is_rewound_and_the_rest_of_the_batch_waits(db, monkeypatch, caplog):
    first, second = _seed(db, "tx-1"), _seed(db, "tx-2")
    ran = []

    async def group(tx_id, events, session, rules):
        ran.append(tx_id)
        return False, str(table_locks.NotHeld(DST, 600)), []

    monkeypatch.setattr(ciw, "process_chain_transaction_group", group)
    with caplog.at_level(logging.WARNING):
        await ciw.process_pending_groups(db, ["tx-1", "tx-2"], {"tx-1": first, "tx-2": second}, RULES, None)
    assert ran == ["tx-1"], "a group after the one not held ran across it"
    db.expire_all()
    for event in first + second:
        assert (event.processed_chain, event.status, event.retry_count or 0) == (False, "PENDING", 0)
    said = [r.getMessage() for r in caplog.records]
    assert any("tx 'tx-1': table not held: %s within 600 s (another group holds it) - rewound, runs again" % DST in line
               for line in said), said
    assert not any("permanently failed" in line or "marked for retry" in line for line in said)


@pytest.mark.pg
def test_a_table_held_elsewhere_is_not_waited_for_past_the_limit(pg_engine, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from parsers import directory_watcher

    monkeypatch.setattr(directory_watcher, "chain_statement_timeout", lambda settings=None: 1.0)
    db = sessionmaker(bind=pg_engine)()
    other = pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        other.execute(text("SELECT pg_advisory_lock(:s, hashtext('wait_t'))"), {"s": table_locks.LOCK_SPACE})
        started = time.monotonic()
        with pytest.raises(table_locks.NotHeld, match="wait_t within 1 s"):
            with table_locks.hold(db, {"wait_t"}):
                pytest.fail("held a table another connection holds")
        assert 0.9 < time.monotonic() - started < 5
        # the limit is the lock connection's own - the pool does not hand it on
        for _ in range(3):
            with pg_engine.connect() as conn:
                assert conn.execute(text("SHOW lock_timeout")).scalar() == "0"
        other.execute(text("SELECT pg_advisory_unlock(:s, hashtext('wait_t'))"), {"s": table_locks.LOCK_SPACE})
        with table_locks.hold(db, {"wait_t"}):
            pass
    finally:
        other.close()
        db.close()


# ------------------------------------------------------------------------------ ④ the dispatcher gives no line onto a running one's tables

def _line(key, tables, orders=False, run=False):
    return {"line": key, "run": run, "orders": orders, "events": tables}


def _touching(monkeypatch):
    import chain.ingestion_worker as worker
    monkeypatch.setattr(worker, "_group_target_tables", lambda events, rules: set(events))
    monkeypatch.setattr(worker, "_group_read_tables", lambda events, rules: set())


def test_a_line_on_a_running_lines_tables_is_not_given_whatever_its_kind(monkeypatch):
    from chain import slots
    _touching(monkeypatch)

    lines = [_line("a", ["t"]), _line("b", ["t"]), _line("c", ["u"]), _line("d", ["t", "v"], run=True)]
    assert [l["line"] for l in slots.lines_to_give(lines, [], behind={"t"})[0]] == ["c"]
    assert slots.lines_to_give(lines, [], behind={"t"})[1] == 3, "held back for t - read again when a batch ends"
    lines = [_line("a", ["t"]), _line("b", ["t"]), _line("c", ["u"])]
    assert [l["line"] for l in slots.lines_to_give(lines, [], behind=())[0]] == ["a", "c"], \
        "two collapsed lines on one table given side by side - one slot waits on the other's lock"
    lines = [_line("a", ["t"], orders=True), _line("b", ["t"]), _line("c", ["u"])]
    assert [l["line"] for l in slots.lines_to_give(lines, [], skip={"a"})[0]] == ["c"], \
        "an unfinished row-by-row line ahead still holds a later one back"


def test_between_batches_only_an_ordering_line_holds_its_tables(monkeypatch):
    from chain import slots
    _touching(monkeypatch)
    pool = slots.SlotPool(spawn=lambda index: None)
    held = {1: (["t"], False, True), 2: (["u"], True, True), 3: (["v"], False, False)}
    for index, (touches, orders, ready) in held.items():
        pool.slots[index] = SimpleNamespace(line={"line": "s%d" % index, "run": False, "orders": orders,
                                                  "touches": touches}, ready=ready)
    monkeypatch.setattr("chain.queue_lines.waiting_lines",
                        lambda db, cap: [SimpleNamespace(key=k, run=None) for k in ("p", "q", "r")])
    monkeypatch.setattr(slots, "line_of", lambda db, line: _line(line.key, {"p": ["t"], "q": ["u"], "r": ["v"]}[line.key]))
    assert [l["line"] for l in pool._givable(None, [], set(), 3)[0]] == ["p"], \
        "t's line is between batches (a replay's), u's orders, v's runs a batch"
