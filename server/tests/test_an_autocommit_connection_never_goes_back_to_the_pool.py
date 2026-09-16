# -*- coding: utf-8 -*-
"""S-272. A seat that needs autocommit opens its OWN connection — the pool's is never
mutated and handed back.

🔴 WHAT PRODUCTION WAS EMITTING. `_analyze_after_load` reached autocommit through
`db.connection().engine.raw_connection()`, which is a POOLED connection:
`set_isolation_level(0)` mutates it and closing the proxy CHECKS IT BACK IN still in
autocommit. The next session to take it never begins a transaction — `session.begin()`
issues no BEGIN on an autocommit connection — so every `begin_nested()` on it raises
25P01 `no_active_sql_transaction`. That is the error the owner's chain was throwing.

⚠️ THE SUITE COULD NOT SEE IT. pysqlite has no such rule, so the seat is green on sqlite
forever; the first test here is `@pytest.mark.pg` and runs under
`server/scripts/run_pg_tests.py`. The second needs no database at all, which is the point:
the rule S-167 wrote down in PROSE three seats ago becomes a measurement here.
"""
import ast
import logging
import os
import subprocess
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the seat, against a real PostgreSQL pool
# ---------------------------------------------------------------------------

@pytest.mark.pg
def test_a_session_after_the_analyze_seat_can_still_open_a_savepoint(pg_engine, monkeypatch):
    """🔴 THE GATE, AND IT GOES RED ON THE OLD CODE. The pool is pinned to ONE connection,
    so the session opened after the seat runs is guaranteed to be handed the very
    connection the seat touched — without that pinning the test could pass by luck.

    ⛔ THE ASSERTION IS `begin_nested()`, NOT `autocommit`. The flag is the mechanism; the
    SAVEPOINT is what the chain actually needs and what 25P01 denied it.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import QueuePool

    from conftest import PG_TEST_SCHEMA
    from parsers import directory_watcher as watcher
    from tests.support.isolated_pg import scratch_connect_args

    # ⚠️ THE SAME SCRATCH SCHEMA `pg_engine` DROPS ON TEARDOWN, through the one spelling of
    # the search path (S-257) - so the probe table goes with it and nothing lands in
    # `public`. The pool is this engine's own, pinned to ONE connection.
    # ⚠️ `str(url)` MASKS THE PASSWORD - it renders `***`, and the seat under test builds a
    # psycopg2 DSN out of whatever URL its engine carries, so a masked one fails to connect
    # and (on a Korean-locale server) surfaces as a UnicodeDecodeError from libpq's message
    # rather than as an auth error. Measured while writing this test.
    pinned = create_engine(
        pg_engine.url.render_as_string(hide_password=False),
        poolclass=QueuePool, pool_size=1, max_overflow=0,
        connect_args=scratch_connect_args(PG_TEST_SCHEMA))
    try:
        with pinned.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS s272_probe"))
            conn.execute(text("CREATE TABLE s272_probe (k text)"))

        Session = sessionmaker(bind=pinned)
        monkeypatch.setattr(watcher, "SessionLocal", Session)
        monkeypatch.setattr(watcher, "analyze_after_rows", lambda: 1)

        assert watcher._analyze_after_load("s272_probe", rows=10) is True, (
            "the seat did not run, so this proves nothing about what it leaves behind")

        after = Session()
        try:
            after.execute(text("SELECT 1"))
            nested = after.begin_nested()      # 🔴 25P01 here on the leaking build
            nested.rollback()
        finally:
            after.close()
    finally:
        with pinned.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS s272_probe"))
        pinned.dispose()


# ---------------------------------------------------------------------------
# ⚠️ ⓐ-bis — the arm where the search path cannot be read (S-275 ③)
# ---------------------------------------------------------------------------

def test_an_unreadable_search_path_is_named_and_costs_only_the_statistics(monkeypatch,
                                                                          caplog):
    """⚠️ MEASURED RATHER THAN ASSUMED, WHICH IS WHY IT HAS A TEST NOW. The dedicated
    connection does not inherit the app's `search_path`, so the seat asks for it - and
    that ask can fail. The answer is the one this seat always gives: it says what it
    could not read, falls back to the server's default path, and NEVER raises, because
    the rows are already durable and a failed re-analyse must not turn into a file
    reported as FAILED.

    🔴 THE TWO ARMS WERE ONE `try` UNTIL THIS TEST, AND THEIR FALLBACKS DIFFER. A failure
    reaching the URL (`db.bind` / `get_bind` / `engine.url`) left `url` unbound while the
    single `except` set only `search_path`, and the seat died on a NameError below -
    reported as 「could not re-analyse」, true and silent about why. A raising `SHOW` was
    never the trigger: `url` is assigned before it. They are separate arms now.
    """
    from parsers import directory_watcher as watcher

    class Session:
        def __init__(self):
            self.closed = False
            self.bind = type("Bind", (), {"url": "postgresql://u@h/db"})()

        def execute(self, *_args, **_kwargs):
            raise RuntimeError("SHOW is not allowed here")

        def close(self):
            self.closed = True

    made = []
    monkeypatch.setattr(watcher, "SessionLocal", lambda: made.append(Session()) or made[-1])
    monkeypatch.setattr(watcher, "analyze_after_rows", lambda: 1)
    caplog.clear()

    with caplog.at_level(logging.INFO):
        answer = watcher._analyze_after_load("s275_probe", rows=10)

    assert answer is False, "a failed re-analyse must be an answer, never an exception"
    assert made and made[0].closed, "the borrowed session is closed on every arm"
    said = [r.getMessage() for r in caplog.records if "search_path unreadable" in r.getMessage()]
    assert len(said) == 1, [r.getMessage() for r in caplog.records]
    assert "s275_probe" in said[0]


# ---------------------------------------------------------------------------
# ⛔ ⓑ — the drift oracle: no seat mutates a POOLED connection's isolation
# ---------------------------------------------------------------------------

def _functions_that_mutate_isolation(path):
    """Every function in `path` that calls `set_isolation_level`, with how it got its
    connection — read from the SYNTAX, so a rename of the variable cannot hide it."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), path)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names = {getattr(call.func, "attr", None)
                 for call in ast.walk(node) if isinstance(call, ast.Call)}
        if "set_isolation_level" not in names:
            continue
        out.append((node.name, names))
    return out


