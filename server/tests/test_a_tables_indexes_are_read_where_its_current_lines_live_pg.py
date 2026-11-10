# -*- coding: utf-8 -*-
"""Cell-source overhaul, D's read share - the grid's index questions name the relation a declared table's indexes
live on (`lines.stored_relation`: t__now; the name t is a view and holds none, C 11-10).

    header and filter marks   an index on t__now(a) is «built» for a (main.filter_index_states · the schema's
                              column_indexes)
    a slow page's plan        a page read through the view t scans t__now: its equal filter column is found
    a reference read          a Seq Scan of t__now asks its index for t (`lines.declared_of`)
"""
import json

import pytest
from sqlalchemy import text

import main
from conftest import retire_dynamic_model
from database import crud, models
from runtime import index_wants
from tests.support import line_tables
from tests.test_a_rows_history_is_its_lines import ENTRY, TABLE

pytestmark = pytest.mark.pg


@pytest.fixture
def indexed(pg_engine, monkeypatch):
    models.init_dynamic_models({TABLE: ENTRY})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    bits = line_tables.build(pg_engine, TABLE)
    with pg_engine.begin() as conn:
        for n in range(50):
            line_tables.now(conn, TABLE, "r%02d" % n, "K%02d" % n, {"k": "K%02d" % n, "a": "A%d" % (n % 5)})
        conn.execute(text('CREATE INDEX "ix_probe_now_a" ON "%s__now" (a)' % TABLE))
        conn.execute(text('ANALYZE "%s__now"' % TABLE))
    try:
        yield pg_engine, bits
    finally:
        line_tables.drop(pg_engine, TABLE)
        retire_dynamic_model(TABLE)


def test_an_index_on_the_current_lines_is_built_for_the_grid(indexed):
    engine, _bits = indexed
    assert main.filter_index_states(engine, TABLE, ["a", "b"]) == {"a": "built", "b": "not built"}


def test_a_page_through_the_view_is_planned_on_the_current_lines(indexed):
    engine, _bits = indexed
    with engine.connect() as conn:
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        plan = conn.execute(text('EXPLAIN (FORMAT JSON) SELECT row_id FROM "%s" WHERE a = \'A1\' ORDER BY b'
                                 % TABLE)).scalar()
    plan = json.loads(plan) if isinstance(plan, str) else plan
    from database import lines

    equal, _by_row, sort = index_wants.page_plan(plan, lines.stored_relation(TABLE, ENTRY))
    assert (equal, sort) == (["a"], True), plan
    assert index_wants.page_plan(plan, TABLE) == ([], [], True), "canary: the plan names t__now, not the view"


def test_a_slow_reference_read_scanning_the_current_lines_asks_for_the_declared_table(indexed, monkeypatch):
    engine, _bits = indexed
    asked = []
    monkeypatch.setattr(index_wants, "want", lambda table, columns, why, seconds, bind: asked.append((table, columns)))
    index_wants._plan_wants("probe", "probe view", 'SELECT row_id FROM "%s" WHERE b = :v' % TABLE, {"v": "x"}, 2.0,
                            engine)
    assert asked == [(TABLE, ["b"])], asked
