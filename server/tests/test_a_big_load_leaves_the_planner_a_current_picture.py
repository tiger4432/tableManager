# -*- coding: utf-8 -*-
"""큰 적재 뒤 통계와, 선언만 되고 없던 인덱스 (S-124, 판정 09-10 13:05).

🔴 WHAT WAS MEASURED. After a 440,000-row load the grid's page query spent 0.7 s choosing
a page of ids. Nothing was broken: the table HAD the index, and the planner was costing the
query against statistics that describe the table as it was BEFORE the load, so it chose a
sequential scan and a sort over an index it already had.

⛔ SO THE FIX IS NOT A SECOND INDEX. It is two things the system should not need a person
to remember: re-analyse a table after a load big enough to have moved it, and build - on a
table that already exists - the indexes the model declares, because `create_all` adds them
only while it is creating the table and an older relation never got them.

⚠️ 「사람이 기억해야 하는 절차는 구멍이다」. Both halves work until the day somebody is
busy, which is the day a large load happens.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import models                                            # noqa: E402
from parsers import directory_watcher as dw                            # noqa: E402


# ── the indexes a model declares and a table may lack ────────────────────────

def test_both_declared_indexes_are_asked_for():
    """⚠️ BOTH, THOUGH ONE IS A PREFIX OF THE OTHER. They are declared together because the
    page query orders by both columns; the migration that retires prefix-redundant indexes
    states why such a pair is kept, so an ensure building one of them would be a third
    opinion about the same declaration."""
    built = dict(models.dynamic_table_index_ddls("some_table", {}))

    assert set(built) == {"ix_some_table_updated_at", "idx_some_table_updated"}
    assert '("updated_at")' in built["ix_some_table_updated_at"]
    assert '("updated_at", "row_id")' in built["idx_some_table_updated"]
    for statement in built.values():
        assert "CONCURRENTLY" in statement and "IF NOT EXISTS" in statement


def test_a_view_is_asked_for_nothing():
    assert models.dynamic_table_index_ddls("v", {"kind": "view"}) == []
    assert models.dynamic_table_index_ddls("", {}) == []


def test_the_count_is_what_was_built_and_not_what_was_attempted():
    """🔴 THE LINE THIS FIXES SAID `built 68` ON EVERY BOOT (caught by this round's own
    gate). `IF NOT EXISTS` succeeds loudly on an index that is already there, so a builder
    reporting "the statement ran" made a second boot announce sixty-eight fresh indexes and
    issue sixty-eight pointless CONCURRENTLY builds. A line that reads the same whether or
    not anything happened is the log equivalent of no line at all."""
    attempted = []

    def _fake(engine, name, statement, what):
        attempted.append(name)
        # 🔴 THREE STATES, NOT A TRUTH VALUE, and the log proved twice in one day why:
        # `True` meaning "the statement ran" announced sixty-eight indexes nobody built,
        # and `False` meaning "already there" made a caller print COULD NOT BE ENSURED
        # about an index that exists. Both false, in opposite directions, from one bit.
        return (models.INDEX_BUILT if name.endswith("_updated")
                else models.INDEX_PRESENT)

    original = models._ensure_one_index
    models._ensure_one_index = _fake
    try:
        created = models.ensure_dynamic_table_indexes(
            object(), config={"t": {}, "v": {"kind": "view"}})
    finally:
        models._ensure_one_index = original

    assert created == ["idx_t_updated"]
    assert attempted == ["ix_t_updated_at", "idx_t_updated"], attempted


def test_every_caller_of_the_builder_speaks_the_same_three_words():
    """⛔ FOUR CALLERS, ONE VOCABULARY. The states exist because a boolean had two things
    to say and one bit to say them with; a caller left reading it as a truth value is the
    regression that shipped a `COULD NOT BE ENSURED` line about an index that exists."""
    import inspect

    from chain import ingestion_worker as worker

    assert {models.INDEX_BUILT, models.INDEX_PRESENT,
            models.INDEX_FAILED} == {"built", "present", "failed"}

    body = inspect.getsource(worker._ensure_human_claims_index_sync)
    assert "models.INDEX_BUILT" in body and "models.INDEX_PRESENT" in body, body[:400]

    for name in ("ensure_dynamic_table_indexes", "ensure_alignment_decision_key_indexes",
                 "ensure_map_key_indexes"):
        source = inspect.getsource(getattr(models, name))
        assert "== INDEX_BUILT" in source, (name, source[:400])


def test_the_ensure_survives_a_database_that_refuses():
    """A boot that dies on an index build is a worse outage than a missing index."""
    class _Refuses:
        def connect(self):
            raise RuntimeError("no database here")

    assert models.ensure_dynamic_table_indexes(_Refuses(), config={"t": {}}) == []


def test_the_boot_sequence_calls_it():
    """🔴 착지는 배선이 아니다 — the check every ensure in this file needed, for the reason
    the decision-key one proved: wired only into a config reload, a restarted deployment
    comes up without the index and nothing says so."""
    import inspect

    from chain import ingestion_worker as worker

    body = inspect.getsource(worker.start_chain_ingestion_worker)
    assert "_ensure_dynamic_table_indexes_sync" in body, body[:400]
    assert hasattr(worker, "_ensure_dynamic_table_indexes_sync")


# ── the statistics a load leaves behind ──────────────────────────────────────

def test_the_threshold_is_declared_and_has_a_default_that_changes_nothing_small():
    """Under the threshold nothing extra runs, so the ordinary drip of small files costs
    what it costs today."""
    assert dw.DEFAULT_ANALYZE_AFTER_ROWS == 10000
    assert dw.analyze_after_rows() >= 0


def test_a_small_load_is_left_alone(monkeypatch):
    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 10000)
    called = []
    monkeypatch.setattr(dw, "SessionLocal", lambda: called.append(1))

    assert dw._analyze_after_load("t", 9999) is False
    assert called == []


def test_it_can_be_turned_off_by_declaration(monkeypatch):
    """⚠️ ZERO IS OFF, not "every load". An operator who has autovacuum tuned should be
    able to say so without editing code."""
    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 0)
    called = []
    monkeypatch.setattr(dw, "SessionLocal", lambda: called.append(1))

    assert dw._analyze_after_load("t", 10_000_000) is False
    assert called == []


def test_a_failure_to_re_analyse_never_takes_the_load_down(monkeypatch):
    """🔴 THE ROWS ARE ALREADY DURABLE WHEN THIS RUNS. Letting a statistics failure escape
    would turn a slower next query into a file reported FAILED - a small cost traded for a
    large lie."""
    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 10)

    class _Boom:
        def connection(self):
            raise RuntimeError("no database here")

        def close(self):
            pass

    monkeypatch.setattr(dw, "SessionLocal", lambda: _Boom())

    assert dw._analyze_after_load("t", 20000) is False


def test_the_load_path_asks_for_it_after_the_last_chunk():
    """착지는 배선이 아니다, again: the seat is the end of the file's own loop, after the
    rows are committed, and not a runbook."""
    import inspect

    body = inspect.getsource(dw.IngestionHandler._send_to_upsert)
    assert "_analyze_after_load(t_name, processed_rows)" in body, body[-1500:]


# ── the always-on timing line must not carry what a person typed ─────────────

def test_the_line_counts_filtered_columns_and_never_reads_their_values():
    """🔴 WHAT THE LINE COULD NOT SHOW (S-123 보강, 09-10 14:19). The owner read
    `ID Scan 0.7 s` with `order=updated_at, q=-` and it had no way to say whether a column
    filter was in play or a target row was being hunted - both change which plan the id
    query gets, so a reader was comparing two requests that were not the same request.

    ⛔ THE COUNT, NEVER THE FILTER. `filters` carries what a person typed; how MANY columns
    are constrained is the shape of the query, which is what a plan question needs.
    """
    import main

    assert main._filtered_column_count(None) == 0
    assert main._filtered_column_count("") == 0
    assert main._filtered_column_count(
        '{"a":{"filter":"secret"},"b":{"filter":"also secret"}}') == 2
    assert main._filtered_column_count({"a": 1}) == 1


def test_a_malformed_filter_gives_a_number_rather_than_a_five_hundred():
    """⚠️ THIS RUNS BESIDE A LOG LINE. A request that was otherwise fine must not fail
    because its instrument could not parse something - the same rule the ingestion pace
    follows, where a settings typo runs at full speed with a warning rather than stopping
    the load."""
    import main

    assert main._filtered_column_count("not json at all") == 0
    assert main._filtered_column_count("[1, 2, 3]") == 0
    assert main._filtered_column_count(object()) == 0


def test_the_timing_line_carries_the_shape_and_not_the_content():
    import inspect

    import main

    body = inspect.getsource(main.get_table_data)
    assert "filters={_filtered_column_count(filters)}" in body, body[-1400:]
    assert "target={'set' if target_row_id else '-'}" in body, body[-1400:]
    assert "filters={filters}" not in body, "the filter object must never reach the line"


def test_the_timing_line_says_whether_a_search_was_set_and_never_what_it_was():
    """🔴 THE LINE IS ALWAYS ON NOW, so `q` would put user-typed values in a permanent
    file. 「payload 본문 로그 금지」 is about content a person supplied, and a search box is
    that even though it is not a payload body. What a diagnosis needs is whether a filter
    was in play."""
    import inspect

    import main

    body = inspect.getsource(main.get_table_data)
    # ⚰️ THE FLAG GREW A NUMBER (S-125, 판정 255). `set` alone could not say WHICH scope
    # answered, and the scope is now declarable - so two searches of the same table could
    # build 3 arms or 31 and read identically here. The term itself still never appears.
    assert "q={'set/' + str(search_scope.get('arms', 0)) if q else '-'}" in body, body[-1400:]
    assert "q={q}" not in body


def test_the_decorator_is_attached_to_the_route_and_not_to_a_helper(caplog):
    """🔴🔴 THE REGRESSION THIS COMMIT REPAIRS, PINNED AS A PROPERTY (판정 09-10 14:34).

    A helper added between `@app.get("/tables/{table_name}/data")` and `def get_table_data`
    registered THE HELPER as the route. Its `filters` argument has no default, so FastAPI
    made `filters` a REQUIRED query parameter and every ordinary grid request - which sends
    none - came back 422. The whole table view was blank on a running deployment.

    ⛔ ASSERTED ON THE BINDING, NOT ON ADJACENCY. 「the next line is `def get_table_data`」
    would be a proxy: it passes for any arrangement that happens to look right and fails
    for any that does not while working. What went wrong is WHICH FUNCTION THE PATH POINTS
    AT, so that is what is read.

    ⚠️ AND THE NEIGHBOURS COULD NOT SEE IT. Eight TestClient assertions in
    `test_the_sort_column_is_named_or_refused.py` hit this exact path without `filters` and
    would have gone red - they were simply not in the list of tests this round ran. A gate
    is only as wide as the population it is pointed at.
    """
    import inspect

    import main

    bound = {route.path: route.endpoint for route in main.app.routes
             if getattr(route, "path", "") in ("/tables/{table_name}/data",
                                               "/tables/{table_name}/data/count")}

    assert bound["/tables/{table_name}/data"].__name__ == "get_table_data"
    assert bound["/tables/{table_name}/data/count"].__name__ == "get_table_data_count"

    for path, endpoint in bound.items():
        parameter = inspect.signature(endpoint).parameters.get("filters")
        assert parameter is not None and parameter.default is None, \
            f"{path}: `filters` is optional - a required one 422s every grid request"


def test_a_request_that_sends_no_filter_is_answered_and_the_line_says_zero(client, caplog):
    """The live gate 판정 14:33 asked for, over HTTP: the browser's own request shape."""
    import logging

    with caplog.at_level(logging.INFO):
        response = client.get("/tables/raw_table_1/data",
                              params={"skip": 0, "limit": 10, "order_by": "updated_at"})

    assert response.status_code == 200, response.text
    assert any("filters=0" in record.getMessage() for record in caplog.records), \
        [record.getMessage() for record in caplog.records][-4:]


