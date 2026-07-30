# -*- coding: utf-8 -*-
"""Board item #16a: a test run must not be able to issue DDL against production.

WHY THIS FILE EXISTS AT ALL
    `main.py` builds the physical schema at boot. That statement used to run at
    module import, so pytest merely COLLECTING the suite issued DDL against
    whatever DATABASE_URL resolved to - unset, the production PostgreSQL. It
    happened: empty tables appeared in production from a test run. The DDL has
    since moved into `bootstrap_database_schema()`, and conftest.py pins
    DATABASE_URL before importing the app, but item #16a stayed open because the
    remaining argument was "the test engines are all sqlite as far as we
    checked". Its sibling #16b is trusted instead because its assertion breaks
    when the isolation is dropped. This file is that, for #16a.

THE THREE NETS, AND WHAT EACH TEST HERE WOULD CATCH
    net 1  `db_safety.install_test_database_guard(engine)` on the shared engine.
           Refuses before the socket opens. Deleted -> section D and probe cell
           F3 go red.
    net 2  `db_safety.install_global_test_database_guard()` on the Engine CLASS,
           so an engine a test builds for itself is covered too. Deleted ->
           section E goes red.
    net 3  `db_safety.require_test_database(...)` inside
           `main.bootstrap_database_schema` - a pure decision, no connection
           opened at all. Deleted -> section C and probe cell F2 go red.

    Section A scores the decision itself (an allowlist, so a URL that merely
    looks harmless is still refused). Section B is the sensitivity control: if
    the guard were not armed in this very process, every other test here would
    pass while proving nothing.

    Section F runs a real process on both sides of the line, because the whole
    design rests on the guard being ARMED under pytest and ABSENT in production:
    the same command, differing only in one inherited environment variable, must
    produce a refusal in one cell and a real, loud connection failure in the
    other.

NOTHING HERE CONTACTS A REAL DATABASE
    Every non-sqlite URL below points at 127.0.0.1 PORT 1, which nothing
    listens on, and the cells where the guard is deliberately absent name a
    database that does not exist (`assy_boot_probe`). A negative test must not
    be able to cause the incident it describes.
"""
import json
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import db_safety  # noqa: E402
import main  # noqa: E402
from database import database as db_mod  # noqa: E402

#: Unreachable on purpose (port 1), and named production on purpose - this is
#: the URL the decision must refuse, not one it may quietly connect to.
UNREACHABLE_PRODUCTION = "postgresql://postgres:admin@127.0.0.1:1/assy_manager"
#: Same host and port, a database name that exists nowhere. Used by the probe
#: cells that run WITHOUT the guard, so that even a total failure of every net
#: could not reach the user's data.
UNREACHABLE_NEUTRAL = "postgresql://postgres:admin@127.0.0.1:1/assy_boot_probe"


