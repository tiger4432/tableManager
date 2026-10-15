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
    """One task, one after the other - so two never build at once - on threads beside the loop. The ledger's
    partitions are not the chain's line any more (총괄 7763dd6d0 - the ledger process builds them)."""
    ran = []
    monkeypatch.setattr(worker, "_ensure_declared_indexes_sync", lambda rules, factory: ran.append("keys"))
    monkeypatch.setattr(models, "ensure_model_indexes_sync", lambda factory, sources, say: ran.append(sources))

    from runtime import maintenance_line

    monkeypatch.setattr(worker, "load_chain_rules", lambda: [])
    monkeypatch.setattr(models, "ensure_auto_indexes_sync", lambda *a: None)
    maintenance_line._each(maintenance_line._declared_work(None))
    assert ran == ["keys", ("model", "table")]


def test_a_ledger_build_that_waits_holds_back_neither_the_follow_up_nor_the_census(monkeypatch):
    """총괄 bdc08ec39 ② in the split shape (7763dd6d0): the ledger's partitions wait on the database's older
    transactions, so the ledger process builds them beside its loops - the follow-up and the census start while the
    build still waits, and the chain's line never had them."""
    from ledger import worker as ledger_worker

    release, began, started = threading.Event(), [], []

    def build(factory, sources, say):
        began.append(sources)
        release.wait(10)

    async def loop(name, factory):
        started.append(name)

    monkeypatch.setattr(models, "ensure_model_indexes_sync", build)
    monkeypatch.setattr(ledger_worker, "_ensure_ledger_schema_sync", lambda factory: None)
    monkeypatch.setattr(ledger_worker, "_restamp_moved_fingerprints_sync", lambda factory: None)
    monkeypatch.setattr(ledger_worker, "run_ledger_followup", lambda factory: loop("followup", factory))
    monkeypatch.setattr(ledger_worker, "run_ledger_row_census", lambda factory: loop("census", factory))
    monkeypatch.setattr(ledger_worker.heartbeat, "another_process_beats", lambda name, now=None: None)
    monkeypatch.setattr(ledger_worker.heartbeat, "beat", lambda *a, **k: None)

    async def go():
        task = asyncio.ensure_future(ledger_worker.start_ledger_worker(None))
        for _ in range(50):
            await asyncio.sleep(0.05)
            if len(started) == 2:
                break
        seen = (sorted(started), began, release.is_set())
        release.set()
        task.cancel()
        return seen

    assert asyncio.run(go()) == (["census", "followup"], [("ledger",)], False)


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
                        lambda: {models.BUILD_MISSING_INDEXES_SETTING: False})
    _ddl(scratch, "DROP INDEX %s" % DROPPED)
    caplog.set_level("WARNING", logger=worker.logger.name)

    models.ensure_model_indexes_sync(sessionmaker(bind=scratch), models.INDEX_SOURCES, worker.logger.warning)

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


@pytest.fixture(name="ledger_space")
def fixture_ledger_space(pg_engine):
    """A schema of the case's own: its ledger and only the partitions it makes (총괄 9752e91f7 ⑥ - a partition another
    case left in the shared scratch made these red after it). Its build is the ledger's line alone."""
    from sqlalchemy import create_engine

    from conftest import PG_TEST_SCHEMA
    from ledger import schema
    from support.isolated_pg import scratch_connect_args

    space = PG_TEST_SCHEMA + "_lx"
    _ddl(pg_engine, 'DROP SCHEMA IF EXISTS "%s" CASCADE' % space, 'CREATE SCHEMA "%s"' % space)
    engine = create_engine(pg_engine.url, connect_args=scratch_connect_args(space))
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            assert cursor.fetchone()[0] == space
        schema.ensure_schema(raw)
        raw.commit()
    finally:
        raw.close()
    try:
        yield engine
    finally:
        engine.dispose()
        _ddl(pg_engine, 'DROP SCHEMA IF EXISTS "%s" CASCADE' % space)


def _months(engine, *months):
    from datetime import datetime, timezone
    from ledger import schema

    raw = engine.raw_connection()
    try:
        for month in months:
            schema.ensure_partition(raw, datetime(2026, month, 15, tzinfo=timezone.utc))
    finally:
        raw.close()
    _ddl(engine, "DROP INDEX IF EXISTS %s" % schema.REF_INDEX)            # every partition's goes with the parent's
    return schema.in_space(schema.world_names(None), schema.REF_INDEX)


LEDGER = ("ledger",)


