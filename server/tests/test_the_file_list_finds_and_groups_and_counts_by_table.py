# -*- coding: utf-8 -*-
"""The file ingestion page's server half (총괄 e390600d6 2·3): GET /admin/file-ingestion/logs finds by table · status ·
name · folder · since/until through the re-read's own filter, and groups by folder or reason; GET
/admin/file-ingestion/tables counts each table's records by state with its last time."""
import os
from datetime import datetime, timedelta, timezone

from database import models
from ingestion import reread


def _log(db, table, path, status, reason=None, at=None):
    row = models.FileIngestionLog(filename=os.path.basename(path), filepath=path, table_name=table, status=status,
                                  reason=reason, retry_count=0)
    if at is not None:
        row.created_at = row.updated_at = at
    db.add(row)
    return row


def test_the_list_finds_groups_and_the_tables_count(client, db_session, tmp_path):
    lot_a, lot_ab = tmp_path / "share" / "LOT_A", tmp_path / "share" / "LOT_AB"
    for folder in (lot_a / "W1", lot_a / "W2", lot_ab / "W1"):
        folder.mkdir(parents=True)
    old = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)
    new = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
    rows = [
        _log(db_session, "insp", str(lot_a / "W1" / "bmap.txt"), "SUCCESS", at=new),
        _log(db_session, "insp", str(lot_a / "W2" / "bmap.txt"), "FAILED", "ValueError: line 3", at=new),
        _log(db_session, "insp", str(lot_a / "W2" / "notes.csv"), "FAILED", "ValueError: line 3", at=new),
        _log(db_session, "insp", str(lot_ab / "W1" / "BMAP.txt"), "SUCCESS", at=new),
        _log(db_session, "insp", str(lot_a / "W1" / "bmap_old.txt"), "SUCCESS", at=old),
        _log(db_session, "voids", str(lot_a / "W1" / "bmap.txt"), "PENDING_RETRY", at=old),
    ]
    db_session.commit()
    ids = [row.id for row in rows]

    def ask(**params):
        res = client.get("/admin/file-ingestion/logs", params=dict(limit=50, **params))
        assert res.status_code == 200, res.text
        return res.json()

    got = ask(table="insp", name="BMAP", folder=str(lot_a), since="2026-10-19")
    assert sorted(r["id"] for r in got["data"]) == [ids[0], ids[1]], got["data"]        # not LOT_AB, not the old one
    assert {r["folder"] for r in got["data"]} == {str(lot_a / "W1"), str(lot_a / "W2")}
    assert "groups" not in got
    assert [r["id"] for r in ask(table="insp", status="FAILED")["data"]] == [ids[2], ids[1]]
    assert [r["id"] for r in ask(until="2026-10-19")["data"]] == [ids[5], ids[4]]

    by_folder = ask(table="insp", folder=str(lot_a), group="folder")["groups"]
    assert sorted(by_folder, key=lambda g: g["key"]) == [{"key": "w1", "label": "W1", "count": 2, "failed": 0},
                                                         {"key": "w2", "label": "W2", "count": 2, "failed": 2}]
    by_reason = {g["key"]: (g["count"], g["failed"]) for g in ask(table="insp", group="reason")["groups"]}
    assert by_reason == {None: (3, 0), "ValueError: line 3": (2, 2)}, by_reason
    by_status = {g["key"]: (g["count"], g["failed"]) for g in ask(table="insp", name="bmap", group="status")["groups"]}
    assert by_status == {"SUCCESS": (3, 0), "FAILED": (1, 1)}, by_status       # the chips' counts, under the name too

    # the re-read and the search take the same rows for the same words
    picked = reread.select_logs(db_session, ("SUCCESS", "FAILED"), table="insp", folder=str(lot_a))
    assert sorted(log.id for log, _rel in picked) == sorted(r["id"] for r in ask(table="insp", folder=str(lot_a))["data"])

    assert client.get("/admin/file-ingestion/logs", params={"group": "day"}).status_code == 400
    assert client.get("/admin/file-ingestion/logs", params={"since": "yesterday"}).status_code == 400

    tables = {t["table_name"]: t for t in client.get("/admin/file-ingestion/tables").json()["data"]}
    assert (tables["insp"]["total"], tables["insp"]["by_status"]) == (5, {"SUCCESS": 3, "FAILED": 2})
    assert (tables["voids"]["total"], tables["voids"]["by_status"]) == (1, {"PENDING_RETRY": 1})
    assert tables["insp"]["last_at"][:16] == "2026-10-20T09:00" and tables["voids"]["last_at"][:16] == "2026-10-18T09:00"