# --------------------------------------------------------------------------- A
class TestTheDecisionIsAnAllowlist:
    """`check_test_database` scored with no engine and no connection anywhere.

    Every case passes `opt_in` explicitly so the verdict never depends on the
    shell this suite runs in (the one exception is the last test, which is
    about the environment lookup itself).
    """

    def test_sqlite_memory_is_allowed(self):
        assert db_safety.check_test_database("sqlite:///:memory:", opt_in=None) == []

    def test_sqlite_file_is_allowed(self):
        assert db_safety.check_test_database("sqlite:///C:/tmp/probe.db",
                                             opt_in=None) == []

    def test_the_production_default_is_refused(self):
        v = db_safety.check_test_database(db_mod.DEFAULT_PG_URL, opt_in=None)
        assert v, "the production database URL was accepted for a test process"
        assert "assy_manager" in " ".join(v), v

    def test_an_undeclared_postgres_url_is_refused_even_when_it_looks_harmless(self):
        """The test that separates an allowlist from a blocklist.

        `assy_qa` is the ISOLATED database - a blocklist of production names
        would wave it through, and would wave through every other name too, so
        the day a second production database exists the guard is already gone.
        Only an explicit declaration may open the door.
        """
        v = db_safety.check_test_database(
            "postgresql://postgres:admin@localhost:5432/assy_qa", opt_in=None)
        assert v, "an undeclared postgres target was accepted"
        assert db_safety.TEST_DATABASE_URL_ENV in " ".join(v), v

    def test_a_declared_isolated_database_is_allowed(self):
        """A rail that refuses everything is as useless as one that refuses
        nothing: running the suite against an isolated postgres must stay
        possible, and it is the documented escape hatch."""
        url = "postgresql://postgres:admin@localhost:5432/assy_qa"
        assert db_safety.check_test_database(url, opt_in=url,
                                             production_url=db_mod.DEFAULT_PG_URL) == []

    def test_a_masked_password_still_matches_its_own_declaration(self):
        """`str(engine.url)` masks the password as ***, the declaration has the
        real one. If the comparison were textual, the legitimate case above
        would break the moment it was asked about a live engine."""
        declared = "postgresql://postgres:admin@localhost:5432/assy_qa"
        masked = "postgresql://postgres:***@localhost:5432/assy_qa"
        assert db_safety.check_test_database(masked, opt_in=declared) == []

    def test_a_declaration_that_vouches_for_a_different_target_is_refused(self):
        v = db_safety.check_test_database(
            "postgresql://postgres:admin@localhost:5432/assy_qa",
            opt_in="postgresql://postgres:admin@otherhost:5432/assy_qa")
        assert v, "a declaration naming a different host let the target through"

    def test_declaring_production_as_the_test_database_is_refused(self):
        """Setting the opt-in to production satisfies 'it was declared' and is
        still catastrophic, so the production name is checked separately."""
        v = db_safety.check_test_database(db_mod.DEFAULT_PG_URL,
                                          opt_in=db_mod.DEFAULT_PG_URL,
                                          production_url=db_mod.DEFAULT_PG_URL)
        assert v, "production was accepted because someone declared it"
        assert "PRODUCTION" in " ".join(v), v

    @pytest.mark.parametrize("url", ["", None, "not a url", "x/assy_qa", 17])
    def test_a_target_that_cannot_be_proven_isolated_is_refused(self, url):
        """Fail closed. 'Unprovable' is a refusal, never a warning."""
        assert db_safety.check_test_database(url, opt_in=None), \
            f"an unprovable target was accepted: {url!r}"

    def test_the_declaration_is_read_from_the_environment_by_default(self, monkeypatch):
        url = "postgresql://postgres:admin@localhost:5432/assy_qa"
        monkeypatch.delenv(db_safety.TEST_DATABASE_URL_ENV, raising=False)
        assert db_safety.check_test_database(url)
        monkeypatch.setenv(db_safety.TEST_DATABASE_URL_ENV, url)
        assert db_safety.check_test_database(url) == []


# --------------------------------------------------------------------------- B
class TestTheGuardIsArmedInThisProcess:
    """The sensitivity control.

    Every guard below is a no-op when `under_pytest()` is False. Without this
    test the whole file could pass against a completely disarmed guard and
    report nothing but its own silence.
    """

    def test_this_process_is_recognised_as_a_test_process(self):
        assert db_safety.under_pytest() is True, (
            "the guards in db_safety.py are DISARMED in the process running "
            "this suite - every other assertion in this file is vacuous")

    def test_a_process_with_no_pytest_signal_is_not_guarded(self, monkeypatch):
        """The other half, in-process: production must not be guarded.

        Guards against 'fixing' #16a by arming everywhere, which would take the
        production web server down the first time it booted.
        """
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("PYTEST_VERSION", raising=False)
        monkeypatch.delitem(sys.modules, "pytest", raising=False)
        assert db_safety.under_pytest() is False
        # ...and with the guard disarmed, the decision does not fire at all.
        db_safety.require_test_database(db_mod.DEFAULT_PG_URL, context="probe")

    @pytest.mark.parametrize("var", ["PYTEST_CURRENT_TEST", "PYTEST_VERSION"])
    def test_each_environment_signal_arms_the_guard_on_its_own(self, monkeypatch, var):
        """Both are in the list because both are INHERITED by subprocesses.

        A probe a test shells out to has no `pytest` in its `sys.modules`, so
        without these two the guard would evaporate exactly where the suite
        reaches outside itself.
        """
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("PYTEST_VERSION", raising=False)
        monkeypatch.delitem(sys.modules, "pytest", raising=False)
        monkeypatch.setenv(var, "1")
        assert db_safety.under_pytest() is True


