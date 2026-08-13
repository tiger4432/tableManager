# -*- coding: utf-8 -*-
"""The read-only pre-flight of all SEVEN operator scripts, and its one home.

THE PROPERTY NOW HAS ONE DEFINITION - `server/db_safety.py`
    It had three spellings across seven scripts, one of them wrong, and the
    scripts did not each invent theirs: they COPIED. `test_no_script_carries_its
    _own_copy_of_the_guard` is the assertion that keeps it that way, and it is
    structural rather than textual - it asks whether each script's name for a
    guard IS the home's object.

THE SEVEN DOORS ARE EXERCISED AGAINST A REAL SERVER, NOT DESCRIBED
    `DOORS` opens each script's own read-only path the way the script opens it,
    and `_assert_guard_holds` puts the same four questions to every one: the flag
    reads back `on`, a real write is REFUSED, the refusal survives a rollback, and
    the identical write SUCCEEDS on a writable engine - that last one being the
    control that separates "the guard works" from "those three statements were
    broken".

THE INJECTION
    `test_injecting_spelling_c_into_the_home_turns_every_door_red` restores the
    retired spelling INSIDE `db_safety` and asserts that `_assert_guard_holds` -
    the same function, not a re-spelling of it - then FAILS for every door. A
    guard whose removal changes nothing is not a guard, and this file has no way
    to know it is discriminating anything without that arm.

WHAT WAS WRONG, MEASURED RATHER THAN ASSUMED
    Three of the seven armed their read-only pass with

        conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("SET SESSION default_transaction_read_only = on"))

    ⚠️ IN THAT ORDER IT WORKED. Measured on an isolated PostgreSQL 18.3 with
    SQLAlchemy 2.0.49 / psycopg2 2.9.11 on 2026-08-13: `execution_options` puts
    psycopg2 into autocommit on that very Connection, so there is no open
    transaction for the SET to be trapped inside; `transaction_read_only` read
    `on` and CREATE/INSERT/UPDATE were all refused, before and after a rollback.
    Nothing was ever written by a check pass that should not have been, and this
    file does not claim otherwise.

    🔴 THE DEFECT IS THAT THE SAFETY PROPERTY RESTED ON A SETTING THAT WAS THERE
    FOR AN UNRELATED REASON, AND THAT NOTHING VERIFIED IT. AUTOCOMMIT is in
    `add_business_key_unique_index.py` because `CREATE INDEX CONCURRENTLY` cannot
    run in a transaction block; the other two inherited the shape. Under the
    ORDINARY isolation level the identical statement lands inside an implicit
    transaction that began under the old default and keeps it:

        default_transaction_read_only = on    <- the variable one would check
        transaction_read_only         = off   <- the one PostgreSQL enforces
        CREATE TABLE                          ACCEPTED

    Those two arrangements are indistinguishable from inside a script that never
    reads the flag back, and none of the three did.

WHAT THIS FILE PINS
    * the flag is armed as a CONNECTION OPTION, so it holds on every connection of
      the engine, after a rollback, and under EITHER isolation level;
    * the scripts REFUSE rather than proceed when the server does not confirm it;
    * `default_transaction_read_only` is not what gets checked - a stub that
      answers `on` there and `off` for `transaction_read_only` is exactly the lie,
      and must be refused;
    * `--apply` gets a SECOND, writable connection, and the counting pass never
      holds it.

    `test_the_old_pattern_fails_the_property_this_file_pins` carries the defect
    itself, so these assertions cannot become a tautology: it builds the old
    pattern on a live server and asserts it does NOT satisfy them.

REPLACES THREE TESTS IN `test_business_key_unique_migration.py`
    `test_check_mode_pins_the_session_read_only_and_then_discards_it` asserted the
    removed statement and the `invalidate()` that went with it; the other two used
    a `FakeEngine` that `run()` can no longer derive a read-only engine from.
    Their claims live on here, restated against what the code does now.

SKIPPING, NOT FAILING, is the contract when no PostgreSQL is declared - the same
`conftest.PG_TEST_URL_ENV` door `test_pg_multirow_upsert.py` uses:

    ASSY_PG_TEST_DATABASE_URL=postgresql://postgres:...@localhost:5432/assy_qa \
        python -m pytest server/tests/test_readonly_guard.py
"""
import ast
import inspect
import itertools
import re

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from conftest import _declared_as_test_database, _resolve_pg_test_url

