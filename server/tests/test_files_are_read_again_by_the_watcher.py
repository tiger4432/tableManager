# -*- coding: utf-8 -*-
"""총괄 a4d135a06 (소유자 10-09 「파일 다시 읽기는 그냥 안 돎」 · 「알아서 해」): a re-read is the retry door
that already runs in production, widened - POST /admin/file-ingestion/retry-failed with `statuses`
(FAILED when not given) and `since`/`until` marks the files PENDING_RETRY in the request, and the
watcher's poller reads each on its table's handler, where the file lies, with today's parser.
⚰️ The retroactive «Re-read files» (976defaac) is retired - no run, no operations gate, no wait.

The watcher's part is played by its own code - `run_watcher.pending_retries` then `retry_one`, as
`poll_pending_retries` does.

  files that went in, statuses=SUCCESS    all marked · the count the preview said
  no statuses                             today's answer: failed files only
  the operations gate closed              marked all the same
  the watcher reads one                   its handler's file-processed callback, once - the toast
  a file that went in, a column declared  read again from its archive: the new value
  an external file, its options changed   read on the watcher's handler: external: name
  the folder · a file twice · a gone file A never takes AB · read once · not handed
  since · a word that is no state         the older row left · refused by name
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import directory_watcher
import run_watcher
from admin import retroactive
from conftest import retire_dynamic_model
from database import crud, models
from tests.test_a_failed_external_file_retries_on_its_own_handler import (  # noqa: F401
    NO_UNIT, TABLES, _cells, env)
from tests.test_external_source_watcher import _write_voids


@pytest.fixture(autouse=True)
def _decoupled(monkeypatch):
    monkeypatch.setenv("DECOUPLED", "True")             # the watcher is its own process, as in production


def _retry(Session, **params):
    import main

    db = Session()
    try:
        asked = dict(log_id=None, folder=None, preview=False, statuses=None, since=None, until=None)
        return asyncio.run(main.retry_failed_file_ingestion(**dict(asked, **params), db=db))
    finally:
        db.close()


def _the_watcher_reads(Session):
    """One step of the watcher's poller - its own two functions."""
    db = Session()
    try:
        for log in run_watcher.pending_retries(db):
            log.status = "PENDING"
            db.commit()
            run_watcher.retry_one(db, log)
    finally:
        db.close()


def _states(Session):
    db = Session()
    try:
        return {log.filename: log.status for log in db.query(models.FileIngestionLog).all()}
    finally:
        db.close()


def _add_logs(Session, paths, status="SUCCESS", table="rt_parts", created_at=None):
    db = Session()
    try:
        for path in paths:
            db.add(models.FileIngestionLog(filename=os.path.basename(str(path)), filepath=str(path),
                                           table_name=table, status=status,
                                           **({"created_at": created_at} if created_at else {})))
        db.commit()
    finally:
        db.close()


def _files(tmp_path, *names):
    out = []
    for name in names:
        path = tmp_path / name
        path.write_text("part_no,category,stock_qty\nP-%s,Cap,1\n" % name[0], encoding="utf-8")
        out.append(path)
    return out


def test_files_that_went_in_are_marked_in_the_request_as_many_as_the_preview_said(env, tmp_path):
    _add_logs(env["Session"], _files(tmp_path, "a.csv", "b.csv", "c.csv"))
    preview = _retry(env["Session"], statuses="SUCCESS", preview=True)
    done = _retry(env["Session"], statuses="SUCCESS")
    assert (preview["status"], preview["count"], preview["by_state"]) == ("preview", 3, {"SUCCESS": 3})
    assert (done["count"], done["message"]) == (3, "3 file(s) handed to the watcher")
    assert set(_states(env["Session"]).values()) == {"PENDING_RETRY"}


def test_with_no_statuses_it_is_todays_answer_failed_files_only(env, tmp_path):
    went_in, failed = _files(tmp_path, "a.csv", "b.csv")
    _add_logs(env["Session"], [went_in])
    _add_logs(env["Session"], [failed, tmp_path / "gone.csv"], status="FAILED")
    done = _retry(env["Session"])
    assert (done["count"], done["missing"]) == (2, 0), "a failed file is retried even when it is gone"
    assert _states(env["Session"]) == {"a.csv": "SUCCESS", "b.csv": "PENDING_RETRY", "gone.csv": "PENDING_RETRY"}


