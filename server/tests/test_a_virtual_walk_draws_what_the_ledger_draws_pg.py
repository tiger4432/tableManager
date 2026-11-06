# -*- coding: utf-8 -*-
"""Lead 11-06 (owner «가상화로 걷는 모드 하나 만들어»): engine=virtual reads the declaration from its own tables; on a
ledger translated from those tables it draws the walk the stored ledger draws.

  the board   the sample's two sources (wafer -> recipe, a `one` predicate · lot slot -> wafer) on their tables,
              translated by the backfill into the stored ledger
  the cells   a walk · a time window · the old facts too (include_superseded) · walk-shadow's bins ·
              the key list · a continued walk refused · the stored answer carries no engine cell
"""
import json
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import paths                                                        # noqa: E402
from ledger import backfill, explorer, schema, trace, trace_router, walk_shadow  # noqa: E402
from ledger.setup import load_setup                                 # noqa: E402
from ledger_api import ledger_subgraph                              # noqa: E402
from test_ledger_worlds_are_independent_and_meet_in_a_walk import (  # noqa: E402,F401
    CHANGED, KEPT, _only, _write, fixture_config, fixture_world)

pytestmark = pytest.mark.pg
ROWS = [{"proc_id": "P1", "wafer_id": "W1", "step": "S1", "recipe_id": "RCP-1", "eventtime": "2026-09-30 10:00:00"},
        {"proc_id": "P2", "wafer_id": "W1", "step": "S2", "recipe_id": "RCP-2", "eventtime": "2026-09-30 11:00:00"},
        {"proc_id": "P3", "wafer_id": "W2", "step": "S1", "recipe_id": "RCP-1", "eventtime": "2026-09-30 10:00:00"},
        {"proc_id": "P4", "wafer_id": "W3", "recipe_id": "RCP-3", "eventtime": "2026-09-30 12:00:00"}]
SEATS = [{"lot_slot_wafer_key": "K1", "lot": "L1", "slot": "1", "wafer": "W1", "event_type": "load",
          "event_time": "2026-09-30 10:00:00"},
         {"lot_slot_wafer_key": "K2", "lot": "L1", "slot": "2", "wafer": "W2", "event_type": "load",
          "event_time": "2026-09-30 10:30:00"}]


@pytest.fixture(name="board")
def fixture_board(world):
    import notation_norm

    with world["engine"].begin() as conn:
        conn.connection.cursor().execute(notation_norm.key_instant_sql() + notation_norm.key_number_sql())
    with open(os.path.join(paths.config_path("ontology"), "ledger_config.json"), "w", encoding="utf-8") as fh:
        json.dump(_only(CHANGED, KEPT, one=True), fh)
    trace_router._COMPILED.clear()
    _write(world, "wafer_process", ROWS)
    _write(world, "lot_slot_wafer", SEATS)
    for source in (CHANGED, KEPT):
        backfill.run(world["engine"], source=source)
    return world


def _walk(board, engine, **asked):
    seeds = {"positive": [explorer.entity_id("lot_slot", {"lot": "L1", "slot": "1"}),
                          explorer.entity_id("wafer", {"wafer": "W3"})], "negative": []}
    with board["engine"].connect() as conn:
        return trace_router._evidence_graph(conn, node_id=seeds, hops=3, direction="both", node_limit=200,
                                            edge_limit=400, engine=engine, **asked)


def _drawn(payload):
    nodes = sorted(json.dumps({k: n.get(k) for k in ("id", "type", "keys", "attributes")}, sort_keys=True)
                   for n in payload["nodes"])
    edges = sorted(json.dumps({k: e.get(k) for k in ("id", "source", "target", "predicate", "qualifiers",
                                                      "occurred_at", "basis", "not_current", "worlds")},
                              sort_keys=True, default=str) for e in payload["edges"])
    return nodes, edges, payload.get("truncated")