# ── the statistics a table that is never loaded again keeps forever ──────────

def test_a_table_the_database_calls_stale_is_analysed_at_boot(monkeypatch):
    """🔴 S-124 ② ONLY REACHES TABLES THAT ARE LOADED AGAIN (S-130). It re-analyses after
    a big load, so a relation that took its rows BEFORE that shipped plans against
    whatever statistics it had then - and production is exactly that shape. Nothing
    announces it: the rows are right, the index is there, only the plan is wrong.

    ⚠️ THE DATABASE IS ASKED RATHER THAN GUESSED. `n_mod_since_analyze` is the count of
    rows changed since the last analyse, so 「stale enough」 is read, not inferred.
    """
    from chain import ingestion_worker as worker
    from parsers import directory_watcher as dw

    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 10000)
    analysed = []
    monkeypatch.setattr(dw, "_analyze_after_load",
                        lambda name, rows, why=None: analysed.append((name, rows)) or True)

    class _Session:
        def execute(self, statement, params=None):
            assert params["threshold"] == 10000
            class _R:
                def all(self_inner):
                    return [("enrich_test_src", 44000), ("not_ours", 999999)]
            return _R()

        def close(self):
            pass

    monkeypatch.setitem(__import__("database").crud.TABLE_CONFIG, "enrich_test_src", {})

    assert worker._analyze_stale_tables_sync(lambda: _Session()) == ["enrich_test_src"]
    assert analysed == [("enrich_test_src", 44000)]


