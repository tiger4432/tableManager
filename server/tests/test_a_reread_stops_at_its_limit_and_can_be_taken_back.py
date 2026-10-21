# -*- coding: utf-8 -*-
"""총괄 10-11 ㄱ (소유자 「다시 읽기 잘못 걸었다가 파일 너무 많아서 서버 뻗었어」): the re-read door gets a safety.

  the limit     more files than reread_max_files -> handed to the watcher all the same, which reads the cap a turn
                (총괄 10-21: a pace); read in the request (not DECOUPLED) -> refused by name, nothing handed
  cancel        rows still waiting go back to the state they had; a row the watcher claimed is not touched
  the folder    narrowed in SQL - the same rows the filesystem judgement picks (boundary · case · separators)"""
import json
import os

import pytest

from database import models
from ingestion import reread

URL = "/admin/file-ingestion/retry-failed"
CANCEL = "/admin/file-ingestion/cancel-reread"


@pytest.fixture
def tree(tmp_path, db_session, monkeypatch):
    monkeypatch.setenv("DECOUPLED", "True")
    settings = tmp_path / "ingestion_settings.json"
    settings.write_text("{}", encoding="utf-8")
    from ingestion import settings as ingestion_settings
    monkeypatch.setattr(ingestion_settings, "INGESTION_SETTINGS_PATH", str(settings))
    base = tmp_path / "share"

    def add(rel, status="FAILED"):
        path = str(base.joinpath(*rel.split("/")))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()                                   # a re-read of a file that went in needs the file
        db_session.add(models.FileIngestionLog(filename=os.path.basename(path), filepath=path,
                                               table_name="t", status=status))
    for rel in ("A/x/f1.csv", "A/x/f2.csv", "A/f3.csv", "B/g1.csv", "AB/h1.csv", "A_1/k1.csv"):
        add(rel)
    add("A/ok.csv", "SUCCESS")
    db_session.commit()
    return {"base": base, "settings": settings}


def _statuses(db_session):
    db_session.expire_all()
    return {log.filename: log.status for log in db_session.query(models.FileIngestionLog).all()}


def test_over_the_limit_the_watcher_gets_them_all_and_reads_the_cap_a_turn(client, db_session, tree, monkeypatch):
    import run_watcher

    tree["settings"].write_text(json.dumps({"reread_max_files": 2}), encoding="utf-8")
    folder = str(tree["base"] / "A")
    preview = client.post(URL, params={"folder": folder, "preview": True}).json()
    assert (preview["count"], preview["limit"]) == (3, 2)
    answer = client.post(URL, params={"folder": folder})
    assert answer.status_code == 200, answer.text
    waiting = {"f1.csv", "f2.csv", "f3.csv"}
    assert {name for name, state in _statuses(db_session).items() if state == "PENDING_RETRY"} == waiting
    monkeypatch.setattr(run_watcher, "workspace_watcher", object())
    db_session.expire_all()
    assert [log.filename for log in run_watcher.pending_retries(db_session)] == ["f1.csv", "f2.csv"], "the cap a turn"


def test_over_the_limit_read_in_the_request_is_refused_by_name_and_hands_nothing(client, db_session, tree,
                                                                                monkeypatch):
    monkeypatch.setenv("DECOUPLED", "False")
    tree["settings"].write_text(json.dumps({"reread_max_files": 2}), encoding="utf-8")
    folder = str(tree["base"] / "A")
    before = _statuses(db_session)
    answer = client.post(URL, params={"folder": folder})
    assert answer.status_code == 409
    assert answer.json()["detail"] == ("3 files - over the limit 2; narrow the folder or raise reread_max_files in "
                                       "ingestion_settings.json")
    assert _statuses(db_session) == before


def test_cancel_puts_the_waiting_rows_back_and_leaves_a_claimed_one(client, db_session, tree):
    folder = str(tree["base"] / "A")
    client.post(URL, params={"folder": folder})
    client.post(URL, params={"folder": folder, "statuses": "SUCCESS"})
    assert sorted(n for n, s in _statuses(db_session).items() if s == "PENDING_RETRY") == [
        "f1.csv", "f2.csv", "f3.csv", "ok.csv"], "CANARY: four handed over"
    claimed = db_session.query(models.FileIngestionLog).filter_by(filename="f1.csv").one()
    claimed.status = "PENDING"                                   # the watcher's claim
    db_session.commit()
    preview = client.post(CANCEL, params={"folder": folder, "preview": True}).json()
    assert (preview["count"], preview["by_state"]) == (3, {"FAILED": 2, "SUCCESS": 1})
    assert client.post(CANCEL, params={"folder": folder}).json()["count"] == 3
    after = _statuses(db_session)
    assert (after["f1.csv"], after["f2.csv"], after["f3.csv"], after["ok.csv"]) == ("PENDING", "FAILED", "FAILED",
                                                                                   "SUCCESS")
    assert db_session.query(models.FileRereadMark).count() == 1, "the claimed row's mark is the one left"


@pytest.mark.parametrize("spelled", ["A", "a", "A/", "A_1"], ids=["as-is", "case", "trailing-separator", "underscore"])
def test_the_folder_narrowed_in_sql_is_the_filesystem_judgement(db_session, tree, spelled):
    from directory_watcher import _safe_relative_path

    folder = os.path.join(str(tree["base"]), *spelled.rstrip("/").split("/")) + ("/" if spelled.endswith("/") else "")
    every = db_session.query(models.FileIngestionLog).all()
    judged = sorted(log.id for log in every if _safe_relative_path(log.filepath, folder) is not None)
    narrowed = sorted(log.id for log in db_session.query(models.FileIngestionLog).filter(
        reread._under_folder(models.FileIngestionLog.filepath, folder)))
    assert judged, "CANARY: the folder holds rows"
    assert narrowed == judged
    assert sorted(log.id for log, _rel in reread.select_logs(db_session, ("FAILED", "SUCCESS"), folder=folder)) == judged
