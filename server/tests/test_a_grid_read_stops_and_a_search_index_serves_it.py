# -*- coding: utf-8 -*-
"""총괄 d16033b63 (소유자 「서버가 다 느림 · 아무 일도 못 함」): a search no row matches reads the whole table, and on 4,000,000
rows that held a pool connection and a worker thread while every other request queued. Two answers, landed first:
① a grid read (rows · count · a search) runs under a statement limit (`grid_read_timeout_seconds`, the one SET LOCAL
  seat) and a read past it is answered as what stopped and what to do;
② a table's declared indexes take a search kind - a trigram index over `models.search_text`, the very expression the
  search condition is - so the planner can read it."""
import time

import pytest

from database import crud, models

TABLE = "grid_read_probe"
ENTRY = {"business_key": "k", "composite_key_source": ["k"],
         "column_types": {"k": "string", "n": "number", "v": "string", "t": "datetime"}}
LIMIT = "the limit is grid_read_timeout_seconds in the ingestion settings"


def _held(monkeypatch, state, building=None):
    """The one comparison (`index_states`) answering `state` for every table index - the database's word, not the file's."""
    real = models.index_states

    def held(engine, tables=None, static=True):
        states = real(engine, tables, static)
        for row in states["declared"]:
            row.update(state=state, building=building)
        return states
    monkeypatch.setattr(models, "index_states", held)


# ── ② the declaration ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("item,refused", [
    ({"columns": ["k"], "search": "yes"}, "search must be true or false"),
    ({"columns": ["k"], "search": True, "unique": True}, "never unique"),
    ({"columns": ["t"], "search": True}, "t is a time column"),
    ({"columns": ["updated_at"], "search": True}, "updated_at is a time column"),
])
def test_a_search_index_is_declared_true_or_false_and_never_unique(item, refused):
    _path, sentence = models.table_index_refusal(TABLE, dict(ENTRY, indexes=[item]))
    assert refused in sentence


def test_the_save_takes_what_the_builder_builds_on_a_key_less_table():
    """Both doors one judgment (총괄 ad38ae9c6): business_key_val is on every dynamic table, as row_id is."""
    entry = {"column_types": {"a": "string"},
             "indexes": [{"columns": ["row_id"], "search": True}, {"columns": ["business_key_val"], "search": True}]}
    assert models.table_index_refusal("keyless", entry) is None
    assert models.search_index_refusal(["a"], {"kind": "view", "column_types": {"a": "string"}}) == \
        "a view cannot carry an index"


def test_a_search_index_and_an_ordered_one_on_the_same_column_are_two_indexes():
    entry = dict(ENTRY, indexes=[{"columns": ["k"]}, {"columns": ["k"], "search": True}])
    assert models.table_index_refusal(TABLE, entry) is None
    declared = models.table_declared_indexes({TABLE: entry})
    assert [(name, shape["search"], shape["unique"]) for _t, name, shape in declared] == [
        ("idx_grid_read_probe_k", False, False), ("idx_grid_read_probe_k_search", True, False)]
    entry["indexes"].append({"columns": ["k"], "search": True})
    assert "declared twice" in models.table_index_refusal(TABLE, entry)[1]


def test_a_search_index_is_built_over_the_expression_the_search_reads():
    """The index and the condition come from `search_text` - two spellings and the planner never reads the index."""
    from sqlalchemy import column
    from sqlalchemy.dialects import postgresql

    ddl = models.table_index_ddl({"name": "idx_t_k_search", "table": "t", "columns": ["k", "n"], "search": True,
                                  "unique": False})
    read = str(models.search_text(column("k")).compile(dialect=postgresql.dialect()))
    assert read == "CAST(k AS VARCHAR)"
    assert ddl == ('CREATE INDEX CONCURRENTLY IF NOT EXISTS "idx_t_k_search" ON "t" USING gin '
                   '((CAST(k AS VARCHAR)) gin_trgm_ops, (CAST(n AS VARCHAR)) gin_trgm_ops)')