# --------------------------------------------------------------------------- C
class TestBootstrapRefusesWithoutContactingAnything:
    """net 3 - the decision at the DDL entry point itself."""

    def test_bootstrap_refuses_a_production_bind(self):
        """Red if the `require_test_database` call is removed from
        `bootstrap_database_schema`.

        With the guard gone, `create_all` reaches for 127.0.0.1:1 and raises
        OperationalError, which is not a RuntimeError - so the failure is loud
        either way, and the message assertion pins WHICH failure this is.
        """
        eng = create_engine(UNREACHABLE_PRODUCTION)
        attempts = []

        def _count(dialect, conn_rec, cargs, cparams):
            attempts.append(1)
            return None  # None = proceed; this listener only observes

        event.listen(eng, "do_connect", _count)

        with pytest.raises(RuntimeError) as exc:
            main.bootstrap_database_schema(bind=eng)

        assert db_safety.REFUSAL_MARKER in str(exc.value), str(exc.value)
        assert "create_all" in str(exc.value), str(exc.value)
        # The claim is not merely "it failed" - it is that the database was
        # never contacted. A refusal taken after a connection attempt would
        # still leave a login record on a reachable production host.
        assert attempts == [], (
            "bootstrap tried to open a connection before refusing")

    def test_bootstrap_still_builds_the_schema_on_an_isolated_target(self, tmp_path):
        """Guards against 'fix' by refusing everything.

        The bootstrap must still do its job, or a fresh install can never come
        up - the reason the path was not simply deleted when #16a was filed.
        """
        db_file = tmp_path / "iso.db"
        eng = create_engine("sqlite:///" + str(db_file).replace("\\", "/"))
        main.bootstrap_database_schema(bind=eng)
        with eng.connect() as conn:
            names = {r[0] for r in conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table'"))}
        assert names, "bootstrap created no tables on a legitimate target"
        assert "database_outbox" in names, sorted(names)


# --------------------------------------------------------------------------- D
class TestTheSharedEngineRefusesBeforeTheSocket:
    """net 1 - `do_connect` on the engine that carries production's credentials."""

    def test_an_armed_engine_refuses_without_opening_a_socket(self):
        """Red if `install_test_database_guard` stops registering the hook.

        The exception TYPE is the proof of "before the socket": 127.0.0.1:1
        refuses instantly, so an unguarded engine answers with OperationalError.
        Only a refusal taken before the DBAPI is invoked can be a RuntimeError.
        """
        eng = create_engine(UNREACHABLE_PRODUCTION)
        db_safety.install_test_database_guard(
            eng, production_url=db_mod.DEFAULT_PG_URL)

        with pytest.raises(RuntimeError) as exc:
            eng.connect()
        assert db_safety.REFUSAL_MARKER in str(exc.value), str(exc.value)

    def test_an_armed_engine_still_connects_to_an_isolated_target(self, tmp_path):
        """The rail must let the legitimate case through."""
        eng = create_engine(
            "sqlite:///" + str(tmp_path / "ok.db").replace("\\", "/"))
        db_safety.install_test_database_guard(
            eng, production_url=db_mod.DEFAULT_PG_URL)
        with eng.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1


# --------------------------------------------------------------------------- E
class TestEveryEngineInTheProcessIsCovered:
    """net 2 - the class-level hook, installed by importing database.database.

    Scored by forcing the DECISION to refuse and checking that the WIRING
    carries it, rather than by pointing an engine at a real database: the
    decision itself is scored in section A, and a test that needed a reachable
    production host to prove a guard would be the incident.
    """

    def test_an_engine_nobody_armed_is_still_refused(self, monkeypatch, tmp_path):
        """Red if `install_global_test_database_guard` is removed, or if
        `database.database` stops calling it.

        The engine here is built inside the test and never handed to
        `install_test_database_guard`, so the only thing that can refuse it is
        the class-level hook.
        """
        monkeypatch.setattr(db_safety, "check_test_database",
                            lambda *a, **k: ["injected: not a test database"])
        eng = create_engine(
            "sqlite:///" + str(tmp_path / "unarmed.db").replace("\\", "/"))
        with pytest.raises(RuntimeError) as exc:
            eng.connect()
        assert db_safety.REFUSAL_MARKER in str(exc.value), str(exc.value)

    def test_the_same_engine_connects_once_the_decision_allows_it(self, tmp_path):
        """The sensitivity control for the test above: the only difference
        between the two is the verdict, so a refusal that fired unconditionally
        would be caught here."""
        eng = create_engine(
            "sqlite:///" + str(tmp_path / "unarmed.db").replace("\\", "/"))
        with eng.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1


# --------------------------------------------------------------------------- F
# The 2x2. One real process per cell, differing ONLY in whether pytest's
# inherited environment markers are present, so the guard's arming - and its
# absence in production - is measured rather than asserted.
_PROBE = r"""
import os, sys, json
sys.path.insert(0, os.environ["PROBE_SERVER_DIR"])
out = {}
try:
    import db_safety
    out["under_pytest"] = db_safety.under_pytest()
    if os.environ["PROBE_ACTION"] == "bootstrap":
        import main
        out["imported_main"] = True
        main.bootstrap_database_schema()
    else:
        # Deliberately NOT importing main: this cell is about the shared engine,
        # and importing the whole app to reach it costs ~15s per cell.
        from database.database import engine
        engine.connect()
    out["outcome"] = "returned"
except BaseException as e:
    out["outcome"] = "raised"
    out["exc_type"] = type(e).__name__
    out["exc_str"] = str(e)[:600]
print("@@" + json.dumps(out))
"""


def _probe(tmp_path, *, action, armed, url=UNREACHABLE_NEUTRAL, timeout=180):
    env = os.environ.copy()
    env["PROBE_SERVER_DIR"] = SERVER_DIR
    env["PROBE_ACTION"] = action
    env["PYTHONIOENCODING"] = "utf-8"
    # Keep the child out of the user's live tree entirely: logs, config and
    # workspace all resolve under a tmp root (server/paths.py).
    env["ASSY_DATA_ROOT"] = str(tmp_path / "probe_root")
    env["DATABASE_URL"] = url
    env.pop("TESTING", None)
    if armed:
        env["PYTEST_VERSION"] = "probe"
        env["PYTEST_CURRENT_TEST"] = "probe"
    else:
        env.pop("PYTEST_VERSION", None)
        env.pop("PYTEST_CURRENT_TEST", None)

    proc = subprocess.run([sys.executable, "-c", _PROBE], cwd=SERVER_DIR, env=env,
                          capture_output=True, text=True, errors="replace",
                          timeout=timeout)
    line = [l for l in proc.stdout.splitlines() if l.startswith("@@")]
    assert line, f"probe produced no result:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(line[-1][2:])


class TestArmedUnderPytestAndAbsentInProduction:

    def test_a_test_process_is_refused_the_boot_ddl(self, tmp_path):
        """net 3 across a real process boundary, armed only by inherited env.

        The context string is asserted, not merely the marker. Measured, not
        assumed: with net 3 deleted this cell still refused - net 1 caught the
        same call one layer down, because the bootstrap binds to the shared
        engine. `RuntimeError` alone therefore proves only that SOME net held.
        Pinning the context to the DDL step is what makes this cell sensitive to
        the guard it is named after.
        """
        got = _probe(tmp_path, action="bootstrap", armed=True)
        assert got["under_pytest"] is True
        assert got.get("imported_main") is True, (
            "the refusal fired during import, not at the DDL step - this cell "
            f"is no longer measuring the bootstrap guard: {got}")
        assert got["outcome"] == "raised", got
        assert got["exc_type"] == "RuntimeError", got
        assert db_safety.REFUSAL_MARKER in got["exc_str"], got
        assert "create_all" in got["exc_str"], (
            "the boot DDL was refused by a lower net, not by the bootstrap "
            f"guard itself: {got}")

    def test_a_test_process_is_refused_a_connection_on_the_shared_engine(self, tmp_path):
        """net 1 on the SHARED engine - the one an ambient DATABASE_URL steers.

        RuntimeError rather than OperationalError is the evidence that the
        refusal happened before the socket: the same call in the unguarded cell
        below reaches the network and comes back with a connection error.
        """
        got = _probe(tmp_path, action="connect", armed=True)
        assert got["outcome"] == "raised", got
        assert got["exc_type"] == "RuntimeError", got
        assert db_safety.REFUSAL_MARKER in got["exc_str"], got

    def test_production_boot_still_fails_loudly_on_an_unreachable_database(self, tmp_path):
        """The constraint that keeps this fix from being a regression.

        `create_all` is deliberately unguarded: a web server whose database is
        unreachable must abort at boot rather than serve a schema-less app. So
        the unarmed cell must NOT come back with a refusal, and must NOT come
        back quiet either - it must raise the real connection error.
        """
        got = _probe(tmp_path, action="bootstrap", armed=False)
        assert got["under_pytest"] is False, got
        assert got["outcome"] == "raised", (
            "boot against an unreachable database returned quietly - the "
            f"create_all failure is being swallowed: {got}")
        assert got["exc_type"] == "OperationalError", got
        assert db_safety.REFUSAL_MARKER not in got.get("exc_str", ""), (
            "a production boot was refused by the TEST guard: " + str(got))

    def test_production_connections_are_not_guarded(self, tmp_path):
        """The fourth cell: outside pytest the shared engine connects for real
        (and here fails for real, on a port nothing listens on)."""
        got = _probe(tmp_path, action="connect", armed=False)
        assert got["under_pytest"] is False, got
        assert got["outcome"] == "raised", got
        assert got["exc_type"] == "OperationalError", got
        assert db_safety.REFUSAL_MARKER not in got.get("exc_str", ""), got
