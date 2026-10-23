# -*- coding: utf-8 -*-
"""The watcher's start deletes every checklist row the declaration does not take now, whatever its state (소유자
10-22 「그냥 자동으로 선언 안 맞는 리스트 지워」 · 「재기동시」, 10-23 「패턴 안 맞는 거 남아 있는데」; 총괄 53e78f5d0 가).

  state × (source written · empty) × (matched · not matched · outside the root)   only the not-taken deleted
  a raws row · an empty-source row under the table's workspace                     kept (raws takes every file)
  a source switched off · refused by the validation                                its rows left and counted
  a row naming a root moved away                                                    judged by the source it lies under
  a waiting row the retry poller claims meanwhile (the cleanup has its own thread)  left - the poller's
Only the checklist: its marks go with it, nothing else is touched. Read a page at a time - any page size, one answer.
"""
import json
import logging
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import directory_watcher
import paths
import run_watcher
from database import crud, models
from database.database import Base
from ingestion import reread

TABLES = {"ta": {"business_key": "lot", "column_types": {"lot": "string", "val": "string"}}}
STATES = ("SUCCESS", "FAILED", "PENDING_RETRY")


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(crud, "TABLE_CONFIG", dict(crud.TABLE_CONFIG, **TABLES))
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: TABLES)
    monkeypatch.setattr(run_watcher, "SessionLocal", Session)
    settings = tmp_path / "ingestion_settings.json"
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(settings))
    workspace = tmp_path / "ingestion_workspace"
    monkeypatch.setattr(paths, "WORKSPACE_DIR", str(workspace))
    share = tmp_path / "share"
    for folder in ("on", "off", "bad", "old", "elsewhere"):
        (share / folder).mkdir(parents=True)
    (workspace / "ta" / "archives").mkdir(parents=True)
    settings.write_text(json.dumps({"external_sources": [
        {"path": str(share / "on"), "table_name": "ta", "options": {"glob": ["*.csv"]}},
        {"path": str(share / "off"), "table_name": "ta", "enabled": False, "options": {"glob": ["*.csv"]}},
        {"path": str(share / "bad"), "table_name": "ta", "parser": "no_such_parser"}]}), encoding="utf-8")
    reread.forget_sources()
    yield {"Session": Session, "share": share, "workspace": workspace}
    reread.forget_sources()
    Base.metadata.drop_all(bind=engine)


def _seed(env):
    """{name: (source, path, expected)} - expected None kept, else the word it is deleted or left by."""
    share, ws = env["share"], env["workspace"]
    on = str(share / "on")
    rows = {}
    for state in STATES:
        for source, tag in ((on, "s"), (None, "n")):
            rows[f"{tag}-{state}-match.csv"] = (state, source, share / "on" / "x" / f"{tag}-{state}-match.csv", None)
            rows[f"{tag}-{state}-nomatch.dat"] = (state, source, share / "on" / f"{tag}-{state}-nomatch.dat",
                                                  "name not matched")
            rows[f"{tag}-{state}-out.csv"] = (state, source, share / "elsewhere" / f"{tag}-{state}-out.csv",
                                              "outside the root")
    rows.update({
        "raws-anywhere.csv": ("SUCCESS", "raws", share / "elsewhere" / "raws-anywhere.csv", None),
        "ws-archived.csv": ("SUCCESS", None, ws / "ta" / "archives" / "ws-archived.csv", None),
        "off-named.csv": ("SUCCESS", str(share / "off"), share / "off" / "off-named.csv", reread.SOURCE_OFF),
        "off-empty.csv": ("FAILED", None, share / "off" / "off-empty.csv", reread.SOURCE_OFF),
        "bad-named.csv": ("SUCCESS", str(share / "bad"), share / "bad" / "bad-named.csv", reread.SOURCE_REFUSED),
        "moved-match.csv": ("SUCCESS", str(share / "old"), share / "on" / "moved-match.csv", None),
        "moved-nomatch.dat": ("SUCCESS", str(share / "old"), share / "on" / "moved-nomatch.dat", "name not matched"),
        "moved-out.csv": ("FAILED", str(share / "old"), share / "elsewhere" / "moved-out.csv", "source not declared"),
    })
    db = env["Session"]()
    try:
        for name, (state, source, path, _why) in rows.items():
            row = models.FileIngestionLog(filename=name, filepath=str(path), table_name="ta", status=state,
                                          source=source)
            db.add(row)
            db.flush()
            if state == "PENDING_RETRY":
                db.add(models.FileRereadMark(log_id=row.id, status_before="FAILED", folder=None))
        db.commit()
    finally:
        db.close()
    return {name: why for name, (_state, _source, _path, why) in rows.items()}


