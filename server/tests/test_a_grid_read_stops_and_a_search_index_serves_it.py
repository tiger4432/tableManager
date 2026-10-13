# -*- coding: utf-8 -*-
"""총괄 d16033b63 (소유자 「서버가 다 느림 · 아무 일도 못 함」): a search no row matches reads the whole table, and on 4,000,000
rows that held a pool connection and a worker thread while every other request queued. Two answers, landed first:
① a grid read (rows · count · a search) runs under a statement limit (`grid_read_timeout_seconds`, the one SET LOCAL
  seat) and a read past it is answered as what stopped and what to do;
② a table's declared indexes take a search kind - a trigram index over `models.search_text`, the very expression the
  search condition is - so the planner can read it."""
import pytest

from database import crud, models

TABLE = "grid_read_probe"
ENTRY = {"business_key": "k", "composite_key_source": ["k"],
         "column_types": {"k": "string", "n": "number", "v": "string"}}


# ── ② the declaration ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("item,refused", [
    ({"columns": ["k"], "search": "yes"}, "search must be true or false"),
    ({"columns": ["k"], "search": True, "unique": True}, "never unique"),
])
def test_a_search_index_is_declared_true_or_false_and_never_unique(item, refused):
    _path, sentence = models.table_index_refusal(TABLE, dict(ENTRY, indexes=[item]))
    assert refused in sentence


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


def test_a_search_index_the_database_cannot_build_is_named_and_not_attempted(monkeypatch):
    """No pg_trgm: the state says what to do, and the builder says it instead of failing a build."""
    owed = {"name": "idx_t_k_search", "table": "t", "columns": ["k"], "search": True, "state": models.INDEX_MISSING,
            "failure": models.PG_TRGM_MISSING, "constraint": False, "source": "table"}
    monkeypatch.setattr(models, "index_states", lambda engine, tables=None: {"declared": [owed], "outside": []})
    built, said = [], []
    monkeypatch.setattr(models, "_build_one", lambda *a, **k: built.append(a) or models.INDEX_BUILT)
    assert models.ensure_model_indexes(None, say=said.append) == {}
    assert built == [] and "pg_trgm" in said[0]


# ── ① a stopped read, said ─────────────────────────────────────────────────────

@pytest.mark.parametrize("q,declared,message", [
    ("x", [], "Search stopped after 7 s - add a search index on k in the table's indexes"),
    ("x", [{"columns": ["k"], "search": True}],
     "Search stopped after 7 s - the limit is grid_read_timeout_seconds in the ingestion settings"),
    (None, [], "Read stopped after 7 s - the limit is grid_read_timeout_seconds in the ingestion settings"),
])
def test_a_stopped_read_says_what_stopped_and_what_to_do(q, declared, message, monkeypatch):
    import main

    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, dict(ENTRY, indexes=declared))
    said = main.grid_read_stopped(TABLE, q, None, 7.0)
    assert said["reason"] == "grid_read_stopped" and said["message"] == message


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
    monkeypatch.setattr(main, "apply_column_filters", slow)
    assert client.get("/tables/%s/data/count?q=K1" % TABLE).json()["total"] == 1111      # K1 · K10-19 · K100-199 · K1000-1999


@pytest.mark.pg
def test_a_declared_search_index_is_read_by_the_search_and_said_in_the_answer(grid, pg_engine):
    from sqlalchemy import text

    import main
    from database.database import SessionLocal  # noqa: F401 - the product's engine is not the test's

    client, made = grid
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
    assert client.get("/tables/%s/data?q=K17" % TABLE).json()["search_index"] == {"k": True}


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
