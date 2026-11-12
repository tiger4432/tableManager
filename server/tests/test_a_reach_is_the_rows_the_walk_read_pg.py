# -*- coding: utf-8 -*-
"""Lead 11-06 (the Tables page, S-hop · S-count): a marking - a table, a column, the values its cells showed - reaches
the rows of another table through the walk's reader (`trace_router.reach`): the reached rows are those every atom read
was read from (`SqlEvidenceLookup.rows_of`), the count is their number, an empty marking is 0 rows.

  the board     the sample's two sources on their tables (lot slot -> wafer · wafer -> recipe), backfilled
  expected      built outside the reach - the stored side from `ledger_atom_rows`, the virtual side from the table
  the cells     one step · two steps · the column names one end, not every end · the current fact only ·
                the cap · an empty marking · a value not in the table · a view
"""
import json
import os
import sys

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import paths                                                        # noqa: E402
from ledger import backfill, schema, trace_router                  # noqa: E402
from ledger_api import ledger_subgraph                              # noqa: E402
from test_ledger_worlds_are_independent_and_meet_in_a_walk import (  # noqa: E402,F401
    CHANGED, KEPT, _only, _timed, _write, fixture_config, fixture_world)

pytestmark = pytest.mark.pg


@pytest.fixture(autouse=True)
def _times_declared(monkeypatch):
    """The world's tables built with the sources' time columns declared datetime (`_timed`)."""
    import test_ledger_worlds_are_independent_and_meet_in_a_walk as worlds

    sample = worlds._sample
    monkeypatch.setattr(worlds, "_sample", lambda name: _timed(sample(name)) if name.startswith("table_config")
                        else sample(name))
ENGINES = ("stored", "virtual")
PROCESSES = [{"proc_id": "P1", "wafer_id": "W1", "step": "S1", "recipe_id": "RCP-1", "eventtime": "2026-09-30 10:00:00"},
             {"proc_id": "P2", "wafer_id": "W1", "step": "S2", "recipe_id": "RCP-2", "eventtime": "2026-09-30 11:00:00"},
             {"proc_id": "P3", "wafer_id": "W2", "step": "S1", "recipe_id": "RCP-1", "eventtime": "2026-09-30 10:00:00"},
             {"proc_id": "P4", "wafer_id": "W3", "recipe_id": "RCP-3", "eventtime": "2026-09-30 12:00:00"}]
SEATS = [{"lot_slot_wafer_key": "K1", "lot": "L1", "slot": "1", "wafer": "W1", "event_type": "load",
          "event_time": "2026-09-30 10:00:00"},
         {"lot_slot_wafer_key": "K2", "lot": "L1", "slot": "2", "wafer": "W2", "event_type": "load",
          "event_time": "2026-09-30 10:30:00"},
         {"lot_slot_wafer_key": "K3", "lot": "L2", "slot": "1", "wafer": "W3", "event_type": "load",
          "event_time": "2026-09-30 10:30:00"}]
WAFERS = dict(table="lot_slot_wafer", column="wafer", type="wafer", follow=["processed_with"], to="wafer_process")
LOTS = dict(table="lot_slot_wafer", column="lot", type="lot_slot", follow=["has_wafer", "processed_with"],
            to="wafer_process")


def _board(world, one=False):
    import notation_norm

    with world["engine"].begin() as conn:
        conn.connection.cursor().execute(notation_norm.key_instant_sql() + notation_norm.key_number_sql())
    with open(os.path.join(paths.config_path("ontology"), "ledger_config.json"), "w", encoding="utf-8") as fh:
        json.dump(_only(CHANGED, KEPT, one=one), fh)
    trace_router._COMPILED.clear()
    _write(world, "wafer_process", PROCESSES)
    _write(world, "lot_slot_wafer", SEATS)
    for source in (CHANGED, KEPT):
        backfill.run(world["engine"], source=source)
    return world


def _reach(world, engine, **asked):
    with world["engine"].connect() as conn:
        return trace_router.reach(conn, engine=engine, **{**WAFERS, **asked})


def _scalars(world, sql, **params):
    with world["engine"].connect() as conn:
        return {row for (row,) in conn.execute(text(sql), params)}


def _expected(world, wafers):
    """(stored: the rows `ledger_atom_rows` names for the wafers' processed_with atoms, virtual: the table's rows of the
    wafers) - built without the reach."""
    stored = _scalars(world, "SELECT source_row_id FROM %s WHERE source_relation = 'wafer_process' "
                             "AND predicate = 'processed_with' AND subject = ANY(:s)" % schema.ATOM_ROWS_VIEW,
                      s=["wafer=" + wafer for wafer in wafers])
    table = _scalars(world, "SELECT row_id FROM wafer_process WHERE wafer_id = ANY(:w)", w=list(wafers))
    return stored, table


