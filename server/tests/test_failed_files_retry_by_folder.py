# -*- coding: utf-8 -*-
"""Retry every failed file under one folder, and see how many first (총괄 fab40ed69 ②,
소유자 「폴더 아래 선택해서 한꺼번에 필요」).

🔴 BY FOLDER BOUNDARY: `.../A` takes what is under A and never `.../AB`. The judgement is the
one the watcher uses for external roots (`_safe_relative_path`), in the filesystem's case, so
a folder typed in another case or with the other separator selects the same files. FAILED only;
the preview writes nothing, and its count is the count that runs.
"""
import os

import pytest

from database import models
from ingestion import checkpoint

URL = "/admin/file-ingestion/retry-failed"


@pytest.fixture
def tree(tmp_path, db_session, monkeypatch):
    monkeypatch.setenv("DECOUPLED", "True")
    base = tmp_path / "share"

    def add(rel, status="FAILED"):
        path = str(base.joinpath(*rel.split("/")))
        # A raws row; one with no source is judged by where its file lies (총괄 10-23).
        checkpoint.note_file(db_session, "t", path, status=status, source="raws")

    for rel in ("A/x/f1.csv", "A/x/f2.csv", "A/f3.csv", "B/g1.csv", "B/g2.csv", "AB/h1.csv"):
        add(rel)
    add("A/ok.csv", "SUCCESS")
    add("A/busy.csv", "PENDING")
    db_session.commit()
    return base


def _statuses(db_session):
    db_session.expire_all()
    return {row.filename: row.status for row in db_session.query(models.FileChecklist).all()}


def test_the_preview_counts_what_is_under_the_folder_and_writes_nothing(client, db_session, tree):
    before = _statuses(db_session)

    body = client.post(URL, params={"folder": str(tree / "A"), "preview": True}).json()

    assert (body["status"], body["count"], body["by_folder"]) == ("preview", 3, {".": 1, "x": 2})
    assert _statuses(db_session) == before


def test_retry_takes_exactly_the_failed_files_under_the_folder(client, db_session, tree):
    preview = client.post(URL, params={"folder": str(tree / "A"), "preview": True}).json()

    client.post(URL, params={"folder": str(tree / "A")})

    after = _statuses(db_session)
    retried = sorted(name for name, status in after.items() if status == "PENDING_RETRY")
    assert retried == ["f1.csv", "f2.csv", "f3.csv"] and len(retried) == preview["count"]
    assert after["h1.csv"] == "FAILED", "AB is not under A"
    assert (after["g1.csv"], after["g2.csv"]) == ("FAILED", "FAILED")
    assert (after["ok.csv"], after["busy.csv"]) == ("SUCCESS", "PENDING")


@pytest.mark.skipif(os.name != "nt", reason="case and separators are Windows' rule")
def test_a_folder_in_another_case_or_separator_is_the_same_folder(client, tree):
    other = str(tree / "A").upper().replace("\\", "/") + "/"

    body = client.post(URL, params={"folder": other, "preview": True}).json()

    assert body["count"] == 3


def test_a_folder_with_nothing_failed_says_so(client, db_session, tree):
    before = _statuses(db_session)

    body = client.post(URL, params={"folder": str(tree / "C")}).json()

    assert body["count"] == 0 and body["message"] == "No failed file under %s" % (tree / "C")
    assert _statuses(db_session) == before


def test_a_preview_without_a_folder_writes_nothing(client, db_session, tree):
    before = _statuses(db_session)

    body = client.post(URL, params={"preview": True}).json()

    assert (body["status"], body["count"]) == ("preview", 6)
    assert _statuses(db_session) == before


def test_read_by_takes_only_the_failed_files_that_table_read(client, db_session, tree):
    """총괄 10-20: two tables' failed files under one folder - `read_by` takes one table's; the preview's count is the
    count handed over, and `table` (read from the disk into a table) with it is refused."""
    path = str(tree / "A" / "x" / "u1.csv")
    checkpoint.note_file(db_session, "u", path, status="FAILED", source="raws")
    db_session.commit()
    folder = str(tree / "A")

    preview = client.post(URL, params={"folder": folder, "read_by": "u", "preview": True}).json()
    body = client.post(URL, params={"folder": folder, "read_by": "u"}).json()

    after = _statuses(db_session)
    assert (preview["count"], body["count"]) == (1, 1)
    assert sorted(name for name, status in after.items() if status == "PENDING_RETRY") == ["u1.csv"]
    assert (after["f1.csv"], after["f2.csv"], after["f3.csv"]) == ("FAILED", "FAILED", "FAILED")
    refused = client.post(URL, params={"folder": folder, "read_by": "u", "table": "t"})
    assert refused.status_code == 400 and "read_by" in refused.json()["detail"]
