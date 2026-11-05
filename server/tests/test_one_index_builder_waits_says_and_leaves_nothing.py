# -*- coding: utf-8 -*-
"""The one index builder (`models._ensure_one_index`, 총괄 11-05 ㄴ) on a real PostgreSQL - its five words:

  present    a valid index of the name - nothing built, nothing said
  built      nothing there, or an INVALID leftover nobody builds (dropped first) - valid after, its table noted
  failed     the build fails (duplicates) - said, and the INVALID leftover it leaves is what the next one repairs
  deferred   a session holds the table past the wait before the build - nothing started, so nothing left behind
  busy       the name is being built by another session - left to it; that build is not thrown away, says whom it
             waits for while it waits, and is valid once the old transaction ends
"""
import threading
import time

import pytest
from sqlalchemy import text

from database import models

pytestmark = pytest.mark.pg

TABLE, NAME = "ib_t", "ib_t_k_uq"
DDL = 'CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "%s" ON "%s" (k)' % (NAME, TABLE)


@pytest.fixture(name="table")
def fixture_table(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"' % TABLE))
        conn.execute(text('CREATE TABLE "%s" (k int)' % TABLE))
        conn.execute(text('INSERT INTO "%s" SELECT g FROM generate_series(1, 50) g' % TABLE))
    yield pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"' % TABLE))


def _state(engine):
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT i.indisvalid FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid "
            "WHERE c.relname = :n AND c.relnamespace = current_schema()::regnamespace"), {"n": NAME}).first()
    return None if row is None else ("valid" if row[0] else "invalid")


def _build(engine, said, **kw):
    with models.built_tables() as built:
        word = models._ensure_one_index(engine, NAME, DDL, "test", say=said.append, table=TABLE, **kw)
    return word, set(built)


def test_present_built_and_a_leftover_repaired(table):
    said = []
    assert _build(table, said) == (models.INDEX_BUILT, {TABLE}) and _state(table) == "valid"
    assert _build(table, said) == (models.INDEX_PRESENT, set()), "a valid index is not built again nor analysed"

    with table.begin() as conn:
        conn.execute(text('DROP INDEX "%s"' % NAME))
        conn.execute(text('INSERT INTO "%s" VALUES (1)' % TABLE))
    said.clear()
    assert _build(table, said) == (models.INDEX_FAILED, set())
    assert _state(table) == "invalid" and "Failed to ensure test index" in said[-1], said

    with table.begin() as conn:
        conn.execute(text('DELETE FROM "%s" WHERE ctid = (SELECT max(ctid) FROM "%s" WHERE k = 1)' % (TABLE, TABLE)))
    said.clear()
    assert _build(table, said) == (models.INDEX_BUILT, {TABLE}) and _state(table) == "valid"
    assert any("is INVALID from an earlier failure; dropping and rebuilding" in line for line in said), said


def test_a_holder_past_the_wait_defers_and_leaves_nothing(table, monkeypatch):
    monkeypatch.setattr(models, "INDEX_WAIT_BEFORE_SECONDS", 1.0)
    monkeypatch.setattr(models, "INDEX_WAIT_POLL_SECONDS", 0.2)
    holder = table.connect()
    try:
        holder.execute(text('INSERT INTO "%s" VALUES (999)' % TABLE))     # RowExclusive, transaction left open
        pid = holder.execute(text("SELECT pg_backend_pid()")).scalar()
        said, out = [], {}
        builder = threading.Thread(target=lambda: out.update(word=_build(table, said)), daemon=True)
        builder.start()
        builder.join(15)
        assert out.get("word") == (models.INDEX_DEFERRED, set()), "past the wait it gives up - not a build that waits"
    finally:
        holder.rollback()
        holder.close()
        builder.join(60)
    assert _state(table) is None, "nothing was started, so nothing is left behind"
    assert "waits for pid %s holding %s" % (pid, TABLE) in said[0], said
    assert ("not built - waited 1s for pid %s holding %s; tried again at the line's next poll" % (pid, TABLE)
            in said[-1]), "asked in a round (`built_tables`) - the line keeps it for its next poll: %s" % said


def test_a_build_under_way_is_left_to_its_session_says_its_waits_and_ends_valid(table):
    old = table.connect()
    old.execute(text("BEGIN ISOLATION LEVEL REPEATABLE READ"))
    old.execute(text("SELECT 1"))                                          # an old snapshot - the build waits it out
    first, first_said = {}, []
    builder = threading.Thread(target=lambda: first.update(word=_build(table, first_said, say_every=0.3)))
    builder.start()
    try:
        deadline = time.monotonic() + 30
        while _state(table) != "invalid" and time.monotonic() < deadline:
            time.sleep(0.1)
        assert _state(table) == "invalid", "the first build is under way"
        second = []
        assert _build(table, second) == (models.INDEX_BUSY, set())
        assert "is being built by another session - left to it" in second[-1], second
        time.sleep(1.0)
        assert _state(table) == "invalid", "the build under way was not thrown away"
    finally:
        old.execute(text("COMMIT"))
        old.close()
        builder.join(60)
    assert first["word"] == (models.INDEX_BUILT, {TABLE}) and _state(table) == "valid"
    assert len([line for line in first_said if NAME in line]) >= 2, first_said


def test_a_statement_that_ran_but_left_no_valid_index_is_failed_not_built(table):
    """«The statement ran» is not «an index enforces it» (C 11-06: the re-check after the build survived a mutant) - a
    statement that leaves no valid index of the name is FAILED, said, and its table not noted for the ANALYZE."""
    said = []
    with models.built_tables() as built:
        word = models._ensure_one_index(table, NAME, "SELECT 1", "test", say=said.append, table=TABLE)
    assert (word, set(built)) == (models.INDEX_FAILED, set()) and _state(table) is None
    assert "was built INVALID" in said[-1], said


def test_outside_a_round_the_deferred_line_says_its_asker_builds_it_again(table, monkeypatch):
    """The ledger worker's start and a retroactive merge ask outside the line's round - nothing keeps it for a poll,
    and the sentence says so (총괄 11-06 ㄱ)."""
    monkeypatch.setattr(models, "INDEX_WAIT_BEFORE_SECONDS", 1.0)
    monkeypatch.setattr(models, "INDEX_WAIT_POLL_SECONDS", 0.2)
    holder = table.connect()
    builder = None
    try:
        holder.execute(text('INSERT INTO "%s" VALUES (999)' % TABLE))
        said, out = [], {}
        builder = threading.Thread(target=lambda: out.update(word=models._ensure_one_index(
            table, NAME, DDL, "test", say=said.append, table=TABLE)), daemon=True)
        builder.start()
        builder.join(15)
        assert out.get("word") == models.INDEX_DEFERRED, said
    finally:
        holder.rollback()
        holder.close()
        if builder is not None:
            builder.join(60)
    assert said[-1].endswith("; built again at the next start or the next run that asks for it"), said