import db_safety
import migrations.add_business_key_unique_index as mig
import migrations.drop_redundant_layering_indexes as dropidx
import scripts.audit_schema_canon as canon
import scripts.check_missing_business_key as checkbk
import scripts.dedupe_business_key_rows as dedupe
import scripts.dev_env.snapshot_db as snapshot
import scripts.rebuild_blank_business_keys as rebuild

#: The three modules that re-export the whole four-name surface. Kept as a
#: parameter set because the stub-level claims are about the shared functions and
#: these are the modules a caller reaches them through by name.
GUARDS = [
    pytest.param(mig, id="add_business_key_unique_index"),
    pytest.param(rebuild, id="rebuild_blank_business_keys"),
    pytest.param(dedupe, id="dedupe_business_key_rows"),
]

#: 🔴 ALL SEVEN. Every script that needs "this pass cannot write", with the door
#: it actually opens - not a re-creation of it here. `opener(url)` returns
#: `(engine, connection)`; whatever the script does to get a proven-read-only
#: connection is what gets tested, so a script that quietly stops using the
#: shared home fails these rather than passing a test of the home.
#:
#: THE SEVENTH IS NOT LIKE THE OTHER SIX AND THAT IS THE POINT. `audit_schema
#: _canon` takes an engine it did not build (`--url`, or the application's pooled
#: engine), so it cannot arm at connect time and uses `PER_TRANSACTION`. It is in
#: the same table under the same assertions: the mode differs, the property does
#: not.
def _door_connect_time(module):
    def opener(url):
        engine = module.open_readonly_engine(url)
        return engine, module.open_readonly_connection(engine)
    return opener


def _door_audit(url):
    """The borrowed-engine arm. A plain engine, armed per transaction."""
    engine = sa.create_engine(url, poolclass=sa.pool.NullPool)
    return engine, canon.readonly_connection(engine)


def _door_snapshot(url):
    """`open_source_readonly` returns `(engine, conn)` and adds a live write
    probe on top of the shared read-back."""
    return snapshot.open_source_readonly(url)


DOORS = [
    pytest.param(_door_connect_time(mig), id="add_business_key_unique_index"),
    pytest.param(_door_connect_time(dropidx), id="drop_redundant_layering_indexes"),
    pytest.param(_door_connect_time(rebuild), id="rebuild_blank_business_keys"),
    pytest.param(_door_connect_time(dedupe), id="dedupe_business_key_rows"),
    pytest.param(_door_connect_time(checkbk), id="check_missing_business_key"),
    pytest.param(_door_snapshot, id="dev_env.snapshot_db"),
    pytest.param(_door_audit, id="audit_schema_canon"),
]

#: Every module that must not carry its own copy, with the guard names it binds.
#: `open_readonly_engine` is deliberately NOT in this list: each script legitimately
#: wraps it to name itself in `pg_stat_activity` and to choose its statement
#: timeout, and those wrappers are asserted thin separately.
SHARED_NAMES = ("assert_readonly", "assert_writable", "open_readonly_connection",
                "close_readonly_connection", "readonly_state", "READONLY_REFUSAL",
                "READONLY_OPTIONS")

CONSOLIDATED = [
    pytest.param(mig, id="add_business_key_unique_index"),
    pytest.param(dropidx, id="drop_redundant_layering_indexes"),
    pytest.param(rebuild, id="rebuild_blank_business_keys"),
    pytest.param(dedupe, id="dedupe_business_key_rows"),
    pytest.param(checkbk, id="check_missing_business_key"),
    pytest.param(snapshot, id="dev_env.snapshot_db"),
    pytest.param(canon, id="audit_schema_canon"),
]

SCHEMA = "roguard_pytest"


# ===========================================================================
# Stubs - no database
# ===========================================================================

class _Scalar:
    def __init__(self, v):
        self._v = v

    def scalar(self):
        return self._v


