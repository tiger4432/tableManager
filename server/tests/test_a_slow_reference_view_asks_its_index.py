# -*- coding: utf-8 -*-
"""소유자 10-14 «넓혀» (총괄 76704b7f2): a slow reference view asks for its indexes through the grid's door - its plan is
read once a process (EXPLAIN), each table it scans whole through a filter is wanted: equal or IN a slow filter, LIKE or
ILIKE a slow search, built as the declared search index's trigram. A pattern a trigram cannot narrow, a database without
pg_trgm and a table the product does not declare are said on that line."""
import json
import logging

import pytest

from database import crud, models
from runtime import index_wants

TABLE = "auto_search_probe"
ENTRY = {"business_key": "k", "composite_key_source": ["k"],
         "column_types": {"k": "string", "s": "string", "n": "number"}}


def _scan(relation, alias, condition):
    return {"Node Type": "Seq Scan", "Relation Name": relation, "Alias": alias, "Filter": condition}


def _plan(*scans):
    return [{"Plan": {"Node Type": "Limit", "Plans": list(scans)}}]


# the Filter strings as PostgreSQL 16 printed them for these views (scratch probe, 10-14)
@pytest.mark.parametrize("condition, found", [
    ("((lot_id)::text ~~* '%abc%'::text)", [("t", "lot_id", "slow search", None)]),
    ("((note ~~ '%abcd%'::text) AND (n = 5))", [("t", "note", "slow search", None), ("t", "n", "slow filter", None)]),
    ("((lot_id)::text = ANY ('{a,b}'::text[]))", [("t", "lot_id", "slow filter", None)]),
    ("((\"Odd Col\")::text ~~* '%abc%'::text)", [("t", "Odd Col", "slow search", None)]),
    ("(((\"Odd Col\")::text ~~* '%abc%'::text) OR (n = ANY ('{1,2}'::integer[])))", []),
    ("((n = 1) OR ((k)::text = 'x'::text))", []),
    ("(n = m)", []),
    ("((lot_id)::text !~~ '%abc%'::text)", []),
    ("(n >= 5)", []),
    # a candidate probe's LATERAL over its keys: the right side is each key's value
    ("(((lot_id)::text = \"*VALUES*\".column2) AND (n = \"*VALUES*\".column3))",
     [("t", "lot_id", "slow filter", None), ("t", "n", "slow filter", None)]),
    ("((lot_id)::text ~~* (('%'::text || \"*VALUES*\".column2) || '%'::text))", [("t", "lot_id", "slow search", None)]),
    ("(t.n = t.m)", []),
])
def test_a_scan_s_filter_reads_as_its_wants(condition, found):
    assert index_wants.scanned_filters(_plan(_scan("t", "t", condition))) == found


@pytest.mark.parametrize("pattern, short", [("%ab%", True), ("%abc%", False), ("%x%y%", True), ("ab_", True),
                                            ("abc%", False)])
def test_a_pattern_under_three_letters_is_said_not_wanted(pattern, short):
    [(_t, _c, why, reason)] = index_wants.scanned_filters(_plan(_scan("t", "t", "(note ~~ '%s'::text)" % pattern)))
    assert why == "slow search"
    assert (reason is not None) is short and (not short or "under 3 characters" in reason), reason


def test_each_scan_of_a_join_says_its_own_table_and_only_a_seq_scan_reads():
    plan = _plan({"Node Type": "Hash Join", "Plans": [
        _scan("t_ref", "a", "(note ~~* '%xyz%'::text)"),
        {"Node Type": "Hash", "Plans": [_scan("t_log", "b", "((lot_id)::text = 'q'::text)")]},
        {"Node Type": "Index Scan", "Relation Name": "t_other", "Filter": "(n = 5)"}]})
    assert index_wants.scanned_filters(plan) == [("t_ref", "note", "slow search", None),
                                                 ("t_log", "lot_id", "slow filter", None)]


