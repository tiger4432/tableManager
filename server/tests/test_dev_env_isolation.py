# -*- coding: utf-8 -*-
"""Regression guards for the isolated development environment.

The isolation rests on two small things that nothing else asserts, and a guard
nothing exercises is indistinguishable from no guard:

  1. conftest.py pins DATABASE_URL before `from main import app`. Without it,
     the boot-time `Base.metadata.create_all(bind=engine)` issues DDL to
     whatever DATABASE_URL resolves to - unset, that is the live production
     database (board issue #16a). That statement has since moved out of module
     scope into `main.bootstrap_database_schema()`, and the pin is no longer the
     only thing standing between the suite and production: see
     `test_ddl_never_reaches_production.py`, which puts the refusal in the
     production modules so deleting this pin fails the suite loudly instead of
     silently removing the protection. The tests below still guard the pin
     itself, because it is what keeps every later import honest.
  2. server/paths.py is the single override point for config/ and
     ingestion_workspace/. If a module goes back to building those paths from its
     own __file__, an isolated server silently reads and writes production again.
  3. mappers/ is deliberately NOT relocated, so an isolated server must refuse to
     write there rather than reach into the user's live files.

Each test is written so that removing the thing it guards turns it red.
"""
import os
import io
import sys
import json
import hashlib
import subprocess

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import admin_auth

#: POST /admin/scripts/code is one of the two code-execution routes, so it now
#: refuses with 503 unless an admin token is configured (see admin_auth.py). The
#: tests below are about the *isolation* guard, not the gate, so they configure
#: the gate and present the header - which keeps them exercising the handler
#: exactly as before instead of stopping at the door.
_ISOLATION_TEST_TOKEN = "isolation-suite-token"


@pytest.fixture
def admin_client(client, monkeypatch):
    """`client` with the admin gate configured and the header attached."""
    monkeypatch.setenv(admin_auth.ADMIN_TOKEN_ENV, _ISOLATION_TEST_TOKEN)
    client.headers[admin_auth.ADMIN_TOKEN_HEADER] = _ISOLATION_TEST_TOKEN
    try:
        yield client
    finally:
        client.headers.pop(admin_auth.ADMIN_TOKEN_HEADER, None)


# --------------------------------------------------------------------------- 1
class TestSuiteNeverTouchesProduction:
    """Guards the conftest.py DATABASE_URL pin."""

    def test_engine_url_is_the_pinned_value_not_the_ambient_one(self):
        """Red if the pin is removed, or weakened to setdefault with an ambient var.

        The pin's contract is: the engine URL equals
        ASSY_TEST_DATABASE_URL, defaulting to in-memory sqlite - regardless of
        any DATABASE_URL already in the shell. Comparing against that expression
        (rather than merely 'is not production') is what catches a `setdefault`
        downgrade, because setdefault would let an ambient value win.
        """
        from database import database as db_mod

        expected = os.environ.get("ASSY_TEST_DATABASE_URL", "sqlite:///:memory:")
        assert db_mod.SQLALCHEMY_DATABASE_URL == expected, (
            "conftest.py must pin DATABASE_URL before `from main import app`; "
            f"engine resolved to {db_mod.SQLALCHEMY_DATABASE_URL!r}"
        )
        # The live engine, not just the module constant - that is what create_all
        # at import time actually binds to.
        assert str(db_mod.engine.url) == expected

    def test_suite_database_is_never_the_production_database(self):
        """Red if anyone points the suite at production, pin or no pin.

        Separate from the test above on purpose: setting ASSY_TEST_DATABASE_URL
        to the production URL would satisfy the pin and still be catastrophic.
        """
        from database import database as db_mod

        url = db_mod.SQLALCHEMY_DATABASE_URL
        assert url != db_mod.DEFAULT_PG_URL, (
            "the suite is pointed at the production database "
            f"({db_mod.DEFAULT_PG_URL})"
        )
        if db_mod.engine.url.get_backend_name() == "postgresql":
            assert db_mod.engine.url.database != "assy_manager", (
                "the suite is pointed at the production database 'assy_manager'"
            )

    def test_create_all_at_import_did_not_reach_postgres(self):
        """main is already imported by conftest; assert where that landed."""
        assert "main" in sys.modules, "conftest should have imported main"
        from database import database as db_mod
        assert db_mod.is_sqlite or db_mod.engine.url.database != "assy_manager"