@pytest.mark.parametrize("page", [3, reread.START_PAGE])
def test_the_start_deletes_what_the_declaration_does_not_take_and_leaves_the_rest(env, page, monkeypatch):
    expected = _seed(env)
    monkeypatch.setattr(reread, "START_PAGE", page)
    monkeypatch.setattr(reread.delete_not_taken, "__defaults__", (page,))
    db = env["Session"]()
    try:
        said = reread.delete_not_taken(db)
        left = {log.filename for log in db.query(models.FileIngestionLog)}
        marked = {mark.log_id for mark in db.query(models.FileRereadMark)}
        ids = {log.id for log in db.query(models.FileIngestionLog)}
    finally:
        db.close()
    gone = {name for name, why in expected.items() if why is not None and why not in reread.KEPT_AT_START}
    assert gone and left == set(expected) - gone
    assert marked <= ids and marked, "the deleted rows' marks went with them, the kept ones stayed"
    count = {}
    for why in (why for name, why in expected.items() if name in gone):
        count[why] = count.get(why, 0) + 1
    assert said == [("ta", dict(sorted(count.items())),
                     {reread.SOURCE_OFF: 2, reread.SOURCE_REFUSED: 1})]
    assert count == {"name not matched": 7, "outside the root": 6, "source not declared": 1}


def test_the_start_line_says_what_was_deleted_and_what_was_left_by_why(env, caplog):
    _seed(env)
    with caplog.at_level(logging.INFO):
        run_watcher.clean_the_checklist()
    lines = [r.getMessage() for r in caplog.records if "checklist" in r.getMessage()]
    assert lines[:3] == [
        "[Watcher] checklist cleanup started - rows the declaration does not take now are deleted",
        "[Watcher] ta: 14 checklist row(s) the declaration does not take - deleted "
        "(name not matched 7 · outside the root 6 · source not declared 1)",
        "[Watcher] ta: 3 checklist row(s) of a source switched off or refused - left for their source "
        "(source refused 1 · source switched off 2)"]
    assert len(lines) == 4 and lines[3].startswith("[Watcher] checklist cleanup done in ") and lines[3].endswith(
        " s - 14 deleted · 3 left for their source")


def test_a_waiting_row_the_poller_claims_meanwhile_is_not_deleted(env, monkeypatch):
    """The cleanup runs beside the retry poller: a not-taken waiting row claimed between its page's read and its
    delete (PENDING_RETRY -> PENDING) is the poller's - left; the rest of the page goes as judged."""
    _seed(env)
    claimed, judge = "n-PENDING_RETRY-nomatch.dat", reread.not_taken_why

    def claim_then_judge(row, tables):
        if row.filename == claimed:
            other = env["Session"]()
            try:
                other.query(models.FileIngestionLog).filter(models.FileIngestionLog.filename == claimed).update(
                    {"status": "PENDING"}, synchronize_session=False)
                other.commit()
            finally:
                other.close()
        return judge(row, tables)

    monkeypatch.setattr(reread, "not_taken_why", claim_then_judge)
    db = env["Session"]()
    try:
        reread.delete_not_taken(db)
        left = {log.filename: log.status for log in db.query(models.FileIngestionLog)}
    finally:
        db.close()
    assert left.get(claimed) == "PENDING"
    assert "s-PENDING_RETRY-nomatch.dat" not in left and "n-FAILED-nomatch.dat" not in left


def test_a_bulk_retry_judges_an_empty_source_row_by_where_it_lies(env):
    _seed(env)
    db = env["Session"]()
    try:
        picked = [(log, None) for log in db.query(models.FileIngestionLog).filter(
            models.FileIngestionLog.source.is_(None))]
        kept, not_taken, _names = reread.taken_now(picked)
    finally:
        db.close()
    assert sorted(log.filename for log, _rel in kept) == [
        "n-FAILED-match.csv", "n-PENDING_RETRY-match.csv", "n-SUCCESS-match.csv", "ws-archived.csv"]
    assert not_taken == {"name not matched": 3, "outside the root": 3, reread.SOURCE_OFF: 1}