def test_a_search_is_the_declared_trigram_under_its_own_name():
    search = models.auto_index_name(TABLE, ["s"], models.AUTO_SLOW_SEARCH)
    assert search != models.auto_index_name(TABLE, ["s"], models.AUTO_SLOW_FILTER) and search.endswith("_s_search")
    assert models.auto_index_ddl(TABLE, ["s"], models.AUTO_SLOW_SEARCH) == models.table_index_ddl(
        {"search": True, "name": search, "table": TABLE, "columns": ["s"]})
    assert models.auto_index_ddl(TABLE, ["s"], models.AUTO_SLOW_FILTER).endswith('("s", "row_id")')


def test_a_view_s_plan_is_queued_once_a_process_and_never_off_postgresql(monkeypatch):
    from types import SimpleNamespace

    read = []
    monkeypatch.setattr(index_wants, "_ASKED", set())
    monkeypatch.setattr(index_wants, "_plan_wants", lambda *a: read.append(a[:2]))
    pg, lite = (SimpleNamespace(dialect=SimpleNamespace(name=name)) for name in ("postgresql", "sqlite"))
    for statement in ("SELECT 1", "SELECT 1", "SELECT 2"):              # another wrap of the same view: still once
        index_wants.want_plan("v", "Q", statement, {}, 2.0, pg)
    index_wants.want_plan("w", "Q2", "SELECT 3", {}, 2.0, lite)
    for _ in range(50):
        if read:
            break
        import time
        time.sleep(0.02)
    assert read == [("v", "Q")]


VIEW = {"label": "lots", "query": "SELECT a FROM t WHERE a = :k", "limit": 5}


def _display(config, db):
    assert config.execute_reference_view(db, VIEW, {"k": "x", "other": 1}) == (["a"], [[1]])


def _probe(config, db):
    config.execute_candidate_probe(db, VIEW, "a", {"k": "x"}, caps=None)


def _probes(config, db):
    answers, failed = config.execute_candidate_probes(db, VIEW, "a", [{"k": "x"}, {"k": "y"}], caps=None)
    assert failed is None and len(answers) == 2


@pytest.mark.parametrize("read", [_display, _probe, _probes])
@pytest.mark.parametrize("after, asked", [(1e-9, True), (1e9, False), (None, False)])
def test_every_read_of_a_view_asks_only_past_the_grid_s_threshold(monkeypatch, read, after, asked):
    from types import SimpleNamespace

    from chain.enrichment import config
    from parsers import directory_watcher

    wanted, ticks = [], iter(range(100))
    monkeypatch.setattr(config, "time", SimpleNamespace(monotonic=lambda: float(next(ticks))))  # a second a read
    monkeypatch.setattr(config, "_isolated_execute", lambda db, stmt, params: (["a"], (
        [(0, "v", 1, 1), (1, "v", 1, 1)] if "LATERAL" in stmt.text else [("v", 1, 1)] if "__scanned" in stmt.text
        else [(1,)])))
    monkeypatch.setattr(directory_watcher, "grid_auto_index_after", lambda settings=None: after)
    monkeypatch.setattr(index_wants, "want_plan", lambda *a: wanted.append(a))
    bind =SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    read(config, SimpleNamespace(get_bind=lambda: bind))
    assert [(w[0], w[1], w[4], w[5]) for w in wanted] == ([("lots", VIEW["query"], 1.0, bind)] if asked else []), wanted
    if asked and read is _display:
        assert wanted[0][2:4] == (config.REFERENCE_LIMIT_WRAP_SQL.format(query=VIEW["query"]),
                                  {"k": "x", "__enrichment_limit": 5})