@pytest.mark.parametrize("f_type,pattern", [("contains", "%K1%"), ("startsWith", "K1%"), ("endsWith", "%K1")])
def test_a_column_filter_s_pattern_reads_the_same_expression(f_type, pattern):
    """The grid's «search» is a column filter (총괄 10-13) - its pattern runs over `search_text`, so the index serves it."""
    from sqlalchemy import Column, Float, MetaData, String, Table
    from sqlalchemy.dialects import postgresql

    from column_filter import get_column_filter_condition

    table = Table("t", MetaData(), Column("k", String), Column("n", Float))
    for name in ("k", "n"):
        said = get_column_filter_condition(table.c, name, {"filterType": "text", "type": f_type, "filter": "K1"})
        sql = str(said.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert sql == "CAST(t.%s AS VARCHAR) ILIKE '%s'" % (name, pattern.replace("%", "%%")), sql   # pyformat


def test_a_column_filter_s_text_form_is_search_text_s(monkeypatch):
    """One author: the expression a search index is built on is the one the filter sends - change it, both change."""
    from sqlalchemy import Column, MetaData, String, Table, func
    from sqlalchemy.dialects import postgresql

    from column_filter import get_column_filter_condition

    monkeypatch.setattr(models, "search_text", lambda column: func.lower(column))
    table = Table("t", MetaData(), Column("k", String))
    said = get_column_filter_condition(table.c, "k", {"filterType": "text", "type": "contains", "filter": "K1"})
    sql = str(said.compile(dialect=postgresql.dialect()))
    assert sql.startswith("lower(t.k) ILIKE"), sql


def test_the_columns_a_filter_narrows_by_a_pattern():
    import json

    from column_filter import pattern_filtered_columns

    model = {"a": {"type": "contains", "filter": "x"}, "b": {"type": "notContains", "filter": "x"},
             "c": {"type": "blank"}, "d": {"filterType": "number", "type": "inRange", "filter": 1, "filterTo": 2},
             "e": {"operator": "OR", "conditions": [{"type": "equals", "filter": "x"}, {"type": "endsWith", "filter": "y"}]},
             "f": {"type": "startsWith"}}
    assert pattern_filtered_columns(json.dumps(model)) == ["a", "e"]
    assert pattern_filtered_columns(None) == [] and pattern_filtered_columns("not json") == []


def test_a_search_index_the_database_cannot_build_is_named_and_not_attempted(monkeypatch):
    """No pg_trgm: the state says what to do, and the builder says it instead of failing a build."""
    owed = {"name": "idx_t_k_search", "table": "t", "columns": ["k"], "search": True, "state": models.INDEX_MISSING,
            "failure": models.PG_TRGM_MISSING, "unbuildable": True, "constraint": False, "source": "table"}
    monkeypatch.setattr(models, "index_states", lambda engine, tables=None: {"declared": [owed], "outside": []})
    built, said = [], []
    monkeypatch.setattr(models, "_build_one", lambda *a, **k: built.append(a) or models.INDEX_BUILT)
    assert models.ensure_model_indexes(None, say=said.append) == {}
    assert built == [] and "pg_trgm" in said[0]


# ── ① a stopped read, said ─────────────────────────────────────────────────────

@pytest.mark.parametrize("q,declared,state,building,message", [
    ("x", [], None, None, "Search stopped after 7 s - add a search index on k in the table's indexes"),
    ("x", [{"columns": ["k"], "search": True}], models.INDEX_PRESENT, None, "Search stopped after 7 s - " + LIMIT),
    ("x", [{"columns": ["k"], "search": True}], models.INDEX_BUILDING, "building - waiting for transactions older than it",
     "Search stopped after 7 s - the search index on k is declared, not built yet (building - waiting for "
     "transactions older than it)"),
    ("x", [{"columns": ["k"], "search": True}], models.INDEX_MISSING, None,
     "Search stopped after 7 s - the search index on k is declared, not built yet (built at the next Reload or restart)"),
])
def test_a_stopped_read_says_what_stopped_and_what_to_do(q, declared, state, building, message, monkeypatch):
    """«Built» is the database's word (총괄 ad38ae9c6) - a declared index still building is not said as built."""
    import main

    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, dict(ENTRY, indexes=declared))
    _held(monkeypatch, state, building)
    said = main.grid_read_stopped(TABLE, q, None, 7.0)
    assert said["reason"] == "grid_read_stopped" and said["message"] == message