@pytest.mark.parametrize("asked, wafers", [({"values": ["W1", "W2"]}, ("W1", "W2")),
                                           ({**LOTS, "values": ["L1"]}, ("W1", "W2"))],
                         ids=["one step", "two steps"])
def test_the_reached_rows_are_the_rows_of_every_atom_read(world, asked, wafers):
    _board(world)
    stored, table = _expected(world, wafers)
    assert stored == table and len(stored) == 3, "canary: P1 · P2 · P3, the same rows either way"
    for engine, expected in zip(ENGINES, (stored, table)):
        said = _reach(world, engine, **asked)
        assert set(said["rows"]) == expected, engine
        assert said["count"]["total"] == len(said["rows"]) and said["count"]["capped"] is False
        assert said["count"]["cap"] == trace_router.REACH_ATOM_CAP and said["count"]["counted_at"]
        assert said["seeds"] == 2 and said["left_out"] == [], said


def test_the_walk_route_answers_a_reach_and_refuses_an_undeclared_name(world):
    """`/subgraph`'s `reach` body - no route of its own; its type and predicates go through the walk's one name seat."""
    from fastapi import HTTPException

    _board(world)

    def asked(**reach):
        return trace_router.evidence_subgraph(
            node_id=None, reach={**WAFERS, "values": ["W1"], **reach}, engine="stored", db=world["db"], world=None,
            follow=None, collect=None, expand=None, seed_type=None, group_by=None, measure=None, since=None,
            until=None, around=None, earlier=None, later=None, positive=None, negative=None, resume=None)

    assert set(asked()["rows"]) == _expected(world, ("W1",))[1]
    for wrong, reason in (({"type": "wafr"}, "node_type_not_declared"), ({"follow": ["processd_with"]},
                                                                         "predicate_not_declared")):
        with pytest.raises(HTTPException) as refused:
            asked(**wrong)
        assert refused.value.status_code == 422 and refused.value.detail["reason"] == reason


@pytest.mark.parametrize("hidden", ["wafer_process", "lot_slot_wafer"], ids=["table B", "table A"])
def test_a_table_the_reader_may_not_read_is_refused(world, hidden, monkeypatch):
    """`hidden` - the tables `access.hidden_tables` says this reader may not read - refuses the reach as a door does."""
    from fastapi import HTTPException

    from types import SimpleNamespace

    from starlette.requests import Request

    from admin import access

    _board(world)
    with pytest.raises(HTTPException) as refused:
        trace_router.evidence_subgraph(
            node_id=None, reach={**WAFERS, "values": ["W1"]}, engine="stored", db=world["db"], world=None,
            hidden=(hidden,), reader="kim", follow=None, collect=None, expand=None, seed_type=None, group_by=None,
            measure=None, since=None, until=None, around=None, earlier=None, later=None, positive=None, negative=None,
            resume=None)
    assert refused.value.status_code == 403
    # the grid door's sentence for the same reader and table - a refusal sentence is a door too (lead 11-07)
    grid = Request({"type": "http", "method": "GET", "path": "/tables/%s/data" % hidden, "query_string": b"",
                    "headers": [], "route": SimpleNamespace(path="/tables/{table_name}/data"),
                    "path_params": {"table_name": hidden}, "state": {"sso_user": "kim"}})
    monkeypatch.setattr(access, "may", lambda user, table, what, row=None: table != hidden)
    with pytest.raises(HTTPException) as door:
        access.table_door(grid)
    assert refused.value.detail == door.value.detail and "kim" in door.value.detail


def test_a_hidden_middle_table_gives_none_of_its_atoms(world, monkeypatch):
    """From W1's process rows back to W1 through its lot slot (lot_slot_wafer, the middle) and on to its processes:
    hidden, the middle's atoms are not read - the reach ends there, and says one table was hidden."""
    _board(world)
    middle = dict(table="wafer_process", column="wafer_id", values=["W1"], type="wafer", to="wafer_process",
                  follow=["has_wafer", "has_wafer", "processed_with"])
    read = []

    def kept(real):
        def reading(self, *args, **kwargs):
            atoms, cut = real(self, *args, **kwargs)
            read.extend(atom.source_who for atom in atoms)
            return atoms, cut
        return reading

    for reader in (ledger_subgraph.SqlEvidenceLookup, ledger_subgraph.VirtualEvidenceLookup):
        monkeypatch.setattr(reader, "reached_for_entities", kept(reader.reached_for_entities))
    for engine in ENGINES:
        seen = _reach(world, engine, **middle)
        assert set(seen["rows"]) == _expected(world, ("W1",))[1] and "hidden" not in seen, engine
        assert KEPT in read, "canary: the middle is read when it is not hidden"
        read.clear()
        said = _reach(world, engine, hidden=("lot_slot_wafer",), **middle)
        assert said["rows"] == [] and said["hidden"] == 1 and said["seeds"] == 1, said
        assert KEPT not in read, engine


