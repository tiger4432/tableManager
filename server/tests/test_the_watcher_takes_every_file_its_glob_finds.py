# -*- coding: utf-8 -*-
"""소유자 10-21 「와처는 glob 으로 잡히는 건 무조건 잡는다」 (총괄): what Python's glob finds under a source's root with its
pattern (a name alone at any depth; to its max_depth when written) is what the sweep hands on - or named on the
source's line. Mixed-case names, deep folders, a hidden file, a junction leading outside the root and a second
table's source over the same tree are on the board.

  taken             glob (hidden files too) - the files under the junction             -> handed on
  outside the root  the files under the junction (glob follows it, the real path is out) -> counted on the line, by name
"""
import glob
import os
import re

import pytest

import directory_watcher
from directory_watcher import IngestionHandler, WorkspaceWatcher
from tests.test_external_source_watcher import TABLES  # noqa: F401 - the autouse table config below
from tests.test_external_source_watcher import canonical_void_config  # noqa: F401

FILES = ("voids.csv", "UP/VOIDS.CSV", "LOT1/W01/STEP_02/voids.csv", "LOT1/W04/STEP_02/Voids.Csv", "lot4/w01/step_02/voids.csv",
         "LOT1/W01/STEP_01/voids.csv", "LOT1/W02/STEP_02/other.csv", "LOT2/W01/STEP_02/a/b/c/d/voids.csv",
         "LOT2/.hidden/STEP_02/voids.csv", "LOT2/W03/STEP_02/.voids.csv", "x/STEP_02/voids.csv")
PATTERNS = {"name": "voids.csv", "sub": "LOT*/W*/STEP_02/*.csv", "star": "**/STEP_02/*oids.csv"}


def _board(tmp_path):
    root = tmp_path / "share"
    for rel in FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    outside = tmp_path / "outside" / "STEP_02"
    outside.mkdir(parents=True)
    (outside / "voids.csv").write_text("x", encoding="utf-8")
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(tmp_path / "outside"), str(root / "LOT3"))
    else:
        os.symlink(tmp_path / "outside", root / "LOT3")
    return root


def _globbed(root, pattern, max_depth):
    """Python's glob: a name alone at any depth, hidden files too, to max_depth."""
    full = os.path.join(str(root), pattern if "/" in pattern else "**/" + pattern)
    found = set()
    for path in glob.glob(full, recursive=True, include_hidden=True):
        rel = os.path.relpath(path, root)
        if os.path.isfile(path) and (max_depth is None or rel.count(os.sep) <= max_depth):
            found.add(os.path.normcase(os.path.abspath(path)))
    return found


@pytest.mark.parametrize("max_depth", [None, 3])
@pytest.mark.parametrize("shape", sorted(PATTERNS))
def test_every_file_the_glob_finds_is_handed_on_or_named(tmp_path, monkeypatch, caplog, shape, max_depth):
    root = _board(tmp_path)
    source = {"path": str(root), "table_name": "void_obs", "parser": "voids_json",
              "options": {"glob": PATTERNS[shape]}}
    if max_depth is not None:
        source["max_depth"] = max_depth
    other = {"path": str(root / "LOT1"), "table_name": "inspection_run", "parser": "voids_json",
             "options": {"glob": "*.csv"}}                                       # a second table over the same files
    monkeypatch.setattr(directory_watcher, "load_ingestion_settings", lambda: {"external_sources": [source, other]})
    handed = []
    monkeypatch.setattr(IngestionHandler, "_handle_event",
                        lambda self, path: handed.append((self.table_name, os.path.normcase(os.path.abspath(path)))))
    monkeypatch.setattr(IngestionHandler, "already_checked", lambda self, entries: set())
    (tmp_path / "ingestion_workspace").mkdir()
    watcher = WorkspaceWatcher(str(tmp_path / "ingestion_workspace"))
    watcher.discover_and_watch()
    assert len(watcher.external_targets) == 2

    with caplog.at_level("INFO", logger="Watcher.DirectoryWatcher"):
        watcher.sweep_external_sources()

    globbed = _globbed(root, PATTERNS[shape], max_depth)
    junction = {path for path in globbed if os.sep + "lot3" + os.sep in path}
    assert {path for table, path in handed if table == "void_obs"} == globbed - junction
    assert {path for table, path in handed if table == "inspection_run"} == _globbed(root / "LOT1", "*.csv", None)
    [line] = [r.getMessage() for r in caplog.records
              if r.getMessage().startswith("External source void_obs@") and "looked at" in r.getMessage()]
    assert re.search(r" - outside the root %d · " % len(junction), line), line
    assert len(globbed - junction) >= 3 and (shape == "sub" or junction)          # the board is not empty