class FlagConn:
    """A connection that answers the two SHOWs however the test wants.

    The interesting instance is `FlagConn(transaction="off", default="on")`: that
    is precisely what the old pattern produced under the ordinary isolation
    level, and a guard that consults the wrong variable calls it armed.
    """

    def __init__(self, transaction="on", default="on", raises=None):
        self.transaction, self.default, self.raises = transaction, default, raises
        self.sql = []

    def execution_options(self, **kw):
        return self

    def execute(self, clause, params=None):
        s = str(clause)
        self.sql.append(s)
        if self.raises is not None:
            raise self.raises
        if "SHOW default_transaction_read_only" in s:
            return _Scalar(self.default)
        if "SHOW transaction_read_only" in s:
            return _Scalar(self.transaction)
        return _Rows([])

    def close(self):
        pass

    def invalidate(self):
        pass


class _Rows(list):
    def fetchall(self):
        return list(self)

    def first(self):
        return self[0] if self else None


class CatalogueConn(FlagConn):
    """`FlagConn` that also answers the migration's catalogue queries."""

    def __init__(self, redundant_rows=(), tables=(), **kw):
        super().__init__(**kw)
        self._redundant, self._tables = list(redundant_rows), list(tables)

    def execute(self, clause, params=None):
        s = str(clause)
        if "SHOW " in s:
            return super().execute(clause, params)
        self.sql.append(s)
        if "information_schema" in s:
            return _Rows([(t,) for t in self._tables])
        if "xd.indkey = xp.indkey" in s:
            return _Rows(self._redundant)
        return _Rows([])


class FakeEngine:
    def __init__(self, conn):
        self._conn = conn

    def connect(self):
        return self._conn

    def dispose(self):
        pass


class ExplodingEngine:
    """A writable engine that fails if anything so much as connects to it."""

    url = "postgresql://never/used"

    def connect(self):
        raise AssertionError("the counting pass opened the WRITABLE engine")


# ===========================================================================
# 1. The guard consults the flag PostgreSQL enforces, and refuses on it
# ===========================================================================

@pytest.mark.parametrize("module", GUARDS)
def test_assert_readonly_accepts_only_an_armed_connection(module):
    assert module.assert_readonly(FlagConn(transaction="on")) is not None


@pytest.mark.parametrize("module", GUARDS)
def test_the_variable_that_lied_is_not_the_one_consulted(module):
    """🔴 THE CENTRAL CLAIM. `default_transaction_read_only='on'` with
    `transaction_read_only='off'` is not a hypothetical: it is what the old
    pattern produced under the ordinary isolation level, and writes were
    ACCEPTED in it. A guard reading the first variable calls that armed."""
    conn = FlagConn(transaction="off", default="on")
    with pytest.raises(RuntimeError) as err:
        module.assert_readonly(conn)
    assert module.READONLY_REFUSAL in str(err.value)
    assert "transaction_read_only='off'" in str(err.value)
    assert any("SHOW transaction_read_only" in s for s in conn.sql), (
        "the guard did not ask for the flag PostgreSQL enforces")


@pytest.mark.parametrize("module", GUARDS)
def test_a_connection_that_cannot_answer_is_refused_not_assumed(module):
    """Unprovable is refused - the stance `db_safety.check_test_database` takes.
    A connection whose backend has no such setting is not a read-only one."""
    with pytest.raises(RuntimeError) as err:
        module.assert_readonly(FlagConn(raises=Exception("no such setting")))
    assert module.READONLY_REFUSAL in str(err.value)


@pytest.mark.parametrize("module", GUARDS)
def test_assert_writable_is_the_mirror(module):
    """`--apply` must fail before its first statement, not on its twelfth. The
    incident this nets is recorded in the migration: a read-only flag inherited
    from a pooled connection surfaced as ReadOnlySqlTransaction on every
    individual CREATE, halfway through a run."""
    assert module.assert_writable(FlagConn(transaction="off")) is not None
    with pytest.raises(RuntimeError) as err:
        module.assert_writable(FlagConn(transaction="on"))
    assert module.READONLY_REFUSAL in str(err.value)