def test_the_column_names_its_type_not_every_end(world):
    """A process row names a wafer and a recipe: marked by its wafer, the seed is the wafer - from a recipe the walk
    would go on to another wafer's process (P3)."""
    _board(world)
    for engine in ENGINES:
        said = _reach(world, engine, table="wafer_process", column="wafer_id", values=["W1"])
        assert set(said["rows"]) == _expected(world, ("W1",))[1] and said["seeds"] == 1, engine


def test_a_one_predicate_reaches_its_current_fact_only(world):
    """`processed_with` holding one recipe: W1's current fact is P2 (11:00), so P1 is not reached - the walk's own
    reading of «current»."""
    _board(world, one=True)
    latest = _scalars(world, "SELECT DISTINCT ON (wafer_id) row_id FROM wafer_process WHERE wafer_id = ANY(:w) "
                             "ORDER BY wafer_id, eventtime DESC", w=["W1", "W2"])
    assert len(latest) == 2
    for engine in ENGINES:
        assert set(_reach(world, engine, values=["W1", "W2"])["rows"]) == latest, engine


def test_the_cap_is_said(world, monkeypatch):
    _board(world)
    monkeypatch.setattr(trace_router, "REACH_ATOM_CAP", 1)
    for engine in ENGINES:
        said = _reach(world, engine, values=["W1", "W2"])
        assert said["count"] == {"total": 1, "capped": True, "cap": 1, "counted_at": said["count"]["counted_at"],
                                 "capped_steps": [{"step": 1, "predicate": "processed_with"}]}
        assert len(said["rows"]) == 1, engine


def test_a_cut_step_goes_on_from_what_it_read(world, monkeypatch):
    """Two steps at a cap of one atom a step: the lot slot step is cut at one wafer, the process step walks from it -
    one row, capped, never «0, capped» (lead 11-07)."""
    _board(world)
    monkeypatch.setattr(trace_router, "REACH_ATOM_CAP", 1)
    for engine in ENGINES:
        said = _reach(world, engine, **{**LOTS, "values": ["L1"]})
        assert said["count"]["capped"] is True and said["count"]["total"] == 1 and said["seeds"] == 2, said
        assert said["count"]["capped_steps"][0] == {"step": 1, "predicate": "has_wafer"}, said
        assert set(said["rows"]) <= _expected(world, ("W1", "W2"))[1], engine


def test_a_cut_step_passes_on_its_newest_far_ends_up_to_the_frontier_cap(world, monkeypatch):
    """Lots L1 · L2 (three slots) at two atoms a step: the slot step is cut at two wafers; at a frontier of one, the
    process step walks from the newest one alone - one process row, where both wafers give two."""
    _board(world)
    monkeypatch.setattr(trace_router, "REACH_ATOM_CAP", 2)
    for engine in ENGINES:
        both = _reach(world, engine, **{**LOTS, "values": ["L1", "L2"]})
        assert both["count"]["total"] == 2 and both["count"]["capped_steps"] == [{"step": 1, "predicate": "has_wafer"}]
        monkeypatch.setattr(trace_router, "REACH_FRONTIER_CAP", 1)
        one = _reach(world, engine, **{**LOTS, "values": ["L1", "L2"]})
        monkeypatch.setattr(trace_router, "REACH_FRONTIER_CAP", 1000)
        assert one["count"]["total"] == 1 and set(one["rows"]) < set(both["rows"]), (engine, one, both)


def test_an_empty_marking_is_zero_rows_and_reads_nothing(world, monkeypatch):
    _board(world)

    def refused(*_args, **_kwargs):
        raise AssertionError("an empty marking read the ledger")

    for name in ("nodes_of_rows", "reached_for_entities", "rows_of"):
        monkeypatch.setattr(ledger_subgraph.SqlEvidenceLookup, name, refused)
        monkeypatch.setattr(ledger_subgraph.VirtualEvidenceLookup, name, refused, raising=False)
    for engine in ENGINES:
        said = _reach(world, engine, values=[])
        assert said["rows"] == [] and said["count"]["total"] == 0 and said["count"]["capped"] is False


