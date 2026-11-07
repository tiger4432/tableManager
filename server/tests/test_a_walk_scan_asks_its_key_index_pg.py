# -*- coding: utf-8 -*-
"""Owner 11-07 «키칸 인덱스 자동» (lead ㄱ 안 1): the key columns a virtual walk scans are asked for an automatic index
from the one seat that says «scan» (`trace_router._engine_reading`), through the grid's door (`index_wants`).

  asked      the scans' (table, first key column) = what is asked, reason «walk key»
  served     an automatic index built on a scanned column takes it out of the scans (the catalogue's judgment)
  view       a source reading a view is never asked for
  cap        a table holding auto_index_per_table automatic indexes is not asked for one more
"""
import json
import os
import sys

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import paths                                                        # noqa: E402
from database import crud, models                                   # noqa: E402
from ledger import trace_router                                     # noqa: E402
from runtime import index_wants                                     # noqa: E402
from test_a_virtual_walk_draws_what_the_ledger_draws_pg import _times_declared, fixture_board  # noqa: E402,F401
from test_ledger_worlds_are_independent_and_meet_in_a_walk import (  # noqa: E402,F401
    CHANGED, KEPT, _only, fixture_config, fixture_world)

pytestmark = pytest.mark.pg


@pytest.fixture(name="asked")
def fixture_asked(monkeypatch):
    asked = []
    monkeypatch.setattr(index_wants, "want", lambda table, columns, why, seconds, bind:
                        asked.append((table, tuple(columns), why, seconds)))
    return asked


def _scans(board):
    trace_router._COMPILED.clear()
    with board["engine"].connect() as conn:
        _legs, said = trace_router._engine_reading(conn, "virtual", trace_router._worlds(None))
    return {(scan["table"], scan["column"]) for scan in said["scans"]}


def test_each_scanned_key_column_is_asked_for_a_walk_key_index(board, asked):
    scans = _scans(board)
    assert {(t, c) for t, c in scans if c} == {("wafer_process", "wafer_id"), ("wafer_process", "recipe_id"),
                                                ("lot_slot_wafer", "lot"), ("lot_slot_wafer", "wafer")}, scans
    assert {(t, c[0]) for t, c, _w, _s in asked} == {(t, c) for t, c in scans if c}
    assert {(why, seconds, len(columns)) for _t, columns, why, seconds in asked} == {(models.AUTO_WALK_KEY, None, 1)}


def test_an_automatic_index_on_a_scanned_column_takes_it_out_of_the_scans(board, asked):
    built = models.ensure_auto_indexes(board["engine"], [("wafer_process", ["wafer_id"], models.AUTO_WALK_KEY)],
                                       say=lambda *_: None)
    assert built == {models.auto_index_name("wafer_process", ["wafer_id"], models.AUTO_WALK_KEY): models.INDEX_BUILT}
    scans = _scans(board)
    assert ("wafer_process", "wafer_id") not in scans and ("wafer_process", "recipe_id") in scans, scans
    assert ("wafer_process", ("wafer_id",)) not in {(t, c) for t, c, _w, _s in asked}


def test_a_source_reading_a_view_is_never_asked_for(board, asked, monkeypatch):
    document = _only(CHANGED, KEPT, one=True)
    viewed = json.loads(json.dumps(document["sources"][CHANGED]))
    viewed["relation"] = "wp_view"
    document["sources"]["wp_view_recipe"] = viewed
    with open(os.path.join(paths.config_path("ontology"), "ledger_config.json"), "w", encoding="utf-8") as fh:
        json.dump(document, fh)
    monkeypatch.setitem(crud.TABLE_CONFIG, "wp_view", {**crud.TABLE_CONFIG["wafer_process"], "kind": "view",
                                                       "query": "SELECT * FROM wafer_process"})
    scans = _scans(board)
    assert scans and asked, "canary: the two table sources still scan and ask"
    assert "wp_view" not in {t for t, _c in scans} | {t for t, _c, _w, _s in asked}


def test_a_table_at_its_cap_is_not_asked_for_one_more(board):
    from conftest import PG_TEST_SCHEMA
    from parsers.directory_watcher import auto_index_per_table

    cap = auto_index_per_table()
    with board["engine"].begin() as conn:
        for n in range(cap):
            conn.execute(text('CREATE INDEX "%scap_%d" ON "%s"."lot_slot_wafer" (slot, row_id)'
                              % (models.AUTO_INDEX_PREFIX, n, PG_TEST_SCHEMA)))

    def wanted():
        with board["engine"].connect() as conn:
            return [json.loads(p) for (p,) in conn.execute(text(
                "SELECT payload FROM database_outbox WHERE event_type = 'INDEX_WANTED' AND table_name = :t"),
                {"t": "lot_slot_wafer"})]

    assert index_wants.ask("wafer_process", ["wafer_id"], models.AUTO_WALK_KEY, None, board["engine"]) is True, \
        "canary: a table under its cap is asked"
    assert index_wants.ask("lot_slot_wafer", ["lot"], models.AUTO_WALK_KEY, None, board["engine"]) is False
    assert wanted() == []