def test_a_stopped_read_never_asks_for_an_index_the_builder_cannot_make(monkeypatch):
    import json

    import main

    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, dict(ENTRY))
    said = main.grid_read_stopped(TABLE, None, None, 7.0, json.dumps({"t": {"type": "contains", "filter": "2026"}}))
    assert said["message"] == "Filter stopped after 7 s - " + LIMIT and said["unindexed"] == []
    assert said["search_index"]["t"].startswith("cannot be built (t is a time column")
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, dict(ENTRY, kind="view"))
    said = main.grid_read_stopped(TABLE, None, None, 7.0, json.dumps({"k": {"type": "contains", "filter": "x"}}))
    assert said["search_index"] == {"k": "cannot be built (a view cannot carry an index)"} and said["unindexed"] == []


@pytest.mark.parametrize("asked,limited", [
    ({}, False),
    ({"filters": '{"n": {"filterType": "number", "type": "inRange", "filter": 1, "filterTo": 2}}'}, False),
    ({"filters": '{"v": {"filterType": "text", "type": "contains", "filter": "x"}}'}, True),
    ({"q": "x"}, True),
])
def test_the_limit_holds_a_search_and_a_pattern_filter_only(asked, limited, monkeypatch):
    """The map editor, the R&D board and the admin cards read the same routes with neither (총괄 10-13)."""
    import main
    from database import context
    from parsers import directory_watcher

    monkeypatch.setattr(directory_watcher, "grid_read_timeout", lambda settings=None: 7.0)
    seen = []

    def route(table_name, q=None, cols=None, filters=None, db=None):
        seen.append(context.request_read_seconds.get())
        return "read"
    assert main.grid_read(route)(TABLE, **asked) == "read" and seen == [7.0 if limited else None]


def test_a_cancel_with_the_limit_off_is_said_not_a_500():
    """`grid_read_timeout_seconds` 0 or null and a statement cancelled anyway (pg_cancel_backend, a database limit)."""
    import main

    said = main.grid_read_stopped(TABLE, None, None, None)
    assert said["message"] == "Read was cancelled by the database" and said["seconds"] is None


@pytest.mark.parametrize("filters,declared,message,unindexed", [
    ({"v": {"type": "contains", "filter": "x"}}, [],
     "Filter stopped after 7 s - add a search index on v in the table's indexes", ["v"]),
    ({"k": {"type": "contains", "filter": "x"}}, [{"columns": ["k"], "search": True}],
     "Filter stopped after 7 s - " + LIMIT, []),
])
def test_a_stopped_filter_names_the_columns_it_narrowed_by_a_pattern(filters, declared, message, unindexed,
                                                                      monkeypatch):
    """The grid's «search» is a column filter (총괄 10-13): its stop names the filtered columns no search index covers."""
    import json

    import main

    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, dict(ENTRY, indexes=declared))
    _held(monkeypatch, models.INDEX_PRESENT)
    said = main.grid_read_stopped(TABLE, None, None, 7.0, json.dumps(filters))
    assert said["message"] == message and said.get("unindexed") == unindexed


# ── on PostgreSQL ──────────────────────────────────────────────────────────────

@pytest.fixture
def grid(pg_engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import MetaData, text
    from sqlalchemy.orm import sessionmaker

    import main
    from conftest import PG_TEST_SCHEMA
    from database.database import get_db

    entry = dict(ENTRY, indexes=[{"columns": ["k"], "search": True}])
    models.init_dynamic_models({TABLE: entry})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, entry)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[TABLE].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text('INSERT INTO "%s"."%s" (row_id, business_key_val, k, n, v) '
                          "SELECT 'r' || g, 'K' || g, 'K' || g, g, 'v' FROM generate_series(1, 2000) g"
                          % (PG_TEST_SCHEMA, TABLE)))
    made = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)

    def per_request():                      # as production: a session a request, closed after it
        session = made()
        try:
            yield session
        finally:
            session.close()

    main.app.dependency_overrides[get_db] = per_request
    try:
        with TestClient(main.app) as client:
            yield client, made
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))


