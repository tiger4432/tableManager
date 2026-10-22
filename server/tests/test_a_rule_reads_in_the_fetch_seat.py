# -*- coding: utf-8 -*-
"""총괄 78eec1ec1 «데이터 받기» 안 1: what a rule's mapper reads is read by the fetch seat (`rule_run.prepare`) before any
rule of the group runs, and handed to the call as `fetched=` - so a built-in kind reads nothing while the rules run.

  built-in   join · decide · auto-confirm: rows land, and no «reads outside the fetch» line
  file       a mapper that reads in its call: the line, once a rule (the canary - the line is not dead)
  order      every rule of a group fetched before the first one is called
  per row    a per-row rule fetched a row at a time, each call handed its own
  failed     a read that raises fails the group under the rule's name
  group_by   a group_by rule handed every row of each key a handed row is in or left (소유자 10-22)
"""
import logging

import pytest

import mapper_sdk
from chain import ingestion_worker as worker, rule_run, rule_shape
from database import crud, models
from test_every_declared_kind_runs_and_leaves_rows import (  # noqa: F401 - the fixture is used
    DST, ROWS, SRC, _events, _run, _values, fixture_db)

LINE = "reads outside the fetch"


@pytest.fixture(autouse=True)
def _said_afresh(monkeypatch, caplog):
    monkeypatch.setattr(rule_run, "_SAID_READING", set())
    rule_run.count_reads()
    caplog.set_level(logging.INFO)


