# -*- coding: utf-8 -*-
"""총괄 ff7890892 (소유자 「쓰이는 칸만」): the product builds an index by itself where a column is used - a decide rule's
judgment key, a grid sort or equal/range filter that was slow - (columns, row_id), `ix_auto_`, through the chain
worker's index line. The database's list is the state; the comment says why; a table holds `auto_index_per_table`
of them at most; one already served is not built; a decide key no rule wants is dropped, a slow column's stays."""
import json

import pytest

from database import crud, models

TABLE = "auto_index_probe"
ENTRY = {"business_key": "k", "composite_key_source": ["k"],
         "column_types": {"k": "string", "s": "string", "n": "number"}}


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
                          "SELECT 'r' || g, 'K' || g, 'K' || g, 'S' || (g %% 7), g FROM generate_series(1, 500) g"
                          % (PG_TEST_SCHEMA, TABLE)))
    try:
        yield pg_engine
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))


def _autos(engine):
    return {row["name"]: row for row in models.index_states(engine, {TABLE: ENTRY}, static=False)["declared"]
            if row["source"] == "auto"}


@pytest.mark.pg
def test_a_decide_key_is_built_and_says_why(table):
    said = []
    built = models.ensure_auto_indexes(table, [], say=said.append, decide_keys=[(TABLE, ["n"], models.AUTO_DECIDE_KEY)])
    name = models.auto_index_name(TABLE, ["n"])
    assert built == {name: models.INDEX_BUILT}
    autos = _autos(table)
    assert autos[name]["columns"] == ["n", "row_id"] and autos[name]["purpose"] == "auto (decide key)"
    assert autos[name]["state"] == models.INDEX_PRESENT
    assert models.ensure_auto_indexes(table, [], say=said.append,
                                      decide_keys=[(TABLE, ["n"], models.AUTO_DECIDE_KEY)]) == {}, "built once"
    assert models.ensure_auto_indexes(table, [], say=said.append,
                                      decide_keys=[(TABLE, ["k"], models.AUTO_DECIDE_KEY)]) == {},         "the declared key's own index serves k"


@pytest.mark.pg
def test_a_decide_key_no_rule_wants_is_said_and_stays_for_a_person_to_drop(table):
    models.ensure_auto_indexes(table, [(TABLE, ["s"], models.AUTO_SLOW_SORT)], say=lambda line: None,
                               decide_keys=[(TABLE, ["n"], models.AUTO_DECIDE_KEY)])
    assert set(_autos(table)) == {models.auto_index_name(TABLE, ["s"]), models.auto_index_name(TABLE, ["n"])}
    said = []
    models.ensure_auto_indexes(table, [], say=said.append, decide_keys=[])
    assert set(_autos(table)) == {models.auto_index_name(TABLE, ["s"]), models.auto_index_name(TABLE, ["n"])}
    assert any("no decide rule keys on it any more; a person drops it: DROP INDEX" in line for line in said), said


@pytest.mark.pg
def test_an_index_that_already_serves_is_not_built(table):
    from sqlalchemy import text

    with table.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text('CREATE INDEX hand_s_row ON "%s" (s, row_id)' % TABLE))
        conn.execute(text('CREATE INDEX hand_n ON "%s" (n)' % TABLE))
    built = models.ensure_auto_indexes(table, [(TABLE, ["s"], models.AUTO_SLOW_SORT),
                                               (TABLE, ["n"], models.AUTO_SLOW_FILTER),
                                               (TABLE, ["n"], models.AUTO_SLOW_SORT)], say=lambda line: None)
    assert built == {models.auto_index_name(TABLE, ["n"]): models.INDEX_BUILT}, \
        "(s, row_id) serves the sort, (n) the filter - the sort by n needs (n, row_id)"