@pytest.mark.pg
def test_the_ledgers_ref_index_is_named_and_built_a_partition_at_a_time(ledger_space):
    """Lead 10-13: the ledger's ref index reached production only by a person's command - now the index master names
    it per world (source ledger, how many partitions lack it) and its build makes it, a partition at a time."""
    name = _months(ledger_space, 1, 2)
    row = _states(ledger_space)[name]
    assert (row["source"], row["state"], row["using"], row["columns"]) == ("ledger", "missing", "hash", ["source_raw_ref"])
    assert row["partitions_missing"] == row["partitions"] == 2

    off = []
    assert models.ensure_model_indexes(ledger_space, build=False, say=off.append, sources=LEDGER) == {}
    assert len(off) == 1 and "%s on ledger_events (missing)" % name in off[0] and "build_missing_indexes is off" in off[0]
    said = []
    assert models.ensure_model_indexes(ledger_space, say=said.append, sources=LEDGER)[name] == models.INDEX_BUILT
    assert len([line for line in said if ": built ledger_events_" in line]) == 2, said
    row = _states(ledger_space)[name]
    assert (row["state"], row["partitions_missing"]) == ("present", 0)


def _build_pid(engine, partition):
    """The backend building `partition`'s index now, or None."""
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT p.pid FROM pg_stat_progress_create_index p JOIN pg_class c ON c.oid = p.index_relid "
            "WHERE c.relname = :n"), {"n": "%s_ref_hash" % partition}).scalar()


@pytest.mark.pg
def test_a_partition_another_session_builds_is_left_to_it_and_a_wait_is_said_once(ledger_space, monkeypatch):
    """총괄 bdc08ec39 ① ② · 9752e91f7 ②: a second builder dropped the first's index in progress - a deadlock (9.3 ->
    21.3 s at 3M). Now that partition is left to its session and the route says building; a build waits on an older
    transaction as long as it lasts - given up at a limit it threw the build away - and says whom once; a partition
    that fails (cancelled here) is said and the next one is built; once the wait is gone the next build attaches what
    the other session made and builds the rest."""
    import psycopg2

    from ledger import schema

    import db_safety

    monkeypatch.setattr(models, "LEDGER_WAIT_SAY_SECONDS", 0.3)
    monkeypatch.setattr(db_safety, "DDL_LOCK_TIMEOUT", "2s")
    engine = ledger_space
    name = _months(engine, 1, 2, 3)
    dsn = engine.url.render_as_string(hide_password=False).replace("postgresql+psycopg2", "postgresql")
    with engine.connect() as conn:
        space = conn.execute(text("SELECT current_schema()")).scalar()
    holder = psycopg2.connect(dsn, application_name="b_old_snapshot")
    holder.set_session(isolation_level="REPEATABLE READ")
    with holder.cursor() as cur:
        cur.execute("SELECT 1")                                          # an older snapshot, on nothing indexed here
    holder_pid = holder.get_backend_pid()
    other, ended, done = psycopg2.connect(dsn, application_name="b_other_builder"), {}, {}
    other.autocommit = True
    canceller = psycopg2.connect(dsn, application_name="b_canceller")
    canceller.autocommit = True

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
    build = threading.Thread(target=lambda: done.update(
        models.ensure_model_indexes(engine, say=said.append, sources=LEDGER)))
    try:
        january.start()
        assert _wait(lambda: _states(engine)[name]["building"]), "the other session's build never showed"
        build.start()
        february = _wait(lambda: _build_pid(engine, "ledger_events_2026_02") if [
            line for line in said if "ledger_events_2026_02_ref_hash still building" in line] else None)
        assert february, said                                           # February built, now waiting on the holder
        with canceller.cursor() as cur:
            cur.execute("SELECT pg_cancel_backend(%s)", (february,))
        assert _wait(lambda: [line for line in said if "ledger_events_2026_02: " in line and " failed after " in line])
        assert _wait(lambda: [line for line in said if "ledger_events_2026_03_ref_hash still building" in line])
        time.sleep(3)                    # March waits past any limit a wait once had (DDL_LOCK_TIMEOUT, made 2 s here)
        assert build.is_alive() and not [line for line in said if "ledger_events_2026_03: " in line], said
        holder.rollback()                                                # the older snapshot gone: the waits end
        build.join(60)
        january.join(60)
    finally:
        holder.close()
        other.close()
        canceller.close()
    assert not build.is_alive() and done == {name: models.INDEX_FAILED}, (done, said)
    assert ended == {"ok": True}, ended                                   # its build was not dropped from under it
    assert [line for line in said if line.startswith(
        "[Indexes] ledger_events_2026_01: ledger_events_2026_01_ref_hash building - ") and "left to it" in line], said
    waits = [line for line in said if "still building after" in line]
    assert waits and all("waiting for transactions older than it: pid " in line for line in waits), waits
    assert any("pid %s (b_old_snapshot)" % holder_pid in line for line in waits), waits
    assert len(waits) == len({line.split(" still building after ")[0] + line.split(" - building - ")[1]
                              for line in waits}), waits             # once a partition and a waiter
    assert [line for line in said if "ledger_events_2026_02: " in line and " failed after " in line
            and "the other partitions go on" in line]
    assert [line for line in said if "ledger_events_2026_03: built ledger_events_2026_03_ref_hash in " in line], said
    again = []
    assert models.ensure_model_indexes(engine, say=again.append, sources=LEDGER)[name] == models.INDEX_BUILT
    assert any("attached the ledger_events_2026_01_ref_hash already there" in line for line in again), again
    assert _states(engine)[name]["state"] == models.INDEX_PRESENT
