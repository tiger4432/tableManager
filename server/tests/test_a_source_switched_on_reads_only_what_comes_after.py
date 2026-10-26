"""소유자 10-26 «외부 저장소 활성화하였을 때 그 시점 이후로 새로 들어오는 거만 자동으로 받고 기존 거는 수동 소급»: a source
switched on (enabled false -> true) is read automatically only for files modified at/after that moment; one already on
when the times were first kept is not cut; a restart does not stamp again; switched off, its time is let go."""
import logging
import os
import sys
import time

import pytest

test_dir = os.path.dirname(os.path.abspath(__file__))
for path in (os.path.abspath(os.path.join(test_dir, "..")), os.path.abspath(os.path.join(test_dir, "..", "parsers"))):
    if path not in sys.path:
        sys.path.insert(0, path)

import directory_watcher
import ingestion.checkpoint
from database import crud
from directory_watcher import IngestionHandler, WorkspaceWatcher
from ingestion import reread

INFO = {"business_key": "void_uid", "column_types": {"void_uid": "string"}, "display_columns": ["void_uid"]}
TABLES = {"void_obs": INFO}


@pytest.fixture(autouse=True)
def one_table(monkeypatch):
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: TABLES)
    monkeypatch.setattr(crud, "TABLE_CONFIG", TABLES)


def _file(root, n, age):
    path = root / f"WF-{n:03d}" / "WORK_20260817_031405" / "voids.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    os.utime(path, (time.time() + age, time.time() + age))
    return str(path)


def test_only_files_after_the_switch_on_are_read_by_themselves(tmp_path, monkeypatch, caplog):
    workspace, on, off = tmp_path / "ingestion_workspace", tmp_path / "on", tmp_path / "off"
    workspace.mkdir()
    old_on = [_file(on, n, -3600) for n in range(2)]
    old_off = [_file(off, n, -3600) for n in range(3)]
    sources = [{"path": str(on), "table_name": "void_obs", "parser": "voids_json"},
               {"path": str(off), "table_name": "void_obs", "parser": "voids_json", "enabled": False}]
    monkeypatch.setattr(directory_watcher, "load_ingestion_settings", lambda: {"external_sources": sources})

    read = set()                    # the checklist: a read path is checked; every other one is new

    def checked(db, table, entries, words=None):
        words.update({p: ingestion.checkpoint.WHY_NEW for p, _s in entries if p not in read})
        return {p: "SUCCESS" for p, _s in entries if p in read}

    monkeypatch.setattr(ingestion.checkpoint, "checked", checked)
    monkeypatch.setattr(IngestionHandler, "_stamp_read_files", lambda self, db, t, entries: True)
    monkeypatch.setattr(IngestionHandler, "_handle_event", lambda self, path: read.add(os.path.abspath(path)))
    state = reread.load_reading_stamps

    # the first start: a source already on is cut from now too (owner 10-26 «기존 저장소고 뭐고 즉시 적용되게»),
    # its old files are left to a hand
    watcher = WorkspaceWatcher(str(workspace))
    watcher.discover_and_watch()
    on_id, off_id = (f"void_obs@{os.path.normcase(os.path.realpath(r))}" for r in (on, off))
    on_cut = state(reread.SWITCHED_ON_FILENAME)[on_id]
    assert on_cut is not None and abs(on_cut - time.time()) < 60
    assert watcher.sweep_external_sources() == 0 and not read & set(old_on)

    # switched on: stamped and said; its old files are left to a hand, counted on the sweep's line
    sources[1]["enabled"] = True
    watcher._ensure_observer_running = lambda: None                 # no events: the sweeps are the reads counted
    watcher.sweep_external_sources_async = lambda ids, reason="": watcher.sweep_external_sources(ids)
    with caplog.at_level(logging.INFO):
        watcher.refresh_external_sources()
    cut = state(reread.SWITCHED_ON_FILENAME)[off_id]
    assert cut is not None and abs(cut - time.time()) < 60
    assert any("External source switched on: " + os.path.realpath(off) in r.message for r in caplog.records)
    assert any(r.message.startswith(f"External source {off_id}: 3 file(s) looked at") and "before switch-on 3"
               in r.message for r in caplog.records)
    assert not read & set(old_off)
    new = [_file(off, 10 + n, 2) for n in range(2)]
    assert watcher.sweep_external_sources() == 2 and read & set(old_off + new) == set(new)

    # the event door asks the same seat: an old file is held, a new one is not
    handler = watcher.external_targets[off_id]["handler"]
    answer = handler.already_checked([(p, ingestion.checkpoint.read_file_stat(p)) for p in (old_off[0], _file(off, 20, 2))])
    assert answer == {old_off[0]} and answer.before_switch_on == {old_off[0]}

    # a restart does not stamp again
    again = WorkspaceWatcher(str(workspace))
    again.discover_and_watch()
    again._ensure_observer_running = lambda: None
    assert state(reread.SWITCHED_ON_FILENAME) == {on_id: on_cut, off_id: cut}
    assert again.sweep_external_sources() == 1 and not read & set(old_off)       # the event's new file, not the old

    # switched off: its time is let go, so the next switch-on stamps anew
    sources[1]["enabled"] = False
    again.refresh_external_sources()
    assert state(reread.SWITCHED_ON_FILENAME) == {on_id: on_cut}
