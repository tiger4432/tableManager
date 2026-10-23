# -*- coding: utf-8 -*-
"""The checklist is a table of its own, one row per (table, file) (소유자 10-23 「파일당 한 행」, 총괄 64b264610 ②); the
records stay one per read. And the external sweep's walk does less for the same answers.

  the fill        records -> each file's newest one its row; a waiting row keeps its mark's state; a row the checklist
                  already has stays; once more -> nothing made
  name first      every path of a board: the name and depth judged before the path on the disk - the same reason or
                  none as the whole judgement first (filename and glob sources, max_depth, a case, a junction out of
                  the root, a junction inside it whose real path is below max_depth)
  folder memory   external_full_walk_every 3: sweep 0 walks all; sweep 1 lists no unchanged folder; a new file moves
                  its folder - that folder listed, a file written in place is not; sweep 3 walks all again; a sweep for
                  files just unchecked (`walk_all`, a changed reading) walks all; a binding retired and back (its
                  glob changed) walks all on its first sweep
  the period      sweep_interval_seconds read as declared, the constant when absent
"""
import json
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (SERVER_DIR, os.path.join(SERVER_DIR, "parsers")):
    if path not in sys.path:
        sys.path.insert(0, path)

import directory_watcher                                         # noqa: E402
from directory_watcher import Checked, IngestionHandler, WorkspaceWatcher, why_not_taken   # noqa: E402
from database import models                                      # noqa: E402
from ingestion import checkpoint                                 # noqa: E402


def _record(db, table, path, status, stamp=None):
    row = models.FileIngestionLog(filename=os.path.basename(path), filepath=path, table_name=table, status=status,
                                  retry_count=0, source="raws", file_mtime=stamp[0] if stamp else None,
                                  file_size=stamp[1] if stamp else None)
    db.add(row)
    db.flush()
    return row


def test_the_checklist_is_made_from_the_records_once(db_session):
    from datetime import datetime, timezone

    stamp = (datetime(2026, 10, 1, tzinfo=timezone.utc), 10)
    _record(db_session, "ta", r"C:\s\a.csv", "SUCCESS", stamp)
    newest_a = _record(db_session, "ta", "c:/s/A.CSV", "FAILED")                  # read again, failed: the newest
    waiting = _record(db_session, "ta", r"C:\s\b.csv", "PENDING_RETRY", stamp)
    db_session.add(models.FileRereadMark(log_id=waiting.id, status_before="SUCCESS"))
    _record(db_session, "ta", r"C:\s\c.csv", "SUCCESS", stamp)
    other_table = _record(db_session, "tb", r"C:\s\a.csv", "SUCCESS", stamp)
    db_session.add(models.FileIngestionLog(filename="x", filepath=None, table_name="ta", status="SUCCESS"))
    kept = checkpoint.note_file(db_session, "ta", r"C:\s\c.csv", status="PENDING_RETRY", status_before="STOOD")
    db_session.commit()

    assert checkpoint.fill_checklist(db_session) == 3
    rows = {(r.table_name, r.path_key): r for r in db_session.query(models.FileChecklist)}
    a = rows[("ta", checkpoint._keys(db_session, [r"C:\s\a.csv"])[0])]
    assert (a.status, a.file_mtime, a.log_id) == ("FAILED", None, newest_a.id)
    b = rows[("ta", checkpoint._keys(db_session, [r"C:\s\b.csv"])[0])]
    assert (b.status, b.status_before, b.file_size) == ("PENDING_RETRY", "SUCCESS", 10)
    assert rows[("ta", kept.path_key)].status_before == "STOOD"                     # the checklist's own row stays
    assert rows[("tb", a.path_key)].log_id == other_table.id
    assert len(rows) == 4
    assert checkpoint.fill_checklist(db_session) == 0


def _write(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _watcher(tmp_path, monkeypatch, sources, **settings):
    from database import crud

    tables = {"ta": {"business_key": "k", "column_types": {"k": "string"}, "display_columns": ["k"]}}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: tables)
    monkeypatch.setattr(crud, "TABLE_CONFIG", tables)
    monkeypatch.setattr(directory_watcher, "load_ingestion_settings",
                        lambda: dict(settings, external_sources=sources))
    workspace = tmp_path / "ingestion_workspace"
    workspace.mkdir(exist_ok=True)
    w = WorkspaceWatcher(str(workspace))
    w.discover_and_watch()
    return w


@pytest.mark.parametrize("options, max_depth", [({"filename": "voids.json"}, None),
                                                ({"glob": ["*/voids.json", "**/*.csv"]}, 1)])