# ------------------------------------------------------------------------------------------------- on PostgreSQL
@pytest.fixture
def table(pg_engine, monkeypatch):
    from sqlalchemy import MetaData, text

    from conftest import PG_TEST_SCHEMA

    models.init_dynamic_models({TABLE: ENTRY})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[TABLE].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text('INSERT INTO "%s"."%s" (row_id, business_key_val, k, s, n) '
                          "SELECT 'r' || g, 'K' || g, 'K' || g, md5(g::text), g FROM generate_series(1, 3000) g"
                          % (PG_TEST_SCHEMA, TABLE)))
        conn.execute(text('ANALYZE "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
    try:
        yield pg_engine
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
            conn.execute(text("DELETE FROM database_outbox WHERE event_type = 'INDEX_WANTED'"))


def _statement(where):
    from chain.enrichment import config
    return config.REFERENCE_LIMIT_WRAP_SQL.format(query="SELECT * FROM %s WHERE %s" % (TABLE, where))


def _read_plan(engine, monkeypatch, where, params, caplog):
    """The thread's job, run here: the plan read, each want asked at once."""
    asked = []
    monkeypatch.setattr(index_wants, "want", lambda t, c, w, s, b: asked.append((t, c, w, index_wants.ask(t, c, w, s, b))))
    with caplog.at_level(logging.INFO, logger="Server"):
        index_wants._plan_wants("lots", where, _statement(where), dict(params, __enrichment_limit=100), 2.5, engine)
    return asked


def _waiting(engine):
    import event_constants
    from sqlalchemy import text

    with engine.connect() as conn:
        return [json.loads(p) for (p,) in conn.execute(text(
            "SELECT payload FROM database_outbox WHERE event_type = :t AND processed_chain = false"),
            {"t": event_constants.EVENT_INDEX_WANTED})]


@pytest.mark.pg
def test_a_slow_search_is_asked_built_said_and_then_served(table, monkeypatch, caplog):
    asked = _read_plan(table, monkeypatch, "s ILIKE '%' || :key || '%' AND n = :n", {"key": "abc", "n": 7}, caplog)
    assert asked == [(TABLE, ["s"], "slow search", True), (TABLE, ["n"], "slow filter", True)], asked
    assert [(w["columns"], w["why"]) for w in _waiting(table)] == [(["s"], "slow search"), (["n"], "slow filter")]
    said = []
    built = models.ensure_auto_indexes(table, [(TABLE, ["s"], "slow search")], say=said.append)
    name = models.auto_index_name(TABLE, ["s"], models.AUTO_SLOW_SEARCH)
    assert built == {name: models.INDEX_BUILT}, said
    [row] = [r for r in models.index_states(table, {TABLE: ENTRY}, static=False)["declared"] if r["name"] == name]
    assert (row["source"], row["columns"], row["search"], row["purpose"], row["state"]) == (
        "auto", ["s"], True, "auto (slow search)", models.INDEX_PRESENT)
    assert index_wants.ask(TABLE, ["s"], "slow search", 2.5, table) is False, "the built trigram serves it"
    assert models.ensure_auto_indexes(table, [(TABLE, ["s"], "slow search")], say=said.append) == {}, "built once"
    assert models.search_column_states(table, TABLE, ["s"], {TABLE: ENTRY}) == {"s": "built"}, \
        "a grid search's state counts it, as a sort's counts an automatic sort index"


@pytest.mark.pg
def test_a_search_over_a_number_names_its_column(table):
    """CAST of a number is an expression key (a varchar's folds to the column) - the screen still names the column."""
    models.ensure_auto_indexes(table, [(TABLE, ["n"], "slow search")], say=lambda line: None)
    name = models.auto_index_name(TABLE, ["n"], models.AUTO_SLOW_SEARCH)
    [row] = [r for r in models.index_states(table, {TABLE: ENTRY}, static=False)["declared"] if r["name"] == name]
    assert (row["columns"], row["search"], row["purpose"]) == (["n"], True, "auto (slow search)")
    assert index_wants.ask(TABLE, ["n"], "slow search", 2.5, table) is False


@pytest.mark.pg
def test_a_btree_on_the_column_does_not_serve_a_search(table):
    from sqlalchemy import text

    with table.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text('CREATE INDEX hand_s ON "%s" (s)' % TABLE))
    assert index_wants.ask(TABLE, ["s"], "slow search", 2.5, table) is True
    assert index_wants.ask(TABLE, ["s"], "slow filter", 2.5, table) is False, "it serves the equal one"


@pytest.mark.pg
def test_a_search_counts_toward_the_table_s_cap(table):
    said = []
    models.ensure_auto_indexes(table, [(TABLE, ["s"], "slow search")], say=said.append)
    assert models.ensure_auto_indexes(table, [(TABLE, ["n"], "slow filter")], say=said.append, cap=1) == {}
    assert any("already holds 1 automatic indexes (auto_index_per_table 1)" in line for line in said), said


@pytest.mark.pg
def test_a_candidate_probe_s_lateral_read_asks_for_its_key_column(table, monkeypatch, caplog):
    from sqlalchemy.orm import Session

    from chain.enrichment import config
    from parsers import directory_watcher

    caught = []
    monkeypatch.setattr(directory_watcher, "grid_auto_index_after", lambda settings=None: 1e-9)
    monkeypatch.setattr(index_wants, "want_plan", lambda *a: caught.append(a))
    view = {"label": "by n", "query": "SELECT s FROM %s WHERE n = :n" % TABLE, "limit": 50}
    with Session(bind=table) as db:
        answers, failed = config.execute_candidate_probes(db, view, "s", [{"n": 7}, {"n": 8}], caps=None)
    assert failed is None and [a["scanned"] for a in answers] == [1, 1]
    [(label, query, statement, params, seconds, bind)] = caught
    assert "CROSS JOIN LATERAL" in statement
    asked = []
    monkeypatch.setattr(index_wants, "want", lambda t, c, w, s, b: asked.append((t, c, w, index_wants.ask(t, c, w, s, b))))
    index_wants._plan_wants(label, query, statement, params, seconds, bind)
    assert asked == [(TABLE, ["n"], "slow filter", True)], asked


@pytest.mark.pg
def test_a_short_pattern_and_an_undeclared_table_are_said_not_asked(table, monkeypatch, caplog):
    where = "s ILIKE '%' || :key || '%'"
    monkeypatch.setattr(index_wants, "_ASKED", {("plan", where)})
    asked = _read_plan(table, monkeypatch, where, {"key": "ab"}, caplog)
    assert asked == [] and _waiting(table) == []
    assert any("auto_search_probe (s) not asked for a slow search: the pattern '%ab%' has under 3 characters" in m
               for m in caplog.messages), caplog.messages
    assert ("plan", where) not in index_wants._ASKED, "judged nothing - the next slow read looks again"
    index_wants._ASKED.add(("plan", where))
    assert _read_plan(table, monkeypatch, where, {"key": "abc"}, caplog) == [(TABLE, ["s"], "slow search", True)]
    assert ("plan", where) in index_wants._ASKED, "judged - the view's once is used"
    monkeypatch.delitem(crud.TABLE_CONFIG, TABLE)
    caplog.clear()
    assert _read_plan(table, monkeypatch, "n = :n", {"n": 7}, caplog) == []
    assert any("(n) not asked for a slow filter: not a table the product declares" in m for m in caplog.messages)


@pytest.mark.pg
def test_a_database_without_pg_trgm_says_it_on_the_ask(table, caplog):
    from sqlalchemy import event

    def no_trgm(_conn, _cursor, statement, parameters, _context, _many):
        return statement.replace("extname = 'pg_trgm'", "extname = 'pg_trgm_not_installed'"), parameters

    event.listen(table, "before_cursor_execute", no_trgm, retval=True)
    try:
        with caplog.at_level(logging.INFO, logger="Server"):
            assert index_wants.ask(TABLE, ["s"], "slow search", 2.5, table) is False
            assert index_wants.ask(TABLE, ["n"], "slow filter", 2.5, table) is True, "a filter needs no trigram"
    finally:
        event.remove(table, "before_cursor_execute", no_trgm)
    assert any("is not asked for a slow search: " + models.PG_TRGM_MISSING in m for m in caplog.messages)
    assert [w["why"] for w in _waiting(table)] == ["slow filter"]
