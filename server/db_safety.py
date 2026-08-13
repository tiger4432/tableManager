# -*- coding: utf-8 -*-
"""A test process must not be able to reach a real database. [board #16a]

THE INCIDENT
    `main.py` builds the physical schema at boot (`Base.metadata.create_all`).
    That statement used to run at module *import*, so anything that merely
    imported the app - pytest collecting the suite - issued DDL against whatever
    DATABASE_URL resolved to. Unset, that default is the production PostgreSQL,
    and it happened: new (empty) tables appeared in production purely from
    running tests. The DDL has since moved into `bootstrap_database_schema()`,
    but "it is fine as far as we checked" is not a mechanism, which is why item
    #16a stayed open while its sibling #16b (tests writing the operator's live
    `config/maps.json`) was closed with an assertion that breaks when the
    isolation is removed.

WHY THIS IS PRODUCTION CODE AND NOT A FIXTURE
    `server/tests/conftest.py` pins DATABASE_URL to an isolated database before
    it imports the app, and that pin is what kept the old leak harmless. But a
    pin is something the TEST TREE does, so deleting it deletes the protection
    with it. The guards here live in the modules under test. Deleting the pin
    now does not disarm them - it makes the suite fail loudly.

THE RULE IS AN ALLOWLIST, NOT A BLOCKLIST
    "anything except assy_manager" fails open the day a second production
    database exists, or the day someone renames this one. `check_test_database`
    therefore names what is ALLOWED - sqlite, or exactly the URL the operator
    declared in ASSY_TEST_DATABASE_URL - and refuses everything else, including
    URLs that merely look harmless. Being unable to PROVE the target is
    isolated is itself a refusal (the same stance `scripts/dev_env/iso_watcher.py`
    takes, and for the same reason).

WHAT THIS DELIBERATELY DOES NOT DO
    Outside pytest every entry point below is a no-op that returns before it
    looks at anything. In particular `main.bootstrap_database_schema` keeps its
    UNGUARDED `create_all`: a production web server whose database is
    unreachable must abort at boot, loudly, rather than serve a schema-less app.
    Nothing here wraps that statement in a try/except or softens its failure -
    the guard refuses BEFORE it, only ever inside a test process.

THE THREE NETS (each has its own regression test + defect injection)
    1. `install_test_database_guard(engine)` - `do_connect` on the one engine
       that carries the production credentials. Refuses before the socket opens.
    2. `install_global_test_database_guard()` - `engine_connect` on the Engine
       CLASS, so an engine a test builds for itself is covered too. Fires before
       any statement can be executed (the socket may already be open by then;
       net 1 is the one that prevents that, for the engine that matters).
    3. `require_test_database(...)` at the DDL entry point - a PURE decision,
       taken with no connection opened at all, on whatever bind the caller
       passed. This is the one that answers #16a directly.

THE SECOND GUARD IN THIS FILE - "this OPERATOR PASS must not be able to write"
    Below the test-database guard lives the READ-ONLY guard: the same genus of
    property (a refusal the server enforces, not a sentence a reader has to
    believe) pointed at a different question. It is here rather than in a module
    of its own because this file is already the place a reader looks for "what
    stops this process from touching what it must not touch", and because the
    alternative has been tried: the property had THREE spellings across seven
    operator scripts, one of which was wrong, and it spread by being copied.
"""
import os
import sys

#: The env var `server/tests/conftest.py` reads to redirect the suite at an
#: isolated database. Declaring it here is the ONLY way a non-sqlite target
#: becomes legal inside a test process.
TEST_DATABASE_URL_ENV = "ASSY_TEST_DATABASE_URL"

#: Present in every refusal, so a test can pin the reason rather than the
#: exception type (an OperationalError from an unreachable host would otherwise
#: satisfy a bare `pytest.raises`).
REFUSAL_MARKER = "[#16a] REFUSED"