# --------------------------------------------------------------------------- 2
# Run in a subprocess: ASSY_DATA_ROOT is read at import time, and reloading
# server/paths.py in-process would leave every already-imported consumer holding
# stale constants (main.py reads paths.WORKSPACE_DIR at request time), poisoning
# later tests in the same session.
_PROBE = r"""
import os, sys, json
sys.path.insert(0, os.environ["PROBE_SERVER_DIR"])
import paths
from database import crud
import map_overlay, bonding_plan, transfer_plan, enrichment_config, ontology_config
import chain_ingestion_worker
from utils import auto_update_control as auc
print("@@" + json.dumps({
    "DATA_ROOT": paths.DATA_ROOT,
    "CONFIG_DIR": paths.CONFIG_DIR,
    "WORKSPACE_DIR": paths.WORKSPACE_DIR,
    "IS_ISOLATED": paths.IS_ISOLATED,
    "crud.CONFIG_PATH": crud.CONFIG_PATH,
    "map_overlay.CONFIG_PATH": map_overlay.CONFIG_PATH,
    "bonding_plan.CONFIG_PATH": bonding_plan.CONFIG_PATH,
    "transfer_plan.CONFIG_PATH": transfer_plan.CONFIG_PATH,
    "enrichment_config.CONFIG_DIR": enrichment_config.CONFIG_DIR,
    "ontology_config.CONFIG_DIR": ontology_config.CONFIG_DIR,
    "chain.RULES_PATH": chain_ingestion_worker.RULES_PATH,
    "auc.control_path": auc.get_control_path(),
    "auc.script_file": auc.resolve_script_file("wsprobe/scriptprobe.py"),
    "paths.log_path": paths.log_path("server.log"),
}))
"""


def _probe_paths(data_root):
    env = os.environ.copy()
    env["PROBE_SERVER_DIR"] = SERVER_DIR
    # Never let the probe's engine construction point at production.
    env["DATABASE_URL"] = "sqlite:///:memory:"
    env["PYTHONIOENCODING"] = "utf-8"
    if data_root is None:
        env.pop("ASSY_DATA_ROOT", None)
    else:
        env["ASSY_DATA_ROOT"] = str(data_root)

    proc = subprocess.run([sys.executable, "-c", _PROBE], cwd=SERVER_DIR, env=env,
                          capture_output=True, text=True, errors="replace")
    assert proc.returncode == 0, f"probe failed:\n{proc.stdout}\n{proc.stderr}"
    line = [l for l in proc.stdout.splitlines() if l.startswith("@@")]
    assert line, f"probe produced no result:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(line[-1][2:])


class TestDataRootOverride:
    """Guards server/paths.py being the single override point."""

    def test_every_config_consumer_follows_assy_data_root(self, tmp_path):
        """Red the moment a module goes back to hardcoding its own path.

        A module that rebuilds `dirname(__file__)/config/...` keeps pointing at
        server/config while everything else moves, so its entry here stays
        outside the overridden root.
        """
        root = tmp_path / "isolated_root"
        got = _probe_paths(root)

        assert got["IS_ISOLATED"] is True
        assert os.path.normcase(got["DATA_ROOT"]) == os.path.normcase(str(root))
        assert os.path.normcase(got["CONFIG_DIR"]) == os.path.normcase(str(root / "config"))
        assert os.path.normcase(got["WORKSPACE_DIR"]) == os.path.normcase(
            str(root / "ingestion_workspace"))

        root_nc = os.path.normcase(str(root)) + os.sep
        stragglers = {
            k: v for k, v in got.items()
            if k not in ("DATA_ROOT", "CONFIG_DIR", "WORKSPACE_DIR", "IS_ISOLATED")
            and not os.path.normcase(str(v)).startswith(root_nc)
        }
        assert not stragglers, (
            "these paths ignored ASSY_DATA_ROOT and still point at the live tree "
            f"(they must resolve through server/paths.py): {stragglers}"
        )

    def test_unset_data_root_is_a_no_op(self):
        """Production behaviour must be untouched when the override is absent."""
        got = _probe_paths(None)
        assert got["IS_ISOLATED"] is False
        assert os.path.normcase(got["DATA_ROOT"]) == os.path.normcase(SERVER_DIR)
        assert os.path.normcase(got["CONFIG_DIR"]) == os.path.normcase(
            os.path.join(SERVER_DIR, "config"))
        assert os.path.normcase(got["crud.CONFIG_PATH"]) == os.path.normcase(
            os.path.join(SERVER_DIR, "config", "table_config.json"))


