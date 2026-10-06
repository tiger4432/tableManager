# -*- coding: utf-8 -*-
"""총괄 be0abe305 ② ③ — a rule cell says WHEN a rule runs, never HOW.

  run_in absent       the group that woke it runs it (today)
  run_in operation    the group queues runs of `rows_per_run` rows and goes on; each run calls
                      the same group body - same mapper call, retraction, write, failure sentence

Measured before (b5b335f2e ③): a 10 s-per-text mapper held the next table's group 20.03 s.
"""
import ast
import asyncio
import inspect
import json
import os
import sys
import textwrap
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import chain_bindings                                                 # noqa: E402
import event_constants                                                # noqa: E402
import mapper_sdk                                                     # noqa: E402
import paths                                                          # noqa: E402
from admin import retroactive                                         # noqa: E402
from chain import activity                                            # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from chain import replay                                              # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from database.context import channel, outbox_mode                     # noqa: E402
from database.database import Base                                    # noqa: E402
from utils import heartbeat                                           # noqa: E402
from utils.payload_helper import get_payload_dict                     # noqa: E402
from test_a_yes_no_cell_holds_true_or_false import (                  # noqa: E402,F401
    UNIFIED, fixture_rules_file, fixture_tables)

TABLES = {name: {"business_key": "k", "composite_key_source": ["k"],
                 "column_types": {"k": "string", "n": "string"}, "display_columns": ["k", "n"]}
          for name in ("q_txt", "q_cand", "q_oa", "q_ob")}
SLEEP = 1.0
MAPPERS = """
import time

def _rows(payload):
    handed = payload if isinstance(payload, list) else [payload]
    for p in handed:
        data = p.get("data") or {}
        yield (data.get("k") or {}).get("value"), (data.get("n") or {}).get("value")

def slow(db, payload, rule=None):
    out = []
    for k, n in _rows(payload):
        time.sleep(%r)
        out.append({"business_key_val": k, "updates": {"k": k, "n": "from " + str(n)}})
    return {"updates": out}

def fast(db, payload, rule=None):
    return {"updates": [{"business_key_val": k, "updates": {"k": k, "n": "from " + str(n)}}
                        for k, n in _rows(payload)]}

def broken(db, payload, rule=None):
    raise ValueError("this mapper cannot read the text")

def loud(db, payload, rule=None):
    raise ValueError("x" * 6000 + ' "quoted" end')

def picky(db, payload, rule=None):
    rows = list(_rows(payload))
    if any(n == "two" for _k, n in rows):
        raise ValueError("this mapper cannot read text two")
    return fast(db, payload, rule)
""" % SLEEP


class _NoClose:
    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


async def _no_post(_endpoint, _payload):
    return True


@pytest.fixture(name="db")
def fixture_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path / "beats"))
    monkeypatch.setattr(heartbeat, "heartbeat_path",
                        lambda name: str(tmp_path / "beats" / (name + ".json")))
    monkeypatch.setattr(heartbeat, "HEARTBEAT_SLICE_SECONDS", 0.2)
    monkeypatch.setattr(retroactive, "_send_broadcasts", lambda messages: None)
    monkeypatch.setattr(worker, "post_event_async", _no_post)
    mapper_sdk.discover()
    (tmp_path / "q_maps.py").write_text(textwrap.dedent(MAPPERS), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("q_maps", None)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    monkeypatch.setattr("database.database.SessionLocal", lambda: _NoClose(session))
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)
        sys.modules.pop("q_maps", None)


def _rule(name, trigger, target, function, **cells):
    return {"name": name, "enabled": True, "is_batch": True, "trigger_table": trigger,
            "target_table": target, "mapper_module": "q_maps", "mapper_function": function,
            "allow_chain_trigger": False, **cells}


def _write(db, table, rows):
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_PER_ROW):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="q")
            for row in rows]))
        db.commit()


