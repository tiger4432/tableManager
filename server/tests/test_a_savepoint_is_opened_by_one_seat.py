# -*- coding: utf-8 -*-
"""S-271 · 판정 414. Every SAVEPOINT in this repository is opened by one function, and
that function RUNS the statement rather than sitting beside it.

🔴 THE CENSUS IS WHAT NARROWED THIS (S-271 ①, 2026-09-16). Of the 43 seats that borrow a
session and touch its transaction state, exactly ONE tracked seat opened a SAVEPOINT and
it already asked whether a transaction was open. The seat that did NOT ask was
`mappers/cross_table_lookup_mapper.py.sample` — the template an operator copies to build
a live mapper, and live mappers are gitignored. So the product asked and the example the
product ships did not, and nobody could count how many copies of the example exist.

⚠️ THE SHAPE, NOT ONLY THE CALL. A guard written as a line BESIDE the work survives being
deleted — the code still runs, just unguarded, which in a file meant to be copied and
edited is the defect arriving on a schedule. `in_savepoint` takes the work, so deleting
it deletes the statement.

⚠️ AND THE SUITE CANNOT SEE THE FAILURE ITSELF. pysqlite opens no transaction for a SELECT
and raises nothing, so the refusal path is unreachable here; the oracle below is
`true on any box` and the refusal is proved against the real thing under
`scripts/run_pg_tests.py`.
"""
import ast
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import operator_line                                                  # noqa: E402
from chain import session_contract                                               # noqa: E402

#: The one seat allowed to say it, plus the file that defines the word.
AUTHOR = "session_contract.py"
#: 🔴 `.sample` IS IN THE POPULATION ON PURPOSE. It is not dead text - it is the shape
#: every live mapper on an operator's box was copied from, and it is the only copy this
#: repository can reach.
SUFFIXES = (".py", ".py.sample")


def _files():
    for folder, dirs, files in os.walk(SERVER_DIR):
        dirs[:] = [d for d in dirs if d not in (".tmp", "__pycache__", "tests")]
        for name in sorted(files):
            if name.endswith(SUFFIXES):
                yield os.path.join(folder, name)


def _savepoint_callers(path):
    """Functions in `path` that call `begin_nested` - read off the AST, so renaming the
    variable that holds the session cannot hide one."""
    with open(path, encoding="utf-8") as handle:
        try:
            tree = ast.parse(handle.read(), path)
        except SyntaxError:                                            # pragma: no cover
            return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(node):
            if isinstance(call, ast.Call) and getattr(call.func, "attr", None) == "begin_nested":
                out.append(node.name)
                break
    return out


def test_only_one_function_in_the_repository_opens_a_savepoint():
    """🔴 THE GATE, AND IT WAS 1-OF-2 WHEN IT WAS WRITTEN. `.sample` is counted because a
    template that teaches the unguarded shape is how the next live mapper gets it."""
    offenders = []
    for path in _files():
        if os.path.basename(path) == AUTHOR:
            continue
        for function in _savepoint_callers(path):
            offenders.append("%s::%s" % (os.path.relpath(path, SERVER_DIR), function))

    assert offenders == [], (
        "these open a SAVEPOINT themselves instead of going through "
        "session_contract.in_savepoint, so each one decides for itself whether a "
        "transaction is open: " + ", ".join(offenders))


def test_the_oracle_would_see_the_shape_it_forbids():
    """⛔ A GATE THAT CANNOT GO RED IS NOT A GATE. Fed the exact shape the template had,
    so 「zero」 means 「none exist」 and not 「the walk never looks」."""
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "old_template.py.sample")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("def lookup(db, query):\n"
                         "    nested = db.begin_nested()\n"
                         "    rows = query.all()\n"
                         "    nested.commit()\n"
                         "    return rows\n")
        assert _savepoint_callers(path) == ["lookup"]


def test_the_guard_runs_the_work_rather_than_sitting_beside_it():
    """🔴 판정 414'S PROPERTY, ASSERTED. The subject of this round is a file operators
    COPY AND EDIT; a guard that can be deleted while the feature keeps working is a guard
    that gets deleted. `in_savepoint` takes the work as an argument, so there is nothing
    left to run if the call goes."""
    import inspect

    signature = inspect.signature(session_contract.in_savepoint)
    assert list(signature.parameters) == ["db", "where", "work"]

    ran = []

    class OpenSession:
        def in_transaction(self):
            return True

        def begin_nested(self):
            return type("Nested", (), {"commit": lambda s: ran.append("commit"),
                                       "rollback": lambda s: ran.append("rollback")})()

    answer = session_contract.in_savepoint(
        OpenSession(), "probe", lambda: ran.append("work") or "ANSWER")

    assert answer == "ANSWER", "the guard must hand back what the work returned"
    assert ran == ["work", "commit"]


