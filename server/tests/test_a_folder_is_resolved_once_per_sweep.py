# -*- coding: utf-8 -*-
"""총괄 f0bdb35eb (소유자 「glob 은 1 초도 안 걸리던데 리스트 뽑는 게 왜 오래 걸려」): `_safe_relative_path` resolved the
file AND the root on every call - a realpath opens the path on Windows, a round trip each on a share, files x (1 +
sources) x 2 of them for a re-read preview and for every external sweep. Now a file's real path is its folder's and
its name, and inside one sweep (`one_sweep`) a folder is resolved once. A junction is a folder: a file under one that
leads outside the root is still outside. What is picked is what each file's judgement outside a sweep picks."""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (SERVER_DIR, os.path.join(SERVER_DIR, "parsers"), os.path.dirname(__file__)):
    if path not in sys.path:
        sys.path.insert(0, path)

import directory_watcher                                         # noqa: E402
from directory_watcher import WorkspaceWatcher, IngestionHandler, _safe_relative_path, one_sweep   # noqa: E402
from ingestion import reread                                     # noqa: E402

FOLDERS, PER_FOLDER = 5, 40


def _tree(root, name="f%02d.csv"):
    files = []
    for folder in range(FOLDERS):
        os.makedirs(os.path.join(root, "d%d" % folder), exist_ok=True)
        for n in range(PER_FOLDER):
            path = os.path.join(root, "d%d" % folder, name % n)
            open(path, "w").close()
            files.append(path)
    return files


def _counted(monkeypatch):
    calls, real = [], os.path.realpath
    monkeypatch.setattr(os.path, "realpath", lambda path, *a, **k: (calls.append(path), real(path, *a, **k))[1])
    return calls


def test_the_preview_resolves_each_folder_once_and_picks_what_each_file_s_judgement_picks(tmp_path, monkeypatch):
    raws, share = str(tmp_path / "raws"), str(tmp_path / "share")
    files = _tree(raws)
    _tree(share)
    specs = [{"root": share, "options": {"glob": ["**/*.csv"]}, "table_name": "t"},
             {"root": str(tmp_path / "other"), "options": {"glob": ["**/*.csv"]}, "table_name": "t"}]
    monkeypatch.setattr(reread, "table_sources", lambda table: (raws, specs))
    monkeypatch.setattr(reread, "_newest_rows_of", lambda db, table, walked: {})
    alone = sorted(path for path in files if _safe_relative_path(path, raws) is not None)      # each, no sweep
    calls = _counted(monkeypatch)
    got = reread.select_files(None, "t", raws)
    assert sorted(path for _log, _rel, path in got["picked"]) == alone and len(alone) == FOLDERS * PER_FOLDER
    # the folders, the raws root and the walked folder (the same), the two source roots - not files x ...
    assert len(calls) <= FOLDERS + 4, len(calls)


def test_the_external_sweep_resolves_each_folder_once(tmp_path, monkeypatch):
    from test_external_source_watcher import TABLES, _specs
    from database import crud

    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: TABLES)
    monkeypatch.setattr(crud, "TABLE_CONFIG", TABLES)
    workspace, external = tmp_path / "ingestion_workspace", tmp_path / "external"
    workspace.mkdir()
    _tree(str(external), name="x%02d.json")
    monkeypatch.setattr(directory_watcher, "load_ingestion_settings", lambda: _specs(external))
    monkeypatch.setattr(IngestionHandler, "_handle_event", lambda self, path: None)
    monkeypatch.setattr(IngestionHandler, "settle_already_terminal", lambda self, entries: set())
    watcher = WorkspaceWatcher(str(workspace))
    watcher.discover_and_watch()
    calls = _counted(monkeypatch)
    watcher.sweep_external_sources()
    # two sources on one root: the root and its folders - not files x sources x 2
    assert 0 < len(calls) <= FOLDERS + 2, len(calls)


@pytest.mark.skipif(os.name != "nt", reason="a directory junction is a Windows folder link")
def test_a_file_under_a_junction_leading_outside_is_still_outside(tmp_path, monkeypatch):
    import _winapi

    raws, outside = tmp_path / "raws", tmp_path / "outside"
    raws.mkdir()
    outside.mkdir()
    (outside / "f.csv").write_text("x")
    _winapi.CreateJunction(str(outside), str(raws / "j"))
    under = str(raws / "j" / "f.csv")
    assert os.path.exists(under), "canary: the junction leads to the file"
    assert _safe_relative_path(under, str(raws)) is None
    with one_sweep():
        assert _safe_relative_path(under, str(raws)) is None
    monkeypatch.setattr(reread, "table_sources", lambda table: (str(raws), []))
    monkeypatch.setattr(reread, "_newest_rows_of", lambda db, table, walked: {})
    got = reread.select_files(None, "t", str(raws))
    assert got["picked"] == [] and got["not_taken"] == {reread.OUTSIDE_SOURCES: 1}, got
