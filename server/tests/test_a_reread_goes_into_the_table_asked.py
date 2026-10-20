# -*- coding: utf-8 -*-
"""A re-read into the table asked (총괄 10-20, 소유자 「어드민 파일 리트라이는 돌았던 테이블로만 도네」).

`retry-failed?folder=…&table=B` picks the files under the folder that B takes - from the disk, so a file B has no
row for is picked - and stands B's rows for them; the watcher's poller reads them on B's handler. The table that
read them before is not touched. Taken is the handler's own judgement (`directory_watcher.source_taking`), so the
preview's count is the count handed over and the count read.
"""
import asyncio
import json
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import directory_watcher
import main
import paths
import run_watcher
from database import crud, models
from database.database import Base
from directory_watcher import WorkspaceWatcher
from ingestion import reread
from tests.test_external_source_watcher import VOID_INFO, _write_voids

with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "sample",
                       "table_config.json.sample"), encoding="utf-8") as _sample:
    RUN = json.load(_sample)["inspection_run"]
#: its times as text - SQLite's DateTime takes no text, PostgreSQL's does; the read is the handler's either way
RUN = dict(RUN, column_types={k: "string" if t == "datetime" else t for k, t in RUN["column_types"].items()})
A, B = "void_obs", "inspection_run"
TABLES = {A: VOID_INFO, B: RUN}


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    monkeypatch.setattr(crud, "TABLE_CONFIG", dict(crud.TABLE_CONFIG, **TABLES))
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    models.ensure_ingestion_checkpoint_table(engine)
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: TABLES)
    monkeypatch.setattr(directory_watcher, "SessionLocal", Session)
    monkeypatch.setattr(run_watcher, "trigger_ws_file_processed", lambda *a, **k: None)
    monkeypatch.setenv("DECOUPLED", "True")
    settings = tmp_path / "ingestion_settings.json"
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(settings))
    workspace = tmp_path / "ingestion_workspace"
    workspace.mkdir()
    monkeypatch.setattr(paths, "WORKSPACE_DIR", str(workspace))
    share = tmp_path / "share"
    root = share / "void"
    # one folder, two tables reading it - A and B both declare it
    settings.write_text(json.dumps({"external_sources": [
        {"path": str(root), "table_name": table, "parser": "voids_json", "recursive": True,
         "options": {"filename": "voids.json"}} for table in (A, B)]}), encoding="utf-8")
    voids = _write_voids(root)
    (root / "WF-001" / "notes.txt").write_text("not a voids file", encoding="utf-8")   # under the root, not matched
    (share / "elsewhere").mkdir()
    (share / "elsewhere" / "voids.json").write_text("{}", encoding="utf-8")            # outside every source root
    w = WorkspaceWatcher(str(workspace))
    w.discover_and_watch()
    monkeypatch.setattr(run_watcher, "workspace_watcher", w)
    # A reads the file - B has no row for it
    w.handlers_by_raw_path[w.raws_root_for(A)].process_with_retry(str(voids), delay=0.01)
    yield {"Session": Session, "share": share, "root": root, "voids": voids}
    Base.metadata.drop_all(bind=engine)


def _ask(Session, **params):
    db = Session()
    try:
        return asyncio.run(main.retry_failed_file_ingestion(db=db, **params))
    finally:
        db.close()


def _logs(Session):
    db = Session()
    try:
        return sorted((log.table_name, log.filename, log.status)
                      for log in db.query(models.FileIngestionLog).all())
    finally:
        db.close()


def _poll(Session):
    """As the poller does it: each waiting row claimed, then `retry_one` on its table's handler."""
    db = Session()
    try:
        ran = 0
        for log in run_watcher.pending_retries(db):
            if run_watcher.claim_retry(db, log):
                run_watcher.retry_one(db, log)
                ran += 1
        return ran
    finally:
        db.close()


def _rows(Session, table):
    db = Session()
    try:
        return db.query(models.DYNAMIC_TABLES[table]).count()
    finally:
        db.close()


def test_a_file_only_a_read_goes_into_b_and_a_is_not_touched(env):
    S = env["Session"]
    before_a, a_rows = _logs(S), _rows(S, A)
    assert before_a == [(A, "voids.json", "SUCCESS")] and a_rows == 1 and _rows(S, B) == 0

    preview = _ask(S, folder=str(env["share"]), table=B, preview=True)
    assert _logs(S) == before_a, "a preview writes nothing"
    assert (preview["count"], preview["by_state"], preview["table"]) == (1, {"NEW": 1}, B)
    assert preview["not_taken"] == {reread.NOT_MATCHED: 1, reread.OUTSIDE_SOURCES: 1}
    assert preview["walked"] == 3

    handed = _ask(S, folder=str(env["share"]), table=B)
    assert handed["count"] == preview["count"]
    assert _logs(S) == sorted([(A, "voids.json", "SUCCESS"), (B, "voids.json", "PENDING_RETRY")])

    assert _poll(S) == preview["count"]
    assert _logs(S) == sorted([(A, "voids.json", "SUCCESS"), (B, "voids.json", "SUCCESS")])
    assert _rows(S, B) >= 1, "read into B"
    assert _rows(S, A) == a_rows, "A's rows are not read again"


def test_a_file_b_already_has_a_row_for_reuses_it(env):
    S = env["Session"]
    _ask(S, folder=str(env["root"]), table=B)
    _poll(S)

    again = _ask(S, folder=str(env["root"]), table=B, preview=True)

    assert (again["count"], again["by_state"]) == (1, {"SUCCESS": 1})
    _ask(S, folder=str(env["root"]), table=B)
    assert [row for row in _logs(S) if row[0] == B] == [(B, "voids.json", "PENDING_RETRY")], "one B row, reused"


def test_cancel_removes_the_row_the_reread_stood_and_leaves_a(env):
    S = env["Session"]
    _ask(S, folder=str(env["root"]), table=B)
    db = S()
    try:
        said = reread.cancel_reread(db, folder=str(env["root"]), apply=True)
    finally:
        db.close()

    assert (said["count"], said["removed"]) == (0, 1)
    assert _logs(S) == [(A, "voids.json", "SUCCESS")]


def test_into_a_table_needs_the_watcher_process(env, monkeypatch):
    monkeypatch.setenv("DECOUPLED", "False")
    with pytest.raises(HTTPException) as refused:
        _ask(env["Session"], folder=str(env["root"]), table=B, preview=True)
    assert (refused.value.status_code, refused.value.detail) == (409, "a re-read into a table needs the watcher process")


def test_a_folder_too_big_to_walk_is_refused_by_name(env, monkeypatch):
    monkeypatch.setattr(reread, "WALK_MAX_ENTRIES", 2)
    with pytest.raises(HTTPException) as refused:
        _ask(env["Session"], folder=str(env["share"]), table=B, preview=True)
    assert refused.value.status_code == 409 and "narrow the folder" in refused.value.detail
    assert _logs(env["Session"]) == [(A, "voids.json", "SUCCESS")]


def test_without_a_table_the_door_is_as_it_was(env):
    body = _ask(env["Session"], folder=str(env["share"]), statuses="SUCCESS", preview=True)

    assert (body["count"], body["by_state"]) == (1, {"SUCCESS": 1}) and "table" not in body