def test_the_name_is_judged_first_and_the_answers_are_the_same(tmp_path, monkeypatch, options, max_depth):
    root, outside = tmp_path / "share", tmp_path / "outside"
    for rel in ("voids.json", "a/voids.json", "a/VOIDS.JSON", "a/img.png", "a/b/c/voids.json", "a/b/x.csv", "y.csv"):
        _write(str(root.joinpath(*rel.split("/"))))
    _write(str(outside / "voids.json"))
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(outside), str(root / "j"))
        # inside the root, deeper than it is walked: the walked path passes the name and depth, the real one is below
        # max_depth - only the disk judgement after the name refuses it
        _winapi.CreateJunction(str(root / "a" / "b" / "c"), str(root / "k"))
    spec = dict({"path": str(root), "table_name": "ta", "options": options}, **({"max_depth": max_depth}
                                                                                if max_depth is not None else {}))
    w = _watcher(tmp_path, monkeypatch, [spec])
    (source_id, target), = w.external_targets.items()
    held = target["spec"]
    dispatched, said = [], []
    monkeypatch.setattr(IngestionHandler, "_handle_event", lambda self, path: dispatched.append(path))
    monkeypatch.setattr(IngestionHandler, "already_checked", lambda self, entries: Checked())
    real = w._external_pages

    def pages(sid, target, why, tick, *rest):
        yield from real(sid, target, why, tick, *rest)
        said.append(dict(why))

    monkeypatch.setattr(w, "_external_pages", pages)
    w.sweep_external_sources()
    # the whole judgement, each file of the board: taken, or its reason
    whole = {}
    for top, _dirs, names in os.walk(str(root)):
        for name in names:
            path = os.path.abspath(os.path.join(top, name))
            rel = os.path.relpath(path, str(root)).replace(os.sep, "/")
            whole[path] = None if target["event_handler"].accepted_path(path) else (
                why_not_taken(held, path, rel) or "outside the root")
    assert sorted(dispatched) == sorted(path for path, why in whole.items() if why is None)
    assert dispatched and len(whole) > len(dispatched), "CANARY: taken and not taken"
    outside = sum(1 for why in whole.values() if why == "outside the root")
    assert said[-1]["outside the root"] == outside
    assert outside == ((2 if max_depth is not None else 1) if os.name == "nt" else 0), "CANARY: the junctions"


def test_an_unchanged_folder_is_not_listed_until_every_nth_sweep(tmp_path, monkeypatch):
    root = tmp_path / "share"
    for w in range(3):
        for k in range(2):
            _write(str(root / ("W%d" % w) / ("K%d" % k) / "voids.json"))
            _write(str(root / ("W%d" % w) / ("K%d" % k) / "img.png"))
    spec = {"path": str(root), "table_name": "ta", "options": {"filename": "voids.json"}}
    w = _watcher(tmp_path, monkeypatch, [spec], external_full_walk_every=3)
    monkeypatch.setattr(IngestionHandler, "_handle_event", lambda self, path: None)
    monkeypatch.setattr(IngestionHandler, "already_checked", lambda self, entries: Checked())
    (source_id, _target), = w.external_targets.items()
    looked = []
    real = w._external_pages

    def pages(sid, target, why, said, *rest):
        yield from real(sid, target, why, said, *rest)
        looked.append((why["looked"], why["folders unchanged"]))

    monkeypatch.setattr(w, "_external_pages", pages)
    w.sweep_external_sources()
    assert looked[-1] == (12, 0)                                   # sweep 0: all, both files of 6 folders
    w.sweep_external_sources()
    assert looked[-1] == (0, 10)                                   # sweep 1: root, 3 wafers, 6 works unchanged
    _write(str(root / "W1" / "K0" / "new.png"))                    # a new file moves W1/K0
    _write(str(root / "W2" / "K1" / "voids.json"), "written again in place")
    w.sweep_external_sources()
    assert looked[-1] == (3, 9)                                    # sweep 2: W1/K0 listed; W2/K1 not
    w.sweep_external_sources()
    assert looked[-1] == (13, 0)                                   # sweep 3: all again
    w.sweep_external_sources(walk_all=True)
    assert looked[-1] == (13, 0)                                   # files just unchecked: all, whatever the turn
    w.sweep_external_sources()
    assert looked[-1] == (0, 10)                                   # sweep 5: the memory skips again
    w.sweep_external_sources()
    assert looked[-1] == (13, 0)                                   # sweep 6: all - so sweep 7 would skip
    w._retire_external(source_id, "changed")
    w._register_external_sources(directory_watcher.load_global_table_config())
    w.sweep_external_sources()
    assert looked[-1] == (13, 0)                                   # back as a new binding: all


def test_the_sweep_period_is_a_setting():
    assert directory_watcher.sweep_interval_seconds({}) == directory_watcher.PERIODIC_SWEEP_INTERVAL_SECONDS
    assert directory_watcher.sweep_interval_seconds({"sweep_interval_seconds": 900}) == 900
    assert directory_watcher.full_walk_every({}) is None and directory_watcher.full_walk_every(
        {"external_full_walk_every": 6}) == 6
    assert json.dumps(directory_watcher.full_walk_every({"external_full_walk_every": "6"})) == "null"