@pytest.mark.parametrize("module", GUARDS)
def test_the_flag_is_a_connect_option_and_no_SET_statement_remains(module):
    """The spelling is the one `scripts/diagnose_wal_headroom.py` already uses.

    A `SET` is asserted absent as well as the option asserted present: leaving
    both would keep the arrangement whose behaviour depends on isolation level
    while looking repaired.

    ⚠️ THE SEARCH IS OVER EXECUTED CODE, NOT OVER THE TEXT OF THE FILE. All three
    modules now DOCUMENT the old statement at length, and a substring search over
    the source calls that documentation a defect - it did, on the first run of
    this test. The AST walk asks only about string literals that are arguments to
    a call, which is the only shape the statement was ever issued in.
    """
    import ast
    import inspect
    assert "-c default_transaction_read_only=on" in module.READONLY_OPTIONS

    tree = ast.parse(inspect.getsource(module))
    executed = [node.value for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                for arg in node.args
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                for node in [arg]]
    offending = [s for s in executed
                 if "default_transaction_read_only" in s and s.lstrip().upper()
                 .startswith("SET")]
    assert offending == [], f"a statement-level pin is still being issued: {offending}"


# ===========================================================================
# 2. Two connections: the counting pass never holds the writable one
#    (replaces the three `FakeEngine` tests in test_business_key_unique_migration)
# ===========================================================================

def test_check_mode_never_opens_the_writable_engine():
    """The pre-flight an operator points at production does not merely avoid
    writing - it has nothing to write WITH. `ExplodingEngine` fails the test if
    anything connects to it."""
    ro = CatalogueConn()
    out = mig.run(apply=False, engine=ExplodingEngine(),
                  readonly_engine=FakeEngine(ro))
    assert out["results"] == []
    assert not any("CREATE" in s or "DROP" in s for s in ro.sql)


def test_check_mode_issues_no_ddl_on_the_counting_connection():
    ro = CatalogueConn(redundant_rows=[("t", "ix_t_id", "t_pkey", 8, "d", "p")])
    out = mig.run(apply=False, readonly_engine=FakeEngine(ro))
    assert [r["index"] for r in out["redundant"]["found"]] == ["ix_t_id"]
    assert out["redundant"]["dropped"] == []
    assert not any("DROP INDEX" in s for s in ro.sql)


def test_apply_sends_the_ddl_to_the_other_connection():
    """🔴 The structural half. The connection that DISCOVERED the redundant index
    is not the connection that drops it, so the counting pass cannot issue the
    DDL it is deciding about even by mistake."""
    ro = CatalogueConn(redundant_rows=[("t", "ix_t_id", "t_pkey", 8, "d", "p")],
                       transaction="on")
    rw = CatalogueConn(transaction="off")
    mig.run(apply=False, drop_redundant=True, engine=FakeEngine(rw),
            readonly_engine=FakeEngine(ro))
    assert any("DROP INDEX CONCURRENTLY" in s for s in rw.sql), rw.sql
    assert not any("DROP INDEX" in s for s in ro.sql), ro.sql
    # and the discovery ran on the read-only side
    assert any("xd.indkey = xp.indkey" in s for s in ro.sql)


def test_run_refuses_a_counting_engine_that_is_not_actually_read_only():
    """Injecting the engine does not skip the proof. This is the case that would
    have caught the old pattern the moment anyone dropped AUTOCOMMIT."""
    with pytest.raises(RuntimeError) as err:
        mig.run(apply=False,
                readonly_engine=FakeEngine(CatalogueConn(transaction="off")))
    assert mig.READONLY_REFUSAL in str(err.value)


def test_apply_refuses_a_write_connection_that_cannot_write():
    with pytest.raises(RuntimeError) as err:
        mig.run(apply=True, engine=FakeEngine(CatalogueConn(transaction="on")),
                readonly_engine=FakeEngine(CatalogueConn(transaction="on")))
    assert mig.READONLY_REFUSAL in str(err.value)


def test_run_reports_both_sections_and_returns_them():
    """Carried over from `test_business_key_unique_migration.py`, which can no
    longer express it - `run()` needs a counting engine it can prove."""
    ro = CatalogueConn(redundant_rows=[("t", "ix_t_id", "t_pkey", 8, "d", "p")])
    out = mig.run(apply=False, readonly_engine=FakeEngine(ro))
    assert out["results"] == []
    assert [r["index"] for r in out["redundant"]["found"]] == ["ix_t_id"]
    assert out["redundant"]["dropped"] == []


