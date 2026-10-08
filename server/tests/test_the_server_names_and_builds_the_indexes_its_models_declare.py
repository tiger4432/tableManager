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
    monkeypatch.setattr(worker, "_ensure_model_indexes_sync", lambda factory: ran.append("models"))

    async def start():
        await worker._start_index_work([], None)

    asyncio.run(start())
    assert ran == ["keys", "models"]


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
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        for statement in statements:
            connection.execute(text(statement))


def _states(engine):
    return {row["name"]: row for row in models.index_states(engine)["declared"]}


#: A declared index dropped, and another made invalid - the catalogue's own flag, set by hand on the
#: superuser test database: a cancelled CONCURRENTLY build leaves the same.
DROPPED, BROKEN = "idx_audit_recent_groups", "idx_outbox_purge"
BREAK = ("DROP INDEX %s" % DROPPED,
         "UPDATE pg_index SET indisvalid = false WHERE indexrelid = '%s'::regclass" % BROKEN)


@pytest.fixture(name="scratch")
def fixture_scratch(pg_engine):
    """pg_engine's schema - what a case dropped or broke is built back after it."""
    yield pg_engine
    _ddl(pg_engine, "DROP INDEX IF EXISTS zz_outside_probe")
    models.ensure_model_indexes(pg_engine, say=lambda *_a: None)
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
    by_name = {row["name"]: row for row in said["declared"]}
    assert len(by_name) == len(models.declared_indexes())
    assert {name: by_name[name]["state"] for name in (DROPPED, BROKEN, "idx_audit_row_history")} == {
        DROPPED: "missing", BROKEN: "invalid", "idx_audit_row_history": "present"}
    present = by_name["idx_audit_row_history"]
    assert present["purpose"] and present["serves"] and present["size_bytes"] > 0
    assert (by_name[DROPPED]["columns"], by_name[DROPPED]["include"], by_name[BROKEN]["where"]) == (
        ["timestamp", "id"], ["transaction_id"], "processed_chain = true")
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

    worker._ensure_model_indexes_sync(sessionmaker(bind=scratch))

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