@pytest.mark.parametrize("asked", [{}, {"since": "2026-09-30T01:30:00+00:00"}, {"include_superseded": True}],
                         ids=["walk", "since", "old facts too"])
def test_the_virtual_walk_draws_the_walk_the_ledger_draws(board, asked):
    stored, virtual = _walk(board, "stored", **asked), _walk(board, "virtual", **asked)
    assert _drawn(virtual) == _drawn(stored)
    assert len(stored["edges"]) >= (1 if asked.get("since") else 3), "canary: the walk crosses both sources"
    assert "engine" not in stored, "the stored answer is today's - no new cell"
    assert virtual["engine"] == {"name": "virtual", "left_out": [], "scans": virtual["engine"]["scans"]}
    assert {scan["table"] for scan in virtual["engine"]["scans"]} <= {"wafer_process", "lot_slot_wafer"}


def test_the_three_questions_are_three_answers(board):
    """Not vacuous: the window and the old facts change what this board draws."""
    whole = _drawn(_walk(board, "virtual"))[1]
    assert _drawn(_walk(board, "virtual", since="2026-09-30T01:30:00+00:00"))[1] != whole
    assert _drawn(_walk(board, "virtual", include_superseded=True))[1] != whole


def test_walk_shadow_finds_no_difference(board):
    raw = board["engine"].raw_connection()
    try:
        def fetch(sql, params=None):
            return trace._fetch(raw, sql, params)
        names = schema.require_world(None)
        snapshot = load_setup(names.declaration_root).snapshot
        legs, left_out = trace_router._compiled(raw, (names,))
        assert left_out == [] and {leg.source for leg in legs} == {CHANGED, KEPT}
        for source in (CHANGED, KEPT):
            mine = [leg for leg in legs if leg.source == source]
            others = {names.name: [other for other in snapshot.source_plans if other != source]}
            seeds = [(kind, json.loads(keys)) for kind, keys in fetch(
                "SELECT DISTINCT subject_type, subject_keys::text FROM %s WHERE source_who = %%(s)s" % names.ledger,
                {"s": source})]
            said = walk_shadow.shadow(
                fetch, names.ledger, snapshot.source_plans[source],
                ledger_subgraph.SqlEvidenceLookup(raw, worlds=(names,), leave_out=others),
                ledger_subgraph.VirtualEvidenceLookup(raw, mine, worlds=(names,)), seeds,
                sorted({leg.predicate for leg in mine}))
            assert said["atoms"]["stored"] and said["atoms"]["stored"] == said["atoms"]["virtual"], said
            assert {k: v for k, v in said["bins"].items() if k != "tie"} == {
                "spelling": 0, "stale": 0, "stored-only": 0, "real": 0}, said
    finally:
        raw.rollback()
        raw.close()


def test_the_key_list_follows_the_engine(board):
    session = board["db"]
    stored = trace_router.ledger_key_values(type="wafer", key=None, limit=50, world=None, starts_with=None,
                                            db=session, engine="stored")
    virtual = trace_router.ledger_key_values(type="wafer", key=None, limit=50, world=None, starts_with=None,
                                             db=session, engine="virtual")
    assert virtual["nodes"] == stored["nodes"] and len(stored["nodes"]) == 3
    assert "engine" not in stored and virtual["engine"]["name"] == "virtual"


def test_a_virtual_walk_is_not_continued(board):
    with pytest.raises(HTTPException) as refused:
        trace_router.evidence_subgraph(node_id=explorer.entity_id("wafer", {"wafer": "W1"}), engine="virtual",
                                       resumable=True, db=board["db"], world=None, follow=None, collect=None,
                                       expand=None, seed_type=None, group_by=None, measure=None, since=None,
                                       until=None, around=None, earlier=None, later=None, positive=None,
                                       negative=None, resume=None)
    assert refused.value.status_code == 422 and refused.value.detail["reason"] == "virtual_walk_not_continued"