# ===========================================================================
# 3. Against a real server - the part a stub cannot answer
# ===========================================================================

@pytest.fixture(scope="module")
def pg_url():
    url, reason = _resolve_pg_test_url()
    if url is None:
        pytest.skip(reason)
    try:
        import psycopg2  # noqa: F401
    except Exception as exc:                                  # pragma: no cover
        pytest.skip(f"psycopg2 is not importable: {exc}")
    with _declared_as_test_database(url):
        engine = sa.create_engine(url, poolclass=sa.pool.NullPool)
        try:
            with engine.begin() as conn:
                conn.execute(text("SELECT 1"))
        except sa.exc.OperationalError as exc:
            engine.dispose()
            pytest.skip(f"PostgreSQL is not reachable: "
                        f"{str(exc).strip().splitlines()[0]}")
        # A scratch schema with a REAL row in it. The INSERT/UPDATE trials below
        # must fail on the read-only rule and not on `UndefinedTable`, which is
        # what an unseeded target produces - a refusal for the wrong reason
        # proves nothing (it cost this lane one full round).
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
            conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
            conn.execute(text(f'CREATE TABLE "{SCHEMA}".probe '
                              f'(id int primary key, v text)'))
            conn.execute(text(f"INSERT INTO \"{SCHEMA}\".probe VALUES (1, 'a')"))
        try:
            yield url
        finally:
            with engine.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
            with engine.connect() as conn:
                left = conn.execute(text(
                    "SELECT count(*) FROM information_schema.schemata "
                    "WHERE schema_name = :s"), {"s": SCHEMA}).scalar()
            engine.dispose()
            assert left == 0, (f"the scratch schema {SCHEMA!r} survived teardown; "
                               f"drop it by hand before the next run")


_seq = itertools.count(1)


def _trial(conn):
    """Each write in its own transaction. Returns {label: 'ok' | error class}.

    🔴 EVERY ANSWER HERE MUST BE ABOUT THE READ-ONLY RULE AND NOTHING ELSE. Three
    ways this instrument has already lied, all fixed here:

      * an unseeded target answers `UndefinedTable` before PostgreSQL reaches the
        read-only check, so a working guard reads as broken;
      * a target left behind by an EARLIER test answers `DuplicateTable` /
        `UniqueViolation`, so a broken guard reads as working - which is why the
        CREATE name and the INSERT key are unique per call rather than per file;
      * rolling back only at the end leaves a non-autocommit connection aborted
        (`InFailedSqlTransaction` for statements 2 and 3) and, on the arm where
        the writes SUCCEED, `idle in transaction` holding a row lock the next arm
        then blocks on.
    """
    n = next(_seq)
    trials = [("CREATE", f'CREATE TABLE "{SCHEMA}".ddl_trial_{n} (x int)'),
              ("INSERT", f"INSERT INTO \"{SCHEMA}\".probe VALUES ({100 + n}, 'x')"),
              ("UPDATE", f"UPDATE \"{SCHEMA}\".probe SET v = 'b' WHERE id = 1")]
    out = {}
    for label, sql in trials:
        try:
            conn.execute(text(sql))
            out[label] = "ok"
        except Exception as exc:
            out[label] = type(getattr(exc, "orig", exc)).__name__
        try:
            conn.rollback()
        except Exception:
            pass
    return out


def _refused(res):
    return all(v == "ReadOnlySqlTransaction" for v in res.values())


def _assert_guard_holds(opener, url):
    """The four questions, put to one script's own read-only door.

    🔴 THIS IS THE ONE FUNCTION THE INJECTION ARM RE-USES, and that is deliberate:
    if the red arm re-spelled these assertions it would be proving something about
    its own copy rather than about the assertions that run in anger. Every failure
    mode below is an `AssertionError`, which is what `pytest.raises` downstream
    keys on.
    """
    engine, conn = opener(url)
    try:
        # 1. the server itself says the flag is on
        assert str(conn.execute(text("SHOW transaction_read_only")).scalar()) == "on", (
            "PostgreSQL does not report this connection read-only")
        # 2. a real write is REFUSED - three shapes, each in its own transaction
        assert _refused(_trial(conn)), "a write got through the guard"
        # 3. the refusal survives a rollback, which is where spelling C was
        #    discarded outright
        conn.rollback()
        assert str(conn.execute(text("SHOW transaction_read_only")).scalar()) == "on", (
            "the flag did not survive a rollback")
        assert _refused(_trial(conn)), "the guard did not survive a rollback"
        conn.close()

        # 4. a SECOND connection off the same engine. A session-level SET arms only
        #    the connection that ran it; a connect-time option arms every one.
        _, second = opener(url)
        assert _refused(_trial(second)), "the guard is per-connection, not per-engine"
        second.close()
    finally:
        engine.dispose()


