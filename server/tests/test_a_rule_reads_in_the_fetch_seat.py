# -*- coding: utf-8 -*-
"""총괄 78eec1ec1 «데이터 받기» 안 1: what a rule's mapper reads is read by the fetch seat (`rule_run.prepare`) before any
rule of the group runs, and handed to the call as `fetched=` - so a built-in kind reads nothing while the rules run.

  built-in   join · decide · auto-confirm: rows land, and no «reads outside the fetch» line
  file       a mapper that reads in its call: the line, once a rule (the canary - the line is not dead)
  order      every rule of a group fetched before the first one is called
  per row    a per-row rule fetched a row at a time, each call handed its own
  failed     a read that raises fails the group under the rule's name
"""
import logging

import pytest

import mapper_sdk
from chain import rule_run, rule_shape
from database import crud, models
from test_every_declared_kind_runs_and_leaves_rows import (  # noqa: F401 - the fixture is used
    DST, ROWS, SRC, _events, _run, _values, fixture_db)

LINE = "reads outside the fetch"


@pytest.fixture(autouse=True)
def _said_afresh(monkeypatch, caplog):
    monkeypatch.setattr(rule_run, "_SAID_READING", set())
    caplog.set_level(logging.INFO)


def _said(caplog):
    return [r.getMessage() for r in caplog.records if LINE in r.getMessage()]


def _register(monkeypatch, name, call, fetch=None):
    if fetch is not None:
        call.fetch = fetch
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, name, call)
    return {"name": name, "enabled": True, "is_batch": True, "trigger_table": SRC, "target_table": SRC,
            "mapper": name}


def test_a_join_reads_nothing_in_its_call(db, caplog):
    rules = rule_shape.expand_declaration(
        {"name": "fetch_join", "on": {"table": DST}, "into": {"table": SRC},
         "derive": {"kind": "join", "join": {
             "on": [{"left": "job", "right": "job"}], "take": [{"from": "lot", "into": "lot_confirmed"}]}}},
        crud.TABLE_CONFIG)[0]
    _run(db, "join", rules, SRC)
    assert _values(db, SRC, "lot_confirmed") == ["LOT"] * ROWS
    assert _said(caplog) == []


def test_a_decide_and_its_auto_confirm_read_nothing_in_their_calls(db, caplog):
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
    assert _said(caplog) == []


def test_a_mapper_that_reads_in_its_call_is_said_once(db, caplog, monkeypatch):
    def reads(db, payload, rule=None):
        db.query(models.DYNAMIC_TABLES[SRC]).count()
        return {"updates": []}

    rule = _register(monkeypatch, "fetch_reads", reads)
    _run(db, "reads-1", [rule], SRC)
    _run(db, "reads-2", [rule], SRC)
    assert len(_said(caplog)) == 1 and "rule=fetch_reads" in _said(caplog)[0]


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
    from chain import ingestion_worker as worker

    def fetch(db, payload, rule=None):
        raise RuntimeError("the read broke")

    rule = _register(monkeypatch, "fetch_broken", lambda db, payload, rule=None, fetched=None: {"updates": []}, fetch)
    ok, why, _ = worker._process_chain_transaction_group_sync("tx-broken", _events(db, SRC), db, [rule])
    assert ok is False and "fetch_broken" in why and "the read broke" in why