def test_a_relation_this_application_did_not_declare_is_left_alone(monkeypatch):
    """⚠️ BOUNDED. A shared database may carry relations that are not ours to touch, so
    the set is the dynamic catalogue plus the framework models - not every user table."""
    from chain import ingestion_worker as worker
    from parsers import directory_watcher as dw

    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 10)
    monkeypatch.setattr(dw, "_analyze_after_load",
                        lambda name, rows, why=None: pytest.fail(f"touched {name}"))

    class _Session:
        def execute(self, statement, params=None):
            class _R:
                def all(self_inner):
                    return [("some_other_apps_table", 10 ** 9)]
            return _R()

        def close(self):
            pass

    assert worker._analyze_stale_tables_sync(lambda: _Session()) == []


def test_the_framework_tables_are_in_scope_because_the_grid_reads_them(monkeypatch):
    """🔴 MEASURED, AND IT IS WHY THE SCOPE IS NOT JUST THE CATALOGUE. On this box the four
    relations over the threshold were `cell_sources` (1,059,219 rows modified since its
    last analyse), `audit_logs`, and two ledger partitions - and NOT ONE was a catalogued
    dynamic table. A page of the grid reads `cell_sources` for its values, so scoping this
    to `TABLE_CONFIG` would have made it a no-op on the shape it exists for."""
    from database import models

    assert "cell_sources" in models.Base.metadata.tables
    assert "audit_logs" in models.Base.metadata.tables