@pytest.mark.parametrize("opener", DOORS)
def test_every_one_of_the_seven_doors_refuses_a_real_write(opener, pg_url):
    """🔴 THE TABLE. Each script's own read-only path, exercised as the script
    opens it, against a live server."""
    _assert_guard_holds(opener, pg_url)


@pytest.mark.parametrize("module", GUARDS)
def test_the_guard_does_not_depend_on_the_isolation_level(module, pg_url):
    """The connect-time arm holds on a connection nobody put into AUTOCOMMIT.

    This is the property the retired spelling did not have, stated as a separate
    test because `open_readonly_connection` sets AUTOCOMMIT for its own reasons
    and would otherwise hide it.
    """
    engine = module.open_readonly_engine(pg_url)
    try:
        plain = engine.connect()
        assert plain.execute(text("SHOW transaction_read_only")).scalar() == "on"
        assert _refused(_trial(plain)), (
            "the guard depends on the isolation level, which is the whole defect")
        plain.close()
    finally:
        engine.dispose()


def test_the_same_three_writes_succeed_without_the_guard(pg_url):
    """The control arm. Without it, the refusals above would be equally
    consistent with three broken statements."""
    engine = sa.create_engine(pg_url, poolclass=sa.pool.NullPool)
    try:
        conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        assert _trial(conn) == {"CREATE": "ok", "INSERT": "ok", "UPDATE": "ok"}
        assert conn.execute(text(
            f'SELECT v FROM "{SCHEMA}".probe WHERE id = 1')).scalar() == "b"
        conn.close()
    finally:
        engine.dispose()


def test_the_old_pattern_fails_the_property_this_file_pins(pg_url):
    """🔴 THE DEFECT, RUN. Without this the assertions above have never been seen
    to fail and could all be tautologies.

    Both halves are asserted because both are true and only one is comfortable:
    under AUTOCOMMIT the old pattern DID refuse writes (so nothing was damaged),
    and under the ordinary isolation level the identical two lines accept them
    while `default_transaction_read_only` still reads `on`.
    """
    engine = sa.create_engine(pg_url, poolclass=sa.pool.NullPool)
    try:
        armed = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        armed.execute(text("SET SESSION default_transaction_read_only = on"))
        assert armed.execute(text("SHOW transaction_read_only")).scalar() == "on"
        assert _refused(_trial(armed)), (
            "the old pattern under AUTOCOMMIT should still refuse - if this "
            "fails, the account in this file's docstring is wrong")
        armed.close()

        unarmed = engine.connect()          # the ordinary isolation level
        unarmed.execute(text("SET SESSION default_transaction_read_only = on"))
        assert unarmed.execute(
            text("SHOW default_transaction_read_only")).scalar() == "on"
        assert unarmed.execute(
            text("SHOW transaction_read_only")).scalar() == "off"
        assert _trial(unarmed) == {"CREATE": "ok", "INSERT": "ok", "UPDATE": "ok"}, (
            "the defect this lane repaired is not reproducible here, so the "
            "tests above are not discriminating anything")
        unarmed.close()
    finally:
        engine.dispose()


@pytest.mark.parametrize("module", GUARDS)
def test_the_repaired_engine_refuses_where_the_old_pattern_did_not(module, pg_url):
    """The two arms side by side, on one server, in one test: the arrangement
    that accepts a write above is refused by the engine these scripts now open."""
    engine = module.open_readonly_engine(pg_url)
    try:
        conn = engine.connect()             # same ordinary isolation level
        assert conn.execute(text("SHOW transaction_read_only")).scalar() == "on"
        assert _refused(_trial(conn))
        conn.close()
    finally:
        engine.dispose()