def under_pytest():
    """True when this process, or a process a test spawned, is a test process.

    Three signals, and the two environment variables are in the list on purpose:
    they are INHERITED by subprocesses, so a probe a test shells out to is still
    a test process and is still refused. `sys.modules` is the signal that is
    already true while conftest.py is being imported - before any test has
    started, which is exactly when the old import-time DDL fired.
    """
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("PYTEST_VERSION"):
        return True
    return "pytest" in sys.modules


def _parts(url):
    """``(backend, host, port, database)`` with credentials dropped, or None.

    Parsed with SQLAlchemy's own `make_url` rather than `urllib`, so the verdict
    is about the place the engine would actually connect to and not about a
    second, subtly different reading of the same string. Anything it cannot
    parse comes back as None, which every caller treats as a refusal.
    """
    if not url or not isinstance(url, str):
        return None
    try:
        from sqlalchemy.engine import make_url
        u = make_url(url)
    except Exception:
        return None
    backend = (u.get_backend_name() or "").lower()
    if not backend:
        return None
    return (backend, (u.host or "").lower(), str(u.port or ""), u.database or "")


def check_test_database(url, *, production_url=None, opt_in=None):
    """Violations that make `url` illegal for a test process. ``[]`` = allowed.

    A pure decision: no engine, no connection, no filesystem, no environment
    beyond the opt-in the caller may also pass explicitly. A caller - including
    a test - can ask "would this be refused?" with nothing pointed anywhere.
    """
    if opt_in is None:
        opt_in = os.environ.get(TEST_DATABASE_URL_ENV) or None

    parts = _parts(url)
    if parts is None:
        return ["the target database URL could not be parsed "
                f"({url!r}), so this process cannot PROVE it is isolated. "
                "Unprovable is refused."]
    backend, host, port, database = parts

    # Production here is PostgreSQL. sqlite - in memory or a file - is never it,
    # and it is what conftest.py pins the suite to.
    if backend == "sqlite":
        return []

    where = f"{database or '?'} on {host or '?'}:{port or '?'}"
    opt_parts = _parts(opt_in) if opt_in else None
    if opt_parts is None:
        return [f"the target is a {backend} database ({where}) and no "
                f"{TEST_DATABASE_URL_ENV} declares it as a test database. A "
                "test process may only touch sqlite, or exactly the URL named "
                f"in {TEST_DATABASE_URL_ENV}."]
    if opt_parts != parts:
        return [f"the target is a {backend} database ({where}) but "
                f"{TEST_DATABASE_URL_ENV} declares a different one "
                f"({opt_parts[3] or '?'} on {opt_parts[1] or '?'}:"
                f"{opt_parts[2] or '?'}). The declaration must name the target "
                "it is vouching for."]

    prod = _parts(production_url) if production_url else None
    if prod and database and database == prod[3]:
        return [f"{TEST_DATABASE_URL_ENV} names database {database!r}, which is "
                "the PRODUCTION database. Declaring production as the test "
                "target does not make it one."]
    return []


def require_test_database(url, *, context, production_url=None, opt_in=None):
    """Raise unless `url` is legal for this process. No-op outside pytest.

    `context` names the operation being refused and appears in the message, so
    an operator reading the traceback learns what was about to happen rather
    than only that something was blocked.
    """
    if not under_pytest():
        return
    violations = check_test_database(url, production_url=production_url,
                                     opt_in=opt_in)
    if not violations:
        return
    detail = "\n".join(f"  - {v}" for v in violations)
    raise RuntimeError(
        f"{REFUSAL_MARKER}: {context} would run against a database that a test "
        f"process must not touch.\n  target: {url}\n{detail}\n"
        f"  Pin DATABASE_URL to an isolated database (server/tests/conftest.py "
        f"does this before it imports the app), or declare the isolated one in "
        f"{TEST_DATABASE_URL_ENV}."
    )