def test_a_folder_group_below_a_chosen_folder_is_its_first_folder(client, db_session, tmp_path):
    """총괄 10-20: a wafer folder holds one file, so grouped by the file's own folder each group was one file and the
    screen grouped again «one folder up». Below a chosen folder the key is the first folder after the path_key prefix
    that picked the row - so in path_key's spelling, lower case - and the label its stored spelling."""
    lot = tmp_path / "LOT"
    failed = {"STEP1": 1, "STEP2": 0, "STEP3": 2}
    for step, n_failed in failed.items():
        for w in range(3):
            path = lot / step / ("W%d" % w) / "bmap.txt"
            path.parent.mkdir(parents=True)
            path.write_text("x", encoding="utf-8")
            _log(db_session, "insp", str(path), "FAILED" if w < n_failed else "SUCCESS",
                 "ValueError: %s" % step if w < n_failed else None)
    db_session.commit()

    def groups(group="folder", **params):
        res = client.get("/admin/file-ingestion/logs", params=dict(table="insp", group=group, limit=50, **params))
        assert res.status_code == 200, res.text
        body = res.json()
        counted = [(g["key"], g["count"]) for g in body["groups"]]
        rows = {}
        for row in body["data"]:
            rows[row["group_key"]] = rows.get(row["group_key"], 0) + 1
        assert sorted(rows.items(), key=str) == sorted(counted, key=str), (group, params)  # a row's key = its group's
        assert sum(n for _key, n in counted) == body["total"], (group, params)        # every picked row in one group
        assert group == "folder" or all(g["label"] == g["key"] for g in body["groups"])
        return sorted(((g["key"], g["count"], g["failed"]) for g in body["groups"]), key=str)

    assert all("group_key" not in row for row in client.get("/admin/file-ingestion/logs").json()["data"])
    assert groups("reason") == sorted([(None, 6, 0), ("ValueError: STEP1", 1, 1), ("ValueError: STEP3", 2, 2)],
                                      key=str)
    assert groups("status", folder=str(lot)) == [("FAILED", 3, 3), ("SUCCESS", 6, 0)]

    assert groups(folder=str(lot)) == [("step1", 3, 1), ("step2", 3, 0), ("step3", 3, 2)]
    if os.path.normcase("A") == "a":                       # a folder spelled in another case picks and groups alike
        assert groups(folder=str(lot).upper() + "/") == [("step1", 3, 1), ("step2", 3, 0), ("step3", 3, 2)]
    assert groups(folder=str(lot / "STEP3")) == [("w0", 1, 1), ("w1", 1, 1), ("w2", 1, 0)]
    labels = {g["key"]: g["label"] for g in client.get("/admin/file-ingestion/logs", params={
        "table": "insp", "group": "folder", "folder": str(lot)}).json()["groups"]}
    assert labels == {"step1": "STEP1", "step2": "STEP2", "step3": "STEP3"}, labels

    # one folder in two spellings (Windows reads them as one): one group, drawn by its stored spelling
    _log(db_session, "spelt", str(lot / "step1" / "W8" / "b.txt"), "FAILED")
    _log(db_session, "spelt", str(lot / "STEP1" / "W9" / "a.txt"), "FAILED")     # the newest: the list's first row
    db_session.commit()
    spelt = client.get("/admin/file-ingestion/logs", params={"table": "spelt", "group": "folder",
                                                             "folder": str(lot)}).json()
    assert [(g["key"], g["label"], g["count"]) for g in spelt["groups"]] == [("step1", "STEP1", 2)], spelt["groups"]
    assert [row["group_key"] for row in spelt["data"]] == ["step1", "step1"]
    assert groups() == sorted(((str(lot / step / ("W%d" % w)), 1, int(w < n)) for step, n in failed.items()
                               for w in range(3)), key=str)                        # no folder: as before


def test_a_file_is_found_by_a_part_of_its_folder(client, db_session, tmp_path):
    """소유자 10-21 「경로는 인식 못 하나?」: two external files of one name, told apart by a folder - Name reads the path."""
    rows = [_log(db_session, "voids", str(tmp_path / "ext" / "LOTQ7" / "W01" / "voids.json"), "SUCCESS"),
            _log(db_session, "voids", str(tmp_path / "ext" / "LOTQ8" / "W01" / "voids.json"), "SUCCESS")]
    db_session.commit()

    got = client.get("/admin/file-ingestion/logs", params={"name": "lotq7", "limit": 50}).json()

    assert [r["id"] for r in got["data"]] == [rows[0].id], got["data"]
    either = client.get("/admin/file-ingestion/logs", params={"name": "LOTQ8/w01", "limit": 50}).json()
    assert [r["id"] for r in either["data"]] == [rows[1].id], either["data"]        # either separator
