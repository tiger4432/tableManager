# -*- coding: utf-8 -*-
"""Cell-source overhaul, D's read share - a grid cell's metadata from the lines (docs/design/CELL_SOURCE_OVERHAUL.md
«읽기 — D 분야»): its winner is the source of the line `t__now.won_by` names (the merge at write time - nothing ranks
again on a read); its sources are each source's head line, a withdrawn one left out.

    page read     priority_source from won_by with or without the sources; sources = the head lines' values;
                  a cell no line won names none
    sources panel cell_layers: the same heads with time and writer, the same winner
"""
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

import grid_read
from conftest import retire_dynamic_model
from database import models
from tests.support import line_tables
from tests.test_a_rows_history_is_its_lines import (ENTRY, T0, TABLE, dialect_client,  # noqa: F401
                                                    _line_table_fixture)


@pytest.fixture
def cells(dialect_client, monkeypatch):
    client, engine, bits = _line_table_fixture(dialect_client, monkeypatch, TABLE, ENTRY)
    with engine.begin() as conn:
        file = line_tables.line(conn, TABLE, bits, "r1", source="f.csv", at=T0, values={"k": "K1", "a": "A1", "b": 1.5},
                                business_key="K1")
        hand = line_tables.line(conn, TABLE, bits, "r1", source="user", at=T0 + timedelta(minutes=1),
                                written_by="person", values={"a": "A2"}, business_key="K1")
        line_tables.line(conn, TABLE, bits, "r1", kind="withdraw", source="chain:rule_x",
                         at=T0 + timedelta(minutes=2), withdrawn=("b",), business_key="K1")
        line_tables.now(conn, TABLE, "r1", "K1", {"k": "K1", "a": "A2", "b": 1.5},
                        {"k": file, "a": hand, "b": file})
    try:
        with Session(bind=engine) as session:
            yield session
    finally:
        line_tables.drop(engine, TABLE)
        retire_dynamic_model(TABLE)


def _page(session, include_sources):
    rows = session.query(models.DYNAMIC_TABLES[TABLE]).all()
    data = grid_read.fetch_and_merge_metadata(session, TABLE, rows, ["k", "a", "b", "c"],
                                              include_sources=include_sources)[0]["data"]
    return {column: (cell["priority_source"], cell["sources"]) for column, cell in data.items() if column in "kabc"}


def test_a_cells_winner_is_the_source_of_the_line_won_by_names(cells):
    assert _page(cells, True) == {"k": ("f.csv", {"f.csv": "K1"}),
                                  "a": ("user", {"f.csv": "A1", "user": "A2"}),
                                  "b": ("f.csv", {"f.csv": 1.5}),
                                  "c": (None, {})}
    assert _page(cells, False) == {"k": ("f.csv", {}), "a": ("user", {}), "b": ("f.csv", {}), "c": (None, {})}


def test_the_sources_panel_reads_the_same_heads_and_winner(cells):
    row = cells.query(models.DYNAMIC_TABLES[TABLE]).one()
    found = grid_read.cell_layers(cells, TABLE, {"r1": row}, [("r1", "a"), ("r1", "b")])
    a, b = found[("r1", "a")], found[("r1", "b")]
    assert (a["priority_source"], sorted(a["sources"]), a["sources"]["user"]["updated_by"], a["value"]) == (
        "user", ["f.csv", "user"], "person", "A2")
    assert (b["priority_source"], list(b["sources"])) == ("f.csv", ["f.csv"]), "the chain's withdrawal says nothing"