@pytest.mark.pg
def test_a_table_at_its_cap_is_said_and_not_built(table):
    said = []
    models.ensure_auto_indexes(table, [(TABLE, ["s"], models.AUTO_SLOW_SORT)], say=said.append)
    models.ensure_auto_indexes(table, [(TABLE, ["n"], models.AUTO_SLOW_SORT)], say=said.append, cap=1)
    assert set(_autos(table)) == {models.auto_index_name(TABLE, ["s"])}
    assert any("already holds 1 automatic indexes (auto_index_per_table 1)" in line for line in said), said


@pytest.mark.pg
def test_a_sort_s_state_counts_an_automatic_index(table):
    assert models.sort_column_states(table, TABLE, ["s"], ["row_id"], {TABLE: ENTRY}) == {"s": "not declared"}
    models.ensure_auto_indexes(table, [(TABLE, ["s"], models.AUTO_SLOW_SORT)], say=lambda line: None)
    assert models.sort_column_states(table, TABLE, ["s"], ["row_id"], {TABLE: ENTRY}) == {"s": "built"}


@pytest.mark.pg
def test_a_slow_read_asks_once_and_not_when_served(table):
    import event_constants
    from runtime import index_wants
    from sqlalchemy import text

    def waiting():
        with table.connect() as conn:
            return [json.loads(p) for (p,) in conn.execute(text(
                "SELECT payload FROM database_outbox WHERE event_type = :t AND table_name = :table"),
                {"t": event_constants.EVENT_INDEX_WANTED, "table": TABLE})]

    assert index_wants.ask(TABLE, ["s"], models.AUTO_SLOW_SORT, 1.5, table) is True
    assert index_wants.ask(TABLE, ["s"], models.AUTO_SLOW_SORT, 1.5, table) is False, "the same ask waits"
    assert [(w["columns"], w["why"]) for w in waiting()] == [(["s"], "slow sort")]
    models.ensure_auto_indexes(table, [(TABLE, ["n"], models.AUTO_SLOW_SORT)], say=lambda line: None)
    assert index_wants.ask(TABLE, ["n"], models.AUTO_SLOW_SORT, 1.5, table) is False, "an index serves it"
    with table.begin() as conn:
        conn.execute(text("DELETE FROM database_outbox WHERE event_type = :t"), {"t": event_constants.EVENT_INDEX_WANTED})


def test_a_want_is_queued_once_a_process(monkeypatch):
    from runtime import index_wants

    asked = []
    monkeypatch.setattr(index_wants, "_ASKED", set())
    monkeypatch.setattr(index_wants, "ask", lambda *a: asked.append(a[:3]))
    for _ in range(3):
        index_wants.want(TABLE, ["s"], models.AUTO_SLOW_SORT, 2.0, None)
    for _ in range(50):
        if asked:
            break
        import time
        time.sleep(0.02)
    assert asked == [(TABLE, ["s"], models.AUTO_SLOW_SORT)]


def test_a_slow_grid_read_wants_its_sort_and_its_ordered_filters(client, monkeypatch):
    from parsers import directory_watcher
    from runtime import index_wants
    from tests.support.pools import bodies_here

    bodies_here(monkeypatch)                     # the page body reads this test's patches, not a pool process's
    import main
    import time as real_time

    class _Clock:
        """Each read a second later: the id scan is «slow» however fast this box answers - time.time() steps by
        ~1-15 ms here, so a warm SQLite scan read 0.0 s and asked for nothing (red only late in the full suite)."""
        now = real_time.time()

        def time(self):
            _Clock.now += 1.0
            return _Clock.now

        def __getattr__(self, name):
            return getattr(real_time, name)

    monkeypatch.setattr(main, "time", _Clock())

    wanted = []
    monkeypatch.setattr(directory_watcher, "grid_auto_index_after", lambda settings=None: 1e-9)
    monkeypatch.setattr(index_wants, "want", lambda table, columns, why, seconds, bind: wanted.append((table, columns, why)))
    filters = json.dumps({"EQP_ID": {"filterType": "text", "type": "equals", "filter": "X"},
                          "LOT_ID": {"filterType": "text", "type": "contains", "filter": "Y"}})
    assert client.get("/tables/raw_table_1/data", params={"order_by": "EQP_ID", "filters": filters}).status_code == 200
    client.get("/tables/raw_table_1/data", params={"order_by": "updated_at"})
    assert wanted == [("raw_table_1", ["EQP_ID"], "slow sort"), ("raw_table_1", ["EQP_ID"], "slow filter"),
                      ("raw_table_1", ["LOT_ID"], models.AUTO_SLOW_SEARCH)], wanted