def _drain(db, rules, monkeypatch):
    """`process_pending_groups` over what is pending, the real body under it; -> {table: (start,
    end)} seconds from the call."""
    pending = (db.query(models.DatabaseOutbox)
               .filter(models.DatabaseOutbox.processed_chain.is_(False),
                       models.DatabaseOutbox.table_name.in_(list(TABLES)))
               .order_by(models.DatabaseOutbox.id).all())
    order, groups = [], {}
    for event in pending:
        tx = get_payload_dict(event).get("transaction_id")
        if tx not in groups:
            order.append(tx)
        groups.setdefault(tx, []).append(event)
    monkeypatch.setattr(replay, "load_rules", lambda: list(rules))
    real, spans, t0 = worker._process_chain_transaction_group_sync, {}, time.monotonic()

    def timed(tx_id, events, session, rules_here):
        start = time.monotonic() - t0
        try:
            return real(tx_id, events, session, rules_here)
        finally:
            spans[",".join(sorted({e.table_name for e in events}))] = (
                start, time.monotonic() - t0)
    worker._process_chain_transaction_group_sync = timed
    try:
        assert not asyncio.run(worker.process_pending_groups(db, order, groups, rules, None))
    finally:
        worker._process_chain_transaction_group_sync = real
    return spans


def _queued(db):
    runs = (db.query(models.RetroactiveRun)
            .filter(models.RetroactiveRun.op == retroactive.RULE_ROWS_OP)
            .all())
    return [retroactive.validate(retroactive.RULE_ROWS_OP, json.loads(run.params)) for run in runs]


def _run_queued(db):
    """Each queued run, under the channel every operation runs under (`run_here`)."""
    with channel(event_constants.CHANNEL_RETROACTIVE):
        for params in _queued(db):
            retroactive._run_rule_rows(db, params, log=lambda *_a, **_k: None)


def _values(db, table):
    return sorted((r.k, r.n) for r in db.query(models.DYNAMIC_TABLES[table]).all())


TEXTS = [{"k": "t1", "n": "one"}, {"k": "t2", "n": "two"}]


def test_a_rule_run_as_an_operation_holds_no_other_group(db, monkeypatch):
    rules = [_rule("q_slow", "q_txt", "q_cand", "slow", run_in="operation"),
             _rule("q_fast", "q_oa", "q_ob", "fast")]
    _write(db, "q_txt", TEXTS)
    _write(db, "q_oa", [{"k": "a1", "n": "other"}])
    spans = _drain(db, rules, monkeypatch)
    assert spans["q_oa"][0] < SLEEP, spans          # was 2 x SLEEP behind the slow mapper
    assert _values(db, "q_ob") == [("a1", "from other")]
    assert _values(db, "q_cand") == [], "queued, not run in the group"
    assert [len(p["rows"]) for p in _queued(db)] == [2]
    _run_queued(db)
    assert _values(db, "q_cand") == [("t1", "from one"), ("t2", "from two")]


def test_the_rule_says_it_was_handed_to_an_operation(db, monkeypatch):
    """Not 「did not run」 - it runs as these runs (총괄 92d0483e5)."""
    _write(db, "q_txt", TEXTS)
    _drain(db, [_rule("q_handed", "q_txt", "q_cand", "fast", run_in="operation")], monkeypatch)
    said = activity.registry.outcomes()["q_handed"]
    (run,) = db.query(models.RetroactiveRun).filter(
        models.RetroactiveRun.op == retroactive.RULE_ROWS_OP).all()
    assert (said["outcome"], said["reason"]) == (
        event_constants.RULE_OUTCOME_QUEUED_AS_OPERATION, "run_id %s" % run.run_id)


def test_the_chain_and_the_operation_write_the_same_rows(db, monkeypatch):
    """One write wakes both: the same mapper into two targets, one each way."""
    rules = [_rule("q_in_chain", "q_txt", "q_cand", "fast"),
             _rule("q_queued", "q_txt", "q_ob", "fast", run_in="operation")]
    _write(db, "q_txt", TEXTS)
    _drain(db, rules, monkeypatch)
    assert _values(db, "q_ob") == []
    _run_queued(db)
    assert _values(db, "q_cand") and _values(db, "q_ob") == _values(db, "q_cand")
    channels = {table: {event_constants.channel_of(get_payload_dict(e))
                        for e in db.query(models.DatabaseOutbox)
                        .filter(models.DatabaseOutbox.table_name == table).all()}
                for table in ("q_cand", "q_ob")}
    assert channels["q_ob"] == channels["q_cand"] == {event_constants.CHANNEL_CHAIN}, (
        "the run's write wakes downstream exactly as the chain's own write does")