def test_a_failing_statement_rolls_back_only_its_savepoint_and_re_raises():
    """⚠️ CONTAINMENT AND DEGRADATION ARE DIFFERENT JOBS. The caller decides what the row
    should say; this keeps the session alive and re-raises."""
    ran = []

    class OpenSession:
        def in_transaction(self):
            return True

        def begin_nested(self):
            return type("Nested", (), {"commit": lambda s: ran.append("commit"),
                                       "rollback": lambda s: ran.append("rollback")})()

    def boom():
        raise ValueError("bad view")

    with pytest.raises(ValueError):
        session_contract.in_savepoint(OpenSession(), "probe", boom)

    assert ran == ["rollback"], "a failed statement must not RELEASE the savepoint"


def test_a_session_with_no_transaction_gets_one_before_the_savepoint():
    """⚠️ A READ-ONLY ROUTE MAY NEVER HAVE ISSUED A STATEMENT, so whether a transaction is
    open depends on what the caller did - which is exactly what this seat may not assume."""
    ran = []

    class ClosedSession:
        def __init__(self):
            self.open = False

        def in_transaction(self):
            return self.open

        def begin(self):
            self.open = True
            ran.append("begin")

        def begin_nested(self):
            ran.append("nested")
            return type("Nested", (), {"commit": lambda s: None, "rollback": lambda s: None})()

    session_contract.in_savepoint(ClosedSession(), "probe", lambda: None)

    assert ran == ["begin", "nested"]


def test_the_refusal_names_the_seat_and_carries_no_driver_sentence():
    """🔴 25P01 MUST NOT REACH AN OPERATOR AS ITSELF. Production logs cannot be pasted
    here, so a line naming `no_active_sql_transaction` and no seat is a line nobody can
    act on. The refusal says which seat, what it could not do, and what to do next.

    ⚠️ The exception type is this repository's, not the driver's, so a caller can tell
    「the session could not carry this」 from 「the statement was wrong」."""
    class Poisoned:
        def in_transaction(self):
            return True                       # the SESSION's fact...

        def begin_nested(self):
            #: ...while the CONNECTION is in autocommit, so the server has no BEGIN.
            orig = type("Orig", (Exception,), {"pgcode": session_contract.NO_ACTIVE_TRANSACTION})()
            raise type("InternalError", (Exception,), {"orig": orig})()

    with pytest.raises(session_contract.SessionNotUsable) as raised:
        session_contract.in_savepoint(Poisoned(), "reference_view", lambda: "never")

    assert "reference_view" in str(raised.value)
    assert "25P01" not in str(raised.value)
    assert "no_active_sql_transaction" not in operator_line.restart_to_clear_the_pool()


@pytest.mark.pg
def test_against_a_real_poisoned_connection_the_operator_gets_a_line_not_25P01(pg_engine):
    """🔴 THE ONE THAT NEEDS POSTGRESQL, BUILT OUT OF THE INCIDENT ITSELF. The session is
    handed the very shape 2026-09-16 produced: a pooled connection left in autocommit, so
    `in_transaction()` is True (the SESSION's fact) while the server has no BEGIN (the
    CONNECTION's fact) and a SAVEPOINT has nothing to sit in.

    ⛔ pysqlite HAS NO SUCH RULE, so every assertion above is about the guard's SHAPE and
    this is the only one about what the database does. The plain suite's passed count says
    nothing here - it is `scripts/run_pg_tests.py` that runs this.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import QueuePool

    from conftest import PG_TEST_SCHEMA
    from tests.support.isolated_pg import scratch_connect_args

    pinned = create_engine(
        pg_engine.url.render_as_string(hide_password=False),
        poolclass=QueuePool, pool_size=1, max_overflow=0,
        connect_args=scratch_connect_args(PG_TEST_SCHEMA))
    try:
        # The leak S-272 closed, reproduced on purpose: mutate the POOL's connection and
        # give it back. The next checkout is the same one, still in autocommit.
        raw = pinned.raw_connection()
        raw.set_isolation_level(0)
        raw.close()

        session = sessionmaker(bind=pinned)()
        try:
            session.execute(text("SELECT 1"))
            assert session.in_transaction(), "the fixture did not reach the shape it tests"

            # ⚠️ THE WORK IS A REAL STATEMENT, because that is where the refusal lands:
            # SQLAlchemy defers the `SAVEPOINT`, so `begin_nested()` returns normally and
            # the server refuses on the first statement inside it. A fixture whose work
            # did nothing would pass on a build with no guard at all.
            with pytest.raises(session_contract.SessionNotUsable) as raised:
                session_contract.in_savepoint(
                    session, "reference_view",
                    lambda: session.execute(text("SELECT 1")).fetchall())

            assert "reference_view" in str(raised.value)
            assert "25P01" not in str(raised.value)
        finally:
            session.close()
    finally:
        pinned.dispose()


def test_an_unrelated_driver_error_is_not_swallowed():
    """⛔ THE NARROWNESS IS THE POINT, and it is the same shape
    `_is_business_key_unique_violation` has: turning every failure of `begin_nested` into
    this refusal would hide a real one behind a sentence about connections."""
    class Broken:
        def in_transaction(self):
            return True

        def begin_nested(self):
            raise RuntimeError("something else entirely")

    with pytest.raises(RuntimeError) as raised:
        session_contract.in_savepoint(Broken(), "probe", lambda: None)

    assert "something else entirely" in str(raised.value)
