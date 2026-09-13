# -*- coding: utf-8 -*-
"""S-211 ③. `client/` became `desktop/`, and four seats name that folder without importing it.

🔴 EVERY CONSUMER OF THAT FOLDER IS INVISIBLE TO AN IMPORT GREP (클라 실측 `1ca4089a`): the
launcher spawns a PATH, two routes serve what was BUILT at a path, and `.gitignore` carries a
hand-written exception. So a rename lands green on every import check while the desktop
window silently never opens - the child is `restartable=False`, which is the quietest way for
a process to die.

🔴 THE LAUNCHER SEAT IS SCORED THROUGH THE FUNCTION IT ACTUALLY CALLS. `main()` builds the
roster after refusing ports and reporting schema drift, so it cannot be run here; the path is
now produced by `desktop_shell_path()`, which the spec list calls. Asserting on the source
text of `main()` would be true of a launcher that points at a folder that does not exist.

⚠️ AND THE ROUTES ARE DRIVEN, not read. Both answer 404 when no build is present - which is
the state of any box where nobody ran the packaging script - so what is scored is WHICH path
they looked at, taken from the refusal itself rather than from a second spelling here.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT_DIR = os.path.dirname(SERVER_DIR)
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import main                                                          # noqa: E402
import run_decoupled_app                                             # noqa: E402


# ---------------------------------------------------------------------------
# 🔴 the launcher spawns a path that is really there
# ---------------------------------------------------------------------------

def test_the_launcher_spawns_the_shell_that_exists():
    """🔴 THE SEAT THAT FAILS SILENTLY. A path nobody checked is a window that never opens."""
    path = run_decoupled_app.desktop_shell_path(ROOT_DIR)

    assert os.path.isfile(path), path
    assert os.path.basename(os.path.dirname(path)) == "desktop"


def test_the_shell_folder_has_one_spelling_across_the_two_processes():
    """⛔ THE LAUNCHER RUNS IT, THE ROUTES SERVE WHAT IS BUILT FROM IT. Two spellings is how a
    rename reaches one end and not the other - which is exactly the defect this round fixes,
    so the two constants are compared rather than each being checked against a literal."""
    assert main.DESKTOP_DIR == run_decoupled_app.DESKTOP_DIR


def test_the_old_folder_is_gone_rather_than_copied():
    assert not os.path.exists(os.path.join(ROOT_DIR, "client")), (
        "the desktop shell has two homes")


# ---------------------------------------------------------------------------
# ⚠️ the two routes, driven through a mounted router
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.add_api_route("/api/download/client", main.download_desktop_client, methods=["GET"])
    app.add_api_route("/api/desktop/download", main.download_desktop_bundle, methods=["GET"])
    return TestClient(app)


def test_the_bundle_route_looks_under_the_desktop_folder(client, monkeypatch):
    """⚠️ SCORED ON THE PATH IT ASKED ABOUT, not on a copy of that path written here. The
    route's own `os.path.exists` call is the only thing that knows where it looked."""
    asked = []
    real = os.path.exists
    monkeypatch.setattr(os.path, "exists", lambda p: asked.append(p) or real(p))

    answer = client.get("/api/desktop/download")

    assert answer.status_code in (200, 404), answer.text
    looked = [p for p in asked if "AssyManagerClient.zip" in p]
    assert looked, asked
    assert os.path.join("desktop", "dist") in looked[0], looked[0]


def test_the_exe_route_looks_under_the_desktop_folder(client, monkeypatch):
    asked = []
    real = os.path.exists
    monkeypatch.setattr(os.path, "exists", lambda p: asked.append(p) or real(p))

    try:
        client.get("/api/download/client")
    except Exception:                                        # pragma: no cover - 404 raises
        pass

    looked = [p for p in asked if "AssyManagerClient.exe" in p]
    assert looked, asked
    for path in looked:
        assert os.path.join("desktop", "dist") in path, path


def test_the_absent_build_is_answered_as_absence(client):
    """⚠️ THE STATE OF ANY BOX WHERE NOBODY RAN THE PACKAGING SCRIPT. 404 with a reason, so
    the admin button can say 「데스크톱 빌드가 없습니다」 instead of showing a 500."""
    answer = client.get("/api/desktop/download")

    if answer.status_code == 404:
        assert answer.json()["reason"] == "desktop_build_absent"
