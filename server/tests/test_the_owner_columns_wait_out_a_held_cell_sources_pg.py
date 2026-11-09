"""The boot adds cell_sources' owner columns (`models.ensure_owner_columns`, step 2) under a lock timeout and asks again
while another session holds the table - a condition no box reaches on its own, so it is made here: a second connection
holds cell_sources in an open transaction (lead 11-09 ㅂ). Let go between the tries: the columns come on the second.
Held to the end: the boot says «not added» and a layer write refuses (`require_owner_columns`). Which failure is a lock
is `db_safety.waited_past_the_lock_timeout`'s answer, the one judge."""
import logging
import os
import sys
import time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import _declared_as_test_database, _resolve_pg_test_url   # noqa: E402
from database import models                                             # noqa: E402
from parsers import directory_watcher                                   # noqa: E402
from tests.support.isolated_pg import scratch_connect_args, scratch_schema   # noqa: E402

pytestmark = pytest.mark.pg

SCHEMA = scratch_schema("a_owner_lock")


@pytest.fixture(name="held")
def fixture_held(monkeypatch):
    """A cell_sources from before owners in a schema of its own, a second connection holding it, the boot's lines."""
    url, reason = _resolve_pg_test_url()
    if url is None:
        pytest.skip(reason)
    with _declared_as_test_database(url):
        engine = create_engine(url, poolclass=NullPool, connect_args=scratch_connect_args(SCHEMA))
        with engine.begin() as conn:
            conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % SCHEMA))
            conn.execute(text('CREATE SCHEMA "%s"' % SCHEMA))
            conn.execute(text('CREATE TABLE "%s".cell_sources (id SERIAL PRIMARY KEY, source_name VARCHAR, '
                              'value VARCHAR)' % SCHEMA))
        holder = engine.connect()
        holding = holder.begin()
        holder.execute(text('LOCK TABLE "%s".cell_sources IN ACCESS SHARE MODE' % SCHEMA))
        said = []
        handler = logging.Handler()
        handler.emit = lambda record: said.append(record.getMessage())
        models.logger.addHandler(handler)
        monkeypatch.setattr(directory_watcher, "ddl_lock_wait", lambda: (0.2, 1.5))   # tries of 0.2 s for 1.5 s
        monkeypatch.setattr(models, "DYNAMIC_TABLES", {})
        try:
            yield {"engine": engine, "holding": holding, "said": said}
        finally:
            models.logger.removeHandler(handler)
            if holding.is_active:
                holding.rollback()
            holder.close()
            with engine.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % SCHEMA))
            engine.dispose()


def _columns(engine):
    with engine.connect() as conn:
        return {name for (name,) in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = :s AND table_name = 'cell_sources'"),
            {"s": SCHEMA})}


def test_a_held_table_let_go_between_the_tries_gets_its_columns_on_the_next(held, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _seconds: held["holding"].commit())   # the holder lets go meanwhile
    # the whole wait not 1.5 s here: a first try slower than 0.5 s under load left no second (red 1 in 3, 11-09)
    monkeypatch.setattr(directory_watcher, "ddl_lock_wait", lambda: (0.2, 30.0))
    models.ensure_owner_columns(held["engine"])
    assert {"owner_rule", "owner_key"} <= _columns(held["engine"])
    assert any("owner_rule and owner_key added" in line for line in held["said"]), held["said"]
    models.require_owner_columns(held["engine"])


def test_a_table_held_to_the_end_says_not_added_and_a_layer_write_refuses(held, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    models.sync_dynamic_tables_schema(held["engine"])
    assert {"owner_rule", "owner_key"} & _columns(held["engine"]) == set()
    assert any("owner columns on cell_sources - its lock not had in" in line and "held by pid" in line
               for line in held["said"]), held["said"]
    assert any("the owner columns were not added - layer writes refuse" in line for line in held["said"]), held["said"]
    with pytest.raises(RuntimeError, match="the boot adds them"):
        models.require_owner_columns(held["engine"])