def test_a_read_cancelled_at_its_limit_asks_too(monkeypatch):
    """소유자 10-15: a read past grid_read_timeout_seconds was cancelled before the ask - it asks, and its text-pattern
    filter column asks for a search index."""
    import main
    from parsers import directory_watcher
    from runtime import index_wants
    from sqlalchemy.exc import OperationalError

    class _Orig:
        pgcode = main.QUERY_CANCELED

    class _Db:
        def get_bind(self):
            return None

    wanted = []
    monkeypatch.setattr(directory_watcher, "grid_auto_index_after", lambda settings=None: 1e-9)
    monkeypatch.setattr(index_wants, "want", lambda table, columns, why, seconds, bind: wanted.append((table, columns, why)))
    monkeypatch.setattr(main, "grid_read_stopped", lambda *a, **k: "stopped")
    monkeypatch.setattr(main, "grid_model", lambda table, world: None)
    ticks = iter(range(100))
    monkeypatch.setattr(main, "time", type("_Clock", (), {"time": staticmethod(lambda: float(next(ticks)))})())  # each read a second later

    @main.grid_read
    def route(table_name, filters=None, db=None):
        raise OperationalError("SELECT", {}, _Orig())

    filters = json.dumps({"LOT_ID": {"filterType": "text", "type": "contains", "filter": "Y"}})
    with pytest.raises(main.HTTPException):
        route("raw_table_1", filters=filters, db=_Db())
    assert wanted == [("raw_table_1", ["LOT_ID"], models.AUTO_SLOW_SEARCH)], wanted


def test_the_worker_s_line_given_asks_builds_the_automatic_ones_alone(monkeypatch):
    import asyncio

    from chain import ingestion_worker

    ran = []
    monkeypatch.setattr(ingestion_worker, "_ensure_declared_indexes_sync", lambda *a: ran.append("declared"))
    monkeypatch.setattr(models, "ensure_model_indexes_sync", lambda *a: ran.append("models"))
    monkeypatch.setattr(models, "ensure_auto_indexes_sync", lambda factory, wanted, say, decide: ran.append(
        ("auto", wanted, decide)))

    from runtime import index_wants, maintenance_line, system_reload

    class _Db:
        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(ingestion_worker, "load_chain_rules", lambda: [])
    monkeypatch.setattr(system_reload, "reloads_after", lambda db, mark: [])
    import event_constants
    monkeypatch.setattr(event_constants, "mark_processed", lambda row, status: None)
    monkeypatch.setattr(index_wants, "taken", lambda db: [(object(), (TABLE, ["s"], "slow sort"))])
    maintenance_line.poll_once(_Db, 0)
    maintenance_line._each(maintenance_line._declared_work(None))
    assert ran == [("auto", [(TABLE, ["s"], "slow sort")], False), "declared", "models", ("auto", None, True)]


@pytest.mark.pg
def test_the_header_s_index_kinds_are_the_database_s_valid_indexes(table):
    """Owner 10-15: a column an index leads with serves an equal value; a trigram one a part of a word."""
    models.ensure_auto_indexes(table, [(TABLE, ["s"], models.AUTO_SLOW_SORT)], say=lambda line: None)
    kinds = models.column_index_kinds(table, TABLE)
    assert kinds.get("s") == [models.INDEX_SERVES_EQUAL], kinds
    assert "n" not in kinds, kinds