# --------------------------------------------------------------------------- 3
MAPPERS_ROOT = os.path.join(SERVER_DIR, "mappers")


def _snapshot_mappers():
    """content + mtime for every file under server/mappers/ (excluding caches)."""
    out = {}
    if not os.path.isdir(MAPPERS_ROOT):
        return out
    for dirpath, dirnames, filenames in os.walk(MAPPERS_ROOT):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            full = os.path.join(dirpath, name)
            with open(full, "rb") as f:
                out[full] = (f.read(), os.stat(full).st_mtime)
    return out


@pytest.fixture
def live_mappers_must_be_untouched():
    """Snapshot server/mappers/**, then repair and assert nothing changed.

    server/mappers/ is gitignored user code, so a test that writes there destroys
    something unrecoverable. When the guard under test was first removed to prove
    the test was real, that injected run clobbered server/mappers/__init__.py -
    a regression test must not be able to damage the very thing it protects.

    Repair happens first, then the assertion, so a broken guard leaves the tree
    pristine AND still reports loudly.
    """
    before = _snapshot_mappers()
    yield
    after = _snapshot_mappers()

    damage = {}
    for full, (data, mtime) in before.items():
        if full not in after:
            with open(full, "wb") as f:
                f.write(data)
            os.utime(full, (mtime, mtime))
            damage[full] = "DELETED (restored)"
        elif after[full][0] != data:
            with open(full, "wb") as f:
                f.write(data)
            os.utime(full, (mtime, mtime))
            damage[full] = "CONTENT CHANGED (restored)"
        elif after[full][1] != mtime:
            os.utime(full, (mtime, mtime))
            damage[full] = "TOUCHED, same bytes (mtime restored)"
    for full in after:
        if full not in before:
            os.remove(full)
            damage[full] = "CREATED (removed)"

    assert not damage, (
        "the isolated server reached into the live server/mappers/ tree: "
        f"{damage} (repaired, but the guard is broken)"
    )


