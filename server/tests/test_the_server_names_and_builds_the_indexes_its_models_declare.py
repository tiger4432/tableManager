"""총괄 e0e8020fb · d71f931c7 (소유자 10-08 「빠진 인덱스 알리게 하고 알아서 만들어」 · 「선언이 마스터」):
the static models' `Index` and UNIQUE declarations are the one list of indexes that should exist.
Each says what it is for; GET /admin/indexes shows them beside the database; the chain worker's
index work names what the database lacks or holds invalid in one line and builds it, one at a time.
"""
import asyncio
import os
import sys
import threading
import time

import pytest
from sqlalchemy import Index, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import ingestion_worker as worker                          # noqa: E402
from database import models                                           # noqa: E402

#: Retired by migrations/drop_redundant_layering_indexes.py (RETIRE_UNUSED) - never declared again,
#: or the boot's own build would make them back.
RETIRED = ("ix_cell_sources_table_name", "ix_cell_sources_column_name")


def test_every_declared_index_says_what_it_is_for():
    declared = models.declared_indexes()
    assert len(declared) > 40, "the static models declare their indexes - else this measures nothing"
    assert [name for _table, name, item in declared
            if not (item.info.get("purpose") and item.info.get("serves"))] == []


def test_a_retired_index_is_not_declared():
    assert set(RETIRED) & {name for _table, name, _item in models.declared_indexes()} == set()


def test_every_declared_index_compiles_to_one_concurrent_build_of_its_own_name():
    built = [(name, models.model_index_ddl(item)) for _table, name, item in models.declared_indexes()
             if isinstance(item, Index)]
    assert built and [name for name, statement in built if not statement.startswith(
        ("CREATE INDEX CONCURRENTLY IF NOT EXISTS %s " % name,
         "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS %s " % name))] == []


def test_the_index_work_builds_the_model_indexes_after_the_declared_keys(monkeypatch):
    """One task, one after the other - so two never build at once - on threads beside the loop."""
    ran = []
    monkeypatch.setattr(worker, "_ensure_declared_indexes_sync", lambda rules, factory: ran.append("keys"))
    monkeypatch.setattr(worker, "_ensure_model_indexes_sync", lambda factory, sources: ran.append(sources))

    async def start():
        await worker._start_index_work([], None)
        await worker._LEDGER_INDEX_LINE["task"]

    asyncio.run(start())
    assert [step for step in ran if step != ("ledger",)] == ["keys", ("model", "table")]
    assert ran.count(("ledger",)) == 1


def test_a_ledger_build_that_waits_holds_back_no_join_key(monkeypatch):
    """총괄 bdc08ec39 ②: a reload's join keys are built while the ledger's partitions still wait - the ledger's own
    line runs after its own last only."""
    release, ran, began = threading.Event(), [], []

    def build(factory, sources):
        if sources == ("ledger",):
            began.append(sources)
            release.wait(10)
        ran.append(sources)
    monkeypatch.setattr(worker, "_ensure_declared_indexes_sync", lambda rules, factory: ran.append("keys"))
    monkeypatch.setattr(worker, "_ensure_model_indexes_sync", build)

    async def go():
        first = worker._start_index_work([], None)
        second = worker._start_index_work([], None, after=first)          # a reload while the ledger's build waits
        await asyncio.wait_for(second, 5)
        await asyncio.sleep(0.3)                                          # room for a second ledger build to begin
        built = (ran.count("keys"), ran.count(("ledger",)), len(began))   # ... it must not: one at a time
        release.set()
        await worker._LEDGER_INDEX_LINE["task"]
        return built

    assert asyncio.run(go()) == (2, 0, 1)
    assert ran.count(("ledger",)) == 2


# ------------------------------------------------------------------------------------- PG

