# -*- coding: utf-8 -*-
"""Retroactive runs block each other by where they write, not by being two runs (lead 11-10 ㄱ).

`retroactive.writes(op, params)` answers each run's places from its operation's `writes` cell and the declarations;
two runs overlap when they share a place, and a place not answered is everywhere. The declarations are fed a small
graph here - the answerers are the product's (`replay.find_rule`, `chain_bindings.rule_tables`, `graph._wakes`,
`_ledger_world`), only what they read is set:

    rule a   writes t1        wakes on t0 (any write)
    rule b   writes t2        wakes on t9
    rule c   writes t3        wakes on t1, chain writes too (`allow_chain_trigger`)
    enrich e derives t1       (`enrichment.backfill.load_rule`); enrich f derives t2
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from admin import retroactive                                                    # noqa: E402

RULES = {"a": {"name": "a", "writes": {"t1"}, "on": "t0", "chain": False},
         "b": {"name": "b", "writes": {"t2"}, "on": "t9", "chain": False},
         "c": {"name": "c", "writes": {"t3"}, "on": "t1", "chain": True}}


@pytest.fixture(autouse=True)
def declarations(monkeypatch):
    from chain import graph, replay

    import chain_bindings

    def find_rule(name, row_scoped=False):
        if name not in RULES:
            raise retroactive.RetroactiveRefused("no rule %s" % name)
        return RULES[name]

    def wakes(worker, rules, table):
        return {"user": sorted(r["name"] for r in rules if r["on"] == table),
                "chain": sorted(r["name"] for r in rules if r["on"] == table and r["chain"])}

    monkeypatch.setattr(replay, "find_rule", find_rule)
    monkeypatch.setattr(chain_bindings, "rule_tables", lambda rule, role: set((rule or {}).get("writes", ())))
    monkeypatch.setattr(graph, "_chain_rules", lambda: list(RULES.values()))
    monkeypatch.setattr(graph, "_wakes", wakes)
    monkeypatch.setattr(retroactive, "_ledger_world", lambda params: params.get("world") or "w1")

    from chain import enrichment

    def load_rule(name, known_tables, force_disabled=False):
        if name not in ENRICH:
            raise retroactive.RetroactiveRefused("no enrich rule %s" % name)
        return {"name": name, "derived_table": ENRICH[name]}

    monkeypatch.setattr(enrichment.backfill, "load_rule", load_rule)


ENRICH = {"e": "t1", "f": "t2"}


REPLAY, REREAD, ENRICH_OP, FOLD = "chain_replay", retroactive.FILE_REREAD_OP, "enrichment_backfill", \
    "fold_written_notation"


@pytest.mark.parametrize("op, params, places", [
    (REPLAY, {"rule": "a"}, {"table:t1"}),
    (REPLAY, {"rule": "a", "cascade": True}, {"table:t1", "table:t3"}),    # t1 wakes c (opted in)
    (REPLAY, {"rule": "b", "cascade": True}, {"table:t2"}),                # t2 wakes nothing
    (REPLAY, {"rule": "nope"}, {retroactive.EVERYWHERE}),                  # a name not answered
    (REREAD, {"table": "t0"}, {"table:t0", "table:t1", "table:t3"}),       # t0 wakes a, its t1 wakes c
    (REREAD, {"table": "t9"}, {"table:t9", "table:t2"}),
    (REREAD, {"table": " "}, {retroactive.EVERYWHERE}),                    # no table named
    ("ledger_backfill", {}, {"ledger:w1"}),
    ("ledger_catch_up", {"world": "w2"}, {"ledger:w2"}),
    ("ledger_rescope", {"world": "w1"}, {"ledger:w1"}),
    (ENRICH_OP, {"rule": "e"}, {"table:t1", "table:t3"}),                 # a chain-layer write: t1 wakes c
    (ENRICH_OP, {"rule": "f"}, {"table:t2"}),
    (ENRICH_OP, {"rule": "nope"}, {retroactive.EVERYWHERE}),
    (FOLD, {"table": "t0"}, {"table:t0", "table:t1", "table:t3"}),
    (FOLD, {"table": "t9", "row_ids": ["r1"]}, {"table:t9", "table:t2"}),
    ("withdraw", {"table": "t1"}, {retroactive.EVERYWHERE}),               # no `writes` cell - everywhere
    ("not_an_op", {}, {retroactive.EVERYWHERE}),
])
def test_where_each_run_writes(op, params, places):
    assert retroactive.writes(op, params) == places


#: op × op - every pair asked both ways; an empty cell is asserted «apart», not left out.
PAIRS = [
    (("ledger_backfill", {}), (REPLAY, {"rule": "a"}), False),
    (("ledger_backfill", {}), ("ledger_rescope", {}), True),
    (("ledger_backfill", {"world": "w1"}), ("ledger_catch_up", {"world": "w2"}), False),
    ((REPLAY, {"rule": "a"}), (REPLAY, {"rule": "a"}), True),
    ((REPLAY, {"rule": "a"}), (REPLAY, {"rule": "b"}), False),
    ((REPLAY, {"rule": "a", "cascade": True}), (REREAD, {"table": "t3"}), True),     # meets only through c
    ((REPLAY, {"rule": "a"}), (REREAD, {"table": "t3"}), False),
    ((REREAD, {"table": "t0"}), (REPLAY, {"rule": "b", "cascade": True}), False),
    ((REREAD, {"table": "t0"}), (REREAD, {"table": "t1"}), True),
    (("withdraw", {"table": "t1"}), ("ledger_backfill", {}), True),                   # everywhere meets all
    (("withdraw", {"table": "t1"}), (REPLAY, {"rule": "b"}), True),
    ((REPLAY, {"rule": "nope"}), (REPLAY, {"rule": "b"}), True),
    # the owner's pair (lead 11-10 «백필이랑 체인 리플레이 서로 안 세우게»)
    ((ENRICH_OP, {"rule": "f"}), (REPLAY, {"rule": "a"}), False),
    ((ENRICH_OP, {"rule": "e"}), (REPLAY, {"rule": "a"}), True),
    ((ENRICH_OP, {"rule": "f"}), ("ledger_backfill", {}), False),
    ((FOLD, {"table": "t9"}), (REPLAY, {"rule": "a"}), False),
    ((FOLD, {"table": "t0"}), (REPLAY, {"rule": "a"}), True),
]


@pytest.mark.parametrize("one, other, meets", PAIRS)
def test_two_runs_meet_where_they_both_write(one, other, meets):
    mine, theirs = retroactive.writes(*one), retroactive.writes(*other)
    assert bool(retroactive.overlap(mine, theirs)) is meets
    assert bool(retroactive.overlap(theirs, mine)) is meets


class _Runs:
    """`retroactive_runs` holding the given rows in flight, newest first."""

    def __init__(self, rows):
        self.rows = rows

    def query(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def all(self):
        return list(self.rows)


def _running(run_id, op, params):
    import json
    from datetime import datetime, timezone
    from types import SimpleNamespace

    now = datetime.now(timezone.utc)
    return SimpleNamespace(run_id=run_id, op=op, state=retroactive.RUN_RUNNING, params=json.dumps(params),
                           requested_by=None, queued_at=now, started_at=now, last_progress_at=now, runner=None,
                           processed_rows=0, total_rows=None)


@pytest.mark.parametrize("op, params, closed_on", [
    (REPLAY, {"rule": "b"}, None),                       # writes apart from both - runs beside them
    (REPLAY, {"rule": "a"}, "replay-a"),                 # newest first: the replay of a, not the backfill
    ("ledger_rescope", {}, "backfill"),
    ("withdraw", {"table": "t2"}, "replay-a"),           # everywhere: the newest run in flight
])
def test_the_gate_is_closed_on_the_newest_run_it_meets(op, params, closed_on):
    db = _Runs([_running("replay-a", REPLAY, {"rule": "a"}), _running("backfill", "ledger_backfill", {})])
    got = retroactive.in_flight(db, op=op, params=params)
    assert (got and got["run_id"]) == closed_on
    said = retroactive.gate_refusal(db, op, params) if closed_on else None
    if closed_on:
        assert ("run_id=%s" % closed_on) in said and "both write" in said


def test_the_pace_help_says_runs_wait_by_place_not_one_at_a_time():
    """The operations list carries the pace help the admin Help quotes (lead 11-11): the gate's rule, not «one at a
    time»."""
    helps = [p["help"] for s in retroactive.inventory() for p in s["params"] if p["name"] == "pace"]
    assert len(helps) > 1, "canary: pace-taking operations are listed"
    assert all("same places" in h and "one at a time" not in h.lower() for h in helps)
