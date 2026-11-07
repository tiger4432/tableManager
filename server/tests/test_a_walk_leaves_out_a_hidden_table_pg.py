# -*- coding: utf-8 -*-
"""Owner 11-06 (access, lead ①ㄴ): a walk leaves out the atoms of a table its reader may not read - on both engines,
in every mode - through the `leave_out` a `first` read uses; the answer says how many tables, never which.

  the board   the virtual walk's (two sources: wafer_process -> recipe, lot_slot_wafer -> wafer), backfilled
  hidden      wafer_process
  the cells   a walk · a time window · old facts too · the rows mode · the key list · the gap measure · nothing
              hidden = today's answer (no `hidden` cell, the same drawing)
"""
import json

import pytest

from ledger import trace_router
from test_a_virtual_walk_draws_what_the_ledger_draws_pg import (  # noqa: F401
    _drawn, _times_declared, _walk, fixture_board)
from test_ledger_worlds_are_independent_and_meet_in_a_walk import fixture_config, fixture_world  # noqa: F401

pytestmark = pytest.mark.pg
HIDDEN = ("wafer_process",)
ENGINES = ("stored", "virtual")


def _relations(payload):
    """The tables an answer's edges stand on - a stored basis names its event's relation (`event_frame`), a virtual one
    is «relation:row id»."""
    return {json.loads(json.loads(edge["basis"])["event"])["relation"] if edge["basis"].startswith("{")
            else edge["basis"].split(":", 1)[0] for edge in payload["edges"] if edge.get("basis")}


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("asked", [{}, {"since": "2026-09-30T01:30:00+00:00"}, {"include_superseded": True}],
                         ids=["walk", "since", "old facts too"])
def test_a_walk_draws_no_atom_of_a_hidden_table(board, engine, asked):
    seen = _walk(board, engine, **asked)
    assert "wafer_process" in _relations(seen), "canary: the walk crosses the table hidden below"
    assert "hidden" not in seen
    hidden = _walk(board, engine, hidden=HIDDEN, **asked)
    assert "wafer_process" not in _relations(hidden) and _relations(hidden) <= _relations(seen)
    assert hidden["hidden"] == 1 and "wafer_process" not in json.dumps(hidden.get("hidden"))


@pytest.mark.parametrize("engine", ENGINES)
def test_nothing_hidden_is_today_s_answer(board, engine):
    today, nobody = _walk(board, engine), _walk(board, engine, hidden=())
    assert _drawn(nobody) == _drawn(today) and "hidden" not in nobody


@pytest.mark.parametrize("engine", ENGINES)
def test_the_rows_mode_reads_no_hidden_atom(board, engine):
    seen = _walk(board, engine, rows=True)["rows"]
    hidden = _walk(board, engine, rows=True, hidden=HIDDEN)["rows"]
    assert "RCP-" in seen and "RCP-" not in hidden                            # recipes are wafer_process's alone


@pytest.mark.parametrize("engine", ENGINES)
def test_the_key_list_leaves_it_out(board, engine):
    session = board["db"]
    asked = dict(type="recipe", key=None, limit=50, world=None, starts_with=None, db=session, engine=engine)
    seen = trace_router.ledger_key_values(**asked)
    hidden = trace_router.ledger_key_values(hidden=HIDDEN, **asked)
    assert len(seen["nodes"]) >= 1 and "hidden" not in seen                      # canary: recipes are listed
    assert hidden["nodes"] == [] and hidden["hidden"] == 1


@pytest.mark.parametrize("engine", ENGINES)
def test_the_gap_measure_counts_no_hidden_atom(board, engine):
    """The board's gaps that need a fact read from lot_slot_wafer (has_wafer) - none asks wafer_process's."""
    names = trace_router.ledger_gap_catalogue(name=None, world=None, engine=engine)["gaps"]
    asked = [item["name"] for item in names if "has_wafer" in (item.get("present") or ())]
    assert asked, "canary: a gap that needs lot_slot_wafer's predicate is declared"
    seen = {name: trace_router.ledger_gap_catalogue(name=name, world=None, engine=engine) for name in asked}
    hidden = {name: trace_router.ledger_gap_catalogue(name=name, world=None, engine=engine,
                                                      hidden=("lot_slot_wafer",))
              for name in asked}
    assert sum(answer["gaps"][0]["count"] for answer in seen.values()) > 0, "canary: the gap is found"
    assert {name: (answer["gaps"][0]["count"], answer["hidden"]) for name, answer in hidden.items()} == {
        name: (0, 1) for name in asked}
    assert all("hidden" not in answer for answer in seen.values())
