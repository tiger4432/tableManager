# -*- coding: utf-8 -*-
"""총괄 976defaac (소유자 10-09 「외부 경로 인제션 소급」 · 「아카이브 파일도 재읽기 소급 — 인제션 파서를 바꿀 경우」
-> 「ㄱ」): the retroactive «Re-read files» widens the retry door to files that went in. The rows
picked (table · folder · time · states, one per file) go PENDING_RETRY a page at a time and the
watcher's poller reads each on its table's handler, where the file lies, with today's parser.

The watcher's part is played by its own code: during the run's wait, one poller step -
`run_watcher.pending_retries` then `retry_one`, as `poll_pending_retries` does.

  a file that went in, then a declared column  read again from its archive: the new value
  an external file, its parser's options changed  read on the watcher's handler: external: name
  the folder                                    A never takes AB
  the preview                                   the count the run hands over · a gone file not marked
  a stop                                        the rows not taken get their state back
  a page                                        the next page waits for this one
  no watcher                                    refused before anything is recorded
"""
import json
import os

import pytest

import directory_watcher
import run_watcher
from admin import retroactive
from conftest import retire_dynamic_model
from database import crud, models
from ingestion import reread
from tests.test_a_failed_external_file_retries_on_its_own_handler import (  # noqa: F401
    NO_UNIT, TABLES, _cells, env)
from tests.test_external_source_watcher import _write_voids

OP = retroactive.OPERATIONS["reread_files"]


@pytest.fixture(autouse=True)
def _the_watcher_reads_during_the_wait(env, monkeypatch):
    """A sleep in the run's wait is one step of the watcher's poller - its own two functions. A
    wait that never ends fails here rather than hanging."""
    steps = []

    def poll(_seconds):
        steps.append(1)
        assert len(steps) < 50, "the run kept waiting - nothing took the rows it handed over"
        db = env["Session"]()
        try:
            for log in run_watcher.pending_retries(db):
                log.status = "PENDING"
                db.commit()
                run_watcher.retry_one(db, log)
        finally:
            db.close()
    monkeypatch.setattr(retroactive.time, "sleep", poll)
    monkeypatch.setattr(reread, "watcher_running", lambda: True)


def _states(Session):
    db = Session()
    try:
        return {log.filename: log.status for log in db.query(models.FileIngestionLog).all()}
    finally:
        db.close()


def _run(Session, params, control=None):
    db = Session()
    try:
        return OP["run"](db, retroactive.validate("reread_files", params), lambda *_: None, control)
    finally:
        db.close()


def _count(Session, params):
    db = Session()
    try:
        return OP["count"](db, retroactive.validate("reread_files", params), 1000)
    finally:
        db.close()


def _add_logs(Session, paths, status="SUCCESS", table="rt_parts"):
    db = Session()
    try:
        for path in paths:
            db.add(models.FileIngestionLog(filename=os.path.basename(str(path)), filepath=str(path),
                                           table_name=table, status=status))
        db.commit()
    finally:
        db.close()


def test_a_file_that_went_in_is_read_again_from_its_archive_with_a_column_declared_since(env, monkeypatch):
    w = env["watcher"]({})
    raws = w.raws_root_for("rt_parts")
    path = os.path.join(raws, "parts.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("part_no,category,stock_qty,note\nP-1,Cap,5,hello\n")
    w.handlers_by_raw_path[raws].process_with_retry(path, delay=0.01)
    assert _states(env["Session"]) == {"parts.csv": "SUCCESS"}, "canary: it went in"
    assert not hasattr(_cells(env["Session"], "rt_parts")[0][0], "note"), "canary: note not declared yet"

    declared = dict(TABLES, rt_parts=dict(TABLES["rt_parts"], column_types=dict(
        TABLES["rt_parts"]["column_types"], note="string")))          # the parser's table, changed
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: declared)
    crud.TABLE_CONFIG["rt_parts"] = declared["rt_parts"]
    retire_dynamic_model("rt_parts")
    models.init_dynamic_models({"rt_parts": declared["rt_parts"]})
    models.sync_dynamic_tables_schema(env["Session"].kw["bind"])

    preview = _count(env["Session"], {"table": "rt_parts"})
    done = _run(env["Session"], {"table": "rt_parts"})

    assert (preview["affected"], done["marked"], done["read"]) == (1, 1, 1)
    rows, _sources = _cells(env["Session"], "rt_parts")
    assert [(r.part_no, r.note) for r in rows] == [("P-1", "hello")], "the same bytes, read again"
    assert _states(env["Session"]) == {"parts.csv": "SUCCESS"}