def install_test_database_guard(engine, *, production_url=None):
    """Net 1 - refuse BEFORE the socket opens, for one engine.

    `do_connect` is the last dialect hook before the DBAPI connection is
    created, so raising here means a test process never opens a session to a
    real database at all - not even to be turned away by it. Reserved for the
    engine that carries the production credentials.
    """
    from sqlalchemy import event

    @event.listens_for(engine, "do_connect")
    def _refuse_non_test_database(dialect, conn_rec, cargs, cparams):
        require_test_database(str(engine.url),
                              context="opening a database connection",
                              production_url=production_url)
        return None  # None = proceed with the dialect's own connect

    return _refuse_non_test_database


_GLOBAL_GUARD_INSTALLED = False


def install_global_test_database_guard(*, production_url=None):
    """Net 2 - the same refusal for EVERY engine in the process.

    Class-level, so an engine a test builds for itself is covered without
    anyone remembering to arm it. `engine_connect` fires when a Connection is
    created, i.e. before any statement can be executed; the physical socket may
    already be open at that point, which is why net 1 exists for the engine
    whose URL is production's.

    Idempotent: importing `database.database` more than once must not stack
    listeners.
    """
    global _GLOBAL_GUARD_INSTALLED
    if _GLOBAL_GUARD_INSTALLED:
        return False
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "engine_connect")
    def _refuse_non_test_database(conn):
        require_test_database(str(conn.engine.url),
                              context="opening a database connection",
                              production_url=production_url)

    _GLOBAL_GUARD_INSTALLED = True
    return True


# =============================================================================
# THE READ-ONLY GUARD - one home, because a copy carries whatever the original
# got wrong
# =============================================================================
# WHY THIS IS CONSOLIDATED AND NOT MERELY TIDIED
#     Seven operator scripts each need "this pass cannot write, and PostgreSQL is
#     what says so". Before this section there were THREE spellings of that one
#     property, and the scripts did not each invent theirs - they COPIED. One of
#     the things being copied was wrong, so the defect propagated by the same
#     mechanism the safety property did.
#
# THE SPELLING THAT WAS WRONG, MEASURED RATHER THAN ASSUMED
#     `conn.execute(text("SET SESSION default_transaction_read_only = on"))`
#     is what a read-only pre-flight looks like. Measured on the isolated
#     `assy_qa` (PostgreSQL 18.3 / SQLAlchemy 2.0.49 / psycopg2 2.9.11) on
#     2026-08-13, on a connection at the ORDINARY isolation level - which is what
#     `engine.connect()` gives you:
#
#         default_transaction_read_only = on    <- the variable one would check
#         transaction_read_only         = off   <- the one PostgreSQL enforces
#         CREATE / INSERT / UPDATE              ALL THREE ACCEPTED
#
#     The SET itself BEGINS the implicit transaction, so the transaction it runs
#     in was opened under the old default and keeps it, and a rollback discards
#     the SET outright. On a connection already switched to AUTOCOMMIT the same
#     two lines DO engage (measured: writes refused, before and after a
#     rollback) - which is worse, not better: it means the property held by
#     accident, on a setting that was there for an unrelated reason, and the two
#     arrangements are indistinguishable from inside a script that never reads
#     the flag back. None of them did.
#
# THE TWO SPELLINGS THAT WORK, AND THE DIFFERENCE THAT IS REAL
#     They are not interchangeable, so this module exposes BOTH rather than
#     picking one and silently breaking the caller the other one existed for:
#
#     CONNECT_TIME     `-c default_transaction_read_only=on` in `connect_args`,
#                      on an engine of OUR OWN with `NullPool`. The server applies
#                      it before this session's first transaction exists and
#                      re-applies it to every transaction after. Strongest, and
#                      independent of isolation level - but it requires BUILDING
#                      an engine, so it is only available to a caller that has a
#                      URL rather than somebody else's engine.
#     PER_TRANSACTION  `postgresql_readonly=True`, SQLAlchemy's own option, which
#                      sets the per-transaction flag at each begin. Works on a
#                      BORROWED engine - the application's pool, or one a caller
#                      built from `--url` - with no second engine and no second
#                      pool. This is what `scripts/audit_schema_canon.py` needs:
#                      its entry points take an `engine` parameter and must accept
#                      one they did not build.
#
#     Measured, both arms, same box, same day: `transaction_read_only = on`,
#     CREATE/INSERT/UPDATE all refused with `ReadOnlySqlTransaction`, still
#     refused after an explicit `rollback()` and on the transaction after that.
#
# GETTING THE MODE WRONG IS A REFUSAL, NOT A HOLE
#     `PER_TRANSACTION` names the mechanism, not a promise, and a caller who picks
#     the wrong one for their engine gets an UNARMED connection - which
#     `assert_readonly` then refuses, because the answer comes from the server
#     rather than from which branch was taken. That is the property the old code
#     did not have and is the reason every door below ends in a read-back.

