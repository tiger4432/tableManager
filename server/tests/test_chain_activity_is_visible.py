# -*- coding: utf-8 -*-
""""Is a mapper in flight right now" has to be answerable, and answerable honestly.

The outbox answers what is WAITING. It cannot tell "picked it up and never finished"
apart from "picked nothing up" - both leave the same waiting count - and that is the
shape of the owner's report on 2026-09-04: rows waiting, no error anywhere, and nothing
that said whether work was in progress.

⛔ AND AN EMPTY LIST MUST NOT BE ABLE TO MEAN TWO THINGS. The registry lives in the
process that runs the loop; run the worker separately and the API serves an empty list
while mappers run elsewhere. `attached` is what keeps that from reading as "idle".
"""
import logging
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_activity                                            # noqa: E402
import chain_ingestion_worker as worker                          # noqa: E402

RULE = {"name": "some_rule", "target_table": "some_target"}


@pytest.fixture(autouse=True)
def clean_registry():
    chain_activity.registry.clear()
    yield
    chain_activity.registry.clear()


def install(monkeypatch, fn, name="activity_probe_module"):
    module = types.ModuleType(name)
    module.run = fn
    monkeypatch.setitem(sys.modules, name, module)
    return name, "run"


def payloads(n):
    return [{"row_id": "r%d" % i, "data": {}} for i in range(n)]


# ------------------------------------------------------------------ in flight

def test_a_running_mapper_is_visible_while_it_runs(monkeypatch):
    """Observed from INSIDE the mapper - the only moment the entry is supposed to exist."""
    seen = {}

    def slow(db, p):
        seen["snapshot"] = chain_activity.registry.snapshot()
        return {"updates": []}

    mod, fn = install(monkeypatch, slow)
    worker.execute_custom_mapper(mod, fn, None, payloads(3), rule=RULE)

    assert len(seen["snapshot"]) == 1
    entry = seen["snapshot"][0]
    assert entry["rule"] == "some_rule"
    assert entry["target_table"] == "some_target"
    assert entry["mapper"].endswith(".run")
    assert entry["rows_in"] == 3
    assert entry["running_seconds"] >= 0


def test_the_entry_is_gone_once_the_mapper_returns(monkeypatch):
    mod, fn = install(monkeypatch, lambda db, p: {"updates": []})
    worker.execute_custom_mapper(mod, fn, None, payloads(1), rule=RULE)
    assert chain_activity.registry.snapshot() == []


def test_a_mapper_that_throws_does_not_leave_itself_running(monkeypatch):
    """🔴 THE LEAK THAT WOULD MATTER. An entry left behind by a raising mapper says a
    mapper is still running, forever - and "the chain is stuck" is precisely the false
    reading this instrument exists to prevent."""
    def boom(db, p):
        raise ValueError("refused")

    mod, fn = install(monkeypatch, boom)
    with pytest.raises(ValueError):
        worker.execute_custom_mapper(mod, fn, None, payloads(2), rule=RULE)
    assert chain_activity.registry.snapshot() == [], "the throw left an entry in flight"


def test_two_mappers_in_flight_are_two_entries(monkeypatch):
    """Concurrency is real here - the loop runs rules within a group one after another,
    but nothing in the registry may assume a single slot."""
    reg = chain_activity.registry
    a = reg.start("rule_a", "m.a", "t_a", 1)
    b = reg.start("rule_b", "m.b", "t_b", 2)
    assert [e["rule"] for e in reg.snapshot()] == ["rule_a", "rule_b"]
    reg.finish(a)
    assert [e["rule"] for e in reg.snapshot()] == ["rule_b"]
    reg.finish(b)
    assert reg.snapshot() == []
    reg.finish(b)                      # idempotent: a double finish is not an error


# ------------------------------------------------------------------ the empty list

def test_an_empty_list_is_not_the_same_answer_as_a_blind_one():
    """`attached` is False until this process's own chain loop starts. Without it,
    "no mapper is running" and "the loop is in another process" are one value."""
    reg = chain_activity.ChainActivityRegistry()
    assert reg.snapshot() == [] and reg.attached is False
    reg.attach()
    assert reg.snapshot() == [] and reg.attached is True


def test_the_loop_marks_itself_attached_when_it_starts(monkeypatch):
    """Driven through the real entry point rather than read out of its source.

    The loop is stopped one step past the flag by making the next thing it does - loading
    the rules - raise, so what is asserted is that entering the loop SETS the flag, not
    that a particular line appears in a file.
    """
    import asyncio

    class Stop(Exception):
        pass

    monkeypatch.setattr(worker.internal_event_client, "startup_lines",
                        lambda *a, **k: [])
    def refuse():
        raise Stop()
    monkeypatch.setattr(worker, "load_chain_rules", refuse)

    fresh = chain_activity.ChainActivityRegistry()
    monkeypatch.setattr(chain_activity, "registry", fresh)
    monkeypatch.setattr(worker.chain_activity, "registry", fresh)
    assert fresh.attached is False

    with pytest.raises(Stop):
        asyncio.run(worker.start_chain_ingestion_worker(None))
    assert fresh.attached is True, "entering the loop did not mark this process"