class TestIsolatedServerCannotWriteLiveMappers:
    """mappers/ is not relocated, so an isolated server must refuse to write it."""

    # A name that cannot collide with a real user mapper.
    PROBE = "mappers/_devenv_isolation_probe_must_not_exist.py"

    def test_resolver_refuses_write_outside_the_relocated_root(self, monkeypatch, tmp_path):
        """Primary guard, checked without touching the filesystem at all.

        Deliberately at the resolver rather than over HTTP: proving the refusal
        must not require issuing a write that could land on a real file.
        """
        import paths
        from fastapi import HTTPException
        import main

        monkeypatch.setattr(paths, "IS_ISOLATED", True)
        monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))

        with pytest.raises(HTTPException) as exc:
            main._resolve_admin_script_path(self.PROBE, for_write=True)
        assert exc.value.status_code == 403

        # Reads stay allowed - reading a mapper is harmless, overwriting is the
        # incident. This also proves the 403 is the *write* guard, not a blanket
        # rejection of the prefix.
        assert main._resolve_admin_script_path(self.PROBE, for_write=False)

        # And the relocated tree is still writable, or the fix would be "refuse
        # everything", which defeats the purpose.
        monkeypatch.setattr(paths, "WORKSPACE_DIR", str(tmp_path / "ingestion_workspace"))
        got = main._resolve_admin_script_path("ingestion_workspace/t/scripts/a.py",
                                              for_write=True)
        assert str(tmp_path) in got

    def test_write_to_mappers_is_refused_end_to_end(
            self, admin_client, monkeypatch, tmp_path, live_mappers_must_be_untouched):
        """Same guard over real HTTP, with the tree protected by the fixture."""
        import paths

        monkeypatch.setattr(paths, "IS_ISOLATED", True)
        monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))

        res = admin_client.post("/admin/scripts/code", json={
            "path": self.PROBE,
            "code": "# isolation probe - must never be written\n",
        })
        assert res.status_code == 403, (
            f"isolated server accepted a write into the live mappers/ tree "
            f"(status {res.status_code})")
        # The admin gate ALSO answers 403 (wrong token), so the status code alone
        # would let this pass for the wrong reason if the header ever broke.
        # Pin the reason to the isolation guard's own message.
        assert "isolated data root" in res.json()["detail"], res.text

    def test_existing_live_mapper_is_not_even_opened(
            self, admin_client, monkeypatch, tmp_path, live_mappers_must_be_untouched):
        """Targets a real file: byte- AND mtime-identical is the claim."""
        import paths

        target = "mappers/__init__.py"
        if not os.path.exists(os.path.join(MAPPERS_ROOT, "__init__.py")):
            pytest.skip("server/mappers/__init__.py not present in this checkout")

        monkeypatch.setattr(paths, "IS_ISOLATED", True)
        monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))

        res = admin_client.post("/admin/scripts/code", json={
            "path": target, "code": "# CLOBBERED\n"})
        assert res.status_code == 403
        # See the sibling test: the admin gate shares this status code, so the
        # refusal has to be attributed to the isolation guard explicitly.
        assert "isolated data root" in res.json()["detail"], res.text

    def test_reads_still_work_when_isolated(
            self, client, monkeypatch, tmp_path, live_mappers_must_be_untouched):
        import paths

        target = "mappers/__init__.py"
        if not os.path.exists(os.path.join(MAPPERS_ROOT, "__init__.py")):
            pytest.skip("server/mappers/__init__.py not present in this checkout")

        monkeypatch.setattr(paths, "IS_ISOLATED", True)
        monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))

        res = client.get("/admin/scripts/code", params={"path": target})
        assert res.status_code == 200, res.text

    def test_workspace_writes_still_work_when_isolated(self, admin_client, monkeypatch, tmp_path):
        """The relocated tree stays writable - that is the whole point.

        Guards against 'fixing' the mappers gap by refusing every write.
        """
        import paths

        iso_root = tmp_path / "iso"
        monkeypatch.setattr(paths, "IS_ISOLATED", True)
        monkeypatch.setattr(paths, "DATA_ROOT", str(iso_root))
        monkeypatch.setattr(paths, "WORKSPACE_DIR", str(iso_root / "ingestion_workspace"))

        rel = "ingestion_workspace/devenv_probe_tbl/scripts/probe.py"
        res = admin_client.post("/admin/scripts/code", json={"path": rel, "code": "# ok\n"})
        assert res.status_code == 200, res.text

        written = iso_root / "ingestion_workspace" / "devenv_probe_tbl" / "scripts" / "probe.py"
        assert written.exists(), "write did not land under the isolated data root"
        assert not os.path.exists(
            os.path.join(SERVER_DIR, "ingestion_workspace", "devenv_probe_tbl")), \
            "write leaked into the live workspace"


# --------------------------------------------------------------------------- 4
# Process log files. Found by the first team to use the isolated environment:
# utils/logger.py built its directory from its own __file__, so every process
# `devenv up` started appended to the user's live server/*.log - transaction ids
# that exist only in assy_qa turned up in server/chain_worker.log. Append-only,
# so nothing was destroyed, but log lines are how the next person reconstructs an
# incident and a drill must not pollute the record it may later be read against.
_LOG_PROBE = r"""
import os, sys, json
sys.path.insert(0, os.environ["PROBE_SERVER_DIR"])
import paths
from utils.logger import get_process_logger

name = os.environ["PROBE_LOG_NAME"]
import logging

lg = get_process_logger("IsoLogProbe", name)
lg.info("PROBE_LINE_MARKER")

# [B3] Handlers live on the root logger now, so collect them the way logging
# itself does at emit time: walk the logger and its ancestors. Reading only
# lg.handlers would have reported "no file handler" for a logger that writes
# perfectly well - and, worse, would have passed for a logger that wrote nowhere
# if the handlers were ever put back on the named logger alone.
effective = []
node = lg
while node:
    effective.extend(node.handlers)
    node = node.parent if node.propagate else None

for h in effective:
    try:
        h.flush()
    except Exception:
        pass
print("@@" + json.dumps({
    "DATA_ROOT": paths.DATA_ROOT,
    "expected": paths.log_path(name),
    "handler_files": [h.baseFilename for h in effective
                      if hasattr(h, "baseFilename")],
}))
"""