def _wait(predicate, seconds=30.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    return None


def _ddl(engine, *statements):
    """`statements` in `engine`'s own schema alone: the search path pinned to it, so a name the schema lacks is an error
    and never public's (총괄 10-13: a DROP INDEX IF EXISTS of an index the scratch lacked dropped public's)."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        space = connection.execute(text("SELECT current_schema()")).scalar()
        assert space and space != "public", space
        connection.execute(text('SET search_path TO "%s"' % space))
        try:
            for statement in statements:
                connection.execute(text(statement))
        finally:
            connection.execute(text("RESET search_path"))


def _states(engine):
    return {row["name"]: row for row in models.index_states(engine)["declared"]}


#: A declared index dropped, and another made invalid - the catalogue's own flag, set by hand on the
#: superuser test database: a cancelled CONCURRENTLY build leaves the same.
DROPPED, BROKEN = "idx_audit_recent_groups", "idx_outbox_purge"
BREAK = ("DROP INDEX %s" % DROPPED,
         "UPDATE pg_index SET indisvalid = false WHERE indexrelid = '%s'::regclass" % BROKEN)


@pytest.fixture(name="scratch")
def fixture_scratch(pg_engine):
    """pg_engine's schema - what a case dropped or broke is built back after it: plain builds of this schema's owed
    indexes, not CONCURRENTLY - a concurrent build waits on the shared database's older transactions (23 min, 총괄
    bdc08ec39 ⑧)."""
    from ledger import schema

    yield pg_engine
    _ddl(pg_engine, "DROP INDEX IF EXISTS zz_outside_probe")
    items = {name: item for _table, name, item in models.declared_indexes()}
    for row in models.index_states(pg_engine)["declared"]:
        if row["state"] not in (models.INDEX_MISSING, models.INDEX_INVALID) or row["constraint"]:
            continue
        if row["source"] == "ledger":
            _ddl(pg_engine, "DROP INDEX IF EXISTS %s" % schema.REF_INDEX,
                 "CREATE INDEX %s ON ledger_events %s" % (schema.REF_INDEX, schema.REF_INDEX_COLUMNS))
            continue
        statement = (models.model_index_ddl(items[row["name"]]) if row["source"] == "model"
                     else models.table_index_ddl(row))
        _ddl(pg_engine, 'DROP INDEX IF EXISTS "%s"' % row["name"], statement.replace(" CONCURRENTLY", "", 1))
    assert {row["state"] for row in _states(pg_engine).values()} == {models.INDEX_PRESENT}


@pytest.mark.pg
def test_the_route_shows_each_declared_index_beside_the_database(scratch):
    import main
    from fastapi.testclient import TestClient
    from database.database import get_db

    _ddl(scratch, *BREAK, "CREATE INDEX zz_outside_probe ON audit_logs (updated_by)")
    session = sessionmaker(bind=scratch)()
    main.app.dependency_overrides[get_db] = lambda: session
    try:
        answer = TestClient(main.app).get("/admin/indexes")
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        session.close()

    assert answer.status_code == 200, answer.text
    said = answer.json()
    by_name = {row["name"]: row for row in said["declared"] if row["source"] != "ledger"}
    assert len(by_name) == len(models.declared_indexes())
    assert {name: by_name[name]["state"] for name in (DROPPED, BROKEN, "idx_audit_row_history")} == {
        DROPPED: "missing", BROKEN: "invalid", "idx_audit_row_history": "present"}
    present = by_name["idx_audit_row_history"]
    assert present["purpose"] and present["serves"] and present["size_bytes"] > 0
    assert (by_name[DROPPED]["columns"], by_name[DROPPED]["include"], by_name[BROKEN]["where"]) == (
        ["timestamp", "id"], ["transaction_id"], "processed_chain = true")
    assert (by_name["idx_audit_logs_timestamp_brin"]["using"], by_name[DROPPED]["using"]) == ("brin", None)
    assert [(row["name"], row["table"]) for row in said["outside"]] == [("zz_outside_probe", "audit_logs")]
    # the catalogue's own tables are not the models' - loaded here, and left out
    assert models.DYNAMIC_TABLES and not {t.name for t in models.model_tables()} & set(models.DYNAMIC_TABLES)


@pytest.mark.pg
def test_the_index_work_names_what_is_owed_in_one_line_and_builds_it(scratch):
    _ddl(scratch, *BREAK)
    said = []

    done = models.ensure_model_indexes(scratch, say=said.append)

    assert done == {DROPPED: models.INDEX_BUILT, BROKEN: models.INDEX_BUILT}
    owed = [line for line in said if "lacks or holds invalid" in line]
    assert len(owed) == 1 and "%s on audit_logs (missing)" % DROPPED in owed[0] \
        and "%s on database_outbox (invalid)" % BROKEN in owed[0], said
    assert {row["state"] for row in _states(scratch).values()} == {models.INDEX_PRESENT}
    again = []
    assert models.ensure_model_indexes(scratch, say=again.append) == {} and again == []


@pytest.mark.pg
def test_a_missing_unique_constraint_is_named_and_not_built(scratch):
    """A UNIQUE constraint is ALTER TABLE, not an index - named, and left for a person."""
    name = "auth_api_keys_key_hash_key"
    _ddl(scratch, "ALTER TABLE auth_api_keys DROP CONSTRAINT %s" % name)
    said = []
    try:
        assert models.ensure_model_indexes(scratch, say=said.append) == {}
        assert any("%s on auth_api_keys (missing)" % name in line for line in said) \
            and "[Indexes] %s is a UNIQUE constraint - not built here" % name in said, said
    finally:
        _ddl(scratch, "ALTER TABLE auth_api_keys ADD CONSTRAINT %s UNIQUE (key_hash)" % name)


@pytest.mark.pg
def test_build_missing_indexes_off_names_what_is_owed_and_builds_nothing(scratch, monkeypatch, caplog):
    import parsers.directory_watcher as directory_watcher

    monkeypatch.setattr(directory_watcher, "load_ingestion_settings",
                        lambda: {worker.BUILD_MISSING_INDEXES_SETTING: False})
    _ddl(scratch, "DROP INDEX %s" % DROPPED)
    caplog.set_level("WARNING", logger=worker.logger.name)

    worker._ensure_model_indexes_sync(sessionmaker(bind=scratch), models.INDEX_SOURCES)

    said = [r.getMessage() for r in caplog.records if "[Indexes]" in r.getMessage()]
    assert len(said) == 1 and "not built: build_missing_indexes is off" in said[0], said
    assert _states(scratch)[DROPPED]["state"] == models.INDEX_MISSING


@pytest.mark.pg
def test_a_build_waiting_on_an_older_transaction_says_whom_and_ends_after_it(scratch):
    """소유자 10-09: 47 minutes of «why does it not finish» - a CONCURRENTLY build waits for every
    older transaction, and now says which, in its line and on the route."""
    _ddl(scratch, "DROP INDEX %s" % DROPPED)
    blocker = scratch.connect()
    held = blocker.begin()
    blocker.execute(text("INSERT INTO audit_logs (table_name, row_id, column_name) VALUES ('zz', 'zz', 'zz')"))
    said, done = [], {}
    build = threading.Thread(target=lambda: done.update(
        models.ensure_model_indexes(scratch, say=said.append, say_every=0.2)))
    try:
        build.start()
        assert _wait(lambda: [line for line in said if "still building" in line
                              and "waiting for transactions older than it: pid " in line]), said
        building = _states(scratch)[DROPPED]
        assert building["state"] == models.INDEX_BUILDING and building["building"].startswith(
            "building - waiting for transactions older than it: pid "), building
    finally:
        held.rollback()
        blocker.close()
        build.join(60)
    assert done == {DROPPED: models.INDEX_BUILT}


# ------------------------------------------------------------- a table's own declared indexes
# 총괄 06e8c22c3 · 98be7faf3 (소유자 「테이블 별로 특정 컬럼 인덱스」): table_config.json's "indexes" -
# the same comparison, the same builder, the same switch.

PROBE = "zz_declared_probe"
PROBE_TABLES = {PROBE: {"column_types": {"lot": "string", "code": "string", "dt_wafer_id": "string"},
                        "indexes": [{"columns": ["lot"], "purpose": "a lot's rows"},
                                    {"columns": ["dt_wafer_id"], "purpose": "a wafer's rows"},
                                    {"columns": ["code"], "unique": True, "purpose": "one row a code"}]},
                "zz_a_view": {"kind": "view", "column_types": {"lot": "string"},
                              "indexes": [{"columns": ["lot"]}]}}


def test_a_table_index_is_named_by_its_table_and_columns_and_a_long_one_keeps_a_hash_tail():
    assert models.table_index_name("dt_log", ["dt_wafer_id"]) == "idx_dt_log_dt_wafer_id"
    long_a = models.table_index_name("a_rather_long_table_name", ["first_long_column", "second_long_column_a"])
    long_b = models.table_index_name("a_rather_long_table_name", ["first_long_column", "second_long_column_b"])
    assert len(long_a) == len(long_b) == 63 and long_a != long_b
    assert long_a == models.table_index_name("a_rather_long_table_name",
                                             ["first_long_column", "second_long_column_a"])


def test_a_save_refuses_an_unknown_column_an_empty_or_twice_declared_index_and_a_view(tmp_path, monkeypatch):
    import json as _json

    from fastapi import HTTPException
    from ledger import admin

    path = tmp_path / "table_config.json"
    path.write_text(_json.dumps({PROBE: PROBE_TABLES[PROBE]}), encoding="utf-8")
    monkeypatch.setattr(admin, "table_config_path", lambda: str(path))
    monkeypatch.setattr(admin, "_atomic_write", lambda p, merged: path.write_text(
        _json.dumps(merged), encoding="utf-8"))

    def refused(declaration):
        with pytest.raises(HTTPException) as caught:
            admin.save_table_config_raw(PROBE, declaration, admin.file_fingerprint(str(path)))
        return caught.value.detail["code"], caught.value.detail["path"], caught.value.detail["message"]

    types = PROBE_TABLES[PROBE]["column_types"]
    assert refused({"column_types": types, "indexes": [{"columns": ["lot", "nope"]}]}) == (
        "indexes_refused", "tables.%s.indexes[0].columns" % PROBE, "%s has no column nope" % PROBE)
    assert refused({"column_types": types, "indexes": [{"columns": []}]})[1] == "tables.%s.indexes[0].columns" % PROBE
    assert refused({"column_types": types, "indexes": [{"columns": ["lot"]}, {"columns": ["lot"]}]})[2] == (
        "(lot) is declared twice")
    assert refused({"kind": "view", "column_types": types, "indexes": [{"columns": ["lot"]}]})[2] == (
        "%s is a view - a view cannot carry an index" % PROBE)
    saved = admin.save_table_config_raw(PROBE, PROBE_TABLES[PROBE], admin.file_fingerprint(str(path)))
    assert saved["ok"] is True, "CANARY: a good declaration saves"


def test_the_ledger_catalogue_reads_a_table_index_written_without_unique(tmp_path):
    import json as _json

    from ledger import setup_bundle

    path = tmp_path / "table_config.json"
    path.write_text(_json.dumps({PROBE: PROBE_TABLES[PROBE]}), encoding="utf-8")
    catalog = setup_bundle.load_physical_catalog(str(path))

    assert setup_bundle._table_has_unique_key(catalog[PROBE], ["lot"]) is False
    assert setup_bundle._table_has_unique_key(catalog[PROBE], ["code"]) is True


@pytest.fixture(name="probe")
def fixture_probe(pg_engine):
    """A table with duplicated codes and the owner's hand-made index on dt_wafer_id, in pg_engine's schema."""
    _ddl(pg_engine, "CREATE TABLE %s (row_id text PRIMARY KEY, lot text, code text, dt_wafer_id text)" % PROBE,
         "INSERT INTO %s VALUES ('1', 'L1', 'A', 'W1'), ('2', 'L1', 'A', 'W2')" % PROBE,
         'CREATE INDEX "idx_%s_dt_wafer_id" ON %s (dt_wafer_id)' % (PROBE, PROBE))
    yield pg_engine
    _ddl(pg_engine, "DROP TABLE IF EXISTS %s" % PROBE)


@pytest.mark.pg
def test_the_index_work_builds_a_table_index_keeps_a_hand_made_one_and_says_why_a_unique_one_failed(probe):
    said = []
    done = models.ensure_model_indexes(probe, say=said.append, tables=PROBE_TABLES)

    lot, wafer, code = ("idx_%s_%s" % (PROBE, column) for column in ("lot", "dt_wafer_id", "code"))
    assert done == {lot: models.INDEX_BUILT, code: models.INDEX_FAILED}, said
    owed = [line for line in said if "lacks or holds invalid" in line]
    assert len(owed) == 1 and "%s on %s (missing)" % (lot, PROBE) in owed[0] and wafer not in owed[0]
    states = {row["name"]: row for row in models.index_states(probe, PROBE_TABLES)["declared"]}
    assert {name: (states[name]["state"], states[name]["source"]) for name in (lot, wafer, code)} == {
        lot: ("present", "table"), wafer: ("present", "table"), code: ("invalid", "table")}
    assert states[lot]["purpose"] == "a lot's rows" and states[code]["unique"] is True
    # the server's words in the server's language - the index and the duplicated key, whatever the locale
    assert code in states[code]["failure"] and "(code)=(A)" in states[code]["failure"], states[code]
    assert not states[code]["failure"].startswith(("ERROR", "오류")), "the severity head is not the reason"
    assert "zz_a_view" not in {row["table"] for row in states.values()}
    _ddl(probe, "DELETE FROM %s WHERE row_id = '2'" % PROBE)
    assert models.ensure_model_indexes(probe, say=lambda *_a: None, tables=PROBE_TABLES) == {
        code: models.INDEX_BUILT}, "the leftover is dropped and the build made again once the data allows"


@pytest.mark.pg
def test_the_route_shows_a_table_index_beside_the_models(probe, monkeypatch):
    import main
    from fastapi.testclient import TestClient
    from database import crud
    from database.database import get_db

    monkeypatch.setitem(crud.TABLE_CONFIG, PROBE, PROBE_TABLES[PROBE])
    _ddl(probe, "CREATE INDEX zz_probe_undeclared ON %s (lot, code)" % PROBE)
    session = sessionmaker(bind=probe)()
    main.app.dependency_overrides[get_db] = lambda: session
    try:
        answer = TestClient(main.app).get("/admin/indexes")
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        session.close()

    assert answer.status_code == 200, answer.text
    rows = {row["name"]: row for row in answer.json()["declared"] if row["source"] != "ledger"}
    assert (rows["idx_%s_lot" % PROBE]["source"], rows["idx_%s_lot" % PROBE]["state"]) == ("table", "missing")
    assert rows["idx_%s_dt_wafer_id" % PROBE]["state"] == "present"
    assert {row["source"] for row in rows.values()} == {"model", "table"}
    # «outside» stays the models' tables - the catalogue's carry product indexes no declaration names
    assert {row["table"] for row in answer.json()["outside"]} <= {t.name for t in models.model_tables()}
    assert "zz_probe_undeclared" not in {row["name"] for row in answer.json()["outside"]}


@pytest.mark.pg
def test_the_ledgers_ref_index_is_named_and_built_a_partition_at_a_time(scratch):
    """Lead 10-13: the ledger's ref index reached production only by a person's command - now the index master names
    it per world (source ledger, how many partitions lack it) and its build makes it, a partition at a time."""
    from datetime import datetime, timezone
    from ledger import schema

    raw = scratch.raw_connection()
    try:
        schema.ensure_schema(raw)
        raw.commit()
        for month in (1, 2):
            schema.ensure_partition(raw, datetime(2026, month, 15, tzinfo=timezone.utc))
    finally:
        raw.close()
    _ddl(scratch, "DROP INDEX IF EXISTS %s" % schema.REF_INDEX)          # every partition's goes with the parent's
    name = schema.in_space(schema.world_names(None), schema.REF_INDEX)
    row = _states(scratch)[name]
    assert (row["source"], row["state"], row["using"], row["columns"]) == ("ledger", "missing", "hash", ["source_raw_ref"])
    assert row["partitions_missing"] == row["partitions"] >= 2

    off = []
    assert models.ensure_model_indexes(scratch, build=False, say=off.append) == {}
    assert len(off) == 1 and "%s on ledger_events (missing)" % name in off[0] and "build_missing_indexes is off" in off[0]
    said = []
    assert models.ensure_model_indexes(scratch, say=said.append)[name] == models.INDEX_BUILT
    assert len([line for line in said if ": built ledger_events_" in line]) == row["partitions"], said
    row = _states(scratch)[name]
    assert (row["state"], row["partitions_missing"]) == ("present", 0)


@pytest.mark.pg
def test_a_partition_another_session_builds_is_left_to_it_and_a_wait_is_given_up(scratch, monkeypatch):
    """총괄 bdc08ec39 ① ②: a second builder dropped the first's index in progress - a deadlock (9.3 -> 21.3 s at 3M).
    Now that partition is left to its session and the route says building; a partition whose build waits on an older
    transaction says whom, gives up at DDL_LOCK_TIMEOUT, and the next one is still tried; once the wait is gone the
    next build attaches what the other session made and builds the rest."""
    from datetime import datetime, timezone

    import psycopg2

    import db_safety
    from ledger import schema

    monkeypatch.setattr(db_safety, "DDL_LOCK_TIMEOUT", "2s")
    monkeypatch.setattr(models, "LEDGER_WAIT_SAY_SECONDS", 0.5)
    raw = scratch.raw_connection()
    try:
        schema.ensure_schema(raw)
        raw.commit()
        for month in (1, 2, 3):
            schema.ensure_partition(raw, datetime(2026, month, 15, tzinfo=timezone.utc))
    finally:
        raw.close()
    _ddl(scratch, "DROP INDEX IF EXISTS %s" % schema.REF_INDEX)
    name = schema.in_space(schema.world_names(None), schema.REF_INDEX)
    dsn = scratch.url.render_as_string(hide_password=False).replace("postgresql+psycopg2", "postgresql")
    with scratch.connect() as conn:
        space = conn.execute(text("SELECT current_schema()")).scalar()
    holder = psycopg2.connect(dsn, application_name="b_old_snapshot")
    holder.set_session(isolation_level="REPEATABLE READ")
    with holder.cursor() as cur:
        cur.execute("SELECT 1")                                          # an older snapshot, on nothing indexed here
    holder_pid = holder.get_backend_pid()
    other, ended = psycopg2.connect(dsn, application_name="b_other_builder"), {}
    other.autocommit = True

    def build_january():
        try:
            with other.cursor() as cur:
                cur.execute('CREATE INDEX CONCURRENTLY ledger_events_2026_01_ref_hash ON "%s".ledger_events_2026_01 %s'
                            % (space, schema.REF_INDEX_COLUMNS))
            ended["ok"] = True
        except Exception as exc:                                         # noqa: BLE001 - asserted below
            ended["error"] = exc
    january = threading.Thread(target=build_january)
    said = []
    try:
        january.start()
        assert _wait(lambda: _states(scratch)[name]["building"]), "the other session's build never showed"
        assert models.ensure_model_indexes(scratch, say=said.append)[name] == models.INDEX_FAILED
        row = _states(scratch)[name]
    finally:
        holder.rollback()
        holder.close()
        january.join(60)
        other.close()
    assert ended == {"ok": True}, ended                                   # its build was not dropped from under it
    assert [line for line in said if line.startswith(
        "[Indexes] ledger_events_2026_01: ledger_events_2026_01_ref_hash building - ") and "left to it" in line], said
    waits = [line for line in said if "still building after" in line
             and "waiting for transactions older than it: pid %s (b_old_snapshot)" % holder_pid in line]
    gave_up = [line for line in said if ": ledger_events_2026_0" in line and " failed after " in line
               and "the other partitions go on" in line]
    assert waits and len(gave_up) == 2, said                             # February's and March's, one after the other
    assert row["state"] == models.INDEX_MISSING and row["partitions_missing"] == 2
    again = []
    assert models.ensure_model_indexes(scratch, say=again.append)[name] == models.INDEX_BUILT
    assert any("attached the ledger_events_2026_01_ref_hash already there" in line for line in again), again
    assert _states(scratch)[name]["state"] == models.INDEX_PRESENT