def test_a_closed_operations_gate_does_not_hold_it(env, tmp_path, monkeypatch):
    db = env["Session"]()
    db.add(models.RetroactiveRun(run_id="a-long-replay", op="chain_replay", params="{}",
                                 state=retroactive.RUN_RUNNING, runner="scheduler/h/42",
                                 started_at=datetime.now(timezone.utc)))
    db.commit()
    monkeypatch.setattr("utils.heartbeat.read_all", lambda *a, **k: {"scheduler": {"pid": 42, "stale": False}})
    assert "a-long-replay" in (retroactive.gate_refusal(db) or ""), "canary: the gate is closed"
    db.close()
    _add_logs(env["Session"], _files(tmp_path, "a.csv"))
    assert _retry(env["Session"], statuses="SUCCESS")["count"] == 1
    assert _states(env["Session"]) == {"a.csv": "PENDING_RETRY"}


def test_the_watcher_reads_it_and_says_so_once_as_any_file_it_reads(env, monkeypatch):
    said = []
    monkeypatch.setattr(run_watcher, "trigger_ws_file_processed",
                        lambda table, filename, status, error=None: said.append((table, filename, status)))
    w = directory_watcher.WorkspaceWatcher(str(env["workspace"]),
                                           on_file_processed_callback=run_watcher.trigger_ws_file_processed)
    w.discover_and_watch()
    monkeypatch.setattr(run_watcher, "workspace_watcher", w)
    raws = w.raws_root_for("rt_parts")
    path = os.path.join(raws, "parts.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("part_no,category,stock_qty\nP-1,Cap,5\n")
    w.handlers_by_raw_path[raws].process_with_retry(path, delay=0.01)
    said.clear()

    _retry(env["Session"], statuses="SUCCESS")
    _the_watcher_reads(env["Session"])

    assert said == [("rt_parts", "parts.csv", "SUCCESS")]
    assert _states(env["Session"]) == {"parts.csv": "SUCCESS"}


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

    assert _retry(env["Session"], statuses="SUCCESS")["count"] == 1
    _the_watcher_reads(env["Session"])

    rows, _sources = _cells(env["Session"], "rt_parts")
    assert [(r.part_no, r.note) for r in rows] == [("P-1", "hello")], "the same bytes, read again"
    assert _states(env["Session"]) == {"parts.csv": "SUCCESS"}


def test_an_external_file_is_read_again_on_the_watchers_handler_with_its_new_options(env):
    path = _write_voids(env["external"], body=NO_UNIT)
    first = env["watcher"]({"unit": "um"})
    first.handlers_by_raw_path[first.raws_root_for("void_obs")].process_with_retry(str(path), delay=0.01)
    assert [r.unit for r in _cells(env["Session"], "void_obs")[0]] == ["um"], "canary: it went in"

    env["watcher"]({"unit": "mm"})                     # the operator changes the source's options
    assert _retry(env["Session"], statuses="SUCCESS")["count"] == 1
    _the_watcher_reads(env["Session"])

    rows, sources = _cells(env["Session"], "void_obs")
    assert [(r.base_wafer_id, r.unit) for r in rows] == [("WF-001", "mm")]
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
    said = _retry(env["Session"], statuses="SUCCESS", folder=str(base / "A"), preview=True)
    assert (said["count"], said["by_folder"]) == (2, {".": 1, "x": 1})


def test_a_file_read_twice_goes_once_and_a_gone_file_is_not_handed(env, tmp_path):
    (here,) = _files(tmp_path, "here.csv")
    _add_logs(env["Session"], [here, here, tmp_path / "gone.csv"])
    said = _retry(env["Session"], statuses="SUCCESS", preview=True)
    assert (said["count"], said["missing"], said["missing_files"]) == (1, 1, ["gone.csv"])
    done = _retry(env["Session"], statuses="SUCCESS")
    assert (done["count"], done["missing"]) == (1, 1)
    db = env["Session"]()
    try:
        states = sorted((log.filename, log.status) for log in db.query(models.FileIngestionLog))
    finally:
        db.close()
    assert states == [("gone.csv", "SUCCESS"), ("here.csv", "PENDING_RETRY"), ("here.csv", "SUCCESS")]


def test_since_leaves_the_older_row_and_a_word_that_is_no_state_is_refused(env, tmp_path):
    now = datetime.now()
    old, new = _files(tmp_path, "old.csv", "new.csv")
    _add_logs(env["Session"], [old], created_at=now - timedelta(days=3))
    _add_logs(env["Session"], [new], created_at=now)
    since = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    assert _retry(env["Session"], statuses="SUCCESS", since=since)["count"] == 1
    assert _states(env["Session"]) == {"old.csv": "SUCCESS", "new.csv": "PENDING_RETRY"}
    with pytest.raises(HTTPException) as refused:
        _retry(env["Session"], statuses="DONE")
    assert refused.value.status_code == 400 and "DONE" in refused.value.detail