@pytest.fixture
def probe_log_name():
    """A log filename that cannot collide with any real process log.

    Then remove it from the live tree if it appears - and report that as the
    failure. Deliberately NOT a snapshot-and-restore fixture like the mappers
    one: server/*.log is being appended to by the user's running processes right
    now, so "restoring" a live log would destroy lines the live server just
    wrote. Only a file this test itself created may be touched.
    """
    import uuid
    name = f"_devenv_logprobe_{uuid.uuid4().hex[:12]}.log"
    yield name

    leaked = os.path.join(SERVER_DIR, name)
    existed = os.path.exists(leaked)
    if existed:
        os.remove(leaked)
    assert not existed, (
        f"the isolated process wrote {leaked} into the LIVE server tree "
        "(removed, but the log relocation is broken)")


class TestProcessLogsFollowTheDataRoot:
    """Guards utils/logger.py resolving its file handler through paths.py."""

    def test_isolated_process_log_lands_under_the_data_root(self, tmp_path,
                                                            probe_log_name):
        """Red the moment the file handler goes back to a __file__-relative dir.

        Exercises get_process_logger itself rather than asserting on
        paths.log_path: the claim is about where a real FileHandler opens, and a
        test that never builds one would pass against the broken version.
        """
        root = tmp_path / "isolated_root"
        env = os.environ.copy()
        env["PROBE_SERVER_DIR"] = SERVER_DIR
        env["PROBE_LOG_NAME"] = probe_log_name
        env["ASSY_DATA_ROOT"] = str(root)
        env["DATABASE_URL"] = "sqlite:///:memory:"
        env["PYTHONIOENCODING"] = "utf-8"

        proc = subprocess.run([sys.executable, "-c", _LOG_PROBE], cwd=SERVER_DIR,
                              env=env, capture_output=True, text=True,
                              errors="replace")
        assert proc.returncode == 0, f"probe failed:\n{proc.stdout}\n{proc.stderr}"
        line = [l for l in proc.stdout.splitlines() if l.startswith("@@")]
        assert line, f"probe produced no result:\n{proc.stdout}\n{proc.stderr}"
        got = json.loads(line[-1][2:])

        relocated = root / probe_log_name
        assert got["handler_files"], "get_process_logger registered no file handler"
        assert len(got["handler_files"]) == 1
        assert os.path.normcase(got["handler_files"][0]) == os.path.normcase(
            str(relocated)), (
            "the process log did not follow ASSY_DATA_ROOT: handler opened "
            f"{got['handler_files'][0]}, expected {relocated}")
        # Binds the handler to paths.py rather than to any coincidental path.
        assert os.path.normcase(got["expected"]) == os.path.normcase(str(relocated))

        # The sensitivity control: the relocated file must actually have grown,
        # or "the live one is unchanged" would be satisfied by a logger that
        # wrote nowhere at all.
        assert relocated.exists(), "no log file was created under the isolated root"
        assert "PROBE_LINE_MARKER" in relocated.read_text(encoding="utf-8")

        # And nothing of that name reached the live tree (also asserted, with
        # repair, by the fixture).
        assert not os.path.exists(os.path.join(SERVER_DIR, probe_log_name))

    def test_unset_data_root_keeps_the_production_log_location(self):
        """Production must be byte-for-byte unchanged when the override is absent.

        Calls the real paths.log_path but deliberately does not construct a
        handler: with ASSY_DATA_ROOT unset that would open a file in the user's
        live tree. Combined with the test above - which proves the handler opens
        at exactly paths.log_path(name) - this pins production's location.
        """
        got = _probe_paths(None)
        assert os.path.normcase(got["paths.log_path"]) == os.path.normcase(
            os.path.join(SERVER_DIR, "server.log"))


# --------------------------------------------------------------------------- 5
# The sibling the log bug pointed at: graph_sync_worker built VIRTUAL_GRAPH_PATH
# from its own __file__ while the module's ONTOLOGY_PATH right above it already
# went through paths.py. Worse than the log: save_virtual_graph() *overwrites*
# it, and run_graph_sync.py is one of the three processes `devenv up` starts.
_GRAPH_PROBE = r"""
import os, sys, json
sys.path.insert(0, os.environ["PROBE_SERVER_DIR"])
import paths
import graph_sync_worker
print("@@" + json.dumps({
    "DATA_ROOT": paths.DATA_ROOT,
    "VIRTUAL_GRAPH_PATH": graph_sync_worker.VIRTUAL_GRAPH_PATH,
    "ONTOLOGY_PATH": graph_sync_worker.ONTOLOGY_PATH,
}))
"""


