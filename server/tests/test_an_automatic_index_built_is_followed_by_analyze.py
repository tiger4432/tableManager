# -*- coding: utf-8 -*-
"""A grid automatic index just built is followed by an ANALYZE of its table (owner 11-05 «ㅇㅇ»), through the join key
index's own path (`ingestion_worker._analyze_stale_tables_sync(built=)` -> `_analyze_after_load(forced=)`): without
statistics a sorted page of two equal values walked the row_id index (1.4 s at 10M rows, box throwaway DB) where
with them it is a bitmap and a sort (29 ms).

  the index           built -> analysed · already there -> not again · analyze_after_rows 0 -> not analysed
  the schema          a name in two schemas -> the search path's one, once · in no schema of the path -> not at all
                      (C 11-05, lead ㄱ) · the ANALYZE failing -> «built on <t>; the ANALYZE after it did not run»
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import conftest  # noqa: E402
from database import crud, models  # noqa: E402
from parsers import directory_watcher as dw  # noqa: E402

pytestmark = pytest.mark.pg
S = conftest.PG_TEST_SCHEMA


def _last_analyze(engine, table):
    with engine.connect() as c:
        c.execute(text("SELECT pg_stat_clear_snapshot()"))
        return c.execute(text("SELECT last_analyze FROM pg_stat_user_tables WHERE schemaname = :s AND relname = :t"),
                         {"s": S, "t": table}).scalar()


def _table(engine, name):
    with engine.begin() as c:
        c.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (S, name)))
        c.execute(text('CREATE TABLE "%s"."%s" (row_id varchar PRIMARY KEY, k varchar) '
                       'WITH (autovacuum_enabled = false)' % (S, name)))
        c.execute(text("INSERT INTO \"%s\".\"%s\" SELECT 'r' || g, 'K' || (g %% 50) FROM generate_series(1, 2000) g"
                       % (S, name)))


@pytest.fixture(name="box")
def fixture_box(pg_engine, monkeypatch):
    factory = sessionmaker(bind=pg_engine)
    monkeypatch.setattr(dw, "SessionLocal", factory)          # the ANALYZE's session: this schema's database
    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 100000)
    names = ["zz_auto_analyze", "zz_auto_analyze_off"]
    for name in names:
        _table(pg_engine, name)
        monkeypatch.setitem(crud.TABLE_CONFIG, name, {"business_key": "row_id", "column_types": {"k": "string"}})
    yield pg_engine, factory
    with pg_engine.begin() as c:
        for name in names:
            c.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (S, name)))


def _ensure(factory, table):
    said = []
    models.ensure_auto_indexes_sync(factory, [(table, ["k"], models.AUTO_SLOW_FILTER)], said.append, decide=False)
    return said


def test_an_index_built_analyses_its_table_and_one_already_there_does_not_again(box):
    engine, factory = box
    assert _last_analyze(engine, "zz_auto_analyze") is None             # canary: never analysed before

    _ensure(factory, "zz_auto_analyze")
    first = _last_analyze(engine, "zz_auto_analyze")
    assert first is not None, "the index was built and its table was not analysed"

    time.sleep(1.1)
    _ensure(factory, "zz_auto_analyze")                                  # the index is there - nothing is built
    assert _last_analyze(engine, "zz_auto_analyze") == first


def test_analyze_after_rows_0_turns_it_off(box, monkeypatch):
    engine, factory = box
    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 0)

    _ensure(factory, "zz_auto_analyze_off")

    with engine.connect() as c:                                          # canary: the index WAS built
        assert c.execute(text("SELECT count(*) FROM pg_indexes WHERE schemaname = :s AND tablename = :t "
                              "AND indexname LIKE :p"), {"s": S, "t": "zz_auto_analyze_off",
                                                          "p": models.AUTO_INDEX_PREFIX + "%"}).scalar() == 1
    assert _last_analyze(engine, "zz_auto_analyze_off") is None


OTHER = "zz_b_stale_other"


def test_a_name_in_two_schemas_is_analysed_once_and_one_off_the_path_not_at_all(pg_engine, monkeypatch):
    """`pg_stat_user_tables` names a relation by name only: the one `ANALYZE "<name>"` reaches is the search path's."""
    from chain import ingestion_worker

    factory = sessionmaker(bind=pg_engine)
    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 100)
    for name in ("zz_stale_dup", "zz_stale_off_path"):
        monkeypatch.setitem(crud.TABLE_CONFIG, name, {"business_key": "row_id", "column_types": {"k": "string"}})
    with pg_engine.begin() as c:
        c.execute(text('CREATE SCHEMA IF NOT EXISTS "%s"' % OTHER))
    try:
        for schema, name in ((S, "zz_stale_dup"), (OTHER, "zz_stale_dup"), (OTHER, "zz_stale_off_path")):
            with pg_engine.begin() as c:
                c.execute(text('CREATE TABLE "%s"."%s" (row_id varchar PRIMARY KEY, k varchar) '
                               'WITH (autovacuum_enabled = false)' % (schema, name)))
                c.execute(text("INSERT INTO \"%s\".\"%s\" SELECT 'r' || g, 'K' FROM generate_series(1, 500) g"
                               % (schema, name)))
                c.execute(text("SELECT pg_stat_force_next_flush()"))
        with pg_engine.connect() as c:                                   # canary: all three are stale by name
            assert c.execute(text("SELECT count(*) FROM pg_stat_user_tables WHERE relname IN "
                                  "('zz_stale_dup', 'zz_stale_off_path') AND n_mod_since_analyze >= 100")).scalar() == 3
        analysed = []
        monkeypatch.setattr(dw, "_analyze_after_load", lambda name, rows, why=None, forced=False: analysed.append(name)
                            or True)
        ingestion_worker._analyze_stale_tables_sync(factory)
        assert sorted(name for name in analysed if name.startswith("zz_stale_")) == ["zz_stale_dup"], analysed
    finally:
        with pg_engine.begin() as c:
            c.execute(text('DROP TABLE IF EXISTS "%s"."zz_stale_dup"' % S))
            c.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % OTHER))


def test_an_analyze_that_fails_after_an_index_is_built_says_the_index_stands(box, monkeypatch):
    from chain import ingestion_worker

    engine, factory = box

    def _fails(*args, **kwargs):
        raise RuntimeError("statistics unreachable")

    monkeypatch.setattr(ingestion_worker, "_analyze_stale_tables_sync", _fails)
    said = _ensure(factory, "zz_auto_analyze")
    assert any(line.startswith("[Indexes] built on zz_auto_analyze; the ANALYZE after it did not run")
               and "statistics unreachable" in line for line in said), said
    assert not any("were not compared" in line for line in said), said