@pytest.mark.pg
def test_a_pooled_connection_does_not_keep_a_grid_read_s_limit(pg_engine):
    """`SET LOCAL`: the next request that borrows the same pooled connection reads with no limit of its own - on a
    QueuePool of one, as production pools (the test engine's NullPool would hide a plain SET, 총괄 ad38ae9c6)."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import QueuePool

    from database.context import read_limit

    pooled = create_engine(pg_engine.url, poolclass=QueuePool, pool_size=1, max_overflow=0)
    made = sessionmaker(bind=pooled)
    try:
        with made() as session:
            with read_limit(0.25):
                pid = session.execute(text("SELECT pg_backend_pid()")).scalar()
                assert session.execute(text("SHOW statement_timeout")).scalar() == "250ms"
            session.commit()
        with made() as session:
            assert session.execute(text("SELECT pg_backend_pid()")).scalar() == pid
            assert session.execute(text("SHOW statement_timeout")).scalar() != "250ms"
    finally:
        pooled.dispose()


@pytest.mark.pg
def test_the_limit_is_the_transaction_s_only_inside_a_grid_read(grid):
    from sqlalchemy import text

    from database.context import read_limit

    _client, made = grid
    session = made()
    try:
        with read_limit(0.25):
            assert session.execute(text("SHOW statement_timeout")).scalar() == "250ms"
        session.commit()
        assert session.execute(text("SHOW statement_timeout")).scalar() != "250ms"
    finally:
        session.close()


@pytest.mark.pg
def test_a_read_past_the_limit_is_stopped_said_and_the_next_one_is_clean(grid, monkeypatch):
    from sqlalchemy import text

    import main
    from parsers import directory_watcher

    client, _made = grid
    monkeypatch.setattr(directory_watcher, "grid_read_timeout", lambda settings=None: 0.05)
    slow = main.apply_column_filters
    monkeypatch.setattr(main, "apply_column_filters", lambda query, *a, **k: slow(query, *a, **k).filter(
        text("(SELECT true FROM pg_sleep(0.5))")))
    for path in ("/tables/%s/data?q=K1" % TABLE, "/tables/%s/data/count?q=K1" % TABLE):
        answer = client.get(path)
        assert answer.status_code == 503 and answer.json()["detail"]["reason"] == "grid_read_stopped"
    filtered = client.get("/tables/%s/data/count" % TABLE,
                          params={"filters": '{"v": {"filterType": "text", "type": "contains", "filter": "x"}}'})
    assert filtered.status_code == 503 and filtered.json()["detail"]["message"] == (
        "Filter stopped after 0.05 s - add a search index on v in the table's indexes"), filtered.text
    plain = client.get("/tables/%s/data/count" % TABLE)                   # neither: outside the limit (총괄 10-13)
    for _ in range(50):                                                     # the table whole: its worker counts (소유자 ㄱ)
        if not plain.json().get("counting"):
            break
        time.sleep(0.1)
        plain = client.get("/tables/%s/data/count" % TABLE)
    assert plain.status_code == 200 and plain.json()["total"] == 2000, plain.text
    monkeypatch.setattr(directory_watcher, "grid_read_timeout", lambda settings=None: None)
    monkeypatch.setattr(main, "apply_column_filters", lambda query, *a, **k: slow(query, *a, **k).filter(
        text("(SELECT pg_cancel_backend(pg_backend_pid())) AND (SELECT true FROM pg_sleep(0.5))")))
    cancelled = client.get("/tables/%s/data?defer_total=true" % TABLE)              # a page: the count above is cached
    assert cancelled.status_code == 503 and cancelled.json()["detail"]["message"] == \
        "Read was cancelled by the database", cancelled.text
    monkeypatch.setattr(main, "apply_column_filters", slow)
    assert client.get("/tables/%s/data/count?q=K1" % TABLE).json()["total"] == 1111      # K1 · K10-19 · K100-199 · K1000-1999


@pytest.mark.pg
def test_a_declared_search_index_is_read_by_the_search_and_said_in_the_answer(grid, pg_engine):
    from sqlalchemy import text

    import main
    from database.database import SessionLocal  # noqa: F401 - the product's engine is not the test's

    client, made = grid
    assert client.get("/tables/%s/data?q=K17" % TABLE).json()["search_index"] == {
        "k": "declared, not built yet (built at the next Reload or restart)"}
    built = models.ensure_model_indexes(pg_engine, tables={TABLE: crud.TABLE_CONFIG[TABLE]}, say=lambda line: None)
    assert built == {"idx_grid_read_probe_k_search": models.INDEX_BUILT}
    session = made()
    try:
        session.execute(text("SET LOCAL enable_seqscan = off"))
        query, _key = main.narrowed_table_query(session, TABLE, models.DYNAMIC_TABLES[TABLE], q="K17", cols="k")
        sql = str(query.statement.compile(dialect=pg_engine.dialect, compile_kwargs={"literal_binds": True}))
        plan = "\n".join(row[0] for row in session.execute(text("EXPLAIN " + sql)))
    finally:
        session.close()
    assert "idx_grid_read_probe_k_search" in plan
    assert client.get("/tables/%s/data?q=K17" % TABLE).json()["search_index"] == {"k": "built"}
    filtered = client.get("/tables/%s/data" % TABLE, params={
        "filters": '{"k": {"filterType": "text", "type": "contains", "filter": "K17"}, '
                   '"v": {"filterType": "text", "type": "startsWith", "filter": "v"}}'}).json()
    assert filtered["search_index"] == {"k": "built", "v": "not declared"} and len(filtered["data"]) == 111   # K17 · K170-179 · K1700-1799


@pytest.mark.pg
def test_a_database_without_pg_trgm_is_named_on_the_search_index_it_owes(grid, pg_engine):
    """The comparison reads pg_extension; here the database answers 「not installed」 at the statement boundary."""
    from sqlalchemy import event

    def owed():
        rows = models.index_states(pg_engine, tables={TABLE: crud.TABLE_CONFIG[TABLE]})["declared"]
        return [row["failure"] for row in rows if row["name"] == "idx_grid_read_probe_k_search"]

    def no_trgm(_conn, _cursor, statement, parameters, _context, _many):
        return statement.replace("extname = 'pg_trgm'", "extname = 'pg_trgm_not_installed'"), parameters

    assert owed() == [None]
    event.listen(pg_engine, "before_cursor_execute", no_trgm, retval=True)
    try:
        assert owed() == [models.PG_TRGM_MISSING]
    finally:
        event.remove(pg_engine, "before_cursor_execute", no_trgm)


def test_a_read_s_comparison_reads_its_table_alone():
    """A grid read asks about one table: no static model's rows and no ledger's (총괄 ad38ae9c6, per request)."""
    from sqlalchemy import create_engine

    entry = dict(ENTRY, indexes=[{"columns": ["k"], "search": True}])
    states = models.index_states(create_engine("sqlite://"), {TABLE: entry}, static=False)
    assert [(row["source"], row["name"]) for row in states["declared"]] == [("table", "idx_grid_read_probe_k_search")]


@pytest.mark.pg
def test_a_time_column_s_search_index_written_by_hand_is_said_and_not_built(grid, pg_engine, monkeypatch):
    """The save refuses it; a table_config.json edited by hand still gets the same sentence, and no build."""
    entry = dict(ENTRY, indexes=[{"columns": ["t"], "search": True}])
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, entry)
    said = []
    assert models.ensure_model_indexes(pg_engine, tables={TABLE: entry}, say=said.append) == {}
    assert any("idx_grid_read_probe_t_search on grid_read_probe is not built: t is a time column" in line
               for line in said), said