def test_no_seat_takes_a_pooled_connection_and_changes_its_isolation():
    """⛔ THE RULE S-167 WROTE IN PROSE, AS A MEASUREMENT (S-272). Three seats in this
    repository need an autocommit connection, and the one that took the pool's put
    production on 25P01 for a day. A function that calls `set_isolation_level` must have
    got its connection from `psycopg2.connect` — never `raw_connection`, which hands out
    the pool's.

    ⚠️ THE SUBJECT IS THE SYNTAX, WHICH THE STANDING RULE PERMITS: the claim is about what
    the source DOES, read off the AST rather than a regex over text, and a seat added
    tomorrow is caught by the same walk. A behavioural version would need a PostgreSQL
    pool per candidate seat and would still only cover the seats somebody remembered.
    """
    offenders = []
    for folder, _dirs, files in os.walk(SERVER_DIR):
        if any(part in folder for part in (".tmp", "__pycache__", "tests")):
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            for function, names in _functions_that_mutate_isolation(path):
                if "connect" in names and "raw_connection" not in names:
                    continue
                offenders.append("%s::%s" % (os.path.relpath(path, SERVER_DIR), function))

    assert offenders == [], (
        "these seats change the isolation of a connection they did not open; closing it "
        "returns it to the pool in autocommit and the next session cannot BEGIN: "
        + ", ".join(offenders))


def test_the_oracle_would_see_the_shape_it_forbids():
    """🔴 A GATE THAT CANNOT GO RED IS NOT A GATE. The scanner is fed the exact shape the
    seat had before this round, so 「zero offenders」 means 「none exist」 and not 「the walk
    never looks」."""
    import tempfile

    source = (
        "def leaky(db):\n"
        "    connection = db.connection().engine.raw_connection()\n"
        "    connection.set_isolation_level(0)\n"
        "    connection.close()\n")
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "leaky.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
        found = _functions_that_mutate_isolation(path)

    assert [name for name, _ in found] == ["leaky"]
    assert "raw_connection" in found[0][1] and "connect" not in found[0][1]
