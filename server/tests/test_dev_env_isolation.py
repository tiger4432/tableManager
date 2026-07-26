# -*- coding: utf-8 -*-
"""Regression guards for the isolated development environment.

The isolation rests on two small things that nothing else asserts, and a guard
nothing exercises is indistinguishable from no guard:

  1. conftest.py pins DATABASE_URL before `from main import app`. Without it,
     main.py's module-level `Base.metadata.create_all(bind=engine)` issues DDL to
     whatever DATABASE_URL resolves to - unset, that is the live production
     database (board issue #16a).
  2. server/paths.py is the single override point for config/ and
     ingestion_workspace/. If a module goes back to building those paths from its
     own __file__, an isolated server silently reads and writes production again.
  3. mappers/ is deliberately NOT relocated, so an isolated server must refuse to
     write there rather than reach into the user's live files.

Each test is written so that removing the thing it guards turns it red.
"""
import os
import sys
import json
import hashlib
import subprocess

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)


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
            self, client, monkeypatch, tmp_path, live_mappers_must_be_untouched):
        """Same guard over real HTTP, with the tree protected by the fixture."""
        import paths

        monkeypatch.setattr(paths, "IS_ISOLATED", True)
        monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))

        res = client.post("/admin/scripts/code", json={
            "path": self.PROBE,
            "code": "# isolation probe - must never be written\n",
        })
        assert res.status_code == 403, (
            f"isolated server accepted a write into the live mappers/ tree "
            f"(status {res.status_code})")

    def test_existing_live_mapper_is_not_even_opened(
            self, client, monkeypatch, tmp_path, live_mappers_must_be_untouched):
        """Targets a real file: byte- AND mtime-identical is the claim."""
        import paths

        target = "mappers/__init__.py"
        if not os.path.exists(os.path.join(MAPPERS_ROOT, "__init__.py")):
            pytest.skip("server/mappers/__init__.py not present in this checkout")

        monkeypatch.setattr(paths, "IS_ISOLATED", True)
        monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))

        res = client.post("/admin/scripts/code", json={
            "path": target, "code": "# CLOBBERED\n"})
        assert res.status_code == 403

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

    def test_workspace_writes_still_work_when_isolated(self, client, monkeypatch, tmp_path):
        """The relocated tree stays writable - that is the whole point.

        Guards against 'fixing' the mappers gap by refusing every write.
        """
        import paths

        iso_root = tmp_path / "iso"
        monkeypatch.setattr(paths, "IS_ISOLATED", True)
        monkeypatch.setattr(paths, "DATA_ROOT", str(iso_root))
        monkeypatch.setattr(paths, "WORKSPACE_DIR", str(iso_root / "ingestion_workspace"))

        rel = "ingestion_workspace/devenv_probe_tbl/scripts/probe.py"
        res = client.post("/admin/scripts/code", json={"path": rel, "code": "# ok\n"})
        assert res.status_code == 200, res.text

        written = iso_root / "ingestion_workspace" / "devenv_probe_tbl" / "scripts" / "probe.py"
        assert written.exists(), "write did not land under the isolated data root"
        assert not os.path.exists(
            os.path.join(SERVER_DIR, "ingestion_workspace", "devenv_probe_tbl")), \
            "write leaked into the live workspace"
