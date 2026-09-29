# -*- coding: utf-8 -*-
"""A failed external file retries on the watcher's own handler for its table (총괄 fab40ed69 ①,
소유자 09-29 「외부 경로 파일 인제션에서 에러난거는 일단 놔두고 나중에 리플레이로 돌리게」 -> ㄱ).

🔴 THE RETRY POLLER BUILT A NEW HANDLER, which had no external source registered - so an
external file's retry read without the folder's wafer and work time, the source's parser
options, and the `external:<parser>:<path>` cell source name. It now runs on the handler the
watcher registered the external source on; a managed raws/ file retries as it did.
"""
import json
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import directory_watcher
import run_watcher
from database import crud, models
from database.database import Base
from directory_watcher import WorkspaceWatcher
from tests.test_external_source_watcher import VOID_INFO, _write_voids

PARTS = {"business_key": "part_no", "column_types": {
    "part_no": "string", "category": "string", "stock_qty": "number"}}
TABLES = {"void_obs": VOID_INFO, "rt_parts": PARTS}
NO_UNIT = {"voids": [{"base_x": 3, "base_y": 4, "gate": 2, "inchip_x": 10.5,
                      "inchip_y": 20.25, "radius_x": 1.5, "radius_y": 2.5}]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    monkeypatch.setattr(crud, "TABLE_CONFIG", dict(crud.TABLE_CONFIG, **TABLES))
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    models.ensure_ingestion_checkpoint_table(engine)
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: TABLES)
    monkeypatch.setattr(directory_watcher, "SessionLocal", Session)
    settings = tmp_path / "ingestion_settings.json"
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(settings))
    monkeypatch.setattr(run_watcher, "trigger_ws_file_processed", lambda *a, **k: None)
    workspace = tmp_path / "ingestion_workspace"
    workspace.mkdir()
    external = tmp_path / "external" / "void"

    def watcher(options):
        """The watcher as it starts: its handlers, and the external source on void_obs."""
        settings.write_text(json.dumps({"external_sources": [{
            "path": str(external), "table_name": "void_obs", "parser": "voids_json",
            "recursive": True, "options": dict({"filename": "voids.json"}, **options)}]}),
            encoding="utf-8")
        w = WorkspaceWatcher(str(workspace))
        w.discover_and_watch()
        monkeypatch.setattr(run_watcher, "workspace_watcher", w)
        return w

    yield {"Session": Session, "watcher": watcher, "external": external, "workspace": workspace}
    Base.metadata.drop_all(bind=engine)


def _log(Session, filename):
    db = Session()
    try:
        return db.query(models.FileIngestionLog).filter_by(filename=filename).one().id
    finally:
        db.close()


def _retry(Session, log_id):
    """As the poller does it: claim the row, then `retry_one`."""
    db = Session()
    try:
        log = db.get(models.FileIngestionLog, log_id)
        log.status = "PENDING"
        db.commit()
        run_watcher.retry_one(db, log)
        return log.status, log.error_message
    finally:
        db.close()


def _cells(Session, table):
    db = Session()
    try:
        rows = db.query(models.DYNAMIC_TABLES[table]).all()
        sources = {s.source_name for s in db.query(models.CellSource).all()}
        return rows, sources
    finally:
        db.close()


def test_an_external_file_fixed_by_its_options_goes_in_on_retry_with_its_folder(env):
    path = _write_voids(env["external"], body=NO_UNIT)
    first = env["watcher"]({})
    handler = first.handlers_by_raw_path[first.raws_root_for("void_obs")]
    handler.process_with_retry(str(path), delay=0.01)
    log_id = _log(env["Session"], "voids.json")
    db = env["Session"]()
    assert db.get(models.FileIngestionLog, log_id).status == "FAILED"
    db.close()

    env["watcher"]({"unit": "um"})           # the operator fixes the source, the watcher restarts
    status, why = _retry(env["Session"], log_id)

    assert status == "SUCCESS", why
    rows, sources = _cells(env["Session"], "void_obs")
    assert [(r.base_wafer_id, r.unit) for r in rows] == [("WF-001", "um")], "the folder's wafer"
    assert "external:voids_json:%s" % os.path.realpath(str(path)) in sources
    assert path.exists(), "an external file is never moved"


def test_a_managed_raws_file_retries_as_it_did(env):
    w = env["watcher"]({})
    raws = w.raws_root_for("rt_parts")
    bad = os.path.join(raws, "parts.csv")
    with open(bad, "w", encoding="utf-8", newline="") as f:
        f.write("part_no,category,stock_qty\nP-1,Cap,abc\n")
    w.handlers_by_raw_path[raws].process_with_retry(bad, delay=0.01)
    log_id = _log(env["Session"], "parts.csv")
    db = env["Session"]()
    where = db.get(models.FileIngestionLog, log_id).filepath
    db.close()
    with open(where, "w", encoding="utf-8", newline="") as f:
        f.write("part_no,category,stock_qty\nP-1,Cap,5\n")

    status, why = _retry(env["Session"], log_id)

    assert status == "SUCCESS", why
    rows, _sources = _cells(env["Session"], "rt_parts")
    assert [(r.part_no, r.stock_qty) for r in rows] == [("P-1", 5)]
    assert os.path.exists(where), "a retry reads the file where it lies and moves nothing"


def test_a_table_the_watcher_does_not_run_fails_by_name(env):
    env["watcher"]({})
    db = env["Session"]()
    log = models.FileIngestionLog(filename="x.csv", filepath="C:/nowhere/x.csv",
                                  table_name="no_such_table", status="PENDING_RETRY")
    db.add(log)
    db.commit()
    log_id = log.id
    db.close()

    status, why = _retry(env["Session"], log_id)

    assert status == "FAILED" and "runs no handler for table 'no_such_table'" in why


def test_nothing_is_claimed_before_the_watcher_holds_its_handlers(env, monkeypatch):
    db = env["Session"]()
    db.add(models.FileIngestionLog(filename="y.csv", filepath="C:/y.csv", table_name="rt_parts",
                                   status="PENDING_RETRY"))
    db.commit()
    monkeypatch.setattr(run_watcher, "workspace_watcher", None)
    assert run_watcher.pending_retries(db) == []
    env["watcher"]({})
    assert [log.filename for log in run_watcher.pending_retries(db)] == ["y.csv"]
    db.close()