# ===========================================================================
# 4. ONE HOME - the property that stops this from happening again
# ===========================================================================

@pytest.mark.parametrize("module", CONSOLIDATED)
def test_no_script_carries_its_own_copy_of_the_guard(module):
    """🔴 THE CONSOLIDATION ITSELF, ASSERTED STRUCTURALLY.

    Not a text search for a spelling - a text search cannot tell a re-export from
    a re-implementation, and the last thing this property needs is a check that
    passes because somebody named their copy the same. Every guard name a script
    binds must BE the home's object (`is`), so a copy fails on identity no matter
    how it is spelled or how faithfully it was transcribed.

    TWO LEGITIMATE SHAPES, AND BOTH HAVE TO BE ACCEPTED. A script may import the
    names (`from db_safety import assert_writable`) or reach them through the
    module (`db_safety.close_readonly_connection(...)`). `snapshot_db` does the
    latter and binds none of the names, which the first draft of this test called
    a failure - a predicate that had quietly decided there was only one way to
    depend on a module.
    """
    imported = [n for n in SHARED_NAMES if hasattr(module, n)]
    for name in imported:
        assert getattr(module, name) is getattr(db_safety, name), (
            f"{module.__name__}.{name} is not `db_safety.{name}` - this is a copy, "
            f"and a copy carries whatever the original got wrong")

    via_module = getattr(module, "db_safety", None)
    assert imported or via_module is db_safety, (
        f"{module.__name__} neither imports the shared guard names nor holds the "
        f"home module - it is getting the property from somewhere else")
    if via_module is not None:
        assert via_module is db_safety


#: A statement that PINS read-only, as opposed to a string that merely talks about
#: it. Structural on purpose: the first draft asked "does this string contain
#: read_only/readonly/READ ONLY" and produced two false members out of two files -
#: an error message ("no read-only engine can be derived from it") and a probe
#: table called `_devenv_readonly_probe`. A detector that cries wolf on its own
#: repository gets read as noise the day it is right.
_READONLY_PIN = re.compile(
    r"^\s*SET\s+(SESSION\s+)?(CHARACTERISTICS\s+AS\s+TRANSACTION\s+READ\s+ONLY"
    r"|(SESSION\s+)?\w*default_transaction_read_only|TRANSACTION\s+READ\s+ONLY)",
    re.IGNORECASE)


def _executed_strings(src):
    """String literals handed to a call - the only shape a pin was ever issued in."""
    tree = ast.parse(src)
    return [arg.value for node in ast.walk(tree) if isinstance(node, ast.Call)
            for arg in node.args
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]


def test_the_pin_detector_would_catch_a_pin():
    """🔴 FAULT-INJECT THE DETECTOR BEFORE TRUSTING ITS ZEROS. All three retired
    spellings must be caught, and the two measured false positives must not be."""
    caught = 'conn.execute(text("SET SESSION default_transaction_read_only = on"))\n' \
             'conn.execute(text("SET default_transaction_read_only = on"))\n' \
             'conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))\n'
    found = [s for s in _executed_strings(caught) if _READONLY_PIN.match(s)]
    assert len(found) == 3, f"the detector misses a retired spelling: {found}"

    innocent = 'raise ValueError("no read-only engine can be derived from it")\n' \
               'conn.execute(text("CREATE TEMP TABLE _devenv_readonly_probe (x int)"))\n' \
               'conn.execute(text("SHOW transaction_read_only"))\n'
    assert [s for s in _executed_strings(innocent) if _READONLY_PIN.match(s)] == []


@pytest.mark.parametrize("module", CONSOLIDATED)
def test_no_script_issues_a_read_only_pin_of_its_own(module):
    """No script executes any of the three spellings itself.

    ⚠️ THE SEARCH IS OVER EXECUTED CODE, NOT OVER THE TEXT OF THE FILE. Six of
    these modules now DOCUMENT the retired statements at length - on purpose, so
    the next reader learns why - and a substring search over the source calls that
    documentation a defect. The AST walk asks only about string literals that are
    arguments to a call, which is the only shape any of them was ever issued in.
    """
    offending = [s for s in _executed_strings(inspect.getsource(module))
                 if _READONLY_PIN.match(s)]
    assert offending == [], (
        f"{module.__name__} issues its own read-only statement: {offending}. "
        f"The guard has one home and it is `db_safety`.")


