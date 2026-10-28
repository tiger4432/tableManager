# -*- coding: utf-8 -*-
"""A file read again keeps the source it was read under (총괄 10-28): a raws file is read again from its archive, and
the record's source - judged «raws» only for a file under raws - came out None, so the checklist row lost «raws»
(0eba61a50 10-20 the record, daafb2214 10-23 the row) and the file page's (table, source) group split. The source a read
is under is one judgement, `_parse_meta_for` (`read_under`); the archive holds only what raws moved there.

    the read                          record · checklist row · the file page's groups
    raws, read again from its archive  «raws» · «raws» · one group
    a row whose source was emptied     back to «raws» at its next re-read
    an external file read again        its root, as before
"""
import asyncio
import os

import pytest

import directory_watcher
import paths
import run_watcher
from database import models
from ingestion import checkpoint, reread
from tests.test_a_failed_external_file_retries_on_its_own_handler import NO_UNIT, env  # noqa: F401
from tests.test_external_source_watcher import _write_voids
from tests.test_files_are_read_again_by_the_watcher import _the_watcher_reads

TABLE = "rt_parts"


def _retry(Session, **params):
    import main

    db = Session()
    try:
        asked = dict(log_id=None, folder=None, preview=False, statuses="SUCCESS", since=None, until=None)
        return asyncio.run(main.retry_failed_file_ingestion(**dict(asked, **params), db=db))
    finally:
        db.close()


def _said(Session, table):
    """(the checklist row's source, the newest record's source, the file page's (table, source) groups)."""
    db = Session()
    try:
        row = db.query(models.FileChecklist).filter_by(table_name=table).one()
        record = (db.query(models.FileIngestionLog).filter_by(table_name=table)
                  .order_by(models.FileIngestionLog.id.desc()).first())
        groups = [(g["table_name"], g["source"]) for g in checkpoint.read_progress(db) if g["table_name"] == table]
        return row.source, record.source, groups
    finally:
        db.close()


@pytest.fixture(name="read_once")
def fixture_read_once(env, monkeypatch):  # noqa: F811
    """parts.csv read once from raws, the watcher's handlers as it starts, the workspace as the server finds it."""
    monkeypatch.setenv("DECOUPLED", "True")
    monkeypatch.setattr(paths, "WORKSPACE_DIR", str(env["workspace"]))
    reread.forget_sources()
    w = directory_watcher.WorkspaceWatcher(str(env["workspace"]))
    w.discover_and_watch()
    monkeypatch.setattr(run_watcher, "workspace_watcher", w)
    raws = w.raws_root_for(TABLE)
    path = os.path.join(raws, "parts.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("part_no,category,stock_qty\nP-1,Cap,5\n")
    w.handlers_by_raw_path[raws].process_with_retry(path, delay=0.01)
    assert _said(env["Session"], TABLE) == ("raws", "raws", [(TABLE, "raws")]), "control: a first read is raws"
    return env


def test_a_raws_file_read_again_from_its_archive_stays_raws(read_once):
    for _press in range(2):
        assert _retry(read_once["Session"])["count"] == 1
        _the_watcher_reads(read_once["Session"])
        assert _said(read_once["Session"], TABLE) == ("raws", "raws", [(TABLE, "raws")])


def test_a_row_whose_source_was_emptied_is_raws_again_at_its_next_reread(read_once):
    db = read_once["Session"]()
    try:
        db.query(models.FileChecklist).update({"source": None})        # as a re-read before this fix left it
        db.commit()
    finally:
        db.close()
    assert _said(read_once["Session"], TABLE)[0] is None, "canary"
    said = _retry(read_once["Session"])
    _the_watcher_reads(read_once["Session"])

    assert (said["count"], said["not_taken"]) == (1, {})
    assert _said(read_once["Session"], TABLE) == ("raws", "raws", [(TABLE, "raws")])


def test_an_external_file_read_again_keeps_its_root(env, monkeypatch):  # noqa: F811
    monkeypatch.setenv("DECOUPLED", "True")
    path = _write_voids(env["external"], body=NO_UNIT)
    w = env["watcher"]({"unit": "um"})
    w.handlers_by_raw_path[w.raws_root_for("void_obs")].process_with_retry(str(path), delay=0.01)
    root = _said(env["Session"], "void_obs")[0]
    assert root and root != "raws", "control: an external read is its root"
    assert _retry(env["Session"])["count"] == 1
    _the_watcher_reads(env["Session"])

    assert _said(env["Session"], "void_obs") == (root, root, [("void_obs", root)])
