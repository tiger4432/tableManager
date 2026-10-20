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
    assert sorted(by_folder, key=lambda g: g["key"]) == [{"key": str(lot_a / "W1"), "count": 2, "failed": 0},
                                                         {"key": str(lot_a / "W2"), "count": 2, "failed": 2}]
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