#: Present in every refusal, so a caller can pin the reason rather than the
#: exception type - the same discipline as `REFUSAL_MARKER` above. An
#: `OperationalError` from an unreachable host would otherwise satisfy a bare
#: `pytest.raises(RuntimeError)`.
READONLY_REFUSAL = "[read-only guard] REFUSED"

#: `open_readonly_connection` modes. See the block comment above for which one a
#: given caller can actually use; the short version is "did you build the engine".
CONNECT_TIME = "connect_time"
PER_TRANSACTION = "per_transaction"

#: The base connect-time options. `client_encoding` matches
#: `database/database.py` so a script does not read text differently from the app.
#:
#: WHAT IS DELIBERATELY NOT IN HERE: `lock_timeout` and
#: `idle_in_transaction_session_timeout`, which `scripts/diagnose_wal_headroom.py`
#: also pins. Adding a timeout to a pass that does a full GROUP BY over every
#: table carrying `business_key_val` on a 14 GB database would turn a pre-flight
#: that works today into one that fails - a separate decision from arming the
#: guard. `statement_timeout` is available per caller instead, below.
READONLY_OPTIONS = "-c default_transaction_read_only=on -c client_encoding=utf8"


def readonly_options(statement_timeout_ms=None):
    """The `connect_args["options"]` string, with an optional statement timeout.

    A builder rather than seven constants: the timeout is the only part that
    legitimately differs between callers (the two business-key scripts cap their
    counting pass at 120 s; the migration has never had a cap and adding one is
    not this lane's decision to make).
    """
    if not statement_timeout_ms:
        return READONLY_OPTIONS
    return f"{READONLY_OPTIONS} -c statement_timeout={int(statement_timeout_ms)}"