def test_a_run_carries_rows_per_run_rows(db, monkeypatch):
    rules = [_rule("q_split", "q_txt", "q_cand", "fast", run_in="operation", rows_per_run=2)]
    _write(db, "q_txt", TEXTS + [{"k": "t3", "n": "three"}])
    _drain(db, rules, monkeypatch)
    assert sorted(len(p["rows"]) for p in _queued(db)) == [1, 2]
    _run_queued(db)
    assert [k for k, _n in _values(db, "q_cand")] == ["t1", "t2", "t3"]


def test_one_event_naming_many_rows_is_split_by_rows(db, monkeypatch):
    """A collapsed event names its rows; each run hands the body only its own."""
    rules = [_rule("q_bulk", "q_txt", "q_cand", "fast", run_in="operation", rows_per_run=2)]
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, "q_txt", schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="q")
            for row in TEXTS + [{"k": "t3", "n": "three"}]]))
        db.commit()
    _drain(db, rules, monkeypatch)
    handed, real = [], worker._process_chain_transaction_group_sync

    def body(tx_id, events, session, rules_here):
        handed.append(sum(len(get_payload_dict(e).get("row_ids") or ()) for e in events))
        return real(tx_id, events, session, rules_here)
    monkeypatch.setattr(worker, "_process_chain_transaction_group_sync", body)
    _run_queued(db)
    assert sorted(handed) == [1, 2]
    assert [k for k, _n in _values(db, "q_cand")] == ["t1", "t2", "t3"]


def test_a_failed_run_says_what_the_group_body_says(db, monkeypatch):
    rules = [_rule("q_broken", "q_txt", "q_cand", "broken", run_in="operation")]
    _write(db, "q_txt", TEXTS[:1])
    _drain(db, rules, monkeypatch)
    (params,) = _queued(db)
    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        retroactive._run_rule_rows(db, params, log=lambda *_a, **_k: None)
    record = json.loads(str(refused.value))
    assert set(record) == {"failed_at", "reason", "rules", "tables", "rows", "row"}, (
        "the chain's failure record (`_failure_record`)")
    assert "q_broken" in record["reason"] and "this mapper cannot read the text" in record["reason"]
    assert record["rows"] == 1
    assert _values(db, "q_cand") == []


def test_a_long_failure_record_stays_whole_json_on_the_run_row(db, monkeypatch):
    """총괄 ff60fe669 ①: the row keeps `RUN_ERROR_LIMIT` characters - the reason gives way."""
    rules = [_rule("q_loud", "q_txt", "q_cand", "loud", run_in="operation")]
    _write(db, "q_txt", TEXTS[:1])
    _drain(db, rules, monkeypatch)
    (run,) = (db.query(models.RetroactiveRun)
              .filter(models.RetroactiveRun.op == retroactive.RULE_ROWS_OP).all())
    params = retroactive.validate(retroactive.RULE_ROWS_OP, json.loads(run.params))
    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        retroactive._run_rule_rows(db, params, log=lambda *_a, **_k: None)
    retroactive._mark_run(run.run_id, state=retroactive.RUN_FAILED, finished=True,
                          error=str(refused.value))
    db.expire_all()
    error = (db.query(models.RetroactiveRun.error)
             .filter(models.RetroactiveRun.run_id == run.run_id).scalar())
    record = json.loads(error)
    assert set(record) == {"failed_at", "reason", "rules", "tables", "rows", "row"}
    assert len(error) == retroactive.RUN_ERROR_LIMIT, (
        "the cut middle must be plain 'x', or this gate stops seeing one character")
    head, tail = record["reason"].split("…")
    assert "q_loud" in head and tail.rstrip().endswith('x "quoted" end')


def test_one_text_per_run_fails_only_that_text(db, monkeypatch):
    """총괄 cb522d1f2: the unit is one text from the start - nothing re-runs to find it."""
    rules = [_rule("q_one", "q_txt", "q_cand", "picky", run_in="operation", rows_per_run=1)]
    _write(db, "q_txt", TEXTS)
    _drain(db, rules, monkeypatch)
    failed = []
    for params in _queued(db):
        try:
            retroactive._run_rule_rows(db, params, log=lambda *_a, **_k: None)
        except retroactive.RetroactiveRefused as refused:
            failed.append(json.loads(str(refused))["rows"])
    assert failed == [1]
    assert _values(db, "q_cand") == [("t1", "from one")]