class TestVirtualGraphFollowsTheDataRoot:
    """Guards the one data file the graph worker writes outside config/."""

    def test_isolated_graph_worker_does_not_write_the_live_virtual_graph(self, tmp_path):
        root = tmp_path / "isolated_root"
        env = os.environ.copy()
        env["PROBE_SERVER_DIR"] = SERVER_DIR
        env["ASSY_DATA_ROOT"] = str(root)
        env["DATABASE_URL"] = "sqlite:///:memory:"
        env["PYTHONIOENCODING"] = "utf-8"

        proc = subprocess.run([sys.executable, "-c", _GRAPH_PROBE], cwd=SERVER_DIR,
                              env=env, capture_output=True, text=True,
                              errors="replace")
        assert proc.returncode == 0, f"probe failed:\n{proc.stdout}\n{proc.stderr}"
        line = [l for l in proc.stdout.splitlines() if l.startswith("@@")]
        assert line, f"probe produced no result:\n{proc.stdout}\n{proc.stderr}"
        got = json.loads(line[-1][2:])

        root_nc = os.path.normcase(str(root)) + os.sep
        assert os.path.normcase(got["VIRTUAL_GRAPH_PATH"]).startswith(root_nc), (
            "an isolated graph worker still writes the LIVE virtual graph: "
            f"{got['VIRTUAL_GRAPH_PATH']}")
        assert os.path.normcase(got["ONTOLOGY_PATH"]).startswith(root_nc)


# --------------------------------------------------------------------------- 6
# The isolated watcher's safety rail. `devenv up` starts no watcher on purpose,
# but an ingestion drill needs one - and a watcher pointed at production would
# ingest drill files into the user's live data. That is the single most
# destructive action in this setup, so the refusal is asserted here as a
# decision, never as the aftermath of a write.
DEV_ENV_DIR = os.path.join(SERVER_DIR, "scripts", "dev_env")
if DEV_ENV_DIR not in sys.path:
    sys.path.insert(0, DEV_ENV_DIR)

import iso_watcher  # noqa: E402

ISO_WATCHER_PY = os.path.join(DEV_ENV_DIR, "iso_watcher.py")


def _isolated_facts(root):
    """A configuration the gate must accept."""
    root = str(root)
    return {
        "server_dir": SERVER_DIR,
        "data_root": root,
        "config_dir": os.path.join(root, "config"),
        "workspace_dir": os.path.join(root, "ingestion_workspace"),
        "is_isolated": True,
        "workspace_exists": True,
        "engine_url": "postgresql://postgres:***@localhost:5432/assy_qa",
        "api_base_url": "http://127.0.0.1:8081",
        "assy_api_base": "http://127.0.0.1:8081",
    }


def _production_facts():
    """The real thing: every fact pointing at the user's live environment."""
    return {
        "server_dir": SERVER_DIR,
        "data_root": SERVER_DIR,
        "config_dir": os.path.join(SERVER_DIR, "config"),
        "workspace_dir": os.path.join(SERVER_DIR, "ingestion_workspace"),
        "is_isolated": False,
        "workspace_exists": True,
        "engine_url": "postgresql://postgres:***@localhost:5432/assy_manager",
        "api_base_url": "http://127.0.0.1:8080",
        "assy_api_base": "http://localhost:8080",
    }