def test_a_value_not_in_the_table_is_said(world):
    _board(world)
    for engine in ENGINES:
        said = _reach(world, engine, values=["W1", "W9"])
        assert {"why": "not in the table", "table": "lot_slot_wafer", "values": 1} in said["left_out"], engine
        assert set(said["rows"]) == _expected(world, ("W1",))[1]


def test_a_view_has_no_rows_to_reach_and_is_said(world):
    _board(world)
    for engine in ENGINES:
        said = _reach(world, engine, values=["W1"], to=schema.ATOM_ROWS_VIEW)
        assert said["rows"] == [] and said["count"]["total"] == 0
        assert said["left_out"] == [{"why": "a view - its rows have no row_id", "table": schema.ATOM_ROWS_VIEW,
                                     "sources": []}], engine


def test_a_marking_names_the_seeds_and_the_answer_says_its_revision(world):
    """Lead 11-07 S-mark: `reach.marking` (the reader's kept marking, `markings.read`) is the same seeds as its table,
    column and values said in the body; with values too, refused - the seeds said twice."""
    from fastapi import HTTPException

    from database import models

    _board(world)
    world["db"].add(models.Marking(owner="", id="m1", table_name="lot_slot_wafer", column_name="wafer",
                                   marked=["W1"], rev=3))
    world["db"].commit()

    def asked(engine="virtual", **reach):
        return trace_router.evidence_subgraph(
            node_id=None, reach={**{k: v for k, v in WAFERS.items() if k not in ("table", "column")}, **reach},
            engine=engine, db=world["db"], world=None, follow=None, collect=None, expand=None, seed_type=None,
            group_by=None, measure=None, since=None, until=None, around=None, earlier=None, later=None,
            positive=None, negative=None, resume=None)

    for engine in ("virtual", "stored"):                     # owner 11-07: virtual first
        said = asked(engine, marking="m1")
        assert set(said["rows"]) == _expected(world, ("W1",))[1] and said["marking"] == {"id": "m1", "rev": 3}, engine
    with pytest.raises(HTTPException) as refused:
        asked(marking="m1", values=["W2"])
    assert refused.value.status_code == 422 and refused.value.detail["reason"] == "seeds_defined_twice"


def test_a_reach_with_no_to_answers_every_table_its_atoms_were_read_from(world):
    """The molecule walk (lead 11-12 ㄴ): lot L1 along has_wafer and processed_with, no `to` - the lot slot rows the
    first step read and the process rows the second read, each table its own rows; `to`'s table is the same rows a
    reach with `to` answers, and a reach with `to` answers as it did (no `tables`)."""
    _board(world)
    seats = _scalars(world, "SELECT row_id FROM lot_slot_wafer WHERE lot = 'L1'")
    assert len(seats) == 2, "canary: K1 · K2"
    for engine in ENGINES:
        to = _reach(world, engine, **{**LOTS, "values": ["L1"]})
        said = _reach(world, engine, **{**LOTS, "values": ["L1"], "to": None})
        assert "tables" not in to and "tables" in said and "rows" not in said and "table" not in said, said
        assert said["tables"] == {
            "lot_slot_wafer": {"rows": sorted(seats), "count": 2, "capped": False},
            "wafer_process": {"rows": to["rows"], "count": 3, "capped": False}}, (engine, said)
        assert set(to["rows"]) == _expected(world, ("W1", "W2"))[1]
        assert said["count"]["total"] == 5 and said["seeds"] == to["seeds"] == 2 and said["left_out"] == [], said


def test_the_walk_route_keeps_each_reached_table_as_a_marking_of_the_readers(world):
    """Each table a reach with no `to` answers is kept as one marking of the reader's on its row_id (`markings.keep`,
    the writer POST /markings calls) - the grid pages it by `?marking=`; a reach with `to` keeps none."""
    import markings
    from database import models

    _board(world)

    def asked(**reach):
        return trace_router.evidence_subgraph(
            node_id=None, reach={**LOTS, "values": ["L1"], **reach}, engine="virtual", db=world["db"], world=None,
            follow=None, collect=None, expand=None, seed_type=None, group_by=None, measure=None, since=None,
            until=None, around=None, earlier=None, later=None, positive=None, negative=None, resume=None)

    before = world["db"].query(models.Marking).count()
    assert "tables" not in asked() and world["db"].query(models.Marking).count() == before
    said = asked(to=None)
    assert sorted(said["tables"]) == ["lot_slot_wafer", "wafer_process"], said
    for table, reached in said["tables"].items():
        assert reached["marking"]["rev"] == 1, reached
        assert markings.read(world["db"], reached["marking"]["id"], None) == (table, "row_id", reached["rows"], 1)
    assert world["db"].query(models.Marking).count() == before + 2