def test_a_failed_group_queues_nothing(db, monkeypatch):
    rules = [_rule("q_later", "q_txt", "q_cand", "fast", run_in="operation"),
             _rule("q_now", "q_txt", "q_ob", "broken")]
    monkeypatch.setattr(replay, "load_rules", lambda: list(rules))
    _write(db, "q_txt", TEXTS[:1])
    pending = (db.query(models.DatabaseOutbox)
               .filter(models.DatabaseOutbox.processed_chain.is_(False),
                       models.DatabaseOutbox.table_name == "q_txt").all())
    tx = get_payload_dict(pending[0]).get("transaction_id")
    ok, _error, _messages = worker._claimed_group_sync(tx, pending, db, rules)
    assert not ok and _queued(db) == []


def test_both_paths_call_the_one_group_body():
    """The cell decides WHEN; HOW is one function (총괄 be0abe305 ②)."""
    def calls(function):
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        return {node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
                for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, (ast.Attribute, ast.Name))}
    body = worker._process_chain_transaction_group_sync.__name__
    assert body in calls(worker._claimed_group_sync)
    assert body in calls(retroactive._run_rule_rows)


@pytest.mark.parametrize("cells,code", [
    ({"run_in": "later"}, "bad_run_in"),
    ({"rows_per_run": 0}, "bad_rows_per_run"),
    ({"rows_per_run": "6"}, "bad_rows_per_run"),
])
def test_a_bad_cell_is_refused_at_load(cells, code):
    issues = chain_bindings.rule_refusals(
        _rule("q", "q_txt", "q_cand", "fast", **cells), "rules[0]",
        mapper_resolvable=lambda _name: True, derived_tables=())
    assert code in {issue.code for issue in issues}


def _run_in_nodes(node):
    """Every node the skeleton gives the `run_in` cell, under whichever root carries it."""
    if isinstance(node, dict):
        if node.get("key") == chain_bindings.RUN_IN_KEY:
            yield node["node"]
        for value in node.values():
            yield from _run_in_nodes(value)
    elif isinstance(node, list):
        for value in node:
            yield from _run_in_nodes(value)


def test_the_form_picks_run_in_from_the_list_the_chain_payload_carries(rules_file):
    """총괄 ff60fe669 ②: one closed leaf in both grammars; the payload carries its members."""
    from ledger import admin

    nodes = list(_run_in_nodes(chain_bindings.skeleton()))
    assert len(nodes) == 2, "the flat root and the unified `limits`"
    assert all(node == {"kind": "leaf", "hint": "choice", "list": "run_in"} for node in nodes)
    assert admin.chain_rule_raw_view()["run_in"] == ["chain", "operation"]


def test_a_typo_in_run_in_is_refused_before_it_is_saved(rules_file):
    from ledger import admin

    path = rules_file([])
    base = admin.file_fingerprint(str(path))
    with pytest.raises(Exception) as raised:
        admin.save_chain_rule_raw("q_typo", dict(UNIFIED, name="q_typo",
                                                 limits={"run_in": "operaton"}), base)
    assert raised.value.detail["code"] == "bad_run_in"
    assert "run_in must be one of chain, operation, got 'operaton'" in json.dumps(
        raised.value.detail)
    assert json.loads(path.read_text(encoding="utf-8")) == {"rules": []}
    admin.save_chain_rule_raw("q_ok", dict(UNIFIED, name="q_ok", limits={"run_in": "operation"}),
                              base)


def test_the_cells_are_one_spelling():
    assert (chain_bindings.RUN_IN_KEY, chain_bindings.ROWS_PER_RUN_KEY) == ("run_in", "rows_per_run")
    assert {"run_in", "rows_per_run"} <= set(chain_bindings.RULE_ROUTING_OPTIONAL)
    assert worker.rows_per_run({}) == chain_bindings.DEFAULT_ROWS_PER_RUN
    assert not worker.runs_as_operation({}) and not worker.runs_as_operation({"run_in": "chain"})