def test_a_threshold_of_zero_turns_the_boot_pass_off(monkeypatch):
    from chain import ingestion_worker as worker
    from parsers import directory_watcher as dw

    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 0)
    monkeypatch.setattr(dw, "_analyze_after_load",
                        lambda name, rows, why=None: pytest.fail("must not run"))

    assert worker._analyze_stale_tables_sync(lambda: pytest.fail("no session either")) == []


def test_a_database_that_cannot_answer_does_not_stop_the_boot(monkeypatch):
    """A boot that dies reading statistics is a worse outage than a stale plan - and the
    view does not exist outside PostgreSQL, which is where the suite runs."""
    from chain import ingestion_worker as worker
    from parsers import directory_watcher as dw

    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 10)

    class _Session:
        def execute(self, statement, params=None):
            raise RuntimeError("no such view")

        def close(self):
            pass

    assert worker._analyze_stale_tables_sync(lambda: _Session()) == []


def test_the_boot_sequence_calls_it_too():
    """착지는 배선이 아니다 - the same check its neighbour needed."""
    import inspect

    from chain import ingestion_worker as worker

    body = inspect.getsource(worker.start_chain_ingestion_worker)
    assert "_analyze_stale_tables_sync" in body, body[:600]


def test_the_load_path_and_the_boot_path_share_one_function_and_one_threshold():
    """⛔ TWO SPELLINGS OF 「stale enough」 WOULD DRIFT, and the one running at boot would
    not be the one anybody had measured."""
    import inspect

    from chain import ingestion_worker as worker

    body = inspect.getsource(worker._analyze_stale_tables_sync)
    assert "dw._analyze_after_load(" in body, body[:800]
    assert "dw.analyze_after_rows()" in body


def test_the_ledger_owns_its_table_names_and_says_which_are_its_own():
    """🔴 ONE SPELLING (판정 16:36). Two lists of 「which tables are the ledger's」 drift,
    and the one a maintenance pass walks is then the one nobody updated - so the module
    that creates them is the module that names them."""
    from ledger import schema

    assert schema.FIXED_TABLES == ("ledger_events", "ledger_translator_cursor",
                                   "ledger_source_row_ref")
    assert schema.PARTITION_PREFIX == "ledger_events_"

    for name in schema.FIXED_TABLES:
        assert schema.owns_table(name), name
    assert schema.owns_table("ledger_events_2026_08"), "a monthly partition is its own"
    assert not schema.owns_table("dt_log")
    assert not schema.owns_table("")
    assert not schema.owns_table(None)


def test_only_partitions_that_exist_are_reached_because_the_database_names_them(monkeypatch):
    """⚠️ EXISTING ONLY, and it falls out of asking rather than generating. Month names are
    never built here; what is matched is what the statistics view reported, so a month that
    was never created cannot appear."""
    from chain import ingestion_worker as worker
    from parsers import directory_watcher as dw

    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 10000)
    analysed = []
    monkeypatch.setattr(dw, "_analyze_after_load",
                        lambda name, rows, why=None: analysed.append(name) or True)

    class _Session:
        def execute(self, statement, params=None):
            class _R:
                def all(self_inner):
                    return [("ledger_source_row_ref", 64178),
                            ("ledger_events_2026_08", 44430),
                            ("someone_elses_table", 10 ** 9)]
            return _R()

        def close(self):
            pass

    worker._analyze_stale_tables_sync(lambda: _Session())

    # ⛔ THE FOREIGN RELATION IS THE POINT OF THE THIRD ROW: it is over the threshold
    # by a mile and must still not be touched.
    assert set(analysed) == {"ledger_source_row_ref", "ledger_events_2026_08"}, analysed


def test_the_boot_pass_asks_the_ledger_rather_than_listing_its_tables_again():
    import inspect

    from chain import ingestion_worker as worker

    body = inspect.getsource(worker._analyze_stale_tables_sync)
    assert "ledger_schema.owns_table(name)" in body, body[-900:]
    assert "ledger_events" not in body, "the names live in ledger/schema.py, not here"