def test_the_home_exposes_both_working_spellings_rather_than_picking_one():
    """A and B differ in something real, so neither could be dropped silently.

    CONNECT_TIME is stronger but needs an engine we BUILD; PER_TRANSACTION works on
    a borrowed one. `audit_schema_canon` takes an `engine` parameter from its
    caller, so collapsing the home onto CONNECT_TIME would have removed a
    capability rather than a duplicate.
    """
    assert db_safety.CONNECT_TIME != db_safety.PER_TRANSACTION
    sig = inspect.signature(db_safety.open_readonly_connection)
    assert sig.parameters["mode"].default == db_safety.CONNECT_TIME
    with pytest.raises(ValueError):
        db_safety.open_readonly_connection(object(), mode="whatever-looks-safe")


def test_choosing_the_wrong_mode_is_a_refusal_and_not_a_hole(pg_url):
    """The mode names a MECHANISM, so a caller can pick the wrong one for their
    engine. That must surface as a refusal, because the verdict comes from the
    server rather than from which branch was taken."""
    engine = sa.create_engine(pg_url, poolclass=sa.pool.NullPool)
    try:
        # CONNECT_TIME on an engine that was never armed at connect time.
        with pytest.raises(RuntimeError) as err:
            db_safety.open_readonly_connection(engine,
                                               mode=db_safety.CONNECT_TIME)
        assert db_safety.READONLY_REFUSAL in str(err.value)
    finally:
        engine.dispose()


# ===========================================================================
# 5. 🔴 THE INJECTION - put the retired spelling back into the HOME
# ===========================================================================

def _spelling_c_options(statement_timeout_ms=None):
    """`readonly_options` with the read-only pin removed - the pre-repair state."""
    if not statement_timeout_ms:
        return "-c client_encoding=utf8"
    return f"-c client_encoding=utf8 -c statement_timeout={int(statement_timeout_ms)}"


def _spelling_c_connection(engine, *, mode=None):
    """Spelling C, restored exactly: connect at the ORDINARY isolation level,
    issue the SET, return without reading anything back."""
    conn = engine.connect()
    conn.execute(text("SET SESSION default_transaction_read_only = on"))
    return conn


@pytest.mark.parametrize("opener", DOORS)
def test_injecting_spelling_c_into_the_home_turns_every_door_red(
        opener, pg_url, monkeypatch):
    """🔴 A GUARD WHOSE REMOVAL CHANGES NOTHING IS NOT A GUARD.

    Both halves of the repair are removed from `db_safety` - the connect-time
    option AND the read-back - which together are what spelling C did not have.
    Then `_assert_guard_holds` runs: the SAME function the green tests call, so
    what is being shown red is the assertion that runs in anger and not a
    restatement of it.

    ⚠️ REMOVING ONE HALF IS NOT ENOUGH AND THAT IS WHY BOTH GO. With only the
    read-back removed the connect option still arms the session and every door
    stays green - an insufficient mutation and a robust test look identical from
    outside. The mutation is verified sufficient by this test failing.

    ⚠️ `dev_env/snapshot_db` goes red with `SystemExit`, not `AssertionError`, and
    that is not a wrinkle to paper over - it is that script's own live write probe
    firing before the shared assertions get a turn. It is the one door in the
    table that proves the guard by exercising it rather than by reading a flag, so
    under injection it aborts first. Both are red; the distinction is recorded so
    nobody later "fixes" it into uniformity and deletes the extra proof.
    """
    monkeypatch.setattr(db_safety, "readonly_options", _spelling_c_options)
    monkeypatch.setattr(db_safety, "open_readonly_connection",
                        _spelling_c_connection)
    # The scripts import the names directly, so the module-level bindings have to
    # be redirected too - which is itself a check that they ARE the home's object.
    for module in (mig, dropidx, rebuild, dedupe, checkbk):
        if hasattr(module, "open_readonly_connection"):
            monkeypatch.setattr(module, "open_readonly_connection",
                                _spelling_c_connection)

    with pytest.raises((AssertionError, SystemExit)):
        _assert_guard_holds(opener, pg_url)
