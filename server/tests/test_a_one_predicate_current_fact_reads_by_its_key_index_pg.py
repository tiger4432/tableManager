# -*- coding: utf-8 -*-
"""Lead 11-11 ① (owner «걸어지는 세계인데 느리다»): a `one` predicate's current fact - the later fact of the same subject
- was read by the subject's spelling coalesce(col, ''), so the column's walk-key index could not serve it and every
step scanned the table. A text key with no notation rule is compared as the column (`Leg.compared`, the frontier's
own seat): `said` drops a blank key first, so the column IS its spelling on every row kept.

  the answer   blank keys (NULL · '' · spaces) on the board: the virtual walk draws the stored ledger's walk, and what
               the spelling drew
  the plan     the current fact's statement with an index on the key and scans priced out: no Seq Scan of the table
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import models                                         # noqa: E402
from ledger import sql_translate, trace, trace_router               # noqa: E402
from ledger_api import ledger_subgraph                              # noqa: E402
from test_a_virtual_walk_draws_what_the_ledger_draws_pg import (    # noqa: E402,F401
    ROWS, _board, _drawn, _times_declared, _walk)
from test_ledger_worlds_are_independent_and_meet_in_a_walk import (  # noqa: E402,F401
    CHANGED, KEPT, _only, fixture_config, fixture_world)

pytestmark = pytest.mark.pg

BLANKS = [dict(ROWS[0], proc_id="PB1", wafer_id=None), dict(ROWS[0], proc_id="PB2", wafer_id=""),
          dict(ROWS[0], proc_id="PB3", wafer_id="   ")]


@pytest.fixture(name="board")
def fixture_board(world):
    return _board(world, _only(CHANGED, KEPT, one=True), rows=ROWS + BLANKS)


def _spelled(monkeypatch):
    """Every key compared by its spelling (`Leg.key`) - the current fact as it was read before."""
    monkeypatch.setattr(sql_translate.Leg, "compared", lambda self, spec: (self.key(spec), "text"))


def test_blank_keys_draw_the_same_walk_by_the_column_as_by_the_spelling(board, monkeypatch):
    with board["engine"].connect() as conn:
        blank = trace._fetch(conn, "SELECT count(*) FROM wafer_process WHERE btrim(coalesce(wafer_id, '')) = ''")[0][0]
    assert blank == len(BLANKS), "canary: the blank-key rows are on the table"
    by_column = _drawn(_walk(board, "virtual"))
    assert by_column == _drawn(_walk(board, "stored"))
    assert any('"processed_with' in edge for edge in by_column[1]), "canary: the walk crosses the `one` predicate"
    _spelled(monkeypatch)
    assert _drawn(_walk(board, "virtual")) == by_column


def _seq_scans(node):
    node = node.get("Plan", node)
    found = [node["Relation Name"]] if node.get("Node Type") == "Seq Scan" else []
    for child in node.get("Plans") or ():
        found += _seq_scans(child)
    return found


def _current_fact_scans(board):
    with board["engine"].connect() as conn:
        legs, _left = trace_router._compiled(conn, trace_router._worlds(None))
        one = ledger_subgraph.one_predicates(trace_router._predicate_cardinalities(None))
        lookup = ledger_subgraph.VirtualEvidenceLookup(conn, legs, one=one)
        leg = next(leg for leg in lookup.legs if leg.relation == "wafer_process" and leg.predicate in one)
        bare, _specs = leg.ends["outgoing"]
        params = {"fetch": 11}
        where = lookup._arms(leg, "outgoing", [(bare, {key: "W1" for key, _spec in leg.columns_of("outgoing")})],
                             params)
        statement = lookup._statement(leg, where, params, tail="LIMIT %(fetch)s")
        conn.exec_driver_sql("SET enable_seqscan = off")
        plan = trace._fetch(conn, "EXPLAIN (FORMAT JSON) " + statement, params)[0][0]
    return _seq_scans(plan[0])


def test_the_current_fact_reads_the_subject_by_its_key_index(board, monkeypatch):
    built = models.ensure_auto_indexes(board["engine"], [("wafer_process", ["wafer_id"], models.AUTO_WALK_KEY)],
                                       say=lambda *_: None)
    assert list(built.values()) == [models.INDEX_BUILT]
    assert "wafer_process" not in _current_fact_scans(board)
    _spelled(monkeypatch)
    assert "wafer_process" in _current_fact_scans(board), "canary: the spelling cannot use the index - the plan sees it"