class TestIsolatedWatcherGateIsAPureDecision:
    """Every rule proven by asking the gate, with nothing pointed anywhere."""

    def test_production_configuration_is_refused(self):
        v = iso_watcher.check_static_isolation(**_production_facts())
        assert v, "the gate accepted a watcher pointed at production"
        blob = " ".join(v)
        assert "assy_manager" in blob, f"the refusal never names the database: {v}"
        assert "ASSY_DATA_ROOT" in blob or "IS_ISOLATED" in blob, (
            f"the refusal never names the data root: {v}")

    def test_isolated_configuration_is_accepted(self, tmp_path):
        """Guards against 'fix' by refusing everything - a rail that never lets
        anything through is as useless as one that never refuses."""
        v = iso_watcher.check_static_isolation(**_isolated_facts(tmp_path))
        assert v == [], f"the gate refused a properly isolated configuration: {v}"

    @pytest.mark.parametrize("field,value", [
        ("is_isolated", False),
        ("data_root", SERVER_DIR),
        ("config_dir", os.path.join(SERVER_DIR, "config")),
        ("workspace_dir", os.path.join(SERVER_DIR, "ingestion_workspace")),
        ("workspace_exists", False),
        ("engine_url", "postgresql://postgres:***@localhost:5432/assy_manager"),
        ("engine_url", ""),
        ("api_base_url", None),
        ("api_base_url", "http://127.0.0.1:8080"),
        ("api_base_url", "http://127.0.0.1:8090"),
        ("assy_api_base", "http://localhost:8080"),
    ])
    def test_each_rule_refuses_on_its_own(self, tmp_path, field, value):
        """One production fact at a time, everything else isolated.

        This is what makes the suite sensitive to a *single* deleted rule:
        an all-or-nothing production case would stay red with ten rules left.
        """
        facts = _isolated_facts(tmp_path)
        facts[field] = value
        v = iso_watcher.check_static_isolation(**facts)
        assert v, f"the gate accepted {field}={value!r}"

    def test_live_connection_on_production_is_refused(self):
        v = iso_watcher.check_live_isolation(
            live_database="assy_manager",
            engine_url="postgresql://postgres:***@localhost:5432/assy_manager")
        assert v and "assy_manager" in " ".join(v)

    def test_url_that_lies_about_its_database_is_refused(self):
        """The reason the live probe exists at all: the URL is not evidence."""
        v = iso_watcher.check_live_isolation(
            live_database="assy_manager",
            engine_url="postgresql://postgres:***@localhost:5432/assy_qa")
        assert v, "a URL claiming assy_qa on a connection reaching production was accepted"

    def test_unprovable_database_is_refused(self):
        v = iso_watcher.check_live_isolation(live_database="", engine_url="x/assy_qa")
        assert v, "the gate accepted a connection that could not name its database"

    def test_isolated_connection_is_accepted(self):
        v = iso_watcher.check_live_isolation(
            live_database="assy_qa",
            engine_url="postgresql://postgres:***@localhost:5432/assy_qa")
        assert v == []

    def test_production_db_name_stays_in_sync_with_the_database_module(self):
        """Red if the production database is ever renamed and this list is not.

        A stale name here would silently turn the whole gate into a no-op.
        """
        from database import database as db_mod
        prod = db_mod.DEFAULT_PG_URL.rsplit("/", 1)[-1].split("?", 1)[0]
        assert prod in iso_watcher.PRODUCTION_DB_NAMES, (
            f"database.py's default database is {prod!r}, which iso_watcher does "
            f"not treat as production ({set(iso_watcher.PRODUCTION_DB_NAMES)})")


class TestIsolatedWatcherRefusalIsStructural:
    """The gate must be unreachable-around, not merely present."""

    def _scoped_imports(self):
        """(enclosing function, imported module) for every import in the file."""
        import ast
        with io.open(ISO_WATCHER_PY, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        found = []

        def visit(node, scope):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.Import):
                    found.extend((scope, a.name) for a in child.names)
                elif isinstance(child, ast.ImportFrom):
                    found.append((scope, child.module or ""))
                inner = child.name if isinstance(child, ast.FunctionDef) else scope
                visit(child, inner)

        visit(tree, "<module>")
        return found

    def test_run_watcher_is_imported_only_after_the_gate(self):
        """`import run_watcher` alone opens a log file, issues DDL and resolves
        the workspace to watch. If it happened at module scope, a refusal would
        arrive after the damage."""
        scoped = self._scoped_imports()
        offenders = [(s, m) for s, m in scoped
                     if m.split(".")[0] in {"run_watcher", "directory_watcher"}
                     and s != "_start_watcher"]
        assert not offenders, (
            f"run_watcher is imported outside _start_watcher: {offenders}")
        assert ("_start_watcher", "run_watcher") in scoped, (
            "_start_watcher no longer imports run_watcher - is the launcher still "
            "wired to anything?")

    def test_nothing_that_touches_disk_is_imported_at_module_scope(self):
        module_scope = {m for s, m in self._scoped_imports() if s == "<module>"}
        risky = {m for m in module_scope
                 if m.split(".")[0] in {"run_watcher", "database", "utils",
                                        "main", "directory_watcher"}}
        assert not risky, (
            f"imported at module scope, i.e. before the gate can refuse: {risky}")

    def test_the_gate_runs_before_the_watcher_starts(self):
        """Ordering inside main(): both checks, then _start_watcher."""
        import ast
        with io.open(ISO_WATCHER_PY, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "main")

        lines = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                lines.setdefault(node.func.id, []).append(node.lineno)

        for required in ("check_static_isolation", "check_live_isolation",
                         "_start_watcher"):
            assert required in lines, f"main() never calls {required}"
        assert min(lines["_start_watcher"]) > max(lines["check_static_isolation"]), \
            "the watcher is started before the static gate has run"
        assert min(lines["_start_watcher"]) > max(lines["check_live_isolation"]), \
            "the watcher is started before the live database check has run"

    def test_devenv_up_still_starts_no_watcher(self):
        """watcher-up is a separate verb precisely so `up` stays churn-free."""
        import devenv
        started = " ".join(" ".join(cmd) for _, cmd in devenv.PROCESSES)
        assert "run_watcher" not in started
        assert "run_auto_update" not in started
        assert {n for n, _ in devenv.PROCESSES} == {"api", "chain", "graph"}


