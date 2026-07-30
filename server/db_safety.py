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
