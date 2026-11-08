# -*- coding: utf-8 -*-
"""The one index builder (`models._ensure_one_index`, 총괄 11-05 ㄴ) on a real PostgreSQL - its five words:

  present    a valid index of the name - nothing built, nothing said
  built      nothing there, or an INVALID leftover nobody builds (dropped first) - valid after, its table noted
  failed     the build fails (duplicates) - said, and the INVALID leftover it leaves is what the next one repairs
  deferred   a session holds the table past the wait before the build - nothing started, so nothing left behind
  written    a session writing the table (an open INSERT) is not waited for - the build starts, waits that writer out
             itself and ends valid (총괄 11-06: a table written without pause put its index off for ever)
  left open  a writer or a query open longer than the wait before the build is waited out before it, then the build is
             put off - the build would wait for it for ever (총괄 11-07); the line names its pid, age and query
  busy       the name is being built by another session - left to it; that build is not thrown away, says whom it
             waits for while it waits, and is valid once the old transaction ends
  cut        once building, a wait past index_build_wait_seconds cuts the build (owner 11-08 ㄴ): put off naming whom it
             waited for, its INVALID leftover repaired by the next try; a wait that ends within it builds as before
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


def _cancel_the_build_after(engine, seconds):
    """The test's cap, not the product's: the build sets its own timeouts to 0, so a build that waits for a holder
    left open would hang the run - cancelled after `seconds` it ends, and the cell is red (총괄 11-07)."""
    def cancel():
        with engine.connect() as conn:
            conn.execute(text("SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE datname = current_database() "
                              "AND pid <> pg_backend_pid() AND query = :q"), {"q": DDL})
            conn.commit()
    timer = threading.Timer(seconds, cancel)
    timer.daemon = True
    timer.start()
    return timer


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
        holder.execute(text('LOCK TABLE "%s" IN SHARE ROW EXCLUSIVE MODE' % TABLE))   # an ALTER's kind, left open
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


def test_a_build_under_way_is_left_to_its_session_says_its_waits_and_ends_valid(table, monkeypatch):
    monkeypatch.setattr(models, "INDEX_WAIT_SAY_SECONDS", 0.5)          # an unchanged wait said again on this period
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
        holder.execute(text('LOCK TABLE "%s" IN SHARE ROW EXCLUSIVE MODE' % TABLE))
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


def test_a_writing_session_is_not_waited_for_and_the_build_ends_valid(table, monkeypatch):
    """총괄 11-06: an open INSERT (RowExclusive) does not hold the build back - no wait before it, the CONCURRENTLY
    build itself waits that transaction out, and the index is valid once it ends."""
    monkeypatch.setattr(models, "INDEX_WAIT_BEFORE_SECONDS", 30.0)    # a wait before it would outlast this test
    holder = table.connect()
    builder, said, out = None, [], {}
    try:
        holder.execute(text('INSERT INTO "%s" VALUES (999)' % TABLE))   # RowExclusive, transaction left open
        builder = threading.Thread(target=lambda: out.update(word=_build(table, said)), daemon=True)
        builder.start()
        deadline = time.monotonic() + 10
        while _state(table) != "invalid" and time.monotonic() < deadline:
            time.sleep(0.1)
        assert _state(table) == "invalid", "the build started with the writer open - %s" % said
        assert not any("waits for pid" in line for line in said), said
    finally:
        holder.rollback()
        holder.close()
        if builder is not None:
            builder.join(60)
    assert out.get("word") == (models.INDEX_BUILT, {TABLE}) and _state(table) == "valid", (out, said)


@pytest.mark.parametrize("left_open", ["idle in transaction", "active"])
def test_a_transaction_open_past_the_wait_defers_the_build_and_leaves_nothing(table, monkeypatch, left_open):
    """총괄 11-07: a CONCURRENTLY build waits for every older snapshot of this database and every writer of its table -
    for ever when one is left open (a writer idle in its transaction, a query that runs on). Open longer than the wait
    before the build, it is waited out before it and the build is put off: nothing started, nothing left behind."""
    monkeypatch.setattr(models, "INDEX_WAIT_BEFORE_SECONDS", 1.0)
    monkeypatch.setattr(models, "INDEX_WAIT_POLL_SECONDS", 0.2)
    holder = table.connect()
    runner = None
    try:
        pid = holder.execute(text("SELECT pg_backend_pid()")).scalar()
        if left_open == "idle in transaction":
            holder.execute(text('INSERT INTO "%s" VALUES (999)' % TABLE))     # a writer, left open
        else:
            runner = threading.Thread(target=lambda: holder.execute(text("SELECT pg_sleep(4)")), daemon=True)
            runner.start()                                                    # a query holding its snapshot
        time.sleep(1.5)                                                       # open longer than the wait
        said = []
        cap = _cancel_the_build_after(table, 20)
        try:
            word = _build(table, said)
        finally:
            cap.cancel()
        assert word == (models.INDEX_DEFERRED, set()), said
        assert _state(table) is None, "nothing was started, so nothing is left behind"
        assert ("not built - waited 1s for pid %s" % pid in said[-1]
                and "(%s, open " % left_open in said[-1] and " since " in said[-1]), said
    finally:
        if runner is not None:
            runner.join(15)
        holder.rollback()
        holder.close()


def _limit(monkeypatch, seconds):
    from parsers import directory_watcher

    monkeypatch.setattr(models, "INDEX_WAIT_BEFORE_SECONDS", 30.0)    # the writer is young - no wait before the build
    monkeypatch.setattr(directory_watcher, "index_build_wait", lambda settings=None: seconds)


def test_a_build_waiting_past_its_limit_is_cut_put_off_and_built_by_the_next_try(table, monkeypatch):
    """Owner 11-08 ㄴ (1bcc2fa03 waited for ever): a writer left open while the build waits for it - cut at the limit,
    put off naming the writer; once it ends, the next try drops the INVALID leftover and builds."""
    _limit(monkeypatch, 2.0)
    holder = table.connect()
    try:
        pid = holder.execute(text("SELECT pg_backend_pid()")).scalar()
        holder.execute(text('INSERT INTO "%s" VALUES (999)' % TABLE))   # RowExclusive, transaction left open
        time.sleep(1.0)
        said = []
        cap = _cancel_the_build_after(table, 20)                        # the test's cap: without the limit, red here
        started = time.monotonic()
        try:
            word = _build(table, said)
        finally:
            cap.cancel()
        took = time.monotonic() - started
        assert word == (models.INDEX_DEFERRED, set()) and took < 15, (took, said)
        assert "cut - waited past index_build_wait_seconds (2s) for pid %s" % pid in said[-1], said
        assert _state(table) == "invalid", "the cut build's leftover - the next try's to repair"
    finally:
        holder.rollback()
        holder.close()
    said = []
    assert _build(table, said) == (models.INDEX_BUILT, {TABLE}) and _state(table) == "valid", said
    assert any("is INVALID from an earlier failure; dropping and rebuilding" in line for line in said), said


def test_a_build_whose_wait_ends_within_its_limit_is_built_as_before(table, monkeypatch):
    _limit(monkeypatch, 10.0)
    holder = table.connect()
    holder.execute(text('INSERT INTO "%s" VALUES (999)' % TABLE))
    ender = threading.Timer(1.5, holder.rollback)
    ender.start()
    said = []
    try:
        word = _build(table, said)
    finally:
        ender.join()
        holder.close()
    assert word == (models.INDEX_BUILT, {TABLE}) and _state(table) == "valid", said
    assert not any(" cut " in line for line in said), said