@pytest.fixture(name="in_the_run")
def fixture_in_the_run(monkeypatch):
    """The SELECTs run while `run_rule` runs - the contract board's R (C 10-22): what is read after the fetch seat."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    counted, inside = [], [False]
    real = rule_run.run_rule

    def run_rule(*a, **k):
        inside[0] = True
        try:
            return real(*a, **k)
        finally:
            inside[0] = False

    def count(conn, cursor, statement, parameters, context, executemany):
        if inside[0] and statement.lstrip().upper().startswith(("SELECT", "WITH")):
            counted.append(statement)

    monkeypatch.setattr(rule_run, "run_rule", run_rule)
    event.listen(Engine, "before_cursor_execute", count)
    yield counted
    event.remove(Engine, "before_cursor_execute", count)


def _said(caplog):
    return [r.getMessage() for r in caplog.records if LINE in r.getMessage()]


def _register(monkeypatch, name, call, fetch=None):
    if fetch is not None:
        call.fetch = fetch
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, name, call)
    return {"name": name, "enabled": True, "is_batch": True, "trigger_table": SRC, "target_table": SRC,
            "mapper": name}


def test_a_join_reads_nothing_in_its_call(db, caplog, in_the_run):
    rules = rule_shape.expand_declaration(
        {"name": "fetch_join", "on": {"table": DST}, "into": {"table": SRC},
         "derive": {"kind": "join", "join": {
             "on": [{"left": "job", "right": "job"}], "take": [{"from": "lot", "into": "lot_confirmed"}]}}},
        crud.TABLE_CONFIG)[0]
    _run(db, "join", rules, SRC)
    assert _values(db, SRC, "lot_confirmed") == ["LOT"] * ROWS
    assert _said(caplog) == [] and in_the_run == []


def test_a_decide_and_its_auto_confirm_read_nothing_in_their_calls(db, caplog, in_the_run):
    rules = rule_shape.expand_declaration(
        {"name": "fetch_confirm", "on": {"table": SRC}, "into": {"table": DST},
         "derive": {"kind": "decide", "decide": {
             "key": ["job"], "fields": ["grade"], "auto_confirm": True,
             "reference_views": [{"label": "c", "query": "SELECT lot AS grade FROM %s WHERE job = :job" % DST,
                                  "candidate_for": {"grade": "grade"}}]}}},
        crud.TABLE_CONFIG)[0]
    dedup = [r for r in rules if r["name"].startswith("enrichment_dedup:")][0]
    confirm = [r for r in rules if r["name"].startswith("enrichment_auto_confirm:")][0]
    _run(db, "dedup", [dedup], SRC)
    _run(db, "confirm", [confirm], DST)
    assert _values(db, DST, "grade") == ["LOT"]
    assert _said(caplog) == [] and in_the_run == []


def test_a_mapper_that_reads_in_its_call_is_said_once(db, caplog, monkeypatch, in_the_run):
    def reads(db, payload, rule=None):
        db.query(models.DYNAMIC_TABLES[SRC]).count()
        return {"updates": []}

    rule = _register(monkeypatch, "fetch_reads", reads)
    _run(db, "reads-1", [rule], SRC)
    _run(db, "reads-2", [rule], SRC)
    assert len(_said(caplog)) == 1 and "rule=fetch_reads" in _said(caplog)[0]
    assert len(in_the_run) == 2                     # the canary: the count sees a read in the run


def test_every_rule_of_a_group_is_fetched_before_the_first_is_called(db, monkeypatch):
    seen = []

    def make(tag):
        def call(db, payload, rule=None, fetched=None):
            seen.append(("call", tag, fetched))
            return {"updates": []}
        return call, lambda db, payload, rule=None: seen.append(("fetch", tag, None)) or tag

    rules = [_register(monkeypatch, "fetch_order_%s" % tag, *make(tag)) for tag in "ab"]
    _run(db, "order", rules, SRC)
    assert seen == [("fetch", "a", None), ("fetch", "b", None), ("call", "a", "a"), ("call", "b", "b")]


def test_a_per_row_rule_is_fetched_a_row_at_a_time(db, monkeypatch):
    calls = []

    def call(db, payload, rule=None, fetched=None):
        calls.append((payload["row_id"], fetched))
        return {"updates": []}

    rule = dict(_register(monkeypatch, "fetch_per_row", call, lambda db, payload, rule=None: payload["row_id"]),
                is_batch=False)
    _run(db, "per-row", [rule], SRC)
    assert len(calls) == ROWS and all(row_id == fetched for row_id, fetched in calls)


def test_a_read_that_raises_fails_the_group_under_its_rule(db, monkeypatch):
    def fetch(db, payload, rule=None):
        raise RuntimeError("the read broke")

    rule = _register(monkeypatch, "fetch_broken", lambda db, payload, rule=None, fetched=None: {"updates": []}, fetch)
    ok, why, _ = worker._process_chain_transaction_group_sync("tx-broken", _events(db, SRC), db, [rule])
    assert ok is False and "fetch_broken" in why and "the read broke" in why


def _edit(db, key, **cells):
    from database import schemas

    model = models.DYNAMIC_TABLES[SRC]
    row_id = db.query(model.row_id).filter(model.log_key == key).scalar()
    crud.apply_batch_updates(db, SRC, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        row_id=row_id, updates=cells, source_name="user", updated_by="t")]))
    db.commit()


@pytest.mark.parametrize("seeded, edited, handed", [
    ({"LK": "K"}, ("L0", {"note": "x"}), ["L0", "L1", "L2"]),                    # the key whole, not K's
    ({"LK": "K"}, ("L0", {"job": "K"}), ["L0", "L1", "L2", "LK"]),               # the key it left and the key it joined
    ({"LB1": None, "LB2": "  "}, ("LB1", {"note": "x"}), ["LB1", "LB2"]),        # a blank key is a key
])
def test_a_group_by_rule_is_handed_its_keys_whole(db, monkeypatch, seeded, edited, handed):
    """소유자 10-22 「ㅇㅇ 넓혀」: a group_by rule is handed every row of each key a handed row is in or left."""
    from database import schemas

    crud.apply_batch_updates(db, SRC, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        updates={"log_key": key, "job": job}, source_name="seed", updated_by="t") for key, job in seeded.items()]))
    db.commit()
    _edit(db, edited[0], **edited[1])
    seen = []

    def call(db, payload, rule=None):
        seen.append(sorted((p.get("data") or {}).get("log_key", {}).get("value") for p in payload))
        return {"updates": []}

    rule = dict(_register(monkeypatch, "fetch_group_by", call), group_by=["job"])
    last = max(_events(db, SRC), key=lambda e: e.id)
    ok, _why, _ = worker._process_chain_transaction_group_sync("tx-key", [last], db, [rule])
    assert ok is True and seen == [handed]


def test_only_a_process_that_runs_rules_counts_their_reads(tmp_path):
    """총괄 10-22: the API's engines carry no hook; the chain worker's and a slot's warm-up attaches it."""
    import os
    import subprocess
    import sys

    probe = ("import main\n"
             "from sqlalchemy import event\n"
             "from sqlalchemy.engine import Engine\n"
             "from chain import ingestion_worker, rule_run\n"
             "print(event.contains(Engine, 'before_cursor_execute', rule_run._count_reads))\n"
             "ingestion_worker.warmup_worker([])\n"
             "print(event.contains(Engine, 'before_cursor_execute', rule_run._count_reads))\n")
    env = dict(os.environ, DATABASE_URL="sqlite:///%s" % (tmp_path / "probe.db").as_posix())
    env.pop("ASSY_ADMIN_TOKEN", None)
    out = subprocess.run([sys.executable, "-c", probe], cwd=os.path.dirname(os.path.dirname(__file__)), env=env,
                         capture_output=True, encoding="utf-8", errors="replace", timeout=180)
    said = [line.strip() for line in out.stdout.splitlines() if line.strip() in ("False", "True")]
    assert said == ["False", "True"], out.stdout[-500:] + out.stderr[-2000:]