class TestIsolatedWatcherLauncherEndToEnd:
    """The real CLI, run as a real process."""

    def _run(self, env_overrides, args=(), timeout=180):
        env = os.environ.copy()
        env.pop("ASSY_DATA_ROOT", None)
        env["PYTHONIOENCODING"] = "utf-8"
        for k, v in env_overrides.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v
        return subprocess.run([sys.executable, ISO_WATCHER_PY, *args],
                              cwd=SERVER_DIR, env=env, capture_output=True,
                              text=True, errors="replace", timeout=timeout)

    def test_production_configuration_does_not_start(self):
        """Pointed at the live data root and a database named assy_manager.

        Two belts, because a negative test must not be able to cause the
        incident it describes:
          * the static gate refuses before any connection is opened, and
          * the database host:port is 127.0.0.1:1, which nothing listens on, so
            even a gate that let this through could not reach production.
        Defect injection for this rail is done on the pure functions above,
        where no process is started at all.
        """
        proc = self._run({
            "ASSY_DATA_ROOT": None,   # -> the live server/ tree
            "DATABASE_URL": "postgresql://postgres:admin@127.0.0.1:1/assy_manager",
            "API_BASE_URL": "http://127.0.0.1:8080",
        })
        out = proc.stdout + proc.stderr
        assert proc.returncode == iso_watcher.EXIT_REFUSED, (
            f"expected exit {iso_watcher.EXIT_REFUSED}, got {proc.returncode}\n{out}")
        assert iso_watcher.REFUSED_MARKER in out, out
        assert iso_watcher.GATE_PASSED_MARKER not in out, (
            "the gate reported PASSED on a production configuration:\n" + out)
        assert "assy_manager" in out
        assert "IS_ISOLATED" in out

    def test_isolated_configuration_passes_the_gate(self, tmp_path):
        """The other half: a rail that never lets anything through is broken too."""
        root = tmp_path / "iso"
        (root / "ingestion_workspace").mkdir(parents=True)
        (root / "config").mkdir()

        proc = self._run({
            "ASSY_DATA_ROOT": str(root),
            "DATABASE_URL": "sqlite:///" + str(root / "iso_probe.db").replace("\\", "/"),
            "API_BASE_URL": "http://127.0.0.1:8081",
            "ASSY_API_BASE": "http://127.0.0.1:8081",
        }, args=("--check-only",))
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert iso_watcher.GATE_PASSED_MARKER in out, out
        assert iso_watcher.REFUSED_MARKER not in out

    def test_missing_isolated_workspace_does_not_start(self, tmp_path):
        """'Cannot prove it is safe' must also mean 'does not start'."""
        proc = self._run({
            "ASSY_DATA_ROOT": str(tmp_path / "never_bootstrapped"),
            "DATABASE_URL": "sqlite:///:memory:",
            "API_BASE_URL": "http://127.0.0.1:8081",
        }, args=("--check-only",))
        assert proc.returncode == iso_watcher.EXIT_REFUSED, proc.stdout + proc.stderr