def test_an_external_file_is_read_again_on_the_watchers_handler_with_its_new_options(env):
    path = _write_voids(env["external"], body=NO_UNIT)
    first = env["watcher"]({"unit": "um"})
    first.handlers_by_raw_path[first.raws_root_for("void_obs")].process_with_retry(str(path), delay=0.01)
    assert [r.unit for r in _cells(env["Session"], "void_obs")[0]] == ["um"], "canary: it went in"

    env["watcher"]({"unit": "mm"})                     # the operator changes the source's options
    done = _run(env["Session"], {"table": "void_obs"})

    rows, sources = _cells(env["Session"], "void_obs")
    assert done["read"] == 1 and [(r.base_wafer_id, r.unit) for r in rows] == [("WF-001", "mm")]
    assert "external:voids_json:%s" % os.path.realpath(str(path)) in sources
    assert path.exists(), "an external file is never moved"


def test_a_folder_takes_what_is_under_it_and_never_its_neighbour(env, tmp_path):
    base = tmp_path / "share"
    files = []
    for rel in ("A/x/f1.csv", "A/f2.csv", "AB/h1.csv"):
        path = base.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("part_no\n", encoding="utf-8")
        files.append(path)
    _add_logs(env["Session"], files)
    said = _count(env["Session"], {"table": "rt_parts", "folder": str(base / "A")})
    assert (said["affected"], said["extra"]["folders"]) == (2, {".": 1, "x": 1})


def test_the_preview_counts_what_the_run_hands_over_and_a_gone_file_is_not_handed(env, tmp_path):
    here = tmp_path / "here.csv"
    here.write_text("part_no\n", encoding="utf-8")
    _add_logs(env["Session"], [here, here, tmp_path / "gone.csv"])          # a file read twice · a gone one
    said = _count(env["Session"], {"table": "rt_parts"})
    assert (said["affected"], said["extra"]["missing"]) == (1, 1)
    assert "gone.csv" in said["detail"] and "split a large folder" in said["detail"]
    env["watcher"]({})
    done = _run(env["Session"], {"table": "rt_parts"})
    assert (done["marked"], done["missing"]) == (said["affected"], 1)
    assert _states(env["Session"])["gone.csv"] == "SUCCESS", "a gone file is not handed over"


class _Stop:
    """A run's control: stop at the first look."""
    def __init__(self):
        self.seen = []

    def progress(self, processed, total=None):
        self.seen.append((processed, total))

    def stop_requested(self):
        return True


def test_a_stop_gives_the_rows_not_taken_their_state_back(env, tmp_path, monkeypatch):
    monkeypatch.setattr(retroactive.time, "sleep", lambda _s: None)          # the watcher takes nothing
    paths = []
    for name in ("a.csv", "b.csv"):
        path = tmp_path / name
        path.write_text("part_no\n", encoding="utf-8")
        paths.append(path)
    _add_logs(env["Session"], paths[:1], status="SUCCESS")
    _add_logs(env["Session"], paths[1:], status="FAILED")
    done = _run(env["Session"], {"table": "rt_parts"}, control=_Stop())
    assert (done["stopped"], done["restored"], done["read"]) == (True, 2, 0)
    assert _states(env["Session"]) == {"a.csv": "SUCCESS", "b.csv": "FAILED"}


def test_the_next_page_waits_for_this_one(env, tmp_path, monkeypatch):
    monkeypatch.setattr(retroactive, "REREAD_PAGE_FILES", 1)
    marked_at_once = []
    real = reread.mark_for_reread

    def mark(db, logs, page=reread.MARK_PAGE):
        in_hand = db.query(models.FileIngestionLog).filter(
            models.FileIngestionLog.status.in_(reread.IN_HAND)).count()
        marked_at_once.append(in_hand)
        return real(db, logs, page)
    monkeypatch.setattr(reread, "mark_for_reread", mark)
    paths = []
    for name in ("a.csv", "b.csv"):
        path = tmp_path / name
        path.write_text("part_no,category,stock_qty\nP-%s,Cap,1\n" % name[0], encoding="utf-8")
        paths.append(path)
    env["watcher"]({})
    _add_logs(env["Session"], paths, status="FAILED")
    done = _run(env["Session"], {"table": "rt_parts"})
    assert marked_at_once == [0, 0] and done["read"] == 2


def test_with_no_watcher_running_it_is_refused_before_anything_is_recorded(env, monkeypatch):
    monkeypatch.setattr(reread, "watcher_running", lambda: False)
    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        retroactive.validate("reread_files", {"table": "rt_parts"})
    assert str(refused.value) == retroactive.WATCHER_NOT_RUNNING


def test_a_state_that_is_no_ingestion_state_is_refused_by_name(env):
    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        retroactive.validate("reread_files", {"table": "rt_parts", "statuses": "DONE"})
    assert "DONE" in str(refused.value)