def open_readonly_engine(url=None, *, application_name="assy_readonly_pass",
                         statement_timeout_ms=None):
    """An engine every one of whose transactions is read-only, armed at connect.

    `NullPool` is load-bearing rather than tidiness: these connections must never
    be handed to anything else, and an engine of our own has no next checkout to
    poison. It is also what retires the `invalidate()` dance the old code needed -
    the old pattern set a session variable on a connection borrowed from the
    APPLICATION pool, and an apply run that followed a check run in the same
    process failed every CREATE with `ReadOnlySqlTransaction`.

    `application_name` is worth setting per caller: it is what an operator reads
    out of `pg_stat_activity` when they want to know which script is holding a
    connection on production.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    if url is None:
        from database.database import SQLALCHEMY_DATABASE_URL
        url = SQLALCHEMY_DATABASE_URL
    return create_engine(
        url, poolclass=NullPool,
        connect_args={"options": readonly_options(statement_timeout_ms),
                      "application_name": application_name})


def readonly_state(conn):
    """What PostgreSQL says about this connection, as a string. No judgement.

    Exists so a script that wants to PRINT the flag for an operator does not have
    to spell `SHOW transaction_read_only` a second time. The literal appearing in
    exactly one file is what makes "is the read-back consulting the right
    variable?" a question with one answer rather than seven.
    """
    from sqlalchemy import text
    return conn.execute(text("SHOW transaction_read_only")).scalar()


def assert_readonly(conn):
    """Refuse unless POSTGRESQL ITSELF reports that this connection cannot write.

    A guard that cannot verify itself is the defect this exists to end, so the
    answer comes from the server rather than from the fact that an option string
    was passed or a branch was taken.

    `default_transaction_read_only` is deliberately NOT what gets consulted: it
    reads `on` in the arrangement that ACCEPTS writes, which is exactly the lie.
    """
    try:
        armed = readonly_state(conn)
    except Exception as exc:
        raise RuntimeError(
            f"{READONLY_REFUSAL}: `transaction_read_only` could not be read from "
            f"this connection ({type(exc).__name__}: "
            f"{str(exc).strip().splitlines()[0]}). This is a PostgreSQL operator "
            f"script and it will not run a pass it cannot prove is read-only."
        ) from exc
    if str(armed).lower() != "on":
        raise RuntimeError(
            f"{READONLY_REFUSAL}: PostgreSQL reports "
            f"transaction_read_only={armed!r} on the connection this run reads "
            f"with. Refusing to run a pass that is not actually protected.")
    return conn


def assert_writable(conn):
    """The mirror, for `--apply`. Fails BEFORE the first statement, not during.

    This is the direct net for a recorded incident: a read-only flag inherited
    from a pooled connection surfaced as `ReadOnlySqlTransaction` on every
    individual CREATE/DROP, halfway through a run that had already changed some
    of the catalogue.
    """
    armed = readonly_state(conn)
    if str(armed).lower() != "off":
        raise RuntimeError(
            f"{READONLY_REFUSAL} (inverted): a write pass was asked for but "
            f"PostgreSQL reports transaction_read_only={armed!r} on the "
            f"connection that would do the writing. Nothing was attempted.")
    return conn


def open_readonly_connection(engine, *, mode=CONNECT_TIME):
    """THE ONLY DOOR to a read-only pass: connect, then PROVE it, or refuse.

    `mode=CONNECT_TIME` expects an engine from `open_readonly_engine`; the
    AUTOCOMMIT here is not what arms the guard (that is the connect option) and
    the guard is verified to hold without it. It is set because a counting pass
    over a large catalogue should not hold one snapshot and one
    `idle in transaction` slot open for its whole run.

    `mode=PER_TRANSACTION` arms THIS connection on a borrowed engine and leaves
    the engine alone. Deliberately not AUTOCOMMIT: callers in this mode roll back
    to recover from an expected per-statement error, and the flag is re-applied
    to the transaction after the rollback (measured, not assumed).
    """
    if mode == PER_TRANSACTION:
        conn = engine.connect().execution_options(postgresql_readonly=True)
    elif mode == CONNECT_TIME:
        conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    else:
        raise ValueError(f"unknown read-only mode {mode!r}; expected "
                         f"{CONNECT_TIME!r} or {PER_TRANSACTION!r}")
    try:
        assert_readonly(conn)
    except BaseException:
        conn.close()
        raise
    return conn


def close_readonly_connection(conn):
    """Uniform teardown, so no caller has to remember which mode it opened with.

    ⚠️ THE `invalidate()` IS DEFENCE IN DEPTH AND THIS COMMENT WILL NOT CLAIM
    OTHERWISE. It was carried here from a docstring that said a session setting
    left on a pooled connection "becomes the next checkout's problem". Measured
    on this box on 2026-08-13, on SQLAlchemy 2.0.49 with a `QueuePool`, it does
    not: with `close()` alone the next checkout read `transaction_read_only=off`
    and accepted a write, for BOTH the `postgresql_readonly` arm and the raw
    `SET SESSION` arm (the pool's reset-on-return rollback discards the SET, and
    SQLAlchemy resets its own option). It is kept because it costs one discarded
    socket and does not depend on that version-specific reset behaviour staying
    true - but a reader must not size the risk of removing it from a claim
    nobody had measured.
    """
    try:
        conn.invalidate()
    finally:
        conn.close()