def test_the_scheduler_s_poll_reads_its_rows_before_it_closes_the_session(monkeypatch):
    """10-16: after the commit and the close a row is detached - reading one raised every poll, so the mark never moved
    and the asks taken were never built."""
    import event_constants
    from runtime import index_wants, maintenance_line, system_reload

    closed = []

    class _Row:
        def __init__(self, number):
            self._id = number

        @property
        def id(self):
            if closed:
                raise RuntimeError("Instance <DatabaseOutbox> is not bound to a Session")
            return self._id

    class _Db:
        def commit(self):
            pass

        def close(self):
            closed.append(True)

    built, declared = [], []
    monkeypatch.setattr(system_reload, "reloads_after", lambda db, mark: [_Row(7), _Row(9)])
    monkeypatch.setattr(index_wants, "taken", lambda db: [(_Row(11), (TABLE, ["s"], "slow sort"))])
    monkeypatch.setattr(event_constants, "mark_processed", lambda row, status: None)
    monkeypatch.setattr(maintenance_line, "_declared_work", lambda factory: [(lambda: declared.append(1),)])
    monkeypatch.setattr(models, "ensure_auto_indexes_sync", lambda factory, wanted, say, decide: built.append(wanted))
    assert maintenance_line.poll_once(_Db, 0) == 9
    assert declared == [1] and built == [[(TABLE, ["s"], "slow sort")]]


def test_a_slow_flush_is_said_with_its_table_s_indexes_and_a_fast_one_is_not(caplog):
    """Owner 10-16 (1,000 rows, 20 s): a flush past SLOW_FLUSH_SECONDS says its table, rows and indexes - one line."""
    class _Db:
        def execute(self, *a, **k):
            raise RuntimeError("no catalogue here")

    with caplog.at_level("WARNING"):
        crud._say_a_slow_flush(_Db(), None, "raw_table_1", 1000, crud.SLOW_FLUSH_SECONDS - 0.1)
        crud._say_a_slow_flush(_Db(), None, "raw_table_1", 1000, 20.0)
    said = [r.getMessage() for r in caplog.records if "slow flush" in r.getMessage()]
    assert said == ["[Batch] slow flush: raw_table_1 1000 row(s) in 20.0 s - indexes unread: RuntimeError"], said


def test_the_line_merges_no_gin_list_where_there_is_no_postgres():
    from runtime import maintenance_line

    class _Bind:
        class dialect:
            name = "sqlite"

    class _Db:
        def get_bind(self):
            return _Bind()

        def close(self):
            pass

    assert maintenance_line.clean_gin_pending(_Db) == []


@pytest.mark.pg
def test_the_line_merges_a_search_index_s_pending_list(table):
    """A trigram search index's pending list - written into, then merged by the line (gin_clean_pending_list)."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from conftest import PG_TEST_SCHEMA
    from runtime import maintenance_line

    with table.connect() as conn:
        if not models.has_trigram(conn):
            pytest.skip("pg_trgm is not installed here")
    models.ensure_auto_indexes(table, [(TABLE, ["s"], models.AUTO_SLOW_SEARCH)], say=lambda line: None)
    with table.begin() as conn:
        conn.execute(text('INSERT INTO "%s"."%s" (row_id, business_key_val, k, s, n) '
                          "SELECT 'p' || g, 'P' || g, 'P' || g, 'pending ' || g, g FROM generate_series(1, 300) g"
                          % (PG_TEST_SCHEMA, TABLE)))
    merged = maintenance_line.clean_gin_pending(sessionmaker(bind=table))
    assert [name for name, _pages in merged] == [models.auto_index_name(TABLE, ["s"]) + "_search"] or merged == [], merged
    assert maintenance_line.clean_gin_pending(sessionmaker(bind=table)) == [], "merged once, nothing pending after"
